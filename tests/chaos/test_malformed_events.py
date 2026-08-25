import pytest
from httpx import ASGITransport, AsyncClient

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store


@pytest.fixture
async def client(tmp_path):
    settings = Settings(require_auth=False, home=tmp_path)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.pipeline = Pipeline(store, adapters, EventBus(), settings)
    await store.connect()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await store.close()


@pytest.mark.asyncio
async def test_malformed_cursor_hook_does_not_crash_bridge(client: AsyncClient):
    res = await client.post("/v1/hooks/cursor", json={"unexpected": True, "nested": {"x": 1}})
    assert res.status_code == 200
    health = await client.get("/health")
    assert health.json()["ok"] is True
