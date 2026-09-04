from __future__ import annotations

import json
from itertools import count

import pytest
from httpx import ASGITransport, AsyncClient
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.mcp_auth import digest_mcp_session_token
from pex_bridge.pets import PetSettings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store

_GOAL_CONTROL_SEQUENCE = count(1)


async def _make_app(
    tmp_path,
    *,
    require_auth: bool = False,
    token: str | None = None,
):
    settings = (
        Settings(require_auth=True, home=tmp_path, autonomy="manage")
        if require_auth
        else Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage")
    )
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = token
    state.pet_settings = PetSettings()
    state.pet_path = tmp_path / "pet.json"
    await store.connect()
    return create_app(), store


async def _create_goal(client: AsyncClient, *, title: str = "Parser") -> dict:
    response = await client.post(
        "/v1/goals",
        json={
            "idempotency_key": f"mcp-credential-goal-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "project_id": "demo",
            "title": title,
            "objective": "Implement the frontend pet atlas with passing tests",
            "acceptance_criteria": ["tests pass"],
        },
    )
    assert response.status_code == 200
    return response.json()


async def _seed_attached_session(client: AsyncClient) -> tuple[str, str]:
    session_response = await client.post("/v1/synthetic/sessions")
    assert session_response.status_code == 200
    session = session_response.json()
    goal = await _create_goal(client)
    attached = await client.post(
        f"/v1/sessions/{session['id']}/attach",
        json={
            "idempotency_key": f"mcp-credential-attach-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "goal_id": goal["id"],
            "expected_goal_id": None,
            "expected_control_revision": 0,
            "expected_goal_intent_revision": goal["intent_revision"],
        },
    )
    assert attached.status_code == 200
    return session["id"], goal["id"]


def _structured(result) -> dict:
    assert result.isError is False
    payload = result.structuredContent
    if payload is None:
        texts = [
            block.text
            for block in (result.content or [])
            if getattr(block, "text", None)
        ]
        assert texts, "MCP tool returned neither structured content nor text"
        payload = json.loads(texts[0])
    if (
        isinstance(payload, dict)
        and set(payload) == {"result"}
        and isinstance(payload["result"], dict)
    ):
        payload = payload["result"]
    assert isinstance(payload, dict)
    return payload


@pytest.mark.asyncio
async def test_operator_rotates_one_time_session_credential_without_storing_token(
    tmp_path,
):
    operator_token = "local-operator-token-that-is-at-least-32"
    app, store = await _make_app(
        tmp_path,
        require_auth=True,
        token=operator_token,
    )
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": f"Bearer {operator_token}"},
            ) as operator:
                session_id, goal_id = await _seed_attached_session(operator)
                first = await operator.post(
                    f"/v1/sessions/{session_id}/mcp-credential"
                )

                assert first.status_code == 200
                assert first.headers["cache-control"] == "no-store"
                assert first.headers["pragma"] == "no-cache"
                first_body = first.json()
                first_token = first_body["token"]
                assert first_body["session_id"] == session_id
                assert first_body["goal_id"] == goal_id
                assert "token_digest" not in first_body
                first_record = await store.get_mcp_principal_by_digest(
                    digest_mcp_session_token(first_token)
                )
                assert first_record is not None
                assert first_record["principal_id"] == first_body["principal_id"]

                rows = await store.db.execute_fetchall(
                    "SELECT json FROM mcp_principals"
                )
                assert all(first_token not in str(row["json"]) for row in rows)

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://127.0.0.1",
                    headers={"Authorization": f"Bearer {first_token}"},
                ) as worker_http:
                    denied_rotation = await worker_http.post(
                        f"/v1/sessions/{session_id}/mcp-credential"
                    )
                    assert denied_rotation.status_code == 401
                    async with streamable_http_client(
                        "http://127.0.0.1/mcp/",
                        http_client=worker_http,
                    ) as (read_stream, write_stream, _sid):
                        async with ClientSession(read_stream, write_stream) as mcp:
                            await mcp.initialize()
                            goal = _structured(
                                await mcp.call_tool(
                                    "pex.get_goal",
                                    {"session_id": session_id},
                                )
                            )
                            assert goal["goal"]["id"] == goal_id

                second = await operator.post(
                    f"/v1/sessions/{session_id}/mcp-credential"
                )
                assert second.status_code == 200
                second_body = second.json()
                second_token = second_body["token"]
                assert second_token != first_token
                assert second_body["principal_id"] != first_body["principal_id"]
                assert (
                    await store.get_mcp_principal_by_digest(
                        digest_mcp_session_token(first_token)
                    )
                    is None
                )
                assert (
                    await store.get_mcp_principal_by_digest(
                        digest_mcp_session_token(second_token)
                    )
                    is not None
                )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_credential_issuance_is_unavailable_in_no_auth_mode(tmp_path):
    app, store = await _make_app(tmp_path)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
        ) as client:
            session_id, _goal_id = await _seed_attached_session(client)
            response = await client.post(
                f"/v1/sessions/{session_id}/mcp-credential"
            )

        assert response.status_code == 403
        cursor = await store.db.execute("SELECT COUNT(*) AS count FROM mcp_principals")
        assert int((await cursor.fetchone())["count"]) == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_goal_rebind_revokes_the_previous_session_credential(tmp_path):
    operator_token = "local-operator-token-that-is-at-least-32"
    app, store = await _make_app(
        tmp_path,
        require_auth=True,
        token=operator_token,
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers={"Authorization": f"Bearer {operator_token}"},
        ) as operator:
            session_id, goal_id = await _seed_attached_session(operator)
            issued = await operator.post(
                f"/v1/sessions/{session_id}/mcp-credential"
            )
            assert issued.status_code == 200
            worker_token = issued.json()["token"]
            worker_digest = digest_mcp_session_token(worker_token)

            replacement = await _create_goal(operator, title="Replacement")
            attached = await operator.post(
                f"/v1/sessions/{session_id}/attach",
                json={
                    "idempotency_key": (
                        f"mcp-credential-attach-{next(_GOAL_CONTROL_SEQUENCE):08d}"
                    ),
                    "goal_id": replacement["id"],
                    "replace_existing": True,
                    "expected_goal_id": goal_id,
                    "expected_control_revision": 1,
                    "expected_goal_intent_revision": replacement["intent_revision"],
                },
            )

            assert attached.status_code == 200
            assert attached.json()["goal_id"] == replacement["id"]
            assert await store.get_mcp_principal_by_digest(worker_digest) is None

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": f"Bearer {worker_token}"},
            ) as stale_worker:
                denied = await stale_worker.post("/mcp/")
            assert denied.status_code == 401
    finally:
        await store.close()
