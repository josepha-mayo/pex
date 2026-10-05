"""/health advertises the test-scoped unauthenticated-operator allowance so
the browser demo can unlock decision resolution and handoff controls. A
production bridge can never set it — Settings refuses the combination."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store


async def _client(tmp_path, **settings_kwargs):
    state.settings = Settings.for_test(require_auth=False, home=tmp_path, **settings_kwargs)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, state.settings)
    await store.connect()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://127.0.0.1",
        ) as client:
            yield client
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_health_reports_no_operator_allowance_by_default(tmp_path) -> None:
    async for client in _client(tmp_path):
        body = (await client.get("/health")).json()
        assert body["unauthenticated_operator"] is False


@pytest.mark.asyncio
async def test_health_advertises_the_demo_operator_allowance(tmp_path) -> None:
    async for client in _client(tmp_path, allow_unauthenticated_operator=True):
        body = (await client.get("/health")).json()
        assert body["unauthenticated_operator"] is True
