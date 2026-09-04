from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

Listener = Callable[[str, dict[str, Any]], Awaitable[None]]
logger = logging.getLogger(__name__)
COMMITTED_LISTENER_TIMEOUT_SECONDS = 1.0


class EventBus:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []
        self._lock = asyncio.Lock()

    def subscribe(self, listener: Listener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            await listener(topic, payload)

    async def publish_committed(
        self,
        topic: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float = COMMITTED_LISTENER_TIMEOUT_SECONDS,
    ) -> int:
        """Notify listeners after a durable commit without invalidating the commit.

        The canonical Store remains the replayable source of truth. A websocket,
        pet, or other presentation listener is therefore not allowed to turn a
        successful durable mutation into an apparent request failure. Failures
        are counted and logged without serializing the payload, which may contain
        internal decision context.
        """

        if not 0 < timeout_seconds <= 5.0:
            raise ValueError("committed listener timeout must be in (0, 5] seconds")
        async with self._lock:
            listeners = list(self._listeners)
        failures = 0
        for listener in listeners:
            try:
                # asyncio.CancelledError intentionally propagates: caller/task
                # cancellation is control flow, not a presentation failure.
                await asyncio.wait_for(listener(topic, payload), timeout=timeout_seconds)
            except Exception as exc:
                failures += 1
                logger.warning(
                    "committed event listener failed topic=%s listener=%s error=%s",
                    topic,
                    getattr(listener, "__name__", type(listener).__name__),
                    type(exc).__name__,
                )
        return failures
