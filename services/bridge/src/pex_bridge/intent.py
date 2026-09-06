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


_OVERRIDE_SPEECH_ACT = re.compile(
    r"^\s*(?:"
    r"(?:please\s+)?(?:intentionally\s+)?override\b"
    r"|i\s+(?:want|intend|choose)\s+to\s+(?:intentionally\s+)?override\b"
    r"|change\s+of\s+plan\s*[:;,.-]"
    r"|(?:please\s+)?ignore\s+(?:the\s+)?(?:previous|active|existing)\b"
    r")",
)
_NEGATED_ACTION = re.compile(
    r"(?:\bdo\s+not|\bdon['’]t|\bnever|\bwithout)\s+"
    r"(?:(?:ever|intentionally|accidentally|really)\s+)?$"
)
_NEGATED_LIST = re.compile(
    r"(?:\bdo\s+not|\bdon['’]t|\bnever|\bwithout)\s+"
    r"(?P<items>[^.!?;]{0,512})(?:,\s*(?:(?:and|or|nor)\s+)?|\b(?:or|nor)\s+)$"
)
_AFFIRMATIVE_BOUNDARY = re.compile(r"\b(?:but|however|instead|then|yet|nevertheless)\b")
_WORD = re.compile(r"[a-z0-9]+(?:[_.-][a-z0-9]+)*")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.-]{3,}")
_LEDGER_OBJECTS = {
    "constraint",
    "constraints",
    "decision",
    "decisions",
    "restriction",
    "restrictions",
    "rule",
    "rules",
}
_META_OR_CONDITIONAL = {
    "could",
    "conditional",
    "describe",
    "described",
    "describing",
    "docs",
    "document",
    "documented",
    "documenting",
    "documentation",
    "example",
    "examples",
    "explain",
    "explained",
    "explaining",
    "hypothetical",
    "if",
    "mention",
    "mentioned",
    "mentioning",
    "might",
    "quote",
    "quoted",
    "quoting",
    "readme",
    "say",
    "should",
    "test",
    "testing",
    "tests",
    "unless",
    "would",
    "when",
}


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
    matched = _matching_constraints(goal, text) + _matching_decisions(decisions or (), text)
    override_scope = _override_authority_scope(text)
    if override_scope is not None:
        override_targets = _matching_constraints(goal, override_scope) + _matching_decisions(
            decisions or (), override_scope
        )
        if override_targets:
            return PromptLint(PromptClass.OVERRIDE, matched_constraints=override_targets)
    if matched:
        return PromptLint(PromptClass.CONTRADICTION, matched_constraints=matched)
    if _dangerously_ambiguous(text):
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
        if lowered.startswith("do not "):
            negated = lowered.removeprefix("do not ")
        elif lowered.startswith(("don't ", "don’t ")):
            negated = lowered[6:]
        elif "without" in lowered:
            negated = lowered.split("without", 1)[-1].strip()
        if not negated:
            continue
        tokens = [token for token in _WORD.findall(negated) if len(token) > 3]
        if _matches_forbidden_terms(text, tokens[:3]):
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
            tokens = [token for token in _WORD.findall(haystack.lower()) if len(token) > 3]
            if _matches_forbidden_terms(text, tokens[:4]):
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


def _matches_forbidden_terms(text: str, terms: list[str]) -> bool:
    """Find a forbidden action mention that is not a simple negated restatement."""

    occurrences = list(_WORD.finditer(text))
    words = {occurrence.group() for occurrence in occurrences}
    if not terms or any(term not in words for term in terms):
        return False
    for occurrence in occurrences:
        if occurrence.group() != terms[0]:
            continue
        # The verb and object must occur in the same local clause. A request to
        # create a report is not evidence of creating a git commit mentioned in
        # a later prohibition. Keep sentence and contrast boundaries intact.
        clause = re.split(
            r"[.!?;](?:\s|$)|\b(?:but|however|instead|nevertheless)\b",
            text[occurrence.start() : occurrence.start() + 560], maxsplit=1,
        )[0]
        clause_words = _WORD.findall(clause)
        cursor = 0
        for term in terms:
            try:
                cursor = clause_words.index(term, cursor) + 1
            except ValueError:
                break
        else:
            cursor = -1
        if cursor != -1:
            continue
        prefix = text[max(0, occurrence.start() - 560) : occurrence.start()]
        negated_list = _NEGATED_LIST.search(prefix)
        list_restatement = negated_list is not None and not _AFFIRMATIVE_BOUNDARY.search(
            negated_list.group("items")
        )
        if not _NEGATED_ACTION.search(prefix) and not list_restatement:
            return True
    return False


def _dangerously_ambiguous(text: str) -> bool:
    """Require an unquoted shortcut plus speed/vagueness; ordinary hedging is safe."""

    words = set(_WORD.findall(_without_quoted_or_code(text)))
    return "hack" in words and bool(words & {"maybe", "whatever", "quick", "quickly"})


def _override_authority_scope(text: str) -> str | None:
    """Return only the direct, unquoted opening directive that may carry authority."""

    speech_act = _OVERRIDE_SPEECH_ACT.match(text)
    if speech_act is None:
        return None
    unquoted = _without_quoted_or_code(text)
    boundary = re.search(r"[.!?;\r\n]", unquoted)
    scope = unquoted[: boundary.start() if boundary else len(unquoted)]
    words = set(_WORD.findall(scope))
    direct_target = _WORD.findall(scope[speech_act.end() :])[:8]
    if not set(direct_target) & _LEDGER_OBJECTS or words & _META_OR_CONDITIONAL:
        return None
    return scope


def _without_quoted_or_code(text: str) -> str:
    """Blank quoted, inline-code, and fenced-code spans, including unclosed spans."""

    result = list(text)
    index = 0
    mode: str | None = None
    closing = ""
    while index < len(text):
        if mode == "fence":
            if text.startswith("```", index):
                result[index : index + 3] = "   "
                index += 3
                mode = None
            else:
                result[index] = " "
                index += 1
            continue
        if mode is not None:
            result[index] = " "
            if text[index] == closing and (index == 0 or text[index - 1] != "\\"):
                mode = None
            index += 1
            continue
        if text.startswith("```", index):
            result[index : index + 3] = "   "
            index += 3
            mode = "fence"
            continue
        character = text[index]
        if character == "`":
            result[index] = " "
            mode, closing = "inline", "`"
        elif character in {'"', "“", "‘"}:
            result[index] = " "
            mode = "quote"
            closing = {'"': '"', "“": "”", "‘": "’"}[character]
        elif character == "'" and not (
            index > 0
            and index + 1 < len(text)
            and text[index - 1].isalnum()
            and text[index + 1].isalnum()
        ):
            result[index] = " "
            mode, closing = "quote", "'"
        index += 1
    return "".join(result)
