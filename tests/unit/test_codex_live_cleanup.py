"""Offline cleanup tests: no real App Server process or inference is started."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from tests.contract.test_live_codex_pump import _close_codex_probe


@pytest.mark.asyncio
@pytest.mark.parametrize("has_pump", [False, True])
@pytest.mark.parametrize("failure", [None, "presentations", "transport"])
async def test_codex_probe_closes_owned_resources_and_preserves_other_tasks(has_pump, failure):
    pump = asyncio.create_task(asyncio.Event().wait()) if has_pump else None
    unrelated = asyncio.create_task(asyncio.Event().wait())
    pipeline, transport, store = AsyncMock(), AsyncMock(), AsyncMock()
    if failure == "presentations":
        pipeline.close_presentations.side_effect = RuntimeError(failure)
    if failure == "transport":
        transport.close.side_effect = RuntimeError(failure)
    try:
        if failure:
            with pytest.raises(RuntimeError, match=failure):
                await _close_codex_probe(pump, pipeline, transport, store)
        else:
            await _close_codex_probe(pump, pipeline, transport, store)
        assert pump is None or pump.cancelled()
        assert not unrelated.done()
        pipeline.close_presentations.assert_awaited_once_with()
        transport.close.assert_awaited_once_with()
        store.close.assert_awaited_once_with()
    finally:
        unrelated.cancel()
        await asyncio.gather(unrelated, return_exceptions=True)


@pytest.mark.asyncio
async def test_failed_codex_pump_does_not_skip_resource_cleanup():
    async def fail():
        raise RuntimeError("pump failed")

    pump = asyncio.create_task(fail())
    await asyncio.gather(pump, return_exceptions=True)
    pipeline, transport, store = AsyncMock(), AsyncMock(), AsyncMock()
    with pytest.raises(RuntimeError, match="pump failed"):
        await _close_codex_probe(pump, pipeline, transport, store)
    pipeline.close_presentations.assert_awaited_once_with()
    transport.close.assert_awaited_once_with()
    store.close.assert_awaited_once_with()
