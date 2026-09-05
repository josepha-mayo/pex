from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sqlite3
import threading
from datetime import datetime

import pytest
from pex_bridge.codex_received_journal import CodexReceivedJournal, CodexReceivedJournalError

ENDPOINT = "e" * 64
ATTEMPT = "a" * 32


def make_journal(tmp_path, *, attempt=ATTEMPT, provenance=None):
    return CodexReceivedJournal(
        tmp_path / "received.sqlite",
        inspection_id=attempt,
        provenance=provenance or {"requested_thread_id": "thread-1", "scope": "received_only"},
    )


def read_rows(path, table="received_chunks"):
    # Recovery is a read-only database inspection, not replay into the live pump.
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
    finally:
        connection.close()


async def append(journal, data=b"exact bytes", *, epoch=1, endpoint=ENDPOINT):
    await journal.append(endpoint_identity=endpoint, connection_generation=epoch, data=data)


@pytest.mark.asyncio
async def test_exact_sensitive_malformed_and_partial_bytes_survive_new_attempt(tmp_path):
    provenance = {"requested_thread_id": "thread-1", "workspace": {"choice": "original"}}
    journal = make_journal(tmp_path, provenance=provenance)
    provenance["workspace"]["choice"] = "mutated"
    chunks = [b"HTTP/1.1 101\r\n", b'\x81\xff{"id":"approval-id",', b"\xff\x00malformed"]
    for chunk in chunks:
        await append(journal, chunk)
    rows = read_rows(journal.path)
    assert [row["payload"] for row in rows] == chunks
    assert [row["payload_sha256"] for row in rows] == [
        hashlib.sha256(x).hexdigest() for x in chunks
    ]
    assert all(
        row["inspection_id"] == ATTEMPT and row["endpoint_identity"] == ENDPOINT for row in rows
    )
    assert all(datetime.fromisoformat(row["received_at"]).tzinfo is not None for row in rows)
    second = make_journal(tmp_path, attempt="b" * 32)
    await append(second, b"new attempt", epoch=1)
    assert read_rows(journal.path)[:3] == rows
    recorded = json.loads(read_rows(journal.path, "receive_attempts")[0]["provenance_json"])
    assert recorded["workspace"]["choice"] == "original"
    assert read_rows(journal.path, "receive_usage")[0] == {
        "singleton": 1,
        "payload_bytes": sum(map(len, chunks)) + 11,
        "records": 4,
        "attempts": 2,
    }


@pytest.mark.asyncio
async def test_epoch_advance_is_recorded_but_regression_latches_failure(tmp_path):
    journal = make_journal(tmp_path)
    await append(journal, b"first", epoch=1)
    await append(journal, b"second", epoch=2)
    with pytest.raises(CodexReceivedJournalError):
        await append(journal, b"old epoch", epoch=1)
    with pytest.raises(CodexReceivedJournalError):
        await append(journal, b"retry", epoch=2)
    assert not journal.healthy
    assert [row["connection_generation"] for row in read_rows(journal.path)] == [1, 2]


@pytest.mark.asyncio
async def test_distinct_endpoint_refuses_relabeling(tmp_path):
    journal = make_journal(tmp_path)
    await append(journal)
    with pytest.raises(CodexReceivedJournalError):
        await append(journal, endpoint="f" * 64)
    assert len(read_rows(journal.path)) == 1
    assert not journal.healthy


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data,epoch,endpoint",
    [
        (b"", 1, ENDPOINT),
        (b"x" * 65_537, 1, ENDPOINT),
        (bytearray(b"x"), 1, ENDPOINT),
        (b"x", True, ENDPOINT),
        (b"x", 0, ENDPOINT),
        (b"x", 2**63, ENDPOINT),
        (b"x", 1, "not-an-endpoint"),
    ],
    ids=["empty", "oversize", "mutable", "bool-epoch", "zero-epoch", "huge-epoch", "bad-endpoint"],
)
async def test_invalid_records_never_commit(tmp_path, data, epoch, endpoint):
    journal = make_journal(tmp_path)
    with pytest.raises(CodexReceivedJournalError):
        await append(journal, data, epoch=epoch, endpoint=endpoint)
    assert read_rows(journal.path) == []
    assert not journal.healthy


@pytest.mark.asyncio
@pytest.mark.parametrize("limit_name,limit", [("MAX_JOURNAL_BYTES", 3), ("MAX_JOURNAL_RECORDS", 1)])
async def test_capacity_keeps_prefix_and_never_rotates_or_retries(
    tmp_path, monkeypatch, limit_name, limit
):
    import pex_bridge.codex_received_journal as module

    monkeypatch.setattr(module, limit_name, limit)
    journal = make_journal(tmp_path)
    await append(journal, b"abc")
    with pytest.raises(CodexReceivedJournalError):
        await append(journal, b"d")
    assert [row["payload"] for row in read_rows(journal.path)] == [b"abc"]
    assert read_rows(journal.path, "receive_usage")[0]["payload_bytes"] == 3
    assert not journal.healthy


def test_attempt_capacity_and_duplicate_id_preserve_original(tmp_path, monkeypatch):
    import pex_bridge.codex_received_journal as module

    first = make_journal(tmp_path)
    with pytest.raises(CodexReceivedJournalError):
        make_journal(tmp_path)
    monkeypatch.setattr(module, "MAX_JOURNAL_ATTEMPTS", 1)
    with pytest.raises(CodexReceivedJournalError):
        make_journal(tmp_path, attempt="b" * 32)
    assert len(read_rows(first.path, "receive_attempts")) == 1
    assert read_rows(first.path, "receive_usage")[0]["attempts"] == 1


@pytest.mark.asyncio
async def test_tables_reject_update_and_delete(tmp_path):
    journal = make_journal(tmp_path)
    await append(journal)
    connection = sqlite3.connect(journal.path)
    try:
        for sql in (
            "UPDATE received_chunks SET payload=X'00'",
            "DELETE FROM received_chunks",
            "UPDATE receive_attempts SET provenance_json='{}'",
            "DELETE FROM receive_attempts",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                connection.execute(sql)
            connection.rollback()
    finally:
        connection.close()
    assert read_rows(journal.path)[0]["payload"] == b"exact bytes"


@pytest.mark.asyncio
async def test_database_loss_is_not_recreated(tmp_path):
    journal = make_journal(tmp_path)
    await append(journal)
    preserved = tmp_path / "preserved.sqlite"
    journal.path.rename(preserved)
    with pytest.raises(CodexReceivedJournalError):
        await append(journal)
    assert not journal.path.exists()
    assert len(read_rows(preserved)) == 1


@pytest.mark.asyncio
async def test_write_failure_rolls_back_and_permanently_refuses_retry(tmp_path):
    journal = make_journal(tmp_path)
    connection = sqlite3.connect(journal.path)
    try:
        connection.execute(
            "CREATE TRIGGER fixture_failure BEFORE UPDATE ON receive_usage "
            "BEGIN SELECT RAISE(ABORT, 'fixture disk error'); END"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(CodexReceivedJournalError, match="no automatic retry"):
        await append(journal)
    assert read_rows(journal.path) == []
    assert read_rows(journal.path, "receive_usage")[0]["records"] == 0
    assert not journal.healthy


@pytest.mark.asyncio
async def test_repeated_cancel_settles_exactly_one_real_commit(tmp_path, monkeypatch):
    journal = make_journal(tmp_path)
    original = journal._append
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def held(*args):
        calls.append(args)
        started.set()
        assert release.wait(5)
        original(*args)
        finished.set()

    monkeypatch.setattr(journal, "_append", held)
    task = asyncio.create_task(append(journal, b"received before cancellation"))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set() and len(calls) == 1
    assert [row["payload"] for row in read_rows(journal.path)] == [b"received before cancellation"]
    assert not journal.healthy


@pytest.mark.asyncio
async def test_parallel_attempts_commit_without_clobbering_counts(tmp_path):
    first = make_journal(tmp_path)
    second = make_journal(tmp_path, attempt="b" * 32)
    await asyncio.gather(*(append(first if i % 2 else second, str(i).encode()) for i in range(20)))
    rows = read_rows(first.path)
    assert len(rows) == 20 and len({row["sequence"] for row in rows}) == 20
    assert {row["payload"] for row in rows} == {str(i).encode() for i in range(20)}
    assert read_rows(first.path, "receive_usage")[0]["records"] == 20


def test_foreign_wal_database_rejection_does_not_checkpoint_or_touch_sidecars(tmp_path):
    source = tmp_path / "foreign.sqlite"
    connection = sqlite3.connect(source)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE foreign_data (value TEXT)")
        connection.execute("INSERT INTO foreign_data VALUES ('preserve foreign WAL too')")
        connection.commit()
        # Copy this quiescent fixture's committed main + WAL while the original
        # connection keeps its WAL open. The copied target has no live writer.
        target = tmp_path / "received.sqlite"
        target_wal = tmp_path / "received.sqlite-wal"
        shutil.copyfile(source, target)
        shutil.copyfile(tmp_path / "foreign.sqlite-wal", target_wal)
        original_main, original_wal = target.read_bytes(), target_wal.read_bytes()
        with pytest.raises(CodexReceivedJournalError, match="format is unavailable"):
            make_journal(tmp_path)
        assert target.read_bytes() == original_main
        assert target_wal.read_bytes() == original_wal
        assert not (tmp_path / "received.sqlite-shm").exists()
    finally:
        connection.close()
