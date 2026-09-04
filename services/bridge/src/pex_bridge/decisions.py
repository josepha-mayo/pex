from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from pex_protocol.actions import InterventionType
from pex_protocol.capabilities import PermissionResponseMode
from pex_protocol.enums import PolicyVerdict, SessionStatus
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessSession

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.decision_delivery import (
    dispatch_human_decision,
    probe_human_decision_delivery,
)
from pex_bridge.store import (
    ProjectIdentityBlockedError,
    Store,
    human_decision_choice_receipt,
    utcnow,
)

_LIFECYCLE_TYPES = {
    InterventionType.START_AGENT,
    InterventionType.STOP_AGENT,
    InterventionType.FORK_PROBE,
    InterventionType.CLEANUP,
}
CAPABILITY_PROBE_TIMEOUT_SECONDS = 3.0
PERMISSION_DELIVERY_TIMEOUT_SECONDS = 15.0
logger = logging.getLogger(__name__)


class DecisionResolutionError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


async def _session_for_intervention_authority(
    store: Store,
    intervention: Intervention,
    *,
    code: str,
    detail: str,
) -> HarnessSession:
    try:
        session = await store.get_session_for_authority(
            intervention.session_id,
            require_goal_binding=intervention.goal_id is not None,
        )
    except ProjectIdentityBlockedError as exc:
        raise DecisionResolutionError(409, exc.code, str(exc)) from exc
    if session is None:
        raise DecisionResolutionError(409, code, detail)
    return session


async def _intervention_for_authority(
    store: Store,
    intervention_id: str,
) -> Intervention:
    try:
        intervention = await store.get_intervention_for_authority(intervention_id)
    except ProjectIdentityBlockedError as exc:
        raise DecisionResolutionError(409, exc.code, str(exc)) from exc
    except (PermissionError, RuntimeError, ValueError) as exc:
        raise DecisionResolutionError(
            409,
            "decision_binding_changed",
            str(exc),
        ) from exc
    if intervention is None:
        raise DecisionResolutionError(404, "decision_not_found", "Decision not found.")
    return intervention


async def _intervention_for_resolution_classification(
    store: Store,
    intervention_id: str,
    *,
    kind: str,
) -> Intervention:
    """Load one frozen target for replay or authority-reducing routing only."""

    try:
        intervention = await store.get_intervention_for_resolution_classification(
            intervention_id
        )
    except ProjectIdentityBlockedError as exc:
        raise DecisionResolutionError(409, exc.code, str(exc)) from exc
    except (PermissionError, RuntimeError, ValueError) as exc:
        raise DecisionResolutionError(409, f"{kind}_binding_changed", str(exc)) from exc
    if intervention is None:
        raise DecisionResolutionError(404, "decision_not_found", "Decision not found.")
    return intervention


async def _session_for_resolution_classification(
    store: Store,
    intervention: Intervention,
    *,
    kind: str,
) -> HarnessSession:
    """Return a snapshot; Store reserve/finalize still grant every mutation."""

    session = await store.get_session(intervention.session_id)
    if session is None:
        raise DecisionResolutionError(
            409,
            f"{kind}_session_missing",
            f"The session for this {kind} decision is no longer available.",
        )
    _validate_binding(intervention, session, kind=kind)
    return session


@dataclass(frozen=True)
class PermissionDecisionResult:
    intervention: Intervention
    session: HarnessSession
    resolution: dict[str, Any]
    delivered: bool
    replayed: bool = False

    def response(self) -> dict[str, Any]:
        return {
            "ok": self.delivered,
            "kind": "permission",
            "delivered": self.delivered,
            "replayed": self.replayed,
            "resolution": self.resolution,
            "intervention": self.intervention.model_dump(mode="json"),
            "session": self.session.model_dump(mode="json"),
        }


@dataclass(frozen=True)
class LifecycleDecisionResult:
    intervention: Intervention
    session: HarnessSession
    resolution: dict[str, Any]
    executed: bool
    replayed: bool = False

    def response(self) -> dict[str, Any]:
        status = str(self.resolution.get("status") or "")
        return {
            "ok": status in {"delivered", "denied"},
            "kind": "lifecycle",
            "executed": self.executed,
            "replayed": self.replayed,
            "resolution": self.resolution,
            "intervention": self.intervention.model_dump(mode="json"),
            "session": self.session.model_dump(mode="json"),
        }


@dataclass(frozen=True)
class HumanDecisionResult:
    intervention: Intervention
    session: HarnessSession
    payload: dict[str, Any]
    replayed: bool = False

    def response(self) -> dict[str, Any]:
        return {**self.payload, "replayed": self.replayed}


def _is_pending_permission(intervention: Intervention) -> bool:
    return (
        intervention.proposed_action.type == InterventionType.RESPOND_PERMISSION
        and intervention.action_taken == InterventionType.RESPOND_PERMISSION.value
        and intervention.policy_verdict == PolicyVerdict.ASK_HUMAN
        and intervention.result == "permission_awaiting_human"
    )


def _is_pending_lifecycle(intervention: Intervention) -> bool:
    return (
        intervention.proposed_action.type in _LIFECYCLE_TYPES
        and intervention.action_taken == intervention.proposed_action.type.value
        and intervention.policy_verdict == PolicyVerdict.ASK_HUMAN
        and intervention.result == "awaiting_human"
    )


def _is_pending_mcp_human_decision(intervention: Intervention) -> bool:
    return (
        intervention.proposed_action.type == InterventionType.ASK_HUMAN
        and intervention.action_taken == InterventionType.ASK_HUMAN.value
        and intervention.policy_verdict == PolicyVerdict.ASK_HUMAN
        and intervention.result == "awaiting_human"
        and intervention.metadata.get("decision_kind") == "mcp_human_request"
    )


def _validate_binding(
    intervention: Intervention,
    session: HarnessSession,
    *,
    kind: str,
) -> None:
    action = intervention.proposed_action
    if action.session_id != intervention.session_id or session.id != intervention.session_id:
        raise DecisionResolutionError(
            409,
            f"{kind}_session_mismatch",
            f"The stored {kind} action is not bound to the intervention session.",
        )
    if action.goal_id != intervention.goal_id or session.goal_id != intervention.goal_id:
        raise DecisionResolutionError(
            409,
            f"{kind}_goal_mismatch",
            f"The stored {kind} action is no longer bound to the session's active goal.",
        )
def _existing_lifecycle_result(
    *,
    intervention: Intervention,
    session: HarnessSession,
    resolution: dict[str, Any],
    decision: str,
) -> LifecycleDecisionResult:
    if resolution.get("decision") != decision:
        raise DecisionResolutionError(
            409,
            "lifecycle_decision_conflict",
            "This lifecycle action already has a different human decision.",
        )
    status = str(resolution.get("status") or "")
    if status in {"delivered", "denied"}:
        return LifecycleDecisionResult(
            intervention=intervention,
            session=session,
            resolution=resolution,
            executed=status == "delivered",
            replayed=True,
        )
    if status in {"reserved", "dispatching", "delivering", "denying"}:
        raise DecisionResolutionError(
            409,
            "lifecycle_delivery_in_progress",
            "This lifecycle decision is already being applied.",
        )
    raise DecisionResolutionError(
        409,
        "lifecycle_delivery_not_retriable",
        (
            "The prior lifecycle delivery did not complete safely. PEX will not replay "
            "a start, stop, fork, or cleanup because the first attempt may have changed state."
        ),
    )


def _lifecycle_delivery_succeeded(action_type: InterventionType, result: str) -> bool:
    if action_type == InterventionType.START_AGENT:
        return result.startswith("agent_started:")
    if action_type == InterventionType.STOP_AGENT:
        return result == "agent_stopped"
    if action_type == InterventionType.FORK_PROBE:
        return result.startswith("probe_forked:")
    if action_type == InterventionType.CLEANUP:
        return result.startswith("cleanup_quarantined:")
    return False


def _lifecycle_delivery_uncertain(result: str) -> bool:
    return (
        "uncertain" in result
        or "persist_failed" in result
        or "persist_conflict" in result
        or "identity_invalid" in result
    )


def _existing_result(
    *,
    intervention: Intervention,
    session: HarnessSession,
    resolution: dict[str, Any],
    decision: str,
) -> PermissionDecisionResult:
    if resolution.get("intervention_id") != intervention.id:
        raise DecisionResolutionError(
            409,
            "permission_request_already_claimed",
            "This permission request is already bound to another intervention.",
        )
    if resolution.get("decision") != decision:
        raise DecisionResolutionError(
            409,
            "permission_decision_conflict",
            "This permission request already has a different human decision.",
        )
    status = str(resolution.get("status") or "")
    if status == "delivered":
        return PermissionDecisionResult(
            intervention=intervention,
            session=session,
            resolution=resolution,
            delivered=True,
            replayed=True,
        )
    if status in {"reserved", "dispatching", "delivering"}:
        raise DecisionResolutionError(
            409,
            "permission_delivery_in_progress",
            "This permission decision is already being delivered.",
        )
    raise DecisionResolutionError(
        409,
        "permission_delivery_not_retriable",
        (
            "The prior delivery did not complete successfully. PEX will not replay it because "
            "the harness may already have received the response; wait for a fresh permission "
            "request."
        ),
    )


def _human_decision_result(
    result: dict[str, Any],
    *,
    replayed: bool,
) -> HumanDecisionResult:
    payload = result.get("response")
    if not isinstance(payload, dict):
        raise DecisionResolutionError(
            409,
            "human_decision_receipt_invalid",
            "The durable human decision receipt is invalid.",
        )
    try:
        intervention = Intervention.model_validate(payload.get("intervention"))
        session = HarnessSession.model_validate(payload.get("session"))
    except Exception as exc:
        raise DecisionResolutionError(
            409,
            "human_decision_receipt_invalid",
            "The durable human decision receipt cannot be validated.",
        ) from exc
    return HumanDecisionResult(
        intervention=intervention,
        session=session,
        payload=payload,
        replayed=replayed,
    )


async def resolve_requested_human_decision(
    store: Store,
    adapters: AdapterRegistry,
    *,
    intervention_id: str,
    choice: str,
) -> HumanDecisionResult:
    """Reserve, deliver, and durably finalize one exact human answer."""

    existing = await store.get_current_human_decision_resolution(intervention_id)
    resuming_reserved = False
    record: dict[str, Any] | None = None
    if existing is not None:
        canonical_choice = human_decision_choice_receipt(
            choice,
            freeform=existing.get("choice_mode") == "freeform",
        )
        if existing.get("choice") != canonical_choice:
            raise DecisionResolutionError(
                409,
                "human_decision_conflict",
                "This human decision was already resolved with a different choice.",
            )
        if existing.get("status") != "delivery_reserved":
            return _human_decision_result(existing, replayed=True)
        resuming_reserved = True
        record = existing

    intervention = await _intervention_for_authority(store, intervention_id)
    if not resuming_reserved and not _is_pending_mcp_human_decision(intervention):
        raise DecisionResolutionError(
            409,
            "decision_not_pending_human_request",
            "This intervention is not an unresolved MCP human decision.",
        )
    options = intervention.proposed_action.payload.get("options")
    if not isinstance(options, list) or any(not isinstance(item, str) for item in options):
        raise DecisionResolutionError(
            409,
            "human_decision_options_invalid",
            "The stored human decision options are invalid.",
        )
    if options and choice not in options:
        raise DecisionResolutionError(
            422,
            "human_decision_choice_not_offered",
            "The choice must exactly match one of the offered decision options.",
        )
    if not resuming_reserved:
        try:
            reserved = await store.reserve_human_decision_delivery(
                intervention_id=intervention_id,
                choice=choice,
                resolved_at=utcnow(),
            )
        except LookupError as exc:
            raise DecisionResolutionError(404, "decision_not_found", str(exc)) from exc
        except ValueError as exc:
            detail = str(exc)
            if "different choice" in detail:
                code = "human_decision_conflict"
            elif "offered options" in detail:
                code = "human_decision_choice_not_offered"
            elif "artifact id collision" in detail:
                code = "human_decision_artifact_collision"
            else:
                code = "human_decision_binding_changed"
            status = 422 if code == "human_decision_choice_not_offered" else 409
            raise DecisionResolutionError(status, code, detail) from exc
        if not bool(reserved.get("created")):
            current = await store.get_current_human_decision_resolution(intervention_id)
            if current is None:  # pragma: no cover - transaction invariant
                raise DecisionResolutionError(
                    409,
                    "human_decision_receipt_invalid",
                    "The durable human decision receipt disappeared after reservation.",
                )
            return _human_decision_result(current, replayed=True)
        record = reserved.get("record")

    if not isinstance(record, dict):
        raise DecisionResolutionError(
            409,
            "human_decision_receipt_invalid",
            "The durable human decision reservation is invalid.",
        )
    effect_id = str(record.get("effect_id") or "")
    reserved_result = _human_decision_result(record, replayed=False)
    session = reserved_result.session
    adapter = adapters.get(session.harness_type.value)
    if adapter is None:
        finalized = await store.finalize_human_decision_delivery(
            intervention_id=intervention_id,
            effect_id=effect_id,
            status="unsupported",
            delivery_code="adapter_unavailable",
            finished_at=utcnow(),
        )
        return _human_decision_result(finalized["record"], replayed=False)

    capability = await probe_human_decision_delivery(adapter)
    if not capability.ready:
        finalized = await store.finalize_human_decision_delivery(
            intervention_id=intervention_id,
            effect_id=effect_id,
            status=capability.status,
            delivery_code=capability.code,
            exception_type=capability.exception_type,
            finished_at=utcnow(),
        )
        return _human_decision_result(finalized["record"], replayed=False)

    try:
        started = await store.start_human_decision_delivery(
            intervention_id=intervention_id,
            effect_id=effect_id,
            started_at=utcnow(),
        )
    except (LookupError, ValueError) as exc:
        finalized = await store.finalize_human_decision_delivery(
            intervention_id=intervention_id,
            effect_id=effect_id,
            status="failed",
            delivery_code="binding_revalidation_failed",
            exception_type=type(exc).__name__,
            finished_at=utcnow(),
        )
        return _human_decision_result(finalized["record"], replayed=False)
    if not bool(started.get("started")):
        current = await store.get_current_human_decision_resolution(intervention_id)
        if current is None:  # pragma: no cover - transaction invariant
            raise DecisionResolutionError(
                409,
                "human_decision_receipt_invalid",
                "The durable human decision dispatch receipt disappeared.",
            )
        return _human_decision_result(current, replayed=True)
    dispatch_session = HarnessSession.model_validate(started.get("session"))
    dispatch = await dispatch_human_decision(
        adapter,
        dispatch_session,
        question=str(intervention.proposed_action.payload.get("question") or ""),
        choice=choice,
    )
    finalization = store.finalize_human_decision_delivery(
        intervention_id=intervention_id,
        effect_id=effect_id,
        status=dispatch.status,
        delivery_code=dispatch.code,
        exception_type=dispatch.exception_type,
        worker_delivery_receipt=dispatch.worker_delivery_receipt,
        finished_at=utcnow(),
    )
    if dispatch.cancelled:
        await _finalize_delivery_then_propagate_cancellation(finalization)
        raise AssertionError("cancellation propagation returned")  # pragma: no cover
    finalized = await finalization
    return _human_decision_result(finalized["record"], replayed=False)


async def _finalize_delivery_then_propagate_cancellation(finalization: Any) -> None:
    """Finish the durable uncertain transition, then restore task cancellation."""

    current = asyncio.current_task()
    cancellation_count = current.cancelling() if current is not None else 0
    if current is not None:
        for _ in range(cancellation_count):
            current.uncancel()
    finalizer = asyncio.create_task(finalization)
    finalization_failure_observed = False
    try:
        while not finalizer.done():
            try:
                await asyncio.shield(finalizer)
            except asyncio.CancelledError:
                if finalizer.done():
                    finalization_failure_observed = True
                    logger.warning(
                        "cancelled human decision finalization was itself cancelled"
                    )
                    break
                if current is None:
                    continue
                newly_requested = current.cancelling()
                cancellation_count += newly_requested
                for _ in range(newly_requested):
                    current.uncancel()
            except Exception as exc:
                finalization_failure_observed = True
                logger.warning(
                    "cancelled human decision finalization failed error=%s",
                    type(exc).__name__,
                )
                break
        if not finalization_failure_observed:
            try:
                finalizer.result()
            except asyncio.CancelledError:
                logger.warning(
                    "cancelled human decision finalization was itself cancelled"
                )
            except Exception as exc:
                logger.warning(
                    "cancelled human decision finalization failed error=%s",
                    type(exc).__name__,
                )
    finally:
        if current is not None:
            for _ in range(max(1, cancellation_count)):
                current.cancel()
    raise asyncio.CancelledError


async def resolve_permission_decision(
    store: Store,
    adapters: AdapterRegistry,
    *,
    intervention_id: str,
    decision: str,
) -> PermissionDecisionResult:
    """Deliver one authenticated human allow/deny response to the exact request.

    Reservation happens before adapter I/O. This gives duplicate calls replay
    protection without pretending that an interrupted external write is safe to
    retry. Inline hook adapters are rejected even when they truthfully support
    approve/deny, because an old synchronous hook cannot be answered later.
    """
    if decision not in {"allow", "deny"}:
        raise DecisionResolutionError(
            422,
            "invalid_permission_decision",
            "Permission decision must be exactly 'allow' or 'deny'.",
        )

    classified = await _intervention_for_resolution_classification(
        store,
        intervention_id,
        kind="permission",
    )
    if decision == "deny":
        intervention = classified
        session = await _session_for_resolution_classification(
            store,
            intervention,
            kind="permission",
        )
    else:
        intervention = await _intervention_for_authority(store, intervention_id)
        session = await _session_for_intervention_authority(
            store,
            intervention,
            code="permission_session_missing",
            detail="The session for this permission request is no longer available.",
        )

    existing = await store.get_permission_resolution(intervention.id)
    resuming_reserved = False
    if existing is not None:
        if existing.get("decision") != decision:
            return _existing_result(
                intervention=intervention,
                session=session,
                resolution=existing,
                decision=decision,
            )
        if existing.get("status") != "reserved":
            return _existing_result(
                intervention=intervention,
                session=session,
                resolution=existing,
                decision=decision,
            )
        resuming_reserved = True

    if not resuming_reserved and not _is_pending_permission(intervention):
        raise DecisionResolutionError(
            409,
            "decision_not_pending_permission",
            "This intervention is not an unresolved human permission decision.",
        )
    _validate_binding(intervention, session, kind="permission")
    request_id = str(intervention.proposed_action.payload.get("request_id") or "").strip()
    if not request_id:
        raise DecisionResolutionError(
            409,
            "permission_request_id_missing",
            "The pending permission does not contain a harness request id.",
        )
    recorded_request_id = str(intervention.metadata.get("permission_request_id") or "").strip()
    if recorded_request_id and recorded_request_id != request_id:
        raise DecisionResolutionError(
            409,
            "permission_request_mismatch",
            "The permission request id does not match its immutable audit metadata.",
        )

    if resuming_reserved:
        resolution = existing
    else:
        try:
            reserved, resolution = await store.reserve_permission_resolution(
                intervention_id=intervention.id,
                session_id=session.id,
                request_id=request_id,
                decision=decision,
                started_at=utcnow(),
            )
        except (PermissionError, RuntimeError, ValueError) as exc:
            raise DecisionResolutionError(
                409,
                "permission_binding_changed_before_reservation",
                str(exc),
            ) from exc
        if not reserved and resolution.get("status") != "reserved":
            return _existing_result(
                intervention=intervention,
                session=session,
                resolution=resolution,
                decision=decision,
            )

    try:
        started = await store.start_permission_resolution_dispatch(
            intervention.id,
            started_at=utcnow(),
        )
    except (LookupError, PermissionError, ValueError) as exc:
        raise DecisionResolutionError(
            409,
            "permission_binding_changed_before_dispatch",
            str(exc),
        ) from exc
    if not bool(started.get("granted")):
        return _existing_result(
            intervention=intervention,
            session=session,
            resolution=started["resolution"],
            decision=decision,
        )
    intervention = Intervention.model_validate(started["intervention"])
    session = HarnessSession.model_validate(started["session"])
    resolution = started["resolution"]

    exception_name: str | None = None
    cancelled = False
    delivery_uncertain = False
    resolution_error: DecisionResolutionError | None = None
    adapter = adapters.for_session(session.id)
    if adapter is None:
        delivered = False
        resolution_error = DecisionResolutionError(
            409,
            "permission_adapter_missing",
            "The adapter for this permission request is no longer available.",
        )
    else:
        try:
            capabilities = await asyncio.wait_for(
                adapter.probe(),
                timeout=CAPABILITY_PROBE_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            delivered = False
            exception_name = "CancelledError"
            cancelled = True
        except Exception as exc:
            delivered = False
            exception_name = type(exc).__name__
            resolution_error = DecisionResolutionError(
                409,
                "permission_adapter_unavailable",
                f"The adapter capability probe failed ({type(exc).__name__}).",
            )
        else:
            capability = "approve" if decision == "allow" else "deny"
            if not capabilities.supports(
                capability
            ) or capabilities.permission_response_mode not in {
                PermissionResponseMode.ASYNC,
                PermissionResponseMode.BOTH,
            }:
                delivered = False
                resolution_error = DecisionResolutionError(
                    409,
                    "permission_delivery_unsupported",
                    (
                        f"The {adapter.name} adapter cannot deliver an asynchronous "
                        f"{decision} response. Use the harness's own active permission prompt."
                    ),
                )
            else:
                session.capabilities = capabilities.model_dump(mode="json")
                try:
                    delivered = await asyncio.wait_for(
                        adapter.respond_permission(session, request_id, decision),
                        timeout=PERMISSION_DELIVERY_TIMEOUT_SECONDS,
                    )
                except asyncio.CancelledError:
                    delivered = False
                    exception_name = "CancelledError"
                    delivery_uncertain = True
                    cancelled = True
                except Exception as exc:  # external delivery may have partially completed
                    delivered = False
                    exception_name = type(exc).__name__
                    delivery_uncertain = True

    finished_at = utcnow()
    if delivered:
        status = "delivered"
        delivery_result = f"permission_{decision}"
        record_type = "human_decision_resolved"
    elif delivery_uncertain:
        status = "delivery_uncertain"
        delivery_result = f"permission_{decision}_delivery_uncertain"
        record_type = "human_decision_delivery_uncertain"
    else:
        status = "failed"
        delivery_result = f"permission_{decision}_failed"
        record_type = "human_decision_delivery_failed"

    resolution_for_audit = {
        **resolution,
        "status": status,
        "delivery_result": delivery_result,
        "finished_at": finished_at.isoformat(),
    }
    if exception_name:
        resolution_for_audit["exception_type"] = exception_name
    intervention.metadata["permission_request_id"] = request_id
    intervention.metadata["permission_resolution"] = resolution_for_audit
    intervention.result = delivery_result
    intervention.outcome = (
        "human_permission_delivered"
        if delivered
        else "human_permission_delivery_uncertain"
        if delivery_uncertain
        else "human_permission_delivery_failed"
    )

    if delivered:
        pending = await store.has_pending_human_intervention(
            session.id,
            excluding_id=intervention.id,
        )
        session.status = SessionStatus.NEEDS_DECISION if pending else SessionStatus.WORKING
        session.last_activity = finished_at
    else:
        session.status = SessionStatus.NEEDS_DECISION
    finalization = store.finalize_permission_resolution(
        intervention,
        session,
        status=status,
        delivery_result=delivery_result,
        finished_at=finished_at,
        record_type=record_type,
    )
    if cancelled:
        await _finalize_delivery_then_propagate_cancellation(finalization)
        raise AssertionError("cancellation propagation returned")  # pragma: no cover
    resolution = await finalization
    persisted_session = await store.get_session(session.id)
    if persisted_session is not None:
        session = persisted_session
    if resolution_error is not None:
        raise resolution_error

    return PermissionDecisionResult(
        intervention=intervention,
        session=session,
        resolution=(
            {**resolution, "exception_type": exception_name}
            if exception_name
            else resolution
        ),
        delivered=delivered,
    )


async def resolve_lifecycle_decision(
    store: Store,
    adapters: AdapterRegistry,
    executor: Any,
    *,
    intervention_id: str,
    decision: str,
) -> LifecycleDecisionResult:
    """Apply one authenticated allow/deny to an exact pending lifecycle action.

    The durable reservation precedes adapter or filesystem I/O. A failed or
    uncertain delivery is never replayed automatically.
    """
    if decision not in {"allow", "deny"}:
        raise DecisionResolutionError(
            422,
            "invalid_lifecycle_decision",
            "Lifecycle decision must be exactly 'allow' or 'deny'.",
        )
    classified = await _intervention_for_resolution_classification(
        store,
        intervention_id,
        kind="lifecycle",
    )
    containment = (
        decision == "deny"
        or classified.proposed_action.type == InterventionType.STOP_AGENT
    )
    if containment:
        intervention = classified
        session = await _session_for_resolution_classification(
            store,
            intervention,
            kind="lifecycle",
        )
    else:
        intervention = await _intervention_for_authority(store, intervention_id)
        session = await _session_for_intervention_authority(
            store,
            intervention,
            code="lifecycle_session_missing",
            detail="The source session for this lifecycle action is no longer available.",
        )
    existing = await store.get_lifecycle_resolution(intervention.id)
    resuming_reserved = False
    if existing is not None:
        if existing.get("decision") != decision:
            return _existing_lifecycle_result(
                intervention=intervention,
                session=session,
                resolution=existing,
                decision=decision,
            )
        if existing.get("status") != "reserved":
            return _existing_lifecycle_result(
                intervention=intervention,
                session=session,
                resolution=existing,
                decision=decision,
            )
        resuming_reserved = True
    if not resuming_reserved and not _is_pending_lifecycle(intervention):
        raise DecisionResolutionError(
            409,
            "decision_not_pending_lifecycle",
            "This intervention is not an unresolved lifecycle decision.",
        )
    _validate_binding(intervention, session, kind="lifecycle")
    if resuming_reserved:
        resolution = existing
    else:
        try:
            reserved, resolution = await store.reserve_lifecycle_resolution(
                intervention_id=intervention.id,
                session_id=session.id,
                decision=decision,
                started_at=utcnow(),
            )
        except (PermissionError, RuntimeError, ValueError) as exc:
            raise DecisionResolutionError(
                409,
                "lifecycle_binding_changed_before_reservation",
                str(exc),
            ) from exc
        if not reserved and resolution.get("status") != "reserved":
            return _existing_lifecycle_result(
                intervention=intervention,
                session=session,
                resolution=resolution,
                decision=decision,
            )

    cancelled = False
    if decision == "deny":
        delivery_result = "denied_by_human"
        status = "denied"
        executed = False
        record_type = "human_lifecycle_denied"
        intervention.result = delivery_result
        intervention.outcome = "human_lifecycle_denied"
    else:
        try:
            started = await store.start_lifecycle_resolution_dispatch(
                intervention.id,
                started_at=utcnow(),
            )
        except (LookupError, PermissionError, ValueError) as exc:
            raise DecisionResolutionError(
                409,
                "lifecycle_binding_changed_before_dispatch",
                str(exc),
            ) from exc
        if not bool(started.get("granted")):
            return _existing_lifecycle_result(
                intervention=intervention,
                session=session,
                resolution=started["resolution"],
                decision=decision,
            )
        intervention = Intervention.model_validate(started["intervention"])
        session = HarnessSession.model_validate(started["session"])
        resolution = started["resolution"]
        try:
            delivery_result = await executor.execute(
                intervention.proposed_action,
                PolicyVerdict.ALLOW,
                human_authorized=True,
                lifecycle_resolution_id=intervention.id,
            )
        except asyncio.CancelledError:
            delivery_result = "lifecycle_delivery_uncertain:CancelledError"
            cancelled = True
        except Exception as exc:  # pragma: no cover - executor is normally fail-closed
            delivery_result = f"lifecycle_delivery_uncertain:{type(exc).__name__}"
        executed = _lifecycle_delivery_succeeded(
            intervention.proposed_action.type,
            delivery_result,
        )
        uncertain = _lifecycle_delivery_uncertain(delivery_result)
        status = "delivered" if executed else "delivery_uncertain" if uncertain else "failed"
        record_type = (
            "human_lifecycle_resolved"
            if executed
            else "human_lifecycle_delivery_uncertain"
            if uncertain
            else "human_lifecycle_delivery_failed"
        )
        intervention.result = delivery_result
        intervention.outcome = (
            "human_lifecycle_delivered"
            if executed
            else "human_lifecycle_delivery_uncertain"
            if uncertain
            else "human_lifecycle_delivery_failed"
        )

    finished_at = utcnow()
    resolution = {
        **resolution,
        "status": status,
        "delivery_result": delivery_result,
        "finished_at": finished_at.isoformat(),
        "action_type": intervention.proposed_action.type.value,
    }
    intervention.metadata["lifecycle_resolution"] = resolution

    current_session = session
    if (
        decision == "allow"
        and executed
        and intervention.proposed_action.type == InterventionType.STOP_AGENT
    ):
        current_session.status = SessionStatus.STOPPED
        current_session.last_activity = finished_at
    elif current_session.status != SessionStatus.STOPPED:
        pending = await store.has_pending_human_intervention(
            session.id,
            excluding_id=intervention.id,
        )
        if pending or (decision == "allow" and not executed):
            current_session.status = SessionStatus.NEEDS_DECISION
        else:
            previous = str(
                intervention.proposed_action.payload.get("previous_session_status") or "working"
            )
            try:
                restored = SessionStatus(previous)
            except ValueError:
                restored = SessionStatus.WORKING
            current_session.status = (
                SessionStatus.WORKING if restored == SessionStatus.NEEDS_DECISION else restored
            )
        current_session.last_activity = finished_at

    finalization = store.finalize_lifecycle_resolution(
        intervention,
        current_session,
        resolution,
        record_type=record_type,
    )
    if decision == "allow" and cancelled:
        await _finalize_delivery_then_propagate_cancellation(finalization)
        raise AssertionError("cancellation propagation returned")  # pragma: no cover
    resolution = await finalization
    persisted_session = await store.get_session(current_session.id)
    if persisted_session is not None:
        current_session = persisted_session
    return LifecycleDecisionResult(
        intervention=intervention,
        session=current_session,
        resolution=resolution,
        executed=executed,
    )
