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

from pex_bridge.adapters.strict_json import strict_json_loads

# Per-read memory budget, not permission to discard a larger unread backlog.
MAX_INBOX_BYTES = 8_388_608
MAX_RECORD_BYTES = 1_048_576
MAX_RECORDS_PER_DRAIN = 128
MAX_OFFSET_BYTES = 64
MAX_CHECKPOINT_BYTES = 256
CHECKPOINT_ANCHOR_BYTES = 4096


class PermanentInboxRecordError(ValueError):
    """A parsed record can never become an admissible Cursor hook on retry."""


@dataclass(frozen=True)
class InboxCheckpoint:
    offset: int = 0
    file_identity: tuple[int, int] | None = None
    anchor: str | None = None
    discarding_line: bool = False


@dataclass(frozen=True)
class InboxBatch:
    source: Path
    marker: Path
    file_identity: tuple[int, int]
    marker_state: bytes
    start: int
    end: int
    digest: str
    records: tuple[dict, ...]
    discarding_line: bool


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


def _read_marker(path: Path) -> bytes:
    try:
        with _checked_reader(path) as handle:
            return handle.read(MAX_CHECKPOINT_BYTES + 1)
    except FileNotFoundError:
        return b""


def _decode_checkpoint(raw: bytes) -> InboxCheckpoint:
    if len(raw) > MAX_CHECKPOINT_BYTES:
        return InboxCheckpoint()
    legacy = raw.strip()
    if len(legacy) <= MAX_OFFSET_BYTES and legacy.isdigit():
        return InboxCheckpoint(offset=int(legacy))
    try:
        value = strict_json_loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return InboxCheckpoint()
    if not isinstance(value, dict):
        return InboxCheckpoint()
    version = value.get("v")
    legacy_keys = {"v", "offset", "dev", "ino", "anchor"}
    resumable_keys = {*legacy_keys, "discarding"}
    if type(version) is not int or (
        (version == 1 and set(value) != legacy_keys)
        or (version == 2 and set(value) != resumable_keys)
        or version not in {1, 2}
    ):
        return InboxCheckpoint()
    for key, bits in (("offset", 63), ("dev", 128), ("ino", 128)):
        if type(value[key]) is not int or not 0 <= value[key] < 2 ** bits:
            return InboxCheckpoint()
    anchor = value["anchor"]
    if not isinstance(anchor, str) or len(anchor) != 64 or set(anchor) - set("0123456789abcdef"):
        return InboxCheckpoint()
    discarding = value.get("discarding", False)
    if type(discarding) is not bool:
        return InboxCheckpoint()
    return InboxCheckpoint(
        value["offset"],
        (value["dev"], value["ino"]),
        anchor,
        discarding,
    )


def _read_offset(path: Path) -> int:
    return _decode_checkpoint(_read_marker(path)).offset


def _checkpoint_anchor(handle: BinaryIO, offset: int) -> str:
    # A cheap append-only restart guard, not a digest of the complete history.
    # Earlier in-place edits outside this boundary require stronger generation tracking.
    length = min(CHECKPOINT_ANCHOR_BYTES, MAX_INBOX_BYTES, offset)
    handle.seek(offset - length)
    return hashlib.sha256(handle.read(length)).hexdigest()


def read_inbox(home: Path) -> InboxBatch | None:
    """Read a bounded prefix without advancing delivery or mutating source bytes."""
    path = inbox_path(home)
    marker = offset_path(home)
    records: list[dict] = []
    consumed = 0
    digest = hashlib.sha256()
    discarding_line = False
    try:
        if not _ordinary(path.parent.lstat(), directory=True):
            raise ValueError("Cursor inbox directory is not ordinary")
        marker_state = _read_marker(marker)
        checkpoint = _decode_checkpoint(marker_state)
        with _checked_reader(path) as handle:
            info = os.fstat(handle.fileno())
            # Legacy offsets have no file-generation proof. Replay them once;
            # successful durable consumption migrates to the bound checkpoint.
            offset = 0
            if (
                checkpoint.file_identity == _identity(info)
                and checkpoint.offset <= info.st_size
                and _checkpoint_anchor(handle, checkpoint.offset) == checkpoint.anchor
            ):
                offset = checkpoint.offset
                discarding_line = checkpoint.discarding_line
            if offset == info.st_size:
                return None
            handle.seek(offset)
            # Stop after the line count too, rather than repeatedly copying an
            # entire backlog for a small batch. A still-admissible partial JSONL
            # record never advances; an already-oversized one cannot become valid.
            record_count = 0
            while record_count < MAX_RECORDS_PER_DRAIN:
                remaining = MAX_INBOX_BYTES - consumed
                if remaining <= 0:
                    break
                line = handle.readline(min(remaining, MAX_RECORD_BYTES + 2))
                if not line:
                    break
                terminated = line.endswith(b"\n")
                if not terminated and not discarding_line and len(line) <= MAX_RECORD_BYTES:
                    break
                consumed += len(line)
                digest.update(line)
                if discarding_line:
                    if terminated:
                        discarding_line = False
                        record_count += 1
                    continue
                if not terminated:
                    # The prefix already exceeds the complete-record limit and
                    # can never become admissible JSON. Persist discard mode so
                    # later reads advance to its newline without parsing a suffix.
                    discarding_line = True
                    continue
                record_count += 1
                content = line[:-1]
                if not content.strip() or len(content) > MAX_RECORD_BYTES:
                    continue
                try:
                    # Hook records are an authority boundary. Python's default
                    # decoder accepts duplicate keys (last one wins) and NaN /
                    # Infinity, making the observed event ambiguous or non-RFC.
                    payload = strict_json_loads(content)
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
                    continue
                if isinstance(payload, dict):
                    records.append(payload)
            current = path.lstat()
            if not _ordinary(current) or _identity(info) != _identity(current):
                raise ValueError("Cursor inbox changed during read")
    except FileNotFoundError:
        return None
    if consumed == 0:
        return None
    return InboxBatch(
        source=path, marker=marker, file_identity=_identity(info),
        marker_state=marker_state, start=offset, end=offset + consumed,
        digest=digest.hexdigest(), records=tuple(records),
        discarding_line=discarding_line,
    )


def acknowledge_inbox(batch: InboxBatch) -> bool:
    """Advance only this unchanged prefix after its consumer has durably accepted it.

    This is a single-consumer checkpoint, not an interprocess CAS or directory lock.
    Concurrent append is allowed; replacement or modification of consumed bytes is not.
    """
    if _read_marker(batch.marker) != batch.marker_state:
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
        anchor = _checkpoint_anchor(handle, batch.end)
    checkpoint_bytes = (json.dumps({
        "v": 2, "offset": batch.end, "dev": batch.file_identity[0],
        "ino": batch.file_identity[1], "anchor": anchor,
        "discarding": batch.discarding_line,
    }, separators=(",", ":"), sort_keys=True) + "\n").encode("ascii")
    if len(checkpoint_bytes) > MAX_CHECKPOINT_BYTES:
        raise ValueError("Cursor checkpoint exceeds its format bound")
    # Replace a freshly created checkpoint, never follow/truncate an existing
    # marker target. Directory check/open boundaries are still not OS-atomic.
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=batch.marker.parent,
                                         prefix=".cursor-offset-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(checkpoint_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        current_parent = batch.marker.parent.lstat()
        if not (
            _ordinary(current_parent, directory=True)
            and _identity(current_parent) == _identity(parent_info)
            and _read_marker(batch.marker) == batch.marker_state
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
        try:
            await consume(payload)
        except PermanentInboxRecordError:
            # Shape/bound failures are deterministic for these immutable source
            # bytes. Transient authority, Store and pipeline failures still
            # propagate and retain the complete at-least-once batch.
            continue
    if stop is not None and stop.is_set():
        return 0
    if not await asyncio.to_thread(acknowledge_inbox, batch):
        raise RuntimeError("Cursor inbox changed before acknowledgement")
    return len(batch.records)
