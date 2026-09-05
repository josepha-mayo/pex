"""Continuity loss through the real coordinator, adapter, Pipeline and Store.

Only the vendor is faked; these are not installed-worker or model benchmarks.
"""

import asyncio

import pex_bridge.adapters.codex_shared_adapter as adapter_module
import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.enums import EventType, SessionStatus
from test_codex_subscription import _notification, _subscribed


@pytest.fixture
async def retained_pipeline(tmp_path, monkeypatch):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    store = Store(tmp_path / "retention.sqlite")
    await store.connect()
    registry = AdapterRegistry()
    registry.bind("codex", adapter)
    pipeline = Pipeline(
        store, registry, EventBus(), Settings.for_test(home=tmp_path, require_auth=False)
    )
    binding = await store.project_binding_for_authority(adapter.session.project_id)
    await store.publish_observer_session(
        adapter.session, expected_control_revision=None, expected_project_binding=binding
    )

    async def forbidden(*args, **kwargs):
        pytest.fail("retained observations must not invoke semantic planning or worker effects")

    monkeypatch.setattr(pipeline, "_build_and_commit_event_plan", forbidden)
    monkeypatch.setattr(pipeline, "_maybe_auto_handoff", forbidden)
    try:
        yield pipeline, store, adapter, transport, registry
    finally:
        if adapter._pump_task is not None:
            adapter._pump_task.cancel()
            await asyncio.gather(adapter._pump_task, return_exceptions=True)
        await transport.close()
        await pipeline.close_presentations()
        await store.close()


def start(pipeline, adapter, **kwargs):
    # Also runs against the baseline, so the reproduction fails on lost rows,
    # not on a missing method or an unexpected callback keyword.
    if hasattr(pipeline, "retain_shared_codex_observations"):
        kwargs.setdefault("retention_ingest", pipeline.retain_shared_codex_observations)
    kwargs.setdefault("lifecycle_ingest", pipeline.ingest_observer_lifecycle)
    return adapter.start_pipeline_pump(pipeline.ingest_shared_codex_event, **kwargs)


def prefix(*, user=False, terminal=False):
    records = [
        _notification("turn/started", {"threadId": "thread-1", "turn": {"id": "retained-turn"}}),
        _notification(
            "item/completed",
            {
                "threadId": "thread-1",
                "turnId": "retained-turn",
                "item": (
                    {
                        "id": "retained-item",
                        "type": "userMessage",
                        "content": [
                            {"type": "text", "text": "Keep the exact original requirement"}
                        ],
                    }
                    if user
                    else {"id": "retained-item", "type": "agentMessage", "text": "Observed work"}
                ),
            },
        ),
    ]
    if terminal:
        records.append(
            _notification(
                "turn/completed",
                {
                    "threadId": "thread-1",
                    "turn": {"id": "retained-turn", "status": "completed"},
                },
            )
        )
    return records


def closed():
    return _notification("thread/closed", {"threadId": "thread-1"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "suffix",
    [
        closed(),
        _notification("turn/completed", {"threadId": "thread-1", "turn": {}}),
        _notification(
            "thread/status/changed",
            {
                "threadId": "thread-1",
                "status": {"type": "active", "activeFlags": "malformed"},
            },
        ),
        _notification("turn/started", {"threadId": "foreign", "turn": {"id": "foreign-turn"}}),
    ],
)
async def test_valid_prefix_survives_bad_suffix_in_real_store(retained_pipeline, suffix):
    pipeline, store, adapter, transport, _ = retained_pipeline
    transport.notifications.extend([*prefix(), suffix, *prefix(user=True)])
    await asyncio.wait_for(start(pipeline, adapter), timeout=8)
    events = await store.recent_events(adapter.session.id)
    observed = sorted(
        (
            event
            for event in events
            if event.metadata.get("source") == "codex_shared_live_notification"
        ),
        key=lambda event: event.metadata["ingress_sequence"],
    )
    assert len(observed) == 2
    assert [event.metadata["ingress_sequence"] for event in observed] == [1, 2]
    assert observed[1].message_delta == "Observed work"
    for event in observed:
        assert (await store.get_event_processing(event.event_id))["mode"] == "record_only"
    assert await store.list_interventions(adapter.session.id) == []
    session = await store.get_session(adapter.session.id)
    assert session.status == SessionStatus.DETACHED
    coverage = session.metadata["observation_coverage"]
    assert coverage["last_observed_live_sequence"] == 2
    assert coverage["last_ingested_live_sequence"] == 2
    assert coverage["pending_normalized_events"] == 0
    assert coverage["raw_stream_complete"] is False
    assert coverage["unobserved_event_count"] is None


@pytest.mark.asyncio
async def test_retained_human_input_and_completion_never_plan(retained_pipeline):
    pipeline, store, adapter, transport, _ = retained_pipeline
    transport.notifications.extend([*prefix(user=True, terminal=True), closed()])
    await asyncio.wait_for(start(pipeline, adapter), timeout=8)
    events = await store.recent_events(adapter.session.id)
    prompt = next(event for event in events if event.event_type == EventType.USER_PROMPT)
    terminal = next(event for event in events if event.event_type == EventType.STOP)
    assert prompt.message_delta == "Keep the exact original requirement"
    for event in (prompt, terminal):
        assert (await store.get_event_processing(event.event_id))["mode"] == "record_only"
    assert await store.list_interventions(adapter.session.id) == []


@pytest.mark.asyncio
async def test_store_retry_reuses_original_observation_receipts(retained_pipeline, monkeypatch):
    pipeline, store, adapter, transport, _ = retained_pipeline
    original = store.retain_observer_events
    attempts = []

    async def transient(events, session, **kwargs):
        attempts.append([event.model_dump(mode="json") for event in events])
        if len(attempts) == 1:
            raise RuntimeError("temporary fixture failure")
        return await original(events, session, **kwargs)

    monkeypatch.setattr(store, "retain_observer_events", transient)
    transport.notifications.extend([*prefix(), closed()])
    await asyncio.wait_for(start(pipeline, adapter), timeout=8)
    assert len(attempts) == 2
    assert attempts[0] == attempts[1]
    assert adapter._retention_state == "retained"
    assert adapter._retained_count == 2
    assert len(await store.recent_events(adapter.session.id)) == 3


@pytest.mark.asyncio
async def test_failed_retention_preserves_pending_count_not_durable_success(
    retained_pipeline, monkeypatch
):
    pipeline, store, adapter, transport, _ = retained_pipeline

    async def unavailable(*args, **kwargs):
        raise RuntimeError("fixture retention storage unavailable")

    monkeypatch.setattr(store, "retain_observer_events", unavailable)
    monkeypatch.setattr(adapter_module, "RETENTION_INGEST_TIMEOUT_SECONDS", 0.15)
    transport.notifications.extend([*prefix(), closed()])
    await asyncio.wait_for(start(pipeline, adapter), timeout=8)
    session = await store.get_session(adapter.session.id)
    coverage = session.metadata["observation_coverage"]
    assert coverage["disconnect_retention_state"] == "failed"
    assert coverage["pending_normalized_events"] == 2
    assert coverage["last_observed_live_sequence"] == 2
    assert coverage["last_ingested_live_sequence"] == 0
    assert coverage["retained_after_disconnect_count"] == 0
    assert len(adapter._undelivered) == 2
    assert len(await store.recent_events(adapter.session.id)) == 1  # gap receipt only


@pytest.mark.asyncio
async def test_cancel_with_full_queue_retains_not_yet_enqueued_tail(retained_pipeline, monkeypatch):
    pipeline, store, adapter, transport, _ = retained_pipeline
    entered = asyncio.Event()

    async def blocked(*args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(pipeline, "ingest_shared_codex_event", blocked)
    transport.notifications.extend(
        _notification("turn/started", {"threadId": "thread-1", "turn": {"id": f"q-{i}"}})
        for i in range(300)
    )
    task = start(pipeline, adapter)
    await asyncio.wait_for(entered.wait(), timeout=5)
    assert len(adapter._undelivered) == 300
    assert adapter._pending.qsize() <= adapter_module.MAX_PENDING_EVENTS
    task.cancel()
    await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=15)
    events = await store.recent_events(adapter.session.id, limit=400)
    assert len(events) == 301
    assert adapter._retained_count == 300
    assert adapter.last_ingested_sequence == 300
    assert adapter._coverage("disconnected")["pending_normalized_events"] == 0
    assert not adapter._pending.qsize()
    assert await store.list_interventions(adapter.session.id) == []


@pytest.mark.asyncio
async def test_repeated_cancellation_does_not_abandon_retention(retained_pipeline):
    pipeline, store, adapter, transport, _ = retained_pipeline
    entered, release = asyncio.Event(), asyncio.Event()

    async def retain(observations, session):
        entered.set()
        await release.wait()
        await pipeline.retain_shared_codex_observations(observations, session)

    transport.notifications.extend([*prefix(), closed()])
    task = start(pipeline, adapter, retention_ingest=retain)
    await asyncio.wait_for(entered.wait(), timeout=5)
    for _ in range(3):
        task.cancel()
        await asyncio.sleep(0)
    assert not adapter._cleanup_task.done()
    release.set()
    await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=8)
    assert adapter._cleanup_task.done()
    assert adapter._retained_count == 2
    assert len(await store.recent_events(adapter.session.id)) == 3


@pytest.mark.asyncio
async def test_commit_then_cancel_does_not_rebind_or_downgrade_existing_event(
    retained_pipeline, monkeypatch
):
    pipeline, store, adapter, transport, _ = retained_pipeline
    entered = asyncio.Event()
    accepted = []

    async def after_acceptance(event_id):
        accepted.append(await store.get_event(event_id))
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(pipeline, "_drain_event_and_followups", after_acceptance)
    transport.notifications.extend(prefix())
    task = start(pipeline, adapter)
    await asyncio.wait_for(entered.wait(), timeout=5)
    event = accepted[0]
    processing = await store.get_event_processing(event.event_id)
    transport.notifications.append(closed())
    await asyncio.wait_for(task, timeout=8)
    assert await store.get_event(event.event_id) == event
    assert await store.get_event_processing(event.event_id) == processing
    assert processing["mode"] == "pipeline"
    events = await store.recent_events(adapter.session.id)
    assert len(events) == 3
    second = next(e for e in events if e.metadata.get("ingress_sequence") == 2)
    assert (await store.get_event_processing(second.event_id))["mode"] == "record_only"
    assert adapter._retained_count == 2  # includes idempotently confirmed existing row


@pytest.mark.asyncio
async def test_unwitnessed_retention_cannot_forge_record_only_events(retained_pipeline):
    pipeline, store, adapter, transport, _ = retained_pipeline
    transport.notifications.extend(prefix())
    batch = await adapter.subscription.drain_live()
    observations = adapter._prepare_records(batch.records)
    adapter._invalid = True
    snapshot = adapter.session.model_copy(deep=True)
    snapshot.status = SessionStatus.DETACHED
    with pytest.raises(ValueError, match="stopped ingestion"):
        await pipeline.retain_shared_codex_observations(observations, snapshot)
    assert await store.recent_events(adapter.session.id) == []


@pytest.mark.asyncio
async def test_registry_replacement_during_retention_cannot_project_old_connection(
    retained_pipeline, monkeypatch
):
    from pex_bridge.adapters.codex import CodexAdapter

    pipeline, store, adapter, transport, registry = retained_pipeline
    original = store.project_binding_for_authority
    before = await store.get_session_control_state(adapter.session.id)

    async def replace_while_awaited(project):
        binding = await original(project)
        registry.bind("codex", CodexAdapter())
        return binding

    monkeypatch.setattr(store, "project_binding_for_authority", replace_while_awaited)
    transport.notifications.extend([*prefix(), closed()])
    await asyncio.wait_for(start(pipeline, adapter), timeout=8)
    assert await store.get_session_control_state(adapter.session.id) == before
    assert await store.recent_events(adapter.session.id) == []
    assert adapter._retention_state == "failed"
    assert len(adapter._undelivered) == 2
