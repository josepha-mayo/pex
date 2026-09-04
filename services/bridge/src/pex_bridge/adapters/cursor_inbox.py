"""Drain fail-open Cursor observer JSONL into the live supervisor."""

from __future__ import annotations

import json
from pathlib import Path

MAX_INBOX_BYTES = 8_388_608
MAX_RECORD_BYTES = 1_048_576


def inbox_path(home: Path) -> Path:
    return home / "hooks" / "cursor.jsonl"


def offset_path(home: Path) -> Path:
    return home / "hooks" / "cursor.offset"


def _read_offset(path: Path) -> int:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return 0
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
    if size > MAX_INBOX_BYTES:
        try:
            path.write_text("", encoding="utf-8")
            marker.write_text("0\n", encoding="utf-8")
        except OSError:
            return []
        return []
    offset = _read_offset(marker)
    if offset > size:
        offset = 0
    records: list[dict] = []
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            leftover = handle.read()
    except OSError:
        return []
    # The fail-open hook appends from a separate process. A read can therefore
    # end between write() calls or before the final newline reaches the file.
    # Never advance the durable marker beyond a complete JSONL record.
    final_newline = leftover.rfind(b"\n")
    if final_newline < 0:
        return []
    complete = leftover[: final_newline + 1]
    new_offset = offset + len(complete)
    for line in complete.splitlines():
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
