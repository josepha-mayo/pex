import pytest
from httpx import ASGITransport, AsyncClient

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pets import PetSettings
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
    state.token = None
    state.pet_settings = PetSettings()
    state.pet_path = tmp_path / "pet.json"
    await store.connect()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await store.close()


@pytest.mark.asyncio
async def test_m0_event_to_action_roundtrip(client: AsyncClient):
    health = await client.get("/health")
    assert health.json()["ok"] is True

    session_resp = await client.post("/v1/synthetic/sessions")
    session = session_resp.json()
    session_id = session["id"]

    goal_resp = await client.post(
        "/v1/goals",
        json={
            "project_id": "demo",
            "title": "Eval pipeline",
            "objective": "Produce a complete evaluation with passing tests",
            "acceptance_criteria": ["tests pass", "results.json has 30 rows"],
            "evidence_requirements": ["pytest output"],
        },
    )
    goal_id = goal_resp.json()["id"]
    attached = await client.post(f"/v1/sessions/{session_id}/attach", json={"goal_id": goal_id})
    assert attached.status_code == 200

    stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session_id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    body = stop.json()
    assert body["intervention"] is not None
    assert body["intervention"]["action_taken"] in {"CONTINUE_SESSION", "SEND_NUDGE"}
    assert body["inbox"], "PEX must send a corrective message through the adapter"
    pet = await client.get("/v1/pet")
    assert "working" in pet.json()["headline"] or "idle" in pet.json()["headline"] or pet.status_code == 200

    adapters = await client.get("/v1/adapters")
    names = {item["name"] for item in adapters.json()}
    assert "synthetic" in names
    assert "cursor" in names
    assert "codex" in names
    asked = await client.post("/v1/ask", json={"question": "what needs me?"})
    assert "answer" in asked.json()
    pets = await client.get("/v1/pets")
    assert len(pets.json()["starters"]) == 10
    assert pets.json()["codex_contract"]["spriteVersionNumber"] == 2
    claude = await client.post(
        "/v1/hooks/claude_code",
        json={"session_id": "claude-demo", "hook_event_name": "Stop", "text": "done"},
    )
    assert claude.status_code == 200
    assert claude.json()["session_id"].startswith("claude_code:")
    assert "hookSpecificOutput" in claude.json() or claude.json().get("ok") is True
    discovered = await client.get("/v1/discover")
    assert "found" in discovered.json()
    deck = await client.get("/v1/deck")
    names = {item["name"] for item in deck.json()["adapters"]}
    assert "opencode" in names
    assert "qwen" in names
    sheet = await client.get("/v1/pets/pex/spritesheet")
    assert sheet.status_code == 200
    assert sheet.headers["content-type"].startswith("image/")
    traj = await client.get("/v1/demo/trajectories")
    ids = {item["id"] for item in traj.json()["fixtures"]}
    assert "premature_stop_eval" in ids
    replay = await client.post("/v1/demo/replay", json={"fixture": "premature_stop_eval"})
    assert replay.status_code == 200
    assert replay.json()["replay"] is True
    assert replay.json()["not_live_control"] is True
    assert replay.json()["inbox"], "replay must still drive the supervisor"
    patched = await client.patch("/v1/pets/settings", json={"custom_name": "Ledgerbot", "selected_id": "ledger"})
    assert patched.status_code == 200
    shown = await client.get("/v1/pet")
    assert shown.json()["appearance"]["display_name"] == "Ledgerbot"
