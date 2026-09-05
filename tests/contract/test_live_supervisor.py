"""Live supervisor inference probe. Skips without a configured key. Not a score."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from dotenv import dotenv_values
from pex_supervisor.providers import load_supervisor_model

from tests.contract.live_gate import require_live_authorization


def _has_supervisor_access() -> bool:
    if os.environ.get("PEX_SUPERVISOR_PROVIDER") in {
        "ollama",
        "lmstudio",
        "llamacpp",
        "vllm",
    }:
        return True
    names = (
        "PEX_SUPERVISOR_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "PEX_ZEN_API_KEY",
        "OPENCODE_API_KEY",
        "ANTHROPIC_API_KEY",
        "XAI_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
    )
    if any(os.environ.get(name) for name in names):
        return True
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    values = dotenv_values(env_path)
    return any(str(values.get(name) or "").strip() for name in names)


@pytest.mark.live_llm
@pytest.mark.skipif(
    not _has_supervisor_access(),
    reason="no supervisor API key or local provider configured",
)
def test_live_supervisor_inference_is_auditable():
    require_live_authorization("PEX_LIVE_SUPERVISOR")
    from pex_protocol.enums import EventType, HarnessType, SessionStatus
    from pex_protocol.goal import Goal
    from pex_protocol.session import HarnessEvent, HarnessSession
    from pex_protocol.supervisor import SupervisorRequest, TrajectoryScores
    from pex_supervisor.loop import decide
    from pex_supervisor.providers import describe_backend

    os.environ.pop("PEX_SUPERVISOR_DISABLE", None)
    model = load_supervisor_model()
    assert model is not None, "authorized live supervisor model did not construct"
    now = datetime.now(UTC)
    request = SupervisorRequest(
        session=HarnessSession(
            id="synthetic:probe",
            harness_type=HarnessType.SYNTHETIC,
            vendor_session_id="probe",
            project_id="p",
            status=SessionStatus.STOPPED,
            goal_id="g",
            cwd=os.getcwd(),
        ),
        goal=Goal(
            id="g",
            project_id="p",
            title="probe",
            objective="Confirm PEX can call a real model once.",
            acceptance_criteria=["used_llm true"],
            created_at=now,
            updated_at=now,
        ),
        event=HarnessEvent(
            event_id="e",
            ts=now,
            harness_type=HarnessType.SYNTHETIC,
            session_id="synthetic:probe",
            event_type=EventType.STOP,
            message_delta="done without tests",
        ),
        scores=TrajectoryScores(premature_completion=0.9, features={"tests_run": 0, "stops": 1}),
    )
    result = decide(request, model=model)
    backend = describe_backend()
    assert result.used_llm is True, (
        f"expected live inference, got {result.diagnosis} backend={backend}"
    )
    assert result.inference_status == "completed", result.model_dump(mode="json")
    assert result.runtime == "strands-agents"
    assert result.runtime_version
    assert result.model_call_count >= 1
    assert result.local_invocation_id and result.local_invocation_id.startswith("pexinv_")
    expected_provider = os.environ.get("PEX_LIVE_EXPECT_PROVIDER")
    expected_model = os.environ.get("PEX_LIVE_EXPECT_MODEL")
    expected_api = os.environ.get("PEX_LIVE_EXPECT_GENERATION_API")
    if expected_provider:
        assert result.provider == expected_provider
    if expected_model:
        assert result.model_name == expected_model
    if expected_api:
        assert getattr(model, "_pex_provenance", {}).get("generation_api") == expected_api
    # The installed generic Strands adapters do not expose every provider's
    # request id. Never fabricate one from PEX's local correlation id.
    assert result.inference_request_id is None
    assert result.action.type.value in {
        "CONTINUE_SESSION",
        "SEND_NUDGE",
        "REQUEST_VERIFICATION",
        "NOOP",
        "ASK_HUMAN",
    }
