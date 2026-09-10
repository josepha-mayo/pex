from __future__ import annotations

import asyncio

import pytest
from pex_bridge.adapters.base import DeliveryUncertainError
from pex_bridge.adapters.http_json import MemoryHttpTransport
from pex_bridge.adapters.opencode import OpenCodeAdapter
from pex_protocol.enums import EventType


def _idle(event_id):
    return {
        "id": event_id,
        "type": "session.idle",
        "properties": {"sessionID": "sess_boundary", "cwd": "/tmp/pex-boundary"},
    }


async def _setup():
    transport = MemoryHttpTransport()
    adapter = OpenCodeAdapter(transport)
    session = adapter._session_for(_idle("setup"))
    assert session is not None

    async def no_receipt(*args, **kwargs):
        return None

    adapter._new_prompt_turn_id = no_receipt
    return adapter, transport, session


@pytest.mark.parametrize("uncertain", [False, True])
async def test_prompt_boundary_suppresses_only_known_old_batch_and_retries_identically(uncertain):
    adapter, transport, session = await _setup()
    transport.events.append(_idle("old-idle"))
    if uncertain:
        request = transport.request

        async def uncertain_post(method, path, **kwargs):
            if method == "POST":
                raise DeliveryUncertainError("test admission unknown")
            return await request(method, path, **kwargs)

        transport.request = uncertain_post
        with pytest.raises(DeliveryUncertainError):
            await adapter.send_message(session, "Finish the missing artifact.")
    else:
        assert await adapter.send_message(session, "Finish the missing artifact.") is True

    received = []
    finished = asyncio.Event()

    async def ingest(event, _session):
        received.append(event.model_dump(mode="json"))
        if len(received) == 1:
            # The pending normalized event must survive an acceptance retry.
            transport.events.append(_idle("new-idle"))
            raise RuntimeError("one retained ingestion retry")
        if len(received) == 3:
            finished.set()

    pump = adapter.start_pipeline_pump(ingest)
    try:
        await asyncio.wait_for(finished.wait(), timeout=3)
    finally:
        pump.cancel()
        await asyncio.gather(pump, return_exceptions=True)
    assert received[0] == received[1]
    assert [event["event_type"] for event in received] == ["status", "status", "stop"]
    assert "opencode_status" not in received[0]["metadata"]


async def test_mixed_batch_does_not_suppress_new_idle():
    adapter, transport, session = await _setup()
    transport.events.append(_idle("old-idle"))
    await adapter.send_message(session, "Finish the missing artifact.")
    transport.events.append(_idle("new-idle"))
    received = []
    finished = asyncio.Event()

    async def ingest(event, _session):
        received.append(event)
        if len(received) == 2:
            finished.set()

    pump = adapter.start_pipeline_pump(ingest)
    try:
        await asyncio.wait_for(finished.wait(), timeout=2)
    finally:
        pump.cancel()
        await asyncio.gather(pump, return_exceptions=True)
    assert all(event.event_type == EventType.STOP for event in received)


async def test_watermark_observation_failure_does_not_block_prompt():
    adapter, transport, session = await _setup()

    def broken_reader(cursor):
        raise RuntimeError("read unavailable")

    transport.events_since = broken_reader
    assert await adapter.send_message(session, "Finish the missing artifact.") is True
    assert len(transport.prompts) == 1
    assert adapter.normalize_sse(session, _idle("new-idle")).event_type == EventType.STOP


async def test_rejected_prompt_does_not_create_boundary():
    adapter, transport, session = await _setup()
    transport.events.append(_idle("old-idle"))
    request = transport.request

    async def rejected_post(method, path, **kwargs):
        if method == "POST":
            raise ValueError("rejected before admission")
        return await request(method, path, **kwargs)

    transport.request = rejected_post
    assert await adapter.send_message(session, "Finish the missing artifact.") is False
    assert session.id not in adapter._prompt_event_boundaries


async def test_transport_replacement_discards_old_boundary_and_wire_cannot_set_flag():
    adapter, transport, session = await _setup()
    transport.events.append(_idle("old-idle"))
    await adapter.send_message(session, "Finish the missing artifact.")
    assert session.id in adapter._prompt_event_boundaries
    adapter.attach_transport(MemoryHttpTransport())
    assert adapter._prompt_event_boundaries == {}
    payload = _idle("new-idle")
    payload["pre_admission_idle"] = True
    assert adapter.normalize_sse(session, payload).event_type == EventType.STOP
