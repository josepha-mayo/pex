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

    monkeypatch.setattr("pex_bridge.adapters.opencode.matching_desktop_image", slow_discovery)
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
    adapter.ingest_hook({"session_id": "ses_isolated", "cwd": "C:/Users/bench/ws"})
    sessions = await adapter.discover_sessions()
    by_id = {session.vendor_session_id: session for session in sessions}
    assert "ses_isolated" in by_id
    assert by_id["ses_isolated"].cwd == "C:/Users/bench/ws"
    assert any(call[0] == "GET" and "directory=" in call[1] for call in transport.calls)


async def test_opencode_discovery_does_not_invent_activity():
    from datetime import UTC, datetime

    from pex_protocol.enums import SessionStatus

    transport = MemoryHttpTransport()
    adapter = OpenCodeAdapter(transport)
    first = (await adapter.discover_sessions())[0]
    first.status = SessionStatus.STOPPED
    first.last_activity = datetime(2026, 1, 1, tzinfo=UTC)
    refreshed = (await adapter.discover_sessions())[0]
    assert refreshed.status == SessionStatus.STOPPED
    assert refreshed.last_activity == first.last_activity


@pytest.mark.parametrize("filtered_tail", [False, True])
async def test_opencode_pump_retries_identical_event_without_replaying_completed_prefix(
    filtered_tail,
):
    transport = MemoryHttpTransport()
    adapter = OpenCodeAdapter(transport)
    transport.events.extend(
        [
            {
                "type": "message.updated",
                "properties": {
                    "cwd": "C:/fake",
                    "info": {
                        "sessionID": "ses_retry",
                        "id": "msg_first",
                        "role": "user",
                    },
                },
            },
            {
                "type": "message.updated",
                "properties": {
                    "cwd": "C:/fake",
                    "info": {
                        "sessionID": "ses_retry",
                        "id": "msg_second",
                        "role": "assistant",
                        "parentID": "msg_first",
                    },
                },
            },
            {"type": "session.idle", "properties": {"cwd": "C:/fake", "sessionID": "ses_retry"}},
        ]
    )
    calls = []
    completed = asyncio.Event()
    if filtered_tail:
        # An invalid trailing raw entry occupies a cursor but is filtered out
        # by the transport. Returned list length does not encode raw positions.
        transport.events_since = lambda cursor: (
            len(transport.events) + 1,
            transport.events[cursor:],
            0,
        )

    async def ingest(event, session):
        calls.append(event.model_dump(mode="json"))
        if len(calls) == 2:
            raise RuntimeError("transient post-acceptance failure")
        if event.event_type == EventType.STOP:
            completed.set()

    task = adapter.start_pipeline_pump(ingest)
    try:
        await asyncio.wait_for(completed.wait(), timeout=3)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert len(calls) == 4
    assert calls[1] == calls[2], "Retry must preserve the originally accepted event exactly"


async def test_opencode_pump_recovers_after_real_journal_acceptance(tmp_path, monkeypatch):
    from pex_bridge.adapters import AdapterRegistry
    from pex_bridge.bus import EventBus
    from pex_bridge.config import Settings
    from pex_bridge.pipeline import Pipeline
    from pex_bridge.store import Store

    monkeypatch.setattr("pex_bridge.adapters.opencode.matching_desktop_image", lambda _: None)
    transport = MemoryHttpTransport()
    registry = AdapterRegistry()
    adapter = registry.opencode
    adapter.attach_transport(transport)
    transport.events.extend(
        [
            {
                "type": "message.updated",
                "properties": {
                    "cwd": str(tmp_path),
                    "info": {
                        "sessionID": "ses_journal",
                        "id": "msg_first",
                        "role": "user",
                    },
                },
            },
            {
                "type": "message.updated",
                "properties": {
                    "cwd": str(tmp_path),
                    "info": {
                        "sessionID": "ses_journal",
                        "id": "msg_second",
                        "role": "assistant",
                        "parentID": "msg_first",
                    },
                },
            },
            {
                "type": "session.idle",
                "properties": {
                    "cwd": str(tmp_path),
                    "sessionID": "ses_journal",
                },
            },
        ]
    )
    store = Store(tmp_path / "journal.sqlite")
    await store.connect()
    pipeline = Pipeline(
        store,
        registry,
        EventBus(),
        Settings.for_test(home=tmp_path, require_auth=False, autonomy="observe"),
        model=None,
    )
    original_accept = store.accept_pipeline_event
    accepted = []
    completed = asyncio.Event()

    async def fail_once_after_commit(event, **kwargs):
        receipt = await original_accept(event, **kwargs)
        accepted.append(event.event_id)
        if len(accepted) == 2:
            raise RuntimeError("injected failure after durable commit")
        return receipt

    monkeypatch.setattr(store, "accept_pipeline_event", fail_once_after_commit)

    async def ingest(event, session):
        await pipeline.ingest_event(event, session)
        if event.event_type == EventType.STOP:
            completed.set()

    task = adapter.start_pipeline_pump(ingest)
    try:
        await asyncio.wait_for(completed.wait(), timeout=10)
        records = [await store.get_event_processing(event_id) for event_id in accepted]
        assert len(records) == 3
        assert all(record["state"] == "complete" for record in records)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await store.close()
