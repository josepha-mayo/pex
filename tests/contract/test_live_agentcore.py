"""Explicitly gated proof against a deployed PEX AgentCore Runtime."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pex_bridge.agentcore import AgentCoreSupervisorClient
from pex_bridge.config import Settings
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorRequest


@pytest.mark.live_llm
@pytest.mark.live_agentcore
@pytest.mark.asyncio
async def test_live_agentcore_returns_bound_strands_decision(tmp_path):
    if os.environ.get("PEX_AGENTCORE_LIVE") != "1":
        pytest.skip("set PEX_AGENTCORE_LIVE=1 only with live-invocation authorization")
    runtime_arn = (os.environ.get("PEX_AGENTCORE_RUNTIME_ARN") or "").strip()
    if not runtime_arn:
        pytest.skip("PEX_AGENTCORE_RUNTIME_ARN is not configured")

    now = datetime.now(UTC)
    session = HarnessSession(
        id=f"agentcore-live-{uuid4().hex}",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id=f"agentcore-live-{uuid4().hex}",
        project_id="agentcore-live-contract",
        goal_id="goal-agentcore-live-contract",
        status=SessionStatus.STOPPED,
    )
    goal = Goal(
        id=session.goal_id,
        project_id=session.project_id,
        title="AgentCore contract proof",
        objective="Return one typed, session-bound supervision decision.",
        acceptance_criteria=["The decision is valid PEX protocol JSON."],
        created_at=now,
        updated_at=now,
    )
    event = HarnessEvent(
        event_id=f"event-agentcore-live-{uuid4().hex}",
        ts=now,
        harness_type=session.harness_type,
        session_id=session.id,
        project_id=session.project_id,
        event_type=EventType.STOP,
        message_delta="The contract check is ready for inspection.",
    )
    request = SupervisorRequest(
        session=session,
        goal=goal,
        event=event,
        recent_events=[event],
        notes="live AgentCore transport contract check",
    )
    settings = Settings.for_test(
        require_auth=False,
        home=tmp_path,
        supervisor_mode="agentcore",
        agentcore_runtime_arn=runtime_arn,
        agentcore_region=(os.environ.get("PEX_AGENTCORE_REGION") or None),
        cloud_reasoning=True,
    )

    result = await AgentCoreSupervisorClient(settings).decide(request)

    assert result.action.session_id == session.id
    assert result.action.goal_id == goal.id
    assert result.execution_mode == "agentcore"
    assert result.transport == "bedrock-agentcore"
    assert result.transport_status == "completed"
    assert result.transport_invocation_id
    assert result.transport_request_id
    assert result.runtime == "strands-agents"
    assert result.used_llm is True
    assert result.inference_status == "completed"
    assert result.model_call_count >= 1
