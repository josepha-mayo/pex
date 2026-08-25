"""Live Codex App Server attach. Skips when the Codex CLI is not on this machine."""

from __future__ import annotations

import pytest

from pex_bridge.adapters.codex import CodexAdapter, CodexStdioTransport
from pex_bridge.adapters.codex_bin import resolve_codex_bin


@pytest.mark.asyncio
async def test_live_codex_appserver_handshake():
    binary = resolve_codex_bin()
    if not binary:
        pytest.skip("codex CLI not found")
    transport = CodexStdioTransport(binary)
    adapter = CodexAdapter(transport)
    try:
        caps = await adapter.probe()
        assert caps.support_label.value == "deep", caps.notes
        sessions = await adapter.discover_sessions()
        assert isinstance(sessions, list)
        assert transport.initialized
        assert transport.init_result is not None
        assert transport.init_result.get("platformOs")
    finally:
        await transport.close()
