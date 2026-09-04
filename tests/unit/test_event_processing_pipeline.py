from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import ProjectIdentityBlockedError, Store
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, EventPhase, EventType
from pex_protocol.goal import Goal
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorResult


class _NudgeSupervisor:
    agentcore = None

    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, request, *, local_model):
        del local_model
        self.calls += 1
        return SupervisorResult(
            action=ProposedAction(
                type=InterventionType.SEND_NUDGE,
                session_id=request.session.id,
                goal_id=request.session.goal_id,
                payload={"text": "Continue with the exact acceptance criteria."},
                rationale="The accepted event still has unfinished work.",
                evidence=[request.event.event_id],
                confidence=0.9,
                risk=RiskLevel.LOW,
                authority_required=Authority.LOCAL_POLICY,
                requires_capability="send_message",
            ),
            used_llm=True,
            diagnosis="unfinished_work",
            inference_status="completed",
            execution_mode="local_model",
            model_call_count=1,
        )


class _RemoteNoop:
    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, request):
        self.calls += 1
        return SupervisorResult(
            action=ProposedAction(
                type=InterventionType.NOOP,
                session_id=request.session.id,
                goal_id=request.session.goal_id,
                rationale="Remote runtime saw no issue.",
                evidence=[request.event.event_id],
                confidence=0.7,
                risk=RiskLevel.NONE,
                authority_required=Authority.LOCAL_POLICY,
            ),
            used_llm=True,
            diagnosis="remote_noop",
            inference_status="completed",
            execution_mode="agentcore",
            transport_status="completed",
            model_call_count=1,
        )


class _AgentCoreOnlyRouter:
    def __init__(self, agentcore: _RemoteNoop) -> None:
        self.agentcore = agentcore


class _SimulatedCrash(BaseException):
    pass


class _CrashExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, action, verdict):
        del action, verdict
        self.calls += 1
        raise _SimulatedCrash("process disappeared after dispatch marker")


class _BlockingExecutor:
    def __init__(self) -> None:
        self.calls = 0
        self.started = asyncio.Event()

    async def execute(self, action, verdict):
        del action, verdict
        self.calls += 1
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


_IDENTITY_ORIGIN = ProjectOrigin(namespace="machine", host="pipeline-test-host")


def _event(
    session: HarnessSession,
    event_id: str,
    *,
    event_type: EventType = EventType.AGENT_RESPONSE,
    message: str = "Work is still in progress.",
) -> HarnessEvent:
    return HarnessEvent(
        event_id=event_id,
        ts=datetime.now(UTC),
        harness_type=session.harness_type,
        session_id=session.id,
        event_type=event_type,
        phase=EventPhase.AFTER,
        message_delta=message,
    )


async def _pipeline(
    tmp_path,
    *,
    path=None,
    boot_id: str | None = None,
    bus: EventBus | None = None,
) -> tuple[Store, AdapterRegistry, HarnessSession, Pipeline]:
    store = Store(path or (tmp_path / "pex.sqlite"), process_boot_id=boot_id)
    await store.connect()
    adapters = AdapterRegistry()
    session = adapters.synthetic.seed_session(vendor_id="event-recovery")
    session.project_id = str(tmp_path)
    session.goal_id = "goal-event-recovery"
    if await store.get_goal(session.goal_id) is None:
        now = datetime.now(UTC)
        await store.upsert_goal(
            Goal(
                id=session.goal_id,
                project_id=str(tmp_path),
                title="Exercise durable event recovery",
                objective="Keep every operational event bound to one explicit goal.",
                created_at=now,
                updated_at=now,
            )
        )
    await store.upsert_session(session)
    pipeline = Pipeline(
        store,
        adapters,
        bus or EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    return store, adapters, session, pipeline


async def _drain_presentations(pipeline: Pipeline) -> None:
    if pipeline._presentation_tasks:
        await asyncio.gather(*tuple(pipeline._presentation_tasks), return_exceptions=True)


async def _followup_row(store: Store, event_id: str, kind: str) -> dict:
    cursor = await store.db.execute(
        "SELECT * FROM event_followups WHERE event_id = ? AND kind = ?",
        (event_id, kind),
    )
    row = await cursor.fetchone()
    assert row is not None
    return dict(row)


@pytest.mark.asyncio
async def test_later_event_drains_an_older_accepted_session_head(tmp_path):
    store, _, session, pipeline = await _pipeline(tmp_path)
    first = _event(session, "accepted-first", event_type=EventType.HEARTBEAT)
    second = _event(session, "accepted-second", event_type=EventType.HEARTBEAT)
    try:
        await store.accept_pipeline_event(first, session_snapshot=session)
        await store.accept_pipeline_event(second, session_snapshot=session)

        assert await pipeline._drain_event_processing(second.event_id) is None
        first_state = await store.get_event_processing(first.event_id)
        second_state = await store.get_event_processing(second.event_id)
        assert first_state is not None and first_state["state"] == "complete"
        assert second_state is not None and second_state["state"] == "complete"
        assert first_state["accept_seq"] < second_state["accept_seq"]
    finally:
        await _drain_presentations(pipeline)
        await store.close()


@pytest.mark.asyncio
async def test_presentation_listener_cannot_delay_or_invalidate_event_receipt(tmp_path):
    bus = EventBus()
    listener_started = asyncio.Event()
    never = asyncio.Event()

    async def hanging_listener(_topic, _payload):
        listener_started.set()
        await never.wait()

    bus.subscribe(hanging_listener)
    store, _, session, pipeline = await _pipeline(tmp_path, bus=bus)
    event = _event(session, "presentation-independent", event_type=EventType.HEARTBEAT)
    try:
        result = await asyncio.wait_for(pipeline.ingest_event(event, session), timeout=1)
        assert result is None
        processing = await store.get_event_processing(event.event_id)
        assert processing is not None and processing["state"] == "complete"
        await asyncio.wait_for(listener_started.wait(), timeout=1)
        await asyncio.sleep(0.15)
        assert not pipeline._presentation_tasks
    finally:
        never.set()
        await _drain_presentations(pipeline)
        await store.close()


@pytest.mark.asyncio
async def test_duplicate_replays_exact_receipt_after_live_session_changes(tmp_path):
    store, _, session, pipeline = await _pipeline(tmp_path)
    supervisor = _NudgeSupervisor()
    pipeline.supervisor = supervisor
    event = _event(session, "duplicate-after-live-change")
    try:
        first = await pipeline.ingest_event(event, session)
        assert first is not None
        live = await store.get_session(session.id)
        assert live is not None
        live.supervision_paused = True
        live.metadata["human_decision_attention"] = {"pending": 1}
        await store.upsert_session(live)

        replay = await pipeline.ingest_event(event, session)
        assert replay == first
        assert supervisor.calls == 1
        assert len(await store.list_interventions(session.id)) == 1
    finally:
        await _drain_presentations(pipeline)
        await store.close()


@pytest.mark.asyncio
async def test_restart_after_main_dispatch_marker_seals_uncertain_without_resend(tmp_path):
    path = tmp_path / "crash.sqlite"
    first, adapters, session, pipeline = await _pipeline(
        tmp_path,
        path=path,
        boot_id="boot-before-crash",
    )
    supervisor = _NudgeSupervisor()
    crashing = _CrashExecutor()
    pipeline.supervisor = supervisor
    pipeline.executor = crashing
    event = _event(session, "main-dispatch-crash")
    try:
        with pytest.raises(_SimulatedCrash):
            await pipeline.ingest_event(event, session)
        effect = await first.get_event_effect(event.event_id, "main")
        assert effect is not None and effect["state"] == "dispatching"
        assert crashing.calls == 1
        assert adapters.synthetic.inbox[session.id] == []
    finally:
        await _drain_presentations(pipeline)
        await first.close()

    recovery = Store(path, process_boot_id="boot-after-crash")
    await recovery.connect()
    recovered_pipeline = Pipeline(
        recovery,
        adapters,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    recovered_pipeline.executor = _CrashExecutor()
    try:
        assert await recovered_pipeline.recover_unfinished_events() == [event.event_id]
        processing = await recovery.get_event_processing(event.event_id)
        assert processing is not None and processing["state"] == "complete"
        assert processing["receipt"]["effect_state"] == "delivery_uncertain"
        assert (
            processing["receipt"]["effect_result"]["code"]
            == "process_restarted_after_dispatch_started"
        )
        assert recovered_pipeline.executor.calls == 0
        assert adapters.synthetic.inbox[session.id] == []
        assert supervisor.calls == 1
    finally:
        await _drain_presentations(recovered_pipeline)
        await recovery.close()


@pytest.mark.asyncio
async def test_cancellation_after_main_marker_is_durably_uncertain_and_not_retried(tmp_path):
    store, adapters, session, pipeline = await _pipeline(tmp_path)
    supervisor = _NudgeSupervisor()
    blocking = _BlockingExecutor()
    pipeline.supervisor = supervisor
    pipeline.executor = blocking
    event = _event(session, "main-dispatch-cancel")
    task = asyncio.create_task(pipeline.ingest_event(event, session))
    try:
        await asyncio.wait_for(blocking.started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        processing = await store.get_event_processing(event.event_id)
        assert processing is not None and processing["state"] == "complete"
        assert processing["receipt"]["effect_state"] == "delivery_uncertain"
        replay = await pipeline.ingest_event(event, session)
        assert replay is not None
        assert replay.result == "worker_delivery_uncertain"
        assert blocking.calls == 1
        assert supervisor.calls == 1
        assert adapters.synthetic.inbox[session.id] == []
    finally:
        if not task.done():
            task.cancel()
        await _drain_presentations(pipeline)
        await store.close()


@pytest.mark.asyncio
async def test_restart_after_planner_result_reuses_first_evidence_generation(tmp_path):
    path = tmp_path / "planner-result-crash.sqlite"
    first, adapters, session, pipeline = await _pipeline(
        tmp_path,
        path=path,
        boot_id="boot-before-plan-commit",
    )
    now = datetime.now(UTC)
    goal = Goal(
        id="goal-planner-snapshot",
        project_id=str(tmp_path),
        title="Durable planning snapshot",
        objective="Create report.txt before stopping.",
        acceptance_criteria=["report.txt exists"],
        evidence_requirements=["report.txt"],
        created_at=now,
        updated_at=now,
    )
    await first.upsert_goal(goal)
    session.goal_id = goal.id
    session.cwd = str(tmp_path)
    await first.upsert_session(session, allow_goal_change=True)
    first_supervisor = _NudgeSupervisor()
    pipeline.supervisor = first_supervisor
    event = _event(
        session,
        "planner-result-crash",
        event_type=EventType.STOP,
        message="Everything is complete.",
    )
    real_commit = first.commit_event_plan
    commit_calls = 0

    async def crash_before_first_plan_commit(**kwargs):
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 1:
            raise _SimulatedCrash("planner result persisted but plan commit did not")
        return await real_commit(**kwargs)

    first.commit_event_plan = crash_before_first_plan_commit  # type: ignore[method-assign]
    try:
        with pytest.raises(_SimulatedCrash):
            await pipeline.ingest_event(event, session)
        planner_effect = await first.get_event_effect(event.event_id, "planner")
        assert planner_effect is not None and planner_effect["state"] == "delivered"
        first_snapshot = planner_effect["payload"]["planning_snapshot"]
        assert "report.txt" in first_snapshot["verification"]["missing_files"]
        processing = await first.get_event_processing(event.event_id)
        assert processing is not None and processing["state"] == "planning"
        assert first_supervisor.calls == 1
    finally:
        await first.close()

    # Mutable workspace truth changes after the semantic result. Recovery must
    # not pair that old result with a newly generated verification projection.
    (tmp_path / "report.txt").write_text("created after the crash", encoding="utf-8")
    recovery = Store(path, process_boot_id="boot-after-plan-commit-crash")
    await recovery.connect()
    recovered_pipeline = Pipeline(
        recovery,
        adapters,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    second_supervisor = _NudgeSupervisor()
    recovered_pipeline.supervisor = second_supervisor
    try:
        assert await recovered_pipeline.recover_unfinished_events() == [event.event_id]
        processing = await recovery.get_event_processing(event.event_id)
        assert processing is not None and processing["state"] == "complete"
        assert processing["plan"]["verification"] == first_snapshot["verification"]
        assert "report.txt" in processing["plan"]["verification"]["missing_files"]
        assert second_supervisor.calls == 0
        assert first_supervisor.calls == 1
    finally:
        await _drain_presentations(recovered_pipeline)
        await recovery.close()


@pytest.mark.asyncio
async def test_direct_agentcore_path_preserves_local_acceptance_gap(tmp_path, monkeypatch):
    store, _, session, pipeline = await _pipeline(tmp_path)
    now = datetime.now(UTC)
    goal = Goal(
        id="goal-agentcore-gap",
        project_id=str(tmp_path),
        title="Required report",
        objective="Create report.txt containing shipped.",
        acceptance_criteria=["report.txt contains shipped"],
        evidence_requirements=["report.txt"],
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    session.goal_id = goal.id
    session.cwd = str(tmp_path)
    await store.upsert_session(session, allow_goal_change=True)
    remote = _RemoteNoop()
    pipeline.settings.supervisor_mode = "agentcore"
    pipeline.supervisor = _AgentCoreOnlyRouter(remote)
    deterministic = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=session.id,
        goal_id=goal.id,
        payload={
            "text": "report.txt is still missing; create and verify it before stopping."
        },
        rationale="A required artifact is absent.",
        evidence=["missing:report.txt"],
        confidence=0.99,
        risk=RiskLevel.LOW,
        authority_required=Authority.LOCAL_POLICY,
        requires_capability="send_message",
    )
    monkeypatch.setattr(
        "pex_bridge.pipeline.plan_deterministic",
        lambda _request: deterministic.model_copy(deep=True),
    )
    event = _event(
        session,
        "agentcore-noop-gap",
        event_type=EventType.STOP,
        message="All work is complete and ready to ship.",
    )
    try:
        intervention = await pipeline.ingest_event(event, session)
        assert intervention is not None
        assert intervention.proposed_action.type == InterventionType.SEND_NUDGE
        assert "report.txt" in str(intervention.proposed_action.payload)
        assert remote.calls == 1
    finally:
        await _drain_presentations(pipeline)
        await store.close()


@pytest.mark.asyncio
async def test_quarantine_at_preparation_rejects_before_event_acceptance(
    tmp_path,
):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = adapters.synthetic.seed_session(
        vendor_id="project-quarantine-race",
        project_id=str(tmp_path),
    )
    now = datetime.now(UTC)
    goal = Goal(
        id="goal-project-quarantine-race",
        project_id=str(tmp_path),
        title="Identity race",
        objective="Keep later events live when a project conflict blocks planning.",
        acceptance_criteria=["work remains supervised"],
        created_at=now,
        updated_at=now,
    )
    first_identity = await store.register_project_locator(
        legacy_project_id=goal.project_id,
        locator=ProjectLocator.path(
            goal.project_id,
            platform=PathPlatform.WINDOWS if ":" in goal.project_id else PathPlatform.POSIX,
            origin=_IDENTITY_ORIGIN,
        ),
        now=now,
    )
    await store.upsert_goal(goal)
    session.goal_id = goal.id
    await store.upsert_session(session)
    pipeline = Pipeline(
        store,
        adapters,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    supervisor = _NudgeSupervisor()
    pipeline.supervisor = supervisor
    second_identity = await store.register_project_locator(
        legacy_project_id=goal.project_id,
        locator=ProjectLocator.path(
            str(tmp_path / "different-project"),
            platform=PathPlatform.WINDOWS if ":" in goal.project_id else PathPlatform.POSIX,
            origin=_IDENTITY_ORIGIN,
        ),
        now=now + timedelta(seconds=1),
    )
    assert second_identity["outcome"] == "quarantined"
    blocked_event = _event(
        session,
        "project-quarantine-race",
        event_type=EventType.STOP,
        message="Everything is complete.",
    )
    try:
        with pytest.raises(ProjectIdentityBlockedError) as blocked:
            await pipeline.ingest_event(blocked_event, session)
        assert blocked.value.code == "project_identity_quarantined"
        assert await store.get_event_processing(blocked_event.event_id) is None
        assert await store.get_event(blocked_event.event_id) is None
        assert supervisor.calls == 0
        assert adapters.synthetic.inbox.get(session.id, []) == []

        await store.resolve_project_identity_conflict(
            resolution_id="resolve-project-quarantine-race",
            legacy_project_id=goal.project_id,
            selected_identity_id=first_identity["identity"].id,
            resolved_by="local-operator",
            rationale="The original temporary workspace is the intended project.",
            resolved_at=now + timedelta(seconds=2),
        )
        resumed_event = _event(session, "project-quarantine-race-resumed")
        await pipeline.ingest_event(resumed_event, session)
        resumed = await store.get_event_processing(resumed_event.event_id)
        assert resumed is not None and resumed["state"] == "complete"
    finally:
        await _drain_presentations(pipeline)
        await store.close()


@pytest.mark.asyncio
async def test_quarantined_followup_completes_skipped_without_external_io(tmp_path):
    store, _, session, pipeline = await _pipeline(tmp_path)
    event = _event(session, "followup-quarantine", event_type=EventType.AGENT_RESPONSE)
    now = datetime.now(UTC)
    try:
        await pipeline.ingest_event(event, session)
        await store.db.execute(
            "UPDATE event_followups SET state = 'pending', result_json = NULL, "
            "lease_owner = NULL, lease_expires_at = NULL, completed_at = NULL "
            "WHERE event_id = ? AND kind = 'auto_handoff'",
            (event.event_id,),
        )
        await store.db.commit()
        await store.register_project_locator(
            legacy_project_id=str(session.project_id),
            locator=ProjectLocator.path(
                str(session.project_id),
                platform=(
                    PathPlatform.WINDOWS
                    if ":" in str(session.project_id)
                    else PathPlatform.POSIX
                ),
                origin=_IDENTITY_ORIGIN,
            ),
            now=now,
        )
        await store.register_project_locator(
            legacy_project_id=str(session.project_id),
            locator=ProjectLocator.path(
                str(tmp_path / "followup-conflict"),
                platform=(
                    PathPlatform.WINDOWS
                    if ":" in str(session.project_id)
                    else PathPlatform.POSIX
                ),
                origin=_IDENTITY_ORIGIN,
            ),
            now=now + timedelta(seconds=1),
        )
        claim = await store.claim_event_followup(
            event_id=event.event_id,
            kind="auto_handoff",
            owner=f"{store.process_boot_id}:quarantine-followup",
        )
        assert claim["outcome"] == "complete"
        assert claim["reason"] == "project_identity_quarantined"
        assert claim["followup"]["state"] == "complete"
        assert claim["followup"]["result"] == {
            "status": "skipped",
            "reason": "project_identity_quarantined",
        }
        assert await store.list_recoverable_event_followups() == []
    finally:
        await _drain_presentations(pipeline)
        await store.close()


@pytest.mark.asyncio
async def test_event_followup_claim_is_leased_and_terminal_result_is_immutable(tmp_path):
    store, _, session, pipeline = await _pipeline(tmp_path)
    event = _event(session, "followup-lease", event_type=EventType.AGENT_RESPONSE)
    try:
        await pipeline.ingest_event(event, session)
        await store.db.execute(
            "UPDATE event_followups SET state = 'pending', result_json = NULL, "
            "lease_owner = NULL, lease_expires_at = NULL, completed_at = NULL "
            "WHERE event_id = ? AND kind = 'auto_handoff'",
            (event.event_id,),
        )
        await store.db.commit()
        first = await store.claim_event_followup(
            event_id=event.event_id,
            kind="auto_handoff",
            owner=f"{store.process_boot_id}:followup-owner-one",
        )
        assert first["outcome"] == "claimed"
        busy = await store.claim_event_followup(
            event_id=event.event_id,
            kind="auto_handoff",
            owner=f"{store.process_boot_id}:followup-owner-two",
        )
        assert busy["outcome"] == "busy"
        with pytest.raises(PermissionError, match="claim is not owned"):
            await store.complete_event_followup(
                event_id=event.event_id,
                kind="auto_handoff",
                owner=f"{store.process_boot_id}:followup-owner-two",
                result={"status": "complete"},
            )
        completed = await store.complete_event_followup(
            event_id=event.event_id,
            kind="auto_handoff",
            owner=f"{store.process_boot_id}:followup-owner-one",
            result={"status": "complete"},
        )
        assert completed["state"] == "complete"
        with pytest.raises(ValueError, match="cannot change"):
            await store.complete_event_followup(
                event_id=event.event_id,
                kind="auto_handoff",
                owner=f"{store.process_boot_id}:followup-owner-one",
                result={"status": "different"},
            )
    finally:
        await _drain_presentations(pipeline)
        await store.close()


@pytest.mark.asyncio
async def test_startup_recovers_pending_event_followup_without_replanning(tmp_path, monkeypatch):
    path = tmp_path / "pex.sqlite"
    first_store, _, session, first_pipeline = await _pipeline(
        tmp_path,
        path=path,
        boot_id="followup-first-boot",
    )
    event = _event(session, "followup-startup", event_type=EventType.AGENT_RESPONSE)
    try:
        await first_pipeline.ingest_event(event, session)
        await first_store.db.execute(
            "UPDATE event_followups SET state = 'claimed', result_json = NULL, "
            "lease_owner = ?, lease_expires_at = ?, completed_at = NULL "
            "WHERE event_id = ? AND kind = 'auto_handoff'",
            (
                "followup-first-boot:dead-runner",
                (datetime.now(UTC) + timedelta(seconds=300)).isoformat(),
                event.event_id,
            ),
        )
        await first_store.db.commit()
    finally:
        await _drain_presentations(first_pipeline)
        await first_store.close()

    recovered_store, _, _, recovered_pipeline = await _pipeline(
        tmp_path,
        path=path,
        boot_id="followup-recovery-boot",
    )
    calls = 0

    async def recovered_handoff(*_args, **_kwargs):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(recovered_pipeline, "_maybe_auto_handoff", recovered_handoff)
    try:
        recovered = await recovered_pipeline.recover_unfinished_events()
        row = await _followup_row(recovered_store, event.event_id, "auto_handoff")
        assert event.event_id in recovered
        assert calls == 1
        assert row["state"] == "complete"
        processing = await recovered_store.get_event_processing(event.event_id)
        assert processing is not None and processing["state"] == "complete"
    finally:
        await _drain_presentations(recovered_pipeline)
        await recovered_store.close()


@pytest.mark.asyncio
async def test_recover_unfinished_events_skips_poison_rows_and_continues(
    tmp_path, monkeypatch
):
    store, _, _, pipeline = await _pipeline(tmp_path)
    try:

        async def poison_then_ok(event_id: str):
            if event_id == "poison":
                raise ValueError("intervention requires a persistent goal binding")

        async def list_rows():
            return [
                {"session_id": "s1", "event_id": "poison"},
                {"session_id": "s2", "event_id": "healthy"},
            ]

        async def no_followups():
            return []

        monkeypatch.setattr(
            pipeline.store, "list_recoverable_event_processing", list_rows
        )
        monkeypatch.setattr(
            pipeline.store, "list_recoverable_event_followups", no_followups
        )
        monkeypatch.setattr(pipeline, "_drain_event_processing", poison_then_ok)
        recovered = await pipeline.recover_unfinished_events()
        assert recovered == ["healthy"]
    finally:
        await _drain_presentations(pipeline)
        await store.close()
