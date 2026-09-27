"""Cancellation-aware admission for controller callbacks with a remaining budget."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def await_with_budget(callback: Callable[[], Awaitable[T]], *, budget: float) -> T:
    """Refuse expired admission and results returned after timeout cancellation."""
    if budget <= 0:
        raise TimeoutError("callback exhausted the shared task deadline")
    task = asyncio.current_task()
    initial_cancellations = task.cancelling() if task else 0
    try:
        async with asyncio.timeout(budget) as window:
            result = await callback()
        if window.expired():
            raise TimeoutError("callback exhausted the shared task deadline")
        return result
    finally:
        if task and task.cancelling() > initial_cancellations:
            raise asyncio.CancelledError
