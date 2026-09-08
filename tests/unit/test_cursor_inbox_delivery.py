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


def test_checkpoint_does_not_skip_a_replacement_file_after_restart(tmp_path):
    source = _seed(tmp_path, "original")
    batch = inbox.read_inbox(tmp_path)
    assert batch is not None and inbox.acknowledge_inbox(batch)
    replacement = tmp_path / "replacement.jsonl"
    replacement.write_bytes(b'{"id":"replacement is larger than the original"}\n')
    os.replace(replacement, source)
    restarted = inbox.read_inbox(tmp_path)
    assert restarted is not None
    assert restarted.records == ({"id": "replacement is larger than the original"},)


def test_checkpoint_rejects_same_inode_rewrite_of_the_consumed_boundary(tmp_path):
    source = _seed(tmp_path, "before")
    batch = inbox.read_inbox(tmp_path)
    assert batch is not None and inbox.acknowledge_inbox(batch)
    source.write_bytes(b'{"id":"rewritten with the same file identity"}\n')
    restarted = inbox.read_inbox(tmp_path)
    assert restarted is not None
    assert restarted.records == ({"id": "rewritten with the same file identity"},)


def test_legacy_offset_replays_once_before_migrating_to_a_bound_checkpoint(tmp_path):
    source = _seed(tmp_path, "unproven legacy admission")
    inbox.offset_path(tmp_path).write_text(f"{source.stat().st_size}\n")
    legacy = inbox.read_inbox(tmp_path)
    assert legacy is not None
    assert legacy.start == 0
    assert legacy.records == ({"id": "unproven legacy admission"},)
    assert inbox.acknowledge_inbox(legacy)
    assert inbox.read_inbox(tmp_path) is None


def test_v1_identity_checkpoint_resumes_without_discard_mode(tmp_path):
    source = _seed(tmp_path, "already-consumed", "pending")
    first_line = b'{"id": "already-consumed"}\n'
    info = source.stat()
    with source.open("rb") as handle:
        anchor = inbox._checkpoint_anchor(handle, len(first_line))
    inbox.offset_path(tmp_path).write_text(
        json.dumps(
            {
                "v": 1,
                "offset": len(first_line),
                "dev": info.st_dev,
                "ino": info.st_ino,
                "anchor": anchor,
            }
        ),
        encoding="ascii",
    )

    resumed = inbox.read_inbox(tmp_path)

    assert resumed is not None
    assert resumed.start == len(first_line)
    assert resumed.records == ({"id": "pending"},)
    assert resumed.discarding_line is False


@pytest.mark.parametrize(
    "change", [
        "bool_offset",
        "bad_anchor",
        "negative_device",
        "bad_discard",
        "duplicate",
        "oversized",
    ],
)
def test_malformed_checkpoint_cannot_skip_records(tmp_path, change):
    _seed(tmp_path, "keep")
    batch = inbox.read_inbox(tmp_path)
    assert batch is not None and inbox.acknowledge_inbox(batch)
    marker = inbox.offset_path(tmp_path)
    value = json.loads(marker.read_bytes())
    if change == "bool_offset":
        value["offset"] = True
    elif change == "bad_anchor":
        value["anchor"] = "0" * 64
    elif change == "negative_device":
        value["dev"] = -1
    elif change == "bad_discard":
        value["discarding"] = "false"
    raw = json.dumps(value)
    if change == "duplicate":
        raw = raw.replace('"v": 2', '"v": 2, "v": 2')
    elif change == "oversized":
        raw = " " * (inbox.MAX_CHECKPOINT_BYTES + 1) + raw
    marker.write_text(raw, encoding="utf-8")
    replay = inbox.read_inbox(tmp_path)
    assert replay is not None
    assert replay.start == 0 and replay.records == ({"id": "keep"},)


def test_idle_checkpoint_reads_only_a_small_boundary_and_no_body(tmp_path, monkeypatch):
    source = _seed(tmp_path, "complete")
    batch = inbox.read_inbox(tmp_path)
    assert batch is not None and inbox.acknowledge_inbox(batch)
    original = Path.open
    sizes = []

    class Tracked:
        def __init__(self):
            self.handle = original(source, "rb")

        def __getattr__(self, name):
            return getattr(self.handle, name)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.handle.close()

        def read(self, size=-1):
            sizes.append(size)
            return self.handle.read(size)

        def readline(self, *_args):
            pytest.fail("a caught-up inbox must not read the backlog body")

    def tracked(self, mode="r", *args, **kwargs):
        return Tracked() if self == source else original(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracked)
    assert inbox.read_inbox(tmp_path) is None
    assert len(sizes) == 1 and 0 < sizes[0] <= 4096


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
