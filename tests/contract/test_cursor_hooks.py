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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await store.close()


@pytest.mark.asyncio
async def test_cursor_stop_hook_returns_followup(client: AsyncClient):
    await client.post("/v1/synthetic/sessions")
    goal = await client.post(
        "/v1/goals",
        json={
            "project_id": "C:/proj",
            "title": "Fix bug",
            "objective": "Fix the failing test",
            "acceptance_criteria": ["tests pass"],
        },
    )
    goal_id = goal.json()["id"]
    # Seed cursor session via hook
    first = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "sessionStart",
            "conversation_id": "conv-1",
            "workspace_roots": ["C:/proj"],
            "session_id": "conv-1",
        },
    )
    assert first.status_code == 200
    await client.post("/v1/sessions/cursor:conv-1/attach", json={"goal_id": goal_id})
    stop = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "stop",
            "conversation_id": "conv-1",
            "workspace_roots": ["C:/proj"],
            "status": "completed",
            "loop_count": 0,
        },
    )
    data = stop.json()
    assert "followup_message" in data
    assert "PEX" in data["followup_message"]


@pytest.mark.asyncio
async def test_pause_supervision_blocks_interventions(client: AsyncClient):
    session = (await client.post("/v1/synthetic/sessions")).json()
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "x",
                "objective": "y",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    sid = session["id"]
    await client.post(f"/v1/sessions/{sid}/attach", json={"goal_id": goal["id"]})
    await client.post(f"/v1/sessions/{sid}/pause-supervision")
    stop = await client.post(
        "/v1/synthetic/events",
        json={"session_id": sid, "event_type": EventType.STOP.value, "message": "done"},
    )
    assert stop.json()["intervention"] is None


@pytest.mark.asyncio
async def test_focus_does_not_inject_worker_text(client: AsyncClient):
    session = (await client.post("/v1/synthetic/sessions")).json()
    sid = session["id"]
    focused = await client.post(f"/v1/sessions/{sid}/focus")
    assert focused.status_code == 200
    assert focused.json()["ok"] is True
    inbox = state.adapters.synthetic.inbox.get(sid, [])
    assert "PEX: focusing this session." not in inbox
