"""Small-file inbox budgets; no Cursor process, bridge or model is started."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pex_bridge.adapters import cursor_inbox as inbox


def _drain_fixture(home: Path) -> list[dict]:
    """Explicit fixture acknowledgement; production requires durable consumption."""
    batch = inbox.read_inbox(home)
    if batch is None:
        return []
    assert inbox.acknowledge_inbox(batch)
    return list(batch.records)


def _write_rows(home: Path, count: int) -> Path:
    path = inbox.inbox_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(
        json.dumps({"conversation_id": str(index)}).encode() + b"\n"
        for index in range(count)
    ))
    return path


def test_inbox_reader_bounds_the_actual_read_not_just_prior_stat(tmp_path, monkeypatch):
    path = _write_rows(tmp_path, 1)
    original = Path.open
    sizes = []

    class TrackedReader:
        def __init__(self):
            self.handle = original(path, "rb")

        def __enter__(self):
            return self

        def fileno(self):
            return self.handle.fileno()

        def close(self):
            self.handle.close()

        def __exit__(self, *args):
            self.handle.close()

        def seek(self, offset):
            return self.handle.seek(offset)

        def read(self, size=-1):
            sizes.append(size)
            return self.handle.read(size)

        def readline(self, size=-1):
            sizes.append(size)
            return self.handle.readline(size)

    def tracked_open(self, mode="r", *args, **kwargs):
        if self == path and mode == "rb":
            return TrackedReader()
        return original(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracked_open)
    assert _drain_fixture(tmp_path) == [{"conversation_id": "0"}]
    assert sizes and all(0 < size <= inbox.MAX_INBOX_BYTES for size in sizes)


def test_inbox_record_batch_keeps_unread_rows_for_the_next_drain(tmp_path, monkeypatch):
    _write_rows(tmp_path, 7)
    monkeypatch.setattr(inbox, "MAX_RECORDS_PER_DRAIN", 3, raising=False)
    assert [row["conversation_id"] for row in _drain_fixture(tmp_path)] == ["0", "1", "2"]
    assert [row["conversation_id"] for row in _drain_fixture(tmp_path)] == ["3", "4", "5"]
    assert _drain_fixture(tmp_path) == [{"conversation_id": "6"}]
    assert _drain_fixture(tmp_path) == []


def test_production_batch_cap_advances_exactly_128_records(tmp_path):
    _write_rows(tmp_path, 130)
    assert len(_drain_fixture(tmp_path)) == 128
    assert _drain_fixture(tmp_path) == [
        {"conversation_id": "128"}, {"conversation_id": "129"},
    ]


def test_byte_offset_preserves_unicode_crlf_and_skips_oversized_complete_line(
    tmp_path, monkeypatch,
):
    path = _write_rows(tmp_path, 0)
    first = json.dumps({"name": "猫"}, ensure_ascii=False).encode() + b"\r\n"
    oversized = json.dumps({"long": "x" * 80}).encode() + b"\n"
    path.write_bytes(first + oversized + b"{}\n")
    monkeypatch.setattr(inbox, "MAX_RECORD_BYTES", 32)
    monkeypatch.setattr(inbox, "MAX_RECORDS_PER_DRAIN", 1)
    assert _drain_fixture(tmp_path) == [{"name": "猫"}]
    assert inbox._read_offset(inbox.offset_path(tmp_path)) == len(first)
    assert _drain_fixture(tmp_path) == []
    assert inbox._read_offset(inbox.offset_path(tmp_path)) == len(first + oversized)
    assert _drain_fixture(tmp_path) == [{}]


def test_backlog_larger_than_read_budget_is_preserved_and_drained_in_order(tmp_path, monkeypatch):
    path = _write_rows(tmp_path, 7)
    original = path.read_bytes()
    monkeypatch.setattr(inbox, "MAX_INBOX_BYTES", 64)
    rows = []
    for _ in range(10):
        rows.extend(_drain_fixture(tmp_path))
    assert [row["conversation_id"] for row in rows] == [str(index) for index in range(7)]
    assert path.read_bytes() == original, "a backlog must never be truncated by its reader"


@pytest.mark.parametrize("invalid", ["²", "9" * 80])
def test_invalid_or_overlong_offset_is_a_bounded_fresh_read(tmp_path, invalid):
    marker = inbox.offset_path(tmp_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(invalid, encoding="utf-8")
    assert inbox._read_offset(marker) == 0


def test_batch_limit_counts_malformed_lines_and_preserves_partial_json(tmp_path, monkeypatch):
    path = _write_rows(tmp_path, 0)
    path.write_bytes(b"bad\n\n{}\n{\"conversation_id\":\"split")
    monkeypatch.setattr(inbox, "MAX_RECORDS_PER_DRAIN", 2, raising=False)
    assert _drain_fixture(tmp_path) == []
    assert inbox._read_offset(inbox.offset_path(tmp_path)) == 5
    assert _drain_fixture(tmp_path) == [{}]
    assert inbox._read_offset(inbox.offset_path(tmp_path)) == 8
    with path.open("ab") as handle:
        handle.write(b"\"}\n")
    assert _drain_fixture(tmp_path) == [{"conversation_id": "split"}]


def test_newline_free_oversized_record_advances_once_and_preserves_next_row(
    tmp_path, monkeypatch,
):
    path = _write_rows(tmp_path, 0)
    poison = b"x" * 80
    path.write_bytes(poison)
    monkeypatch.setattr(inbox, "MAX_RECORD_BYTES", 16)
    monkeypatch.setattr(inbox, "MAX_INBOX_BYTES", 20)
    monkeypatch.setattr(inbox, "MAX_RECORDS_PER_DRAIN", 2)

    ends: list[int] = []
    for _ in range(8):
        batch = inbox.read_inbox(tmp_path)
        assert batch is not None
        assert batch.records == ()
        assert batch.end > (ends[-1] if ends else 0)
        ends.append(batch.end)
        assert inbox.acknowledge_inbox(batch)
        if batch.end == len(poison):
            break

    assert ends[-1] == len(poison)
    assert inbox._read_offset(inbox.offset_path(tmp_path)) == len(poison)

    with path.open("ab") as handle:
        handle.write(b"\n{}\n")
    assert _drain_fixture(tmp_path) == [{}]


def test_offset_reader_never_reads_the_whole_marker(tmp_path, monkeypatch):
    marker = inbox.offset_path(tmp_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("12\n", encoding="utf-8")
    original = Path.open
    sizes = []

    class TrackedMarker:
        def __init__(self):
            self.handle = original(marker, "rb")

        def __enter__(self):
            return self

        def fileno(self):
            return self.handle.fileno()

        def close(self):
            self.handle.close()

        def __exit__(self, *args):
            self.handle.close()

        def read(self, size=-1):
            sizes.append(size)
            return self.handle.read(size)

    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: TrackedMarker())
    assert inbox._read_offset(marker) == 12
    assert sizes and all(0 < size <= inbox.MAX_CHECKPOINT_BYTES + 1 for size in sizes)
