from __future__ import annotations

import ctypes
import os
import sys
from types import SimpleNamespace

import pytest
from pex_bridge import file_identity
from pex_bridge.store import _lifecycle_entity_identity


@pytest.mark.skipif(sys.platform != "linux", reason="native Linux creation identity")
def test_linux_identity_survives_edit_and_quarantine_rename(tmp_path):
    source = tmp_path / "owned.txt"
    source.write_text("first")
    before = _lifecycle_entity_identity(source)
    source.write_text("updated by the worker")
    assert _lifecycle_entity_identity(source) == before
    destination = tmp_path / "quarantined.txt"
    source.rename(destination)
    assert _lifecycle_entity_identity(destination) == before


@pytest.mark.skipif(sys.platform != "linux", reason="native Linux creation identity")
def test_linux_replacement_cannot_reuse_recorded_identity(tmp_path):
    source = tmp_path / "owned.txt"
    source.write_text("same bytes")
    before = _lifecycle_entity_identity(source)
    source.unlink()
    source.write_text("same bytes")
    assert _lifecycle_entity_identity(source) != before


def test_linux_identity_refuses_filesystem_without_creation_time(tmp_path, monkeypatch):
    source = tmp_path / "owned.txt"
    source.write_text("data")

    class MissingBirthTime:
        def __call__(self, _fd, _path, _flags, _mask, result):
            ctypes.cast(result, ctypes.POINTER(file_identity._Statx)).contents.mask = 0x101
            return 0

    monkeypatch.setattr(
        file_identity.ctypes, "CDLL", lambda *a, **k: SimpleNamespace(statx=MissingBirthTime())
    )
    with pytest.raises(ValueError, match="STATX_BTIME"):
        file_identity.linux_birthtime_ns(source, os.lstat(source))
