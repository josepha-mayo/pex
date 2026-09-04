from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pets import PetSettings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store

_OPERATOR_TOKEN = "goal-control-route-operator-token-0123456789"


async def _configured_client(
    root: Path,
    *,
    require_auth: bool,
) -> AsyncIterator[tuple[AsyncClient, Store]]:
    settings = (
        Settings(
            require_auth=True,
            token=_OPERATOR_TOKEN,
            home=root,
            autonomy="manage",
        )
        if require_auth
        else Settings.for_test(
            require_auth=False,
            token=None,
            home=root,
            autonomy="manage",
        )
    )
    store = Store(root / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = _OPERATOR_TOKEN if require_auth else None
    state.pet_settings = PetSettings()
    state.pet_path = root / "pet.json"
    await store.connect()
    headers = (
        {"Authorization": f"Bearer {_OPERATOR_TOKEN}"}
        if require_auth
        else None
    )
    transport = ASGITransport(app=create_app())
    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1",
        headers=headers,
    ) as client:
        yield client, store
    await store.close()


@pytest.fixture
async def operator_client(tmp_path: Path):
    async for configured in _configured_client(tmp_path, require_auth=True):
        yield configured


def _goal_request(
    key: str,
    *,
    title: str = "Durable route goal",
    objective: str = "Prove exact authenticated REST replay",
) -> dict[str, Any]:
    return {
        "idempotency_key": key,
        "project_id": "demo",
        "title": title,
        "objective": objective,
        "acceptance_criteria": ["the committed response replays exactly"],
        "constraints": ["do not reacquire mutable authority before replay"],
    }


def _assert_operation_headers(response: Response, *, replayed: bool) -> str:
    payload = response.json()
    operation = payload["operator_operation_receipt"]
    operation_id = operation["operation_id"]
    assert response.headers["Idempotency-Replayed"] == str(replayed).lower()
    assert response.headers["PEX-Operation-Id"] == operation_id
    assert operation["principal_id"] == "local_bridge_operator"
    assert operation["actor_assurance"] == "bridge_bearer"
    assert operation["state"] == "committed"
    return operation_id


async def _operation_count(store: Store) -> int:
    cursor = await store.db.execute("SELECT COUNT(*) FROM goal_control_operations")
    row = await cursor.fetchone()
    assert row is not None
    return int(row[0])


@pytest.mark.asyncio
async def test_keyed_create_replays_exact_response_after_later_goal_state(
    operator_client: tuple[AsyncClient, Store],
) -> None:
    client, store = operator_client
    create_request = _goal_request("route-goal-create-replay-0001")

    first = await client.post("/v1/goals", json=create_request)
    assert first.status_code == 200
    first_body = first.json()
    first_operation_id = _assert_operation_headers(first, replayed=False)

    changed = await client.patch(
        f"/v1/goals/{first_body['id']}",
        json={
            "idempotency_key": "route-goal-update-later-0001",
            "mode": "update",
            "expected_intent_revision": first_body["intent_revision"],
            "objective": "A later committed objective",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["objective"] == "A later committed objective"

    replay = await client.post("/v1/goals", json=create_request)
    assert replay.status_code == first.status_code
    assert replay.json() == first_body
    assert _assert_operation_headers(replay, replayed=True) == first_operation_id

    current = await client.get(f"/v1/goals/{first_body['id']}")
    assert current.status_code == 200
    assert current.json()["objective"] == "A later committed objective"
    assert await _operation_count(store) == 2


@pytest.mark.asyncio
async def test_keyed_create_same_key_different_request_is_typed_conflict(
    operator_client: tuple[AsyncClient, Store],
) -> None:
    client, store = operator_client
    key = "route-goal-create-conflict-0001"
    first = await client.post("/v1/goals", json=_goal_request(key))
    assert first.status_code == 200

    conflict = await client.post(
        "/v1/goals",
        json=_goal_request(key, objective="Different logical request content"),
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == (
        "operator_intent_idempotency_conflict"
    )
    assert await _operation_count(store) == 1
    goals = await client.get("/v1/goals")
    assert goals.status_code == 200
    assert len(goals.json()) == 1


@pytest.mark.asyncio
async def test_keyed_patch_replay_precedes_current_goal_authority(
    operator_client: tuple[AsyncClient, Store],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = operator_client
    created = await client.post(
        "/v1/goals",
        json=_goal_request("route-goal-create-for-patch-0001"),
    )
    assert created.status_code == 200
    goal = created.json()
    patch_request = {
        "idempotency_key": "route-goal-patch-replay-0001",
        "mode": "update",
        "expected_intent_revision": goal["intent_revision"],
        "objective": "Committed through the keyed patch route",
    }

    first = await client.patch(f"/v1/goals/{goal['id']}", json=patch_request)
    assert first.status_code == 200
    first_body = first.json()
    first_operation_id = _assert_operation_headers(first, replayed=False)

    async def fail_if_authority_is_reacquired(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("current goal authority was read before terminal replay")

    monkeypatch.setattr(
        state.store,
        "get_goal_for_authority",
        fail_if_authority_is_reacquired,
    )
    monkeypatch.setattr(
        state.store,
        "has_goal_successor_for_authority",
        fail_if_authority_is_reacquired,
    )

    replay = await client.patch(f"/v1/goals/{goal['id']}", json=patch_request)
    assert replay.status_code == first.status_code
    assert replay.json() == first_body
    assert _assert_operation_headers(replay, replayed=True) == first_operation_id


@pytest.mark.asyncio
async def test_keyed_attach_replays_exact_receipt_after_later_replacement(
    operator_client: tuple[AsyncClient, Store],
) -> None:
    client, store = operator_client
    session_response = await client.post("/v1/synthetic/sessions")
    assert session_response.status_code == 200
    session = session_response.json()
    session_control = await store.get_session_control_state(session["id"])
    assert session_control is not None
    first_goal_response = await client.post(
        "/v1/goals",
        json=_goal_request(
            "route-goal-create-for-attach-a-0001",
            title="First attachment goal",
        ),
    )
    second_goal_response = await client.post(
        "/v1/goals",
        json=_goal_request(
            "route-goal-create-for-attach-b-0001",
            title="Replacement attachment goal",
        ),
    )
    assert first_goal_response.status_code == 200
    assert second_goal_response.status_code == 200
    first_goal = first_goal_response.json()
    second_goal = second_goal_response.json()
    attach_request = {
        "idempotency_key": "route-goal-attach-replay-0001",
        "goal_id": first_goal["id"],
        "replace_existing": False,
        "expected_goal_id": None,
        "expected_control_revision": session_control["control_revision"],
        "expected_goal_intent_revision": first_goal["intent_revision"],
    }

    first_attach = await client.post(
        f"/v1/sessions/{session['id']}/attach",
        json=attach_request,
    )
    assert first_attach.status_code == 200
    first_body = first_attach.json()
    first_operation_id = _assert_operation_headers(first_attach, replayed=False)
    assert first_body["session_goal_attachment_receipt"]["changed"] is True
    assert first_body["session_goal_attachment_receipt"]["reason"] == (
        "session_goal_attached"
    )

    replacement = await client.post(
        f"/v1/sessions/{session['id']}/attach",
        json={
            "idempotency_key": "route-goal-attach-replacement-0001",
            "goal_id": second_goal["id"],
            "replace_existing": True,
            "expected_goal_id": first_goal["id"],
            "expected_control_revision": first_body["control_revision"],
            "expected_goal_intent_revision": second_goal["intent_revision"],
        },
    )
    assert replacement.status_code == 200
    assert replacement.json()["goal_id"] == second_goal["id"]

    replay = await client.post(
        f"/v1/sessions/{session['id']}/attach",
        json=attach_request,
    )
    assert replay.status_code == first_attach.status_code
    assert replay.json() == first_body
    assert _assert_operation_headers(replay, replayed=True) == first_operation_id

    current = await client.get(f"/v1/sessions/{session['id']}")
    assert current.status_code == 200
    assert current.json()["goal_id"] == second_goal["id"]
    assert await _operation_count(store) == 4


@pytest.mark.asyncio
async def test_no_auth_legacy_create_does_not_write_goal_control_operation(
    tmp_path: Path,
) -> None:
    async for client, store in _configured_client(tmp_path, require_auth=False):
        created = await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Legacy unassured goal",
                "objective": "Remain compatible without inferred actor assurance",
                "acceptance_criteria": ["no operator operation is invented"],
            },
        )
        assert created.status_code == 200
        assert "operator_operation_receipt" not in created.json()
        assert "Idempotency-Replayed" not in created.headers
        assert "PEX-Operation-Id" not in created.headers
        assert await _operation_count(store) == 0
