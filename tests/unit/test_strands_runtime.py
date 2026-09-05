from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
from pex_protocol.supervisor import SupervisorResult
from pex_supervisor.evidence_observations import EvidenceObservationCollector
from pex_supervisor.loop import (
    _action_from_proposal,
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
        evidence_tool_calls: int | None = None,
        verifier_evidence_tool_calls: int = 0,
        verifier_evidence_tool_name: str = "run_verification",
        message: str | None = None,
        cite_evidence: bool = True,
    ) -> None:
        self.action_type = action_type
        self.verifier_approved = verifier_approved
        self.verifier_evidence = (
            ["observable verification receipt"]
            if verifier_evidence is None
            else verifier_evidence
        )
        self.evidence_tool_calls = (
            int(action_type != "NOOP")
            if evidence_tool_calls is None
            else evidence_tool_calls
        )
        self.verifier_evidence_tool_calls = verifier_evidence_tool_calls
        self.verifier_evidence_tool_name = verifier_evidence_tool_name
        self.message = message
        self.cite_evidence = cite_evidence
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
        serialized_messages = json.dumps(messages)
        self.captured_messages.append(serialized_messages)
        observation_ids = re.findall(r"pexobs_[a-f0-9]{32}", serialized_messages)
        evidence_refs = (
            list(dict.fromkeys(observation_ids))[-20:]
            if self.cite_evidence
            else []
        )
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
                "evidence_refs": evidence_refs,
            }
        else:
            message = self.message
            if message is None:
                message = (
                    "Create report.txt containing shipped."
                    if self.action_type == "SEND_NUDGE"
                    else ""
                )
            arguments = {
                "action_type": self.action_type,
                "rationale": "validated fake decision",
                "evidence": ["workspace fact"],
                "evidence_refs": evidence_refs,
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
    assert result.model_call_count == 2
    assert result.model_name == "fake-local"
    assert result.model_class and result.model_class.endswith("FakeStructuredModel")
    assert result.inference_request_id is None
    assert result.local_invocation_id and result.local_invocation_id.startswith("pexinv_")
    assert result.input_tokens == 5
    assert result.output_tokens == 5
    assert result.action.type.value == "SEND_NUDGE"
    assert result.action.payload["text"] == "Create report.txt containing shipped."
    assert len(model.captured_messages) == 2


@pytest.mark.asyncio
async def test_returned_but_uncited_tool_output_cannot_authorize_main_action():
    result = await run_strands_async(
        _request(0.95),
        model=FakeStructuredModel("SEND_NUDGE", cite_evidence=False),
    )

    assert result.action.type.value == "NOOP"
    assert "invalid_evidence_refs" in result.diagnosis
    assert len(result.evidence_observations) == 1
    assert result.evidence_refs == []


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
    assert result.action.type.value == "NOOP"
    assert "provider-secret-sentinel" not in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "expected_status", "expected_diagnosis"),
    [
        (FailingModel(), "failed", "strands_failed:RuntimeError"),
        (SlowModel(), "timeout", "strands_timeout"),
    ],
)
async def test_real_model_failure_paths_cannot_restore_non_noop_preplan(
    monkeypatch, model, expected_status, expected_diagnosis
):
    monkeypatch.setenv("PEX_SUPERVISOR_WALL_TIMEOUT", "1")
    request = _request(0.95)
    request.scores.features["verification"] = {
        "status": "contradicted",
        "correction": "Fix exact failing test_alpha and rerun it.",
        "evidence": ["pytest_exit:1", "failed:test_alpha"],
    }

    result = await decide_async(request, model=model)

    assert result.action.type.value == "NOOP"
    assert result.used_llm is True
    assert result.inference_status == expected_status
    assert result.diagnosis == expected_diagnosis
    assert "text" not in result.action.payload


@pytest.mark.asyncio
async def test_missing_structured_runtime_result_cannot_restore_non_noop_preplan(
    monkeypatch,
):
    request = _request(0.95)
    request.scores.features["verification"] = {
        "status": "contradicted",
        "correction": "Fix exact failing test_alpha and rerun it.",
        "evidence": ["pytest_exit:1", "failed:test_alpha"],
    }

    class MissingStructuredAgent:
        event_loop_metrics = None

        async def invoke_async(self, *_args, **_kwargs):
            return SimpleNamespace(
                structured_output=None,
                metrics=None,
                stop_reason="end_turn",
            )

    monkeypatch.setattr(
        "pex_supervisor.loop.build_agent",
        lambda *_args, **_kwargs: MissingStructuredAgent(),
    )
    result = await decide_async(request, model=object())

    assert result.action.type.value == "NOOP"
    assert result.used_llm is True
    assert result.inference_status == "failed"
    assert result.diagnosis == "strands_missing_structured_output"
    assert "text" not in result.action.payload


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
async def test_completed_model_noop_is_not_replaced_by_deterministic_contradiction():
    request = _request(0.95)
    request.scores.features["verification"] = {
        "status": "contradicted",
        "correction": "The observed pytest run failed. Fix it and rerun pytest.",
        "evidence": ["pytest_exit:1"],
    }
    result = await decide_async(request, model=FakeStructuredModel("NOOP"))

    assert result.used_llm is True
    assert result.inference_status == "completed"
    assert result.action.type.value == "NOOP"
    assert result.diagnosis == "strands_structured_decision"


@pytest.mark.asyncio
async def test_completed_noop_after_tool_call_is_not_replaced_by_stale_probe_request():
    request = _request(0.9)
    request.scores.features["verification"] = {
        "status": "uncertain",
        "acceptance_status": "uncertain",
        "evidence": ["temporarily_unreadable:report.txt"],
        "evidence_gathering": {
            "state": "inspected",
            "probe": {
                "id": "probe_file_count",
                "kind": "file_count",
                "harness_type": "synthetic",
                "session_id": request.session.id,
                "project_id": request.session.project_id,
                "goal_id": request.goal.id,
                "request_event_id": request.event.event_id,
                "cwd": "C:/workspace",
                "relative_targets": ["report.txt"],
                "timeout_seconds": 60,
                "output_limit_bytes": 16_384,
            },
        },
        "verdicts": [
            {
                "status": "uncertain",
                "evidence": ["temporarily_unreadable:report.txt"],
            }
        ],
    }
    model = FakeStructuredModel("NOOP", evidence_tool_calls=1)

    result = await decide_async(request, model=model)

    assert result.action.type.value == "NOOP"
    assert result.inference_status == "completed"
    assert result.evidence_tools == ["run_verification"]
    assert result.model_call_count == 2
    assert "deterministic_truth_preserved" not in result.diagnosis


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("inference_status", "diagnosis"),
    [
        ("failed", "strands_failed:RuntimeError"),
        ("timeout", "strands_timeout"),
        ("failed", "strands_missing_structured_output"),
    ],
)
async def test_incomplete_semantic_inference_cannot_restore_deterministic_intervention(
    monkeypatch, inference_status, diagnosis
):
    request = _request(0.95)
    request.scores.features["verification"] = {
        "status": "contradicted",
        "correction": "Fix exact failing test_alpha and rerun it.",
        "evidence": ["pytest_exit:1", "failed:test_alpha"],
    }
    deterministic_action = _action_from_proposal(
        request,
        {
            "type": "SEND_NUDGE",
            "rationale": "Observed test failure.",
            "evidence": ["pytest_exit:1", "failed:test_alpha"],
            "payload": {"text": "Fix exact failing test_alpha and rerun it."},
        },
    )

    async def incomplete(*_args, **_kwargs):
        return SupervisorResult(
            action=deterministic_action,
            used_llm=True,
            diagnosis=diagnosis,
            inference_status=inference_status,
            model_call_count=1,
        )

    monkeypatch.setattr("pex_supervisor.loop.run_strands_async", incomplete)
    result = await decide_async(request, model=object())

    assert result.action.type.value == "NOOP"
    assert result.used_llm is True
    assert result.inference_status == inference_status
    assert "incomplete_inference_noop" in result.diagnosis
    assert "text" not in result.action.payload


@pytest.mark.asyncio
async def test_outer_supervisor_setup_failure_is_noop(monkeypatch):
    request = _request(0.95)
    request.scores.features["verification"] = {
        "status": "contradicted",
        "correction": "Fix exact failing test_alpha and rerun it.",
        "evidence": ["pytest_exit:1", "failed:test_alpha"],
    }

    async def unavailable(*_args, **_kwargs):
        raise RuntimeError("setup failed")

    monkeypatch.setattr("pex_supervisor.loop.run_strands_async", unavailable)
    result = await decide_async(request, model=object())

    assert result.action.type.value == "NOOP"
    assert result.used_llm is False
    assert result.inference_status == "failed"
    assert result.diagnosis == "strands_unavailable:RuntimeError"


@pytest.mark.asyncio
async def test_post_inference_failure_keeps_real_model_provenance(monkeypatch):
    request = _request(0.1)
    model = FakeStructuredModel("NOOP")

    def arbitration_failed(*_args, **_kwargs):
        raise RuntimeError("private post-processing detail")

    monkeypatch.setattr(
        "pex_supervisor.loop._preserve_deterministic_truth",
        arbitration_failed,
    )
    result = await decide_async(request, model=model)

    assert len(model.captured_messages) == 1
    assert result.action.type.value == "NOOP"
    assert result.used_llm is True
    assert result.inference_status == "completed"
    assert result.model_call_count == 1
    assert result.local_invocation_id and result.local_invocation_id.startswith("pexinv_")
    assert result.diagnosis.endswith("post_inference_failure:RuntimeError")
    assert "private post-processing detail" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_no_model_keeps_explicit_deterministic_triage(monkeypatch):
    monkeypatch.delenv("PEX_FORCE_LLM", raising=False)
    request = _request(0.95)
    request.scores.features["verification"] = {
        "status": "contradicted",
        "correction": "Fix exact failing test_alpha and rerun it.",
        "evidence": ["pytest_exit:1", "failed:test_alpha"],
    }

    result = await decide_async(request, model=None)

    assert result.action.type.value == "SEND_NUDGE"
    assert result.used_llm is False
    assert result.inference_status == "not_attempted"
    assert result.diagnosis == "deterministic_triage_no_supervisor_model"


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
async def test_supported_claim_alone_cannot_suppress_semantic_intervention():
    request = _request(0.1)
    request.goal.acceptance_criteria = ["tests pass", "report.txt exists"]
    request.scores.features["verification"] = {
        "status": "supported",
        "acceptance_status": "uncertain",
        "evidence": ["pytest_ok=true"],
        "verdicts": [{"status": "supported", "evidence": ["pytest_ok=true"]}],
    }
    model = FakeStructuredModel(
        "SEND_NUDGE",
        verifier_approved=True,
        verifier_evidence_tool_calls=1,
        verifier_evidence_tool_name="get_recent_events",
    )

    result = await decide_async(request, model=model)

    assert result.action.type.value == "SEND_NUDGE"
    assert "independent_verifier_approved" in result.diagnosis
    assert "verified_noop_preserved" not in result.diagnosis


@pytest.mark.asyncio
async def test_same_type_semantic_action_keeps_model_wording_after_verification():
    request = _request(0.95)
    request.scores.features["verification"] = {
        "status": "contradicted",
        "acceptance_status": "contradicted",
        "correction": "The observed pytest run failed. Fix it and rerun pytest.",
        "evidence": ["pytest_exit:1", "failed:test_alpha"],
    }
    semantic_text = (
        "test_alpha failed in the latest observed pytest run. "
        "Fix test_alpha and rerun pytest."
    )
    model = FakeStructuredModel(
        "SEND_NUDGE",
        message=semantic_text,
        verifier_approved=True,
        verifier_evidence_tool_calls=1,
        verifier_evidence_tool_name="get_recent_events",
    )

    result = await decide_async(request, model=model)

    assert result.action.type.value == "SEND_NUDGE"
    assert result.action.payload["text"] == semantic_text
    assert "independent_verifier_approved" in result.diagnosis
    assert "deterministic_truth_preserved" not in result.diagnosis


@pytest.mark.asyncio
async def test_verifier_rejection_never_restores_non_noop_preplan():
    request = _request(0.95)
    request.scores.features["verification"] = {
        "status": "contradicted",
        "acceptance_status": "contradicted",
        "correction": "The observed pytest run failed. Fix it and rerun pytest.",
        "evidence": ["pytest_exit:1", "failed:test_alpha"],
    }
    model = FakeStructuredModel(
        "SEND_NUDGE",
        verifier_approved=False,
        verifier_evidence=["proposal not supported"],
        verifier_evidence_tool_calls=1,
        verifier_evidence_tool_name="get_recent_events",
    )

    result = await decide_async(request, model=model)

    assert result.action.type.value == "NOOP"
    assert "independent_verifier_rejected" in result.diagnosis
    assert "text" not in result.action.payload
    assert result.independent_verifier is not None
    assert result.independent_verifier.approved is False
    assert result.independent_verifier.status == "rejected"
    assert result.independent_verifier.model_call_count == 2


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
    assert result.model_call_count == 4
    assert len(model.captured_messages) == 4
    assert "get_recent_events" in result.evidence_tools
    assert result.independent_verifier is not None
    assert result.independent_verifier.approved is True
    assert result.independent_verifier.status == "approved"
    assert result.independent_verifier.model_call_count == 2
    assert result.independent_verifier.evidence_tools == ["get_recent_events"]
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
    assert result.model_call_count == 4
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
    assert result.model_call_count == 3
    assert result.independent_verifier is not None
    assert result.independent_verifier.approved is False
    assert result.independent_verifier.status == "missing_or_invalid_evidence_refs"
    assert result.independent_verifier.model_call_count == 1
    assert any(
        "independent_verifier_status=missing_or_invalid_evidence_refs" in item
        for item in result.traces
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "failed"),
        ("model_call_count", 0),
        ("model_call_count", True),
        ("model_call_count", "1"),
        ("evidence", []),
        ("evidence_tools", []),
    ],
)
async def test_raw_approved_verifier_receipt_must_meet_shared_authority_contract(
    monkeypatch, field, value
):
    request = _request(0.1)

    async def forged_receipt(*_args, **_kwargs):
        receipt = {
            "approved": True,
            "status": "approved",
            "rationale": "claimed approval",
            "evidence": ["observable verification receipt"],
            "evidence_tools": ["get_recent_events"],
            "model_call_count": 1,
            "input_tokens": 1,
            "output_tokens": 1,
            "latency_ms": 1,
        }
        receipt[field] = value
        return receipt

    monkeypatch.setattr(
        "pex_supervisor.loop.run_independent_verifier_async",
        forged_receipt,
    )
    result = await decide_async(request, model=FakeStructuredModel("SEND_NUDGE"))

    assert result.action.type.value == "NOOP"
    assert "independent_verifier_rejected" in result.diagnosis
    assert result.independent_verifier is not None
    assert result.independent_verifier.approved is True
    assert result.independent_verifier.authorizes_intervention() is False


@pytest.mark.asyncio
async def test_raw_verifier_numeric_telemetry_does_not_coerce_strings_or_booleans(
    monkeypatch,
):
    request = _request(0.1)

    async def forged_receipt(*_args, **_kwargs):
        return {
            "approved": True,
            "status": "approved",
            "rationale": "valid decision with forged telemetry scalars",
            "evidence": ["observable verification receipt"],
            "evidence_tools": ["get_recent_events"],
            "model_call_count": 1,
            "input_tokens": "7",
            "output_tokens": True,
            "latency_ms": "9",
        }

    monkeypatch.setattr(
        "pex_supervisor.loop.run_independent_verifier_async",
        forged_receipt,
    )
    result = await decide_async(request, model=FakeStructuredModel("SEND_NUDGE"))

    assert result.action.type.value == "NOOP"
    assert result.independent_verifier is not None
    assert result.independent_verifier.authorizes_intervention() is False
    assert result.independent_verifier.input_tokens == 0
    assert result.independent_verifier.output_tokens == 0
    assert result.independent_verifier.latency_ms == 0
    assert result.input_tokens == 5
    assert result.output_tokens == 5


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
    assert result.model_call_count == 4


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
    assert result.model_call_count == 2
    assert result.action.type.value == "NOOP"
    assert "independent_verifier_rejected" in result.diagnosis
    assert any(
        "independent_verifier_status=failed:RuntimeError" in item
        for item in result.traces
    )


@pytest.mark.asyncio
async def test_foreign_verifier_observations_fail_closed_without_losing_main_receipts(
    monkeypatch,
):
    request = _request(0.1)
    foreign = request.model_copy(deep=True)
    foreign.session.id = "foreign-session"
    collector = EvidenceObservationCollector(
        foreign,
        stage="verifier",
        invocation_id="foreign-verifier",
    )
    collector.record(
        tool_name="get_recent_events",
        arguments_json="{}",
        value={"events": []},
    )
    observation = collector.observations[0]

    async def forged_receipt(*_args, **_kwargs):
        return {
            "approved": True,
            "status": "approved",
            "rationale": "foreign receipt",
            "evidence": ["foreign evidence"],
            "invocation_id": "foreign-verifier",
            "evidence_observations": [observation],
            "evidence_refs": [observation.observation_id],
            "model_call_count": 1,
        }

    monkeypatch.setattr(
        "pex_supervisor.loop.run_independent_verifier_async",
        forged_receipt,
    )
    result = await decide_async(request, model=FakeStructuredModel("SEND_NUDGE"))

    assert result.action.type.value == "NOOP"
    assert len(result.evidence_observations) == 1
    assert result.independent_verifier is not None
    assert result.independent_verifier.evidence_observations == []
    assert result.independent_verifier.authorizes_intervention() is False


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_invocation_id", [None, "token=unsafe-verifier-secret"])
async def test_invalid_verifier_invocation_drops_receipts_without_losing_main_receipts(
    monkeypatch,
    raw_invocation_id,
):
    request = _request(0.1)
    collector = EvidenceObservationCollector(
        request,
        stage="verifier",
        invocation_id="valid-verifier",
    )
    collector.record(
        tool_name="get_recent_events",
        arguments_json="{}",
        value={"events": []},
    )
    observation = collector.observations[0]

    async def forged_receipt(*_args, **_kwargs):
        return {
            "approved": True,
            "status": "approved",
            "rationale": "invalid invocation receipt",
            "evidence": ["claimed evidence"],
            "invocation_id": raw_invocation_id,
            "evidence_observations": [observation],
            "evidence_refs": [observation.observation_id],
            "model_call_count": 1,
        }

    monkeypatch.setattr(
        "pex_supervisor.loop.run_independent_verifier_async",
        forged_receipt,
    )
    result = await decide_async(request, model=FakeStructuredModel("SEND_NUDGE"))

    assert result.action.type.value == "NOOP"
    assert len(result.evidence_observations) == 1
    assert result.independent_verifier is not None
    assert result.independent_verifier.evidence_observations == []
    assert result.independent_verifier.evidence_refs == []
