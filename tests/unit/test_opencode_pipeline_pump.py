from __future__ import annotations

import asyncio
import threading
import time

import pytest
from pex_bridge.adapters.http_json import MemoryHttpTransport
from pex_bridge.adapters.opencode import OpenCodeAdapter
from pex_protocol.enums import EventType


@pytest.mark.live_desktop
async def test_opencode_probe_reuses_scoped_snapshot_in_worker_thread(monkeypatch):
    from pex_bridge.adapters import desktop

    reads = []

    def unexpected_read():
        reads.append(True)
        return set()

    monkeypatch.setattr(desktop, "_read_running_image_names", unexpected_read)
    snapshot = desktop.DesktopProcessSnapshot(
        names=frozenset({"OpenCode.exe"}), available=True, captured_at=time.monotonic()
    )
    with desktop.scoped_running_image_snapshot(snapshot):
        capabilities = await OpenCodeAdapter(MemoryHttpTransport()).probe()
    assert capabilities.focus_ui is True
    assert reads == []


async def test_opencode_probe_keeps_loop_responsive_during_desktop_discovery(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    timed_out = threading.Event()

    def slow_discovery(_images):
        entered.set()
        if not release.wait(timeout=2):
            timed_out.set()
        return "opencode.exe"

    monkeypatch.setattr(
        "pex_bridge.adapters.opencode.matching_desktop_image", slow_discovery
    )
    adapter = OpenCodeAdapter(MemoryHttpTransport())
    probe = asyncio.create_task(adapter.probe())
    try:
        async with asyncio.timeout(3):
            while not entered.is_set():
                await asyncio.sleep(0)
            # This coroutine must resume before the synchronous discovery exits.
            assert not timed_out.is_set()
            assert not probe.done()
            release.set()
            capabilities = await probe
        assert capabilities.focus_ui is True
        assert capabilities.send_message is True
    finally:
        release.set()
        await asyncio.gather(probe, return_exceptions=True)


async def test_opencode_pump_ingests_idle_as_stop():
    transport = MemoryHttpTransport()
    adapter = OpenCodeAdapter(transport)
    ingested: list = []

    async def ingest(event, session):
        ingested.append((event, session))

    transport.events.append({"type": "server.connected", "properties": {}})
    transport.events.append(
        {
            "id": "evt_msg",
            "type": "message.updated",
            "properties": {
                "info": {"sessionID": "sess_pump", "role": "assistant"},
                "cwd": "/tmp/pex-opencode",
            },
            "text": "working",
        }
    )
    transport.events.append(
        {
            "id": "evt_idle",
            "type": "session.idle",
            "properties": {"sessionID": "sess_pump", "cwd": "/tmp/pex-opencode"},
        }
    )

    task = adapter.start_pipeline_pump(ingest)
    try:
        wanted = {EventType.AGENT_RESPONSE.value, EventType.STOP.value}
        for _ in range(40):
            types = {event.event_type.value for event, _ in ingested}
            if wanted <= types:
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    types = {event.event_type.value for event, _ in ingested}
    assert EventType.AGENT_RESPONSE.value in types
    assert EventType.STOP.value in types
    assert all(session.vendor_session_id == "sess_pump" for _, session in ingested)
    assert any(session.cwd == "/tmp/pex-opencode" for _, session in ingested)
    assert "server.connected" not in {event.metadata.get("sse_type") for event, _ in ingested}


async def test_opencode_discover_relists_isolated_project_sessions():
    transport = MemoryHttpTransport()
    transport.sessions = [
        {"id": "sess_demo", "title": "demo", "cwd": "C:/fake"},
        {
            "id": "ses_isolated",
            "title": "bench",
            "cwd": "C:/Users/bench/ws",
            "directory": "C:/Users/bench/ws",
            "isolated_project": True,
        },
    ]
    adapter = OpenCodeAdapter(transport)
    adapter.ingest_hook(
        {"session_id": "ses_isolated", "cwd": "C:/Users/bench/ws"}
    )
    sessions = await adapter.discover_sessions()
    by_id = {session.vendor_session_id: session for session in sessions}
    assert "ses_isolated" in by_id
    assert by_id["ses_isolated"].cwd == "C:/Users/bench/ws"
    assert any(
        call[0] == "GET" and "directory=" in call[1]
        for call in transport.calls
    )
