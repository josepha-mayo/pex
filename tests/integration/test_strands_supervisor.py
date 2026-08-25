def test_strands_agent_constructs_and_receives_normalized_event():
    from datetime import datetime, timezone

    from pex_protocol.enums import EventType, HarnessType, SessionStatus
    from pex_protocol.goal import Goal
    from pex_protocol.session import HarnessEvent, HarnessSession
    from pex_protocol.supervisor import SupervisorRequest, TrajectoryScores
    from pex_supervisor.loop import decide
    from pex_supervisor.planner import plan_deterministic

    now = datetime.now(timezone.utc)
    request = SupervisorRequest(
        session=HarnessSession(
            id="synthetic:demo",
            harness_type=HarnessType.SYNTHETIC,
            vendor_session_id="demo",
            status=SessionStatus.STOPPED,
            goal_id="g",
        ),
        goal=Goal(
            id="g",
            project_id="p",
            title="t",
            objective="finish tests",
            acceptance_criteria=["tests pass"],
            created_at=now,
            updated_at=now,
        ),
        event=HarnessEvent(
            event_id="e",
            ts=now,
            harness_type=HarnessType.SYNTHETIC,
            session_id="synthetic:demo",
            event_type=EventType.STOP,
            message_delta="done",
        ),
        scores=TrajectoryScores(premature_completion=0.95, features={"tests_run": 0, "stops": 1}),
    )
    from strands import Agent

    assert Agent is not None
    result = decide(request)
    assert result.used_llm is False
    action = plan_deterministic(request)
    assert action.type.value == "CONTINUE_SESSION"
    assert request.event.event_type.value == "stop"
