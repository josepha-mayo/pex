from __future__ import annotations

from datetime import datetime, timezone

from pex_protocol.actions import InterventionType
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorRequest, TrajectoryScores
from pex_supervisor.planner import plan_deterministic


def _goal() -> Goal:
    now = datetime.now(timezone.utc)
    return Goal(
        id="goal_1",
        project_id="p1",
        title="Ship eval",
        objective="Finish the evaluation pipeline with passing tests",
        acceptance_criteria=["tests pass", "results.json exists"],
        evidence_requirements=["pytest output"],
        created_at=now,
        updated_at=now,
    )


def _session() -> HarnessSession:
    return HarnessSession(
        id="synthetic:s1",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="s1",
        project_id="p1",
        goal_id="goal_1",
        status=SessionStatus.STOPPED,
    )


def _event(event_type: EventType, **kwargs) -> HarnessEvent:
    return HarnessEvent(
        event_id="e1",
        ts=datetime.now(timezone.utc),
        harness_type=HarnessType.SYNTHETIC,
        session_id="synthetic:s1",
        event_type=event_type,
        phase=kwargs.pop("phase", EventPhase.TERMINAL),
        **kwargs,
    )


def test_stop_without_contradicting_evidence_is_noop():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.STOP, message_delta="All done"),
        scores=TrajectoryScores(premature_completion=0.9, features={"tests_run": 0, "stops": 1}),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.NOOP
    assert not str(action.payload.get("text") or "").startswith("PEX:")


def test_safe_pytest_permission_is_brokered():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(
            EventType.SHELL,
            phase=EventPhase.BEFORE,
            command="pytest -q",
            approval_request={"request_id": "perm-1"},
        ),
        scores=TrajectoryScores(),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.RESPOND_PERMISSION


def test_pre_tool_use_permission_is_brokered():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(
            EventType.TOOL_CALL,
            phase=EventPhase.BEFORE,
            command="rm -rf /tmp/pex",
            tool_name="Shell",
            approval_request={"request_id": "perm-2"},
        ),
        scores=TrajectoryScores(),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.RESPOND_PERMISSION


def test_eval_before_dataset_is_blocked():
    now = datetime.now(timezone.utc)
    goal = Goal(
        id="goal_ds",
        project_id="p1",
        title="Dataset then eval",
        objective="Generate the evaluation dataset then run eval_runner",
        acceptance_criteria=["dataset.parquet exists"],
        created_at=now,
        updated_at=now,
    )
    request = SupervisorRequest(
        session=_session(),
        goal=goal,
        event=_event(EventType.SHELL, phase=EventPhase.DURING, command="python eval_runner.py --full"),
        scores=TrajectoryScores(),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.SEND_NUDGE
    assert "dataset" in action.payload["text"].lower()


def test_contradictory_prompt_escalates():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.USER_PROMPT, message_delta="just skip tests"),
        scores=TrajectoryScores(),
        notes="possible_contradiction",
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.ASK_HUMAN
    assert action.requires_capability is None


def test_repeated_low_info_work_is_redirected():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.SHELL, phase=EventPhase.DURING, command="python train.py"),
        scores=TrajectoryScores(drift=0.82, features={"repeated_command_count": 5}),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.SEND_NUDGE
    assert "acceptance" in action.payload["text"].lower()
    assert not str(action.payload.get("text") or "").startswith("PEX:")
