"""Live Codex App Server attach. Skips when the Codex CLI is not on this machine."""

from __future__ import annotations

import asyncio

import pytest
from pex_bridge.adapters.codex import CodexAdapter, CodexStdioTransport
from pex_bridge.adapters.codex_bin import resolve_codex_bin

from tests.contract.live_gate import require_live_authorization


@pytest.mark.live_codex
@pytest.mark.asyncio
async def test_live_codex_appserver_handshake():
    require_live_authorization("PEX_LIVE_CODEX")
    binary = resolve_codex_bin()
    if not binary:
        pytest.skip("codex CLI not found")
    transport = CodexStdioTransport(binary)
    adapter = CodexAdapter(transport)
    pump = None
    try:
        caps = await adapter.probe()
        assert caps.support_label.value == "basic", caps.notes

        async def ingest(*_):
            return None

        pump = adapter.start_pipeline_pump(ingest)
        caps = await adapter.probe()
        assert caps.support_label.value == "deep", caps.notes
        sessions = await adapter.discover_sessions()
        assert isinstance(sessions, list)
        assert transport.initialized
        assert transport.init_result is not None
        assert transport.init_result.get("platformOs")
    finally:
        if pump is not None:
            pump.cancel()
            try:
                await pump
            except asyncio.CancelledError:
                pass
        await transport.close()
