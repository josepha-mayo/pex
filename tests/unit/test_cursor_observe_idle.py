from __future__ import annotations

import asyncio
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
