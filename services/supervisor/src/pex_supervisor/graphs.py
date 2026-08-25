"""High-stakes intervention graph: supervisor then independent verifier.

Cheap deterministic triage stays outside this graph. When a worker claims
completion or drift/stagnation is high, the verifier can reject a weak NOOP
and force a continue/verify action. The typed action still comes from
supervisor tools, not from discarded graph text.
"""

from __future__ import annotations

import time
from uuid import uuid4

from pex_protocol.actions import InterventionType
from pex_protocol.supervisor import SupervisorRequest, SupervisorResult

from pex_supervisor.planner import plan_deterministic
from pex_supervisor.providers import describe_backend

VERIFIER_PROMPT = """You are PEX's independent verifier.
You do not trust the worker's narrative.
Given the goal, observable scores, and proposed action, reply with:
VERIFY or REJECT and one sentence.
Reject if the worker's completion claim is unsupported, or if the proposed
action is NOOP while tests have not been evidenced.
"""


def should_use_graph(request: SupervisorRequest) -> bool:
    scores = request.scores
    return (
        scores.premature_completion >= 0.7
        or scores.claim_contradiction >= 0.7
        or scores.drift >= 0.85
    )


def run_intervention_graph(request: SupervisorRequest, model=None) -> SupervisorResult:
    """Strands Graph path: supervisor tools, then verifier can override a weak NOOP."""
    from pex_supervisor.loop import (
        _action_from_proposal,
        _format_user,
        _system_prompt,
        _usage,
    )
    from pex_supervisor.tools import SUPERVISOR_TOOLS, bind_request, reset_request, take_proposed

    try:
        from strands import Agent
        from strands.multiagent import GraphBuilder
    except Exception as exc:
        return _fail_closed(request, f"graph_unavailable:{exc}", used_llm=False)

    token = bind_request(request)
    traces: list[str] = []
    request_id = str(uuid4())
    started = time.perf_counter()
    backend = describe_backend()
    try:
        kwargs = {"system_prompt": _system_prompt(), "tools": SUPERVISOR_TOOLS}
        vkwargs = {"system_prompt": VERIFIER_PROMPT}
        if model is not None:
            kwargs["model"] = model
            vkwargs["model"] = model
        supervisor = Agent(**kwargs)
        verifier = Agent(**vkwargs)
        builder = GraphBuilder()
        builder.add_node(supervisor, "supervisor")
        builder.add_node(verifier, "verifier")
        builder.add_edge("supervisor", "verifier")
        builder.set_entry_point("supervisor")
        builder.set_max_node_executions(4)
        graph = builder.build()
        result = graph(_format_user(request))
        traces.append(str(result))
        proposal = take_proposed()
        if proposal:
            action = _action_from_proposal(request, proposal)
            diagnosis = "strands_graph_supervisor"
        else:
            action = plan_deterministic(request)
            traces.append("graph supervisor produced no typed action; using deterministic planner")
            diagnosis = "strands_graph_no_tool_fallback_deterministic"
        verdict, verifier_text = _verifier_verdict(result)
        traces.append(f"verifier:{verifier_text}")
        if verdict == "REJECT" and action.type in {
            InterventionType.NOOP,
            InterventionType.NOTIFY,
            InterventionType.ANNOTATE,
        }:
            action = plan_deterministic(request)
            if action.type == InterventionType.NOOP:
                action = _force_continue(request)
            diagnosis = "strands_graph_verifier_rejected"
        elif verdict == "VERIFY":
            diagnosis = f"{diagnosis}_verified"
        input_tokens, output_tokens = _usage(result)
        return SupervisorResult(
            action=action,
            used_llm=True,
            model_name=backend.get("model_id")
            or (type(model).__name__ if model is not None else "strands-graph"),
            diagnosis=diagnosis,
            traces=traces,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
            inference_request_id=request_id,
            backend=backend.get("backend"),
        )
    except Exception as exc:
        traces.append(f"graph_failed:{exc}")
        fallback = _fail_closed(request, f"graph_failed:{exc}", used_llm=True)
        fallback.traces = traces
        return fallback
    finally:
        reset_request(token)


def _force_continue(request: SupervisorRequest):
    from pex_supervisor.planner import plan_deterministic as _plan

    action = _plan(request)
    if action.type != InterventionType.NOOP:
        return action
    from pex_protocol.actions import ProposedAction, RiskLevel
    from pex_protocol.enums import Authority

    return ProposedAction(
        type=InterventionType.CONTINUE_SESSION,
        session_id=request.session.id,
        goal_id=request.goal.id if request.goal else None,
        payload={
            "text": (
                "PEX: independent verification rejected an unsupported completion claim. "
                "Continue until the persistent goal is evidenced."
            )
        },
        rationale="Verifier rejected a weak or missing intervention on a high-stakes stop.",
        evidence=["graph_verifier_REJECT"],
        confidence=0.8,
        risk=RiskLevel.LOW,
        reversible=True,
        cooldown_seconds=60,
        authority_required=Authority.LOCAL_POLICY,
        requires_capability="send_message",
    )


def _verifier_verdict(result: object) -> tuple[str, str]:
    status = getattr(getattr(result, "status", None), "value", None)
    failed_nodes = int(getattr(result, "failed_nodes", 0) or 0)
    results = getattr(result, "results", None)
    if status != "completed" or failed_nodes or not isinstance(results, dict):
        return "REJECT", f"graph status={status!r}, failed_nodes={failed_nodes}"
    node = results.get("verifier")
    node_status = getattr(getattr(node, "status", None), "value", None)
    if node is None or node_status != "completed":
        return "REJECT", f"verifier status={node_status!r}"
    text = str(node).strip()
    first = text.split(maxsplit=1)[0].upper().rstrip(":") if text else ""
    if first == "VERIFY":
        return "VERIFY", text
    if first == "REJECT":
        return "REJECT", text
    return "REJECT", f"malformed verifier response: {text[:240]}"


def _fail_closed(
    request: SupervisorRequest, diagnosis: str, *, used_llm: bool
) -> SupervisorResult:
    backend = describe_backend()
    action = plan_deterministic(request)
    if action.type == InterventionType.NOOP:
        action = _force_continue(request)
    return SupervisorResult(
        action=action,
        used_llm=used_llm,
        model_name=backend.get("model_id") if used_llm else None,
        diagnosis=diagnosis,
        traces=[diagnosis],
        inference_request_id=str(uuid4()) if used_llm else None,
        backend=backend.get("backend"),
    )
