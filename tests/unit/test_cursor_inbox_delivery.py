"""At-least-once local inbox handoff; fake consumers, no models or live Cursor."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path

import pytest
from pex_bridge.adapters import cursor_inbox as inbox


def _seed(home, *ids):
    path = inbox.inbox_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(json.dumps({"id": item}).encode() + b"\n" for item in ids))
    return path


@pytest.mark.asyncio
async def test_consumer_failure_keeps_the_batch_pending(tmp_path):
    path = _seed(tmp_path, "first", "retry")
    original = path.read_bytes()
    seen = []

    async def consume(payload):
        seen.append(payload["id"])
        if payload["id"] == "retry":
            raise RuntimeError("fixture admission failed")

    with pytest.raises(RuntimeError, match="admission failed"):
        await inbox.process_inbox(tmp_path, consume)
    assert inbox._read_offset(inbox.offset_path(tmp_path)) == 0
    assert path.read_bytes() == original
    seen.clear()

    async def accepted(payload):
        seen.append(payload["id"])

    assert await inbox.process_inbox(tmp_path, accepted) == 2
    assert seen == ["first", "retry"]
    assert inbox._read_offset(inbox.offset_path(tmp_path)) == len(original)


@pytest.mark.asyncio
async def test_cancelled_consumer_does_not_acknowledge_later_records(tmp_path):
    _seed(tmp_path, "pending", "not-started")
    started = asyncio.Event()
    seen = []

    async def consume(payload):
        seen.append(payload["id"])
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(inbox.process_inbox(tmp_path, consume))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert seen == ["pending"]
        assert inbox._read_offset(inbox.offset_path(tmp_path)) == 0
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_reader_and_acknowledgement_run_off_the_event_loop(tmp_path, monkeypatch):
    _seed(tmp_path, "one")
    current_thread = threading.get_ident()
    read = inbox.read_inbox
    acknowledge = inbox.acknowledge_inbox

    def checked_read(home):
        assert threading.get_ident() != current_thread
        return read(home)

    def checked_ack(batch):
        assert threading.get_ident() != current_thread
        return acknowledge(batch)

    async def consume(_payload):
        assert threading.get_ident() == current_thread
        assert inbox._read_offset(inbox.offset_path(tmp_path)) == 0

    monkeypatch.setattr(inbox, "read_inbox", checked_read)
    monkeypatch.setattr(inbox, "acknowledge_inbox", checked_ack)
    assert await inbox.process_inbox(tmp_path, consume) == 1


def test_changed_source_or_marker_refuses_batch_acknowledgement(tmp_path):
    path = _seed(tmp_path, "one")
    batch = inbox.read_inbox(tmp_path)
    assert batch is not None
    path.write_bytes(b'{"id":"two"}\n')
    assert not inbox.acknowledge_inbox(batch)
    assert inbox._read_offset(inbox.offset_path(tmp_path)) == 0

    batch = inbox.read_inbox(tmp_path)
    assert batch is not None
    inbox.offset_path(tmp_path).write_text("1\n")
    assert not inbox.acknowledge_inbox(batch)
    assert inbox._read_offset(inbox.offset_path(tmp_path)) == 1


def test_appending_to_the_same_file_does_not_acknowledge_new_records(tmp_path):
    path = _seed(tmp_path, "first")
    batch = inbox.read_inbox(tmp_path)
    assert batch is not None
    with path.open("ab") as handle:
        handle.write(b'{"id":"later"}\n')
    assert inbox.acknowledge_inbox(batch)
    later = inbox.read_inbox(tmp_path)
    assert later is not None
    assert later.records == ({"id": "later"},)


@pytest.mark.parametrize("target", ["source", "marker"])
def test_linked_inbox_paths_are_refused_without_modifying_the_target(tmp_path, target):
    source = _seed(tmp_path, "one")
    external = tmp_path / "outside-fixture"
    external.write_bytes(b"12\n" if target == "marker" else b'{"secret":"fixture"}\n')
    path = inbox.offset_path(tmp_path) if target == "marker" else source
    if path.exists():
        path.unlink()
    try:
        os.link(external, path)
    except OSError as exc:
        pytest.skip(f"hardlink unsupported: {type(exc).__name__}")
    before = external.read_bytes()
    with pytest.raises(ValueError, match="single-link"):
        inbox.read_inbox(tmp_path)
    assert external.read_bytes() == before


def test_replacement_during_open_is_refused_before_reading_bytes(tmp_path, monkeypatch):
    source = _seed(tmp_path, "one")
    external = tmp_path / "outside-fixture"
    external.write_bytes(b'{"private":"fixture"}\n')
    original = Path.open
    read = []

    class OtherFile:
        def __init__(self):
            self.handle = original(external, "rb")

        def fileno(self):
            return self.handle.fileno()

        def close(self):
            self.handle.close()

        def read(self, *_args):
            read.append(True)
            return self.handle.read(*_args)

    def replaced(self, mode="r", *args, **kwargs):
        return OtherFile() if self == source else original(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", replaced)
    with pytest.raises(ValueError, match="changed during open"):
        inbox.read_inbox(tmp_path)
    assert read == []


def test_checkpoint_replace_failure_keeps_prior_marker_and_removes_own_temp(tmp_path, monkeypatch):
    _seed(tmp_path, "one")
    marker = inbox.offset_path(tmp_path)
    marker.write_bytes(b"0\n")
    batch = inbox.read_inbox(tmp_path)
    assert batch is not None

    def failed_replace(*_args):
        raise OSError("fixture checkpoint failure")

    monkeypatch.setattr(inbox.os, "replace", failed_replace)
    with pytest.raises(OSError, match="checkpoint failure"):
        inbox.acknowledge_inbox(batch)
    assert marker.read_bytes() == b"0\n"
    assert list(marker.parent.glob(".cursor-offset-*")) == []


@pytest.mark.asyncio
async def test_stop_between_records_retains_batch_for_replay(tmp_path):
    _seed(tmp_path, "first", "next")
    stop = asyncio.Event()
    seen = []

    async def consume(payload):
        seen.append(payload["id"])
        stop.set()

    assert await inbox.process_inbox(tmp_path, consume, stop) == 0
    assert seen == ["first"]
    assert inbox._read_offset(inbox.offset_path(tmp_path)) == 0
