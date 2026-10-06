from __future__ import annotations

import pytest
from pex_bridge.store import Store, utcnow
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessSession


async def _seed(
    store: Store,
    *,
    session_status: SessionStatus = SessionStatus.NEEDS_DECISION,
    replay: bool = False,
    suffix: str = "",
) -> tuple[HarnessSession, Goal]:
    now = utcnow()
    await store.register_project_locator(
        legacy_project_id="escalation-project",
        locator=ProjectLocator.path(
            "/work/escalation-project",
            platform=PathPlatform.POSIX,
            origin=ProjectOrigin(namespace="machine", host="escalation-test"),
        ),
        now=now,
    )
    goal = Goal(
        id=f"goal-escalation{suffix}",
        project_id="escalation-project",
        title="Escalation resolution",
        objective="Route supervisor standoffs to a durable human answer.",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id=f"synthetic:escalation{suffix}",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id=f"escalation{suffix}",
        project_id="escalation-project",
        goal_id=goal.id,
        status=session_status,
        last_activity=now,
        metadata={"replay": True} if replay else {},
    )
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    return session, goal


async def _escalation(
    store: Store,
    session: HarnessSession,
    goal: Goal,
    *,
    intervention_id: str,
    previous_status: str | None = "stopped",
) -> Intervention:
    now = utcnow()
    action = ProposedAction(
        type=InterventionType.ASK_HUMAN,
        session_id=session.id,
        goal_id=goal.id,
        payload=(
            {"previous_session_status": previous_status} if previous_status else {}
        ),
        rationale="A delivered corrective nudge remains disputed and unresolved.",
        evidence=[f"nudge_dispute:{intervention_id}-nudge"],
        confidence=0.8,
        risk=RiskLevel.MEDIUM,
        authority_required=Authority.HUMAN,
    )
    intervention = Intervention(
        id=intervention_id,
        session_id=session.id,
        goal_id=goal.id,
        trigger="stop",
        evidence=action.evidence,
        diagnosis="recorded_replay_deterministic",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ASK_HUMAN,
        result="escalated",
        created_at=now,
    )
    await store.add_intervention(intervention)
    return intervention


@pytest.mark.asyncio
async def test_escalation_resolution_records_answer_and_restores_session(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, goal = await _seed(store, replay=True)
        intervention = await _escalation(
            store, session, goal, intervention_id="int-esc-1"
        )
        resolved_at = utcnow()
        finalized = await store.finalize_escalation_resolution(
            intervention.id,
            answer="Keep the requirement.",
            resolved_at=resolved_at,
            resolved_by="local_operator",
        )
        assert finalized["replayed"] is False
        stored = await store.get_intervention(intervention.id)
        assert stored.result == "human_answered"
        assert stored.outcome == "human_answered"
        assert stored.metadata["human_resolution"]["answer"] == "Keep the requirement."
        restored = await store.get_session(session.id)
        assert restored.status == SessionStatus.STOPPED

        same = await store.finalize_escalation_resolution(
            intervention.id,
            answer="Keep the requirement.",
            resolved_at=utcnow(),
            resolved_by="local_operator",
        )
        assert same["replayed"] is True
        with pytest.raises(PermissionError):
            await store.finalize_escalation_resolution(
                intervention.id,
                answer="Amend the goal.",
                resolved_at=utcnow(),
                resolved_by="local_operator",
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_escalation_resolution_waits_for_other_pending_cards(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, goal = await _seed(store)
        first = await _escalation(
            store, session, goal, intervention_id="int-esc-a"
        )
        await _escalation(store, session, goal, intervention_id="int-esc-b")
        finalized = await store.finalize_escalation_resolution(
            first.id,
            answer="Keep the requirement.",
            resolved_at=utcnow(),
            resolved_by="local_operator",
        )
        assert finalized["replayed"] is False
        restored = await store.get_session(session.id)
        assert restored.status == SessionStatus.NEEDS_DECISION
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_escalation_resolution_leaves_stopped_live_session_alone(tmp_path):
    """A live session that kept its terminal STOPPED status must not revive."""
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, goal = await _seed(
            store, session_status=SessionStatus.STOPPED
        )
        intervention = await _escalation(
            store,
            session,
            goal,
            intervention_id="int-esc-live",
            previous_status=None,
        )
        finalized = await store.finalize_escalation_resolution(
            intervention.id,
            answer="Keep the requirement.",
            resolved_at=utcnow(),
            resolved_by="local_operator",
        )
        assert finalized["replayed"] is False
        stored = await store.get_intervention(intervention.id)
        assert stored.result == "human_answered"
        still_stopped = await store.get_session(session.id)
        assert still_stopped.status == SessionStatus.STOPPED
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_escalation_resolution_rejects_missing_and_foreign_cards(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session, goal = await _seed(store)
        nudge = Intervention(
            id="int-nudge-only",
            session_id=session.id,
            goal_id=goal.id,
            trigger="observe",
            evidence=["acceptance_surface_modified:tests/test_core.py"],
            diagnosis="acceptance surface modified",
            proposed_action=ProposedAction(
                type=InterventionType.SEND_NUDGE,
                session_id=session.id,
                goal_id=goal.id,
                rationale="Restore the sealed test.",
                evidence=["acceptance_surface_modified:tests/test_core.py"],
                confidence=0.9,
                risk=RiskLevel.LOW,
                authority_required=Authority.LOCAL_POLICY,
                reversible=False,
            ),
            confidence=0.9,
            risk=RiskLevel.LOW.value,
            reversible=False,
            authority_required=Authority.LOCAL_POLICY.value,
            action_taken=InterventionType.SEND_NUDGE.value,
            policy_verdict=PolicyVerdict.ALLOW,
            result="sent",
            created_at=utcnow(),
        )
        await store.add_intervention(nudge)
        with pytest.raises(LookupError):
            await store.finalize_escalation_resolution(
                "int-missing",
                answer="Keep the requirement.",
                resolved_at=utcnow(),
                resolved_by="local_operator",
            )
        with pytest.raises(PermissionError):
            await store.finalize_escalation_resolution(
                nudge.id,
                answer="Keep the requirement.",
                resolved_at=utcnow(),
                resolved_by="local_operator",
            )
    finally:
        await store.close()
