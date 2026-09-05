"""Fresh local stat samples only: no providers, worker launches or ACL changes."""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from pex_bridge import local_workspace
from pex_bridge.local_workspace import (
    LocalDirectoryIdentity,
    measure_local_directory,
    require_same_local_directory,
)
from pex_protocol.project_identity import PathPlatform, PhysicalIdentityProof


def test_actual_directory_uses_server_stat_identity(tmp_path):
    measured = measure_local_directory(str(tmp_path))
    observed = tmp_path.stat()
    assert measured.cwd == str(tmp_path.resolve(strict=True))
    assert measured.physical == PhysicalIdentityProof(
        provider=f"pex-os-stat-{measured.platform.value}-v1",
        volume_id=str(observed.st_dev), object_id=str(observed.st_ino),
    )
    assert require_same_local_directory(str(tmp_path), measured) is None
    with pytest.raises(FrozenInstanceError):
        measured.cwd = "changed"


def test_rename_and_replacement_do_not_reuse_old_directory_identity(tmp_path):
    original = tmp_path / "workspace"
    original.mkdir()
    measured = measure_local_directory(str(original))
    retained = tmp_path / "original-preserved"
    original.rename(retained)
    original.mkdir()
    assert retained.is_dir()  # The original remains recoverable, never deleted.
    assert measure_local_directory(str(retained)).physical == measured.physical
    assert measure_local_directory(str(original)).physical != measured.physical
    with pytest.raises(ValueError, match="identity changed"):
        require_same_local_directory(str(original), measured)
    with pytest.raises(ValueError, match="identity changed"):
        require_same_local_directory(str(retained), measured)


def test_directory_entry_changes_do_not_change_object_identity(tmp_path):
    measured = measure_local_directory(str(tmp_path))
    (tmp_path / "new-child").mkdir()
    assert measure_local_directory(str(tmp_path)) == measured
    require_same_local_directory(str(tmp_path), measured)


@pytest.mark.parametrize(
    "path", [None, 4, Path("relative"), "", "relative", "\x00", "a\n", "x" * 4097],
)
def test_invalid_or_relative_input_is_rejected_without_stat(path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid paths must not access the filesystem")
    monkeypatch.setattr(local_workspace, "_os_stat", forbidden)
    with pytest.raises(ValueError):
        measure_local_directory(path)


def test_missing_directory_and_regular_file_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="could not be measured"):
        measure_local_directory(str(tmp_path / "missing"))
    with pytest.raises(ValueError, match="not a real directory"):
        measure_local_directory(__file__)


@pytest.mark.parametrize(
    ("field", "value"),
    [("st_ino", 0), ("st_dev", 0), ("st_ino", -1), ("st_dev", -1),
     ("st_ino", True), ("st_dev", "123"), ("st_ino", None), ("st_dev", None),
     ("st_ino", 2**128), ("st_mode", True), ("st_mode", None)],
)
def test_unknown_or_malformed_stat_identity_is_unsupported(tmp_path, monkeypatch, field, value):
    values = {"st_mode": 0o40755, "st_dev": 12, "st_ino": 34, field: value}
    monkeypatch.setattr(local_workspace, "_os_stat", lambda *a, **kw: SimpleNamespace(**values))
    with pytest.raises(ValueError):
        measure_local_directory(str(tmp_path))


def test_windows_128_bit_file_identity_is_not_truncated(tmp_path, monkeypatch):
    monkeypatch.setattr(local_workspace, "_host_platform", lambda: PathPlatform.WINDOWS)
    values = SimpleNamespace(st_mode=0o40755, st_dev=12, st_ino=2**127 + 91)
    monkeypatch.setattr(local_workspace, "_os_stat", lambda *a, **kw: values)
    measured = measure_local_directory(str(tmp_path))
    assert measured.physical.object_id == str(2**127 + 91)
    assert measured.physical.provider == "pex-os-stat-windows-v1"


def test_unsupported_host_platform_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(local_workspace, "os", SimpleNamespace(name="unknown"))
    with pytest.raises(ValueError, match="unsupported on this platform"):
        measure_local_directory(str(tmp_path))


@pytest.mark.parametrize("failure", [PermissionError, OSError, NotImplementedError])
def test_stat_failure_does_not_echo_input_path(tmp_path, monkeypatch, failure):
    def unavailable(*args, **kwargs):
        raise failure("sensitive fixture path")
    monkeypatch.setattr(local_workspace, "_os_stat", unavailable)
    with pytest.raises(ValueError, match="could not be measured") as caught:
        measure_local_directory(str(tmp_path))
    assert "sensitive" not in str(caught.value)


@pytest.mark.parametrize("sample", [2, 3, 4])
def test_replacement_during_each_stat_sample_fails_closed(tmp_path, monkeypatch, sample):
    samples = 0
    def changed(*args, **kwargs):
        nonlocal samples
        samples += 1
        return SimpleNamespace(st_mode=0o40755, st_dev=12, st_ino=99 if samples >= sample else 34)
    monkeypatch.setattr(local_workspace, "_os_stat", changed)
    with pytest.raises(ValueError, match="changed during identity measurement"):
        measure_local_directory(str(tmp_path))


def test_resolved_target_change_is_not_hidden_by_equal_mocked_stat_ids(tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    targets = iter((tmp_path, other))
    monkeypatch.setattr(local_workspace, "_resolved_directory", lambda path: next(targets))
    monkeypatch.setattr(local_workspace, "_os_stat", lambda *a, **kw: SimpleNamespace(
        st_mode=0o40755, st_dev=12, st_ino=34,
    ))
    with pytest.raises(ValueError, match="changed during identity measurement"):
        measure_local_directory(str(tmp_path))


def test_unresolved_windows_reparse_directory_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(local_workspace, "_host_platform", lambda: PathPlatform.WINDOWS)
    monkeypatch.setattr(local_workspace, "_os_stat", lambda *a, **kw: SimpleNamespace(
        st_mode=0o40755, st_dev=12, st_ino=34, st_file_attributes=0x400,
    ))
    with pytest.raises(ValueError, match="unsupported reparse point"):
        measure_local_directory(str(tmp_path))


def test_real_symlink_alias_is_target_bound_when_supported(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlink not available: {type(exc).__name__}")
    measured = measure_local_directory(str(target))
    assert measure_local_directory(str(alias)) == measured
    require_same_local_directory(str(alias), measured)


@pytest.mark.parametrize("change", ["provider", "volume", "object", "platform", "type"])
def test_foreign_or_changed_expected_identity_is_not_mapped(tmp_path, change):
    measured = measure_local_directory(str(tmp_path))
    physical = measured.physical
    if change == "type":
        expected = {"cwd": measured.cwd}
    elif change == "platform":
        other = (
            PathPlatform.POSIX
            if measured.platform == PathPlatform.WINDOWS
            else PathPlatform.WINDOWS
        )
        expected = replace(measured, platform=other)
    else:
        updates = {
            "provider": {"provider": "caller-invented-proof"},
            "volume": {"volume_id": "different"},
            "object": {"object_id": "different"},
        }
        expected = replace(measured, physical=physical.model_copy(update=updates[change]))
    with pytest.raises(ValueError):
        require_same_local_directory(str(tmp_path), expected)


def test_expected_identity_needs_typed_fields(tmp_path):
    invalid = LocalDirectoryIdentity(str(tmp_path), "windows", {"object_id": "123"})
    with pytest.raises(ValueError, match="expected local directory identity is invalid"):
        require_same_local_directory(str(tmp_path), invalid)
