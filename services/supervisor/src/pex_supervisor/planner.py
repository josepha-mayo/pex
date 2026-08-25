from __future__ import annotations

from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, EventPhase, EventType
from pex_protocol.supervisor import SupervisorRequest


def _nudge(request: SupervisorRequest, rationale: str, evidence: list[str], message: str) -> ProposedAction:
    return ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=request.session.id,
        goal_id=request.goal.id if request.goal else None,
        payload={"text": message},
        rationale=rationale,
        evidence=evidence,
        confidence=0.86,
        risk=RiskLevel.LOW,
        reversible=True,
        expected_benefit="Redirect the worker toward evidenced progress without interrupting the human.",
        cooldown_seconds=45,
        requires_capability="send_message",
    )


def plan_deterministic(request: SupervisorRequest) -> ProposedAction:
    event = request.event
    scores = request.scores
    goal = request.goal
    criteria = list(goal.acceptance_criteria) if goal else []
    evidence_needed = list(goal.evidence_requirements) if goal else []

    if event.event_type == EventType.USER_PROMPT and request.notes.startswith("possible_contradiction"):
        return ProposedAction(
            type=InterventionType.ASK_HUMAN,
            session_id=request.session.id,
            goal_id=goal.id if goal else None,
            payload={
                "prompt": event.message_delta,
                "question": "This prompt conflicts with a persistent constraint. Confirm override or keep the ledger.",
            },
            rationale="Human prompt appears to contradict the persistent intent ledger.",
            evidence=[request.notes, event.message_delta or ""],
            confidence=0.8,
            risk=RiskLevel.MEDIUM,
            reversible=True,
            authority_required=Authority.HUMAN,
            requires_capability="inject_context",
        )

    command = event.command or (event.tool_input or {}).get("command")
    if command and any(token in str(command).lower() for token in ("eval_runner", "evaluate.py", "run_eval")):
        blob = " ".join([goal.objective if goal else "", *criteria, *evidence_needed]).lower()
        if "dataset" in blob:
            return _nudge(
                request,
                "Worker started evaluation before the required dataset artifact exists.",
                [str(command)],
                "PEX: do not start the expensive evaluator yet. Generate/verify the dataset artifact first, then run eval.",
            )

    if event.event_type in {EventType.PERMISSION_REQUEST, EventType.SHELL} and event.phase == EventPhase.BEFORE:
        return ProposedAction(
            type=InterventionType.RESPOND_PERMISSION,
            session_id=request.session.id,
            goal_id=goal.id if goal else None,
            payload={
                "request_id": (event.approval_request or {}).get("request_id") or event.event_id,
                "command": command,
                "decision": "allow",
            },
            rationale="Permission request intercepted for local policy evaluation.",
            evidence=[command or "unspecified command"],
            confidence=0.9,
            risk=RiskLevel.LOW,
            reversible=True,
            requires_capability="approve",
        )

    if scores.premature_completion >= 0.7 or (
        event.event_type == EventType.STOP and criteria and scores.features.get("tests_run", 0) == 0
    ):
        missing = criteria + evidence_needed
        message = (
            "PEX: you stopped before the persistent goal is evidenced. "
            "Do not claim completion yet. Missing:\n"
            + "\n".join(f"- {item}" for item in missing[:12])
        )
        return ProposedAction(
            type=InterventionType.CONTINUE_SESSION,
            session_id=request.session.id,
            goal_id=goal.id if goal else None,
            payload={"text": message},
            rationale="Worker stopped or claimed done without required evidence.",
            evidence=[f"premature_completion={scores.premature_completion}"] + missing[:6],
            confidence=0.9,
            risk=RiskLevel.LOW,
            reversible=True,
            expected_benefit="Prevent a false-done outcome without asking the human to type continue.",
            cooldown_seconds=60,
            requires_capability="send_message",
        )

    if scores.claim_contradiction >= 0.7:
        return _nudge(
            request,
            "A completion claim is not supported by observable evidence.",
            [f"claims={scores.features.get('success_claims')}", f"tests_run={scores.features.get('tests_run')}"],
            "PEX: a completion claim is contradicted by current state (no matching test/artifact evidence). "
            "Verify with the required command and report the actual output.",
        )

    if scores.stagnation >= 0.7:
        return _nudge(
            request,
            "Trajectory is repeating low-information actions.",
            [str(scores.features)],
            "PEX: you are repeating the same failing action. Change diagnosis before retrying. "
            "Inspect the unchanged config/input that caused the last identical error.",
        )

    if scores.drift >= 0.7 and goal:
        return _nudge(
            request,
            "Recent actions drifted from the persistent objective.",
            [goal.objective],
            f"PEX: return to the persistent goal: {goal.objective}. "
            f"Acceptance criteria: {'; '.join(criteria[:6])}",
        )

    return ProposedAction(
        type=InterventionType.NOOP,
        session_id=request.session.id,
        goal_id=goal.id if goal else None,
        payload={},
        rationale="No deterministic intervention is warranted.",
        evidence=[],
        confidence=0.7,
        risk=RiskLevel.NONE,
        reversible=True,
        cooldown_seconds=5,
    )
