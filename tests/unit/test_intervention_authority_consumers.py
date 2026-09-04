from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.decisions import DecisionResolutionError, resolve_lifecycle_decision
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import ProjectIdentityBlockedError, Store, utcnow
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import (
    Authority,
    EventPhase,
    EventType,
    PolicyVerdict,
)
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessEvent


def _lifecycle_intervention(session, *, intervention_id: str) -> Intervention:
    action = ProposedAction(
        type=InterventionType.START_AGENT,
        session_id=session.id,
        goal_id=session.goal_id,
        payload={
            "project": session.project_id,
            "prompt": "Run one bounded probe.",
            "config": {"goal_id": session.goal_id},
        },
        rationale="A separate bounded probe requires explicit human authority.",
        evidence=["event:bounded-probe"],
        confidence=0.9,
        risk=RiskLevel.LOW,
        authority_required=Authority.HUMAN,
    )
    return Intervention(
        id=intervention_id,
        session_id=session.id,
        goal_id=session.goal_id,
        trigger="status",
        evidence=action.evidence,
        diagnosis="bounded_probe_requested",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ASK_HUMAN,
        result="awaiting_human",
        created_at=utcnow(),
    )


@pytest.mark.asyncio
async def test_rebound_intervention_blocks_pipeline_observation_and_lifecycle_dispatch(
    tmp_path,
):
    project_id = "legacy-intervention-project"
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    await store.connect()
    try:
        now = utcnow()
        goal = Goal(
            id="goal-intervention-authority",
            project_id=project_id,
            title="Keep intervention evidence isolated",
            objective="Never apply project A intervention evidence to project B.",
            created_at=now,
            updated_at=now,
        )
        await store.upsert_goal(goal)
        session = adapters.synthetic.seed_session(
            vendor_id="intervention-authority",
            project_id=project_id,
            goal_id=goal.id,
        )
        await store.upsert_session(session)
        intervention = _lifecycle_intervention(
            session,
            intervention_id="int-intervention-authority",
        )
        await store.add_intervention(intervention)

        await store.register_project_locator(
            legacy_project_id=project_id,
            locator=ProjectLocator.path(
                "/workspace/rebound-intervention-project",
                platform=PathPlatform.POSIX,
                origin=ProjectOrigin(
                    namespace="machine",
                    host="intervention-consumer-test",
                ),
            ),
        )

        executor = SimpleNamespace(execute=AsyncMock())
        with pytest.raises(DecisionResolutionError) as blocked:
            await resolve_lifecycle_decision(
                store,
                adapters,
                executor,
                intervention_id=intervention.id,
                decision="allow",
            )
        assert blocked.value.status_code == 409
        assert blocked.value.code == "artifact_project_identity_changed"
        executor.execute.assert_not_awaited()
        assert await store.get_lifecycle_resolution(intervention.id) is None

        pipeline = Pipeline(
            store,
            adapters,
            EventBus(),
            Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
        )
        event = HarnessEvent(
            event_id="event-intervention-authority",
            ts=utcnow(),
            harness_type=session.harness_type,
            session_id=session.id,
            project_id=project_id,
            goal_id=goal.id,
            event_type=EventType.AGENT_RESPONSE,
            phase=EventPhase.AFTER,
            message_delta="This must not update project A intervention evidence.",
        )
        with pytest.raises(ProjectIdentityBlockedError) as observation_blocked:
            await pipeline._observe_prior_intervention(session, event)
        assert observation_blocked.value.code == "artifact_project_identity_changed"
        forensic = await store.get_intervention(intervention.id)
        assert forensic is not None
        assert not forensic.worker_response
        assert "outcome_event_ids" not in forensic.metadata
    finally:
        await store.close()


def test_operational_consumers_have_no_forensic_intervention_fallbacks():
    pipeline_methods = (
        Pipeline._drain_event_and_followups,
        Pipeline._build_and_commit_event_plan,
        Pipeline._resume_planned_event,
        Pipeline._observe_prior_intervention,
        Pipeline._delivered_context_item_ids,
    )
    for method in pipeline_methods:
        source = inspect.getsource(method)
        assert ".get_intervention(" not in source
        assert ".list_interventions(" not in source

    from pex_bridge import decisions, mcp_server

    decisions_source = inspect.getsource(decisions)
    assert ".get_intervention(" not in decisions_source
    assert "get_intervention_for_authority" in decisions_source
    assert "get_session_for_authority" in decisions_source

    authority_loader = inspect.getsource(decisions._session_for_intervention_authority)
    assert ".get_session(" not in authority_loader
    assert "get_session_for_authority" in authority_loader

    lifecycle_source = inspect.getsource(decisions.resolve_lifecycle_decision)
    authority_check = lifecycle_source.index("_session_for_intervention_authority")
    external_effect = lifecycle_source.index("executor.execute")
    assert authority_check < external_effect

    mcp_source = inspect.getsource(mcp_server)
    assert ".list_interventions_for_goal(" not in mcp_source
    assert "list_interventions_for_goal_for_authority" in mcp_source
