from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pex_protocol.project_identity import (
    PathPlatform,
    PhysicalIdentityProof,
    ProjectIdentity,
    ProjectLocator,
    ProjectOrigin,
    same_project_locator,
)

LOCAL = ProjectOrigin(namespace="machine", host="workstation-a")
OTHER = ProjectOrigin(namespace="machine", host="workstation-b")


def _posix(raw: str, *, origin: ProjectOrigin = LOCAL, physical=None):
    return ProjectLocator.path(
        raw,
        platform=PathPlatform.POSIX,
        origin=origin,
        physical=physical,
    )


def _windows(raw: str, *, origin: ProjectOrigin = LOCAL):
    return ProjectLocator.path(
        raw,
        platform=PathPlatform.WINDOWS,
        origin=origin,
    )


def test_posix_lexical_identity_preserves_backslash_case_space_and_unicode():
    pairs = [
        ("/tmp/a\\b", "/tmp/a/b"),
        ("/tmp/Foo", "/tmp/foo"),
        ("/tmp/a ", "/tmp/a"),
        ("/tmp/ß", "/tmp/ss"),
    ]
    for left_raw, right_raw in pairs:
        left = _posix(left_raw)
        right = _posix(right_raw)
        assert left.raw == left_raw
        assert not same_project_locator(left, right)
        assert left.fingerprint != right.fingerprint


def test_windows_lexical_identity_is_explicit_and_drive_absolute():
    assert same_project_locator(_windows(r"C:\Repo\.\src\.."), _windows("c:/repo"))
    assert _windows("C:\\").canonical == "c:/"
    for ambiguous in ["C:", "C:repo", "repo", r"\\server"]:
        with pytest.raises(ValueError):
            _windows(ambiguous)
    with pytest.raises(ValueError, match="trailing dot or space"):
        _windows(r"C:\repo\ambiguous. ")
    assert same_project_locator(
        _windows(r"\\SERVER\Share\Repo"),
        _windows(r"\\server\share\repo"),
    )
    assert not same_project_locator(
        _windows(r"\\?\C:\Repo"),
        _windows(r"C:\Repo"),
    )
    for invalid_device in [r"\\?\X", r"\\?\GLOBALROOT\Device\Volume"]:
        with pytest.raises(ValueError, match="device project path"):
            _windows(invalid_device)
    assert same_project_locator(
        _windows(r"\\server\share\..\other"),
        _windows(r"\\server\share\other"),
    )


def test_same_spelling_on_two_machines_is_not_the_same_project():
    assert not same_project_locator(
        _posix("/srv/work", origin=LOCAL),
        _posix("/srv/work", origin=OTHER),
    )


def test_physical_proof_can_establish_alias_without_rewriting_raw_locator():
    proof = PhysicalIdentityProof(
        provider="windows-file-id",
        volume_id="volume-4",
        object_id="object-99",
    )
    first = _posix("/mnt/repo", physical=proof)
    alias = _posix("/worktrees/repo-link", physical=proof)
    assert first.fingerprint != alias.fingerprint
    assert same_project_locator(first, alias)
    assert not same_project_locator(first, _posix("/mnt/repo", origin=OTHER, physical=proof))


def test_conflicting_physical_proofs_never_merge_the_same_lexical_path():
    first = PhysicalIdentityProof(provider="posix-stat", volume_id="dev-1", object_id="ino-1")
    replacement = PhysicalIdentityProof(
        provider="posix-stat",
        volume_id="dev-2",
        object_id="ino-2",
    )
    original = _posix("/work/repo", physical=first)
    moved_target = _posix("/work/repo", physical=replacement)
    assert original.fingerprint != moved_target.fingerprint
    assert not same_project_locator(original, moved_target)


def test_remote_provider_and_opaque_locators_keep_origin_and_exact_ids():
    cloud_a = ProjectOrigin(namespace="provider", host="tenant-a")
    cloud_b = ProjectOrigin(namespace="provider", host="tenant-b")
    first = ProjectLocator.provider_workspace("workspace-7", origin=cloud_a)
    trailing = ProjectLocator.provider_workspace("workspace-7 ", origin=cloud_a)
    other_tenant = ProjectLocator.provider_workspace("workspace-7", origin=cloud_b)
    opaque = ProjectLocator.opaque("opaque\\id", origin=cloud_a)
    assert not same_project_locator(first, trailing)
    assert not same_project_locator(first, other_tenant)
    assert opaque.canonical == "opaque\\id"
    assert not same_project_locator(
        ProjectLocator.provider_workspace(
            "workspace-7",
            origin=ProjectOrigin(namespace="provider", host="Tenant-A"),
        ),
        first,
    )


def test_repository_uri_has_typed_origin_without_erasing_path_case():
    canonical = ProjectLocator.repository("https://GitHub.COM:443/Org/Repo.git")
    same = ProjectLocator.repository("https://github.com/Org/Repo.git")
    different_case = ProjectLocator.repository("https://github.com/org/repo.git")
    assert same_project_locator(canonical, same)
    assert not same_project_locator(canonical, different_case)
    assert ProjectLocator.repository("https://[::1]/Org/Repo").canonical == (
        "https://[::1]/Org/Repo"
    )
    for invalid in [
        "https://user@github.com/Org/Repo",
        "https://github.com/Org/Repo?ref=main",
        "file:///tmp/repo",
    ]:
        with pytest.raises(ValueError):
            ProjectLocator.repository(invalid)


def test_workspace_set_is_order_independent_but_rejects_duplicate_members():
    first = _posix("/workspace/a")
    second = _posix("/workspace/b")
    left = ProjectLocator.workspace_set([first, second], origin=LOCAL)
    right = ProjectLocator.workspace_set([second, first], origin=LOCAL)
    assert same_project_locator(left, right)
    with pytest.raises(ValueError, match="duplicate"):
        ProjectLocator.workspace_set([first, first], origin=LOCAL)


def test_extended_windows_paths_do_not_invent_dot_segment_equivalence():
    with pytest.raises(ValueError, match="dot segment"):
        _windows(r"\\?\C:\a\..\b")


def test_canonical_value_cannot_be_forged_and_identity_id_is_random():
    locator = _posix("/workspace/project")
    payload = locator.model_dump(mode="json")
    payload["canonical"] = "/workspace/other"
    with pytest.raises(ValueError, match="does not match"):
        ProjectLocator.model_validate(payload)

    now = datetime.now(UTC)
    first = ProjectIdentity.create([locator], now=now)
    second = ProjectIdentity.create([locator], now=now)
    assert first.id != second.id
    assert first.locator_fingerprints == second.locator_fingerprints
    assert first.locator_fingerprints == (locator.fingerprint,)
    assert locator.model_dump(mode="json")["schema"] == "pex.project-locator.v2"
    assert first.model_dump(mode="json")["schema"] == "pex.project-identity.v2"
