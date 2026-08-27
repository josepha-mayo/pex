from datetime import UTC, datetime

from pex_bridge.intent import PromptClass, classify_prompt
from pex_bridge.policy.engine import PolicyEngine
from pex_bridge.scoring import score_trajectory
from pex_bridge.secrets import redact_mapping, redact_text
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import AutonomyLevel, EventType, HarnessType, PolicyVerdict
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent


def test_redact_openai_key():
    text, found = redact_text("token sk-abcdefghijklmnopqrstuvwxyz123456")
    assert "sk-" not in (text or "")
    assert found


def test_redact_nested_secret_fields_and_lists():
    cleaned, found = redact_mapping(
        {
            "authorization": "Bearer top-secret-token",
            "nested": [{"api_key": "secret-value-123456"}, "sk-abcdefghijklmnopqrstuvwxyz123456"],
        }
    )
    rendered = str(cleaned)
    assert "top-secret-token" not in rendered
    assert "secret-value-123456" not in rendered
    assert "sk-" not in rendered
    assert found


def test_policy_allows_pytest_in_manage():
    engine = PolicyEngine(AutonomyLevel.MANAGE)
    action = ProposedAction(
        type=InterventionType.RESPOND_PERMISSION,
        session_id="s",
        rationale="test",
        risk=RiskLevel.LOW,
        payload={"command": "pytest -q"},
    )
    assert engine.decide(action, command="pytest -q") == PolicyVerdict.ALLOW


def test_policy_asks_on_force_push():
    engine = PolicyEngine(AutonomyLevel.AUTOPILOT)
    action = ProposedAction(
        type=InterventionType.RESPOND_PERMISSION,
        session_id="s",
        rationale="danger",
        risk=RiskLevel.LOW,
        payload={"command": "git push --force origin main"},
    )
    assert engine.decide(action, command="git push --force origin main") == PolicyVerdict.ASK_HUMAN


def test_observe_mode_denies_control():
    engine = PolicyEngine(AutonomyLevel.OBSERVE)
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id="s",
        rationale="x",
        payload={"text": "hi"},
    )
    assert engine.decide(action) == PolicyVerdict.DENY


def test_classify_do_not_preprocess_constraint():
    now = datetime.now(UTC)
    goal = Goal(
        id="g",
        project_id="p",
        title="t",
        objective="train model",
        constraints=["Do not alter dataset preprocessing."],
        created_at=now,
        updated_at=now,
    )
    assert (
        classify_prompt(goal, "Just alter dataset preprocessing first.")
        == PromptClass.CONTRADICTION
    )


def test_non_goals_are_constraints_for_prompt_classification():
    now = datetime.now(UTC)
    goal = Goal(
        id="g",
        project_id="p",
        title="t",
        objective="ship the evaluator",
        non_goals=["Do not rewrite the dataset loader."],
        created_at=now,
        updated_at=now,
    )
    assert (
        classify_prompt(goal, "Please rewrite the dataset loader from scratch.")
        == PromptClass.CONTRADICTION
    )


def test_stagnation_from_repeated_errors():
    now = datetime.now(UTC)
    events = []
    for i in range(6):
        events.append(
            HarnessEvent(
                event_id=str(i),
                ts=now,
                harness_type=HarnessType.SYNTHETIC,
                session_id="s",
                event_type=EventType.SHELL,
                command="python train.py",
                error="FileNotFoundError: data.parquet",
            )
        )
    scores = score_trajectory(events, None)
    assert scores.stagnation > 0.3
