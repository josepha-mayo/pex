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
    assert result.action.type.value == "CONTINUE_SESSION"


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
