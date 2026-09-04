from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store, utcnow
from pex_protocol.enums import EventType, HarnessType
from pex_protocol.session import HarnessEvent


def _event(event_id: str, session_id: str, seconds: int) -> HarnessEvent:
    return HarnessEvent(
        event_id=event_id,
        ts=utcnow() - timedelta(seconds=seconds),
        harness_type=HarnessType.SYNTHETIC,
        session_id=session_id,
        project_id="demo",
        event_type=EventType.AGENT_RESPONSE,
        message_delta=event_id,
    )


@pytest.mark.asyncio
async def test_event_page_uses_acceptance_order_and_frozen_through(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        # Vendor timestamps intentionally run opposite to acceptance order.
        await store.add_event(_event("evt-a", "synthetic:a", 1))
        await store.add_event(_event("evt-b", "synthetic:a", 20))
        await store.add_event(_event("evt-c", "synthetic:b", 10))

        assert [event.event_id for event in await store.recent_events("synthetic:a")] == [
            "evt-a",
            "evt-b",
        ]
        assert [event.event_id for event in await store.latest_events()] == [
            "evt-c",
            "evt-b",
            "evt-a",
        ]

        first = await store.event_publication_page(after=0, limit=2)
        assert [row["event"]["event_id"] for row in first["items"]] == [
            "evt-a",
            "evt-b",
        ]
        assert first["after"] == "0"
        assert first["through"] == "3"
        assert first["next"] == "2"
        assert first["has_more"] is True

        await store.add_event(_event("evt-d", "synthetic:a", 30))
        second = await store.event_publication_page(
            after=int(first["next"]),
            through=int(first["through"]),
            limit=2,
        )
        assert [row["event"]["event_id"] for row in second["items"]] == ["evt-c"]
        assert second["through"] == "3"
        assert second["watermark"] == "4"
        assert second["has_more"] is False
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_event_page_scope_validation_and_publication_backfill(tmp_path):
    path = tmp_path / "pex.sqlite"
    first = Store(path)
    await first.connect()
    await first.add_event(_event("evt-a", "synthetic:a", 1))
    await first.add_event(_event("evt-b", "synthetic:b", 2))
    await first.close()

    reopened = Store(path)
    await reopened.connect()
    try:
        scoped = await reopened.event_publication_page(
            after=0,
            limit=10,
            session_id="synthetic:b",
        )
        assert [row["event"]["event_id"] for row in scoped["items"]] == ["evt-b"]
        assert scoped["scope"] == {"session_id": "synthetic:b"}
        assert scoped["gap"] == {"detected": False}
        with pytest.raises(ValueError, match="after exceeds through"):
            await reopened.event_publication_page(after=2, through=1)
        with pytest.raises(ValueError, match="exceeds the current watermark"):
            await reopened.event_publication_page(after=0, through=99)
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_get_events_exposes_decimal_cursors_and_rejects_bad_ranges(tmp_path):
    settings = Settings.for_test(require_auth=False, home=tmp_path)
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    state.settings = settings
    state.store = store
    state.adapters = AdapterRegistry()
    state.pipeline = Pipeline(store, state.adapters, EventBus(), settings)
    await store.add_event(_event("evt-http", "synthetic:http", 1))
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://127.0.0.1",
        ) as client:
            response = await client.get("/v1/events", params={"after": "0"})
            assert response.status_code == 200
            body = response.json()
            assert body["items"][0]["cursor"] == "1"
            assert body["items"][0]["event"]["event_id"] == "evt-http"
            assert isinstance(body["through"], str)
            assert (
                await client.get(
                    "/v1/events",
                    params={"after": "2", "through": "1"},
                )
            ).status_code == 400
            assert (
                await client.get("/v1/events", params={"after": "01"})
            ).status_code == 422
    finally:
        await state.pipeline.close_presentations()
        await store.close()


@pytest.mark.asyncio
async def test_event_page_reports_retention_gap_instead_of_silent_skip(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await store.add_event(_event("evt-pruned", "synthetic:a", 2))
        await store.add_event(_event("evt-kept", "synthetic:a", 1))
        await store.db.execute(
            "DELETE FROM event_publications WHERE event_id = ?",
            ("evt-pruned",),
        )
        await store.db.commit()

        page = await store.event_publication_page(after=0, limit=10)
        assert page["items"] == []
        assert page["gap"] == {
            "detected": True,
            "requested_after": "0",
            "earliest_available": "2",
        }
        resumed = await store.event_publication_page(after=1, limit=10)
        assert resumed["gap"] == {"detected": False}
        assert resumed["items"][0]["event"]["event_id"] == "evt-kept"
    finally:
        await store.close()
