import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.base import HarnessAdapter
from pex_bridge.app import state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import (
    Pipeline,
    activity_phrase,
    agent_label,
    clip_status_line,
    collapse_live_agents,
    collapse_promptable_agents,
    pet_transition,
    visible_event_line,
)
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.enums import (
    Authority,
    EventPhase,
    EventType,
    HarnessType,
    PolicyVerdict,
    SessionStatus,
)
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession

PET_GOAL_ID = "goal-pet-state"


class DelayedDiscoveryAdapter(HarnessAdapter):
    def __init__(self, name: str, delay: float) -> None:
        self.name = name
        self.delay = delay

    async def probe(self) -> AdapterCapabilities:
        return AdapterCapabilities(notes="test")

    async def discover_sessions(self) -> list[HarnessSession]:
        await asyncio.sleep(self.delay)
        return []


def _pet_intervention(
    action_type: InterventionType,
    *,
    result: str,
    trigger: str = "stop",
    created_at: datetime | None = None,
    metadata: dict | None = None,
    diagnosis: str = "pet_transition_test",
    evidence: list[str] | None = None,
) -> Intervention:
    action = ProposedAction(
        type=action_type,
        session_id="codex:pet-state",
        goal_id=PET_GOAL_ID,
        rationale="Observed pet transition test.",
        evidence=evidence or ["event:pet-state"],
        confidence=0.9,
        risk=RiskLevel.NONE,
        authority_required=Authority.LOCAL_POLICY,
    )
    return Intervention(
        id=f"int_{action_type.value.lower()}",
        session_id=action.session_id,
        goal_id=PET_GOAL_ID,
        trigger=trigger,
        evidence=action.evidence,
        diagnosis=diagnosis,
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action_type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result=result,
        created_at=created_at or datetime.now(UTC),
        metadata=metadata or {},
    )


def test_pet_transition_exposes_recent_audited_states_and_expires_them():
    now = datetime.now(UTC)
    handoff = _pet_intervention(
        InterventionType.FRESH_HANDOFF,
        result="handoff_injected",
        created_at=now,
    )
    approved = _pet_intervention(
        InterventionType.RESPOND_PERMISSION,
        result="permission_allow",
        trigger="permission_request",
        created_at=now,
    )
    observed = _pet_intervention(
        InterventionType.NOOP,
        result="noop",
        created_at=now,
        metadata={
            "verification": {
                "status": "uncertain",
                "evidence_gathering": {"state": "inspected"},
            }
        },
    )

    assert pet_transition(handoff, now) == ("handoff", "Context moved → Codex")
    assert pet_transition(approved, now) == ("approved", "Codex permission handled")
    assert pet_transition(observed, now) == (
        "observing",
        "Evidence inspected → no action needed",
    )
    nudge = _pet_intervention(
        InterventionType.SEND_NUDGE,
        result="sent",
        created_at=now,
        diagnosis="Repeated command drift on train.py",
        evidence=["drift=0.4", "repeated_command_count=3"],
    )
    assert pet_transition(nudge, now) == (None, None)
    assert pet_transition(handoff, now + timedelta(seconds=13)) == (None, None)


def test_pet_decoration_preserves_transition_with_safety_priority():
    base = {
        "headline": "Context moved → Codex",
        "working": 1,
        "drifting": 0,
        "blocked": 0,
        "needs_you": 0,
        "mood": "handoff",
        "last_action": None,
        "sessions": [],
    }

    assert state.decorate_pet(dict(base))["mood"] == "handoff"
    assert state.decorate_pet({**base, "mood": "approved"})["mood"] == "approved"
    assert state.decorate_pet({**base, "needs_you": 1})["mood"] == "decision"
    assert state.decorate_pet({**base, "blocked": 1})["mood"] == "warning"


@pytest.mark.asyncio
async def test_pet_snapshot_emits_transition_but_never_hides_human_decision(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    await store.upsert_goal(
        Goal(
            id=PET_GOAL_ID,
            project_id=str(tmp_path),
            title="Render the current pet state",
            objective="Show recent supervised transitions without hiding decisions.",
            created_at=now,
            updated_at=now,
        )
    )
    session = HarnessSession(
        id="codex:pet-state",
        harness_type=HarnessType.CODEX,
        vendor_session_id="pet-state",
        project_id=str(tmp_path),
        goal_id=PET_GOAL_ID,
        cwd=str(tmp_path),
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    await store.upsert_session(session)
    await store.add_intervention(
        _pet_intervention(
            InterventionType.FRESH_HANDOFF,
            result="handoff_injected",
            created_at=now,
        )
    )
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="observe"),
    )

    transition = await pipeline.pet_snapshot()
    assert transition["mood"] == "handoff"
    assert transition["headline"] == "Context moved → Codex"

    session.status = SessionStatus.NEEDS_DECISION
    await store.upsert_session(session)
    decision = await pipeline.pet_snapshot()
    await store.close()
    assert decision["mood"] == "decision"
    assert decision["headline"] == "Codex needs a decision"


@pytest.mark.asyncio
async def test_pet_snapshot_does_not_claim_drift_corrected_from_a_nudge(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    await store.upsert_goal(
        Goal(
            id=PET_GOAL_ID,
            project_id=str(tmp_path),
            title="Render the current pet state",
            objective="Do not claim a drift correction from a nudge alone.",
            created_at=now,
            updated_at=now,
        )
    )
    session = HarnessSession(
        id="codex:pet-state",
        harness_type=HarnessType.CODEX,
        vendor_session_id="pet-state",
        project_id=str(tmp_path),
        goal_id=PET_GOAL_ID,
        cwd=str(tmp_path),
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    await store.upsert_session(session)
    nudge = _pet_intervention(
        InterventionType.SEND_NUDGE,
        result="sent",
        created_at=now,
        diagnosis="Repeated command drift on train.py",
        evidence=["drift=0.4", "repeated_command_count=3"],
    )
    await store.add_intervention(nudge)
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="observe"),
    )
    snap = await pipeline.pet_snapshot()
    await store.close()
    assert "corrected" not in (snap["headline"] or "").casefold()
    assert snap["headline"] == "1 working · 0 need you"
    assert snap["mood"] == "working"


@pytest.mark.asyncio
async def test_pet_snapshot_names_a_drifting_session_in_the_present_tense(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    session = HarnessSession(
        id="codex:pet-state",
        harness_type=HarnessType.CODEX,
        vendor_session_id="pet-state",
        cwd=str(tmp_path),
        status=SessionStatus.DRIFTING,
        last_activity=now,
    )
    await store.upsert_session(session)
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="observe"),
    )
    snap = await pipeline.pet_snapshot()
    await store.close()
    assert snap["headline"] == "Codex drifting"
    assert snap["mood"] == "drift"
    assert snap["drifting"] == 1
    assert snap["working"] == 0
    assert "corrected" not in (snap["headline"] or "").casefold()


@pytest.mark.asyncio
async def test_pet_snapshot_uses_last_worker_message(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    goal = Goal(
        id="goal-current-worker-message",
        project_id=str(tmp_path),
        title="pex",
        objective="Project only authority-bound worker evidence.",
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    session = HarnessSession(
        id="cursor:live",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="live",
        project_id=goal.project_id,
        goal_id=goal.id,
        cwd=goal.project_id,
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    await store.upsert_session(session)
    await store.accept_pipeline_event(
        HarnessEvent(
            event_id=uuid4().hex,
            ts=datetime.now(UTC),
            harness_type=HarnessType.CURSOR,
            session_id=session.id,
            project_id=goal.project_id,
            goal_id=goal.id,
            event_type=EventType.AGENT_RESPONSE,
            phase=EventPhase.AFTER,
            message_delta="Ran pytest: 92 passed, 2 skipped.",
        ),
        session_snapshot=session,
    )
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="observe"),
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
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="observe"),
    )
    await pipeline.refresh_desktop_sessions()
    kept = await store.get_session(session.id)
    await store.close()
    assert kept is not None
    assert kept.status == SessionStatus.WORKING


@pytest.mark.asyncio
async def test_desktop_refresh_discovers_adapters_concurrently(tmp_path, monkeypatch):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    registry = AdapterRegistry()
    for name in (
        "cursor",
        "codex",
        "opencode",
        "hermes",
        "claude_code",
    ):
        registry.bind(name, DelayedDiscoveryAdapter(name, 0.1))
    pipeline = Pipeline(
        store,
        registry,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="observe"),
    )
    monkeypatch.setattr("pex_bridge.pipeline.DESKTOP_DISCOVERY_TIMEOUT_SECONDS", 0.2)
    started = asyncio.get_running_loop().time()
    await pipeline.refresh_desktop_sessions()
    elapsed = asyncio.get_running_loop().time() - started
    await store.close()
    assert elapsed < 0.25


def test_clip_status_line_skips_noise():
    assert clip_status_line("ok") is None
    assert clip_status_line("All tests passed. I am done.") == "All tests passed. I am done."
    assert clip_status_line(
        "PEX: the goal is not complete."
    )  # still a line; skip happens in snapshot
    long = "word " * 80
    clipped = clip_status_line(long)
    assert clipped is not None and clipped.endswith("…") and len(clipped) <= 160


def test_visible_event_line_uses_hook_name():
    event = HarnessEvent(
        event_id="e1",
        ts=datetime.now(UTC),
        harness_type=HarnessType.CURSOR,
        session_id="cursor:live",
        event_type=EventType.AGENT_RESPONSE,
        phase=EventPhase.AFTER,
        metadata={"hook_event_name": "afterAgentResponse"},
    )
    assert visible_event_line(event) == "cursor · agent replied"


def test_collapse_live_agents_hides_hook_spam():
    now = datetime.now(UTC)
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
    now = datetime.now(UTC)
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


def test_confirmed_shared_codex_is_promptable_before_first_observed_event():
    session = HarnessSession(
        id="codex:shared-thread",
        harness_type=HarnessType.CODEX,
        vendor_session_id="shared-thread",
        cwd=r"C:\Users\JosephMayo\Projects\pex",
        status=SessionStatus.IDLE,
        last_activity=None,
        metadata={"connection_kind": "codex_shared"},
    )

    assert collapse_promptable_agents([session]) == [session]


def test_unconfirmed_idle_codex_without_activity_remains_hidden():
    session = HarnessSession(
        id="codex:historical-thread",
        harness_type=HarnessType.CODEX,
        vendor_session_id="historical-thread",
        status=SessionStatus.IDLE,
        last_activity=None,
    )

    assert collapse_promptable_agents([session]) == []


@pytest.mark.asyncio
async def test_pet_snapshot_includes_idle_harness_for_prompts(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
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
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="observe"),
    )
    snap = await pipeline.pet_snapshot()
    await store.close()
    assert snap["headline"] == "quiet"
    assert snap["sessions"][0]["id"] == "codex:thread-1"
    assert snap["sessions"][0]["activity"] == "Ready for a prompt"


def test_activity_phrase_matches_codex_style():
    now = datetime.now(UTC)
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
