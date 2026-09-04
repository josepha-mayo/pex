from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge.hook_auth import CURSOR_HOOK_ROUTE
from pex_bridge.store import Store
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.project_identity import (
    PathPlatform,
    PhysicalIdentityProof,
    ProjectLocator,
    ProjectOrigin,
)
from pex_protocol.session import HarnessSession

ORIGIN = ProjectOrigin(namespace="machine", host="credential-binding-test")


def _locator(
    path: str,
    *,
    physical: PhysicalIdentityProof | None = None,
) -> ProjectLocator:
    return ProjectLocator.path(
        path,
        platform=PathPlatform.POSIX,
        origin=ORIGIN,
        physical=physical,
    )


def _goal(project_id: str, *, goal_id: str = "goal-credential-binding") -> Goal:
    now = datetime.now(UTC)
    return Goal(
        id=goal_id,
        project_id=project_id,
        title="Credential binding",
        objective="Keep bearer authority on its creation-time physical project.",
        created_at=now,
        updated_at=now,
    )


def _session(project_id: str, goal_id: str | None) -> HarnessSession:
    return HarnessSession(
        id="cursor:credential-binding",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="credential-binding",
        project_id=project_id,
        goal_id=goal_id,
        status=SessionStatus.WORKING,
        last_activity=datetime.now(UTC),
    )


async def _issue_pair(
    store: Store,
    *,
    goal: Goal,
    session: HarnessSession,
    project_id: str,
    now: datetime,
    prefix: str = "a",
) -> tuple[dict, dict]:
    principal = await store.issue_mcp_principal(
        principal_id=f"principal-{prefix}",
        session_id=session.id,
        goal_id=goal.id,
        project_id=project_id,
        vendor_session_id=session.vendor_session_id,
        harness_type=session.harness_type.value,
        scopes=["mcp:read"],
        token_digest=prefix * 64,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )
    hook = await store.issue_hook_credential(
        credential_id=f"hook-{prefix}",
        session_id=session.id,
        project_id=project_id,
        vendor_session_id=session.vendor_session_id,
        harness_type=session.harness_type.value,
        allowed_routes=[CURSOR_HOOK_ROUTE],
        token_digest=prefix.upper().encode().hex()[:64].ljust(64, "0"),
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )
    return principal, hook


@pytest.mark.asyncio
async def test_typed_nonlexical_aliases_share_one_credential_binding(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    proof = PhysicalIdentityProof(
        provider="posix-stat",
        volume_id="credential-device",
        object_id="credential-inode",
    )
    try:
        first = await store.register_project_locator(
            legacy_project_id="credential-alias-a",
            locator=_locator("/workspace/credential-a", physical=proof),
        )
        second = await store.register_project_locator(
            legacy_project_id="credential-alias-b",
            locator=_locator("/workspace/credential-b", physical=proof),
        )
        assert second["identity"].id == first["identity"].id
        goal = _goal("credential-alias-a")
        session = _session("credential-alias-b", goal.id)
        await store.upsert_goal(goal)
        await store.upsert_session(session)

        principal, hook = await _issue_pair(
            store,
            goal=goal,
            session=session,
            project_id="credential-alias-a",
            now=now,
        )
        expected = f"identity:{first['identity'].id}"
        assert principal["project_binding"] == expected
        assert hook["project_binding"] == expected
        assert (await store.get_mcp_principal_by_digest("a" * 64, now=now)) == principal
        hook_digest = str(hook["token_digest"])
        assert (await store.get_hook_credential_by_digest(hook_digest, now=now)) == hook
        assert await store.project_binding_for_authority("credential-alias-b") == expected
        assert await store.project_id_matches_binding("credential-alias-b", expected)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_untyped_credentials_fail_after_project_becomes_typed(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    project_id = "credential-untyped-to-typed"
    try:
        goal = _goal(project_id)
        session = _session(project_id, goal.id)
        await store.upsert_goal(goal)
        await store.upsert_session(session)
        principal, hook = await _issue_pair(
            store,
            goal=goal,
            session=session,
            project_id=project_id,
            now=now,
        )
        assert str(principal["project_binding"]).startswith("legacy:")
        assert str(hook["project_binding"]).startswith("legacy:")

        await store.register_project_locator(
            legacy_project_id=project_id,
            locator=_locator("/workspace/credential-typed"),
        )
        assert await store.get_mcp_principal_by_digest("a" * 64, now=now) is None
        assert (
            await store.get_hook_credential_by_digest(str(hook["token_digest"]), now=now)
            is None
        )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_sessionless_hook_cannot_bind_normalized_untyped_alias(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    digest = "b" * 64
    try:
        record = await store.issue_hook_credential(
            credential_id="hook-normalized-untyped",
            session_id=None,
            project_id=r"C:\Repo",
            vendor_session_id=None,
            harness_type=HarnessType.CURSOR.value,
            allowed_routes=[CURSOR_HOOK_ROUTE],
            token_digest=digest,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
        )
        assert str(record["project_binding"]).startswith("legacy:")
        incoming = _session("c:/repo/", None)
        with pytest.raises(PermissionError, match="project binding mismatch"):
            await store.bind_hook_credential_session(digest, incoming, bound_at=now)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_legacy_credentials_remain_unbound_inactive_and_revocable(tmp_path):
    path = tmp_path / "pex.sqlite"
    store = Store(path)
    await store.connect()
    now = datetime.now(UTC)
    project_id = "legacy-credential-row"
    goal = _goal(project_id)
    session = _session(project_id, goal.id)
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    principal, hook = await _issue_pair(
        store,
        goal=goal,
        session=session,
        project_id=project_id,
        now=now,
    )
    for trigger in await store.db.execute_fetchall(
        "SELECT name FROM sqlite_master WHERE type = 'trigger' "
        "AND (name LIKE 'trg_mcp_principals_%' OR name LIKE 'trg_hook_credentials_%')"
    ):
        await store.db.execute(f"DROP TRIGGER IF EXISTS {trigger['name']}")
    for table, row_id, record in (
        ("mcp_principals", principal["principal_id"], principal),
        ("hook_credentials", hook["credential_id"], hook),
    ):
        legacy_record = dict(record)
        legacy_record.pop("project_binding")
        await store.db.execute(
            f"UPDATE {table} SET project_binding = NULL, json = ? WHERE id = ?",
            (json.dumps(legacy_record, sort_keys=True, separators=(",", ":")), row_id),
        )
    await store.db.commit()
    await store.close()

    restarted = Store(path)
    await restarted.connect()
    try:
        assert await restarted.get_mcp_principal_by_digest("a" * 64, now=now) is None
        assert (
            await restarted.get_hook_credential_by_digest(
                str(hook["token_digest"]), now=now
            )
            is None
        )
        rows = await restarted.db.execute_fetchall(
            "SELECT project_binding FROM mcp_principals UNION ALL "
            "SELECT project_binding FROM hook_credentials"
        )
        assert [row["project_binding"] for row in rows] == [None, None]
        assert (
            await restarted.revoke_mcp_principals_for_session(
                session.id,
                revoked_at=now + timedelta(minutes=1),
            )
            == 1
        )
        assert (
            await restarted.revoke_hook_credentials_for_session(
                session.id,
                revoked_at=now + timedelta(minutes=1),
            )
            == 1
        )
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_scalar_json_divergence_is_rejected_and_lookup_fails_closed(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    project_id = "credential-divergence"
    try:
        goal = _goal(project_id)
        session = _session(project_id, goal.id)
        await store.upsert_goal(goal)
        await store.upsert_session(session)
        principal, hook = await _issue_pair(
            store,
            goal=goal,
            session=session,
            project_id=project_id,
            now=now,
        )
        with pytest.raises(sqlite3.IntegrityError, match="bound identity cannot change"):
            await store.db.execute(
                "UPDATE mcp_principals SET revoked_at = ? WHERE id = ?",
                ((now + timedelta(minutes=1)).isoformat(), principal["principal_id"]),
            )
        await store.db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="bound identity cannot change"):
            await store.db.execute(
                "UPDATE hook_credentials SET revoked_at = ? WHERE id = ?",
                ((now + timedelta(minutes=1)).isoformat(), hook["credential_id"]),
            )
        await store.db.rollback()

        for trigger in await store.db.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' "
            "AND name = 'trg_mcp_principals_bound_json_identity'"
        ):
            await store.db.execute(f"DROP TRIGGER {trigger['name']}")
        await store.db.execute(
            "UPDATE mcp_principals SET revoked_at = ? WHERE id = ?",
            ((now + timedelta(minutes=1)).isoformat(), principal["principal_id"]),
        )
        await store.db.commit()
        assert await store.get_mcp_principal_by_digest("a" * 64, now=now) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_goal_supersede_revokes_mcp_and_hook_credentials(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    project_id = "credential-supersede"
    try:
        goal = _goal(project_id)
        session = _session(project_id, goal.id)
        await store.upsert_goal(goal)
        await store.upsert_session(session)
        _, hook = await _issue_pair(
            store,
            goal=goal,
            session=session,
            project_id=project_id,
            now=now,
        )
        successor = _goal(project_id, goal_id="goal-credential-successor").model_copy(
            update={
                "objective": "Keep bearer credentials bound after a real intent override.",
                "supersedes": goal.id,
                "updated_at": goal.updated_at + timedelta(seconds=1),
            }
        )
        assert await store.supersede_goal_with_ledger(goal, successor, []) == [session.id]
        assert await store.get_mcp_principal_by_digest("a" * 64, now=now) is None
        assert (
            await store.get_hook_credential_by_digest(str(hook["token_digest"]), now=now)
            is None
        )
    finally:
        await store.close()
