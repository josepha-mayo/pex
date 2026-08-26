from __future__ import annotations

import asyncio

from pex_bridge.adapters.http_json import MemoryHttpTransport
from pex_bridge.adapters.opencode import OpenCodeAdapter
from pex_protocol.enums import EventType


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
            "properties": {"info": {"sessionID": "sess_pump", "role": "assistant"}},
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
