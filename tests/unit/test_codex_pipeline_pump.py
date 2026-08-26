from __future__ import annotations

import asyncio

from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport
from pex_protocol.enums import EventType


async def test_codex_pump_ingests_stop_permission_and_agent_message():
    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_pump", "preview": "pump thread", "cwd": "C:/proj"}]
    adapter = CodexAdapter(transport)
    ingested: list = []

    async def ingest(event, session):
        ingested.append((event, session))

    transport.pending_approvals["req_pump"] = {
        "id": "req_pump",
        "method": "item/commandExecution/requestApproval",
        "params": {"threadId": "thr_pump", "command": "pytest", "cwd": "C:/proj"},
    }
    transport.notifications.append(
        {
            "method": "item/completed",
            "params": {
                "threadId": "thr_pump",
                "cwd": "C:/proj",
                "item": {"id": "item_msg", "type": "agentMessage", "text": "working on it"},
            },
        }
    )
    transport.notifications.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": "thr_pump",
                "cwd": "C:/proj",
                "turn": {"id": "t_pump", "status": "completed", "items": []},
            },
        }
    )

    task = adapter.start_pipeline_pump(ingest)
    try:
        wanted = {
            EventType.PERMISSION_REQUEST.value,
            EventType.AGENT_RESPONSE.value,
            EventType.STOP.value,
        }
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
    assert EventType.PERMISSION_REQUEST.value in types
    assert EventType.AGENT_RESPONSE.value in types
    assert EventType.STOP.value in types
    session = adapter.sessions.get("codex:thr_pump")
    assert session is not None
    assert session.cwd == "C:/proj"
