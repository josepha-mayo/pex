"""Drain fail-open Cursor observer JSONL into the live supervisor."""

from __future__ import annotations

import json
from pathlib import Path

# Per-read memory budget, not permission to discard a larger unread backlog.
MAX_INBOX_BYTES = 8_388_608
MAX_RECORD_BYTES = 1_048_576
MAX_RECORDS_PER_DRAIN = 128
MAX_OFFSET_BYTES = 64


def inbox_path(home: Path) -> Path:
    return home / "hooks" / "cursor.jsonl"


def offset_path(home: Path) -> Path:
    return home / "hooks" / "cursor.offset"


def _read_offset(path: Path) -> int:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_OFFSET_BYTES + 1)
    except OSError:
        return 0
    if len(raw) > MAX_OFFSET_BYTES:
        return 0
    raw = raw.strip()
    if not raw.isdigit():
        return 0
    return int(raw)


def drain_inbox(home: Path) -> list[dict]:
    path = inbox_path(home)
    marker = offset_path(home)
    if not path.is_file():
        return []
    try:
        size = path.stat().st_size
    except OSError:
        return []
    offset = _read_offset(marker)
    if offset > size:
        offset = 0
    records: list[dict] = []
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            # The append-only producer can grow the file after the size check.
            leftover = handle.read(MAX_INBOX_BYTES)
    except OSError:
        return []
    # The fail-open hook appends from a separate process. A read can therefore
    # end between write() calls or before the final newline reaches the file.
    # Never advance the durable marker beyond a complete JSONL record.
    final_newline = leftover.rfind(b"\n")
    if final_newline < 0:
        return []
    complete = leftover[: final_newline + 1]
    new_offset = offset
    # Count malformed/empty lines too: they must not bypass the parse-work budget.
    # The final split item is either the empty tail or the unconsumed next batch.
    for line in complete.split(b"\n", MAX_RECORDS_PER_DRAIN)[:-1]:
        new_offset += len(line) + 1
        if not line.strip():
            continue
        if len(line) > MAX_RECORD_BYTES:
            continue
        try:
            payload = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
            continue
        if isinstance(payload, dict):
            records.append(payload)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"{new_offset}\n", encoding="utf-8")
    except OSError:
        return records
    return records
