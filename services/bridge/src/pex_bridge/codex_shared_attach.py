"""Explicit inspect/confirm attachment; never substitute a private App Server."""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, HTTPException
from pex_protocol.project_identity import PathPlatform, ProjectLocatorKind
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


@dataclass
class _Pending:
    coordinator: CodexExistingThreadSubscription
    selected: CodexSelectedThread
    expiry: asyncio.Task
    deadline: float
    project_binding: str


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

    async def _project_binding_for_cwd(self, store, project_id: str, cwd: str) -> str:
        binding = await store.project_binding_for_authority(project_id)
        if self._canonical_local_path(project_id) == cwd:
            return binding
        resolved = await store.resolve_project_identity(project_id)
        expected_platform = PathPlatform.WINDOWS if os.name == "nt" else PathPlatform.POSIX
        if resolved is not None and any(
            locator.kind == ProjectLocatorKind.LOCAL_PATH
            and locator.platform == expected_platform
            and self._canonical_local_path(locator.raw) == cwd
            for locator in resolved["locators"]
        ):
            return binding
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

    def _active_is_current(self, state, adapter: CodexSharedAdapter) -> bool:
        return (
            self.active is not None
            and self.active[2] is adapter
            and (state.adapters.codex is adapter)
        )

    async def inspect(self, body: SharedCodexInspect, state) -> dict:
        async with self.lock:
            self._require_open()
            if len(self.pending) >= MAX_PENDING:
                raise HTTPException(409, "Too many pending Codex selections; wait for expiry.")
            binary = resolve_codex_bin()
            if not binary:
                raise HTTPException(409, "No configured local Codex executable is available.")
            transport = None
            try:
                transport = await asyncio.to_thread(
                    CodexSharedAppServerTransport, binary, body.socket_path, body.thread_id
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
                project_binding = await self._project_binding_for_cwd(
                    state.store, selected.project_id, selected.cwd
                )
            except BaseException:
                if transport is not None:
                    await transport.close()
                raise
            inspection_id = uuid4().hex
            deadline = asyncio.get_running_loop().time() + SELECTION_TTL_SECONDS
            expiry = asyncio.create_task(self._expire(inspection_id, deadline))
            self.pending[inspection_id] = _Pending(
                coordinator,
                selected,
                expiry,
                deadline,
                project_binding,
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

    @staticmethod
    def _receipt(adapter: CodexSharedAdapter) -> dict:
        return {
            "ok": True,
            "kind": "shared",
            "support": "observe_only",
            "session_id": adapter.session.id,
            "subscription": asdict(adapter.subscription.state.receipt),
            "worker_delivery_enabled": False,
        }


def register_shared_codex_routes(app, state, require_token, require_operator_token) -> None:
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
