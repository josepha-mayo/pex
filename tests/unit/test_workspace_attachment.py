"""Real local config/Store with fake existing-worker transport; no native launch."""
# ruff: noqa: F811 -- pytest fixture imported explicitly for this module.

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pex_bridge.app import state
from pex_bridge.codex_shared_attach import LocalOriginUpdate, SharedCodexConfirm
from pex_bridge.local_origin_config import load_local_origin_choice, save_local_origin_choice
from pex_bridge.local_workspace import measure_local_directory
from pex_protocol.project_identity import ProjectLocator, ProjectOrigin
from test_codex_shared_attach import _confirm, _inspect, shared_client  # noqa: F401

ORIGIN_URL = "/v1/local-workspace-origin"
STATUS_URL = "/v1/adapters/codex/shared/status"


def _update(choice, host="attachment-fixture"):
    return {
        "origin": {"namespace": "machine", "host": host},
        "expected_revision": choice.revision if choice else None,
        "expected_choice_id": choice.choice_id if choice else None,
        "confirm_local_origin": True,
    }


@pytest.mark.asyncio
async def test_status_is_read_only_and_auth_required(shared_client):
    client, _, transports, _, _, manager = shared_client
    for url in (ORIGIN_URL, STATUS_URL):
        assert (await client.get(url, headers={"Authorization": "Bearer wrong"})).status_code == 401
    result = (await client.get(STATUS_URL)).json()
    assert result["connection"] is None
    assert result["pending"] == []
    assert result["origin"]["status"] == "configured"
    assert result["worker_delivery_enabled"] is False
    assert transports == [] and manager.active is None


@pytest.mark.asyncio
@pytest.mark.parametrize("typed_raw_key", [False, True])
async def test_foreign_origin_cannot_attach_even_with_identical_path(shared_client, typed_raw_key):
    client, body, transports, _, _, _ = shared_client
    directory = measure_local_directory(body["cwd"])
    key = body["cwd"] if typed_raw_key else "foreign-project"
    await state.store.register_project_locator(
        legacy_project_id=key,
        locator=ProjectLocator.path(
            body["cwd"],
            platform=directory.platform,
            origin=ProjectOrigin(namespace="machine", host="foreign-machine"),
            physical=directory.physical,
        ),
    )
    response = await client.post(
        "/v1/adapters/codex/shared/inspect", json={**body, "project_id": key}
    )
    assert response.status_code == 409
    assert transports == []


@pytest.mark.asyncio
async def test_unregistered_exact_directory_remains_explicitly_attachable(shared_client):
    client, body, _, _, _, manager = shared_client
    selected = await _inspect(client, {**body, "project_id": body["cwd"]})
    assert selected["workspace_binding"]["locator"] is None
    response = await manager.confirm(
        SharedCodexConfirm(
            inspection_id=selected["inspection_id"],
            selection_id=selected["selection_id"],
            allow_resume=True,
        ),
        state,
    )
    assert response["workspace_binding"] == selected["workspace_binding"]


@pytest.mark.asyncio
async def test_missing_origin_blocks_inspection_before_transport(shared_client):
    client, body, transports, _, _, _ = shared_client
    path = Path(body["cwd"]) / "local-origin.json"
    path.rename(path.with_suffix(".preserved"))
    assert (await client.get(ORIGIN_URL)).json()["status"] == "unconfigured"
    assert (await client.post("/v1/adapters/codex/shared/inspect", json=body)).status_code == 409
    assert transports == []
    saved = await client.patch(ORIGIN_URL, json=_update(None))
    assert saved.status_code == 200
    await _inspect(client, body)


@pytest.mark.asyncio
async def test_origin_save_requires_operator_consent_and_exact_revision(shared_client):
    client, body, _, _, _, _ = shared_client
    path = Path(body["cwd"]) / "local-origin.json"
    choice = load_local_origin_choice(path)
    payload = _update(choice)
    before = path.read_bytes()
    for changes, status in [
        ({"confirm_local_origin": False}, 400),
        ({"expected_choice_id": "0" * 32}, 409),
        ({"expected_revision": True}, 422),
    ]:
        response = await client.patch(ORIGIN_URL, json={**payload, **changes})
        assert response.status_code == status, response.text
        assert path.read_bytes() == before
    denied = await client.patch(ORIGIN_URL, json=payload, headers={"Authorization": "Bearer wrong"})
    assert denied.status_code == 401
    assert path.read_bytes() == before


@pytest.mark.asyncio
async def test_origin_update_invalidates_pending_without_resuming_worker(shared_client):
    client, body, transports, _, _, manager = shared_client
    selected = await _inspect(client, body)
    choice = load_local_origin_choice(Path(body["cwd"]) / "local-origin.json")
    changed = await client.patch(ORIGIN_URL, json=_update(choice))
    assert changed.status_code == 200, changed.text
    assert changed.json()["invalidated_selections"] == 1
    assert not manager.pending
    assert (await _confirm(client, selected)).status_code == 409
    assert [method for method, _ in transports[0].calls] == ["thread/read"]


@pytest.mark.asyncio
async def test_external_origin_change_blocks_confirmation(shared_client):
    client, body, transports, _, _, _ = shared_client
    selected = await _inspect(client, body)
    path = Path(body["cwd"]) / "local-origin.json"
    choice = load_local_origin_choice(path)
    save_local_origin_choice(
        path,
        choice.origin,
        expected_revision=choice.revision,
        expected_choice_id=choice.choice_id,
    )
    assert (await _confirm(client, selected)).status_code == 409
    assert [method for method, _ in transports[0].calls] == ["thread/read"]


@pytest.mark.asyncio
async def test_active_origin_change_requires_detach_and_status_survives_reload(shared_client):
    client, body, _, _, _, _ = shared_client
    selected = await _inspect(client, body)
    assert (await _confirm(client, selected)).status_code == 200
    snapshot = (await client.get(STATUS_URL)).json()["connection"]
    assert snapshot["inspection_id"] == selected["inspection_id"]
    assert snapshot["selection_id"] == selected["selection_id"]
    assert snapshot["state"] == "observing" and snapshot["can_detach"]
    path = Path(body["cwd"]) / "local-origin.json"
    before = path.read_bytes()
    choice = load_local_origin_choice(path)
    assert (await client.patch(ORIGIN_URL, json=_update(choice))).status_code == 409
    assert path.read_bytes() == before
    detached = await client.post(
        "/v1/adapters/codex/shared/detach",
        json={
            "inspection_id": snapshot["inspection_id"],
            "selection_id": snapshot["selection_id"],
        },
    )
    assert detached.status_code == 200, detached.text
    assert (await client.get(STATUS_URL)).json()["connection"] is None


@pytest.mark.asyncio
async def test_cancelled_threaded_origin_save_keeps_lock_until_publication_settles(
    shared_client,
    monkeypatch,
):
    import threading

    import pex_bridge.codex_shared_attach as module

    _, body, _, _, _, manager = shared_client
    path = Path(body["cwd"]) / "local-origin.json"
    choice = load_local_origin_choice(path)
    started, release = threading.Event(), threading.Event()
    original = module.save_local_origin_choice

    def delayed(*args, **kwargs):
        started.set()
        assert release.wait(timeout=5)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "save_local_origin_choice", delayed)
    task = asyncio.create_task(manager.update_origin(LocalOriginUpdate(**_update(choice)), state))
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        await asyncio.sleep(0)
        assert manager.lock.locked()
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 5)
    assert not manager.lock.locked()
    assert load_local_origin_choice(path).revision == choice.revision + 1


@pytest.mark.asyncio
async def test_expired_status_does_not_claim_confirmable_or_touch_transport(shared_client):
    client, body, transports, _, _, manager = shared_client
    selected = await _inspect(client, body)
    manager.pending[selected["inspection_id"]].deadline = 0
    snapshot = (await client.get(STATUS_URL)).json()
    assert snapshot["pending"][0]["can_confirm"] is False
    assert snapshot["pending"][0]["expires_in_seconds"] == 0
    assert [method for method, _ in transports[0].calls] == ["thread/read"]
