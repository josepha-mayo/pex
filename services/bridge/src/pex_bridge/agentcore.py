"""Strict Amazon Bedrock AgentCore transport for semantic supervision.

The cloud runtime may only propose a typed action. Session binding, policy, and
all side effects remain in the local bridge.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
import time
from collections.abc import Iterable, Mapping
from math import isfinite
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid5

from pex_protocol.actions import InterventionType
from pex_protocol.enums import EventType
from pex_protocol.project_binding import project_binding_key as _project_key
from pex_protocol.session import HarnessEvent
from pex_protocol.supervisor import (
    INDEPENDENT_VERIFIER_EVIDENCE_TOOLS,
    SupervisorRequest,
    SupervisorResult,
    supervisor_request_digest,
)
from pex_supervisor.loop import (
    _action_from_proposal,
    _preserve_deterministic_truth,
    decide_async,
    needs_semantic_inference,
)
from pex_supervisor.planner import plan_deterministic

from pex_bridge.config import Settings
from pex_bridge.secrets import redact_mapping, redact_text

PROTOCOL_VERSION = 1
TRANSPORT_NAME = "bedrock-agentcore"
_ARN = re.compile(
    r"^arn:(?P<partition>aws(?:-[a-z0-9-]+)?):bedrock-agentcore:"
    r"(?P<region>[a-z0-9-]+):(?P<account>[0-9]{12}):runtime/"
    r"(?P<runtime>[A-Za-z][A-Za-z0-9_]{0,99}-[A-Za-z0-9]{10})$"
)
_MAX_STREAM_CHUNKS = 4_096


class AgentCoreError(RuntimeError):
    """Base class for safe, user-displayable AgentCore failures."""


class AgentCoreConfigurationError(AgentCoreError):
    """The configured AgentCore target is invalid."""


class AgentCoreTransportError(AgentCoreError):
    """AWS did not return a usable response."""


class AgentCoreProtocolError(AgentCoreError):
    """The deployed PEX runtime returned an incompatible response."""


class AgentCorePreDispatchError(AgentCoreProtocolError):
    """Local request/client preparation failed before semantic dispatch."""


_UncertainReason = Literal[
    "timeout",
    "transport_failure",
    "response_protocol_failure",
    "unexpected_failure",
]
_UNCERTAIN_REASONS = {
    "timeout",
    "transport_failure",
    "response_protocol_failure",
    "unexpected_failure",
}
_TRANSPORT_INVOCATION_ID = re.compile(r"^pexinv_[0-9a-f]{32}$")


class AgentCoreDeliveryUncertainError(AgentCoreTransportError):
    """A possibly dispatched invocation has no usable, bound result.

    Only bridge-generated identifiers and a closed reason code are retained.
    Provider exception text is deliberately excluded because it can echo
    credentials, prompt data, or response bodies.
    """

    delivery_status: Literal["delivery_uncertain"] = "delivery_uncertain"

    def __init__(
        self,
        *,
        transport_invocation_id: str,
        reason_code: _UncertainReason,
    ) -> None:
        if reason_code not in _UNCERTAIN_REASONS:
            raise ValueError("invalid AgentCore delivery uncertainty reason code")
        if _TRANSPORT_INVOCATION_ID.fullmatch(transport_invocation_id) is None:
            raise ValueError("invalid AgentCore transport invocation id")
        self.transport_invocation_id = transport_invocation_id
        self.reason_code = reason_code
        super().__init__(f"AgentCore delivery is uncertain ({reason_code})")


def _safe_text(value: object, limit: int, local_values: Iterable[str] = ()) -> str:
    cleaned, _ = redact_text(str(value or ""))
    rendered = cleaned or ""
    for local in sorted({item for item in local_values if item}, key=len, reverse=True):
        variants = {local, local.replace("\\", "/"), local.replace("/", "\\")}
        for variant in variants:
            rendered = re.sub(re.escape(variant), "<workspace>", rendered, flags=re.IGNORECASE)
    return rendered[:limit]


def _opaque(value: str | None, prefix: str) -> str | None:
    if not value:
        return None
    digest = hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _project_matches(observed: str | None, expected: str | None) -> bool:
    if observed is None:
        return True
    return bool(expected and _project_key(observed) == _project_key(expected))


def _bounded_int(
    value: object,
    *,
    minimum: int = 0,
    maximum: int = (1 << 63) - 1,
) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return minimum
    return min(maximum, max(minimum, parsed))


def _reject_nonfinite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _safe_endpoint(value: object) -> str:
    """Return endpoint provenance without user-info, query secrets, or fragments."""

    try:
        parsed = urlsplit(str(value or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "[configured]"
        hostname = parsed.hostname
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        netloc = hostname
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except ValueError:
        return "[configured]"


def _safe_path(value: object, local_values: Iterable[str] = ()) -> str:
    rendered = _safe_text(value, 480, local_values).replace("\\", "/")
    if not rendered:
        return ""
    inside_workspace = rendered == "<workspace>" or rendered.startswith("<workspace>/")
    is_absolute = rendered.startswith("/") or bool(re.match(r"^[A-Za-z]:/", rendered))
    parts = [part for part in rendered.split("/") if part not in {"", ".", ".."}]
    if inside_workspace:
        tail = [part for part in parts if part != "<workspace>"][-8:]
        return "<workspace>" + ("/" + "/".join(tail) if tail else "")
    if is_absolute:
        return "<absolute>/" + "/".join(parts[-3:])
    return "/".join(parts[-8:])


def _bounded_json(
    value: object,
    *,
    local_values: Iterable[str] = (),
    depth: int = 0,
) -> object:
    if depth >= 6:
        return "[truncated]"
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return _bounded_int(value, minimum=-(1 << 63))
    if isinstance(value, float):
        return value if isfinite(value) else None
    if isinstance(value, str):
        return _safe_text(value, 1_200, local_values)
    if isinstance(value, Mapping):
        bounded = {
            _safe_text(key, 100, local_values): _bounded_json(
                item,
                local_values=local_values,
                depth=depth + 1,
            )
            for key, item in list(value.items())[:48]
        }
        cleaned, _ = redact_mapping(bounded)
        return cleaned or {}
    if isinstance(value, (list, tuple)):
        return [
            _bounded_json(item, local_values=local_values, depth=depth + 1)
            for item in list(value)[:48]
        ]
    return _safe_text(value, 300, local_values)


def compact_workspace_evidence(workspace: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep counts and artifact metadata, never repository contents or absolute paths."""
    raw = dict(workspace or {})
    raw_files = raw.get("files")
    files = list(raw_files[:80]) if isinstance(raw_files, (list, tuple)) else []
    raw_file_meta = raw.get("file_meta")
    file_meta = [
        item for item in raw_file_meta[:80] if isinstance(item, Mapping)
    ] if isinstance(raw_file_meta, (list, tuple)) else []
    raw_artifacts = raw.get("artifacts")
    artifacts = [
        item for item in raw_artifacts[:24] if isinstance(item, Mapping)
    ] if isinstance(raw_artifacts, (list, tuple)) else []
    git = raw.get("git") if isinstance(raw.get("git"), Mapping) else {}
    pytest = raw.get("pytest") if isinstance(raw.get("pytest"), Mapping) else {}
    changed = [line for line in str(git.get("status") or "").splitlines() if line.strip()]
    by_path = {str(item.get("path") or ""): item for item in file_meta}
    safe_files: list[dict[str, Any]] = []
    for item in files[:80]:
        path = item.get("path") if isinstance(item, Mapping) else item
        metadata = item if isinstance(item, Mapping) else by_path.get(str(path)) or {}
        safe_files.append(
            {
                "path": _safe_path(path),
                "bytes": _bounded_int(metadata.get("bytes")),
            }
        )
    return {
        "observed": (
            raw.get("observed")
            if isinstance(raw.get("observed"), bool)
            else not bool(raw.get("error"))
        ),
        "observed_file_count": (
            _bounded_int(raw.get("observed_file_count"), maximum=1_000_000_000)
            if isinstance(raw.get("observed_file_count"), int)
            else len(files)
        ),
        "file_inventory_truncated": bool(
            raw.get("files_truncated") or raw.get("file_inventory_truncated")
        ),
        "files": safe_files,
        "artifacts": [
            {
                "path": _safe_path(item.get("path")),
                "bytes": _bounded_int(item.get("bytes")),
            }
            for item in artifacts[:24]
        ],
        "git": {
            "available": bool(git.get("available")),
            "dirty": git.get("dirty") if isinstance(git.get("dirty"), bool) else bool(changed),
            "changed_file_count": (
                _bounded_int(git.get("changed_file_count"), maximum=1_000_000_000)
                if isinstance(git.get("changed_file_count"), int)
                else len(changed)
            ),
            "changed_paths": [
                _safe_path(line.split()[-1] if line.split() else line)
                for line in changed[:24]
            ],
        },
        "pytest": {
            "ok": pytest.get("ok") if isinstance(pytest.get("ok"), bool) else None,
            "exit_code": (
                _bounded_int(
                    pytest.get("exit_code"), minimum=-(1 << 31), maximum=(1 << 31) - 1
                )
                if isinstance(pytest.get("exit_code"), int)
                else None
            ),
        },
    }


def _safe_event(
    event: HarnessEvent,
    *,
    project_id: str | None,
    local_values: Iterable[str],
) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "ts": event.ts,
        "harness_type": event.harness_type,
        "session_id": event.session_id,
        "project_id": project_id,
        "event_type": event.event_type,
        "phase": event.phase,
        "message_delta": _safe_text(event.message_delta, 2_000, local_values) or None,
        "tool_name": _safe_text(event.tool_name, 160, local_values) or None,
        "command": _safe_text(event.command, 1_000, local_values) or None,
        "file_paths": [
            path
            for item in event.file_paths[:32]
            if (path := _safe_path(item, local_values))
        ],
        "cost": event.cost if event.cost is None or isfinite(event.cost) else None,
        "error": _safe_text(event.error, 1_000, local_values) or None,
        # Raw adapter refs, tool inputs/output, approval payloads, process output,
        # tokens, and vendor metadata stay on the local bridge.
        "raw_event_ref": None,
        "tool_input": None,
        "tool_output_ref": None,
        "diff_ref": None,
        "approval_request": None,
        "token_usage": None,
        "process_state": None,
        "metadata": {},
    }


def cloud_request(request: SupervisorRequest) -> SupervisorRequest:
    """Return the minimum redacted request needed by the remote semantic judge."""
    session = request.session
    local_values = tuple(
        value for value in (session.cwd, session.repo, session.external_url) if value
    )
    raw_project_id = session.project_id or (request.goal.project_id if request.goal else None)
    project_id = _opaque(raw_project_id, "p")
    goal = None
    if request.goal is not None:
        goal_data = request.goal.model_dump()
        goal_data["project_id"] = project_id or "p_unset"
        for field in (
            "title",
            "objective",
            "acceptance_criteria",
            "constraints",
            "preferences",
            "forbidden_outcomes",
            "non_goals",
            "evidence_requirements",
        ):
            goal_data[field] = _bounded_json(goal_data.get(field), local_values=local_values)
        goal = goal_data

    capability_flags = {
        _safe_text(key, 100, local_values): _bounded_json(value, local_values=local_values)
        for key, value in session.capabilities.items()
        if isinstance(value, (bool, int, float))
    }
    allowed_features: dict[str, Any] = {
        key: request.scores.features.get(key)
        for key in ("claims", "verification")
        if key in request.scores.features
    }
    prefetched = request.scores.features.get("prefetched_evidence")
    if isinstance(prefetched, Mapping):
        allowed_features["prefetched_evidence"] = compact_workspace_evidence(prefetched)
    supervisor_context = None
    if request.supervisor_context is not None:
        context_data = request.supervisor_context.model_dump(mode="json", by_alias=True)
        context_data["project_id"] = project_id
        for item in context_data.get("context_items") or []:
            if isinstance(item, dict):
                item["project_id"] = project_id
        supervisor_context = _bounded_json(context_data, local_values=local_values)
    data = {
        "session": {
            "id": session.id,
            "harness_type": session.harness_type,
            "vendor_session_id": _opaque(session.vendor_session_id, "vendor") or "vendor_unset",
            "project_id": project_id,
            "goal_id": session.goal_id,
            "cwd": None,
            "repo": None,
            "branch": None,
            "model": _safe_text(session.model, 200, local_values) or None,
            "reasoning_effort": _safe_text(session.reasoning_effort, 80) or None,
            "status": session.status,
            "context_health": session.context_health,
            "last_activity": session.last_activity,
            "capabilities": capability_flags,
            "external_url": None,
            "local_window_id": None,
            "supervision_paused": session.supervision_paused,
            "metadata": {},
        },
        "goal": goal,
        "event": _safe_event(
            request.event,
            project_id=project_id,
            local_values=local_values,
        ),
        "recent_events": [
            _safe_event(item, project_id=project_id, local_values=local_values)
            for item in request.recent_events[-12:]
        ],
        "scores": {
            "drift": request.scores.drift,
            "stagnation": request.scores.stagnation,
            "premature_completion": request.scores.premature_completion,
            "claim_contradiction": request.scores.claim_contradiction,
            "features": _bounded_json(allowed_features, local_values=local_values),
        },
        "supervisor_context": supervisor_context,
        "autonomy": request.autonomy,
        "notes": _safe_text(request.notes, 1_500, local_values),
    }
    cleaned, _ = redact_mapping(data)
    return SupervisorRequest.model_validate(cleaned)


def transport_invocation_id(request: SupervisorRequest) -> str:
    """Return a stable opaque id for this one normalized harness event."""
    material = f"{request.session.id}\0{request.event.event_id}"
    return f"pexinv_{uuid5(NAMESPACE_URL, 'pex-agentcore-invoke:' + material).hex}"


def _validate_request_binding(request: SupervisorRequest) -> None:
    """Reject locally inconsistent requests before any cloud transmission."""
    session = request.session
    if request.event.session_id != session.id:
        raise AgentCoreProtocolError("AgentCore event is bound to a different session")
    if request.event.harness_type != session.harness_type:
        raise AgentCoreProtocolError("AgentCore event is bound to a different harness")
    if not _project_matches(request.event.project_id, session.project_id):
        raise AgentCoreProtocolError("AgentCore event is bound to a different project")
    expected_goal = request.goal.id if request.goal else None
    if session.goal_id != expected_goal:
        raise AgentCoreProtocolError("AgentCore request has inconsistent goal binding")
    if request.goal and not _project_matches(request.goal.project_id, session.project_id):
        raise AgentCoreProtocolError("AgentCore request has inconsistent project binding")
    context = request.supervisor_context
    if context is not None and (
        context.target_session_id != session.id
        or not _project_matches(context.project_id, session.project_id)
        or context.goal_id != expected_goal
    ):
        raise AgentCoreProtocolError("AgentCore context has inconsistent authority binding")
    for event in request.recent_events:
        if event.session_id != session.id:
            raise AgentCoreProtocolError(
                "AgentCore recent event is bound to a different session"
            )
        if event.harness_type != session.harness_type:
            raise AgentCoreProtocolError(
                "AgentCore recent event is bound to a different harness"
            )
        if not _project_matches(event.project_id, session.project_id):
            raise AgentCoreProtocolError(
                "AgentCore recent event is bound to a different project"
            )


def _exact_observation_text_is_safe(value: object, local_values: tuple[str, ...]) -> bool:
    """Reject unsafe returned observations instead of rewriting their hashed bytes."""

    if isinstance(value, str):
        return _safe_text(value, len(value), local_values) == value
    if isinstance(value, dict):
        cleaned, _ = redact_mapping(value)
        return cleaned == value and all(
            _exact_observation_text_is_safe(key, local_values)
            and _exact_observation_text_is_safe(item, local_values)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return all(_exact_observation_text_is_safe(item, local_values) for item in value)
    return value is None or isinstance(value, (bool, int, float))


def _validate_remote_observations(
    request: SupervisorRequest,
    result: SupervisorResult,
    *,
    dispatched_request_digest: str,
) -> None:
    """Bind exact remote tool results to the actual sanitized request sent to AWS.

    A locally generated digest is correlation, not attestation of remote execution.
    Never sanitize/re-hash an incompatible observation and call it what a model saw.
    """

    local_values = tuple(
        value for value in (
            request.session.cwd, request.session.repo, request.session.external_url,
        ) if value
    )
    verifier = result.independent_verifier
    groups = [("main", result.local_invocation_id, result.evidence_observations)]
    if verifier is not None:
        groups.append(("verifier", verifier.invocation_id, verifier.evidence_observations))
    expected_goal = request.goal.id if request.goal is not None else None
    observed_ids: set[str] = set()
    for stage, invocation_id, observations in groups:
        for observation in observations:
            if (
                observation.stage != stage
                or observation.invocation_id != invocation_id
                or observation.request_digest != dispatched_request_digest
                or observation.session_id != request.session.id
                or observation.goal_id != expected_goal
                or observation.event_id != request.event.event_id
            ):
                raise AgentCoreProtocolError("AgentCore evidence observation binding mismatch")
            if observation.observation_id in observed_ids:
                raise AgentCoreProtocolError("AgentCore stages reused an evidence observation ID")
            observed_ids.add(observation.observation_id)
            if not all(
                _safe_text(value, len(value), local_values) == value
                for value in (observation.invocation_id, observation.tool_name)
            ):
                raise AgentCoreProtocolError("AgentCore evidence observation labels are unsafe")
            # Protocol validation bounds/decodes each JSON string. Parse again
            # here only to check escaped secrets and local paths before storage.
            for rendered in (observation.arguments_json, observation.output):
                parsed = json.loads(rendered)
                if not _exact_observation_text_is_safe(parsed, local_values):
                    raise AgentCoreProtocolError("AgentCore evidence observation is not sanitized")
    if (
        verifier is not None and verifier.evidence_observations
        and verifier.invocation_id == result.local_invocation_id
    ):
        raise AgentCoreProtocolError("AgentCore verifier reused the main invocation identity")


def _remote_verifier_contract_failure(
    request: SupervisorRequest,
    result: SupervisorResult,
) -> str | None:
    """Require cited main evidence and independent verification for STOP actions."""

    if result.action.type == InterventionType.NOOP:
        return None
    if result.inference_status != "completed":
        return "main_inference_not_completed"
    if not result.used_llm or result.model_call_count < 1:
        return "missing_main_inference"
    if request.event.event_type != EventType.STOP:
        return None if result.evidence_refs else "missing_main_evidence_observation"
    receipt = result.independent_verifier
    if receipt is None:
        return "missing_receipt"
    if not receipt.authorizes_intervention():
        if receipt.approved is not True:
            return "not_approved"
        if receipt.status != "approved":
            return "invalid_status"
        if receipt.model_call_count < 1:
            return "missing_verifier_call"
        if not receipt.evidence_refs or not receipt.evidence_observations:
            return "missing_evidence_observation"
        if not any(
            item.observation_id in receipt.evidence_refs
            and item.tool_name in INDEPENDENT_VERIFIER_EVIDENCE_TOOLS
            for item in receipt.evidence_observations
        ):
            return "missing_evidence_tool"
        return "invalid_receipt"
    if not result.evidence_refs:
        return "missing_main_evidence_observation"
    if result.model_call_count <= receipt.model_call_count:
        return "missing_main_inference"
    verifier_tools = {
        item.tool_name for item in receipt.evidence_observations
        if item.observation_id in receipt.evidence_refs
    }
    verification = (request.scores.features or {}).get("verification") or {}
    if not isinstance(verification, Mapping):
        return "invalid_verification_state"
    verification_only = bool(verifier_tools) and verifier_tools <= {
        "get_goal",
        "run_verification",
    }
    if (
        verification_only
        and str(verification.get("status") or "unavailable")
        in {"no_claims", "uncertain", "unavailable"}
        and str(verification.get("acceptance_status") or "unavailable")
        in {"uncertain", "unavailable"}
    ):
        return "uncertain_evidence"
    return None


def request_envelope(request: SupervisorRequest, *, max_bytes: int) -> bytes:
    _validate_request_binding(request)
    payload = {
        "schema_version": PROTOCOL_VERSION,
        "invocation_id": transport_invocation_id(request),
        "request": cloud_request(request).model_dump(mode="json"),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > max_bytes:
        raise AgentCoreProtocolError(
            f"sanitized AgentCore request exceeds the {max_bytes}-byte local limit"
        )
    return encoded


def runtime_session_id(session_id: str) -> str:
    return f"pex-{uuid5(NAMESPACE_URL, 'pex-agentcore:' + session_id).hex}"


def _target_region(runtime_arn: str, configured_region: str | None) -> str:
    match = _ARN.fullmatch(runtime_arn.strip())
    if match is None:
        raise AgentCoreConfigurationError(
            "PEX_AGENTCORE_RUNTIME_ARN must be a Runtime ARN, not an endpoint ARN or URL"
        )
    arn_region = match.group("region")
    if configured_region and configured_region != arn_region:
        raise AgentCoreConfigurationError(
            "PEX_AGENTCORE_REGION does not match PEX_AGENTCORE_RUNTIME_ARN"
        )
    return configured_region or arn_region


def _read_stream(body: object, limit: int) -> bytes:
    if hasattr(body, "read"):
        raw = body.read(limit + 1)  # type: ignore[attr-defined]
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        if not isinstance(raw, bytes):
            raise AgentCoreProtocolError("AgentCore response stream did not return bytes")
    elif isinstance(body, (bytes, bytearray)):
        raw = bytes(body)
    elif isinstance(body, Iterable):
        sink = io.BytesIO()
        for index, chunk in enumerate(body):
            if index >= _MAX_STREAM_CHUNKS:
                raise AgentCoreProtocolError("AgentCore response contained too many chunks")
            if not isinstance(chunk, (bytes, bytearray)):
                raise AgentCoreProtocolError("AgentCore response contained a non-byte chunk")
            sink.write(bytes(chunk))
            if sink.tell() > limit:
                break
        raw = sink.getvalue()
    else:
        raise AgentCoreProtocolError("AgentCore response is missing a readable body")
    if len(raw) > limit:
        raise AgentCoreProtocolError(
            f"AgentCore response exceeds the {limit}-byte local limit"
        )
    return raw


class AgentCoreSupervisorClient:
    def __init__(self, settings: Settings, *, client: object | None = None) -> None:
        runtime_arn = (settings.agentcore_runtime_arn or "").strip()
        self.runtime_arn = runtime_arn
        self.region = _target_region(runtime_arn, settings.agentcore_region)
        self.qualifier = settings.agentcore_qualifier
        self.timeout = settings.agentcore_timeout_seconds
        self.max_request_bytes = settings.agentcore_max_request_bytes
        self.max_response_bytes = settings.agentcore_max_response_bytes
        self._client = client

    def _aws_client(self) -> object:
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "bedrock-agentcore",
                region_name=self.region,
                config=Config(
                    connect_timeout=min(3.0, self.timeout),
                    read_timeout=self.timeout,
                    retries={"mode": "standard", "total_max_attempts": 1},
                    user_agent_extra="pex-supervisor/0.1",
                ),
            )
        return self._client

    def _invoke(
        self,
        client: object,
        request: SupervisorRequest,
        payload: bytes,
    ) -> tuple[dict[str, Any], bytes]:
        response = client.invoke_agent_runtime(  # type: ignore[attr-defined]
            agentRuntimeArn=self.runtime_arn,
            runtimeSessionId=runtime_session_id(request.session.id),
            payload=payload,
            qualifier=self.qualifier,
            contentType="application/json",
            accept="application/json",
        )
        if not isinstance(response, dict):
            raise AgentCoreProtocolError("AgentCore SDK returned a non-object response")
        metadata = response.get("ResponseMetadata") or {}
        status = int(response.get("statusCode") or metadata.get("HTTPStatusCode") or 0)
        if status != 200:
            raise AgentCoreTransportError(f"AgentCore returned HTTP {status or 'unknown'}")
        content_type = str(response.get("contentType") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise AgentCoreProtocolError(
                f"AgentCore returned unsupported content type {content_type or 'missing'}"
            )
        expected_session = runtime_session_id(request.session.id)
        if response.get("runtimeSessionId") != expected_session:
            raise AgentCoreProtocolError(
                "AgentCore response is bound to a different runtime session"
            )
        return response, _read_stream(response.get("response"), self.max_response_bytes)

    async def decide(self, request: SupervisorRequest) -> SupervisorResult:
        invocation_id = transport_invocation_id(request)
        try:
            return await self._decide_once(request)
        except asyncio.CancelledError:
            raise
        except (
            AgentCoreConfigurationError,
            AgentCorePreDispatchError,
            AgentCoreDeliveryUncertainError,
        ):
            raise
        except Exception:
            # All ordinary pre-dispatch failures are converted inside
            # _decide_once. Anything else occurred after the invocation
            # boundary and therefore cannot safely trigger another model.
            raise AgentCoreDeliveryUncertainError(
                transport_invocation_id=invocation_id,
                reason_code="unexpected_failure",
            ) from None

    async def _decide_once(self, request: SupervisorRequest) -> SupervisorResult:
        started = time.perf_counter()
        invocation_id = transport_invocation_id(request)
        try:
            payload = request_envelope(request, max_bytes=self.max_request_bytes)
            # Compute against the exact sanitized payload, not a second mutable
            # reconstruction from the local workspace-bearing request.
            dispatched_request = SupervisorRequest.model_validate(json.loads(payload)["request"])
            dispatched_digest = supervisor_request_digest(dispatched_request)
        except AgentCoreProtocolError as exc:
            # This is the one protocol phase that is provably pre-dispatch.
            # The messages originate in this module and contain no provider data.
            raise AgentCorePreDispatchError(str(exc)) from None
        try:
            client = await asyncio.to_thread(self._aws_client)
        except asyncio.CancelledError:
            raise
        except AgentCoreConfigurationError:
            raise
        except Exception:
            raise AgentCorePreDispatchError(
                "AgentCore SDK client setup failed before dispatch"
            ) from None
        try:
            response, raw = await asyncio.wait_for(
                asyncio.to_thread(self._invoke, client, request, payload),
                timeout=self.timeout,
            )
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise AgentCoreDeliveryUncertainError(
                transport_invocation_id=invocation_id,
                reason_code="timeout",
            ) from None
        except AgentCoreTransportError:
            raise AgentCoreDeliveryUncertainError(
                transport_invocation_id=invocation_id,
                reason_code="transport_failure",
            ) from None
        except AgentCoreProtocolError:
            raise AgentCoreDeliveryUncertainError(
                transport_invocation_id=invocation_id,
                reason_code="response_protocol_failure",
            ) from None
        except Exception:
            raise AgentCoreDeliveryUncertainError(
                transport_invocation_id=invocation_id,
                reason_code="unexpected_failure",
            ) from None

        try:
            envelope = json.loads(
                raw.decode("utf-8"),
                parse_constant=_reject_nonfinite_json_constant,
                object_pairs_hook=_unique_json_object,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
            raise AgentCoreDeliveryUncertainError(
                transport_invocation_id=invocation_id,
                reason_code="response_protocol_failure",
            ) from None
        if (
            not isinstance(envelope, dict)
            or type(envelope.get("schema_version")) is not int
            or envelope["schema_version"] != PROTOCOL_VERSION
        ):
            raise AgentCoreDeliveryUncertainError(
                transport_invocation_id=invocation_id,
                reason_code="response_protocol_failure",
            )
        expected_invocation = invocation_id
        if envelope.get("invocation_id") != expected_invocation:
            raise AgentCoreDeliveryUncertainError(
                transport_invocation_id=invocation_id,
                reason_code="response_protocol_failure",
            )
        if not isinstance(envelope.get("result"), dict):
            raise AgentCoreDeliveryUncertainError(
                transport_invocation_id=invocation_id,
                reason_code="response_protocol_failure",
            )
        try:
            result = SupervisorResult.model_validate(envelope["result"])
            _validate_remote_observations(
                request, result, dispatched_request_digest=dispatched_digest,
            )
        except Exception:
            raise AgentCoreDeliveryUncertainError(
                transport_invocation_id=invocation_id,
                reason_code="response_protocol_failure",
            ) from None
        expected_goal = request.goal.id if request.goal else None
        if result.action.session_id != request.session.id:
            raise AgentCoreDeliveryUncertainError(
                transport_invocation_id=invocation_id,
                reason_code="response_protocol_failure",
            )
        if result.action.goal_id != expected_goal:
            raise AgentCoreDeliveryUncertainError(
                transport_invocation_id=invocation_id,
                reason_code="response_protocol_failure",
            )

        # The remote runtime is a proposal boundary, not a policy authority.
        # Rebuild the action locally so a stale/compromised runtime cannot
        # choose reversibility, authority, capability mappings, generic text,
        # or bridge-owned context payloads by serializing ProposedAction fields.
        remote_action = result.action
        bounded_payload = _bounded_json(remote_action.payload)
        result.action = _action_from_proposal(
            request,
            {
                "type": remote_action.type.value,
                "rationale": _safe_text(remote_action.rationale, 2_000),
                "evidence": [
                    _safe_text(item, 1_000) for item in list(remote_action.evidence)[:20]
                ],
                "payload": bounded_payload if isinstance(bounded_payload, dict) else {},
                "confidence": remote_action.confidence,
                "risk": remote_action.risk.value,
            },
        )
        local_values = tuple(
            value
            for value in (
                request.session.cwd,
                request.session.repo,
                request.session.external_url,
            )
            if value
        )
        result.diagnosis = _safe_text(result.diagnosis, 300, local_values)
        result.traces = [
            _safe_text(item, 500, local_values) for item in list(result.traces)[:20]
        ]
        result.evidence_tools = [
            _safe_text(item, 200, local_values)
            for item in list(result.evidence_tools)[:20]
        ]
        verifier = result.independent_verifier
        if verifier is not None:
            verifier.status = _safe_text(verifier.status, 120, local_values)
            verifier.rationale = _safe_text(verifier.rationale, 2_000, local_values)
            verifier.evidence = [
                _safe_text(item, 1_000, local_values)
                for item in list(verifier.evidence)[:20]
            ]
            verifier.evidence_tools = [
                _safe_text(item, 128, local_values)
                for item in list(verifier.evidence_tools)[:20]
            ]
        for field in (
            "model_name",
            "inference_request_id",
            "local_invocation_id",
            "runtime",
            "runtime_version",
            "model_class",
            "provider",
            "auth_mode",
            "backend",
        ):
            value = getattr(result, field)
            if value is not None:
                setattr(result, field, _safe_text(value, 300, local_values))
        if result.base_url is not None:
            result.base_url = _safe_endpoint(result.base_url)
        result.input_tokens = max(0, min(result.input_tokens, 1_000_000_000))
        result.output_tokens = max(0, min(result.output_tokens, 1_000_000_000))
        result.latency_ms = max(0, min(result.latency_ms, 86_400_000))
        result.model_call_count = max(0, min(result.model_call_count, 10_000))

        verifier_failure = _remote_verifier_contract_failure(request, result)
        if verifier_failure is not None:
            result.action = _action_from_proposal(
                request,
                {
                    "type": "NOOP",
                    "rationale": (
                        "The remote semantic intervention lacked an approved "
                        "independent-verifier receipt; defaulting to silence."
                    ),
                    "evidence": [f"agentcore_verifier_contract:{verifier_failure}"],
                    "confidence": 1.0,
                    "risk": "none",
                },
            )
            result.diagnosis = (
                f"{result.diagnosis}:agentcore_verifier_contract_rejected:"
                f"{verifier_failure}"
            ).strip(":")
            result.traces = [
                *result.traces[-19:],
                f"agentcore_verifier_contract={verifier_failure}",
            ]

        metadata = response.get("ResponseMetadata") or {}
        result.execution_mode = "agentcore"
        result.transport = TRANSPORT_NAME
        result.transport_invocation_id = expected_invocation
        result.transport_request_id = _safe_text(metadata.get("RequestId"), 200) or None
        result.transport_status = "completed"
        # Preserve the remote Strands/model latency as provenance. End-to-end
        # transport timing is an additional trace, not a replacement.
        transport_ms = int((time.perf_counter() - started) * 1000)
        result.traces.append(f"agentcore_transport_ms={transport_ms}")
        return result


class SupervisorRouter:
    """Route semantic inference without ever hiding a fallback."""

    def __init__(
        self,
        settings: Settings,
        *,
        agentcore_client: AgentCoreSupervisorClient | None = None,
    ) -> None:
        self.mode = settings.supervisor_mode
        self.agentcore = agentcore_client
        self._configuration_failed = False
        if self.mode in {"agentcore", "hybrid"} and self.agentcore is None:
            try:
                self.agentcore = AgentCoreSupervisorClient(settings)
            except AgentCoreConfigurationError:
                # Preserve only the failure class. Configuration text is not
                # needed for routing and may contain operator-controlled input.
                self._configuration_failed = True

    @staticmethod
    def _deterministic(request: SupervisorRequest, mode: str) -> SupervisorResult:
        return SupervisorResult(
            action=plan_deterministic(request),
            used_llm=False,
            diagnosis="deterministic_triage",
            execution_mode=mode,
        )

    @staticmethod
    def _remote_failure(request: SupervisorRequest, exc: Exception) -> SupervisorResult:
        detail = type(exc).__name__
        return SupervisorResult(
            action=_action_from_proposal(
                request,
                {
                    "type": "NOOP",
                    "rationale": (
                        "AgentCore semantic supervision was unavailable; "
                        "defaulting to silence."
                    ),
                    "evidence": [f"agentcore_unavailable:{detail}"],
                    "confidence": 1.0,
                    "risk": "none",
                },
            ),
            used_llm=False,
            diagnosis=f"agentcore_unavailable:{detail}",
            traces=[detail, "agentcore_failure_noop"],
            inference_status="failed",
            execution_mode="agentcore",
            transport=TRANSPORT_NAME,
            transport_invocation_id=transport_invocation_id(request),
            transport_status="failed",
        )

    @staticmethod
    async def _hybrid_configuration_fallback(
        request: SupervisorRequest,
        local_model: object | None,
    ) -> SupervisorResult:
        result = await decide_async(request, local_model)
        result.execution_mode = "hybrid_local_fallback"
        result.transport = TRANSPORT_NAME
        result.transport_invocation_id = transport_invocation_id(request)
        result.transport_status = "failed"
        result.traces.append("agentcore_fallback:AgentCoreConfigurationError")
        result.diagnosis = f"{result.diagnosis}:agentcore_local_fallback"
        return result

    async def decide(
        self,
        request: SupervisorRequest,
        *,
        local_model: object | None,
    ) -> SupervisorResult:
        if self.mode == "local":
            result = await decide_async(request, local_model)
            result.execution_mode = result.execution_mode or "local"
            return result

        # Deterministic high-frequency facts remain local by design. AgentCore
        # is used only for the semantic judgment that benefits from a model.
        if not needs_semantic_inference(request):
            return self._deterministic(request, "local_deterministic")

        if self.agentcore is None:
            failure = AgentCoreConfigurationError("AgentCore client is not configured")
            if self.mode == "hybrid" and self._configuration_failed:
                return await self._hybrid_configuration_fallback(request, local_model)
            return self._remote_failure(request, failure)
        try:
            result = await self.agentcore.decide(request)
        except asyncio.CancelledError:
            # asyncio.to_thread cannot stop an already-running SDK call. Preserve
            # cancellation so no caller mistakes it for a definite failure and
            # starts another semantic model.
            raise
        except AgentCoreDeliveryUncertainError:
            raise
        except AgentCoreConfigurationError as exc:
            if self.mode != "hybrid":
                return self._remote_failure(request, exc)
            return await self._hybrid_configuration_fallback(request, local_model)
        except AgentCorePreDispatchError as exc:
            # Definite and safe to report, but not an allowlisted reason to start
            # a second semantic backend. Local deterministic truth is retained.
            return self._remote_failure(request, exc)
        except AgentCoreTransportError:
            # A custom/older client may not yet emit the typed uncertain error.
            # Once its decide method was entered, transport failure is ambiguous.
            raise AgentCoreDeliveryUncertainError(
                transport_invocation_id=transport_invocation_id(request),
                reason_code="transport_failure",
            ) from None
        except Exception:
            # Opaque client failures are conservative: semantic dispatch may have
            # happened even if the client did not expose its exact phase.
            raise AgentCoreDeliveryUncertainError(
                transport_invocation_id=transport_invocation_id(request),
                reason_code="unexpected_failure",
            ) from None
        return _preserve_deterministic_truth(
            request, plan_deterministic(request), result
        )
