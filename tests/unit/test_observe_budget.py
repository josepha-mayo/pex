"""Tiny-fixture resource and freshness checks; no real worker execution."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from pex_bridge import observe


def test_read_only_snapshot_hashes_each_file_once(tmp_path, monkeypatch):
    for name in ("answer.py", "report.txt"):
        (tmp_path / name).write_text("public fixture", encoding="utf-8")
    digested = []
    original = observe._file_digest

    def tracked(path, **kwargs):
        digested.append(path.name)
        return original(path, **kwargs)

    monkeypatch.setattr(observe, "_file_digest", tracked)
    snapshot = observe.snapshot(tmp_path)
    assert snapshot["files"] == ["answer.py", "report.txt"]
    assert digested == ["answer.py", "report.txt"]
    assert snapshot["file_manifest"][0]["sha256"] == hashlib.sha256(b"public fixture").hexdigest()


def test_explicit_verification_still_observes_new_artifacts_afterward(tmp_path, monkeypatch):
    (tmp_path / "test_public.py").write_text("# public fixture", encoding="utf-8")

    def fake_public_verification(root, files):
        assert files == ["test_public.py"]
        (root / "result.txt").write_text("observed result", encoding="utf-8")
        return {"ok": True, "exit_code": 0, "output": "fixture", "timed_out": False}

    monkeypatch.setattr(observe, "_public_pytest", fake_public_verification)
    snapshot = observe.snapshot(tmp_path, run_pytest=True)
    assert snapshot["files"] == ["result.txt", "test_public.py"]
    assert snapshot["pytest"]["ok"] is True


def test_manifest_byte_budget_refuses_next_file_before_hashing_it(tmp_path, monkeypatch):
    (tmp_path / "first.txt").write_bytes(b"1234")
    (tmp_path / "second.txt").write_bytes(b"5678")
    monkeypatch.setattr(observe, "_MAX_MANIFEST_TOTAL_BYTES", 4)
    original = observe._file_digest
    digested = []

    def tracked(path, **kwargs):
        digested.append(path.name)
        return original(path, **kwargs)

    monkeypatch.setattr(observe, "_file_digest", tracked)
    with pytest.raises(ValueError, match="512 MiB observation bound"):
        observe.snapshot(tmp_path)
    assert digested == ["first.txt"]


def test_manifest_time_budget_stops_before_the_next_file(tmp_path, monkeypatch):
    for name in ("first.txt", "second.txt"):
        (tmp_path / name).write_bytes(b"tiny fixture")
    now = [0.0]
    monkeypatch.setattr(observe, "time", SimpleNamespace(monotonic=lambda: now[0]), raising=False)
    monkeypatch.setattr(observe, "_MAX_MANIFEST_SECONDS", 5.0, raising=False)
    original = observe._file_digest
    digested = []

    def slow_digest(path, **kwargs):
        digested.append(path.name)
        result = original(path, **kwargs)
        now[0] = 6.0
        return result

    monkeypatch.setattr(observe, "_file_digest", slow_digest)
    with pytest.raises(ValueError, match="time budget"):
        observe.snapshot(tmp_path)
    assert digested == ["first.txt"]


def test_digest_time_budget_is_checked_between_file_chunks(tmp_path, monkeypatch):
    visible = tmp_path / "report.txt"
    visible.write_bytes(b"ab")
    now = [0.0]
    monkeypatch.setattr(observe, "time", SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(observe, "_HASH_CHUNK_BYTES", 1)
    original_sha256 = hashlib.sha256
    updated = []

    class MeasuredHash:
        def __init__(self):
            self.digest = original_sha256()

        def update(self, chunk):
            updated.append(chunk)
            self.digest.update(chunk)
            now[0] = 6.0

        def hexdigest(self):
            return self.digest.hexdigest()

    monkeypatch.setattr(observe.hashlib, "sha256", MeasuredHash)
    with pytest.raises(ValueError, match="time budget"):
        observe._file_digest(visible, deadline=5.0)
    assert updated == [b"a"]


def test_manifest_caps_directory_entries_before_sorting_or_hashing(tmp_path, monkeypatch):
    for name in ("first.txt", "second.txt", "third.txt"):
        (tmp_path / name).write_bytes(b"tiny")
    monkeypatch.setattr(observe, "_MAX_MANIFEST_ENTRIES", 2, raising=False)
    monkeypatch.setattr(
        observe, "_file_digest", lambda *_args, **_kwargs: pytest.fail("hashed before entry cap")
    )
    with pytest.raises(ValueError, match="entry observation bound"):
        observe.snapshot(tmp_path)


def test_directory_enumeration_checks_budget_before_consuming_more_entries(tmp_path, monkeypatch):
    for name in ("first.txt", "second.txt", "third.txt"):
        (tmp_path / name).write_bytes(b"tiny")
    now = [0.0]
    consumed = []
    original_scandir = observe.os.scandir
    monkeypatch.setattr(observe, "time", SimpleNamespace(monotonic=lambda: now[0]))

    class SlowDirectory:
        def __init__(self, path):
            self.iterator = original_scandir(path)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.iterator.close()

        def __iter__(self):
            return self

        def __next__(self):
            if len(consumed) >= 2:
                pytest.fail("continued enumeration after deadline")
            entry = next(self.iterator)
            consumed.append(entry.name)
            now[0] += 3.0
            return entry

    monkeypatch.setattr(observe.os, "scandir", SlowDirectory)
    with pytest.raises(ValueError, match="time budget"):
        observe.snapshot(tmp_path)
    assert len(consumed) == 2


def test_bounded_scan_preserves_sorted_depth_first_manifest_order(tmp_path):
    for relative in ("z.txt", "a.txt", "z/deep.txt", "a/z.txt", "a/a.txt", "a/sub/x.txt"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"tiny")
    assert observe.snapshot(tmp_path)["files"] == [
        "a.txt", "z.txt", "a/a.txt", "a/z.txt", "a/sub/x.txt", "z/deep.txt"
    ]


def test_queued_directory_replacement_is_rejected_before_enumerating_it(tmp_path, monkeypatch):
    child = tmp_path / "child"
    child.mkdir()
    (child / "report.txt").write_text("public", encoding="utf-8")
    original_scandir = observe.os.scandir
    scanned = []

    class RootScan:
        def __enter__(self):
            self.iterator = original_scandir(tmp_path)
            return self.iterator

        def __exit__(self, *_args):
            self.iterator.close()
            child.rename(tmp_path / "moved")
            child.mkdir()

    def replaced_scandir(path):
        scanned.append(path)
        if path == tmp_path:
            return RootScan()
        pytest.fail("enumerated replaced queued directory")

    monkeypatch.setattr(observe.os, "scandir", replaced_scandir)
    with pytest.raises(ValueError, match="directory changed"):
        observe.snapshot(tmp_path)
    assert scanned == [tmp_path]
