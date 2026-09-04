from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge.ledger import ledger_projections
from pex_bridge.store import ProjectIdentityBlockedError, Store
from pex_protocol.enums import DecisionSource, DecisionStatus, HarnessType, SessionStatus
from pex_protocol.goal import Decision, Goal
from pex_protocol.project_identity import (
    PathPlatform,
    PhysicalIdentityProof,
    ProjectLocator,
    ProjectOrigin,
)
from pex_protocol.session import HarnessSession
from pydantic import ValidationError

MACHINE = ProjectOrigin(namespace="machine", host="goal-transaction-test")


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


def _goal(goal_id: str, *, supersedes: str | None = None) -> Goal:
    now = datetime.now(UTC)
    return Goal(
        id=goal_id,
        project_id="demo",
        title=goal_id,
        objective=f"Complete {goal_id}",
        created_at=now,
        updated_at=now,
        supersedes=supersedes,
    )


@pytest.mark.asyncio
async def test_supersede_goal_rolls_back_goal_and_session_changes_together(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    current = _goal("goal_old")
    replacement = _goal("goal_new", supersedes=current.id)
    session = HarnessSession(
        id="synthetic:goal-transaction",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="goal-transaction",
        project_id=current.project_id,
        goal_id=current.id,
    )
    await store.upsert_goal(current)
    await store.upsert_session(session)
    await store.db.execute(
        "INSERT INTO sessions(id, vendor_session_id, harness_type, json) VALUES (?, ?, ?, ?)",
        ("broken", "broken", HarnessType.SYNTHETIC.value, "not-json"),
    )
    await store.db.commit()

    try:
        with pytest.raises(ValidationError):
            await store.supersede_goal(current.id, replacement)
        assert await store.get_goal(replacement.id) is None
        unchanged = await store.get_session(session.id)
        assert unchanged is not None
        assert unchanged.goal_id == current.id
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_supersede_goal_rejects_a_cross_project_attached_session(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    current = _goal("goal_old")
    replacement = _goal("goal_new", supersedes=current.id)
    mismatched = HarnessSession(
        id="synthetic:wrong-project",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="wrong-project",
        project_id="another-project",
        goal_id=current.id,
    )
    try:
        await store.upsert_goal(current)
        await store.upsert_session(mismatched)
        with pytest.raises(ValueError, match="superseded goal project"):
            await store.supersede_goal(current.id, replacement)
        assert await store.get_goal(replacement.id) is None
        assert await store.get_session(mismatched.id) == mismatched
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_older_session_snapshot_cannot_rollback_newer_durable_state(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    newer = HarnessSession(
        id="codex:ordered",
        harness_type=HarnessType.CODEX,
        vendor_session_id="ordered",
        goal_id="goal_current",
        supervision_paused=True,
        status=SessionStatus.WORKING,
        last_activity=now,
        capabilities={"send_message": True},
    )
    stale = HarnessSession(
        id=newer.id,
        harness_type=HarnessType.CODEX,
        vendor_session_id="ordered",
        goal_id="goal_stale",
        supervision_paused=False,
        status=SessionStatus.STOPPED,
        last_activity=now - timedelta(minutes=1),
    )
    try:
        await store.upsert_session(newer)
        await store.upsert_session(stale)
        saved = await store.get_session(newer.id)
        assert saved == newer
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_new_adapter_activity_cannot_replace_bridge_owned_goal_or_pause(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    attached = HarnessSession(
        id="cursor:durable",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="durable",
        goal_id="goal_current",
        supervision_paused=True,
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    adapter_snapshot = attached.model_copy(
        update={
            "goal_id": "goal_stale",
            "supervision_paused": False,
            "status": SessionStatus.STOPPED,
            "last_activity": now + timedelta(seconds=1),
        }
    )
    try:
        await store.upsert_session(attached)
        await store.upsert_session(adapter_snapshot)
        saved = await store.get_session(attached.id)
        assert saved is not None
        assert saved.goal_id == "goal_current"
        assert saved.supervision_paused is True
        assert saved.status == SessionStatus.STOPPED
        assert saved.last_activity == adapter_snapshot.last_activity

        await store.upsert_goal(_goal("goal_human_replacement"))
        saved.goal_id = "goal_human_replacement"
        saved.supervision_paused = False
        await store.upsert_session(
            saved,
            allow_goal_change=True,
            allow_supervision_change=True,
        )
        updated = await store.get_session(attached.id)
        assert updated is not None
        assert updated.goal_id == "goal_human_replacement"
        assert updated.supervision_paused is False
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_goal_listing_is_latest_updated_first(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    older = _goal("goal_older")
    older.created_at = now - timedelta(days=1)
    older.updated_at = now - timedelta(hours=1)
    newer = _goal("goal_newer")
    newer.created_at = now - timedelta(days=2)
    newer.updated_at = now
    try:
        await store.upsert_goal(older)
        await store.upsert_goal(newer)
        assert [goal.id for goal in await store.list_goals()] == ["goal_newer", "goal_older"]
        assert [goal.id for goal in await store.list_goals_page(limit=1)] == ["goal_newer"]
        assert [goal.id for goal in await store.list_goals_page(limit=1, offset=1)] == [
            "goal_older"
        ]
        with pytest.raises(ValueError, match="between 1"):
            await store.list_goals_page(limit=0)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_goal_successor_lookup_is_direct_and_bounded(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    original = _goal("goal_original")
    successor = _goal("goal_successor")
    successor.supersedes = original.id
    try:
        await store.upsert_goal(original)
        assert await store.has_goal_successor(original.id) is False
        with pytest.raises(ValueError, match="atomic supersede"):
            await store.upsert_goal(successor)
        await store.supersede_goal(original.id, successor)
        assert await store.has_goal_successor(original.id) is True
        assert await store.has_goal_successor(successor.id) is False
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_concurrent_goal_supersedes_commit_exactly_one_successor(tmp_path):
    database = tmp_path / "pex.sqlite"
    first = Store(database)
    second = Store(database)
    await first.connect()
    await second.connect()
    original = _goal("goal_concurrent_original")
    replacements = [
        _goal("goal_concurrent_first", supersedes=original.id),
        _goal("goal_concurrent_second", supersedes=original.id),
    ]
    try:
        await first.upsert_goal(original)
        results = await asyncio.gather(
            first.supersede_goal(original.id, replacements[0]),
            second.supersede_goal(original.id, replacements[1]),
            return_exceptions=True,
        )
        assert sum(not isinstance(result, BaseException) for result in results) == 1
        assert sum(
            isinstance(result, ValueError)
            and "already been superseded" in str(result)
            for result in results
        ) == 1
        successors = [
            goal
            for goal in await first.list_goals()
            if goal.supersedes == original.id
        ]
        assert len(successors) == 1
    finally:
        await second.close()
        await first.close()


@pytest.mark.asyncio
async def test_goal_patch_uses_exact_current_compare_and_swap(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    original = _goal("goal_exact_cas")
    first = original.model_copy(
        update={
            "objective": "First committed objective",
            "updated_at": original.updated_at + timedelta(seconds=1),
        }
    )
    stale_second = original.model_copy(
        update={
            "objective": "Stale competing objective",
            "updated_at": original.updated_at + timedelta(seconds=2),
        }
    )
    try:
        await store.upsert_goal(original)
        await store.patch_goal_with_ledger(original, first, [])
        with pytest.raises(ValueError, match="changed since it was read"):
            await store.patch_goal_with_ledger(original, stale_second, [])
        assert await store.get_goal(original.id) == first
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_goal_patch_preserves_raw_project_key_across_typed_aliases(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    proof = PhysicalIdentityProof(
        provider="posix-stat",
        volume_id="dev-goal-alias",
        object_id="inode-goal-alias",
    )
    goal = _goal("goal_raw_project_key")
    goal.project_id = "legacy-project-primary"
    try:
        await store.register_project_locator(
            legacy_project_id=goal.project_id,
            locator=_path("/workspace/primary", physical=proof),
        )
        await store.register_project_locator(
            legacy_project_id="legacy-project-alias",
            locator=_path("/workspace/alias", physical=proof),
        )
        await store.upsert_goal(goal)

        alias_rewrite = goal.model_copy(
            update={
                "project_id": "legacy-project-alias",
                "updated_at": goal.updated_at + timedelta(seconds=1),
            }
        )
        with pytest.raises(ValueError, match="cannot change project identity"):
            await store.upsert_goal(alias_rewrite)
        assert await store.get_goal(goal.id) == goal
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_ledger_replacement_ignores_untyped_operational_decisions(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    goal = _goal("goal_operational_decision")
    shared_statement = "Use the durable decision channel"
    operational = Decision(
        id="dec_operational",
        goal_id=goal.id,
        statement=shared_statement,
        source=DecisionSource.HUMAN,
        status=DecisionStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )
    projection = ledger_projections(
        goal,
        explicit={"decisions": [shared_statement]},
        skip_fields={"decisions"},
    )
    try:
        await store.upsert_goal(goal)
        await store.add_decision(operational)
        await store.patch_goal_with_ledger(
            goal,
            goal,
            projection,
            replace_ledger_kinds=frozenset({"decision"}),
        )
        decisions = await store.list_decisions(goal.id)
        assert {item.id for item in decisions} == {
            operational.id,
            projection[0][0].id,
        }
        assert next(item for item in decisions if item.id == operational.id).status == (
            DecisionStatus.ACTIVE
        )
        assert next(item for item in decisions if item.id == operational.id).metadata == {}
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_goal_ledger_collision_rolls_back_goal_and_prior_projection_retirement(
    tmp_path,
):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    original = _goal("goal_ledger_rollback")
    original_projection = ledger_projections(
        original,
        explicit={"decisions": ["Keep the committed storage format"]},
        skip_fields={"decisions"},
    )
    updated = original.model_copy(
        update={
            "objective": "Replace the committed storage format",
            "updated_at": original.updated_at + timedelta(seconds=1),
        }
    )
    replacement_projection = ledger_projections(
        updated,
        explicit={"decisions": ["Use the replacement storage format"]},
        skip_fields={"decisions"},
    )
    replacement_decision, replacement_context = replacement_projection[0]
    conflicting_context = replacement_context.model_copy(
        update={
            "content": "An unrelated row already owns this context id",
            "metadata": {"collision_fixture": True},
        }
    )
    try:
        await store.create_goal_with_ledger(original, original_projection)
        await store.add_context(conflicting_context)
        with pytest.raises(ValueError, match="context id already exists"):
            await store.patch_goal_with_ledger(
                original,
                updated,
                replacement_projection,
                replace_ledger_kinds=frozenset({"decision"}),
            )

        assert await store.get_goal(original.id) == original
        decisions = await store.list_decisions(original.id)
        assert [(item.statement, item.status) for item in decisions] == [
            ("Keep the committed storage format", DecisionStatus.ACTIVE)
        ]
        original_context = await store.get_context(original_projection[0][1].id)
        assert original_context is not None
        assert original_context.metadata["status"] == DecisionStatus.ACTIVE.value
        assert original_context.stale_after is None
        assert await store.get_context(conflicting_context.id) == conflicting_context
        assert all(item.id != replacement_decision.id for item in decisions)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_supersede_ledger_collision_rolls_back_session_and_principal_changes(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    current = _goal("goal_supersede_rollback")
    replacement = _goal("goal_supersede_replacement", supersedes=current.id)
    session = HarnessSession(
        id="synthetic:supersede-ledger-rollback",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="supersede-ledger-rollback",
        project_id=current.project_id,
        goal_id=current.id,
    )
    projections = ledger_projections(
        replacement,
        explicit={"decisions": ["Commit the replacement goal"]},
        skip_fields={"decisions"},
    )
    conflicting_context = projections[0][1].model_copy(
        update={
            "goal_id": current.id,
            "content": "Preexisting context collision",
            "metadata": {"collision_fixture": True},
        }
    )
    issued_at = datetime.now(UTC) - timedelta(seconds=1)
    try:
        await store.upsert_goal(current)
        await store.upsert_session(session)
        await store.issue_mcp_principal(
            principal_id="principal-supersede-ledger-rollback",
            session_id=session.id,
            goal_id=current.id,
            project_id=current.project_id,
            vendor_session_id=session.vendor_session_id,
            harness_type=session.harness_type.value,
            scopes=["mcp:read"],
            token_digest="d" * 64,
            issued_at=issued_at,
            expires_at=issued_at + timedelta(hours=1),
        )
        await store.add_context(conflicting_context)

        with pytest.raises(ValueError, match="context id already exists"):
            await store.supersede_goal_with_ledger(current, replacement, projections)

        assert await store.get_goal(replacement.id) is None
        assert await store.has_goal_successor(current.id) is False
        assert (await store.get_session(session.id)).goal_id == current.id
        principal = await store.get_mcp_principal(
            "principal-supersede-ledger-rollback"
        )
        assert principal is not None
        assert principal["revoked_at"] is None
        assert await store.list_decisions(replacement.id) == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_quarantine_allows_only_exact_pause_without_ledger_mutation(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    original = _goal("goal_quarantined_pause")
    try:
        await store.upsert_goal(original)
        await store.register_project_locator(
            legacy_project_id=original.project_id,
            locator=_path("/workspace/quarantine-one"),
        )
        await store.register_project_locator(
            legacy_project_id=original.project_id,
            locator=_path("/workspace/quarantine-two"),
        )

        paused = original.model_copy(
            update={
                "paused": True,
                "updated_at": original.updated_at + timedelta(seconds=1),
            }
        )
        await store.patch_goal_with_ledger(original, paused, [])
        assert await store.get_goal(original.id) == paused

        changed = paused.model_copy(
            update={
                "objective": "Unsafe quarantined intent change",
                "updated_at": paused.updated_at + timedelta(seconds=1),
            }
        )
        with pytest.raises(ProjectIdentityBlockedError):
            await store.patch_goal_with_ledger(paused, changed, [])
        with pytest.raises(ProjectIdentityBlockedError):
            await store.patch_goal_with_ledger(
                paused,
                paused,
                [],
                replace_ledger_kinds=frozenset({"decision"}),
            )
        assert await store.get_goal(original.id) == paused
        assert await store.list_decisions(original.id) == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_quarantined_successor_still_blocks_predecessor_containment_mutation(
    tmp_path,
):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    parent = _goal("goal_quarantined_parent")
    successor = _goal("goal_quarantined_successor", supersedes=parent.id)
    try:
        await store.upsert_goal(parent)
        await store.supersede_goal(parent.id, successor)
        parent_before = await store.db.execute(
            "SELECT intent_revision, intent_hash, json FROM goals WHERE id = ?",
            (parent.id,),
        )
        frozen = dict(await parent_before.fetchone())
        await store.register_project_locator(
            legacy_project_id=parent.project_id,
            locator=_path("/workspace/quarantined-successor-one"),
        )
        await store.register_project_locator(
            legacy_project_id=parent.project_id,
            locator=_path("/workspace/quarantined-successor-two"),
        )

        paused_parent = parent.model_copy(
            update={
                "paused": True,
                "updated_at": parent.updated_at + timedelta(seconds=1),
            }
        )
        with pytest.raises(ValueError, match="already been superseded"):
            await store.patch_goal_with_ledger(parent, paused_parent, [])
        parent_after = await store.db.execute(
            "SELECT intent_revision, intent_hash, json FROM goals WHERE id = ?",
            (parent.id,),
        )
        assert dict(await parent_after.fetchone()) == frozen
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_session_identity_cannot_move_to_another_project_or_vendor(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    session = HarnessSession(
        id="codex:identity-bound",
        harness_type=HarnessType.CODEX,
        vendor_session_id="identity-bound",
        project_id="C:/project-a",
        status=SessionStatus.WORKING,
        last_activity=datetime.now(UTC),
    )
    try:
        await store.upsert_session(session)
        with pytest.raises(ValueError, match="project identity"):
            await store.upsert_session(
                session.model_copy(
                    update={
                        "project_id": "C:/project-b",
                        "last_activity": session.last_activity + timedelta(seconds=1),
                    }
                )
            )
        with pytest.raises(ValueError, match="vendor identity"):
            await store.upsert_session(
                session.model_copy(
                    update={
                        "vendor_session_id": "another-vendor",
                        "last_activity": session.last_activity + timedelta(seconds=1),
                    }
                )
            )
        assert await store.get_session(session.id) == session
    finally:
        await store.close()
