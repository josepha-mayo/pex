from datetime import UTC, datetime

from pex_bridge.scoring import extract_features, score_trajectory
from pex_protocol.enums import EventType, HarnessType
from pex_protocol.session import HarnessEvent


def _event(**kwargs) -> HarnessEvent:
    return HarnessEvent(
        event_id="e",
        ts=datetime.now(UTC),
        harness_type=HarnessType.SYNTHETIC,
        session_id="synthetic:s",
        event_type=kwargs.pop("event_type", EventType.AGENT_RESPONSE),
        **kwargs,
    )


def test_bare_done_is_not_a_success_claim():
    features = extract_features([_event(message_delta="done")])
    assert features["success_claims"] == 0


def test_all_tests_passed_is_a_success_claim():
    features = extract_features([_event(message_delta="All tests passed")])
    assert features["success_claims"] == 1


def test_user_prompt_and_shell_output_are_not_success_claims():
    features = extract_features(
        [
            _event(
                event_type=EventType.USER_PROMPT,
                message_delta="Make all tests pass before you stop.",
            ),
            _event(
                event_type=EventType.SHELL,
                message_delta="All tests passed",
                command="printf diagnostic",
            ),
        ]
    )
    assert features["success_claims"] == 0


def test_missing_tests_is_not_contradiction():
    scores = score_trajectory(
        [
            _event(event_type=EventType.STOP, message_delta="All tests passed. I am done."),
        ],
        None,
    )
    assert scores.features["tests_run"] == 0
    assert scores.claim_contradiction < 0.7
    assert scores.premature_completion < 0.7


def test_failed_pytest_plus_success_claim_is_contradiction():
    scores = score_trajectory(
        [
            _event(
                event_type=EventType.SHELL,
                command="pytest -q",
                process_state={"pytest": {"ok": False}},
            ),
            _event(event_type=EventType.STOP, message_delta="All tests passed"),
        ],
        None,
    )
    assert scores.features["pytest_failed"] is True
    assert scores.claim_contradiction >= 0.7


def test_one_pytest_event_is_counted_once_when_command_and_state_are_present():
    features = extract_features(
        [
            _event(
                event_type=EventType.SHELL,
                command="pytest -q",
                process_state={"pytest": {"ok": True}},
            )
        ]
    )
    assert features["tests_run"] == 1


def test_latest_pytest_result_replaces_an_older_failure():
    scores = score_trajectory(
        [
            _event(
                event_type=EventType.SHELL,
                command="pytest -q",
                process_state={"pytest": {"ok": False}},
            ),
            _event(
                event_type=EventType.SHELL,
                command="pytest -q",
                process_state={"pytest": {"ok": True}},
            ),
            _event(event_type=EventType.STOP, message_delta="All tests passed"),
        ],
        None,
    )
    assert scores.features["pytest_failed"] is False
    assert scores.claim_contradiction == 0


def test_repeated_tools_contribute_to_low_information_drift():
    events = [_event(event_type=EventType.TOOL_CALL, tool_name="read_file") for _ in range(7)]
    features = extract_features(events)
    scores = score_trajectory(events, None)
    assert features["repeated_tool_count"] == 6
    assert scores.drift > 0


def test_identical_error_count_measures_repeat_occurrences():
    features = extract_features(
        [_event(error="same failure") for _ in range(4)] + [_event(error="different failure")]
    )
    assert features["identical_error_count"] == 3


def test_repeated_identical_command_errors_reach_redirect_drift():
    events = [
        _event(
            event_type=EventType.SHELL,
            command="python train.py",
            error="FileNotFoundError: data.parquet",
        )
        for _ in range(4)
    ]
    scores = score_trajectory(events, None)
    assert scores.features["repeated_command_count"] >= 3
    assert scores.features["identical_error_count"] >= 3
    assert scores.drift >= 0.75
