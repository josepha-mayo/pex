from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.context import ContextBundle, ContextItem
from pex_protocol.enums import (
    Authority,
    ContextKind,
    EventType,
    HarnessType,
    Sensitivity,
    SessionStatus,
    SourceKind,
)
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorResult


class _ConcurrencyProbeSupervisor:
    def __init__(self, *, parties: int | None = None) -> None:
        self.active = 0
        self.max_active = 0
        self.calls = 0
        self._barrier = asyncio.Barrier(parties) if parties else None

    async def decide(self, request, *, local_model):
        del local_model
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self._barrier is not None:
                await asyncio.wait_for(self._barrier.wait(), timeout=5)
            else:
                await asyncio.sleep(0.05)
        finally:
            self.active -= 1
        return SupervisorResult(
            action=ProposedAction(
                type=InterventionType.NOOP,
                session_id=request.session.id,
                goal_id=request.session.goal_id,
                rationale="No evidence-grounded intervention is needed.",
                evidence=[request.event.event_id],
                confidence=0.9,
                risk=RiskLevel.NONE,
                authority_required=Authority.LOCAL_POLICY,
            ),
            used_llm=True,
            diagnosis="no_intervention_needed",
            inference_status="completed",
        )


class _CrossTargetSupervisor:
    def __init__(self, target_session_id: str) -> None:
        self.target_session_id = target_session_id

    async def decide(self, request, *, local_model):
        del local_model
        return SupervisorResult(
            action=ProposedAction(
                type=InterventionType.SEND_NUDGE,
                session_id=self.target_session_id,
                goal_id=request.session.goal_id,
                payload={"text": "This must never reach the other worker."},
                rationale="Act on a different session.",
                evidence=[request.event.event_id],
                confidence=0.99,
                risk=RiskLevel.LOW,
                requires_capability="send_message",
            ),
            used_llm=True,
            diagnosis="malformed_cross_target_result",
            inference_status="completed",
            model_call_count=1,
        )


def _stop(session: HarnessSession, event_id: str, offset: int = 0) -> HarnessEvent:
    return HarnessEvent(
        event_id=event_id,
        ts=datetime.now(UTC) + timedelta(milliseconds=offset),
        harness_type=session.harness_type,
        session_id=session.id,
        event_type=EventType.STOP,
        message_delta="I am stopping without a completion claim.",
    )


async def _persist_goal_bound_sessions(
    store: Store,
    *sessions: HarnessSession,
    project_id: str,
    goal_id: str,
) -> None:
    now = datetime.now(UTC)
    goal = Goal(
        id=goal_id,
        project_id=project_id,
        title="Exercise pipeline serialization",
        objective="Keep semantic decisions bound and ordered.",
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    for session in sessions:
        session.project_id = project_id
        session.cwd = project_id
        session.goal_id = goal.id
        await store.upsert_session(session)


@pytest.mark.asyncio
async def test_same_session_semantic_decisions_never_overlap(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = adapters.synthetic.seed_session(vendor_id="serialized")
    await _persist_goal_bound_sessions(
        store,
        session,
        project_id=str(tmp_path),
        goal_id="goal-serialized",
    )
    pipeline = Pipeline(
        store,
        adapters,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path),
    )
    probe = _ConcurrencyProbeSupervisor()
    pipeline.supervisor = probe
    try:
        await asyncio.gather(
            pipeline.ingest_event(_stop(session, "stop-1"), session),
            pipeline.ingest_event(_stop(session, "stop-2", 1), session),
        )
        assert probe.calls == 2
        assert probe.max_active == 1
        assert len(await store.list_interventions(session.id)) == 2
        saved = await store.get_session(session.id)
        assert saved is not None
        assert saved.status == SessionStatus.STOPPED
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_different_sessions_remain_parallel(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    first = adapters.synthetic.seed_session(vendor_id="parallel-one")
    second = adapters.synthetic.seed_session(vendor_id="parallel-two")
    await _persist_goal_bound_sessions(
        store,
        first,
        second,
        project_id=str(tmp_path),
        goal_id="goal-parallel",
    )
    pipeline = Pipeline(
        store,
        adapters,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path),
    )
    probe = _ConcurrencyProbeSupervisor(parties=2)
    pipeline.supervisor = probe
    try:
        await asyncio.gather(
            pipeline.ingest_event(_stop(first, "parallel-stop-1"), first),
            pipeline.ingest_event(_stop(second, "parallel-stop-2"), second),
        )
        assert probe.calls == 2
        assert probe.max_active == 2
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_pipeline_rejects_cross_session_event_binding(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = adapters.synthetic.seed_session(vendor_id="identity")
    pipeline = Pipeline(
        store,
        adapters,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path),
    )
    event = _stop(session, "wrong-binding").model_copy(
        update={"session_id": "synthetic:other"}
    )
    try:
        with pytest.raises(ValueError, match="identity mismatch"):
            await pipeline.ingest_event(event, session)
        assert await store.latest_events() == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_pipeline_rejects_cross_project_event_binding_before_persistence(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = adapters.synthetic.seed_session(vendor_id="project-identity")
    session.project_id = "project-a"
    pipeline = Pipeline(
        store,
        adapters,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path),
    )
    event = _stop(session, "wrong-project-binding").model_copy(
        update={"project_id": "project-b"}
    )
    try:
        with pytest.raises(ValueError, match="project identity mismatch"):
            await pipeline.ingest_event(event, session)
        assert await store.latest_events() == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_pipeline_rejects_conflicting_stored_vendor_before_event_persistence(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    stored = adapters.synthetic.seed_session(vendor_id="durable-vendor")
    await store.upsert_session(stored)
    incoming = stored.model_copy(update={"vendor_session_id": "spoofed-vendor"})
    pipeline = Pipeline(
        store,
        adapters,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path),
    )
    try:
        with pytest.raises(ValueError, match="vendor identity mismatch"):
            await pipeline.ingest_event(_stop(incoming, "spoofed-vendor-event"), incoming)
        assert await store.latest_events() == []
        assert await store.get_session(stored.id) == stored
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_supervisor_cannot_redirect_action_before_adapter_io(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    source = adapters.synthetic.seed_session(vendor_id="bound-source")
    target = adapters.synthetic.seed_session(vendor_id="unrelated-target")
    await _persist_goal_bound_sessions(
        store,
        source,
        target,
        project_id=str(tmp_path),
        goal_id="goal-cross-target",
    )
    pipeline = Pipeline(
        store,
        adapters,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    pipeline.supervisor = _CrossTargetSupervisor(target.id)
    try:
        intervention = await pipeline.ingest_event(
            _stop(source, "cross-target-result"), source
        )
        assert intervention is not None
        assert intervention.session_id == source.id
        assert intervention.proposed_action.session_id == source.id
        assert intervention.action_taken == InterventionType.NOOP.value
        assert intervention.result == "noop"
        assert intervention.diagnosis == "supervisor_action_identity_mismatch"
        assert intervention.metadata["inference_status"] == "failed"
        assert adapters.synthetic.inbox[source.id] == []
        assert adapters.synthetic.inbox[target.id] == []
        rows = await store.list_interventions(source.id)
        assert len(rows) == 1
        assert await store.list_interventions(target.id) == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_unattached_session_does_not_persist_intervention(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = adapters.synthetic.seed_session(vendor_id="unattached-opencode")
    session.project_id = str(tmp_path)
    session.cwd = str(tmp_path)
    session.goal_id = None
    await store.upsert_session(session)
    pipeline = Pipeline(
        store,
        adapters,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    pipeline.supervisor = _CrossTargetSupervisor(session.id)
    try:
        intervention = await pipeline.ingest_event(
            _stop(session, "unattached-stop"), session
        )
        assert intervention is None
        assert await store.list_interventions(session.id) == []
        processing = await store.get_event_processing("unattached-stop")
        assert processing is not None
        assert processing["state"] == "complete"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_context_handoff_rejects_cross_project_target_before_adapter_io(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    source = adapters.synthetic.seed_session(vendor_id="handoff-source")
    target = adapters.synthetic.seed_session(vendor_id="handoff-target")
    source.project_id = "C:/project-a"
    target.project_id = "C:/project-b"
    source.goal_id = target.goal_id = "goal-handoff"
    pipeline = Pipeline(
        store,
        adapters,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    now = datetime.now(UTC)
    item = ContextItem(
        id="ctx-cross-project",
        project_id=source.project_id,
        goal_id=source.goal_id,
        kind=ContextKind.FACT,
        content="A relevant parser artifact exists.",
        source_refs=["event-cross-project"],
        provenance=SourceKind.HARNESS,
        confidence=0.8,
        valid_from=now,
        sensitivity=Sensitivity.INTERNAL,
    )
    bundle = ContextBundle(
        goal_id=source.goal_id,
        target_session_id=target.id,
        source_session_ids=[source.id],
        goal_summary="Share the parser artifact.",
        items=[item],
        created_at=now,
    )
    event = HarnessEvent(
        event_id="event-cross-project",
        ts=now,
        harness_type=source.harness_type,
        session_id=source.id,
        project_id=source.project_id,
        event_type=EventType.AGENT_RESPONSE,
        message_delta=item.content,
    )
    try:
        with pytest.raises(ValueError, match="handoff_project_mismatch"):
            await pipeline.deliver_context_handoff(source, target, bundle, event)
        assert adapters.synthetic.inbox[target.id] == []
        assert await store.list_interventions(target.id) == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_handoff_rejects_item_from_an_unlisted_source_session(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    source = adapters.synthetic.seed_session(vendor_id="handoff-source-bound")
    target = adapters.synthetic.seed_session(vendor_id="handoff-target-bound")
    source.project_id = target.project_id = "C:/project-a"
    source.goal_id = target.goal_id = "goal-handoff"
    pipeline = Pipeline(
        store,
        adapters,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    now = datetime.now(UTC)
    item = ContextItem(
        id="ctx-wrong-source",
        project_id=source.project_id,
        goal_id=source.goal_id,
        kind=ContextKind.FACT,
        content="A parser artifact was observed in another worker.",
        source_refs=["event-other-worker"],
        provenance=SourceKind.HARNESS,
        confidence=0.8,
        valid_from=now,
        sensitivity=Sensitivity.INTERNAL,
        metadata={"source_session_id": "synthetic:other-worker"},
    )
    bundle = ContextBundle(
        goal_id=source.goal_id,
        target_session_id=target.id,
        source_session_ids=[source.id],
        goal_summary="Share the parser artifact.",
        items=[item],
        created_at=now,
    )
    event = HarnessEvent(
        event_id="event-source-worker",
        ts=now,
        harness_type=source.harness_type,
        session_id=source.id,
        project_id=source.project_id,
        event_type=EventType.AGENT_RESPONSE,
        message_delta="The source worker has new context.",
    )
    try:
        with pytest.raises(ValueError, match="handoff_item_source_session_mismatch"):
            await pipeline.deliver_context_handoff(source, target, bundle, event)
        assert adapters.synthetic.inbox[target.id] == []
        assert await store.list_interventions(target.id) == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_store_rejects_conflicting_event_id_replay(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    session = HarnessSession(
        id="synthetic:event-collision",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="event-collision",
        project_id="project-a",
    )
    first = _stop(session, "same-id")
    first.project_id = session.project_id
    conflicting = first.model_copy(update={"message_delta": "different content"})
    try:
        await store.upsert_session(session)
        assert await store.add_event(first) is True
        assert await store.add_event(first.model_copy(deep=True)) is False
        later = first.model_copy(update={"ts": first.ts.replace(year=first.ts.year + 1)})
        assert await store.add_event(later) is False
        with pytest.raises(ValueError, match="event id collision"):
            await store.add_event(conflicting)
        assert await store.latest_events() == [first]
    finally:
        await store.close()
