"""Explicit inspect/confirm attachment; never substitute a private App Server."""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, HTTPException
from pex_protocol.project_identity import ProjectOrigin
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from pex_bridge.adapters.codex import CodexAdapter
from pex_bridge.adapters.codex_bin import resolve_codex_bin
from pex_bridge.adapters.codex_shared import CodexSharedAppServerTransport
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.adapters.codex_subscription import (
    CodexExistingThreadSubscription,
    CodexSelectedThread,
    CodexSubscriptionAuthorization,
)
from pex_bridge.codex_received_journal import CodexReceivedJournal
from pex_bridge.local_origin_config import (
    LocalOriginBindingMismatch,
    LocalOriginChoice,
    load_local_origin_choice,
    save_local_origin_choice,
)
from pex_bridge.local_workspace import measure_local_directory, require_same_local_directory
from pex_bridge.workspace_binding import (
    WorkspaceBinding,
    require_current_workspace,
    require_local_locator_consistency,
    require_locator_directory,
)

MAX_PENDING = 4
SELECTION_TTL_SECONDS = 60
ATTACH_TIMEOUT_SECONDS = 45


class SharedCodexInspect(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    socket_path: str = Field(min_length=1, max_length=4096)
    thread_id: str = Field(min_length=1, max_length=512)
    project_id: str = Field(min_length=1, max_length=512)
    cwd: str = Field(min_length=1, max_length=4096)


class SharedCodexSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    inspection_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    selection_id: str = Field(pattern=r"^[a-f0-9]{64}$")


class SharedCodexConfirm(SharedCodexSelection):
    allow_resume: StrictBool


class LocalOriginUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    origin: ProjectOrigin
    expected_revision: int | None = Field(ge=1)
    expected_choice_id: str | None = Field(pattern=r"^[a-f0-9]{32}$")
    confirm_local_origin: StrictBool
    allow_storage_rebind: StrictBool = False


@dataclass
class _Pending:
    coordinator: CodexExistingThreadSubscription
    selected: CodexSelectedThread
    expiry: asyncio.Task
    deadline: float
    project_binding: str
    workspace_binding: WorkspaceBinding


class SharedCodexAttachments:
    def __init__(self) -> None:
        self.pending: dict[str, _Pending] = {}
        self.lock = asyncio.Lock()
        self.active: tuple[str, str, CodexSharedAdapter] | None = None
        self.last_detached: tuple[str, str, dict] | None = None
        self.closed = False

    async def _expire(self, inspection_id: str, deadline: float) -> None:
        await asyncio.sleep(max(0.0, deadline - asyncio.get_running_loop().time()))
        async with self.lock:
            pending = self.pending.pop(inspection_id, None)
        if pending is not None:
            await pending.coordinator.transport.close()

    async def close_pending(self) -> None:
        async with self.lock:
            self.closed = True
            pending, self.pending = list(self.pending.values()), {}
            active, self.active = self.active, None
            self.last_detached = None
        for item in pending:
            item.expiry.cancel()
        await asyncio.gather(*(item.expiry for item in pending), return_exceptions=True)
        await asyncio.gather(
            *(item.coordinator.transport.close() for item in pending), return_exceptions=True
        )
        if active is not None:
            adapter = active[2]
            pump = adapter._pump_task
            if pump is not None:
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)
            await adapter.transport.close()

    def _require_open(self) -> None:
        if self.closed:
            raise HTTPException(409, "The Codex attachment manager is shutting down.")

    async def _require_unexpired(self, inspection_id: str, pending: _Pending) -> None:
        # The expiry task cannot acquire our lock during confirmation. Admission
        # must therefore check monotonic time again after fallible authority I/O.
        if asyncio.get_running_loop().time() < pending.deadline:
            return
        self.pending.pop(inspection_id, None)
        pending.expiry.cancel()
        await asyncio.gather(pending.expiry, return_exceptions=True)
        await pending.coordinator.transport.close()
        raise HTTPException(409, "Codex selection expired or does not match.")

    @staticmethod
    def _adopt_session(adapter: CodexSharedAdapter, session) -> None:
        adapter.session = session
        adapter.sessions[session.id] = session
        adapter._normalizer.sessions[session.id] = session

    @staticmethod
    async def _settle_publication(operation):
        """Finish one bounded Store transaction before releasing the registry lock.

        Cancellation cannot establish whether SQLite committed. Shield the one
        operation (never retry it), publish its result, then propagate cancellation.
        This handles task cancellation, not process crashes or power loss.
        """
        task = asyncio.create_task(operation)
        cancelled = False
        while True:
            try:
                return await asyncio.shield(task), cancelled
            except asyncio.CancelledError:
                if task.cancelled():
                    raise
                cancelled = True

    @staticmethod
    def _canonical_local_path(value: str) -> str | None:
        try:
            path = Path(value)
            if not path.is_absolute():
                return None
            return os.path.normcase(str(path.resolve()))
        except (OSError, RuntimeError, ValueError):
            return None

    @staticmethod
    def _origin_path(state) -> Path:
        # GET/status must not create a data directory. Normal bridge bootstrap
        # creates it; a missing/inaccessible directory is not a saved choice.
        return state.settings.home / "local-origin.json"

    def _origin_choice(self, state) -> LocalOriginChoice:
        choice = load_local_origin_choice(self._origin_path(state))
        if choice is None:
            raise HTTPException(409, "Confirm this installation's local origin before attaching.")
        return choice

    async def _project_binding_for_cwd(
        self,
        store,
        project_id: str,
        cwd: str,
        choice: LocalOriginChoice,
    ) -> WorkspaceBinding:
        directory = measure_local_directory(cwd)
        binding = await store.project_binding_for_authority(project_id)
        resolved = await store.resolve_project_identity(project_id)
        if resolved is not None:
            if binding != f"identity:{resolved['identity'].id}":
                raise HTTPException(409, "The selected PEX project binding changed.")
            require_local_locator_consistency(resolved["locators"], choice, directory)
            for locator in resolved["locators"]:
                try:
                    require_locator_directory(locator, choice, directory)
                except ValueError:
                    continue
                return WorkspaceBinding(
                    project_id=project_id,
                    project_binding=binding,
                    origin_choice=choice,
                    directory=directory,
                    locator=locator,
                )
        elif binding.startswith("legacy:") and self._canonical_local_path(project_id) == (
            os.path.normcase(directory.cwd)
        ):
            # Only an actually unregistered key can use the legacy path route.
            # A typed key spelled like cwd must still pass its locator/origin.
            return WorkspaceBinding(
                project_id=project_id,
                project_binding=binding,
                origin_choice=choice,
                directory=directory,
                locator=None,
            )
        raise HTTPException(
            409,
            "The PEX project is not authoritatively bound to the selected workspace.",
        )

    @staticmethod
    def _registry_is_unchanged(state, old) -> bool:
        return state.adapters.codex is old and (
            getattr(old, "transport", None) is None
            or (isinstance(old, CodexSharedAdapter) and not old._connected())
        )

    async def _require_workspace_current(self, state, workspace: WorkspaceBinding) -> None:
        if not await state.store.project_id_matches_binding(
            workspace.project_id,
            workspace.project_binding,
        ):
            raise HTTPException(409, "The selected PEX project binding changed.")
        if workspace.locator is not None:
            resolved = await state.store.resolve_project_identity(workspace.project_id)
            if resolved is None or not any(
                locator == workspace.locator for locator in resolved["locators"]
            ):
                raise HTTPException(409, "The selected project locator changed; inspect again.")
            require_local_locator_consistency(
                resolved["locators"],
                workspace.origin_choice,
                workspace.directory,
            )
        require_current_workspace(workspace, self._origin_path(state))

    def _active_is_current(self, state, adapter: CodexSharedAdapter) -> bool:
        return (
            self.active is not None
            and self.active[2] is adapter
            and (state.adapters.codex is adapter)
        )

    @staticmethod
    def _new_transport(
        binary: str,
        body: SharedCodexInspect,
        workspace: WorkspaceBinding,
        inspection_id: str,
        journal_path: Path,
    ) -> CodexSharedAppServerTransport:
        # Before the first connector read: requested provenance is not a verified
        # subscription. Confirmation must never relabel these historical bytes.
        journal = CodexReceivedJournal(
            journal_path,
            inspection_id=inspection_id,
            provenance={
                "schema": "pex.codex-received-attempt.v1",
                "scope": "connector_received_bytes_not_live_authority",
                "requested_session_id": f"codex:{body.thread_id}",
                "requested_thread_id": body.thread_id,
                "requested_project_id": body.project_id,
                "requested_cwd": body.cwd,
                "requested_socket_path": body.socket_path,
                "workspace_binding_at_inspect": workspace.model_dump(mode="json"),
            },
        )
        return CodexSharedAppServerTransport(
            binary, body.socket_path, body.thread_id, receive_journal=journal,
        )

    async def inspect(self, body: SharedCodexInspect, state) -> dict:
        async with self.lock:
            self._require_open()
            if len(self.pending) >= MAX_PENDING:
                raise HTTPException(409, "Too many pending Codex selections; wait for expiry.")
            choice = self._origin_choice(state)
            workspace = await self._project_binding_for_cwd(
                state.store,
                body.project_id,
                body.cwd,
                choice,
            )
            require_current_workspace(workspace, self._origin_path(state))
            binary = resolve_codex_bin()
            if not binary:
                raise HTTPException(409, "No configured local Codex executable is available.")
            transport = None
            inspection_id = uuid4().hex
            try:
                transport = await asyncio.to_thread(
                    self._new_transport, binary, body, workspace, inspection_id,
                    state.settings.home / "codex-received.sqlite",
                )
                coordinator = CodexExistingThreadSubscription(transport)
                selected = await asyncio.wait_for(
                    coordinator.inspect_thread(
                        pex_session_id=f"codex:{body.thread_id}",
                        thread_id=body.thread_id,
                        project_id=body.project_id,
                        cwd=body.cwd,
                    ),
                    timeout=ATTACH_TIMEOUT_SECONDS,
                )
                if self._canonical_local_path(selected.cwd) != os.path.normcase(
                    workspace.directory.cwd
                ):
                    raise HTTPException(409, "Codex workspace differs from the inspection.")
                require_same_local_directory(selected.cwd, workspace.directory)
                require_current_workspace(workspace, self._origin_path(state))
                if not await state.store.project_id_matches_binding(
                    selected.project_id,
                    workspace.project_binding,
                ):
                    raise HTTPException(409, "The selected PEX project binding changed.")
            except BaseException:
                if transport is not None:
                    await transport.close()
                raise
            deadline = asyncio.get_running_loop().time() + SELECTION_TTL_SECONDS
            expiry = asyncio.create_task(self._expire(inspection_id, deadline))
            self.pending[inspection_id] = _Pending(
                coordinator,
                selected,
                expiry,
                deadline,
                workspace.project_binding,
                workspace,
            )
            return {
                "inspection_id": inspection_id,
                "selection_id": selected.selection_id,
                "session_id": selected.pex_session_id,
                "thread_id": selected.thread_id,
                "root_session_id": selected.root_session_id,
                "project_id": selected.project_id,
                "vendor_project_id": selected.vendor_project_id,
                "cwd": selected.cwd,
                "model": selected.model,
                "model_provider": selected.model_provider,
                "expires_in_seconds": SELECTION_TTL_SECONDS,
                "subscribed": False,
                "workspace_binding": workspace.model_dump(mode="json"),
                "note": (
                    "Confirm to subscribe to this existing thread. No new turn will be started."
                ),
            }

    async def confirm(self, body: SharedCodexConfirm, state) -> dict:
        if body.allow_resume is not True:
            raise HTTPException(400, "Explicit resume/subscription consent is required.")
        async with self.lock:
            self._require_open()
            if self.active is not None and self.active[:2] == (
                body.inspection_id,
                body.selection_id,
            ):
                adapter = self.active[2]
                if state.adapters.codex is adapter and adapter._connected():
                    return self._receipt(adapter)
                raise HTTPException(
                    409, "This attachment lost continuity; detach it, then inspect again."
                )
            if self.active is not None:
                raise HTTPException(
                    409, "Detach the previous shared Codex connection before confirming another."
                )
            pending = self.pending.get(body.inspection_id)
            if pending is None or pending.selected.selection_id != body.selection_id:
                raise HTTPException(409, "Codex selection expired or does not match.")
            await self._require_unexpired(body.inspection_id, pending)
            old = state.adapters.codex
            if not self._registry_is_unchanged(state, old):
                raise HTTPException(
                    409, "An existing Codex transport must be explicitly detached first."
                )
            selected = pending.selected
            require_current_workspace(pending.workspace_binding, self._origin_path(state))
            if not await state.store.project_id_matches_binding(
                selected.project_id, pending.project_binding
            ):
                raise HTTPException(409, "The selected PEX project binding changed.")
            if not self._registry_is_unchanged(state, old):
                raise HTTPException(409, "Codex attachment changed during confirmation.")
            existing = await state.store.get_session_for_authority(selected.pex_session_id)
            if not self._registry_is_unchanged(state, old):
                raise HTTPException(409, "Codex attachment changed during confirmation.")
            existing_binding_matches = bool(
                existing is None
                or (
                    existing.project_id
                    and await state.store.project_id_matches_binding(
                        existing.project_id, pending.project_binding
                    )
                )
            )
            if not self._registry_is_unchanged(state, old):
                raise HTTPException(409, "Codex attachment changed during confirmation.")
            if existing is not None and (
                not existing_binding_matches
                or (
                    existing.cwd
                    and os.path.normcase(str(Path(existing.cwd).resolve())) != selected.cwd
                )
            ):
                raise HTTPException(
                    409, "The selected thread conflicts with its existing PEX binding."
                )
            control_state = await state.store.get_session_control_state(selected.pex_session_id)
            if not self._registry_is_unchanged(state, old):
                raise HTTPException(409, "Codex attachment changed during confirmation.")
            await self._require_unexpired(body.inspection_id, pending)
            self.pending.pop(body.inspection_id)
            pending.expiry.cancel()
            await asyncio.gather(pending.expiry, return_exceptions=True)
            if not self._registry_is_unchanged(state, old):
                await pending.coordinator.transport.close()
                raise HTTPException(409, "Codex attachment changed during confirmation.")
            stopped_bare_pump = False
            try:
                # Authority may have changed while Store reads or expiry-task
                # settlement yielded. Recheck before the subscription side effect,
                # not merely before the later SQLite publication.
                await self._require_workspace_current(state, pending.workspace_binding)
                await self._require_unexpired(body.inspection_id, pending)
                if not self._registry_is_unchanged(state, old):
                    raise HTTPException(409, "Codex attachment changed during confirmation.")
                await asyncio.wait_for(
                    pending.coordinator.subscribe(
                        selected,
                        CodexSubscriptionAuthorization(
                            authorization_id=body.inspection_id,
                            selection_id=selected.selection_id,
                            endpoint_identity=selected.endpoint_identity,
                            connection_generation=selected.connection_generation,
                            pex_session_id=selected.pex_session_id,
                            thread_id=selected.thread_id,
                            project_id=selected.project_id,
                            allow_resume=True,
                        ),
                    ),
                    timeout=ATTACH_TIMEOUT_SECONDS,
                )
                adapter = CodexSharedAdapter(pending.coordinator)
                require_current_workspace(pending.workspace_binding, self._origin_path(state))
                adapter.session.metadata["workspace_binding"] = (
                    pending.workspace_binding.model_dump(mode="json")
                )
                adapter.session.capabilities = (await adapter.probe()).model_dump(mode="json")
                if not self._registry_is_unchanged(state, old):
                    raise HTTPException(409, "Codex attachment changed during confirmation.")
                if not await state.store.project_id_matches_binding(
                    selected.project_id, pending.project_binding
                ):
                    raise HTTPException(409, "The selected PEX project binding changed.")
                if not self._registry_is_unchanged(state, old):
                    raise HTTPException(409, "Codex attachment changed during confirmation.")
                pump = getattr(old, "_pump_task", None)
                if pump is not None and not pump.done():
                    stopped_bare_pump = isinstance(old, CodexAdapter) and old.transport is None
                    pump.cancel()
                    await asyncio.gather(pump, return_exceptions=True)
                if not self._registry_is_unchanged(state, old):
                    raise HTTPException(409, "Codex attachment changed during confirmation.")
                old_transport = getattr(old, "transport", None)
                if old_transport is not None:
                    await old_transport.close()
                if not self._registry_is_unchanged(state, old):
                    raise HTTPException(409, "Codex attachment changed during confirmation.")
                canonical, cancelled = await self._settle_publication(
                    state.store.publish_observer_session(
                        adapter.session,
                        expected_control_revision=(
                            control_state["control_revision"] if control_state is not None else None
                        ),
                        expected_project_binding=pending.project_binding,
                        expected_workspace=pending.workspace_binding,
                        local_origin_path=self._origin_path(state),
                    )
                )
                # All adapter replacement routes hold this manager lock. No
                # yielding is allowed between durable publication and binding.
                self._adopt_session(adapter, canonical)
                state.adapters.bind("codex", adapter)
                self.active = (body.inspection_id, body.selection_id, adapter)
                self.last_detached = None
                adapter.start_pipeline_pump(
                    state.pipeline.ingest_shared_codex_event,
                    lifecycle_ingest=state.pipeline.ingest_observer_lifecycle,
                    retention_ingest=state.pipeline.retain_shared_codex_observations,
                    provenance_loader=state.store.list_codex_correction_attributions,
                )
                if cancelled:
                    raise asyncio.CancelledError
                return self._receipt(adapter)
            except BaseException:
                if (
                    self.active is None
                    or self.active[2].transport is not pending.coordinator.transport
                ):
                    try:
                        await pending.coordinator.transport.close()
                    finally:
                        # Restore only a bare pump this attempt actually stopped.
                        # A successful shielded commit already replaced registry
                        # ownership and must never resurrect the previous adapter.
                        if (
                            stopped_bare_pump
                            and state.adapters.codex is old
                            and old.transport is None
                            and not self.closed
                        ):
                            old.start_pipeline_pump(state.pipeline.ingest_event)
                raise

    async def detach(self, body: SharedCodexSelection, state) -> dict:
        async with self.lock:
            self._require_open()
            if self.active is None and self.last_detached is not None:
                inspection_id, selection_id, receipt = self.last_detached
                if (inspection_id, selection_id) == (
                    body.inspection_id,
                    body.selection_id,
                ):
                    return {**receipt, "replayed": True}
            if self.active is None or self.active[:2] != (body.inspection_id, body.selection_id):
                raise HTTPException(
                    409, "This request does not identify the active shared connection."
                )
            adapter = self.active[2]
            if state.adapters.codex is not adapter:
                raise HTTPException(409, "The active Codex adapter changed.")
            pump = adapter._pump_task
            if pump is not None:
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)
                if not self._active_is_current(state, adapter):
                    raise HTTPException(409, "The active Codex adapter changed.")
            await adapter.transport.close()
            if not self._active_is_current(state, adapter):
                raise HTTPException(409, "The active Codex adapter changed.")
            from pex_protocol.enums import SessionStatus

            adapter.session.status = SessionStatus.DETACHED
            adapter.session.capabilities = (await adapter.probe()).model_dump(mode="json")
            if not self._active_is_current(state, adapter):
                raise HTTPException(409, "The active Codex adapter changed.")
            control_state = await state.store.get_session_control_state(adapter.session.id)
            if control_state is None or not self._active_is_current(state, adapter):
                raise HTTPException(409, "The active Codex session authority changed.")
            canonical, cancelled = await self._settle_publication(
                state.store.publish_observer_session(
                    adapter.session,
                    expected_control_revision=control_state["control_revision"],
                    expected_project_binding=control_state["project_binding"],
                )
            )
            self._adopt_session(adapter, canonical)
            replacement = CodexAdapter()
            state.adapters.bind("codex", replacement)
            self.active = None
            replacement.start_pipeline_pump(state.pipeline.ingest_event)
            receipt = {
                "ok": True,
                "detached": True,
                "worker_stopped": False,
                "replayed": False,
            }
            self.last_detached = (body.inspection_id, body.selection_id, receipt)
            if cancelled:
                raise asyncio.CancelledError
            return receipt

    def origin_status(self, state) -> dict:
        try:
            choice = load_local_origin_choice(self._origin_path(state))
        except LocalOriginBindingMismatch as exc:
            return {
                "status": "reconfirmation_required",
                "choice": exc.choice.model_dump(mode="json"),
            }
        except (ValueError, OSError):
            return {
                "status": "unavailable",
                "choice": None,
                "note": "Local origin could not be verified; existing data was not changed.",
            }
        return {
            "status": "configured" if choice else "unconfigured",
            "choice": choice.model_dump(mode="json") if choice else None,
        }

    async def update_origin(self, body: LocalOriginUpdate, state) -> dict:
        if body.confirm_local_origin is not True:
            raise HTTPException(400, "Explicit local-origin confirmation is required.")
        async with self.lock:
            self._require_open()
            if self.active is not None:
                raise HTTPException(
                    409, "Detach the shared Codex connection before changing origin."
                )

            async def save_and_invalidate():
                choice = await asyncio.to_thread(
                    save_local_origin_choice,
                    self._origin_path(state),
                    body.origin,
                    expected_revision=body.expected_revision,
                    expected_choice_id=body.expected_choice_id,
                    allow_storage_rebind=body.allow_storage_rebind,
                )
                pending, self.pending = list(self.pending.values()), {}
                for item in pending:
                    item.expiry.cancel()
                await asyncio.gather(*(item.expiry for item in pending), return_exceptions=True)
                await asyncio.gather(*(item.coordinator.transport.close() for item in pending))
                return {
                    "status": "configured",
                    "choice": choice.model_dump(mode="json"),
                    "invalidated_selections": len(pending),
                }

            result, cancelled = await self._settle_publication(save_and_invalidate())
            if cancelled:
                raise asyncio.CancelledError
            return result

    async def status(self, state) -> dict:
        async with self.lock:
            connection = None
            if self.active is not None:
                inspection_id, selection_id, adapter = self.active
                current = state.adapters.codex is adapter
                pump = adapter._pump_task
                observing = (
                    current and adapter._connected() and pump is not None and not pump.done()
                )
                connection = {
                    "inspection_id": inspection_id,
                    "selection_id": selection_id,
                    "state": "observing"
                    if observing
                    else ("disconnected" if current else "ownership_changed"),
                    "can_detach": current and not self.closed,
                    "session_id": adapter.session.id,
                    "thread_id": adapter.session.vendor_session_id,
                    "project_id": adapter.session.project_id,
                    "cwd": adapter.session.cwd,
                    "workspace_binding": adapter.session.metadata.get("workspace_binding"),
                    "observation_coverage": adapter.session.metadata.get("observation_coverage"),
                    "worker_delivery_enabled": False,
                }
            now = asyncio.get_running_loop().time()
            pending_status = []
            for key, item in self.pending.items():
                valid = False
                if not self.closed and item.deadline > now and self.active is None:
                    try:
                        await self._require_workspace_current(state, item.workspace_binding)
                        valid = True
                    except (ValueError, OSError, HTTPException):
                        pass
                remaining = max(0, item.deadline - asyncio.get_running_loop().time())
                pending_status.append(
                    {
                        "inspection_id": key,
                        "selection_id": item.selected.selection_id,
                        "session_id": item.selected.pex_session_id,
                        "expires_in_seconds": remaining,
                        "can_confirm": valid and remaining > 0,
                    }
                )
            return {
                "origin": self.origin_status(state),
                "connection": connection,
                "pending": pending_status,
                "worker_delivery_enabled": False,
            }

    @staticmethod
    def _receipt(adapter: CodexSharedAdapter) -> dict:
        return {
            "ok": True,
            "kind": "shared",
            "support": "observe_only",
            "session_id": adapter.session.id,
            "subscription": asdict(adapter.subscription.state.receipt),
            "worker_delivery_enabled": False,
            "workspace_binding": adapter.session.metadata.get("workspace_binding"),
        }


def register_shared_codex_routes(app, state, require_token, require_operator_token) -> None:
    @app.get("/v1/local-workspace-origin")
    async def get_local_origin(_: object = Depends(require_operator_token)):
        async with state.codex_shared_attachments.lock:
            return state.codex_shared_attachments.origin_status(state)

    @app.patch("/v1/local-workspace-origin")
    async def update_local_origin(
        body: LocalOriginUpdate, _: object = Depends(require_operator_token)
    ):
        try:
            return await state.codex_shared_attachments.update_origin(body, state)
        except HTTPException:
            raise
        except (ValueError, OSError) as exc:
            raise HTTPException(
                409, "Local origin save could not be confirmed; reload before retrying."
            ) from exc

    @app.get("/v1/adapters/codex/shared/status")
    async def shared_status(_: object = Depends(require_operator_token)):
        return await state.codex_shared_attachments.status(state)

    @app.post("/v1/adapters/codex/shared/inspect")
    async def inspect_shared(body: SharedCodexInspect, _: None = Depends(require_token)):
        try:
            return await state.codex_shared_attachments.inspect(body, state)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(409, "Shared Codex selection could not be verified.") from exc

    @app.post("/v1/adapters/codex/shared/confirm")
    async def confirm_shared(
        body: SharedCodexConfirm,
        _: object = Depends(require_operator_token),
    ):
        try:
            return await state.codex_shared_attachments.confirm(body, state)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                409, "Shared Codex attachment failed; no worker delivery was enabled."
            ) from exc

    @app.post("/v1/adapters/codex/shared/detach")
    async def detach_shared(
        body: SharedCodexSelection,
        _: object = Depends(require_operator_token),
    ):
        try:
            return await state.codex_shared_attachments.detach(body, state)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                409,
                "Shared Codex detach could not be finalized; "
                "reload connection state before retrying.",
            ) from exc
