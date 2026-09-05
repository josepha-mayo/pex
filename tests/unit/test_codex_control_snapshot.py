from __future__ import annotations

import asyncio
import hashlib
import time
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import pytest
from pex_bridge.adapters.codex_shared import SharedCodexReadSnapshot
from pex_bridge.adapters.codex_subscription import (
    CodexExistingThreadSubscription,
    CodexSubscriptionError,
)
from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads
from test_codex_subscription import FakeSharedTransport, _authorization, _inspect, _thread_response


def turn(status="completed"):
    return {
        "id": "turn-1", "status": status, "itemsView": "full",
        "items": [{"id": "human-1", "type": "userMessage", "clientId": None,
                   "content": [{"type": "text", "text": "Finish the actual report."}]}],
    }


async def setup(tmp_path):
    response = _thread_response(tmp_path, turns=[turn()])
    transport = FakeSharedTransport(
        [response, response, response], _thread_response(tmp_path, include_turns=False),
    )
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)
    await coordinator.subscribe(selected, _authorization(selected))
    return coordinator, transport, response


def witnessed(transport, response):
    return SharedCodexReadSnapshot(
        strict_json_dumps(response), transport.connection_token(), 10, 12, time.monotonic(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("active", [False, True])
async def test_explicit_idle_and_active_freeze_identity_inputs_without_drain(tmp_path, active):
    coordinator, transport, response = await setup(tmp_path)
    response["thread"]["turns"][0]["status"] = "inProgress" if active else "completed"
    status = {"type": "active", "activeFlags": []} if active else {"type": "idle"}
    response["status"] = response["thread"]["status"] = status
    original_state = coordinator.state
    transport.notifications.append({"retained": "not drained from action"})
    calls = []

    async def read():
        calls.append("fresh")
        return witnessed(transport, response)

    transport.read_current_thread = read
    result = await asyncio.wait_for(coordinator.refresh_control_snapshot(), 1)
    assert calls == ["fresh"]
    assert result.active_turn_id == ("turn-1" if active else None)
    assert result.receipt == original_state.receipt
    assert coordinator.state is original_state
    assert transport.notifications == [{"retained": "not drained from action"}]
    assert result.user_inputs_digest == hashlib.sha256(result.user_inputs_json.encode()).hexdigest()
    assert strict_json_loads(result.user_inputs_json)[0]["item_id"] == "human-1"
    with pytest.raises(FrozenInstanceError):
        result.active_turn_id = "other"
    response["thread"]["turns"][0]["items"][0]["content"][0]["text"] = "new human intent"
    newer = await coordinator.refresh_control_snapshot()
    assert newer.user_inputs_digest != result.user_inputs_digest
    assert "new human intent" not in result.user_inputs_json


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [
    "cwd", "model", "project", "thread", "root", "direct", "direct_missing",
    "not_loaded", "unknown_status", "missing_flags", "approval", "unknown_flag",
    "idle_with_active", "active_without_turn", "two_active", "summary", "no_items",
    "turn_truncated", "unknown_turn", "missing_client", "client_boolean",
    "content_missing", "image", "partial", "redacted", "empty", "item_truncated",
    "wrong_epoch", "epoch_during_read", "inactive", "unknown_item", "empty_item_type",
])
async def test_uncertain_identity_runtime_or_input_refuses_control(tmp_path, case):
    coordinator, transport, response = await setup(tmp_path)
    thread = response["thread"]
    current_turn = thread["turns"][0]
    item = current_turn["items"][0]
    identity_fields = {
        "cwd": ("cwd", str(tmp_path / "other")), "model": ("model", "other-model"),
        "project": ("projectId", "other-project"), "root": ("sessionId", "other-root"),
        "direct": ("canAcceptDirectInput", False),
    }
    if case in identity_fields:
        key, value = identity_fields[case]
        response[key] = thread[key] = value
    elif case == "thread":
        thread["id"] = "other-thread"
    elif case == "direct_missing":
        del response["canAcceptDirectInput"], thread["canAcceptDirectInput"]
    elif case in {"not_loaded", "unknown_status", "missing_flags", "approval",
                  "unknown_flag", "active_without_turn", "two_active"}:
        status = {"type": "active", "activeFlags": []}
        if case == "not_loaded":
            status = {"type": "notLoaded"}
        elif case == "unknown_status":
            status = {"type": "future"}
        elif case == "missing_flags":
            status = {"type": "active"}
        elif case in {"approval", "unknown_flag"}:
            status["activeFlags"] = ["waitingOnApproval" if case == "approval" else "future"]
        if case != "active_without_turn":
            current_turn["status"] = "inProgress"
        if case == "two_active":
            another = deepcopy(current_turn)
            another["id"] = "turn-2"
            thread["turns"].append(another)
        response["status"] = thread["status"] = status
    elif case == "idle_with_active":
        current_turn["status"] = "inProgress"
    elif case == "summary":
        current_turn["itemsView"] = "summary"
    elif case == "no_items":
        del current_turn["items"]
    elif case == "turn_truncated":
        current_turn["hasMore"] = True
    elif case == "unknown_turn":
        current_turn["status"] = "future"
    elif case == "missing_client":
        del item["clientId"]
    elif case == "client_boolean":
        item["clientId"] = False
    elif case == "content_missing":
        del item["content"]
    elif case == "image":
        item["content"].append({"type": "image", "url": "data:image/png;base64,abc"})
    elif case == "partial":
        item["content"][0]["truncated"] = True
    elif case == "redacted":
        item["content"][0]["text"] = "[REDACTED:secret]"
    elif case == "empty":
        item["content"] = []
    elif case == "item_truncated":
        item["hasMore"] = True
    elif case in {"unknown_item", "empty_item_type"}:
        item["type"] = "futureUserInput" if case == "unknown_item" else ""
    elif case == "inactive":
        coordinator._state = replace(coordinator.state, active=False)

    async def read():
        result = witnessed(transport, response)
        if case == "wrong_epoch":
            result = replace(result, connection_token=(transport.endpoint_identity, 99))
        if case == "epoch_during_read":
            transport.connection_generation += 1
        return result

    transport.read_current_thread = read
    before = list(transport.calls)
    with pytest.raises(CodexSubscriptionError):
        await asyncio.wait_for(coordinator.refresh_control_snapshot(), 1)
    assert transport.calls == before
