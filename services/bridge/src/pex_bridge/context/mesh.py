from __future__ import annotations

from datetime import datetime, timezone

from pex_protocol.context import ContextBundle, ContextItem, ContextKind
from pex_protocol.enums import Sensitivity, SourceKind
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.store import new_id


def score_item(item: ContextItem, goal: Goal, target: HarnessSession) -> float:
    text = f"{item.content} {' '.join(item.relevance_tags)}".lower()
    goal_bits = " ".join(
        [goal.objective, *goal.acceptance_criteria, *goal.constraints]
    ).lower()
    overlap = len(set(text.split()) & set(goal_bits.split()))
    score = overlap / max(len(set(goal_bits.split())), 1)
    if item.kind in {ContextKind.DECISION, ContextKind.CONSTRAINT}:
        score += 0.35
    if item.kind == ContextKind.ARTIFACT:
        score += 0.15
    if item.sensitivity == Sensitivity.SECRET:
        score -= 1.0
    if target.project_id and item.project_id != target.project_id:
        score -= 0.5
    return score


def build_bundle(
    goal: Goal,
    target: HarnessSession,
    items: list[ContextItem],
    recent: list[HarnessEvent],
    source_session_ids: list[str],
    token_budget: int = 12000,
) -> ContextBundle:
    ranked = sorted(items, key=lambda item: score_item(item, goal, target), reverse=True)
    selected: list[ContextItem] = []
    tokens = 0
    for item in ranked:
        cost = max(8, len(item.content) // 4)
        if tokens + cost > token_budget:
            break
        if item.sensitivity in {Sensitivity.SECRET, Sensitivity.LOCAL_ONLY}:
            continue
        selected.append(item)
        tokens += cost
    progress = [
        (e.message_delta or e.command or e.event_type.value)
        for e in recent[-8:]
        if e.message_delta or e.command
    ]
    return ContextBundle(
        goal_id=goal.id,
        target_session_id=target.id,
        source_session_ids=source_session_ids,
        goal_summary=goal.objective,
        acceptance_criteria=list(goal.acceptance_criteria),
        critical_decisions=[i.content for i in selected if i.kind == ContextKind.DECISION][:8],
        relevant_artifacts=[i.content for i in selected if i.kind == ContextKind.ARTIFACT][:8],
        direct_evidence=[i.content for i in selected if i.kind == ContextKind.RESULT][:8],
        recent_progress=progress,
        next_objective="Continue the attached goal using the facts below. Do not redo completed investigations.",
        do_not_redo=[i.content for i in selected if "already" in i.content.lower()][:8],
        items=selected,
        token_estimate=tokens,
        created_at=datetime.now(timezone.utc),
    )


def item_from_event(project_id: str, goal_id: str | None, event: HarnessEvent) -> ContextItem | None:
    content = event.message_delta or event.command
    if not content:
        return None
    kind = ContextKind.FACT
    if event.event_type.value in {"file_edit", "tool_result"}:
        kind = ContextKind.ARTIFACT
    return ContextItem(
        id=new_id("ctx_"),
        project_id=project_id,
        goal_id=goal_id,
        kind=kind,
        content=content[:4000],
        source_refs=[event.event_id],
        provenance=SourceKind.HARNESS,
        confidence=0.4,
        relevance_tags=[event.event_type.value],
        valid_from=event.ts,
        sensitivity=Sensitivity.INTERNAL,
    )
