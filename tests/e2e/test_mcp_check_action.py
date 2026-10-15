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
from pex_bridge.pets import PetSettings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store

_GOAL_CONTROL_SEQUENCE = count(1)


async def _make_app(tmp_path, *, operator_token: str):
    settings = Settings(require_auth=True, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = operator_token
    state.pet_settings = PetSettings()
    state.pet_path = tmp_path / "pet.json"
    await store.connect()
    return create_app(), store


async def _create_goal(client: AsyncClient, title: str) -> dict:
    response = await client.post(
        "/v1/goals",
        json={
            "idempotency_key": f"check-action-goal-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "project_id": "demo",
            "title": title,
            "objective": "Ship only after the complete test suite passes",
            "acceptance_criteria": ["tests pass"],
            "forbidden_outcomes": ["do not modify the acceptance tests"],
        },
    )
    assert response.status_code == 200
    return response.json()


async def _seed_attached_session(client: AsyncClient, goal_id: str) -> str:
    created = await client.post("/v1/synthetic/sessions")
    assert created.status_code == 200
    session_id = created.json()["id"]
    goal = await state.store.get_goal_intent_view(goal_id)
    assert goal is not None
    attached = await client.post(
        f"/v1/sessions/{session_id}/attach",
        json={
            "idempotency_key": f"check-action-attach-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "goal_id": goal_id,
            "expected_goal_id": None,
            "expected_control_revision": 0,
            "expected_goal_intent_revision": goal["intent_revision"],
        },
    )
    assert attached.status_code == 200
    return session_id


async def _issue_worker_token(client: AsyncClient, session_id: str) -> str:
    response = await client.post(f"/v1/sessions/{session_id}/mcp-credential")
    assert response.status_code == 200
    return response.json()["token"]


def _structured(result) -> dict:
    assert result.isError is False
    payload = result.structuredContent
    if payload is None:
        texts = [block.text for block in (result.content or []) if getattr(block, "text", None)]
        assert texts
        payload = json.loads(texts[0])
    if (
        isinstance(payload, dict)
        and set(payload) == {"result"}
        and isinstance(payload["result"], dict)
    ):
        payload = payload["result"]
    assert isinstance(payload, dict)
    return payload


def _error_text(result) -> str:
    return "\n".join(
        str(block.text) for block in (result.content or []) if getattr(block, "text", None)
    )


async def _durable_counts(store: Store) -> dict[str, int]:
    counts = {}
    for table in (
        "events",
        "context_items",
        "interventions",
        "intervention_audit",
        "mcp_mutations",
    ):
        cursor = await store.db.execute(f"SELECT COUNT(*) AS count FROM {table}")
        counts[table] = int((await cursor.fetchone())["count"])
    return counts


@pytest.mark.asyncio
async def test_check_action_flags_forbidden_intent_and_replays_exactly(tmp_path):
    operator_token = "check-action-operator-token-at-least-32"
    app, store = await _make_app(tmp_path, operator_token=operator_token)
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": f"Bearer {operator_token}"},
            ) as operator:
                goal = await _create_goal(operator, "Preflight adjudication")
                session_id = await _seed_attached_session(operator, goal["id"])
                worker_token = await _issue_worker_token(operator, session_id)

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://127.0.0.1",
                    headers={"Authorization": f"Bearer {worker_token}"},
                ) as worker_http:
                    async with streamable_http_client(
                        "http://127.0.0.1/mcp/",
                        http_client=worker_http,
                    ) as (read_stream, write_stream, _sid):
                        async with ClientSession(read_stream, write_stream) as mcp:
                            await mcp.initialize()
                            payload = {
                                "session_id": session_id,
                                "request": {
                                    "idempotency_key": "check-tamper-0001",
                                    "intended_action": (
                                        "I will modify the acceptance tests to make the suite pass."
                                    ),
                                },
                            }
                            created = _structured(await mcp.call_tool("pex.check_action", payload))
                            assert created["ok"] is True
                            assert created["verified"] is False
                            assert created["advisory"] is True
                            assert created["status"] == "conflict"
                            assert created["classification"] == "possible_contradiction"
                            assert created["matched_constraints"] == [
                                "do not modify the acceptance tests"
                            ]
                            assert created["suggest_request_decision"] is True
                            assert created["replayed"] is False
                            assert created["item"]["metadata"]["verified"] is False
                            assert created["item"]["metadata"]["verdict"] == "conflict"
                            assert "not authorization" in created["note"]

                            after_create = await _durable_counts(store)
                            assert after_create["mcp_mutations"] >= 1

                            replayed = _structured(await mcp.call_tool("pex.check_action", payload))
                            assert replayed["replayed"] is True
                            assert replayed["mutation_id"] == created["mutation_id"]
                            assert replayed["item"]["id"] == created["item"]["id"]
                            assert replayed["intervention"]["id"] == created["intervention"]["id"]
                            assert await _durable_counts(store) == after_create

                            changed = await mcp.call_tool(
                                "pex.check_action",
                                {
                                    "session_id": session_id,
                                    "request": {
                                        "idempotency_key": "check-tamper-0001",
                                        "intended_action": "I will write docs.",
                                    },
                                },
                            )
                            assert changed.isError is True
                            assert "reused with new content" in _error_text(changed)
                            assert await _durable_counts(store) == after_create
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_check_action_flat_shape_and_consistent_verdict(tmp_path):
    operator_token = "check-action-flat-operator-token-32chars"
    app, store = await _make_app(tmp_path, operator_token=operator_token)
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": f"Bearer {operator_token}"},
            ) as operator:
                goal = await _create_goal(operator, "Flat preflight")
                session_id = await _seed_attached_session(operator, goal["id"])
                worker_token = await _issue_worker_token(operator, session_id)

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://127.0.0.1",
                    headers={"Authorization": f"Bearer {worker_token}"},
                ) as worker_http:
                    async with streamable_http_client(
                        "http://127.0.0.1/mcp/",
                        http_client=worker_http,
                    ) as (read_stream, write_stream, _sid):
                        async with ClientSession(read_stream, write_stream) as mcp:
                            await mcp.initialize()
                            payload = {
                                "session_id": session_id,
                                "action": "create report.txt with the run summary",
                            }
                            created = _structured(await mcp.call_tool("pex.check_action", payload))
                            assert created["status"] == "clear"
                            assert created["matched_constraints"] == []
                            assert created["suggest_request_decision"] is False
                            assert created["replayed"] is False
                            assert created["intervention"]["outcome"] == "action_check_clear"

                            replayed = _structured(await mcp.call_tool("pex.check_action", payload))
                            assert replayed["replayed"] is True
                            assert replayed["mutation_id"] == created["mutation_id"]

                            ambiguous = _structured(
                                await mcp.call_tool(
                                    "pex.check_action",
                                    {
                                        "session_id": session_id,
                                        "action": "just hack it quickly whatever",
                                    },
                                )
                            )
                            assert ambiguous["status"] == "uncertain"
                            assert ambiguous["classification"] == "dangerous_ambiguity"
                            assert ambiguous["suggest_request_decision"] is True
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_check_action_rejects_a_principal_bound_to_another_session(tmp_path):
    operator_token = "check-action-scope-operator-token-32ch"
    app, store = await _make_app(tmp_path, operator_token=operator_token)
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": f"Bearer {operator_token}"},
            ) as operator:
                goal = await _create_goal(operator, "Scoped preflight")
                session_id = await _seed_attached_session(operator, goal["id"])
                other_goal_response = await operator.post(
                    "/v1/goals",
                    json={
                        "idempotency_key": (
                            f"check-action-other-goal-{next(_GOAL_CONTROL_SEQUENCE):08d}"
                        ),
                        "project_id": "demo",
                        "title": "Other goal",
                        "objective": "Ship after tests pass",
                    },
                )
                assert other_goal_response.status_code == 200
                other_goal_id = other_goal_response.json()["id"]
                other = state.adapters.synthetic.seed_session(
                    vendor_id="check-action-other",
                    project_id="demo",
                )
                await state.store.upsert_session(other)
                other_intent = await state.store.get_goal_intent_view(other_goal_id)
                other_attached = await operator.post(
                    f"/v1/sessions/{other.id}/attach",
                    json={
                        "idempotency_key": (
                            f"check-action-other-attach-{next(_GOAL_CONTROL_SEQUENCE):08d}"
                        ),
                        "goal_id": other_goal_id,
                        "expected_goal_id": None,
                        "expected_control_revision": 0,
                        "expected_goal_intent_revision": other_intent["intent_revision"],
                    },
                )
                assert other_attached.status_code == 200
                other_token = await _issue_worker_token(operator, other.id)

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://127.0.0.1",
                    headers={"Authorization": f"Bearer {other_token}"},
                ) as worker_http:
                    async with streamable_http_client(
                        "http://127.0.0.1/mcp/",
                        http_client=worker_http,
                    ) as (read_stream, write_stream, _sid):
                        async with ClientSession(read_stream, write_stream) as mcp:
                            await mcp.initialize()
                            denied = await mcp.call_tool(
                                "pex.check_action",
                                {
                                    "session_id": session_id,
                                    "action": "create report.txt",
                                },
                            )
                            assert denied.isError is True
                            assert "not bound" in _error_text(denied)
    finally:
        await store.close()
