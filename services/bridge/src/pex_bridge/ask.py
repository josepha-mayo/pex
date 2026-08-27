from __future__ import annotations

from pex_protocol.enums import SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessSession

_REVIEW_SYSTEM = (
    "You are PEX, a goal-aware supervisor that reviews coding agents. "
    "Answer the human from the canonical session and intervention state. "
    "Do not tell them to prompt Cursor, Codex, or any other worker. "
    "Do not invent sessions, files, or actions. "
    "Use the Counts line as the only session totals; never inflate them. "
    "If the grounded fallback already answers, you may restate it more clearly. "
    "Never prefix with PEX:."
)


def answer_question(
    question: str,
    sessions: list[HarnessSession],
    interventions: list[Intervention],
    goals: list[Goal] | None = None,
    model=None,
) -> str:
    """Answer from canonical PEX state. Never interrupts a worker to fetch an answer."""
    grounded = _keyword_answer(question, sessions, interventions, goals or [])
    if model is None:
        return grounded
    try:
        from pex_supervisor.inspect_http import complete_review_answer

        answer, _, _ = complete_review_answer(
            _REVIEW_SYSTEM,
            _review_user(question, sessions, interventions, goals or [], grounded),
        )
        if answer:
            return answer
    except Exception:
        pass
    return grounded


def _review_user(
    question: str,
    sessions: list[HarnessSession],
    interventions: list[Intervention],
    goals: list[Goal],
    grounded: str,
) -> str:
    needs = [s for s in sessions if s.status == SessionStatus.NEEDS_DECISION]
    working = [s for s in sessions if s.status.value in {"working", "verifying"}]
    lines = [
        f"Human asked: {question.strip()[:400]}",
        f"Counts: total={len(sessions)} working={len(working)} needs_you={len(needs)}",
        "Sessions:",
    ]
    for session in sessions[:12]:
        goal = session.goal_id or "unattached"
        lines.append(
            f"- {session.harness_type}:{session.vendor_session_id} "
            f"status={session.status} goal={goal} paused={session.supervision_paused}"
        )
    if interventions:
        last = interventions[0]
        lines.append(
            f"Last PEX action: {last.action_taken} result={last.result} "
            f"diagnosis={last.diagnosis} evidence={list(last.evidence[:4])}"
        )
    else:
        lines.append("Last PEX action: none")
    if goals:
        goal = goals[0]
        lines.append(f"Goal: {goal.title} — {goal.objective}")
    lines.append(f"Grounded fallback: {grounded}")
    return "\n".join(lines)


def _keyword_answer(
    question: str,
    sessions: list[HarnessSession],
    interventions: list[Intervention],
    goals: list[Goal],
) -> str:
    q = question.lower().strip()
    needs = [s for s in sessions if s.status == SessionStatus.NEEDS_DECISION]
    working = [s for s in sessions if s.status.value in {"working", "verifying"}]
    last = interventions[0] if interventions else None
    paused = [s for s in sessions if s.supervision_paused]

    if "need me" in q or "needs me" in q or q in {"?", "what needs me?"}:
        if needs:
            s = needs[0]
            return (
                f"{s.harness_type} session {s.vendor_session_id} needs a decision. "
                "PEX did not auto-approve because the action is consequential."
            )
        if last and last.policy_verdict.value != "allow" and last.action_taken != "NOOP":
            return (
                f"Last intervention: {last.action_taken} ({last.result}). Nothing else needs you."
            )
        if working:
            return f"{len(working)} agent(s) working. Nothing needs you."
        return "Nothing needs you. PEX is observing."

    if "why" in q and last:
        evidence = "; ".join(last.evidence[:4]) or "n/a"
        return (
            f"PEX {last.action_taken} on {last.session_id} because {last.diagnosis}. "
            f"Evidence: {evidence}. Result: {last.result}."
        )

    if "paused" in q or "quiet" in q:
        if not paused:
            return "Supervision is active on all sessions."
        return "Paused: " + ", ".join(f"{s.harness_type}:{s.vendor_session_id}" for s in paused)

    if "goal" in q and goals:
        g = goals[0]
        return f"Persistent goal: {g.title} — {g.objective}"

    if "blocked" in q:
        blocked = [s for s in sessions if s.status.value in {"blocked", "needs_decision", "error"}]
        if not blocked:
            return "No blocked agents."
        return "Blocked: " + ", ".join(f"{s.harness_type}:{s.vendor_session_id}" for s in blocked)

    if last:
        return (
            f"{len(sessions)} sessions. Latest PEX action: {last.action_taken} ({last.diagnosis})."
        )
    return f"{len(sessions)} sessions. No interventions yet."
