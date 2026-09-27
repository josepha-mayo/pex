"""Offline cleanup tests: no real App Server process or inference is started."""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pex_bridge.adapters.codex import CodexStdioTransport

from tests.contract.test_live_codex_pump import _close_codex_probe


@pytest.mark.asyncio
async def test_stdio_close_retains_unexited_child_and_allows_cleanup_retry():
    transport = CodexStdioTransport(sys.executable)
    process = SimpleNamespace(
        stdin=Mock(), kill=Mock(), returncode=None,
        wait=AsyncMock(side_effect=TimeoutError),
    )
    transport._proc = process
    transport.initialized = True
    pending = asyncio.get_running_loop().create_future()
    transport._pending[1] = pending
    reader = asyncio.create_task(asyncio.Event().wait())
    transport._reader_task = reader

    with pytest.raises(RuntimeError, match="exit was not confirmed"):
        await transport.close()
    assert transport._proc is process
    assert reader.cancelled()
    assert not transport.initialized
    with pytest.raises(RuntimeError, match="transport closed"):
        await pending

    async def exit_child():
        process.returncode = -9
        return -9

    process.wait.side_effect = exit_child
    await transport.close()
    assert transport._proc is None
    assert process.kill.call_count == 2


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
