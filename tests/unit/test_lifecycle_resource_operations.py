from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pex_bridge.store import ProjectIdentityBlockedError, Store, utcnow
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.enums import (
    Authority,
    HarnessType,
    PolicyVerdict,
    SessionStatus,
)
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.project_identity import (
    PathPlatform,
    ProjectLocator,
    ProjectOrigin,
)
from pex_protocol.session import HarnessSession

ORIGIN = ProjectOrigin(namespace="machine", host="cleanup-operation-test-host")


def _locator(path: Path) -> ProjectLocator:
    return ProjectLocator.path(
        str(path.resolve()),
        platform=PathPlatform.WINDOWS if os.name == "nt" else PathPlatform.POSIX,
        origin=ORIGIN,
    )


async def _seed(
    store: Store,
    tmp_path: Path,
    *,
    suffix: str,
) -> tuple[Goal, HarnessSession, Path]:
    project = tmp_path / f"project-{suffix}"
    project.mkdir(parents=True, exist_ok=True)
    await store.register_project_locator(
        legacy_project_id=str(project),
        locator=_locator(project),
    )
    now = datetime.now(UTC)
    goal = Goal(
        id=f"goal-{suffix}",
        project_id=str(project),
        title="Quarantine one exact registered resource",
        objective="Keep cleanup authority bound to one filesystem entity.",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id=f"synthetic:cleanup-{suffix}",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id=f"vendor-cleanup-{suffix}",
        project_id=str(project),
        cwd=str(project),
        goal_id=goal.id,
        status=SessionStatus.STOPPED,
        capabilities=AdapterCapabilities().model_dump(mode="json"),
    )
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    return goal, session, project


def _cleanup_intervention(
    session: HarnessSession,
    resource_ids: list[str],
    *,
    suffix: str,
) -> Intervention:
    action = ProposedAction(
        type=InterventionType.CLEANUP,
        session_id=session.id,
        goal_id=session.goal_id,
        payload={"mode": "quarantine", "resource_ids": resource_ids},
        rationale="Quarantine the exact stopped-session residue.",
        evidence=[f"cleanup:{suffix}"],
        confidence=1.0,
        risk=RiskLevel.MEDIUM,
        reversible=True,
        authority_required=Authority.HUMAN,
    )
    return Intervention(
        id=f"int-cleanup-{suffix}",
        session_id=session.id,
        goal_id=session.goal_id,
        trigger="status",
        evidence=action.evidence,
        diagnosis="cleanup_requires_exact_manifest",
        proposed_action=action,
        confidence=1.0,
        risk=RiskLevel.MEDIUM.value,
        reversible=True,
        authority_required=Authority.HUMAN.value,
        action_taken=InterventionType.CLEANUP.value,
        policy_verdict=PolicyVerdict.ASK_HUMAN,
        result="awaiting_human",
        created_at=utcnow(),
    )


async def _ready_resource(
    store: Store,
    session: HarnessSession,
    project: Path,
    *,
    suffix: str,
) -> tuple[dict, Path]:
    source = project / "scratch" / f"artifact-{suffix}.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("recoverable", encoding="utf-8")
    resource = await store.register_lifecycle_resource(
        session_id=session.id,
        path=source,
        scope_root=project,
        kind="scratch",
        created_by="lifecycle-operation-test",
        resource_id=f"resource-{suffix}",
        metadata={"bounded": True},
    )
    ready = await store.mark_lifecycle_resource_cleanup_ready(
        resource_id=resource["id"],
        session_id=session.id,
        evidence=["source_session_stopped", "artifact_is_disposable"],
        expected_version=resource["version"],
    )
    return ready, source


async def _reserved_operation(
    store: Store,
    tmp_path: Path,
    *,
    suffix: str,
) -> tuple[Goal, HarnessSession, dict, Path, Intervention, dict]:
    goal, session, project = await _seed(store, tmp_path, suffix=suffix)
    resource, source = await _ready_resource(
        store,
        session,
        project,
        suffix=suffix,
    )
    intervention = _cleanup_intervention(session, [resource["id"]], suffix=suffix)
    await store.add_intervention(intervention)
    created, _ = await store.reserve_lifecycle_resolution(
        intervention_id=intervention.id,
        session_id=session.id,
        decision="allow",
        started_at=utcnow(),
    )
    assert created is True
    dispatch = await store.start_lifecycle_resolution_dispatch(intervention.id)
    assert dispatch["granted"] is True
    reserved = await store.reserve_cleanup_operation(intervention.id)
    assert reserved["created"] is True
    return goal, session, resource, source, intervention, reserved["operation"]


@pytest.mark.asyncio
async def test_bound_resource_blocks_rebind_but_forensic_read_survives(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        _, session, project = await _seed(store, tmp_path, suffix="rebind")
        resource, _ = await _ready_resource(
            store,
            session,
            project,
            suffix="rebind",
        )
        replacement = tmp_path / "replacement-project"
        replacement.mkdir()
        conflict = await store.register_project_locator(
            legacy_project_id=str(project),
            locator=_locator(replacement),
        )
        assert conflict["outcome"] == "quarantined"
        await store.resolve_project_identity_conflict(
            resolution_id="resolve-resource-to-b",
            legacy_project_id=str(project),
            selected_identity_id=conflict["identity"].id,
            resolved_by="test_operator",
            rationale="Exercise resource creation-time binding.",
        )

        assert await store.get_lifecycle_resource(resource["id"]) == resource
        with pytest.raises(ProjectIdentityBlockedError, match="identity changed"):
            await store.get_lifecycle_resource_for_authority(resource["id"])
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_historical_resource_remains_unbound_and_forensic_only(tmp_path):
    path = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE lifecycle_resources (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
        "state TEXT NOT NULL, json TEXT NOT NULL);"
    )
    connection.execute(
        "INSERT INTO lifecycle_resources(id, session_id, state, json) VALUES (?, ?, ?, ?)",
        (
            "legacy-resource",
            "legacy-session",
            "active",
            '{"id":"legacy-resource","session_id":"legacy-session","state":"active"}',
        ),
    )
    connection.commit()
    connection.close()

    store = Store(path)
    await store.connect()
    try:
        forensic = await store.get_lifecycle_resource("legacy-resource")
        assert forensic is not None and forensic["state"] == "active"
        with pytest.raises(ProjectIdentityBlockedError, match="immutable project identity"):
            await store.get_lifecycle_resource_for_authority("legacy-resource")
        row = await (
            await store.db.execute(
                "SELECT project_binding, entity_fingerprint FROM lifecycle_resources "
                "WHERE id = 'legacy-resource'"
            )
        ).fetchone()
        assert row["project_binding"] is None
        assert row["entity_fingerprint"] is None
        with pytest.raises(sqlite3.IntegrityError, match="cannot be reauthorized"):
            await store.db.execute(
                "UPDATE lifecycle_resources SET project_binding = 'identity:forged' "
                "WHERE id = 'legacy-resource'"
            )
        await store.db.rollback()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_ready_rejects_stale_version_and_same_path_replacement(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        _, session, project = await _seed(store, tmp_path, suffix="stale")
        source = project / "artifact.txt"
        source.write_text("first", encoding="utf-8")
        resource = await store.register_lifecycle_resource(
            session_id=session.id,
            path=source,
            scope_root=project,
            kind="scratch",
            created_by="stale-test",
            resource_id="resource-stale",
        )
        with pytest.raises(ValueError, match="version changed"):
            await store.mark_lifecycle_resource_cleanup_ready(
                resource_id=resource["id"],
                session_id=session.id,
                evidence=["stale"],
                expected_version=resource["version"] + 1,
            )

        replacement = project / "replacement.txt"
        replacement.write_text("replacement", encoding="utf-8")
        os.replace(replacement, source)
        with pytest.raises(PermissionError, match="entity was replaced"):
            await store.mark_lifecycle_resource_cleanup_ready(
                resource_id=resource["id"],
                session_id=session.id,
                evidence=["replacement must not inherit authority"],
                expected_version=resource["version"],
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_registration_rejects_symlink_or_reparse_resource(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        _, session, project = await _seed(store, tmp_path, suffix="symlink")
        target = project / "target.txt"
        target.write_text("target", encoding="utf-8")
        link = project / "link.txt"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("symlink creation is not supported for this test account")
        with pytest.raises(ValueError, match="symlink|reparse"):
            await store.register_lifecycle_resource(
                session_id=session.id,
                path=link,
                scope_root=project,
                kind="scratch",
                created_by="symlink-test",
                resource_id="resource-symlink",
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_reserve_and_start_freeze_exact_manifest_and_grant_once(tmp_path):
    path = tmp_path / "pex.sqlite"
    first = Store(path, process_boot_id="cleanup-race-boot")
    await first.connect()
    _, _, resource, source, intervention, operation = await _reserved_operation(
        first,
        tmp_path,
        suffix="race",
    )
    second = Store(path, process_boot_id="cleanup-race-boot")
    await second.connect()
    try:
        original_action = intervention.proposed_action.model_dump(mode="json")
        manifest = operation["manifest"]
        assert [entry["resource_id"] for entry in manifest] == [resource["id"]]
        assert manifest[0]["resource_version"] == resource["version"]
        assert manifest[0]["source_path"] == str(source.resolve())
        assert operation["action_hash"]
        with pytest.raises(sqlite3.IntegrityError, match="binding is immutable"):
            await first.db.execute(
                "UPDATE lifecycle_operations SET json = json_set(json, '$.project_id', ?) "
                "WHERE id = ?",
                ("different-project", operation["id"]),
            )
        await first.db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="binding is immutable"):
            await first.db.execute(
                "UPDATE lifecycle_operation_resources SET json = "
                "json_set(json, '$.source_path', ?) WHERE operation_id = ?",
                ("different-source", operation["id"]),
            )
        await first.db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="binding is immutable"):
            await first.db.execute(
                "UPDATE lifecycle_operations SET state = 'completed', version = 1, json = "
                "json_set(json, '$.state', 'completed', '$.version', 1) WHERE id = ?",
                (operation["id"],),
            )
        await first.db.rollback()

        results = await asyncio.gather(
            first.start_cleanup_operation(operation["id"]),
            second.start_cleanup_operation(operation["id"]),
        )
        assert sum(result["granted"] is True for result in results) == 1
        assert sum(result["granted"] is False for result in results) == 1
        staged = await first.get_lifecycle_resource(resource["id"])
        assert staged is not None
        assert staged["state"] == "quarantining"
        assert staged["current_operation_id"] == operation["id"]
        assert staged["quarantine_path"] == manifest[0]["destination_path"]
        stored_intervention = await first.get_intervention(intervention.id)
        assert stored_intervention is not None
        assert stored_intervention.proposed_action.model_dump(mode="json") == original_action
    finally:
        await second.close()
        await first.close()


@pytest.mark.asyncio
async def test_resource_scalar_json_tamper_is_rejected_by_schema(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        _, session, project = await _seed(store, tmp_path, suffix="tamper")
        resource, _ = await _ready_resource(
            store,
            session,
            project,
            suffix="tamper",
        )
        with pytest.raises(sqlite3.IntegrityError, match="binding is immutable"):
            await store.db.execute(
                "UPDATE lifecycle_resources SET project_id = ? WHERE id = ?",
                ("different-project", resource["id"]),
            )
        await store.db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="binding is required"):
            await store.db.execute(
                "INSERT INTO lifecycle_resources(id, session_id, state, json) "
                "VALUES ('raw-omission', ?, 'active', ?)",
                (
                    session.id,
                    '{"id":"raw-omission","session_id":"synthetic",'
                    '"state":"active"}',
                ),
            )
        await store.db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="binding is immutable"):
            await store.db.execute(
                "UPDATE lifecycle_resources SET json = json_set(json, '$.session_id', ?) "
                "WHERE id = ?",
                ("different-session", resource["id"]),
            )
        await store.db.rollback()
    finally:
        await store.close()


@pytest.mark.parametrize("observed", ["not_moved", "moved", "conflict"])
@pytest.mark.asyncio
async def test_restart_classifies_interrupted_cleanup_without_replay(tmp_path, observed: str):
    path = tmp_path / f"{observed}.sqlite"
    first = Store(path, process_boot_id=f"before-{observed}")
    await first.connect()
    _, _, resource, source, intervention, operation = await _reserved_operation(
        first,
        tmp_path,
        suffix=f"recovery-{observed}",
    )
    started = await first.start_cleanup_operation(operation["id"])
    assert started["granted"] is True
    destination = Path(operation["manifest"][0]["destination_path"])
    if observed == "moved":
        destination.parent.mkdir(parents=True)
        os.replace(source, destination)
    elif observed == "conflict":
        destination.parent.mkdir(parents=True)
        destination.write_text("unrelated", encoding="utf-8")
    await first.close()

    recovered = Store(path, process_boot_id=f"after-{observed}")
    await recovered.connect()
    try:
        current_operation = await recovered.get_cleanup_operation(operation["id"])
        current_resource = await recovered.get_lifecycle_resource(resource["id"])
        resolution = await recovered.get_lifecycle_resolution(intervention.id)
        stored_intervention = await recovered.get_intervention(intervention.id)
        assert current_operation is not None and current_resource is not None
        assert resolution is not None and stored_intervention is not None
        assert resolution["downstream_operation_id"] == operation["id"]
        assert stored_intervention.metadata["lifecycle_resolution"] == resolution
        assert stored_intervention.proposed_action == intervention.proposed_action
        if observed == "not_moved":
            assert current_operation["state"] == "failed"
            assert current_resource["state"] == "cleanup_ready"
            assert resolution["status"] == "failed"
            assert resolution["delivery_result"] == "cleanup_not_moved:1"
            assert stored_intervention.result == "cleanup_not_moved:1"
            assert stored_intervention.outcome == "human_lifecycle_delivery_failed"
            assert source.exists() and not destination.exists()
        elif observed == "moved":
            assert current_operation["state"] == "completed"
            assert current_resource["state"] == "quarantined"
            assert resolution["status"] == "delivered"
            assert resolution["delivery_result"] == "cleanup_quarantined:1"
            assert stored_intervention.result == "cleanup_quarantined:1"
            assert stored_intervention.outcome == "human_lifecycle_delivered"
            assert not source.exists() and destination.exists()
        else:
            assert current_operation["state"] == "conflict"
            assert current_resource["state"] == "conflict"
            assert resolution["status"] == "delivery_uncertain"
            assert resolution["delivery_result"] == "cleanup_delivery_uncertain:conflict:1"
            assert stored_intervention.result == "cleanup_delivery_uncertain:conflict:1"
            assert stored_intervention.outcome == "human_lifecycle_delivery_uncertain"
            assert source.exists() and destination.exists()
        replay = await recovered.start_cleanup_operation(operation["id"])
        assert replay["granted"] is False
    finally:
        await recovered.close()


@pytest.mark.asyncio
async def test_restart_reserved_cleanup_child_is_inert_and_parent_is_not_started(tmp_path):
    path = tmp_path / "reserved.sqlite"
    first = Store(path, process_boot_id="before-reserved")
    await first.connect()
    _, _, _, source, intervention, operation = await _reserved_operation(
        first,
        tmp_path,
        suffix="recovery-reserved",
    )
    destination = Path(operation["manifest"][0]["destination_path"])
    await first.close()

    recovered = Store(path, process_boot_id="after-reserved")
    await recovered.connect()
    try:
        current_operation = await recovered.get_cleanup_operation(operation["id"])
        resolution = await recovered.get_lifecycle_resolution(intervention.id)
        stored_intervention = await recovered.get_intervention(intervention.id)
        assert current_operation is not None
        assert current_operation["state"] == "reserved"
        assert resolution is not None
        assert resolution["status"] == "failed"
        assert resolution["delivery_result"] == "cleanup_not_started:1"
        assert resolution["downstream_operation_id"] == operation["id"]
        assert stored_intervention is not None
        assert stored_intervention.result == "cleanup_not_started:1"
        assert stored_intervention.outcome == "human_lifecycle_delivery_failed"
        assert source.exists() and not destination.exists()
        with pytest.raises(PermissionError, match="parent grant changed"):
            await recovered.start_cleanup_operation(operation["id"])
    finally:
        await recovered.close()


@pytest.mark.asyncio
async def test_restart_corrupt_cleanup_child_link_makes_parent_uncertain(tmp_path):
    path = tmp_path / "corrupt-child.sqlite"
    first = Store(path, process_boot_id="before-corrupt-child")
    await first.connect()
    _, _, _, source, intervention, operation = await _reserved_operation(
        first,
        tmp_path,
        suffix="recovery-corrupt-child",
    )
    destination = Path(operation["manifest"][0]["destination_path"])
    await first.close()

    connection = sqlite3.connect(path)
    connection.execute("DROP TRIGGER trg_lifecycle_operations_bound_update")
    connection.execute(
        "UPDATE lifecycle_operations SET json = json_set(json, '$.action_hash', ?) "
        "WHERE id = ?",
        ("forged-action-hash", operation["id"]),
    )
    connection.commit()
    connection.close()

    recovered = Store(path, process_boot_id="after-corrupt-child")
    await recovered.connect()
    try:
        resolution = await recovered.get_lifecycle_resolution(intervention.id)
        stored_intervention = await recovered.get_intervention(intervention.id)
        assert resolution is not None
        assert resolution["status"] == "delivery_uncertain"
        assert resolution["delivery_result"] == (
            "cleanup_delivery_uncertain:operation_corrupt"
        )
        assert resolution["downstream_operation_id"] == operation["id"]
        assert stored_intervention is not None
        assert stored_intervention.result == "cleanup_delivery_uncertain:operation_corrupt"
        assert stored_intervention.outcome == "human_lifecycle_delivery_uncertain"
        assert source.exists() and not destination.exists()
    finally:
        await recovered.close()


@pytest.mark.asyncio
async def test_connect_failure_closes_partial_database_connection(tmp_path, monkeypatch):
    store = Store(tmp_path / "pex.sqlite")

    async def fail_migration() -> None:
        raise RuntimeError("synthetic migration failure")

    monkeypatch.setattr(store, "_migrate_lifecycle_resource_operations", fail_migration)
    with pytest.raises(RuntimeError, match="synthetic migration failure"):
        await store.connect()
    assert store._db is None
