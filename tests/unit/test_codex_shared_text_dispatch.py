from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from typing import Any
from uuid import uuid4

import pytest
from pex_bridge.adapters.codex_shared import (
    MAX_DISPATCH_TEXT_BYTES,
    CodexSharedAppServerTransport,
    SharedCodexDeliveryUncertainError,
    SharedCodexTextDispatchCancelled,
    SharedCodexTextDispatchRejected,
    SharedCodexTextDispatchRemoteError,
)
from pex_bridge.codex_received_journal import CodexReceivedJournal
from test_codex_shared_transport import MemoryAppServerChannel
from websockets.frames import Frame, Opcode


def make_transport(tmp_path, channel, *, request_timeout_s=1):
    executable, endpoint = tmp_path / "codex.exe", tmp_path / "codex.sock"
    executable.write_bytes(b"fake executable never run")
    endpoint.write_bytes(b"fake rendezvous never opened")
    journal = CodexReceivedJournal(
        tmp_path / "received.sqlite3",
        inspection_id=uuid4().hex,
        provenance={"requested_thread": "thr_exact", "fixture": True},
    )

    async def factory(argv):
        channel.argv = argv
        return channel

    return CodexSharedAppServerTransport(
        executable,
        endpoint,
        "thr_exact",
        channel_factory=factory,
        endpoint_validator=lambda _executable, _endpoint: None,
        connect_timeout_s=2,
        request_timeout_s=request_timeout_s,
        receive_journal=journal,
    )


class TextChannel(MemoryAppServerChannel):
    """Actual framed wire with a fake vendor; never opens a process or socket."""

    def __init__(self, *, response: dict[str, Any] | None = None) -> None:
        super().__init__(withhold={"turn/start", "turn/steer"})
        self.response = response
        self.written = asyncio.Event()
        self.hold_response = False
        self.hold_write = False
        self.release_write = asyncio.Event()
        self.hold_close = False
        self.close_entered = asyncio.Event()
        self.release_close = asyncio.Event()
        self.close_calls = 0

    async def write(self, data: bytes) -> None:
        before = len(self.messages)
        await super().write(data)
        for message in self.messages[before:]:
            if message.get("method") not in {"turn/start", "turn/steer"}:
                continue
            self.written.set()
            if self.hold_write:
                await self.release_write.wait()
            if self.hold_response:
                continue
            response = self.response
            if response is None:
                response = (
                    {"result": {"turn": {"id": "turn_new", "status": "inProgress", "items": []}}}
                    if message["method"] == "turn/start"
                    else {"result": {"turnId": message["params"]["expectedTurnId"]}}
                )
            await self.emit({"id": message["id"], **response})

    async def close(self) -> None:
        self.close_calls += 1
        self.close_entered.set()
        if self.hold_close:
            await self.release_close.wait()
        await super().close()


def dispatch_args(transport, **overrides):
    return {
        "thread_id": "thr_exact",
        "text": (
            "The public artifact has 27 rows; criterion 3 requires 30. Complete the missing rows."
        ),
        "client_user_message_id": "pex-effect-1",
        "expected_connection_token": transport.connection_token(),
        "expected_received_revision": transport.received_envelope_revision,
        "expected_received_chunk_revision": transport.received_chunk_revision,
        "expected_turn_id": None,
        "final_authority_check": lambda: None,
        **overrides,
    }


def writes(channel):
    return [m for m in channel.messages if m.get("method") in {"turn/start", "turn/steer"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("turn_id", [None, "turn_active"])
async def test_exact_start_and_steer_on_existing_framed_connection(tmp_path, turn_id):
    channel = TextChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    calls = []

    def authority():
        assert transport._protocol_lock.locked()
        calls.append("checked")

    args = dispatch_args(transport, expected_turn_id=turn_id, final_authority_check=authority)
    ack = await transport._dispatch_text(**args)
    try:
        assert calls == ["checked"]
        assert len(writes(channel)) == 1
        params = writes(channel)[0]["params"]
        assert params == {
            "threadId": "thr_exact",
            "clientUserMessageId": "pex-effect-1",
            "input": [{"type": "text", "text": args["text"], "text_elements": []}],
            **({"expectedTurnId": turn_id} if turn_id else {}),
        }
        assert ack.turn_id == (turn_id or "turn_new")
        assert ack.method == ("turn/steer" if turn_id else "turn/start")
        assert ack.thread_id == "thr_exact"
        assert ack.received_revision_at_write == args["expected_received_revision"]
        assert ack.received_revision_at_ack > ack.received_revision_at_write
        assert transport.shared_observe_only is True
        with pytest.raises(FrozenInstanceError):
            ack.turn_id = "changed"
        with pytest.raises(PermissionError):
            await transport.request("turn/start", params)
        assert len(writes(channel)) == 1
    finally:
        await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["uninitialized", "closed", "wrong_epoch", "wrong_endpoint"])
async def test_no_initialization_or_reconnect_for_dispatch(tmp_path, state):
    channel = TextChannel()
    transport = make_transport(tmp_path, channel)
    if state != "uninitialized":
        await transport.ensure_ready()
    args = dispatch_args(transport)
    if state == "closed":
        await transport.close()
    elif state == "wrong_epoch":
        args["expected_connection_token"] = (transport.endpoint_identity, 99)
    elif state == "wrong_endpoint":
        args["expected_connection_token"] = ("other-endpoint", transport.connection_generation)
    before = list(channel.messages)
    try:
        with pytest.raises(SharedCodexTextDispatchRejected):
            await transport._dispatch_text(**args)
        assert channel.messages == before
        assert not writes(channel)
    finally:
        await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [
    {"thread_id": "thr_other"},
    {"thread_id": " thr_exact"},
    {"text": ""},
    {"text": " \n"},
    {"text": "secret\x00"},
    {"text": "x" * (MAX_DISPATCH_TEXT_BYTES + 1)},
    {"text": "\ud800"},
    {"client_user_message_id": "\x00"},
    {"client_user_message_id": " leading"},
    {"expected_turn_id": ""},
    {"expected_turn_id": " trailing "},
    {"expected_received_revision": True},
    {"expected_connection_token": ("endpoint", True)},
    {"final_authority_check": None},
])
async def test_invalid_inputs_write_nothing(tmp_path, override):
    channel = TextChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    try:
        with pytest.raises(SharedCodexTextDispatchRejected):
            await transport._dispatch_text(**dispatch_args(transport, **override))
        assert not writes(channel)
        assert transport.initialized
    finally:
        await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["raises", "async", "false", "mutates_epoch", "mutates_revision"])
async def test_final_authority_is_mandatory_synchronous_and_rechecked(tmp_path, kind):
    channel = TextChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    async_entered = False

    async def asynchronous():
        nonlocal async_entered
        async_entered = True

    def authority():
        assert transport._protocol_lock.locked()
        if kind == "raises":
            raise ValueError("private authority detail")
        if kind == "async":
            return asynchronous()
        if kind == "false":
            return False
        if kind == "mutates_epoch":
            transport.connection_generation += 1
        if kind == "mutates_revision":
            transport._received_envelope_revision += 1
        return None

    try:
        with pytest.raises(SharedCodexTextDispatchRejected) as error:
            await transport._dispatch_text(
                **dispatch_args(transport, final_authority_check=authority)
            )
        assert "private authority detail" not in str(error.value)
        assert not writes(channel)
        assert not async_entered
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_decoded_ingress_advances_before_flush_or_writer_can_pass(tmp_path):
    channel = TextChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    args = dispatch_args(transport)
    original_flush = transport._flush
    reader_at_flush, release = asyncio.Event(), asyncio.Event()

    async def held_flush(websocket, owned_channel):
        if asyncio.current_task() is transport._reader_task:
            reader_at_flush.set()
            await release.wait()
        await original_flush(websocket, owned_channel)

    transport._flush = held_flush
    await channel.emit({"method": "unknown/newInput", "params": {}})
    await asyncio.wait_for(reader_at_flush.wait(), 1)
    assert transport.received_envelope_revision == args["expected_received_revision"] + 1
    assert transport.notifications[0]["method"] == "unknown/newInput"
    sending = asyncio.create_task(transport._dispatch_text(**args))
    try:
        await asyncio.sleep(0)
        assert not sending.done()
        release.set()
        with pytest.raises(SharedCodexTextDispatchRejected):
            await sending
        assert not writes(channel)
    finally:
        release.set()
        await asyncio.gather(sending, return_exceptions=True)
        await transport.close()


@pytest.mark.asyncio
async def test_revision_counts_complete_envelopes_responses_and_server_requests(tmp_path):
    channel = TextChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    assert transport.received_envelope_revision == 1
    channel.server.send_frame(Frame(Opcode.TEXT, b'{"method":"custom/notice",', fin=False))
    await channel._flush()
    async with asyncio.timeout(2):
        while transport.received_chunk_revision < 3 or not transport.receive_journal_ready:
            await asyncio.sleep(0.001)
    assert transport.received_envelope_revision == 1
    channel.server.send_frame(Frame(Opcode.CONT, b'"params":{}}', fin=True))
    await channel._flush()
    await channel.emit({"id": "approval", "method": "item/requestApproval", "params": {}})
    async with asyncio.timeout(2):
        while transport.received_envelope_revision < 3:
            await asyncio.sleep(0.001)
    assert transport.received_envelope_revision == 3
    await transport.request("thread/read", {"threadId": "thr_exact"})
    assert transport.received_envelope_revision == 4
    await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("response, turn_id", [
    ({"result": {"turnId": "wrong"}}, "turn_active"),
    ({"result": {"turnId": " turn_active "}}, "turn_active"),
    ({"result": {"turnId": "turn_active", "unexpected": True}}, "turn_active"),
    ({"result": {"turn": {"id": "", "status": "inProgress"}}}, None),
    ({"result": {"turn": {"id": " turn_new ", "status": "inProgress"}}}, None),
    ({"result": {"turn": {"id": "turn_new", "status": "completed"}}}, None),
    ({"result": {"turn": {"id": "turn_new", "status": "inProgress", "threadId": "other"}}}, None),
    ({"error": "not a JSON-RPC refusal"}, None),
    ({"error": {"code": True, "message": "bad"}}, None),
])
async def test_malformed_or_wrong_ack_is_uncertain_and_never_retried(tmp_path, response, turn_id):
    channel = TextChannel(response=response)
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    with pytest.raises(SharedCodexDeliveryUncertainError):
        await transport._dispatch_text(**dispatch_args(transport, expected_turn_id=turn_id))
    assert len(writes(channel)) == 1
    assert channel.closed
    assert not transport.initialized
    assert not transport._pending


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [-32600, -32603, -32000])
async def test_matching_returned_error_preserves_code_without_claiming_no_effect(tmp_path, code):
    channel = TextChannel(response={"error": {"code": code, "message": "private vendor detail"}})
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    try:
        with pytest.raises(SharedCodexTextDispatchRemoteError) as error:
            await transport._dispatch_text(
                **dispatch_args(transport, expected_turn_id="turn_active")
            )
        assert "private" not in str(error.value)
        assert error.value.code == code
        assert error.value.result_class == "returned_error"
        assert error.value.delivery_uncertain
        assert not transport.initialized
        assert channel.closed
        assert len(writes(channel)) == 1
        assert not transport._pending
    finally:
        await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("hold_write", [False, True])
async def test_post_enqueue_cancellation_owns_close_through_repeated_cancel(tmp_path, hold_write):
    channel = TextChannel()
    channel.hold_response = True
    channel.hold_write = hold_write
    channel.hold_close = True
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    sending = asyncio.create_task(transport._dispatch_text(**dispatch_args(transport)))
    try:
        await asyncio.wait_for(channel.written.wait(), 1)
        sending.cancel()
        await asyncio.wait_for(channel.close_entered.wait(), 1)
        assert not transport.initialized
        for _ in range(3):
            sending.cancel()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not sending.done()
        channel.release_close.set()
        with pytest.raises(SharedCodexTextDispatchCancelled) as error:
            await sending
        assert error.value.delivery_uncertain
        assert channel.closed
        assert channel.close_calls == 1
        assert len(writes(channel)) == 1
        assert not transport._pending
    finally:
        channel.release_write.set()
        channel.release_close.set()
        await asyncio.gather(sending, return_exceptions=True)
        await transport.close()


@pytest.mark.asyncio
async def test_timeout_after_write_is_unknown_and_settles_close(tmp_path):
    channel = TextChannel()
    channel.hold_response = True
    transport = make_transport(tmp_path, channel, request_timeout_s=0.1)
    await transport.ensure_ready()
    with pytest.raises(SharedCodexDeliveryUncertainError):
        await transport._dispatch_text(**dispatch_args(transport))
    assert channel.closed
    assert len(writes(channel)) == 1


@pytest.mark.asyncio
async def test_cancel_while_waiting_to_write_is_prewrite_and_keeps_connection(tmp_path):
    channel = TextChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    await transport._protocol_lock.acquire()
    sending = asyncio.create_task(transport._dispatch_text(**dispatch_args(transport)))
    try:
        await asyncio.sleep(0)
        sending.cancel()
        with pytest.raises(asyncio.CancelledError) as error:
            await sending
        assert not isinstance(error.value, SharedCodexTextDispatchCancelled)
        assert transport.initialized
        assert not writes(channel)
    finally:
        transport._protocol_lock.release()
        await asyncio.gather(sending, return_exceptions=True)
        await transport.close()


@pytest.mark.asyncio
async def test_same_snapshot_cannot_dispatch_twice_concurrently(tmp_path):
    channel = TextChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    args = dispatch_args(transport)
    results = await asyncio.gather(
        transport._dispatch_text(**args), transport._dispatch_text(**args), return_exceptions=True
    )
    assert sum(isinstance(result, SharedCodexTextDispatchRejected) for result in results) == 1
    assert len(writes(channel)) == 1
    await transport.close()


@pytest.mark.asyncio
async def test_write_failure_after_vendor_received_input_is_unknown(tmp_path):
    class FailingWrite(TextChannel):
        async def write(self, data):
            await super().write(data)
            if self.written.is_set():
                raise OSError("fixture write failed after peer receipt")

    channel = FailingWrite()
    channel.hold_response = True
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    with pytest.raises(SharedCodexDeliveryUncertainError):
        await transport._dispatch_text(**dispatch_args(transport))
    assert len(writes(channel)) == 1
    assert not transport.initialized
    assert channel.closed


@pytest.mark.asyncio
async def test_close_failure_does_not_relabel_unknown_as_successful_cleanup(tmp_path):
    class FailingClose(TextChannel):
        async def close(self):
            self.close_calls += 1
            raise OSError("fixture connector close failed")

    channel = FailingClose()
    channel.hold_response = True
    transport = make_transport(tmp_path, channel, request_timeout_s=0.1)
    await transport.ensure_ready()
    with pytest.raises(SharedCodexDeliveryUncertainError):
        await transport._dispatch_text(**dispatch_args(transport))
    assert channel.close_calls == 1
    assert not channel.closed
    assert not transport.initialized
    assert transport._channel is None
    assert not transport._pending
    # The fake failed close owns no OS resources. Explicitly settle its queue.
    await MemoryAppServerChannel.close(channel)


@pytest.mark.asyncio
async def test_authority_change_while_waiting_for_write_lock_is_rejected(tmp_path):
    channel = TextChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    active = True

    def authority():
        if not active:
            raise ValueError("paused before dispatch")

    await transport._protocol_lock.acquire()
    sending = asyncio.create_task(
        transport._dispatch_text(**dispatch_args(transport, final_authority_check=authority))
    )
    try:
        await asyncio.sleep(0)
        active = False
        transport._protocol_lock.release()
        with pytest.raises(SharedCodexTextDispatchRejected):
            await sending
        assert not writes(channel)
        assert transport.initialized
    finally:
        await asyncio.gather(sending, return_exceptions=True)
        await transport.close()


@pytest.mark.asyncio
async def test_timeout_before_write_is_rejection_not_unknown(tmp_path):
    channel = TextChannel()
    transport = make_transport(tmp_path, channel, request_timeout_s=0.1)
    await transport.ensure_ready()
    await transport._protocol_lock.acquire()
    try:
        with pytest.raises(SharedCodexTextDispatchRejected):
            await transport._dispatch_text(**dispatch_args(transport))
        assert not writes(channel)
        assert transport.initialized
    finally:
        transport._protocol_lock.release()
        await transport.close()


@pytest.mark.asyncio
async def test_dispatch_waits_for_channel_cleanup_claimed_by_concurrent_read(tmp_path):
    channel = TextChannel()
    channel.withhold.add("thread/read")
    channel.hold_response = True
    channel.hold_close = True
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    reading = asyncio.create_task(transport.request("thread/read", {"threadId": "thr_exact"}))
    for _ in range(40):
        if any(message["method"] == "thread/read" for message in channel.messages):
            break
        await asyncio.sleep(0)
    assert any(message["method"] == "thread/read" for message in channel.messages)
    sending = asyncio.create_task(transport._dispatch_text(**dispatch_args(transport)))
    try:
        await asyncio.wait_for(channel.written.wait(), 1)
        sending.cancel()
        await asyncio.wait_for(channel.close_entered.wait(), 1)
        for _ in range(10):
            await asyncio.sleep(0)
        assert not sending.done(), "dispatch returned while another close still owns its channel"
        channel.release_close.set()
        with pytest.raises(SharedCodexTextDispatchCancelled):
            await sending
        assert channel.closed
        assert channel.close_calls == 1
    finally:
        channel.release_close.set()
        await asyncio.gather(sending, reading, return_exceptions=True)
        await transport.close()


@pytest.mark.asyncio
async def test_concurrent_close_callers_settle_one_close_and_block_reopen(tmp_path):
    channel = TextChannel()
    channel.hold_close = True
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    first = asyncio.create_task(transport.close())
    await asyncio.wait_for(channel.close_entered.wait(), 1)
    second = asyncio.create_task(transport.close())
    try:
        await asyncio.sleep(0)  # Both close callers have entered and joined ownership.
        for _ in range(3):
            first.cancel()
            second.cancel()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not first.done()
            assert not second.done()
        assert not transport.initialized
        with pytest.raises(ConnectionError, match="cleanup is still in progress"):
            await transport.ensure_ready()
        assert [m["method"] for m in channel.messages].count("initialize") == 1
        channel.release_close.set()
        results = await asyncio.gather(first, second, return_exceptions=True)
        assert all(isinstance(result, asyncio.CancelledError) for result in results)
        assert channel.close_calls == 1
        assert channel.closed
        assert transport._close_task.done()
        replacement = TextChannel()

        async def factory(_argv):
            return replacement

        transport._channel_factory = factory
        assert await transport.ensure_ready() == {"serverInfo": {"name": "memory-codex"}}
        assert transport.initialized
        await transport.close()
        assert replacement.closed
    finally:
        channel.release_close.set()
        await asyncio.gather(first, second, return_exceptions=True)
        await transport.close()


@pytest.mark.asyncio
async def test_close_joins_reader_that_already_owns_channel_cleanup(tmp_path):
    channel = TextChannel()
    channel.hold_close = True
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    await channel.close_peer()
    await asyncio.wait_for(channel.close_entered.wait(), 1)
    closing = asyncio.create_task(transport.close())
    try:
        await asyncio.sleep(0)
        closing.cancel()
        await asyncio.sleep(0)
        assert not closing.done()
        channel.release_close.set()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert channel.closed
        assert channel.close_calls == 1
    finally:
        channel.release_close.set()
        await asyncio.gather(closing, return_exceptions=True)
        await transport.close()
