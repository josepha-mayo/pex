from __future__ import annotations

from datetime import UTC, datetime
from unicodedata import category

from pex_protocol.context import ContextItem
from pex_protocol.enums import ContextKind, DecisionStatus, Sensitivity, SourceKind
from pex_protocol.goal import Decision
from pex_protocol.redaction import redact_text
from pex_protocol.session import HarnessSession
from pex_protocol.supervisor import (
    SupervisorContextEnvelope,
    SupervisorContextItem,
    SupervisorDecisionItem,
)

_MAX_CONTEXT_TEXT = 28_000
_MAX_DECISION_TEXT = 18_000
_ALLOWED_SENSITIVITY = {Sensitivity.PUBLIC, Sensitivity.INTERNAL}
_KIND_PRIORITY = {
    ContextKind.CONSTRAINT: 9,
    ContextKind.DECISION: 8,
    ContextKind.RESULT: 7,
    ContextKind.WARNING: 6,
    ContextKind.FACT: 5,
    ContextKind.ARTIFACT: 4,
    ContextKind.CLAIM: 3,
    ContextKind.HYPOTHESIS: 2,
}
_STRONG_PROVENANCE = {
    SourceKind.HUMAN,
    SourceKind.TEST,
    SourceKind.GIT,
    SourceKind.WORKSPACE,
}
_VERIFIABLE_PROVENANCE = {SourceKind.TEST, SourceKind.WORKSPACE}


def _project_key(value: str) -> str:
    return value.strip().replace("\\", "/").rstrip("/").casefold()


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _clean_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    redacted, _ = redact_text(value)
    cleaned = "".join(
        char if not category(char).startswith("C") or char in "\n\t" else " "
        for char in (redacted or "")
    ).strip()
    return cleaned[:limit]


def _clean_label(value: object, limit: int) -> str:
    return " ".join(_clean_text(value, limit).split())[:limit]


def _clean_id(value: object, limit: int = 512) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > limit:
        return None
    if any(category(char).startswith("C") for char in value):
        return None
    redacted, hits = redact_text(value)
    if hits or redacted != value:
        return None
    return value


def _unique_ids(values: object, *, limit: int = 16) -> tuple[str, ...]:
    candidates = values if isinstance(values, (list, tuple)) else []
    result: list[str] = []
    for value in candidates:
        cleaned = _clean_id(value)
        if cleaned is not None and cleaned not in result:
            result.append(cleaned)
        if len(result) >= limit:
            break
    return tuple(result)


def _metadata_source_refs(metadata: object) -> tuple[str, ...]:
    if not isinstance(metadata, dict):
        return ()
    values: list[object] = []
    for key in (
        "source_event_id",
        "source_intervention_id",
        "source_context_id",
        "source_decision_id",
    ):
        value = metadata.get(key)
        if value is not None:
            values.append(value)
    source_refs = metadata.get("source_refs")
    if isinstance(source_refs, (list, tuple)):
        values.extend(source_refs)
    return _unique_ids(values)


def _source_session_id(metadata: object) -> str | None:
    return _clean_id(metadata.get("source_session_id")) if isinstance(metadata, dict) else None


def _context_status(item: ContextItem) -> str:
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    if _context_verified(item):
        return "verified"
    return _clean_label(metadata.get("status"), 80) or "active"


def _context_verified(item: ContextItem) -> bool:
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    return metadata.get("verified") is True and item.provenance in _VERIFIABLE_PROVENANCE


def _context_rank(item: ContextItem) -> tuple[int, int, int, float, datetime, str]:
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    status = str(metadata.get("status") or "").casefold()
    return (
        1 if _context_verified(item) else 0,
        1 if item.provenance in _STRONG_PROVENANCE else 0,
        _KIND_PRIORITY.get(item.kind, 0) + (1 if status == "uncertain" else 0),
        item.confidence,
        item.valid_from,
        item.id,
    )


def _decision_rank(decision: Decision) -> tuple[int, int, float, datetime, str]:
    return (
        1 if decision.source.value == "human" else 0,
        1 if decision.status == DecisionStatus.UNCERTAIN else 0,
        decision.confidence,
        decision.created_at,
        decision.id,
    )


def build_supervisor_context(
    session: HarnessSession,
    context_items: list[ContextItem],
    decisions: list[Decision],
    now: datetime | None = None,
) -> SupervisorContextEnvelope:
    """Select bounded durable context for one exact session/project/goal authority.

    The helper accepts Store records, but independently enforces their scope,
    validity, supersession, sensitivity and size before a model can see them.
    It does not infer new authority or claim that any supplied result is verified.
    """

    observed_at = now or datetime.now(UTC)
    if not _aware(observed_at):
        raise ValueError("supervisor context observation time must be timezone-aware")
    project_id = session.project_id
    goal_id = session.goal_id
    if not project_id or not goal_id:
        return SupervisorContextEnvelope(
            target_session_id=session.id,
            project_id=project_id,
            goal_id=goal_id,
            observed_at=observed_at,
            offered_context_ids=(),
            offered_decision_ids=(),
        )

    in_scope: list[ContextItem] = []
    for item in context_items:
        if (
            not isinstance(item, ContextItem)
            or not _aware(item.valid_from)
            or (item.stale_after is not None and not _aware(item.stale_after))
            or _project_key(item.project_id) != _project_key(project_id)
            or item.goal_id not in {None, goal_id}
            or item.valid_from > observed_at
            or (item.stale_after is not None and item.stale_after <= observed_at)
            or _clean_id(item.id) is None
        ):
            continue
        in_scope.append(item)

    # A valid in-scope replacement suppresses its predecessor even when the
    # replacement itself is too sensitive to disclose to the model.
    superseded_ids = {
        superseded
        for item in in_scope
        if (superseded := _clean_id(item.supersedes)) is not None
    }
    selected_context: list[SupervisorContextItem] = []
    selected_context_ids: set[str] = set()
    context_text = 0
    for item in sorted(in_scope, key=_context_rank, reverse=True):
        if (
            item.id in superseded_ids
            or item.id in selected_context_ids
            or item.sensitivity not in _ALLOWED_SENSITIVITY
        ):
            continue
        content = _clean_text(item.content, 2_000)
        if not content or context_text + len(content) > _MAX_CONTEXT_TEXT:
            continue
        metadata = item.metadata if isinstance(item.metadata, dict) else {}
        semantic_kind = _clean_label(metadata.get("kind"), 80) or None
        source_refs = _unique_ids(item.source_refs)
        relevance_tags = tuple(
            value
            for value in (_clean_label(tag, 120) for tag in item.relevance_tags[:16])
            if value
        )
        relevance_tags = tuple(dict.fromkeys(relevance_tags))
        selected_context.append(
            SupervisorContextItem(
                id=item.id,
                project_id=project_id,
                goal_id=item.goal_id,
                kind=item.kind,
                content=content,
                semantic_kind=semantic_kind,
                status=_context_status(item),
                source_refs=source_refs,
                source_session_id=_source_session_id(metadata),
                provenance=item.provenance,
                confidence=item.confidence,
                verified=_context_verified(item),
                relevance_tags=relevance_tags,
                valid_from=item.valid_from,
                stale_after=item.stale_after,
                supersedes=_clean_id(item.supersedes),
                sensitivity=item.sensitivity,
            )
        )
        selected_context_ids.add(item.id)
        context_text += len(content)
        if len(selected_context) >= 32:
            break

    selected_decisions: list[SupervisorDecisionItem] = []
    selected_decision_ids: set[str] = set()
    decision_text = 0
    eligible_decisions = [
        decision
        for decision in decisions
        if isinstance(decision, Decision)
        and decision.goal_id == goal_id
        and decision.sensitivity in _ALLOWED_SENSITIVITY
        and decision.status in {DecisionStatus.ACTIVE, DecisionStatus.UNCERTAIN}
        and _aware(decision.created_at)
        and decision.created_at <= observed_at
        and _clean_id(decision.id) is not None
    ]
    for decision in sorted(eligible_decisions, key=_decision_rank, reverse=True):
        if decision.id in selected_decision_ids:
            continue
        statement = _clean_text(decision.statement, 2_000)
        rationale = _clean_text(decision.rationale, 1_000)
        alternatives = tuple(
            value
            for value in (
                _clean_text(alternative, 1_000)
                for alternative in decision.alternatives_rejected[:12]
            )
            if value
        )
        cost = len(statement) + len(rationale) + sum(len(value) for value in alternatives)
        if not statement or decision_text + cost > _MAX_DECISION_TEXT:
            continue
        metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
        selected_decisions.append(
            SupervisorDecisionItem(
                id=decision.id,
                goal_id=goal_id,
                statement=statement,
                rationale=rationale,
                alternatives_rejected=alternatives,
                scope=_clean_text(decision.scope, 500),
                confidence=decision.confidence,
                source=decision.source,
                status=decision.status,
                created_at=decision.created_at,
                source_refs=_metadata_source_refs(metadata),
                source_session_id=_source_session_id(metadata),
                sensitivity=decision.sensitivity,
            )
        )
        selected_decision_ids.add(decision.id)
        decision_text += cost
        if len(selected_decisions) >= 24:
            break

    return SupervisorContextEnvelope(
        target_session_id=session.id,
        project_id=project_id,
        goal_id=goal_id,
        observed_at=observed_at,
        context_items=tuple(selected_context),
        decisions=tuple(selected_decisions),
        offered_context_ids=tuple(item.id for item in selected_context),
        offered_decision_ids=tuple(item.id for item in selected_decisions),
    )
