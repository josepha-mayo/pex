from __future__ import annotations

from pex_protocol.enums import SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessSession


def answer_question(
    question: str,
    sessions: list[HarnessSession],
    interventions: list[Intervention],
    goals: list[Goal] | None = None,
    model=None,
) -> str:
    """Answer from canonical PEX state. Never interrupts a worker to fetch an answer."""
    del model
    return _keyword_answer(question, sessions, interventions, goals or [])


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
