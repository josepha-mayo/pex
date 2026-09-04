from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from pex_bridge.adapters.base import (
    CURSOR_HOOK_PREPARATION_SCHEMA,
    CursorHookPreparation,
    resolve_adapter_message_result,
    validate_cursor_hook_preparation_receipt,
)
from pex_bridge.adapters.cursor import CursorAdapter
from pex_bridge.executor import ActionExecutionResult, _message_execution_result
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, EventType, HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessSession


def _active_stop(
    adapter: CursorAdapter,
    *,
    conversation_id: str = "cursor-prepared",
    generation_id: str = "generation-1",
):
    payload = {
        "hook_event_name": "stop",
        "conversation_id": conversation_id,
        "generation_id": generation_id,
    }
    session = adapter.upsert_from_hook(payload)
    session.goal_id = "goal-1"
    event = adapter.normalize_hook(payload, session)
    return session, event, payload


def _intervention(
    session: HarnessSession,
    text: str,
    receipt: dict[str, str],
    *,
    result: str = "hook_followup_prepared_delivery_uncertain",
    verdict: PolicyVerdict = PolicyVerdict.ALLOW,
    goal_id: str | None = "goal-1",
    action_taken: str = InterventionType.SEND_NUDGE.value,
) -> Intervention:
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=session.id,
        goal_id=goal_id,
        payload={"text": text},
        rationale="The observed acceptance evidence is incomplete.",
        evidence=["missing:report.txt"],
        risk=RiskLevel.LOW,
        authority_required=Authority.LOCAL_POLICY,
    )
    return Intervention(
        id="int-cursor-prepared",
        session_id=session.id,
        goal_id=goal_id,
        trigger=EventType.STOP.value,
        evidence=list(action.evidence),
        diagnosis="Missing required acceptance evidence.",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action_taken,
        policy_verdict=verdict,
        result=result,
        created_at=datetime.now(UTC),
        metadata={"hook_preparation_receipt": receipt},
    )


@pytest.mark.asyncio
async def test_cursor_stop_returns_preparation_not_vendor_acceptance():
    adapter = CursorAdapter()
    session, event, _payload = _active_stop(adapter)
    text = "Inspect report.txt and complete the missing criterion."

    prepared = await adapter.send_message(session, text)

    assert isinstance(prepared, CursorHookPreparation)
    assert not hasattr(prepared, "accepted")
    assert not hasattr(prepared, "vendor_turn_id")
    assert prepared.trigger_event_id == event.event_id
    assert prepared.vendor_session_id == session.vendor_session_id
    assert prepared.message_sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert adapter.inbox[session.id] == []
    assert set(adapter.pending_followups) == {(session.id, event.event_id)}

    resolution = resolve_adapter_message_result(prepared, session=session)
    assert resolution.status == "hook_prepared"
    assert resolution.worker_delivery_receipt is None
    assert resolution.hook_preparation_receipt == {
        "schema": CURSOR_HOOK_PREPARATION_SCHEMA,
        "preparation_id": prepared.preparation_id,
        "trigger_event_id": event.event_id,
        "target_session_id": session.id,
        "vendor_session_id": session.vendor_session_id,
        "message_sha256": prepared.message_sha256,
    }


@pytest.mark.asyncio
async def test_executor_marks_hook_preparation_delivery_uncertain():
    adapter = CursorAdapter()
    session, _event, _payload = _active_stop(adapter)
    prepared = await adapter.send_message(session, "Verify report.txt before stopping.")
    assert isinstance(prepared, CursorHookPreparation)

    execution = _message_execution_result(
        prepared,
        session=session,
        accepted_outcome="sent",
        rejected_outcome="send_failed",
    )

    assert isinstance(execution, ActionExecutionResult)
    assert execution.outcome == "hook_followup_prepared_delivery_uncertain"
    assert execution.worker_delivery_receipt is None
    assert execution.hook_preparation_receipt is not None
    assert execution.hook_preparation_receipt["preparation_id"] == prepared.preparation_id


@pytest.mark.parametrize(
    "prepared",
    [
        CursorHookPreparation(" prep ", "event-1", "vendor-1", "a" * 64),
        CursorHookPreparation("prep", " event-1", "vendor-1", "a" * 64),
        CursorHookPreparation("prep", "event-1", "vendor-other", "a" * 64),
        CursorHookPreparation("prep", "event-1", "vendor-1", "A" * 64),
        CursorHookPreparation("prep", "event-1", "vendor-1", "a" * 63),
    ],
)
def test_preparation_resolution_rejects_non_exact_ids_vendor_and_hash(prepared):
    session = HarnessSession(
        id="cursor:vendor-1",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="vendor-1",
        status=SessionStatus.IDLE,
    )

    resolution = resolve_adapter_message_result(prepared, session=session)

    assert resolution.status == "delivery_uncertain"
    assert resolution.worker_delivery_receipt is None
    assert resolution.hook_preparation_receipt is None


def test_preparation_receipt_is_cursor_only():
    session = HarnessSession(
        id="codex:vendor-1",
        harness_type=HarnessType.CODEX,
        vendor_session_id="vendor-1",
        status=SessionStatus.IDLE,
    )
    prepared = CursorHookPreparation("prep", "event-1", "vendor-1", "a" * 64)

    assert resolve_adapter_message_result(prepared, session=session).status == (
        "delivery_uncertain"
    )


def test_preparation_receipt_requires_canonical_cursor_session_id():
    session = HarnessSession(
        id="cursor:other",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="vendor-1",
        status=SessionStatus.IDLE,
    )
    prepared = CursorHookPreparation("prep", "event-1", "vendor-1", "a" * 64)

    assert resolve_adapter_message_result(prepared, session=session).status == (
        "delivery_uncertain"
    )


@pytest.mark.asyncio
async def test_generation_and_pending_followups_are_bound_to_exact_stop_events():
    adapter = CursorAdapter()
    session, first, first_payload = _active_stop(adapter, generation_id="generation-1")
    first_text = "First exact correction."
    first_prepared = await adapter.send_message(session, first_text)
    assert isinstance(first_prepared, CursorHookPreparation)

    second_payload = {**first_payload, "generation_id": "generation-2"}
    second = adapter.normalize_hook(second_payload, session)
    second_text = "Second exact correction."
    second_prepared = await adapter.send_message(session, second_text)
    assert isinstance(second_prepared, CursorHookPreparation)

    assert first.metadata["generation_id"] == "generation-1"
    assert second.metadata["generation_id"] == "generation-2"
    assert adapter._active_hook.get() == (session.id, "stop", second.event_id)
    assert set(adapter.pending_followups) == {
        (session.id, first.event_id),
        (session.id, second.event_id),
    }

    first_receipt = resolve_adapter_message_result(
        first_prepared, session=session
    ).hook_preparation_receipt
    assert first_receipt is not None
    assert (
        adapter.consume_verified_stop_followup(
            session,
            _intervention(session, first_text, first_receipt),
        )
        is None
    )
    assert (session.id, first.event_id) in adapter.pending_followups
    assert (session.id, second.event_id) not in adapter.pending_followups


@pytest.mark.asyncio
async def test_verified_prepared_outcome_exposes_exact_followup_without_fake_sent():
    adapter = CursorAdapter()
    session, event, _payload = _active_stop(adapter)
    text = "Verify report.txt before stopping."
    prepared = await adapter.send_message(session, text)
    assert isinstance(prepared, CursorHookPreparation)
    receipt = resolve_adapter_message_result(
        prepared, session=session
    ).hook_preparation_receipt
    assert receipt is not None

    intervention = _intervention(session, text, receipt)

    assert intervention.result != "sent"
    assert "worker_delivery_receipt" not in intervention.metadata
    assert adapter.consume_verified_stop_followup(session, intervention) == text
    assert (session.id, event.event_id) not in adapter.pending_followups


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "preparation_id",
        "trigger_event_id",
        "target_session_id",
        "vendor_session_id",
        "message_sha256",
        "policy",
        "goal",
        "action_goal",
        "action",
        "result",
        "payload",
        "worker_receipt",
    ],
)
async def test_followup_consumption_fails_closed_on_any_binding_mismatch(mutation):
    adapter = CursorAdapter()
    session, event, _payload = _active_stop(adapter)
    text = "Verify report.txt before stopping."
    prepared = await adapter.send_message(session, text)
    assert isinstance(prepared, CursorHookPreparation)
    receipt = resolve_adapter_message_result(
        prepared, session=session
    ).hook_preparation_receipt
    assert receipt is not None

    changed_receipt = dict(receipt)
    kwargs = {}
    if mutation in changed_receipt:
        changed_receipt[mutation] = (
            "b" * 64 if mutation == "message_sha256" else f"wrong-{mutation}"
        )
    elif mutation == "policy":
        kwargs["verdict"] = PolicyVerdict.DENY
    elif mutation == "goal":
        kwargs["goal_id"] = "goal-other"
    elif mutation == "action":
        kwargs["action_taken"] = InterventionType.NOOP.value
    elif mutation == "result":
        kwargs["result"] = "sent"
    intervention = _intervention(session, text, changed_receipt, **kwargs)
    if mutation == "payload":
        action = intervention.proposed_action.model_copy(
            update={"payload": {"text": "Different correction."}}
        )
        intervention = intervention.model_copy(update={"proposed_action": action})
    elif mutation == "action_goal":
        action = intervention.proposed_action.model_copy(
            update={"goal_id": "goal-other"}
        )
        intervention = intervention.model_copy(update={"proposed_action": action})
    elif mutation == "worker_receipt":
        intervention.metadata["worker_delivery_receipt"] = {
            "schema": "pex.worker-delivery.v1"
        }

    assert adapter.consume_verified_stop_followup(session, intervention) is None
    assert (session.id, event.event_id) not in adapter.pending_followups


@pytest.mark.asyncio
async def test_unverified_consume_api_only_discards_exact_event():
    adapter = CursorAdapter()
    session, event, _payload = _active_stop(adapter)
    prepared = await adapter.send_message(session, "Do not expose this text.")
    assert isinstance(prepared, CursorHookPreparation)

    assert (
        adapter.consume_followup(session.id, trigger_event_id=event.event_id) is None
    )
    assert (session.id, event.event_id) not in adapter.pending_followups


def test_validator_rejects_extra_keys():
    session = HarnessSession(
        id="cursor:vendor-1",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="vendor-1",
        status=SessionStatus.IDLE,
    )
    receipt = {
        "schema": CURSOR_HOOK_PREPARATION_SCHEMA,
        "preparation_id": "prep",
        "trigger_event_id": "event-1",
        "target_session_id": session.id,
        "vendor_session_id": session.vendor_session_id,
        "message_sha256": "a" * 64,
        "accepted": "forged",
    }

    with pytest.raises(ValueError, match="invalid keys"):
        validate_cursor_hook_preparation_receipt(receipt, session=session)
