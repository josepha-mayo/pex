"""Bounded, non-consuming reads from the fail-open Cursor observer inbox."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

# Per-read memory budget, not permission to discard a larger unread backlog.
MAX_INBOX_BYTES = 8_388_608
MAX_RECORD_BYTES = 1_048_576
MAX_RECORDS_PER_DRAIN = 128
MAX_OFFSET_BYTES = 64


@dataclass(frozen=True)
class InboxBatch:
    source: Path
    marker: Path
    file_identity: tuple[int, int]
    marker_offset: int
    start: int
    end: int
    digest: str
    records: tuple[dict, ...]


def inbox_path(home: Path) -> Path:
    return home / "hooks" / "cursor.jsonl"


def offset_path(home: Path) -> Path:
    return home / "hooks" / "cursor.offset"


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _ordinary(info: os.stat_result, *, directory: bool = False) -> bool:
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    return (
        expected(info.st_mode)
        and not getattr(info, "st_file_attributes", 0) & 0x400
        and (directory or info.st_nlink == 1)
    )


def _checked_reader(path: Path) -> BinaryIO:
    before = path.lstat()
    if not _ordinary(before):
        raise ValueError("Cursor inbox path is not an ordinary single-link file")
    handle = path.open("rb")
    try:
        opened = os.fstat(handle.fileno())
        current = path.lstat()
        if not (
            _ordinary(opened) and _ordinary(current)
            and _identity(before) == _identity(opened) == _identity(current)
        ):
            raise ValueError("Cursor inbox file changed during open")
    except BaseException:
        handle.close()
        raise
    return handle


def _read_offset(path: Path) -> int:
    try:
        with _checked_reader(path) as handle:
            raw = handle.read(MAX_OFFSET_BYTES + 1)
    except FileNotFoundError:
        return 0
    if len(raw) > MAX_OFFSET_BYTES:
        return 0
    raw = raw.strip()
    if not raw.isdigit():
        return 0
    return int(raw)


def read_inbox(home: Path) -> InboxBatch | None:
    """Read a bounded prefix without advancing delivery or mutating source bytes."""
    path = inbox_path(home)
    marker = offset_path(home)
    try:
        if not _ordinary(path.parent.lstat(), directory=True):
            raise ValueError("Cursor inbox directory is not ordinary")
        marker_offset = _read_offset(marker)
        with _checked_reader(path) as handle:
            info = os.fstat(handle.fileno())
            offset = marker_offset if marker_offset <= info.st_size else 0
            handle.seek(offset)
            leftover = handle.read(MAX_INBOX_BYTES)
            current = path.lstat()
            if not _ordinary(current) or _identity(info) != _identity(current):
                raise ValueError("Cursor inbox changed during read")
    except FileNotFoundError:
        return None
    # Only complete JSONL lines belong to this batch. Malformed/empty lines count
    # against its processing budget; partial writes remain pending.
    final_newline = leftover.rfind(b"\n")
    if final_newline < 0:
        return None
    records: list[dict] = []
    consumed = 0
    for line in leftover[:final_newline + 1].split(b"\n", MAX_RECORDS_PER_DRAIN)[:-1]:
        consumed += len(line) + 1
        if not line.strip() or len(line) > MAX_RECORD_BYTES:
            continue
        try:
            payload = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return InboxBatch(
        source=path, marker=marker, file_identity=_identity(info),
        marker_offset=marker_offset, start=offset, end=offset + consumed,
        digest=hashlib.sha256(leftover[:consumed]).hexdigest(), records=tuple(records),
    )


def acknowledge_inbox(batch: InboxBatch) -> bool:
    """Advance only this unchanged prefix after its consumer has durably accepted it.

    This is a single-consumer checkpoint, not an interprocess CAS or directory lock.
    Concurrent append is allowed; replacement or modification of consumed bytes is not.
    """
    if _read_offset(batch.marker) != batch.marker_offset:
        return False
    parent_info = batch.marker.parent.lstat()
    if not _ordinary(parent_info, directory=True):
        raise ValueError("Cursor inbox directory is not ordinary")
    with _checked_reader(batch.source) as handle:
        if _identity(os.fstat(handle.fileno())) != batch.file_identity:
            return False
        handle.seek(batch.start)
        consumed = handle.read(batch.end - batch.start)
        if hashlib.sha256(consumed).hexdigest() != batch.digest:
            return False
    # Replace a freshly created checkpoint, never follow/truncate an existing
    # marker target. Directory check/open boundaries are still not OS-atomic.
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=batch.marker.parent,
                                         prefix=".cursor-offset-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(f"{batch.end}\n".encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        current_parent = batch.marker.parent.lstat()
        if not (
            _ordinary(current_parent, directory=True)
            and _identity(current_parent) == _identity(parent_info)
            and _read_offset(batch.marker) == batch.marker_offset
            and _identity(batch.source.lstat()) == batch.file_identity
        ):
            return False
        os.replace(temporary, batch.marker)
        temporary = None
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


async def process_inbox(
    home: Path,
    consume: Callable[[dict], Awaitable[None]],
    stop: asyncio.Event | None = None,
) -> int:
    """Serial, at-least-once delivery; failed/cancelled batches remain replayable."""
    if stop is not None and stop.is_set():
        return 0
    batch = await asyncio.to_thread(read_inbox, home)
    if batch is None:
        return 0
    for payload in batch.records:
        if stop is not None and stop.is_set():
            return 0
        await consume(payload)
    if stop is not None and stop.is_set():
        return 0
    if not await asyncio.to_thread(acknowledge_inbox, batch):
        raise RuntimeError("Cursor inbox changed before acknowledgement")
    return len(batch.records)
