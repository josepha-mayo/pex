"""Live-observation gap: a 'working' worker with no recent events is reported
as observed silence — never as verified work, and never silently green."""

from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import (
    OBSERVATION_GAP_STALL_SECONDS,
    _session_observation,
    create_app,
    state,
    utcnow,
)
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.session import HarnessSession


def _session(status: SessionStatus, age_s: float | None, paused: bool = False) -> HarnessSession:
    now = utcnow()
    return HarnessSession(
        id="opencode:stall-1",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="stall-1",
        status=status,
        supervision_paused=paused,
        last_activity=None if age_s is None else now - timedelta(seconds=age_s),
    )


def test_working_beyond_gap_reports_stalled() -> None:
    now = utcnow()
    obs = _session_observation(
        _session(SessionStatus.WORKING, OBSERVATION_GAP_STALL_SECONDS + 30), now
    )
    assert obs is not None
    assert obs["stalled"] is True
    assert obs["last_event_age_seconds"] >= int(OBSERVATION_GAP_STALL_SECONDS + 30) - 1


def test_working_inside_gap_is_observed_not_stalled() -> None:
    obs = _session_observation(_session(SessionStatus.WORKING, 30), utcnow())
    assert obs is not None
    assert obs["stalled"] is False


@pytest.mark.parametrize(
    "status",
    [
        SessionStatus.STOPPED,
        SessionStatus.DISCOVERED,
        SessionStatus.NEEDS_DECISION,
        SessionStatus.BLOCKED,
        SessionStatus.DRIFTING,
    ],
)
def test_non_live_statuses_carry_no_gap(status: SessionStatus) -> None:
    assert _session_observation(_session(status, 9999), utcnow()) is None


def test_verifying_is_a_live_observed_status() -> None:
    obs = _session_observation(
        _session(SessionStatus.VERIFYING, OBSERVATION_GAP_STALL_SECONDS + 1), utcnow()
    )
    assert obs is not None and obs["stalled"] is True


def test_paused_supervision_suppresses_the_gap() -> None:
    assert _session_observation(
        _session(SessionStatus.WORKING, 9999, paused=True), utcnow()
    ) is None


def test_no_activity_recorded_yields_no_gap() -> None:
    assert _session_observation(_session(SessionStatus.WORKING, None), utcnow()) is None


@pytest.fixture
async def client(tmp_path):
    settings = Settings.for_test(require_auth=False, home=tmp_path)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    await store.connect()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://127.0.0.1",
        ) as c:
            yield c, store
    finally:
        await store.close()


async def test_sessions_endpoint_reports_the_gap(client) -> None:
    http, store = client
    stalled = _session(SessionStatus.WORKING, OBSERVATION_GAP_STALL_SECONDS + 120)
    fresh = HarnessSession(
        id="opencode:fresh-1",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="fresh-1",
        status=SessionStatus.WORKING,
        last_activity=utcnow(),
    )
    await store.upsert_session(stalled)
    await store.upsert_session(fresh)

    detail = (await http.get(f"/v1/sessions/{stalled.id}")).json()
    assert detail["observation"]["stalled"] is True
    assert (
        detail["observation"]["last_event_age_seconds"]
        >= OBSERVATION_GAP_STALL_SECONDS + 120
    )

    listing = {s["id"]: s for s in (await http.get("/v1/sessions")).json()}
    assert listing[stalled.id]["observation"]["stalled"] is True
    assert listing[fresh.id]["observation"]["stalled"] is False
