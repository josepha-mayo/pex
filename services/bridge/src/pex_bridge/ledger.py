"""Persist build-spec §9.2 Decision rows from labeled persistent-intent sections."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from pex_protocol.context import ContextItem
from pex_protocol.enums import ContextKind, DecisionSource, DecisionStatus, Sensitivity, SourceKind
from pex_protocol.goal import Decision, Goal
from pex_supervisor.public_task import LEDGER_DECISION_FIELDS, extracted_ledger_lists

from pex_bridge.store import Store, new_id, utcnow

_KIND_BY_FIELD = {
    "decisions": "decision",
    "rejected_approaches": "rejected_approach",
    "unresolved_questions": "unresolved_question",
}


def ledger_kinds_for_fields(fields: Iterable[str]) -> frozenset[str]:
    """Translate explicit REST ledger fields into their durable Decision kinds."""

    return frozenset(_KIND_BY_FIELD[field] for field in fields if field in _KIND_BY_FIELD)


def merge_ledger_lists(
    objective: str,
    explicit: dict[str, Sequence[str]] | None = None,
    *,
    skip_fields: set[str] | frozenset[str] | None = None,
) -> dict[str, list[str]]:
    skipped = skip_fields or set()
    extracted = extracted_ledger_lists(objective)
    merged: dict[str, list[str]] = {}
    for field in LEDGER_DECISION_FIELDS:
        provided = [
            str(item).strip()
            for item in (explicit or {}).get(field) or []
            if str(item).strip()
        ]
        if field in skipped:
            merged[field] = provided
            continue
        merged[field] = provided or extracted.get(field) or []
    return merged


def decisions_from_lists(goal_id: str, lists: dict[str, list[str]]) -> list[Decision]:
    now = utcnow()
    rows: list[Decision] = []
    for field in LEDGER_DECISION_FIELDS:
        kind = _KIND_BY_FIELD[field]
        status = (
            DecisionStatus.UNCERTAIN
            if kind == "unresolved_question"
            else DecisionStatus.ACTIVE
        )
        for item in lists.get(field) or []:
            statement = item.strip()
            if not statement:
                continue
            rows.append(
                Decision(
                    id=new_id("dec_"),
                    goal_id=goal_id,
                    statement=statement,
                    rationale=(
                        "Unresolved question recorded on the persistent intent ledger."
                        if kind == "unresolved_question"
                        else "Rejected approach recorded on the persistent intent ledger."
                        if kind == "rejected_approach"
                        else "Decision recorded on the persistent intent ledger."
                    ),
                    alternatives_rejected=[statement] if kind == "rejected_approach" else [],
                    source=DecisionSource.HUMAN,
                    status=status,
                    created_at=now,
                    metadata={"kind": kind},
                )
            )
    return rows


def ledger_projections(
    goal: Goal,
    *,
    explicit: dict[str, Sequence[str]] | None = None,
    skip_fields: set[str] | frozenset[str] | None = None,
) -> list[tuple[Decision, ContextItem]]:
    """Build ledger pairs without crossing the Store transaction boundary."""

    decisions = decisions_from_lists(
        goal.id,
        merge_ledger_lists(goal.objective, explicit, skip_fields=skip_fields),
    )
    projections: list[tuple[Decision, ContextItem]] = []
    for decision in decisions:
        kind = str(decision.metadata.get("kind") or "decision")
        projections.append(
            (
                decision,
                ContextItem(
                    id=new_id("ctx_"),
                    project_id=goal.project_id,
                    goal_id=goal.id,
                    kind=ContextKind.DECISION,
                    content=decision.statement,
                    source_refs=[decision.id],
                    provenance=SourceKind.HUMAN,
                    confidence=0.9,
                    relevance_tags=["decision", kind],
                    valid_from=decision.created_at,
                    sensitivity=Sensitivity.INTERNAL,
                    metadata={
                        "decision_id": decision.id,
                        "kind": kind,
                        "status": decision.status.value,
                        "unresolved": kind == "unresolved_question",
                    },
                ),
            )
        )
    return projections


async def persist_extracted_decisions(
    store: Store,
    goal: Goal,
    *,
    explicit: dict[str, Sequence[str]] | None = None,
    skip_fields: set[str] | frozenset[str] | None = None,
) -> list[Decision]:
    """Compatibility wrapper for one atomic ledger-only goal mutation."""

    await store.patch_goal_with_ledger(
        goal,
        goal,
        ledger_projections(
            goal,
            explicit=explicit,
            skip_fields=skip_fields,
        ),
        replace_ledger_kinds=ledger_kinds_for_fields((explicit or {}).keys()),
    )
    return await store.list_decisions_for_authority(goal.id)


def ledger_lists_from_body(data: dict[str, Any]) -> dict[str, list[str]]:
    return {
        field: [str(item) for item in (data.pop(field, None) or []) if str(item).strip()]
        for field in LEDGER_DECISION_FIELDS
    }
