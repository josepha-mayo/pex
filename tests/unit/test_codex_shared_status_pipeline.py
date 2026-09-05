"""Real Pipeline/Store projection, with only the vendor transport faked."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.enums import EventType, SessionStatus
from pex_protocol.session import HarnessEvent
from test_codex_subscription import _notification, _subscribed


@pytest.fixture
async def live_pipeline(tmp_path, request):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    store = Store(tmp_path / "status.sqlite")
    await store.connect()
    registry = AdapterRegistry()
    registry.bind("codex", adapter)
    pipeline = Pipeline(
        store, registry, EventBus(), Settings.for_test(home=tmp_path, require_auth=False)
    )
    adapter.session.last_activity = getattr(
        request, "param", datetime.now(UTC) - timedelta(hours=1)
    )
    binding = await store.project_binding_for_authority(adapter.session.project_id)
    await store.publish_observer_session(
        adapter.session, expected_control_revision=None, expected_project_binding=binding
    )
    task = adapter.start_pipeline_pump(
        pipeline.ingest_shared_codex_event,
        lifecycle_ingest=pipeline.ingest_observer_lifecycle,
    )
    try:
        yield pipeline, store, adapter, transport
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await pipeline.close_presentations()
        await store.close()


async def deliver(adapter, transport, method, params):
    before = adapter.last_ingested_sequence
    transport.notifications.append(_notification(method, params))

    async def wait():
        while adapter.last_ingested_sequence <= before:
            await asyncio.sleep(0.005)

    await asyncio.wait_for(wait(), timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ({"type": "idle"}, SessionStatus.IDLE),
        ({"type": "systemError"}, SessionStatus.ERROR),
        ({"type": "notLoaded"}, SessionStatus.DISCOVERED),
        ({"type": "active", "activeFlags": []}, SessionStatus.WORKING),
        ({"type": "active", "activeFlags": ["waitingOnApproval"]}, SessionStatus.BLOCKED),
        ({"type": "active", "activeFlags": ["waitingOnUserInput"]}, SessionStatus.DISCOVERED),
    ],
)
async def test_runtime_status_survives_pipeline_without_inventing_work(
    live_pipeline, status, expected
):
    _, store, adapter, transport = live_pipeline
    before = await store.get_session(adapter.session.id)
    await deliver(
        adapter, transport, "thread/status/changed", {"threadId": "thread-1", "status": status}
    )
    saved = await store.get_session(adapter.session.id)
    assert saved.status == expected
    assert saved.last_activity == before.last_activity
    assert saved.metadata["observation_coverage"]["last_observed_live_sequence"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("turn_status", ["completed", "interrupted", "failed"])
async def test_turn_terminal_still_triggers_inspection_but_does_not_replace_runtime_state(
    live_pipeline, turn_status
):
    _, store, adapter, transport = live_pipeline
    await deliver(
        adapter,
        transport,
        "thread/status/changed",
        {"threadId": "thread-1", "status": {"type": "idle"}},
    )
    before = await store.get_session(adapter.session.id)
    await deliver(
        adapter,
        transport,
        "turn/completed",
        {"threadId": "thread-1", "turn": {"id": "turn-1", "status": turn_status}},
    )
    saved = await store.get_session(adapter.session.id)
    assert saved.status == SessionStatus.IDLE
    assert saved.last_activity > before.last_activity
    events = await store.recent_events(adapter.session.id)
    terminal = next(event for event in events if event.event_type == EventType.STOP)
    assert terminal.metadata["turn_status"] == turn_status
    assert (await store.get_event_processing(terminal.event_id))["mode"] == "pipeline"


@pytest.mark.asyncio
async def test_untrusted_metadata_cannot_attest_observer_state(live_pipeline):
    pipeline, store, adapter, _ = live_pipeline
    event = HarnessEvent(
        event_id="forged-observer-state",
        ts=datetime.now(UTC),
        harness_type=adapter.session.harness_type,
        session_id=adapter.session.id,
        event_type=EventType.STATUS,
        metadata={"pex_observer_snapshot": {"status": "idle"}},
    )
    with pytest.raises(ValueError, match="internal ingestion"):
        await pipeline.ingest_event(event, adapter.session)
    with pytest.raises(ValueError, match="current ingestion"):
        await pipeline.ingest_shared_codex_event(event, adapter.session)
    assert await store.get_event(event.event_id) is None


@pytest.mark.asyncio
async def test_batch_status_is_projected_in_record_order_not_future_coordinator_state(
    live_pipeline,
):
    _, store, adapter, transport = live_pipeline
    transport.notifications.extend(
        [
            _notification("turn/started", {"threadId": "thread-1", "turn": {"id": "t-batch"}}),
            _notification(
                "turn/completed",
                {"threadId": "thread-1", "turn": {"id": "t-batch", "status": "completed"}},
            ),
            _notification(
                "thread/status/changed", {"threadId": "thread-1", "status": {"type": "idle"}}
            ),
        ]
    )

    async def wait():
        while adapter.last_ingested_sequence < 3:
            await asyncio.sleep(0.005)

    await asyncio.wait_for(wait(), timeout=5)
    events = await store.recent_events(adapter.session.id)
    terminal = next(event for event in events if event.event_type == EventType.STOP)
    snapshot = terminal.metadata["pex_observer_snapshot"]
    assert snapshot["status"] == "working"
    saved = await store.get_session(adapter.session.id)
    assert saved.status == SessionStatus.IDLE
    assert saved.last_activity.isoformat() == snapshot["last_activity"]


@pytest.mark.asyncio
@pytest.mark.parametrize("live_pipeline", [None], indirect=True)
async def test_status_does_not_invent_first_worker_activity(live_pipeline):
    _, store, adapter, transport = live_pipeline
    # A newly attached observer can truthfully lack any observed worker work.
    before = await store.get_session(adapter.session.id)
    assert before.last_activity is None
    await deliver(
        adapter,
        transport,
        "thread/status/changed",
        {"threadId": "thread-1", "status": {"type": "idle"}},
    )
    saved = await store.get_session(adapter.session.id)
    assert adapter.session.last_activity is None
    assert saved.last_activity == before.last_activity
