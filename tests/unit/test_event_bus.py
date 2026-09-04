from __future__ import annotations

import asyncio

import pytest
from pex_bridge.bus import EventBus


@pytest.mark.asyncio
async def test_event_bus_subscription_is_idempotent() -> None:
    bus = EventBus()
    seen: list[tuple[str, dict]] = []

    async def listener(topic: str, payload: dict) -> None:
        seen.append((topic, payload))

    bus.subscribe(listener)
    bus.subscribe(listener)
    await bus.publish("pet", {"working": 1})

    assert seen == [("pet", {"working": 1})]


@pytest.mark.asyncio
async def test_committed_publish_is_best_effort_and_continues_after_listener_failure() -> None:
    bus = EventBus()
    seen: list[tuple[str, dict]] = []

    async def broken_listener(_topic: str, _payload: dict) -> None:
        raise RuntimeError("presentation transport failed")

    async def healthy_listener(topic: str, payload: dict) -> None:
        seen.append((topic, payload))

    bus.subscribe(broken_listener)
    bus.subscribe(healthy_listener)

    failures = await bus.publish_committed("intervention", {"id": "durable"})

    assert failures == 1
    assert seen == [("intervention", {"id": "durable"})]


@pytest.mark.asyncio
async def test_committed_publish_bounds_hanging_listener_and_continues() -> None:
    bus = EventBus()
    blocked = asyncio.Event()
    seen: list[str] = []

    async def hanging_listener(_topic: str, _payload: dict) -> None:
        await blocked.wait()

    async def healthy_listener(topic: str, _payload: dict) -> None:
        seen.append(topic)

    bus.subscribe(hanging_listener)
    bus.subscribe(healthy_listener)

    failures = await bus.publish_committed(
        "pet",
        {"status": "durable"},
        timeout_seconds=0.01,
    )

    assert failures == 1
    assert seen == ["pet"]
