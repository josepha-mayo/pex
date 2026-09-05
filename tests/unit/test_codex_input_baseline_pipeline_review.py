"""Independent real Pipeline/Store prefix tests; no model or native worker runs."""

import asyncio
from dataclasses import asdict

import pytest
import test_workspace_continuity_pipeline as continuity_fixture
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.adapters.codex_subscription import (
    CodexExistingThreadSubscription,
    CodexObservationInterrupted,
)
from pex_bridge.codex_input_baseline import CodexInputBaseline
from pex_protocol.enums import EventType
from test_codex_shared_adapter import eventually
from test_codex_subscription import (
    FakeSharedTransport,
    _authorization,
    _inspect,
    _notification,
    _thread_response,
)
from test_workspace_continuity_pipeline import bound_pipeline as bound_pipeline


@pytest.fixture(autouse=True)
def actual_baseline_bootstrap(monkeypatch):
    """Give the existing bound fixture full selected history and its real Store loader."""
    async def subscribed(workspace):
        response = _thread_response(workspace, turns=[{
            "id": "turn-1", "status": "completed", "itemsView": "full", "items": [],
        }])
        transport = FakeSharedTransport(
            [response, response, response], _thread_response(workspace, include_turns=False),
        )
        coordinator = CodexExistingThreadSubscription(transport)
        selected = await _inspect(coordinator, workspace)
        await coordinator.subscribe(selected, _authorization(selected))
        return coordinator, transport

    original_start = CodexSharedAdapter.start_pipeline_pump

    def start(adapter, ingest, **kwargs):
        kwargs["provenance_loader"] = ingest.__self__.store.list_codex_correction_attributions
        return original_start(adapter, ingest, **kwargs)

    monkeypatch.setattr(continuity_fixture, "_subscribed", subscribed)
    monkeypatch.setattr(CodexSharedAdapter, "start_pipeline_pump", start)


def stop():
    return _notification("turn/completed", {
        "threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"},
    })


def human():
    return _notification("item/completed", {
        "threadId": "thread-1", "turnId": "turn-1",
        "item": {"id": "new-human", "type": "userMessage", "clientId": None,
                 "content": [{"type": "text", "text": "New external instruction",
                              "text_elements": []}]},
    })


async def events_settled(bound, count):
    async def wait():
        while True:
            events = [event for event in await bound.store.recent_events(bound.adapter.session.id)
                      if "pex_observer_snapshot" in event.metadata]
            if len(events) >= count:
                states = [
                    await bound.store.get_event_processing(event.event_id) for event in events
                ]
                if all(state and state["state"] in {
                    "complete", "failed", "record_only_complete",
                } for state in states):
                    return sorted(events, key=lambda event: event.metadata["ingress_sequence"])
            await asyncio.sleep(0.01)
    return await asyncio.wait_for(wait(), 10)


def baseline(event):
    return event.metadata["pex_observer_snapshot"]["input_baseline"]


async def test_stop_then_external_input_same_batch_freezes_distinct_prefixes(bound_pipeline):
    bound = bound_pipeline
    await eventually(lambda: bound.adapter._input_baseline is not None)
    before = asdict(bound.adapter._input_baseline.snapshot())
    assert before["complete"] and before["external_count"] == 0
    bound.transport.notifications.extend([stop(), human()])
    events = await events_settled(bound, 2)
    assert events[0].event_type == EventType.STOP
    assert baseline(events[0]) == before
    assert baseline(events[1])["external_count"] == 1
    assert baseline(events[1])["revision"] == 1
    assert baseline(events[0])["digest"] != baseline(events[1])["digest"]
    assert baseline(bound.supervisor_calls[0].event) == before
    await eventually(lambda: not bound.adapter._input_baselines)


async def test_missing_frozen_sidecar_is_rejected_before_store_or_model(bound_pipeline):
    bound = bound_pipeline
    await eventually(lambda: bound.adapter._input_baseline is not None)
    bound.transport.notifications.append(stop())
    records = (await bound.adapter.subscription.drain_live()).records
    ((event, session),) = bound.adapter._prepare_records(records)
    bound.adapter._input_baselines.pop(event.event_id)
    bound.adapter._ingesting_observation = (event, session)
    with pytest.raises(ValueError, match="lacks its frozen input baseline"):
        await bound.pipeline.ingest_shared_codex_event(event, session)
    assert await bound.store.get_event(event.event_id) is None
    assert bound.supervisor_calls == []
    # Leave no manufactured queue ownership for unrelated fixture teardown.
    bound.adapter._ingesting_observation = None
    bound.adapter._undelivered.clear()


async def test_later_input_during_model_await_cannot_mutate_accepted_stop(
    bound_pipeline, monkeypatch,
):
    bound = bound_pipeline
    await eventually(lambda: bound.adapter._input_baseline is not None)
    before = asdict(bound.adapter._input_baseline.snapshot())
    entered, release = asyncio.Event(), asyncio.Event()
    original_decide = bound.pipeline.supervisor.decide
    requests = []

    async def decide(request, *, local_model):
        if request.event.event_type == EventType.STOP:
            requests.append(request.model_copy(deep=True))
            entered.set()
            await release.wait()
        return await original_decide(request, local_model=local_model)

    monkeypatch.setattr(bound.pipeline.supervisor, "decide", decide)
    bound.transport.notifications.append(stop())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        stop_event_id = requests[0].event.event_id
        assert baseline(await bound.store.get_event(stop_event_id)) == before
        bound.transport.notifications.append(human())
        await eventually(lambda: bound.adapter._input_baseline.snapshot().revision == 1)
        current = asdict(bound.adapter._input_baseline.snapshot())
        assert current["digest"] != before["digest"]
        assert asdict(bound.adapter._input_baselines[stop_event_id]) == before
        assert baseline(await bound.store.get_event(stop_event_id)) == before
        assert baseline(requests[0].event) == before
    finally:
        release.set()
    events = await events_settled(bound, 2)
    assert baseline(events[0]) == before


async def test_disconnect_retains_exact_sidecars_not_current_ledger(bound_pipeline, monkeypatch):
    bound = bound_pipeline
    await eventually(lambda: bound.adapter._input_baseline is not None)
    entered = asyncio.Event()

    async def held_before_accept(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(bound.pipeline, "_ingest_event_locked", held_before_accept)
    bound.transport.notifications.extend([stop(), human()])
    await asyncio.wait_for(entered.wait(), 5)
    assert len(bound.adapter._undelivered) == 2
    snapshots = {key: asdict(value) for key, value in bound.adapter._input_baselines.items()}
    assert sorted(value["external_count"] for value in snapshots.values()) == [0, 1]
    bound.task.cancel()
    await asyncio.wait_for(asyncio.gather(bound.task, return_exceptions=True), 5)
    assert bound.adapter._retention_state == "retained"
    events = await events_settled(bound, 2)
    assert {event.event_id: baseline(event) for event in events} == snapshots
    for event in events:
        processing = await bound.store.get_event_processing(event.event_id)
        assert processing["state"] == "record_only_complete"
    assert not bound.adapter._input_baselines and not bound.adapter._undelivered
    assert bound.supervisor_calls == []


@pytest.fixture
def failed_ledger_bootstrap(monkeypatch):
    joining, release = asyncio.Event(), asyncio.Event()

    def fail_ledger(*args, **kwargs):
        raise ValueError("fixture selected ledger unavailable")

    async def held_consumer(adapter, ingest):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Deterministic cleanup boundary, not a replacement normalization
            # or retention implementation. The actual coordinator drains below.
            joining.set()
            await release.wait()
            raise

    monkeypatch.setattr(CodexInputBaseline, "from_selected", fail_ledger)
    monkeypatch.setattr(CodexSharedAdapter, "_consume", held_consumer)
    return joining, release


async def test_failed_ledger_after_store_load_never_normalizes_interrupted_prefix(
    failed_ledger_bootstrap, bound_pipeline,
):
    bound = bound_pipeline
    joining, release = failed_ledger_bootstrap
    try:
        await asyncio.wait_for(joining.wait(), 5)
        assert bound.adapter._input_provenance is not None
        assert bound.adapter._input_baseline is None
        assert not bound.adapter._input_bootstrap_complete
        bound.transport.notifications.extend([
            human(), _notification("thread/closed", {"threadId": "thread-1"}),
        ])
        with pytest.raises(CodexObservationInterrupted):
            await bound.adapter.subscription.drain_live()
        assert len(bound.adapter.subscription.interrupted_batch.records) == 1
    finally:
        release.set()
    await asyncio.wait_for(bound.task, 5)
    assert bound.transport.closed
    assert bound.adapter.input_revision == 0
    assert not bound.adapter._undelivered and not bound.adapter._input_baselines
    assert bound.adapter._retention_state == "not_needed"
    assert bound.supervisor_calls == []
    events = await bound.store.recent_events(bound.adapter.session.id)
    assert not any(event.metadata.get("raw_method") == "item/completed" for event in events)
