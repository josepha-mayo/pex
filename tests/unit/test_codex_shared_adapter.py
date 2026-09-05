"""Actual shared adapter pump with an in-memory vendor, never a live worker."""

import asyncio

import pytest
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_protocol.enums import EventType, SessionStatus
from test_codex_subscription import _notification, _subscribed


async def eventually(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(wait(), timeout=2)


@pytest.mark.asyncio
async def test_closed_thread_is_a_durable_local_gap_not_fake_worker_completion(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    events = []

    async def ingest(event, session):
        events.append((event, session))

    task = adapter.start_pipeline_pump(ingest, lifecycle_ingest=ingest)
    transport.notifications.append(_notification("thread/closed", {"threadId": "thread-1"}))
    await asyncio.wait_for(task, timeout=2)
    assert len(events) == 1
    event, session = events[0]
    assert event.event_type == EventType.STATUS
    assert event.metadata["source"] == "pex_observer_lifecycle"
    assert event.metadata["worker_stopped"] is False
    assert session.status == SessionStatus.DETACHED
    assert session.last_activity is None
    assert session.capabilities["observe_messages"] is False
    coverage = event.metadata["observation_coverage"]
    assert coverage["state"] == "disconnected"
    assert coverage["reason"] == "vendor_thread_closed"
    assert coverage["raw_stream_complete"] is False
    assert coverage["unobserved_event_count"] is None
    assert transport.closed


@pytest.mark.asyncio
async def test_disconnect_preserves_unknown_pending_observations(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    entered = asyncio.Event()
    events = []

    async def ingest(event, session):
        if event.metadata.get("source") != "pex_observer_lifecycle":
            entered.set()
            await asyncio.Event().wait()
        events.append((event, session))

    task = adapter.start_pipeline_pump(ingest, lifecycle_ingest=ingest)
    transport.notifications.extend(
        [
            _notification("turn/started", {"threadId": "thread-1", "turn": {"id": "t1"}}),
            _notification("turn/started", {"threadId": "thread-1", "turn": {"id": "t2"}}),
        ]
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    await eventually(lambda: adapter.ingress_sequence == 2)
    activity = adapter.session.last_activity
    transport.notifications.append(_notification("thread/closed", {"threadId": "thread-1"}))
    await asyncio.wait_for(task, timeout=2)
    assert len(events) == 1
    coverage = events[0][0].metadata["observation_coverage"]
    assert coverage["last_observed_live_sequence"] == 2
    assert coverage["last_ingested_live_sequence"] == 0
    assert coverage["pending_normalized_events"] == 2
    assert events[0][1].last_activity == activity


@pytest.mark.asyncio
async def test_failed_gap_ingestion_is_not_reported_as_durable_success(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)

    async def unavailable(event, session):
        raise RuntimeError("fixture store is unavailable")

    transport.notifications.append(_notification("thread/closed", {"threadId": "thread-1"}))
    await asyncio.wait_for(
        adapter.start_pipeline_pump(unavailable, lifecycle_ingest=unavailable), timeout=2
    )
    assert adapter.last_pump_error == "disconnect_receipt_RuntimeError"
    assert not adapter._connected()
    assert adapter.session.status == SessionStatus.DETACHED


@pytest.mark.asyncio
async def test_turn_completion_items_are_not_fabricated_as_live_item_events(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    events = []

    async def ingest(event, session):
        events.append(event)

    task = adapter.start_pipeline_pump(ingest, lifecycle_ingest=ingest)
    transport.notifications.append(
        _notification(
            "turn/completed",
            {
                "threadId": "thread-1",
                "turn": {
                    "id": "turn-1",
                    "status": "completed",
                    "items": [
                        {
                            "type": "userMessage",
                            "id": "u1",
                            "content": [{"type": "text", "text": "input"}],
                        }
                    ],
                },
            },
        )
    )
    try:
        await eventually(lambda: len(events) == 1)
        assert events[0].event_type == EventType.STOP
        assert events[0].metadata["sequence_scope"] == "retained_lifecycle_records_not_raw_frames"
        assert adapter.input_revision == 0
        assert adapter.session.metadata["observation_coverage"]["raw_stream_complete"] is False
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
