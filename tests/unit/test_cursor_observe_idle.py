from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pex_bridge import app as bridge_app
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.config import Settings


def test_cursor_observe_delay_backs_off_only_when_idle():
    delay = bridge_app._cursor_observe_delay
    assert [delay(idle_passes=count, failures=0) for count in range(6)] == [
        0.25,
        0.25,
        0.5,
        1.0,
        2.0,
        2.0,
    ]
    assert delay(idle_passes=99, failures=1) == 0.5
    assert delay(idle_passes=99, failures=7) == 30.0


@pytest.mark.asyncio
async def test_cursor_observe_loop_resets_idle_backoff_after_work(monkeypatch, tmp_path):
    stop = asyncio.Event()
    results = iter([0, 0, 0, 1, 0])
    observed_delays: list[float] = []

    async def process_inbox(_home, _consume, _stop, *, reject):
        assert callable(reject)
        try:
            return next(results)
        except StopIteration:
            stop.set()
            return 0

    real_wait_for = asyncio.wait_for

    async def record_wait(awaitable, *, timeout):
        observed_delays.append(timeout)
        if hasattr(awaitable, "close"):
            awaitable.close()
        if len(observed_delays) == 5:
            stop.set()

    monkeypatch.setattr("pex_bridge.adapters.cursor_inbox.process_inbox", process_inbox)
    monkeypatch.setattr(bridge_app.asyncio, "wait_for", record_wait)
    monkeypatch.setattr(
        bridge_app.state,
        "settings",
        Settings.for_test(require_auth=False, home=tmp_path, codex_attach=False),
    )
    try:
        await bridge_app._cursor_observe_loop(stop)
    finally:
        monkeypatch.setattr(bridge_app.asyncio, "wait_for", real_wait_for)

    assert observed_delays == [0.25, 0.5, 1.0, 0.25, 0.25]


@pytest.mark.asyncio
async def test_observer_classifies_only_shape_rejections_as_permanent() -> None:
    from pex_bridge.adapters.cursor_inbox import PermanentInboxRecordError

    with pytest.raises(PermanentInboxRecordError):
        await bridge_app._process_cursor_observation({})


@pytest.mark.asyncio
async def test_invalid_normalized_hook_is_rejected_before_durable_upsert(monkeypatch) -> None:
    from pex_bridge.adapters.cursor_inbox import PermanentInboxRecordError

    store = SimpleNamespace(
        get_session_for_authority=AsyncMock(return_value=None),
        upsert_session=AsyncMock(),
    )
    monkeypatch.setattr(bridge_app.state, "adapters", AdapterRegistry())
    monkeypatch.setattr(bridge_app.state, "store", store)

    with pytest.raises(PermanentInboxRecordError):
        await bridge_app._process_cursor_observation(
            {
                "conversation_id": "invalid-normalized-hook",
                "hook_event_name": {"not": "text"},
            }
        )

    store.upsert_session.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("recorded_status", ["working", "stopped"])
async def test_replayed_cursor_hook_does_not_refresh_session_activity(
    monkeypatch, tmp_path, recorded_status,
):
    from pex_bridge.store import Store
    from pex_protocol.enums import SessionStatus

    registry = AdapterRegistry()
    store = Store(tmp_path / "replay.sqlite")
    await store.connect()
    monkeypatch.setattr(bridge_app.state, "adapters", registry)
    monkeypatch.setattr(bridge_app.state, "store", store)
    payload = {
        "conversation_id": "retained-hook",
        "hook_event_name": "afterFileEdit",
        "file_path": str(tmp_path / "result.txt"),
        "observed_ns": 1_788_640_000_000_000_000,
    }
    try:
        original = registry.cursor.upsert_from_hook(payload)
        event = registry.cursor.normalize_hook(payload, original)
        old = datetime.now(UTC) - timedelta(days=8)
        original.last_activity = old
        original.status = SessionStatus(recorded_status)
        event.ts = old
        await store.upsert_session(original)
        await store.add_event(event)
        registry.cursor._last_hook_at = None

        session, replay = await bridge_app._prepare_cursor_hook(payload)

        retained = await store.get_session_for_authority(original.id)
        assert retained.last_activity == old
        assert retained.status == SessionStatus(recorded_status)
        assert session.last_activity == old
        assert registry.cursor.sessions[original.id].last_activity == old
        assert registry.cursor._last_hook_at is None
        # Still pass the incoming event to normal pipeline duplicate validation;
        # don't discard the event or replace its payload with a cached answer.
        assert replay.event_id == event.event_id
        assert replay.file_paths == event.file_paths

        # A genuine hook arriving during the duplicate lookup must not have its
        # in-memory projection or adapter heartbeat rolled back by that replay.
        get_event = store.get_event
        newer = None

        async def observe_concurrent_hook(event_id):
            nonlocal newer
            recorded = await get_event(event_id)
            newer = registry.cursor.upsert_from_hook(
                {**payload, "observed_ns": payload["observed_ns"] + 1}
            )
            await store.upsert_session(newer)
            return recorded

        monkeypatch.setattr(store, "get_event", observe_concurrent_hook)
        await bridge_app._prepare_cursor_hook(payload)
        assert registry.cursor.sessions[original.id] is newer
        assert registry.cursor._last_hook_at is not None
        assert (await store.get_session_for_authority(original.id)).last_activity > old
        monkeypatch.setattr(store, "get_event", get_event)

        fresh, fresh_event = await bridge_app._prepare_cursor_hook(
            {**payload, "observed_ns": payload["observed_ns"] + 2}
        )
        assert fresh_event.event_id != event.event_id
        assert fresh.last_activity > old
        assert fresh.status == SessionStatus.WORKING
        assert registry.cursor._last_hook_at is not None
    finally:
        await store.close()
