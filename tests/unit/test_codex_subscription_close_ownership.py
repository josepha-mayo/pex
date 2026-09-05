"""Failed subscription cleanup ownership; fake transport, no native processes."""

import asyncio

import pytest
from pex_bridge.adapters.codex_subscription import (
    CodexExistingThreadSubscription,
    CodexSubscriptionError,
)
from test_codex_subscription import FakeSharedTransport, _authorization, _inspect, _thread_response


class HeldCloseTransport(FakeSharedTransport):
    def __init__(self, cwd, *, close_fails=False):
        response = _thread_response(cwd)
        super().__init__(
            [response, response],
            _thread_response(
                cwd, include_turns=False, thread_update={"sessionId": "foreign-root"},
            ),
        )
        self.close_started = asyncio.Event()
        self.release_close = asyncio.Event()
        self.close_settled = asyncio.Event()
        self.close_task = None
        self.close_calls = 0
        self.close_fails = close_fails

    async def close(self):
        self.close_calls += 1
        self.close_task = asyncio.current_task()
        # Revocation is immediate, but is deliberately separate from settled
        # connector cleanup. No model/worker operation exists in this fake.
        self.initialized = False
        self.connection_generation += 1
        self.close_started.set()
        try:
            await self.release_close.wait()
            if self.close_fails:
                raise OSError("injected connector cleanup failure")
            self.closed = True
        finally:
            self.close_settled.set()


async def _failed_resume(cwd, *, close_fails=False):
    transport = HeldCloseTransport(cwd, close_fails=close_fails)
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, cwd)
    caller = asyncio.create_task(coordinator.subscribe(selected, _authorization(selected)))
    await asyncio.wait_for(transport.close_started.wait(), timeout=2)
    return transport, coordinator, caller


async def _settle_fixture(transport, caller):
    transport.release_close.set()
    await asyncio.wait_for(asyncio.gather(caller, return_exceptions=True), timeout=2)
    if transport.close_task is not None:
        await asyncio.wait_for(
            asyncio.gather(transport.close_task, return_exceptions=True), timeout=2,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_count", [1, 3])
async def test_failed_resume_cancellation_does_not_orphan_owned_close(tmp_path, cancel_count):
    transport, coordinator, caller = await _failed_resume(tmp_path)
    try:
        assert not transport.initialized
        assert coordinator.state is None
        assert not transport.closed and not transport.close_settled.is_set()
        for _ in range(cancel_count):
            caller.cancel()
            # Separate cancellation deliveries across scheduler turns; multiple
            # immediate cancel() calls can otherwise coalesce into one throw.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not caller.done(), (
                "failed subscription returned while its shielded close task was still running"
            )
        assert transport.close_calls == 1
        assert not transport.close_settled.is_set()
        transport.release_close.set()
        with pytest.raises((CodexSubscriptionError, asyncio.CancelledError)):
            await caller
        assert transport.close_settled.is_set() and transport.closed
    finally:
        await _settle_fixture(transport, caller)


@pytest.mark.asyncio
async def test_failed_resume_without_cancellation_waits_for_close(tmp_path):
    transport, coordinator, caller = await _failed_resume(tmp_path)
    try:
        await asyncio.sleep(0)
        assert not caller.done()
        assert coordinator.state is None and not transport.initialized
        transport.release_close.set()
        with pytest.raises(CodexSubscriptionError, match="identity mismatch"):
            await caller
        assert transport.close_calls == 1
        assert transport.closed and transport.close_settled.is_set()
    finally:
        await _settle_fixture(transport, caller)


@pytest.mark.asyncio
async def test_failed_resume_preserves_original_error_when_close_itself_fails(tmp_path):
    transport, coordinator, caller = await _failed_resume(tmp_path, close_fails=True)
    try:
        transport.release_close.set()
        with pytest.raises(CodexSubscriptionError, match="identity mismatch"):
            await caller
        assert transport.close_calls == 1 and transport.close_settled.is_set()
        assert not transport.initialized and coordinator.state is None
    finally:
        await _settle_fixture(transport, caller)


@pytest.mark.asyncio
async def test_failed_resume_preserves_original_error_when_owned_close_is_cancelled(tmp_path):
    transport, coordinator, caller = await _failed_resume(tmp_path)
    try:
        transport.close_task.cancel()
        with pytest.raises(CodexSubscriptionError, match="identity mismatch"):
            await asyncio.wait_for(caller, timeout=2)
        assert transport.close_task.cancelled()
        assert transport.close_calls == 1 and transport.close_settled.is_set()
        assert not transport.closed and not transport.initialized
        assert coordinator.state is None
    finally:
        await _settle_fixture(transport, caller)
