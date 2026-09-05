from __future__ import annotations

import asyncio
import math
import os
import re
import time
from contextlib import suppress
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority
from pex_protocol.redaction import redact_text
from pex_protocol.supervisor import (
    IndependentVerifierReceipt,
    SupervisorEvidenceObservation,
    SupervisorRequest,
    SupervisorResult,
    supervisor_request_digest,
    validate_evidence_observation_bindings,
)
from pydantic import BaseModel, ConfigDict, Field

from pex_supervisor.evidence_observations import EvidenceObservationCollector
from pex_supervisor.evidence_tools import build_evidence_tools
from pex_supervisor.planner import plan_deterministic
from pex_supervisor.providers import describe_backend, load_supervisor_model

PROMPT_PATH = Path(__file__).parent / "prompts" / "supervisor.md"
VERIFIER_PROMPT_PATH = Path(__file__).parent / "prompts" / "verifier.md"


class SupervisorDecision(BaseModel):
    """The one validated decision a Strands invocation must return."""

    model_config = ConfigDict(extra="forbid")

    action_type: InterventionType
    rationale: str = Field(min_length=1, max_length=2_000)
    evidence: list[str] = Field(default_factory=list, max_length=20)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    message: str = Field(default="", max_length=4_000)
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    risk: RiskLevel = RiskLevel.LOW


class IndependentVerifierDecision(BaseModel):
    """Independent verdict over one semantic-only proposed intervention."""

    model_config = ConfigDict(extra="forbid")

    approved: bool
    rationale: str = Field(min_length=1, max_length=2_000)
    evidence: list[str] = Field(default_factory=list, max_length=20)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)


def _safe_text(value: object) -> str:
    text = str(value)
    return text.encode("utf-8", "replace").decode("utf-8")


def _clip(value: object, limit: int) -> str:
    return _safe_text(value)[:limit]


def _bounded_items(values: object, *, count: int = 24, width: int = 500) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    return [_clip(value, width) for value in values[:count]]


def _confidence(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.6
    if not math.isfinite(parsed):
        return 0.6
    return min(1.0, max(0.0, parsed))


def _bounded_nonnegative_int(value: object, *, maximum: int = 1_000_000_000_000) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return min(maximum, max(0, parsed))


def _strict_verifier_int(value: object, *, maximum: int = 1_000_000_000_000) -> int:
    """Bound verifier telemetry without coercing booleans or numeric strings."""

    if type(value) is not int:
        return 0
    return _bounded_nonnegative_int(value, maximum=maximum)


def _bounded_wall_timeout(value: object, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        parsed = default
    if not math.isfinite(parsed):
        parsed = default
    return min(25.0, max(1.0, parsed))


def _configure_stdio() -> None:
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            continue


def _system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _verifier_system_prompt() -> str:
    return VERIFIER_PROMPT_PATH.read_text(encoding="utf-8")


def _redact_request_text(request: SupervisorRequest, value: object) -> str:
    rendered = redact_text(_safe_text(value))[0] or ""
    local_values = tuple(
        local
        for local in (
            request.session.cwd,
            request.session.repo,
            request.session.external_url,
        )
        if local
    )
    for local in sorted(local_values, key=len, reverse=True):
        for variant in {local, local.replace("\\", "/"), local.replace("/", "\\")}:
            rendered = re.sub(
                re.escape(variant),
                "<workspace>",
                rendered,
                flags=re.IGNORECASE,
            )
    return rendered


def _redact_payload_value(
    request: SupervisorRequest,
    value: object,
    *,
    depth: int = 0,
) -> object:
    if depth >= 8:
        return "[truncated]"
    if isinstance(value, str):
        return _clip(_redact_request_text(request, value), 4_000)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return min((1 << 63) - 1, max(-(1 << 63), value))
    if isinstance(value, dict):
        return {
            _clip(_redact_request_text(request, key), 200): _redact_payload_value(
                request, item, depth=depth + 1
            )
            for key, item in list(value.items())[:100]
        }
    if isinstance(value, (list, tuple)):
        return [
            _redact_payload_value(request, item, depth=depth + 1)
            for item in list(value)[:100]
        ]
    if value is None or isinstance(value, (bool, float)):
        return value
    return _clip(_redact_request_text(request, value), 4_000)


def _format_user(request: SupervisorRequest) -> str:
    goal = request.goal
    event_text = _clip(request.event.command or request.event.message_delta or "", 2_000)
    claims = request.scores.features.get("claims") if request.scores.features else []
    verification = request.scores.features.get("verification") if request.scores.features else {}
    context = request.supervisor_context
    rendered = (
        "Normalized supervision request.\n"
        f"Harness: {request.session.harness_type}\n"
        f"Session: {request.session.id}\n"
        f"Status: {request.session.status}\n"
        f"Event: {request.event.event_type} {event_text}\n"
        f"Goal: {_clip(goal.objective, 4_000) if goal else 'unattached'}\n"
        f"Acceptance: {_bounded_items(goal.acceptance_criteria) if goal else []}\n"
        f"Evidence requirements: {_bounded_items(goal.evidence_requirements) if goal else []}\n"
        f"Extracted claims: {_clip(claims, 4_000)}\n"
        f"Verification: {_clip(verification, 6_000)}\n"
        "Offered durable context: "
        f"count={len(context.offered_context_ids) if context else 0} "
        f"first_ids={list(context.offered_context_ids[:3]) if context else []}\n"
        "Offered durable decisions: "
        f"count={len(context.offered_decision_ids) if context else 0} "
        f"first_ids={list(context.offered_decision_ids[:3]) if context else []}\n"
        "Page through get_context_items and get_decisions, or query an exact offered ID, "
        "for durable project/goal context. "
        "Query inspect_workspace, inspect_git, inspect_file, inspect_artifact, "
        "inspect_process, and run_verification for repo, diff, tests, artifacts, "
        "and process state. Use web_search or scrape_url only for a public claim "
        "the worker cited. Do not assume those facts without a tool result.\n"
        "Return exactly one validated structured decision."
    )
    return _redact_request_text(request, rendered)


_GENERIC_NAG = re.compile(
    r"^(keep going|continue|verify with the required|do not stop|don't stop until)\b",
    re.I,
)


def _sanitize_worker_text(text: str) -> str | None:
    cleaned = re.sub(r"^PEX:\s*", "", (text or "").strip(), flags=re.I)
    if not cleaned:
        return None
    if _GENERIC_NAG.search(cleaned) and not re.search(
        r"\b[A-Za-z0-9._-]{1,72}\.[A-Za-z0-9]{1,8}\b", cleaned
    ):
        return None
    return cleaned


def _action_from_proposal(request: SupervisorRequest, proposal: dict) -> ProposedAction:
    try:
        itype = InterventionType(proposal["type"])
    except (KeyError, ValueError):
        itype = InterventionType.NOOP
    supplied_risk = proposal.get("risk")
    risk_raw = str(supplied_risk or "low").lower()
    try:
        risk = RiskLevel(risk_raw)
    except ValueError:
        return _invalid_proposal(request, f"unknown risk level: {_clip(risk_raw, 64)}")
    payload = proposal.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    else:
        payload = _redact_payload_value(request, payload)
        if not isinstance(payload, dict):
            payload = {}
    payload_error = _redact_request_text(request, proposal.get("payload_error") or "")
    if payload_error:
        return _invalid_proposal(request, f"invalid payload JSON: {payload_error}")
    if itype in {InterventionType.FRESH_HANDOFF, InterventionType.INJECT_CONTEXT}:
        return _invalid_proposal(
            request,
            f"{itype.value} must be assembled by the provenance-backed bridge context store",
        )
    raw_evidence = proposal.get("evidence") or []
    if not isinstance(raw_evidence, (list, tuple)):
        raw_evidence = []
    evidence = [
        _redact_request_text(request, item)
        for item in raw_evidence
        if str(item).strip()
    ]
    lifecycle = {
        InterventionType.CLEANUP,
        InterventionType.FORK_PROBE,
        InterventionType.START_AGENT,
        InterventionType.STOP_AGENT,
    }
    if itype in lifecycle and not evidence:
        return _invalid_proposal(request, f"{itype.value} requires observed evidence")
    if itype == InterventionType.START_AGENT:
        project = str(payload.get("project") or "").strip()
        prompt = str(payload.get("prompt") or "").strip()
        config = payload.get("config", {})
        if config is None:
            config = {}
        if not project or not prompt or not isinstance(config, dict):
            return _invalid_proposal(
                request,
                "START_AGENT requires a project, prompt, and optional config object",
            )
        payload = {"project": project, "prompt": prompt, "config": config}
    if itype == InterventionType.STOP_AGENT:
        payload = {}
    if itype == InterventionType.FORK_PROBE and not isinstance(payload.get("bundle"), dict):
        return _invalid_proposal(request, "FORK_PROBE requires a context bundle")
    if itype == InterventionType.CLEANUP:
        resource_ids = payload.get("resource_ids")
        if (
            payload.get("mode") != "quarantine"
            or not isinstance(resource_ids, list)
            or not resource_ids
        ):
            return _invalid_proposal(
                request,
                "CLEANUP requires quarantine mode and registered resource ids",
            )
        payload = {
            "mode": "quarantine",
            "resource_ids": [str(item) for item in resource_ids],
        }
    if itype == InterventionType.RESPOND_PERMISSION:
        request_id = str(payload.get("request_id") or "").strip()
        decision = str(payload.get("decision") or "").strip().lower()
        if not request_id or decision not in {"allow", "deny"}:
            return _invalid_proposal(
                request,
                "permission responses require a request_id and an explicit allow or deny decision",
            )
        payload = {"request_id": request_id, "decision": decision}
    if itype == InterventionType.APPLY_OVERLAY and not isinstance(payload.get("overlay"), dict):
        return _invalid_proposal(request, "APPLY_OVERLAY requires an overlay object")
    if (
        itype == InterventionType.REVERT_OVERLAY
        and not str(payload.get("overlay_id") or "").strip()
    ):
        return _invalid_proposal(request, "REVERT_OVERLAY requires overlay_id")
    if itype == InterventionType.NOTIFY:
        text = str(payload.get("text") or "").strip()
        if not text:
            return _invalid_proposal(request, "NOTIFY requires human-facing text")
        payload = {"text": text}
    capability = {
        InterventionType.APPLY_OVERLAY: "modify_config",
        InterventionType.CONTINUE_SESSION: "resume",
        InterventionType.FOCUS_UI: "focus_ui",
        InterventionType.FRESH_HANDOFF: (
            "inject_context" if isinstance(payload.get("bundle"), dict) else "send_message"
        ),
        InterventionType.INJECT_CONTEXT: "send_message",
        InterventionType.REQUEST_VERIFICATION: "send_message",
        InterventionType.RESPOND_PERMISSION: (
            "approve" if payload.get("decision") == "allow" else "deny"
        ),
        InterventionType.REVERT_OVERLAY: "modify_config",
        InterventionType.SEND_NUDGE: "send_message",
        InterventionType.START_AGENT: "start",
        InterventionType.STOP_AGENT: "stop",
        InterventionType.FORK_PROBE: "fork",
    }.get(itype)
    worker_facing = {
        InterventionType.SEND_NUDGE,
        InterventionType.CONTINUE_SESSION,
        InterventionType.INJECT_CONTEXT,
        InterventionType.REQUEST_VERIFICATION,
        InterventionType.FRESH_HANDOFF,
    }
    if itype in worker_facing and not evidence:
        return ProposedAction(
            type=InterventionType.NOOP,
            session_id=request.session.id,
            goal_id=request.goal.id if request.goal else None,
            payload={},
            rationale="Worker-facing action had no evidence; defaulting to silence.",
            evidence=["empty_evidence_coerced_noop"],
            confidence=1.0,
            risk=RiskLevel.NONE,
            reversible=False,
            cooldown_seconds=5,
        )
    worker_text = str(payload.get("text") or "")
    if itype == InterventionType.NOOP and worker_text.strip():
        payload = {key: value for key, value in payload.items() if key != "text"}
        worker_text = ""
    if itype in worker_facing:
        cleaned = _sanitize_worker_text(worker_text)
        if worker_text.strip() and cleaned is None:
            return ProposedAction(
                type=InterventionType.NOOP,
                session_id=request.session.id,
                goal_id=request.goal.id if request.goal else None,
                payload={},
                rationale="Rejected generic worker-facing text.",
                evidence=["generic_worker_text_coerced_noop"],
                confidence=1.0,
                risk=RiskLevel.NONE,
                reversible=False,
                cooldown_seconds=5,
            )
        if worker_text.strip().startswith("PEX:"):
            payload = {**payload, "text": cleaned}
            worker_text = cleaned
        elif cleaned is not None and cleaned != worker_text:
            payload = {**payload, "text": cleaned}
            worker_text = cleaned
    return ProposedAction(
        type=itype,
        session_id=request.session.id,
        goal_id=request.goal.id if request.goal else None,
        payload=payload,
        rationale=_clip(
            _redact_request_text(request, proposal.get("rationale") or "strands"),
            2_000,
        ),
        evidence=[_clip(item, 1_000) for item in evidence[:20]],
        confidence=_confidence(proposal.get("confidence", 0.6)),
        risk=risk,
        reversible=itype in {InterventionType.APPLY_OVERLAY, InterventionType.CLEANUP},
        authority_required=Authority.HUMAN
        if itype
        in {
            InterventionType.ASK_HUMAN,
            InterventionType.START_AGENT,
            InterventionType.STOP_AGENT,
            InterventionType.FORK_PROBE,
        }
        else Authority.LOCAL_POLICY,
        requires_capability=capability,
    )


def _invalid_proposal(request: SupervisorRequest, reason: str) -> ProposedAction:
    return ProposedAction(
        type=InterventionType.NOOP,
        session_id=request.session.id,
        goal_id=request.goal.id if request.goal else None,
        payload={"invalid_proposal": reason},
        rationale=f"Rejected malformed supervisor proposal: {reason}",
        evidence=["typed_action_validation_failed"],
        confidence=1.0,
        risk=RiskLevel.NONE,
        reversible=False,
        cooldown_seconds=0,
        authority_required=Authority.LOCAL_POLICY,
    )


def build_agent(
    request: SupervisorRequest,
    *,
    model=None,
    used_tools: list[str] | None = None,
    collector: EvidenceObservationCollector | None = None,
):
    from strands import Agent

    observed_tools = used_tools if used_tools is not None else []
    kwargs = {
        "system_prompt": _system_prompt(),
        # These request-scoped tools expose bounded redacted evidence. Some make
        # fresh read-only workspace/public-web observations; none execute worker
        # code, touch a harness, mutate PEX, or read hidden benchmark material.
        "tools": build_evidence_tools(request, observed_tools, collector=collector),
        "callback_handler": None,
    }
    if model is not None:
        kwargs["model"] = model
    return Agent(**kwargs)


def build_verifier_agent(
    request: SupervisorRequest,
    *,
    model: object,
    used_tools: list[str],
    collector: EvidenceObservationCollector,
):
    """Create a fresh agent that can only inspect the same bounded evidence."""
    from strands import Agent

    return Agent(
        system_prompt=_verifier_system_prompt(),
        tools=build_evidence_tools(request, used_tools, collector=collector),
        callback_handler=None,
        model=model,
    )


def _format_verifier_user(
    request: SupervisorRequest,
    proposal: ProposedAction,
) -> str:
    import json

    goal = request.goal
    proposal_json = json.dumps(
        proposal.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )[:8_000]
    features = request.scores.features or {}
    context = request.supervisor_context
    rendered = (
        "Independently verify this proposed intervention.\n"
        f"Harness={request.session.harness_type.value} session={_clip(request.session.id, 200)}\n"
        f"Event={request.event.event_type.value} "
        f"{_clip(request.event.message_delta or request.event.command or '', 1_000)}\n"
        f"Goal={_clip(goal.objective, 4_000) if goal else 'unattached'}\n"
        f"Acceptance={_bounded_items(goal.acceptance_criteria) if goal else []}\n"
        f"Verification={_clip(features.get('verification') or 'none', 6_000)}\n"
        "OfferedContext="
        f"count={len(context.offered_context_ids) if context else 0} "
        f"first_ids={list(context.offered_context_ids[:3]) if context else []}\n"
        "OfferedDecisions="
        f"count={len(context.offered_decision_ids) if context else 0} "
        f"first_ids={list(context.offered_decision_ids[:3]) if context else []}\n"
        f"Proposal={proposal_json}\n"
        "Page through get_context_items and get_decisions, or query an exact offered ID, "
        "when durable context or user decisions justify the proposal. Query "
        "inspect_workspace, inspect_git, inspect_file, "
        "inspect_artifact, "
        "inspect_process, and run_verification when local state is required. "
        "Use web_search or scrape_url only for a public claim the worker cited. "
        "Approve or reject; do not propose or execute a different action."
    )
    return _redact_request_text(request, rendered)


def _runtime_version() -> str | None:
    try:
        return version("strands-agents")
    except PackageNotFoundError:
        return None


def _model_provenance(model: object) -> dict[str, Any]:
    attached = None
    with suppress(Exception):
        attached = getattr(model, "_pex_provenance", None)
    provenance = dict(attached) if isinstance(attached, dict) else {}
    if not provenance.get("model_id"):
        with suppress(Exception):
            config = model.get_config()  # type: ignore[attr-defined]
            if isinstance(config, dict):
                provenance["model_id"] = config.get("model_id") or config.get("model")
    provenance["model_class"] = f"{type(model).__module__}.{type(model).__qualname__}"
    return provenance


def _model_call_count(metrics: object | None) -> int:
    if metrics is None:
        return 0
    try:
        invocations = getattr(metrics, "agent_invocations", None) or []
        if isinstance(invocations, (list, tuple)):
            count = sum(
                min(10_000, len(getattr(item, "cycles", None) or []))
                for item in invocations[:10_000]
            )
            if count:
                return min(1_000_000, count)
        return _bounded_nonnegative_int(
            getattr(metrics, "cycle_count", 0), maximum=1_000_000
        )
    except Exception:
        return 0


def _public_base_url(request: SupervisorRequest, value: object) -> str | None:
    cleaned = _clip(_redact_request_text(request, value), 2_000).strip()
    if not cleaned:
        return None
    try:
        parsed = urlsplit(cleaned)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            return cleaned.split("?", 1)[0].split("#", 1)[0]
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return urlunsplit((parsed.scheme.casefold(), f"{host}{port}", parsed.path, "", ""))
    except (TypeError, ValueError):
        return cleaned.split("?", 1)[0].split("#", 1)[0]


def _decision_proposal(decision: SupervisorDecision) -> dict[str, Any]:
    payload = dict(decision.payload)
    if decision.message:
        payload.setdefault("text", decision.message)
    return {
        "type": decision.action_type.value,
        "rationale": decision.rationale,
        "evidence": list(decision.evidence),
        "payload": payload,
        "confidence": decision.confidence,
        "risk": decision.risk.value,
    }


def _result_metadata(
    *,
    request: SupervisorRequest,
    model: object,
    local_invocation_id: str,
    inference_status: str,
    metrics: object | None,
    evidence_tools: list[str],
    evidence_observations: list[SupervisorEvidenceObservation],
    evidence_refs: list[str],
) -> dict[str, Any]:
    provenance = _model_provenance(model)
    model_name = _clip(
        _redact_request_text(request, provenance.get("model_id") or type(model).__name__),
        512,
    )
    provider = _clip(_redact_request_text(request, provenance.get("provider") or ""), 128)
    auth_mode = _clip(_redact_request_text(request, provenance.get("auth_mode") or ""), 128)
    config_fingerprint = _clip(
        _redact_request_text(request, provenance.get("config_fingerprint") or ""), 64
    )
    return {
        "model_name": model_name or None,
        "inference_request_id": None,
        "local_invocation_id": local_invocation_id,
        "inference_status": inference_status,
        "model_call_count": _model_call_count(metrics),
        "runtime": "strands-agents",
        "runtime_version": _runtime_version(),
        "model_class": _clip(
            _redact_request_text(request, provenance.get("model_class") or ""), 512
        )
        or None,
        "provider": provider or None,
        "base_url": _public_base_url(request, provenance.get("base_url") or ""),
        "auth_mode": auth_mode or None,
        "config_fingerprint": config_fingerprint or None,
        "evidence_tools": list(dict.fromkeys(evidence_tools))[:20],
        "evidence_observations": evidence_observations,
        "evidence_refs": evidence_refs,
        "backend": provider or None,
    }


def _resolve_evidence_refs(
    request: SupervisorRequest,
    *,
    observations: list[SupervisorEvidenceObservation],
    raw_refs: object,
    stage: str,
    invocation_id: str,
) -> tuple[list[str], bool]:
    """Resolve model-cited observation IDs under exact request authority."""

    if (
        not isinstance(raw_refs, (list, tuple))
        or len(raw_refs) > 20
        or any(type(value) is not str or not value or len(value) > 128 for value in raw_refs)
    ):
        return [], False
    refs = list(raw_refs)
    try:
        validate_evidence_observation_bindings(
            observations,
            refs,
            stage="verifier" if stage == "verifier" else "main",
            request_digest=supervisor_request_digest(request),
            session_id=request.session.id,
            goal_id=request.goal.id if request.goal else None,
            event_id=request.event.event_id,
            invocation_id=invocation_id,
        )
    except ValueError:
        return [], False
    return refs, True


def _uncertain_verification_only(
    request: SupervisorRequest,
    referenced_tools: set[str],
) -> bool:
    verification = (request.scores.features or {}).get("verification") or {}
    verification_status = str(verification.get("status") or "unavailable")
    acceptance_status = str(verification.get("acceptance_status") or "unavailable")
    return (
        bool(referenced_tools)
        and referenced_tools <= {"get_goal", "run_verification"}
        and verification_status in {"no_claims", "uncertain", "unavailable"}
        and acceptance_status in {"uncertain", "unavailable"}
    )


async def run_strands_async(
    request: SupervisorRequest,
    model: object,
    *,
    wall_timeout: float | None = None,
) -> SupervisorResult:
    """Run one fresh, bounded Strands Agent and require validated output."""

    _configure_stdio()
    started = time.perf_counter()
    local_invocation_id = f"pexinv_{uuid4()}"
    used_tools: list[str] = []
    collector = EvidenceObservationCollector(
        request,
        stage="main",
        invocation_id=local_invocation_id,
    )
    agent = build_agent(
        request,
        model=model,
        used_tools=used_tools,
        collector=collector,
    )
    invocation = asyncio.create_task(
        agent.invoke_async(
            _format_user(request),
            structured_output_model=SupervisorDecision,
            limits={"turns": 3, "output_tokens": 1_200, "total_tokens": 12_000},
        )
    )
    if wall_timeout is None:
        try:
            wall_timeout = float(os.environ.get("PEX_SUPERVISOR_WALL_TIMEOUT", "25"))
        except ValueError:
            wall_timeout = 25.0
    wall_timeout = _bounded_wall_timeout(wall_timeout, default=25.0)
    try:
        result = await asyncio.wait_for(asyncio.shield(invocation), timeout=wall_timeout)
    except TimeoutError:
        with suppress(Exception):
            agent.cancel()
        invocation.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await invocation
        metrics = getattr(agent, "event_loop_metrics", None)
        meta = _result_metadata(
            request=request,
            model=model,
            local_invocation_id=local_invocation_id,
            inference_status="timeout",
            metrics=metrics,
            evidence_tools=used_tools,
            evidence_observations=list(collector.observations),
            evidence_refs=[],
        )
        return SupervisorResult(
            action=_action_from_proposal(
                request,
                {
                    "type": "NOOP",
                    "rationale": "Strands supervisor timed out.",
                    "evidence": ["strands_timeout"],
                },
            ),
            used_llm=True,
            diagnosis="strands_timeout",
            traces=["strands_timeout"],
            latency_ms=int((time.perf_counter() - started) * 1000),
            **meta,
        )
    except asyncio.CancelledError:
        with suppress(Exception):
            agent.cancel()
        invocation.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await invocation
        raise
    except Exception as exc:
        metrics = getattr(agent, "event_loop_metrics", None)
        meta = _result_metadata(
            request=request,
            model=model,
            local_invocation_id=local_invocation_id,
            inference_status="failed",
            metrics=metrics,
            evidence_tools=used_tools,
            evidence_observations=list(collector.observations),
            evidence_refs=[],
        )
        detail = type(exc).__name__
        return SupervisorResult(
            action=_action_from_proposal(
                request,
                {
                    "type": "NOOP",
                    "rationale": "Strands supervisor failed to return a decision.",
                    "evidence": ["strands_inference_failed"],
                },
            ),
            used_llm=True,
            diagnosis=f"strands_failed:{detail}",
            traces=[detail],
            latency_ms=int((time.perf_counter() - started) * 1000),
            **meta,
        )

    metrics = getattr(result, "metrics", None)
    structured = getattr(result, "structured_output", None)
    evidence_refs: list[str] = []
    refs_valid = True
    if isinstance(structured, SupervisorDecision):
        evidence_refs, refs_valid = _resolve_evidence_refs(
            request,
            observations=list(collector.observations),
            raw_refs=structured.evidence_refs,
            stage="main",
            invocation_id=local_invocation_id,
        )
    meta = _result_metadata(
        request=request,
        model=model,
        local_invocation_id=local_invocation_id,
        inference_status="completed" if isinstance(structured, SupervisorDecision) else "failed",
        metrics=metrics,
        evidence_tools=used_tools,
        evidence_observations=list(collector.observations),
        evidence_refs=evidence_refs,
    )
    input_tokens, output_tokens = _usage(result)
    if not isinstance(structured, SupervisorDecision):
        return SupervisorResult(
            action=_action_from_proposal(
                request,
                {
                    "type": "NOOP",
                    "rationale": "Strands returned no validated structured decision.",
                    "evidence": ["strands_missing_structured_output"],
                },
            ),
            used_llm=True,
            diagnosis="strands_missing_structured_output",
            traces=[f"stop_reason={getattr(result, 'stop_reason', None)}"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
            **meta,
        )
    action = _action_from_proposal(request, _decision_proposal(structured))
    if action.type != InterventionType.NOOP and (not refs_valid or not evidence_refs):
        action = _action_from_proposal(
            request,
            {
                "type": "NOOP",
                "rationale": "Supervisor intervention lacked cited request-bound evidence.",
                "evidence": ["missing_or_invalid_evidence_refs"],
            },
        )
    return SupervisorResult(
        action=action,
        used_llm=True,
        diagnosis=(
            "strands_structured_decision"
            if action.type == structured.action_type
            else "strands_structured_decision:invalid_evidence_refs"
        ),
        traces=[f"stop_reason={getattr(result, 'stop_reason', None)}"],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=int((time.perf_counter() - started) * 1000),
        **meta,
    )


async def run_independent_verifier_async(
    request: SupervisorRequest,
    proposal: ProposedAction,
    *,
    model: object,
    wall_timeout: float | None = None,
) -> dict[str, Any]:
    """Run a fresh second Agent; failure or missing evidence rejects the action."""

    started = time.perf_counter()
    verifier_invocation_id = f"pexver_{uuid4()}"
    used_tools: list[str] = []
    collector = EvidenceObservationCollector(
        request,
        stage="verifier",
        invocation_id=verifier_invocation_id,
    )
    agent = build_verifier_agent(
        request,
        model=model,
        used_tools=used_tools,
        collector=collector,
    )
    invocation = asyncio.create_task(
        agent.invoke_async(
            _format_verifier_user(request, proposal),
            structured_output_model=IndependentVerifierDecision,
            limits={"turns": 3, "output_tokens": 900, "total_tokens": 10_000},
        )
    )
    if wall_timeout is None:
        try:
            wall_timeout = float(os.environ.get("PEX_VERIFIER_WALL_TIMEOUT", "15"))
        except ValueError:
            wall_timeout = 15.0
    wall_timeout = _bounded_wall_timeout(wall_timeout, default=15.0)
    try:
        result = await asyncio.wait_for(asyncio.shield(invocation), timeout=wall_timeout)
    except TimeoutError:
        with suppress(Exception):
            agent.cancel()
        invocation.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await invocation
        metrics = getattr(agent, "event_loop_metrics", None)
        return {
            "approved": False,
            "status": "timeout",
            "rationale": "Independent verifier timed out; semantic-only action rejected.",
            "evidence": [],
            "evidence_tools": list(dict.fromkeys(used_tools))[:20],
            "invocation_id": verifier_invocation_id,
            "evidence_observations": list(collector.observations),
            "evidence_refs": [],
            "model_call_count": _model_call_count(metrics),
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except asyncio.CancelledError:
        with suppress(Exception):
            agent.cancel()
        invocation.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await invocation
        raise
    except Exception as exc:
        metrics = getattr(agent, "event_loop_metrics", None)
        return {
            "approved": False,
            "status": f"failed:{type(exc).__name__}",
            "rationale": "Independent verifier failed; semantic-only action rejected.",
            "evidence": [],
            "evidence_tools": list(dict.fromkeys(used_tools))[:20],
            "invocation_id": verifier_invocation_id,
            "evidence_observations": list(collector.observations),
            "evidence_refs": [],
            "model_call_count": _model_call_count(metrics),
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }

    metrics = getattr(result, "metrics", None)
    structured = getattr(result, "structured_output", None)
    input_tokens, output_tokens = _usage(result)
    if not isinstance(structured, IndependentVerifierDecision):
        return {
            "approved": False,
            "status": "missing_structured_output",
            "rationale": "Independent verifier returned no validated verdict.",
            "evidence": [],
            "evidence_tools": list(dict.fromkeys(used_tools))[:20],
            "invocation_id": verifier_invocation_id,
            "evidence_observations": list(collector.observations),
            "evidence_refs": [],
            "model_call_count": _model_call_count(metrics),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    evidence = [
        _clip(_redact_request_text(request, item), 1_000)
        for item in structured.evidence[:20]
        if item.strip()
    ]
    evidence_refs, refs_valid = _resolve_evidence_refs(
        request,
        observations=list(collector.observations),
        raw_refs=structured.evidence_refs,
        stage="verifier",
        invocation_id=verifier_invocation_id,
    )
    referenced = {
        item.observation_id: item for item in collector.observations
    }
    unique_tools = {
        referenced[item].tool_name for item in evidence_refs if item in referenced
    }
    evidence_tool_used = bool(
        unique_tools
        & {
            "get_context",
            "get_recent_events",
            "get_scores",
            "get_session_state",
            "inspect_workspace",
            "inspect_git",
            "inspect_file",
            "inspect_artifact",
            "inspect_process",
            "run_verification",
        }
    )
    uncertain_verification_only = _uncertain_verification_only(request, unique_tools)
    approved = bool(
        structured.approved
        and evidence
        and refs_valid
        and bool(evidence_refs)
        and evidence_tool_used
        and not uncertain_verification_only
    )
    if approved:
        status = "approved"
    elif structured.approved and evidence and uncertain_verification_only:
        status = "uncertain_evidence"
    elif structured.approved and (not refs_valid or not evidence_refs):
        status = "missing_or_invalid_evidence_refs"
    elif structured.approved and evidence and not evidence_tool_used:
        status = "missing_evidence_tool"
    else:
        status = "rejected"
    return {
        "approved": approved,
        "status": status,
        "rationale": _clip(_redact_request_text(request, structured.rationale), 2_000),
        "evidence": evidence,
        "evidence_tools": list(dict.fromkeys(used_tools))[:20],
        "invocation_id": verifier_invocation_id,
        "evidence_observations": list(collector.observations),
        "evidence_refs": evidence_refs,
        "model_call_count": _model_call_count(metrics),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def run_strands(request: SupervisorRequest, model=None) -> SupervisorResult:
    """Compatibility entry point for synchronous callers and tests."""

    if model is None:
        model = load_supervisor_model()
    if model is None:
        return SupervisorResult(
            action=plan_deterministic(request),
            used_llm=False,
            diagnosis="deterministic_triage_no_supervisor_model",
        )
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_strands_async(request, model=model))
    raise RuntimeError("run_strands() cannot run inside an event loop; await run_strands_async()")


def _usage(result: object) -> tuple[int, int]:
    metrics = getattr(result, "metrics", None)
    usage = (
        getattr(result, "accumulated_usage", None)
        or getattr(metrics, "accumulated_usage", None)
        or getattr(result, "usage", None)
    )
    def bounded_count(value: object) -> int:
        try:
            parsed = int(value or 0)
        except (TypeError, ValueError, OverflowError):
            return 0
        return min(1_000_000_000_000, max(0, parsed))

    if isinstance(usage, dict):
        return bounded_count(
            usage.get("inputTokens") or usage.get("input_tokens")
        ), bounded_count(usage.get("outputTokens") or usage.get("output_tokens"))
    if usage is None:
        return 0, 0
    return bounded_count(
        getattr(usage, "inputTokens", 0) or getattr(usage, "input_tokens", 0)
    ), bounded_count(
        getattr(usage, "outputTokens", 0) or getattr(usage, "output_tokens", 0)
    )


def needs_semantic_inference(request: SupervisorRequest, force_llm: bool = False) -> bool:
    """Deterministic triage first. Model inspect only on STOP with a attached goal."""
    from pex_protocol.enums import EventType

    if force_llm or os.environ.get("PEX_FORCE_LLM") == "1":
        return True
    if request.event.event_type != EventType.STOP:
        return False
    return request.goal is not None


def _preserve_deterministic_truth(
    request: SupervisorRequest,
    deterministic: ProposedAction,
    semantic: SupervisorResult,
) -> SupervisorResult:
    """Keep triage from manufacturing a decision after semantic inspection.

    The deterministic plan is computed before the supervisor can inspect more
    evidence.  It may guard a fully verified completion, but it must not turn a
    failed inference or an intentional semantic NOOP into an intervention.
    """

    if semantic.inference_status != "completed":
        if semantic.action.type != InterventionType.NOOP:
            semantic.action = _action_from_proposal(
                request,
                {
                    "type": "NOOP",
                    "rationale": "Semantic inference did not complete; defaulting to silence.",
                    "evidence": ["incomplete_semantic_inference"],
                },
            )
            semantic.diagnosis = f"{semantic.diagnosis}:incomplete_inference_noop"
            semantic.traces.append("incomplete_inference_action_rejected")
        return semantic

    # A completed NOOP is a real supervisor decision.  In particular, do not
    # restore a stale pre-model REQUEST_VERIFICATION after the supervisor has
    # used its evidence tools and concluded that no action is needed.
    if semantic.action.type == InterventionType.NOOP:
        return semantic

    verification = (request.scores.features or {}).get("verification") or {}
    acceptance_supported = verification.get("acceptance_status") == "supported"
    verification_status = verification.get("status")
    completion_supported = acceptance_supported and verification_status in {
        "supported",
        "no_claims",
    }
    if (
        deterministic.type == InterventionType.NOOP
        and completion_supported
    ):
        semantic.action = deterministic
        semantic.diagnosis = f"{semantic.diagnosis}:verified_noop_preserved"
        semantic.traces.append("verified_noop_preserved")
    return semantic


def _needs_independent_verifier(
    request: SupervisorRequest,
    _deterministic: ProposedAction,
    semantic: SupervisorResult,
) -> bool:
    """Every completed semantic STOP intervention needs independent evidence."""
    from pex_protocol.enums import EventType

    return (
        request.event.event_type == EventType.STOP
        and semantic.inference_status == "completed"
        and semantic.action.type != InterventionType.NOOP
    )


def _apply_verifier_receipt(
    request: SupervisorRequest,
    semantic: SupervisorResult,
    _deterministic: ProposedAction,
    receipt: dict[str, Any],
) -> SupervisorResult:
    status = _clip(_redact_request_text(request, receipt.get("status") or "failed"), 120)
    rationale = _clip(
        _redact_request_text(request, receipt.get("rationale") or ""), 2_000
    )
    raw_evidence = receipt.get("evidence")
    receipt_evidence = raw_evidence if isinstance(raw_evidence, (list, tuple)) else []
    verifier_evidence = [
        _clip(_redact_request_text(request, item), 1_000)
        for item in receipt_evidence[:20]
    ]
    raw_invocation_id = receipt.get("invocation_id")
    invocation_id = None
    if (
        type(raw_invocation_id) is str
        and raw_invocation_id
        and len(raw_invocation_id) <= 128
        and _redact_request_text(request, raw_invocation_id) == raw_invocation_id
    ):
        invocation_id = raw_invocation_id
    observations: list[SupervisorEvidenceObservation] = []
    raw_observations = receipt.get("evidence_observations")
    observations_valid = (
        isinstance(raw_observations, (list, tuple))
        and len(raw_observations) <= 24
    )
    if observations_valid:
        try:
            observations = [
                item
                if isinstance(item, SupervisorEvidenceObservation)
                else SupervisorEvidenceObservation.model_validate(item)
                for item in raw_observations[:24]
            ]
        except Exception:
            observations_valid = False
            observations = []
    raw_refs = receipt.get("evidence_refs")
    verifier_refs: list[str] = []
    refs_valid = False
    bindings_valid = False
    if observations_valid and invocation_id is not None:
        try:
            validate_evidence_observation_bindings(
                observations,
                [],
                stage="verifier",
                request_digest=supervisor_request_digest(request),
                session_id=request.session.id,
                goal_id=request.goal.id if request.goal else None,
                event_id=request.event.event_id,
                invocation_id=invocation_id,
            )
            bindings_valid = True
        except ValueError:
            observations = []
    if not bindings_valid:
        observations = []
    if bindings_valid:
        verifier_refs, refs_valid = _resolve_evidence_refs(
            request,
            observations=observations,
            raw_refs=raw_refs,
            stage="verifier",
            invocation_id=invocation_id,
        )
    if invocation_id == semantic.local_invocation_id:
        observations = []
        refs_valid = False
        verifier_refs = []
    referenced_ids = set(verifier_refs)
    referenced_tools = {
        item.tool_name
        for item in observations
        if item.observation_id in referenced_ids
    }
    verifier_tools = list(dict.fromkeys(item.tool_name for item in observations))[:20]
    if receipt.get("approved") is True and (
        not refs_valid or _uncertain_verification_only(request, referenced_tools)
    ):
        status = (
            "uncertain_evidence"
            if refs_valid and _uncertain_verification_only(request, referenced_tools)
            else "invalid_evidence_refs"
        )
    verifier_model_call_count = _strict_verifier_int(
        receipt.get("model_call_count"), maximum=1_000_000
    )
    verifier_input_tokens = _strict_verifier_int(receipt.get("input_tokens"))
    verifier_output_tokens = _strict_verifier_int(receipt.get("output_tokens"))
    verifier_latency_ms = _strict_verifier_int(
        receipt.get("latency_ms"), maximum=86_400_000
    )
    semantic.independent_verifier = IndependentVerifierReceipt(
        approved=receipt.get("approved") is True,
        status=status,
        rationale=rationale,
        evidence=verifier_evidence,
        evidence_tools=verifier_tools,
        invocation_id=invocation_id,
        evidence_observations=observations,
        evidence_refs=verifier_refs,
        model_call_count=verifier_model_call_count,
        input_tokens=verifier_input_tokens,
        output_tokens=verifier_output_tokens,
        latency_ms=verifier_latency_ms,
    )
    semantic.model_call_count = _bounded_nonnegative_int(
        semantic.model_call_count + verifier_model_call_count,
        maximum=1_000_000,
    )
    semantic.input_tokens = _bounded_nonnegative_int(
        semantic.input_tokens + verifier_input_tokens
    )
    semantic.output_tokens = _bounded_nonnegative_int(
        semantic.output_tokens + verifier_output_tokens
    )
    semantic.latency_ms = _bounded_nonnegative_int(
        semantic.latency_ms + verifier_latency_ms,
        maximum=86_400_000,
    )
    semantic.evidence_tools = list(
        dict.fromkeys(
            [
                *semantic.evidence_tools,
                *verifier_tools,
            ]
        )
    )[:20]
    traces = [*semantic.traces, f"independent_verifier_status={status}"]
    if rationale:
        traces.append(f"independent_verifier_rationale={rationale}")
    traces.extend(f"independent_verifier_evidence={item}" for item in verifier_evidence)
    semantic.traces = [_clip(item, 4_000) for item in traces[-256:]]
    if semantic.independent_verifier.authorizes_intervention():
        semantic.diagnosis = f"{semantic.diagnosis}:independent_verifier_approved"
        return semantic
    semantic.action = _action_from_proposal(
        request,
        {
            "type": "NOOP",
            "rationale": "Independent verification did not authorize the intervention.",
            "evidence": [f"independent_verifier:{status}"],
        },
    )
    semantic.diagnosis = f"{semantic.diagnosis}:independent_verifier_rejected"
    return semantic


async def decide_async(
    request: SupervisorRequest,
    model=None,
    force_llm: bool = False,
) -> SupervisorResult:
    deterministic = plan_deterministic(request)
    if model is None and (force_llm or os.environ.get("PEX_FORCE_LLM") == "1"):
        model = load_supervisor_model()
    if model is None:
        return SupervisorResult(
            action=deterministic,
            used_llm=False,
            diagnosis="deterministic_triage_no_supervisor_model",
            backend=None,
        )
    if not needs_semantic_inference(request, force_llm=force_llm):
        return SupervisorResult(
            action=deterministic,
            used_llm=False,
            diagnosis="deterministic_triage",
            backend=describe_backend().get("backend"),
        )
    try:
        semantic = await run_strands_async(request, model=model)
    except Exception as exc:
        detail = type(exc).__name__
        return SupervisorResult(
            action=_action_from_proposal(
                request,
                {
                    "type": "NOOP",
                    "rationale": "Strands supervisor could not start; defaulting to silence.",
                    "evidence": ["strands_setup_failed"],
                },
            ),
            used_llm=False,
            diagnosis=f"strands_unavailable:{detail}",
            traces=[detail],
            inference_status="failed",
            backend=describe_backend().get("backend"),
        )
    try:
        semantic = _preserve_deterministic_truth(request, deterministic, semantic)
        if _needs_independent_verifier(request, deterministic, semantic):
            try:
                receipt = await run_independent_verifier_async(
                    request,
                    semantic.action,
                    model=model,
                )
            except Exception as exc:
                # The main model call already happened. Preserve that provenance
                # while failing the unverified action closed.
                receipt = {
                    "approved": False,
                    "status": f"failed:{type(exc).__name__}",
                    "rationale": "Independent verifier setup failed; action rejected.",
                    "evidence": [],
                    "evidence_tools": [],
                    "model_call_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "latency_ms": 0,
                }
            semantic = _apply_verifier_receipt(request, semantic, deterministic, receipt)
        return semantic
    except Exception as exc:
        detail = type(exc).__name__
        semantic.action = _action_from_proposal(
            request,
            {
                "type": "NOOP",
                "rationale": "Supervisor arbitration failed; defaulting to silence.",
                "evidence": ["post_inference_arbitration_failed"],
            },
        )
        semantic.diagnosis = f"{semantic.diagnosis}:post_inference_failure:{detail}"
        semantic.traces = [
            *semantic.traces,
            f"post_inference_failure:{detail}",
        ][-256:]
        return semantic


def decide(request: SupervisorRequest, model=None, force_llm: bool = False) -> SupervisorResult:
    """Synchronous entry point for CLI/AgentCore callers outside an event loop."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(decide_async(request, model=model, force_llm=force_llm))
    raise RuntimeError("decide() cannot run inside an event loop; await decide_async()")
