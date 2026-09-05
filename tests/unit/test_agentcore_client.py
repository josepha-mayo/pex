from __future__ import annotations

import asyncio
import hashlib
import io
import json
import threading
import traceback
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pex_bridge.agentcore import (
    AgentCoreConfigurationError,
    AgentCoreDeliveryUncertainError,
    AgentCorePreDispatchError,
    AgentCoreProtocolError,
    AgentCoreSupervisorClient,
    AgentCoreTransportError,
    SupervisorRouter,
    cloud_request,
    compact_workspace_evidence,
    request_envelope,
    runtime_session_id,
    transport_invocation_id,
)
from pex_bridge.config import Settings
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import (
    IndependentVerifierReceipt,
    SupervisorEvidenceObservation,
    SupervisorRequest,
    SupervisorResult,
    TrajectoryScores,
    supervisor_request_digest,
)
from pydantic import ValidationError

ARN = (
    "arn:aws:bedrock-agentcore:eu-north-1:123456789012:"
    "runtime/PexRuntime-ABCDEFGHIJ"
)


def _request(event_type: EventType = EventType.STOP) -> SupervisorRequest:
    now = datetime.now(UTC)
    session = HarnessSession(
        id="session_exact",
        harness_type=HarnessType.CODEX,
        vendor_session_id="vendor-secret-session",
        project_id=r"C:\Users\JosephMayo\Projects\private-repo",
        goal_id="goal_exact",
        cwd=r"C:\Users\JosephMayo\Projects\private-repo",
        repo=r"C:\Users\JosephMayo\Projects\private-repo",
        branch="private-branch",
        status=SessionStatus.STOPPED,
        capabilities={"send_message": True, "notes": "local-only detail"},
        metadata={"api_key": "should-never-leave"},
    )
    event = HarnessEvent(
        event_id="evt_exact",
        ts=now,
        harness_type=HarnessType.CODEX,
        session_id=session.id,
        project_id=session.project_id,
        event_type=event_type,
        message_delta=(
            "Completed report at "
            r"C:\Users\JosephMayo\Projects\private-repo\src\report.txt "
            "Authorization: Bearer top-secret-token"
        ),
        file_paths=[
            r"C:\Users\JosephMayo\Projects\private-repo\src\report.txt"
        ],
        tool_input={"password": "should-never-leave"},
        process_state={"stdout": "raw process output"},
        metadata={"token": "should-never-leave"},
    )
    goal = Goal(
        id="goal_exact",
        project_id=session.project_id,
        title="Ship report",
        objective="Create src/report.txt",
        acceptance_criteria=["src/report.txt"],
        evidence_requirements=["src/report.txt"],
        created_at=now,
        updated_at=now,
    )
    scores = TrajectoryScores(
        premature_completion=0.9,
        features={
            "claims": [{"statement": "report exists", "kind": "complete"}],
            "verification": {
                "status": "supported",
                "api_key": "should-never-leave",
            },
            "prefetched_evidence": {
                "observed_file_count": 1,
                "files": [{"path": "src/report.txt", "bytes": 7}],
            },
            "raw_diff": "must not leave",
        },
    )
    return SupervisorRequest(
        session=session,
        goal=goal,
        event=event,
        recent_events=[event],
        scores=scores,
        notes="verify local state",
    )


def _result(
    request: SupervisorRequest,
    *,
    session_id: str | None = None,
    goal_id: str | None = None,
) -> SupervisorResult:
    return SupervisorResult(
        action=ProposedAction(
            type=InterventionType.NOOP,
            session_id=session_id or request.session.id,
            goal_id=goal_id if goal_id is not None else request.goal.id,
            rationale="verified complete",
        ),
        used_llm=True,
        model_name="bedrock-test-model",
        diagnosis="strands_structured_decision",
        inference_status="completed",
        model_call_count=1,
        runtime="strands-agents",
        auth_mode="aws_sigv4",
    )


def _observation(request: SupervisorRequest, stage: str) -> SupervisorEvidenceObservation:
    observation_id = "pexobs_" + ("1" if stage == "main" else "2") * 32
    output = json.dumps({
        "pex_observation_id": observation_id,
        "status": "supported",
        "evidence": ["observed verification receipt"],
    }, separators=(",", ":"))
    return SupervisorEvidenceObservation(
        observation_id=observation_id, invocation_id=f"pexinv_{stage}_fixture",
        stage=stage, request_digest=supervisor_request_digest(cloud_request(request)),
        session_id=request.session.id, goal_id=request.goal.id,
        event_id=request.event.event_id, observed_at=datetime.now(UTC),
        tool_name="run_verification", arguments_json="{}", output=output,
        output_sha256=hashlib.sha256(output.encode()).hexdigest(),
    )


def _approved_verifier_receipt(request: SupervisorRequest) -> IndependentVerifierReceipt:
    observation = _observation(request, "verifier")
    return IndependentVerifierReceipt(
        approved=True,
        status="approved",
        rationale="A separate verifier checked observable evidence.",
        evidence=["observed verification receipt"],
        evidence_tools=["run_verification"],
        invocation_id=observation.invocation_id,
        evidence_observations=[observation],
        evidence_refs=[observation.observation_id],
        model_call_count=2,
        input_tokens=4,
        output_tokens=3,
        latency_ms=2,
    )


def _remote_nudge(request: SupervisorRequest) -> SupervisorResult:
    remote = _result(request)
    observation = _observation(request, "main")
    remote.local_invocation_id = observation.invocation_id
    remote.evidence_observations = [observation]
    remote.evidence_refs = [observation.observation_id]
    remote.action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=request.session.id,
        goal_id=request.goal.id,
        payload={"text": "Inspect src/report.txt before stopping."},
        rationale="Observed report evidence is incomplete.",
        evidence=["missing:src/report.txt"],
        risk=RiskLevel.NONE,
        reversible=True,
        authority_required=Authority.HUMAN,
        requires_capability="stop",
    )
    return remote


class FakeAwsClient:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[dict] = []

    def invoke_agent_runtime(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class BlockingAwsClient(FakeAwsClient):
    def __init__(self, response: dict) -> None:
        super().__init__(response)
        self.started = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()

    def invoke_agent_runtime(self, **kwargs):
        self.calls.append(kwargs)
        self.started.set()
        try:
            if not self.release.wait(5):
                raise RuntimeError("test provider release timed out")
            return self.response
        finally:
            self.finished.set()


async def _wait_thread_event(event: threading.Event) -> None:
    assert await asyncio.wait_for(asyncio.to_thread(event.wait, 2), timeout=3)


def _settings(tmp_path: Path, mode: str = "agentcore") -> Settings:
    return Settings(
        home=tmp_path,
        supervisor_mode=mode,
        agentcore_runtime_arn=ARN,
        agentcore_region="eu-north-1",
    )


def _aws_response(
    request: SupervisorRequest,
    result: SupervisorResult,
    **overrides,
) -> dict:
    body = json.dumps(
        {
            "schema_version": 1,
            "invocation_id": transport_invocation_id(request),
            "result": result.model_dump(mode="json"),
        }
    ).encode()
    response = {
        "statusCode": 200,
        "contentType": "application/json",
        "runtimeSessionId": runtime_session_id(request.session.id),
        "response": io.BytesIO(body),
        "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "aws-request-1"},
    }
    response.update(overrides)
    return response


@pytest.mark.asyncio
async def test_agentcore_client_invokes_bound_runtime_with_sanitized_payload(tmp_path):
    request = _request()
    aws = FakeAwsClient(_aws_response(request, _result(request)))
    client = AgentCoreSupervisorClient(_settings(tmp_path), client=aws)

    result = await client.decide(request)

    assert result.execution_mode == "agentcore"
    assert result.transport == "bedrock-agentcore"
    assert result.transport_invocation_id == transport_invocation_id(request)
    assert result.transport_request_id == "aws-request-1"
    assert result.inference_status == "completed"
    assert len(aws.calls) == 1
    call = aws.calls[0]
    assert call["agentRuntimeArn"] == ARN
    assert call["qualifier"] == "DEFAULT"
    assert call["contentType"] == "application/json"
    assert call["accept"] == "application/json"
    assert call["runtimeSessionId"] == runtime_session_id(request.session.id)
    assert len(call["runtimeSessionId"]) >= 33

    payload = call["payload"].decode()
    decoded = json.loads(payload)
    assert decoded["invocation_id"] == transport_invocation_id(request)
    cloud = decoded["request"]
    assert decoded["schema_version"] == 1
    assert cloud["session"]["id"] == request.session.id
    assert cloud["session"]["cwd"] is None
    assert cloud["session"]["repo"] is None
    assert cloud["session"]["metadata"] == {}
    assert cloud["event"]["tool_input"] is None
    assert cloud["event"]["process_state"] is None
    assert "raw_diff" not in cloud["scores"]["features"]
    assert "private-repo" not in payload
    assert "should-never-leave" not in payload
    assert "top-secret-token" not in payload
    assert "<workspace>" in payload


@pytest.mark.asyncio
async def test_agentcore_action_is_reconstructed_under_local_authority_contract(tmp_path):
    request = _request()
    remote = _remote_nudge(request)
    remote.independent_verifier = _approved_verifier_receipt(request)
    remote.model_call_count = 3
    client = AgentCoreSupervisorClient(
        _settings(tmp_path),
        client=FakeAwsClient(_aws_response(request, remote)),
    )

    result = await client.decide(request)

    assert result.action.type == InterventionType.SEND_NUDGE
    assert result.action.reversible is False
    assert result.action.authority_required == Authority.LOCAL_POLICY
    assert result.action.requires_capability == "send_message"
    assert result.independent_verifier == remote.independent_verifier


@pytest.mark.asyncio
async def test_agentcore_stale_runtime_action_without_verifier_receipt_is_noop(tmp_path):
    request = _request()
    remote = _remote_nudge(request)
    client = AgentCoreSupervisorClient(
        _settings(tmp_path),
        client=FakeAwsClient(_aws_response(request, remote)),
    )

    result = await client.decide(request)

    assert result.action.type == InterventionType.NOOP
    assert result.action.payload == {}
    assert result.action.evidence == [
        "agentcore_verifier_contract:missing_receipt"
    ]
    assert result.inference_status == "completed"
    assert result.transport_status == "completed"
    assert result.independent_verifier is None
    assert "agentcore_verifier_contract_rejected:missing_receipt" in result.diagnosis


@pytest.mark.asyncio
async def test_agentcore_rejected_verifier_receipt_is_preserved_but_action_is_noop(tmp_path):
    request = _request()
    remote = _remote_nudge(request)
    remote.independent_verifier = IndependentVerifierReceipt(
        approved=False,
        status="rejected",
        rationale="The proposed correction was not supported.",
        evidence=["report evidence was inconclusive"],
        evidence_tools=["inspect_artifact"],
        model_call_count=1,
    )
    remote.model_call_count = 2
    client = AgentCoreSupervisorClient(
        _settings(tmp_path),
        client=FakeAwsClient(_aws_response(request, remote)),
    )

    result = await client.decide(request)

    assert result.action.type == InterventionType.NOOP
    assert result.action.evidence == ["agentcore_verifier_contract:not_approved"]
    assert result.independent_verifier is not None
    assert result.independent_verifier.approved is False
    assert result.independent_verifier.status == "rejected"
    assert result.transport_status == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("receipt_update", "reason"),
    [
        ({"status": "rejected"}, "invalid_status"),
        ({"model_call_count": 0}, "missing_verifier_call"),
        ({"evidence_refs": []}, "missing_evidence_observation"),
        ({"evidence_observations": [], "evidence_refs": []}, "missing_evidence_observation"),
    ],
)
async def test_agentcore_incomplete_approved_verifier_receipt_is_noop(
    tmp_path,
    receipt_update,
    reason,
):
    request = _request()
    remote = _remote_nudge(request)
    remote.independent_verifier = _approved_verifier_receipt(request).model_copy(
        update=receipt_update
    )
    remote.model_call_count = 3
    client = AgentCoreSupervisorClient(
        _settings(tmp_path),
        client=FakeAwsClient(_aws_response(request, remote)),
    )

    result = await client.decide(request)

    assert result.action.type == InterventionType.NOOP
    assert result.action.evidence == [f"agentcore_verifier_contract:{reason}"]
    assert result.transport_status == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("used_llm", "aggregate_calls"),
    [(False, 3), (True, 2)],
)
async def test_agentcore_verifier_receipt_requires_distinct_main_inference(
    tmp_path,
    used_llm,
    aggregate_calls,
):
    request = _request()
    remote = _remote_nudge(request)
    remote.independent_verifier = _approved_verifier_receipt(request)
    remote.used_llm = used_llm
    remote.model_call_count = aggregate_calls
    client = AgentCoreSupervisorClient(
        _settings(tmp_path),
        client=FakeAwsClient(_aws_response(request, remote)),
    )

    result = await client.decide(request)

    assert result.action.type == InterventionType.NOOP
    assert result.action.evidence == [
        "agentcore_verifier_contract:missing_main_inference"
    ]
    assert result.transport_status == "completed"


@pytest.mark.asyncio
async def test_agentcore_runtime_cannot_approve_from_uncertain_verification_alone(tmp_path):
    request = _request()
    request.scores.features["verification"] = {
        "status": "uncertain",
        "acceptance_status": "uncertain",
        "evidence": ["no_external_check"],
    }
    remote = _remote_nudge(request)
    remote.independent_verifier = _approved_verifier_receipt(request)
    remote.model_call_count = 3
    client = AgentCoreSupervisorClient(
        _settings(tmp_path),
        client=FakeAwsClient(_aws_response(request, remote)),
    )

    result = await client.decide(request)

    assert result.action.type == InterventionType.NOOP
    assert result.action.evidence == [
        "agentcore_verifier_contract:uncertain_evidence"
    ]
    assert result.independent_verifier is not None
    assert result.independent_verifier.approved is True
    assert result.transport_status == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed_update",
    [
        {"model_call_count": -1},
        {"model_call_count": True},
        {"approved": "true"},
    ],
)
async def test_agentcore_malformed_verifier_receipt_is_protocol_uncertain(
    tmp_path,
    malformed_update,
):
    request = _request()
    remote = _remote_nudge(request)
    response = _aws_response(request, remote)
    envelope = json.loads(response["response"].read())
    receipt = {
        "approved": True,
        "status": "approved",
        "evidence": ["observed verification receipt"],
        "evidence_tools": ["run_verification"],
        "model_call_count": 1,
    }
    receipt.update(malformed_update)
    envelope["result"]["independent_verifier"] = receipt
    response["response"] = io.BytesIO(json.dumps(envelope).encode())
    client = AgentCoreSupervisorClient(
        _settings(tmp_path),
        client=FakeAwsClient(response),
    )

    with pytest.raises(AgentCoreDeliveryUncertainError) as caught:
        await client.decide(request)

    assert caught.value.reason_code == "response_protocol_failure"


@pytest.mark.asyncio
async def test_agentcore_verifier_receipt_is_redacted_before_local_provenance(tmp_path):
    request = _request()
    remote = _remote_nudge(request)
    secret = "super-secret-verifier-value"
    workspace = request.session.cwd
    remote.independent_verifier = _approved_verifier_receipt(request).model_copy(
        update={
            "rationale": f"Checked {workspace}; token={secret}",
            "evidence": [f"Observed {workspace}\\report.txt password={secret}"],
        }
    )
    remote.model_call_count = 3
    client = AgentCoreSupervisorClient(
        _settings(tmp_path),
        client=FakeAwsClient(_aws_response(request, remote)),
    )

    result = await client.decide(request)
    rendered = result.model_dump_json()

    assert result.action.type == InterventionType.SEND_NUDGE
    assert workspace.casefold() not in rendered.casefold()
    assert secret not in rendered
    assert "<workspace>" in rendered
    assert "[REDACTED:credential_assignment]" in rendered


@pytest.mark.asyncio
async def test_agentcore_cannot_serialize_bridge_owned_context_delivery(tmp_path):
    request = _request()
    remote = _result(request)
    remote.action = ProposedAction(
        type=InterventionType.FRESH_HANDOFF,
        session_id=request.session.id,
        goal_id=request.goal.id,
        payload={"bundle": {"fabricated": "remote context"}},
        rationale="Share context.",
        evidence=["remote-only"],
        risk=RiskLevel.NONE,
        reversible=True,
    )
    client = AgentCoreSupervisorClient(
        _settings(tmp_path),
        client=FakeAwsClient(_aws_response(request, remote)),
    )

    result = await client.decide(request)

    assert result.action.type == InterventionType.NOOP
    assert "must be assembled" in result.action.payload["invalid_proposal"]


def test_cloud_request_is_valid_and_keeps_only_numeric_capabilities():
    safe = cloud_request(_request())
    assert safe.session.capabilities == {"send_message": True}
    assert safe.session.vendor_session_id.startswith("vendor_")
    assert safe.goal is not None
    assert safe.goal.project_id.startswith("p_")


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["main", "verifier"])
@pytest.mark.parametrize("field", ["request_digest", "session_id", "goal_id", "event_id"])
async def test_remote_observation_must_match_exact_dispatched_request(tmp_path, stage, field):
    request = _request()
    remote = _remote_nudge(request)
    remote.independent_verifier = _approved_verifier_receipt(request)
    remote.model_call_count = 3
    receipt = remote if stage == "main" else remote.independent_verifier
    receipt.evidence_observations = [receipt.evidence_observations[0].model_copy(update={
        field: "f" * 64 if field == "request_digest" else "foreign-authority",
    })]
    aws = FakeAwsClient(_aws_response(request, remote))
    client = AgentCoreSupervisorClient(_settings(tmp_path), client=aws)
    with pytest.raises(AgentCoreDeliveryUncertainError) as caught:
        await client.decide(request)
    assert caught.value.reason_code == "response_protocol_failure"
    assert len(aws.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("unsafe", ["secret", "escaped_path", "bad_hash", "unresolved_ref"])
async def test_remote_exact_observations_are_rejected_not_rewritten(tmp_path, unsafe):
    request = _request()
    remote = _remote_nudge(request)
    remote.independent_verifier = _approved_verifier_receipt(request)
    remote.model_call_count = 3
    observation = remote.evidence_observations[0]
    if unsafe == "unresolved_ref":
        remote.evidence_refs = ["pexobs_" + "f" * 32]
    elif unsafe == "bad_hash":
        remote.evidence_observations = [observation.model_copy(update={"output_sha256": "0" * 64})]
    else:
        value = {"password": "not-for-a-model-123"} if unsafe == "secret" else {
            "file": request.session.cwd + "\\report.txt",
        }
        output = json.dumps({"pex_observation_id": observation.observation_id, **value})
        remote.evidence_observations = [observation.model_copy(update={
            "output": output, "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
        })]
    client = AgentCoreSupervisorClient(
        _settings(tmp_path), client=FakeAwsClient(_aws_response(request, remote)),
    )
    with pytest.raises(AgentCoreDeliveryUncertainError) as caught:
        await client.decide(request)
    assert caught.value.reason_code == "response_protocol_failure"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["shared_invocation", "shared_observation", "unsafe_label"])
async def test_remote_observation_stages_have_distinct_safe_identity(tmp_path, invalid):
    request = _request()
    remote = _remote_nudge(request)
    verifier = _approved_verifier_receipt(request)
    remote.independent_verifier = verifier
    remote.model_call_count = 3
    observation = verifier.evidence_observations[0]
    if invalid == "shared_invocation":
        verifier.invocation_id = remote.local_invocation_id
        observation = observation.model_copy(update={"invocation_id": remote.local_invocation_id})
    elif invalid == "shared_observation":
        shared_id = remote.evidence_observations[0].observation_id
        output = json.dumps({"pex_observation_id": shared_id, "status": "supported"})
        observation = observation.model_copy(update={
            "observation_id": shared_id, "output": output,
            "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
        })
        verifier.evidence_refs = [shared_id]
    else:
        observation = observation.model_copy(update={"tool_name": "password=private-value"})
    verifier.evidence_observations = [observation]
    aws = FakeAwsClient(_aws_response(request, remote))
    client = AgentCoreSupervisorClient(_settings(tmp_path), client=aws)
    with pytest.raises(AgentCoreDeliveryUncertainError) as caught:
        await client.decide(request)
    assert caught.value.reason_code == "response_protocol_failure"
    assert len(aws.calls) == 1


@pytest.mark.asyncio
async def test_remote_tool_names_cannot_disguise_uncertain_verification_only(tmp_path):
    request = _request()
    request.scores.features["verification"] = {
        "status": "uncertain", "acceptance_status": "uncertain",
    }
    remote = _remote_nudge(request)
    remote.independent_verifier = _approved_verifier_receipt(request)
    remote.independent_verifier.evidence_tools = ["run_verification", "get_recent_events"]
    remote.model_call_count = 3
    client = AgentCoreSupervisorClient(
        _settings(tmp_path), client=FakeAwsClient(_aws_response(request, remote)),
    )
    result = await client.decide(request)
    assert result.action.type == InterventionType.NOOP
    assert result.action.evidence == ["agentcore_verifier_contract:uncertain_evidence"]


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", [EventType.STOP, EventType.AGENT_RESPONSE])
@pytest.mark.parametrize(
    ("inference_status", "used_llm", "model_call_count", "reason"),
    [
        ("failed", True, 3, "main_inference_not_completed"),
        ("timeout", True, 3, "main_inference_not_completed"),
        ("not_attempted", False, 0, "main_inference_not_completed"),
        ("completed", False, 3, "missing_main_inference"),
        ("completed", True, 0, "missing_main_inference"),
    ],
)
async def test_every_remote_intervention_requires_completed_main_inference(
    tmp_path, event_type, inference_status, used_llm, model_call_count, reason,
):
    request = _request()
    request.event.event_type = event_type
    remote = _remote_nudge(request)
    remote.independent_verifier = _approved_verifier_receipt(request)
    remote.inference_status = inference_status
    remote.used_llm = used_llm
    remote.model_call_count = model_call_count
    client = AgentCoreSupervisorClient(
        _settings(tmp_path), client=FakeAwsClient(_aws_response(request, remote)),
    )
    result = await client.decide(request)
    assert result.action.type == InterventionType.NOOP
    assert result.action.evidence == [f"agentcore_verifier_contract:{reason}"]
    assert result.evidence_observations == remote.evidence_observations
    assert result.inference_status == inference_status


@pytest.mark.asyncio
async def test_remote_intervention_requires_main_observation_refs_too(tmp_path):
    request = _request()
    remote = _remote_nudge(request)
    remote.evidence_refs = []
    remote.independent_verifier = _approved_verifier_receipt(request)
    remote.model_call_count = 3
    client = AgentCoreSupervisorClient(
        _settings(tmp_path), client=FakeAwsClient(_aws_response(request, remote)),
    )
    result = await client.decide(request)
    assert result.action.type == InterventionType.NOOP
    assert result.action.evidence == [
        "agentcore_verifier_contract:missing_main_evidence_observation",
    ]
    assert result.evidence_observations == remote.evidence_observations


def test_cloud_request_does_not_mislabel_external_absolute_path_as_workspace():
    request = _request()
    request.event.file_paths.append(r"D:\Outside\private\note.txt")

    safe = cloud_request(request)

    assert "<workspace>/src/report.txt" in safe.event.file_paths
    assert "<absolute>/Outside/private/note.txt" in safe.event.file_paths
    assert all("D:" not in path for path in safe.event.file_paths)


def test_cloud_request_converts_nonfinite_feature_values_to_strict_json():
    request = _request()
    request.scores.features["verification"]["nonfinite"] = float("nan")

    encoded = request_envelope(request, max_bytes=262_144)
    cloud = json.loads(encoded)["request"]

    assert cloud["scores"]["features"]["verification"]["nonfinite"] is None
    assert "NaN" not in encoded.decode("utf-8")


def test_agentcore_boundary_recompacts_raw_workspace_evidence_before_cloud():
    request = _request()
    request.scores.features["prefetched_evidence"] = {
        "workspace": r"C:\Users\JosephMayo\Projects\private-repo",
        "files": ["src/report.txt"],
        "file_meta": [{"path": "src/report.txt", "bytes": 7}],
        "artifacts": [
            {
                "path": "results.jsonl",
                "bytes": 100,
                "tail": "RAW_ARTIFACT_CONTENT_MUST_NOT_LEAVE",
            }
        ],
        "git": {
            "available": True,
            "status": " M src/report.txt",
            "diff": "RAW_GIT_DIFF_MUST_NOT_LEAVE",
        },
    }

    encoded = request_envelope(request, max_bytes=262_144)
    rendered = encoded.decode("utf-8")
    workspace = json.loads(rendered)["request"]["scores"]["features"][
        "prefetched_evidence"
    ]

    assert "RAW_ARTIFACT_CONTENT_MUST_NOT_LEAVE" not in rendered
    assert "RAW_GIT_DIFF_MUST_NOT_LEAVE" not in rendered
    assert workspace["observed_file_count"] == 1
    assert workspace["files"] == [{"path": "src/report.txt", "bytes": 7}]
    assert workspace["artifacts"] == [{"path": "results.jsonl", "bytes": 100}]
    assert workspace["git"] == {
        "available": True,
        "dirty": True,
        "changed_file_count": 1,
        "changed_paths": ["src/report.txt"],
    }


def test_workspace_compaction_bounds_cycles_invalid_collections_and_large_numbers():
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    compacted = compact_workspace_evidence(
        {
            "files": "not-a-file-list",
            "file_meta": 42,
            "artifacts": [
                {"path": "results.jsonl", "bytes": 10**5_000, "extra": cyclic}
            ],
            "observed_file_count": -10,
            "git": {"changed_file_count": 10**5_000},
            "pytest": {"exit_code": 10**5_000},
        }
    )

    assert compacted["files"] == []
    assert compacted["observed_file_count"] == 0
    assert compacted["artifacts"][0]["bytes"] == (1 << 63) - 1
    assert compacted["git"]["changed_file_count"] == 1_000_000_000
    assert compacted["pytest"]["exit_code"] == (1 << 31) - 1


def test_agentcore_request_binding_normalizes_windows_project_spelling():
    request = _request()
    request.event.project_id = "c:/users/josephmayo/projects/private-repo/"
    request.recent_events[0].project_id = "C:/USERS/JOSEPHMAYO/PROJECTS/PRIVATE-REPO"

    encoded = request_envelope(request, max_bytes=262_144)

    assert json.loads(encoded)["request"]["session"]["project_id"].startswith("p_")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_id", "goal_id"),
    [
        ("wrong-session", "goal_exact"),
        ("session_exact", "wrong-goal"),
    ],
)
async def test_agentcore_client_rejects_cross_binding(
    tmp_path, session_id, goal_id
):
    request = _request()
    aws = FakeAwsClient(
        _aws_response(
            request,
            _result(request, session_id=session_id, goal_id=goal_id),
        )
    )
    client = AgentCoreSupervisorClient(_settings(tmp_path), client=aws)

    with pytest.raises(AgentCoreDeliveryUncertainError) as caught:
        await client.decide(request)
    assert caught.value.reason_code == "response_protocol_failure"
    assert caught.value.transport_invocation_id == transport_invocation_id(request)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"runtimeSessionId": "wrong-runtime-session"},
        {"runtimeSessionId": None},
    ],
)
async def test_agentcore_client_rejects_runtime_session_mismatch(
    tmp_path, overrides
):
    request = _request()
    aws = FakeAwsClient(_aws_response(request, _result(request), **overrides))
    client = AgentCoreSupervisorClient(_settings(tmp_path), client=aws)

    with pytest.raises(AgentCoreDeliveryUncertainError) as caught:
        await client.decide(request)
    assert caught.value.reason_code == "response_protocol_failure"


@pytest.mark.asyncio
async def test_agentcore_client_rejects_stale_same_session_response(tmp_path):
    request = _request()
    response = _aws_response(request, _result(request))
    envelope = json.loads(response["response"].read())
    envelope["invocation_id"] = "pexinv_" + "0" * 32
    response["response"] = io.BytesIO(json.dumps(envelope).encode())
    client = AgentCoreSupervisorClient(_settings(tmp_path), client=FakeAwsClient(response))

    with pytest.raises(AgentCoreDeliveryUncertainError) as caught:
        await client.decide(request)
    assert caught.value.reason_code == "response_protocol_failure"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("binding", "expected"),
    [
        ("event_session", "event.*different session"),
        ("event_harness", "event.*different harness"),
        ("event_project", "event.*different project"),
        ("recent_harness", "recent event.*different harness"),
        ("recent_project", "recent event.*different project"),
    ],
)
async def test_agentcore_client_rejects_inconsistent_request_before_aws(
    tmp_path, binding, expected
):
    request = _request()
    if binding == "event_session":
        request.event.session_id = "wrong-session"
    elif binding == "event_harness":
        request.event.harness_type = HarnessType.CURSOR
    elif binding == "event_project":
        request.event.project_id = "wrong-project"
    elif binding == "recent_harness":
        request.recent_events = [request.event.model_copy(deep=True)]
        request.recent_events[0].harness_type = HarnessType.CURSOR
    else:
        request.recent_events = [request.event.model_copy(deep=True)]
        request.recent_events[0].project_id = "wrong-project"
    aws = FakeAwsClient(_aws_response(_request(), _result(_request())))
    client = AgentCoreSupervisorClient(_settings(tmp_path), client=aws)

    with pytest.raises(AgentCoreProtocolError, match=expected):
        await client.decide(request)
    assert aws.calls == []


@pytest.mark.asyncio
async def test_agentcore_client_rejects_non_json_and_oversized_response(tmp_path):
    request = _request()
    non_json = FakeAwsClient(
        _aws_response(request, _result(request), contentType="text/event-stream")
    )
    with pytest.raises(AgentCoreDeliveryUncertainError):
        await AgentCoreSupervisorClient(_settings(tmp_path), client=non_json).decide(request)

    jsonp = FakeAwsClient(
        _aws_response(request, _result(request), contentType="application/jsonp")
    )
    with pytest.raises(AgentCoreDeliveryUncertainError):
        await AgentCoreSupervisorClient(_settings(tmp_path), client=jsonp).decide(request)

    settings = _settings(tmp_path)
    settings.agentcore_max_response_bytes = 1_024
    oversized = FakeAwsClient(
        _aws_response(
            request,
            _result(request),
            response=io.BytesIO(b"x" * 1_025),
        )
    )
    with pytest.raises(AgentCoreDeliveryUncertainError):
        await AgentCoreSupervisorClient(settings, client=oversized).decide(request)

    too_many_empty_chunks = FakeAwsClient(
        _aws_response(
            request,
            _result(request),
            response=[b""] * 4_097,
        )
    )
    with pytest.raises(AgentCoreDeliveryUncertainError):
        await AgentCoreSupervisorClient(
            _settings(tmp_path), client=too_many_empty_chunks
        ).decide(request)

    nonfinite = FakeAwsClient(
        _aws_response(
            request,
            _result(request),
            response=io.BytesIO(
                (
                    '{"schema_version":1,"invocation_id":"'
                    + transport_invocation_id(request)
                    + '","result":NaN}'
                ).encode()
            ),
        )
    )
    with pytest.raises(AgentCoreDeliveryUncertainError):
        await AgentCoreSupervisorClient(_settings(tmp_path), client=nonfinite).decide(request)

    duplicate_binding = FakeAwsClient(
        _aws_response(
            request,
            _result(request),
            response=io.BytesIO(
                (
                    '{"schema_version":1,"invocation_id":"wrong",'
                    '"invocation_id":"'
                    + transport_invocation_id(request)
                    + '","result":{}}'
                ).encode()
            ),
        )
    )
    with pytest.raises(AgentCoreDeliveryUncertainError):
        await AgentCoreSupervisorClient(
            _settings(tmp_path), client=duplicate_binding
        ).decide(request)


@pytest.mark.asyncio
async def test_agentcore_client_strips_credentials_from_remote_endpoint_provenance(tmp_path):
    request = _request()
    remote = _result(request)
    remote.base_url = "https://user:password@example.invalid/v1?token=secret#private"
    client = AgentCoreSupervisorClient(
        _settings(tmp_path),
        client=FakeAwsClient(_aws_response(request, remote)),
    )

    result = await client.decide(request)

    assert result.base_url == "https://example.invalid/v1"
    assert "password" not in result.model_dump_json()
    assert "secret" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_agentcore_client_masks_workspace_and_secrets_in_all_remote_metadata(tmp_path):
    request = _request()
    workspace = request.session.cwd
    remote = _result(request)
    remote.diagnosis = f"Observed {workspace}; token=super-secret-value"
    remote.traces = [f"Read {workspace}\\private.txt password=super-secret-value"]
    remote.model_name = f"{workspace} token=super-secret-value"
    client = AgentCoreSupervisorClient(
        _settings(tmp_path),
        client=FakeAwsClient(_aws_response(request, remote)),
    )

    result = await client.decide(request)
    rendered = result.model_dump_json()

    assert workspace.casefold() not in rendered.casefold()
    assert "super-secret-value" not in rendered
    assert "<workspace>" in rendered
    assert "[REDACTED:credential_assignment]" in rendered


class FakeRemote:
    def __init__(self, result: SupervisorResult | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls = 0

    async def decide(self, request):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_agentcore_mode_surfaces_uncertain_transport_without_local_semantic_fallback(
    tmp_path, monkeypatch
):
    request = _request()
    remote = FakeRemote(error=AgentCoreTransportError("SECRET_PROVIDER_BODY"))
    router = SupervisorRouter(_settings(tmp_path), agentcore_client=remote)
    local_calls = 0

    async def local(*_args, **_kwargs):
        nonlocal local_calls
        local_calls += 1
        return _result(request)

    monkeypatch.setattr("pex_bridge.agentcore.decide_async", local)
    with pytest.raises(AgentCoreDeliveryUncertainError) as caught:
        await router.decide(request, local_model=object())

    assert remote.calls == 1
    assert local_calls == 0
    assert caught.value.delivery_status == "delivery_uncertain"
    assert caught.value.reason_code == "transport_failure"
    assert caught.value.transport_invocation_id == transport_invocation_id(request)
    assert "SECRET_PROVIDER_BODY" not in str(caught.value)
    assert "SECRET_PROVIDER_BODY" not in repr(caught.value)


def _acceptance_gap_request() -> SupervisorRequest:
    request = _request()
    request.scores.features["verification"] = {
        "status": "acceptance_gap",
        "correction": (
            "results.jsonl has 27 rows; 30 are required. Continue until the file is complete."
        ),
        "evidence": ["row_count=27", "required=30"],
    }
    return request


@pytest.mark.asyncio
async def test_agentcore_predispatch_failure_defaults_to_noop(tmp_path, monkeypatch):
    request = _acceptance_gap_request()
    remote = FakeRemote(
        error=AgentCorePreDispatchError("local request invalid: SECRET_PROVIDER_BODY")
    )
    router = SupervisorRouter(_settings(tmp_path), agentcore_client=remote)
    local_calls = 0

    async def local(*_args, **_kwargs):
        nonlocal local_calls
        local_calls += 1
        return _result(request)

    monkeypatch.setattr("pex_bridge.agentcore.decide_async", local)
    result = await router.decide(request, local_model=object())

    assert remote.calls == 1
    assert local_calls == 0
    assert result.action.type == InterventionType.NOOP
    assert result.action.payload == {}
    assert result.action.evidence == [
        "agentcore_unavailable:AgentCorePreDispatchError"
    ]
    assert result.used_llm is False
    assert result.inference_status == "failed"
    assert result.execution_mode == "agentcore"
    assert result.transport == "bedrock-agentcore"
    assert result.transport_status == "failed"
    assert result.transport_invocation_id == transport_invocation_id(request)
    assert result.diagnosis == "agentcore_unavailable:AgentCorePreDispatchError"
    assert result.traces == ["AgentCorePreDispatchError", "agentcore_failure_noop"]
    assert "SECRET_PROVIDER_BODY" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_completed_agentcore_noop_is_not_replaced_by_local_acceptance_gap(tmp_path):
    request = _acceptance_gap_request()
    remote = FakeRemote(result=_result(request))
    router = SupervisorRouter(_settings(tmp_path), agentcore_client=remote)
    result = await router.decide(request, local_model=object())
    assert remote.calls == 1
    assert result.action.type == InterventionType.NOOP
    assert result.action.payload == {}
    assert result.inference_status == "completed"
    assert "deterministic_action_preserved" not in result.traces


@pytest.mark.asyncio
async def test_agentcore_invalid_configuration_defaults_to_bound_noop(tmp_path, monkeypatch):
    request = _acceptance_gap_request()
    settings = Settings(
        home=tmp_path,
        supervisor_mode="agentcore",
        agentcore_runtime_arn="operator-controlled-invalid-runtime-arn",
    )
    local_calls = 0

    async def local(*_args, **_kwargs):
        nonlocal local_calls
        local_calls += 1
        return _result(request)

    monkeypatch.setattr("pex_bridge.agentcore.decide_async", local)
    router = SupervisorRouter(settings)
    result = await router.decide(request, local_model=object())

    assert router.agentcore is None
    assert local_calls == 0
    assert result.action.type == InterventionType.NOOP
    assert result.action.session_id == request.session.id
    assert result.action.goal_id == request.goal.id
    assert result.action.payload == {}
    assert result.action.evidence == [
        "agentcore_unavailable:AgentCoreConfigurationError"
    ]
    assert result.used_llm is False
    assert result.inference_status == "failed"
    assert result.execution_mode == "agentcore"
    assert result.transport == "bedrock-agentcore"
    assert result.transport_status == "failed"
    assert result.transport_invocation_id == transport_invocation_id(request)
    assert result.diagnosis == "agentcore_unavailable:AgentCoreConfigurationError"
    assert result.traces == ["AgentCoreConfigurationError", "agentcore_failure_noop"]
    assert "operator-controlled-invalid-runtime-arn" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_hybrid_configuration_fallback_is_explicit_and_valid_remote_noop_never_falls_back(
    tmp_path, monkeypatch
):
    request = _request()
    local_calls = 0

    async def local(*_args, **_kwargs):
        nonlocal local_calls
        local_calls += 1
        return _result(request)

    monkeypatch.setattr("pex_bridge.agentcore.decide_async", local)
    failed_remote = FakeRemote(error=AgentCoreConfigurationError("runtime missing"))
    hybrid = SupervisorRouter(
        _settings(tmp_path, "hybrid"), agentcore_client=failed_remote
    )
    fallback = await hybrid.decide(request, local_model=object())
    assert fallback.execution_mode == "hybrid_local_fallback"
    assert fallback.transport_status == "failed"
    assert fallback.transport_invocation_id == transport_invocation_id(request)
    assert local_calls == 1
    assert fallback.traces[-1] == "agentcore_fallback:AgentCoreConfigurationError"

    valid_remote = FakeRemote(result=_result(request))
    hybrid = SupervisorRouter(_settings(tmp_path, "hybrid"), agentcore_client=valid_remote)
    direct = await hybrid.decide(request, local_model=object())
    assert direct.action.type == InterventionType.NOOP
    assert local_calls == 1


@pytest.mark.asyncio
async def test_hybrid_invalid_runtime_configuration_falls_back_before_any_sdk_call(
    tmp_path, monkeypatch
):
    request = _request()
    settings = Settings(
        home=tmp_path,
        supervisor_mode="hybrid",
        agentcore_runtime_arn="operator-controlled-invalid-runtime-arn",
    )
    local_calls = 0

    async def local(*_args, **_kwargs):
        nonlocal local_calls
        local_calls += 1
        return _result(request)

    monkeypatch.setattr("pex_bridge.agentcore.decide_async", local)
    router = SupervisorRouter(settings)
    result = await router.decide(request, local_model=object())

    assert local_calls == 1
    assert result.execution_mode == "hybrid_local_fallback"
    assert result.transport_status == "failed"
    assert "operator-controlled-invalid-runtime-arn" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_hybrid_timeout_is_uncertain_never_starts_local_and_ignores_late_result(
    tmp_path, monkeypatch
):
    request = _request()
    settings = _settings(tmp_path, "hybrid")
    settings.agentcore_timeout_seconds = 0.02
    aws = BlockingAwsClient(_aws_response(request, _result(request)))
    client = AgentCoreSupervisorClient(settings, client=aws)
    router = SupervisorRouter(settings, agentcore_client=client)
    local_calls = 0

    async def local(*_args, **_kwargs):
        nonlocal local_calls
        local_calls += 1
        return _result(request)

    monkeypatch.setattr("pex_bridge.agentcore.decide_async", local)
    try:
        with pytest.raises(AgentCoreDeliveryUncertainError) as caught:
            await router.decide(request, local_model=object())

        error = caught.value
        assert error.delivery_status == "delivery_uncertain"
        assert error.reason_code == "timeout"
        assert error.transport_invocation_id == transport_invocation_id(request)
        assert len(aws.calls) == 1
        assert local_calls == 0

        # The SDK thread cannot be force-cancelled. A late valid response must be
        # abandoned; it cannot change the already-returned receipt or start a retry.
        aws.release.set()
        await _wait_thread_event(aws.finished)
        await asyncio.sleep(0)
        assert error.reason_code == "timeout"
        assert len(aws.calls) == 1
        assert local_calls == 0
    finally:
        aws.release.set()


@pytest.mark.asyncio
async def test_hybrid_cancellation_propagates_and_never_starts_local_fallback(
    tmp_path, monkeypatch
):
    request = _request()
    settings = _settings(tmp_path, "hybrid")
    aws = BlockingAwsClient(_aws_response(request, _result(request)))
    client = AgentCoreSupervisorClient(settings, client=aws)
    router = SupervisorRouter(settings, agentcore_client=client)
    local_calls = 0

    async def local(*_args, **_kwargs):
        nonlocal local_calls
        local_calls += 1
        return _result(request)

    monkeypatch.setattr("pex_bridge.agentcore.decide_async", local)
    task = asyncio.create_task(router.decide(request, local_model=object()))
    try:
        await _wait_thread_event(aws.started)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(aws.calls) == 1
        assert local_calls == 0

        aws.release.set()
        await _wait_thread_event(aws.finished)
        await asyncio.sleep(0)
        assert len(aws.calls) == 1
        assert local_calls == 0
    finally:
        aws.release.set()
        if not task.done():
            task.cancel()


@pytest.mark.asyncio
async def test_post_dispatch_provider_error_is_typed_and_secret_safe(tmp_path):
    secret = "Bearer SUPER-SECRET-PROVIDER-BODY"

    class SecretFailingAwsClient:
        def invoke_agent_runtime(self, **_kwargs):
            raise RuntimeError(secret)

    request = _request()
    client = AgentCoreSupervisorClient(
        _settings(tmp_path),
        client=SecretFailingAwsClient(),
    )

    with pytest.raises(AgentCoreDeliveryUncertainError) as caught:
        await client.decide(request)

    rendered = "".join(traceback.format_exception(caught.value))
    assert caught.value.reason_code == "unexpected_failure"
    assert caught.value.transport_invocation_id == transport_invocation_id(request)
    assert secret not in str(caught.value)
    assert secret not in repr(caught.value)
    assert secret not in rendered


def test_uncertain_error_rejects_unbounded_or_untyped_fields():
    with pytest.raises(ValueError, match="reason code"):
        AgentCoreDeliveryUncertainError(
            transport_invocation_id="pexinv_" + "a" * 32,
            reason_code="Bearer SECRET",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="invocation id"):
        AgentCoreDeliveryUncertainError(
            transport_invocation_id="pexinv_not-bounded",
            reason_code="timeout",
        )


@pytest.mark.asyncio
async def test_agentcore_routine_event_stays_deterministic_and_does_not_call_remote(
    tmp_path,
):
    request = _request(EventType.HEARTBEAT)
    remote = FakeRemote(result=_result(request))
    router = SupervisorRouter(_settings(tmp_path), agentcore_client=remote)
    result = await router.decide(request, local_model=object())
    assert remote.calls == 0
    assert result.execution_mode == "local_deterministic"
    assert result.used_llm is False


def test_agentcore_settings_require_explicit_cloud_target(tmp_path):
    with pytest.raises(ValidationError, match="PEX_AGENTCORE_RUNTIME_ARN"):
        Settings(home=tmp_path, supervisor_mode="agentcore")
    with pytest.raises(ValidationError, match="PEX_CLOUD_REASONING"):
        Settings(
            home=tmp_path,
            supervisor_mode="agentcore",
            agentcore_runtime_arn=ARN,
            cloud_reasoning=False,
        )
    with pytest.raises(ValidationError, match="PEX_AGENTCORE_QUALIFIER"):
        Settings(
            home=tmp_path,
            supervisor_mode="agentcore",
            agentcore_runtime_arn=ARN,
            agentcore_qualifier="1-invalid",
        )


def test_agentcore_client_requires_official_runtime_arn_shape(tmp_path):
    settings = Settings(
        home=tmp_path,
        supervisor_mode="agentcore",
        agentcore_runtime_arn=(
            "arn:aws:bedrock-agentcore:eu-north-1:123456789012:runtime/not-a-runtime"
        ),
    )
    with pytest.raises(AgentCoreConfigurationError, match="Runtime ARN"):
        AgentCoreSupervisorClient(settings)
