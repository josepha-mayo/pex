from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge.ledger import ledger_projections
from pex_bridge.store import Store, goal_intent_semantic_hash
from pex_protocol.enums import DecisionStatus
from pex_protocol.goal import Goal
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin

ORIGIN = ProjectOrigin(namespace="machine", host="goal-intent-authority-test")
NOW = datetime(2026, 9, 1, 12, tzinfo=UTC)


def _goal(goal_id: str = "goal-intent", *, objective: str = "Build real PEX") -> Goal:
    return Goal(
        id=goal_id,
        project_id="intent-project",
        title="Win honestly",
        objective=objective,
        acceptance_criteria=["real closed-loop evidence"],
        constraints=["no fake benchmark evidence"],
        created_at=NOW,
        updated_at=NOW,
    )


async def _register(store: Store) -> None:
    await store.register_project_locator(
        legacy_project_id="intent-project",
        locator=ProjectLocator.path(
            "/workspace/intent-project",
            platform=PathPlatform.POSIX,
            origin=ORIGIN,
        ),
    )


async def _authority_row(store: Store, goal_id: str) -> dict[str, object]:
    cursor = await store.db.execute(
        "SELECT intent_revision, intent_hash, json FROM goals WHERE id = ?",
        (goal_id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    return dict(row)


@pytest.mark.asyncio
async def test_prospective_goal_revision_tracks_only_semantic_intent(tmp_path) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)
        original = _goal()
        projection = ledger_projections(
            original,
            explicit={"decisions": ["Keep PEX independent"]},
            skip_fields={"decisions"},
        )
        await store.create_goal_with_ledger(original, projection)
        created = await _authority_row(store, original.id)
        assert created["intent_revision"] == 1
        assert created["intent_hash"] == goal_intent_semantic_hash(
            original,
            decisions=[projection[0][0]],
            context_items=[projection[0][1]],
        )

        same_timestamp_only = original.model_copy(
            update={"updated_at": original.updated_at + timedelta(seconds=1)}
        )
        await store.patch_goal_with_ledger(original, same_timestamp_only, [])
        assert await _authority_row(store, original.id) == created

        same_projection = ledger_projections(
            original,
            explicit={"decisions": ["Keep PEX independent"]},
            skip_fields={"decisions"},
        )
        await store.patch_goal_with_ledger(
            original,
            original,
            same_projection,
            replace_ledger_kinds=frozenset({"decision"}),
        )
        assert await _authority_row(store, original.id) == created
        decisions = await store.list_decisions(original.id)
        assert [item.id for item in decisions if item.status.value == "active"] == [
            projection[0][0].id
        ]

        changed = original.model_copy(
            update={
                "objective": "Build and prove the real independent PEX loop",
                "updated_at": original.updated_at + timedelta(seconds=2),
            }
        )
        await store.patch_goal_with_ledger(original, changed, [])
        updated = await _authority_row(store, original.id)
        assert updated["intent_revision"] == 2
        assert updated["intent_hash"] != created["intent_hash"]
        assert await store.get_goal_for_authority(original.id) == changed
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_goal_mutation_receipts_are_transaction_frozen_and_compatibility_holds(
    tmp_path,
) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)
        original = _goal("goal-receipt")
        created = await store.create_goal_with_ledger_receipt(original, [])
        assert created.mode == "create"
        assert created.changed is True
        assert created.before_intent_revision is None
        assert created.after_intent_revision == 1
        assert created.goal == original
        assert created.public()["intent_hash"] == created.after_intent_hash

        proposed_timestamp = original.model_copy(
            update={"updated_at": original.updated_at + timedelta(seconds=1)}
        )
        unchanged = await store.patch_goal_with_ledger_receipt(
            original,
            proposed_timestamp,
            [],
            expected_intent_revision=1,
        )
        assert unchanged.changed is False
        assert unchanged.goal == original
        assert unchanged.before_intent_revision == unchanged.after_intent_revision == 1
        assert unchanged.before_intent_hash == unchanged.after_intent_hash

        first_update = original.model_copy(
            update={
                "objective": "First committed objective",
                "updated_at": original.updated_at + timedelta(seconds=2),
            }
        )
        first = await store.patch_goal_with_ledger_receipt(
            original,
            first_update,
            [],
            expected_intent_revision=1,
        )
        second_update = first_update.model_copy(
            update={
                "objective": "Second committed objective",
                "updated_at": original.updated_at + timedelta(seconds=3),
            }
        )
        assert await store.patch_goal_with_ledger(
            first_update,
            second_update,
            [],
            expected_intent_revision=2,
        ) is None
        assert first.changed is True
        assert first.before_intent_revision == 1
        assert first.after_intent_revision == 2
        assert first.goal.objective == "First committed objective"
        assert first.public()["objective"] == "First committed objective"
        assert (await store.get_goal_for_authority(original.id)).objective == (
            "Second committed objective"
        )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_ledger_only_writers_require_exact_revision_when_supplied(tmp_path) -> None:
    path = tmp_path / "pex.sqlite"
    first = Store(path)
    second = Store(path)
    await first.connect()
    await second.connect()
    try:
        await _register(first)
        goal = _goal("goal-ledger-cas")
        assert await first.create_goal_with_ledger(goal, []) is None
        projection_a = ledger_projections(
            goal,
            explicit={"decisions": ["Writer A wins the exact CAS"]},
            skip_fields={"decisions"},
        )
        projection_b = ledger_projections(
            goal,
            explicit={"decisions": ["Writer B must be rejected as stale"]},
            skip_fields={"decisions"},
        )
        await first.patch_goal_with_ledger(
            goal,
            goal,
            projection_a,
            replace_ledger_kinds=frozenset({"decision"}),
            expected_intent_revision=1,
        )
        with pytest.raises(ValueError, match="intent revision changed"):
            await second.patch_goal_with_ledger(
                goal,
                goal,
                projection_b,
                replace_ledger_kinds=frozenset({"decision"}),
                expected_intent_revision=1,
            )
        active = [
            item.statement
            for item in await first.list_decisions_for_authority(goal.id)
            if item.status.value == "active"
        ]
        assert active == ["Writer A wins the exact CAS"]
        assert (await _authority_row(first, goal.id))["intent_revision"] == 2
    finally:
        await second.close()
        await first.close()


@pytest.mark.asyncio
async def test_managed_goal_ledger_cannot_bypass_atomic_mutation_boundary(tmp_path) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)
        goal = _goal("goal-managed-writer-guard")
        await store.create_goal_with_ledger(goal, [])
        decision, context = ledger_projections(
            goal,
            explicit={"decisions": ["Only the atomic goal boundary may write this"]},
            skip_fields={"decisions"},
        )[0]
        before = await _authority_row(store, goal.id)

        with pytest.raises(ValueError, match="atomic goal mutation boundary"):
            await store.add_decision(decision)
        with pytest.raises(ValueError, match="atomic goal mutation boundary"):
            await store.add_context(context)
        with pytest.raises(ValueError, match="atomic goal mutation boundary"):
            await store.add_decision_context_pair(decision, context)

        decision_count = await store.db.execute("SELECT COUNT(*) AS count FROM decisions")
        context_count = await store.db.execute("SELECT COUNT(*) AS count FROM context_items")
        assert int((await decision_count.fetchone())["count"]) == 0
        assert int((await context_count.fetchone())["count"]) == 0
        assert await _authority_row(store, goal.id) == before
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_retired_managed_goal_ledger_rows_are_append_only_and_immutable(tmp_path) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)
        goal = _goal("goal-retired-history-guard")
        original = ledger_projections(
            goal,
            explicit={"decisions": ["Preserve this retired decision exactly"]},
            skip_fields={"decisions"},
        )
        await store.create_goal_with_ledger(goal, original)
        replacement = ledger_projections(
            goal,
            explicit={"decisions": ["Use the new active decision"]},
            skip_fields={"decisions"},
        )
        await store.patch_goal_with_ledger(
            goal,
            goal,
            replacement,
            replace_ledger_kinds=frozenset({"decision"}),
        )
        retired = next(
            item for item in await store.list_decisions(goal.id) if item.id == original[0][0].id
        )
        retired_context = await store.get_context(original[0][1].id)
        assert retired.status == DecisionStatus.SUPERSEDED
        assert retired_context is not None and retired_context.stale_after is not None

        reactivated = retired.model_copy(
            update={
                "status": DecisionStatus.ACTIVE,
                "metadata": {"kind": "decision"},
            }
        )
        with pytest.raises(sqlite3.IntegrityError, match="managed decision is immutable"):
            await store.db.execute(
                "UPDATE decisions SET json = ? WHERE id = ?",
                (reactivated.model_dump_json(), retired.id),
            )
        await store.db.rollback()

        reactivated_context = retired_context.model_copy(
            update={
                "stale_after": None,
                "metadata": {
                    **retired_context.metadata,
                    "status": DecisionStatus.ACTIVE.value,
                    "superseded_at": None,
                },
            }
        )
        with pytest.raises(sqlite3.IntegrityError, match="managed context is immutable"):
            await store.db.execute(
                "UPDATE context_items SET json = ? WHERE id = ?",
                (reactivated_context.model_dump_json(), retired_context.id),
            )
        await store.db.rollback()

        with pytest.raises(sqlite3.IntegrityError, match="managed decision is append-only"):
            await store.db.execute("DELETE FROM decisions WHERE id = ?", (retired.id,))
        await store.db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="managed context is append-only"):
            await store.db.execute(
                "DELETE FROM context_items WHERE id = ?",
                (retired_context.id,),
            )
        await store.db.rollback()

        assert await store.get_context(retired_context.id) == retired_context
        assert next(
            item for item in await store.list_decisions(goal.id) if item.id == retired.id
        ) == retired
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_managed_goal_ledger_rejects_direct_rewrite_and_superseded_parent_insert(
    tmp_path,
) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)
        parent = _goal("goal-managed-trigger-parent")
        projection = ledger_projections(
            parent,
            explicit={"decisions": ["Keep the bound statement"]},
            skip_fields={"decisions"},
        )
        await store.create_goal_with_ledger(parent, projection)
        decision = projection[0][0]
        rewritten = decision.model_copy(update={"statement": "Hostile rewritten statement"})
        with pytest.raises(sqlite3.IntegrityError, match="managed decision is immutable"):
            await store.db.execute(
                "UPDATE decisions SET json = ? WHERE id = ?",
                (rewritten.model_dump_json(), decision.id),
            )
        await store.db.rollback()

        successor = _goal(
            "goal-managed-trigger-successor",
            objective="A real successor objective",
        ).model_copy(update={"supersedes": parent.id})
        await store.supersede_goal(parent.id, successor)
        injected = ledger_projections(
            parent,
            explicit={"decisions": ["Injected after supersede"]},
            skip_fields={"decisions"},
        )[0][0]
        row_cursor = await store.db.execute(
            "SELECT project_id, project_binding FROM goals WHERE id = ?",
            (parent.id,),
        )
        row = await row_cursor.fetchone()
        assert row is not None
        with pytest.raises(sqlite3.IntegrityError, match="live parent goal"):
            await store.db.execute(
                "INSERT INTO decisions(id, goal_id, project_id, project_binding, json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    injected.id,
                    parent.id,
                    row["project_id"],
                    row["project_binding"],
                    injected.model_dump_json(),
                ),
            )
        await store.db.rollback()

        stored = next(
            item
            for item in await store.list_decisions(parent.id)
            if item.id == decision.id
        )
        assert stored == decision
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_legacy_migration_baselines_valid_goal_and_quarantines_malformed(tmp_path) -> None:
    path = tmp_path / "pex.sqlite"
    first = Store(path)
    await first.connect()
    await first.close()

    goal = _goal("goal-legacy")
    projection = ledger_projections(
        goal,
        explicit={"decisions": ["Preserve real evidence"]},
        skip_fields={"decisions"},
    )[0]
    connection = sqlite3.connect(path)
    try:
        triggers = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND "
            "(name LIKE 'trg_goals_%' OR name LIKE 'trg_decisions_%' OR "
            "name LIKE 'trg_context_items_%')"
        ).fetchall()
        for (trigger,) in triggers:
            connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        connection.execute("DROP TABLE goal_intent_migration_state")
        connection.execute("DROP TABLE context_goal_id_migration_state")
        connection.execute(
            "INSERT INTO goals(id, json) VALUES (?, ?)",
            (goal.id, goal.model_dump_json()),
        )
        connection.execute(
            "INSERT INTO goals(id, json) VALUES (?, ?)",
            ("goal-malformed", "{}"),
        )
        connection.execute(
            "INSERT INTO decisions(id, goal_id, json) VALUES (?, ?, ?)",
            (projection[0].id, goal.id, projection[0].model_dump_json()),
        )
        connection.execute(
            "INSERT INTO context_items(id, project_id, json) VALUES (?, ?, ?)",
            (projection[1].id, goal.project_id, projection[1].model_dump_json()),
        )
        connection.commit()
    finally:
        connection.close()

    restarted = Store(path)
    await restarted.connect()
    try:
        valid = await _authority_row(restarted, goal.id)
        assert valid["intent_revision"] == 0
        assert valid["intent_hash"] == goal_intent_semantic_hash(
            goal,
            decisions=[projection[0]],
            context_items=[projection[1]],
        )
        malformed = await _authority_row(restarted, "goal-malformed")
        assert malformed["intent_revision"] is None
        assert malformed["intent_hash"] is None
        listed = await restarted.list_goal_intent_views_page()
        assert [row["id"] for row in listed] == [goal.id]
        with pytest.raises(
            ValueError,
            match="goal intent authority is quarantined",
        ):
            await restarted.get_goal_intent_view("goal-malformed")
    finally:
        await restarted.close()

    again = Store(path)
    await again.connect()
    try:
        assert await _authority_row(again, goal.id) == valid
    finally:
        await again.close()


@pytest.mark.asyncio
async def test_legacy_successor_chain_preserves_unknown_revision_zero_lineage(tmp_path) -> None:
    path = tmp_path / "pex.sqlite"
    first = Store(path)
    await first.connect()
    await first.close()
    parent = _goal("goal-legacy-parent")
    successor = _goal("goal-legacy-successor").model_copy(
        update={"supersedes": parent.id}
    )
    connection = sqlite3.connect(path)
    try:
        triggers = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND "
            "name LIKE 'trg_goal%'"
        ).fetchall()
        for (trigger,) in triggers:
            connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        connection.execute("DROP TABLE goal_intent_migration_state")
        connection.execute("DROP TABLE context_goal_id_migration_state")
        connection.execute(
            "INSERT INTO goals(id, json) VALUES (?, ?), (?, ?)",
            (
                parent.id,
                parent.model_dump_json(),
                successor.id,
                successor.model_dump_json(),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    migrated = Store(path)
    await migrated.connect()
    try:
        assert (await _authority_row(migrated, parent.id))["intent_revision"] == 0
        assert (await _authority_row(migrated, successor.id))["intent_revision"] == 0
        assert await migrated.has_goal_successor_for_authority(parent.id) is True
    finally:
        await migrated.close()


@pytest.mark.asyncio
async def test_corrupt_goal_intent_migration_boundary_fails_reconnect(tmp_path) -> None:
    path = tmp_path / "pex.sqlite"
    store = Store(path)
    await store.connect()
    await store.close()
    connection = sqlite3.connect(path)
    try:
        for trigger in (
            "trg_goal_intent_migration_state_immutable",
            "trg_goal_intent_migration_state_no_delete",
            "trg_goal_intent_migration_state_singleton",
        ):
            connection.execute(f"DROP TRIGGER {trigger}")
        connection.execute(
            "UPDATE goal_intent_migration_state SET json = ? WHERE singleton = 1",
            ('{"schema":"forged"}',),
        )
        connection.commit()
    finally:
        connection.close()

    restarted = Store(path)
    with pytest.raises(RuntimeError, match="migration boundary is corrupt"):
        await restarted.connect()


@pytest.mark.asyncio
async def test_prospective_goal_insert_trigger_enforces_revision_class(tmp_path) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)
        parent = _goal("goal-trigger-parent")
        await store.create_goal_with_ledger(parent, [])
        row_cursor = await store.db.execute(
            "SELECT project_binding FROM goals WHERE id = ?",
            (parent.id,),
        )
        binding = str((await row_cursor.fetchone())["project_binding"])

        independent = _goal("goal-trigger-independent")
        with pytest.raises(sqlite3.IntegrityError, match="authority is required"):
            await store.db.execute(
                "INSERT INTO goals(id, project_id, project_binding, intent_revision, "
                "intent_hash, json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    independent.id,
                    independent.project_id,
                    binding,
                    0,
                    goal_intent_semantic_hash(independent),
                    independent.model_dump_json(),
                ),
            )
        await store.db.rollback()

        successor = _goal("goal-trigger-successor").model_copy(
            update={"supersedes": parent.id}
        )
        with pytest.raises(sqlite3.IntegrityError, match="authority is required"):
            await store.db.execute(
                "INSERT INTO goals(id, project_id, project_binding, intent_revision, "
                "intent_hash, json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    successor.id,
                    successor.project_id,
                    binding,
                    99,
                    goal_intent_semantic_hash(successor),
                    successor.model_dump_json(),
                ),
            )
        await store.db.rollback()
        assert await store.get_goal(parent.id) == parent
        assert await store.get_goal(independent.id) is None
        assert await store.get_goal(successor.id) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_same_binding_successor_corruption_fails_authority_closed(tmp_path) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)
        parent = _goal("goal-corrupt-successor-parent")
        await store.create_goal_with_ledger(parent, [])
        successor = _goal("goal-corrupt-successor-child").model_copy(
            update={
                "objective": "A real successor with a stronger objective",
                "supersedes": parent.id,
            }
        )
        await store.supersede_goal(parent.id, successor)
        row = await _authority_row(store, successor.id)
        forged = "f" * 64 if row["intent_hash"] != "f" * 64 else "e" * 64
        await store.db.execute(
            "UPDATE goals SET intent_revision = ?, intent_hash = ? WHERE id = ?",
            (int(row["intent_revision"]) + 1, forged, successor.id),
        )
        await store.db.commit()
        with pytest.raises(RuntimeError, match="corrupt"):
            await store.has_goal_successor_for_authority(parent.id)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_partial_legacy_intent_pair_fails_reconnect_closed(tmp_path) -> None:
    path = tmp_path / "pex.sqlite"
    store = Store(path)
    await store.connect()
    try:
        await _register(store)
        goal = _goal("goal-partial")
        await store.upsert_goal(goal)
    finally:
        await store.close()

    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "DROP TRIGGER IF EXISTS trg_goals_intent_update"
        )
        connection.execute(
            "UPDATE goals SET intent_hash = NULL WHERE id = ?",
            (goal.id,),
        )
        connection.commit()
    finally:
        connection.close()

    restarted = Store(path)
    with pytest.raises(RuntimeError, match="partially bound"):
        await restarted.connect()


@pytest.mark.asyncio
async def test_complete_intent_pair_erasure_cannot_rebaseline_on_reconnect(tmp_path) -> None:
    path = tmp_path / "pex.sqlite"
    store = Store(path)
    await store.connect()
    try:
        await _register(store)
        goal = _goal("goal-erased")
        await store.upsert_goal(goal)
    finally:
        await store.close()

    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TRIGGER IF EXISTS trg_goals_intent_update")
        connection.execute(
            "UPDATE goals SET intent_revision = NULL, intent_hash = NULL WHERE id = ?",
            (goal.id,),
        )
        connection.commit()
    finally:
        connection.close()

    restarted = Store(path)
    with pytest.raises(RuntimeError, match="erased after migration"):
        await restarted.connect()


@pytest.mark.asyncio
async def test_goal_intent_triggers_reject_direct_history_rewrites(tmp_path) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)
        goal = _goal("goal-trigger")
        await store.upsert_goal(goal)
        row = await _authority_row(store, goal.id)

        with pytest.raises(sqlite3.IntegrityError, match="intent update is inconsistent"):
            await store.db.execute(
                "UPDATE goals SET json = ? WHERE id = ?",
                (
                    goal.model_copy(update={"objective": "forged"}).model_dump_json(),
                    goal.id,
                ),
            )
        await store.db.rollback()

        with pytest.raises(sqlite3.IntegrityError, match="intent update is inconsistent"):
            await store.db.execute(
                "UPDATE goals SET intent_revision = intent_revision + 1 WHERE id = ?",
                (goal.id,),
            )
        await store.db.rollback()

        with pytest.raises(sqlite3.IntegrityError, match="history cannot be deleted"):
            await store.db.execute("DELETE FROM goals WHERE id = ?", (goal.id,))
        await store.db.rollback()

        with pytest.raises(sqlite3.IntegrityError, match="identity is immutable"):
            await store.db.execute(
                "UPDATE goals SET id = ? WHERE id = ?",
                ("goal-renamed", goal.id),
            )
        await store.db.rollback()

        other = _goal("goal-trigger-other")
        await store.upsert_goal(other)
        with pytest.raises(sqlite3.IntegrityError, match="identity is immutable"):
            await store.db.execute(
                "UPDATE OR REPLACE goals SET id = ? WHERE id = ?",
                (other.id, goal.id),
            )
        await store.db.rollback()
        assert await store.get_goal(goal.id) == goal
        assert await store.get_goal(other.id) == other

        with pytest.raises(sqlite3.IntegrityError, match="identity already exists"):
            await store.db.execute(
                "INSERT OR REPLACE INTO goals(id, project_id, project_binding, "
                "intent_revision, intent_hash, json) SELECT id, project_id, "
                "project_binding, intent_revision, intent_hash, json FROM goals WHERE id = ?",
                (goal.id,),
            )
        await store.db.rollback()
        assert await _authority_row(store, goal.id) == row
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_authority_loader_recomputes_hash_after_scalar_forgery(tmp_path) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register(store)
        goal = _goal("goal-forged-hash")
        await store.upsert_goal(goal)
        await store.db.execute(
            "UPDATE goals SET intent_revision = intent_revision + 1, intent_hash = ? "
            "WHERE id = ?",
            ("0" * 64, goal.id),
        )
        await store.db.commit()
        with pytest.raises(RuntimeError, match="intent hash is corrupt"):
            await store.get_goal_for_authority(goal.id)
    finally:
        await store.close()
