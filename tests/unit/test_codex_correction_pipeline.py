"""Real Pipeline/Store planning with published workspace and explicit fake workers.

No provider, native worker, or actual shared mutation is enabled by these tests.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pex_bridge.adapters.base import AdapterMessageResult
from pex_bridge.codex_correction import CORRECTION_SCHEMA, canonical
from pex_bridge.store import stable_event_effect_id, utcnow
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.enums import Authority, EventPhase, EventType
from pex_protocol.session import HarnessEvent
from pex_protocol.supervisor import SupervisorResult
from test_event_processing_pipeline import _event, _pipeline
from test_workspace_continuity_pipeline import bound_pipeline as bound_pipeline

EXACT_TEXT = "  Inspect café/report.csv against criterion 2 and finish the missing rows.\n"


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
async def correction_pipeline(bound_pipeline, monkeypatch):
    bound = bound_pipeline
    pipeline, store = bound.pipeline, bound.store
    session = await store.get_session(bound.adapter.session.id)
    capabilities = AdapterCapabilities(send_message=True, resume=True)
    session.capabilities = capabilities.model_dump(mode="json")
    await store.upsert_session(session)
    session = await store.get_session(session.id)
    event = HarnessEvent(
        event_id="correction-pipeline-trigger",
        ts=utcnow(),
        session_id=session.id,
        harness_type=session.harness_type,
        project_id=session.project_id,
        goal_id=session.goal_id,
        event_type=EventType.AGENT_RESPONSE,
        phase=EventPhase.AFTER,
        message_delta="The worker fixture reports an incomplete public artifact.",
    )
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

    async def fake_send(target, text):
        sequence.append("adapter")
        assert text == EXACT_TEXT
        assert target.id == session.id
        effect = await store.get_event_effect(event.event_id, "main")
        assert effect is not None and effect["state"] == "dispatching"
        assert effect["payload"] == prepared_payloads[-1]
        assert effect["payload"]["codex_correction"]["content"][0]["text"] == text
        return AdapterMessageResult(True, session.vendor_session_id, "fixture-correction-turn")

    fake = SimpleNamespace(
        name="codex",
        probe=AsyncMock(return_value=capabilities),
        send_message=AsyncMock(side_effect=fake_send),
        continue_or_resume=AsyncMock(side_effect=fake_send),
    )
    pipeline.adapters.bind("codex", fake)
    pipeline.supervisor = CorrectionSupervisor()
    execute = AsyncMock(wraps=pipeline.executor.execute)
    monkeypatch.setattr(pipeline.executor, "execute", execute)
    try:
        yield SimpleNamespace(
            bound=bound, pipeline=pipeline, store=store, session=session, event=event,
            fake=fake, execute=execute, sequence=sequence, prepared_payloads=prepared_payloads,
        )
    finally:
        pipeline.adapters.bind("codex", bound.adapter)


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
    result = await case.pipeline.ingest_event(case.event, case.session)
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
    await case.pipeline.ingest_event(case.event, case.session)
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
        await case.pipeline.ingest_event(case.event, case.session)
    assert "prepare" in case.sequence
    assert ("commit" in case.sequence) is (failure == "insert")
    case.execute.assert_not_awaited()
    case.fake.send_message.assert_not_awaited()
    case.fake.continue_or_resume.assert_not_awaited()
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
        await case.pipeline.ingest_event(case.event, case.session)
    assert case.sequence == ["prepare"]
    case.execute.assert_not_awaited()
    case.fake.send_message.assert_not_awaited()
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
