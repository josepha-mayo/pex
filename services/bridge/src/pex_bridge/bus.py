from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

Listener = Callable[[str, dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []
        self._lock = asyncio.Lock()

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            await listener(topic, payload)
