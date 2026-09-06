from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.adapters.codex_subscription import CodexSubscriptionError
from test_codex_subscription import _subscribed


@pytest.mark.asyncio
async def test_consumer_exits_after_ingest_suppresses_shutdown_cancellation(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    entered = asyncio.Event()

    async def ingest(_event, _session) -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # A real pipeline may finish a shielded durable settlement before
            # returning from the cancelled ingestion call.
            return

    event = SimpleNamespace(event_id="event-1", metadata={"ingress_sequence": 1})
    await adapter._pending.put((event, SimpleNamespace()))
    consumer = asyncio.create_task(adapter._consume(ingest))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        adapter._invalid = True
        consumer.cancel()
        with pytest.raises(CodexSubscriptionError, match="before event dequeue"):
            await asyncio.wait_for(consumer, timeout=1)
        assert adapter._pending.empty()
    finally:
        adapter._invalid = True
        if not consumer.done():
            consumer.cancel()
        done, pending = await asyncio.wait({consumer}, timeout=1)
        await transport.close()
        if pending:
            consumer.cancel()
            newly_done, pending = await asyncio.wait(pending, timeout=1)
            done.update(newly_done)
        for task in done:
            try:
                task.result()
            except (asyncio.CancelledError, CodexSubscriptionError):
                pass
        assert not pending, "owned consumer did not settle during test cleanup"
