from datetime import UTC, datetime

from pex_bridge.claims import extract_claims
from pex_bridge.shell_state import parse_pytest_process_state
from pex_protocol.enums import EventType, HarnessType
from pex_protocol.session import HarnessEvent


def _response(text: str) -> HarnessEvent:
    return HarnessEvent(
        event_id="claim",
        ts=datetime.now(UTC),
        harness_type=HarnessType.SYNTHETIC,
        session_id="synthetic:s",
        event_type=EventType.AGENT_RESPONSE,
        message_delta=text,
    )


def test_negative_claim_strips_check_and_checked_helpers():
    unchecked = extract_claims([_response("I did not check the release artifact.")])
    checked = extract_claims([_response("I have not checked the deployment receipt.")])

    assert unchecked[0]["statement"] == "the release artifact"
    assert checked[0]["statement"] == "the deployment receipt"
    assert unchecked[0]["polarity"] == "denied"


def test_http_code_is_not_mistaken_for_process_exit_code():
    state = parse_pytest_process_state(
        "pytest -q",
        {"code": 200, "status_code": 200, "stdout": "1 passed in 0.01s"},
    )

    assert state == {
        "pytest": {"ok": None, "output": "1 passed in 0.01s", "passed": 1}
    }


def test_explicit_process_exit_code_still_controls_result():
    state = parse_pytest_process_state(
        "pytest -q", {"processExitCode": 1, "stdout": "1 passed in 0.01s"}
    )

    assert state["pytest"]["ok"] is False
    assert state["pytest"]["exit_code"] == 1
    assert state["pytest"]["passed"] == 1


def test_compound_pytest_command_is_rejected_even_with_failure_output():
    state = parse_pytest_process_state(
        "pytest -q || true",
        {"processExitCode": 0, "stdout": "FAILED tests/test_real.py::test_result\n1 failed"},
    )

    assert state is None


def test_direct_pytest_failure_summary_is_observed():
    state = parse_pytest_process_state(
        "pytest -q",
        {"processExitCode": 1, "stdout": "FAILED tests/test_real.py::test_result\n1 failed"},
    )

    assert state is not None
    assert state["pytest"]["ok"] is False
    assert state["pytest"]["failed"] == "tests/test_real.py::test_result"
    assert state["pytest"]["failed_count"] == 1


def test_pass_summary_with_terminal_zero_preserves_count_and_support_state():
    state = parse_pytest_process_state(
        "pytest -q", {"processExitCode": 0, "stdout": "4 passed in 0.02s"}
    )

    assert state == {
        "pytest": {
            "ok": True,
            "output": "4 passed in 0.02s",
            "exit_code": 0,
            "passed": 4,
        }
    }


def test_generic_passed_status_is_not_a_terminal_process_exit_receipt():
    state = parse_pytest_process_state(
        "pytest -q", {"status": "passed", "stdout": "4 passed in 0.02s"}
    )

    assert state == {
        "pytest": {"ok": None, "output": "4 passed in 0.02s", "passed": 4}
    }


def test_conflicting_explicit_exit_fields_are_not_a_terminal_receipt():
    state = parse_pytest_process_state(
        "pytest -q",
        {"exit_code": 0, "processExitCode": 1, "stdout": "4 passed in 0.02s"},
    )

    assert state == {
        "pytest": {"ok": None, "output": "4 passed in 0.02s", "passed": 4}
    }


def test_distinct_pass_like_lines_do_not_choose_a_spoofed_count():
    state = parse_pytest_process_state(
        "pytest -q",
        {
            "processExitCode": 0,
            "stdout": "999 passed in 0.01s\n4 passed in 0.02s",
        },
    )

    assert state == {
        "pytest": {
            "ok": True,
            "output": "999 passed in 0.01s\n4 passed in 0.02s",
            "exit_code": 0,
        }
    }


def test_terminal_summary_preserves_passed_collected_and_nonpassing_categories():
    state = parse_pytest_process_state(
        "pytest -q",
        {
            "processExitCode": 0,
            "stdout": (
                "collected 7 items\n"
                "================ 4 passed, 2 skipped, 1 xfailed in 0.03s ================"
            ),
        },
    )

    assert state is not None
    assert state["pytest"] == {
        "ok": True,
        "output": (
            "collected 7 items\n"
            "================ 4 passed, 2 skipped, 1 xfailed in 0.03s ================"
        ),
        "exit_code": 0,
        "passed": 4,
        "collected": 7,
        "skipped": 2,
        "xfailed": 1,
    }
