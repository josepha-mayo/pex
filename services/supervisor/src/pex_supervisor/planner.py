from __future__ import annotations

from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, EventPhase, EventType
from pex_protocol.supervisor import SupervisorRequest


def _noop(request: SupervisorRequest, rationale: str, evidence: list[str] | None = None) -> ProposedAction:
    return ProposedAction(
        type=InterventionType.NOOP,
        session_id=request.session.id,
        goal_id=request.goal.id if request.goal else None,
        payload={},
        rationale=rationale,
        evidence=evidence or [],
        confidence=0.7,
        risk=RiskLevel.NONE,
        reversible=True,
        cooldown_seconds=5,
    )


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
    """Cheap facts only. Stop/completion copy is never canned worker text.

    A stop event is a trigger to inspect (via the supervisor model), not to nag.
    """
    event = request.event
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
        )

    command = event.command or (event.tool_input or {}).get("command")
    if command and any(token in str(command).lower() for token in ("eval_runner", "evaluate.py", "run_eval")):
        blob = " ".join([goal.objective if goal else "", *criteria, *evidence_needed]).lower()
        if "dataset" in blob:
            return _nudge(
                request,
                "Worker started evaluation before the required dataset artifact exists.",
                [str(command)],
                "The evaluator started before a dataset artifact exists. Generate or verify the dataset file first, then rerun eval.",
            )

    if event.event_type in {
        EventType.PERMISSION_REQUEST,
        EventType.SHELL,
        EventType.TOOL_CALL,
    } and event.phase == EventPhase.BEFORE:
        return ProposedAction(
            type=InterventionType.RESPOND_PERMISSION,
            session_id=request.session.id,
            goal_id=goal.id if goal else None,
            payload={
                "request_id": (event.approval_request or {}).get("request_id") or event.event_id,
                "command": command,
            },
            rationale="Routine permission brokered by local policy.",
            evidence=[str(command or event.tool_name or "")],
            confidence=0.7,
            risk=RiskLevel.LOW,
            reversible=True,
        )

    if (
        event.event_type not in {EventType.STOP, EventType.USER_PROMPT}
        and request.scores.drift >= 0.75
        and int(request.scores.features.get("repeated_command_count") or 0) >= 3
    ):
        return _nudge(
            request,
            "Trajectory is repeating low-information work instead of attached acceptance criteria.",
            [
                f"drift={request.scores.drift}",
                f"repeated_command_count={request.scores.features.get('repeated_command_count')}",
            ],
            "Recent actions repeated without moving the attached acceptance criteria. Return to the remaining criterion and produce the required evidence.",
        )

    return _noop(
        request,
        "No deterministic fact requires interruption. Stop/completion needs supervisor inference or silence.",
        [event.event_type.value],
    )
