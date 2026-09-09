"""Slow OS inventory must not freeze unrelated bridge coroutines."""

from __future__ import annotations

import asyncio
import threading

import pytest
from pex_bridge.adapters.acp_harness import HermesAdapter
from pex_bridge.adapters.claude_code import ClaudeCodeAdapter
from pex_bridge.adapters.codex import CodexAdapter
from pex_bridge.adapters.cursor import CursorAdapter


@pytest.mark.parametrize(
    ("factory", "lookup"),
    [
        (CodexAdapter, "pex_bridge.adapters.codex.chatgpt_desktop_running"),
        (CursorAdapter, "pex_bridge.adapters.cursor.desktop_process_running"),
        (ClaudeCodeAdapter, "pex_bridge.adapters.claude_code.matching_desktop_image"),
        (HermesAdapter, "pex_bridge.adapters.desktop.matching_desktop_image"),
    ],
)
async def test_probe_yields_during_process_discovery(monkeypatch, factory, lookup):
    entered = threading.Event()
    release = threading.Event()
    timed_out = threading.Event()

    def slow_lookup(*_args):
        entered.set()
        if not release.wait(timeout=1):
            timed_out.set()
        return "desktop.exe" if lookup.endswith("matching_desktop_image") else True

    monkeypatch.setattr(lookup, slow_lookup)
    probe = asyncio.create_task(factory().probe())
    try:
        async with asyncio.timeout(3):
            while not entered.is_set():
                await asyncio.sleep(0)
            assert not timed_out.is_set(), "OS discovery blocked the bridge event loop"
            assert not probe.done()
            release.set()
            capabilities = await probe
        assert capabilities.focus_ui
        # Seeing a desktop process alone must never grant worker control.
        assert not capabilities.send_message
    finally:
        release.set()
        await asyncio.gather(probe, return_exceptions=True)
