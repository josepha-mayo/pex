from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge.hook_auth import CURSOR_HOOK_ROUTE
from pex_bridge.store import ProjectIdentityBlockedError, Store
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.project_identity import (
    PathPlatform,
    PhysicalIdentityProof,
    ProjectLocator,
    ProjectOrigin,
)
from pex_protocol.session import HarnessEvent, HarnessSession

MACHINE = ProjectOrigin(namespace="machine", host="identity-test-host")


def _path(raw: str, *, physical: PhysicalIdentityProof | None = None) -> ProjectLocator:
    return ProjectLocator.path(
        raw,
        platform=PathPlatform.POSIX,
        origin=MACHINE,
        physical=physical,
    )


def _event(event_id: str, session: HarnessSession, goal: Goal) -> HarnessEvent:
    return HarnessEvent(
        event_id=event_id,
        ts=datetime.now(UTC),
        harness_type=session.harness_type,
        session_id=session.id,
        project_id=goal.project_id,
        goal_id=goal.id,
        event_type=EventType.AGENT_RESPONSE,
        message_delta="still working",
    )


@pytest.mark.asyncio
async def test_explicit_locator_registration_is_replayable_and_legacy_exact(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    try:
        first = await store.register_project_locator(
            legacy_project_id="/tmp/Project",
            locator=_path("/tmp/Project"),
            now=now,
        )
        replay = await store.register_project_locator(
            legacy_project_id="/tmp/Project",
            locator=_path("/tmp/Project"),
            now=now,
        )
        different_case = await store.register_project_locator(
            legacy_project_id="/tmp/project",
            locator=_path("/tmp/project"),
            now=now,
        )
        trailing_space = await store.register_project_locator(
            legacy_project_id="/tmp/Project ",
            locator=_path("/tmp/Project "),
            now=now,
        )

        assert first["outcome"] == "created"
        assert replay["outcome"] == "replayed"
        assert replay["identity"].id == first["identity"].id
        assert different_case["identity"].id != first["identity"].id
        assert trailing_space["identity"].id != first["identity"].id
        assert (await store.resolve_project_identity("/tmp/Project"))["identity"].id == (
            first["identity"].id
        )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_physical_alias_adds_locator_to_one_stable_random_identity(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    proof = PhysicalIdentityProof(
        provider="posix-stat",
        volume_id="dev-1",
        object_id="inode-7",
    )
    try:
        first = await store.register_project_locator(
            legacy_project_id="legacy-a",
            locator=_path("/work/a", physical=proof),
        )
        alias = await store.register_project_locator(
            legacy_project_id="legacy-b",
            locator=_path("/links/a", physical=proof),
        )
        resolved = await store.resolve_project_identity("legacy-a")
        assert alias["identity"].id == first["identity"].id
        assert resolved is not None
        assert len(resolved["identity"].locator_fingerprints) == 2
        assert {locator.raw for locator in resolved["locators"]} == {
            "/work/a",
            "/links/a",
        }
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_conflicting_locator_quarantines_without_rewriting_or_merging(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        first = await store.register_project_locator(
            legacy_project_id="ambiguous-legacy",
            locator=_path("/workspace/one"),
        )
        conflict = await store.register_project_locator(
            legacy_project_id="ambiguous-legacy",
            locator=_path("/workspace/two"),
        )
        replay = await store.register_project_locator(
            legacy_project_id="ambiguous-legacy",
            locator=_path("/workspace/two"),
        )
        assert conflict["outcome"] == replay["outcome"] == "quarantined"
        assert conflict["identity"].id != first["identity"].id
        assert await store.resolve_project_identity("ambiguous-legacy") is None
        assert conflict["binding"]["status"] == "quarantined"
        assert len(conflict["binding"]["candidate_identity_ids"]) == 2
        cursor = await store.db.execute(
            "SELECT COUNT(*) AS count FROM project_identity_conflicts WHERE legacy_project_id = ?",
            ("ambiguous-legacy",),
        )
        assert int((await cursor.fetchone())["count"]) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_legacy_rows_are_not_silently_inferred_into_v2_identity(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    try:
        await store.upsert_goal(
            Goal(
                id="legacy-goal",
                project_id="C:/possibly-remote-or-local",
                title="Legacy",
                objective="Remain readable without speculative identity inference.",
                created_at=now,
                updated_at=now,
            )
        )
        assert await store.resolve_project_identity("C:/possibly-remote-or-local") is None
        cursor = await store.db.execute("SELECT COUNT(*) AS count FROM project_identities")
        assert int((await cursor.fetchone())["count"]) == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_quarantine_revokes_project_credentials_and_blocks_reissue(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    project_id = "credential-project"
    goal = Goal(
        id="credential-goal",
        project_id=project_id,
        title="Credential boundary",
        objective="Fail closed if the project identity becomes ambiguous.",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id="cursor:credential-session",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="credential-session",
        project_id=project_id,
        goal_id=goal.id,
        status=SessionStatus.WORKING,
    )
    try:
        await store.register_project_locator(
            legacy_project_id=project_id,
            locator=_path("/workspace/credential-one"),
            now=now,
        )
        await store.upsert_goal(goal)
        await store.upsert_session(session)
        await store.issue_mcp_principal(
            principal_id="principal-project-identity",
            session_id=session.id,
            goal_id=goal.id,
            project_id=project_id,
            vendor_session_id=session.vendor_session_id,
            harness_type=session.harness_type.value,
            scopes=["mcp:read"],
            token_digest="a" * 64,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
        )
        await store.issue_hook_credential(
            credential_id="hook-project-identity",
            session_id=session.id,
            project_id=project_id,
            vendor_session_id=session.vendor_session_id,
            harness_type=session.harness_type.value,
            allowed_routes=[CURSOR_HOOK_ROUTE],
            token_digest="b" * 64,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
        )

        await store.register_project_locator(
            legacy_project_id=project_id,
            locator=_path("/workspace/credential-two"),
            now=now + timedelta(seconds=1),
        )
        assert await store.get_mcp_principal_by_digest("a" * 64, now=now) is None
        assert await store.get_hook_credential_by_digest("b" * 64, now=now) is None
        principal = await store.get_mcp_principal("principal-project-identity")
        assert principal is not None
        assert principal["revocation_reason"] == "project_identity_quarantined"

        with pytest.raises(ValueError, match="project identity is quarantined"):
            await store.issue_mcp_principal(
                principal_id="principal-project-identity-new",
                session_id=session.id,
                goal_id=goal.id,
                project_id=project_id,
                vendor_session_id=session.vendor_session_id,
                harness_type=session.harness_type.value,
                scopes=["mcp:read"],
                token_digest="c" * 64,
                issued_at=now + timedelta(seconds=2),
                expires_at=now + timedelta(hours=1),
            )
        with pytest.raises(ValueError, match="project identity is quarantined"):
            await store.issue_hook_credential(
                credential_id="hook-project-identity-new",
                session_id=session.id,
                project_id=project_id,
                vendor_session_id=session.vendor_session_id,
                harness_type=session.harness_type.value,
                allowed_routes=[CURSOR_HOOK_ROUTE],
                token_digest="d" * 64,
                issued_at=now + timedelta(seconds=2),
                expires_at=now + timedelta(hours=1),
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_canonical_aliases_and_workspace_order_replay_without_collision(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        windows_first = await store.register_project_locator(
            legacy_project_id="windows-a",
            locator=ProjectLocator.path(
                r"C:\Repo\.\src\..",
                platform=PathPlatform.WINDOWS,
                origin=MACHINE,
            ),
        )
        windows_alias = await store.register_project_locator(
            legacy_project_id="windows-b",
            locator=ProjectLocator.path(
                "c:/repo",
                platform=PathPlatform.WINDOWS,
                origin=MACHINE,
            ),
        )
        first = _path("/workspace/a")
        second = _path("/workspace/b")
        set_first = await store.register_project_locator(
            legacy_project_id="set-a",
            locator=ProjectLocator.workspace_set([first, second], origin=MACHINE),
        )
        set_alias = await store.register_project_locator(
            legacy_project_id="set-b",
            locator=ProjectLocator.workspace_set(
                [second, first],
                origin=MACHINE,
                display="same set in another order",
            ),
        )
        assert windows_alias["identity"].id == windows_first["identity"].id
        assert set_alias["identity"].id == set_first["identity"].id
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_same_path_new_physical_object_quarantines_instead_of_rolling_back(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    first_proof = PhysicalIdentityProof(
        provider="posix-stat",
        volume_id="dev-1",
        object_id="inode-1",
    )
    replacement_proof = PhysicalIdentityProof(
        provider="posix-stat",
        volume_id="dev-2",
        object_id="inode-2",
    )
    try:
        first = await store.register_project_locator(
            legacy_project_id="moving-path",
            locator=_path("/work/repo", physical=first_proof),
        )
        conflict = await store.register_project_locator(
            legacy_project_id="moving-path",
            locator=_path("/work/repo", physical=replacement_proof),
        )
        assert conflict["outcome"] == "quarantined"
        assert conflict["identity"].id != first["identity"].id
        assert await store.resolve_project_identity("moving-path") is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_resolution_is_idempotent_and_replay_reports_live_requarantine(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        first = await store.register_project_locator(
            legacy_project_id="resolution-project",
            locator=_path("/workspace/resolution-one"),
        )
        await store.register_project_locator(
            legacy_project_id="resolution-project",
            locator=_path("/workspace/resolution-two"),
        )
        resolved = await store.resolve_project_identity_conflict(
            resolution_id="project-resolution-1",
            legacy_project_id="resolution-project",
            selected_identity_id=first["identity"].id,
            resolved_by="local-operator",
            rationale="The first locator is the operator-confirmed workspace.",
        )
        replay = await store.resolve_project_identity_conflict(
            resolution_id="project-resolution-1",
            legacy_project_id="resolution-project",
            selected_identity_id=first["identity"].id,
            resolved_by="local-operator",
            rationale="The first locator is the operator-confirmed workspace.",
        )
        assert resolved["outcome"] == "resolved"
        assert replay["outcome"] == "replayed"
        assert replay["binding"]["status"] == "active"
        assert replay["resolution"]["credentials_restored"] is False

        await store.register_project_locator(
            legacy_project_id="resolution-project",
            locator=_path("/workspace/resolution-two"),
        )
        stale_replay = await store.resolve_project_identity_conflict(
            resolution_id="project-resolution-1",
            legacy_project_id="resolution-project",
            selected_identity_id=first["identity"].id,
            resolved_by="local-operator",
            rationale="The first locator is the operator-confirmed workspace.",
        )
        assert stale_replay["binding"]["status"] == "quarantined"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_live_quarantine_listing_pages_typed_candidates_and_disappears_on_resolution(
    tmp_path,
):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        first = await store.register_project_locator(
            legacy_project_id="listed-project",
            locator=_path("/workspace/listed-one"),
        )
        second = await store.register_project_locator(
            legacy_project_id="listed-project",
            locator=_path("/workspace/listed-two"),
        )

        page = await store.list_project_identity_conflicts_page(limit=10)
        assert page["total"] == 1
        assert page["next_offset"] is None
        assert page["items"] == [
            {
                "schema": "pex.project-identity-conflict-summary.v1",
                "legacy_project_id": "listed-project",
                "status": "quarantined",
                "candidate_identity_ids": sorted(
                    [first["identity"].id, second["identity"].id]
                ),
                "candidate_count": 2,
                "quarantined_at": second["binding"]["quarantined_at"],
                "updated_at": second["binding"]["updated_at"],
            }
        ]
        first_page = await store.get_project_identity_conflict(
            "listed-project",
            candidate_limit=1,
        )
        assert first_page is not None
        assert first_page["candidate_count"] == 2
        assert first_page["next_candidate_offset"] == 1
        assert len(first_page["candidates"]) == 1
        candidate = first_page["candidates"][0]
        assert candidate["identity"]["id"] in {
            first["identity"].id,
            second["identity"].id,
        }
        assert candidate["locators"][0]["schema"] == "pex.project-locator.v2"
        quarantined_status = await store.get_project_identity_status("listed-project")
        assert quarantined_status["status"] == "quarantined"
        assert quarantined_status["credential_reissue_blocked"] is True

        await store.resolve_project_identity_conflict(
            resolution_id="project-resolution-listed",
            legacy_project_id="listed-project",
            selected_identity_id=first["identity"].id,
            resolved_by="local-operator",
            rationale="The first typed locator is the confirmed workspace.",
        )
        assert (await store.list_project_identity_conflicts_page(limit=10))["items"] == []
        assert await store.get_project_identity_conflict("listed-project") is None
        active_status = await store.get_project_identity_status("listed-project")
        assert active_status["status"] == "active"
        assert active_status["fresh_credentials_required"] is True
        assert active_status["last_resolution"]["credentials_restored"] is False
        assert (await store.get_project_identity_status("unknown-project"))["status"] == (
            "unregistered"
        )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_quarantine_blocks_core_mutations_until_explicit_resolution(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    project_id = "mutation-project"
    goal = Goal(
        id="mutation-goal",
        project_id=project_id,
        title="Mutation boundary",
        objective="Stop writes while physical project identity is ambiguous.",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id="cursor:mutation-session",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="mutation-session",
        project_id=project_id,
        goal_id=goal.id,
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    try:
        await store.upsert_goal(goal)
        await store.upsert_session(session)
        first = await store.register_project_locator(
            legacy_project_id=project_id,
            locator=_path("/workspace/mutation-one"),
            now=now,
        )
        await store.register_project_locator(
            legacy_project_id=project_id,
            locator=_path("/workspace/mutation-two"),
            now=now + timedelta(seconds=1),
        )
        assert await store.get_goal(goal.id) is not None
        assert await store.get_session(session.id) is not None
        with pytest.raises(ValueError, match="project identity is quarantined"):
            await store.upsert_goal(
                goal.model_copy(update={"updated_at": now + timedelta(seconds=2)})
            )
        with pytest.raises(ValueError, match="project identity is quarantined"):
            await store.upsert_session(
                session.model_copy(update={"last_activity": now + timedelta(seconds=2)})
            )
        with pytest.raises(ValueError, match="project identity is quarantined"):
            await store.add_event(_event("mutation-record-only", session, goal))
        with pytest.raises(ValueError, match="project identity is quarantined"):
            await store.accept_pipeline_event(
                _event("mutation-pipeline", session, goal),
                session_snapshot=session,
            )

        paused_goal = goal.model_copy(
            update={"paused": True, "updated_at": now + timedelta(seconds=2)}
        )
        paused_session = session.model_copy(update={"supervision_paused": True})
        await store.upsert_goal(paused_goal)
        await store.upsert_session(paused_session, allow_supervision_change=True)
        with pytest.raises(ValueError, match="project identity is quarantined"):
            await store.upsert_goal(
                paused_goal.model_copy(
                    update={"paused": False, "updated_at": now + timedelta(seconds=3)}
                )
            )
        with pytest.raises(ValueError, match="project identity is quarantined"):
            await store.upsert_session(
                paused_session.model_copy(update={"supervision_paused": False}),
                allow_supervision_change=True,
            )

        await store.resolve_project_identity_conflict(
            resolution_id="project-resolution-mutation",
            legacy_project_id=project_id,
            selected_identity_id=first["identity"].id,
            resolved_by="local-operator",
            rationale="The first workspace is the confirmed project.",
        )
        resumed_goal = paused_goal.model_copy(
            update={"updated_at": now + timedelta(seconds=3)}
        )
        with pytest.raises(
            ProjectIdentityBlockedError,
            match="goal project identity changed after creation",
        ):
            await store.upsert_goal(resumed_goal)
        with pytest.raises(
            ProjectIdentityBlockedError,
            match="session project identity changed",
        ):
            await store.upsert_session(
                paused_session.model_copy(
                    update={"last_activity": now + timedelta(seconds=3)}
                )
            )
        with pytest.raises(ProjectIdentityBlockedError):
            await store.add_event(_event("mutation-resumed", session, goal))
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_quarantined_cwd_only_session_cannot_rebind_or_accept_unbound_events(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    cwd = "/workspace/cwd-only"
    session = HarnessSession(
        id="cursor:cwd-only",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="cwd-only",
        cwd=cwd,
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    try:
        await store.upsert_session(session)
        await store.register_project_locator(
            legacy_project_id=cwd,
            locator=_path(cwd),
            now=now,
        )
        await store.register_project_locator(
            legacy_project_id=cwd,
            locator=_path("/workspace/different-cwd"),
            now=now + timedelta(seconds=1),
        )
        with pytest.raises(ValueError, match="project identity is quarantined"):
            await store.upsert_session(
                session.model_copy(
                    update={
                        "project_id": "different-active-project",
                        "last_activity": now + timedelta(seconds=2),
                    }
                )
            )

        unbound = HarnessEvent(
            event_id="cwd-only-record",
            ts=now,
            harness_type=session.harness_type,
            session_id=session.id,
            event_type=EventType.AGENT_RESPONSE,
            message_delta="must not cross a quarantined cwd",
        )
        with pytest.raises(ValueError, match="project identity is quarantined"):
            await store.add_event(unbound.model_copy(deep=True))
        with pytest.raises(ValueError, match="project identity is quarantined"):
            await store.accept_pipeline_event(
                unbound.model_copy(update={"event_id": "cwd-only-pipeline"}),
                session_snapshot=session,
            )
        assert await store.get_event("cwd-only-record") is None
        assert await store.get_event("cwd-only-pipeline") is None
        stored = await store.get_session(session.id)
        assert stored is not None
        assert stored.project_id is None
        assert stored.cwd == cwd
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_quarantine_revokes_legacy_alias_credentials_bound_to_exact_session(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    project_id = r"C:\Repo"
    goal = Goal(
        id="alias-goal",
        project_id=project_id,
        title="Alias credentials",
        objective="Revoke old lexical aliases when the exact session binding is quarantined.",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id="cursor:alias-session",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="alias-session",
        project_id=project_id,
        goal_id=goal.id,
        status=SessionStatus.WORKING,
    )
    try:
        await store.upsert_goal(goal)
        await store.upsert_session(session)
        await store.issue_mcp_principal(
            principal_id="principal-project-alias",
            session_id=session.id,
            goal_id=goal.id,
            project_id=project_id,
            vendor_session_id=session.vendor_session_id,
            harness_type=session.harness_type.value,
            scopes=["mcp:read"],
            token_digest="e" * 64,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
        )
        await store.issue_hook_credential(
            credential_id="hook-project-alias",
            session_id=session.id,
            project_id=project_id,
            vendor_session_id=session.vendor_session_id,
            harness_type=session.harness_type.value,
            allowed_routes=[CURSOR_HOOK_ROUTE],
            token_digest="f" * 64,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
        )
        await store.register_project_locator(
            legacy_project_id=project_id,
            locator=ProjectLocator.path(
                project_id,
                platform=PathPlatform.WINDOWS,
                origin=MACHINE,
            ),
            now=now,
        )
        await store.register_project_locator(
            legacy_project_id=project_id,
            locator=ProjectLocator.path(
                r"C:\OtherRepo",
                platform=PathPlatform.WINDOWS,
                origin=MACHINE,
            ),
            now=now + timedelta(seconds=1),
        )
        assert await store.get_mcp_principal_by_digest("e" * 64, now=now) is None
        assert await store.get_hook_credential_by_digest("f" * 64, now=now) is None
        principal = await store.get_mcp_principal("principal-project-alias")
        assert principal is not None
        assert principal["revocation_reason"] == "project_identity_quarantined"
    finally:
        await store.close()
