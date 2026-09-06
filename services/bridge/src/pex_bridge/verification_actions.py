"""Resolve model-selected probe references against current local authority.

The model chooses whether to request evidence. It cannot choose the workspace,
execution bounds, targets, or identity of that evidence request.
"""

from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.project_identity import same_absolute_path
from pex_protocol.supervisor import SupervisorRequest
from pex_protocol.verification import EvidenceGatheringReceipt, EvidenceGatheringState
from pex_supervisor.loop import _redact_payload_value
from pex_supervisor.planner import _verification_request_copy


def bind_verification_action(
    action: ProposedAction,
    gathering: EvidenceGatheringReceipt,
    request: SupervisorRequest,
) -> ProposedAction | None:
    """Bind only an exact current reference or exact public/canonical probe echo.

    A missing or conflicting reference is not repaired. In particular, this
    never replaces a semantic NOOP with a deterministic verification request.
    Returned local authority is copied, not derived from model-supplied paths.
    """
    probe = gathering.probe
    if (
        action.type != InterventionType.REQUEST_VERIFICATION
        or gathering.state != EvidenceGatheringState.INSPECTED
        or probe is None
        or request.goal is None
        or action.session_id != request.session.id
        or action.goal_id != request.goal.id
        or probe.session_id != request.session.id
        or probe.goal_id != request.goal.id
        or probe.harness_type != request.session.harness_type
        or probe.project_id != (request.session.project_id or request.goal.project_id)
        or probe.request_event_id != request.event.event_id
        or not request.session.cwd
        or not same_absolute_path(probe.cwd, request.session.cwd)
    ):
        return None
    payload = action.payload
    if set(payload) - {"probe", "probe_id", "kind", "text"}:
        return None
    if "probe_id" in payload and payload["probe_id"] != probe.id:
        return None
    if "kind" in payload and payload["kind"] != probe.kind.value:
        return None
    canonical = probe.model_dump(mode="json")
    if "probe" in payload:
        candidate = payload["probe"]
        # Model-facing evidence and the proposal parser redact workspace paths.
        # Accept that exact projection, never arbitrary partial probe objects.
        if candidate != canonical and candidate != _redact_payload_value(request, canonical):
            return None
    elif payload.get("probe_id") != probe.id or payload.get("kind") != probe.kind.value:
        return None
    if not isinstance(payload.get("text", ""), str):
        return None
    # A correct reference must not authorize unrelated instructions smuggled in
    # model prose. REQUEST_VERIFICATION has a closed, bridge-owned scope even
    # when the model returned a full canonical probe and an approved message.
    text = _verification_request_copy(probe.kind.value, list(probe.relative_targets), [])
    return action.model_copy(update={"payload": {"probe": canonical, "text": text}})
