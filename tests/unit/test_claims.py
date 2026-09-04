from datetime import UTC, datetime

from pex_bridge.claims import extract_claims
from pex_protocol.enums import EventType, HarnessType
from pex_protocol.session import HarnessEvent


def _event(text: str, event_id: str = "e1") -> HarnessEvent:
    return HarnessEvent(
        event_id=event_id,
        ts=datetime.now(UTC),
        harness_type=HarnessType.SYNTHETIC,
        session_id="synthetic:s",
        event_type=EventType.AGENT_RESPONSE,
        message_delta=text,
    )


def test_parser_and_tests_pass_are_two_claims():
    claims = extract_claims([_event("Implemented the parser and tests pass.")])
    kinds = {item["kind"] for item in claims}
    statements = " ".join(item["statement"] for item in claims).lower()
    assert "tests_pass" in kinds
    assert "implemented" in kinds
    assert "parser" in statements


def test_negative_claim_is_not_completion():
    claims = extract_claims([_event("I updated the config. I did not run integration tests.")])
    polarities = {item["kind"]: item["polarity"] for item in claims}
    assert polarities.get("unverified") == "denied"
    assert any("integration" in item["statement"].lower() for item in claims)


def test_stop_without_narration_extracts_nothing():
    claims = extract_claims(
        [
            HarnessEvent(
                event_id="stop",
                ts=datetime.now(UTC),
                harness_type=HarnessType.SYNTHETIC,
                session_id="synthetic:s",
                event_type=EventType.STOP,
            )
        ]
    )
    assert claims == []


def test_user_prompt_and_shell_output_are_not_worker_claims():
    now = datetime.now(UTC)
    claims = extract_claims(
        [
            HarnessEvent(
                event_id="prompt",
                ts=now,
                harness_type=HarnessType.SYNTHETIC,
                session_id="synthetic:s",
                event_type=EventType.USER_PROMPT,
                message_delta="Make all tests pass and finish the deployment.",
            ),
            HarnessEvent(
                event_id="shell",
                ts=now,
                harness_type=HarnessType.SYNTHETIC,
                session_id="synthetic:s",
                event_type=EventType.SHELL,
                message_delta="All tests passed",
                command="pytest -q",
            ),
        ]
    )
    assert claims == []


def test_failed_tests_are_denied_and_contrast_clause_is_still_extracted():
    claims = extract_claims(
        [_event("Some tests failed, but implemented the parser.")]
    )

    assert any(
        item["kind"] == "tests_pass" and item["polarity"] == "denied"
        for item in claims
    )
    assert any(
        item["kind"] == "implemented" and item["polarity"] == "asserted"
        for item in claims
    )


def test_not_all_tests_passed_is_never_an_asserted_pass_claim():
    claims = extract_claims([_event("Not all tests passed.")])

    assert claims
    assert all(item["polarity"] == "denied" for item in claims)
