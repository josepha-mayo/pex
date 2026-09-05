from __future__ import annotations

import asyncio
import time
from dataclasses import FrozenInstanceError

import pytest
from pex_bridge.adapters.codex_shared import (
    SharedCodexDeliveryUncertainError,
    SharedCodexTextDispatchRejected,
    _BoundaryClientProtocol,
)
from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads
from test_codex_shared_text_dispatch import (
    TextChannel,
    dispatch_args,
    make_transport,
    writes,
)
from test_codex_shared_transport import make_transport as make_unjournaled_transport
from websockets.frames import Frame, Opcode
from websockets.uri import parse_uri
from websockets.utils import accept_key


def encoded_frame(value):
    return Frame(Opcode.TEXT, strict_json_dumps(value).encode()).serialize(mask=False)


def notification():
    return {
        "method": "item/completed",
        "params": {
            "threadId": "thr_exact",
            "turnId": "human-turn",
            "item": {"id": "human-input", "type": "userMessage", "content": []},
        },
    }


class SnapshotChannel(TextChannel):
    """Framed fake peer with precise response/suffix chunk ownership."""

    def __init__(self, *, suffix=b"", hold_read=False):
        super().__init__()
        self.withhold.add("thread/read")
        self.suffix = suffix
        self.hold_read = hold_read
        self.read_written = asyncio.Event()
        self.result = {"thread": {"id": "thr_exact", "turns": []}}

    async def write(self, data):
        before = len(self.messages)
        await super().write(data)
        for message in self.messages[before:]:
            if message.get("method") != "thread/read":
                continue
            self.read_written.set()
            if not self.hold_read:
                await self.incoming.put(
                    encoded_frame({"id": message["id"], "result": self.result})
                    + self.suffix
                )


async def feed_settled(transport, channel, data):
    previous = transport.received_chunk_revision
    chunks = (len(data) + 65_535) // 65_536
    await channel.incoming.put(data)

    async def settle():
        while transport.received_chunk_revision < previous + chunks:
            await asyncio.sleep(0)
        async with transport._protocol_lock:
            pass

    await asyncio.wait_for(settle(), timeout=2)


@pytest.mark.asyncio
async def test_read_captures_immutable_exact_response_without_draining_notifications(tmp_path):
    channel = SnapshotChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    try:
        await feed_settled(transport, channel, encoded_frame(notification()))
        before_time = time.monotonic()
        snapshot = await transport.read_current_thread()
        assert before_time <= snapshot.observed_at_monotonic <= time.monotonic()
        assert strict_json_loads(snapshot.result_json) == channel.result
        assert snapshot.connection_token == transport.connection_token()
        assert snapshot.received_envelope_revision == transport.received_envelope_revision
        assert snapshot.received_chunk_revision == transport.received_chunk_revision
        assert transport.receive_protocol_complete
        with pytest.raises(FrozenInstanceError):
            snapshot.result_json = "{}"
        decoded = strict_json_loads(snapshot.result_json)
        decoded["thread"]["id"] = "changed"
        assert strict_json_loads(snapshot.result_json)["thread"]["id"] == "thr_exact"
        assert len(transport.drain_notifications()) == 1
        assert [m for m in channel.messages if m.get("method") == "thread/read"] == [{
            "id": 2,
            "method": "thread/read",
            "params": {"threadId": "thr_exact", "includeTurns": True},
        }]
        assert not transport._read_captures
        assert not writes(channel)
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_new_notification_after_response_in_same_chunk_invalidates_snapshot(tmp_path):
    channel = SnapshotChannel(suffix=encoded_frame(notification()))
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    try:
        with pytest.raises(SharedCodexTextDispatchRejected, match="superseded"):
            await transport.read_current_thread()
        assert transport.receive_protocol_complete
        assert len(transport.drain_notifications()) == 1
        assert not transport._read_captures
        assert not writes(channel)
    finally:
        await transport.close()


def incomplete_suffix(kind):
    message = encoded_frame(notification())
    if kind == "one-header-byte":
        return message[:1], message[1:]
    if kind == "consumed-header":
        return message[:2], message[2:]
    if kind == "extended-header":
        return message[:3], message[3:]
    if kind == "extended-64-bit-header":
        # Large wire envelope, small bounded parsed observation. The whitespace
        # keeps this test about framing, not oversized notification metadata.
        body = strict_json_dumps(notification()).encode() + b" " * 65_536
        message = Frame(Opcode.TEXT, body).serialize(mask=False)
        assert message[1] == 127
        return message[:9], message[9:]
    if kind == "payload":
        return message[:-1], message[-1:]
    if kind == "empty-fragment":
        return (
            Frame(Opcode.TEXT, b"", fin=False).serialize(mask=False),
            Frame(Opcode.CONT, strict_json_dumps(notification()).encode()).serialize(mask=False),
        )
    if kind == "fragment-and-ping":
        body = strict_json_dumps(notification()).encode()
        return (
            Frame(Opcode.TEXT, body[:4], fin=False).serialize(mask=False)
            + Frame(Opcode.PING, b"ping").serialize(mask=False),
            Frame(Opcode.CONT, body[4:]).serialize(mask=False),
        )
    raise AssertionError(kind)


INCOMPLETE_KINDS = [
    "one-header-byte", "consumed-header", "extended-header", "extended-64-bit-header", "payload",
    "empty-fragment", "fragment-and-ping",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", INCOMPLETE_KINDS)
async def test_response_followed_by_incomplete_message_refuses_snapshot(tmp_path, kind):
    prefix, remainder = incomplete_suffix(kind)
    channel = SnapshotChannel(suffix=prefix)
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    try:
        with pytest.raises(SharedCodexTextDispatchRejected, match="superseded"):
            await transport.read_current_thread()
        assert not transport.receive_protocol_complete
        assert not transport._read_captures
        await feed_settled(transport, channel, remainder)
        assert transport.receive_protocol_complete
        assert len(transport.drain_notifications()) == 1
        channel.suffix = b""
        recovered = await transport.read_current_thread()
        assert strict_json_loads(recovered.result_json) == channel.result
        assert not writes(channel)
    finally:
        await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", INCOMPLETE_KINDS)
async def test_already_incomplete_message_refuses_read_and_dispatch_without_write(tmp_path, kind):
    prefix, remainder = incomplete_suffix(kind)
    channel = SnapshotChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    try:
        await feed_settled(transport, channel, prefix)
        assert not transport.receive_protocol_complete
        before = list(channel.messages)
        with pytest.raises(SharedCodexTextDispatchRejected, match="unavailable"):
            await transport.read_current_thread()
        with pytest.raises(SharedCodexTextDispatchRejected):
            await transport._dispatch_text(**dispatch_args(transport))
        assert channel.messages == before
        assert not transport._read_captures
        await feed_settled(transport, channel, remainder)
        assert transport.receive_protocol_complete
        snapshot = await transport.read_current_thread()
        ack = await transport._dispatch_text(**dispatch_args(
            transport,
            expected_received_revision=snapshot.received_envelope_revision,
            expected_received_chunk_revision=snapshot.received_chunk_revision,
        ))
        assert ack.turn_id == "turn_new"
        assert len(writes(channel)) == 1
    finally:
        await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["uninitialized", "closed", "no-journal"])
async def test_read_does_not_initialize_reconnect_or_bypass_missing_journal(tmp_path, state):
    channel = SnapshotChannel()
    factory = make_unjournaled_transport if state == "no-journal" else make_transport
    transport = factory(tmp_path, channel)
    if state != "uninitialized":
        await transport.ensure_ready()
    if state == "closed":
        await transport.close()
    before = list(channel.messages)
    token = transport.connection_token()
    try:
        with pytest.raises(SharedCodexTextDispatchRejected, match="unavailable"):
            await transport.read_current_thread()
        assert transport.connection_token() == token
        assert channel.messages == before
        assert not transport._read_captures
    finally:
        await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["epoch", "endpoint"])
async def test_identity_change_while_read_is_outstanding_rejects_snapshot(tmp_path, change):
    channel = SnapshotChannel(hold_read=True)
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    task = asyncio.create_task(transport.read_current_thread())
    try:
        await asyncio.wait_for(channel.read_written.wait(), timeout=2)
        if change == "epoch":
            transport.connection_generation += 1
        else:
            transport.endpoint_identity = "replacement-endpoint"
        await channel.emit({"id": channel.messages[-1]["id"], "result": channel.result})
        with pytest.raises((SharedCodexTextDispatchRejected, SharedCodexDeliveryUncertainError)):
            await asyncio.wait_for(task, timeout=2)
        assert not transport._read_captures
        assert not writes(channel)
    finally:
        await transport.close()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_read_settles_owned_close_and_cleans_capture(tmp_path):
    channel = SnapshotChannel(hold_read=True)
    channel.hold_close = True
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    task = asyncio.create_task(transport.read_current_thread())
    try:
        await asyncio.wait_for(channel.read_written.wait(), timeout=2)
        assert len(transport._read_captures) == 1
        task.cancel()
        await asyncio.wait_for(channel.close_entered.wait(), timeout=2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        channel.release_close.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)
        assert channel.close_calls == 1
        assert channel.closed
        assert not transport.initialized
        assert not transport._read_captures
        assert not transport._pending
        assert not writes(channel)
    finally:
        channel.release_close.set()
        await transport.close()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_complete_ping_after_response_does_not_invent_new_input(tmp_path):
    channel = SnapshotChannel(suffix=Frame(Opcode.PING, b"ping").serialize(mask=False))
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    try:
        snapshot = await transport.read_current_thread()
        assert snapshot.received_envelope_revision == transport.received_envelope_revision
        assert transport.receive_protocol_complete
        assert not transport.drain_notifications()
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_cancellation_while_final_read_witness_waits_for_protocol_lock_cleans_capture(
    tmp_path, monkeypatch,
):
    channel = SnapshotChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    flush_entered = asyncio.Event()
    release_flush = asyncio.Event()
    original_flush = transport._flush

    async def held_response_flush(websocket, connection):
        if any(transport._read_captures.values()):
            flush_entered.set()
            await release_flush.wait()
        await original_flush(websocket, connection)

    monkeypatch.setattr(transport, "_flush", held_response_flush)
    task = asyncio.create_task(transport.read_current_thread())
    try:
        await asyncio.wait_for(flush_entered.wait(), timeout=2)
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)
        assert not transport._read_captures
        assert not transport._pending
        assert not writes(channel)
        release_flush.set()
        async with transport._protocol_lock:
            pass
        assert transport.receive_protocol_complete
    finally:
        release_flush.set()
        await transport.close()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("payload_size", [5, 126, 65_536])
@pytest.mark.parametrize("split", [1, 2, 3, 4, -1])
def test_upgrade_suffix_and_consumed_frame_headers_preserve_exact_boundary(payload_size, split):
    # Exercise the installed parser itself, including upgrade + partial-frame
    # bytes in a single read. No sockets, subprocesses, or provider involvement.
    websocket = _BoundaryClientProtocol(parse_uri("ws://localhost/rpc"))
    request = websocket.connect()
    upgrade = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept_key(request.headers['Sec-WebSocket-Key'])}\r\n\r\n"
    ).encode()
    frame = Frame(Opcode.TEXT, b"x" * payload_size).serialize(mask=False)
    websocket.receive_data(upgrade + frame[:split])
    assert not websocket.at_complete_boundary
    assert websocket._complete_boundary == len(upgrade)
    assert websocket._fed_bytes == len(upgrade + frame[:split])
    websocket.receive_data(frame[split:])
    assert websocket.at_complete_boundary
    assert websocket._complete_boundary == len(upgrade + frame)
