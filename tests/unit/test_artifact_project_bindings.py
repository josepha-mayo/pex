from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge.store import (
    ProjectIdentityBlockedError,
    Store,
    goal_intent_semantic_hash,
)
from pex_protocol.context import ContextItem
from pex_protocol.enums import (
    ContextKind,
    DecisionSource,
    DecisionStatus,
    HarnessType,
    Sensitivity,
    SessionStatus,
    SourceKind,
)
from pex_protocol.goal import Decision, Goal
from pex_protocol.project_identity import (
    PathPlatform,
    PhysicalIdentityProof,
    ProjectLocator,
    ProjectOrigin,
)
from pex_protocol.session import HarnessSession

MACHINE = ProjectOrigin(namespace="machine", host="artifact-binding-test")


def _path(
    raw: str,
    *,
    physical: PhysicalIdentityProof | None = None,
) -> ProjectLocator:
    return ProjectLocator.path(
        raw,
        platform=PathPlatform.POSIX,
        origin=MACHINE,
        physical=physical,
    )


def _goal(goal_id: str, project_id: str) -> Goal:
    now = datetime.now(UTC)
    return Goal(
        id=goal_id,
        project_id=project_id,
        title=goal_id,
        objective=f"Keep {goal_id} bound to its creation-time project.",
        created_at=now,
        updated_at=now,
    )


def _pair(goal: Goal, *, project_id: str | None = None) -> tuple[Decision, ContextItem]:
    now = datetime.now(UTC)
    decision = Decision(
        id=f"decision-{goal.id}",
        goal_id=goal.id,
        statement="Preserve the immutable project boundary.",
        rationale="A durable decision must not move when a legacy key is rebound.",
        source=DecisionSource.HUMAN,
        status=DecisionStatus.ACTIVE,
        created_at=now,
    )
    context = ContextItem(
        id=f"context-{goal.id}",
        project_id=project_id or goal.project_id,
        goal_id=goal.id,
        kind=ContextKind.DECISION,
        content=decision.statement,
        source_refs=[decision.id],
        provenance=SourceKind.HUMAN,
        confidence=1.0,
        relevance_tags=["decision"],
        valid_from=now,
        sensitivity=Sensitivity.INTERNAL,
        metadata={"decision_id": decision.id},
    )
    return decision, context


def _legacy_binding(project_id: str) -> str:
    return f"legacy:{hashlib.sha256(project_id.encode('utf-8')).hexdigest()}"


async def _resolve_same_key_to_second_identity(store: Store, project_id: str) -> None:
    await store.register_project_locator(
        legacy_project_id=project_id,
        locator=_path(f"/workspace/{project_id}/a"),
    )
    second = await store.register_project_locator(
        legacy_project_id=project_id,
        locator=_path(f"/workspace/{project_id}/b"),
    )
    assert second["outcome"] == "quarantined"
    await store.resolve_project_identity_conflict(
        resolution_id=f"resolve-{project_id}",
        legacy_project_id=project_id,
        selected_identity_id=second["identity"].id,
        resolved_by="artifact-binding-test",
        rationale="Select the second deliberately distinct test workspace.",
    )


@pytest.mark.asyncio
async def test_historical_rows_backfill_legacy_even_when_key_is_already_typed(tmp_path):
    path = tmp_path / "pex.sqlite"
    project_id = "already-typed-history"
    first = Store(path)
    await first.connect()
    await first.register_project_locator(
        legacy_project_id=project_id,
        locator=_path("/workspace/already-typed-history"),
    )
    await first.close()

    goal = _goal("goal-already-typed-history", project_id)
    decision, context = _pair(goal)
    connection = sqlite3.connect(path)
    try:
        artifact_triggers = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' "
            "AND (name LIKE 'trg_goals_%' OR name LIKE 'trg_decisions_%' "
            "OR name LIKE 'trg_context_items_%')"
        ).fetchall()
        for (trigger,) in artifact_triggers:
            connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        connection.execute("DROP TABLE goal_intent_migration_state")
        connection.execute("DROP TABLE context_goal_id_migration_state")
        connection.execute(
            "INSERT INTO goals(id, json) VALUES (?, ?)",
            (goal.id, goal.model_dump_json()),
        )
        connection.execute(
            "INSERT INTO decisions(id, goal_id, json) VALUES (?, ?, ?)",
            (decision.id, decision.goal_id, decision.model_dump_json()),
        )
        connection.execute(
            "INSERT INTO context_items(id, project_id, json) VALUES (?, ?, ?)",
            (context.id, context.project_id, context.model_dump_json()),
        )
        connection.commit()
    finally:
        connection.close()

    restarted = Store(path)
    await restarted.connect()
    try:
        expected = _legacy_binding(project_id)
        goal_row = await restarted.db.execute(
            "SELECT project_id, project_binding FROM goals WHERE id = ?",
            (goal.id,),
        )
        decision_row = await restarted.db.execute(
            "SELECT project_id, project_binding FROM decisions WHERE id = ?",
            (decision.id,),
        )
        context_row = await restarted.db.execute(
            "SELECT project_id, project_binding, goal_id FROM context_items WHERE id = ?",
            (context.id,),
        )
        assert dict(await goal_row.fetchone()) == {
            "project_id": project_id,
            "project_binding": expected,
        }
        assert dict(await decision_row.fetchone()) == {
            "project_id": project_id,
            "project_binding": expected,
        }
        assert dict(await context_row.fetchone()) == {
            "project_id": project_id,
            "project_binding": expected,
            "goal_id": goal.id,
        }

        assert await restarted.get_goal(goal.id) == goal
        assert await restarted.list_context(project_id) == [context]
        assert await restarted.list_decisions(goal.id) == [decision]
        with pytest.raises(ProjectIdentityBlockedError) as goal_block:
            await restarted.get_goal_for_authority(goal.id)
        assert goal_block.value.code == "artifact_project_identity_changed"
        with pytest.raises(ProjectIdentityBlockedError):
            await restarted.list_context_for_authority(project_id, goal_id=goal.id)
        with pytest.raises(ProjectIdentityBlockedError):
            await restarted.list_decisions_for_authority(goal.id)
    finally:
        await restarted.close()

    again = Store(path)
    await again.connect()
    try:
        row = await again.db.execute(
            "SELECT project_binding FROM goals WHERE id = ?",
            (goal.id,),
        )
        assert (await row.fetchone())["project_binding"] == _legacy_binding(project_id)
    finally:
        await again.close()


@pytest.mark.asyncio
async def test_migration_leaves_orphan_malformed_and_mismatched_goal_context_unbound(
    tmp_path,
):
    path = tmp_path / "pex.sqlite"
    first = Store(path)
    await first.connect()
    await first.close()

    parent = _goal("goal-valid-parent", "migration-parent-project")
    project_level = _pair(parent)[1].model_copy(
        update={"id": "context-project-level", "goal_id": None}
    )
    orphan = _pair(parent)[1].model_copy(
        update={"id": "context-orphan", "goal_id": "goal-missing"}
    )
    malformed_parent = _pair(parent)[1].model_copy(
        update={"id": "context-malformed-parent", "goal_id": "goal-malformed"}
    )
    mismatched = _pair(parent, project_id="migration-other-project")[1].model_copy(
        update={"id": "context-mismatched-parent"}
    )
    connection = sqlite3.connect(path)
    try:
        artifact_triggers = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' "
            "AND (name LIKE 'trg_goals_%' OR name LIKE 'trg_decisions_%' "
            "OR name LIKE 'trg_context_items_%')"
        ).fetchall()
        for (trigger,) in artifact_triggers:
            connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        connection.execute("DROP TABLE goal_intent_migration_state")
        connection.execute("DROP TABLE context_goal_id_migration_state")
        connection.execute(
            "INSERT INTO goals(id, json) VALUES (?, ?)",
            (parent.id, parent.model_dump_json()),
        )
        connection.execute(
            "INSERT INTO goals(id, json) VALUES (?, ?)",
            ("goal-malformed", "{}"),
        )
        for item in (project_level, orphan, malformed_parent, mismatched):
            connection.execute(
                "INSERT INTO context_items(id, project_id, json) VALUES (?, ?, ?)",
                (item.id, item.project_id, item.model_dump_json()),
            )
        connection.commit()
    finally:
        connection.close()

    restarted = Store(path)
    await restarted.connect()
    try:
        rows = await restarted.db.execute(
            "SELECT id, project_binding, goal_id FROM context_items ORDER BY id"
        )
        migrated_rows = {str(row["id"]): dict(row) for row in await rows.fetchall()}
        bindings = {
            context_id: row["project_binding"]
            for context_id, row in migrated_rows.items()
        }
        assert bindings == {
            "context-malformed-parent": None,
            "context-mismatched-parent": None,
            "context-orphan": None,
            "context-project-level": _legacy_binding(parent.project_id),
        }
        assert all(row["goal_id"] is None for row in migrated_rows.values())
        with pytest.raises(sqlite3.IntegrityError, match="context goal binding is immutable"):
            await restarted.db.execute(
                "UPDATE context_items SET goal_id = ? WHERE id = ?",
                (parent.id, orphan.id),
            )
        await restarted.db.rollback()
        assert await restarted.list_context_for_authority(parent.project_id) == [
            project_level
        ]
        assert {item.id for item in await restarted.list_context(parent.project_id)} == {
            project_level.id,
            orphan.id,
            malformed_parent.id,
        }
        assert await restarted.list_context("migration-other-project") == [mismatched]
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_historical_session_never_backfills_from_current_typed_binding(tmp_path):
    path = tmp_path / "pex.sqlite"
    project_id = "historical-session-rebound"
    first = Store(path)
    await first.connect()
    await _resolve_same_key_to_second_identity(first, project_id)
    await first.close()

    now = datetime.now(UTC)
    session = HarnessSession(
        id="codex:historical-session-rebound",
        harness_type=HarnessType.CODEX,
        vendor_session_id="historical-session-rebound",
        project_id=project_id,
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO sessions(id, vendor_session_id, harness_type, project_binding, json) "
            "VALUES (?, ?, ?, NULL, ?)",
            (
                session.id,
                session.vendor_session_id,
                session.harness_type.value,
                session.model_dump_json(),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    restarted = Store(path)
    await restarted.connect()
    try:
        row = await restarted.db.execute(
            "SELECT project_binding FROM sessions WHERE id = ?",
            (session.id,),
        )
        assert (await row.fetchone())["project_binding"] == _legacy_binding(project_id)
        with pytest.raises(ProjectIdentityBlockedError) as blocked:
            await restarted.upsert_session(session)
        assert blocked.value.code == "session_project_identity_changed"
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_untyped_rows_remain_forensic_but_lose_authority_when_key_becomes_typed(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    project_id = "untyped-then-typed"
    goal = _goal("goal-untyped-then-typed", project_id)
    decision, context = _pair(goal)
    try:
        await store.upsert_goal(goal)
        await store.add_decision_context_pair(decision, context)
        assert await store.get_goal_for_authority(goal.id) == goal
        assert await store.list_context_for_authority(project_id, goal_id=goal.id) == [context]
        assert await store.list_decisions_for_authority(goal.id) == [decision]

        await store.register_project_locator(
            legacy_project_id=project_id,
            locator=_path("/workspace/untyped-then-typed"),
        )
        changed = goal.model_copy(
            update={
                "objective": "This mutation must not cross identity registration.",
                "updated_at": goal.updated_at + timedelta(seconds=1),
            }
        )
        with pytest.raises(ProjectIdentityBlockedError) as mutation_block:
            await store.patch_goal_with_ledger(goal, changed, [])
        assert mutation_block.value.code == "artifact_project_identity_changed"
        with pytest.raises(ProjectIdentityBlockedError):
            await store.list_context_for_authority(project_id, goal_id=goal.id)
        with pytest.raises(ProjectIdentityBlockedError):
            await store.list_decisions_for_authority(goal.id)

        assert await store.get_goal(goal.id) == goal
        assert await store.list_context(project_id) == [context]
        assert await store.list_decisions(goal.id) == [decision]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_typed_a_rows_do_not_gain_authority_after_same_key_resolves_to_b(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    project_id = "typed-a-to-b"
    try:
        first = await store.register_project_locator(
            legacy_project_id=project_id,
            locator=_path("/workspace/typed-a-to-b/a"),
        )
        goal = _goal("goal-typed-a-to-b", project_id)
        decision, context = _pair(goal)
        await store.upsert_goal(goal)
        await store.add_decision_context_pair(decision, context)
        row = await store.db.execute(
            "SELECT project_binding FROM goals WHERE id = ?",
            (goal.id,),
        )
        assert (await row.fetchone())["project_binding"] == f"identity:{first['identity'].id}"

        await _resolve_same_key_to_second_identity(store, project_id)
        changed = goal.model_copy(
            update={
                "objective": "Do not reinterpret typed A as typed B.",
                "updated_at": goal.updated_at + timedelta(seconds=1),
            }
        )
        with pytest.raises(ProjectIdentityBlockedError):
            await store.patch_goal_with_ledger(goal, changed, [])
        with pytest.raises(ProjectIdentityBlockedError):
            await store.list_context_for_authority(project_id, goal_id=goal.id)
        with pytest.raises(ProjectIdentityBlockedError):
            await store.list_decisions_for_authority(goal.id)
        assert await store.get_goal(goal.id) == goal
        assert await store.list_context(project_id) == [context]
        assert await store.list_decisions(goal.id) == [decision]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_explicit_typed_aliases_share_authority_without_raw_key_normalization(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    proof = PhysicalIdentityProof(
        provider="posix-stat",
        volume_id="dev-artifact",
        object_id="inode-artifact",
    )
    try:
        first = await store.register_project_locator(
            legacy_project_id="typed-alias-a",
            locator=_path("/workspace/typed-alias-a", physical=proof),
        )
        alias = await store.register_project_locator(
            legacy_project_id="typed-alias-b",
            locator=_path("/workspace/typed-alias-b", physical=proof),
        )
        assert alias["identity"].id == first["identity"].id

        goal = _goal("goal-typed-alias", "typed-alias-a")
        decision, context = _pair(goal, project_id="typed-alias-b")
        await store.upsert_goal(goal)
        await store.add_decision_context_pair(decision, context)

        assert await store.list_context_for_authority(
            "typed-alias-a",
            goal_id=goal.id,
        ) == [context]
        assert await store.list_context_for_authority(
            "typed-alias-b",
            goal_id=goal.id,
        ) == [context]
        assert await store.list_decisions_for_authority(goal.id) == [decision]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_different_identity_forensic_successor_cannot_deny_live_goal_authority(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        project_a = await store.register_project_locator(
            legacy_project_id="successor-project-a",
            locator=_path("/workspace/successor-project-a"),
        )
        project_b = await store.register_project_locator(
            legacy_project_id="successor-project-b",
            locator=_path("/workspace/successor-project-b"),
        )
        current = _goal("goal-live-against-foreign-successor", "successor-project-a")
        await store.upsert_goal(current)
        foreign = _goal("goal-foreign-successor", "successor-project-b").model_copy(
            update={"supersedes": current.id}
        )
        # Simulate a forensic pre-boundary row that the prospective insert guard
        # now rejects; reconnect migration must preserve it without granting it
        # authority over a different physical project.
        await store.db.execute("DROP TRIGGER trg_goals_intent_require")
        await store.db.execute(
            "INSERT INTO goals(id, project_id, project_binding, intent_revision, "
            "intent_hash, json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                foreign.id,
                foreign.project_id,
                f"identity:{project_b['identity'].id}",
                2,
                goal_intent_semantic_hash(foreign),
                foreign.model_dump_json(),
            ),
        )
        await store.db.commit()
        await store._migrate_goal_intent_authority()

        assert await store.has_goal_successor(current.id) is True
        assert await store.get_goal_for_authority(current.id) == current
        updated = current.model_copy(
            update={
                "objective": "Ignore a successor from another physical identity.",
                "updated_at": current.updated_at + timedelta(seconds=1),
            }
        )
        await store.patch_goal_with_ledger(current, updated, [])
        decision, context = _pair(updated)
        await store.add_decision_context_pair(decision, context)
        assert await store.list_context_for_authority(
            current.project_id,
            goal_id=current.id,
        ) == [context]
        assert await store.list_decisions_for_authority(current.id) == [decision]

        binding = await store.db.execute(
            "SELECT project_binding FROM goals WHERE id = ?",
            (current.id,),
        )
        assert (await binding.fetchone())["project_binding"] == (
            f"identity:{project_a['identity'].id}"
        )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_rebound_successor_alias_cannot_deny_still_live_parent_alias(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    proof = PhysicalIdentityProof(
        provider="posix-stat",
        volume_id="dev-successor-alias",
        object_id="inode-successor-alias",
    )
    try:
        parent_registration = await store.register_project_locator(
            legacy_project_id="successor-parent-alias",
            locator=_path("/workspace/successor-parent-alias", physical=proof),
        )
        successor_registration = await store.register_project_locator(
            legacy_project_id="successor-child-alias",
            locator=_path("/workspace/successor-child-alias", physical=proof),
        )
        assert successor_registration["identity"].id == parent_registration["identity"].id

        parent = _goal("goal-parent-live-alias", "successor-parent-alias")
        successor = _goal("goal-child-rebound-alias", "successor-child-alias").model_copy(
            update={"supersedes": parent.id}
        )
        await store.upsert_goal(parent)
        await store.db.execute(
            "INSERT INTO goals(id, project_id, project_binding, intent_revision, "
            "intent_hash, json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                successor.id,
                successor.project_id,
                f"identity:{parent_registration['identity'].id}",
                2,
                goal_intent_semantic_hash(successor),
                successor.model_dump_json(),
            ),
        )
        await store.db.commit()
        assert await store.has_goal_successor_for_authority(parent.id) is True

        second = await store.register_project_locator(
            legacy_project_id="successor-child-alias",
            locator=_path("/workspace/successor-child-alias-rebound"),
        )
        assert second["outcome"] == "quarantined"
        await store.resolve_project_identity_conflict(
            resolution_id="resolve-successor-child-alias-to-b",
            legacy_project_id="successor-child-alias",
            selected_identity_id=second["identity"].id,
            resolved_by="artifact-binding-test",
            rationale="Move only the successor alias to a distinct checkout.",
        )

        assert await store.has_goal_successor(parent.id) is True
        assert await store.has_goal_successor_for_authority(parent.id) is False
        updated = parent.model_copy(
            update={
                "objective": "A stale successor alias cannot deny the live parent alias.",
                "updated_at": parent.updated_at + timedelta(seconds=1),
            }
        )
        await store.patch_goal_with_ledger(parent, updated, [])
        assert await store.get_goal_for_authority(parent.id) == updated
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_new_direct_rows_require_binding_and_bound_columns_are_immutable(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    goal = _goal("goal-trigger-boundary", "trigger-boundary")
    try:
        with pytest.raises(sqlite3.IntegrityError, match="goal project binding is required"):
            await store.db.execute(
                "INSERT INTO goals(id, json) VALUES (?, ?)",
                (goal.id, goal.model_dump_json()),
            )
        await store.db.rollback()

        await store.upsert_goal(goal)
        with pytest.raises(sqlite3.IntegrityError, match="goal project binding is immutable"):
            await store.db.execute(
                "UPDATE goals SET project_binding = ? WHERE id = ?",
                ("identity:forged", goal.id),
            )
        await store.db.rollback()

        decision, context = _pair(goal)
        with pytest.raises(sqlite3.IntegrityError, match="decision project binding is required"):
            await store.db.execute(
                "INSERT INTO decisions(id, goal_id, json) VALUES (?, ?, ?)",
                (decision.id, decision.goal_id, decision.model_dump_json()),
            )
        await store.db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="context project binding is required"):
            await store.db.execute(
                "INSERT INTO context_items(id, project_id, json) VALUES (?, ?, ?)",
                (context.id, context.project_id, context.model_dump_json()),
            )
        await store.db.rollback()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_context_goal_scalar_is_bound_immutable_and_indexed(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    goal = _goal("goal-context-scalar", "context-scalar")
    try:
        await store.upsert_goal(goal)
        decision, context = _pair(goal)
        await store.add_decision_context_pair(decision, context)
        cursor = await store.db.execute(
            "SELECT goal_id, json FROM context_items WHERE id = ?",
            (context.id,),
        )
        row = await cursor.fetchone()
        assert row is not None and row["goal_id"] == context.goal_id

        with pytest.raises(sqlite3.IntegrityError, match="context goal binding is immutable"):
            await store.db.execute(
                "UPDATE context_items SET goal_id = NULL WHERE id = ?",
                (context.id,),
            )
        await store.db.rollback()

        mismatched = context.model_copy(update={"id": "context-scalar-mismatch"})
        goal_row = await store.db.execute(
            "SELECT project_binding FROM goals WHERE id = ?",
            (goal.id,),
        )
        binding = str((await goal_row.fetchone())["project_binding"])
        with pytest.raises(sqlite3.IntegrityError, match="context project binding is required"):
            await store.db.execute(
                "INSERT INTO context_items(id, project_id, project_binding, goal_id, json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    mismatched.id,
                    mismatched.project_id,
                    binding,
                    None,
                    mismatched.model_dump_json(),
                ),
            )
        await store.db.rollback()

        plan_cursor = await store.db.execute(
            "EXPLAIN QUERY PLAN SELECT json FROM context_items "
            "WHERE project_binding = ? AND goal_id = ? ORDER BY id LIMIT 100",
            (binding, goal.id),
        )
        plan = " ".join(str(tuple(item)) for item in await plan_cursor.fetchall())
        assert "idx_context_items_project_binding_goal_id" in plan
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_context_goal_scalar_corruption_fails_reconnect_closed(tmp_path):
    path = tmp_path / "pex.sqlite"
    store = Store(path)
    await store.connect()
    goal = _goal("goal-context-scalar-corrupt", "context-scalar-corrupt")
    decision, context = _pair(goal)
    try:
        await store.upsert_goal(goal)
        await store.add_decision_context_pair(decision, context)
    finally:
        await store.close()

    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TRIGGER trg_context_items_goal_id_immutable")
        connection.execute(
            "UPDATE context_items SET goal_id = NULL WHERE id = ?",
            (context.id,),
        )
        connection.commit()
    finally:
        connection.close()

    restarted = Store(path)
    with pytest.raises(RuntimeError, match="context scalar goal binding is corrupt"):
        await restarted.connect()
