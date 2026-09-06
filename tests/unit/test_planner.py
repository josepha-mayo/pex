from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pex_protocol.actions import InterventionType
from pex_protocol.enums import Authority, EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorRequest, TrajectoryScores
from pex_supervisor.loop import _action_from_proposal
from pex_supervisor.planner import plan_deterministic


def _goal() -> Goal:
    now = datetime.now(UTC)
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
        event_id=kwargs.pop("event_id", "e1"),
        ts=kwargs.pop("ts", datetime.now(UTC)),
        harness_type=kwargs.pop("harness_type", HarnessType.SYNTHETIC),
        session_id=kwargs.pop("session_id", "synthetic:s1"),
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


def test_eval_command_does_not_invent_missing_dataset_evidence():
    now = datetime.now(UTC)
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
        session=_session().model_copy(update={"goal_id": goal.id}),
        goal=goal,
        event=_event(
            EventType.SHELL, phase=EventPhase.DURING, command="python eval_runner.py --full"
        ),
        scores=TrajectoryScores(),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.NOOP


def test_eval_command_redirects_when_required_artifact_is_observed_missing():
    now = datetime.now(UTC)
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
        session=_session().model_copy(update={"goal_id": goal.id}),
        goal=goal,
        event=_event(
            EventType.SHELL,
            phase=EventPhase.DURING,
            command="python eval_runner.py --full",
        ),
        scores=TrajectoryScores(features={"missing_prerequisites": ["dataset.parquet"]}),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.SEND_NUDGE
    assert "dataset.parquet" in action.payload["text"]
    assert not str(action.payload.get("text") or "").startswith("PEX:")


def test_dataset_generator_is_not_treated_as_downstream_eval():
    now = datetime.now(UTC)
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
        session=_session().model_copy(update={"goal_id": goal.id}),
        goal=goal,
        event=_event(
            EventType.SHELL,
            phase=EventPhase.DURING,
            command="python generate_dataset.py",
        ),
        scores=TrajectoryScores(features={"missing_prerequisites": ["dataset.parquet"]}),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.NOOP


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


@pytest.mark.parametrize("policy_note", [
    "", "\n\nStanding operator permission enables the private claimed-correction route.",
])
def test_contradictory_prompt_names_the_active_constraint(policy_note):
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.USER_PROMPT, message_delta="just skip tests"),
        scores=TrajectoryScores(),
        notes="possible_contradiction:Do not skip the public tests." + policy_note,
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.ASK_HUMAN
    question = str(action.payload.get("question") or "")
    assert "Do not skip the public tests." in question
    assert "explicit override" in question.lower()
    assert "Standing operator" not in question


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


def test_repeated_identical_failures_apply_debug_overlay():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.SHELL, phase=EventPhase.DURING, command="pytest -q"),
        scores=TrajectoryScores(
            drift=0.82,
            features={"repeated_command_count": 5, "identical_error_count": 3},
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.APPLY_OVERLAY
    overlay = action.payload["overlay"]
    assert overlay["diff"]["extra"]["phase"] == "debug"
    assert "WebSearch" in overlay["diff"]["tools_disabled"]


def test_contradicted_stop_sends_specific_evidence():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.STOP, message_delta="All tests passed"),
        scores=TrajectoryScores(
            claim_contradiction=0.88,
            features={
                "verification": {
                    "status": "acceptance_gap",
                    "correction": (
                        "You said the test suite passes. The latest observed pytest run failed "
                        "(exit 1). Failing test: tests/test_parser.py::test_nested_array. "
                        "Continue from that failure."
                    ),
                    "evidence": [
                        "pytest_ok=False",
                        "failed:tests/test_parser.py::test_nested_array",
                    ],
                }
            },
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.SEND_NUDGE
    assert "test_nested_array" in action.payload["text"]
    assert not action.payload["text"].startswith("PEX:")


def test_repeated_premature_fingerprint_applies_evidence_overlay_on_stop():
    verification = {
        "status": "acceptance_gap",
        "correction": (
            "report.txt is missing from the workspace. "
            "Create that artifact before stopping."
        ),
        "evidence": ["missing:report.txt"],
    }
    first = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.STOP, message_delta="Stopping here."),
        scores=TrajectoryScores(
            features={
                "verification": verification,
                "recommended_overlays": ["evidence-before-done"],
                "gap_stop_sessions": 1,
            }
        ),
    )
    assert plan_deterministic(first).type == InterventionType.SEND_NUDGE

    ready = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.STOP, message_delta="Stopping here."),
        scores=TrajectoryScores(
            features={
                "verification": verification,
                "recommended_overlays": ["evidence-before-done"],
                "gap_stop_sessions": 2,
            }
        ),
    )
    action = plan_deterministic(ready)
    assert action.type == InterventionType.APPLY_OVERLAY
    overlay = action.payload["overlay"]
    assert overlay["diff"]["extra"]["phase"] == "evidence-before-done"
    assert "report.txt" in overlay["diff"]["system_instructions"]
    assert not overlay["diff"]["system_instructions"].startswith("PEX:")


def test_fingerprint_lowers_drift_overlay_threshold_without_one_session_overfit():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.SHELL, phase=EventPhase.DURING, command="python train.py"),
        scores=TrajectoryScores(
            drift=0.62,
            features={
                "repeated_command_count": 5,
                "identical_error_count": 3,
                "recommended_overlays": ["evidence-before-done"],
                "gap_stop_sessions": 2,
            },
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.APPLY_OVERLAY
    overlay = action.payload["overlay"]
    assert overlay["diff"]["extra"]["fingerprint_overlay"] == "evidence-before-done"
    assert "acceptance evidence" in overlay["diff"]["system_instructions"]


def test_premature_stop_without_claim_uses_verification():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.STOP, message_delta="Stopping here."),
        scores=TrajectoryScores(
            features={
                "verification": {
                    "status": "contradicted",
                    "correction": (
                        "report.txt is missing from the workspace. "
                        "Create report.txt containing shipped."
                    ),
                    "evidence": ["missing:report.txt"],
                }
            },
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.SEND_NUDGE
    assert "report.txt" in action.payload["text"]
    assert not action.payload["text"].startswith("PEX:")


def test_lifecycle_proposal_remains_typed_and_human_gated():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.STOP),
        scores=TrajectoryScores(),
    )
    action = _action_from_proposal(
        request,
        {
            "type": "START_AGENT",
            "rationale": "A separate bounded worker is needed.",
            "evidence": ["source session cannot run the isolated probe"],
            "payload": {
                "project": "C:/project",
                "prompt": "Run only the isolated probe.",
                "config": {},
            },
        },
    )
    assert action.type == InterventionType.START_AGENT
    assert action.requires_capability == "start"
    assert action.authority_required == Authority.HUMAN
    assert action.reversible is False


def test_start_agent_requires_explicit_project_and_object_config():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.STOP),
        scores=TrajectoryScores(),
    )
    for payload in (
        {"prompt": "Run only the isolated probe.", "config": {}},
        {"project": "C:/project", "prompt": "Run only the isolated probe.", "config": []},
    ):
        action = _action_from_proposal(
            request,
            {
                "type": "START_AGENT",
                "rationale": "A separate bounded worker is needed.",
                "evidence": ["source session cannot run the isolated probe"],
                "payload": payload,
            },
        )
        assert action.type == InterventionType.NOOP
        assert action.evidence == ["typed_action_validation_failed"]


def test_cleanup_proposal_cannot_smuggle_a_raw_delete_path():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.STOP),
        scores=TrajectoryScores(),
    )
    action = _action_from_proposal(
        request,
        {
            "type": "CLEANUP",
            "rationale": "Remove residue.",
            "evidence": ["scratch expired"],
            "payload": {"mode": "delete", "paths": ["C:/project"]},
        },
    )
    assert action.type == InterventionType.NOOP
    assert "CLEANUP requires" in action.rationale


def test_before_delete_of_required_artifact_asks_the_human():
    now = datetime.now(UTC)
    goal = Goal(
        id="goal_ds",
        project_id="p1",
        title="Dataset then eval",
        objective="Keep the evaluation dataset",
        acceptance_criteria=["dataset.parquet exists"],
        created_at=now,
        updated_at=now,
    )
    request = SupervisorRequest(
        session=_session().model_copy(update={"goal_id": goal.id}),
        goal=goal,
        event=_event(
            EventType.SHELL,
            phase=EventPhase.BEFORE,
            command="rm dataset.parquet",
            approval_request={"request_id": "perm-clean"},
        ),
        scores=TrajectoryScores(),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.ASK_HUMAN
    assert "dataset.parquet" in str(action.payload.get("question") or "")


def test_during_delete_of_required_artifact_nudges_to_restore():
    now = datetime.now(UTC)
    goal = Goal(
        id="goal_ds",
        project_id="p1",
        title="Dataset then eval",
        objective="Keep the evaluation dataset",
        acceptance_criteria=["dataset.parquet exists"],
        created_at=now,
        updated_at=now,
    )
    request = SupervisorRequest(
        session=_session().model_copy(update={"goal_id": goal.id}),
        goal=goal,
        event=_event(
            EventType.SHELL,
            phase=EventPhase.DURING,
            command="rm dataset.parquet",
        ),
        scores=TrajectoryScores(),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.SEND_NUDGE
    assert "dataset.parquet" in str(action.payload.get("text") or "")
    assert "Restore" in str(action.payload.get("text") or "")


def test_agent_output_that_contradicts_the_ledger_is_redirected():
    now = datetime.now(UTC)
    goal = Goal(
        id="goal_1",
        project_id="p1",
        title="Train model",
        objective="Train without touching preprocessing",
        constraints=["Do not alter dataset preprocessing."],
        created_at=now,
        updated_at=now,
    )
    request = SupervisorRequest(
        session=_session(),
        goal=goal,
        event=_event(
            EventType.AGENT_RESPONSE,
            phase=EventPhase.DURING,
            message_delta="I will alter dataset preprocessing next.",
        ),
        scores=TrajectoryScores(),
        notes="agent_contradiction:Do not alter dataset preprocessing.",
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.SEND_NUDGE
    assert "Do not alter dataset preprocessing." in str(action.payload.get("text") or "")


def test_stop_after_abandoned_background_job_wakes_the_worker():
    now = datetime.now(UTC)
    launch = _event(
        EventType.SHELL,
        event_id="launch",
        ts=now,
        phase=EventPhase.DURING,
        command="nohup python train.py --full &",
        process_state={"background": True, "pid": 4242, "running": True},
    )
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.STOP, event_id="stop", ts=now, message_delta="I am done."),
        recent_events=[launch],
        scores=TrajectoryScores(),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.SEND_NUDGE
    text = str(action.payload.get("text") or "")
    assert "train.py" in text
    assert "4242" in text
    assert not text.startswith("PEX:")


def test_process_table_cleared_job_is_not_reopened_from_events():
    now = datetime.now(UTC)
    launch = _event(
        EventType.SHELL,
        event_id="launch",
        ts=now,
        phase=EventPhase.DURING,
        command="nohup python train.py --full &",
        process_state={"background": True, "pid": 4242, "running": True},
    )
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.STOP, event_id="stop", ts=now, message_delta="I am done."),
        recent_events=[launch],
        scores=TrajectoryScores(features={"abandoned_background": None}),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.NOOP


def test_process_table_running_job_names_the_table():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.STOP, message_delta="I am done."),
        scores=TrajectoryScores(
            features={
                "abandoned_background": {
                    "command": "nohup python train.py --full &",
                    "pid": 4242,
                    "process_table": "running",
                }
            }
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.SEND_NUDGE
    text = str(action.payload.get("text") or "")
    assert "process table" in text.lower()
    assert "4242" in text
    assert not text.startswith("PEX:")


def test_finished_background_job_does_not_wake_on_stop():
    now = datetime.now(UTC)
    launch = _event(
        EventType.SHELL,
        event_id="launch",
        ts=now,
        phase=EventPhase.DURING,
        command="nohup python train.py --full &",
        process_state={"background": True, "pid": 4242, "running": True},
    )
    done = _event(
        EventType.SHELL,
        event_id="done",
        ts=now + timedelta(seconds=1),
        phase=EventPhase.DURING,
        command="nohup python train.py --full &",
        process_state={"pid": 4242, "running": False, "exit_code": 0},
    )
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.STOP, event_id="stop", message_delta="Training finished."),
        recent_events=[launch, done],
        scores=TrajectoryScores(),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.NOOP


def test_broad_file_edits_alone_do_not_prove_goal_drift():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(
            EventType.FILE_EDIT,
            phase=EventPhase.DURING,
            file_paths=["style.css", "readme.md", "helpers.py", "utils.py"],
            message_delta="Refactor the unrelated helpers.",
        ),
        scores=TrajectoryScores(),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.NOOP
    assert not action.payload.get("text")
    assert "semantic review" in action.rationale
    assert any("style.css" in item for item in action.evidence)


def test_edit_of_required_artifact_is_not_refactor_drift():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(
            EventType.FILE_EDIT,
            phase=EventPhase.DURING,
            file_paths=["results.json"],
            message_delta="Update evaluation rows.",
        ),
        scores=TrajectoryScores(),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.NOOP


def test_compaction_checkpoints_the_attached_ledger():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.COMPACTION, message_delta="Compacting context."),
        scores=TrajectoryScores(),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.SEND_NUDGE
    text = str(action.payload.get("text") or "")
    assert "Ship eval" in text
    assert "results.json" in text
    assert not text.startswith("PEX:")


def test_pre_hook_compaction_annotates_instead_of_nudging():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(
            EventType.COMPACTION,
            phase=EventPhase.BEFORE,
            message_delta="Compacting context.",
        ),
        scores=TrajectoryScores(),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.ANNOTATE
    text = str(action.payload.get("text") or "")
    assert "Ship eval" in text
    assert "results.json" in text
    assert not text.startswith("PEX:")


def test_compaction_checkpoints_forgotten_facts_without_overlay_on_first_sample():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.COMPACTION, message_delta="Compacting context."),
        scores=TrajectoryScores(
            features={
                "context_health": 0.72,
                "compaction_count": 1,
                "forgotten_facts": ["schema.json is the source of truth for the parser."],
            }
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.SEND_NUDGE
    text = str(action.payload.get("text") or "")
    assert "schema.json is the source of truth" in text
    assert "Ship eval" in text
    assert not text.startswith("PEX:")


def test_repeated_forgotten_context_applies_health_overlay_on_compaction():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.COMPACTION, message_delta="Compacting context."),
        scores=TrajectoryScores(
            features={
                "context_health": 0.41,
                "compaction_count": 2,
                "forgotten_facts": ["schema.json is the source of truth for the parser."],
            }
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.APPLY_OVERLAY
    overlay = action.payload.get("overlay") or {}
    diff = overlay.get("diff") or {}
    assert "schema.json is the source of truth" in str(diff.get("system_instructions") or "")
    assert "WebSearch" in (diff.get("tools_disabled") or [])
    assert action.reversible is True


def test_cursor_without_modify_config_still_checkpoints_forgotten_facts():
    session = HarnessSession(
        id="cursor:s1",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="s1",
        project_id="p1",
        goal_id="goal_1",
        status=SessionStatus.WORKING,
    )
    request = SupervisorRequest(
        session=session,
        goal=_goal(),
        event=_event(
            EventType.COMPACTION,
            harness_type=HarnessType.CURSOR,
            session_id=session.id,
            message_delta="Compacting context.",
        ),
        scores=TrajectoryScores(
            features={
                "context_health": 0.41,
                "compaction_count": 2,
                "forgotten_facts": ["schema.json is the source of truth for the parser."],
            }
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.SEND_NUDGE
    text = str(action.payload.get("text") or "")
    assert "schema.json is the source of truth" in text
    assert not text.startswith("PEX:")


def test_sibling_overlap_is_not_deterministic_proof_of_duplicate_work():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(
            EventType.FILE_EDIT,
            phase=EventPhase.DURING,
            file_paths=["parser.py"],
            message_delta="Inspect the parser.",
        ),
        scores=TrajectoryScores(
            features={
                "duplicate_work": {
                    "sibling_session_id": "cursor:secret-vendor-99",
                    "harness": "cursor",
                    "path": "parser.py",
                }
            }
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.NOOP
    text = str(action.payload.get("text") or "")
    assert text == ""
    assert "semantic review" in action.rationale
    assert "overlap:parser.py" in action.evidence


def test_ambiguous_user_prompt_is_rewritten_against_the_ledger():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(
            EventType.USER_PROMPT,
            message_delta="Just quickly hack whatever works.",
        ),
        scores=TrajectoryScores(),
        notes="dangerous_ambiguity",
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.ANNOTATE
    text = str(action.payload.get("text") or "")
    assert "Ship eval" in text
    assert "ambiguous" in text.lower()
    assert not text.startswith("PEX:")


def test_stop_with_two_cheap_approaches_asks_human_to_fork():
    session = _session()
    session.capabilities = {"fork": True, "stop": True, "send_message": True}
    request = SupervisorRequest(
        session=session,
        goal=_goal(),
        event=_event(EventType.STOP, message_delta="Paused to pick an approach."),
        scores=TrajectoryScores(
            features={
                "competing_approaches": [
                    "Try an in-memory index first",
                    "Try a sqlite index first",
                ],
                "parent_objective": (
                    "Isolated speculative probe. Try only this approach: "
                    "Try an in-memory index first."
                ),
                "probe_bundle": {
                    "goal_id": "goal_1",
                    "target_session_id": session.id,
                    "source_session_ids": [session.id],
                    "next_objective": (
                        "Isolated speculative probe. Try only this approach: "
                        "Try a sqlite index first."
                    ),
                },
            }
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.FORK_PROBE
    assert action.authority_required == Authority.HUMAN
    assert action.requires_capability == "fork"
    assert action.payload["approaches"][0] == "Try an in-memory index first"
    assert "sqlite" in str(action.payload["bundle"]["next_objective"])
    assert not str(action.payload.get("parent_objective") or "").startswith("PEX:")


def test_acceptance_gap_still_outranks_speculative_fork():
    session = _session()
    session.capabilities = {"fork": True, "send_message": True}
    request = SupervisorRequest(
        session=session,
        goal=_goal(),
        event=_event(EventType.STOP, message_delta="I am done."),
        scores=TrajectoryScores(
            features={
                "verification": {
                    "status": "acceptance_gap",
                    "correction": "Create report.txt containing shipped.",
                    "evidence": ["missing:report.txt"],
                },
                "competing_approaches": ["Try sqlite", "Try memory"],
                "parent_objective": "probe A",
                "probe_bundle": {"goal_id": "goal_1"},
            }
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.SEND_NUDGE
    assert "report.txt" in str(action.payload.get("text") or "")


def test_speculative_compare_disposes_loser_and_continues_winner():
    loser = _session()
    loser.capabilities = {"fork": True, "stop": True}
    lost = SupervisorRequest(
        session=loser,
        goal=_goal(),
        event=_event(EventType.STOP),
        scores=TrajectoryScores(
            features={
                "in_speculative_pair": True,
                "speculative_compare": {
                    "winner": "b",
                    "winner_session_id": "synthetic:winner",
                    "loser_session_id": loser.id,
                    "winner_approach": "sqlite",
                    "loser_approach": "in-memory",
                    "reasons": ["Approach B: supported, pytest=True"],
                },
            }
        ),
    )
    action = plan_deterministic(lost)
    assert action.type == InterventionType.STOP_AGENT
    assert action.authority_required == Authority.HUMAN

    winner = _session()
    winner.id = "synthetic:winner"
    winner.vendor_session_id = "winner"
    winner.capabilities = {"fork": True, "send_message": True}
    won = SupervisorRequest(
        session=winner,
        goal=_goal(),
        event=_event(EventType.STOP, session_id=winner.id),
        scores=TrajectoryScores(
            features={
                "in_speculative_pair": True,
                "speculative_compare": {
                    "winner": "b",
                    "winner_session_id": winner.id,
                    "loser_session_id": "synthetic:s1",
                    "winner_approach": "sqlite",
                    "loser_approach": "in-memory",
                    "reasons": ["Approach B: supported, pytest=True"],
                },
            }
        ),
    )
    keep = plan_deterministic(won)
    assert keep.type == InterventionType.SEND_NUDGE
    text = str(keep.payload.get("text") or "")
    assert "sqlite" in text
    assert "in-memory" in text
    assert not text.startswith("PEX:")


def test_speculative_fork_requires_negotiated_fork_capability():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.STOP),
        scores=TrajectoryScores(
            features={
                "competing_approaches": ["Try sqlite", "Try memory"],
                "parent_objective": "probe A",
                "probe_bundle": {"goal_id": "goal_1"},
            }
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.NOOP


def test_in_pair_failed_pytest_waits_instead_of_nagged_continue():
    session = _session()
    session.capabilities = {"fork": True, "stop": True, "send_message": True}
    request = SupervisorRequest(
        session=session,
        goal=_goal(),
        event=_event(EventType.STOP),
        scores=TrajectoryScores(
            features={
                "in_speculative_pair": True,
                "verification": {
                    "status": "acceptance_gap",
                    "correction": (
                        "The latest observed pytest run failed. Continue from that failure."
                    ),
                    "evidence": ["pytest_ok=False"],
                },
            }
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.NOOP


def test_file_count_probe_requests_verification_instead_of_noop():
    now = datetime.now(UTC)
    goal = Goal(
        id="goal_1",
        project_id="p1",
        title="Ship report",
        objective="Ship the report artifact",
        acceptance_criteria=["report.txt"],
        created_at=now,
        updated_at=now,
    )
    probe = {
        "id": "probe_file_count",
        "kind": "file_count",
        "harness_type": "synthetic",
        "session_id": "synthetic:s1",
        "project_id": "p1",
        "goal_id": "goal_1",
        "request_event_id": "e1",
        "cwd": "C:/workspace",
        "relative_targets": ["report.txt"],
        "timeout_seconds": 60,
        "output_limit_bytes": 16_384,
    }
    request = SupervisorRequest(
        session=_session(),
        goal=goal,
        event=_event(EventType.STOP, message_delta="I am done."),
        scores=TrajectoryScores(
            premature_completion=0.9,
            features={
                "verification": {
                    "status": "uncertain",
                    "evidence_gathering": {
                        "state": "inspected",
                        "probe": probe,
                    },
                    "verdicts": [
                        {
                            "status": "uncertain",
                            "evidence": ["temporarily_unreadable:report.txt"],
                        }
                    ],
                }
            },
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.REQUEST_VERIFICATION
    assert action.payload["probe"]["kind"] == "file_count"
    assert "report.txt" in action.payload["text"]
    assert not action.payload["text"].startswith("PEX:")


def test_unknown_probe_kind_stays_noop():
    request = SupervisorRequest(
        session=_session(),
        goal=_goal(),
        event=_event(EventType.STOP, message_delta="I am done."),
        scores=TrajectoryScores(
            features={
                "verification": {
                    "status": "uncertain",
                    "evidence_gathering": {
                        "state": "inspected",
                        "probe": {"id": "probe_x", "kind": "invented_kind"},
                    },
                }
            }
        ),
    )
    action = plan_deterministic(request)
    assert action.type == InterventionType.NOOP
    assert "unsupported_probe:invented_kind" in action.evidence
