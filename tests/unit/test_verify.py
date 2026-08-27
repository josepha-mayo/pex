from datetime import UTC, datetime

from pex_protocol.enums import EventType, HarnessType
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent
from pex_supervisor.verify import verify_claims
from pex_supervisor.workspace import snapshot


def _event(**kwargs) -> HarnessEvent:
    return HarnessEvent(
        event_id=kwargs.pop("event_id", "e"),
        ts=datetime.now(UTC),
        harness_type=HarnessType.SYNTHETIC,
        session_id="synthetic:s",
        event_type=kwargs.pop("event_type", EventType.AGENT_RESPONSE),
        **kwargs,
    )


def _goal(**kwargs) -> Goal:
    now = datetime.now(UTC)
    return Goal(
        id="g",
        project_id="p",
        title="t",
        objective=kwargs.pop("objective", "Finish eval"),
        created_at=now,
        updated_at=now,
        **kwargs,
    )


def test_tests_pass_without_pytest_is_uncertain():
    result = verify_claims(
        [{"statement": "All tests passed", "kind": "tests_pass", "polarity": "asserted", "confidence": 0.9, "source_event_id": "e"}],
        [_event(message_delta="All tests passed")],
        _goal(acceptance_criteria=["tests pass"]),
        {},
    )
    assert result["status"] == "uncertain"
    assert result["correction"] is None


def test_tests_pass_after_failed_pytest_is_contradicted():
    result = verify_claims(
        [{"statement": "All tests passed", "kind": "tests_pass", "polarity": "asserted", "confidence": 0.9, "source_event_id": "e2"}],
        [
            _event(
                event_id="e1",
                event_type=EventType.SHELL,
                command="pytest -q",
                process_state={"pytest": {"ok": False, "exit_code": 1, "failed": "tests/test_parser.py::test_nested_array"}},
                file_paths=["src/parser.py"],
            ),
            _event(event_id="e2", event_type=EventType.STOP, message_delta="All tests passed"),
        ],
        _goal(acceptance_criteria=["tests pass"]),
        {},
    )
    assert result["status"] == "contradicted"
    assert "test_nested_array" in (result["correction"] or "")
    assert not (result["correction"] or "").startswith("PEX:")


def test_short_eval_file_contradicts_completion(tmp_path):
    rows = "\n".join(f'{{"id": {i}}}' for i in range(27))
    (tmp_path / "results.jsonl").write_text(rows + "\n", encoding="utf-8")
    workspace = snapshot(tmp_path, run_pytest=False)
    result = verify_claims(
        [{"statement": "The evaluation is complete", "kind": "evaluation_complete", "polarity": "asserted", "confidence": 0.85, "source_event_id": "e"}],
        [_event(event_type=EventType.STOP, message_delta="The evaluation is complete.")],
        _goal(acceptance_criteria=["results.jsonl has 30 rows"]),
        workspace,
    )
    assert result["status"] == "contradicted"
    assert "27" in (result["correction"] or "")
    assert "30" in (result["correction"] or "")
