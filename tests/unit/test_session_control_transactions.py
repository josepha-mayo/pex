from __future__ import annotations

import asyncio
import sqlite3
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.hook_auth import (
    CURSOR_HOOK_ROUTE,
    digest_hook_token,
    mint_hook_token,
)
from pex_bridge.mcp_auth import digest_mcp_session_token, mint_mcp_session_token
from pex_bridge.pets import PetSettings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store, goal_intent_semantic_hash, utcnow
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessSession

PROJECT_ID = "session-control-project"
ORIGIN = ProjectOrigin(namespace="machine", host="session-control-test-host")


def _goal(goal_id: str, *, supersedes: str | None = None) -> Goal:
    now = utcnow()
    return Goal(
        id=goal_id,
        project_id=PROJECT_ID,
        title=goal_id,
        objective=f"Complete {goal_id} without crossing session identity.",
        created_at=now,
        updated_at=now,
        supersedes=supersedes,
    )


def _session(*, generation: str = "discovery-1") -> HarnessSession:
    return HarnessSession(
        id="cursor:session-control",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="session-control",
        project_id=PROJECT_ID,
        cwd=PROJECT_ID,
        repo="https://example.invalid/session-control.git",
        branch="main",
        model="worker-model",
        reasoning_effort="high",
        status=SessionStatus.VERIFYING,
        context_health=0.73,
        last_activity=utcnow(),
        capabilities={"send_message": True, "stop": True},
        metadata={
            "source": "hook",
            "discovery_generation": generation,
            "adapter_observation": "must survive control mutations",
        },
    )


async def _seed(
    store: Store,
    *,
    goals: tuple[str, ...] = ("goal-a",),
    session: HarnessSession | None = None,
) -> tuple[HarnessSession, dict[str, Goal]]:
    records = {goal_id: _goal(goal_id) for goal_id in goals}
    for goal in records.values():
        await store.upsert_goal(goal)
    seeded = session or _session()
    await store.upsert_session(seeded)
    return seeded, records


async def _register_identity(store: Store, raw_path: str) -> str:
    result = await store.register_project_locator(
        legacy_project_id=PROJECT_ID,
        locator=ProjectLocator.path(
            raw_path,
            platform=PathPlatform.POSIX,
            origin=ORIGIN,
        ),
    )
    return result["identity"].id


async def _issue_bound_credentials(
    store: Store,
    session: HarnessSession,
    goal: Goal,
) -> tuple[str, str]:
    issued_at = utcnow()
    expires_at = issued_at + timedelta(hours=1)
    mcp_token = mint_mcp_session_token()
    mcp_digest = digest_mcp_session_token(mcp_token)
    await store.issue_mcp_principal(
        principal_id="mcp-session-control",
        session_id=session.id,
        goal_id=goal.id,
        project_id=PROJECT_ID,
        vendor_session_id=session.vendor_session_id,
        harness_type=session.harness_type.value,
        scopes=["mcp:read"],
        token_digest=mcp_digest,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    hook_token = mint_hook_token()
    hook_digest = digest_hook_token(hook_token)
    await store.issue_hook_credential(
        credential_id="hook-session-control",
        session_id=session.id,
        project_id=PROJECT_ID,
        vendor_session_id=session.vendor_session_id,
        harness_type=session.harness_type.value,
        allowed_routes=[CURSOR_HOOK_ROUTE],
        token_digest=hook_digest,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    return mcp_digest, hook_digest


@pytest.mark.asyncio
async def test_attach_no_replace_is_exact_and_replay_safe(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, goals = await _seed(store, goals=("goal-a", "goal-b"))
        stale_control = await store.attach_session_goal(
            session.id,
            goals["goal-a"].id,
            expected_goal_id=None,
            replace_existing=False,
            expected_control_revision=1,
            expected_goal_intent_revision=1,
        )
        assert stale_control["granted"] is False
        assert stale_control["reason"] == "session_control_revision_changed"
        stale_goal = await store.attach_session_goal(
            session.id,
            goals["goal-a"].id,
            expected_goal_id=None,
            replace_existing=False,
            expected_control_revision=0,
            expected_goal_intent_revision=2,
        )
        assert stale_goal["granted"] is False
        assert stale_goal["reason"] == "goal_intent_revision_changed"
        attached = await store.attach_session_goal(
            session.id,
            goals["goal-a"].id,
            expected_goal_id=None,
            replace_existing=False,
            expected_control_revision=0,
            expected_goal_intent_revision=1,
        )
        assert attached["granted"] is True
        assert attached["changed"] is True
        assert attached["session"].goal_id == goals["goal-a"].id
        assert attached["control_revision"] == 1
        assert attached["reason"] == "session_goal_attached"
        assert attached["before_control_revision"] == 0
        assert attached["after_control_revision"] == 1

        replay = await store.attach_session_goal(
            session.id,
            goals["goal-a"].id,
            expected_goal_id=None,
            replace_existing=False,
            expected_control_revision=1,
            expected_goal_intent_revision=1,
        )
        assert replay["granted"] is True
        assert replay["changed"] is False
        assert replay["reason"] == "session_goal_already_attached"
        assert replay["before_control_revision"] == replay["after_control_revision"] == 1

        false_prior = await store.attach_session_goal(
            session.id,
            goals["goal-a"].id,
            expected_goal_id=goals["goal-b"].id,
            replace_existing=True,
            expected_control_revision=1,
            expected_goal_intent_revision=1,
        )
        assert false_prior["granted"] is False
        assert false_prior["changed"] is False
        assert false_prior["reason"] == "session_goal_changed"
        assert false_prior["control_revision"] == 1

        refused = await store.attach_session_goal(
            session.id,
            goals["goal-b"].id,
            expected_goal_id=None,
            replace_existing=False,
        )
        assert refused["granted"] is False
        assert refused["reason"] == "session_goal_changed"
        assert (await store.get_session(session.id)).goal_id == goals["goal-a"].id
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_corrupt_goal_authority_cannot_commit_session_attachment(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, goals = await _seed(store, goals=("goal-a",))
        authority = await store.db.execute(
            "SELECT intent_revision, intent_hash FROM goals WHERE id = ?",
            (goals["goal-a"].id,),
        )
        row = await authority.fetchone()
        assert row is not None
        forged = "f" * 64 if row["intent_hash"] != "f" * 64 else "e" * 64
        await store.db.execute(
            "UPDATE goals SET intent_revision = ?, intent_hash = ? WHERE id = ?",
            (int(row["intent_revision"]) + 1, forged, goals["goal-a"].id),
        )
        await store.db.commit()

        with pytest.raises(RuntimeError, match="intent hash is corrupt"):
            await store.attach_session_goal(
                session.id,
                goals["goal-a"].id,
                expected_goal_id=None,
                replace_existing=False,
            )
        control = await store.get_session_control_state(session.id)
        assert control is not None
        assert control["session"].goal_id is None
        assert control["control_revision"] == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_concurrent_no_replace_attach_grants_exactly_one_goal(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, goals = await _seed(store, goals=("goal-a", "goal-b"))

        first, second = await asyncio.gather(
            store.attach_session_goal(
                session.id,
                goals["goal-a"].id,
                expected_goal_id=None,
                replace_existing=False,
            ),
            store.attach_session_goal(
                session.id,
                goals["goal-b"].id,
                expected_goal_id=None,
                replace_existing=False,
            ),
        )
        granted = [item for item in (first, second) if item["granted"]]
        refused = [item for item in (first, second) if not item["granted"]]
        assert len(granted) == 1
        assert len(refused) == 1
        assert refused[0]["reason"] == "session_goal_changed"
        stored = await store.get_session(session.id)
        assert stored is not None
        assert stored.goal_id == granted[0]["session"].goal_id
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_attach_and_goal_supersede_race_never_leaves_predecessor_attached(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, goals = await _seed(store)
        successor = _goal("goal-successor", supersedes=goals["goal-a"].id)

        attach_result, supersede_result = await asyncio.gather(
            store.attach_session_goal(
                session.id,
                goals["goal-a"].id,
                expected_goal_id=None,
                replace_existing=False,
            ),
            store.supersede_goal(goals["goal-a"].id, successor),
            return_exceptions=True,
        )
        assert not isinstance(supersede_result, Exception)
        assert not isinstance(attach_result, AttributeError)
        stored = await store.get_session(session.id)
        assert stored is not None
        assert stored.goal_id in {None, successor.id}
        if isinstance(attach_result, dict) and not attach_result["granted"]:
            assert attach_result["reason"] == "goal_superseded"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_attach_mutates_only_goal_control_fields_and_preserves_live_telemetry(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, goals = await _seed(store)
        before = await store.get_session(session.id)
        assert before is not None

        attached = await store.attach_session_goal(
            session.id,
            goals["goal-a"].id,
            expected_goal_id=None,
            replace_existing=False,
        )
        after = attached["session"]
        assert after.goal_id == goals["goal-a"].id
        before_payload = before.model_dump(exclude={"goal_id"})
        after_payload = after.model_dump(exclude={"goal_id"})
        assert after_payload == before_payload
        assert await store.get_session(session.id) == after
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_explicit_replace_requires_exact_old_goal_and_revokes_mcp_atomically(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, goals = await _seed(store, goals=("goal-a", "goal-b"))
        attached = await store.attach_session_goal(
            session.id,
            goals["goal-a"].id,
            expected_goal_id=None,
            replace_existing=False,
        )
        mcp_digest, hook_digest = await _issue_bound_credentials(
            store,
            attached["session"],
            goals["goal-a"],
        )

        missing_cas = await store.attach_session_goal(
            session.id,
            goals["goal-b"].id,
            expected_goal_id=None,
            replace_existing=True,
        )
        assert missing_cas["granted"] is False
        assert missing_cas["reason"] == "session_goal_changed"
        assert await store.get_mcp_principal_by_digest(mcp_digest) is not None

        replaced = await store.attach_session_goal(
            session.id,
            goals["goal-b"].id,
            expected_goal_id=goals["goal-a"].id,
            replace_existing=True,
        )
        assert replaced["granted"] is True
        assert replaced["changed"] is True
        assert replaced["session"].goal_id == goals["goal-b"].id
        assert replaced["reason"] == "session_goal_replaced"
        assert replaced["before_control_revision"] == 1
        assert replaced["after_control_revision"] == 2
        assert replaced["mcp_principals_revoked"] == 1
        assert replaced["hook_credentials_revoked"] == 1
        assert await store.get_mcp_principal_by_digest(mcp_digest) is None
        assert await store.get_hook_credential_by_digest(hook_digest) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_replace_rolls_back_goal_if_mcp_revocation_fails(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, goals = await _seed(store, goals=("goal-a", "goal-b"))
        attached = await store.attach_session_goal(
            session.id,
            goals["goal-a"].id,
            expected_goal_id=None,
            replace_existing=False,
        )
        await _issue_bound_credentials(store, attached["session"], goals["goal-a"])
        await store.db.execute(
            "CREATE TRIGGER fail_mcp_revoke BEFORE UPDATE OF revoked_at "
            "ON mcp_principals WHEN NEW.revoked_at IS NOT NULL BEGIN "
            "SELECT RAISE(ABORT, 'forced attach rollback'); END"
        )
        await store.db.commit()

        with pytest.raises(sqlite3.IntegrityError, match="forced attach rollback"):
            await store.attach_session_goal(
                session.id,
                goals["goal-b"].id,
                expected_goal_id=goals["goal-a"].id,
                replace_existing=True,
            )
        current = await store.get_session(session.id)
        assert current is not None
        assert current.goal_id == goals["goal-a"].id
        principal = await store.db.execute(
            "SELECT revoked_at FROM mcp_principals WHERE session_id = ?",
            (session.id,),
        )
        assert (await principal.fetchone())["revoked_at"] is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_attach_route_requires_client_expected_goal_for_explicit_replace(tmp_path):
    settings = Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = None
    state.pet_settings = PetSettings()
    state.pet_path = tmp_path / "pet.json"
    await store.connect()
    try:
        session, goals = await _seed(store, goals=("goal-a", "goal-b"))
        await store.attach_session_goal(
            session.id,
            goals["goal-a"].id,
            expected_goal_id=None,
            replace_existing=False,
        )
        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            missing_cas = await client.post(
                f"/v1/sessions/{session.id}/attach",
                json={"goal_id": goals["goal-b"].id, "replace_existing": True},
            )
            assert missing_cas.status_code == 409
            assert (await store.get_session(session.id)).goal_id == goals["goal-a"].id

            replaced = await client.post(
                f"/v1/sessions/{session.id}/attach",
                json={
                    "goal_id": goals["goal-b"].id,
                    "replace_existing": True,
                    "expected_goal_id": goals["goal-a"].id,
                },
            )
            assert replaced.status_code == 200
            assert replaced.json()["goal_id"] == goals["goal-b"].id
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_pause_resume_routes_require_operator_auth_and_return_exact_receipts(tmp_path):
    settings = Settings(require_auth=True, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = "pause-resume-operator-token-000001"
    state.pet_settings = PetSettings()
    state.pet_path = tmp_path / "pet.json"
    await store.connect()
    try:
        await _register_identity(store, "/work/session-control-route")
        session, _ = await _seed(store)
        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            path = f"/v1/sessions/{session.id}/pause-supervision"
            assert (await client.post(path)).status_code == 401
            assert (
                await client.post(path, headers={"Authorization": "Bearer wrong"})
            ).status_code == 401
            token = state.token
            state.token = None
            assert (await client.post(path)).status_code == 503
            state.token = token
            headers = {"Authorization": f"Bearer {token}"}
            paused = await client.post(path, headers=headers)
            assert paused.status_code == 200
            pause_receipt = paused.json()["human_action_receipt"]
            assert pause_receipt["action_kind"] == "pause_supervision"
            assert pause_receipt["actor_assurance"] == "bridge_bearer"

            replay = await client.post(path, headers=headers)
            assert replay.status_code == 200
            assert replay.json()["human_action_receipt"] is None

            resumed = await client.post(
                f"/v1/sessions/{session.id}/resume-supervision",
                headers=headers,
            )
            assert resumed.status_code == 200
            assert resumed.json()["human_action_receipt"]["action_kind"] == (
                "resume_supervision"
            )
            metrics = await client.get("/v1/attention/metrics", headers=headers)
            assert metrics.status_code == 200
            assert metrics.json()["human_interventions"]["source_counts"][
                "supervision_control"
            ] == 2
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_pause_route_refuses_test_only_no_auth_before_store_access(tmp_path, monkeypatch):
    settings = Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = None
    state.pet_settings = PetSettings()
    state.pet_path = tmp_path / "pet.json"
    await store.connect()
    try:
        touched = False

        async def forbidden_lookup(_session_id: str):
            nonlocal touched
            touched = True
            raise AssertionError("auth denial must happen before Store access")

        monkeypatch.setattr(store, "get_session_control_state", forbidden_lookup)
        transport = ASGITransport(app=create_app())
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            response = await client.post(
                "/v1/sessions/synthetic:any/pause-supervision"
            )
        assert response.status_code == 403
        assert touched is False
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_attach_cannot_cross_typed_project_rebinding(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        identity_a = await _register_identity(store, "/work/session-control-a")
        session, goals = await _seed(store)
        control = await store.get_session_control_state(session.id)
        assert control is not None
        assert control["project_binding"] == f"identity:{identity_a}"

        conflict = await store.register_project_locator(
            legacy_project_id=PROJECT_ID,
            locator=ProjectLocator.path(
                "/work/session-control-b",
                platform=PathPlatform.POSIX,
                origin=ORIGIN,
            ),
        )
        await store.resolve_project_identity_conflict(
            resolution_id="resolve-attach-session-control-to-b",
            legacy_project_id=PROJECT_ID,
            selected_identity_id=conflict["identity"].id,
            resolved_by="test_operator",
            rationale="Select the second physical checkout.",
        )

        refused = await store.attach_session_goal(
            session.id,
            goals["goal-a"].id,
            expected_goal_id=None,
            replace_existing=False,
        )
        assert refused["granted"] is False
        assert refused["reason"] == "session_project_identity_changed"
        assert (await store.get_session(session.id)).goal_id is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_attach_rejects_paused_goal_and_non_live_session(tmp_path):
    paused_store = Store(tmp_path / "paused.sqlite")
    await paused_store.connect()
    try:
        session, goals = await _seed(paused_store)
        paused_goal = goals["goal-a"].model_copy(
            update={"paused": True, "updated_at": utcnow()}
        )
        await paused_store.patch_goal_with_ledger(goals["goal-a"], paused_goal, [])
        refused = await paused_store.attach_session_goal(
            session.id,
            paused_goal.id,
            expected_goal_id=None,
            replace_existing=False,
        )
        assert refused["granted"] is False
        assert refused["reason"] == "goal_paused"
    finally:
        await paused_store.close()

    for label, session in (
        ("detached", _session().model_copy(update={"status": SessionStatus.DETACHED})),
        (
            "not-live",
            _session().model_copy(
                update={"metadata": {**_session().metadata, "not_live_control": True}}
            ),
        ),
        (
            "observe-only",
            _session().model_copy(
                update={"metadata": {**_session().metadata, "observe_only": True}}
            ),
        ),
    ):
        store = Store(tmp_path / f"{label}.sqlite")
        await store.connect()
        try:
            seeded, goals = await _seed(store, session=session)
            refused = await store.attach_session_goal(
                seeded.id,
                goals["goal-a"].id,
                expected_goal_id=None,
                replace_existing=False,
            )
            assert refused["granted"] is False
            assert refused["reason"] == "session_not_live_control"
        finally:
            await store.close()


@pytest.mark.asyncio
async def test_telemetry_upsert_cannot_refresh_a_frozen_typed_identity(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register_identity(store, "/work/session-control-a")
        session, _ = await _seed(store)
        conflict = await store.register_project_locator(
            legacy_project_id=PROJECT_ID,
            locator=ProjectLocator.path(
                "/work/session-control-b",
                platform=PathPlatform.POSIX,
                origin=ORIGIN,
            ),
        )
        await store.resolve_project_identity_conflict(
            resolution_id="resolve-telemetry-session-control-to-b",
            legacy_project_id=PROJECT_ID,
            selected_identity_id=conflict["identity"].id,
            resolved_by="test_operator",
            rationale="Select the second physical checkout.",
        )
        telemetry = session.model_copy(deep=True)
        telemetry.last_activity = session.last_activity + timedelta(seconds=1)
        telemetry.context_health = 0.99

        with pytest.raises(ValueError, match="session project identity changed"):
            await store.upsert_session(telemetry)
        assert (await store.get_session(session.id)).context_health == session.context_health
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_pause_uses_live_row_and_preserves_newer_telemetry(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, _ = await _seed(store)
        newer = session.model_copy(deep=True)
        newer.last_activity = session.last_activity + timedelta(seconds=1)
        newer.status = SessionStatus.WORKING
        newer.context_health = 0.91
        newer.capabilities["approve"] = True
        newer.metadata["adapter_observation"] = "newer telemetry"
        await store.upsert_session(newer)

        paused = await store.set_session_supervision_paused(
            session.id,
            paused=True,
            expected_control_revision=0,
        )
        assert paused["granted"] is True
        assert paused["changed"] is True
        assert paused["session"].supervision_paused is True
        assert paused["session"].status == newer.status
        assert paused["session"].last_activity == newer.last_activity
        assert paused["session"].context_health == newer.context_health
        assert paused["session"].capabilities == newer.capabilities
        assert paused["session"].metadata == newer.metadata
        assert (await store.get_session(session.id)).supervision_paused is True
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_pause_resume_replay_is_exact_and_stale_opposite_cas_is_refused(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, _ = await _seed(store)
        control = await store.get_session_control_state(session.id)
        assert control is not None

        paused = await store.set_session_supervision_paused(
            session.id,
            paused=True,
            expected_control_revision=control["control_revision"],
        )
        pause_replay = await store.set_session_supervision_paused(
            session.id,
            paused=True,
            expected_control_revision=control["control_revision"],
        )
        assert pause_replay["granted"] is True
        assert pause_replay["changed"] is False
        assert pause_replay["control_revision"] == paused["control_revision"]

        stale_resume = await store.set_session_supervision_paused(
            session.id,
            paused=False,
            expected_control_revision=control["control_revision"],
        )
        assert stale_resume["granted"] is False
        assert stale_resume["reason"] == "session_control_revision_changed"
        assert stale_resume["session"].supervision_paused is True

        resumed = await store.set_session_supervision_paused(
            session.id,
            paused=False,
            expected_control_revision=paused["control_revision"],
        )
        resume_replay = await store.set_session_supervision_paused(
            session.id,
            paused=False,
            expected_control_revision=paused["control_revision"],
        )
        assert resumed["granted"] is True
        assert resume_replay["granted"] is True
        assert resume_replay["changed"] is False
        assert resume_replay["control_revision"] == resumed["control_revision"]
        receipts = await store.db.execute(
            "SELECT COUNT(*) FROM human_session_control_actions"
        )
        assert (await receipts.fetchone())[0] == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_assured_pause_resume_receipts_are_atomic_append_only_and_replay_safe(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register_identity(store, "/work/session-control-receipts")
        session, _ = await _seed(store)
        control = await store.get_session_control_state(session.id)
        assert control is not None

        paused = await store.set_session_supervision_paused(
            session.id,
            paused=True,
            expected_control_revision=control["control_revision"],
            principal_id="local_bridge_operator",
            actor_assurance="bridge_bearer",
        )
        pause_receipt = paused["human_action_receipt"]
        assert pause_receipt["schema"] == "pex.human-action-receipt.v1"
        assert pause_receipt["action_kind"] == "pause_supervision"
        assert pause_receipt["principal_id"] == "local_bridge_operator"
        assert pause_receipt["actor_assurance"] == "bridge_bearer"
        assert pause_receipt["session_id"] == session.id
        assert pause_receipt["before_control_revision"] == control["control_revision"]
        assert pause_receipt["after_control_revision"] == paused["control_revision"]
        assert pause_receipt["before_session_sha256"] != pause_receipt[
            "after_session_sha256"
        ]

        replay = await store.set_session_supervision_paused(
            session.id,
            paused=True,
            expected_control_revision=control["control_revision"],
            principal_id="local_bridge_operator",
            actor_assurance="bridge_bearer",
        )
        assert replay["changed"] is False
        assert "human_action_receipt" not in replay

        resumed = await store.set_session_supervision_paused(
            session.id,
            paused=False,
            expected_control_revision=paused["control_revision"],
            principal_id="local_bridge_operator",
            actor_assurance="bridge_bearer",
        )
        assert resumed["human_action_receipt"]["action_kind"] == "resume_supervision"

        cursor = await store.db.execute(
            "SELECT id, json FROM human_session_control_actions "
            "ORDER BY after_control_revision"
        )
        rows = await cursor.fetchall()
        assert len(rows) == 2
        assert rows[0]["id"] == pause_receipt["id"]
        assert rows[1]["id"] == resumed["human_action_receipt"]["id"]
        coverage = await store.db.execute(
            "SELECT action_kind, coverage_started_at "
            "FROM human_session_control_coverage "
            "ORDER BY action_kind"
        )
        coverage_rows = await coverage.fetchall()
        assert [row["action_kind"] for row in coverage_rows] == [
            "pause_supervision",
            "resume_supervision",
        ]
        assert len({row["coverage_started_at"] for row in coverage_rows}) == 1

        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            await store.db.execute(
                "UPDATE human_session_control_actions SET principal_id = 'forged' "
                "WHERE id = ?",
                (pause_receipt["id"],),
            )
        await store.db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            await store.db.execute(
                "DELETE FROM human_session_control_actions WHERE id = ?",
                (pause_receipt["id"],),
            )
        await store.db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="coverage is immutable"):
            await store.db.execute(
                "UPDATE human_session_control_coverage SET schema_version = 2 "
                "WHERE action_kind = 'pause_supervision'"
            )
        await store.db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="coverage is append-only"):
            await store.db.execute(
                "DELETE FROM human_session_control_coverage "
                "WHERE action_kind = 'pause_supervision'"
            )
        await store.db.rollback()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_assured_pause_receipt_failure_rolls_back_session_state(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, _ = await _seed(store)
        control = await store.get_session_control_state(session.id)
        assert control is not None
        with pytest.raises(ValueError, match="supplied together"):
            await store.set_session_supervision_paused(
                session.id,
                paused=True,
                expected_control_revision=control["control_revision"],
                principal_id="local_bridge_operator",
            )
        with pytest.raises(ValueError, match="assurance is invalid"):
            await store.set_session_supervision_paused(
                session.id,
                paused=True,
                expected_control_revision=control["control_revision"],
                principal_id="local_bridge_operator",
                actor_assurance="claimed_by_caller",
            )
        await store.db.execute(
            "CREATE TRIGGER fail_human_action_receipt BEFORE INSERT "
            "ON human_session_control_actions BEGIN "
            "SELECT RAISE(ABORT, 'forced receipt rollback'); END"
        )
        await store.db.commit()

        with pytest.raises(sqlite3.IntegrityError, match="forced receipt rollback"):
            await store.set_session_supervision_paused(
                session.id,
                paused=True,
                expected_control_revision=control["control_revision"],
                principal_id="local_bridge_operator",
                actor_assurance="bridge_bearer",
            )
        current = await store.get_session_control_state(session.id)
        assert current is not None
        assert current["control_revision"] == control["control_revision"]
        assert current["session"].supervision_paused is False
        count = await store.db.execute(
            "SELECT COUNT(*) FROM human_session_control_actions"
        )
        assert (await count.fetchone())[0] == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_resume_rejects_detached_session_and_paused_or_superseded_goal(tmp_path):
    detached_store = Store(tmp_path / "detached.sqlite")
    await detached_store.connect()
    try:
        session, _ = await _seed(detached_store)
        paused = await detached_store.set_session_supervision_paused(
            session.id,
            paused=True,
            expected_control_revision=0,
        )
        detached = await detached_store.mark_session_detached(
            session.id,
            expected_revision=paused["revision"],
            expected_discovery_generation="discovery-1",
        )
        refused = await detached_store.set_session_supervision_paused(
            session.id,
            paused=False,
            expected_control_revision=detached["control_revision"],
        )
        assert refused["granted"] is False
        assert refused["reason"] == "session_not_live_control"
    finally:
        await detached_store.close()

    paused_goal_store = Store(tmp_path / "paused-goal.sqlite")
    await paused_goal_store.connect()
    try:
        session, goals = await _seed(paused_goal_store)
        attached = await paused_goal_store.attach_session_goal(
            session.id,
            goals["goal-a"].id,
            expected_goal_id=None,
            replace_existing=False,
        )
        paused = await paused_goal_store.set_session_supervision_paused(
            session.id,
            paused=True,
            expected_control_revision=attached["control_revision"],
        )
        paused_goal = goals["goal-a"].model_copy(
            update={"paused": True, "updated_at": utcnow()}
        )
        await paused_goal_store.patch_goal_with_ledger(goals["goal-a"], paused_goal, [])
        refused = await paused_goal_store.set_session_supervision_paused(
            session.id,
            paused=False,
            expected_control_revision=paused["control_revision"],
        )
        assert refused["granted"] is False
        assert refused["reason"] == "goal_paused"

        unpaused_goal = paused_goal.model_copy(
            update={"paused": False, "updated_at": utcnow()}
        )
        await paused_goal_store.patch_goal_with_ledger(
            paused_goal,
            unpaused_goal,
            [],
        )
        successor = _goal("goal-successor", supersedes=goals["goal-a"].id)
        binding_cursor = await paused_goal_store.db.execute(
            "SELECT project_id, project_binding, intent_revision FROM goals WHERE id = ?",
            (goals["goal-a"].id,),
        )
        binding_row = await binding_cursor.fetchone()
        assert binding_row is not None
        await paused_goal_store.db.execute(
            "INSERT INTO goals(id, project_id, project_binding, intent_revision, "
            "intent_hash, json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                successor.id,
                binding_row["project_id"],
                binding_row["project_binding"],
                int(binding_row["intent_revision"]) + 1,
                goal_intent_semantic_hash(successor),
                successor.model_dump_json(),
            ),
        )
        await paused_goal_store.db.commit()
        superseded = await paused_goal_store.set_session_supervision_paused(
            session.id,
            paused=False,
            expected_control_revision=paused["control_revision"],
        )
        assert superseded["granted"] is False
        assert superseded["reason"] == "goal_superseded"
    finally:
        await paused_goal_store.close()


@pytest.mark.asyncio
async def test_pause_survives_quarantine_but_resume_requires_exact_typed_snapshot(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        identity_a = await _register_identity(store, "/work/session-control-a")
        session, _ = await _seed(store)
        control = await store.get_session_control_state(session.id)
        assert control is not None
        assert control["project_binding"] == f"identity:{identity_a}"

        paused = await store.set_session_supervision_paused(
            session.id,
            paused=True,
            expected_control_revision=control["control_revision"],
        )
        resumed = await store.set_session_supervision_paused(
            session.id,
            paused=False,
            expected_control_revision=paused["control_revision"],
        )
        assert resumed["granted"] is True
        assert resumed["session"].supervision_paused is False

        conflict = await store.register_project_locator(
            legacy_project_id=PROJECT_ID,
            locator=ProjectLocator.path(
                "/work/session-control-b",
                platform=PathPlatform.POSIX,
                origin=ORIGIN,
            ),
        )
        assert conflict["outcome"] == "quarantined"
        quarantined_pause = await store.set_session_supervision_paused(
            session.id,
            paused=True,
            expected_control_revision=resumed["control_revision"],
        )
        assert quarantined_pause["granted"] is True
        assert quarantined_pause["session"].supervision_paused is True
        quarantined_resume = await store.set_session_supervision_paused(
            session.id,
            paused=False,
            expected_control_revision=quarantined_pause["control_revision"],
        )
        assert quarantined_resume["granted"] is False
        assert quarantined_resume["reason"] == "project_identity_quarantined"
        assert quarantined_resume["session"].supervision_paused is True

        identity_b = conflict["identity"].id
        await store.resolve_project_identity_conflict(
            resolution_id="resolve-session-control-to-b",
            legacy_project_id=PROJECT_ID,
            selected_identity_id=identity_b,
            resolved_by="test_operator",
            rationale="Select the second physical checkout.",
        )
        refused = await store.set_session_supervision_paused(
            session.id,
            paused=False,
            expected_control_revision=quarantined_pause["control_revision"],
        )
        assert refused["granted"] is False
        assert refused["reason"] == "session_project_identity_changed"
        assert refused["session"].supervision_paused is True
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_detach_revision_and_generation_cas_preserves_a_new_heartbeat(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, _ = await _seed(store)
        stale = await store.get_session_control_state(session.id)
        assert stale is not None
        heartbeat = session.model_copy(deep=True)
        heartbeat.last_activity = session.last_activity + timedelta(seconds=1)
        heartbeat.metadata["discovery_generation"] = "discovery-2"
        await store.upsert_session(heartbeat)

        refused = await store.mark_session_detached(
            session.id,
            expected_revision=stale["revision"],
            expected_discovery_generation="discovery-1",
        )
        assert refused["granted"] is False
        assert refused["reason"] == "session_revision_changed"
        current = await store.get_session(session.id)
        assert current is not None
        assert current.status != SessionStatus.DETACHED
        assert current.metadata["discovery_generation"] == "discovery-2"

        current_control = await store.get_session_control_state(session.id)
        assert current_control is not None
        generation_refused = await store.mark_session_detached(
            session.id,
            expected_revision=current_control["revision"],
            expected_discovery_generation="discovery-1",
        )
        assert generation_refused["granted"] is False
        assert generation_refused["reason"] == "discovery_generation_changed"
        assert generation_refused["session"].status != SessionStatus.DETACHED
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_detach_atomically_revokes_credentials_and_they_never_resurrect(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, goals = await _seed(store)
        attached = await store.attach_session_goal(
            session.id,
            goals["goal-a"].id,
            expected_goal_id=None,
            replace_existing=False,
        )
        mcp_digest, hook_digest = await _issue_bound_credentials(
            store,
            attached["session"],
            goals["goal-a"],
        )
        control = await store.get_session_control_state(session.id)
        assert control is not None

        detached = await store.mark_session_detached(
            session.id,
            expected_revision=control["revision"],
            expected_discovery_generation="discovery-1",
        )
        assert detached["granted"] is True
        assert detached["session"].status == SessionStatus.DETACHED
        assert detached["control_revision"] == control["control_revision"] + 1
        assert detached["mcp_principals_revoked"] == 1
        assert detached["hook_credentials_revoked"] == 1
        assert await store.get_mcp_principal_by_digest(mcp_digest) is None
        assert await store.get_hook_credential_by_digest(hook_digest) is None

        revived = detached["session"].model_copy(
            update={
                "status": SessionStatus.WORKING,
                "last_activity": utcnow(),
            }
        )
        await store.db.execute(
            "UPDATE sessions SET json = ? WHERE id = ?",
            (revived.model_dump_json(), revived.id),
        )
        await store.db.commit()
        assert await store.get_mcp_principal_by_digest(mcp_digest) is None
        assert await store.get_hook_credential_by_digest(hook_digest) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_detach_is_allowed_as_containment_through_project_quarantine(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register_identity(store, "/work/session-control-a")
        session, goals = await _seed(store)
        attached = await store.attach_session_goal(
            session.id,
            goals["goal-a"].id,
            expected_goal_id=None,
            replace_existing=False,
        )
        mcp_digest, hook_digest = await _issue_bound_credentials(
            store,
            attached["session"],
            goals["goal-a"],
        )
        conflict = await store.register_project_locator(
            legacy_project_id=PROJECT_ID,
            locator=ProjectLocator.path(
                "/work/session-control-b",
                platform=PathPlatform.POSIX,
                origin=ORIGIN,
            ),
        )
        assert conflict["outcome"] == "quarantined"
        control = await store.get_session_control_state(session.id)
        assert control is not None

        detached = await store.mark_session_detached(
            session.id,
            expected_revision=control["revision"],
            expected_discovery_generation="discovery-1",
        )
        assert detached["granted"] is True
        assert detached["session"].status == SessionStatus.DETACHED
        assert await store.get_mcp_principal_by_digest(mcp_digest) is None
        assert await store.get_hook_credential_by_digest(hook_digest) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_detach_rolls_back_status_and_both_credential_revocations_together(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, goals = await _seed(store)
        attached = await store.attach_session_goal(
            session.id,
            goals["goal-a"].id,
            expected_goal_id=None,
            replace_existing=False,
        )
        await _issue_bound_credentials(store, attached["session"], goals["goal-a"])
        control = await store.get_session_control_state(session.id)
        assert control is not None
        await store.db.execute(
            "CREATE TRIGGER fail_hook_revoke BEFORE UPDATE OF revoked_at "
            "ON hook_credentials WHEN NEW.revoked_at IS NOT NULL BEGIN "
            "SELECT RAISE(ABORT, 'forced detach rollback'); END"
        )
        await store.db.commit()

        with pytest.raises(sqlite3.IntegrityError, match="forced detach rollback"):
            await store.mark_session_detached(
                session.id,
                expected_revision=control["revision"],
                expected_discovery_generation="discovery-1",
            )
        current = await store.get_session(session.id)
        assert current is not None
        assert current.status != SessionStatus.DETACHED
        mcp = await store.db.execute(
            "SELECT revoked_at FROM mcp_principals WHERE session_id = ?",
            (session.id,),
        )
        hook = await store.db.execute(
            "SELECT revoked_at FROM hook_credentials WHERE session_id = ?",
            (session.id,),
        )
        assert (await mcp.fetchone())["revoked_at"] is None
        assert (await hook.fetchone())["revoked_at"] is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_attach_rejects_goal_created_before_typed_identity_reresolution(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _register_identity(store, "/work/session-control-identity-a")
        goal = _goal("goal-created-under-a")
        await store.upsert_goal(goal)
        conflict = await store.register_project_locator(
            legacy_project_id=PROJECT_ID,
            locator=ProjectLocator.path(
                "/work/session-control-identity-b",
                platform=PathPlatform.POSIX,
                origin=ORIGIN,
            ),
        )
        await store.resolve_project_identity_conflict(
            resolution_id="resolve-attach-to-identity-b",
            legacy_project_id=PROJECT_ID,
            selected_identity_id=conflict["identity"].id,
            resolved_by="test_operator",
            rationale="Select the newly verified physical checkout.",
        )
        session = _session()
        await store.upsert_session(session)

        refused = await store.attach_session_goal(
            session.id,
            goal.id,
            expected_goal_id=None,
            replace_existing=False,
        )

        assert refused["granted"] is False
        assert refused["changed"] is False
        assert refused["reason"] == "artifact_project_identity_changed"
        assert refused["session"].goal_id is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_attach_rejects_untyped_goal_after_typed_registration(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        goal = _goal("goal-created-before-typing")
        await store.upsert_goal(goal)
        await _register_identity(store, "/work/session-control-now-typed")
        session = _session()
        await store.upsert_session(session)

        refused = await store.attach_session_goal(
            session.id,
            goal.id,
            expected_goal_id=None,
            replace_existing=False,
        )

        assert refused["granted"] is False
        assert refused["changed"] is False
        assert refused["reason"] == "artifact_project_identity_changed"
        assert refused["session"].goal_id is None
    finally:
        await store.close()
