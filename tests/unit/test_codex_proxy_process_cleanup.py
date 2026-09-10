"""Connector cleanup contracts; no OS process is created or terminated."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pex_bridge.adapters.codex_shared import _ProxyProcessChannel


@pytest.mark.asyncio
@pytest.mark.parametrize("timeouts", [0, 1, 2])
async def test_cleanup_escalates_only_when_connector_wait_times_out(timeouts):
    connector = SimpleNamespace(
        stdin=SimpleNamespace(close=Mock()),
        wait=AsyncMock(side_effect=[TimeoutError()] * timeouts + [0]),
        terminate=Mock(),
        kill=Mock(),
    )
    await _ProxyProcessChannel(connector).close()

    connector.stdin.close.assert_called_once_with()
    assert connector.wait.await_count == timeouts + 1
    assert connector.terminate.call_count == int(timeouts >= 1)
    assert connector.kill.call_count == int(timeouts >= 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_during", ["terminate", "kill"])
async def test_connector_exit_race_does_not_trigger_other_cleanup(exit_during):
    connector = SimpleNamespace(
        stdin=None,
        wait=AsyncMock(side_effect=TimeoutError()),
        terminate=Mock(),
        kill=Mock(),
    )
    getattr(connector, exit_during).side_effect = ProcessLookupError()

    await _ProxyProcessChannel(connector).close()

    connector.terminate.assert_called_once_with()
    assert connector.kill.call_count == int(exit_during == "kill")
    assert connector.wait.await_count == (1 if exit_during == "terminate" else 2)
