from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.agentcore import transport_invocation_id
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorResult


class _FailedRemoteSupervisor:
    async def decide(self, request, *, local_model):
        del local_model
        return SupervisorResult(
            action=ProposedAction(
                type=InterventionType.NOOP,
                session_id=request.session.id,
                goal_id=request.goal.id if request.goal else None,
                rationale="Remote semantic supervision failed closed.",
                evidence=["agentcore_unavailable"],
            ),
            diagnosis="agentcore_unavailable:transport failure",
            inference_status="failed",
            execution_mode="agentcore",
            transport="bedrock-agentcore",
            transport_invocation_id=transport_invocation_id(request),
            transport_status="failed",
        )


async def _bound_session(
    store: Store,
    tmp_path,
    *,
    vendor_session_id: str,
    now: datetime,
) -> HarnessSession:
    project_id = str(tmp_path.resolve())
    goal = Goal(
        id=f"goal-{vendor_session_id}",
        project_id=project_id,
        title="Preserve failed-closed supervision",
        objective="Keep a durable intervention receipt when semantic supervision fails.",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id=f"codex:{vendor_session_id}",
        harness_type=HarnessType.CODEX,
        vendor_session_id=vendor_session_id,
        project_id=project_id,
        goal_id=goal.id,
        cwd=project_id,
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    return session


@pytest.mark.asyncio
async def test_agentcore_failure_noop_keeps_durable_transport_receipt(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    session = await _bound_session(
        store,
        tmp_path,
        vendor_session_id="agentcore-failure",
        now=now,
    )
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    pipeline.supervisor = _FailedRemoteSupervisor()
    event = HarnessEvent(
        event_id="agentcore-failure-event",
        ts=now,
        harness_type=HarnessType.CODEX,
        session_id=session.id,
        project_id=session.project_id,
        goal_id=session.goal_id,
        event_type=EventType.AGENT_RESPONSE,
        message_delta="I think the task is complete.",
    )
    try:
        intervention = await pipeline.ingest_event(event, session)
        rows = await store.list_interventions(session.id)

        assert intervention is not None
        assert intervention.result == "noop"
        assert intervention.metadata["execution_mode"] == "agentcore"
        assert intervention.metadata["transport"] == "bedrock-agentcore"
        assert intervention.metadata["transport_status"] == "failed"
        assert intervention.metadata["transport_invocation_id"]
        assert len(rows) == 1
        assert rows[0].id == intervention.id
        audit = json.loads(store.audit_path.read_text(encoding="utf-8").splitlines()[0])
        assert audit["execution_mode"] == "agentcore"
        assert audit["transport"] == "bedrock-agentcore"
        assert audit["transport_status"] == "failed"
        assert audit["transport_invocation_id"]
    finally:
        await store.close()


class _CrashingSupervisor:
    async def decide(self, request, *, local_model):
        del request, local_model
        raise RuntimeError("supervisor exploded")


@pytest.mark.asyncio
async def test_unexpected_supervisor_failure_is_failed_closed_and_persisted(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    session = await _bound_session(
        store,
        tmp_path,
        vendor_session_id="supervisor-crash",
        now=now,
    )
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    pipeline.supervisor = _CrashingSupervisor()
    event = HarnessEvent(
        event_id="supervisor-crash-event",
        ts=now,
        harness_type=HarnessType.CODEX,
        session_id=session.id,
        project_id=session.project_id,
        goal_id=session.goal_id,
        event_type=EventType.AGENT_RESPONSE,
        message_delta="Still working.",
    )
    try:
        intervention = await pipeline.ingest_event(event, session)
        rows = await store.list_interventions(session.id)

        assert intervention is not None
        assert intervention.proposed_action.type == InterventionType.NOOP
        assert intervention.result == "noop"
        assert intervention.metadata["inference_status"] == "failed"
        assert intervention.metadata["execution_mode"] == "deterministic_reconciliation"
        planner_effect = await store.get_event_effect(event.event_id, "planner")
        assert planner_effect is not None
        assert planner_effect["state"] == "delivery_uncertain"
        assert planner_effect["result"] == {
            "status": "delivery_uncertain",
            "code": "planner_failed_after_dispatch_marker",
        }
        assert len(rows) == 1
        assert "supervisor exploded" not in intervention.model_dump_json()
        assert "supervisor exploded" not in store.audit_path.read_text(encoding="utf-8")
    finally:
        await store.close()
