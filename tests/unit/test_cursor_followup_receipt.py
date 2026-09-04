from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pex_bridge.adapters.base import (
    CursorHookPreparation,
    resolve_adapter_message_result,
)
from pex_bridge.adapters.cursor import CursorAdapter
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, EventType, PolicyVerdict
from pex_protocol.intervention import Intervention


def _receipt(
    session_id: str,
    text: str,
    preparation_receipt: dict[str, str],
) -> Intervention:
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=session_id,
        goal_id="goal-cursor-receipt",
        payload={"text": text},
        rationale="Observed acceptance evidence is missing.",
        evidence=["missing:report.txt"],
        risk=RiskLevel.LOW,
        authority_required=Authority.LOCAL_POLICY,
    )
    return Intervention(
        id="int-cursor-stop",
        session_id=session_id,
        goal_id="goal-cursor-receipt",
        trigger=EventType.STOP.value,
        evidence=list(action.evidence),
        diagnosis="Missing required acceptance evidence.",
        proposed_action=action,
        risk=action.risk.value,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="hook_followup_prepared_delivery_uncertain",
        created_at=datetime.now(UTC),
        metadata={"hook_preparation_receipt": preparation_receipt},
    )


async def _queued_stop(text: str = "Verify report.txt"):
    adapter = CursorAdapter()
    payload = {"hook_event_name": "stop", "conversation_id": "cursor-receipt"}
    session = adapter.upsert_from_hook(payload)
    session.goal_id = "goal-cursor-receipt"
    adapter.normalize_hook(payload, session)
    prepared = await adapter.send_message(session, text)
    assert isinstance(prepared, CursorHookPreparation)
    preparation_receipt = resolve_adapter_message_result(
        prepared,
        session=session,
    ).hook_preparation_receipt
    assert preparation_receipt is not None
    return adapter, session, preparation_receipt


@pytest.mark.asyncio
async def test_cursor_stop_followup_requires_exact_preparation_receipt():
    text = "Verify report.txt"
    adapter, session, preparation_receipt = await _queued_stop(text)
    assert (
        adapter.consume_verified_stop_followup(
            session,
            _receipt(session.id, text, preparation_receipt),
        )
        == text
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("policy_verdict", PolicyVerdict.DENY),
        ("result", "denied_by_policy"),
        ("result", "send_failed"),
        ("trigger", EventType.STATUS.value),
        ("action_taken", InterventionType.NOOP.value),
        ("session_id", "cursor:other"),
        ("evidence", []),
    ],
)
async def test_cursor_stop_discards_unverified_or_denied_pending_text(mutation, value):
    text = "Verify report.txt"
    adapter, session, preparation_receipt = await _queued_stop(text)
    invalid = _receipt(session.id, text, preparation_receipt).model_copy(
        update={mutation: value}
    )
    assert adapter.consume_verified_stop_followup(session, invalid) is None
    # A rejected receipt consumes the pending text; it cannot leak to a later stop.
    assert (
        adapter.consume_verified_stop_followup(
            session,
            _receipt(session.id, text, preparation_receipt),
        )
        is None
    )


@pytest.mark.asyncio
async def test_cursor_stop_requires_payload_text_to_match_delivered_text():
    text = "Verify report.txt"
    adapter, session, preparation_receipt = await _queued_stop(text)
    receipt = _receipt(
        session.id,
        "Run a different check",
        preparation_receipt,
    )
    assert adapter.consume_verified_stop_followup(session, receipt) is None
