from __future__ import annotations

import stat
from types import SimpleNamespace

import pex_bridge.adapters.codex_shared as shared
import pytest

AF_UNIX_REPARSE_TAG = 0x80000023
UNKNOWN_REPARSE_TAG = 0x80000024
JUNCTION_REPARSE_TAG = 0xA0000003
REPARSE_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _metadata(*, mode: int = stat.S_IFDIR | 0o700, tag: int = 0):
    return SimpleNamespace(
        st_mode=mode,
        st_file_attributes=REPARSE_ATTRIBUTE if tag else 0,
        st_reparse_tag=tag,
    )


def _mock_path_metadata(monkeypatch, path, *, marked_path=None, marked=None):
    def fake_lstat(current):
        if marked_path is not None and current == marked_path:
            return marked
        mode = stat.S_IFREG | 0o600 if current == path else stat.S_IFDIR | 0o700
        return _metadata(mode=mode)

    monkeypatch.setattr(shared.Path, "lstat", fake_lstat)


def test_windows_af_unix_reparse_is_allowed_only_for_socket_leaf(monkeypatch, tmp_path):
    socket_path = tmp_path / "private" / "control.sock"
    _mock_path_metadata(
        monkeypatch,
        socket_path,
        marked_path=socket_path,
        marked=_metadata(mode=stat.S_IFREG | 0o600, tag=AF_UNIX_REPARSE_TAG),
    )
    monkeypatch.setattr(shared.sys, "platform", "win32")

    shared._reject_reparse_components(socket_path, allow_windows_socket_leaf=True)
    with pytest.raises(ValueError, match="reparse point"):
        shared._reject_reparse_components(socket_path)


@pytest.mark.parametrize(
    ("case", "tag", "symlink"),
    [
        ("unknown leaf", UNKNOWN_REPARSE_TAG, False),
        ("junction leaf", JUNCTION_REPARSE_TAG, False),
        ("symlink leaf", 0, True),
    ],
)
def test_windows_socket_leaf_allowance_rejects_other_link_types(
    monkeypatch, tmp_path, case, tag, symlink
):
    socket_path = tmp_path / "private" / "control.sock"
    mode = stat.S_IFLNK | 0o777 if symlink else stat.S_IFREG | 0o600
    marked = _metadata(mode=mode, tag=tag)
    if symlink:
        marked.st_file_attributes = REPARSE_ATTRIBUTE
        marked.st_reparse_tag = JUNCTION_REPARSE_TAG
    _mock_path_metadata(monkeypatch, socket_path, marked_path=socket_path, marked=marked)
    monkeypatch.setattr(shared.sys, "platform", "win32")

    with pytest.raises(ValueError, match="link|reparse point"):
        shared._reject_reparse_components(socket_path, allow_windows_socket_leaf=True)


def test_windows_af_unix_reparse_is_rejected_on_ancestor(monkeypatch, tmp_path):
    socket_path = tmp_path / "private" / "control.sock"
    ancestor = socket_path.parent
    _mock_path_metadata(
        monkeypatch,
        socket_path,
        marked_path=ancestor,
        marked=_metadata(tag=AF_UNIX_REPARSE_TAG),
    )
    monkeypatch.setattr(shared.sys, "platform", "win32")

    with pytest.raises(ValueError, match="reparse point"):
        shared._reject_reparse_components(socket_path, allow_windows_socket_leaf=True)


def test_windows_af_unix_reparse_is_rejected_for_executable(monkeypatch, tmp_path):
    executable = tmp_path / "bin" / "codex.exe"
    _mock_path_metadata(
        monkeypatch,
        executable,
        marked_path=executable,
        marked=_metadata(mode=stat.S_IFREG | 0o700, tag=AF_UNIX_REPARSE_TAG),
    )
    monkeypatch.setattr(shared.sys, "platform", "win32")

    with pytest.raises(ValueError, match="reparse point"):
        shared._reject_reparse_components(executable)


def test_af_unix_tag_is_not_special_off_windows(monkeypatch, tmp_path):
    socket_path = tmp_path / "private" / "control.sock"
    _mock_path_metadata(
        monkeypatch,
        socket_path,
        marked_path=socket_path,
        marked=_metadata(mode=stat.S_IFREG | 0o600, tag=AF_UNIX_REPARSE_TAG),
    )
    monkeypatch.setattr(shared.sys, "platform", "linux")

    with pytest.raises(ValueError, match="reparse point"):
        shared._reject_reparse_components(socket_path, allow_windows_socket_leaf=True)


def test_launch_identity_allows_only_socket_leaf(monkeypatch, tmp_path):
    executable = tmp_path / "codex.exe"
    socket_path = tmp_path / "control.sock"
    executable.write_bytes(b"pinned executable")
    socket_path.write_bytes(b"rendezvous")
    calls = []

    def record(path, *, allow_windows_socket_leaf=False):
        calls.append((path, allow_windows_socket_leaf))

    monkeypatch.setattr(shared, "_reject_reparse_components", record)

    identity = shared._launch_identity(executable, socket_path)

    assert calls == [(executable, False), (socket_path, True)]
    assert identity[-1]
