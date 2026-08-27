from __future__ import annotations

import os
import re
import time
from pathlib import Path
from uuid import uuid4

from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority
from pex_protocol.supervisor import SupervisorRequest, SupervisorResult

from pex_supervisor.inspect_http import InspectUnavailable, complete_typed_action
from pex_supervisor.planner import plan_deterministic
from pex_supervisor.providers import describe_backend, load_supervisor_model
from pex_supervisor.tools import bind_request, propose_typed_action, record_proposal, reset_request, take_proposed

PROMPT_PATH = Path(__file__).parent / "prompts" / "supervisor.md"


def _safe_text(value: object) -> str:
    text = str(value)
    return text.encode("utf-8", "replace").decode("utf-8")


def _configure_stdio() -> None:
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            continue


def _system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _prefetch_evidence(request: SupervisorRequest) -> str:
    import json

    from pex_supervisor.workspace import snapshot

    cwd = request.session.cwd
    events = request.recent_events[-12:]
    recent = [
        {
            "type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
            "text": (event.message_delta or event.command or "")[:240],
        }
        for event in events
    ]
    workspace: dict = {"cwd": cwd or None}
    if cwd:
        raw = snapshot(cwd)
        workspace = {
            "cwd": raw.get("workspace") or cwd,
            "files": (raw.get("files") or [])[:80],
            "artifacts": raw.get("artifacts") or [],
            "git": raw.get("git") or {},
        }
    return json.dumps({"recent_events": recent, "workspace": workspace}, ensure_ascii=False)[:6000]


def _compact_inspect_user(request: SupervisorRequest) -> str:
    goal = request.goal
    event_text = (request.event.command or request.event.message_delta or "")[:300]
    prefetch = _prefetch_evidence(request)[:2000]
    claims = request.scores.features.get("claims") if request.scores.features else None
    return (
        f"Harness={request.session.harness_type} event={request.event.event_type} {event_text}\n"
        f"Goal={goal.objective if goal else 'unattached'}\n"
        f"Acceptance={list(goal.acceptance_criteria) if goal else []}\n"
        f"Required={list(goal.evidence_requirements) if goal else []}\n"
        f"Claims={claims or request.notes or 'none'}\n"
        f"Evidence={prefetch}\n"
        "JSON only: action_type, rationale, evidence, message. "
        "If a required file is missing, SEND_NUDGE naming it. "
        "If no completion claims were extracted, do not assume the worker said it is done. "
        "If evidence supports completion, NOOP. Never prefix the message with PEX:."
    )


def _http_system_prompt() -> str:
    return (
        "You are PEX, a goal-aware supervisor for existing coding agents. "
        "A stop event is a trigger to inspect, not proof of failure. "
        "If a listed evidence requirement is absent from workspace files, "
        "action_type must be SEND_NUDGE or CONTINUE_SESSION and message must name that file. "
        "Do not NOOP while a required file is missing. Never invent capabilities. "
        "Never prefix worker text with PEX:."
    )


def _format_user(request: SupervisorRequest) -> str:
    goal = request.goal
    event_text = request.event.command or request.event.message_delta or ""
    return (
        "Normalized supervision request.\n"
        f"Harness: {request.session.harness_type}\n"
        f"Session: {request.session.id}\n"
        f"Status: {request.session.status}\n"
        f"Event: {request.event.event_type} {event_text}\n"
        f"Scores: {request.scores.model_dump_json()}\n"
        f"Goal: {goal.objective if goal else 'unattached'}\n"
        f"Acceptance: {goal.acceptance_criteria if goal else []}\n"
        f"Evidence requirements: {goal.evidence_requirements if goal else []}\n"
        f"Notes: {request.notes}\n"
        f"Extracted claims: {request.scores.features.get('claims') if request.scores.features else []}\n"
        f"Observed process state: {request.event.process_state}\n"
        f"Prefetched evidence (do not re-fetch):\n{_prefetch_evidence(request)}\n"
        "Call propose_typed_action exactly once. Do not call other tools."
    )


_FILE_TOKEN = re.compile(r"^[A-Za-z0-9._-]{1,72}\.[A-Za-z0-9]{1,8}$")
_GENERIC_NAG = re.compile(
    r"^(keep going|continue|verify with the required|do not stop|don't stop until)\b",
    re.I,
)


def _sanitize_worker_text(text: str) -> str | None:
    cleaned = re.sub(r"^PEX:\s*", "", (text or "").strip())
    if not cleaned:
        return None
    if _GENERIC_NAG.search(cleaned) and not re.search(
        r"\b[A-Za-z0-9._-]{1,72}\.[A-Za-z0-9]{1,8}\b", cleaned
    ):
        return None
    return cleaned


def _missing_required_files(request: SupervisorRequest) -> list[str]:
    goal = request.goal
    cwd = request.session.cwd
    if not goal or not cwd:
        return []

    root = Path(cwd)
    missing: list[str] = []
    for raw in list(goal.evidence_requirements or []) + list(goal.acceptance_criteria or []):
        name = str(raw or "").strip()
        if not _FILE_TOKEN.fullmatch(name):
            continue
        if not (root / name).exists():
            missing.append(name)
    return missing


def _action_from_proposal(request: SupervisorRequest, proposal: dict) -> ProposedAction:
    try:
        itype = InterventionType(proposal["type"])
    except (KeyError, ValueError):
        itype = InterventionType.NOOP
    risk_raw = str(proposal.get("risk") or "low").lower()
    try:
        risk = RiskLevel(risk_raw)
    except ValueError:
        risk = RiskLevel.LOW
    payload = proposal.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    payload_error = str(proposal.get("payload_error") or "")
    unsupported = {
        InterventionType.CLEANUP,
        InterventionType.FORK_PROBE,
        InterventionType.START_AGENT,
        InterventionType.STOP_AGENT,
    }
    if itype in unsupported:
        return _ask_human_for_unsupported(request, itype)
    if payload_error:
        return _invalid_proposal(request, f"invalid payload JSON: {payload_error}")
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
    if itype == InterventionType.REVERT_OVERLAY and not str(
        payload.get("overlay_id") or ""
    ).strip():
        return _invalid_proposal(request, "REVERT_OVERLAY requires overlay_id")
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
    }.get(itype)
    evidence = list(proposal.get("evidence") or [])
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
            reversible=True,
            cooldown_seconds=5,
        )
    worker_text = str(payload.get("text") or "")
    if itype == InterventionType.NOOP and worker_text.strip():
        payload = {key: value for key, value in payload.items() if key != "text"}
        worker_text = ""
    if itype == InterventionType.NOOP:
        missing = _missing_required_files(request)
        if missing:
            itype = InterventionType.SEND_NUDGE
            capability = "send_message"
            goal = request.goal
            objective = str(getattr(goal, "objective", "") or "").strip()
            payload = {
                **payload,
                "text": (
                    f"{missing[0]} is missing from the workspace. "
                    + (objective or f"Create {missing[0]}.")
                ),
            }
            worker_text = payload["text"]
            evidence = [
                *evidence,
                *(f"missing:{name}" for name in missing if f"missing:{name}" not in evidence),
            ]
    if itype in worker_facing:
        cleaned = _sanitize_worker_text(worker_text)
        if worker_text.strip().startswith("PEX:"):
            if cleaned is None:
                return ProposedAction(
                    type=InterventionType.NOOP,
                    session_id=request.session.id,
                    goal_id=request.goal.id if request.goal else None,
                    payload={},
                    rationale="Rejected generic PEX-prefixed worker text.",
                    evidence=["canned_prefix_coerced_noop"],
                    confidence=1.0,
                    risk=RiskLevel.NONE,
                    reversible=True,
                    cooldown_seconds=5,
                )
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
        rationale=str(proposal.get("rationale") or "strands"),
        evidence=evidence,
        confidence=float(proposal.get("confidence") or 0.6),
        risk=risk,
        reversible=itype not in {InterventionType.STOP_AGENT, InterventionType.CLEANUP},
        authority_required=Authority.HUMAN
        if itype == InterventionType.ASK_HUMAN
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
        reversible=True,
        cooldown_seconds=0,
        authority_required=Authority.LOCAL_POLICY,
    )


def _ask_human_for_unsupported(
    request: SupervisorRequest, proposed_type: InterventionType
) -> ProposedAction:
    return ProposedAction(
        type=InterventionType.ASK_HUMAN,
        session_id=request.session.id,
        goal_id=request.goal.id if request.goal else None,
        payload={
            "text": (
                f"PEX proposed {proposed_type.value}, which requires explicit human control."
            )
        },
        rationale=f"{proposed_type.value} is not executable by the local supervisor.",
        evidence=["unsupported_supervisor_action"],
        confidence=1.0,
        risk=RiskLevel.HIGH,
        reversible=True,
        cooldown_seconds=0,
        authority_required=Authority.HUMAN,
    )


def build_agent(model=None):
    from strands import Agent

    kwargs = {
        "system_prompt": _system_prompt(),
        "tools": [propose_typed_action],
        "callback_handler": None,
    }
    if model is not None:
        kwargs["model"] = model
    return Agent(**kwargs)


def run_strands(request: SupervisorRequest, model=None) -> SupervisorResult:
    token = bind_request(request)
    traces: list[str] = []
    request_id = str(uuid4())
    started = time.perf_counter()
    backend = describe_backend()
    try:
        _configure_stdio()
        used_llm = False
        input_tokens = 0
        output_tokens = 0
        try:
            args, usage, preview = complete_typed_action(
                _http_system_prompt(), _compact_inspect_user(request)
            )
            record_proposal(
                action_type=str(args.get("action_type") or "NOOP"),
                rationale=str(args.get("rationale") or "strands"),
                evidence=args.get("evidence") or "",
                message=str(args.get("message") or ""),
                payload_json=str(args.get("payload_json") or ""),
                request_id=str(args.get("request_id") or ""),
                decision=str(args.get("decision") or ""),
                overlay_id=str(args.get("overlay_id") or ""),
                confidence=args.get("confidence") or 0.7,
                risk=str(args.get("risk") or "low"),
            )
            traces.append(preview)
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            used_llm = True
        except InspectUnavailable:
            traces.append("openai-compat inspect unavailable")
        except Exception as exc:
            traces.append(_safe_text(exc))
        proposal = take_proposed()
        if proposal:
            action = _action_from_proposal(request, proposal)
            diagnosis = "strands_supervisor"
        else:
            action = _action_from_proposal(
                request,
                {
                    "type": "NOOP",
                    "rationale": traces[-1] if traces else "inspect produced no typed action",
                    "evidence": ["inspect_no_proposal"],
                },
            )
            diagnosis = (
                "strands_no_tool_fallback_noop"
                if used_llm
                else f"strands_unavailable:{traces[-1] if traces else 'inspect_failed'}"
            )
        return SupervisorResult(
            action=action,
            used_llm=used_llm,
            model_name=backend.get("model_id")
            or (type(model).__name__ if model is not None else "strands-default"),
            diagnosis=diagnosis,
            traces=traces,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
            inference_request_id=request_id,
            backend=backend.get("backend"),
        )
    finally:
        reset_request(token)


def _usage(result: object) -> tuple[int, int]:
    metrics = getattr(result, "metrics", None)
    usage = (
        getattr(result, "accumulated_usage", None)
        or getattr(metrics, "accumulated_usage", None)
        or getattr(result, "usage", None)
    )
    if isinstance(usage, dict):
        return int(usage.get("inputTokens") or usage.get("input_tokens") or 0), int(
            usage.get("outputTokens") or usage.get("output_tokens") or 0
        )
    if usage is None:
        return 0, 0
    return int(
        getattr(usage, "inputTokens", 0) or getattr(usage, "input_tokens", 0) or 0
    ), int(getattr(usage, "outputTokens", 0) or getattr(usage, "output_tokens", 0) or 0)


def needs_semantic_inference(request: SupervisorRequest, force_llm: bool = False) -> bool:
    """Deterministic triage first. Model inspect only on STOP with a attached goal."""
    from pex_protocol.enums import EventType

    if force_llm or os.environ.get("PEX_FORCE_LLM") == "1":
        return True
    if request.event.event_type != EventType.STOP:
        return False
    return request.goal is not None


def decide(request: SupervisorRequest, model=None, force_llm: bool = False) -> SupervisorResult:
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
        # STOP inspect must finish inside Cursor's stop hook. The multi-agent
        # graph tool-loops past that budget; one propose-only Strands call is enough.
        return run_strands(request, model=model)
    except Exception as exc:
        deterministic.payload["degraded"] = _safe_text(exc)
        return SupervisorResult(
            action=deterministic,
            used_llm=False,
            diagnosis=f"strands_unavailable:{_safe_text(exc)}",
            traces=[_safe_text(exc)],
            backend=describe_backend().get("backend"),
        )
