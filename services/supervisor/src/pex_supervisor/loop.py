from __future__ import annotations

import os
import time
from pathlib import Path
from uuid import uuid4

from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority
from pex_protocol.supervisor import SupervisorRequest, SupervisorResult

from pex_supervisor.planner import plan_deterministic
from pex_supervisor.providers import describe_backend, load_supervisor_model
from pex_supervisor.tools import SUPERVISOR_TOOLS, bind_request, reset_request, take_proposed

PROMPT_PATH = Path(__file__).parent / "prompts" / "supervisor.md"


def _system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


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
        f"Notes: {request.notes}\n"
        f"Observed process state: {request.event.process_state}\n"
        "Use tools if needed, then call propose_typed_action exactly once."
    )


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
    return ProposedAction(
        type=itype,
        session_id=request.session.id,
        goal_id=request.goal.id if request.goal else None,
        payload=payload,
        rationale=str(proposal.get("rationale") or "strands"),
        evidence=list(proposal.get("evidence") or []),
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
        "tools": SUPERVISOR_TOOLS,
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
        agent = build_agent(model=model)
        prompt = _format_user(request)
        result = agent(prompt)
        traces.append(str(getattr(result, "message", result)))
        proposal = take_proposed()
        if proposal:
            action = _action_from_proposal(request, proposal)
            diagnosis = "strands_supervisor"
        else:
            action = plan_deterministic(request)
            traces.append("strands produced no typed action; fell back to deterministic planner")
            diagnosis = "strands_no_tool_fallback_deterministic"
        input_tokens, output_tokens = _usage(result)
        return SupervisorResult(
            action=action,
            used_llm=True,
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
    try:
        from pex_supervisor.graphs import run_intervention_graph, should_use_graph

        if should_use_graph(request):
            return run_intervention_graph(request, model=model)
        return run_strands(request, model=model)
    except Exception as exc:
        deterministic.payload["degraded"] = str(exc)
        return SupervisorResult(
            action=deterministic,
            used_llm=False,
            diagnosis=f"strands_unavailable:{exc}",
            traces=[str(exc)],
            backend=describe_backend().get("backend"),
        )
