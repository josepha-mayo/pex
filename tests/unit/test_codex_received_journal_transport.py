from __future__ import annotations

import asyncio
import hashlib
import sqlite3
import threading
from contextlib import closing

import pytest
from pex_bridge.adapters.codex_shared import (
    SharedCodexDeliveryUncertainError,
    SharedCodexTextDispatchRejected,
)
from pex_bridge.codex_received_journal import CodexReceivedJournalError
from test_codex_shared_text_dispatch import TextChannel, dispatch_args, make_transport, writes
from test_codex_shared_transport import make_transport as make_observer_transport
from websockets.frames import Frame, Opcode


class RecordingChannel(TextChannel):
    def __init__(self):
        super().__init__()
        self.read_chunks: list[bytes] = []

    async def read(self, limit):
        data = await super().read(limit)
        if data:
            self.read_chunks.append(data)
        return data


def rows(transport):
    journal = transport._receive_journal
    with closing(sqlite3.connect(journal.path.as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute(
            "SELECT endpoint_identity, connection_generation, payload, payload_sha256 "
            "FROM received_chunks WHERE inspection_id=? ORDER BY sequence",
            (journal.inspection_id,),
        ).fetchall()


async def until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.002)


def assert_exact_committed_reads(transport, channel, generation):
    records = rows(transport)
    assert [record[2] for record in records] == channel.read_chunks
    assert all(record[0] == transport.endpoint_identity for record in records)
    assert all(record[1] == generation for record in records)
    assert all(record[3] == hashlib.sha256(record[2]).hexdigest() for record in records)


@pytest.mark.asyncio
async def test_upgrade_partial_and_malformed_wire_bytes_survive_protocol_failure(tmp_path):
    channel = RecordingChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    generation = transport.connection_generation
    try:
        assert channel.read_chunks[0].startswith(b"HTTP/1.1 101")
        channel.server.send_frame(Frame(Opcode.TEXT, b'{"method":"new/notice",', fin=False))
        await channel._flush()
        await until(
            lambda: transport.received_chunk_revision == 3 and transport.receive_journal_ready
        )
        assert transport.received_envelope_revision == 1
        channel.server.send_frame(Frame(Opcode.CONT, b'"params":{}}', fin=True))
        await channel._flush()
        await until(lambda: len(transport.notifications) == 1)
        channel.server.send_text(b'{"method":"broken", "params":not-json}')
        await channel._flush()
        await until(lambda: not transport.initialized)
        await transport.close()
        assert_exact_committed_reads(transport, channel, generation)
        assert b"not-json" in b"".join(record[2] for record in rows(transport))
        assert transport.notifications == []
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_received_human_notification_survives_held_ack_timeout_and_queue_clear(tmp_path):
    channel = RecordingChannel()
    channel.hold_response = True
    transport = make_transport(tmp_path, channel, request_timeout_s=1)
    await transport.ensure_ready()
    generation = transport.connection_generation
    sending = asyncio.create_task(transport._dispatch_text(**dispatch_args(transport)))
    try:
        await asyncio.wait_for(channel.written.wait(), 2)
        await channel.emit({
            "method": "item/completed",
            "params": {"threadId": "thr_exact", "turnId": "turn_human", "item": {
                "id": "human-1", "type": "userMessage", "content": [
                    {"type": "text", "text": "new human goal", "text_elements": []}
                ]
            }},
        })
        await until(lambda: len(transport.notifications) == 1)
        assert b"new human goal" in b"".join(record[2] for record in rows(transport))
        with pytest.raises(SharedCodexDeliveryUncertainError):
            await sending
        assert transport.notifications == []
        assert_exact_committed_reads(transport, channel, generation)
        assert len(writes(channel)) == 1
    finally:
        await asyncio.gather(sending, return_exceptions=True)
        await transport.close()


@pytest.mark.asyncio
async def test_no_journal_observer_stays_available_but_cannot_dispatch(tmp_path):
    channel = RecordingChannel()
    transport = make_observer_transport(tmp_path, channel)
    await transport.ensure_ready()
    try:
        assert await transport.request("thread/read", {"threadId": "thr_exact"})
        with pytest.raises(SharedCodexTextDispatchRejected):
            await transport._dispatch_text(**dispatch_args(transport))
        assert transport.initialized
        assert not writes(channel)
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_partial_chunk_revokes_snapshot_without_complete_envelope(tmp_path):
    channel = RecordingChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    args = dispatch_args(transport)
    try:
        # Even an incomplete WebSocket header is retained; no JSON event exists.
        channel.server.send_frame(Frame(Opcode.TEXT, b'{"method":"new/input"}', fin=True))
        frame = b"".join(channel.server.data_to_send())
        await channel.incoming.put(frame[:1])
        await until(
            lambda: transport.received_chunk_revision == 3 and transport.receive_journal_ready
        )
        assert transport.received_envelope_revision == args["expected_received_revision"]
        with pytest.raises(SharedCodexTextDispatchRejected):
            await transport._dispatch_text(**args)
        assert not writes(channel)
        assert rows(transport)[-1][2] == frame[:1]
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_pending_chunk_blocks_queued_writer_before_journal_lock_acquisition(tmp_path):
    channel = RecordingChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    args = dispatch_args(transport)
    await transport._protocol_lock.acquire()
    sending = asyncio.create_task(transport._dispatch_text(**args))
    await asyncio.sleep(0)  # Writer enters lock queue before reader.
    try:
        await channel.emit({"method": "custom/newInput", "params": {}})
        await until(lambda: transport._receive_pending == 1)
        assert not transport.receive_journal_ready
        transport._protocol_lock.release()
        with pytest.raises(SharedCodexTextDispatchRejected):
            await sending
        await until(lambda: transport.receive_journal_ready)
        assert not writes(channel)
    finally:
        if transport._protocol_lock.locked() and not transport._receive_pending:
            transport._protocol_lock.release()
        await asyncio.gather(sending, return_exceptions=True)
        await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["upgrade", "stream"])
async def test_append_failure_prevents_parse_and_permanently_refuses_reopen(tmp_path, phase):
    channel = RecordingChannel()
    transport = make_transport(tmp_path, channel)
    journal = transport._receive_journal
    if phase == "stream":
        await transport.ensure_ready()
    calls = 0

    def fail(*_args):
        nonlocal calls
        calls += 1
        raise OSError("fixture disk unavailable")

    journal._append = fail
    try:
        if phase == "upgrade":
            with pytest.raises(CodexReceivedJournalError):
                await transport.ensure_ready()
        else:
            await channel.emit({"method": "thread/status/changed", "params": {"status": {}}})
            await until(lambda: not transport.initialized)
        assert not journal.healthy
        assert transport.notifications == []
        assert calls == 1
        with pytest.raises(CodexReceivedJournalError):
            await transport.ensure_ready()
        with pytest.raises(SharedCodexTextDispatchRejected):
            await transport._dispatch_text(**dispatch_args(transport))
        assert calls == 1
        assert not writes(channel)
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_cancel_during_single_append_settles_commit_without_routing_old_epoch(tmp_path):
    channel = RecordingChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    journal = transport._receive_journal
    generation = transport.connection_generation
    original = journal._append
    entered, release = threading.Event(), threading.Event()
    calls = 0

    def held(*args):
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(5), "test must release owned append"
        original(*args)

    journal._append = held
    await channel.emit({"method": "custom/retained", "params": {"private": "raw-only"}})
    assert await asyncio.to_thread(entered.wait, 3)
    closing_task = asyncio.create_task(transport.close())
    try:
        for _ in range(3):
            await asyncio.sleep(0)
            closing_task.cancel()
            await asyncio.sleep(0)
            assert not closing_task.done()
        assert transport.notifications == []
        release.set()
        await asyncio.gather(closing_task, return_exceptions=True)
        assert_exact_committed_reads(transport, channel, generation)
        assert not transport.receive_journal_ready
        assert not journal.healthy
        assert calls == 1
        assert transport.notifications == []
        with pytest.raises(CodexReceivedJournalError):
            await transport.ensure_ready()
    finally:
        release.set()
        await asyncio.gather(closing_task, return_exceptions=True)
        await transport.close()


@pytest.mark.asyncio
async def test_cancel_before_append_lock_still_commits_returned_bytes_once(tmp_path):
    channel = RecordingChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    generation = transport.connection_generation
    await transport._protocol_lock.acquire()
    await channel.emit({"method": "custom/heldBeforeAppend", "params": {}})
    await until(lambda: transport._receive_pending == 1)
    closing_task = asyncio.create_task(transport.close())
    try:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not closing_task.done()
        transport._protocol_lock.release()
        await closing_task
        assert transport.notifications == []
        assert_exact_committed_reads(transport, channel, generation)
        assert len(rows(transport)) == 3
        assert not transport.receive_journal_ready
        with pytest.raises(CodexReceivedJournalError):
            await transport.ensure_ready()
    finally:
        if transport._protocol_lock.locked() and not transport._receive_pending:
            transport._protocol_lock.release()
        await asyncio.gather(closing_task, return_exceptions=True)
        await transport.close()
