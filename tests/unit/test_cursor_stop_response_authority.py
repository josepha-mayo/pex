from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pex_bridge.app as bridge_app
import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "revocation",
    ["missing_before", "missing_after", "revision_changed", "paused", "aborted", "error"],
)
async def test_stop_response_discards_preparation_after_authority_loss(monkeypatch, revocation):
    session = SimpleNamespace(id="cursor:authority-stop")
    event = SimpleNamespace(event_id="stop-authority-event", metadata={})
    signature = (4, "project-binding", None, "goal-1", 2, "intent-hash")
    snapshots = [(session, signature), (session, signature)]
    if revocation == "missing_before":
        snapshots[0] = None
    elif revocation == "missing_after":
        snapshots[1] = None
    elif revocation == "revision_changed":
        snapshots[1] = (session, (6, *signature[1:]))
    elif revocation in {"aborted", "error"}:
        event.metadata["tool_status"] = revocation
    adapter = SimpleNamespace(
        consume_verified_stop_followup=Mock(),
        consume_followup=Mock(),
    )
    store = SimpleNamespace(prepare_cursor_hook_delivery=AsyncMock())
    pipeline = SimpleNamespace(
        supervision_paused=revocation == "paused",
        ingest_event=AsyncMock(return_value=SimpleNamespace(id="prepared-intervention")),
    )
    monkeypatch.setattr(bridge_app.state, "adapters", SimpleNamespace(cursor=adapter))
    monkeypatch.setattr(bridge_app.state, "store", store)
    monkeypatch.setattr(bridge_app.state, "pipeline", pipeline)
    monkeypatch.setattr(
        bridge_app, "_cursor_submit_authority", AsyncMock(side_effect=snapshots),
    )
    monkeypatch.setattr(bridge_app, "_observe_cursor_continuation", AsyncMock())

    assert await bridge_app._process_cursor_stop(event, session) == {}

    adapter.consume_verified_stop_followup.assert_not_called()
    store.prepare_cursor_hook_delivery.assert_not_awaited()
    adapter.consume_followup.assert_called_once_with(
        session.id, trigger_event_id=event.event_id,
    )


@pytest.mark.asyncio
async def test_stop_cancellation_discards_only_the_trigger_event(monkeypatch):
    import asyncio

    session = SimpleNamespace(id="cursor:cancelled-stop")
    event = SimpleNamespace(event_id="cancelled-event", metadata={})
    adapter = SimpleNamespace(consume_followup=Mock())
    pipeline = SimpleNamespace(
        supervision_paused=False,
        ingest_event=AsyncMock(side_effect=asyncio.CancelledError),
    )
    monkeypatch.setattr(bridge_app.state, "adapters", SimpleNamespace(cursor=adapter))
    monkeypatch.setattr(bridge_app.state, "pipeline", pipeline)
    monkeypatch.setattr(bridge_app, "_cursor_submit_authority", AsyncMock(return_value=None))

    with pytest.raises(asyncio.CancelledError):
        await bridge_app._process_cursor_stop(event, session)

    adapter.consume_followup.assert_called_once_with(
        session.id, trigger_event_id=event.event_id,
    )
