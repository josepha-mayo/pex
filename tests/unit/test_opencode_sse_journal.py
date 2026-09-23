import hashlib

import pytest

from benchmarks.opencode_sse_journal import OpenCodeSseJournal


def test_opencode_sse_journal_seals_exact_bytes(tmp_path):
    path = tmp_path / "capture.sse"
    journal = OpenCodeSseJournal(path)
    chunks = [b'data: {"text":"', b"\xc3", b'\xa9"}\n\n']
    for chunk in chunks:
        journal.observe("/global/event", chunk)
    receipt = journal.finish(stream_count=1, capture_failed=False, event_gap=False)
    assert path.read_bytes() == b"".join(chunks)
    assert receipt["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert receipt["bytes"] == len(path.read_bytes())
    assert receipt["chunks"] == 3
    with pytest.raises(RuntimeError, match="unavailable"):
        journal.observe("/global/event", b"later")


@pytest.mark.parametrize(
    "stream_count,capture_failed,event_gap",
    [(0, False, False), (2, False, False), (1, True, False), (1, False, True)],
)
def test_opencode_sse_journal_refuses_incomplete_stream(
    tmp_path, stream_count, capture_failed, event_gap
):
    journal = OpenCodeSseJournal(tmp_path / "capture.sse")
    try:
        journal.observe("/global/event", b"data: {}\n\n")
        with pytest.raises(RuntimeError, match="incomplete"):
            journal.finish(
                stream_count=stream_count,
                capture_failed=capture_failed,
                event_gap=event_gap,
            )
    finally:
        journal.abort()


def test_opencode_sse_journal_detects_tampering_and_preserves_incomplete_capture(tmp_path):
    path = tmp_path / "capture.sse"
    journal = OpenCodeSseJournal(path)
    journal.observe("/global/event", b"data: original\n\n")
    with path.open("r+b") as file:
        file.write(b"data: changed!\n\n")
    try:
        with pytest.raises(RuntimeError, match="changed"):
            journal.finish(stream_count=1, capture_failed=False, event_gap=False)
    finally:
        journal.abort()
    assert path.exists()


def test_opencode_sse_journal_rejects_duplicate_path_and_wrong_stream(tmp_path):
    path = tmp_path / "capture.sse"
    journal = OpenCodeSseJournal(path)
    try:
        with pytest.raises(FileExistsError):
            OpenCodeSseJournal(path)
        with pytest.raises(RuntimeError, match="unexpected path"):
            journal.observe("/event", b"data: {}\n\n")
    finally:
        journal.abort()
