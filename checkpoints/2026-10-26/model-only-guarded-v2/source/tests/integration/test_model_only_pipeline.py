"""Real SQLite/pipeline/Strands + authored model + synthetic worker. NOT inference."""

import json
import socket

import pytest
from pex_bridge.agentcore import SupervisorRouter
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType
from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.context import ContextHandoffRequest
from pex_protocol.enums import EventType, PolicyVerdict
from pex_supervisor import model_only_transport

from tests.model_only_support import AuthoredSupervisorModel
from tests.unit.test_event_processing_pipeline import (
    _event,
    _followup_row,
    _pipeline,
    _SimulatedCrash,
)
from tests.unit.test_operator_handoff_effects import _artifacts

_PRODUCTION_ADMISSION = model_only_transport.qualified


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("network call")
        raise AssertionError("local pipeline test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(
        model_only_transport, "qualified", lambda model: type(model) is AuthoredSupervisorModel
    )
    yield
    assert attempts == [], "even caught network attempts invalidate this test"


async def setup(tmp_path, model=None, *, mode="supervisor_model_only"):
    store, adapters, session, pipeline = await _pipeline(tmp_path)
    pipeline.settings.supervisor_decision_mode = mode
    pipeline.supervisor = SupervisorRouter(pipeline.settings)
    pipeline.model = model
    session.cwd = str(tmp_path)
    await store.upsert_session(session)
    goal = await store.get_goal(session.goal_id)
    goal.acceptance_criteria = ["report.txt exists"]
    goal.evidence_requirements = ["report.txt"]
    await store.upsert_goal(goal)
    return store, adapters, session, pipeline


async def close(store, pipeline):
    await pipeline.close_presentations()
    await store.close()


@pytest.mark.asyncio
async def test_actual_pipeline_delivers_model_text_once_and_preserves_terminal_history(tmp_path):
    model = AuthoredSupervisorModel()
    store, adapters, session, pipeline = await setup(tmp_path, model)
    event = _event(session, "model-only-success", event_type=EventType.STOP, message="Done.")
    try:
        result = await pipeline.ingest_event(event, session)
        assert result.action_taken == "SEND_NUDGE", result.model_dump()
        assert result.result == "sent"
        assert model.calls == 4
        planner = await store.get_event_effect(event.event_id, "planner")
        assert planner["payload"]["request"]["supervisor_decision_mode"] == "supervisor_model_only"
        assert planner["result"]["supervisor_result"]["usage_validated"] is True
        assert len(adapters.synthetic.inbox[session.id]) == 1
        assert adapters.synthetic.inbox[session.id][0] == result.proposed_action.payload["text"]
        pipeline.settings.supervisor_decision_mode = "default"
        replay = await pipeline.ingest_event(event, session)
        assert replay.id == result.id
        assert replay.result == "sent"
        assert len(adapters.synthetic.inbox[session.id]) == 1
        assert model.calls == 4
    finally:
        await close(store, pipeline)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing", "invalid_main", "invalid_verifier", "exception"])
async def test_failed_model_never_sends_or_retries_same_durable_event(tmp_path, failure):
    model = (
        None
        if failure == "missing"
        else AuthoredSupervisorModel(failure=RuntimeError("authored transport failure"))
        if failure == "exception"
        else AuthoredSupervisorModel(
            bad_usage=True, bad_call=3 if failure == "invalid_verifier" else 1
        )
    )
    store, adapters, session, pipeline = await setup(tmp_path, model)
    event = _event(session, "model-only-failure", event_type=EventType.STOP, message="Done.")
    try:
        result = await pipeline.ingest_event(event, session)
        assert result.proposed_action.type == InterventionType.NOOP
        planner = await store.get_event_effect(event.event_id, "planner")
        assert planner["state"] == ("skipped" if failure == "missing" else "delivery_uncertain")
        counts = await store.supervisor_dispatch_counts([session.id])
        assert counts[session.id] == (0 if failure == "missing" else 1)
        assert await store.get_event_effect(event.event_id, "main") is None
        calls = model.calls if model else 0
        await pipeline.ingest_event(event, session)
        await pipeline.recover_unfinished_events()
        assert await store.supervisor_dispatch_counts([session.id]) == counts
        assert (model.calls if model else 0) == calls
        assert adapters.synthetic.inbox[session.id] == []
    finally:
        await close(store, pipeline)


@pytest.mark.asyncio
@pytest.mark.parametrize("gate", ["budget", "pause", "policy", "capability"])
async def test_existing_hard_vetoes_remain_authoritative(tmp_path, gate, monkeypatch):
    model = AuthoredSupervisorModel()
    store, adapters, session, pipeline = await setup(tmp_path, model)
    if gate == "budget":
        pipeline.settings.supervisor_max_dispatches_per_session = 0
    elif gate == "pause":
        pipeline.supervision_paused = True
    elif gate == "policy":
        monkeypatch.setattr(pipeline.policy, "decide", lambda *a, **k: PolicyVerdict.DENY)
    elif gate == "capability":

        async def no_capabilities():
            return AdapterCapabilities(send_message=False)

        monkeypatch.setattr(adapters.synthetic, "probe", no_capabilities)
    event = _event(session, "model-only-veto", event_type=EventType.STOP, message="Done.")
    try:
        await pipeline.ingest_event(event, session)
        assert adapters.synthetic.inbox[session.id] == []
        assert await store.get_event_effect(event.event_id, "main") is None
        assert model.calls == (0 if gate in {"budget", "pause"} else 4)
    finally:
        await close(store, pipeline)


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_mode", ["default", "supervisor_model_only"])
async def test_undispatched_plan_cannot_cross_decision_modes(tmp_path, initial_mode, monkeypatch):
    model = AuthoredSupervisorModel()
    store, adapters, session, pipeline = await setup(tmp_path, model, mode=initial_mode)
    event = _event(session, "model-only-mode-switch", event_type=EventType.STOP, message="Done.")
    original_resume = pipeline._resume_planned_event

    async def defer(*args, **kwargs):
        raise _SimulatedCrash("plan persisted, dispatch not started")

    monkeypatch.setattr(pipeline, "_resume_planned_event", defer)
    try:
        with pytest.raises(_SimulatedCrash):
            await pipeline.ingest_event(event, session)
        processing = await store.get_event_processing(event.event_id)
        assert processing["state"] == "planned"
        calls = model.calls
        pipeline.settings.supervisor_decision_mode = (
            "supervisor_model_only" if initial_mode == "default" else "default"
        )
        monkeypatch.setattr(pipeline, "_resume_planned_event", original_resume)
        await original_resume(processing, owner=processing["lease_owner"])
        main = await store.get_event_effect(event.event_id, "main")
        assert main["state"] == "skipped"
        assert main["result"]["code"] == "supervisor_decision_mode_changed"
        assert model.calls == calls
        assert adapters.synthetic.inbox[session.id] == []
    finally:
        await close(store, pipeline)


@pytest.mark.asyncio
async def test_restart_after_ambiguous_model_boundary_does_not_infer_or_send(tmp_path):
    model = AuthoredSupervisorModel(failure=_SimulatedCrash("authored process loss"))
    store, adapters, session, pipeline = await setup(tmp_path, model)
    event = _event(session, "model-only-restart", event_type=EventType.STOP, message="Done.")
    try:
        with pytest.raises(_SimulatedCrash):
            await pipeline.ingest_event(event, session)
        effect = await store.get_event_effect(event.event_id, "planner")
        assert effect["state"] == "dispatching"
        assert model.calls == 1
    finally:
        await close(store, pipeline)
    recovery = Store(tmp_path / "pex.sqlite", process_boot_id="model-only-restart")
    await recovery.connect()
    replacement = AuthoredSupervisorModel()
    resumed = Pipeline(
        recovery,
        adapters,
        EventBus(),
        Settings.for_test(
            require_auth=False, home=tmp_path, supervisor_decision_mode="supervisor_model_only"
        ),
        model=replacement,
    )
    try:
        await resumed.recover_unfinished_events()
        effect = await recovery.get_event_effect(event.event_id, "planner")
        assert effect["state"] == "delivery_uncertain"
        assert replacement.calls == 0
        assert await recovery.get_event_effect(event.event_id, "main") is None
        await resumed.ingest_event(event, session)
        assert replacement.calls == 0
        assert adapters.synthetic.inbox[session.id] == []
    finally:
        await close(recovery, resumed)


@pytest.mark.asyncio
async def test_model_only_compaction_does_not_send_deterministic_contract(tmp_path):
    model = AuthoredSupervisorModel()
    store, adapters, session, pipeline = await setup(tmp_path, model)
    event = _event(session, "model-only-compaction", event_type=EventType.COMPACTION)
    try:
        await pipeline.ingest_event(event, session)
        assert model.calls == 0
        assert adapters.synthetic.inbox[session.id] == []
    finally:
        await close(store, pipeline)


@pytest.mark.asyncio
async def test_route_change_during_authority_await_never_reaches_remote(tmp_path, monkeypatch):
    from tests.unit.test_supervisor_model_only import request

    store, adapters, session, pipeline = await setup(tmp_path, AuthoredSupervisorModel())
    calls = []

    class Remote:
        async def decide(self, value):
            calls.append(value)
            raise AssertionError("unqualified remote must not run")

    async def change_route(value):
        pipeline.settings.supervisor_mode = "agentcore"
        return None

    pipeline.supervisor.agentcore = Remote()
    monkeypatch.setattr(store, "require_session_workspace_current", change_route)
    try:
        result = await pipeline._invoke_supervisor(request(), semantic=True, witness=None)
        assert result.action.type == InterventionType.NOOP
        assert calls == []
        assert pipeline.model.calls == 0
    finally:
        await close(store, pipeline)


@pytest.mark.asyncio
async def test_mode_change_during_main_effect_claim_never_enters_worker(tmp_path, monkeypatch):
    model = AuthoredSupervisorModel()
    store, adapters, session, pipeline = await setup(tmp_path, model, mode="default")
    original = store.claim_main_event_effect

    async def change_mode(**kwargs):
        claim = await original(**kwargs)
        pipeline.settings.supervisor_decision_mode = "supervisor_model_only"
        return claim

    monkeypatch.setattr(store, "claim_main_event_effect", change_mode)
    event = _event(session, "model-only-claim-race", event_type=EventType.STOP, message="Done.")
    try:
        await pipeline.ingest_event(event, session)
        effect = await store.get_event_effect(event.event_id, "main")
        assert effect["state"] == "failed"
        assert effect["result"]["code"] == "supervisor_decision_mode_changed"
        assert adapters.synthetic.inbox[session.id] == []
    finally:
        await close(store, pipeline)


@pytest.mark.asyncio
async def test_production_transport_refusal_precedes_durable_dispatch(tmp_path, monkeypatch):
    model = AuthoredSupervisorModel()
    store, adapters, session, pipeline = await setup(tmp_path, model)
    monkeypatch.setattr(model_only_transport, "qualified", _PRODUCTION_ADMISSION)
    event = _event(session, "transport-unqualified", event_type=EventType.STOP, message="Done.")
    try:
        result = await pipeline.ingest_event(event, session)
        assert result.diagnosis == "model_only_transport_unqualified"
        effect = await store.get_event_effect(event.event_id, "planner")
        assert effect["state"] == "skipped"
        assert effect["result"]["provider_started"] is False
        assert (await store.supervisor_dispatch_counts([session.id]))[session.id] == 0
        assert model.calls == 0
        assert adapters.synthetic.inbox[session.id] == []
        await pipeline.ingest_event(event, session)
        assert model.calls == 0
    finally:
        await close(store, pipeline)


@pytest.mark.asyncio
async def test_pending_model_only_effect_cannot_outlive_test_transport_admission(
    tmp_path, monkeypatch
):
    model = AuthoredSupervisorModel()
    store, adapters, session, pipeline = await setup(tmp_path, model)
    event = _event(
        session, "transport-no-longer-qualified", event_type=EventType.STOP, message="Done."
    )
    original = pipeline._resume_planned_event

    async def defer(*args, **kwargs):
        raise _SimulatedCrash("effect persisted under test-only admission")

    monkeypatch.setattr(pipeline, "_resume_planned_event", defer)
    try:
        with pytest.raises(_SimulatedCrash):
            await pipeline.ingest_event(event, session)
        processing = await store.get_event_processing(event.event_id)
        assert processing["state"] == "planned"
        monkeypatch.setattr(model_only_transport, "qualified", _PRODUCTION_ADMISSION)
        await original(processing, owner=processing["lease_owner"])
        effect = await store.get_event_effect(event.event_id, "main")
        assert effect["state"] == "skipped"
        assert effect["result"]["code"] == "model_only_transport_unqualified"
        assert adapters.synthetic.inbox[session.id] == []
        assert model.calls == 4
    finally:
        await close(store, pipeline)


@pytest.mark.asyncio
@pytest.mark.parametrize("defer_until_default", [False, True])
async def test_automatic_handoff_is_not_model_feedback_even_on_history_replay(
    tmp_path, monkeypatch, defer_until_default
):
    store, adapters, session, pipeline = await setup(tmp_path)
    event = _event(session, "no-scripted-handoff", event_type=EventType.STOP, message="Done.")
    calls = []
    original_claim = store.claim_event_followup

    async def handoff(*args, **kwargs):
        calls.append("automatic handoff")

    async def defer_auto(*args, **kwargs):
        if kwargs["kind"] == "auto_handoff":
            return {"outcome": "busy"}
        return await original_claim(*args, **kwargs)

    monkeypatch.setattr(pipeline, "_maybe_auto_handoff", handoff)
    if defer_until_default:
        monkeypatch.setattr(store, "claim_event_followup", defer_auto)
    try:
        await pipeline.ingest_event(event, session)
        if defer_until_default:
            pipeline.settings.supervisor_decision_mode = "default"
            monkeypatch.setattr(store, "claim_event_followup", original_claim)
            await pipeline.ingest_event(event, session)
        receipt = await _followup_row(store, event.event_id, "auto_handoff")
        assert json.loads(receipt["result_json"]) == {
            "status": "skipped",
            "reason": "model_only_automatic_handoff_disabled",
        }
        assert calls == []
        assert adapters.synthetic.inbox[session.id] == []
    finally:
        await close(store, pipeline)


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["before_claim", "after_workspace_await", "manual"])
async def test_automatic_operator_effect_cannot_send_across_mode_switch(
    tmp_path, monkeypatch, boundary
):
    store, adapters, source, pipeline = await setup(tmp_path, mode="default")
    target = adapters.synthetic.seed_session(vendor_id="handoff-target")
    target.project_id, target.goal_id = source.project_id, source.goal_id
    target.cwd = source.cwd
    target.capabilities = (await adapters.synthetic.probe()).model_dump()
    await store.upsert_session(target)
    goal = await store.get_goal(source.goal_id)
    item, bundle, _, _ = _artifacts(goal, source, target)
    await store.add_context(item)
    manual = boundary == "manual"
    try:
        record = await pipeline._reserve_context_handoff_locked(
            source=source,
            target=target,
            goal=goal,
            bundle=bundle,
            principal_id="local_bridge_operator" if manual else "system_auto_handoff",
            request=ContextHandoffRequest(
                target_session_id=target.id,
                idempotency_key="mode-switch-handoff",
                token_budget=2000,
            ),
            human_requested=manual,
            actor_assurance="bridge_bearer" if manual else None,
            diagnosis="test local handoff boundary",
        )
        if boundary == "after_workspace_await":
            original = store.require_session_workspace_current

            async def switch(*args, **kwargs):
                value = await original(*args, **kwargs)
                pipeline.settings.supervisor_decision_mode = "supervisor_model_only"
                return value

            monkeypatch.setattr(store, "require_session_workspace_current", switch)
        else:
            pipeline.settings.supervisor_decision_mode = "supervisor_model_only"
        response = await pipeline._dispatch_operator_handoff(record, replayed=False)
        if manual:
            assert response["status"] == "delivered"
            assert len(adapters.synthetic.inbox[target.id]) == 1
        else:
            assert response["status"] == ("skipped" if boundary == "before_claim" else "failed")
            assert response["effect"]["result"]["reason"] == (
                "model_only_automatic_handoff_disabled"
            )
            assert adapters.synthetic.inbox[target.id] == []
    finally:
        await close(store, pipeline)
