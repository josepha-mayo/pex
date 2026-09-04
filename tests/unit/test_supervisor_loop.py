"""Tests for the live structured-output supervisor loop."""

from datetime import UTC, datetime
from types import SimpleNamespace

from pex_protocol.actions import InterventionType, RiskLevel
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorRequest, TrajectoryScores
from pex_supervisor.loop import (
    _action_from_proposal,
    _preserve_deterministic_truth,
    _usage,
    decide,
)


def _request(premature: float) -> SupervisorRequest:
    now = datetime.now(UTC)
    return SupervisorRequest(
        session=HarnessSession(
            id="synthetic:demo",
            harness_type=HarnessType.SYNTHETIC,
            vendor_session_id="demo",
            project_id="p",
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
        scores=TrajectoryScores(
            premature_completion=premature, features={"tests_run": 0, "stops": 1}
        ),
    )


def test_decide_without_model_stays_deterministic():
    result = decide(_request(0.95))
    assert result.used_llm is False
    assert result.action.type.value == "NOOP"


def test_decide_skips_model_on_non_stop_events():
    from pex_supervisor.loop import needs_semantic_inference

    stop = _request(0.1)
    assert needs_semantic_inference(stop) is True
    now = datetime.now(UTC)
    shell = SupervisorRequest(
        session=stop.session,
        goal=stop.goal,
        event=HarnessEvent(
            event_id="shell",
            ts=now,
            harness_type=HarnessType.SYNTHETIC,
            session_id="synthetic:demo",
            event_type=EventType.SHELL,
            command="pytest -q",
        ),
        scores=TrajectoryScores(premature_completion=0.1, features={}),
    )
    assert needs_semantic_inference(shell) is False
    result = decide(shell, model=object())
    assert result.used_llm is False
    assert result.diagnosis == "deterministic_triage"


def test_decide_skips_model_when_no_goal_is_attached():
    from pex_supervisor.loop import needs_semantic_inference

    stop = _request(0.1)
    stop.goal = None
    stop.session.goal_id = None
    assert needs_semantic_inference(stop) is False
    result = decide(stop, model=object())
    assert result.used_llm is False
    assert result.diagnosis == "deterministic_triage"


def test_typed_permission_action_requires_explicit_request_and_decision():
    invalid = _action_from_proposal(
        _request(0.1),
        {
            "type": "RESPOND_PERMISSION",
            "rationale": "approve",
            "evidence": [],
            "payload": {},
        },
    )
    assert invalid.type == InterventionType.NOOP

    valid = _action_from_proposal(
        _request(0.1),
        {
            "type": "RESPOND_PERMISSION",
            "rationale": "safe visible test",
            "evidence": ["request observed"],
            "payload": {"request_id": "req-1", "decision": "deny"},
        },
    )
    assert valid.type == InterventionType.RESPOND_PERMISSION
    assert valid.payload == {"request_id": "req-1", "decision": "deny"}
    assert valid.requires_capability == "deny"
    assert valid.reversible is False


def test_unknown_risk_cannot_be_downgraded_to_low():
    action = _action_from_proposal(
        _request(0.1),
        {
            "type": "RESPOND_PERMISSION",
            "risk": "totally-safe-trust-me",
            "rationale": "approve",
            "evidence": ["request observed"],
            "payload": {"request_id": "req-risk", "decision": "allow"},
        },
    )

    assert action.type == InterventionType.NOOP
    assert action.risk == RiskLevel.NONE
    assert "unknown risk level" in action.rationale


def test_model_cannot_manufacture_context_actions():
    for action_type in ("FRESH_HANDOFF", "INJECT_CONTEXT"):
        action = _action_from_proposal(
            _request(0.1),
            {
                "type": action_type,
                "rationale": "model supplied context",
                "evidence": ["claimed source"],
                "payload": {"text": "untrusted", "bundle": {"items": []}},
            },
        )
        assert action.type == InterventionType.NOOP
        assert action.reversible is False
        assert "provenance-backed bridge context store" in action.rationale


def test_strands_accumulated_usage_is_audited():
    result = SimpleNamespace(accumulated_usage=SimpleNamespace(inputTokens=12, outputTokens=7))
    assert _usage(result) == (12, 7)


def test_worker_facing_empty_evidence_is_noop():
    action = _action_from_proposal(
        _request(0.1),
        {
            "type": "SEND_NUDGE",
            "rationale": "guess",
            "evidence": [],
            "payload": {"text": "please continue"},
        },
    )
    assert action.type == InterventionType.NOOP
    assert "empty_evidence_coerced_noop" in action.evidence
    assert action.reversible is False


def test_worker_message_is_not_falsely_marked_reversible():
    action = _action_from_proposal(
        _request(0.1),
        {
            "type": "SEND_NUDGE",
            "rationale": "specific observed issue",
            "evidence": ["test_a failed"],
            "payload": {"text": "Re-run test_a after correcting the observed assertion."},
        },
    )
    assert action.type == InterventionType.SEND_NUDGE
    assert action.reversible is False


def test_deterministic_preplan_does_not_replace_completed_semantic_wording():
    request = _request(0.9)
    deterministic = _action_from_proposal(
        request,
        {
            "type": "SEND_NUDGE",
            "rationale": "verified acceptance gap",
            "evidence": ["report.txt absent"],
            "payload": {"text": "Create report.txt from the verified output."},
        },
    )
    semantic_action = _action_from_proposal(
        request,
        {
            "type": "SEND_NUDGE",
            "rationale": "model connected the observed failure to the goal",
            "evidence": ["report.txt absent"],
            "payload": {
                "text": "report.txt is absent; create it and verify its contents."
            },
        },
    )
    semantic = __import__(
        "pex_protocol.supervisor", fromlist=["SupervisorResult"]
    ).SupervisorResult(
        action=semantic_action,
        used_llm=True,
        diagnosis="semantic",
        inference_status="completed",
    )

    result = _preserve_deterministic_truth(request, deterministic, semantic)

    assert result.action == semantic_action
    assert result.action.payload["text"].startswith("report.txt is absent")
    assert "deterministic_truth_preserved" not in result.diagnosis


def test_model_noop_cannot_infer_missing_files_from_runtime_cwd(tmp_path):
    request = _request(0.9)
    request.session.cwd = str(tmp_path)
    request.goal.evidence_requirements = ["report.txt"]
    request.goal.objective = "Create report.txt containing shipped."
    action = _action_from_proposal(
        request,
        {
            "type": "NOOP",
            "rationale": "stopped",
            "evidence": ["workspace files=[]"],
            "payload": {},
        },
    )
    assert action.type == InterventionType.NOOP
    assert action.payload == {}


def test_noop_with_missing_artifact_message_without_required_file_stays_silent():
    action = _action_from_proposal(
        _request(0.1),
        {
            "type": "NOOP",
            "rationale": "missing file",
            "evidence": ["run_verification artifacts=[]"],
            "payload": {
                "text": (
                    "Goal not met: report.txt is missing. "
                    "Please create report.txt containing shipped."
                )
            },
        },
    )
    assert action.type == InterventionType.NOOP
    assert not action.payload.get("text")


def test_pex_prefixed_specific_nudge_is_stripped():
    action = _action_from_proposal(
        _request(0.1),
        {
            "type": "SEND_NUDGE",
            "rationale": "file missing",
            "evidence": ["cwd exists"],
            "payload": {"text": "PEX: Create report.txt containing shipped."},
        },
    )
    assert action.type == InterventionType.SEND_NUDGE
    assert action.payload["text"] == "Create report.txt containing shipped."


def test_pex_prefixed_worker_text_is_noop():
    action = _action_from_proposal(
        _request(0.1),
        {
            "type": "SEND_NUDGE",
            "rationale": "template",
            "evidence": ["cwd exists"],
            "payload": {"text": "PEX: keep going until tests pass"},
        },
    )
    assert action.type == InterventionType.NOOP
    assert "generic_worker_text_coerced_noop" in action.evidence


def test_model_action_recursively_masks_workspace_and_secrets_in_keys_and_values():
    request = _request(0.1)
    workspace = r"C:\Users\JosephMayo\Projects\private-repo"
    secret = "super-secret-value"
    request.session.cwd = workspace
    request.session.repo = workspace

    action = _action_from_proposal(
        request,
        {
            "type": "SEND_NUDGE",
            "rationale": f"Inspect {workspace}; token={secret}",
            "evidence": [f"Observed {workspace}\\report.txt token={secret}"],
            "payload": {
                "text": f"pex: Inspect {workspace}\\report.txt; token={secret}",
                f"token={secret}": {
                    "path": workspace,
                    "nested": [f"password={secret}", float("nan")],
                },
            },
        },
    )
    serialized = action.model_dump_json()

    assert action.type == InterventionType.SEND_NUDGE
    assert action.payload["text"].startswith("Inspect <workspace>")
    assert workspace.casefold() not in serialized.casefold()
    assert secret not in serialized
    assert "<workspace>" in serialized
    assert "[REDACTED:credential_assignment]" in serialized
    assert "NaN" not in serialized
