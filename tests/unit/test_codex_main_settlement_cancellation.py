"""Cancellation cannot strand an acknowledged claimed Codex correction."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

pytest_plugins = ("test_codex_correction_pipeline",)


async def _wait_for_boundary(task: asyncio.Task, entered: asyncio.Event) -> None:
    """Wait for ordering, not a three-second integration performance target."""
    waiter = asyncio.create_task(entered.wait())
    try:
        done, _ = await asyncio.wait(
            {task, waiter}, timeout=15, return_when=asyncio.FIRST_COMPLETED,
        )
        if entered.is_set():
            return
        if task in done:
            task.result()  # Surface the actual ingestion error before any timeout.
            raise AssertionError("ingestion completed without reaching the held boundary")
        raise TimeoutError("ingestion did not reach the held boundary within 15 seconds")
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


async def test_boundary_wait_reports_early_ingestion_error():
    async def fail():
        raise ValueError("original ingestion error")

    task = asyncio.create_task(fail())
    with pytest.raises(ValueError, match="original ingestion error"):
        await _wait_for_boundary(task, asyncio.Event())
    assert task.done()


@asynccontextmanager
async def _owned_ingestion(coroutine, release: asyncio.Event):
    task = asyncio.create_task(coroutine)
    try:
        yield task
    finally:
        # A failed boundary wait must not leave the test's artificial barrier
        # blocking the production settlement task during fixture teardown.
        release.set()
        if not task.done():
            task.cancel()
        done, _ = await asyncio.wait({task}, timeout=10)
        assert done, "test-owned ingestion did not settle after releasing its barrier"
        try:
            task.result()
        except asyncio.CancelledError:
            pass


async def test_owned_ingestion_releases_barrier_on_early_test_failure():
    release = asyncio.Event()
    entered = asyncio.Event()
    settled = asyncio.Event()

    async def ingest():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await release.wait()
            settled.set()

    with pytest.raises(TimeoutError, match="fixture boundary timeout"):
        async with _owned_ingestion(ingest(), release) as task:
            await entered.wait()
            raise TimeoutError("fixture boundary timeout")
    assert release.is_set() and settled.is_set() and task.done()


async def _assert_cancelled_after_release(task: asyncio.Task, release: asyncio.Event) -> None:
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task


async def _assert_durable_delivery(case) -> None:
    event = case.current_event[0]
    processing = await case.store.get_event_processing(event.event_id)
    effect = await case.store.get_event_effect(event.event_id, "main")
    assert processing is not None and processing["state"] == "complete"
    assert effect is not None and effect["state"] == "delivered"
    assert processing["receipt"]["effect_state"] == "delivered"
    assert effect["result"]["worker_delivery_receipt"]["vendor_turn_id"] == (
        "fixture-correction-turn"
    )
    case.private_dispatch.assert_awaited_once()


async def test_cancel_during_post_executor_refresh_still_seals_acknowledged_effect(
    correction_pipeline,
    monkeypatch,
):
    case = correction_pipeline
    executor_returned = asyncio.Event()
    refresh_entered = asyncio.Event()
    release_refresh = asyncio.Event()
    execute = case.pipeline.executor.execute
    get_effect = case.store.get_event_effect

    async def execute_spy(*args, **kwargs):
        result = await execute(*args, **kwargs)
        executor_returned.set()
        return result

    blocked = False

    async def get_effect_spy(event_id, effect_key):
        nonlocal blocked
        if executor_returned.is_set() and effect_key == "main" and not blocked:
            blocked = True
            refresh_entered.set()
            await release_refresh.wait()
        return await get_effect(event_id, effect_key)

    monkeypatch.setattr(case.pipeline.executor, "execute", execute_spy)
    monkeypatch.setattr(case.store, "get_event_effect", get_effect_spy)
    async with _owned_ingestion(case.ingest_observed(), release_refresh) as ingest:
        await _wait_for_boundary(ingest, refresh_entered)
        await _assert_cancelled_after_release(ingest, release_refresh)
        await _assert_durable_delivery(case)


async def test_repeated_cancel_while_final_seal_is_held_still_finishes_settlement(
    correction_pipeline,
    monkeypatch,
):
    case = correction_pipeline
    executor_returned = asyncio.Event()
    seal_entered = asyncio.Event()
    release_seal = asyncio.Event()
    execute = case.pipeline.executor.execute
    seal = case.pipeline._seal_main_event_effect

    async def execute_spy(*args, **kwargs):
        result = await execute(*args, **kwargs)
        executor_returned.set()
        return result

    blocked = False

    async def seal_spy(**kwargs):
        nonlocal blocked
        if executor_returned.is_set() and kwargs.get("publish") is True and not blocked:
            blocked = True
            seal_entered.set()
            await release_seal.wait()
        return await seal(**kwargs)

    monkeypatch.setattr(case.pipeline.executor, "execute", execute_spy)
    monkeypatch.setattr(case.pipeline, "_seal_main_event_effect", seal_spy)
    async with _owned_ingestion(case.ingest_observed(), release_seal) as ingest:
        await _wait_for_boundary(ingest, seal_entered)
        await _assert_cancelled_after_release(ingest, release_seal)
        await _assert_durable_delivery(case)


async def test_executor_error_and_repeated_cancel_still_seal_delivery_uncertain(
    correction_pipeline,
    monkeypatch,
):
    case = correction_pipeline
    seal_entered = asyncio.Event()
    release_seal = asyncio.Event()
    seal = case.pipeline._seal_main_event_effect
    case.execute.side_effect = RuntimeError("fixture executor failed after durable claim")
    blocked = False

    async def seal_spy(**kwargs):
        nonlocal blocked
        if (
            kwargs.get("effect_state") == "delivery_uncertain"
            and kwargs.get("publish") is False
            and not blocked
        ):
            blocked = True
            seal_entered.set()
            await release_seal.wait()
        return await seal(**kwargs)

    monkeypatch.setattr(case.pipeline, "_seal_main_event_effect", seal_spy)
    async with _owned_ingestion(case.ingest_observed(), release_seal) as ingest:
        await _wait_for_boundary(ingest, seal_entered)
        await _assert_cancelled_after_release(ingest, release_seal)
    event = case.current_event[0]
    processing = await case.store.get_event_processing(event.event_id)
    effect = await case.store.get_event_effect(event.event_id, "main")
    assert processing is not None and processing["state"] == "complete"
    assert effect is not None and effect["state"] == "delivery_uncertain"
    assert processing["receipt"]["effect_state"] == "delivery_uncertain"
    assert processing["receipt"]["intervention"]["result"] == (
        "worker_delivery_uncertain"
    )
    case.execute.assert_awaited_once()
    case.private_dispatch.assert_not_awaited()
