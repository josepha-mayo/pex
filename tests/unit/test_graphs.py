from datetime import UTC, datetime
from types import SimpleNamespace

from pex_protocol.actions import InterventionType
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorRequest, TrajectoryScores
from pex_supervisor.graphs import _verifier_verdict, should_use_graph
from pex_supervisor.loop import _action_from_proposal, _usage, decide


def _request(premature: float) -> SupervisorRequest:
    now = datetime.now(UTC)
    return SupervisorRequest(
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
        scores=TrajectoryScores(
            premature_completion=premature, features={"tests_run": 0, "stops": 1}
        ),
    )


def test_high_stakes_uses_graph_predicate():
    assert should_use_graph(_request(0.95)) is True
    assert should_use_graph(_request(0.1)) is False


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


def test_verifier_is_fail_closed_on_failure_or_malformed_text():
    failed = SimpleNamespace(status=SimpleNamespace(value="failed"), failed_nodes=1, results={})
    assert _verifier_verdict(failed)[0] == "REJECT"

    malformed_node = SimpleNamespace(
        status=SimpleNamespace(value="completed"),
        __str__=lambda self: "looks fine",
    )
    malformed = SimpleNamespace(
        status=SimpleNamespace(value="completed"),
        failed_nodes=0,
        results={"verifier": malformed_node},
    )
    assert _verifier_verdict(malformed)[0] == "REJECT"


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


def test_graph_accumulated_usage_is_audited():
    result = SimpleNamespace(
        accumulated_usage=SimpleNamespace(inputTokens=12, outputTokens=7)
    )
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


def test_noop_when_required_file_missing_becomes_nudge(tmp_path):
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
    assert action.type == InterventionType.SEND_NUDGE
    assert "report.txt" in action.payload["text"]
    assert not action.payload["text"].startswith("PEX:")


def test_noop_with_missing_artifact_message_becomes_nudge():
    action = _action_from_proposal(
        _request(0.1),
        {
            "type": "NOOP",
            "rationale": "missing file",
            "evidence": ["run_verification artifacts=[]"],
            "payload": {
                "text": "Goal not met: report.txt is missing. Please create report.txt containing shipped."
            },
        },
    )
    assert action.type == InterventionType.SEND_NUDGE
    assert "report.txt" in action.payload["text"]


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
    assert "canned_prefix_coerced_noop" in action.evidence
