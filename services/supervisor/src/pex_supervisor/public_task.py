"""Parse structured sections from a public TASK.md without task-id branches."""

from __future__ import annotations

import re

from pex_protocol.goal import Goal

_SECTION = re.compile(
    r"^(?P<name>Acceptance criteria|Constraints|Non-goals|Preferences|"
    r"Evidence(?: requirements?)?|"
    r"(?:Current |Important )?Decisions|"
    r"Rejected(?: approaches?)?|"
    r"(?:Unresolved|Open) questions?)\s*:\s*$",
    re.I,
)
_BULLET = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(?P<item>\S.*)$")
_FENCE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
_SECTION_KEYS = {
    "acceptance criteria": "acceptance_criteria",
    "constraints": "constraints",
    "non-goals": "non_goals",
    "preferences": "preferences",
    "evidence": "evidence_requirements",
    "evidence requirement": "evidence_requirements",
    "evidence requirements": "evidence_requirements",
    "decisions": "decisions",
    "current decisions": "decisions",
    "important decisions": "decisions",
    "rejected": "rejected_approaches",
    "rejected approach": "rejected_approaches",
    "rejected approaches": "rejected_approaches",
    "unresolved question": "unresolved_questions",
    "unresolved questions": "unresolved_questions",
    "open question": "unresolved_questions",
    "open questions": "unresolved_questions",
}
MAX_ITEMS = 40
MAX_ITEM_CHARS = 500
MAX_OBJECTIVE_CHARS = 20_000
MAX_TITLE_CHARS = 80
_LIST_FIELDS = (
    "acceptance_criteria",
    "constraints",
    "non_goals",
    "preferences",
    "evidence_requirements",
)
LEDGER_DECISION_FIELDS = (
    "decisions",
    "rejected_approaches",
    "unresolved_questions",
)


def parse_public_task(task_md: str) -> dict[str, str | list[str]]:
    """Keep the full objective and lift only labeled public lists into Goal fields."""
    text = str(task_md or "").replace("\r\n", "\n")
    sections: dict[str, list[str]] = {
        "acceptance_criteria": [],
        "constraints": [],
        "non_goals": [],
        "preferences": [],
        "evidence_requirements": [],
        "decisions": [],
        "rejected_approaches": [],
        "unresolved_questions": [],
    }
    current: str | None = None
    fence_marker: str | None = None
    for line in text.split("\n"):
        fence = _FENCE.match(line)
        if fence_marker is not None:
            if (
                fence
                and fence.group("marker")[0] == fence_marker[0]
                and len(fence.group("marker")) >= len(fence_marker)
                and not fence.group("info").strip()
            ):
                fence_marker = None
            continue
        if fence and not (
            fence.group("marker").startswith("`") and "`" in fence.group("info")
        ):
            # Examples remain in the objective, never promoted into authoritative
            # goal/ledger lists. A fresh explicit section must follow the fence.
            fence_marker = fence.group("marker")
            current = None
            continue
        heading = _SECTION.match(line.strip())
        if heading:
            current = _SECTION_KEYS[heading.group("name").casefold()]
            continue
        bullet = _BULLET.match(line)
        if current and bullet:
            item = bullet.group("item").strip()
            if item and len(sections[current]) < MAX_ITEMS:
                sections[current].append(item[:MAX_ITEM_CHARS])
            continue
        if current and not line.strip():
            continue
        if current and line.strip():
            current = None
    objective = text.strip()[:MAX_OBJECTIVE_CHARS]
    title = next((part.strip() for part in objective.split("\n") if part.strip()), "Task")
    return {
        "title": title[:MAX_TITLE_CHARS],
        "objective": objective,
        **sections,
    }


def fill_empty_goal_lists_from_objective(
    goal: Goal,
    *,
    skip_fields: set[str] | frozenset[str] | None = None,
) -> Goal:
    """Build-spec §14.2: extract labeled lists from the objective when those fields are empty.

    Fields present on an explicit write (including empty lists) stay authoritative.
    """
    skipped = skip_fields or set()
    parsed = parse_public_task(goal.objective)
    updates: dict[str, list[str]] = {}
    for key in _LIST_FIELDS:
        if key in skipped or getattr(goal, key):
            continue
        extracted = [str(item) for item in (parsed.get(key) or []) if str(item).strip()]
        if extracted:
            updates[key] = extracted
    return goal.model_copy(update=updates) if updates else goal


def extracted_ledger_lists(objective: str) -> dict[str, list[str]]:
    """Build-spec §14.2: current decisions, rejected approaches, unresolved questions."""
    parsed = parse_public_task(objective)
    return {
        key: [str(item) for item in (parsed.get(key) or []) if str(item).strip()]
        for key in LEDGER_DECISION_FIELDS
    }
