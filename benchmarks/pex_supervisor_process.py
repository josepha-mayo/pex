"""Out-of-process PEX decision worker for public benchmark observations.

This process receives only the public task, normalized worker events, and a
workspace file inventory. It never imports the hidden evaluator or benchmark
controller.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pex_bridge.scoring import score_trajectory
from pex_bridge.store import new_id
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorRequest
from pex_supervisor.loop import decide
from pex_supervisor.providers import describe_backend, load_supervisor_model


def decide_public_observation(payload: dict) -> dict:
    now = datetime.now(UTC)
    task_md = str(payload["public_task"]).strip()
    session = HarnessSession.model_validate(payload["session"])
    session.status = SessionStatus.STOPPED
    goal = Goal(
        id=str(payload["goal_id"]),
        project_id=str(payload["project_id"]),
        title="Task",
        objective=task_md,
        created_at=now,
        updated_at=now,
    )
    session.goal_id = goal.id
    events = [
        HarnessEvent(
            event_id=new_id("evt_"),
            ts=now,
            harness_type=HarnessType.CODEX,
            session_id=session.id,
            event_type=EventType.AGENT_RESPONSE,
            phase=EventPhase.DURING,
            message_delta=str(text)[:4000],
        )
        for text in payload.get("agent_messages") or []
    ]
    stop = HarnessEvent(
        event_id=new_id("evt_"),
        ts=now,
        harness_type=HarnessType.CODEX,
        session_id=session.id,
        event_type=EventType.STOP,
        phase=EventPhase.TERMINAL,
        message_delta=str(payload.get("last_message") or "stopped")[:4000],
        process_state={"workspace_files": list(payload.get("workspace_files") or [])},
    )
    events.append(stop)
    request = SupervisorRequest(
        session=session,
        goal=goal,
        event=stop,
        recent_events=events,
        scores=score_trajectory(events, goal),
        notes="",
    )
    model = load_supervisor_model()
    result = decide(request, model=model)
    return {
        "backend": describe_backend(),
        "action": result.action.model_dump(mode="json"),
        "diagnosis": result.diagnosis,
        "used_llm": result.used_llm,
        "model_name": result.model_name,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "latency_ms": result.latency_ms,
        "inference_request_id": result.inference_request_id,
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: pex_supervisor_process.py REQUEST.json RESPONSE.json")
    request_path = Path(sys.argv[1])
    response_path = Path(sys.argv[2])
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    response = decide_public_observation(payload)
    response_path.write_text(json.dumps(response, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
