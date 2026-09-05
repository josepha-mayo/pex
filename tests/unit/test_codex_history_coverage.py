"""Malformed top-level coverage must not disappear into a complete selected seed."""

import pytest
from pex_bridge.adapters.codex_subscription import (
    CodexExistingThreadSubscription,
    CodexSubscriptionError,
)
from test_codex_subscription import FakeSharedTransport, _inspect, _thread_response


@pytest.mark.parametrize("level", ["response", "thread"])
@pytest.mark.parametrize("field", ["truncated", "hasMore", "has_more", "redacted"])
@pytest.mark.parametrize("value", [True, 1, 0, "false", None, [], {}])
async def test_ambiguous_coverage_cannot_be_discarded_before_selection(
    tmp_path, level, field, value,
):
    response = _thread_response(tmp_path)
    target = response if level == "response" else response["thread"]
    target[field] = value
    coordinator = CodexExistingThreadSubscription(FakeSharedTransport([response], {}))
    with pytest.raises(CodexSubscriptionError, match="truncated"):
        await _inspect(coordinator, tmp_path)


@pytest.mark.parametrize("level", ["response", "thread"])
@pytest.mark.parametrize("value", ["partial", "redacted", None, 1])
async def test_explicit_incomplete_content_status_is_not_lost(tmp_path, level, value):
    response = _thread_response(tmp_path)
    target = response if level == "response" else response["thread"]
    target["content_status"] = value
    coordinator = CodexExistingThreadSubscription(FakeSharedTransport([response], {}))
    with pytest.raises(CodexSubscriptionError, match="truncated"):
        await _inspect(coordinator, tmp_path)


@pytest.mark.parametrize("level", ["response", "thread"])
async def test_explicit_complete_coverage_remains_selectable(tmp_path, level):
    response = _thread_response(tmp_path)
    target = response if level == "response" else response["thread"]
    target.update(
        truncated=False, hasMore=False, has_more=False, redacted=False,
        nextCursor=None, next_cursor="", content_status="complete",
    )
    coordinator = CodexExistingThreadSubscription(FakeSharedTransport([response], {}))
    selected = await _inspect(coordinator, tmp_path)
    assert selected.history_mode == "includeTurns"
    assert selected.history_records == ()
