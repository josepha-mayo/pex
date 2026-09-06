from datetime import UTC, datetime, timedelta

from pex_protocol.enums import EventPhase, EventType, HarnessType
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorRequest
from pex_supervisor.loop import needs_semantic_inference


def request_for_failures(count=3):
    now = datetime.now(UTC)
    events = [HarnessEvent(
        event_id=f"failure-{index}", ts=now + timedelta(seconds=index),
        session_id="s", project_id="p", goal_id="g", harness_type=HarnessType.SYNTHETIC,
        event_type=EventType.SHELL, phase=EventPhase.AFTER,
        command="pytest -q", error="ImportError: missing dependency",
        process_state={"exit_code": 1},
    ) for index in range(count)]
    return SupervisorRequest(
        session=HarnessSession(id="s", project_id="p", goal_id="g",
                               harness_type=HarnessType.SYNTHETIC, vendor_session_id="s"),
        goal=Goal(id="g", project_id="p", title="Test", objective="Repair failing tests",
                  created_at=now, updated_at=now),
        event=events[-1], recent_events=events, trajectory_review_enabled=True,
    )


def test_repeated_observed_failures_are_review_candidates_not_verdicts():
    from pex_supervisor.trajectory import trajectory_review_candidate

    request = request_for_failures()
    candidate = trajectory_review_candidate(request)
    assert candidate is not None
    assert candidate.event_ids == ("failure-0", "failure-1", "failure-2")
    assert needs_semantic_inference(request)


def test_routine_or_unbound_progress_does_not_trigger_review():
    for change in ("disabled", "no_goal", "paused_goal", "paused_session", "success",
                   "before", "unbound_event", "one_failure", "duplicate_ids"):
        request = request_for_failures(1 if change == "one_failure" else 3)
        if change == "disabled":
            request.trajectory_review_enabled = False
        elif change == "no_goal":
            request.goal = None
        elif change == "paused_goal":
            request.goal.paused = True
        elif change == "paused_session":
            request.session.supervision_paused = True
        elif change == "success":
            request.event.process_state = {"exit_code": 0}
        elif change == "before":
            request.event.phase = EventPhase.BEFORE
        elif change == "unbound_event":
            request.event.goal_id = None
        elif change == "duplicate_ids":
            request.recent_events[0].event_id = request.event.event_id
        assert not needs_semantic_inference(request), change


def test_repeat_candidate_key_survives_new_receipts_but_changes_with_goal():
    from pex_supervisor.trajectory import trajectory_review_candidate

    request = request_for_failures()
    original = trajectory_review_candidate(request)
    later = request.event.model_copy(update={"event_id": "failure-3",
                                           "ts": request.event.ts + timedelta(seconds=1)})
    request.recent_events.append(later)
    request.event = later
    assert trajectory_review_candidate(request).key == original.key
    request.session.metadata["workspace_binding"] = {"test_incarnation": "new"}
    assert trajectory_review_candidate(request).key != original.key
    request.session.metadata.clear()
    request.goal.objective = "A new goal"
    assert trajectory_review_candidate(request).key != original.key


def test_codex_exit_receipts_and_candidate_evidence_are_visible_to_reasoning():
    import json

    from pex_supervisor.evidence_tools import build_evidence_tools
    from pex_supervisor.loop import _format_user

    request = request_for_failures()
    for event in request.recent_events:
        event.process_state = None
        event.metadata["command_exit_code"] = 1
        event.error = None
    assert needs_semantic_inference(request)
    tool = next(tool for tool in build_evidence_tools(request, [])
                if tool.tool_name == "get_recent_events")
    observations = json.loads(tool())["result"]
    assert [item["command_exit_code"] for item in observations] == [1, 1, 1]
    assert [item["event_id"] for item in observations] == ["failure-0", "failure-1", "failure-2"]
    assert "NOT a drift verdict" in _format_user(request)
    request.event.process_state = {"exit_code": 0}
    assert not needs_semantic_inference(request)


def test_trajectory_correction_requires_independent_verifier_but_noop_does_not():
    from pex_bridge.agentcore import _remote_verifier_contract_failure
    from pex_protocol.actions import InterventionType
    from pex_protocol.supervisor import SupervisorResult
    from pex_supervisor.loop import _action_from_proposal, _needs_independent_verifier

    request = request_for_failures()
    action = _action_from_proposal(request, {"type": "NOOP", "rationale": "Wait", "evidence": []})
    semantic = SupervisorResult(action=action, inference_status="completed")
    assert not _needs_independent_verifier(request, action, semantic)
    semantic.action.type = InterventionType.SEND_NUDGE
    assert _needs_independent_verifier(request, action, semantic)
    semantic.used_llm = True
    semantic.model_call_count = 1
    semantic.evidence_refs = ["main-observation"]
    assert _remote_verifier_contract_failure(request, semantic) == "missing_receipt"


def test_progress_and_old_or_conflicting_receipts_do_not_manufacture_candidates():
    for change in ("edit", "old", "future", "conflicting", "bool_exit"):
        request = request_for_failures()
        if change == "edit":
            request.recent_events[1].event_type = EventType.FILE_EDIT
        elif change == "old":
            request.goal.updated_at = request.event.ts
        elif change == "future":
            request.recent_events[0].ts = request.event.ts + timedelta(seconds=1)
        elif change == "conflicting":
            request.event = request.event.model_copy(update={"command": "another command"})
        elif change == "bool_exit":
            request.event.process_state = {"exit_code": True}
        assert not needs_semantic_inference(request), change


def test_actual_cloud_redaction_keeps_material_eligibility_without_local_paths():
    from pex_bridge.agentcore import cloud_request
    from pex_supervisor.trajectory import trajectory_review_candidate

    request = request_for_failures()
    request.session.cwd = "C:/private/worker"
    for event in request.recent_events:
        event.process_state = None
        event.metadata["command_exit_code"] = 1
    remote = cloud_request(request)
    assert needs_semantic_inference(remote)
    assert trajectory_review_candidate(remote).event_ids == ("failure-0", "failure-1", "failure-2")
    assert remote.session.cwd is None
    assert "C:/private/worker" not in remote.model_dump_json()
    request.trajectory_review_enabled = False
    assert not needs_semantic_inference(cloud_request(request))
    assert "trajectory_review_enabled" not in request.model_dump(mode="json")
