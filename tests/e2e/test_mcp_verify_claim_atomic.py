from __future__ import annotations

import json
from datetime import UTC, datetime
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
from pex_bridge.store import Store, new_id
from pex_protocol.enums import EventType
from pex_protocol.session import HarnessEvent

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
            "idempotency_key": f"verify-claim-goal-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "project_id": "demo",
            "title": title,
            "objective": "Ship only after the complete test suite passes",
            "acceptance_criteria": ["tests pass"],
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
            "idempotency_key": f"verify-claim-attach-{next(_GOAL_CONTROL_SEQUENCE):08d}",
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


async def _seed_passing_pytest(store: Store, session_id: str, event_id: str) -> None:
    session = await store.get_session(session_id)
    assert session is not None
    event = HarnessEvent(
        event_id=event_id,
        ts=datetime.now(UTC),
        harness_type=session.harness_type,
        session_id=session.id,
        project_id=session.project_id,
        goal_id=session.goal_id,
        event_type=EventType.SHELL,
        command="pytest -q",
        process_state={"pytest": {"ok": True, "exit_code": 0, "passed": 12}},
    )
    accepted = await store.accept_pipeline_event(event, session_snapshot=session)
    assert accepted["processing"]["state"] == "accepted"


def _structured(result) -> dict:
    assert result.isError is False
    payload = result.structuredContent
    if payload is None:
        texts = [
            block.text
            for block in (result.content or [])
            if getattr(block, "text", None)
        ]
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
        str(block.text)
        for block in (result.content or [])
        if getattr(block, "text", None)
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
async def test_typed_verify_claim_exact_retry_and_changed_payload_are_atomic(tmp_path):
    operator_token = "verify-atomic-operator-token-at-least-32"
    app, store = await _make_app(tmp_path, operator_token=operator_token)
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": f"Bearer {operator_token}"},
            ) as operator:
                goal = await _create_goal(operator, "Atomic verification")
                session_id = await _seed_attached_session(operator, goal["id"])
                await _seed_passing_pytest(
                    store,
                    session_id,
                    new_id("pytest_current_"),
                )
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
                                    "idempotency_key": "verify-tests-pass-0001",
                                    "claim": "All tests passed.",
                                },
                            }
                            created = _structured(
                                await mcp.call_tool("pex.verify_claim", payload)
                            )
                            assert created["status"] == "verified"
                            assert created["outcome"] == "supported"
                            assert created["verified"] is True
                            assert created["replayed"] is False
                            assert created["verified_items"]
                            assert created["item"]["metadata"]["verified"] is False
                            assert all(
                                item["metadata"].get("verified") is True
                                and item["provenance"] in {"test", "workspace"}
                                and item["id"] != created["item"]["id"]
                                for item in created["verified_items"]
                            )
                            after_create = await _durable_counts(store)

                            replayed = _structured(
                                await mcp.call_tool("pex.verify_claim", payload)
                            )
                            assert replayed["replayed"] is True
                            assert replayed["mutation_id"] == created["mutation_id"]
                            assert replayed["item"]["id"] == created["item"]["id"]
                            assert (
                                replayed["intervention"]["id"]
                                == created["intervention"]["id"]
                            )
                            assert await _durable_counts(store) == after_create

                            changed = await mcp.call_tool(
                                "pex.verify_claim",
                                {
                                    "session_id": session_id,
                                    "request": {
                                        "idempotency_key": "verify-tests-pass-0001",
                                        "claim": "The deployment is complete.",
                                    },
                                },
                            )
                            assert changed.isError is True
                            assert "reused with new content" in _error_text(changed)
                            assert await _durable_counts(store) == after_create
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_old_goal_pytest_cannot_launder_a_new_goal_verification(tmp_path):
    operator_token = "verify-old-goal-operator-token-at-least-32"
    app, store = await _make_app(tmp_path, operator_token=operator_token)
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": f"Bearer {operator_token}"},
            ) as operator:
                old_goal = await _create_goal(operator, "Old goal")
                old_session_id = await _seed_attached_session(operator, old_goal["id"])
                old_pytest_id = new_id("pytest_old_goal_")
                await _seed_passing_pytest(store, old_session_id, old_pytest_id)

                new_goal = await _create_goal(operator, "New goal")
                rebound = await operator.post(
                    f"/v1/sessions/{old_session_id}/attach",
                    json={
                        "idempotency_key": (
                            f"verify-claim-attach-{next(_GOAL_CONTROL_SEQUENCE):08d}"
                        ),
                        "goal_id": new_goal["id"],
                        "replace_existing": True,
                        "expected_goal_id": old_goal["id"],
                        "expected_control_revision": 1,
                        "expected_goal_intent_revision": new_goal["intent_revision"],
                    },
                )
                assert rebound.status_code == 200
                assert rebound.json()["goal_id"] == new_goal["id"]
                session_id = old_session_id
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
                            result = _structured(
                                await mcp.call_tool(
                                    "pex.verify_claim",
                                    {
                                        "session_id": session_id,
                                        "request": {
                                            "idempotency_key": "verify-new-goal-0001",
                                            "claim": "All tests passed.",
                                        },
                                    },
                                )
                            )

                assert result["status"] == "uncertain"
                assert result["outcome"] == "uncertain"
                assert result["verified"] is False
                assert old_pytest_id not in result["item"]["source_refs"]
                assert all(
                    old_pytest_id not in item["source_refs"]
                    for item in result["verified_items"]
                )
                current_goal_context = [
                    item
                    for item in await store.list_context("demo")
                    if item.goal_id == new_goal["id"]
                ]
                assert current_goal_context
                assert all(
                    item.metadata.get("verified") is not True
                    for item in current_goal_context
                )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_contradicted_claim_is_durable_but_never_mints_verified_context(tmp_path):
    operator_token = "verify-contradicted-operator-token-at-least-32"
    app, store = await _make_app(tmp_path, operator_token=operator_token)
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": f"Bearer {operator_token}"},
            ) as operator:
                goal = await _create_goal(operator, "Contradicted verification")
                session_id = await _seed_attached_session(operator, goal["id"])
                session = await store.get_session(session_id)
                assert session is not None
                failed_pytest_id = new_id("pytest_failed_")
                failed_pytest = HarnessEvent(
                    event_id=failed_pytest_id,
                    ts=datetime.now(UTC),
                    harness_type=session.harness_type,
                    session_id=session.id,
                    project_id=session.project_id,
                    goal_id=session.goal_id,
                    event_type=EventType.SHELL,
                    command="pytest -q",
                    process_state={
                        "pytest": {"ok": False, "exit_code": 1, "failed": 2}
                    },
                )
                accepted = await store.accept_pipeline_event(
                    failed_pytest,
                    session_snapshot=session,
                )
                assert accepted["processing"]["state"] == "accepted"
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
                            result = _structured(
                                await mcp.call_tool(
                                    "pex.verify_claim",
                                    {
                                        "session_id": session_id,
                                        "request": {
                                            "idempotency_key": "verify-failed-tests-0001",
                                            "claim": "All tests passed.",
                                        },
                                    },
                                )
                            )

                assert result["status"] == "contradicted"
                assert result["outcome"] == "contradicted"
                assert result["verified"] is False
                assert result["verified_items"] == []
                assert result["item"]["metadata"]["verified"] is False
                assert failed_pytest_id in result["item"]["source_refs"]
                stored = await store.get_context(result["item"]["id"])
                assert stored is not None
                assert stored.metadata["status"] == "contradicted"
                assert stored.metadata["verified"] is False
                intervention = await store.get_intervention(
                    result["intervention"]["id"]
                )
                assert intervention is not None
                assert intervention.outcome == "claim_verification_contradicted"
    finally:
        await store.close()
