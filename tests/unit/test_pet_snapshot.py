import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import (
    Pipeline,
    activity_phrase,
    agent_label,
    clip_status_line,
    collapse_live_agents,
    collapse_promptable_agents,
    visible_event_line,
)
from pex_bridge.store import Store
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.session import HarnessEvent, HarnessSession


@pytest.mark.asyncio
async def test_pet_snapshot_uses_last_worker_message(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(timezone.utc)
    session = HarnessSession(
        id="cursor:live",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="live",
        cwd=r"C:\Users\JosephMayo\Projects\pex",
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    await store.upsert_session(session)
    await store.add_event(
        HarnessEvent(
            event_id=uuid4().hex,
            ts=datetime.now(timezone.utc),
            harness_type=HarnessType.CURSOR,
            session_id=session.id,
            event_type=EventType.AGENT_RESPONSE,
            phase=EventPhase.AFTER,
            message_delta="Ran pytest: 92 passed, 2 skipped.",
        )
    )
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings(require_auth=False, home=tmp_path, autonomy="observe"),
    )
    snap = await pipeline.pet_snapshot()
    await store.close()
    assert snap["headline"] == "1 working · 0 need you"
    assert snap["last_source"] == "cursor"
    assert snap["last_message"] == "Ran pytest: 92 passed, 2 skipped."
    assert snap["sessions"][0]["last_message"] == "Ran pytest: 92 passed, 2 skipped."
    assert snap["sessions"][0]["label"] == "pex"
    assert snap["working"] == 1
    assert len(snap["sessions"]) == 1


@pytest.mark.asyncio
async def test_refresh_keeps_hook_working_over_idle_discover(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    session = HarnessSession(
        id="cursor:live",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="live",
        status=SessionStatus.WORKING,
    )
    await store.upsert_session(session)
    registry = AdapterRegistry()
    registry.cursor.sessions[session.id] = HarnessSession(
        id=session.id,
        harness_type=HarnessType.CURSOR,
        vendor_session_id="live",
        status=SessionStatus.IDLE,
    )
    pipeline = Pipeline(
        store,
        registry,
        EventBus(),
        Settings(require_auth=False, home=tmp_path, autonomy="observe"),
    )
    await pipeline.refresh_desktop_sessions()
    kept = await store.get_session(session.id)
    await store.close()
    assert kept is not None
    assert kept.status == SessionStatus.WORKING


def test_clip_status_line_skips_noise():
    assert clip_status_line("ok") is None
    assert clip_status_line("All tests passed. I am done.") == "All tests passed. I am done."
    assert clip_status_line("PEX: the goal is not complete.")  # still a line; skip happens in snapshot
    long = "word " * 80
    clipped = clip_status_line(long)
    assert clipped is not None and clipped.endswith("…") and len(clipped) <= 160


def test_visible_event_line_uses_hook_name():
    event = HarnessEvent(
        event_id="e1",
        ts=datetime.now(timezone.utc),
        harness_type=HarnessType.CURSOR,
        session_id="cursor:live",
        event_type=EventType.AGENT_RESPONSE,
        phase=EventPhase.AFTER,
        metadata={"hook_event_name": "afterAgentResponse"},
    )
    assert visible_event_line(event) == "cursor · agent replied"


def test_collapse_live_agents_hides_hook_spam():
    now = datetime.now(timezone.utc)
    cwd = r"C:\Users\JosephMayo\Projects\pex"
    clones = [
        HarnessSession(
            id=f"cursor:gen-{i}",
            harness_type=HarnessType.CURSOR,
            vendor_session_id=f"gen-{i}",
            cwd=cwd,
            status=SessionStatus.WORKING,
            last_activity=now,
        )
        for i in range(6)
    ]
    live = collapse_live_agents(clones, now)
    assert len(live) == 1
    assert agent_label(live[0]) == "pex"


def test_collapse_live_agents_skips_stale_and_unknown():
    now = datetime.now(timezone.utc)
    stale = HarnessSession(
        id="cursor:old",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="old",
        cwd=r"C:\old",
        status=SessionStatus.WORKING,
        last_activity=now - timedelta(minutes=20),
    )
    unknown = HarnessSession(
        id="cursor:unknown",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="unknown",
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    idle = HarnessSession(
        id="codex:idle",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-1",
        cwd=r"C:\Users\JosephMayo\Projects\pex",
        status=SessionStatus.IDLE,
        last_activity=now,
    )
    live = collapse_live_agents([stale, unknown, idle], now)
    assert live == []
    promptable = collapse_promptable_agents([stale, unknown, idle], now)
    assert [row.id for row in promptable] == ["codex:idle"]


@pytest.mark.asyncio
async def test_pet_snapshot_includes_idle_harness_for_prompts(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(timezone.utc)
    await store.upsert_session(
        HarnessSession(
            id="codex:thread-1",
            harness_type=HarnessType.CODEX,
            vendor_session_id="thread-1",
            cwd=r"C:\Users\JosephMayo\Projects\pex",
            status=SessionStatus.IDLE,
            last_activity=now,
        )
    )
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings(require_auth=False, home=tmp_path, autonomy="observe"),
    )
    snap = await pipeline.pet_snapshot()
    await store.close()
    assert snap["headline"] == "quiet"
    assert snap["sessions"][0]["id"] == "codex:thread-1"
    assert snap["sessions"][0]["activity"] == "Ready for a prompt"


def test_activity_phrase_matches_codex_style():
    now = datetime.now(timezone.utc)
    edit = HarnessEvent(
        event_id="e1",
        ts=now,
        harness_type=HarnessType.CURSOR,
        session_id="cursor:live",
        event_type=EventType.FILE_EDIT,
        file_paths=["a.py"],
    )
    shell = HarnessEvent(
        event_id="e2",
        ts=now,
        harness_type=HarnessType.CURSOR,
        session_id="cursor:live",
        event_type=EventType.SHELL,
        command="pytest",
    )
    assert activity_phrase(edit) == "Edited 1 file"
    assert activity_phrase(shell) == "Ran command"


def test_cursor_hook_ignores_generation_id():
    from pex_bridge.adapters.cursor import CursorAdapter

    adapter = CursorAdapter()
    first = adapter.upsert_from_hook(
        {
            "conversation_id": "conv-1",
            "generation_id": "gen-aaa",
            "workspace_roots": [r"C:\Users\JosephMayo\Projects\pex"],
        }
    )
    second = adapter.upsert_from_hook(
        {
            "generation_id": "gen-bbb",
            "conversation_id": "conv-1",
            "workspace_roots": [r"C:\Users\JosephMayo\Projects\pex"],
        }
    )
    assert first.id == "cursor:conv-1"
    assert second.id == "cursor:conv-1"
    assert list(adapter.sessions) == ["cursor:conv-1"]
