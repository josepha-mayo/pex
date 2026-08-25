"""Live supervisor inference probe. Skips without a configured key. Not a score."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from pex_supervisor.providers import load_supervisor_model


def _has_supervisor_key() -> bool:
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
    try:
        text = open(env_path, encoding="utf-8").read()
    except OSError:
        return False
    return any(name in text for name in names)


@pytest.mark.live_llm
@pytest.mark.skipif(not _has_supervisor_key(), reason="no supervisor API key configured")
def test_live_supervisor_inference_is_auditable():
    from pex_protocol.enums import EventType, HarnessType, SessionStatus
    from pex_protocol.goal import Goal
    from pex_protocol.session import HarnessEvent, HarnessSession
    from pex_protocol.supervisor import SupervisorRequest, TrajectoryScores
    from pex_supervisor.loop import decide
    from pex_supervisor.providers import describe_backend

    os.environ.pop("PEX_SUPERVISOR_DISABLE", None)
    model = load_supervisor_model()
    if model is None:
        pytest.skip("supervisor model did not construct")
    now = datetime.now(UTC)
    request = SupervisorRequest(
        session=HarnessSession(
            id="synthetic:probe",
            harness_type=HarnessType.SYNTHETIC,
            vendor_session_id="probe",
            status=SessionStatus.STOPPED,
            goal_id="g",
            cwd=".",
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
    assert result.inference_request_id
    assert result.action.type.value in {
        "CONTINUE_SESSION",
        "SEND_NUDGE",
        "REQUEST_VERIFICATION",
        "NOOP",
        "ASK_HUMAN",
    }
