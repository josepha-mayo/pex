"""Temporary installation directories only; never writes real bridge settings."""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pex_bridge import local_origin_config as config
from pex_bridge.local_origin_config import (
    MAX_LOCAL_ORIGIN_CHOICE_BYTES,
    LocalOriginBindingMismatch,
    LocalOriginConfigError,
    LocalOriginConflict,
    load_local_origin_choice,
    save_local_origin_choice,
)
from pex_bridge.local_workspace import measure_local_directory
from pex_protocol.project_identity import ProjectOrigin
from pydantic import ValidationError


@pytest.fixture
def origin():
    return ProjectOrigin(namespace="local-machine", host="operator-chosen-host")


def _save(path, origin, prior=None, **kwargs):
    return save_local_origin_choice(
        path,
        origin,
        expected_revision=prior.revision if prior else None,
        expected_choice_id=prior.choice_id if prior else None,
        **kwargs,
    )


def test_absent_then_save_roundtrip_and_fresh_incarnation(tmp_path, origin):
    path = tmp_path / "origin.json"
    assert load_local_origin_choice(path) is None
    first = _save(path, origin)
    assert first.revision == 1
    assert UUID(hex=first.choice_id).version == 4
    assert first.origin == origin
    assert first.storage_physical == measure_local_directory(str(tmp_path)).physical
    assert load_local_origin_choice(path) == first
    assert set(json.loads(path.read_bytes())) == {
        "schema",
        "revision",
        "choice_id",
        "origin",
        "storage_physical",
    }
    second = _save(path, origin, first)
    assert second.revision == 2
    assert second.choice_id != first.choice_id
    assert load_local_origin_choice(path) == second
    assert list(tmp_path.iterdir()) == [path]
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_choice_and_nested_origin_are_frozen(tmp_path, origin):
    choice = _save(tmp_path / "origin.json", origin)
    with pytest.raises(ValidationError):
        choice.revision = 4
    with pytest.raises(ValidationError):
        choice.origin.host = "changed"


@pytest.mark.parametrize("revision,choice_id", [(None, None), (1, uuid4().hex), (2, None)])
def test_stale_or_partial_token_never_overwrites(tmp_path, origin, revision, choice_id):
    path = tmp_path / "origin.json"
    _save(path, origin)
    before = path.read_bytes()
    with pytest.raises(LocalOriginConflict):
        save_local_origin_choice(
            path,
            origin,
            expected_revision=revision,
            expected_choice_id=choice_id,
        )
    assert path.read_bytes() == before


def test_delete_reset_does_not_allow_revision_aba(tmp_path, origin):
    path = tmp_path / "origin.json"
    old = _save(path, origin)
    path.rename(tmp_path / "preserved-old.json")
    with pytest.raises(LocalOriginConflict):
        _save(path, origin, old)
    new = _save(path, origin)
    assert new.revision == old.revision == 1
    assert new.choice_id != old.choice_id
    with pytest.raises(LocalOriginConflict):
        _save(path, origin, old)
    assert load_local_origin_choice(path) == new


def test_copied_choice_requires_explicit_exact_reconfirmation(tmp_path, origin):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    old = _save(source / "origin.json", origin)
    path = destination / "origin.json"
    copied = (source / "origin.json").read_bytes()
    path.write_bytes(copied)
    with pytest.raises(LocalOriginBindingMismatch) as error:
        load_local_origin_choice(path)
    assert error.value.choice == old
    with pytest.raises(LocalOriginBindingMismatch):
        _save(path, origin, old)
    with pytest.raises(LocalOriginConflict):
        _save(path, origin, allow_storage_rebind=True)
    assert path.read_bytes() == copied
    new = _save(path, origin, old, allow_storage_rebind=True)
    assert new.revision == old.revision + 1
    assert new.choice_id != old.choice_id
    assert new.storage_physical == measure_local_directory(str(destination)).physical
    assert new.origin == old.origin
    assert load_local_origin_choice(path) == new
    assert load_local_origin_choice(source / "origin.json") == old


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{",
        b"[]",
        b"null",
        b"\xff",
        b'{"x":NaN}',
        b'{"x":1e999}',
        b'{"x":1,"x":2}',
        b" " * (MAX_LOCAL_ORIGIN_CHOICE_BYTES + 1),
    ],
)
def test_corrupt_choice_is_unavailable_never_first_run(tmp_path, origin, raw):
    path = tmp_path / "origin.json"
    path.write_bytes(raw)
    with pytest.raises(LocalOriginConfigError):
        load_local_origin_choice(path)
    with pytest.raises(LocalOriginConfigError):
        _save(path, origin, allow_storage_rebind=True)
    assert path.read_bytes() == raw
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "pex.local-origin-choice.v2"),
        ("revision", True),
        ("revision", "1"),
        ("revision", 0),
        ("revision", -1),
        ("revision", 2**63),
        ("extra", "invalid"),
        ("choice_id", "a" * 32),
        ("choice_id", uuid4().hex.upper()),
        ("origin", {"namespace": "local-machine", "host": "host", "extra": True}),
        ("origin", {"namespace": "local-machine", "host": 42}),
        ("storage_physical", {"provider": "claimed", "volume_id": "1", "object_id": "2"}),
        (
            "storage_physical",
            {
                "provider": "pex-os-stat-windows-v1",
                "volume_id": "1",
                "object_id": "not-measured",
            },
        ),
    ],
)
def test_strict_schema_rejects_malformed_fields(tmp_path, origin, field, value):
    path = tmp_path / "origin.json"
    old = _save(path, origin)
    payload = json.loads(path.read_bytes())
    payload[field] = value
    raw = json.dumps(payload).encode()
    path.write_bytes(raw)
    with pytest.raises(LocalOriginConfigError):
        load_local_origin_choice(path)
    with pytest.raises(LocalOriginConfigError):
        _save(path, origin, old, allow_storage_rebind=True)
    assert path.read_bytes() == raw


def test_missing_schema_is_not_defaulted_when_loading(tmp_path, origin):
    path = tmp_path / "origin.json"
    _save(path, origin)
    payload = json.loads(path.read_bytes())
    del payload["schema"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LocalOriginConfigError):
        load_local_origin_choice(path)


def test_directory_config_and_relative_paths_are_rejected(tmp_path, origin):
    with pytest.raises(LocalOriginConfigError):
        load_local_origin_choice(tmp_path)
    with pytest.raises(LocalOriginConfigError):
        _save(tmp_path, origin)
    with pytest.raises(LocalOriginConfigError):
        load_local_origin_choice(Path("relative.json"))
    missing = tmp_path / "missing" / "origin.json"
    with pytest.raises(LocalOriginConfigError):
        _save(missing, origin)
    assert not missing.parent.exists()


def test_symlink_config_is_rejected_without_touching_target(tmp_path, origin):
    target = tmp_path / "target.json"
    old = _save(target, origin)
    path = tmp_path / "origin.json"
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("host does not grant temporary symlink creation")
    with pytest.raises(LocalOriginConfigError):
        load_local_origin_choice(path)
    with pytest.raises(LocalOriginConfigError):
        _save(path, origin, old, allow_storage_rebind=True)
    assert load_local_origin_choice(target) == old


@pytest.mark.parametrize("operation", ["fsync", "replace"])
def test_write_failure_preserves_original_and_cleans_only_temp(
    tmp_path,
    origin,
    monkeypatch,
    operation,
):
    path = tmp_path / "origin.json"
    old = _save(path, origin)
    before = path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("injected write failure")

    monkeypatch.setattr(config.os, operation, fail)
    with pytest.raises(OSError, match="injected"):
        _save(path, origin, old)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_concurrent_file_change_before_replace_is_preserved(tmp_path, origin, monkeypatch):
    path = tmp_path / "origin.json"
    old = _save(path, origin)
    real_fsync = config.os.fsync

    def change_after_flush(descriptor):
        real_fsync(descriptor)
        path.write_bytes(b"external corrupt change")

    monkeypatch.setattr(config.os, "fsync", change_after_flush)
    with pytest.raises(LocalOriginConfigError):
        _save(path, origin, old)
    assert path.read_bytes() == b"external corrupt change"
    assert list(tmp_path.iterdir()) == [path]


def test_parent_replacement_rejected_before_publication(tmp_path, origin, monkeypatch):
    path = tmp_path / "origin.json"
    old = _save(path, origin)
    elsewhere = tmp_path / "other"
    elsewhere.mkdir()
    original = config._measure_parent
    calls = 0

    def changed_parent(candidate):
        nonlocal calls
        calls += 1
        return (
            original(candidate) if calls == 1 else measure_local_directory(str(elsewhere)).physical
        )

    monkeypatch.setattr(config, "_measure_parent", changed_parent)
    with pytest.raises(LocalOriginConflict):
        _save(path, origin, old)
    assert json.loads(path.read_bytes())["choice_id"] == old.choice_id
    assert sorted(p.name for p in tmp_path.iterdir()) == ["origin.json", "other"]


@pytest.mark.parametrize(
    "revision,choice_id,consent",
    [
        (True, uuid4().hex, False),
        ("1", uuid4().hex, False),
        (None, None, 1),
    ],
)
def test_save_control_types_are_strict(tmp_path, origin, revision, choice_id, consent):
    path = tmp_path / "origin.json"
    with pytest.raises(LocalOriginConfigError):
        save_local_origin_choice(
            path,
            origin,
            expected_revision=revision,
            expected_choice_id=choice_id,
            allow_storage_rebind=consent,
        )
    assert not path.exists()


def test_reparse_regular_mode_is_still_rejected():
    assert not config._regular(SimpleNamespace(st_mode=0o100600, st_file_attributes=0x400))


def test_cross_api_ctime_difference_does_not_reject_stable_file(tmp_path, origin, monkeypatch):
    path = tmp_path / "origin.json"
    old = _save(path, origin)
    actual_fstat = config.os.fstat

    def fstat_with_different_ctime(descriptor):
        info = actual_fstat(descriptor)
        fields = {
            name: getattr(info, name)
            for name in (
                "st_dev",
                "st_ino",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
                "st_mode",
            )
        }
        fields["st_ctime_ns"] = 123
        fields["st_file_attributes"] = getattr(info, "st_file_attributes", 0)
        return SimpleNamespace(**fields)

    monkeypatch.setattr(config.os, "fstat", fstat_with_different_ctime)
    assert load_local_origin_choice(path) == old


def test_post_replace_verification_failure_requires_reload_not_blind_retry(
    tmp_path,
    origin,
    monkeypatch,
):
    path = tmp_path / "origin.json"
    old = _save(path, origin)
    actual_load = config.load_local_origin_choice

    def fail_after_replace(candidate):
        raise OSError("injected post-replace read failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(config, "load_local_origin_choice", fail_after_replace)
        with pytest.raises(OSError, match="post-replace"):
            _save(path, origin, old)
    written = actual_load(path)
    assert written.revision == 2
    assert written.choice_id != old.choice_id
    with pytest.raises(LocalOriginConflict):
        _save(path, origin, old)
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("change", ["same_payload_new_object", "valid_payload_modified_object"])
def test_temporary_publication_requires_owned_object_and_exact_bytes(
    tmp_path, origin, monkeypatch, change,
):
    path = tmp_path / "origin.json"
    old = _save(path, origin)
    original = path.read_bytes()
    real_measure = config._measure_parent
    measurements = 0
    preserved = tmp_path / "preserved-owned-temporary"
    foreign_bytes = None

    def change_closed_temporary(candidate):
        nonlocal measurements, foreign_bytes
        measurements += 1
        measured = real_measure(candidate)
        if measurements == 2:
            temporary, = tmp_path.glob(".origin.json.*.tmp")
            payload = temporary.read_bytes()
            if change == "same_payload_new_object":
                temporary.rename(preserved)
                foreign_bytes = payload
            else:
                parsed = json.loads(payload)
                parsed["origin"]["host"] = "externally-changed-choice"
                foreign_bytes = json.dumps(parsed).encode("utf-8")
            temporary.write_bytes(foreign_bytes)
        return measured

    monkeypatch.setattr(config, "_measure_parent", change_closed_temporary)
    with pytest.raises(LocalOriginConflict, match="temporary file changed"):
        _save(path, origin, old)
    assert path.read_bytes() == original
    assert load_local_origin_choice(path) == old
    if change == "same_payload_new_object":
        assert preserved.is_file()
        temporary, = tmp_path.glob(".origin.json.*.tmp")
        assert temporary.read_bytes() == foreign_bytes
    else:
        assert list(tmp_path.iterdir()) == [path]
