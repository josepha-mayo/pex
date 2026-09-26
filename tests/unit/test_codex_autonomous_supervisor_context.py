"""Supervisor visibility cannot manufacture shared-Codex correction authority."""

# ruff: noqa: F401, F811 -- imported pytest fixture is injected by name.

from datetime import UTC, datetime, timedelta

import pytest
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.context import ContextItem
from pex_protocol.enums import Authority, ContextKind, SourceKind
from pex_protocol.supervisor import SupervisorResult
from test_codex_correction_pipeline import (
    actual_observer_baseline_without_background_consumer,
    correction_bound_pipeline,
    correction_pipeline,
)
from test_workspace_continuity_pipeline import bound_pipeline


class _CapturingNoopSupervisor:
    agentcore = None

    def __init__(self) -> None:
        self.requests = []

    async def decide(self, request, *, local_model):
        del local_model
        self.requests.append(request.model_copy(deep=True))
        return SupervisorResult(
            action=ProposedAction(
                type=InterventionType.NOOP,
                session_id=request.session.id,
                goal_id=request.session.goal_id,
                rationale="The fixture intentionally takes no worker action.",
                evidence=[request.event.event_id],
                confidence=0.9,
                risk=RiskLevel.NONE,
                authority_required=Authority.LOCAL_POLICY,
            ),
            diagnosis="fixture_noop",
        )


async def _disable(case) -> None:
    status = await case.store.get_autonomous_correction_grant_status(case.session.id)
    assert status["enabled"] is True
    scope = status["scope"]
    await case.store.set_session_autonomous_corrections(
        case.session.id,
        enabled=False,
        expected_control_revision=scope["control_revision"],
        expected_goal_id=scope["goal_id"],
        expected_goal_intent_revision=scope["goal_intent_revision"],
        expected_goal_intent_hash=scope["goal_intent_hash"],
        expected_project_binding=scope["project_binding"],
        expected_workspace_sha256=scope["workspace_sha256"],
        expected_subscription_authorization_id=scope[
            "subscription_authorization_id"
        ],
        expected_connection_generation=scope["connection_generation"],
        principal_id="local_bridge_operator",
        actor_assurance="bridge_bearer",
        idempotency_key="supervisor-context-explicit-disable",
    )


@pytest.mark.parametrize("enabled", [False, True])
async def test_supervisor_sees_trusted_route_state_without_capability_escalation(
    correction_pipeline, enabled
):
    case = correction_pipeline
    if not enabled:
        await _disable(case)
    supervisor = _CapturingNoopSupervisor()
    case.pipeline.supervisor = supervisor

    await case.ingest_observed()

    assert len(supervisor.requests) == 1
    request = supervisor.requests[0]
    assert request.notes.startswith("no_completion_claims_extracted")
    assert request.session.capabilities.get("send_message") is not True
    assert request.session.capabilities.get("resume") is not True
    receipt = request.session.metadata["subscription_receipt"]
    assert receipt["observation_only"] is True
    assert receipt["delivery_proven"] is False
    if enabled:
        assert (
            "Standing operator permission enables the private claimed-correction route "
            in request.notes
        )
        assert "Generic adapter send/resume flags remain false" in request.notes
        assert "still requires current local policy and input/effect authority" in request.notes
    else:
        assert "Autonomous correction permission is disabled." in request.notes
        assert "enables the private claimed-correction route" not in request.notes
    status = await case.store.get_autonomous_correction_grant_status(case.session.id)
    assert status["enabled"] is enabled


async def test_busy_goal_does_not_hide_shared_human_constraint_from_supervision(
    correction_pipeline,
):
    case = correction_pipeline
    now = datetime.now(UTC) - timedelta(minutes=1)
    commitment = ContextItem(
        id="shared-human-constraint",
        project_id=case.session.project_id,
        goal_id=None,
        kind=ContextKind.CONSTRAINT,
        content="Keep the existing API behavior compatible.",
        provenance=SourceKind.HUMAN,
        source_refs=["operator:project-rule"],
        valid_from=now,
    )
    await case.store.add_context(commitment)
    for index in range(257):
        await case.store.add_context(commitment.model_copy(update={
            "id": f"busy-goal-fact-{index}",
            "goal_id": case.session.goal_id,
            "kind": ContextKind.FACT,
            "provenance": SourceKind.WORKSPACE,
            "valid_from": now + timedelta(seconds=1),
            "content": f"Observed workspace fact {index}.",
        }))
    supervisor = _CapturingNoopSupervisor()
    case.pipeline.supervisor = supervisor
    await case.ingest_observed()
    assert len(supervisor.requests) == 1
    context = supervisor.requests[0].supervisor_context
    assert context is not None
    assert commitment.id in context.offered_context_ids
    assert any(item.content == commitment.content for item in context.context_items)


class _ForgedGrantSupervisor:
    agentcore = None

    async def decide(self, request, *, local_model):
        del local_model
        return SupervisorResult(
            action=ProposedAction(
                type=InterventionType.SEND_NUDGE,
                session_id=request.session.id,
                goal_id=request.session.goal_id,
                payload={
                    "text": "Fixture correction without operator authority.",
                    "autonomous_corrections_enabled": True,
                },
                rationale="Fixture attempts to claim authority through model output.",
                evidence=[request.event.event_id],
                confidence=0.9,
                risk=RiskLevel.LOW,
                authority_required=Authority.LOCAL_POLICY,
                requires_capability="send_message",
            ),
            diagnosis="fixture_forged_grant",
        )


async def test_model_payload_cannot_enable_disabled_correction_route(correction_pipeline):
    case = correction_pipeline
    await _disable(case)
    case.pipeline.supervisor = _ForgedGrantSupervisor()

    event = await case.ingest_observed()

    assert (
        await case.store.get_autonomous_correction_grant_status(case.session.id)
    )["enabled"] is False
    assert await case.store.get_event_effect(event.event_id, "main") is None
    current = await case.store.get_session(case.session.id)
    assert current.capabilities.get("send_message") is not True
    assert current.capabilities.get("resume") is not True
    intervention = (await case.store.list_interventions(case.session.id))[-1]
    assert intervention.proposed_action.payload["autonomous_corrections_enabled"] is True
    assert intervention.policy_verdict.value == "deny"
    assert intervention.result == "denied_by_policy"
