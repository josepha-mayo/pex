from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
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
