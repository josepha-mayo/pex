"""Retain actual normalized observer records with SQLite, never a live worker."""

from datetime import UTC, datetime

import pytest
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.store import Store
from pex_protocol.enums import EventType
from pex_protocol.goal import Goal
from test_codex_subscription import _notification, _subscribed


@pytest.fixture
async def retention(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    store = Store(tmp_path / "retention.sqlite")
    await store.connect()
    binding = await store.project_binding_for_authority(adapter.session.project_id)
    await store.publish_observer_session(
        adapter.session, expected_control_revision=None, expected_project_binding=binding
    )
    original = adapter.session.model_copy(deep=True)
    transport.notifications.extend(
        [
            _notification(
                "item/completed",
                {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": {
                        "id": "user-1",
                        "type": "userMessage",
                        "content": [
                            {
                                "type": "text",
                                "text": "Keep the human request in the observed prefix.",
                            },
                        ],
                    },
                },
            ),
            _notification(
                "turn/completed",
                {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "completed"},
                },
            ),
        ]
    )
    events = []
    for record in (await coordinator.drain_live()).records:
        event = adapter._event(record)
        snapshot = adapter.session
        event.metadata["pex_observer_snapshot"] = {
            "schema": "pex.codex-live-observation.v1",
            "subscription_receipt": dict(snapshot.metadata["subscription_receipt"]),
            "status": snapshot.status.value,
            "last_activity": snapshot.last_activity.isoformat() if snapshot.last_activity else None,
            "observation_coverage": dict(snapshot.metadata["observation_coverage"]),
        }
        events.append(event)
    try:
        yield store, original, tuple(events), binding
    finally:
        await transport.close()
        await store.close()


async def retain(fixture, events=None, session=None, binding=None):
    store, original, records, expected = fixture
    return await store.retain_observer_events(
        records if events is None else events,
        original if session is None else session,
        expected_project_binding=expected if binding is None else binding,
    )


@pytest.mark.asyncio
async def test_valid_prefix_retention_is_record_only_and_has_no_session_projection(retention):
    store, session, events, _ = retention
    before = await store.get_session_control_state(session.id)
    saved = await retain(retention)
    assert [e.event_type for e in saved] == [EventType.USER_PROMPT, EventType.STOP]
    assert [e.event_id for e in saved] == [e.event_id for e in events]
    assert await store.get_session_control_state(session.id) == before
    for event in events:
        assert await store.get_event(event.event_id) == event
        processing = await store.get_event_processing(event.event_id)
        assert processing["mode"] == "record_only"
        assert processing["state"] == "record_only_complete"
        assert processing["plan"] is None
    assert await store.list_interventions(session.id) == []


@pytest.mark.asyncio
async def test_exact_retry_preserves_canonical_records_and_acceptance_order(retention):
    store, session, events, _ = retention
    first = await retain(retention)
    processing = [await store.get_event_processing(e.event_id) for e in events]
    assert await retain(retention) == first
    assert [await store.get_event_processing(e.event_id) for e in events] == processing
    assert processing[0]["accept_seq"] < processing[1]["accept_seq"]
    assert (await store.get_session(session.id)).last_activity is None


@pytest.mark.asyncio
async def test_collision_rolls_back_earlier_new_prefix_insert(retention):
    store, _, events, _ = retention
    await retain(retention, events=(events[1],))
    conflict = events[1].model_copy(deep=True)
    conflict.error = "different content for the same stable event"
    with pytest.raises(ValueError, match="collision"):
        await retain(retention, events=(events[0], conflict))
    assert await store.get_event(events[0].event_id) is None
    assert await store.get_event(events[1].event_id) == events[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["receipt", "cwd", "binding", "event_project"])
async def test_stale_target_cannot_retain_any_records(retention, tmp_path, change):
    store, session, events, binding = retention
    if change in {"receipt", "cwd"}:
        current = await store.get_session(session.id)
        if change == "receipt":
            current.metadata["subscription_receipt"]["authorization_id"] = "another-subscription"
        else:
            current.cwd = str(tmp_path / "another-workspace")
        await store.upsert_session(current)
    elif change == "binding":
        binding = await store.project_binding_for_authority("another-project")
    else:
        altered = events[1].model_copy(deep=True)
        altered.project_id = "another-project"
        events = (events[0], altered)
    before = await store.get_session_control_state(session.id)
    with pytest.raises(ValueError):
        await retain(retention, events=events, binding=binding)
    assert await store.get_session_control_state(session.id) == before
    assert all([await store.get_event(event.event_id) is None for event in events])


@pytest.mark.asyncio
async def test_new_records_bind_current_goal_without_changing_human_controls(retention):
    store, session, events, _ = retention
    now = datetime.now(UTC)
    goal = Goal(
        id="retention-goal",
        project_id=session.project_id,
        title="Retention",
        objective="Preserve the current human goal",
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    await store.attach_session_goal(session.id, goal.id, expected_goal_id=None)
    control = await store.get_session_control_state(session.id)
    await store.set_session_supervision_paused(
        session.id, paused=True, expected_control_revision=control["control_revision"]
    )
    before = await store.get_session_control_state(session.id)
    saved = await retain(retention)
    assert all(event.goal_id == goal.id for event in saved)
    assert all(event.goal_id is None for event in events)
    assert await store.get_session_control_state(session.id) == before
    assert await retain(retention) == saved


@pytest.mark.asyncio
async def test_existing_pipeline_acceptance_is_not_rebound_or_downgraded(retention):
    store, session, events, _ = retention
    accepted = await store.accept_pipeline_event(events[0], session_snapshot=session)
    assert accepted["processing"]["mode"] == "pipeline"
    before = await store.get_event_processing(events[0].event_id)
    now = datetime.now(UTC)
    goal = Goal(
        id="later-goal",
        project_id=session.project_id,
        title="Later goal",
        objective="A later human decision",
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    await store.attach_session_goal(session.id, goal.id, expected_goal_id=None)
    saved = await retain(retention)
    assert saved[0].goal_id is None
    assert saved[1].goal_id == goal.id
    assert await store.get_event_processing(events[0].event_id) == before
    assert (await store.get_event_processing(events[1].event_id))["mode"] == "record_only"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "order",
        "duplicate",
        "sequence_bool",
        "snapshot_extra",
        "snapshot_receipt",
        "status",
        "activity",
        "coverage",
        "endpoint",
        "harness",
        "source",
        "coverage_extension",
        "coverage_unknown",
        "delivery_authority",
    ],
)
async def test_invalid_frozen_observations_abort_the_batch(retention, change):
    store, _, events, _ = retention
    invalid = events[1].model_copy(deep=True)
    marker = invalid.metadata["pex_observer_snapshot"]
    if change == "order":
        candidates = tuple(reversed(events))
    elif change == "duplicate":
        candidates = (events[0], events[0])
    else:
        if change == "sequence_bool":
            invalid.metadata["ingress_sequence"] = True
        elif change == "snapshot_extra":
            marker["invented_authority"] = True
        elif change == "snapshot_receipt":
            marker["subscription_receipt"]["authorization_id"] = "changed"
        elif change == "status":
            marker["status"] = "invented"
        elif change == "activity":
            marker["last_activity"] = "2026-09-05T00:00:00"
        elif change == "coverage":
            marker["observation_coverage"]["raw_stream_complete"] = True
        elif change == "endpoint":
            invalid.metadata["endpoint_identity"] = "wrong-endpoint"
        elif change == "harness":
            invalid.session_id = "codex:another-thread"
        elif change == "source":
            invalid.metadata["source"] = "history"
        elif change == "coverage_extension":
            marker["observation_coverage"]["retained_after_disconnect_count"] = True
        elif change == "coverage_unknown":
            marker["observation_coverage"]["unknown_privilege"] = True
        elif change == "delivery_authority":
            invalid.metadata["delivery_proven"] = True
        candidates = (events[0], invalid)
    with pytest.raises(ValueError):
        await retain(retention, events=candidates)
    assert all([await store.get_event(event.event_id) is None for event in events])


@pytest.mark.asyncio
async def test_retention_bounds_are_fail_closed(retention):
    store, _, events, _ = retention
    for candidates in ((), list(events), (events[0],) * 2049):
        with pytest.raises(ValueError, match="1 to 2048"):
            await retain(retention, events=candidates)
    oversized = events[0].model_copy(deep=True)
    oversized.message_delta = "x" * 1_048_576
    with pytest.raises(ValueError, match="size bound"):
        await retain(retention, events=(oversized,))
    assert await store.get_event(events[0].event_id) is None


@pytest.mark.asyncio
async def test_retention_aggregate_byte_bound_prevents_any_insert(retention):
    store, _, events, _ = retention
    # Reuse one immutable string: test the serialized bound without retaining
    # 33 independent megabyte payloads in the test process.
    payload = "x" * (1_048_576 - 8_192)
    candidates = []
    for index in range(33):
        event = events[0].model_copy(deep=True)
        event.event_id = f"bounded-retention-{index}"
        event.metadata["ingress_sequence"] = index + 1
        event.metadata["pex_observer_snapshot"]["observation_coverage"][
            "last_observed_live_sequence"
        ] = index + 1
        event.message_delta = payload
        candidates.append(event)
    with pytest.raises(ValueError, match="size bound"):
        await retain(retention, events=tuple(candidates))
    assert await store.get_event(candidates[0].event_id) is None
