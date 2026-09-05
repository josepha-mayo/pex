"""Fail-closed OpenCode worker-message lineage checks.

OpenCode identifies a worker response by an assistant message whose ``parentID``
is the admitted user-message ID.  Session activity and ``session.idle`` do not
carry that relationship and are therefore not sufficient outcome evidence.
"""

from __future__ import annotations

from typing import Any

from pex_protocol.actions import InterventionType
from pex_protocol.enums import EventType, HarnessType, PolicyVerdict
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.base import (
    WORKER_DELIVERY_SCHEMA_GENERIC,
    bounded_adapter_id,
    validate_worker_delivery_receipt_binding,
)

OPENCODE_MESSAGE_LINEAGE_SCHEMA = "pex.opencode-message-lineage.v1"
OPENCODE_MESSAGE_LINEAGE_KEY = "opencode_message_lineage"
OPENCODE_MESSAGE_LINEAGE_KEYS = frozenset(
    {
        "schema",
        "target_session_id",
        "vendor_session_id",
        "message_id",
        "role",
        "parent_message_id",
        "source_event_type",
        "stream_contiguous",
        "parent_removed_observed",
        "assistant_message_completed",
        "assistant_message_error",
        "assistant_finish",
    }
)
_MESSAGE_ACTIONS = frozenset(
    {
        InterventionType.SEND_NUDGE,
        InterventionType.CONTINUE_SESSION,
        InterventionType.INJECT_CONTEXT,
        InterventionType.REQUEST_VERIFICATION,
        InterventionType.FRESH_HANDOFF,
    }
)
_MESSAGE_RESULTS = {
    InterventionType.SEND_NUDGE: "sent",
    InterventionType.INJECT_CONTEXT: "sent",
    InterventionType.CONTINUE_SESSION: "continued",
    InterventionType.REQUEST_VERIFICATION: "verification_requested",
    InterventionType.FRESH_HANDOFF: "handoff_injected",
}
_DESCENDANT_EVENT_TYPES = frozenset(
    {
        EventType.AGENT_RESPONSE,
        EventType.AGENT_THOUGHT,
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
        EventType.TOOL_FAILURE,
        EventType.ERROR,
        EventType.STOP,
    }
)


def opencode_message_lineage(
    *,
    session: HarnessSession,
    message_id: object,
    role: object,
    parent_message_id: object | None,
    source_event_type: object,
    stream_contiguous: bool,
    parent_removed_observed: bool = False,
    assistant_message_completed: bool = False,
    assistant_message_error: bool = False,
    assistant_finish: object = "",
) -> dict[str, Any] | None:
    """Return one bounded vendor lineage record, or ``None`` if incomplete."""

    if (
        session.harness_type != HarnessType.OPENCODE
        or session.id != f"opencode:{session.vendor_session_id}"
        or type(stream_contiguous) is not bool
        or type(parent_removed_observed) is not bool
        or type(assistant_message_completed) is not bool
        or type(assistant_message_error) is not bool
    ):
        return None
    try:
        bounded_message_id = bounded_adapter_id(message_id, field="OpenCode message id")
        bounded_role = bounded_adapter_id(role, field="OpenCode message role")
        bounded_source = bounded_adapter_id(
            source_event_type, field="OpenCode lineage source event type"
        )
        bounded_parent = (
            bounded_adapter_id(parent_message_id, field="OpenCode parent message id")
            if parent_message_id is not None and parent_message_id != ""
            else ""
        )
        bounded_finish = (
            bounded_adapter_id(assistant_finish, field="OpenCode assistant finish")
            if assistant_finish is not None and assistant_finish != ""
            else ""
        )
    except (TypeError, ValueError):
        return None
    if (
        not bounded_message_id
        or not bounded_source
        or message_id != bounded_message_id
        or role != bounded_role
        or source_event_type != bounded_source
        or (
            parent_message_id not in {None, ""}
            and parent_message_id != bounded_parent
        )
        or (
            assistant_finish not in {None, ""}
            and assistant_finish != bounded_finish
        )
        or bounded_role not in {"user", "assistant"}
    ):
        return None
    if bounded_role == "assistant" and not bounded_parent:
        return None
    if bounded_role == "user" and bounded_parent:
        return None
    if bounded_role != "assistant" and (
        assistant_message_completed or assistant_message_error or bounded_finish
    ):
        return None
    if assistant_message_completed and assistant_message_error:
        return None
    return {
        "schema": OPENCODE_MESSAGE_LINEAGE_SCHEMA,
        "target_session_id": session.id,
        "vendor_session_id": session.vendor_session_id,
        "message_id": bounded_message_id,
        "role": bounded_role,
        "parent_message_id": bounded_parent,
        "source_event_type": bounded_source,
        "stream_contiguous": stream_contiguous,
        "parent_removed_observed": parent_removed_observed,
        "assistant_message_completed": assistant_message_completed,
        "assistant_message_error": assistant_message_error,
        "assistant_finish": bounded_finish,
    }


def _validated_event_lineage(event: HarnessEvent) -> dict[str, Any] | None:
    candidate = (event.metadata or {}).get(OPENCODE_MESSAGE_LINEAGE_KEY)
    if not isinstance(candidate, dict) or set(candidate) != OPENCODE_MESSAGE_LINEAGE_KEYS:
        return None
    if (
        candidate.get("schema") != OPENCODE_MESSAGE_LINEAGE_SCHEMA
        or candidate.get("stream_contiguous") is not True
        or candidate.get("parent_removed_observed") is not False
        or candidate.get("role") != "assistant"
        or candidate.get("source_event_type")
        not in {"message.updated", "message.part.updated"}
    ):
        return None
    try:
        normalized = opencode_message_lineage(
            session=HarnessSession(
                id=bounded_adapter_id(
                    candidate.get("target_session_id"),
                    field="OpenCode lineage target session id",
                ),
                harness_type=HarnessType.OPENCODE,
                vendor_session_id=bounded_adapter_id(
                    candidate.get("vendor_session_id"),
                    field="OpenCode lineage vendor session id",
                ),
            ),
            message_id=candidate.get("message_id"),
            role=candidate.get("role"),
            parent_message_id=candidate.get("parent_message_id"),
            source_event_type=candidate.get("source_event_type"),
            stream_contiguous=candidate.get("stream_contiguous"),
            parent_removed_observed=candidate.get("parent_removed_observed"),
            assistant_message_completed=candidate.get("assistant_message_completed"),
            assistant_message_error=candidate.get("assistant_message_error"),
            assistant_finish=candidate.get("assistant_finish"),
        )
    except (TypeError, ValueError):
        return None
    return normalized if normalized == candidate else None


def event_matches_opencode_delivery(
    intervention: Intervention,
    session: HarnessSession,
    event: HarnessEvent,
) -> bool:
    """Whether ``event`` is a vendor-proven descendant of this PEX prompt.

    This deliberately rejects idle/status/file events and any assistant event
    whose exact OpenCode ``parentID`` was not preserved through normalization.
    """

    action = intervention.proposed_action
    ordinary_delivery = bool(
        action.type in _MESSAGE_ACTIONS
        and intervention.policy_verdict == PolicyVerdict.ALLOW
        and intervention.result == _MESSAGE_RESULTS.get(action.type)
        and (intervention.metadata or {}).get("effect_state") == "delivered"
    )
    human_resolution = (intervention.metadata or {}).get("human_decision_resolution")
    human_decision_delivery = bool(
        action.type == InterventionType.ASK_HUMAN
        and intervention.policy_verdict == PolicyVerdict.ASK_HUMAN
        and intervention.result == "human_decision_delivered"
        and isinstance(human_resolution, dict)
        and human_resolution.get("status") == "delivered"
    )
    if (
        session.harness_type != HarnessType.OPENCODE
        or session.id != f"opencode:{session.vendor_session_id}"
        or event.harness_type != HarnessType.OPENCODE
        or event.session_id != session.id
        or event.project_id != session.project_id
        or event.event_type not in _DESCENDANT_EVENT_TYPES
        or intervention.session_id != session.id
        or intervention.goal_id is None
        or intervention.goal_id != session.goal_id
        or event.goal_id != intervention.goal_id
        or intervention.action_taken != action.type.value
        or not (ordinary_delivery or human_decision_delivery)
    ):
        return False
    receipt = (intervention.metadata or {}).get("worker_delivery_receipt")
    try:
        normalized_receipt = validate_worker_delivery_receipt_binding(
            receipt,
            target_session_id=session.id,
            vendor_session_id=session.vendor_session_id,
            harness_type=session.harness_type,
        )
    except (TypeError, ValueError):
        return False
    if (
        receipt != normalized_receipt
        or normalized_receipt.get("schema") != WORKER_DELIVERY_SCHEMA_GENERIC
    ):
        return False
    lineage = _validated_event_lineage(event)
    if lineage is None:
        return False
    clean_terminal = (
        event.event_type == EventType.STOP
        and lineage["source_event_type"] == "message.updated"
        and lineage["assistant_message_completed"] is True
        and lineage["assistant_message_error"] is False
        and lineage["assistant_finish"] == "stop"
    )
    error_terminal = (
        event.event_type == EventType.ERROR
        and lineage["source_event_type"] == "message.updated"
        and lineage["assistant_message_error"] is True
        and lineage["assistant_message_completed"] is False
    )
    intermediate = (
        event.event_type
        in {
            EventType.AGENT_RESPONSE,
            EventType.AGENT_THOUGHT,
            EventType.TOOL_CALL,
            EventType.TOOL_RESULT,
            EventType.TOOL_FAILURE,
        }
        and lineage["assistant_message_completed"] is False
        and lineage["assistant_message_error"] is False
    )
    if not (clean_terminal or error_terminal or intermediate):
        return False
    return bool(
        lineage["target_session_id"] == session.id
        and lineage["vendor_session_id"] == session.vendor_session_id
        and lineage["message_id"] != normalized_receipt["vendor_turn_id"]
        and lineage["parent_message_id"] == normalized_receipt["vendor_turn_id"]
    )
