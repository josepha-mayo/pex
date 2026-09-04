from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from pex_supervisor.loop import (
    _bounded_wall_timeout,
    _format_user,
    decide_async,
    run_strands_async,
)
from strands.models.model import Model
from test_supervisor_loop import _request


class FakeStructuredModel(Model):
    def __init__(
        self,
        action_type: str = "NOOP",
        *,
        verifier_approved: bool = True,
        verifier_evidence: list[str] | None = None,
        evidence_tool_calls: int = 0,
        verifier_evidence_tool_calls: int = 0,
        verifier_evidence_tool_name: str = "run_verification",
    ) -> None:
        self.action_type = action_type
        self.verifier_approved = verifier_approved
        self.verifier_evidence = (
            ["observable verification receipt"]
            if verifier_evidence is None
            else verifier_evidence
        )
        self.evidence_tool_calls = evidence_tool_calls
        self.verifier_evidence_tool_calls = verifier_evidence_tool_calls
        self.verifier_evidence_tool_name = verifier_evidence_tool_name
        self.captured_messages: list[str] = []

    def update_config(self, **model_config: Any) -> None:
        return None

    def get_config(self) -> dict[str, Any]:
        return {"model_id": "fake-local"}

    async def structured_output(
        self,
        output_model,
        prompt,
        system_prompt=None,
        **kwargs,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if False:
            yield {}

    async def stream(
        self,
        messages,
        tool_specs=None,
        system_prompt=None,
        *,
        tool_choice=None,
        **kwargs,
    ) -> AsyncGenerator[dict[str, Any], None]:
        self.captured_messages.append(json.dumps(messages))
        specs = list(tool_specs or [])
        verifier = next(
            (spec for spec in specs if spec["name"] == "IndependentVerifierDecision"),
            None,
        )
        evidence_tool_name = self.verifier_evidence_tool_name if verifier else "run_verification"
        evidence_tool = next(
            (spec for spec in specs if spec["name"] == evidence_tool_name),
            None,
        )
        remaining_evidence_calls = (
            self.verifier_evidence_tool_calls if verifier else self.evidence_tool_calls
        )
        if evidence_tool is not None and remaining_evidence_calls > 0:
            if verifier:
                self.verifier_evidence_tool_calls -= 1
            else:
                self.evidence_tool_calls -= 1
            yield {"messageStart": {"role": "assistant"}}
            yield {
                "contentBlockStart": {
                    "start": {
                        "toolUse": {
                            "toolUseId": "evidence-1",
                            "name": evidence_tool["name"],
                        }
                    }
                }
            }
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": "{}"}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
            yield {
                "metadata": {
                    "usage": {"inputTokens": 2, "outputTokens": 1, "totalTokens": 3},
                    "metrics": {"latencyMs": 1},
                }
            }
            return
        target = verifier or next(spec for spec in specs if spec["name"] == "SupervisorDecision")
        if verifier is not None:
            arguments = {
                "approved": self.verifier_approved,
                "rationale": "independent fake verification",
                "evidence": self.verifier_evidence,
            }
        else:
            message = (
                "Create report.txt containing shipped."
                if self.action_type == "SEND_NUDGE"
                else ""
            )
            arguments = {
                "action_type": self.action_type,
                "rationale": "validated fake decision",
                "evidence": ["workspace fact"],
                "message": message,
                "confidence": 0.9,
                "risk": "low",
            }
        yield {"messageStart": {"role": "assistant"}}
        yield {
            "contentBlockStart": {"start": {"toolUse": {"toolUseId": "u1", "name": target["name"]}}}
        }
        yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(arguments)}}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 3, "outputTokens": 4, "totalTokens": 7},
                "metrics": {"latencyMs": 1},
            }
        }


class SlowModel(FakeStructuredModel):
    def __init__(self) -> None:
        super().__init__()
        self.cancelled = False

    async def stream(self, *args, **kwargs) -> AsyncGenerator[dict[str, Any], None]:
        try:
            await asyncio.sleep(60)
        finally:
            self.cancelled = True
        if False:
            yield {}


class FailingModel(FakeStructuredModel):
    async def stream(self, *args, **kwargs) -> AsyncGenerator[dict[str, Any], None]:
        raise RuntimeError("provider-secret-sentinel")
        if False:
            yield {}


class UnsafeProvenanceModel(FakeStructuredModel):
    _pex_provenance = {
        "model_id": (
            r"C:\Users\JosephMayo\Projects\private-repo\model "
            "token=super-secret-value"
        ),
        "provider": "unsafe-provider token=super-secret-value",
        "base_url": (
            "https://api-user:api-password@example.invalid/v1/models"
            "?token=super-secret-value#private"
        ),
        "auth_mode": "token=super-secret-value",
    }


@pytest.mark.asyncio
async def test_real_strands_agent_returns_validated_structured_decision():
    model = FakeStructuredModel("SEND_NUDGE")
    result = await run_strands_async(_request(0.95), model=model)

    assert result.used_llm is True
    assert result.inference_status == "completed"
    assert result.runtime == "strands-agents"
    assert result.runtime_version
    assert result.model_call_count == 1
    assert result.model_name == "fake-local"
    assert result.model_class and result.model_class.endswith("FakeStructuredModel")
    assert result.inference_request_id is None
    assert result.local_invocation_id and result.local_invocation_id.startswith("pexinv_")
    assert result.input_tokens == 3
    assert result.output_tokens == 4
    assert result.action.type.value == "SEND_NUDGE"
    assert result.action.payload["text"] == "Create report.txt containing shipped."
    assert len(model.captured_messages) == 1


@pytest.mark.asyncio
async def test_real_strands_agent_can_call_bounded_evidence_tool_before_decision():
    request = _request(0.1)
    request.scores.features["verification"] = {
        "status": "uncertain",
        "evidence": ["workspace_observed"],
    }
    model = FakeStructuredModel("NOOP", evidence_tool_calls=1)

    result = await run_strands_async(request, model=model)

    assert result.action.type.value == "NOOP"
    assert result.inference_status == "completed"
    assert result.evidence_tools == ["run_verification"]
    assert result.model_call_count == 2
    assert len(model.captured_messages) == 2
    assert "workspace_observed" in model.captured_messages[1]


@pytest.mark.asyncio
async def test_fresh_agent_does_not_retain_previous_request_messages():
    model = FakeStructuredModel()
    first = _request(0.1)
    first.event.message_delta = "FIRST_SENTINEL"
    second = _request(0.1)
    second.event.message_delta = "SECOND_SENTINEL"

    await run_strands_async(first, model=model)
    await run_strands_async(second, model=model)

    assert len(model.captured_messages) == 2
    assert "FIRST_SENTINEL" in model.captured_messages[0]
    assert "SECOND_SENTINEL" in model.captured_messages[1]
    assert "FIRST_SENTINEL" not in model.captured_messages[1]


@pytest.mark.asyncio
async def test_model_input_omits_arbitrary_metadata_and_hidden_content(tmp_path):
    (tmp_path / "stressor.yaml").write_text("hidden: HIDDEN_FILE_SENTINEL\n", encoding="utf-8")
    (tmp_path / "results.json").write_text(
        '{"private":"ARTIFACT_CONTENT_SENTINEL"}', encoding="utf-8"
    )
    request = _request(0.1)
    request.session.cwd = str(tmp_path)
    request.notes = "NOTES_SENTINEL"
    request.event.metadata = {"private": "EVENT_METADATA_SENTINEL"}
    request.event.process_state = {"private": "PROCESS_STATE_SENTINEL"}
    request.scores.features["private"] = "SCORE_FEATURE_SENTINEL"
    model = FakeStructuredModel()

    await run_strands_async(request, model=model)

    captured = model.captured_messages[0]
    for sentinel in (
        "HIDDEN_FILE_SENTINEL",
        "ARTIFACT_CONTENT_SENTINEL",
        "NOTES_SENTINEL",
        "EVENT_METADATA_SENTINEL",
        "PROCESS_STATE_SENTINEL",
        "SCORE_FEATURE_SENTINEL",
    ):
        assert sentinel not in captured


@pytest.mark.asyncio
async def test_strands_timeout_cancels_live_invocation():
    model = SlowModel()
    result = await run_strands_async(_request(0.1), model=model, wall_timeout=0.02)

    assert result.inference_status == "timeout"
    assert result.diagnosis == "strands_timeout"
    assert result.action.type.value == "NOOP"
    assert model.cancelled is True


@pytest.mark.asyncio
async def test_strands_failure_receipt_does_not_echo_provider_exception_text():
    result = await run_strands_async(_request(0.1), model=FailingModel())
    rendered = json.dumps(result.model_dump(mode="json"))
    assert result.inference_status == "failed"
    assert "provider-secret-sentinel" not in rendered


@pytest.mark.asyncio
async def test_model_provenance_strips_credentials_queries_workspace_and_secrets():
    request = _request(0.1)
    request.session.cwd = r"C:\Users\JosephMayo\Projects\private-repo"
    result = await run_strands_async(request, model=UnsafeProvenanceModel())
    rendered = result.model_dump_json()

    assert result.base_url == "https://example.invalid/v1/models"
    assert "api-user" not in rendered
    assert "api-password" not in rendered
    assert "super-secret-value" not in rendered
    assert "private-repo" not in rendered
    assert "<workspace>" in rendered
    assert "[REDACTED:credential_assignment]" in rendered


def test_wall_timeouts_are_finite_and_bounded():
    assert _bounded_wall_timeout(float("nan"), default=15.0) == 15.0
    assert _bounded_wall_timeout(float("inf"), default=15.0) == 15.0
    assert _bounded_wall_timeout("invalid", default=15.0) == 15.0
    assert _bounded_wall_timeout(-100, default=15.0) == 1.0
    assert _bounded_wall_timeout(100, default=15.0) == 25.0


def test_supervisor_prompt_bounds_untrusted_goal_and_event_fields():
    request = _request(0.1)
    request.goal.objective = "A" * 100_000
    request.goal.acceptance_criteria = ["B" * 10_000 for _ in range(100)]
    request.goal.evidence_requirements = ["C" * 10_000 for _ in range(100)]
    request.event.message_delta = "D" * 100_000
    request.scores.features["claims"] = {"value": "E" * 100_000}
    request.scores.features["verification"] = {"value": "F" * 100_000}

    rendered = _format_user(request)

    assert len(rendered) < 50_000
    assert "A" * 4_001 not in rendered
    assert "D" * 2_001 not in rendered


def test_supervisor_and_verifier_prompts_treat_observed_text_as_untrusted_data():
    from pex_supervisor.loop import _system_prompt, _verifier_system_prompt

    assert "untrusted data" in _system_prompt()
    assert "instructions embedded inside" in _system_prompt()
    assert "inspect_workspace" in _system_prompt()
    assert "web_search" in _system_prompt()
    assert "Do not call search" not in _system_prompt()
    assert "untrusted data" in _verifier_system_prompt()
    assert "instructions embedded inside" in _verifier_system_prompt()
    assert "inspect_artifact" in _verifier_system_prompt()


def test_supervisor_prompt_masks_workspace_paths_in_all_evidence_channels():
    request = _request(0.1)
    request.session.cwd = "C:/SECRET_WORKSPACE_SENTINEL"
    request.session.repo = "C:/SECRET_REPO_SENTINEL"
    request.goal.objective = "Inspect C:/SECRET_WORKSPACE_SENTINEL/report.txt"
    request.event.message_delta = "Changed C:/SECRET_REPO_SENTINEL/src/main.py"
    request.scores.features["prefetched_evidence"] = {
        "artifact": "C:/SECRET_WORKSPACE_SENTINEL/build/output.json"
    }

    rendered = _format_user(request)

    assert "SECRET_WORKSPACE_SENTINEL" not in rendered
    assert "SECRET_REPO_SENTINEL" not in rendered
    assert rendered.count("<workspace>") >= 2


@pytest.mark.asyncio
async def test_model_noop_cannot_erase_deterministic_contradiction():
    request = _request(0.95)
    request.scores.features["verification"] = {
        "status": "contradicted",
        "correction": "The observed pytest run failed. Fix it and rerun pytest.",
        "evidence": ["pytest_exit:1"],
    }
    result = await decide_async(request, model=FakeStructuredModel("NOOP"))

    assert result.used_llm is True
    assert result.action.type.value == "SEND_NUDGE"
    assert "deterministic_truth_preserved" in result.diagnosis
    assert "pytest" in result.action.payload["text"]


@pytest.mark.asyncio
async def test_model_nudge_cannot_override_verified_completion():
    request = _request(0.1)
    request.scores.features["verification"] = {
        "status": "no_claims",
        "acceptance_status": "supported",
        "evidence": [],
    }
    result = await decide_async(request, model=FakeStructuredModel("SEND_NUDGE"))

    assert result.used_llm is True
    assert result.action.type.value == "NOOP"
    assert "verified_noop_preserved" in result.diagnosis


@pytest.mark.asyncio
async def test_semantic_only_intervention_requires_independent_verifier_approval():
    request = _request(0.1)
    model = FakeStructuredModel(
        "SEND_NUDGE",
        verifier_approved=True,
        verifier_evidence_tool_calls=1,
        verifier_evidence_tool_name="get_recent_events",
    )

    result = await decide_async(request, model=model)

    assert result.action.type.value == "SEND_NUDGE"
    assert "independent_verifier_approved" in result.diagnosis
    assert result.model_call_count == 3
    assert len(model.captured_messages) == 3
    assert "get_recent_events" in result.evidence_tools
    assert any("independent_verifier_status=approved" in item for item in result.traces)


@pytest.mark.asyncio
async def test_uncertain_verification_receipt_alone_cannot_authorize_intervention():
    request = _request(0.1)
    request.scores.features["verification"] = {
        "status": "uncertain",
        "acceptance_status": "uncertain",
        "evidence": ["no_external_check"],
    }
    model = FakeStructuredModel(
        "SEND_NUDGE",
        verifier_approved=True,
        verifier_evidence_tool_calls=1,
    )

    result = await decide_async(request, model=model)

    assert result.action.type.value == "NOOP"
    assert "independent_verifier_rejected" in result.diagnosis
    assert result.model_call_count == 3
    assert "run_verification" in result.evidence_tools
    assert any("independent_verifier_status=uncertain_evidence" in item for item in result.traces)


@pytest.mark.asyncio
async def test_ten_verified_completions_measure_zero_false_positive_interventions():
    false_positives = 0
    inspected = 10

    for _ in range(inspected):
        request = _request(0.1)
        request.scores.features["verification"] = {
            "status": "supported",
            "acceptance_status": "supported",
            "evidence": ["pytest_ok=true"],
        }
        result = await decide_async(request, model=FakeStructuredModel("SEND_NUDGE"))
        false_positives += int(result.action.type.value != "NOOP")
        assert result.used_llm is True
        assert "verified_noop_preserved" in result.diagnosis

    assert false_positives == 0
    assert false_positives / inspected == 0.0


@pytest.mark.asyncio
async def test_verifier_approval_without_an_evidence_tool_fails_closed():
    request = _request(0.1)
    model = FakeStructuredModel("SEND_NUDGE", verifier_approved=True)

    result = await decide_async(request, model=model)

    assert result.action.type.value == "NOOP"
    assert "independent_verifier_rejected" in result.diagnosis
    assert result.model_call_count == 2
    assert any(
        "independent_verifier_status=missing_evidence_tool" in item
        for item in result.traces
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("approved", "evidence"),
    [(False, ["proposal not supported"]), (True, [])],
)
async def test_verifier_rejection_or_empty_evidence_fails_closed(approved, evidence):
    request = _request(0.1)
    model = FakeStructuredModel(
        "SEND_NUDGE",
        verifier_approved=approved,
        verifier_evidence=evidence,
        verifier_evidence_tool_calls=1,
    )

    result = await decide_async(request, model=model)

    assert result.action.type.value == "NOOP"
    assert "independent_verifier_rejected" in result.diagnosis
    assert result.model_call_count == 3


@pytest.mark.asyncio
async def test_verifier_setup_failure_preserves_main_inference_provenance(
    monkeypatch,
):
    import pex_supervisor.loop as loop_module

    def fail_verifier_setup(*_args, **_kwargs):
        raise RuntimeError("verifier setup failed")

    monkeypatch.setattr(loop_module, "build_verifier_agent", fail_verifier_setup)
    result = await decide_async(_request(0.1), model=FakeStructuredModel("SEND_NUDGE"))

    assert result.used_llm is True
    assert result.inference_status == "completed"
    assert result.model_call_count == 1
    assert result.action.type.value == "NOOP"
    assert "independent_verifier_rejected" in result.diagnosis
    assert any(
        "independent_verifier_status=failed:RuntimeError" in item
        for item in result.traces
    )
