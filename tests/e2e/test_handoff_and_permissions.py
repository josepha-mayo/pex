import pytest
from httpx import ASGITransport, AsyncClient

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.enums import EventType


@pytest.fixture
async def client(tmp_path):
    settings = Settings(require_auth=False, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.pipeline = Pipeline(store, adapters, bus, settings)
    await store.connect()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await store.close()


@pytest.mark.asyncio
async def test_context_handoff_injects_bundle(client: AsyncClient):
    source = (await client.post("/v1/synthetic/sessions")).json()
    # second session
    source_adapter = state.adapters.synthetic
    target = source_adapter.seed_session(vendor_id="synth-2")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Eval",
                "objective": "Share the dataset path discovered by Codex with Cursor",
                "acceptance_criteria": ["both agents use prepared_dataset.parquet"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{source['id']}/attach", json={"goal_id": goal["id"]})
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source["id"],
            "event_type": EventType.AGENT_RESPONSE.value,
            "message": "Dataset is at artifacts/prepared_dataset.parquet. Do not regenerate it.",
        },
    )
    handoff = await client.post(
        f"/v1/sessions/{source['id']}/handoff",
        json={"target_session_id": target.id},
    )
    assert handoff.status_code == 200
    body = handoff.json()
    assert body["ok"] is True
    assert "prepared_dataset" in str(body["bundle"]).lower() or body["bundle"]["goal_summary"]
    assert source_adapter.inbox[target.id]


@pytest.mark.asyncio
async def test_pytest_permission_auto_allowed(client: AsyncClient):
    session = (await client.post("/v1/synthetic/sessions")).json()
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "t",
                "objective": "o",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session['id']}/attach", json={"goal_id": goal["id"]})
    event = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session["id"],
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
        },
    )
    # default phase is DURING; force via hook-style permission using cursor adapter
    assert event.status_code == 200
    hook = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeShellExecution",
            "conversation_id": "conv-perm",
            "command": "pytest -q",
            "workspace_roots": ["C:/proj"],
        },
    )
    assert hook.json().get("permission") == "allow"


@pytest.mark.asyncio
async def test_destructive_shell_permission_asks_human(client: AsyncClient):
    hook = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeShellExecution",
            "conversation_id": "conv-rm",
            "command": "rm -rf /tmp/pex-scratch",
            "workspace_roots": ["C:/proj"],
        },
    )
    assert hook.json().get("permission") == "ask"
