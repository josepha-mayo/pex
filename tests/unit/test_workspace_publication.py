"""Workspace authority checked by real temporary Store transactions, no workers."""

import json
import os
from datetime import UTC, datetime

import pytest
from pex_bridge import store as store_module
from pex_bridge.local_origin_config import save_local_origin_choice
from pex_bridge.local_workspace import measure_local_directory
from pex_bridge.store import Store
from pex_bridge.workspace_binding import WorkspaceBinding
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.project_identity import ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessEvent, HarnessSession


@pytest.fixture
async def publication(tmp_path, request):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    origin_path = tmp_path / "origin.json"
    origin = save_local_origin_choice(
        origin_path,
        ProjectOrigin(namespace="machine", host="fixture-origin"),
        expected_revision=None,
        expected_choice_id=None,
    )
    directory = measure_local_directory(str(workspace))
    locator = ProjectLocator.path(
        directory.cwd,
        platform=directory.platform,
        origin=origin.origin,
        physical=None if getattr(request, "param", None) == "bare" else directory.physical,
    )
    store = Store(tmp_path / "workspace.sqlite")
    await store.connect()
    project = "selected-project"
    await store.register_project_locator(legacy_project_id=project, locator=locator)
    binding = WorkspaceBinding(
        project_id=project,
        project_binding=await store.project_binding_for_authority(project),
        origin_choice=origin,
        directory=directory,
        locator=locator,
    )
    session = HarnessSession(
        id="codex:workspace-thread",
        vendor_session_id="workspace-thread",
        harness_type=HarnessType.CODEX,
        project_id=project,
        cwd=directory.cwd,
        metadata={
            "workspace_binding": binding.model_dump(mode="json"),
            "subscription_receipt": {"authorization_id": "subscription-1"},
        },
    )
    try:
        yield store, session, binding, origin_path
    finally:
        await store.close()


async def publish(fixture, *, session=None, binding=None, expected_revision=None, fenced=True):
    store, original, workspace, origin_path = fixture
    chosen = workspace if binding is None else binding
    return await store.publish_observer_session(
        original if session is None else session,
        expected_control_revision=expected_revision,
        expected_project_binding=chosen.project_binding,
        expected_workspace=chosen if fenced else None,
        local_origin_path=origin_path if fenced else None,
    )


async def test_valid_selected_workspace_is_published_exactly(publication):
    store, session, binding, _ = publication
    saved = await publish(publication)
    assert saved.metadata["workspace_binding"] == binding.model_dump(mode="json")
    assert await store.get_session(session.id) == saved
    assert saved.last_activity is None
    assert await store.list_interventions(session.id) == []


async def test_new_subscription_preserves_current_human_goal_and_pause(publication):
    store, original, _, _ = publication
    await publish(publication)
    now = datetime.now(UTC)
    goal = Goal(
        id="workspace-goal",
        project_id=original.project_id,
        title="Goal",
        objective="Preserve the current human choice",
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    await store.attach_session_goal(original.id, goal.id, expected_goal_id=None)
    control = await store.get_session_control_state(original.id)
    await store.set_session_supervision_paused(
        original.id,
        paused=True,
        expected_control_revision=control["control_revision"],
    )
    control = await store.get_session_control_state(original.id)
    incoming = original.model_copy(deep=True)
    incoming.metadata["subscription_receipt"]["authorization_id"] = "subscription-2"
    saved = await publish(
        publication,
        session=incoming,
        expected_revision=control["control_revision"],
    )
    assert saved.goal_id == goal.id
    assert saved.supervision_paused is True
    assert saved.last_activity is None


@pytest.mark.parametrize("change", ["remove", "json", "membership", "owner"])
async def test_changed_locator_rejected_under_transaction(publication, change):
    store, session, binding, _ = publication
    fingerprint = binding.locator.fingerprint
    if change == "remove":
        await store.db.execute("DELETE FROM project_locators WHERE fingerprint = ?", (fingerprint,))
    elif change == "json":
        payload = binding.locator.model_dump(mode="json")
        payload["raw"] += "\\"
        await store.db.execute(
            "UPDATE project_locators SET json = ? WHERE fingerprint = ?",
            (json.dumps(payload), fingerprint),
        )
    elif change == "membership":
        identity = (await store.resolve_project_identity(binding.project_id))["identity"]
        payload = identity.model_dump(mode="json")
        payload["locator_fingerprints"] = []
        await store.db.execute(
            "UPDATE project_identities SET json = ? WHERE id = ?",
            (json.dumps(payload), identity.id),
        )
    else:
        other = await store.register_project_locator(
            legacy_project_id="other-project",
            locator=ProjectLocator.opaque("other", origin=binding.origin_choice.origin),
        )
        await store.db.execute(
            "UPDATE project_locators SET project_identity_id = ? WHERE fingerprint = ?",
            (other["identity"].id, fingerprint),
        )
    await store.db.commit()
    with pytest.raises(ValueError):
        await publish(publication)
    assert await store.get_session(session.id) is None


@pytest.mark.parametrize("change", ["project", "binding", "cwd", "metadata"])
async def test_cross_workspace_target_or_snapshot_rejected(publication, change):
    store, original, binding, _ = publication
    session = original.model_copy(deep=True)
    if change == "project":
        session.project_id = "foreign-project"
    elif change == "binding":
        binding = binding.model_copy(update={"project_binding": "legacy:foreign-project"})
        session.metadata["workspace_binding"] = binding.model_dump(mode="json")
    elif change == "cwd":
        session.cwd = str(store.path.parent)
    else:
        session.metadata["workspace_binding"]["project_id"] = "foreign-project"
    with pytest.raises(ValueError):
        await publish(publication, session=session, binding=binding)
    assert await store.get_session(session.id) is None


@pytest.mark.parametrize("change", ["origin", "directory"])
async def test_current_origin_and_directory_rechecked_before_publication(publication, change):
    store, session, binding, origin_path = publication
    if change == "origin":
        save_local_origin_choice(
            origin_path,
            binding.origin_choice.origin,
            expected_revision=binding.origin_choice.revision,
            expected_choice_id=binding.origin_choice.choice_id,
        )
    else:
        directory = origin_path.parent / "workspace"
        directory.rename(origin_path.parent / "preserved-workspace")
        directory.mkdir()
    with pytest.raises(ValueError):
        await publish(publication)
    assert await store.get_session(session.id) is None


async def test_filesystem_check_follows_awaited_identity_reads(publication, monkeypatch):
    store, session, binding, origin_path = publication
    real_snapshot = store_module._project_binding_snapshot
    changed = False

    async def change_origin_after_read(tx, project):
        nonlocal changed
        result = await real_snapshot(tx, project)
        if not changed:
            changed = True
            save_local_origin_choice(
                origin_path,
                binding.origin_choice.origin,
                expected_revision=binding.origin_choice.revision,
                expected_choice_id=binding.origin_choice.choice_id,
            )
        return result

    monkeypatch.setattr(store_module, "_project_binding_snapshot", change_origin_after_read)
    with pytest.raises(ValueError):
        await publish(publication)
    assert changed
    assert await store.get_session(session.id) is None


@pytest.mark.parametrize("lifecycle", [False, True])
async def test_detach_preserves_receipt_when_origin_and_workspace_disappear(publication, lifecycle):
    store, session, binding, origin_path = publication
    await publish(publication)
    control = await store.get_session_control_state(session.id)
    origin_path.rename(origin_path.with_name("preserved-origin.json"))
    (origin_path.parent / "workspace").rename(origin_path.parent / "preserved-workspace")
    detached = session.model_copy(deep=True)
    detached.status = SessionStatus.DETACHED
    detached.capabilities = {"observe_messages": False}
    del detached.metadata["workspace_binding"]
    event = (
        HarnessEvent(
            event_id="workspace-detached",
            ts=datetime.now(UTC),
            harness_type=HarnessType.CODEX,
            session_id=session.id,
            project_id=session.project_id,
            event_type=EventType.STATUS,
            metadata={
                "source": "pex_observer_lifecycle",
                "worker_stopped": False,
                "subscription_id": "subscription-1",
            },
        )
        if lifecycle
        else None
    )
    saved = await store.publish_observer_session(
        detached,
        expected_control_revision=control["control_revision"],
        expected_project_binding=binding.project_binding,
        lifecycle_event=event,
        expected_subscription_id="subscription-1" if lifecycle else None,
    )
    assert saved.status == SessionStatus.DETACHED
    assert saved.metadata["workspace_binding"] == binding.model_dump(mode="json")
    assert saved.metadata["subscription_receipt"] == session.metadata["subscription_receipt"]
    assert saved.last_activity is None
    if lifecycle:
        assert (await store.get_event_processing(event.event_id))["mode"] == "record_only"


@pytest.mark.parametrize("change", ["drop", "change", "new-receipt", "metadata-only-new"])
async def test_workspace_metadata_cannot_replace_authority_without_witness(publication, change):
    store, original, _, _ = publication
    if change != "metadata-only-new":
        await publish(publication)
    before = await store.get_session_control_state(original.id)
    session = original.model_copy(deep=True)
    if change == "drop":
        del session.metadata["workspace_binding"]
    elif change == "change":
        session.metadata["workspace_binding"]["project_id"] = "changed"
    elif change == "new-receipt":
        session.metadata["subscription_receipt"]["authorization_id"] = "different"
    with pytest.raises(ValueError):
        await publish(
            publication,
            session=session,
            fenced=False,
            expected_revision=before["control_revision"] if before else None,
        )
    assert await store.get_session_control_state(original.id) == before


async def test_legacy_exact_directory_allowed_only_without_registered_identity(publication):
    store, original, binding, _ = publication
    project = binding.directory.cwd
    legacy = binding.model_copy(
        update={
            "project_id": project,
            "project_binding": await store.project_binding_for_authority(project),
            "locator": None,
        }
    )
    session = original.model_copy(deep=True)
    session.project_id = project
    session.metadata["workspace_binding"] = legacy.model_dump(mode="json")
    assert (await publish(publication, session=session, binding=legacy)).project_id == project
    await store.register_project_locator(legacy_project_id=project, locator=binding.locator)
    control = await store.get_session_control_state(session.id)
    with pytest.raises(ValueError):
        await publish(
            publication,
            session=session,
            binding=legacy,
            expected_revision=control["control_revision"],
        )


@pytest.mark.parametrize("missing", ["origin_path", "workspace"])
async def test_workspace_arguments_must_be_paired(publication, missing):
    store, session, binding, origin_path = publication
    with pytest.raises(ValueError, match="local origin path"):
        await store.publish_observer_session(
            session,
            expected_control_revision=None,
            expected_project_binding=binding.project_binding,
            expected_workspace=binding if missing == "origin_path" else None,
            local_origin_path=origin_path if missing == "workspace" else None,
        )
    assert await store.get_session(session.id) is None


async def test_same_subscription_cannot_rebind_even_with_new_valid_origin_choice(publication):
    store, session, binding, origin_path = publication
    await publish(publication)
    before = await store.get_session_control_state(session.id)
    new_choice = save_local_origin_choice(
        origin_path,
        binding.origin_choice.origin,
        expected_revision=binding.origin_choice.revision,
        expected_choice_id=binding.origin_choice.choice_id,
    )
    new_binding = binding.model_copy(update={"origin_choice": new_choice})
    incoming = session.model_copy(deep=True)
    incoming.metadata["workspace_binding"] = new_binding.model_dump(mode="json")
    with pytest.raises(ValueError, match="cannot change in place"):
        await publish(
            publication,
            session=incoming,
            binding=new_binding,
            expected_revision=before["control_revision"],
        )
    assert await store.get_session_control_state(session.id) == before
    incoming.metadata["subscription_receipt"]["authorization_id"] = "new-subscription"
    saved = await publish(
        publication,
        session=incoming,
        binding=new_binding,
        expected_revision=before["control_revision"],
    )
    assert saved.metadata["workspace_binding"] == new_binding.model_dump(mode="json")


async def test_existing_alias_cannot_silently_rewrite_exact_workspace_target(publication):
    store, session, binding, _ = publication
    await store.register_project_locator(legacy_project_id="alias", locator=binding.locator)
    bare = session.model_copy(deep=True)
    bare.project_id = "alias"
    del bare.metadata["workspace_binding"]
    await store.upsert_session(bare)
    before = await store.get_session_control_state(session.id)
    with pytest.raises(ValueError, match="stored target differs"):
        await publish(publication, expected_revision=before["control_revision"])
    assert await store.get_session_control_state(session.id) == before


async def test_selected_normalized_cwd_preserves_valid_directory_identity(publication):
    store, original, binding, _ = publication
    session = original.model_copy(deep=True)
    session.cwd = os.path.normcase(binding.directory.cwd)
    await store.upsert_session(session)
    before = await store.get_session_control_state(session.id)
    saved = await publish(
        publication,
        session=session,
        expected_revision=before["control_revision"],
    )
    assert saved.cwd == session.cwd
    assert saved.metadata["workspace_binding"] == binding.model_dump(mode="json")


@pytest.mark.parametrize("publication", ["bare"], indirect=True)
@pytest.mark.parametrize("claim", ["provider", "object"])
@pytest.mark.parametrize("existing_session", [False, True])
async def test_conflicting_physical_locator_added_after_inspection_is_rejected(
    publication,
    claim,
    existing_session,
):
    store, session, binding, _ = publication
    assert binding.locator.physical is None
    if existing_session:
        await publish(publication)
    before = await store.get_session_control_state(session.id)
    physical = binding.directory.physical.model_copy(
        update={
            "provider": "unsupported-provider",
        }
        if claim == "provider"
        else {
            "object_id": str(int(binding.directory.physical.object_id) + 1),
        }
    )
    conflict = ProjectLocator.path(
        binding.directory.cwd,
        platform=binding.directory.platform,
        origin=binding.origin_choice.origin,
        physical=physical,
    )
    await store.register_project_locator(legacy_project_id=binding.project_id, locator=conflict)
    # Lexical merging keeps the same identity ID: a binding-only check misses it.
    assert await store.project_binding_for_authority(binding.project_id) == binding.project_binding
    assert len((await store.resolve_project_identity(binding.project_id))["locators"]) == 2
    with pytest.raises(ValueError, match="conflicting or unsupported physical"):
        await publish(
            publication,
            expected_revision=before["control_revision"] if before else None,
        )
    assert await store.get_session_control_state(session.id) == before


async def test_final_sample_measures_actual_session_cwd_spelling(publication, monkeypatch):
    store, session, binding, _ = publication
    incoming = session.model_copy(deep=True)
    incoming.cwd = os.path.normcase(binding.directory.cwd)
    measured = []

    def different_directory(actual_path, expected):
        measured.append((actual_path, expected))
        raise ValueError("actual session path no longer names selected directory")

    monkeypatch.setattr(store_module, "require_same_local_directory", different_directory)
    with pytest.raises(ValueError, match="actual session path"):
        await publish(publication, session=incoming)
    assert measured == [(incoming.cwd, binding.directory)]
    assert await store.get_session(session.id) is None
