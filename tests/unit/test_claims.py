from pex_bridge.claims import extract_claims
from pex_protocol.enums import EventType, HarnessType
from pex_protocol.session import HarnessEvent
from datetime import UTC, datetime


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
