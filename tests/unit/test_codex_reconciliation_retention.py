"""Both real reconciliation drains survive bounded-queue teardown, with fake I/O."""

import asyncio

import pytest
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.adapters.codex_subscription import (
    MAX_NOTIFICATIONS_PER_DRAIN,
    CodexExistingThreadSubscription,
)
from pex_protocol.enums import SessionStatus
from test_codex_subscription import (
    FakeSharedTransport,
    _authorization,
    _inspect,
    _notification,
    _thread_response,
)


@pytest.mark.asyncio
async def test_two_full_reconciliation_drains_survive_backpressure_and_cancellation(tmp_path):
    response = _thread_response(tmp_path)
    transport = FakeSharedTransport([response] * 3, response)
    original_request = transport.request
    reads = 0

    def full_drain():
        return [
            _notification(
                "thread/status/changed",
                {"threadId": "thread-1", "status": {"type": "idle"}},
            )
            for _ in range(MAX_NOTIFICATIONS_PER_DRAIN)
        ]

    async def request(method, params=None):
        nonlocal reads
        result = await original_request(method, params)
        if method == "thread/resume":
            transport.notifications.extend(full_drain())
        elif method == "thread/read":
            reads += 1
            if reads == 3:
                transport.notifications.extend(full_drain())
        return result

    transport.request = request
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)
    subscribed = await coordinator.subscribe(selected, _authorization(selected))
    expected_count = 2 * MAX_NOTIFICATIONS_PER_DRAIN
    assert len(subscribed.reconciliation_records) == expected_count == 2048

    adapter = CodexSharedAdapter(coordinator)
    entered = asyncio.Event()
    retained = []
    disconnects = []
    ordinary_completed = []

    async def ingest(event, session):
        entered.set()
        await asyncio.Event().wait()
        ordinary_completed.append(event)

    async def retain(observations, session):
        assert session.status == SessionStatus.DETACHED
        assert adapter._retaining_observations is observations
        assert adapter._retaining_session is session
        retained.extend(observations)

    async def lifecycle(event, session):
        disconnects.append((event, session))

    task = adapter.start_pipeline_pump(
        ingest, lifecycle_ingest=lifecycle, retention_ingest=retain
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        assert adapter._pending.full()
        assert adapter._enqueueing
        assert adapter._ingesting_observation is not None
        assert len(adapter._undelivered) == expected_count
        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=5)

        assert task.cancelled()
        assert ordinary_completed == []
        assert len(retained) == expected_count
        assert len({event.event_id for event, _ in retained}) == expected_count
        assert [event.metadata["ingress_sequence"] for event, _ in retained] == list(
            range(1, expected_count + 1)
        )
        assert all(snapshot.status == SessionStatus.IDLE for _, snapshot in retained)
        assert all(snapshot.last_activity is None for _, snapshot in retained)
        assert len(disconnects) == 1
        event, session = disconnects[0]
        coverage = event.metadata["observation_coverage"]
        assert session.metadata["observation_coverage"] == coverage
        assert session.last_activity is None
        assert event.metadata["worker_stopped"] is False
        assert coverage["state"] == "disconnected"
        assert coverage["disconnect_retention_state"] == "retained"
        assert coverage["pending_normalized_events"] == 0
        assert coverage["retained_after_disconnect_count"] == expected_count
        assert coverage["last_observed_live_sequence"] == expected_count
        assert coverage["last_retained_live_sequence"] == expected_count
        assert coverage["raw_stream_complete"] is False
        assert coverage["durable_before_ingest"] is False
        assert coverage["unobserved_event_count"] is None
        assert transport.closed
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await transport.close()
