import asyncio
from datetime import UTC, datetime

import pytest
from pex_bridge.adapters.http_json import MemoryHttpTransport
from pex_bridge.adapters.opencode import OpenCodeAdapter
from pex_bridge.adapters.opencode_outcomes import OPENCODE_MESSAGE_LINEAGE_KEY
from pex_bridge.context.health import assess_context_health
from pex_protocol.actions import InterventionType
from pex_protocol.enums import EventPhase, EventType, HarnessType
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessSession
from pex_protocol.supervisor import SupervisorRequest, TrajectoryScores
from pex_supervisor.planner import plan_deterministic


def _worker():
    adapter = OpenCodeAdapter(MemoryHttpTransport())
    session = HarnessSession(
        id="opencode:compact-worker", harness_type=HarnessType.OPENCODE,
        vendor_session_id="compact-worker", cwd="/project", project_id="/project",
        goal_id="persistent-goal",
    )
    adapter.sessions[session.id] = session
    return adapter, session


def _completed_message(session, message_id, **markers):
    return {
        "type": "message.updated",
        "properties": {
            "info": {
                "id": message_id, "sessionID": session.vendor_session_id,
                "role": "assistant", "parentID": "user-one", "finish": "stop",
                "time": {"created": 1, "completed": 2}, **markers,
            },
        },
    }


@pytest.mark.parametrize("markers", [
    {"summary": True}, {"mode": "compaction"}, {"agent": "compaction"},
    {"summary": "true"}, {"summary": {"unexpected": True}},
])
def test_compaction_summary_cannot_complete_a_worker_turn(markers):
    adapter, session = _worker()
    summary = adapter.normalize_sse(
        session, _completed_message(session, "summary-one", **markers),
    )
    assert summary.event_type == EventType.AGENT_RESPONSE
    assert summary.phase == EventPhase.AFTER
    assert summary.metadata[OPENCODE_MESSAGE_LINEAGE_KEY]["assistant_message_completed"] is False
    assert session.id not in adapter._completed_terminal_parents

    # A later ordinary terminal response for that same parent must still be reviewed.
    final = adapter.normalize_sse(session, _completed_message(session, "final-one"))
    assert final.event_type == EventType.STOP
    assert final.metadata[OPENCODE_MESSAGE_LINEAGE_KEY]["assistant_message_completed"] is True


def test_compacted_lifecycle_event_restores_the_durable_goal():
    adapter, session = _worker()
    compacted = adapter.normalize_sse(session, {
        "type": "session.compacted",
        "properties": {"sessionID": session.vendor_session_id},
    })
    assert compacted.event_type == EventType.COMPACTION
    assert compacted.phase == EventPhase.AFTER
    assert compacted.goal_id == session.goal_id
    health = assess_context_health([compacted], [], now=compacted.ts)
    assert health.signals["compaction_count"] == 1
    next_compaction = adapter.normalize_sse(session, {
        "type": "session.compacted",
        "properties": {"sessionID": session.vendor_session_id},
    })
    assert next_compaction.event_id != compacted.event_id
    assert assess_context_health(
        [compacted, next_compaction], [], now=next_compaction.ts,
    ).signals["compaction_count"] == 2
    now = datetime.now(UTC)
    goal = Goal(
        id=session.goal_id, project_id=session.project_id, title="Finish the parser",
        objective="Repair the parser and verify it.", acceptance_criteria=["parser tests pass"],
        constraints=["Preserve the public API"], forbidden_outcomes=["Do not spend paid credits"],
        evidence_requirements=["Record the test output"], created_at=now, updated_at=now,
    )
    action = plan_deterministic(SupervisorRequest(
        session=session, event=compacted, goal=goal,
        scores=TrajectoryScores(features=health.planner_features()),
    ))
    assert action.type == InterventionType.SEND_NUDGE
    for value in [goal.objective, *goal.acceptance_criteria, *goal.constraints,
                  *goal.forbidden_outcomes, *goal.evidence_requirements]:
        assert value in action.payload["text"]


@pytest.mark.asyncio
async def test_compaction_pump_keeps_retry_identity_and_distinguishes_next_occurrence():
    adapter, session = _worker()
    frame = {"type": "session.compacted", "properties": {"sessionID": session.vendor_session_id}}
    adapter.transport.events.extend([frame, frame])
    observed = []
    completed = asyncio.Event()

    async def ingest(event, _session):
        observed.append(event)
        if len(observed) == 1:
            raise RuntimeError("transient ingestion failure")
        if len(observed) == 3:
            completed.set()

    task = adapter.start_pipeline_pump(ingest)
    try:
        await asyncio.wait_for(completed.wait(), timeout=3)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert [event.event_type for event in observed] == [EventType.COMPACTION] * 3
    assert observed[0].model_dump() == observed[1].model_dump()
    assert observed[1].event_id != observed[2].event_id
