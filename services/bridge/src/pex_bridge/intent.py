from __future__ import annotations

from enum import StrEnum

from pex_protocol.goal import Goal


class PromptClass(StrEnum):
    CONSISTENT = "consistent"
    REFINEMENT = "likely_refinement"
    CONTRADICTION = "possible_contradiction"
    OVERRIDE = "explicit_override"
    AMBIGUOUS = "dangerous_ambiguity"


_OVERRIDE_MARKERS = ("actually", "ignore previous", "override", "new goal", "instead,")


def classify_prompt(goal: Goal | None, prompt: str) -> PromptClass:
    if not goal or not prompt.strip():
        return PromptClass.CONSISTENT
    text = prompt.lower()
    if any(marker in text for marker in _OVERRIDE_MARKERS):
        return PromptClass.OVERRIDE

    contradictions = 0
    for constraint in goal.constraints + goal.forbidden_outcomes + goal.non_goals:
        lowered = constraint.lower()
        negated = None
        if lowered.startswith("do not ") or lowered.startswith("don't "):
            negated = lowered.split(" ", 2)[-1]
        elif "without" in lowered:
            negated = lowered.split("without", 1)[-1].strip()
        if negated:
            tokens = [t for t in negated.replace(".", " ").split() if len(t) > 3]
            if tokens and all(token in text for token in tokens[:3]):
                contradictions += 1
    if contradictions:
        return PromptClass.CONTRADICTION
    if any(word in text for word in ("maybe", "whatever", "just quickly", "hack")):
        return PromptClass.AMBIGUOUS
    return PromptClass.CONSISTENT
