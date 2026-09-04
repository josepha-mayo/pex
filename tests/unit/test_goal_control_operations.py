from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge import store as store_module
from pex_bridge.store import OperatorEffectConflictError, Store
from pex_protocol.goal import Goal
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin

PROJECT_ID = "goal-control-operation-project"
PRINCIPAL_ID = "local_bridge_operator"
ACTOR_ASSURANCE = "bridge_bearer"
NOW = datetime(2026, 9, 1, 18, tzinfo=UTC)
ORIGIN = ProjectOrigin(namespace="machine", host="goal-control-operation-test")


def _goal(
    goal_id: str,
    *,
    objective: str = "Prove atomic goal control operations",
    updated_at: datetime = NOW,
) -> Goal:
    return Goal(
        id=goal_id,
        project_id=PROJECT_ID,
        title="Durable goal control",
        objective=objective,
        acceptance_criteria=["replay is exact", "history is append-only"],
        constraints=["do not infer legacy actor identity"],
        created_at=NOW,
        updated_at=updated_at,
    )


def _create_request(*, objective: str = "Prove atomic goal control operations") -> dict:
    return {
        "project_id": PROJECT_ID,
        "title": "Durable goal control",
        "objective": objective,
        "acceptance_criteria": ["replay is exact", "history is append-only"],
        "constraints": ["do not infer legacy actor identity"],
    }


async def _register(store: Store) -> None:
    await store.register_project_locator(
        legacy_project_id=PROJECT_ID,
        locator=ProjectLocator.path(
            "/workspace/goal-control-operation-project",
            platform=PathPlatform.POSIX,
            origin=ORIGIN,
        ),
    )


async def _operation_count(store: Store) -> int:
    cursor = await store.db.execute("SELECT COUNT(*) FROM goal_control_operations")
    row = await cursor.fetchone()
    assert row is not None
    return int(row[0])


async def _goal_count(store: Store) -> int:
    cursor = await store.db.execute("SELECT COUNT(*) FROM goals")
    row = await cursor.fetchone()
    assert row is not None
    return int(row[0])


@pytest.mark.asyncio
async def test_goal_create_exact_replay_survives_reconnect(tmp_path) -> None:
    path = tmp_path / "pex.sqlite"
    request = _create_request()
    first_store = Store(path)
    await first_store.connect()
    try:
        await _register(first_store)
        first = await first_store.create_goal_with_ledger_receipt(
            _goal("goal-control-first-generated-id"),
            [],
            principal_id=PRINCIPAL_ID,
            actor_assurance=ACTOR_ASSURANCE,
            idempotency_key="goal-create-reconnect-0001",
            request_payload=request,
        )
        assert first.replayed is False
        assert first.operator_operation is not None
        assert await _operation_count(first_store) == 1
    finally:
        await first_store.close()

    replay_store = Store(path)
    await replay_store.connect()
    try:
        replay = await replay_store.create_goal_with_ledger_receipt(
            _goal("goal-control-discarded-retry-id", updated_at=NOW + timedelta(minutes=5)),
            [],
            principal_id=PRINCIPAL_ID,
            actor_assurance=ACTOR_ASSURANCE,
            idempotency_key="goal-create-reconnect-0001",
            request_payload=request,
        )
        assert replay.replayed is True
        assert replay.public() == first.public()
        assert replay.goal.id == "goal-control-first-generated-id"
        assert await replay_store.get_goal("goal-control-discarded-retry-id") is None
        assert await _goal_count(replay_store) == 1
        assert await _operation_count(replay_store) == 1
    finally:
        await replay_store.close()


@pytest.mark.asyncio
async def test_goal_patch_exact_replay_survives_reconnect(tmp_path) -> None:
    path = tmp_path / "pex.sqlite"
    original = _goal("goal-control-patch-reconnect")
    request = {
        "goal_id": original.id,
        "body": {
            "mode": "update",
            "expected_intent_revision": 1,
            "objective": "Committed before reconnect",
        },
    }
    first_store = Store(path)
    await first_store.connect()
    try:
        await _register(first_store)
        await first_store.create_goal_with_ledger(original, [])
        first = await first_store.patch_goal_with_ledger_receipt(
            original,
            original.model_copy(
                update={
                    "objective": "Committed before reconnect",
                    "updated_at": NOW + timedelta(minutes=1),
                }
            ),
            [],
            expected_intent_revision=1,
            principal_id=PRINCIPAL_ID,
            actor_assurance=ACTOR_ASSURANCE,
            idempotency_key="goal-patch-reconnect-0001",
            request_payload=request,
        )
        assert first.replayed is False
        assert first.operator_operation is not None
    finally:
        await first_store.close()

    replay_store = Store(path)
    await replay_store.connect()
    try:
        replay = await replay_store.patch_goal_with_ledger_receipt(
            original,
            original.model_copy(
                update={
                    "objective": "Discarded retry proposal",
                    "updated_at": NOW + timedelta(minutes=2),
                }
            ),
            [],
            expected_intent_revision=1,
            principal_id=PRINCIPAL_ID,
            actor_assurance=ACTOR_ASSURANCE,
            idempotency_key="goal-patch-reconnect-0001",
            request_payload=request,
        )

        assert replay.replayed is True
        assert replay.public() == first.public()
        assert replay.goal.objective == "Committed before reconnect"
        current = await replay_store.get_goal_for_authority(original.id)
        assert current is not None
        assert current.objective == "Committed before reconnect"
        assert await _operation_count(replay_store) == 1
    finally:
        await replay_store.close()


@pytest.mark.asyncio
async def test_concurrent_goal_create_across_stores_commits_once(tmp_path) -> None:
    path = tmp_path / "pex.sqlite"
    first_store = Store(path)
    second_store = Store(path)
    await first_store.connect()
    await second_store.connect()
    try:
        await _register(first_store)
        request = _create_request()
        first, second = await asyncio.gather(
            first_store.create_goal_with_ledger_receipt(
                _goal("goal-control-concurrent-first"),
                [],
                principal_id=PRINCIPAL_ID,
                actor_assurance=ACTOR_ASSURANCE,
                idempotency_key="goal-create-concurrent-0001",
                request_payload=request,
            ),
            second_store.create_goal_with_ledger_receipt(
                _goal(
                    "goal-control-concurrent-second",
                    updated_at=NOW + timedelta(minutes=1),
                ),
                [],
                principal_id=PRINCIPAL_ID,
                actor_assurance=ACTOR_ASSURANCE,
                idempotency_key="goal-create-concurrent-0001",
                request_payload=request,
            ),
        )

        assert {first.replayed, second.replayed} == {False, True}
        assert first.public() == second.public()
        assert first.goal.id == second.goal.id
        assert await _goal_count(first_store) == 1
        assert await _operation_count(second_store) == 1
    finally:
        await second_store.close()
        await first_store.close()


@pytest.mark.asyncio
async def test_receipt_insert_failure_rolls_back_goal_create(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)

        async def reject_operation(*_args, **_kwargs):
            raise RuntimeError("forced goal operation receipt failure")

        monkeypatch.setattr(
            store_module,
            "_insert_goal_control_operation",
            reject_operation,
        )
        with pytest.raises(RuntimeError, match="forced goal operation receipt failure"):
            await store.create_goal_with_ledger_receipt(
                _goal("goal-control-rolled-back"),
                [],
                principal_id=PRINCIPAL_ID,
                actor_assurance=ACTOR_ASSURANCE,
                idempotency_key="goal-create-rollback-0001",
                request_payload=_create_request(),
            )

        assert await store.get_goal("goal-control-rolled-back") is None
        assert await _goal_count(store) == 0
        assert await _operation_count(store) == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_goal_create_same_key_with_different_request_conflicts(tmp_path) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)
        await store.create_goal_with_ledger_receipt(
            _goal("goal-control-key-owner"),
            [],
            principal_id=PRINCIPAL_ID,
            actor_assurance=ACTOR_ASSURANCE,
            idempotency_key="goal-create-conflict-0001",
            request_payload=_create_request(),
        )

        with pytest.raises(
            OperatorEffectConflictError,
            match="idempotency key was reused with different content",
        ):
            await store.create_goal_with_ledger_receipt(
                _goal(
                    "goal-control-key-collision",
                    objective="A different logical request",
                ),
                [],
                principal_id=PRINCIPAL_ID,
                actor_assurance=ACTOR_ASSURANCE,
                idempotency_key="goal-create-conflict-0001",
                request_payload=_create_request(objective="A different logical request"),
            )

        assert await store.get_goal("goal-control-key-owner") is not None
        assert await store.get_goal("goal-control-key-collision") is None
        assert await _goal_count(store) == 1
        assert await _operation_count(store) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_goal_control_operations_are_immutable_and_append_only(tmp_path) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)
        receipt = await store.create_goal_with_ledger_receipt(
            _goal("goal-control-append-only"),
            [],
            principal_id=PRINCIPAL_ID,
            actor_assurance=ACTOR_ASSURANCE,
            idempotency_key="goal-create-append-only-0001",
            request_payload=_create_request(),
        )
        assert receipt.operator_operation is not None
        operation_id = receipt.operator_operation.operation_id

        with pytest.raises(sqlite3.IntegrityError, match="operation is immutable"):
            await store.db.execute(
                "UPDATE goal_control_operations SET committed_at = committed_at "
                "WHERE operation_id = ?",
                (operation_id,),
            )
        await store.db.rollback()

        with pytest.raises(sqlite3.IntegrityError, match="operation is append-only"):
            await store.db.execute(
                "DELETE FROM goal_control_operations WHERE operation_id = ?",
                (operation_id,),
            )
        await store.db.rollback()
        assert await _operation_count(store) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_corrupt_stored_response_fails_closed_without_reexecution(tmp_path) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)
        request = _create_request()
        await store.create_goal_with_ledger_receipt(
            _goal("goal-control-corrupt-owner"),
            [],
            principal_id=PRINCIPAL_ID,
            actor_assurance=ACTOR_ASSURANCE,
            idempotency_key="goal-create-corrupt-0001",
            request_payload=request,
        )
        await store.db.execute("DROP TRIGGER trg_goal_control_operation_immutable")
        await store.db.execute(
            "UPDATE goal_control_operations SET result_hash = ?",
            ("0" * 64,),
        )
        await store.db.commit()

        with pytest.raises(RuntimeError, match="operation receipt is corrupt"):
            await store.create_goal_with_ledger_receipt(
                _goal("goal-control-corrupt-discarded-retry"),
                [],
                principal_id=PRINCIPAL_ID,
                actor_assurance=ACTOR_ASSURANCE,
                idempotency_key="goal-create-corrupt-0001",
                request_payload=request,
            )

        assert await store.get_goal("goal-control-corrupt-owner") is not None
        assert await store.get_goal("goal-control-corrupt-discarded-retry") is None
        assert await _goal_count(store) == 1
        assert await _operation_count(store) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_rehashed_response_with_conflicting_authority_fails_closed(tmp_path) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)
        request = _create_request()
        receipt = await store.create_goal_with_ledger_receipt(
            _goal("goal-control-conflicting-authority"),
            [],
            principal_id=PRINCIPAL_ID,
            actor_assurance=ACTOR_ASSURANCE,
            idempotency_key="goal-create-authority-conflict-0001",
            request_payload=request,
        )
        assert receipt.operator_operation is not None
        cursor = await store.db.execute(
            "SELECT response_json FROM goal_control_operations WHERE operation_id = ?",
            (receipt.operator_operation.operation_id,),
        )
        row = await cursor.fetchone()
        assert row is not None
        response = store_module._strict_json_loads(str(row["response_json"]))
        response["goal_mutation_receipt"]["changed"] = False
        response_json = store_module._canonical_json(response)
        result_hash = store_module.hashlib.sha256(response_json.encode("utf-8")).hexdigest()
        await store.db.execute("DROP TRIGGER trg_goal_control_operation_immutable")
        await store.db.execute(
            "UPDATE goal_control_operations SET response_json = ?, result_hash = ? "
            "WHERE operation_id = ?",
            (response_json, result_hash, receipt.operator_operation.operation_id),
        )
        await store.db.commit()

        with pytest.raises(RuntimeError, match="operation response authority is corrupt"):
            await store.get_goal_control_operation_replay(
                action_kind="goal_create",
                principal_id=PRINCIPAL_ID,
                actor_assurance=ACTOR_ASSURANCE,
                idempotency_key="goal-create-authority-conflict-0001",
                request_payload=request,
            )

        assert await store.get_goal("goal-control-conflicting-authority") is not None
        assert await _goal_count(store) == 1
        assert await _operation_count(store) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_semantic_noop_patch_is_a_replayable_terminal_operation(tmp_path) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)
        original = _goal("goal-control-noop")
        await store.create_goal_with_ledger(original, [])
        request = {
            "mode": "update",
            "expected_intent_revision": 1,
            "objective": original.objective,
        }
        proposal = original.model_copy(update={"updated_at": NOW + timedelta(minutes=1)})
        first = await store.patch_goal_with_ledger_receipt(
            original,
            proposal,
            [],
            expected_intent_revision=1,
            principal_id=PRINCIPAL_ID,
            actor_assurance=ACTOR_ASSURANCE,
            idempotency_key="goal-update-noop-0001",
            request_payload=request,
        )
        replay = await store.patch_goal_with_ledger_receipt(
            original,
            original.model_copy(update={"updated_at": NOW + timedelta(minutes=2)}),
            [],
            expected_intent_revision=1,
            principal_id=PRINCIPAL_ID,
            actor_assurance=ACTOR_ASSURANCE,
            idempotency_key="goal-update-noop-0001",
            request_payload=request,
        )

        assert first.changed is False
        assert first.replayed is False
        assert first.operator_operation is not None
        assert replay.changed is False
        assert replay.replayed is True
        assert replay.public() == first.public()
        assert replay.goal == original
        assert await store.get_goal_for_authority(original.id) == original
        assert await _operation_count(store) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_corrupt_migration_marker_rejects_reconnect(tmp_path) -> None:
    path = tmp_path / "pex.sqlite"
    store = Store(path)
    await store.connect()
    try:
        await store.db.execute("DROP TRIGGER trg_goal_control_operation_migration_immutable")
        await store.db.execute(
            "UPDATE goal_control_operation_migration_state SET json = '{}' "
            "WHERE singleton = 1"
        )
        await store.db.commit()
    finally:
        await store.close()

    reconnect = Store(path)
    with pytest.raises(RuntimeError, match="migration marker is corrupt"):
        await reconnect.connect()
