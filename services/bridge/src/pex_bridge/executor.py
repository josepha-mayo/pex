from __future__ import annotations

import asyncio
import ctypes
import errno
import inspect
import json
import os
import sys
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.capabilities import PermissionResponseMode
from pex_protocol.context import ContextBundle
from pex_protocol.enums import HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.overlay import Overlay, locally_proven_session_overlay
from pex_protocol.session import HarnessSession
from pydantic import ValidationError

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.base import (
    AdapterMessageResult,
    CursorHookPreparation,
    resolve_adapter_message_result,
)
from pex_bridge.local_workspace import require_same_local_directory
from pex_bridge.store import (
    Store,
    _canonical_lifecycle_path,
    _lifecycle_entity_identity,
    utcnow,
)
from pex_bridge.workspace_binding import require_current_workspace

OVERLAY_ADAPTER_TIMEOUT_SECONDS = 10.0
OVERLAY_EXPIRY_PAGE_SIZE = 1_000
LIFECYCLE_ADAPTER_TIMEOUT_SECONDS = 15.0
HANDOFF_ADAPTER_TIMEOUT_SECONDS = 10.0
MESSAGE_ADAPTER_TIMEOUT_SECONDS = 10.0
PERMISSION_ADAPTER_TIMEOUT_SECONDS = 15.0
FOCUS_ADAPTER_TIMEOUT_SECONDS = 5.0
MAX_ACTION_TEXT_CHARS = 65_536
MAX_CONTEXT_BUNDLE_BYTES = 262_144
MAX_LIFECYCLE_CONFIG_BYTES = 65_536
MAX_CLEANUP_RESOURCES = 128
AT_FDCWD = -100
RENAME_NOREPLACE = 1
RENAME_EXCL = 0x00000004
_DispatchResult = TypeVar("_DispatchResult")


@dataclass(frozen=True)
class ActionExecutionResult:
    outcome: str
    worker_delivery_receipt: dict[str, str] | None = None
    hook_preparation_receipt: dict[str, str] | None = None


@dataclass(frozen=True)
class ClaimedMainEffect:
    """An exact claim reference, not a reusable execution permission."""

    event_id: str
    owner: str
    effect_id: str
    effect_version: int
    check_local_authority: Callable[[], None]


class _WorkspaceDispatchRefused(Exception):
    """Only raised before an adapter operation is entered, never after it."""


def _message_execution_result(
    result: bool | AdapterMessageResult | CursorHookPreparation,
    *,
    session: HarnessSession,
    accepted_outcome: str,
    rejected_outcome: str,
) -> str | ActionExecutionResult:
    resolution = resolve_adapter_message_result(result, session=session)
    if resolution.status == "rejected":
        return rejected_outcome
    if resolution.status == "delivery_uncertain":
        uncertain_outcomes = {
            "sent": "send_delivery_uncertain",
            "continued": "continue_delivery_uncertain",
            "verification_requested": "verification_delivery_uncertain",
            "handoff_injected": "handoff_delivery_uncertain",
        }
        try:
            return uncertain_outcomes[accepted_outcome]
        except KeyError as exc:
            raise RuntimeError(
                f"unsupported message acceptance outcome: {accepted_outcome}"
            ) from exc
    if resolution.status == "hook_prepared":
        if resolution.hook_preparation_receipt is None:
            return "send_delivery_uncertain"
        return ActionExecutionResult(
            outcome="hook_followup_prepared_delivery_uncertain",
            hook_preparation_receipt=resolution.hook_preparation_receipt,
        )
    if resolution.worker_delivery_receipt is None:
        return accepted_outcome
    return ActionExecutionResult(
        outcome=accepted_outcome,
        worker_delivery_receipt=resolution.worker_delivery_receipt,
    )


class ActionExecutor:
    def __init__(self, adapters: AdapterRegistry, store: Store, channels=None) -> None:
        self.adapters = adapters
        self.store = store
        self.channels = channels
        self._overlay_lock = asyncio.Lock()

    async def _workspace_dispatch(
        self,
        session: HarnessSession,
        operation: Callable[[], Awaitable[_DispatchResult]],
        *,
        sources: Sequence[HarnessSession] = (),
    ) -> _DispatchResult:
        # This coroutine runs inside wait_for's task: a check performed before
        # constructing that task would miss changes while it waits to start.
        try:
            witnesses = [
                (target, await self.store.require_session_workspace_current(target))
                for target in (session, *sources)
            ]
            # Store commit/connection closure and later source checks can yield.
            # Sample trusted witnesses once more with no await before adapter I/O.
            for target, witness in witnesses:
                if witness is not None:
                    binding, origin_path = witness
                    require_current_workspace(binding, origin_path)
                    require_same_local_directory(target.cwd, binding.directory)
        except Exception as exc:
            raise _WorkspaceDispatchRefused from exc
        return await operation()

    async def _workspace_is_current(self, session) -> bool:
        async def checked() -> bool:
            return True

        try:
            return await self._workspace_dispatch(session, checked)
        except _WorkspaceDispatchRefused:
            return False

    async def execute(
        self,
        action: ProposedAction,
        verdict: PolicyVerdict,
        *,
        human_authorized: bool = False,
        lifecycle_resolution_id: str | None = None,
        operation_owner_id: str | None = None,
        operation_parent_effect_id: str | None = None,
        main_effect_context: ClaimedMainEffect | None = None,
    ) -> str | ActionExecutionResult:
        if action.type == InterventionType.NOOP:
            return "noop"
        if action.type == InterventionType.RESPOND_PERMISSION:
            if verdict == PolicyVerdict.DENY:
                # DENY rejects the proposed PEX side effect. It is not itself an
                # authorization to send a worker-facing permission denial.
                return "denied_by_policy"
            session = await self.store.get_session(action.session_id)
            adapter = self.adapters.for_session(action.session_id)
            if session is None or adapter is None:
                return "permission_missing_session_or_adapter"
            if not await self._workspace_is_current(session):
                return "workspace_authority_changed"
            try:
                response_mode = PermissionResponseMode(
                    session.capabilities.get("permission_response_mode", "none")
                )
            except ValueError:
                response_mode = PermissionResponseMode.NONE
            inline = response_mode in {
                PermissionResponseMode.INLINE,
                PermissionResponseMode.BOTH,
            }
            if verdict == PolicyVerdict.ASK_HUMAN:
                if inline:
                    # The hook is blocked waiting for this response. Returning
                    # ASK/defer lets the harness own the human prompt; there is
                    # no valid request to resolve later from the PEX UI.
                    return "permission_delegated_to_harness"
                session.status = SessionStatus.NEEDS_DECISION
                await self.store.upsert_session(session)
                return "permission_awaiting_human"
            requested = str(action.payload.get("decision") or "").strip().lower()
            if (
                not requested
                and verdict == PolicyVerdict.ALLOW
                and action.payload.get("decision_source") == "local_policy"
            ):
                decision = "allow"
            elif requested in {"allow", "deny"}:
                decision = requested
            else:
                return "permission_invalid_decision"
            request_id = str(action.payload.get("request_id") or "")
            if not request_id or len(request_id) > 512:
                return "permission_invalid_request"
            if action.goal_id != session.goal_id:
                return "action_goal_mismatch"
            if inline:
                return f"permission_{decision}_inline"
            if response_mode == PermissionResponseMode.NONE:
                return "permission_delivery_unsupported"
            try:
                ok = await asyncio.wait_for(
                    self._workspace_dispatch(
                        session, lambda: adapter.respond_permission(session, request_id, decision),
                    ),
                    timeout=PERMISSION_ADAPTER_TIMEOUT_SECONDS,
                )
            except _WorkspaceDispatchRefused:
                return "workspace_authority_changed"
            except Exception:
                # The external harness may have received a response before the
                # transport raised. Surface uncertainty and never claim success.
                return f"permission_{decision}_delivery_uncertain"
            return f"permission_{decision}" if ok else f"permission_{decision}_failed"
        if verdict == PolicyVerdict.DENY:
            return "denied_by_policy"
        if verdict == PolicyVerdict.ASK_HUMAN:
            session = await self.store.get_session(action.session_id)
            if session:
                if action.goal_id != session.goal_id:
                    return "action_goal_mismatch"
                if not await self._workspace_is_current(session):
                    return "workspace_authority_changed"
                # Never trust a model-supplied status snapshot. Preserve a
                # stopped source as stopped; the pending intervention itself is
                # the durable decision signal.
                action.payload["previous_session_status"] = session.status.value
                if session.status != SessionStatus.STOPPED:
                    session.status = SessionStatus.NEEDS_DECISION
                    await self.store.upsert_session(session)
            return "awaiting_human"

        # Overlay operations own their immutable session/project authority in
        # the Store.  Reserve them before consulting mutable live session state
        # so a terminal receipt can replay through pause, quarantine, or an
        # A->B project rebind without probing or touching an adapter.
        if action.type == InterventionType.APPLY_OVERLAY:
            raw_overlay = action.payload.get("overlay")
            if not isinstance(raw_overlay, dict):
                return "overlay_invalid"
            try:
                overlay = Overlay.model_validate(raw_overlay)
            except ValidationError:
                return "overlay_invalid"
            if overlay.session_id != action.session_id:
                return "overlay_session_mismatch"
            adapter_name = _overlay_adapter_name(overlay.session_id)
            if adapter_name is None:
                return "overlay_unproven_or_authority_expanding"
            return await self._apply_overlay(
                overlay,
                adapter_name=adapter_name,
                expected_goal_id=action.goal_id,
                owner_intervention_id=operation_owner_id,
                parent_effect_id=operation_parent_effect_id,
            )
        if action.type == InterventionType.REVERT_OVERLAY:
            overlay_id = str(action.payload.get("overlay_id") or "")
            if not overlay_id:
                return "overlay_revert_invalid"
            return await self.revert_overlay(
                overlay_id,
                expected_session_id=action.session_id,
                expected_goal_id=action.goal_id,
                reason="action_requested",
                trigger_intervention_id=operation_owner_id,
                parent_effect_id=operation_parent_effect_id,
            )

        session = await self.store.get_session(action.session_id)
        if session is None:
            return "missing_session_or_adapter"
        if action.goal_id != session.goal_id:
            return "action_goal_mismatch"
        if action.type in {
            InterventionType.START_AGENT,
            InterventionType.STOP_AGENT,
            InterventionType.FORK_PROBE,
            InterventionType.CLEANUP,
        }:
            # A Boolean or caller-selected id is not an execution capability.
            # Re-read the Store-owned dispatch marker and its frozen bindings
            # immediately before any adapter or filesystem I/O.
            if not human_authorized or not lifecycle_resolution_id:
                return "lifecycle_human_authorization_required"
            granted_session = await self._validated_lifecycle_dispatch_session(
                action,
                lifecycle_resolution_id,
            )
            if granted_session is None:
                return "lifecycle_dispatch_grant_invalid"
            session = granted_session
            # Lifecycle helpers may attach ephemeral execution outputs such as
            # a child session id. Never mutate the Store-frozen action carried
            # by the durable intervention.
            action = action.model_copy(deep=True)
        if action.type == InterventionType.CLEANUP:
            return await self._cleanup(
                action,
                session,
                lifecycle_resolution_id=lifecycle_resolution_id,
            )
        if not await self._workspace_is_current(session):
            return "workspace_authority_changed"
        adapter = self.adapters.for_session(action.session_id)
        if adapter is None:
            return "missing_session_or_adapter"

        from pex_bridge.codex_correction import requires_correction

        if requires_correction(session, action.model_dump(mode="json")):
            return await self._execute_shared_codex_correction(
                action, session, adapter, main_effect_context,
            )

        try:
            if action.type == InterventionType.START_AGENT:
                return await self._start_agent(action, session, adapter)
            if action.type == InterventionType.STOP_AGENT:
                return await self._stop_agent(
                    session,
                    adapter,
                    defer_control_projection=lifecycle_resolution_id is not None,
                )
            if action.type == InterventionType.FORK_PROBE:
                return await self._fork_probe(action, session, adapter)
        except _WorkspaceDispatchRefused:
            return "workspace_authority_changed"

        text = str(action.payload.get("text") or "")
        if len(text) > MAX_ACTION_TEXT_CHARS:
            return "action_text_too_large"
        if action.type in {InterventionType.SEND_NUDGE, InterventionType.INJECT_CONTEXT}:
            if not text.strip():
                return "send_skipped_empty"
            try:
                ok = await asyncio.wait_for(
                    self._workspace_dispatch(session, lambda: adapter.send_message(session, text)),
                    timeout=MESSAGE_ADAPTER_TIMEOUT_SECONDS,
                )
            except _WorkspaceDispatchRefused:
                return "workspace_authority_changed"
            except Exception:
                return "send_delivery_uncertain"
            return _message_execution_result(
                ok,
                session=session,
                accepted_outcome="sent",
                rejected_outcome="send_failed",
            )
        if action.type == InterventionType.REQUEST_VERIFICATION:
            if not text.strip():
                return "verification_skipped_no_specific_probe"
            try:
                ok = await asyncio.wait_for(
                    self._workspace_dispatch(session, lambda: adapter.send_message(session, text)),
                    timeout=MESSAGE_ADAPTER_TIMEOUT_SECONDS,
                )
            except _WorkspaceDispatchRefused:
                return "workspace_authority_changed"
            except Exception:
                return "verification_delivery_uncertain"
            return _message_execution_result(
                ok,
                session=session,
                accepted_outcome="verification_requested",
                rejected_outcome="verification_failed",
            )
        if action.type == InterventionType.FRESH_HANDOFF:
            try:
                raw = action.payload.get("bundle")
                if isinstance(raw, dict):
                    bundle = ContextBundle.model_validate(raw)
                    if _json_bytes(bundle.model_dump(mode="json")) > MAX_CONTEXT_BUNDLE_BYTES:
                        return "handoff_context_too_large"
                    expected_goal = action.goal_id or session.goal_id
                    if (
                        bundle.target_session_id != session.id
                        or (expected_goal is not None and bundle.goal_id != expected_goal)
                        or not bundle.source_session_ids
                        or len(bundle.source_session_ids) > 64
                        or len(set(bundle.source_session_ids)) != len(bundle.source_session_ids)
                        or session.id in bundle.source_session_ids
                        or any(len(source_id) > 512 for source_id in bundle.source_session_ids)
                        or any(
                            not session.project_id
                            or _project_key(item.project_id) != _project_key(session.project_id)
                            or (item.goal_id is not None and item.goal_id != bundle.goal_id)
                            for item in bundle.items
                        )
                    ):
                        return "handoff_context_mismatch"
                    sources = await asyncio.gather(
                        *(
                            self.store.get_session(source_id)
                            for source_id in bundle.source_session_ids
                        )
                    )
                    if any(
                        source is None
                        or source.goal_id != bundle.goal_id
                        or not source.project_id
                        or not session.project_id
                        or _project_key(source.project_id) != _project_key(session.project_id)
                        for source in sources
                    ):
                        return "handoff_context_mismatch"
                    ok = await asyncio.wait_for(
                        self._workspace_dispatch(
                            session, lambda: adapter.inject_context(session, bundle),
                            sources=sources,
                        ),
                        timeout=HANDOFF_ADAPTER_TIMEOUT_SECONDS,
                    )
                else:
                    if not text.strip():
                        return "handoff_skipped_no_specific_context"
                    ok = await asyncio.wait_for(
                        self._workspace_dispatch(
                            session, lambda: adapter.send_message(session, text),
                        ),
                        timeout=HANDOFF_ADAPTER_TIMEOUT_SECONDS,
                    )
            except _WorkspaceDispatchRefused:
                return "workspace_authority_changed"
            except ValidationError:
                return "handoff_failed"
            except TimeoutError:
                # ``wait_for`` can time out after the vendor accepted the
                # irreversible handoff.  Treat that boundary as unresolved so
                # the durable receipt suppresses every later redelivery.
                return "handoff_delivery_uncertain"
            except Exception:
                # Delivery may have reached the vendor before transport failed.
                return "handoff_delivery_uncertain"
            return _message_execution_result(
                ok,
                session=session,
                accepted_outcome="handoff_injected",
                rejected_outcome="handoff_failed",
            )
        if action.type == InterventionType.CONTINUE_SESSION:
            try:
                ok = await asyncio.wait_for(
                    self._workspace_dispatch(
                        session, lambda: adapter.continue_or_resume(session, text or None),
                    ),
                    timeout=MESSAGE_ADAPTER_TIMEOUT_SECONDS,
                )
            except _WorkspaceDispatchRefused:
                return "workspace_authority_changed"
            except Exception:
                return "continue_delivery_uncertain"
            return _message_execution_result(
                ok,
                session=session,
                accepted_outcome="continued",
                rejected_outcome="continue_failed",
            )
        if action.type == InterventionType.FOCUS_UI:
            try:
                ok = await asyncio.wait_for(
                    self._workspace_dispatch(session, lambda: adapter.focus_ui(session)),
                    timeout=FOCUS_ADAPTER_TIMEOUT_SECONDS,
                )
            except _WorkspaceDispatchRefused:
                return "workspace_authority_changed"
            except Exception:
                return "focus_delivery_uncertain"
            return "focused" if ok else "focus_failed"
        if action.type == InterventionType.ASK_HUMAN:
            session.status = SessionStatus.NEEDS_DECISION
            await self.store.upsert_session(session)
            return "escalated"
        if action.type == InterventionType.ANNOTATE:
            return "annotated"
        if action.type == InterventionType.NOTIFY:
            text = str(action.payload.get("text") or "").strip()
            if not text:
                return "notify_skipped_empty"
            hub = self.channels
            if hub is None:
                return "notification_not_configured"
            return hub.deliver(text, kind="notify")
        return f"unhandled_{action.type}"

    async def _execute_shared_codex_correction(
        self,
        action: ProposedAction,
        session: HarnessSession,
        adapter,
        context: ClaimedMainEffect | None,
    ) -> str | ActionExecutionResult:
        """Use only a persisted claim and the private same-connection route."""
        from pex_bridge.adapters.codex_shared import SharedCodexTextDispatchRejected
        from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
        from pex_bridge.codex_correction import canonical
        from pex_bridge.codex_input_baseline import CodexInputBaselineSnapshot
        from pex_bridge.store import _validate_observer_input_baseline

        if (
            not isinstance(context, ClaimedMainEffect)
            or not callable(context.check_local_authority)
            or not isinstance(adapter, CodexSharedAdapter)
        ):
            return "codex_claimed_dispatch_required"
        # Freeze caller-owned objects before any Store or transport await.
        action = action.model_copy(deep=True)
        session = session.model_copy(deep=True)
        expected_action = action.model_dump(mode="json")
        arguments = {
            "event_id": context.event_id,
            "owner": context.owner,
            "effect_id": context.effect_id,
            "effect_version": context.effect_version,
            "expected_action": expected_action,
        }

        def check_local() -> None:
            checked = context.check_local_authority()
            if inspect.isawaitable(checked):
                if inspect.iscoroutine(checked):
                    checked.close()
                raise ValueError("local policy callback must be synchronous")
            if checked is not None:
                raise ValueError("local policy callback must return None")

        try:
            check_local()
            grant = await self.store.validate_main_event_effect_dispatch(**arguments)
            if grant.get("granted") is not True:
                return "codex_dispatch_authority_refused"
            correction = grant["effect"]["payload"]["codex_correction"]
            correction_json = canonical(correction)
            event = await self.store.get_event(context.event_id)
            if event is None or event.session_id != session.id or event.goal_id != action.goal_id:
                return "codex_dispatch_trigger_mismatch"
            baseline = event.metadata.get("pex_observer_snapshot", {}).get("input_baseline")
            _validate_observer_input_baseline(baseline)
            accepted_baseline = CodexInputBaselineSnapshot(**baseline)
            if not accepted_baseline.complete:
                return "codex_dispatch_input_incomplete"
            attribution_records = await self.store.list_codex_correction_attributions(session)
            witness = await self.store.require_session_workspace_current(session)
            if witness is None:
                return "codex_dispatch_workspace_missing"

            def validate_store() -> None:
                # Independent connections/loop: never submit work to the
                # application loop blocked by this synchronous final callback.
                latest = asyncio.run(self.store.validate_main_event_effect_dispatch(**arguments))
                if (
                    latest.get("granted") is not True
                    or canonical(latest["effect"]["payload"].get("codex_correction"))
                    != correction_json
                ):
                    raise ValueError("claimed correction authority changed")

            def final_check() -> None:
                check_local()
                with ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="pex-codex-dispatch-check",
                ) as pool:
                    pool.submit(validate_store).result()
                # Database connection cleanup and transport locks may outlast
                # earlier samples. These local checks immediately precede the
                # adapter's input fence and transport enqueue checks.
                check_local()
                if self.adapters.for_session(session.id) is not adapter:
                    raise ValueError("registered shared adapter changed")
                require_current_workspace(*witness)
                require_same_local_directory(session.cwd, witness[0].directory)

        except Exception:
            return "codex_dispatch_preparation_refused"

        try:
            result = await adapter._dispatch_claimed_text(
                correction_json=correction_json,
                attribution_records=attribution_records,
                accepted_baseline=accepted_baseline,
                final_authority_check=final_check,
            )
        except SharedCodexTextDispatchRejected:
            return "codex_dispatch_refused"
        except asyncio.CancelledError:
            # Pipeline seals the already-claimed effect uncertain and never
            # retries. The transport retains its pre/post-enqueue distinction.
            raise
        except Exception:
            return "codex_delivery_uncertain"
        accepted_outcome = {
            InterventionType.SEND_NUDGE: "sent",
            InterventionType.INJECT_CONTEXT: "sent",
            InterventionType.REQUEST_VERIFICATION: "verification_requested",
            InterventionType.CONTINUE_SESSION: "continued",
        }[action.type]
        return _message_execution_result(
            result, session=session, accepted_outcome=accepted_outcome,
            rejected_outcome="codex_dispatch_failed",
        )

    async def _validated_lifecycle_dispatch_session(
        self,
        action: ProposedAction,
        lifecycle_resolution_id: str,
    ) -> HarnessSession | None:
        """Return the exact Store-authorized lifecycle target, or fail closed."""

        try:
            grant = await self.store.validate_lifecycle_dispatch_grant(
                lifecycle_resolution_id,
                action,
            )
            if not isinstance(grant, dict) or grant.get("granted") is not True:
                return None
            resolution = grant.get("resolution")
            intervention = grant.get("intervention")
            if not isinstance(resolution, dict) or not isinstance(intervention, dict):
                return None
            session = HarnessSession.model_validate(grant.get("session"))
            if resolution.get("intervention_id") != lifecycle_resolution_id:
                return None
            if intervention.get("id") != lifecycle_resolution_id:
                return None
            if intervention.get("proposed_action") != action.model_dump(mode="json"):
                return None
            if (
                intervention.get("session_id") != session.id
                or intervention.get("goal_id") != session.goal_id
                or action.session_id != session.id
                or action.goal_id != session.goal_id
            ):
                return None
            return session
        except (LookupError, PermissionError, RuntimeError, TypeError, ValueError):
            return None

    async def _refresh_lifecycle_capability(
        self,
        session,
        adapter,
        capability: str,
        *,
        persist: bool = True,
    ) -> bool:
        """Re-probe immediately before a lifecycle side effect and fail closed."""
        try:
            capabilities = await asyncio.wait_for(
                self._workspace_dispatch(session, adapter.probe), timeout=2.0,
            )
        except _WorkspaceDispatchRefused:
            raise
        except Exception:
            return False
        if not await self._workspace_is_current(session):
            raise _WorkspaceDispatchRefused
        session.capabilities = capabilities.model_dump(mode="json")
        if persist:
            await self.store.upsert_session(session)
        return capabilities.supports(capability)

    async def _start_agent(self, action: ProposedAction, source, adapter) -> str:
        project = str(action.payload.get("project") or "").strip()
        prompt = str(action.payload.get("prompt") or "").strip()
        config = action.payload.get("config")
        if (
            not project
            or len(project) > 4096
            or not prompt
            or len(prompt) > MAX_ACTION_TEXT_CHARS
            or (config is not None and not isinstance(config, dict))
            or _json_bytes(config or {}) > MAX_LIFECYCLE_CONFIG_BYTES
        ):
            return "agent_start_invalid"
        if source.project_id and _project_key(project) != _project_key(source.project_id):
            return "agent_start_project_mismatch"
        expected_goal = action.goal_id or source.goal_id
        requested_goal = (
            str(config.get("goal_id") or "").strip() if isinstance(config, dict) else ""
        )
        if requested_goal and requested_goal != expected_goal:
            return "agent_start_goal_mismatch"
        # Validate the complete local request before even probing the external
        # harness. A rejected lifecycle action must have zero adapter effects.
        if not await self._refresh_lifecycle_capability(source, adapter, "start"):
            return "agent_start_unsupported"
        try:
            created = await asyncio.wait_for(
                self._workspace_dispatch(
                    source, lambda: adapter.start_session(
                        project, prompt, config if isinstance(config, dict) else None,
                    ),
                ),
                timeout=LIFECYCLE_ADAPTER_TIMEOUT_SECONDS,
            )
        except _WorkspaceDispatchRefused:
            raise
        except Exception:
            # The harness may have created a session before transport failure.
            return "agent_start_delivery_uncertain"
        if created is None:
            return "agent_start_failed"
        # Preserve the vendor-backed identity even when a later validation or
        # persistence step is uncertain, so the audit can point at the orphan.
        action.payload["started_session_id"] = created.id
        if (
            created.id == source.id
            or created.harness_type != source.harness_type
            or (
                created.project_id is not None
                and _project_key(created.project_id) != _project_key(project)
            )
        ):
            return "agent_start_identity_invalid"
        if await self.store.get_session(created.id) is not None:
            return "agent_start_persist_conflict"
        if created.goal_id is not None and expected_goal and created.goal_id != expected_goal:
            return "agent_start_identity_invalid"
        created.goal_id = expected_goal
        created.project_id = project
        created.metadata.update(
            {
                "lifecycle_parent_session_id": source.id,
                "lifecycle_action": InterventionType.START_AGENT.value,
            }
        )
        if not created.capabilities:
            created.capabilities = dict(source.capabilities)
        try:
            await self.store.upsert_session(created)
        except Exception:
            return "agent_start_persist_failed"
        return f"agent_started:{created.id}"

    async def _stop_agent(
        self,
        session,
        adapter,
        *,
        defer_control_projection: bool = False,
    ) -> str:
        if not await self._refresh_lifecycle_capability(
            session,
            adapter,
            "stop",
            persist=not defer_control_projection,
        ):
            return "agent_stop_unsupported"
        try:
            stopped = await asyncio.wait_for(
                self._workspace_dispatch(session, lambda: adapter.stop(session)),
                timeout=LIFECYCLE_ADAPTER_TIMEOUT_SECONDS,
            )
        except _WorkspaceDispatchRefused:
            raise
        except Exception:
            return "agent_stop_delivery_uncertain"
        if not stopped:
            return "agent_stop_failed"
        session.status = SessionStatus.STOPPED
        session.last_activity = utcnow()
        if defer_control_projection:
            return "agent_stopped"
        try:
            await self.store.upsert_session(session)
        except Exception:
            return "agent_stopped_persist_failed"
        return "agent_stopped"

    async def _fork_probe(self, action: ProposedAction, session, adapter) -> str:
        raw = action.payload.get("bundle")
        if not isinstance(raw, dict):
            return "probe_fork_invalid"
        try:
            bundle = ContextBundle.model_validate(raw)
        except ValidationError:
            return "probe_fork_invalid"
        if _json_bytes(bundle.model_dump(mode="json")) > MAX_CONTEXT_BUNDLE_BYTES:
            return "probe_fork_invalid"
        expected_goal = action.goal_id or session.goal_id
        if (
            (expected_goal and bundle.goal_id != expected_goal)
            or bundle.target_session_id != session.id
            or session.id not in bundle.source_session_ids
        ):
            return "probe_fork_context_mismatch"
        # Parsing and binding checks are local. Do not probe the harness until
        # the complete fork request is known to target this exact session/goal.
        if not await self._refresh_lifecycle_capability(session, adapter, "fork"):
            return "probe_fork_unsupported"
        try:
            child = await asyncio.wait_for(
                self._workspace_dispatch(
                    session, lambda: adapter.fork_or_fresh_handoff(session, bundle),
                ),
                timeout=LIFECYCLE_ADAPTER_TIMEOUT_SECONDS,
            )
        except _WorkspaceDispatchRefused:
            raise
        except Exception:
            return "probe_fork_delivery_uncertain"
        if child is None:
            return "probe_fork_failed"
        action.payload["forked_session_id"] = child.id
        if (
            child.id == session.id
            or child.harness_type != session.harness_type
            or (
                session.project_id is not None
                and child.project_id is not None
                and _project_key(child.project_id) != _project_key(session.project_id)
            )
        ):
            return "probe_fork_identity_invalid"
        if await self.store.get_session(child.id) is not None:
            return "probe_fork_persist_conflict"
        if child.goal_id is not None and expected_goal and child.goal_id != expected_goal:
            return "probe_fork_identity_invalid"
        child.goal_id = expected_goal
        child.project_id = session.project_id
        child.metadata.update(
            {
                "lifecycle_parent_session_id": session.id,
                "lifecycle_action": InterventionType.FORK_PROBE.value,
                "probe": True,
            }
        )
        if not child.capabilities:
            child.capabilities = dict(session.capabilities)
        try:
            await self.store.upsert_session(child)
        except Exception:
            return "probe_fork_persist_failed"
        pair_id = f"probe_{uuid4().hex[:12]}"
        approaches = action.payload.get("approaches")
        cleaned = (
            [str(item).strip() for item in approaches[:2] if str(item).strip()]
            if isinstance(approaches, list)
            else []
        )
        parent_objective = str(action.payload.get("parent_objective") or "").strip()
        approach_a = cleaned[0] if cleaned else parent_objective
        approach_b = cleaned[1] if len(cleaned) > 1 else str(bundle.next_objective or "")
        parent = await self.store.get_session(session.id) or session
        parent_metadata = dict(parent.metadata or {})
        parent_metadata["speculative"] = {
            "pair_id": pair_id,
            "role": "a",
            "approach": approach_a,
            "sibling_session_id": child.id,
        }
        parent.metadata = parent_metadata
        child_metadata = dict(child.metadata or {})
        child_metadata["speculative"] = {
            "pair_id": pair_id,
            "role": "b",
            "approach": approach_b,
            "sibling_session_id": parent.id,
        }
        child.metadata = child_metadata
        try:
            await self.store.upsert_session(parent)
            await self.store.upsert_session(child)
        except Exception:
            return "probe_fork_persist_failed"
        if parent_objective:
            try:
                await asyncio.wait_for(
                    self._workspace_dispatch(
                        parent, lambda: adapter.continue_or_resume(parent, parent_objective),
                    ),
                    timeout=MESSAGE_ADAPTER_TIMEOUT_SECONDS,
                )
            except Exception:
                # The isolated child still exists; parent continue is best-effort.
                pass
        return f"probe_forked:{child.id}"

    async def _cleanup(
        self,
        action: ProposedAction,
        session: HarnessSession,
        *,
        lifecycle_resolution_id: str | None = None,
    ) -> str:
        """Quarantine only the Store-frozen manifest granted for this dispatch.

        ``action`` and ``session`` are intentionally not consulted here.  The
        caller has already validated them against the lifecycle resolution, and
        the Store operation is the sole mutable, crash-recoverable filesystem
        authority.  Keeping the parameters makes the boundary explicit and
        preserves a fail-closed result for direct/internal calls without a
        resolution capability.
        """

        del action, session
        if not lifecycle_resolution_id:
            return "cleanup_lifecycle_resolution_required"
        try:
            reservation = await self.store.reserve_cleanup_operation(
                lifecycle_resolution_id
            )
        except (LookupError, PermissionError, TypeError, ValueError):
            return "cleanup_reservation_refused"
        except Exception:
            return "cleanup_reservation_uncertain"
        operation = reservation.get("operation") if isinstance(reservation, dict) else None
        if not isinstance(operation, dict):
            return "cleanup_reservation_uncertain"
        if operation.get("state") != "reserved":
            return self._cleanup_operation_result(operation)

        operation_id = str(operation.get("id") or "")
        if not operation_id:
            return "cleanup_reservation_uncertain"
        try:
            started = await self.store.start_cleanup_operation(operation_id)
        except (LookupError, PermissionError, TypeError, ValueError):
            return "cleanup_start_refused"
        except Exception:
            return "cleanup_start_uncertain"
        if not isinstance(started, dict):
            return "cleanup_start_uncertain"
        if started.get("granted") is not True:
            canonical = started.get("operation")
            return (
                self._cleanup_operation_result(canonical)
                if isinstance(canonical, dict)
                else "cleanup_start_uncertain"
            )
        manifest = started.get("manifest")
        canonical = started.get("operation")
        if (
            not isinstance(canonical, dict)
            or canonical.get("id") != operation_id
            or canonical.get("state") != "dispatching"
            or not isinstance(manifest, list)
            or not manifest
            or len(manifest) > MAX_CLEANUP_RESOURCES
        ):
            return "cleanup_start_uncertain"

        cancellation: asyncio.CancelledError | None = None
        for entry in manifest:
            try:
                self._move_cleanup_entry(entry)
            except asyncio.CancelledError as exc:
                cancellation = exc
                break
            except Exception:
                # A prior successful move is never rolled back.  The complete
                # identity observation below is the only truthful outcome.
                break

        outcomes = [self._classify_cleanup_entry(entry) for entry in manifest]
        finalize_task = asyncio.create_task(
            self.store.finalize_cleanup_operation(
                operation_id,
                outcomes=outcomes,
                finished_at=utcnow(),
            ),
            name=f"cleanup-finalize:{operation_id}",
        )
        try:
            finalized = await asyncio.shield(finalize_task)
        except asyncio.CancelledError:
            # The rename may already have happened.  Finish the durable exact
            # observation before propagating cancellation to the caller.
            try:
                await finalize_task
            except Exception:
                pass
            raise
        except Exception:
            if cancellation is not None:
                raise cancellation from None
            return "cleanup_finalization_uncertain"
        if cancellation is not None:
            raise cancellation
        if not isinstance(finalized, dict):
            return "cleanup_finalization_uncertain"
        terminal = finalized.get("operation")
        return (
            self._cleanup_operation_result(terminal)
            if isinstance(terminal, dict)
            else "cleanup_finalization_uncertain"
        )

    async def restore_cleanup(
        self,
        intervention_id: str,
        legacy_manifest: object | None = None,
        *,
        authorized_by: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object] | str:
        """Restore only the Store-frozen manifest bound to one operator request.

        The optional positional argument is a deliberately inert compatibility
        boundary for older internal callers.  A raw session/manifest pair never
        grants restore authority and continues to fail closed.
        """

        if (
            legacy_manifest is not None
            or authorized_by is None
            or idempotency_key is None
        ):
            return "cleanup_restore_reservation_required"
        try:
            reservation = await self.store.reserve_restore_operation(
                intervention_id,
                authorized_by=authorized_by,
                idempotency_key=idempotency_key,
            )
        except (LookupError, PermissionError, TypeError, ValueError):
            return self._restore_result("cleanup_restore_reservation_refused")
        except Exception:
            return self._restore_result("cleanup_restore_reservation_uncertain")
        operation = reservation.get("operation") if isinstance(reservation, dict) else None
        if not isinstance(operation, dict):
            return self._restore_result("cleanup_restore_reservation_uncertain")
        replayed = bool(reservation.get("replayed"))
        if operation.get("state") != "reserved":
            return self._restore_operation_result(operation, replayed=replayed)

        operation_id = str(operation.get("id") or "")
        if not operation_id:
            return self._restore_result(
                "cleanup_restore_reservation_uncertain",
                operation=operation,
                replayed=replayed,
            )
        try:
            started = await self.store.start_restore_operation(operation_id)
        except (LookupError, PermissionError, TypeError, ValueError):
            return self._restore_result(
                "cleanup_restore_start_refused",
                operation=operation,
                replayed=replayed,
            )
        except Exception:
            return self._restore_result(
                "cleanup_restore_start_uncertain",
                operation=operation,
                replayed=replayed,
            )
        if not isinstance(started, dict):
            return self._restore_result(
                "cleanup_restore_start_uncertain",
                operation=operation,
                replayed=replayed,
            )
        if started.get("granted") is not True:
            canonical = started.get("operation")
            return (
                self._restore_operation_result(
                    canonical,
                    replayed=bool(started.get("replayed")) or replayed,
                )
                if isinstance(canonical, dict)
                else self._restore_result(
                    "cleanup_restore_start_uncertain",
                    operation=operation,
                    replayed=replayed,
                )
            )
        manifest = started.get("manifest")
        canonical = started.get("operation")
        if (
            not isinstance(canonical, dict)
            or canonical.get("id") != operation_id
            or canonical.get("state") != "dispatching"
            or not isinstance(manifest, list)
            or not manifest
            or len(manifest) > 256
        ):
            return self._restore_result(
                "cleanup_restore_start_uncertain",
                operation=(canonical if isinstance(canonical, dict) else operation),
                replayed=replayed,
            )

        cancellation: asyncio.CancelledError | None = None
        for entry in manifest:
            try:
                self._move_restore_entry(entry)
            except asyncio.CancelledError as exc:
                cancellation = exc
                break
            except Exception:
                # Preserve earlier successful restores.  The complete exact
                # observation below is the only safe recovery authority.
                break

        outcomes = [self._classify_restore_entry(entry) for entry in manifest]
        finalize_task = asyncio.create_task(
            self.store.finalize_restore_operation(
                operation_id,
                outcomes=outcomes,
                finished_at=utcnow(),
            ),
            name=f"cleanup-restore-finalize:{operation_id}",
        )
        try:
            finalized = await asyncio.shield(finalize_task)
        except asyncio.CancelledError:
            # A no-replace rename may already have committed.  Complete the
            # durable identity observation before propagating cancellation.
            try:
                await finalize_task
            except Exception:
                pass
            raise
        except Exception:
            if cancellation is not None:
                raise cancellation from None
            return self._restore_result(
                "cleanup_restore_finalization_uncertain",
                operation=canonical,
                replayed=replayed,
            )
        if cancellation is not None:
            raise cancellation
        terminal = finalized.get("operation") if isinstance(finalized, dict) else None
        return (
            self._restore_operation_result(
                terminal,
                replayed=bool(finalized.get("replayed")) or replayed,
            )
            if isinstance(terminal, dict)
            else self._restore_result(
                "cleanup_restore_finalization_uncertain",
                operation=canonical,
                replayed=replayed,
            )
        )

    @staticmethod
    def _move_restore_entry(entry: object) -> None:
        if not isinstance(entry, dict):
            raise ValueError("restore manifest entry is invalid")
        source_text = str(entry.get("source_path") or "")
        destination_text = str(entry.get("destination_path") or "")
        expected = str(entry.get("entity_fingerprint") or "")
        if not source_text or not destination_text or not expected:
            raise ValueError("restore manifest entry is incomplete")

        source = _canonical_lifecycle_path(Path(source_text), must_exist=True)
        _, source_fingerprint = _lifecycle_entity_identity(source)
        if str(source) != source_text or source_fingerprint != expected:
            raise PermissionError("restore source entity changed")
        destination = Path(destination_text)
        destination_parent = _canonical_lifecycle_path(
            destination.parent,
            must_exist=True,
        )
        if (
            not destination_parent.is_dir()
            or str(destination_parent / destination.name) != destination_text
        ):
            raise PermissionError("restore destination parent changed")
        try:
            _lifecycle_entity_identity(destination)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("restore destination is occupied")

        # Revalidate both identities after all preparatory reads and immediately
        # before the atomic no-replace move.  Missing parents are never created.
        source = _canonical_lifecycle_path(Path(source_text), must_exist=True)
        _, source_fingerprint = _lifecycle_entity_identity(source)
        if str(source) != source_text or source_fingerprint != expected:
            raise PermissionError("restore source changed immediately before move")
        destination_parent = _canonical_lifecycle_path(
            destination.parent,
            must_exist=True,
        )
        if (
            not destination_parent.is_dir()
            or str(destination_parent / destination.name) != destination_text
        ):
            raise PermissionError("restore destination changed immediately before move")
        try:
            _lifecycle_entity_identity(destination)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("restore destination changed immediately before move")
        ActionExecutor._atomic_rename_noreplace(source, destination)

    @staticmethod
    def _atomic_rename_noreplace(source: Path, destination: Path) -> None:
        """Atomically rename without replacing, or fail closed if unavailable."""

        if os.name == "nt":
            # CPython's Windows rename uses MoveFileExW without
            # MOVEFILE_REPLACE_EXISTING and fails if the destination exists.
            os.rename(source, destination)
            return
        if sys.platform.startswith("linux"):
            libc = ctypes.CDLL(None, use_errno=True)
            renameat2 = getattr(libc, "renameat2", None)
            if renameat2 is None:
                raise OSError(
                    errno.ENOTSUP,
                    "atomic no-replace rename is unavailable",
                    str(destination),
                )
            renameat2.argtypes = (
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            )
            renameat2.restype = ctypes.c_int
            result = renameat2(
                AT_FDCWD,
                os.fsencode(source),
                AT_FDCWD,
                os.fsencode(destination),
                RENAME_NOREPLACE,
            )
            if result != 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error), str(destination))
            return
        if sys.platform == "darwin":
            libc = ctypes.CDLL(None, use_errno=True)
            renamex_np = getattr(libc, "renamex_np", None)
            if renamex_np is None:
                raise OSError(
                    errno.ENOTSUP,
                    "atomic no-replace rename is unavailable",
                    str(destination),
                )
            renamex_np.argtypes = (
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.c_uint,
            )
            renamex_np.restype = ctypes.c_int
            result = renamex_np(
                os.fsencode(source),
                os.fsencode(destination),
                RENAME_EXCL,
            )
            if result != 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error), str(destination))
            return
        raise OSError(
            errno.ENOTSUP,
            "atomic no-replace rename is unavailable",
            str(destination),
        )

    @classmethod
    def _classify_restore_entry(cls, entry: object) -> dict[str, object]:
        if not isinstance(entry, dict):
            raise ValueError("restore manifest entry is invalid")
        resource_id = str(entry.get("resource_id") or "")
        expected = str(entry.get("entity_fingerprint") or "")
        source = cls._observed_cleanup_fingerprint(str(entry.get("source_path") or ""))
        destination = cls._observed_cleanup_fingerprint(
            str(entry.get("destination_path") or "")
        )
        outcome = (
            "not_restored"
            if source == expected and destination is None
            else "restored"
            if source is None and destination == expected
            else "conflict"
        )
        return {
            "resource_id": resource_id,
            "outcome": outcome,
            "source_fingerprint": source,
            "destination_fingerprint": destination,
        }

    @classmethod
    def _restore_operation_result(
        cls,
        operation: object,
        *,
        replayed: bool,
    ) -> dict[str, object]:
        if not isinstance(operation, dict):
            return cls._restore_result(
                "cleanup_restore_operation_uncertain",
                replayed=replayed,
            )
        state = str(operation.get("state") or "")
        raw_outcomes = operation.get("outcomes")
        outcomes = raw_outcomes if isinstance(raw_outcomes, list) else []
        restored = sum(
            isinstance(row, dict) and row.get("outcome") == "restored"
            for row in outcomes
        )
        not_restored = sum(
            isinstance(row, dict) and row.get("outcome") == "not_restored"
            for row in outcomes
        )
        conflicts = sum(
            isinstance(row, dict) and row.get("outcome") == "conflict"
            for row in outcomes
        )
        if state == "completed" and outcomes and restored == len(outcomes):
            code = f"cleanup_restored:{restored}"
        elif state == "failed" and outcomes and not_restored == len(outcomes):
            code = f"cleanup_restore_not_restored:{not_restored}"
        elif state == "conflict":
            code = f"cleanup_restore_conflict:{conflicts or len(outcomes)}"
        elif state == "delivery_uncertain":
            code = (
                "cleanup_restore_delivery_uncertain:"
                f"restored={restored},not_restored={not_restored},conflict={conflicts}"
            )
        elif state == "dispatching":
            code = "cleanup_restore_dispatch_in_progress"
        elif state == "reserved":
            code = "cleanup_restore_reserved_not_started"
        else:
            code = "cleanup_restore_operation_uncertain"
        return cls._restore_result(
            code,
            operation=operation,
            replayed=replayed,
        )

    @staticmethod
    def _restore_result(
        code: str,
        *,
        operation: dict[str, object] | None = None,
        replayed: bool = False,
    ) -> dict[str, object]:
        outcomes = (
            operation.get("outcomes")
            if isinstance(operation, dict)
            and isinstance(operation.get("outcomes"), list)
            else []
        )
        manifest = (
            operation.get("manifest")
            if isinstance(operation, dict)
            and isinstance(operation.get("manifest"), list)
            else []
        )
        outcome_counts = {
            name: sum(
                isinstance(row, dict) and row.get("outcome") == name
                for row in outcomes
            )
            for name in ("restored", "not_restored", "conflict")
        }
        receipt = (
            {
                "operation_id": operation.get("id"),
                "cleanup_operation_id": operation.get("cleanup_operation_id"),
                "intervention_id": operation.get("intervention_id"),
                "session_id": operation.get("session_id"),
                "goal_id": operation.get("goal_id"),
                "state": operation.get("state"),
                "version": operation.get("version"),
                "reserved_at": operation.get("reserved_at"),
                "dispatch_started_at": operation.get("dispatch_started_at"),
                "finished_at": operation.get("finished_at"),
                "resource_count": len(outcomes) if outcomes else len(manifest),
                "outcome_counts": outcome_counts,
            }
            if isinstance(operation, dict)
            else None
        )
        return {
            "ok": code.startswith("cleanup_restored:"),
            "code": code,
            "status": (
                str(operation.get("state") or "unknown")
                if isinstance(operation, dict)
                else "uncertain"
                if code.endswith("uncertain")
                else "refused"
            ),
            "replayed": replayed,
            "receipt": receipt,
        }

    @staticmethod
    def _move_cleanup_entry(entry: object) -> None:
        if not isinstance(entry, dict):
            raise ValueError("cleanup manifest entry is invalid")
        source_text = str(entry.get("source_path") or "")
        destination_text = str(entry.get("destination_path") or "")
        expected = str(entry.get("entity_fingerprint") or "")
        if not source_text or not destination_text or not expected:
            raise ValueError("cleanup manifest entry is incomplete")

        source = _canonical_lifecycle_path(Path(source_text), must_exist=True)
        if str(source) != source_text:
            raise PermissionError("cleanup source canonical identity changed")
        _, source_fingerprint = _lifecycle_entity_identity(source)
        if source_fingerprint != expected:
            raise PermissionError("cleanup source entity was replaced")

        destination = _canonical_lifecycle_path(
            Path(destination_text),
            must_exist=False,
        )
        if str(destination) != destination_text:
            raise PermissionError("cleanup destination canonical identity changed")
        try:
            _lifecycle_entity_identity(destination)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("cleanup destination already exists")

        destination.parent.mkdir(parents=True, exist_ok=False)
        destination = _canonical_lifecycle_path(destination, must_exist=False)
        if str(destination) != destination_text:
            raise PermissionError("cleanup destination ancestor changed")
        try:
            _lifecycle_entity_identity(destination)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("cleanup destination was created concurrently")

        # Revalidate after the only preceding mutation and immediately before
        # the frozen same-volume rename.
        source = _canonical_lifecycle_path(Path(source_text), must_exist=True)
        _, source_fingerprint = _lifecycle_entity_identity(source)
        if str(source) != source_text or source_fingerprint != expected:
            raise PermissionError("cleanup source changed immediately before move")

        destination = _canonical_lifecycle_path(
            Path(destination_text),
            must_exist=False,
        )
        if str(destination) != destination_text:
            raise PermissionError("cleanup destination changed immediately before move")
        try:
            _lifecycle_entity_identity(destination)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("cleanup destination changed immediately before move")
        source.rename(destination)

    @staticmethod
    def _observed_cleanup_fingerprint(path_text: str) -> str | None:
        try:
            canonical = _canonical_lifecycle_path(Path(path_text), must_exist=True)
            if str(canonical) != path_text:
                return "mismatch"
            _, fingerprint = _lifecycle_entity_identity(canonical)
            return fingerprint
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return "mismatch"

    @classmethod
    def _classify_cleanup_entry(cls, entry: object) -> dict[str, object]:
        if not isinstance(entry, dict):
            raise ValueError("cleanup manifest entry is invalid")
        resource_id = str(entry.get("resource_id") or "")
        expected = str(entry.get("entity_fingerprint") or "")
        source = cls._observed_cleanup_fingerprint(
            str(entry.get("source_path") or "")
        )
        destination = cls._observed_cleanup_fingerprint(
            str(entry.get("destination_path") or "")
        )
        outcome = (
            "not_moved"
            if source == expected and destination is None
            else "moved"
            if source is None and destination == expected
            else "conflict"
        )
        return {
            "resource_id": resource_id,
            "outcome": outcome,
            "source_fingerprint": source,
            "destination_fingerprint": destination,
            "classified_by": "executor_identity_observation",
        }

    @staticmethod
    def _cleanup_operation_result(operation: object) -> str:
        if not isinstance(operation, dict):
            return "cleanup_operation_uncertain"
        state = str(operation.get("state") or "")
        outcomes = operation.get("outcomes")
        rows = outcomes if isinstance(outcomes, list) else []
        moved = sum(
            isinstance(row, dict) and row.get("outcome") == "moved" for row in rows
        )
        not_moved = sum(
            isinstance(row, dict) and row.get("outcome") == "not_moved"
            for row in rows
        )
        conflicts = sum(
            isinstance(row, dict) and row.get("outcome") == "conflict" for row in rows
        )
        if state == "completed" and rows and moved == len(rows):
            return f"cleanup_quarantined:{moved}"
        if state == "failed" and rows and not_moved == len(rows):
            return f"cleanup_not_moved:{not_moved}"
        if state == "conflict":
            return f"cleanup_conflict:{conflicts or len(rows)}"
        if state == "delivery_uncertain":
            return (
                "cleanup_delivery_uncertain:"
                f"moved={moved},not_moved={not_moved},conflict={conflicts}"
            )
        if state == "dispatching":
            return "cleanup_dispatch_in_progress"
        if state == "reserved":
            return "cleanup_reserved_not_started"
        return "cleanup_operation_uncertain"

    async def _apply_overlay(
        self,
        overlay: Overlay,
        *,
        adapter_name: str,
        expected_goal_id: str | None = None,
        owner_intervention_id: str | None = None,
        parent_effect_id: str | None = None,
    ) -> str:
        if overlay.promoted:
            return "overlay_promotion_requires_explicit_user"
        if not _overlay_has_local_reversibility_proof(overlay, adapter_name):
            return "overlay_unproven_or_authority_expanding"
        rollback = {
            "adapter": adapter_name,
            "operation": "revert_overlay",
            "overlay_id": overlay.id,
        }
        if adapter_name == "opencode":
            rollback.update(
                {
                    "strategy": "bridge_active_overlay_query",
                    "scope": "session",
                    "plugin": "pex-opencode-plugin",
                    "session_id": overlay.session_id,
                }
            )
        overlay = Overlay.model_validate(
            {
                **overlay.model_dump(mode="python"),
                "applied_at": None,
                "expires_at": None,
                "reverted_at": None,
                "revert_reason": None,
                "promoted": False,
                "rollback": rollback,
            }
        )

        async with self._overlay_lock:
            try:
                operation = await self.store.reserve_overlay_apply(
                    overlay,
                    adapter_name=adapter_name,
                    owner_intervention_id=owner_intervention_id,
                    parent_effect_id=parent_effect_id,
                )
            except ValueError:
                return "overlay_id_conflict"
            except LookupError:
                return "overlay_missing_session_or_adapter"
            except PermissionError:
                return "overlay_dispatch_refused"
            if operation.get("state") != "reserved":
                return _overlay_operation_outcome(operation, kind="apply")
            operation_id = str(operation.get("operation_id") or "")
            if not operation_id:
                return "overlay_apply_reservation_uncertain"
            if (
                expected_goal_id is not None
                and operation.get("goal_id") != expected_goal_id
            ):
                skipped = await self._finalize_overlay_skipped(
                    operation_id,
                    code="action_goal_mismatch",
                )
                return _overlay_operation_outcome(skipped, kind="apply")

            adapter = self.adapters.get(adapter_name)
            session = await self.store.get_session(overlay.session_id)
            if (
                adapter is None
                or session is None
                or not _overlay_session_matches_operation(session, operation)
            ):
                skipped = await self._finalize_overlay_skipped(
                    operation_id,
                    code="overlay_missing_session_or_adapter",
                )
                return _overlay_operation_outcome(skipped, kind="apply")
            try:
                capabilities = await asyncio.wait_for(
                    self._workspace_dispatch(session, adapter.probe), timeout=2.0,
                )
            except _WorkspaceDispatchRefused:
                skipped = await self._finalize_overlay_skipped(
                    operation_id, code="workspace_authority_changed",
                )
                return _overlay_operation_outcome(skipped, kind="apply")
            except asyncio.CancelledError:
                await self._finalize_overlay_skipped(
                    operation_id,
                    code="overlay_preflight_cancelled",
                )
                raise
            except Exception:
                skipped = await self._finalize_overlay_skipped(
                    operation_id,
                    code="overlay_capability_probe_failed",
                )
                return _overlay_operation_outcome(skipped, kind="apply")
            if not capabilities.modify_config or capabilities.config_scope != "session":
                skipped = await self._finalize_overlay_skipped(
                    operation_id,
                    code="overlay_modify_config_unsupported",
                )
                return _overlay_operation_outcome(skipped, kind="apply")
            if adapter_name == "opencode" and not adapter.overlay_projection_ready(session):
                skipped = await self._finalize_overlay_skipped(
                    operation_id,
                    code="overlay_session_plugin_not_live",
                )
                return _overlay_operation_outcome(skipped, kind="apply")
            if session.harness_type == HarnessType.OPENCODE:
                from pex_bridge.overlay_runtime import compile_overlay_runtime

                try:
                    active = await self.store.active_overlays(session.id)
                    candidate_at = utcnow()
                    candidate = Overlay.model_validate(
                        {
                            **overlay.model_dump(mode="python"),
                            "applied_at": candidate_at,
                            "expires_at": candidate_at
                            + timedelta(seconds=overlay.ttl_seconds),
                        }
                    )
                    compile_overlay_runtime([*active, candidate], now=candidate_at)
                except (LookupError, PermissionError, RuntimeError, ValueError):
                    skipped = await self._finalize_overlay_skipped(
                        operation_id,
                        code="overlay_runtime_contract_invalid",
                    )
                    return _overlay_operation_outcome(skipped, kind="apply")

            if not await self._workspace_is_current(session):
                skipped = await self._finalize_overlay_skipped(
                    operation_id, code="workspace_authority_changed",
                )
                return _overlay_operation_outcome(skipped, kind="apply")
            started = await self._start_overlay_operation(
                operation,
                kind="apply",
                store_projected=adapter_name == "opencode",
                refusal_code="overlay_dispatch_refused",
            )
            terminal = await self._dispatch_overlay_grant(started, kind="apply")
            return _overlay_operation_outcome(terminal, kind="apply")

    async def revert_overlay(
        self,
        overlay_id: str | None = None,
        *,
        expected_session_id: str | None = None,
        expected_goal_id: str | None = None,
        required_owner_intervention_id: str | None = None,
        owned_by_intervention_id: str | None = None,
        trigger_intervention_id: str | None = None,
        parent_effect_id: str | None = None,
        authorized_by: str | None = None,
        idempotency_key: str | None = None,
        reason: str = "manual",
        reverted_at: datetime | None = None,
    ) -> str:
        code, _ = await self._revert_overlay_operation(
            overlay_id,
            expected_session_id=expected_session_id,
            expected_goal_id=expected_goal_id,
            required_owner_intervention_id=required_owner_intervention_id,
            owned_by_intervention_id=owned_by_intervention_id,
            trigger_intervention_id=trigger_intervention_id,
            parent_effect_id=parent_effect_id,
            authorized_by=authorized_by,
            idempotency_key=idempotency_key,
            reason=reason,
            reverted_at=reverted_at,
        )
        return code

    async def revert_overlay_receipt(
        self,
        overlay_id: str | None = None,
        *,
        expected_session_id: str | None = None,
        expected_goal_id: str | None = None,
        required_owner_intervention_id: str | None = None,
        owned_by_intervention_id: str | None = None,
        trigger_intervention_id: str | None = None,
        parent_effect_id: str | None = None,
        authorized_by: str | None = None,
        idempotency_key: str | None = None,
        reason: str = "manual",
        reverted_at: datetime | None = None,
    ) -> dict:
        """Return a path-free exact receipt for REST/Desktop overlay Undo."""

        code, operation = await self._revert_overlay_operation(
            overlay_id,
            expected_session_id=expected_session_id,
            expected_goal_id=expected_goal_id,
            required_owner_intervention_id=required_owner_intervention_id,
            owned_by_intervention_id=owned_by_intervention_id,
            trigger_intervention_id=trigger_intervention_id,
            parent_effect_id=parent_effect_id,
            authorized_by=authorized_by,
            idempotency_key=idempotency_key,
            reason=reason,
            reverted_at=reverted_at,
        )
        return _overlay_structured_result(code, operation)

    async def _revert_overlay_operation(
        self,
        overlay_id: str | None,
        *,
        expected_session_id: str | None,
        expected_goal_id: str | None,
        required_owner_intervention_id: str | None,
        owned_by_intervention_id: str | None,
        trigger_intervention_id: str | None,
        parent_effect_id: str | None,
        authorized_by: str | None,
        idempotency_key: str | None,
        reason: str,
        reverted_at: datetime | None,
    ) -> tuple[str, dict | None]:
        async with self._overlay_lock:
            try:
                if owned_by_intervention_id is not None:
                    if authorized_by is None or idempotency_key is None:
                        return "overlay_revert_invalid", None
                    operation = await self.store.reserve_owned_overlay_revert(
                        owned_by_intervention_id,
                        authorized_by=authorized_by,
                        idempotency_key=idempotency_key,
                        reason=reason,
                        now=reverted_at,
                    )
                else:
                    if not overlay_id:
                        return "overlay_revert_invalid", None
                    operation = await self.store.reserve_overlay_revert(
                        overlay_id,
                        expected_session_id=expected_session_id,
                        required_owner_intervention_id=required_owner_intervention_id,
                        trigger_intervention_id=trigger_intervention_id,
                        parent_effect_id=parent_effect_id,
                        authorized_by=authorized_by,
                        idempotency_key=idempotency_key,
                        reason=reason,
                        now=reverted_at,
                    )
            except LookupError:
                return "overlay_not_found", None
            except PermissionError as exc:
                message = str(exc)
                if message == "overlay session mismatch":
                    return "overlay_session_mismatch", None
                if "overlay owner" in message or "different intervention" in message:
                    return "overlay_owner_mismatch", None
                if message == "overlay apply was not delivered":
                    return "overlay_apply_not_delivered", None
                return "overlay_revert_refused", None
            except ValueError:
                return "overlay_revert_invalid", None
            if operation.get("state") != "reserved":
                if operation.get("state") == "delivered":
                    return "overlay_already_reverted", operation
                return _overlay_operation_outcome(operation, kind="revert"), operation
            if (
                expected_goal_id is not None
                and operation.get("goal_id") != expected_goal_id
            ):
                skipped = await self._finalize_overlay_skipped(
                    str(operation.get("operation_id") or ""),
                    code="action_goal_mismatch",
                )
                return _overlay_operation_outcome(skipped, kind="revert"), skipped
            terminal = await self._dispatch_reserved_overlay_operation(
                operation,
                kind="revert",
                finished_at=reverted_at,
            )
            return _overlay_operation_outcome(terminal, kind="revert"), terminal

    async def expire_overlays(self, now: datetime | None = None) -> dict[str, str]:
        now = now or utcnow()
        outcomes: dict[str, str] = {}
        after_expires_at: datetime | None = None
        after_id: str | None = None
        seen_cursors: set[tuple[str, str]] = set()
        async with self._overlay_lock:
            while True:
                claimed = await self.store.claim_expired_overlay_reverts(
                    now,
                    limit=OVERLAY_EXPIRY_PAGE_SIZE,
                    after_expires_at=after_expires_at,
                    after_id=after_id,
                )
                operations = claimed.get("operations")
                if not isinstance(operations, list):
                    break
                for index, operation in enumerate(operations):
                    if not isinstance(operation, dict):
                        continue
                    overlay_id = str(operation.get("overlay_id") or "")
                    if not overlay_id:
                        continue
                    try:
                        terminal = await self._dispatch_reserved_overlay_operation(
                            operation,
                            kind="revert",
                            finished_at=now,
                        )
                        outcomes[overlay_id] = _overlay_operation_outcome(
                            terminal,
                            kind="revert",
                        )
                    except asyncio.CancelledError:
                        await self._skip_unstarted_expiry_operations(
                            operations[index + 1 :]
                        )
                        raise
                cursor = claimed.get("next_cursor")
                if not isinstance(cursor, dict):
                    break
                cursor_id = str(cursor.get("overlay_id") or "")
                cursor_time = str(cursor.get("expires_at") or "")
                marker = (cursor_time, cursor_id)
                if not cursor_id or not cursor_time or marker in seen_cursors:
                    break
                try:
                    after_expires_at = _parse_overlay_cursor_time(cursor_time)
                except ValueError:
                    break
                seen_cursors.add(marker)
                after_id = cursor_id
        return outcomes

    async def _dispatch_reserved_overlay_operation(
        self,
        operation: dict,
        *,
        kind: str,
        finished_at: datetime | None = None,
    ) -> dict:
        if operation.get("state") != "reserved":
            return operation
        operation_id = str(operation.get("operation_id") or "")
        payload = operation.get("payload")
        adapter_name = (
            str(payload.get("adapter") or "") if isinstance(payload, dict) else ""
        )
        if not operation_id or not adapter_name:
            return {
                "state": "delivery_uncertain",
                "result": {"code": f"overlay_{kind}_reservation_uncertain"},
            }
        if adapter_name != "opencode" and self.adapters.get(adapter_name) is None:
            skipped = await self._finalize_overlay_skipped(
                operation_id,
                code="overlay_missing_session_or_adapter",
            )
            return skipped
        started = await self._start_overlay_operation(
            operation,
            kind=kind,
            store_projected=adapter_name == "opencode",
            refusal_code=(
                "overlay_dispatch_refused"
                if kind == "apply"
                else "overlay_revert_refused"
            ),
        )
        if (
            isinstance(started, dict)
            and (
                operation.get("replayed") is True
                or operation.get("blocked_by_existing") is True
            )
            and started.get("replayed") is not True
        ):
            # Replay is caller-observation metadata, not persisted authority.
            # Preserve it when this reservation loses the one-shot start race.
            started = {**started, "replayed": True}
        return await self._dispatch_overlay_grant(
            started,
            kind=kind,
            finished_at=finished_at,
        )

    async def _start_overlay_operation(
        self,
        operation: dict,
        *,
        kind: str,
        store_projected: bool,
        refusal_code: str,
    ) -> dict:
        operation_id = str(operation.get("operation_id") or "")
        if not operation_id:
            return {
                "state": "delivery_uncertain",
                "result": {"code": f"overlay_{kind}_start_uncertain"},
            }
        try:
            return await self.store.start_overlay_operation(
                operation_id,
                store_projected=store_projected,
            )
        except asyncio.CancelledError as cancelled:
            settle_task = asyncio.create_task(
                self._settle_cancelled_overlay_start(operation_id),
                name=f"overlay-start-cancel:{operation_id}",
            )
            await _await_retained_task(settle_task, initial_cancel=cancelled)
            raise cancelled from None
        except Exception:
            try:
                current = await self.store.get_overlay_operation_for_authority(
                    operation_id,
                    require_live=False,
                )
            except Exception:
                current = None
            if isinstance(current, dict):
                if current.get("state") == "reserved":
                    return await self._finalize_overlay_skipped(
                        operation_id,
                        code=refusal_code,
                    )
                return current
            return {
                "operation_id": operation_id,
                "state": "delivery_uncertain",
                "result": {"code": f"overlay_{kind}_start_uncertain"},
            }

    async def _settle_cancelled_overlay_start(self, operation_id: str) -> None:
        try:
            current = await self.store.get_overlay_operation_for_authority(
                operation_id,
                require_live=False,
            )
        except Exception:
            return
        if isinstance(current, dict) and current.get("state") == "reserved":
            try:
                await self._finalize_overlay_retained(
                    operation_id,
                    state="skipped",
                    result={"code": "overlay_start_cancelled"},
                )
            except Exception:
                pass

    async def _dispatch_overlay_grant(
        self,
        started: dict,
        *,
        kind: str,
        finished_at: datetime | None = None,
    ) -> dict:
        canonical = started.get("operation")
        if not isinstance(canonical, dict):
            canonical = started
        if started.get("replayed") is True and canonical.get("replayed") is not True:
            canonical = {**canonical, "replayed": True}
        if canonical.get("state") != "dispatching":
            return canonical
        if started.get("granted") is not True:
            return canonical
        operation_id = str(canonical.get("operation_id") or "")
        overlay = started.get("overlay")
        session = started.get("session")
        adapter_name = str(started.get("adapter") or "")
        rollback = started.get("rollback")
        if (
            not operation_id
            or canonical.get("kind") != kind
            or not isinstance(overlay, Overlay)
            or not isinstance(session, HarnessSession)
            or not isinstance(rollback, dict)
            or overlay.id != canonical.get("overlay_id")
            or overlay.session_id != session.id
            or adapter_name != str(canonical.get("payload", {}).get("adapter") or "")
        ):
            skipped = await self._finalize_overlay_skipped(
                operation_id,
                code="overlay_canonical_grant_invalid",
            )
            return skipped
        adapter = self.adapters.get(adapter_name)
        if adapter is None or adapter_name == "opencode":
            skipped = await self._finalize_overlay_skipped(
                operation_id,
                code="overlay_missing_session_or_adapter",
            )
            return skipped

        uncertain_code = f"overlay_{kind}_delivery_uncertain"
        try:
            if kind == "apply":
                succeeded = await asyncio.wait_for(
                    self._workspace_dispatch(
                        session, lambda: adapter.apply_overlay(session, overlay),
                    ),
                    timeout=OVERLAY_ADAPTER_TIMEOUT_SECONDS,
                )
            else:
                succeeded = await asyncio.wait_for(
                    adapter.revert_overlay(overlay.id, rollback),
                    timeout=OVERLAY_ADAPTER_TIMEOUT_SECONDS,
                )
        except _WorkspaceDispatchRefused:
            return await self._finalize_overlay_skipped(
                operation_id, code="workspace_authority_changed",
            )
        except asyncio.CancelledError:
            await self._finalize_overlay_with_recovery(
                operation_id,
                state="delivery_uncertain",
                result={"code": uncertain_code},
                uncertain_code=uncertain_code,
                now=finished_at,
            )
            raise
        except Exception:
            terminal = await self._finalize_overlay_with_recovery(
                operation_id,
                state="delivery_uncertain",
                result={"code": uncertain_code},
                uncertain_code=uncertain_code,
                now=finished_at,
            )
            return terminal

        success_code = "overlay_applied" if kind == "apply" else "overlay_reverted"
        failure_code = "overlay_failed" if kind == "apply" else "overlay_revert_failed"
        terminal = await self._finalize_overlay_with_recovery(
            operation_id,
            state="delivered" if succeeded else "failed",
            result={"code": success_code if succeeded else failure_code},
            uncertain_code=uncertain_code,
            now=finished_at,
        )
        return terminal

    async def _finalize_overlay_retained(
        self,
        operation_id: str,
        *,
        state: str,
        result: dict,
        now: datetime | None = None,
    ) -> dict:
        finalize_task = asyncio.create_task(
            self.store.finalize_overlay_operation(
                operation_id,
                state=state,
                result=result,
                now=now,
            ),
            name=f"overlay-finalize:{operation_id}",
        )
        return await _await_retained_task(finalize_task)

    async def _finalize_overlay_with_recovery(
        self,
        operation_id: str,
        *,
        state: str,
        result: dict,
        uncertain_code: str,
        now: datetime | None = None,
    ) -> dict:
        try:
            return await self._finalize_overlay_retained(
                operation_id,
                state=state,
                result=result,
                now=now,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return await self._recover_overlay_finalize_failure(
                operation_id,
                uncertain_code=uncertain_code,
            )

    async def _finalize_overlay_skipped(
        self,
        operation_id: str,
        *,
        code: str,
    ) -> dict:
        if not operation_id:
            return {
                "state": "delivery_uncertain",
                "result": {"code": "overlay_finalization_uncertain"},
            }
        try:
            return await self._finalize_overlay_retained(
                operation_id,
                state="skipped",
                result={"code": code},
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            try:
                current = await self.store.get_overlay_operation_for_authority(
                    operation_id,
                    require_live=False,
                )
            except Exception:
                current = None
            if isinstance(current, dict):
                return current
            return {
                "operation_id": operation_id,
                "state": "delivery_uncertain",
                "result": {"code": "overlay_finalization_uncertain"},
            }

    async def _skip_unstarted_expiry_operations(self, operations: list) -> None:
        async def skip_all() -> None:
            for operation in operations:
                if not isinstance(operation, dict) or operation.get("state") != "reserved":
                    continue
                operation_id = str(operation.get("operation_id") or "")
                if not operation_id:
                    continue
                try:
                    await self._finalize_overlay_skipped(
                        operation_id,
                        code="overlay_expiry_sweep_cancelled_before_dispatch",
                    )
                except Exception:
                    continue

        settle_task = asyncio.create_task(skip_all(), name="overlay-expiry-cancel")
        await _await_retained_task(settle_task)

    async def _recover_overlay_finalize_failure(
        self,
        operation_id: str,
        *,
        uncertain_code: str,
    ) -> dict:
        """Resolve a lost finalize acknowledgement without repeating adapter I/O."""

        try:
            current = await self.store.get_overlay_operation_for_authority(
                operation_id,
                require_live=False,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            current = None
        if current is None:
            return {
                "operation_id": operation_id,
                "state": "delivery_uncertain",
                "result": {"code": uncertain_code},
            }
        if current["state"] == "dispatching":
            try:
                return await self._finalize_overlay_retained(
                    operation_id,
                    state="delivery_uncertain",
                    result={"code": uncertain_code},
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                try:
                    exact = await self.store.get_overlay_operation_for_authority(
                        operation_id,
                        require_live=False,
                    )
                except Exception:
                    exact = None
                if isinstance(exact, dict) and exact.get("state") != "dispatching":
                    return exact
                return {
                    **current,
                    "state": "delivery_uncertain",
                    "result": {"code": uncertain_code},
                }
        return current


async def _await_retained_task(
    retained_task: asyncio.Task,
    *,
    initial_cancel: asyncio.CancelledError | None = None,
):
    """Wait through repeated caller cancellation without exposing the child."""

    cancelled = initial_cancel
    completion_error: BaseException | None = None
    while not retained_task.done():
        try:
            await asyncio.shield(retained_task)
        except asyncio.CancelledError as exc:
            cancelled = exc
        except BaseException as exc:
            completion_error = exc
            break
    if cancelled is not None:
        # Retrieve any child exception so cancellation remains the caller-visible
        # result and no unobserved-task warning can escape after settlement.
        try:
            retained_task.exception()
        except asyncio.CancelledError:
            pass
        raise cancelled
    if completion_error is not None:
        raise completion_error
    return retained_task.result()


def _overlay_adapter_name(session_id: str) -> str | None:
    prefix = session_id.split(":", 1)[0]
    return prefix if prefix in {"opencode", "synthetic"} else None


def _overlay_session_matches_operation(
    session: HarnessSession,
    operation: dict,
) -> bool:
    return bool(
        session.id == operation.get("session_id")
        and session.vendor_session_id == operation.get("vendor_session_id")
        and session.harness_type.value == operation.get("harness_type")
        and session.goal_id == operation.get("goal_id")
    )


def _parse_overlay_cursor_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("overlay expiry cursor must be timezone-aware")
    return parsed.astimezone(UTC)


def _overlay_has_local_reversibility_proof(overlay: Overlay, adapter_name: str) -> bool:
    """Allow only bounded, session-scoped, authority-reducing runtime overlays."""

    return adapter_name in {"opencode", "synthetic"} and locally_proven_session_overlay(
        overlay
    )


def _overlay_operation_outcome(operation: dict, *, kind: str) -> str:
    result = operation.get("result")
    if isinstance(result, dict) and isinstance(result.get("code"), str):
        return result["code"]
    state = str(operation.get("state") or "")
    if state == "dispatching":
        return f"overlay_{kind}_in_progress"
    if state == "reserved":
        return f"overlay_{kind}_reserved"
    return f"overlay_{kind}_{state or 'unknown'}"


def _overlay_structured_result(code: str, operation: dict | None) -> dict:
    if isinstance(operation, dict):
        state = str(operation.get("state") or "uncertain")
        raw_result = operation.get("result")
        result = _overlay_public_result(raw_result)
        receipt = {
            "operation_id": operation.get("operation_id"),
            "state": state,
            "version": operation.get("version"),
            "reserved_at": operation.get("reserved_at"),
            "dispatch_started_at": operation.get("dispatch_started_at"),
            "finished_at": operation.get("finished_at"),
            "result": result,
        }
        replayed = bool(
            operation.get("replayed") is True
            or operation.get("blocked_by_existing") is True
        )
    else:
        if code == "overlay_not_found":
            state = "not_found"
        elif "uncertain" in code:
            state = "delivery_uncertain"
        else:
            state = "refused"
        receipt = None
        replayed = False
    return {
        "ok": state == "delivered" and code in {
            "overlay_reverted",
            "overlay_already_reverted",
        },
        "code": code,
        "state": state,
        "replayed": replayed,
        "receipt": receipt,
    }


def _overlay_public_result(value: object) -> dict | None:
    """Project only stable non-authority result fields into external receipts."""

    if not isinstance(value, dict):
        return None
    result = {
        key: value[key]
        for key in ("code", "mode")
        if isinstance(value.get(key), str)
    }
    return result or None


def _json_bytes(value: object) -> int:
    try:
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return MAX_CONTEXT_BUNDLE_BYTES + 1
    return len(rendered.encode("utf-8"))


def _project_key(value: str) -> str:
    return value.strip().replace("\\", "/").rstrip("/").casefold()
