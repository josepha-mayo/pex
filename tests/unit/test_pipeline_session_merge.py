from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store, new_id
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession


@pytest.mark.asyncio
async def test_ingest_copies_goal_and_cwd_from_store(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    goal = Goal(
        id=new_id("goal_"),
        project_id=str(tmp_path),
        title="report",
        objective="Create report.txt containing exactly the word shipped.",
        acceptance_criteria=["report.txt contains shipped"],
        evidence_requirements=["report.txt"],
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    stored = HarnessSession(
        id="opencode:sess_merge",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="sess_merge",
        goal_id=goal.id,
        cwd=str(tmp_path),
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    await store.upsert_session(stored)
    incoming = HarnessSession(
        id=stored.id,
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="sess_merge",
        status=SessionStatus.WORKING,
    )
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    event = HarnessEvent(
        event_id=uuid4().hex,
        ts=now,
        harness_type=HarnessType.OPENCODE,
        session_id=stored.id,
        event_type=EventType.STOP,
        phase=EventPhase.TERMINAL,
        message_delta="I am done.",
    )
    try:
        await pipeline.ingest_event(event, incoming)
        saved = await store.get_session(stored.id)
        assert saved is not None
        assert saved.goal_id == goal.id
        assert saved.cwd == str(tmp_path)
        rows = await store.list_interventions(stored.id)
        assert rows
        assert rows[0].goal_id == goal.id
    finally:
        await store.close()
