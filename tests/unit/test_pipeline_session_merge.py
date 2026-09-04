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
        project_id=str(tmp_path),
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
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
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


@pytest.mark.asyncio
async def test_progress_event_does_not_pollute_intervention_log_with_noop(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    session = HarnessSession(
        id="codex:progress",
        harness_type=HarnessType.CODEX,
        vendor_session_id="progress",
        project_id=str(tmp_path),
        cwd=str(tmp_path),
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    event = HarnessEvent(
        event_id="progress-event",
        ts=now,
        harness_type=HarnessType.CODEX,
        session_id=session.id,
        event_type=EventType.AGENT_RESPONSE,
        message_delta="I am still working on the requested file.",
    )
    try:
        intervention = await pipeline.ingest_event(event, session)
        assert intervention is None
        assert await store.list_interventions(session.id) == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_ingest_persists_context_routing_state_across_adapter_snapshots(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    goal = Goal(
        id="goal-routing-state",
        project_id=str(tmp_path),
        title="Keep routing state durable",
        objective="Preserve the active task and files across adapter snapshots.",
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    session = HarnessSession(
        id="codex:routing-state",
        harness_type=HarnessType.CODEX,
        vendor_session_id="routing-state",
        project_id=str(tmp_path),
        goal_id=goal.id,
        cwd=str(tmp_path),
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    await store.upsert_session(session)
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    prompt = HarnessEvent(
        event_id="routing-prompt",
        ts=now,
        harness_type=HarnessType.CODEX,
        session_id=session.id,
        event_type=EventType.USER_PROMPT,
        message_delta="Work only on the frontend pet sprites atlas.",
    )
    adapter_snapshot = HarnessSession(
        id=session.id,
        harness_type=HarnessType.CODEX,
        vendor_session_id=session.vendor_session_id,
        project_id=session.project_id,
        cwd=session.cwd,
        status=SessionStatus.WORKING,
    )
    edit = HarnessEvent(
        event_id="routing-edit",
        ts=now,
        harness_type=HarnessType.CODEX,
        session_id=session.id,
        event_type=EventType.FILE_EDIT,
        file_paths=["apps/desktop/src/pets/atlas.tsx"],
    )
    try:
        await pipeline.ingest_event(prompt, session)
        await pipeline.ingest_event(edit, adapter_snapshot)
        saved = await store.get_session(session.id)
        assert saved is not None
        assert saved.metadata["current_task"] == prompt.message_delta
        assert saved.metadata["active_files"] == ["apps/desktop/src/pets/atlas.tsx"]
        assert saved.metadata["task_phase"] == "implementation"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_duplicate_stop_event_is_idempotent(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    goal = Goal(
        id="goal_duplicate",
        project_id=str(tmp_path),
        title="report",
        objective="Create report.txt containing shipped.",
        acceptance_criteria=["report.txt contains shipped"],
        evidence_requirements=["report.txt"],
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    session = HarnessSession(
        id="codex:duplicate",
        harness_type=HarnessType.CODEX,
        vendor_session_id="duplicate",
        project_id=str(tmp_path),
        goal_id=goal.id,
        cwd=str(tmp_path),
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    await store.upsert_session(session)
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    event = HarnessEvent(
        event_id="same-stop-event",
        ts=now,
        harness_type=HarnessType.CODEX,
        session_id=session.id,
        event_type=EventType.STOP,
        phase=EventPhase.TERMINAL,
        message_delta="I am done.",
    )
    try:
        first = await pipeline.ingest_event(event, session)
        second = await pipeline.ingest_event(event, session)

        assert first is not None
        assert second == first
        assert len(await store.list_interventions(session.id)) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_ingest_persists_measured_context_health(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    goal = Goal(
        id=new_id("goal_"),
        project_id=str(tmp_path),
        title="Parser",
        objective="Keep schema.json as the source of truth.",
        acceptance_criteria=["parser tests pass"],
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    session = HarnessSession(
        id="synthetic:health",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="health",
        project_id=str(tmp_path),
        goal_id=goal.id,
        cwd=str(tmp_path),
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    await store.upsert_session(session)
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    fact = "schema.json is the source of truth for the parser."
    events = [
        HarnessEvent(
            event_id="edit",
            ts=now,
            harness_type=HarnessType.SYNTHETIC,
            session_id=session.id,
            event_type=EventType.FILE_EDIT,
            phase=EventPhase.DURING,
            message_delta=fact,
            file_paths=["src/schema.json"],
        ),
        HarnessEvent(
            event_id="compact-1",
            ts=now,
            harness_type=HarnessType.SYNTHETIC,
            session_id=session.id,
            event_type=EventType.COMPACTION,
            phase=EventPhase.DURING,
            message_delta="Compacting context.",
        ),
        HarnessEvent(
            event_id="read-1",
            ts=now,
            harness_type=HarnessType.SYNTHETIC,
            session_id=session.id,
            event_type=EventType.FILE_READ,
            phase=EventPhase.DURING,
            message_delta="Read schema.json",
            file_paths=["src/schema.json"],
        ),
        HarnessEvent(
            event_id="read-2",
            ts=now,
            harness_type=HarnessType.SYNTHETIC,
            session_id=session.id,
            event_type=EventType.FILE_READ,
            phase=EventPhase.DURING,
            message_delta="Read schema.json again",
            file_paths=["src/schema.json"],
        ),
    ]
    try:
        for event in events:
            await pipeline.ingest_event(event, session)
        saved = await store.get_session(session.id)
        assert saved is not None
        assert saved.context_health < 1.0
        signals = saved.metadata.get("context_health_signals") or {}
        assert signals.get("compaction_count") == 1
        assert signals.get("forgotten_fact_count") == 1
        assert signals.get("summary_depth") is None
        assert signals.get("token_utilization") is None
    finally:
        await store.close()
