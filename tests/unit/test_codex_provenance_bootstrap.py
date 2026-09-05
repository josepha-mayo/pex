"""Read-only review regressions using fake subscriptions, never native workers."""

import asyncio

import pytest
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.adapters.codex_subscription import CodexObservationInterrupted
from pex_bridge.codex_correction import CORRECTION_SCHEMA, canonical
from pex_bridge.codex_input_provenance import CodexInputProvenance
from pex_protocol.enums import EventType
from test_codex_correction_store import attempt, enable_corrections, prepare
from test_codex_shared_adapter import eventually
from test_codex_subscription import _notification, _subscribed
from test_workspace_continuity_pipeline import bound_pipeline as bound_pipeline


def raw_user():
    return {
        "id": "echo-item", "type": "userMessage", "clientId": "known-correlation",
        "content": [{"type": "text", "text": "Continue exact task", "text_elements": []}],
    }


def records(adapter):
    return (canonical({
        "correction": {
            "schema": CORRECTION_SCHEMA, "session_id": adapter.session.id,
            "thread_id": adapter.session.vendor_session_id, "effect_id": "attempted-effect",
            "client_message_id": "known-correlation", "content": raw_user()["content"],
        },
        "effect_state": "delivery_uncertain", "effect_version": 2,
    }),)


def notification():
    return _notification("item/completed", {
        "threadId": "thread-1", "turnId": "turn-1", "item": raw_user(),
    })


async def ignore(*args):
    pass


async def test_no_initial_normalization_before_owned_provenance_bootstrap(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    transport.notifications.append(notification())
    adapter._initial = (await coordinator.drain_live()).records
    entered, release = asyncio.Event(), asyncio.Event()
    ingested = []

    async def load(session):
        entered.set()
        await release.wait()
        return records(adapter)

    async def ingest(event, session):
        ingested.append(event)

    task = adapter.start_pipeline_pump(ingest, provenance_loader=load, lifecycle_ingest=ignore)
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        assert not adapter._undelivered and not adapter._correction_items
        assert not ingested and adapter.input_revision == 0
        release.set()
        await eventually(lambda: bool(ingested))
        assert ingested[0].event_type == EventType.STATUS
        assert "pex_correction_observation" in ingested[0].metadata
        assert adapter.input_revision == 0
        assert not adapter._correction_items
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert transport.closed


async def test_bootstrap_cancellation_joins_loader_before_closing(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    transport.notifications.append(notification())
    entered, settled = asyncio.Event(), asyncio.Event()
    ingested = []

    async def load(session):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            settled.set()

    async def ingest(event, session):
        ingested.append(event)

    task = adapter.start_pipeline_pump(ingest, provenance_loader=load, lifecycle_ingest=ignore)
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    result = await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=2)
    assert isinstance(result[0], asyncio.CancelledError)
    assert settled.is_set() and transport.closed
    assert not ingested and not adapter._undelivered


@pytest.mark.parametrize("direct", [False, True])
async def test_failed_bootstrap_never_normalizes_interrupted_batch_as_human(tmp_path, direct):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    entered, release = asyncio.Event(), asyncio.Event()
    retained = []

    async def load(session):
        entered.set()
        await release.wait()
        raise ValueError("fixture attribution coverage unavailable")

    async def retain(observations, session):
        retained.extend(event for event, _ in observations)

    if direct:
        task = asyncio.create_task(adapter.pump_into_pipeline(
            ignore, provenance_loader=load, lifecycle_ingest=ignore, retention_ingest=retain,
        ))
    else:
        task = adapter.start_pipeline_pump(
            ignore, provenance_loader=load, lifecycle_ingest=ignore, retention_ingest=retain,
        )
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        # Exercise the real coordinator's interrupted-prefix receipt while the
        # owned receiver is waiting for its attribution dependency.
        transport.notifications.extend([
            notification(), _notification("thread/closed", {"threadId": "thread-1"}),
        ])
        with pytest.raises(CodexObservationInterrupted):
            await coordinator.drain_live()
        assert len(coordinator.interrupted_batch.records) == 1
        release.set()
        await asyncio.wait_for(task, timeout=2)
        assert not retained
        assert adapter.input_revision == 0
        assert adapter._input_provenance is None
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert transport.closed


async def test_exact_echo_sidecar_survives_transient_ingestion_until_retained(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    entered = asyncio.Event()
    retained = []

    async def load(session):
        return records(adapter)

    async def ingest(event, session):
        entered.set()
        assert event.event_id in adapter._correction_items
        raise RuntimeError("fixture Store unavailable")

    async def retain(observations, session):
        for event, _ in observations:
            assert event.event_id in adapter._correction_items
            retained.append(event)

    task = adapter.start_pipeline_pump(
        ingest, provenance_loader=load, lifecycle_ingest=ignore, retention_ingest=retain,
    )
    transport.notifications.append(notification())
    await asyncio.wait_for(entered.wait(), timeout=2)
    transport.notifications.append(_notification("thread/closed", {"threadId": "thread-1"}))
    await asyncio.wait_for(task, timeout=2)
    assert len(retained) == 1 and retained[0].event_type == EventType.STATUS
    assert adapter._retention_state == "retained"
    assert not adapter._correction_items and not adapter._undelivered


async def test_durable_duplicate_after_fresh_registry_cannot_retry_or_retain_as_exact(
    bound_pipeline, monkeypatch,
):
    """Actual Store+consumer; reset only the transient map as a fresh adapter would."""
    bound = bound_pipeline
    store, adapter = bound.store, bound.adapter
    session = await store.get_session(adapter.session.id)
    await enable_corrections(store, session)
    session = await store.get_session(session.id)
    prepared = await prepare((store, session, None))
    await attempt((store, session, None), prepared)
    loaded = await store.list_codex_correction_attributions(session)
    adapter._input_provenance = CodexInputProvenance.from_store_records(
        loaded, session_id=session.id, thread_id=session.vendor_session_id,
    )
    correction = prepared[2]["codex_correction"]
    first_committed = asyncio.Event()
    errors = []
    original_record = store.record_codex_correction_observation

    async def record_spy(event, snapshot, **kwargs):
        try:
            result = await original_record(event, snapshot, **kwargs)
        except ValueError as exc:
            errors.append(exc)
            raise
        else:
            first_committed.set()
            return result

    monkeypatch.setattr(store, "record_codex_correction_observation", record_spy)

    def echo(item_id):
        return _notification("item/completed", {
            "threadId": session.vendor_session_id, "turnId": "turn-1",
            "item": {
                "type": "userMessage", "id": item_id,
                "clientId": correction["client_message_id"], "content": correction["content"],
            },
        })

    bound.transport.notifications.append(echo("first-vendor-item"))
    await asyncio.wait_for(first_committed.wait(), timeout=2)
    await eventually(lambda: not adapter._undelivered)
    # Store-loaded contract survives reattachment, but the current loader does
    # not include previously observed vendor tuple identity. Simulate exactly
    # that empty new-incarnation cache, not a forged/changed durable receipt.
    adapter._correction_vendor_items.clear()
    adapter._input_provenance = CodexInputProvenance.from_store_records(
        await store.list_codex_correction_attributions(session),
        session_id=session.id, thread_id=session.vendor_session_id,
    )
    bound.transport.notifications.append(echo("second-vendor-item"))
    await eventually(lambda: bound.task.done() or len(errors) >= 2)
    assert bound.task.done(), "permanent duplicate correction refusal was retried by consumer"
    assert len(errors) == 1
    assert adapter._retention_state == "failed"
    assert not bound.supervisor_calls
    cursor = await store.db.execute(
        "SELECT COUNT(*) AS total FROM events WHERE json_extract("
        "json, '$.metadata.pex_correction_observation.effect_id')=?",
        (correction["effect_id"],),
    )
    assert (await cursor.fetchone())["total"] == 1
