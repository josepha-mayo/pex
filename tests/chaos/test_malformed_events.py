from unittest.mock import AsyncMock

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
    settings = Settings.for_test(require_auth=False, home=tmp_path)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.pipeline = Pipeline(store, adapters, EventBus(), settings)
    await store.connect()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as ac:
        yield ac
    await store.close()


@pytest.mark.asyncio
async def test_malformed_cursor_hook_does_not_crash_bridge(client: AsyncClient):
    res = await client.post("/v1/hooks/cursor", json={"unexpected": True, "nested": {"x": 1}})
    assert res.status_code == 422
    health = await client.get("/health")
    assert health.json()["ok"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [None, 1])
@pytest.mark.parametrize("configure_during_dispatch", [False, True])
async def test_malformed_adapter_event_does_not_stop_sibling_supervision(
    client: AsyncClient, tmp_path, monkeypatch, limit, configure_during_dispatch,
):
    monkeypatch.delenv("PEX_FORCE_LLM", raising=False)
    state.pipeline.settings.supervisor_max_dispatches_per_session = limit
    worker = tmp_path / "healthy-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="healthy-sibling", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "report",
                "objective": "Create report.txt containing exactly the word shipped.",
                "acceptance_criteria": ["report.txt contains shipped"],
                "evidence_requirements": ["report.txt"],
            },
        )
    ).json()
    attached = await client.post(
        f"/v1/sessions/{session.id}/attach",
        json={"goal_id": goal["id"]},
    )
    assert attached.status_code == 200
    malformed = await client.post(
        "/v1/hooks/cursor",
        json={"unexpected": True, "nested": {"x": 1}},
    )
    assert malformed.status_code == 422
    provider_route = AsyncMock(side_effect=AssertionError("unreserved provider route"))
    monkeypatch.setattr(state.pipeline.supervisor, "decide", provider_route)
    if configure_during_dispatch:
        original_dispatch = state.store.start_event_effect_dispatch

        async def dispatch_then_configure(**kwargs):
            result = await original_dispatch(**kwargs)
            state.pipeline.model = object()
            return result

        monkeypatch.setattr(state.store, "start_event_effect_dispatch", dispatch_then_configure)
    stopped = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "I am done.",
        },
    )
    intervention = stopped.json()["intervention"]
    assert intervention["action_taken"] == "SEND_NUDGE"
    text = adapter.inbox[session.id][-1]
    assert "report.txt" in text
    assert not text.startswith("PEX:")
    provider_route.assert_not_awaited()
    assert intervention["metadata"]["used_llm"] is False
    assert await state.store.supervisor_dispatch_counts([session.id]) == {session.id: 0}
    health = await client.get("/health")
    assert health.json()["ok"] is True
