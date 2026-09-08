from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pex_bridge import app as bridge_app


def test_overlay_expiry_delay_backs_off_only_while_idle() -> None:
    delay = bridge_app._overlay_expiry_delay
    assert [delay(idle_passes=count, failures=0) for count in range(7)] == [
        1.0,
        1.0,
        2.0,
        4.0,
        8.0,
        8.0,
        8.0,
    ]
    assert delay(idle_passes=99, failures=1) == 2.0
    assert delay(idle_passes=99, failures=5) == 30.0


@pytest.mark.asyncio
async def test_overlay_expiry_loop_resets_idle_backoff_after_work(monkeypatch) -> None:
    stop = asyncio.Event()
    outcomes = iter([{}, {}, {}, {"overlay-1": "overlay_reverted"}, {}])
    observed_delays: list[float] = []

    async def expire_overlays():
        try:
            return next(outcomes)
        except StopIteration:
            stop.set()
            return {}

    async def record_wait(awaitable, *, timeout):
        observed_delays.append(timeout)
        if hasattr(awaitable, "close"):
            awaitable.close()
        if len(observed_delays) == 5:
            stop.set()

    previous_pipeline = bridge_app.state.pipeline
    monkeypatch.setattr(
        bridge_app.state,
        "pipeline",
        SimpleNamespace(executor=SimpleNamespace(expire_overlays=expire_overlays)),
    )
    monkeypatch.setattr(bridge_app.asyncio, "wait_for", record_wait)
    try:
        await bridge_app._overlay_expiry_loop(stop)
    finally:
        bridge_app.state.pipeline = previous_pipeline

    assert observed_delays == [1.0, 2.0, 4.0, 1.0, 1.0]
