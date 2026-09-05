"""Authenticated local control API; fake Codex I/O and real Store transactions."""

import pytest
from pex_bridge.app import state
from test_codex_autonomous_correction_grant import _attached, _grant_arguments
from test_codex_shared_attach import shared_client as shared_client


def request_body(status, **overrides):
    return {
        key: value for key, value in {**_grant_arguments(status), **overrides}.items()
        if key not in {"principal_id", "actor_assurance"}
    }


async def endpoint(case):
    client, _, selection, _, _ = await _attached(case)
    return client, f"/v1/sessions/{selection['session_id']}/autonomous-corrections"


async def test_operator_can_enable_disable_and_replay_without_worker_write(shared_client):
    client, path = await endpoint(shared_client)
    initial = (await client.get(path)).json()
    assert initial["enabled"] is False and initial["connected"] is True
    body = request_body(initial)
    response = await client.patch(path, json=body)
    assert response.status_code == 200, response.text
    replay = await client.patch(path, json=body)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    active = (await client.get(path)).json()
    assert active["effective_enabled"] is True
    assert active["delivery_proven"] is False
    adapter = state.adapters.for_session(active["scope"]["session_id"])
    assert (await adapter.probe()).send_message is False
    assert adapter.session.metadata["subscription_receipt"]["observation_only"] is True
    disabled = await client.patch(path, json=request_body(
        active, enabled=False, idempotency_key="disable-fixture-operation",
    ))
    assert disabled.status_code == 200, disabled.text
    assert (await client.get(path)).json()["effective_enabled"] is False


@pytest.mark.parametrize("method", ["GET", "PATCH"])
async def test_operator_authentication_is_required(shared_client, method):
    client, path = await endpoint(shared_client)
    before = (await client.get(path)).json()
    response = await client.request(
        method, path, json=request_body(before) if method == "PATCH" else None,
        headers={"Authorization": "Bearer wrong-fixture-token"},
    )
    assert response.status_code in {401, 403}
    assert (await client.get(path)).json()["enabled"] is False


@pytest.mark.parametrize("change", [
    {"enabled": "true"}, {"enabled": 1}, {"expected_control_revision": True},
    {"expected_connection_generation": 0}, {"expected_goal_intent_hash": "not-a-hash"},
    {"principal_id": "local_bridge_operator"}, {"expected_workspace_sha256": None},
])
async def test_strict_request_cannot_coerce_or_supply_actor(shared_client, change):
    client, path = await endpoint(shared_client)
    initial = (await client.get(path)).json()
    response = await client.patch(path, json={**request_body(initial), **change})
    assert response.status_code == 422, response.text
    assert (await client.get(path)).json()["enabled"] is False


async def test_stale_scope_and_reused_key_are_conflicts(shared_client):
    client, path = await endpoint(shared_client)
    initial = (await client.get(path)).json()
    stale = request_body(initial, expected_control_revision=999)
    assert (await client.patch(path, json=stale)).status_code == 409
    body = request_body(initial)
    assert (await client.patch(path, json=body)).status_code == 200
    assert (await client.patch(path, json={**body, "enabled": False})).status_code == 409


async def test_disconnected_adapter_is_not_effectively_enabled(shared_client):
    client, path = await endpoint(shared_client)
    initial = (await client.get(path)).json()
    assert (await client.patch(path, json=request_body(initial))).status_code == 200
    adapter = state.adapters.for_session(initial["scope"]["session_id"])
    adapter._invalid = True
    status = (await client.get(path)).json()
    assert status["connected"] is False and status["effective_enabled"] is False
    response = await client.patch(path, json=request_body(
        status, idempotency_key="reconnect-required-fixture",
    ))
    assert response.status_code == 409
