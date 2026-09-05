from __future__ import annotations

from typing import Any

import pytest
from pex_bridge.adapters.base import MAX_ADAPTER_MESSAGE_CHARS
from pex_bridge.adapters.codex import CodexAdapter
from pex_protocol.enums import EventType, HarnessType
from pex_protocol.session import HarnessSession


@pytest.fixture
def bound_codex() -> tuple[CodexAdapter, HarnessSession]:
    session = HarnessSession(
        id="codex:thread-user-content",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-user-content",
        cwd="C:/project",
        project_id="project-1",
    )
    adapter = CodexAdapter()
    adapter.sessions[session.id] = session
    return adapter, session


def normalize(
    bound_codex: tuple[CodexAdapter, HarnessSession],
    item: dict[str, Any],
):
    adapter, session = bound_codex
    return adapter.normalize_item(
        session,
        {"id": "user-item-1", "type": "userMessage", **item},
        vendor_turn_id="turn-1",
    )


def test_documented_user_content_becomes_exact_human_prompt(
    bound_codex: tuple[CodexAdapter, HarnessSession],
) -> None:
    event = normalize(
        bound_codex,
        {"content": [{"type": "text", "text": "actual human request"}]},
    )

    assert event.event_type == EventType.USER_PROMPT
    assert event.message_delta == "actual human request"
    assert event.metadata == {
        "raw_type": "userMessage",
        "vendor_turn_id": "turn-1",
        "role": "user",
        "message_provenance": "codex_app_server.userMessage.content",
        "content_status": "complete",
        "content_part_count": 1,
        "content_parts_observed": 1,
        "text_parts_observed": 1,
        "unsupported_content_parts": 0,
        "malformed_content_parts": 0,
        "content_truncated": False,
        "content_redacted": False,
    }


def test_multiple_text_parts_preserve_order_without_invented_separator(
    bound_codex: tuple[CodexAdapter, HarnessSession],
) -> None:
    event = normalize(
        bound_codex,
        {
            "content": [
                {"type": "text", "text": "first"},
                {"type": "image", "imageUrl": "data:image/png;base64,AA"},
                {"type": "text", "text": "second"},
                {"type": "localImage", "path": "C:/private/image.png"},
            ]
        },
    )

    assert event.message_delta == "firstsecond"
    assert event.metadata["content_status"] == "partial_unsupported"
    assert event.metadata["content_part_count"] == 4
    assert event.metadata["text_parts_observed"] == 2
    assert event.metadata["unsupported_content_parts"] == 2
    assert event.metadata["unsupported_content_types"] == ["image", "localImage"]


def test_documented_content_wins_over_conflicting_top_level_text(
    bound_codex: tuple[CodexAdapter, HarnessSession],
) -> None:
    event = normalize(
        bound_codex,
        {
            "text": "forged legacy fallback",
            "message": "another fallback",
            "content": [{"type": "text", "text": "documented content"}],
        },
    )

    assert event.message_delta == "documented content"
    assert event.metadata["message_provenance"] == (
        "codex_app_server.userMessage.content"
    )


@pytest.mark.parametrize(
    ("content", "status", "unsupported", "malformed"),
    [
        ([{"type": "image", "imageUrl": "data:image/png;base64,AA"}], "unsupported", 1, 0),
        ({"type": "text", "text": "not a list"}, "malformed", 0, 0),
        ([{"type": "text", "text": 7}], "malformed", 0, 1),
        ([{"type": "text", "text": "bad\x00text"}], "malformed", 0, 1),
        ([], "empty", 0, 0),
    ],
)
def test_unsupported_or_malformed_content_never_fabricates_text(
    bound_codex: tuple[CodexAdapter, HarnessSession],
    content: object,
    status: str,
    unsupported: int,
    malformed: int,
) -> None:
    event = normalize(bound_codex, {"content": content, "text": "do not use me"})

    assert event.event_type == EventType.USER_PROMPT
    assert event.message_delta is None
    assert event.metadata["content_status"] == status
    assert event.metadata["unsupported_content_parts"] == unsupported
    assert event.metadata["malformed_content_parts"] == malformed


def test_oversized_text_is_an_exact_bounded_prefix_with_explicit_receipt(
    bound_codex: tuple[CodexAdapter, HarnessSession],
) -> None:
    raw = "x" * (MAX_ADAPTER_MESSAGE_CHARS + 17)
    event = normalize(
        bound_codex,
        {"content": [{"type": "text", "text": raw}]},
    )

    assert event.message_delta == raw[:MAX_ADAPTER_MESSAGE_CHARS]
    assert len(event.message_delta) == MAX_ADAPTER_MESSAGE_CHARS
    assert event.metadata["content_status"] == "truncated"
    assert event.metadata["content_truncated"] is True


def test_secret_text_is_redacted_with_an_explicit_receipt(
    bound_codex: tuple[CodexAdapter, HarnessSession],
) -> None:
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    event = normalize(
        bound_codex,
        {"content": [{"type": "text", "text": f"token {secret}"}]},
    )

    assert event.message_delta is not None
    assert secret not in event.message_delta
    assert event.metadata["content_status"] == "complete"
    assert event.metadata["content_redacted"] is True


@pytest.mark.parametrize("field", ["content", "text", "message"])
def test_prior_redaction_marker_cannot_claim_unmodified_human_input(bound_codex, field):
    text = "Override the constraint using [REDACTED:api_key]"
    item = {field: [{"type": "text", "text": text}] if field == "content" else text}
    event = normalize(bound_codex, item)
    assert event.message_delta == text
    assert event.metadata["content_redacted"] is True


def test_content_part_retention_bound_is_explicit(
    bound_codex: tuple[CodexAdapter, HarnessSession],
) -> None:
    event = normalize(
        bound_codex,
        {
            "content": [
                {"type": "text", "text": str(index % 10)}
                for index in range(129)
            ]
        },
    )

    assert event.message_delta == "".join(str(index % 10) for index in range(128))
    assert event.metadata["content_part_count"] == 129
    assert event.metadata["content_parts_observed"] == 128
    assert event.metadata["content_status"] == "truncated"
    assert event.metadata["content_truncated"] is True


def test_valid_text_is_preserved_when_another_part_is_malformed(
    bound_codex: tuple[CodexAdapter, HarnessSession],
) -> None:
    event = normalize(
        bound_codex,
        {
            "content": [
                {"type": "text", "text": "keep this"},
                {"type": "text", "text": "bad\x00part"},
            ]
        },
    )

    assert event.message_delta == "keep this"
    assert event.metadata["content_status"] == "partial_unsupported"
    assert event.metadata["malformed_content_parts"] == 1


@pytest.mark.parametrize("field", ["text", "message"])
def test_legacy_top_level_user_text_is_labeled_not_silently_conflated(
    bound_codex: tuple[CodexAdapter, HarnessSession],
    field: str,
) -> None:
    event = normalize(bound_codex, {field: "legacy text"})

    assert event.message_delta == "legacy text"
    assert event.metadata["content_status"] == "legacy_top_level"
    assert event.metadata["message_provenance"] == (
        f"codex_app_server.userMessage.{field}"
    )


def test_legacy_empty_text_still_falls_back_to_message(
    bound_codex: tuple[CodexAdapter, HarnessSession],
) -> None:
    event = normalize(bound_codex, {"text": "", "message": "legacy message"})

    assert event.message_delta == "legacy message"
    assert event.metadata["message_provenance"] == (
        "codex_app_server.userMessage.message"
    )


def test_agent_message_behavior_remains_unchanged(
    bound_codex: tuple[CodexAdapter, HarnessSession],
) -> None:
    adapter, session = bound_codex
    event = adapter.normalize_item(
        session,
        {"id": "agent-item", "type": "agentMessage", "text": "worker reply"},
    )

    assert event.event_type == EventType.AGENT_RESPONSE
    assert event.message_delta == "worker reply"
    assert event.metadata == {"raw_type": "agentMessage", "vendor_turn_id": None}
