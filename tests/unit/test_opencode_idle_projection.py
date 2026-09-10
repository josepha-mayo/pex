from __future__ import annotations

from datetime import UTC, datetime

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.http_json import MemoryHttpTransport
from pex_bridge.adapters.opencode_outcomes import OPENCODE_MESSAGE_LINEAGE_KEY
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessSession


async def _bound_opencode_pipeline(tmp_path):
    store = Store(tmp_path / "opencode-idle.sqlite")
    await store.connect()
    registry = AdapterRegistry()
    adapter = registry.opencode
    adapter.attach_transport(MemoryHttpTransport())
    now = datetime.now(UTC)
    goal = Goal(
        id="goal-opencode-idle",
        project_id=str(tmp_path),
        title="Preserve OpenCode terminal state",
        objective="A completed parent-bound turn remains stopped until new work starts.",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id="opencode:ses_idle",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="ses_idle",
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

    async def offline_probe():
        return AdapterCapabilities()

    adapter.probe = offline_probe
    return store, adapter, session, pipeline


def _payload(cwd: str, kind: str, *, properties: dict | None = None) -> dict:
    return {
        "id": f"{kind}-event",
        "type": kind,
        "properties": {"cwd": cwd, "sessionID": "ses_idle", **(properties or {})},
    }


def _completed_parent(
    cwd: str,
    *,
    parent_id: str = "userX",
    assistant_id: str = "assistant-complete",
) -> dict:
    return _payload(
        cwd,
        "message.updated",
        properties={
            "info": {
                "sessionID": "ses_idle",
                "id": assistant_id,
                "role": "assistant",
                "parentID": parent_id,
                "finish": "stop",
                "time": {"created": 10, "completed": 11},
            }
        },
    )


async def _ingest(pipeline, adapter, session, payload):
    event = adapter.normalize_sse(session, payload)
    await pipeline.ingest_event(event, session)
    return event


async def test_opencode_quiet_tail_keeps_completed_parent_stopped_without_second_stop(
    tmp_path,
):
    store, adapter, session, pipeline = await _bound_opencode_pipeline(tmp_path)
    try:
        stop = await _ingest(pipeline, adapter, session, _completed_parent(str(tmp_path)))
        assert stop.event_type == EventType.STOP
        assert stop.metadata[OPENCODE_MESSAGE_LINEAGE_KEY]["parent_message_id"] == "userX"
        stopped = await store.get_session(session.id)
        assert stopped is not None and stopped.status == SessionStatus.STOPPED
        explicit_idle = [
            _payload(str(tmp_path), "session.status", properties={"status": {"type": "idle"}}),
            _payload(
                str(tmp_path), "session.status", properties={"status": {"type": "idle"}, "n": 2}
            ),
            _payload(str(tmp_path), "session.idle"),
        ]
        idle_events = [
            await _ingest(pipeline, adapter, session, payload) for payload in explicit_idle
        ]
        assert all(event.event_type == EventType.STATUS for event in idle_events)
        assert idle_events[0].metadata["opencode_status"] == "idle"
        assert idle_events[1].metadata["opencode_status"] == "idle"
        after_idle = await store.get_session(session.id)
        assert after_idle is not None and after_idle.status == SessionStatus.STOPPED

        quiet_tail = [
            _payload(str(tmp_path), "session.updated"),
            _payload(str(tmp_path), "session.diff"),
            _payload(
                str(tmp_path),
                "message.updated",
                properties={"info": {"sessionID": "ses_idle", "id": "userX", "role": "user"}},
            ),
        ]
        tail_events = [await _ingest(pipeline, adapter, session, payload) for payload in quiet_tail]

        assert all(event.event_type == EventType.STATUS for event in tail_events)
        assert adapter._completed_terminal_parents[session.id] == "userX"
        persisted = await store.get_session(session.id)
        assert persisted is not None and persisted.status == SessionStatus.STOPPED
        assert persisted.last_activity == after_idle.last_activity
        events = await store.recent_events(session.id, limit=20)
        assert sum(event.event_type == EventType.STOP for event in events) == 1
    finally:
        await store.close()


async def test_opencode_new_user_and_busy_retry_are_explicit_work_resumption(tmp_path):
    store, adapter, session, pipeline = await _bound_opencode_pipeline(tmp_path)
    try:
        await _ingest(pipeline, adapter, session, _completed_parent(str(tmp_path)))
        assert adapter._completed_terminal_parents[session.id] == "userX"

        new_user = await _ingest(
            pipeline,
            adapter,
            session,
            _payload(
                str(tmp_path),
                "message.updated",
                properties={"info": {"sessionID": "ses_idle", "id": "userY", "role": "user"}},
            ),
        )
        assert new_user.event_type == EventType.USER_PROMPT
        assert session.id not in adapter._completed_terminal_parents
        persisted = await store.get_session(session.id)
        assert persisted is not None and persisted.status == SessionStatus.WORKING

        await _ingest(
            pipeline,
            adapter,
            session,
            _completed_parent(
                str(tmp_path), parent_id="userY", assistant_id="assistant-complete-two"
            ),
        )
        stopped_again = await store.get_session(session.id)
        assert stopped_again is not None and stopped_again.status == SessionStatus.STOPPED
        for status in ("busy", "retry"):
            event = await _ingest(
                pipeline,
                adapter,
                session,
                _payload(str(tmp_path), "session.status", properties={"status": {"type": status}}),
            )
            assert event.event_type == EventType.STATUS
            assert event.metadata["opencode_status"] == status
            persisted = await store.get_session(session.id)
            assert persisted is not None and persisted.status == SessionStatus.WORKING
    finally:
        await store.close()


async def test_opencode_unrelated_status_does_not_invent_activity(tmp_path):
    store, adapter, session, pipeline = await _bound_opencode_pipeline(tmp_path)
    try:
        await _ingest(pipeline, adapter, session, _completed_parent(str(tmp_path)))
        before = await store.get_session(session.id)
        assert before is not None and before.status == SessionStatus.STOPPED

        event = await _ingest(pipeline, adapter, session, _payload(str(tmp_path), "session.diff"))
        assert event.event_type == EventType.STATUS
        assert "opencode_status" not in event.metadata
        after = await store.get_session(session.id)
        assert after is not None
        assert after.status == SessionStatus.STOPPED
        assert after.last_activity == before.last_activity
    finally:
        await store.close()
