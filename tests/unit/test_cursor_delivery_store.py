from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta

import pex_bridge.store as store_module
import pytest
from pex_bridge.cursor_delivery import CURSOR_HOOK_PREPARED_OUTCOME
from pex_bridge.store import Store, utcnow
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import EventPhase, EventType, HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession


def _plan(event: HarnessEvent, intervention: Intervention) -> dict:
    return {
        "schema": "pex.event-plan.v1",
        "event_id": event.event_id,
        "session_id": event.session_id,
        "goal_id": event.goal_id,
        "project_id": event.project_id,
        "effect_kind": "worker_action",
        "intervention_id": intervention.id,
        "action": intervention.proposed_action.model_dump(mode="json"),
        "required_capability": "send_message",
        "context_ids": [],
        "decision_ids": [],
        "intervention_update_ids": [],
    }


async def _prepared_cursor(
    store: Store,
    *,
    expected_authority_overrides: dict | None = None,
) -> tuple[dict, HarnessSession, Goal, Intervention]:
    now = utcnow()
    goal = Goal(
        id="goal-cursor-delivery",
        project_id="C:/cursor-delivery",
        title="Finish Cursor task",
        objective="Create the required report with evidence.",
        acceptance_criteria=["report exists"],
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    session = HarnessSession(
        id="cursor:conversation-one",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="conversation-one",
        project_id=goal.project_id,
        goal_id=goal.id,
        status=SessionStatus.WORKING,
        capabilities={"send_message": True},
        last_activity=now,
        metadata={"discovery_generation": "discovery-one"},
    )
    await store.upsert_session(session)
    event = HarnessEvent(
        event_id="cursor:conversation-one:hook:stop-one",
        ts=now,
        harness_type=HarnessType.CURSOR,
        session_id=session.id,
        project_id=goal.project_id,
        goal_id=goal.id,
        event_type=EventType.STOP,
        phase=EventPhase.TERMINAL,
        message_delta="done",
        metadata={
            "hook_event_name": "stop",
            "conversation_id": session.vendor_session_id,
            "generation_id": "generation-one",
        },
    )
    await store.accept_pipeline_event(event, session_snapshot=session)
    claim = await store.claim_event_processing(event.event_id, owner="cursor-test-owner")
    assert claim["outcome"] == "claimed"

    text = "  Check report.txt against the acceptance criterion.  "
    message_sha256 = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
    preparation_receipt = {
        "schema": "pex.cursor-hook-preparation.v1",
        "preparation_id": "cursor-prep-one",
        "trigger_event_id": event.event_id,
        "target_session_id": session.id,
        "vendor_session_id": session.vendor_session_id,
        "message_sha256": message_sha256,
    }
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=session.id,
        goal_id=goal.id,
        payload={"text": text},
        rationale="The required report is not verified.",
        evidence=["missing:report.txt"],
        risk=RiskLevel.LOW,
        requires_capability="send_message",
    )
    reserved = Intervention(
        id="int-cursor-delivery",
        session_id=session.id,
        goal_id=goal.id,
        trigger=EventType.STOP.value,
        evidence=list(action.evidence),
        diagnosis="Required evidence is missing.",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="delivery_reserved",
        created_at=event.ts,
        metadata={"trigger_event_id": event.event_id},
    )
    payload = {
        "schema": "pex.worker-effect.v1",
        "event_id": event.event_id,
        "intervention_id": reserved.id,
        "action": action.model_dump(mode="json"),
        "required_capability": "send_message",
    }
    request_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    await store.commit_event_plan(
        event_id=event.event_id,
        owner="cursor-test-owner",
        plan=_plan(event, reserved),
        session=session,
        intervention=reserved,
        main_effect={
            "effect_key": "main",
            "kind": "worker_action",
            "target_session_id": session.id,
            "payload": payload,
            "request_hash": request_hash,
        },
    )
    dispatch = await store.claim_main_event_effect(
        event_id=event.event_id,
        owner="cursor-test-owner",
    )
    assert dispatch["granted"] is True
    effect = dispatch["effect"]
    effect_result = {
        "status": "delivery_uncertain",
        "outcome": CURSOR_HOOK_PREPARED_OUTCOME,
        "code": CURSOR_HOOK_PREPARED_OUTCOME,
        "effect_id": effect["effect_id"],
        "hook_preparation_receipt": preparation_receipt,
    }
    final = reserved.model_copy(deep=True)
    final.result = CURSOR_HOOK_PREPARED_OUTCOME
    final.outcome = "worker_delivery_uncertain"
    final.helped = None
    final.metadata.update(
        {
            "delivery": CURSOR_HOOK_PREPARED_OUTCOME,
            "delivery_code": CURSOR_HOOK_PREPARED_OUTCOME,
            "effect_id": effect["effect_id"],
            "effect_state": "delivery_uncertain",
            "hook_preparation_receipt": preparation_receipt,
        }
    )
    processing_receipt = {
        "schema": "pex.event-processing.receipt.v1",
        "event_id": event.event_id,
        "status": "complete",
        "effect_id": effect["effect_id"],
        "effect_state": "delivery_uncertain",
        "effect_result": effect_result,
        "downstream_operation_id": None,
        "intervention": final.model_dump(mode="json"),
    }
    await store.finalize_event_processing(
        event_id=event.event_id,
        effect_state="delivery_uncertain",
        effect_result=effect_result,
        intervention=final,
        receipt=processing_receipt,
        session=session,
    )
    control = await store.get_session_control_state(session.id)
    intent = await store.get_goal_intent_view(goal.id)
    assert control is not None and intent is not None
    expected_authority = {
        "control_revision": control["control_revision"],
        "project_binding": control["project_binding"],
        "discovery_generation": control["discovery_generation"],
        "goal_id": goal.id,
        "intent_revision": intent["intent_revision"],
        "intent_hash": intent["intent_hash"],
    }
    expected_authority.update(expected_authority_overrides or {})
    packet = await store.prepare_cursor_hook_delivery(
        final.id,
        preparation_receipt,
        expected_authority=expected_authority,
    )
    return packet, session, goal, final


async def _accept_activity(
    store: Store,
    session: HarnessSession,
    goal: Goal,
    *,
    event_id: str,
    event_type: EventType,
    generation_id: str,
) -> HarnessEvent:
    event = HarnessEvent(
        event_id=event_id,
        ts=utcnow(),
        harness_type=HarnessType.CURSOR,
        session_id=session.id,
        project_id=goal.project_id,
        goal_id=goal.id,
        event_type=event_type,
        phase=(
            EventPhase.BEFORE if event_type == EventType.USER_PROMPT else EventPhase.AFTER
        ),
        message_delta="activity" if event_type == EventType.AGENT_RESPONSE else None,
        metadata={
            "hook_event_name": "afterAgentResponse",
            "conversation_id": session.vendor_session_id,
            "generation_id": generation_id,
        },
    )
    await store.accept_pipeline_event(event, session_snapshot=session)
    return event


@pytest.mark.asyncio
async def test_cursor_flush_is_append_only_idempotent_and_stays_uncertain(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        packet, session, _, final = await _prepared_cursor(store)
        assert set(packet) == {
            "schema",
            "preparation_id",
            "intervention_id",
            "trigger_event_id",
            "target_session_id",
            "vendor_session_id",
            "goal_id",
            "message_sha256",
            "nonce",
        }
        stored = await store.db.execute_fetchall(
            "SELECT json FROM cursor_hook_preparations WHERE preparation_id = ?",
            (packet["preparation_id"],),
        )
        assert packet["nonce"] not in stored[0]["json"]
        with pytest.raises(ValueError, match="already exists"):
            control = await store.get_session_control_state(session.id)
            intent = await store.get_goal_intent_view(final.goal_id)
            assert control is not None and intent is not None
            await store.prepare_cursor_hook_delivery(
                final.id,
                final.metadata["hook_preparation_receipt"],
                expected_authority={
                    "control_revision": control["control_revision"],
                    "project_binding": control["project_binding"],
                    "discovery_generation": control["discovery_generation"],
                    "goal_id": final.goal_id,
                    "intent_revision": intent["intent_revision"],
                    "intent_hash": intent["intent_hash"],
                },
            )
        with pytest.raises(PermissionError, match="nonce"):
            await store.record_cursor_hook_flush(
                {**packet, "nonce": "0" * 64}, project_id=session.project_id
            )
        first = await store.record_cursor_hook_flush(packet, project_id=session.project_id)
        assert first["delivery_evidence"] == "hook_stdout_flushed"
        assert first["vendor_acceptance_proven"] is False
        assert (
            await store.record_cursor_hook_flush(packet, project_id=session.project_id)
            == first
        )
        stored_intervention = await store.get_intervention(final.id)
        assert stored_intervention is not None
        assert stored_intervention.result == CURSOR_HOOK_PREPARED_OUTCOME
        assert stored_intervention.outcome == "worker_delivery_uncertain"
        assert stored_intervention.helped is None
        assert stored_intervention.metadata["cursor_hook_delivery"]["state"] == (
            "hook_stdout_flushed"
        )
        assert stored_intervention.metadata["cursor_hook_delivery"][
            "prompt_coverage_complete"
        ] is False
        assert stored_intervention.metadata["cursor_hook_delivery"][
            "causal_continuation_proven"
        ] is False
        assert "worker_delivery_receipt" not in stored_intervention.metadata
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            await store.db.execute(
                "UPDATE cursor_hook_flush_receipts SET message_sha256 = ?",
                ("0" * 64,),
            )
    finally:
        await store.db.rollback()
        await store.close()


@pytest.mark.asyncio
async def test_cursor_continuation_requires_ordered_distinct_generation(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        packet, session, goal, final = await _prepared_cursor(store)
        await store.record_cursor_hook_flush(packet, project_id=session.project_id)
        same_generation = await _accept_activity(
            store,
            session,
            goal,
            event_id="cursor:same-generation",
            event_type=EventType.AGENT_RESPONSE,
            generation_id="generation-one",
        )
        assert await store.observe_cursor_hook_continuation(same_generation.event_id) is None
        continued = await _accept_activity(
            store,
            session,
            goal,
            event_id="cursor:new-generation",
            event_type=EventType.AGENT_RESPONSE,
            generation_id="generation-two",
        )
        observation = await store.observe_cursor_hook_continuation(continued.event_id)
        assert observation is not None
        assert observation["observation"] == "same_session_activity_observed"
        assert observation["vendor_acceptance_proven"] is False
        assert observation["observed_generation"] == "generation-two"
        assert await store.observe_cursor_hook_continuation(continued.event_id) == observation
        stored = await store.get_intervention(final.id)
        assert stored is not None
        assert stored.result == CURSOR_HOOK_PREPARED_OUTCOME
        assert stored.outcome == "same_session_activity_observed"
        assert stored.helped is None
        assert stored.metadata["cursor_hook_delivery"]["vendor_acceptance_proven"] is False
        assert stored.metadata["cursor_hook_delivery"]["prompt_coverage_complete"] is False
        assert stored.metadata["cursor_hook_delivery"]["causal_continuation_proven"] is False
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cursor_intervening_user_prompt_blocks_causal_credit(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        packet, session, goal, final = await _prepared_cursor(store)
        await store.record_cursor_hook_flush(packet, project_id=session.project_id)
        await _accept_activity(
            store,
            session,
            goal,
            event_id="cursor:human-prompt",
            event_type=EventType.USER_PROMPT,
            generation_id="generation-human",
        )
        later = await _accept_activity(
            store,
            session,
            goal,
            event_id="cursor:after-human-prompt",
            event_type=EventType.AGENT_RESPONSE,
            generation_id="generation-two",
        )
        result = await store.observe_cursor_hook_continuation(later.event_id)
        assert result == {
            "status": "causality_ambiguous_intervening_user_prompt",
            "event_id": later.event_id,
        }
        rows = await store.db.execute_fetchall("SELECT * FROM cursor_hook_continuations")
        assert rows == []
        stored = await store.get_intervention(final.id)
        assert stored is not None
        assert stored.outcome == "worker_delivery_uncertain"
        assert stored.metadata["cursor_hook_delivery"]["state"] == "hook_stdout_flushed"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cursor_control_drift_blocks_continuation_but_not_historical_flush(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        packet, session, goal, _ = await _prepared_cursor(store)
        changed = session.model_copy(deep=True)
        changed.supervision_paused = True
        changed.last_activity = utcnow()
        await store.upsert_session(changed, allow_supervision_change=True)
        # The callback records the already-observed stdout flush despite later control drift.
        assert (
            await store.record_cursor_hook_flush(packet, project_id=session.project_id)
        )["delivery_evidence"] == "hook_stdout_flushed"
        event = await _accept_activity(
            store,
            changed,
            goal,
            event_id="cursor:paused-continuation",
            event_type=EventType.AGENT_RESPONSE,
            generation_id="generation-two",
        )
        assert await store.observe_cursor_hook_continuation(event.event_id) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cursor_first_flush_rejects_wrong_project_boot_and_late_event(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="cursor-boot-one")
    await store.connect()
    try:
        packet, session, goal, _ = await _prepared_cursor(store)
        with pytest.raises(PermissionError, match="project binding"):
            await store.record_cursor_hook_flush(packet, project_id="C:/other-project")

        store.process_boot_id = "cursor-boot-two"
        with pytest.raises(PermissionError, match="expired"):
            await store.record_cursor_hook_flush(packet, project_id=session.project_id)
        store.process_boot_id = "cursor-boot-one"

        await _accept_activity(
            store,
            session,
            goal,
            event_id="cursor:activity-before-flush",
            event_type=EventType.AGENT_RESPONSE,
            generation_id="generation-two",
        )
        with pytest.raises(PermissionError, match="stale"):
            await store.record_cursor_hook_flush(packet, project_id=session.project_id)
        rows = await store.db.execute_fetchall("SELECT * FROM cursor_hook_flush_receipts")
        assert rows == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cursor_exact_flush_replay_survives_later_boot_change(tmp_path):
    path = tmp_path / "pex.sqlite"
    store = Store(path, process_boot_id="cursor-boot-one")
    await store.connect()
    try:
        packet, session, _, _ = await _prepared_cursor(store)
        first = await store.record_cursor_hook_flush(packet, project_id=session.project_id)
    finally:
        await store.close()

    reopened = Store(path, process_boot_id="cursor-boot-two")
    await reopened.connect()
    try:
        assert (
            await reopened.record_cursor_hook_flush(packet, project_id=session.project_id)
            == first
        )
        with pytest.raises(PermissionError, match="project binding"):
            await reopened.record_cursor_hook_flush(packet, project_id="C:/other-project")
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_cursor_first_flush_rejects_delayed_ack(tmp_path, monkeypatch):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="cursor-boot-one")
    await store.connect()
    try:
        packet, session, _, _ = await _prepared_cursor(store)
        row = (
            await store.db.execute_fetchall(
                "SELECT prepared_at FROM cursor_hook_preparations "
                "WHERE preparation_id = ?",
                (packet["preparation_id"],),
            )
        )[0]
        delayed = datetime.fromisoformat(row["prepared_at"]) + timedelta(seconds=31)
        monkeypatch.setattr(store_module, "utcnow", lambda: delayed)
        with pytest.raises(PermissionError, match="expired"):
            await store.record_cursor_hook_flush(packet, project_id=session.project_id)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cursor_prepare_rejects_stale_expected_authority_without_mint(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        with pytest.raises(PermissionError, match="authority changed"):
            await _prepared_cursor(
                store,
                expected_authority_overrides={"control_revision": 999},
            )
        rows = await store.db.execute_fetchall("SELECT * FROM cursor_hook_preparations")
        assert rows == []
    finally:
        await store.close()
