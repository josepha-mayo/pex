from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.adapters.codex_subscription import _stable_record_id, shared_live_event_id
from pex_bridge.pipeline import Pipeline
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import EventPhase, EventType, HarnessType, PolicyVerdict
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.verification import (
    EvidenceGatheringReceipt,
    EvidenceGatheringState,
    VerificationBackendKind,
    VerificationExecutionReceipt,
    VerificationExecutionResult,
    VerificationProbe,
    VerificationProbeKind,
)
from test_codex_subscription import _notification, _subscribed


def _pipeline_with(prior: Intervention) -> Pipeline:
    pipeline = object.__new__(Pipeline)
    pipeline.store = AsyncMock()
    pipeline.store.list_interventions_for_authority.return_value = [prior]
    return pipeline


def _session(harness: HarnessType, workspace: str) -> HarnessSession:
    return HarnessSession(
        id=f"{harness.value}:worker",
        vendor_session_id="worker",
        harness_type=harness,
        project_id=workspace,
        cwd=workspace,
        goal_id="goal-causal-proof",
    )


def _completed_verification_request(
    session: HarnessSession,
    created_at: datetime,
) -> Intervention:
    probe = VerificationProbe(
        id="probe-causal-proof",
        kind=VerificationProbeKind.PYTEST,
        harness_type=session.harness_type,
        session_id=session.id,
        project_id=session.project_id,
        goal_id=session.goal_id,
        request_event_id="request-stop",
        cwd=session.cwd,
        relative_targets=[],
    )
    execution = VerificationExecutionReceipt(
        backend=VerificationBackendKind.HARNESS,
        policy_verdict=PolicyVerdict.ALLOW,
        source_event_id="pytest-source",
        observed_at=created_at + timedelta(seconds=1),
        observed_command="pytest -q",
        cwd=session.cwd,
        process_started=True,
        exit_code=0,
        result=VerificationExecutionResult.PASSED,
    )
    gathering = EvidenceGatheringReceipt(
        state=EvidenceGatheringState.EXECUTED,
        probe=probe,
        execution=execution,
        sources=["harness_execution"],
    )
    action = ProposedAction(
        type=InterventionType.REQUEST_VERIFICATION,
        session_id=session.id,
        goal_id=session.goal_id,
        payload={"text": "Run the requested verification."},
        rationale="The worker claim needs independent evidence.",
        evidence=["claim:tests-pass"],
    )
    metadata = {
        "trigger_event_id": "request-stop",
        "verification": {
            "evidence_gathering": gathering.model_dump(mode="json"),
        },
    }
    if session.harness_type == HarnessType.SYNTHETIC:
        metadata["worker_delivery_receipt"] = {
            "schema": "pex.worker-delivery.v1",
            "target_session_id": session.id,
            "vendor_session_id": session.vendor_session_id,
            "vendor_turn_id": "synthetic-turn",
        }
    return Intervention(
        id=f"verification-{session.harness_type.value}",
        session_id=session.id,
        goal_id=session.goal_id,
        trigger=EventType.STOP.value,
        evidence=action.evidence,
        diagnosis=action.rationale,
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="verification_requested",
        created_at=created_at,
        metadata=metadata,
    )


def _later_stop(session: HarnessSession, created_at: datetime) -> HarnessEvent:
    return HarnessEvent(
        event_id="later-stop",
        ts=created_at + timedelta(seconds=2),
        session_id=session.id,
        harness_type=session.harness_type,
        project_id=session.project_id,
        goal_id=session.goal_id,
        event_type=EventType.STOP,
        phase=EventPhase.TERMINAL,
        message_delta="Everything passes.",
    )


def _supported_verification() -> dict:
    return {
        "status": "supported",
        "acceptance_status": "supported",
        "pytest_event_id": "pytest-source",
        "evidence_gathering": EvidenceGatheringReceipt(
            state=EvidenceGatheringState.INSPECTED,
            sources=["recent_events"],
            recent_events="inspected",
            claim_count=1,
            reason="bounded_existing_evidence_only",
        ).model_dump(mode="json"),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", [HarnessType.SYNTHETIC, HarnessType.CURSOR])
async def test_generic_stop_cannot_claim_a_delivered_verification_helped(
    harness: HarnessType,
    tmp_path,
):
    created_at = datetime.now(UTC)
    session = _session(harness, str(tmp_path))
    prior = _completed_verification_request(session, created_at)

    updates = await _pipeline_with(prior)._observe_prior_intervention(
        session,
        _later_stop(session, created_at),
        _supported_verification(),
        persist=False,
    )

    assert len(updates) == 1
    assert updates[0].helped is None
    assert updates[0].outcome == "post_delivery_activity_observed_causality_unavailable"
    assert updates[0].metadata["causal_continuation_proven"] is False
    assert "goal_satisfied" not in updates[0].metadata


@pytest.mark.asyncio
async def test_exact_codex_turn_receipt_remains_eligible_for_outcome_attribution(tmp_path):
    created_at = datetime.now(UTC)
    session = _session(HarnessType.CODEX, str(tmp_path))
    turn_id = "turn-causal-proof"
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=session.id,
        goal_id=session.goal_id,
        payload={"text": "Check the failing test."},
        rationale="A test still fails.",
        evidence=["pytest:failed"],
    )
    prior = Intervention(
        id="codex-exact-turn",
        session_id=session.id,
        goal_id=session.goal_id,
        trigger=EventType.STOP.value,
        evidence=action.evidence,
        diagnosis=action.rationale,
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="sent",
        created_at=created_at,
        metadata={
            "worker_delivery_receipt": {
                "schema": "pex.worker-delivery.codex-turn.v1",
                "target_session_id": session.id,
                "vendor_session_id": session.vendor_session_id,
                "vendor_turn_id": turn_id,
            },
        },
    )
    event = _later_stop(session, created_at).model_copy(
        update={
            "event_id": f"{session.id}:turn:{turn_id}",
            "raw_event_ref": json.dumps(
                {
                    "schema": "pex.codex-event-ref.v1",
                    "thread_id": session.vendor_session_id,
                    "turn_id": turn_id,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            "metadata": {"vendor_turn_id": turn_id},
        }
    )

    updates = await _pipeline_with(prior)._observe_prior_intervention(
        session,
        event,
        {"status": "supported", "acceptance_status": "supported"},
        persist=False,
    )

    assert len(updates) == 1
    assert updates[0].outcome == "goal_evidence_supported"
    assert updates[0].helped is True
    assert updates[0].metadata["outcome_final"] is True


@pytest.mark.asyncio
async def test_shared_codex_normalized_delivery_events_require_exact_durable_binding(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    session = adapter.session
    session.goal_id = "goal-shared-causal-proof"
    turn_id = "turn-shared-causal-proof"
    created_at = datetime.now(UTC) - timedelta(seconds=1)
    subscription = session.metadata["subscription_receipt"]
    delivery_scope = {
        "schema": "pex.shared-codex-delivery-scope.v1",
        "authorization_id": subscription["authorization_id"],
        "endpoint_identity": subscription["endpoint_identity"],
        "connection_generation": subscription["connection_generation"],
        "target_session_id": session.id,
        "vendor_session_id": session.vendor_session_id,
        "project_id": session.project_id,
        "cwd": session.cwd,
    }
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=session.id,
        goal_id=session.goal_id,
        payload={"text": "Complete the requested work."},
        rationale="The observed artifact is incomplete.",
        evidence=["artifact:missing"],
    )
    prior = Intervention(
        id="shared-codex-exact-turn",
        session_id=session.id,
        goal_id=session.goal_id,
        trigger=EventType.STOP.value,
        evidence=action.evidence,
        diagnosis=action.rationale,
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="sent",
        created_at=created_at,
        metadata={
            "worker_delivery_receipt": {
                "schema": "pex.worker-delivery.codex-turn.v1",
                "target_session_id": session.id,
                "vendor_session_id": session.vendor_session_id,
                "vendor_turn_id": turn_id,
            },
            "shared_delivery_scope": delivery_scope,
        },
    )
    transport.notifications.extend(
        [
            _notification("turn/started", {"threadId": "thread-1", "turn": {"id": turn_id}}),
            _notification(
                "item/completed",
                {
                    "threadId": "thread-1",
                    "turnId": turn_id,
                    "item": {
                        "id": "shared-agent-response",
                        "type": "agentMessage",
                        "text": "The requested report is now complete.",
                    },
                },
            ),
            _notification(
                "turn/completed",
                {
                    "threadId": "thread-1",
                    "turn": {"id": turn_id, "status": "completed"},
                },
            ),
        ]
    )
    try:
        events = [adapter._event(record) for record in (await coordinator.drain_live()).records]
        response = next(event for event in events if event.event_type == EventType.AGENT_RESPONSE)
        stop = next(event for event in events if event.event_type == EventType.STOP)
        assert response.raw_event_ref is not None
        assert stop.raw_event_ref is not None

        pipeline = _pipeline_with(prior)
        updates = await pipeline._observe_prior_intervention(
            session, response, None, persist=False
        )
        assert updates == [prior]
        assert prior.outcome == "worker_responded"
        assert prior.worker_response
        updates = await pipeline._observe_prior_intervention(
            session,
            stop,
            {"status": "supported", "acceptance_status": "supported"},
            persist=False,
        )
        assert updates == [prior]
        assert prior.outcome == "goal_evidence_supported"
        assert prior.helped is True

        for forged in (
            stop.model_copy(
                update={"raw_event_ref": stop.raw_event_ref.replace(turn_id, "other-turn")}
            ),
            stop.model_copy(update={"event_id": "codex-shared:" + "0" * 64}),
            stop.model_copy(update={"raw_event_ref": None}),
        ):
            assert Pipeline._event_matches_worker_delivery(prior, session, forged) is False
        rebinding = session.model_copy(deep=True)
        rebinding.metadata["subscription_receipt"]["authorization_id"] = "other-subscription"
        assert Pipeline._event_matches_worker_delivery(prior, rebinding, stop) is False
        reconnect = session.model_copy(deep=True)
        reconnect.metadata["subscription_receipt"]["connection_generation"] += 1
        reconnect.metadata["subscription_receipt"]["endpoint_identity"] = "other-endpoint"
        reconnected = stop.model_copy(deep=True)
        reconnected.metadata["connection_generation"] += 1
        reconnected.metadata["endpoint_identity"] = "other-endpoint"
        reconnected.event_id = shared_live_event_id(
            subscription_id=subscription["authorization_id"],
            endpoint_identity="other-endpoint",
            connection_generation=subscription["connection_generation"] + 1,
            stable_id=_stable_record_id("live_notification", "turn/completed", turn_id, None),
        )
        assert Pipeline._event_matches_worker_delivery(prior, reconnect, reconnected) is False
    finally:
        await transport.close()
