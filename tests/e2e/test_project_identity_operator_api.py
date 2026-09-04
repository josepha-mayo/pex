from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.hook_auth import digest_hook_token
from pex_bridge.mcp_auth import digest_mcp_session_token
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin


async def _open_operator_app(tmp_path, token: str):
    settings = Settings(require_auth=True, home=tmp_path, codex_attach=False)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = token
    await store.connect()
    return create_app(), store


async def test_operator_project_identity_conflict_flow_is_authenticated_and_replay_safe(
    tmp_path,
):
    settings = Settings(require_auth=True, home=tmp_path, codex_attach=False)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    token = "project-identity-operator-token-0001"
    state.token = token
    headers = {"Authorization": f"Bearer {token}"}
    origin = ProjectOrigin(namespace="machine", host="operator-api-test")
    first_locator = ProjectLocator.path(
        "/workspace/operator-one",
        platform=PathPlatform.POSIX,
        origin=origin,
    )
    second_locator = ProjectLocator.path(
        "/workspace/operator-two",
        platform=PathPlatform.POSIX,
        origin=origin,
    )
    await store.connect()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://127.0.0.1",
        ) as client:
            register_url = "/v1/project-identities/locators"
            assert (
                await client.post(
                    register_url,
                    json={
                        "legacy_project_id": "operator-project",
                        "locator": first_locator.model_dump(mode="json"),
                    },
                )
            ).status_code == 401

            first = await client.post(
                register_url,
                headers=headers,
                json={
                    "legacy_project_id": "operator-project",
                    "locator": first_locator.model_dump(mode="json"),
                },
            )
            assert first.status_code == 200, first.text
            assert first.json()["outcome"] == "created"
            first_identity_id = first.json()["identity"]["id"]

            quarantined = await client.post(
                register_url,
                headers=headers,
                json={
                    "legacy_project_id": "operator-project",
                    "locator": second_locator.model_dump(mode="json"),
                },
            )
            assert quarantined.status_code == 200, quarantined.text
            assert quarantined.json()["outcome"] == "quarantined"
            second_identity_id = quarantined.json()["identity"]["id"]

            assert (
                await client.get("/v1/project-identities/conflicts")
            ).status_code == 401
            conflicts = await client.get(
                "/v1/project-identities/conflicts",
                headers=headers,
            )
            assert conflicts.status_code == 200, conflicts.text
            assert conflicts.json()["total"] == 1
            assert conflicts.json()["items"][0]["legacy_project_id"] == "operator-project"
            assert set(conflicts.json()["items"][0]["candidate_identity_ids"]) == {
                first_identity_id,
                second_identity_id,
            }

            detail = await client.get(
                "/v1/project-identities/conflict",
                headers=headers,
                params={"legacy_project_id": "operator-project", "candidate_limit": 1},
            )
            assert detail.status_code == 200, detail.text
            assert detail.json()["candidate_count"] == 2
            assert detail.json()["next_candidate_offset"] == 1
            assert detail.json()["candidates"][0]["locators"][0]["schema"] == (
                "pex.project-locator.v2"
            )
            quarantined_status = await client.get(
                "/v1/project-identities/status",
                headers=headers,
                params={"legacy_project_id": "operator-project"},
            )
            assert quarantined_status.status_code == 200
            assert quarantined_status.json()["status"] == "quarantined"
            assert quarantined_status.json()["credential_reissue_blocked"] is True

            blocked_goal = await client.post(
                "/v1/goals",
                headers=headers,
                json={
                    "idempotency_key": "project-identity-blocked-goal-0001",
                    "project_id": "operator-project",
                    "title": "Must remain quarantined",
                    "objective": "Do not mutate an ambiguous project.",
                },
            )
            assert blocked_goal.status_code == 409, blocked_goal.text

            resolution = {
                "idempotency_key": "resolve-operator-project-0001",
                "legacy_project_id": "operator-project",
                "selected_identity_id": first_identity_id,
                "rationale": "The first typed locator is the operator-confirmed workspace.",
            }
            assert (
                await client.post("/v1/project-identities/resolve", json=resolution)
            ).status_code == 401
            resolved = await client.post(
                "/v1/project-identities/resolve",
                headers=headers,
                json=resolution,
            )
            assert resolved.status_code == 200, resolved.text
            assert resolved.json()["outcome"] == "resolved"
            assert resolved.json()["resolution"]["credentials_restored"] is False
            replay = await client.post(
                "/v1/project-identities/resolve",
                headers=headers,
                json=resolution,
            )
            assert replay.status_code == 200, replay.text
            assert replay.json()["outcome"] == "replayed"
            assert replay.json()["current_status"] == "active"
            assert replay.json()["fresh_credentials_required"] is True

            collision = await client.post(
                "/v1/project-identities/resolve",
                headers=headers,
                json={**resolution, "selected_identity_id": second_identity_id},
            )
            assert collision.status_code == 409
            assert "resolution id collision" in collision.json()["detail"]
            assert (
                await client.get(
                    "/v1/project-identities/conflicts",
                    headers=headers,
                )
            ).json()["items"] == []
            active_status = await client.get(
                "/v1/project-identities/status",
                headers=headers,
                params={"legacy_project_id": "operator-project"},
            )
            assert active_status.json()["status"] == "active"
            assert active_status.json()["fresh_credentials_required"] is True
            assert active_status.json()["last_resolution"]["credentials_restored"] is False
    finally:
        await store.close()


async def test_project_identity_persistence_never_revives_credentials(
    tmp_path,
):
    token = "project-identity-persistence-token-0001"
    headers = {"Authorization": f"Bearer {token}"}
    project_id = "persistent-operator-project"
    origin = ProjectOrigin(namespace="machine", host="operator-persistence-test")
    first_locator = ProjectLocator.path(
        "/workspace/persistent-one",
        platform=PathPlatform.POSIX,
        origin=origin,
    )
    second_locator = ProjectLocator.path(
        "/workspace/persistent-two",
        platform=PathPlatform.POSIX,
        origin=origin,
    )
    register_url = "/v1/project-identities/locators"

    app, store = await _open_operator_app(tmp_path, token)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=headers,
        ) as operator:
            first = await operator.post(
                register_url,
                json={
                    "legacy_project_id": project_id,
                    "locator": first_locator.model_dump(mode="json"),
                },
            )
            assert first.status_code == 200, first.text
            first_identity_id = first.json()["identity"]["id"]

            goal = await operator.post(
                "/v1/goals",
                json={
                    "idempotency_key": "project-identity-resolved-goal-0001",
                    "project_id": project_id,
                    "title": "Persistent identity boundary",
                    "objective": "Keep revoked credentials revoked across resolution and restart.",
                },
            )
            assert goal.status_code == 200, goal.text
            session = state.adapters.synthetic.seed_session(
                vendor_id="persistent-identity-session",
                project_id=project_id,
                goal_id=goal.json()["id"],
            )
            await store.upsert_session(session)
            session_id = session.id

            mcp_credential = await operator.post(
                f"/v1/sessions/{session_id}/mcp-credential"
            )
            assert mcp_credential.status_code == 200, mcp_credential.text
            mcp_digest = digest_mcp_session_token(mcp_credential.json()["token"])
            hook_credential = await operator.post(
                "/v1/hook-credentials/bootstrap",
                json={"harness_type": "cursor", "project_id": project_id},
            )
            assert hook_credential.status_code == 200, hook_credential.text
            hook_digest = digest_hook_token(hook_credential.json()["token"])
            assert await store.get_mcp_principal_by_digest(mcp_digest) is not None
            assert await store.get_hook_credential_by_digest(hook_digest) is not None

            quarantined = await operator.post(
                register_url,
                json={
                    "legacy_project_id": project_id,
                    "locator": second_locator.model_dump(mode="json"),
                },
            )
            assert quarantined.status_code == 200, quarantined.text
            assert quarantined.json()["project_identity_status"] == "quarantined"
            assert await store.get_mcp_principal_by_digest(mcp_digest) is None
            assert await store.get_hook_credential_by_digest(hook_digest) is None
    finally:
        await store.close()

    restarted_app, restarted_store = await _open_operator_app(tmp_path, token)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=restarted_app),
            base_url="http://127.0.0.1",
            headers=headers,
        ) as operator:
            conflicts = await operator.get("/v1/project-identities/conflicts")
            assert conflicts.status_code == 200, conflicts.text
            assert conflicts.json()["total"] == 1
            assert conflicts.json()["items"][0]["legacy_project_id"] == project_id
            status = await operator.get(
                "/v1/project-identities/status",
                params={"legacy_project_id": project_id},
            )
            assert status.status_code == 200, status.text
            assert status.json()["status"] == "quarantined"
            assert status.json()["credential_reissue_blocked"] is True
            assert await restarted_store.get_mcp_principal_by_digest(mcp_digest) is None
            assert await restarted_store.get_hook_credential_by_digest(hook_digest) is None

            resolution = {
                "idempotency_key": "resolve-persistent-project-0001",
                "legacy_project_id": project_id,
                "selected_identity_id": first_identity_id,
                "rationale": "The first typed locator is the persistent confirmed workspace.",
            }
            resolved = await operator.post(
                "/v1/project-identities/resolve",
                json=resolution,
            )
            assert resolved.status_code == 200, resolved.text
            resolved_body = resolved.json()
            assert resolved_body["outcome"] == "resolved"
            assert resolved_body["current_status"] == "active"
            assert resolved_body["fresh_credentials_required"] is True
            assert resolved_body["resolution"]["credentials_restored"] is False
            resolution_receipt = resolved_body["resolution"]
            resolved_binding = resolved_body["binding"]
            assert await restarted_store.get_mcp_principal_by_digest(mcp_digest) is None
            assert await restarted_store.get_hook_credential_by_digest(hook_digest) is None
    finally:
        await restarted_store.close()

    replay_app, replay_store = await _open_operator_app(tmp_path, token)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=replay_app),
            base_url="http://127.0.0.1",
            headers=headers,
        ) as operator:
            replay = await operator.post(
                "/v1/project-identities/resolve",
                json=resolution,
            )
            assert replay.status_code == 200, replay.text
            assert replay.json()["outcome"] == "replayed"
            assert replay.json()["current_status"] == "active"
            assert replay.json()["fresh_credentials_required"] is True
            assert replay.json()["resolution"] == resolution_receipt
            assert replay.json()["binding"] == resolved_binding

            collision = await operator.post(
                "/v1/project-identities/resolve",
                json={
                    **resolution,
                    "rationale": "A changed rationale must not reuse the persisted key.",
                },
            )
            assert collision.status_code == 409, collision.text
            assert "resolution id collision" in collision.json()["detail"]
            assert await replay_store.get_mcp_principal_by_digest(mcp_digest) is None
            assert await replay_store.get_hook_credential_by_digest(hook_digest) is None

            status = await operator.get(
                "/v1/project-identities/status",
                params={"legacy_project_id": project_id},
            )
            assert status.status_code == 200, status.text
            assert status.json()["status"] == "active"
            assert status.json()["fresh_credentials_required"] is True
            assert status.json()["last_resolution"] == resolution_receipt
    finally:
        await replay_store.close()
