from datetime import UTC, datetime

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.cursor import CursorAdapter
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import EventPhase, EventType, HarnessType, PolicyVerdict
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession


def _case(harness, *, project_id="C:/outcome-test"):
    now = datetime.now(UTC)
    session = HarnessSession(
        id=f"{harness.value}:worker", vendor_session_id="worker",
        harness_type=harness, project_id=project_id, goal_id="goal-outcome",
    )
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE, session_id=session.id,
        goal_id=session.goal_id, payload={"text": "Verify the required report."},
        rationale="An acceptance criterion is missing.", evidence=["missing:report.txt"],
    )
    intervention = Intervention(
        id="int-outcome", session_id=session.id, goal_id=session.goal_id,
        trigger=EventType.STOP.value, evidence=action.evidence,
        diagnosis=action.rationale, proposed_action=action,
        confidence=action.confidence, risk=action.risk.value,
        authority_required=action.authority_required.value,
        action_taken=action.type.value, policy_verdict=PolicyVerdict.ALLOW,
        result="sent", created_at=now,
        metadata={"worker_delivery_receipt": {
            "schema": "pex.worker-delivery.v1", "target_session_id": session.id,
            "vendor_session_id": session.vendor_session_id, "vendor_turn_id": "injected",
        }},
    )
    event = HarnessEvent(
        event_id="unrelated-completion", ts=now, session_id=session.id,
        harness_type=harness, project_id=project_id, goal_id=session.goal_id,
        event_type=EventType.STOP, phase=EventPhase.TERMINAL,
        message_delta="Done, all acceptance criteria are satisfied.",
    )
    return session, intervention, event


@pytest.mark.parametrize("harness", [h for h in HarnessType if h != HarnessType.CODEX])
@pytest.mark.parametrize("kind", [EventType.STOP, EventType.AGENT_RESPONSE, EventType.FILE_EDIT])
def test_generic_receipt_and_later_activity_do_not_prove_an_outcome(harness, kind):
    session, intervention, event = _case(harness)
    event.event_type = kind
    # Matching-looking metadata alone cannot turn generic activity into a receipt.
    event.metadata["vendor_turn_id"] = "injected"
    assert Pipeline._event_matches_worker_delivery(intervention, session, event) is False


@pytest.mark.asyncio
async def test_unsupported_correlation_records_unknown_not_helpful(tmp_path):
    session, intervention, event = _case(HarnessType.SYNTHETIC, project_id=str(tmp_path))
    store = Store(tmp_path / "outcomes.sqlite")
    await store.connect()
    pipeline = Pipeline(
        store, AdapterRegistry(), EventBus(),
        Settings.for_test(home=tmp_path, require_auth=False),
    )
    try:
        now = datetime.now(UTC)
        await store.upsert_goal(Goal(
            id=session.goal_id, project_id=str(tmp_path), title="Report",
            objective="Produce the report.", created_at=now, updated_at=now,
        ))
        await store.upsert_session(session)
        await store.add_intervention(intervention)
        updates = await pipeline._observe_prior_intervention(
            session, event, {"status": "supported", "acceptance_status": "supported"},
        )
        assert len(updates) == 1
        assert updates[0].helped is None
        assert updates[0].outcome == "post_delivery_activity_observed_causality_unavailable"
        assert updates[0].metadata["causal_continuation_proven"] is False
        assert updates[0].metadata["outcome_event_ids"] == [event.event_id]
        persisted = (await store.list_interventions(session.id))[0]
        assert persisted.helped is None
        assert persisted.result == "sent"  # Delivery history is not rewritten.
        audit = store._intervention_audit_record(persisted, "test")
        assert audit["causal_continuation_proven"] is False
        assert audit["helped"] is None
        assert await pipeline._observe_prior_intervention(session, event) == []
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["session", "harness", "goal", "project"])
async def test_foreign_event_cannot_even_update_unknown_outcome(changed):
    session, _, event = _case(HarnessType.SYNTHETIC)
    if changed == "session":
        event.session_id = "synthetic:foreign"
    elif changed == "harness":
        event.harness_type = HarnessType.CODEX
    elif changed == "goal":
        event.goal_id = "goal-other"
    else:
        event.project_id = "C:/other-project"
    # The identity fence must return before touching Store or publishing.
    pipeline = object.__new__(Pipeline)
    assert await pipeline._observe_prior_intervention(session, event) == []


@pytest.mark.asyncio
async def test_cursor_arbitrary_turn_query_cannot_manufacture_acceptance():
    session, _, _ = _case(HarnessType.CURSOR)
    result = await CursorAdapter().wait_for_turn_completion(session, "made-up-turn", timeout=0)
    assert result["status"] == "unsupported"
    assert result["vendor_acceptance_proven"] is False
    assert result["completion_observed"] is False
    assert "id" not in result
