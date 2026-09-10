from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

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


async def test_opencode_ordinary_retry_preserves_observed_drifting_state(tmp_path):
    store, adapter, session, pipeline = await _bound_opencode_pipeline(tmp_path)
    session.status = SessionStatus.DRIFTING
    session.supervision_paused = True
    await store.upsert_session(session)
    try:
        event = await _ingest(
            pipeline,
            adapter,
            session,
            _payload(
                str(tmp_path),
                "session.status",
                properties={"status": {"type": "retry"}},
            ),
        )
        persisted = await store.get_session(session.id)

        assert event.metadata["opencode_status"] == "retry"
        assert persisted is not None and persisted.status == SessionStatus.DRIFTING
    finally:
        await store.close()


async def test_opencode_free_tier_retry_blocks_without_planning_or_recovery(tmp_path):
    store, adapter, session, pipeline = await _bound_opencode_pipeline(tmp_path)
    supervisor = SimpleNamespace(agentcore=None, calls=0)
    executor = SimpleNamespace(calls=0)

    async def decide(*_args, **_kwargs):
        supervisor.calls += 1
        raise AssertionError("provider limit must not reach planning")

    async def execute(*_args, **_kwargs):
        executor.calls += 1
        raise AssertionError("provider limit must not reach dispatch")

    supervisor.decide = decide
    executor.execute = execute
    pipeline.supervisor = supervisor
    pipeline.executor = executor
    payload = _payload(
        str(tmp_path),
        "session.status",
        properties={
            "status": {
                "type": "retry",
                "message": "Free limit reached for this provider.",
                "action": {
                    "reason": "free_tier_limit",
                    "provider": "opencode",
                    "title": "Free limit reached",
                    "message": "Upgrade before retrying.",
                    "label": "subscribe",
                    "link": "https://opencode.ai/go",
                },
            }
        },
    )
    try:
        event = await _ingest(pipeline, adapter, session, payload)
        persisted = await store.get_session(session.id)
        processing = await store.get_event_processing(event.event_id)

        assert event.message_delta == "Free limit reached for this provider."
        assert event.metadata["opencode_status"] == "retry"
        assert event.metadata["opencode_status_action"]["reason"] == "free_tier_limit"
        assert persisted is not None and persisted.status == SessionStatus.BLOCKED
        assert persisted.metadata["opencode_provider_block"]["label"] == "subscribe"
        assert processing is not None and processing["state"] == "complete"
        assert (
            processing["receipt"]["terminal_reason"]
            == "opencode_free_tier_limit_without_followup"
        )
        assert supervisor.calls == executor.calls == 0
        assert await pipeline.recover_unfinished_events() == []
        assert supervisor.calls == executor.calls == 0
        for payload in (
            _payload(
                str(tmp_path),
                "message.updated",
                properties={
                    "info": {
                        "sessionID": "ses_idle",
                        "id": "assistant-metadata",
                        "role": "assistant",
                    }
                },
            ),
            _payload(
                str(tmp_path),
                "message.updated",
                properties={
                    "info": {"sessionID": "ses_idle", "id": "userX", "role": "user"}
                },
            ),
            _payload(
                str(tmp_path),
                "message.updated",
                properties={
                    "info": {"sessionID": "ses_idle", "id": "userX", "role": "user"}
                },
            ),
        ):
            payload["id"] = f"{payload['id']}-{len(await store.recent_events(session.id))}"
            await _ingest(pipeline, adapter, session, payload)
            persisted = await store.get_session(session.id)
            assert persisted is not None and persisted.status == SessionStatus.BLOCKED
        fenced_status = _payload(
            str(tmp_path), "session.status", properties={"status": {"type": "idle"}}
        )
        fenced_status["id"] = "fenced-idle-status"
        await _ingest(pipeline, adapter, session, fenced_status)
        persisted = await store.get_session(session.id)
        assert persisted is not None and persisted.status == SessionStatus.BLOCKED
        trailing_idle = await _ingest(
            pipeline, adapter, session, _payload(str(tmp_path), "session.idle")
        )
        persisted = await store.get_session(session.id)
        trailing_processing = await store.get_event_processing(trailing_idle.event_id)
        assert trailing_idle.event_type == EventType.STOP
        assert persisted is not None and persisted.status == SessionStatus.BLOCKED
        assert trailing_processing is not None
        assert (
            trailing_processing["receipt"]["terminal_reason"]
            == "opencode_free_tier_limit_without_followup"
        )
        assert supervisor.calls == executor.calls == 0
        session.supervision_paused = True
        await store.upsert_session(session)
        concrete_work = _payload(
            str(tmp_path),
            "file.edited",
            properties={"file": str(tmp_path / "resumed-work.txt")},
        )
        concrete_work["id"] = "concrete-file-work"
        await _ingest(pipeline, adapter, session, concrete_work)
        resumed = await store.get_session(session.id)
        assert resumed is not None and resumed.status == SessionStatus.WORKING
        assert "opencode_free_tier_limited" not in resumed.metadata
        assert "opencode_provider_block" not in resumed.metadata
    finally:
        await store.close()


async def test_opencode_exact_message_abort_stays_stopped_until_concrete_work(tmp_path):
    store, adapter, session, pipeline = await _bound_opencode_pipeline(tmp_path)
    supervisor = SimpleNamespace(agentcore=None, calls=0)
    executor = SimpleNamespace(calls=0)

    async def decide(*_args, **_kwargs):
        supervisor.calls += 1
        raise AssertionError("an exact aborted turn must not reach planning")

    async def execute(*_args, **_kwargs):
        executor.calls += 1
        raise AssertionError("an exact aborted turn must not reach dispatch")

    supervisor.decide = decide
    executor.execute = execute
    pipeline.supervisor = supervisor
    pipeline.executor = executor
    aborted_payload = _payload(
        str(tmp_path),
        "message.updated",
        properties={
            "info": {
                "sessionID": "ses_idle",
                "id": "assistant-aborted",
                "role": "assistant",
                "error": {
                    "name": "MessageAbortedError",
                    "data": {"message": "aborted"},
                },
            }
        },
    )
    path = store.path
    try:
        aborted = await _ingest(pipeline, adapter, session, aborted_payload)
        persisted = await store.get_session(session.id)
        processing = await store.get_event_processing(aborted.event_id)

        assert aborted.event_type == EventType.ERROR
        assert aborted.metadata["opencode_message_aborted"] is True
        assert persisted is not None and persisted.status == SessionStatus.STOPPED
        assert persisted.metadata["opencode_turn_aborted"] is True
        assert processing is not None
        assert (
            processing["receipt"]["terminal_reason"]
            == "opencode_message_aborted_without_followup"
        )
        for payload in (
            _payload(
                str(tmp_path),
                "message.updated",
                properties={
                    "info": {"sessionID": "ses_idle", "id": "userX", "role": "user"}
                },
            ),
            _payload(str(tmp_path), "session.status", properties={"status": {"type": "idle"}}),
            _payload(str(tmp_path), "session.idle"),
        ):
            payload["id"] = f"{payload['id']}-{len(await store.recent_events(session.id))}"
            trailing = await _ingest(pipeline, adapter, session, payload)
            persisted = await store.get_session(session.id)
            trailing_processing = await store.get_event_processing(trailing.event_id)
            assert persisted is not None and persisted.status == SessionStatus.STOPPED
            assert persisted.metadata["opencode_turn_aborted"] is True
            assert trailing_processing is not None
            assert (
                trailing_processing["receipt"]["terminal_reason"]
                == "opencode_message_aborted_without_followup"
            )
        assert supervisor.calls == executor.calls == 0
    finally:
        await store.close()

    recovery = Store(path)
    await recovery.connect()
    registry = AdapterRegistry()
    recovered_adapter = registry.opencode
    recovered_adapter.attach_transport(MemoryHttpTransport())
    recovered_session = await recovery.get_session(session.id)
    assert recovered_session is not None
    recovered_adapter.sessions[recovered_session.id] = recovered_session
    recovered_pipeline = Pipeline(
        recovery,
        registry,
        EventBus(),
        Settings.for_test(home=tmp_path, require_auth=False, autonomy="observe"),
        model=None,
    )
    recovered_supervisor = SimpleNamespace(agentcore=None, calls=0)

    async def recovered_decide(*_args, **_kwargs):
        recovered_supervisor.calls += 1
        raise AssertionError("persisted aborted turn must not reach planning")

    recovered_supervisor.decide = recovered_decide
    recovered_pipeline.supervisor = recovered_supervisor
    try:
        after_restart = _payload(str(tmp_path), "session.idle")
        after_restart["id"] = "aborted-after-restart-idle"
        idle = await _ingest(
            recovered_pipeline,
            recovered_adapter,
            recovered_session,
            after_restart,
        )
        persisted = await recovery.get_session(session.id)
        processing = await recovery.get_event_processing(idle.event_id)
        assert persisted is not None and persisted.status == SessionStatus.STOPPED
        assert persisted.metadata["opencode_turn_aborted"] is True
        assert processing is not None
        assert (
            processing["receipt"]["terminal_reason"]
            == "opencode_message_aborted_without_followup"
        )
        assert recovered_supervisor.calls == 0

        recovered_session.supervision_paused = True
        await recovery.upsert_session(recovered_session)
        concrete_work = _payload(
            str(tmp_path),
            "file.edited",
            properties={"file": str(tmp_path / "resumed-after-abort.txt")},
        )
        concrete_work["id"] = "aborted-concrete-file-work"
        await _ingest(recovered_pipeline, recovered_adapter, recovered_session, concrete_work)
        resumed = await recovery.get_session(session.id)
        assert resumed is not None and resumed.status == SessionStatus.WORKING
        assert "opencode_turn_aborted" not in resumed.metadata
    finally:
        await recovery.close()


async def test_opencode_provider_limit_keeps_priority_over_exact_message_abort(tmp_path):
    store, adapter, session, pipeline = await _bound_opencode_pipeline(tmp_path)
    session.status = SessionStatus.BLOCKED
    session.metadata["opencode_free_tier_limited"] = True
    session.metadata["opencode_provider_block"] = {"reason": "free_tier_limit"}
    await store.upsert_session(session)
    try:
        abort = _payload(
            str(tmp_path),
            "message.updated",
            properties={
                "info": {
                    "sessionID": "ses_idle",
                    "id": "assistant-aborted-after-limit",
                    "role": "assistant",
                    "error": {"name": "MessageAbortedError"},
                }
            },
        )
        event = await _ingest(pipeline, adapter, session, abort)
        persisted = await store.get_session(session.id)
        processing = await store.get_event_processing(event.event_id)
        assert persisted is not None and persisted.status == SessionStatus.BLOCKED
        assert persisted.metadata["opencode_free_tier_limited"] is True
        assert persisted.metadata["opencode_turn_aborted"] is True
        assert processing is not None
        assert (
            processing["receipt"]["terminal_reason"]
            == "opencode_free_tier_limit_without_followup"
        )
    finally:
        await store.close()


async def test_opencode_discovery_cannot_erase_or_mint_provider_fence(tmp_path):
    store, _adapter, session, _pipeline = await _bound_opencode_pipeline(tmp_path)
    session.metadata["opencode_free_tier_limited"] = True
    session.metadata["opencode_provider_block"] = {"reason": "free_tier_limit"}
    await store.upsert_session(session)
    try:
        discovery = session.model_copy(
            update={
                "metadata": {
                    "discovery_observation_only": True,
                    "title": "discovered",
                    # This marker is event-processing-only: discovery cannot
                    # forge a reset for a provider-owned fence.
                    "opencode_provider_block_cleared": True,
                }
            }
        )
        await store.upsert_session(discovery)
        preserved = await store.get_session(session.id)
        assert preserved is not None
        assert preserved.metadata["opencode_free_tier_limited"] is True
        assert preserved.metadata["opencode_provider_block"] == {"reason": "free_tier_limit"}
        assert "opencode_provider_block_cleared" not in preserved.metadata
        assert preserved.status == SessionStatus.BLOCKED

        unfenced = HarnessSession(
            id="opencode:unfenced",
            harness_type=HarnessType.OPENCODE,
            vendor_session_id="unfenced",
            project_id=str(tmp_path),
            cwd=str(tmp_path),
            status=SessionStatus.DISCOVERED,
        )
        await store.upsert_session(unfenced)
        await store.upsert_session(
            unfenced.model_copy(
                update={
                    "metadata": {
                        "discovery_observation_only": True,
                        "opencode_free_tier_limited": True,
                        "opencode_provider_block": {"reason": "free_tier_limit"},
                    }
                }
            )
        )
        not_minted = await store.get_session(unfenced.id)
        assert not_minted is not None
        assert "opencode_free_tier_limited" not in not_minted.metadata
        assert "opencode_provider_block" not in not_minted.metadata
        first_discovery = unfenced.model_copy(update={
            "id": "opencode:first-discovery",
            "vendor_session_id": "first-discovery",
            "metadata": {
                "discovery_observation_only": True,
                "opencode_free_tier_limited": True,
                "opencode_provider_block": {"reason": "free_tier_limit"},
            },
        })
        await store.upsert_session(first_discovery)
        created = await store.get_session(first_discovery.id)
        assert created is not None
        assert "opencode_free_tier_limited" not in created.metadata
        assert "opencode_provider_block" not in created.metadata

        aborted = HarnessSession(
            id="opencode:aborted",
            harness_type=HarnessType.OPENCODE,
            vendor_session_id="aborted",
            project_id=str(tmp_path),
            cwd=str(tmp_path),
            status=SessionStatus.STOPPED,
            metadata={"opencode_turn_aborted": True},
        )
        await store.upsert_session(aborted)
        await store.upsert_session(
            aborted.model_copy(
                update={"metadata": {"discovery_observation_only": True}}
            )
        )
        preserved_abort = await store.get_session(aborted.id)
        assert preserved_abort is not None
        assert preserved_abort.status == SessionStatus.STOPPED
        assert preserved_abort.metadata["opencode_turn_aborted"] is True
    finally:
        await store.close()


async def test_opencode_free_tier_fence_survives_restart_before_idle(tmp_path):
    store, adapter, session, pipeline = await _bound_opencode_pipeline(tmp_path)
    retry = _payload(
        str(tmp_path),
        "session.status",
        properties={
            "status": {
                "type": "retry",
                "message": "Free limit reached for this provider.",
                "action": {"reason": "free_tier_limit"},
            }
        },
    )
    path = store.path
    try:
        await _ingest(pipeline, adapter, session, retry)
    finally:
        await store.close()

    recovery = Store(path)
    await recovery.connect()
    registry = AdapterRegistry()
    recovered_adapter = registry.opencode
    recovered_adapter.attach_transport(MemoryHttpTransport())
    recovered_session = await recovery.get_session(session.id)
    assert recovered_session is not None
    recovered_adapter.sessions[recovered_session.id] = recovered_session
    recovered_pipeline = Pipeline(
        recovery,
        registry,
        EventBus(),
        Settings.for_test(home=tmp_path, require_auth=False, autonomy="observe"),
        model=None,
    )
    supervisor = SimpleNamespace(agentcore=None, calls=0)

    async def decide(*_args, **_kwargs):
        supervisor.calls += 1
        raise AssertionError("persisted provider block must not reach planning")

    supervisor.decide = decide
    recovered_pipeline.supervisor = supervisor
    try:
        idle = await _ingest(
            recovered_pipeline,
            recovered_adapter,
            recovered_session,
            _payload(str(tmp_path), "session.idle"),
        )
        persisted = await recovery.get_session(session.id)
        processing = await recovery.get_event_processing(idle.event_id)

        assert idle.event_type == EventType.STOP
        assert persisted is not None and persisted.status == SessionStatus.BLOCKED
        assert persisted.metadata["opencode_free_tier_limited"] is True
        assert processing is not None
        assert (
            processing["receipt"]["terminal_reason"]
            == "opencode_free_tier_limit_without_followup"
        )
        assert supervisor.calls == 0
    finally:
        await recovery.close()
