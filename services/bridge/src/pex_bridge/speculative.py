"""Build spec §23: cheap two-approach probes, never uncontrolled spawning."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pex_protocol.enums import DecisionStatus

PROBE_BUDGET_TOOL_CALLS = 8
CHEAP_APPROACH_MAX_CHARS = 400
_STATUS_SCORE = {
    "supported": 4,
    "uncertain": 1,
    "acceptance_gap": 0,
    "contradicted": -2,
}


def cheap_competing_approaches(decisions: Sequence[Any]) -> list[str]:
    """Return two short unresolved questions, or nothing.

    A long architecture debate is not a cheap probe. Duplicate wording is one
    approach, not two.
    """

    seen: set[str] = set()
    approaches: list[str] = []
    for row in decisions:
        metadata = getattr(row, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        if str(metadata.get("kind") or "") != "unresolved_question":
            continue
        status = getattr(row, "status", None)
        status_value = status.value if isinstance(status, DecisionStatus) else str(status or "")
        if status_value == DecisionStatus.SUPERSEDED.value:
            continue
        statement = str(getattr(row, "statement", "") or "").strip()
        if not statement or len(statement) > CHEAP_APPROACH_MAX_CHARS:
            continue
        key = statement.casefold()
        if key in seen:
            continue
        seen.add(key)
        approaches.append(statement)
        if len(approaches) == 2:
            return approaches
    return []


def probe_instructions(approach: str, *, budget: int = PROBE_BUDGET_TOOL_CALLS) -> str:
    cleaned = " ".join(approach.split())[:CHEAP_APPROACH_MAX_CHARS]
    return (
        f"Isolated speculative probe. Try only this approach: {cleaned}. "
        f"Budget: at most {budget} tool calls. Stop after the first pytest "
        "result or a clear failure. Do not expand scope, start extra workers, "
        "or mutate unrelated files."
    )


def speculative_pair(session: Any) -> dict[str, Any] | None:
    raw = (getattr(session, "metadata", None) or {}).get("speculative")
    if not isinstance(raw, dict):
        return None
    pair_id = str(raw.get("pair_id") or "").strip()
    sibling = str(raw.get("sibling_session_id") or "").strip()
    if not pair_id or not sibling:
        return None
    return raw


def probe_already_running(
    sessions: Sequence[Any],
    *,
    goal_id: str,
    current_session_id: str,
) -> bool:
    for row in sessions:
        if getattr(row, "id", None) == current_session_id:
            continue
        if getattr(row, "goal_id", None) != goal_id:
            continue
        metadata = getattr(row, "metadata", None) or {}
        if metadata.get("probe") is True or speculative_pair(row) is not None:
            return True
    return False


def probe_result_from_stop(
    session: Any,
    verification: dict[str, Any] | None,
    recent: Sequence[Any],
) -> dict[str, Any]:
    pytest_ok: bool | None = None
    for event in reversed(list(recent)):
        state = getattr(event, "process_state", None) or {}
        info = state.get("pytest") if isinstance(state, dict) else None
        if isinstance(info, dict) and "ok" in info:
            pytest_ok = bool(info.get("ok"))
            break
    pair = speculative_pair(session) or {}
    return {
        "session_id": getattr(session, "id", ""),
        "status": str((verification or {}).get("status") or "uncertain"),
        "pytest_ok": pytest_ok,
        "approach": str(pair.get("approach") or ""),
        "role": str(pair.get("role") or ""),
    }


def _result_score(result: dict[str, Any]) -> int:
    score = _STATUS_SCORE.get(str(result.get("status") or "uncertain"), 1)
    pytest_ok = result.get("pytest_ok")
    if pytest_ok is True:
        score += 2
    elif pytest_ok is False:
        score -= 2
    return score


def compare_probe_results(
    *,
    parent: dict[str, Any],
    child: dict[str, Any],
) -> dict[str, Any]:
    """Pick a winner from observed probe evidence only. Ties stay ties."""

    parent_score = _result_score(parent)
    child_score = _result_score(child)
    reasons = [
        (
            f"Approach A ({parent.get('approach') or 'parent'}): "
            f"{parent.get('status')}, pytest={parent.get('pytest_ok')}"
        ),
        (
            f"Approach B ({child.get('approach') or 'child'}): "
            f"{child.get('status')}, pytest={child.get('pytest_ok')}"
        ),
    ]
    if parent_score == child_score:
        return {
            "winner": "tie",
            "winner_session_id": None,
            "loser_session_id": None,
            "winner_approach": str(parent.get("approach") or ""),
            "loser_approach": str(child.get("approach") or ""),
            "reasons": reasons,
        }
    if child_score > parent_score:
        winner, loser = child, parent
        winner_role = "b"
    else:
        winner, loser = parent, child
        winner_role = "a"
    return {
        "winner": winner_role,
        "winner_session_id": str(winner.get("session_id") or ""),
        "loser_session_id": str(loser.get("session_id") or ""),
        "winner_approach": str(winner.get("approach") or ""),
        "loser_approach": str(loser.get("approach") or ""),
        "reasons": reasons,
    }
