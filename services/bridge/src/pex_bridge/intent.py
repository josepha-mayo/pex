from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pex_protocol.enums import DecisionStatus
from pex_protocol.goal import Decision, Goal


class PromptClass(StrEnum):
    CONSISTENT = "consistent"
    REFINEMENT = "likely_refinement"
    CONTRADICTION = "possible_contradiction"
    OVERRIDE = "explicit_override"
    AMBIGUOUS = "dangerous_ambiguity"


_OVERRIDE_MARKERS = (
    "ignore previous",
    "override",
    "new goal",
    "instead,",
    "intentionally override",
    "change of plan",
)
_AMBIGUOUS_MARKERS = ("maybe", "whatever", "just quickly", "hack")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.-]{3,}")


@dataclass(frozen=True)
class PromptLint:
    classification: PromptClass
    matched_constraints: tuple[str, ...] = ()
    refinement_terms: tuple[str, ...] = ()


def classify_prompt(
    goal: Goal | None,
    prompt: str,
    decisions: tuple[Decision, ...] | list[Decision] | None = None,
) -> PromptClass:
    return lint_prompt(goal, prompt, decisions=decisions).classification


def lint_prompt(
    goal: Goal | None,
    prompt: str,
    decisions: tuple[Decision, ...] | list[Decision] | None = None,
) -> PromptLint:
    """Build-spec §14.3: compare a user prompt against the persistent ledger."""
    if not goal or not prompt.strip():
        return PromptLint(PromptClass.CONSISTENT)
    text = prompt.lower()
    if any(marker in text for marker in _OVERRIDE_MARKERS):
        return PromptLint(PromptClass.OVERRIDE)

    matched = _matching_constraints(goal, text) + _matching_decisions(decisions or (), text)
    if matched:
        return PromptLint(PromptClass.CONTRADICTION, matched_constraints=matched)
    if any(word in text for word in _AMBIGUOUS_MARKERS):
        return PromptLint(PromptClass.AMBIGUOUS)
    overlap = _refinement_overlap(goal, text)
    if len(overlap) >= 2:
        return PromptLint(PromptClass.REFINEMENT, refinement_terms=overlap)
    return PromptLint(PromptClass.CONSISTENT)


def _matching_constraints(goal: Goal, text: str) -> tuple[str, ...]:
    matched: list[str] = []
    for constraint in goal.constraints + goal.forbidden_outcomes + goal.non_goals:
        lowered = constraint.lower()
        negated = None
        if lowered.startswith("do not ") or lowered.startswith("don't "):
            negated = lowered.split(" ", 2)[-1]
        elif "without" in lowered:
            negated = lowered.split("without", 1)[-1].strip()
        if not negated:
            continue
        tokens = [token for token in negated.replace(".", " ").split() if len(token) > 3]
        if tokens and all(token in text for token in tokens[:3]):
            matched.append(constraint)
    return tuple(matched)


def _matching_decisions(
    decisions: tuple[Decision, ...] | list[Decision],
    text: str,
) -> tuple[str, ...]:
    matched: list[str] = []
    for decision in decisions:
        if decision.status != DecisionStatus.ACTIVE:
            continue
        kind = str(decision.metadata.get("kind") or "decision")
        if kind == "unresolved_question":
            continue
        haystack = " ".join([decision.statement, *decision.alternatives_rejected])
        if kind == "rejected_approach" or decision.alternatives_rejected:
            tokens = [
                token
                for token in haystack.lower().replace(".", " ").split()
                if len(token) > 3
            ]
            if tokens and all(token in text for token in tokens[:4]):
                matched.append(decision.statement)
            continue
        fake = Goal(
            id="lint",
            project_id="lint",
            title="lint",
            objective="",
            constraints=[decision.statement],
            created_at=decision.created_at,
            updated_at=decision.created_at,
        )
        matched.extend(_matching_constraints(fake, text))
    return tuple(matched)


def _refinement_overlap(goal: Goal, text: str) -> tuple[str, ...]:
    ledger = _tokens(
        " ".join(
            [
                goal.objective,
                *goal.acceptance_criteria,
                *goal.evidence_requirements,
            ]
        )
    )
    overlap = sorted(ledger & _tokens(text))
    return tuple(overlap[:8])


def _tokens(value: str) -> set[str]:
    return set(_TOKEN.findall(value.lower()))
