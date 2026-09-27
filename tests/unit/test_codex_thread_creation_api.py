from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.codex import CodexAppServerTransport
from pex_bridge.app import create_app, state
from pex_bridge.codex_shared_attach import SharedCodexAttachments
from pex_bridge.config import Settings
from pex_bridge.store import Store


@pytest.fixture
async def creation(tmp_path, monkeypatch):
    store = Store(tmp_path / "creation.sqlite")
    await store.connect()
    registry = AdapterRegistry()
    transport = CodexAppServerTransport()
    registry.codex.attach_transport(transport)
    manager = SharedCodexAttachments()
    monkeypatch.setattr(state, "store", store)
    monkeypatch.setattr(state, "adapters", registry)
    monkeypatch.setattr(state, "codex_shared_attachments", manager)
    monkeypatch.setattr(
        state, "settings", Settings(home=tmp_path, require_auth=True, cloud_reasoning=False)
    )
    monkeypatch.setattr(state, "token", "fixture-only-creation-token")
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://127.0.0.1",
            headers={"Authorization": "Bearer fixture-only-creation-token"},
        ) as client:
            yield SimpleNamespace(
                client=client,
                store=store,
                registry=registry,
                transport=transport,
                manager=manager,
                workspace=tmp_path,
            )
    finally:
        await transport.close()
        await store.close()


async def test_creation_registers_exact_idle_thread_without_model_turn(creation):
    case = creation
    response = await case.client.post(
        "/v1/adapters/codex/threads", json={"workspace": str(case.workspace)}
    )
    assert response.status_code == 200, response.text
    receipt = response.json()
    session = receipt["session"]
    assert receipt["model_turn_started"] is False
    assert receipt["requested_workspace"] == str(case.workspace)
    assert session["status"] == "idle"
    assert session["cwd"] == str(case.workspace.resolve())
    assert session["metadata"]["isolated"] is True
    assert session["metadata"]["source"] == "pex_ui"
    assert session["capabilities"]["observe_session_status"] is True
    stored = await case.store.get_session_for_authority(session["id"])
    assert stored is not None and stored.status.value == "idle"
    assert case.transport.turns == []
    assert stored.id in case.registry.codex.sessions


@pytest.mark.parametrize("kind", ["relative", "missing", "file", "root", "nul", "extra"])
async def test_invalid_workspace_has_no_codex_side_effects(creation, kind, monkeypatch):
    case = creation
    file = case.workspace / "not-folder.txt"
    file.write_text("file", encoding="utf-8")
    workspace = {
        "relative": "relative/project",
        "missing": str(case.workspace / "missing"),
        "file": str(file),
        "root": case.workspace.anchor,
        "nul": "invalid\0path",
        "extra": str(case.workspace),
    }[kind]
    calls = []
    original = case.transport.request

    async def record(method, params=None):
        calls.append(method)
        return await original(method, params)

    monkeypatch.setattr(case.transport, "request", record)
    body = {"workspace": workspace}
    if kind == "extra":
        body["sandbox"] = "danger-full-access"
    response = await case.client.post("/v1/adapters/codex/threads", json=body)
    assert response.status_code == 422
    assert calls == []
    assert case.registry.codex.sessions == {}


@pytest.mark.parametrize("kind", ["bad_token", "test_no_auth", "detached", "closed", "shared"])
async def test_unavailable_or_unauthorized_creation_is_refused(creation, kind, monkeypatch):
    case = creation
    headers = {}
    if kind == "bad_token":
        headers["Authorization"] = "Bearer wrong-fixture-token"
    elif kind == "test_no_auth":
        monkeypatch.setattr(
            state, "settings", Settings.for_test(home=case.workspace, require_auth=False)
        )
    elif kind == "detached":
        case.registry.codex.transport = None
    elif kind == "closed":
        case.manager.closed = True
    else:
        case.manager.active = SimpleNamespace()
    response = await case.client.post(
        "/v1/adapters/codex/threads", json={"workspace": str(case.workspace)}, headers=headers
    )
    assert response.status_code in {401, 403, 409}
    assert case.registry.codex.sessions == {}
    assert case.transport.turns == []


async def test_lost_persistence_reports_uncertainty_without_repeating_creation(
    creation, monkeypatch
):
    case = creation

    async def fail(session):
        raise RuntimeError("fixture database failure")

    monkeypatch.setattr(case.store, "upsert_session", fail)
    response = await case.client.post(
        "/v1/adapters/codex/threads", json={"workspace": str(case.workspace)}
    )
    assert response.status_code == 502
    assert "inspect Home before retrying" in response.text
    assert len(case.registry.codex.sessions) == 1
    assert case.transport.turns == []


async def test_live_cli_creation_does_not_wait_for_unrelated_desktop_inventory(
    creation, monkeypatch
):
    def forbidden_scan():
        raise AssertionError("headless App Server must not scan Codex Desktop")

    monkeypatch.setattr("pex_bridge.adapters.codex.chatgpt_desktop_running", forbidden_scan)
    response = await creation.client.post(
        "/v1/adapters/codex/threads",
        json={"workspace": str(creation.workspace)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["session"]["capabilities"]["focus_ui"] is False
