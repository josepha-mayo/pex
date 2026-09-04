"""Live OpenCode attach. Skips when `opencode serve` is not listening."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from pex_bridge.adapters.http_json import LiveHttpTransport
from pex_bridge.adapters.opencode import OpenCodeAdapter

from tests.contract.live_gate import require_live_authorization

LIVE = "http://127.0.0.1:4097"


async def _healthy() -> bool:
    try:
        async with httpx.AsyncClient(timeout=0.8) as client:
            response = await client.get(f"{LIVE}/global/health")
        return response.status_code < 500
    except Exception:
        return False


@pytest.mark.live_opencode
@pytest.mark.asyncio
async def test_live_opencode_attach_is_deep():
    require_live_authorization("PEX_LIVE_OPENCODE")
    if not await _healthy():
        pytest.skip("opencode serve is not listening on 4097")
    adapter = OpenCodeAdapter(LiveHttpTransport(LIVE))
    assert (await adapter.probe()).support_label.value == "strong"

    async def ingest(*_):
        return None

    task = adapter.start_pipeline_pump(ingest)
    try:
        caps = await adapter.probe()
        assert caps.support_label.value == "deep"
        sessions = await adapter.discover_sessions()
        assert isinstance(sessions, list)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
