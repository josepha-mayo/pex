"""Real Pipeline/Store planning with published workspace and explicit fake workers.

No provider, native worker, or actual shared mutation is enabled by these tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import test_workspace_continuity_pipeline as continuity_fixture
from pex_bridge.adapters.base import AdapterMessageResult
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.adapters.codex_subscription import CodexExistingThreadSubscription
from pex_bridge.codex_correction import CORRECTION_SCHEMA, canonical
from pex_bridge.codex_input_baseline import CodexInputBaseline
from pex_bridge.codex_input_provenance import CodexInputProvenance
from pex_bridge.store import stable_event_effect_id
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority
from pex_protocol.session import HarnessEvent
from pex_protocol.supervisor import SupervisorResult
from test_codex_subscription import (
    FakeSharedTransport,
    _authorization,
    _inspect,
    _notification,
    _thread_response,
)
from test_event_processing_pipeline import _event, _pipeline
from test_workspace_continuity_pipeline import bound_pipeline as bound_pipeline

EXACT_TEXT = "  Inspect café/report.csv against criterion 2 and finish the missing rows.\n"


@pytest.fixture
def actual_observer_baseline_without_background_consumer(monkeypatch):
    """Use real selected history and explicit ownership for each manual ingress."""

    async def subscribed(workspace):
        response = _thread_response(workspace, turns=[{
            "id": "turn-1", "status": "completed", "itemsView": "full", "items": [],
        }])
        transport = FakeSharedTransport(
            [response, response, response], _thread_response(workspace, include_turns=False),
        )
        coordinator = CodexExistingThreadSubscription(transport)
        selected = await _inspect(coordinator, workspace)
        await coordinator.subscribe(selected, _authorization(selected))
        return coordinator, transport

    def start(adapter, ingest, **kwargs):
        del ingest, kwargs
        provenance = CodexInputProvenance.from_store_records(
            (), session_id=adapter.session.id, thread_id=adapter.session.vendor_session_id,
        )
        adapter._input_provenance = provenance
        adapter._input_baseline = CodexInputBaseline.from_selected(adapter._selected, provenance)
        adapter._input_bootstrap_complete = True

        async def idle():
            await asyncio.Event().wait()

        adapter._pump_task = asyncio.create_task(idle())
        return adapter._pump_task

    monkeypatch.setattr(continuity_fixture, "_subscribed", subscribed)
    monkeypatch.setattr(CodexSharedAdapter, "start_pipeline_pump", start)


@pytest.fixture
async def correction_bound_pipeline(
    actual_observer_baseline_without_background_consumer,
    bound_pipeline,
):
    del actual_observer_baseline_without_background_consumer
    return bound_pipeline


class CorrectionSupervisor:
    """Explicit fake decision; telemetry below is fixture data, not live inference."""

    agentcore = None

    def __init__(self, *, action_type=InterventionType.SEND_NUDGE, extra=None):
        self.calls = 0
        self.action_type = action_type
        self.extra = extra or {}

    async def decide(self, request, *, local_model):
        self.calls += 1
        capability = (
            "resume" if self.action_type == InterventionType.CONTINUE_SESSION else "send_message"
        )
        return SupervisorResult(
            action=ProposedAction(
                type=self.action_type,
                session_id=request.session.id,
                goal_id=request.session.goal_id,
                payload={"text": EXACT_TEXT, **self.extra},
                rationale="Explicit fake supervisor result for durable correction testing.",
                evidence=[request.event.event_id],
                confidence=0.9,
                risk=RiskLevel.LOW,
                authority_required=Authority.LOCAL_POLICY,
                requires_capability=capability,
            ),
            used_llm=True,
            diagnosis="fixture_only_correction",
            inference_status="completed",
            execution_mode="local_model",
            model_call_count=1,
        )


@pytest.fixture
async def correction_pipeline(correction_bound_pipeline, monkeypatch):
    bound = correction_bound_pipeline
    pipeline, store = bound.pipeline, bound.store
    session = await store.get_session(bound.adapter.session.id)
    assert session.capabilities.get("send_message") is not True
    assert session.capabilities.get("resume") is not True
    status = await store.get_autonomous_correction_grant_status(session.id)
    assert status["enabled"] is False and status["scope"] is not None
    scope = status["scope"]
    grant = await store.set_session_autonomous_corrections(
        session.id,
        enabled=True,
        expected_control_revision=scope["control_revision"],
        expected_goal_id=scope["goal_id"],
        expected_goal_intent_revision=scope["goal_intent_revision"],
        expected_goal_intent_hash=scope["goal_intent_hash"],
        expected_project_binding=scope["project_binding"],
        expected_workspace_sha256=scope["workspace_sha256"],
        expected_subscription_authorization_id=scope["subscription_authorization_id"],
        expected_connection_generation=scope["connection_generation"],
        principal_id="local_bridge_operator",
        actor_assurance="bridge_bearer",
        idempotency_key="correction-pipeline-standing-grant",
    )
    assert grant["autonomous_correction_grant"]["enabled"] is True
    session = await store.get_session(session.id)
    bound.adapter.session = session
    bound.adapter.sessions[session.id] = session
    bound.adapter._normalizer.sessions[session.id] = session
    assert session.capabilities.get("send_message") is not True
    assert session.capabilities.get("resume") is not True
    sequence = []
    prepared_payloads = []
    original_prepare = store.prepare_main_effect_payload

    async def prepare_spy(**kwargs):
        sequence.append("prepare")
        payload = await original_prepare(**kwargs)
        prepared_payloads.append(payload)
        return payload

    monkeypatch.setattr(store, "prepare_main_effect_payload", prepare_spy)
    original_commit = store.commit_event_plan

    async def commit_spy(**kwargs):
        if kwargs.get("main_effect") is not None:
            sequence.append("commit")
            assert prepared_payloads
            assert kwargs["main_effect"]["payload"] == prepared_payloads[-1]
        return await original_commit(**kwargs)

    monkeypatch.setattr(store, "commit_event_plan", commit_spy)

    current_event: list[HarnessEvent] = []

    async def fake_private_dispatch(**kwargs):
        kwargs["final_authority_check"]()
        sequence.append("adapter")
        assert current_event
        event = current_event[0]
        assert kwargs["accepted_baseline"] == bound.adapter._input_baselines[event.event_id]
        correction = decoded_correction = json.loads(kwargs["correction_json"])
        assert canonical(correction) == kwargs["correction_json"]
        assert correction["content"][0]["text"] == EXACT_TEXT
        records = [json.loads(record) for record in kwargs["attribution_records"]]
        assert any(record["correction"] == correction for record in records)
        effect = await store.get_event_effect(event.event_id, "main")
        assert effect is not None and effect["state"] == "dispatching"
        assert effect["payload"] == prepared_payloads[-1]
        assert effect["payload"]["codex_correction"] == decoded_correction
        return AdapterMessageResult(True, session.vendor_session_id, "fixture-correction-turn")

    private_dispatch = AsyncMock(side_effect=fake_private_dispatch)
    monkeypatch.setattr(
        bound.adapter, "_dispatch_claimed_text", private_dispatch,
    )
    generic_send = AsyncMock(side_effect=AssertionError("generic send forbidden"))
    generic_continue = AsyncMock(side_effect=AssertionError("generic continue forbidden"))
    monkeypatch.setattr(bound.adapter, "send_message", generic_send)
    monkeypatch.setattr(bound.adapter, "continue_or_resume", generic_continue)
    pipeline.supervisor = CorrectionSupervisor()
    execute = AsyncMock(wraps=pipeline.executor.execute)
    monkeypatch.setattr(pipeline.executor, "execute", execute)

    async def ingest_observed() -> HarnessEvent:
        bound.transport.notifications.append(_notification("turn/completed", {
            "threadId": session.vendor_session_id,
            "turn": {"id": "turn-1", "status": "completed"},
        }))
        records = (await bound.adapter.subscription.drain_live()).records
        assert len(records) == 1
        ((event, observed_session),) = bound.adapter._prepare_records(records)
        current_event[:] = [event]
        bound.adapter._ingesting = True
        bound.adapter._ingesting_observation = (event, observed_session)
        try:
            await pipeline.ingest_shared_codex_event(event, observed_session)
        finally:
            bound.adapter._ingesting = False
            bound.adapter._ingesting_observation = None
            bound.adapter._undelivered.pop(event.event_id, None)
            bound.adapter._input_baselines.pop(event.event_id, None)
        stored = await store.get_event(event.event_id)
        assert stored is not None
        return stored

    async def replay_observed(event: HarnessEvent) -> None:
        from pex_bridge.codex_input_baseline import CodexInputBaselineSnapshot

        baseline = CodexInputBaselineSnapshot(
            **event.metadata["pex_observer_snapshot"]["input_baseline"]
        )
        observed_session = bound.adapter.session.model_copy(deep=True)
        bound.adapter._input_baselines[event.event_id] = baseline
        bound.adapter._ingesting = True
        bound.adapter._ingesting_observation = (event, observed_session)
        try:
            await pipeline.ingest_shared_codex_event(event, observed_session)
        finally:
            bound.adapter._ingesting = False
            bound.adapter._ingesting_observation = None
            bound.adapter._input_baselines.pop(event.event_id, None)

    yield SimpleNamespace(
        bound=bound, pipeline=pipeline, store=store, session=session, event=None,
        ingest_observed=ingest_observed, replay_observed=replay_observed,
        current_event=current_event,
        private_dispatch=private_dispatch,
        generic_send=generic_send, generic_continue=generic_continue,
        execute=execute, sequence=sequence, prepared_payloads=prepared_payloads,
    )


@pytest.mark.parametrize("action_type", [
    InterventionType.SEND_NUDGE,
    InterventionType.INJECT_CONTEXT,
    InterventionType.CONTINUE_SESSION,
])
async def test_actual_pipeline_commits_exact_correction_before_executor(
    correction_pipeline, action_type,
):
    case = correction_pipeline
    case.pipeline.supervisor = CorrectionSupervisor(action_type=action_type)
    case.event = await case.ingest_observed()
    result = (await case.store.list_interventions(case.session.id))[-1]
    assert result is not None
    assert case.sequence == ["prepare", "commit", "adapter"]
    case.execute.assert_awaited_once()
    effect = await case.store.get_event_effect(case.event.event_id, "main")
    assert effect["state"] == "delivered"
    assert effect["payload"]["action"]["payload"]["text"] == EXACT_TEXT
    correction = effect["payload"]["codex_correction"]
    assert correction["schema"] == CORRECTION_SCHEMA
    assert correction["effect_id"] == stable_event_effect_id(case.event.event_id, "main")
    assert correction["event_id"] == case.event.event_id
    assert correction["intervention_id"] == result.id
    assert correction["content"] == [{
        "type": "text", "text": EXACT_TEXT, "text_elements": [],
    }]
    assert correction["workspace_binding"] == case.session.metadata["workspace_binding"]
    assert correction["subscription_receipt"] == case.session.metadata["subscription_receipt"]
    assert correction["client_message_id"] == "pex-correction-" + hashlib.sha256(
        canonical([CORRECTION_SCHEMA, correction["effect_id"]]).encode()
    ).hexdigest()
    assert effect["request_hash"] == hashlib.sha256(
        canonical(effect["payload"]).encode()
    ).hexdigest()
    assert effect["result"]["worker_delivery_receipt"] == {
        "schema": "pex.worker-delivery.codex-turn.v1",
        "target_session_id": case.session.id,
        "vendor_session_id": case.session.vendor_session_id,
        "vendor_turn_id": "fixture-correction-turn",
    }
    attributions = await case.store.list_codex_correction_attributions(case.session)
    assert len(attributions) == 1
    assert json.loads(attributions[0])["correction"] == correction
    # Terminal replay must not prepare new correlation or run the fake worker again.
    await case.replay_observed(case.event)
    assert case.sequence == ["prepare", "commit", "adapter"]
    assert case.pipeline.supervisor.calls == 1
    assert await case.store.get_event_effect(case.event.event_id, "main") == effect


@pytest.mark.parametrize("failure", ["prepare", "insert"])
async def test_persistence_failure_prevents_executor_and_rolls_back_main_effect(
    correction_pipeline, monkeypatch, failure,
):
    case = correction_pipeline
    if failure == "prepare":
        original = case.store.prepare_main_effect_payload

        async def failed_prepare(**kwargs):
            await original(**kwargs)
            raise OSError("fixture correction persistence unavailable")

        monkeypatch.setattr(case.store, "prepare_main_effect_payload", failed_prepare)
        expected = OSError
    else:
        await case.store.db.execute(
            "CREATE TRIGGER correction_pipeline_insert_fault BEFORE INSERT ON event_effects "
            "WHEN NEW.effect_key='main' "
            "BEGIN SELECT RAISE(ABORT, 'fixture correction insert failure'); END",
        )
        await case.store.db.commit()
        expected = sqlite3.IntegrityError
    with pytest.raises(expected, match="fixture correction"):
        case.event = await case.ingest_observed()
    case.event = case.current_event[0]
    assert "prepare" in case.sequence
    assert ("commit" in case.sequence) is (failure == "insert")
    case.execute.assert_not_awaited()
    case.generic_send.assert_not_awaited()
    case.generic_continue.assert_not_awaited()
    assert await case.store.get_event_effect(case.event.event_id, "main") is None
    assert await case.store.list_interventions(case.session.id) == []
    assert await case.store.list_codex_correction_attributions(case.session) == ()
    # The fake supervisor really ran before this storage fault. Preserve its
    # durable result; never misreport it as an unattempted planner invocation.
    planner = await case.store.get_event_effect(case.event.event_id, "planner")
    assert planner["state"] == "delivered"
    assert case.pipeline.supervisor.calls == 1


@pytest.mark.parametrize("key", ["clientUserMessageId", "client_message_id", "codex_correction"])
async def test_model_supplied_correlation_cannot_enter_committed_main_effect(
    correction_pipeline, key,
):
    case = correction_pipeline
    case.pipeline.supervisor = CorrectionSupervisor(extra={key: "forged-correlation"})
    with pytest.raises(ValueError, match="correction action binding"):
        case.event = await case.ingest_observed()
    case.event = case.current_event[0]
    assert case.sequence == ["prepare"]
    case.execute.assert_not_awaited()
    case.generic_send.assert_not_awaited()
    assert await case.store.get_event_effect(case.event.event_id, "main") is None
    assert await case.store.list_interventions(case.session.id) == []
    assert await case.store.list_codex_correction_attributions(case.session) == ()


async def test_existing_legacy_pipeline_payload_and_delivery_stay_unchanged(tmp_path, monkeypatch):
    store, _, session, pipeline = await _pipeline(tmp_path)
    pipeline.supervisor = CorrectionSupervisor()
    prepare = AsyncMock(wraps=store.prepare_main_effect_payload)
    monkeypatch.setattr(store, "prepare_main_effect_payload", prepare)
    try:
        event = _event(session, "legacy-correction-pipeline")
        result = await pipeline.ingest_event(event, session)
        assert result is not None and result.result == "sent"
        prepare.assert_awaited_once()
        effect = await store.get_event_effect(event.event_id, "main")
        assert effect["state"] == "delivered"
        assert set(effect["payload"]) == {
            "schema", "event_id", "intervention_id", "action", "required_capability",
        }
        assert effect["payload"]["schema"] == "pex.worker-effect.v1"
        assert effect["payload"]["action"]["payload"]["text"] == EXACT_TEXT
        assert "codex_correction" not in effect["payload"]
    finally:
        await pipeline.close_presentations()
        await store.close()
