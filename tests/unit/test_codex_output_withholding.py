from __future__ import annotations

import copy
import hashlib

import pytest
from pex_bridge.adapters.codex import CodexAdapter
from pex_bridge.adapters.codex_output import (
    OUTPUT_WITHHELD_KEY,
    OUTPUT_WITHHELD_NOTICE,
    bounded_shared_command_params,
    command_output_is_withheld,
)
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.session import HarnessSession
from test_codex_received_journal_transport import (
    RecordingChannel,
    assert_exact_committed_reads,
    rows,
    until,
)
from test_codex_shared_text_dispatch import make_transport
from test_codex_shared_transport import make_transport as make_unjournaled_transport
from test_codex_subscription import _notification, _subscribed


def command_message():
    return {
        "method": "item/completed",
        "params": {
            "threadId": "thr_exact", "turnId": "turn_exact",
            "item": {
                "id": "cmd_exact", "type": "commandExecution",
                "command": "pytest -q", "cwd": "C:/proj", "status": "completed",
                "exitCode": 0, "aggregatedOutput": "x" * 58_000 + "\n4 passed\n",
            },
        },
    }


def prepare(message):
    return bounded_shared_command_params(
        message, thread_id="thr_exact", received_bytes_journaled=True,
    )


def test_withholding_is_deterministic_and_never_infers_pytest_success():
    message = command_message()
    original = copy.deepcopy(message)
    params = prepare(message)
    assert params == prepare(message)
    assert message == original
    item = params["item"]
    assert command_output_is_withheld(item)
    output = original["params"]["item"]["aggregatedOutput"]
    assert item[OUTPUT_WITHHELD_KEY]["characters"] == len(output)
    assert item[OUTPUT_WITHHELD_KEY]["sha256"] == hashlib.sha256(output.encode()).hexdigest()
    assert item["aggregatedOutput"] == OUTPUT_WITHHELD_NOTICE
    session = HarnessSession(
        id="codex:thr_exact", harness_type=HarnessType.CODEX,
        vendor_session_id="thr_exact", status=SessionStatus.WORKING,
        cwd="C:/proj", project_id="C:/proj",
    )
    adapter = CodexAdapter()
    adapter.sessions[session.id] = session
    event = adapter.normalize_item(session, item, vendor_turn_id="turn_exact")
    assert event.event_type == EventType.SHELL
    assert event.message_delta is None
    assert event.process_state == {"pytest_unavailable_reason": "output_exceeds_bound"}


@pytest.mark.parametrize(("where", "key", "value"), [
    ("message", "id", None), ("message", "jsonrpc", "1.0"),
    ("message", "method", "item/commandExecution/requestApproval"),
    ("message", "method", {}), ("params", "threadId", "foreign"),
    ("params", "turnId", " turn_exact"), ("params", "itemId", "other"),
    ("params", "turn", {"id": "turn_exact"}),
    ("item", "itemId", "other"), ("item", "threadId", "foreign"),
    ("item", "turnId", "other"), ("item", "id", "cmd_exact "),
    ("item", "status", []), ("item", "type", "agentMessage"),
    ("item", "command", "x" * 32769), ("item", "pex_output_fake", True),
    ("item", "aggregatedOutput", "x" * 32769 + "\x00"),
    ("item", "aggregatedOutput", "x" * 32769 + "\ud800"),
], ids=[f"invalid-{index}" for index in range(18)])
def test_oversized_rewrite_rejects_ambiguous_or_unbounded_fields(where, key, value):
    message = command_message()
    target = {"message": message, "params": message["params"],
              "item": message["params"]["item"]}[where]
    target[key] = value
    assert prepare(message) is None


def test_no_journal_proof_and_vendor_marker_are_rejected():
    message = command_message()
    assert bounded_shared_command_params(message, thread_id="thr_exact") is None
    message["params"] = prepare(message)
    assert prepare(message) is None


def test_small_output_unchanged():
    message = command_message()
    message["params"]["item"]["aggregatedOutput"] = "4 passed"
    assert prepare(message) == message["params"]
    assert not command_output_is_withheld(message["params"]["item"])


@pytest.mark.asyncio
async def test_fragmented_output_is_committed_before_notice_and_stop_survives(tmp_path):
    channel = RecordingChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    generation = transport.connection_generation
    try:
        message = command_message()
        await channel.emit(message, fragmented=True)
        await until(lambda: len(transport.notifications) == 1)
        assert_exact_committed_reads(transport, channel, generation)
        assert b"x" * 1000 in b"".join(row[2] for row in rows(transport))
        assert transport.notifications[0]["params"] == prepare(message)
        await channel.emit({"method": "turn/completed", "params": {
            "threadId": "thr_exact", "turn": {"id": "turn_exact", "status": "completed"},
        }})
        await until(lambda: len(transport.notifications) == 2)
        assert transport.initialized
        assert transport.notifications[1]["method"] == "turn/completed"
        assert not any(m.get("method") in {"turn/start", "turn/steer"} for m in channel.messages)
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_unjournaled_transport_does_not_silently_withhold_output(tmp_path):
    channel = RecordingChannel()
    transport = make_unjournaled_transport(tmp_path, channel)
    await transport.ensure_ready()
    try:
        await channel.emit(command_message(), fragmented=True)
        await until(lambda: not transport.initialized)
        assert transport.notifications == []
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_withheld_duplicate_coalesces_without_losing_stop_watermark(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    message = command_message()
    message["params"]["threadId"] = "thread-1"
    params = bounded_shared_command_params(
        message, thread_id="thread-1", received_bytes_journaled=True,
    )
    completed = _notification("item/completed", params)
    transport.notifications.extend([
        _notification("turn/started", {
            "threadId": "thread-1", "turn": {"id": "turn_exact"},
        }),
        completed, copy.deepcopy(completed),
        _notification("turn/completed", {
            "threadId": "thread-1", "turn": {"id": "turn_exact"},
        }),
    ])
    batch = await coordinator.drain_live()
    assert batch.live_watermark == 3
    assert [record.method for record in batch.records] == [
        "turn/started", "item/completed", "turn/completed",
    ]
    assert coordinator.state.active
