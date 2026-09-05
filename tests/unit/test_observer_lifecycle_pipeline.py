from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent
from test_codex_subscription import _notification, _subscribed


@pytest.fixture
async def lifecycle(tmp_path, monkeypatch):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    store = Store(tmp_path / "lifecycle.sqlite")
    await store.connect()
    registry = AdapterRegistry()
    registry.bind("codex", adapter)
    pipeline = Pipeline(
        store, registry, EventBus(), Settings.for_test(home=tmp_path, require_auth=False)
    )
    binding = await store.project_binding_for_authority(adapter.session.project_id)
    canonical = await store.publish_observer_session(
        adapter.session, expected_control_revision=None, expected_project_binding=binding
    )
    adapter.session = canonical
    adapter.sessions[canonical.id] = canonical
    adapter._normalizer.sessions[canonical.id] = canonical

    async def forbidden(*args, **kwargs):
        pytest.fail("local lifecycle must never enter semantic worker planning")

    monkeypatch.setattr(pipeline, "_build_and_commit_event_plan", forbidden)
    monkeypatch.setattr(pipeline, "_maybe_auto_handoff", forbidden)
    try:
        yield pipeline, store, adapter, registry
    finally:
        await transport.close()
        await pipeline.close_presentations()
        await store.close()


async def disconnected(adapter):
    adapter._invalid = True
    await adapter.transport.close()
    adapter.session.status = SessionStatus.DETACHED
    adapter.session.capabilities = (await adapter.probe()).model_dump(mode="json")
    coverage = adapter._coverage("disconnected", reason="fixture_disconnect")
    adapter.session.metadata["observation_coverage"] = coverage
    event = HarnessEvent(
        event_id=f"codex-shared-disconnected:{adapter._subscription_id}",
        ts=datetime.now(UTC),
        harness_type=HarnessType.CODEX,
        session_id=adapter.session.id,
        project_id=adapter.session.project_id,
        event_type=EventType.STATUS,
        metadata={
            "source": "pex_observer_lifecycle",
            "timestamp_kind": "pex_receipt_time",
            "subscription_id": adapter._subscription_id,
            "observation_coverage": coverage,
            "worker_stopped": False,
            "delivery_proven": False,
        },
    )
    return event, adapter.session.model_copy(deep=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("has_activity", [False, True])
async def test_disconnect_is_atomic_record_only_without_new_worker_activity(
    lifecycle, has_activity
):
    pipeline, store, adapter, _ = lifecycle
    activity = datetime.now(UTC) - timedelta(hours=1) if has_activity else None
    adapter.session.last_activity = activity
    await store.upsert_session(adapter.session)
    event, snapshot = await disconnected(adapter)
    await pipeline.ingest_observer_lifecycle(event, snapshot)
    saved = await store.get_session(snapshot.id)
    assert saved.status == SessionStatus.DETACHED
    assert saved.last_activity == activity
    assert saved.metadata["observation_coverage"]["state"] == "disconnected"
    assert saved.capabilities["observe_messages"] is False
    assert await store.get_event(event.event_id) is not None
    assert (await store.get_event_processing(event.event_id))["mode"] == "record_only"
    assert await store.list_interventions(snapshot.id) == []


@pytest.mark.asyncio
async def test_lifecycle_preserves_newer_durable_goal_and_pause(lifecycle, monkeypatch):
    pipeline, store, adapter, _ = lifecycle
    publications = []
    monkeypatch.setattr(
        pipeline,
        "_schedule_committed_publication",
        lambda kind, payload: publications.append((kind, payload)),
    )
    event, stale = await disconnected(adapter)
    now = datetime.now(UTC)
    goal = Goal(
        id="lifecycle-goal",
        project_id=stale.project_id,
        title="Review",
        objective="Preserve the human goal and pause",
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    await store.attach_session_goal(stale.id, goal.id, expected_goal_id=None)
    control = await store.get_session_control_state(stale.id)
    await store.set_session_supervision_paused(
        stale.id, paused=True, expected_control_revision=control["control_revision"]
    )
    durable = await store.get_session(stale.id)
    assert durable.goal_id == goal.id
    assert durable.supervision_paused
    await pipeline.ingest_observer_lifecycle(event, stale)
    saved = await store.get_session(stale.id)
    assert saved.goal_id == goal.id
    assert saved.supervision_paused
    assert saved.status == SessionStatus.DETACHED
    assert saved.last_activity is None
    assert publications[0][0] == "event"
    assert publications[0][1]["goal_id"] == goal.id
    assert publications[0][1] == (await store.get_event(event.event_id)).model_dump(mode="json")


@pytest.mark.asyncio
async def test_actual_adapter_disconnect_uses_local_lifecycle_callback(lifecycle):
    pipeline, store, adapter, _ = lifecycle
    adapter.transport.notifications.append(_notification("thread/closed", {"threadId": "thread-1"}))
    await asyncio.wait_for(
        adapter.start_pipeline_pump(
            pipeline.ingest_event,
            lifecycle_ingest=pipeline.ingest_observer_lifecycle,
        ),
        timeout=5,
    )
    saved = await store.get_session(adapter.session.id)
    assert saved.status == SessionStatus.DETACHED
    assert saved.last_activity is None
    assert saved.metadata["observation_coverage"]["state"] == "disconnected"
    assert (
        await store.get_event_processing(f"codex-shared-disconnected:{adapter._subscription_id}")
    )["mode"] == "record_only"


@pytest.mark.asyncio
async def test_old_adapter_lifecycle_cannot_overwrite_new_registry_connection(lifecycle, tmp_path):
    pipeline, store, old, registry = lifecycle
    event, snapshot = await disconnected(old)
    coordinator, transport = await _subscribed(tmp_path)
    replacement = CodexSharedAdapter(coordinator)
    registry.bind("codex", replacement)
    try:
        with pytest.raises(ValueError, match="current connection"):
            await pipeline.ingest_observer_lifecycle(event, snapshot)
        assert await store.get_event(event.event_id) is None
        assert (await store.get_session(snapshot.id)).metadata["observation_coverage"][
            "state"
        ] == "observing"
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_stale_durable_subscription_is_not_overwritten(lifecycle):
    pipeline, store, adapter, _ = lifecycle
    event, snapshot = await disconnected(adapter)
    current = await store.get_session(snapshot.id)
    current.metadata["subscription_receipt"]["authorization_id"] = "new-subscription"
    await store.upsert_session(current)
    with pytest.raises(ValueError, match="durable connection changed"):
        await pipeline.ingest_observer_lifecycle(event, snapshot)
    assert await store.get_event(event.event_id) is None


@pytest.mark.asyncio
async def test_connected_adapter_cannot_publish_disconnect(lifecycle):
    pipeline, store, adapter, _ = lifecycle
    # Forge only the snapshot. The adapter itself is still connected.
    snapshot = adapter.session.model_copy(deep=True)
    snapshot.status = SessionStatus.DETACHED
    coverage = adapter._coverage("disconnected")
    snapshot.metadata["observation_coverage"] = coverage
    event = HarnessEvent(
        event_id="forged-lifecycle",
        ts=datetime.now(UTC),
        harness_type=HarnessType.CODEX,
        session_id=snapshot.id,
        event_type=EventType.STATUS,
        metadata={
            "source": "pex_observer_lifecycle",
            "worker_stopped": False,
            "subscription_id": adapter._subscription_id,
            "observation_coverage": coverage,
        },
    )
    with pytest.raises(ValueError, match="current connection"):
        await pipeline.ingest_observer_lifecycle(event, snapshot)
    assert await store.get_event(event.event_id) is None
