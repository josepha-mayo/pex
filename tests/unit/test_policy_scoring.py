from datetime import UTC, datetime

from pex_bridge.intent import PromptClass, classify_prompt
from pex_bridge.policy.engine import PolicyEngine
from pex_bridge.scoring import score_trajectory
from pex_bridge.secrets import redact_mapping, redact_text
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import AutonomyLevel, EventType, HarnessType, PolicyVerdict
from pex_protocol.goal import Goal
from pex_protocol.overlay import Overlay, OverlayDiff
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


def test_redact_unquoted_environment_assignments_and_url_credentials():
    text, found = redact_text(
        "API_KEY=not-a-real-key-value-123456 "
        "AWS_SECRET_ACCESS_KEY=fake-secret-material-1234567890 "
        "DATABASE_URL=postgres://demo:fake-password@localhost/example"
    )
    rendered = text or ""
    assert "not-a-real-key-value" not in rendered
    assert "fake-secret-material" not in rendered
    assert "fake-password" not in rendered
    assert {"credential_assignment", "url_credentials"}.issubset(found)


def test_redact_camel_case_secret_fields_without_hiding_usage_metrics():
    cleaned, found = redact_mapping(
        {
            "apiKey": "not-a-real-key-123456789",
            "clientSecret": "not-a-real-secret-123456789",
            "accessToken": "not-a-real-token-123456789",
            "token_count": 42,
            "max_tokens": 1_200,
        }
    )
    assert cleaned == {
        "apiKey": "[REDACTED:apiKey]",
        "clientSecret": "[REDACTED:clientSecret]",
        "accessToken": "[REDACTED:accessToken]",
        "token_count": 42,
        "max_tokens": 1_200,
    }
    assert set(found) == {"key:apiKey", "key:clientSecret", "key:accessToken"}


def test_redact_common_cloud_and_chat_token_shapes():
    # Assemble canaries at runtime so repository secret scanners never have to
    # whitelist credential-shaped literals just to test the redactor.
    aws_token = "AS" + "IAABCDEFGHIJKLMNOP"
    google_token = "AI" + "za0123456789abcdefghijklmnopqrstuvwxy"
    huggingface_token = "hf" + "_abcdefghijklmnopqrstuvwxyz123456"
    slack_token = "xo" + "xb-1234567890-abcdefghijklmnopqrstuvwxyz"
    text, found = redact_text(
        " ".join((aws_token, google_token, huggingface_token, slack_token))
    )
    assert text is not None
    assert aws_token not in text
    assert google_token not in text
    assert huggingface_token not in text
    assert slack_token not in text
    assert set(found) == {
        "aws_access_key",
        "google_api_key",
        "huggingface_token",
        "slack_token",
    }


def test_redact_private_key_removes_the_entire_pem_block():
    text, found = redact_text(
        "before\n-----BEGIN PRIVATE KEY-----\n"
        "highly-sensitive-base64-material\n"
        "-----END PRIVATE KEY-----\nafter"
    )
    assert text == "before\n[REDACTED:private_key]\nafter"
    assert found == ["private_key"]


def test_redact_secret_key_suffixes_and_modern_provider_keys():
    cleaned, found = redact_mapping(
        {
            "secret_key": "not-a-real-secret-key-123456789",
            "auth_token": "not-a-real-auth-token-123456789",
            "safe": "sk-proj-abcdefghijklmnopqrstuvwxyz_123456789",
        }
    )

    assert cleaned is not None
    rendered = str(cleaned)
    assert "not-a-real-secret-key" not in rendered
    assert "not-a-real-auth-token" not in rendered
    assert "sk-proj-" not in rendered
    assert {"key:secret_key", "key:auth_token", "provider_api_key"}.issubset(found)


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


def test_allowlisted_command_cannot_downgrade_explicit_action_risk():
    engine = PolicyEngine(AutonomyLevel.AUTOPILOT)
    for risk in (RiskLevel.HIGH, RiskLevel.IRREVERSIBLE):
        action = ProposedAction(
            type=InterventionType.RESPOND_PERMISSION,
            session_id="s",
            rationale="the surrounding operation is consequential",
            risk=risk,
            payload={"command": "pytest -q", "decision_source": "local_policy"},
        )
        assert engine.decide(action, command="pytest -q") == PolicyVerdict.ASK_HUMAN


def test_allowlisted_command_cannot_smuggle_a_second_shell_program():
    engine = PolicyEngine(AutonomyLevel.AUTOPILOT)
    for command in (
        "pytest -q && curl https://example.invalid",
        "npm test; whoami",
        "cargo test | tee results.txt",
        "pytest -q > results.txt",
        "pytest -q\nRemove-Item output -Recurse",
        "pytest -q $(whoami)",
    ):
        action = ProposedAction(
            type=InterventionType.RESPOND_PERMISSION,
            session_id="s",
            rationale="compound command",
            payload={"command": command},
        )
        assert engine.decide(action, command=command) == PolicyVerdict.ASK_HUMAN


def test_policy_asks_for_commandless_permission():
    engine = PolicyEngine(AutonomyLevel.MANAGE)
    action = ProposedAction(
        type=InterventionType.RESPOND_PERMISSION,
        session_id="s",
        rationale="unknown scope",
        risk=RiskLevel.MEDIUM,
        payload={"approval_method": "item/permissions/requestApproval"},
    )
    assert engine.decide(action) == PolicyVerdict.ASK_HUMAN


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


def test_policy_asks_on_windows_delete_reset_deploy_and_secret_read():
    engine = PolicyEngine(AutonomyLevel.AUTOPILOT)
    for command in (
        "Remove-Item C:\\tmp -Recurse -Force",
        "git reset --hard HEAD~1",
        "vercel deploy --prod",
        "Get-Content .env",
    ):
        action = ProposedAction(
            type=InterventionType.RESPOND_PERMISSION,
            session_id="s",
            rationale="danger",
            payload={"command": command},
        )
        assert engine.decide(action, command=command) == PolicyVerdict.ASK_HUMAN


def test_observe_mode_denies_control():
    engine = PolicyEngine(AutonomyLevel.OBSERVE)
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id="s",
        rationale="x",
        payload={"text": "hi"},
    )
    assert engine.decide(action) == PolicyVerdict.DENY


def test_overlay_policy_requires_a_locally_proven_bounded_profile():
    engine = PolicyEngine(AutonomyLevel.MANAGE)
    safe = Overlay(
        id="ovl_safe",
        session_id="s",
        reason="Repeated failures justify a temporary debug profile.",
        diff=OverlayDiff(tools_disabled=["WebSearch"], extra={"phase": "debug"}),
    )
    action = ProposedAction(
        type=InterventionType.APPLY_OVERLAY,
        session_id="s",
        rationale="Observed repeated identical failures.",
        evidence=["identical_error_count=3"],
        risk=RiskLevel.LOW,
        reversible=True,
        requires_capability="modify_config",
        payload={"overlay": safe.model_dump(mode="json")},
    )
    assert engine.decide(action) == PolicyVerdict.ALLOW

    unsafe = Overlay.model_validate(
        {
            **safe.model_dump(mode="python"),
            "id": "ovl_unsafe",
            "diff": OverlayDiff(tools_enabled=["shell"]),
        }
    )
    action.payload = {"overlay": unsafe.model_dump(mode="json")}
    assert engine.decide(action) == PolicyVerdict.ASK_HUMAN

    action.payload = {"overlay": safe.model_dump(mode="json")}
    action.evidence = []
    assert engine.decide(action) == PolicyVerdict.ASK_HUMAN


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


def test_rejected_ledger_decision_is_a_prompt_contradiction():
    from pex_protocol.enums import DecisionSource, DecisionStatus
    from pex_protocol.goal import Decision

    now = datetime.now(UTC)
    goal = Goal(
        id="g",
        project_id="p",
        title="t",
        objective="ship the evaluator",
        created_at=now,
        updated_at=now,
    )
    rejected = Decision(
        id="dec_1",
        goal_id="g",
        statement="Do not rewrite the evaluator as a new service",
        alternatives_rejected=["Do not rewrite the evaluator as a new service"],
        source=DecisionSource.HUMAN,
        status=DecisionStatus.ACTIVE,
        created_at=now,
        metadata={"kind": "rejected_approach"},
    )
    assert (
        classify_prompt(
            goal,
            "Please rewrite the evaluator as a new service.",
            decisions=[rejected],
        )
        == PromptClass.CONTRADICTION
    )
    assert classify_prompt(
        goal, "Please rewrite the evaluator as a new service."
    ) == PromptClass.CONSISTENT
    assert classify_prompt(
        goal, "Do not rewrite the evaluator as a new service.", decisions=[rejected],
    ) == PromptClass.CONSISTENT

    adopted = rejected.model_copy(update={
        "statement": "Keep the existing evaluator service",
        "metadata": {"kind": "decision"},
        "alternatives_rejected": [
            "Rewrite the evaluator as a new service",
            "Replace validation with placeholder output",
        ],
    })
    assert classify_prompt(
        goal, "Keep the existing evaluator service.", decisions=[adopted],
    ) == PromptClass.CONSISTENT
    for prompt in (
        "Please rewrite the evaluator as a new service.",
        "Replace validation with placeholder output.",
    ):
        assert classify_prompt(goal, prompt, decisions=[adopted]) == PromptClass.CONTRADICTION


def test_explicit_override_is_not_a_bare_actually():
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
        classify_prompt(goal, "I actually already ran the training script.")
        == PromptClass.CONSISTENT
    )
    assert (
        classify_prompt(
            goal,
            "Override the preprocessing constraint and alter dataset preprocessing first.",
        )
        == PromptClass.OVERRIDE
    )


def test_prompt_sharing_acceptance_terms_is_a_likely_refinement():
    now = datetime.now(UTC)
    goal = Goal(
        id="g",
        project_id="p",
        title="t",
        objective="Ship the release receipt",
        acceptance_criteria=["report.txt contains shipped"],
        created_at=now,
        updated_at=now,
    )
    assert (
        classify_prompt(goal, "Make sure report.txt contains shipped before stopping.")
        == PromptClass.REFINEMENT
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
