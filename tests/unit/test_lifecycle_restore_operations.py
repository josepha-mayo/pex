from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from pex_bridge.store import (
    ProjectIdentityBlockedError,
    Store,
    _intervention_action_hash,
    _lifecycle_observed_fingerprint,
    utcnow,
)

from tests.unit.test_lifecycle_resource_operations import (
    _cleanup_intervention,
    _locator,
    _ready_resource,
    _seed,
)


async def _quarantined_cleanup(
    store: Store,
    tmp_path: Path,
    *,
    suffix: str,
    resource_count: int = 1,
) -> tuple[dict[str, Any], list[dict[str, Any]], Any, Any]:
    goal, session, project = await _seed(store, tmp_path, suffix=suffix)
    resources: list[dict[str, Any]] = []
    for index in range(resource_count):
        resource, _ = await _ready_resource(
            store,
            session,
            project,
            suffix=f"{suffix}-{index}",
        )
        resources.append(resource)
    intervention = _cleanup_intervention(
        session,
        [str(resource["id"]) for resource in resources],
        suffix=suffix,
    )
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
    cleanup = reserved["operation"]
    started = await store.start_cleanup_operation(cleanup["id"])
    assert started["granted"] is True
    cleanup_outcomes: list[dict[str, Any]] = []
    for entry in cleanup["manifest"]:
        source = Path(entry["source_path"])
        destination = Path(entry["destination_path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)
        cleanup_outcomes.append(
            {
                "resource_id": entry["resource_id"],
                "outcome": "moved",
                "source_fingerprint": None,
                "destination_fingerprint": entry["entity_fingerprint"],
            }
        )
    finalized = await store.finalize_cleanup_operation(
        cleanup["id"],
        outcomes=cleanup_outcomes,
    )
    assert finalized["operation"]["state"] == "completed"

    resolution = await store.get_lifecycle_resolution(intervention.id)
    assert resolution is not None
    resolution.update(
        {
            "status": "delivered",
            "delivery_result": f"cleanup_quarantined:{resource_count}",
            "finished_at": utcnow().isoformat(),
        }
    )
    intervention.result = resolution["delivery_result"]
    intervention.outcome = "human_lifecycle_delivered"
    intervention.metadata["lifecycle_resolution"] = resolution
    await store.finalize_lifecycle_resolution(
        intervention,
        session,
        resolution,
        record_type="human_lifecycle_resolved",
    )
    return cleanup, resources, intervention, session


def _observed_outcome(entry: dict[str, Any]) -> dict[str, Any]:
    source = _lifecycle_observed_fingerprint(Path(entry["source_path"]))
    destination = _lifecycle_observed_fingerprint(Path(entry["destination_path"]))
    expected = entry["entity_fingerprint"]
    outcome = (
        "not_restored"
        if source == expected and destination is None
        else "restored"
        if source is None and destination == expected
        else "conflict"
    )
    return {
        "resource_id": entry["resource_id"],
        "outcome": outcome,
        "source_fingerprint": source,
        "destination_fingerprint": destination,
    }


@pytest.mark.asyncio
async def test_historical_restore_row_remains_unbound_and_forensic_only(tmp_path):
    path = tmp_path / "legacy-restore.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE lifecycle_restore_operations (id TEXT PRIMARY KEY, state TEXT NOT NULL, "
        "version INTEGER NOT NULL DEFAULT 0, json TEXT NOT NULL);"
        "CREATE TABLE lifecycle_restore_operation_resources (operation_id TEXT NOT NULL, "
        "resource_id TEXT NOT NULL, ordinal INTEGER NOT NULL, version INTEGER NOT NULL "
        "DEFAULT 0, json TEXT NOT NULL);"
    )
    connection.execute(
        "INSERT INTO lifecycle_restore_operations(id, state, version, json) VALUES (?, ?, 0, ?)",
        (
            "legacy-restore-operation",
            "failed",
            '{"id":"legacy-restore-operation","state":"failed","version":0}',
        ),
    )
    connection.commit()
    connection.close()

    store = Store(path)
    await store.connect()
    try:
        forensic = await store.get_restore_operation("legacy-restore-operation")
        assert forensic is not None and forensic["state"] == "failed"
        row = await (
            await store.db.execute(
                "SELECT project_binding, request_hash FROM lifecycle_restore_operations "
                "WHERE id = 'legacy-restore-operation'"
            )
        ).fetchone()
        assert row["project_binding"] is None and row["request_hash"] is None
        with pytest.raises(ProjectIdentityBlockedError):
            await store.get_restore_operation_for_authority("legacy-restore-operation")
        with pytest.raises(sqlite3.IntegrityError, match="cannot be reauthorized"):
            await store.db.execute(
                "UPDATE lifecycle_restore_operations SET project_binding = 'identity:forged' "
                "WHERE id = 'legacy-restore-operation'"
            )
        await store.db.rollback()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restore_success_is_atomic_idempotent_and_path_free_in_intervention(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="restore-success")
    await store.connect()
    try:
        cleanup, resources, intervention, session = await _quarantined_cleanup(
            store,
            tmp_path,
            suffix="success",
        )
        original_action = intervention.proposed_action.model_dump(mode="json")
        original_hash = _intervention_action_hash(intervention)
        reserved = await store.reserve_restore_operation(
            intervention.id,
            authorized_by="operator:alice",
            idempotency_key="restore-success-1",
        )
        assert reserved["created"] is True and reserved["replayed"] is False
        replay = await store.reserve_restore_operation(
            intervention.id,
            authorized_by="operator:alice",
            idempotency_key="restore-success-1",
        )
        assert replay["created"] is False and replay["replayed"] is True
        assert replay["operation"]["id"] == reserved["operation"]["id"]
        entry = reserved["operation"]["manifest"][0]
        assert entry["cleanup_operation_id"] == cleanup["id"]
        assert entry["cleanup_resource_version"] == cleanup["manifest"][0][
            "resource_version"
        ]
        assert entry["cleanup_readiness_fingerprint"] == cleanup["manifest"][0][
            "readiness_fingerprint"
        ]
        started = await store.start_restore_operation(reserved["operation"]["id"])
        assert started["granted"] is True
        os.replace(Path(entry["source_path"]), Path(entry["destination_path"]))
        finalized = await store.finalize_restore_operation(
            reserved["operation"]["id"],
            outcomes=[_observed_outcome(entry)],
        )
        assert finalized["finalized"] is True and finalized["replayed"] is False
        assert finalized["operation"]["state"] == "completed"
        terminal_replay = await store.finalize_restore_operation(
            reserved["operation"]["id"],
            outcomes=[_observed_outcome(entry)],
        )
        assert terminal_replay["finalized"] is False
        assert terminal_replay["replayed"] is True

        resource = await store.get_lifecycle_resource(resources[0]["id"])
        stored_intervention = await store.get_intervention(intervention.id)
        assert resource is not None and stored_intervention is not None
        assert resource["state"] == "active"
        assert resource["current_operation_id"] is None
        assert resource["readiness_fingerprint"] is None
        assert resource["cleanup_ready_at"] is None
        assert resource["cleanup_ready_evidence"] == []
        assert stored_intervention.proposed_action.model_dump(mode="json") == original_action
        assert _intervention_action_hash(stored_intervention) == original_hash
        assert stored_intervention.result == "cleanup_restored:1"
        assert stored_intervention.outcome == "cleanup_restored_by_operator"
        receipt = stored_intervention.metadata["undo_receipt"]
        assert receipt["operation_id"] == reserved["operation"]["id"]
        assert "path" not in str(receipt).lower()
        audit = await (
            await store.db.execute(
                "SELECT record_type FROM intervention_audit WHERE intervention_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (intervention.id,),
            )
        ).fetchone()
        assert audit is not None and audit["record_type"] == "cleanup_restore_completed"
        with pytest.raises((PermissionError, RuntimeError)):
            await store.reserve_restore_operation(
                intervention.id,
                authorized_by="operator:alice",
                idempotency_key="restore-after-active",
            )

        conflict_path = tmp_path / "success-rebound"
        conflict_path.mkdir()
        conflict = await store.register_project_locator(
            legacy_project_id=str(session.project_id),
            locator=_locator(conflict_path),
        )
        await store.resolve_project_identity_conflict(
            resolution_id="resolve-terminal-restore-to-b",
            legacy_project_id=str(session.project_id),
            selected_identity_id=conflict["identity"].id,
            resolved_by="test_operator",
            rationale="Terminal receipt replay must not reacquire filesystem authority.",
        )
        terminal_receipt = await store.reserve_restore_operation(
            intervention.id,
            authorized_by="operator:alice",
            idempotency_key="restore-success-1",
        )
        assert terminal_receipt["created"] is False
        assert terminal_receipt["replayed"] is True
        assert terminal_receipt["operation"]["state"] == "completed"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restore_occupied_original_creates_no_operation_then_allows_retry(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        cleanup, _, intervention, _ = await _quarantined_cleanup(
            store,
            tmp_path,
            suffix="occupied",
        )
        original = Path(cleanup["manifest"][0]["source_path"])
        original.write_text("occupied", encoding="utf-8")
        with pytest.raises(PermissionError, match="occupied"):
            await store.reserve_restore_operation(
                intervention.id,
                authorized_by="operator:alice",
                idempotency_key="occupied-1",
            )
        assert await store.list_restore_operations() == []
        original.unlink()
        reserved = await store.reserve_restore_operation(
            intervention.id,
            authorized_by="operator:alice",
            idempotency_key="occupied-1",
        )
        assert reserved["created"] is True
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restore_rebind_and_quarantine_replacement_block_authority(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        cleanup, _, intervention, session = await _quarantined_cleanup(
            store,
            tmp_path,
            suffix="binding",
        )
        reserved = await store.reserve_restore_operation(
            intervention.id,
            authorized_by="operator:alice",
            idempotency_key="binding-1",
        )
        source = Path(reserved["operation"]["manifest"][0]["source_path"])
        replacement = source.with_name("replacement.tmp")
        replacement.write_text("replacement", encoding="utf-8")
        os.replace(replacement, source)
        with pytest.raises(PermissionError, match="filesystem authority changed"):
            await store.start_restore_operation(reserved["operation"]["id"])

        conflict_path = tmp_path / "different-project"
        conflict_path.mkdir()
        conflict = await store.register_project_locator(
            legacy_project_id=str(session.project_id),
            locator=_locator(conflict_path),
        )
        await store.resolve_project_identity_conflict(
            resolution_id="resolve-restore-to-b",
            legacy_project_id=str(session.project_id),
            selected_identity_id=conflict["identity"].id,
            resolved_by="test_operator",
            rationale="Exercise restore creation-time binding.",
        )
        with pytest.raises(ProjectIdentityBlockedError):
            await store.get_restore_operation_for_authority(reserved["operation"]["id"])
        with pytest.raises(ProjectIdentityBlockedError):
            await store.reserve_restore_operation(
                intervention.id,
                authorized_by="operator:alice",
                idempotency_key="binding-2",
            )
        assert await store.get_restore_operation(reserved["operation"]["id"]) is not None
        assert cleanup["id"] == reserved["operation"]["cleanup_operation_id"]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restore_start_race_and_idempotency_scope(tmp_path):
    path = tmp_path / "pex.sqlite"
    first = Store(path, process_boot_id="restore-race")
    await first.connect()
    cleanup, _, intervention, _ = await _quarantined_cleanup(
        first,
        tmp_path,
        suffix="race",
    )
    same = await first.reserve_restore_operation(
        intervention.id,
        authorized_by="operator:alice",
        idempotency_key="same-key",
    )
    replay = await first.reserve_restore_operation(
        intervention.id,
        authorized_by="operator:alice",
        idempotency_key="same-key",
    )
    different = await first.reserve_restore_operation(
        intervention.id,
        authorized_by="operator:alice",
        idempotency_key="different-key",
    )
    other_principal = await first.reserve_restore_operation(
        intervention.id,
        authorized_by="operator:bob",
        idempotency_key="same-key",
    )
    assert replay["operation"]["id"] == same["operation"]["id"]
    assert different["operation"]["id"] != same["operation"]["id"]
    assert other_principal["operation"]["id"] != same["operation"]["id"]
    assert same["operation"]["cleanup_operation_id"] == cleanup["id"]
    second = Store(path, process_boot_id="restore-race")
    await second.connect()
    try:
        results = await asyncio.gather(
            first.start_restore_operation(same["operation"]["id"]),
            second.start_restore_operation(same["operation"]["id"]),
        )
        assert sum(result["granted"] is True for result in results) == 1
        assert sum(result["granted"] is False for result in results) == 1
        with pytest.raises((PermissionError, RuntimeError)):
            await first.start_restore_operation(different["operation"]["id"])
    finally:
        await second.close()
        await first.close()


@pytest.mark.asyncio
async def test_restore_incomplete_outcomes_do_not_overwrite_state(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        _, resources, intervention, _ = await _quarantined_cleanup(
            store,
            tmp_path,
            suffix="partial",
            resource_count=2,
        )
        reserved = await store.reserve_restore_operation(
            intervention.id,
            authorized_by="operator:alice",
            idempotency_key="partial-1",
        )
        started = await store.start_restore_operation(reserved["operation"]["id"])
        assert started["granted"] is True
        with pytest.raises(ValueError, match="incomplete"):
            await store.finalize_restore_operation(
                reserved["operation"]["id"],
                outcomes=[_observed_outcome(started["manifest"][0])],
            )
        operation = await store.get_restore_operation(reserved["operation"]["id"])
        assert operation is not None and operation["state"] == "dispatching"
        for resource in resources:
            current = await store.get_lifecycle_resource(resource["id"])
            assert current is not None and current["state"] == "restoring"
    finally:
        await store.close()


@pytest.mark.parametrize("observed", ["restored", "not_restored", "conflict"])
@pytest.mark.asyncio
async def test_restore_restart_classifies_without_replay(tmp_path, observed: str):
    path = tmp_path / f"{observed}.sqlite"
    first = Store(path, process_boot_id=f"restore-before-{observed}")
    await first.connect()
    _, resources, intervention, _ = await _quarantined_cleanup(
        first,
        tmp_path,
        suffix=f"restart-{observed}",
    )
    reserved = await first.reserve_restore_operation(
        intervention.id,
        authorized_by="operator:alice",
        idempotency_key=f"restart-{observed}",
    )
    started = await first.start_restore_operation(reserved["operation"]["id"])
    entry = started["manifest"][0]
    source = Path(entry["source_path"])
    destination = Path(entry["destination_path"])
    if observed == "restored":
        os.replace(source, destination)
    elif observed == "conflict":
        destination.write_text("unrelated", encoding="utf-8")
    await first.close()

    recovered = Store(path, process_boot_id=f"restore-after-{observed}")
    await recovered.connect()
    try:
        operation = await recovered.get_restore_operation(reserved["operation"]["id"])
        resource = await recovered.get_lifecycle_resource(resources[0]["id"])
        stored_intervention = await recovered.get_intervention(intervention.id)
        assert operation is not None and resource is not None and stored_intervention is not None
        if observed == "restored":
            assert operation["state"] == "completed"
            assert resource["state"] == "active"
            assert not source.exists() and destination.exists()
            assert stored_intervention.result == "cleanup_restored:1"
        elif observed == "not_restored":
            assert operation["state"] == "failed"
            assert resource["state"] == "quarantined"
            assert source.exists() and not destination.exists()
            assert stored_intervention.result == "cleanup_restore_not_restored:1"
        else:
            assert operation["state"] == "conflict"
            assert resource["state"] == "conflict"
            assert source.exists() and destination.exists()
            assert stored_intervention.result == "cleanup_restore_conflict:1"
        assert stored_intervention.metadata["restore_operation_id"] == operation["id"]
        assert "path" not in str(stored_intervention.metadata["undo_receipt"]).lower()
    finally:
        await recovered.close()


@pytest.mark.asyncio
async def test_restore_schema_tamper_and_legacy_updater_are_blocked(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        _, resources, intervention, _ = await _quarantined_cleanup(
            store,
            tmp_path,
            suffix="tamper",
        )
        reserved = await store.reserve_restore_operation(
            intervention.id,
            authorized_by="operator:alice",
            idempotency_key="tamper-1",
        )
        operation_id = reserved["operation"]["id"]
        with pytest.raises(sqlite3.IntegrityError, match="binding is immutable"):
            await store.db.execute(
                "UPDATE lifecycle_restore_operations SET json = json_set(json, "
                "'$.project_id', 'forged') WHERE id = ?",
                (operation_id,),
            )
        await store.db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="binding is immutable"):
            await store.db.execute(
                "UPDATE lifecycle_restore_operation_resources SET json = json_set(json, "
                "'$.cleanup_resource_version', 999) WHERE operation_id = ?",
                (operation_id,),
            )
        await store.db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="binding is immutable"):
            await store.db.execute(
                "UPDATE lifecycle_restore_operations SET state = 'completed', version = 1, "
                "json = json_set(json, '$.state', 'completed', '$.version', 1) WHERE id = ?",
                (operation_id,),
            )
        await store.db.rollback()
        with pytest.raises(PermissionError, match="generic lifecycle resource updates"):
            await store.update_lifecycle_resources([resources[0]])
        current = await store.get_lifecycle_resource(resources[0]["id"])
        assert current is not None and current["state"] == "quarantined"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restore_requires_existing_original_parent(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        cleanup, _, intervention, _ = await _quarantined_cleanup(
            store,
            tmp_path,
            suffix="missing-parent",
        )
        original_parent = Path(cleanup["manifest"][0]["source_path"]).parent
        original_parent.rmdir()
        with pytest.raises(FileNotFoundError):
            await store.reserve_restore_operation(
                intervention.id,
                authorized_by="operator:alice",
                idempotency_key="missing-parent-1",
            )
        assert await store.list_restore_operations() == []
        original_parent.mkdir()
        reserved = await store.reserve_restore_operation(
            intervention.id,
            authorized_by="operator:alice",
            idempotency_key="missing-parent-2",
        )
        original_parent.rmdir()
        with pytest.raises(FileNotFoundError):
            await store.start_restore_operation(reserved["operation"]["id"])
    finally:
        await store.close()
