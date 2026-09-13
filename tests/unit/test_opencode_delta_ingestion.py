from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.http_json import MemoryHttpTransport
from pex_bridge.adapters.opencode_outcomes import OPENCODE_MESSAGE_LINEAGE_KEY
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession


async def _bound_opencode_pipeline(tmp_path):
    store = Store(tmp_path / "opencode-deltas.sqlite")
    await store.connect()
    registry = AdapterRegistry()
    transport = MemoryHttpTransport()
    adapter = registry.opencode
    adapter.attach_transport(transport)
    now = datetime.now(UTC)
    goal = Goal(
        id="goal-opencode-deltas",
        project_id=str(tmp_path),
        title="Retain OpenCode observations",
        objective="Preserve the exact event journal until the worker stops.",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id="opencode:ses_delta",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="ses_delta",
        project_id=str(tmp_path),
        cwd=str(tmp_path),
        goal_id=goal.id,
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    adapter.sessions[session.id] = session
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    pipeline = Pipeline(
        store,
        registry,
        EventBus(),
        Settings.for_test(home=tmp_path, require_auth=False, autonomy="observe"),
        model=None,
    )
    return store, adapter, session, pipeline


def _delta_payload(cwd: str, index: int) -> dict:
    return {
        "id": f"delta-{index}",
        "type": "message.part.delta",
        "properties": {
            "cwd": cwd,
            "info": {"sessionID": "ses_delta", "id": "assistant-turn", "role": "assistant"},
            "delta": f"fragment {index}",
        },
    }


def _completed_assistant_payload(cwd: str) -> dict:
    return {
        "id": "completed-assistant",
        "type": "message.updated",
        "properties": {
            "cwd": cwd,
            "info": {
                "sessionID": "ses_delta",
                "id": "assistant-turn",
                "role": "assistant",
                "parentID": "user-turn",
                "finish": "stop",
                "time": {"created": 1, "completed": 2},
            },
        },
    }


async def test_opencode_deltas_are_durable_record_only_and_do_not_delay_parent_bound_stop(
    tmp_path, monkeypatch
):
    store, adapter, session, pipeline = await _bound_opencode_pipeline(tmp_path)
    probes = 0

    async def probe():
        nonlocal probes
        probes += 1
        return AdapterCapabilities()

    monkeypatch.setattr(adapter, "probe", probe)
    try:
        deltas = [
            adapter.normalize_sse(session, _delta_payload(str(tmp_path), index))
            for index in range(100)
        ]
        assert all(event.event_type == EventType.STATUS for event in deltas)
        assert all(event.metadata == {"sse_type": "message.part.delta"} for event in deltas)

        for event in deltas:
            assert await pipeline.ingest_event(event, session) is None

        assert probes == 0
        for event in deltas:
            saved = await store.get_event(event.event_id)
            processing = await store.get_event_processing(event.event_id)
            assert saved is not None
            assert saved.model_dump(mode="json") == event.model_dump(mode="json")
            assert processing is not None
            assert processing["mode"] == "record_only"
            assert processing["state"] == "record_only_complete"
            assert await store.get_event_effect(event.event_id, "planner") is None

        replay = deltas[0].model_copy(update={"ts": datetime.now(UTC)})
        assert await pipeline.ingest_event(replay, session) is None
        assert probes == 0
        collision = deltas[0].model_copy(update={"message_delta": "different fragment"})
        with pytest.raises(ValueError, match="different content"):
            await pipeline.ingest_event(collision, session)

        stop = adapter.normalize_sse(session, _completed_assistant_payload(str(tmp_path)))
        assert stop.event_type == EventType.STOP
        lineage = stop.metadata[OPENCODE_MESSAGE_LINEAGE_KEY]
        assert lineage["parent_message_id"] == "user-turn"
        assert lineage["stream_contiguous"] is True
        await pipeline.ingest_event(stop, session)
        processing = await store.get_event_processing(stop.event_id)
        saved_stop = await store.get_event(stop.event_id)
        assert probes == 1
        assert processing is not None and processing["mode"] == "pipeline"
        assert processing["state"] == "complete"
        assert saved_stop is not None
        assert saved_stop.metadata[OPENCODE_MESSAGE_LINEAGE_KEY] == lineage
    finally:
        await store.close()


@pytest.mark.parametrize(
    "event",
    [
        HarnessEvent(
            event_id="non-status-delta",
            ts=datetime.now(UTC),
            harness_type=HarnessType.OPENCODE,
            session_id="opencode:ses_delta",
            event_type=EventType.AGENT_RESPONSE,
            phase=EventPhase.AFTER,
            metadata={"sse_type": "message.part.delta"},
        ),
        HarnessEvent(
            event_id="non-delta-status",
            ts=datetime.now(UTC),
            harness_type=HarnessType.OPENCODE,
            session_id="opencode:ses_delta",
            event_type=EventType.STATUS,
            phase=EventPhase.AFTER,
            metadata={"sse_type": "session.status"},
        ),
        HarnessEvent(
            event_id="tool-bearing-delta",
            ts=datetime.now(UTC),
            harness_type=HarnessType.OPENCODE,
            session_id="opencode:ses_delta",
            event_type=EventType.STATUS,
            phase=EventPhase.AFTER,
            tool_name="shell",
            metadata={"sse_type": "message.part.delta"},
        ),
    ],
)
async def test_opencode_progress_observations_take_record_only_path(
    tmp_path, monkeypatch, event
):
    store, _, session, pipeline = await _bound_opencode_pipeline(tmp_path)
    normal: list[str] = []

    async def normal_path(observed, observed_session):
        assert observed_session.id == session.id
        normal.append(observed.event_id)
        return None

    monkeypatch.setattr(pipeline, "_accept_and_resume_event", normal_path)
    try:
        assert await pipeline._ingest_event_locked(event, session) is None
        assert normal == []
        assert await store.get_event(event.event_id) is not None
        processing = await store.get_event_processing(event.event_id)
        assert processing is not None
        assert processing["mode"] == "record_only"
        assert processing["state"] == "record_only_complete"
        # Durable progress must remain visible through the same immutable
        # goal/project boundary used by Home and Inspector, without planning.
        visible = await store.recent_events_for_authority(
            session.id,
            goal_id=session.goal_id,
            project_id=session.project_id,
            harness_type=session.harness_type,
        )
        assert event.event_id in {item.event_id for item in visible}
    finally:
        await store.close()


async def test_fresh_progress_replaces_old_prompt_in_authoritative_pet_snapshot(tmp_path):
    store, _, session, pipeline = await _bound_opencode_pipeline(tmp_path)
    old = HarnessEvent(
        event_id="old-correction", ts=datetime.now(UTC) - timedelta(seconds=10),
        harness_type=session.harness_type, session_id=session.id,
        goal_id=session.goal_id, project_id=session.project_id,
        event_type=EventType.USER_PROMPT, phase=EventPhase.AFTER,
        message_delta="Repair the missing output file.",
    )
    fresh = old.model_copy(update={
        "event_id": "fresh-worker-result", "ts": datetime.now(UTC),
        "event_type": EventType.AGENT_RESPONSE,
        "message_delta": "Output file written; exact bytes checked.",
        "metadata": {"sse_type": "message.part.updated"},
    })
    try:
        await store.add_event(old, bind_observation=True)
        await pipeline._ingest_event_locked(fresh, session)
        snapshot = await pipeline.pet_snapshot()
        displayed = next(row for row in snapshot["sessions"] if row["id"] == session.id)
        assert displayed["last_message"] == fresh.message_delta
        assert snapshot["last_message"] == fresh.message_delta
        assert await store.list_interventions(session.id) == []
    finally:
        await store.close()


async def test_live_progress_replay_does_not_promote_unbound_history(tmp_path):
    store, _, session, pipeline = await _bound_opencode_pipeline(tmp_path)
    event = HarnessEvent(
        event_id="historical-progress", ts=datetime.now(UTC),
        harness_type=session.harness_type, session_id=session.id,
        goal_id=session.goal_id, project_id=session.project_id,
        event_type=EventType.AGENT_RESPONSE, phase=EventPhase.AFTER,
        message_delta="Historical worker response.",
        metadata={"sse_type": "message.part.updated"},
    )
    try:
        assert await store.add_event(event)
        await pipeline._ingest_event_locked(event, session)
        processing = await store.get_event_processing(event.event_id)
        assert processing["accepted_project_binding"] is None
        assert await store.recent_events_for_authority(
            session.id, goal_id=session.goal_id, project_id=session.project_id,
            harness_type=session.harness_type,
        ) == []
    finally:
        await store.close()


@pytest.mark.parametrize("mismatch", ["goal", "harness"])
async def test_bound_progress_rejects_changed_identity_without_inserting(tmp_path, mismatch):
    store, _, session, _ = await _bound_opencode_pipeline(tmp_path)
    event = HarnessEvent(
        event_id="wrong-identity-progress", ts=datetime.now(UTC),
        harness_type=HarnessType.CODEX if mismatch == "harness" else session.harness_type,
        session_id=session.id,
        goal_id="other-goal" if mismatch == "goal" else session.goal_id,
        project_id=session.project_id,
        event_type=EventType.AGENT_RESPONSE, phase=EventPhase.AFTER,
        message_delta="This must not become current progress.",
    )
    try:
        with pytest.raises(ValueError, match="identity mismatch"):
            await store.add_event(event, bind_observation=True)
        assert await store.get_event(event.event_id) is None
        assert await store.get_event_processing(event.event_id) is None
    finally:
        await store.close()


@pytest.mark.parametrize(
    "event_type",
    [EventType.STOP, EventType.ERROR, EventType.PERMISSION_REQUEST, EventType.SESSION_END],
)
async def test_opencode_decision_boundaries_keep_full_pipeline_path(
    tmp_path, monkeypatch, event_type
):
    store, _, session, pipeline = await _bound_opencode_pipeline(tmp_path)
    event = HarnessEvent(
        event_id=f"decision-{event_type.value}",
        ts=datetime.now(UTC),
        harness_type=HarnessType.OPENCODE,
        session_id=session.id,
        event_type=event_type,
        phase=EventPhase.AFTER,
        metadata={"sse_type": "fixture"},
    )
    normal: list[str] = []

    async def normal_path(observed, observed_session):
        assert observed_session.id == session.id
        normal.append(observed.event_id)
        return None

    monkeypatch.setattr(pipeline, "_accept_and_resume_event", normal_path)
    try:
        assert await pipeline._ingest_event_locked(event, session) is None
        assert normal == [event.event_id]
        assert await store.get_event(event.event_id) is None
    finally:
        await store.close()


async def test_first_unknown_opencode_delta_uses_normal_pipeline_path(tmp_path, monkeypatch):
    store = Store(tmp_path / "unknown-opencode-delta.sqlite")
    await store.connect()
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(home=tmp_path, require_auth=False, autonomy="observe"),
        model=None,
    )
    session = HarnessSession(
        id="opencode:unknown-delta",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="unknown-delta",
        cwd=str(tmp_path),
        project_id=str(tmp_path),
    )
    event = HarnessEvent(
        event_id="unknown-delta-event",
        ts=datetime.now(UTC),
        harness_type=HarnessType.OPENCODE,
        session_id=session.id,
        event_type=EventType.STATUS,
        phase=EventPhase.AFTER,
        metadata={"sse_type": "message.part.delta"},
    )
    normal: list[str] = []

    async def normal_path(observed, observed_session):
        assert observed_session.id == session.id
        normal.append(observed.event_id)
        return None

    monkeypatch.setattr(pipeline, "_accept_and_resume_event", normal_path)
    try:
        assert await pipeline._ingest_event_locked(event, session) is None
        assert normal == [event.event_id]
    finally:
        await store.close()
