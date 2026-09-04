from __future__ import annotations

import hashlib
from datetime import timedelta

import pytest
from pex_bridge.store import Store, utcnow
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.context import ContextItem
from pex_protocol.enums import (
    Authority,
    ContextKind,
    EventType,
    HarnessType,
    PolicyVerdict,
    Sensitivity,
)
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessEvent, HarnessSession


def _intervention(
    intervention_id: str,
    *,
    session_id: str,
    goal_id: str,
    created_at,
) -> Intervention:
    action = ProposedAction(
        type=InterventionType.NOOP,
        session_id=session_id,
        goal_id=goal_id,
        rationale="No interruption is justified by the observed evidence.",
        evidence=[f"event:{intervention_id}"],
        confidence=0.9,
        risk=RiskLevel.NONE,
        authority_required=Authority.LOCAL_POLICY,
    )
    return Intervention(
        id=intervention_id,
        session_id=action.session_id,
        goal_id=goal_id,
        trigger="status",
        evidence=action.evidence,
        diagnosis="no_intervention_needed",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="noop",
        created_at=created_at,
    )


def _context(
    context_id: str,
    *,
    project_id: str = "C:/repo",
    goal_id: str | None = "goal-target",
    kind: ContextKind = ContextKind.FACT,
    sensitivity: Sensitivity = Sensitivity.INTERNAL,
) -> ContextItem:
    return ContextItem(
        id=context_id,
        project_id=project_id,
        goal_id=goal_id,
        kind=kind,
        content=f"Observed context {context_id}",
        valid_from=utcnow(),
        sensitivity=sensitivity,
    )


@pytest.mark.asyncio
async def test_canonical_event_and_context_lookups_are_exact_and_bounded(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    event = HarnessEvent(
        event_id="evt-proof",
        ts=utcnow(),
        harness_type=HarnessType.CODEX,
        session_id="codex:proof",
        project_id="C:/repo",
        event_type=EventType.SHELL,
        command="pytest -q",
    )
    context = _context("ctx-proof", goal_id=None)
    try:
        await store.add_event(event)
        await store.add_context(context)

        assert await store.get_event(event.event_id) == event
        assert await store.get_context(context.id) == context
        assert await store.get_event("evt-missing") is None
        assert await store.get_context("ctx-missing") is None

        for invalid in ("", " ", "x" * 513):
            with pytest.raises(ValueError, match="event id is invalid"):
                await store.get_event(invalid)
            with pytest.raises(ValueError, match="context id is invalid"):
                await store.get_context(invalid)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_goal_queries_filter_before_limit_and_preserve_newest_order(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = utcnow()
    sessions = [
        HarnessSession(
            id="codex:target-old",
            harness_type=HarnessType.CODEX,
            vendor_session_id="target-old",
            project_id="C:\\repo\\",
            goal_id="goal-target",
            last_activity=now - timedelta(minutes=4),
        ),
        HarnessSession(
            id="codex:target-new",
            harness_type=HarnessType.CODEX,
            vendor_session_id="target-new",
            cwd="C:/REPO",
            goal_id="goal-target",
            last_activity=now - timedelta(minutes=3),
        ),
        HarnessSession(
            id="codex:wrong-project",
            harness_type=HarnessType.CODEX,
            vendor_session_id="wrong-project",
            project_id="C:/other",
            goal_id="goal-other",
            last_activity=now,
        ),
        HarnessSession(
            id="codex:decoy",
            harness_type=HarnessType.CODEX,
            vendor_session_id="decoy",
            project_id="C:/repo",
            goal_id="goal-decoy",
            last_activity=now + timedelta(minutes=1),
        ),
    ]
    try:
        origin = ProjectOrigin(namespace="machine", host="canonical-query-test")
        for project_id in ("C:/repo", "C:\\repo\\", "C:/REPO"):
            await store.register_project_locator(
                legacy_project_id=project_id,
                locator=ProjectLocator.path(
                    project_id,
                    platform=PathPlatform.WINDOWS,
                    origin=origin,
                ),
                now=now,
            )
        for goal_id, project_id in (
            ("goal-target", "C:/repo"),
            ("goal-other", "C:/other"),
            ("goal-decoy", "C:/repo"),
        ):
            await store.upsert_goal(
                Goal(
                    id=goal_id,
                    project_id=project_id,
                    title=goal_id,
                    objective=f"Exercise canonical queries for {goal_id}.",
                    created_at=now,
                    updated_at=now,
                )
            )
        for session in sessions:
            await store.upsert_session(session)
        for intervention in (
            _intervention(
                "int-target-old",
                session_id="codex:target-old",
                goal_id="goal-target",
                created_at=now - timedelta(minutes=4),
            ),
            _intervention(
                "int-target-new",
                session_id="codex:target-new",
                goal_id="goal-target",
                created_at=now - timedelta(minutes=3),
            ),
            _intervention(
                "int-decoy",
                session_id="codex:decoy",
                goal_id="goal-decoy",
                created_at=now,
            ),
        ):
            await store.add_intervention(intervention)

        first_session = await store.list_sessions_for_goal(
            "goal-target",
            project_id="c:/repo/",
            limit=1,
        )
        second_session = await store.list_sessions_for_goal(
            "goal-target",
            project_id="c:/repo/",
            limit=1,
            offset=1,
        )
        assert [row.id for row in first_session] == ["codex:target-new"]
        assert [row.id for row in second_session] == ["codex:target-old"]

        first_intervention = await store.list_interventions_for_goal(
            "goal-target",
            limit=1,
        )
        second_intervention = await store.list_interventions_for_goal(
            "goal-target",
            limit=1,
            offset=1,
        )
        assert [row.id for row in first_intervention] == ["int-target-new"]
        assert [row.id for row in second_intervention] == ["int-target-old"]

        with pytest.raises(ValueError, match="goal id is invalid"):
            await store.list_sessions_for_goal("")
        with pytest.raises(ValueError, match="project id is invalid"):
            await store.list_sessions_for_goal("goal-target", project_id=" ")
        with pytest.raises(ValueError, match="limit must be between"):
            await store.list_interventions_for_goal("goal-target", limit=0)
        with pytest.raises(ValueError, match="offset cannot be negative"):
            await store.list_interventions_for_goal("goal-target", offset=-1)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_context_kind_counts_cover_full_goal_and_exclude_private_rows(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    public_rows = [_context(f"ctx-fact-{index}") for index in range(1001)]
    public_rows.extend(
        _context(f"ctx-decision-{index}", kind=ContextKind.DECISION)
        for index in range(2)
    )
    excluded_rows = [
        _context("ctx-secret", kind=ContextKind.WARNING, sensitivity=Sensitivity.SECRET),
        _context(
            "ctx-local",
            kind=ContextKind.RESULT,
            sensitivity=Sensitivity.LOCAL_ONLY,
        ),
        _context("ctx-other-goal", goal_id="goal-other"),
        _context(
            "ctx-other-project",
            project_id="C:/other",
            goal_id="goal-other-project",
        ),
    ]
    try:
        now = utcnow()
        for goal_id, project_id in (
            ("goal-target", "C:/repo"),
            ("goal-other", "C:/repo"),
            ("goal-other-project", "C:/other"),
        ):
            await store.upsert_goal(
                Goal(
                    id=goal_id,
                    project_id=project_id,
                    title=goal_id,
                    objective=f"Count context for {goal_id}.",
                    created_at=now,
                    updated_at=now,
                )
            )
        await store.db.executemany(
            "INSERT INTO context_items(id, project_id, project_binding, goal_id, json) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
                    item.id,
                    item.project_id,
                    f"legacy:{hashlib.sha256(item.project_id.encode('utf-8')).hexdigest()}",
                    item.goal_id,
                    item.model_dump_json(),
                )
                for item in [*public_rows, *excluded_rows]
            ],
        )
        await store.db.commit()

        counts = await store.context_kind_counts_for_goal(
            "C:/repo",
            "goal-target",
        )
        assert counts == {"decision": 2, "fact": 1001}

        with pytest.raises(ValueError, match="project id is invalid"):
            await store.context_kind_counts_for_goal("", "goal-target")
        with pytest.raises(ValueError, match="goal id is invalid"):
            await store.context_kind_counts_for_goal("C:/repo", "x" * 513)
    finally:
        await store.close()
