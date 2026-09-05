"""Independent workspace attachment probes: temporary Store and fake vendor only."""
# ruff: noqa: F811 -- pytest fixture imported explicitly for this module.

from pathlib import Path

import pytest
from pex_bridge.app import state
from pex_bridge.local_origin_config import load_local_origin_choice, save_local_origin_choice
from pex_bridge.local_workspace import measure_local_directory
from pex_protocol.project_identity import ProjectLocator
from test_codex_shared_attach import _confirm, _inspect, shared_client  # noqa: F401
from test_codex_subscription import FakeSharedTransport, _thread_response


def _refresh_origin(body):
    path = Path(body["cwd"]) / "local-origin.json"
    choice = load_local_origin_choice(path)
    return save_local_origin_choice(
        path, choice.origin,
        expected_revision=choice.revision, expected_choice_id=choice.choice_id,
    )


@pytest.mark.asyncio
async def test_origin_change_during_authority_await_cannot_resume_selected_worker(
    shared_client, monkeypatch,
):
    client, body, transports, _, _, _ = shared_client
    selected = await _inspect(client, body)
    original = state.store.get_session_control_state
    changed = False

    async def change_during_control_read(session_id):
        nonlocal changed
        result = await original(session_id)
        if not changed:
            changed = True
            _refresh_origin(body)
        return result

    monkeypatch.setattr(state.store, "get_session_control_state", change_during_control_read)
    response = await _confirm(client, selected)
    assert response.status_code == 409, response.text
    assert changed
    assert "thread/resume" not in [method for method, _ in transports[0].calls]
    assert await state.store.get_session(selected["session_id"]) is None


@pytest.mark.asyncio
async def test_status_does_not_advertise_stale_origin_selection_as_confirmable(shared_client):
    client, body, transports, _, _, _ = shared_client
    selected = await _inspect(client, body)
    fresh = _refresh_origin(body)
    response = await client.get("/v1/adapters/codex/shared/status")
    assert response.status_code == 200, response.text
    status = response.json()
    assert status["origin"]["choice"]["choice_id"] == fresh.choice_id
    pending = next(p for p in status["pending"] if p["inspection_id"] == selected["inspection_id"])
    assert pending["can_confirm"] is False
    assert [method for method, _ in transports[0].calls] == ["thread/read"]


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_field", ["provider", "object_id"])
@pytest.mark.parametrize("preexisting_unproved", [False, True])
async def test_same_origin_with_foreign_physical_proof_cannot_attach(
    shared_client, changed_field, preexisting_unproved,
):
    client, body, transports, _, _, _ = shared_client
    choice = load_local_origin_choice(Path(body["cwd"]) / "local-origin.json")
    workspace = Path(body["cwd"])
    if not preexisting_unproved:
        workspace = workspace / "separate-workspace"
        workspace.mkdir()
    directory = measure_local_directory(str(workspace))
    physical = directory.physical.model_copy(update={changed_field: "foreign-proof"})
    key = f"review-project-{changed_field}"
    await state.store.register_project_locator(
        legacy_project_id=key,
        locator=ProjectLocator.path(
            str(workspace), platform=directory.platform, origin=choice.origin, physical=physical,
        ),
    )
    response = await client.post(
        "/v1/adapters/codex/shared/inspect",
        json={**body, "project_id": key, "cwd": str(workspace)},
    )
    assert response.status_code == 409, response.text
    assert transports == []


@pytest.mark.asyncio
async def test_replaced_workspace_directory_rejects_pending_confirmation(
    shared_client, monkeypatch,
):
    import pex_bridge.codex_shared_attach as module

    client, body, transports, _, _, _ = shared_client
    workspace = Path(body["cwd"]) / "replaceable-workspace"
    workspace.mkdir()
    choice = load_local_origin_choice(Path(body["cwd"]) / "local-origin.json")
    measured = measure_local_directory(str(workspace))
    key = "review-replaceable-workspace"
    await state.store.register_project_locator(
        legacy_project_id=key,
        locator=ProjectLocator.path(
            str(workspace), platform=measured.platform, origin=choice.origin,
        ),
    )

    def transport_factory(*args, **kwargs):
        response = _thread_response(workspace)
        transport = FakeSharedTransport([response] * 3, response)
        transport.receive_journal = kwargs["receive_journal"]
        transports.append(transport)
        return transport

    monkeypatch.setattr(module, "CodexSharedAppServerTransport", transport_factory)
    selected = await _inspect(client, {**body, "project_id": key, "cwd": str(workspace)})
    original_preserved = workspace.with_name("preserved-original-workspace")
    workspace.rename(original_preserved)
    workspace.mkdir()
    assert measure_local_directory(str(original_preserved)).physical == measured.physical
    response = await _confirm(client, selected)
    assert response.status_code == 409, response.text
    status = (await client.get("/v1/adapters/codex/shared/status")).json()
    pending = next(p for p in status["pending"] if p["inspection_id"] == selected["inspection_id"])
    assert pending["can_confirm"] is False
    assert [method for method, _ in transports[0].calls] == ["thread/read"]
    assert await state.store.get_session(selected["session_id"]) is None
