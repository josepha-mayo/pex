from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pex_protocol.context import ContextBundle, ContextItem, ContextKind
from pex_protocol.enums import DecisionStatus, EventType, Sensitivity, SourceKind
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.secrets import redact_text
from pex_bridge.store import new_id

_WORD = re.compile(r"[a-z0-9][a-z0-9._/-]*", re.I)
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
_STRONG_PROVENANCE = {SourceKind.TEST, SourceKind.GIT, SourceKind.WORKSPACE}
_MAX_HANDOFF_TOKENS = 12_000
_MAX_HANDOFF_ITEM_CHARS = 4_000
_MAX_PROGRESS_CHARS = 1_000
_MAX_HANDOFF_CANDIDATES = 256
_MIN_HANDOFF_TOKENS = 256


def _terms(*values: object) -> set[str]:
    words: set[str] = set()
    for value in values:
        if isinstance(value, (list, tuple, set)):
            words.update(_terms(*value))
        elif value is not None:
            words.update(
                token.casefold()
                for token in _WORD.findall(str(value))
                if len(token) > 1 and token.casefold() not in _STOP_WORDS
            )
    return words


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _token_cost(text: str) -> int:
    return max(1, (len(text.encode("utf-8", "replace")) + 3) // 4)


def _bundle_wire_tokens(bundle: ContextBundle) -> int:
    """Estimate the complete serialized bundle, including duplicated summaries.

    The old implementation counted only item content and could label a 230-token
    JSON payload as 92 tokens. Iterate the self-referential ``token_estimate``
    field to a stable value so the receipt describes the payload actually sent.
    """

    estimate = 0
    for _ in range(4):
        rendered = bundle.model_copy(update={"token_estimate": estimate}).model_dump_json()
        updated = _token_cost(rendered)
        if updated == estimate:
            break
        estimate = updated
    return estimate


def _project_key(value: str) -> str:
    return value.strip().replace("\\", "/").rstrip("/").casefold()


def _safe_text(value: object, limit: int) -> str:
    cleaned, _ = redact_text(str(value))
    text = (cleaned or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _safe_item(item: ContextItem) -> ContextItem:
    """Minimize and redact one item at the final handoff boundary."""
    metadata: dict[str, Any] = {}
    if isinstance(item.metadata.get("verified"), bool):
        metadata["verified"] = item.metadata["verified"]
    if isinstance(item.metadata.get("unresolved"), bool):
        metadata["unresolved"] = item.metadata["unresolved"]
    for key in ("status", "kind"):
        if item.metadata.get(key) is not None:
            metadata[key] = _safe_text(item.metadata[key], 128)
    if item.metadata.get("source_session_id") is not None:
        metadata["source_session_id"] = _safe_text(
            item.metadata["source_session_id"],
            512,
        )
    for key in ("files", "evidence"):
        raw = item.metadata.get(key)
        if isinstance(raw, (list, tuple)):
            metadata[key] = [
                text
                for value in raw[:16]
                if (text := _safe_text(value, 512))
            ]
    return item.model_copy(
        update={
            "content": _safe_text(item.content, _MAX_HANDOFF_ITEM_CHARS),
            "source_refs": [
                text
                for value in item.source_refs[:24]
                if (text := _safe_text(value, 512))
            ],
            "relevance_tags": [
                text
                for value in item.relevance_tags[:24]
                if (text := _safe_text(value, 256))
            ],
            "metadata": metadata,
        }
    )


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _near_duplicate(left: ContextItem, right: ContextItem) -> bool:
    if left.kind != right.kind:
        return False
    left_terms = _terms(left.content)
    right_terms = _terms(right.content)
    union = left_terms | right_terms
    return bool(union) and len(left_terms & right_terms) / len(union) >= 0.9


def _item_relevance_terms(item: ContextItem) -> set[str]:
    return _terms(item.content, item.relevance_tags, item.metadata.get("files"))


def _target_relevance_terms(target: HarnessSession) -> set[str]:
    return _terms(
        target.metadata.get("role"),
        target.metadata.get("task"),
        target.metadata.get("current_task"),
        target.metadata.get("task_phase"),
        target.metadata.get("active_files"),
    )


def _is_unresolved(item: ContextItem, item_terms: set[str] | None = None) -> bool:
    terms = item_terms if item_terms is not None else _item_relevance_terms(item)
    return bool(item.metadata.get("unresolved")) or bool(
        terms & {"blocked", "dependency", "missing", "unresolved"}
    )


def _matches_declared_target(item: ContextItem, target: HarnessSession) -> bool:
    """Require target-specific evidence when the target declares its current work.

    Goal-wide decisions, constraints, and unresolved dependencies remain useful
    regardless of phase. Other items must overlap the target's role, task, or
    active files; broad goal relevance alone is not enough for a minimal bundle.
    """

    target_terms = _target_relevance_terms(target)
    if not target_terms:
        return True
    item_terms = _item_relevance_terms(item)
    return (
        item.kind in {ContextKind.DECISION, ContextKind.CONSTRAINT}
        or _is_unresolved(item, item_terms)
        or bool(item_terms & target_terms)
    )


def score_item(
    item: ContextItem,
    goal: Goal,
    target: HarnessSession,
    *,
    now: datetime | None = None,
) -> float:
    """Score legitimate context using the algorithm required by the build spec."""
    now = now or datetime.now(UTC)
    if item.sensitivity in {Sensitivity.SECRET, Sensitivity.LOCAL_ONLY}:
        return -1.0
    if _project_key(item.project_id) != _project_key(goal.project_id) or item.goal_id != goal.id:
        return -1.0
    if target.project_id and _project_key(item.project_id) != _project_key(target.project_id):
        return -1.0
    if (
        item.kind == ContextKind.DECISION
        and str(item.metadata.get("status") or "").casefold()
        == DecisionStatus.SUPERSEDED.value
    ):
        return -1.0
    if item.stale_after is not None and _as_utc(item.stale_after) <= now:
        return -1.0
    # A handoff must be traceable to something PEX legitimately observed.
    if not item.source_refs:
        return -1.0

    item_terms = _item_relevance_terms(item)
    goal_terms = _terms(
        goal.objective,
        goal.acceptance_criteria,
        goal.constraints,
        goal.non_goals,
        goal.preferences,
        goal.evidence_requirements,
    )
    target_terms = _target_relevance_terms(target)

    score = _overlap(item_terms, goal_terms)
    score += 0.55 * _overlap(item_terms, target_terms)

    unresolved = _is_unresolved(item, item_terms)
    if unresolved:
        score += 0.25
    if item.kind == ContextKind.DECISION:
        score += 0.30
    elif item.kind == ContextKind.CONSTRAINT:
        score += 0.25
    elif item.kind == ContextKind.ARTIFACT:
        score += 0.15
    elif item.kind == ContextKind.RESULT:
        score += 0.25
    elif item.kind == ContextKind.CLAIM:
        # A worker claim is useful context, but never strong evidence by itself.
        score += 0.03

    if item.provenance in _STRONG_PROVENANCE:
        score += 0.20
    elif item.provenance == SourceKind.HUMAN:
        score += 0.12
    if item.kind == ContextKind.RESULT and bool(item.metadata.get("verified")):
        score += 0.20

    age_days = max(0.0, (now - _as_utc(item.valid_from)).total_seconds() / 86_400)
    score += 0.15 * max(0.0, 1.0 - age_days / 30.0)
    return score * (0.6 + 0.4 * item.confidence)


def build_bundle(
    goal: Goal,
    target: HarnessSession,
    items: list[ContextItem],
    recent: list[HarnessEvent],
    source_session_ids: list[str],
    token_budget: int = 12000,
    exclude_item_ids: set[str] | None = None,
) -> ContextBundle:
    """Build the smallest provenance-preserving context bundle under budget."""
    if (
        not isinstance(token_budget, int)
        or not _MIN_HANDOFF_TOKENS <= token_budget <= _MAX_HANDOFF_TOKENS
    ):
        raise ValueError(
            f"token_budget must be between {_MIN_HANDOFF_TOKENS} "
            f"and {_MAX_HANDOFF_TOKENS}"
        )
    now = datetime.now(UTC)
    bounded_source_session_ids = [
        text
        for value in source_session_ids[:64]
        if (text := _safe_text(value, 512))
    ]
    source_session_set = set(bounded_source_session_ids)

    def source_matches(item: ContextItem) -> bool:
        if not source_session_set or item.provenance in {SourceKind.HUMAN, SourceKind.PEX}:
            return True
        source_session_id = _safe_text(item.metadata.get("source_session_id") or "", 512)
        return source_session_id in source_session_set

    excluded = exclude_item_ids or set()
    previously_delivered = [item for item in items if item.id in excluded]
    superseded = {
        item.supersedes
        for item in items
        if item.supersedes
        and item.id not in excluded
        and score_item(item, goal, target, now=now) > 0
    }
    verified_refs = {
        ref
        for item in items
        if item.kind == ContextKind.RESULT
        and bool(item.metadata.get("verified"))
        and score_item(item, goal, target, now=now) > 0
        for ref in item.source_refs
    }
    eligible = [
        item
        for item in items
        if item.id not in excluded
        and item.id not in superseded
        and source_matches(item)
        and _matches_declared_target(item, target)
        and not (
            item.kind in {ContextKind.FACT, ContextKind.CLAIM}
            and bool(set(item.source_refs) & verified_refs)
        )
        and score_item(item, goal, target, now=now) > 0.18
    ]
    ranked = sorted(
        eligible,
        key=lambda item: (
            score_item(item, goal, target, now=now),
            _as_utc(item.valid_from),
            item.id,
        ),
        reverse=True,
    )[:_MAX_HANDOFF_CANDIDATES]

    goal_summary = _safe_text(goal.objective, 4_000)
    acceptance_criteria = [
        text
        for value in goal.acceptance_criteria[:32]
        if (text := _safe_text(value, 1_000))
    ]

    def _next_objective(chosen: list[ContextItem]) -> str:
        for item in chosen:
            kind = str(item.metadata.get("kind") or "").casefold()
            status = str(item.metadata.get("status") or "").casefold()
            if kind == "unresolved_question" or (
                item.kind == ContextKind.DECISION and status == "uncertain"
            ):
                text = _safe_text(item.content, 1_000)
                if text:
                    return text
        evidenced = " ".join(
            item.content
            for item in chosen
            if item.kind == ContextKind.RESULT
            and (
                item.provenance in _STRONG_PROVENANCE
                or bool(item.metadata.get("verified"))
            )
        ).casefold()
        for criterion in goal.acceptance_criteria:
            cleaned = _safe_text(criterion, 1_000)
            tokens = [token for token in cleaned.casefold().split() if len(token) > 3]
            if tokens and evidenced and all(token in evidenced for token in tokens[:3]):
                continue
            if cleaned:
                return cleaned
        return _safe_text(goal.title, 200) or _safe_text(
            goal.objective.split("\n", 1)[0], 1_000
        )

    def _do_not_redo(selected: list[ContextItem]) -> list[str]:
        rows: list[str] = []
        for item in selected:
            kind = str(item.metadata.get("kind") or "").casefold()
            status = str(item.metadata.get("status") or "").casefold()
            if kind == "rejected_approach":
                rows.append(item.content)
                continue
            if item.kind in {ContextKind.DECISION, ContextKind.RESULT} and (
                status in {"supported", "verified", "complete", "passed"}
                or re.search(
                    r"\balready (?:verified|completed|passed)\b",
                    item.content,
                    re.I,
                )
            ):
                rows.append(item.content)
        return rows[:8]

    def _deep_links(selected: list[ContextItem]) -> list[str]:
        links: list[str] = []
        for item in selected:
            raw = item.metadata.get("files")
            if not isinstance(raw, (list, tuple)):
                continue
            for value in raw:
                text = _safe_text(value, 512)
                if text and text not in links:
                    links.append(text)
                if len(links) >= 8:
                    return links
        return links

    def assemble(
        chosen_raw: list[ContextItem],
        progress: list[str],
    ) -> ContextBundle:
        selected = [_safe_item(item) for item in chosen_raw]
        critical = [
            (
                f"Constraint: {item.content}"
                if item.kind == ContextKind.CONSTRAINT
                else item.content
            )
            for item in selected
            if item.kind in {ContextKind.DECISION, ContextKind.CONSTRAINT}
        ][:8]
        direct_evidence = [
            item.content
            for item in selected
            if item.kind == ContextKind.RESULT
            and (
                item.provenance in _STRONG_PROVENANCE
                or bool(item.metadata.get("verified"))
            )
        ][:8]
        bundle = ContextBundle(
            goal_id=goal.id,
            target_session_id=target.id,
            source_session_ids=bounded_source_session_ids,
            goal_summary=goal_summary,
            acceptance_criteria=acceptance_criteria,
            critical_decisions=critical,
            relevant_artifacts=[
                item.content for item in selected if item.kind == ContextKind.ARTIFACT
            ][:8],
            direct_evidence=direct_evidence,
            recent_progress=progress,
            next_objective=_next_objective(selected),
            do_not_redo=_do_not_redo(selected),
            deep_links=_deep_links(selected),
            items=selected,
            token_estimate=0,
            created_at=now,
        )
        bundle.token_estimate = _bundle_wire_tokens(bundle)
        return bundle

    base = assemble([], [])
    if base.token_estimate > token_budget:
        raise ValueError("token_budget is too small for the mandatory goal contract")

    selected_raw: list[ContextItem] = []
    for item in ranked:
        if any(
            _near_duplicate(item, prior)
            for prior in [*previously_delivered, *selected_raw]
        ):
            continue
        safe_item = _safe_item(item)
        if not safe_item.content or not safe_item.source_refs:
            continue
        trial = assemble([*selected_raw, item], [])
        if trial.token_estimate > token_budget:
            # A large top-ranked item must not crowd out smaller useful facts.
            continue
        selected_raw.append(item)

    seen_progress: set[str] = set()
    source_ids = set(bounded_source_session_ids)
    selected_source_refs = {
        ref for item in selected_raw for ref in item.source_refs if ref
    }
    newest_progress: list[str] = []
    for event in reversed(recent[-12:]):
        if source_ids and event.session_id not in source_ids:
            continue
        # Recent progress is useful, but only when it is direct provenance for a
        # selected fact. This prevents a relevant item from dragging unrelated
        # transcript turns into the bundle.
        if event.event_id not in selected_source_refs:
            continue
        text = _safe_text(event.message_delta or event.command or "", _MAX_PROGRESS_CHARS)
        if not text or text in seen_progress:
            continue
        trial_newest = [*newest_progress, text]
        trial = assemble(selected_raw, list(reversed(trial_newest)))
        if trial.token_estimate > token_budget:
            continue
        newest_progress = trial_newest
        seen_progress.add(text)
        if len(newest_progress) == 6:
            break

    return assemble(selected_raw, list(reversed(newest_progress)))


def items_from_verification(
    project_id: str,
    goal_id: str,
    event: HarnessEvent,
    verification: dict[str, Any],
    recent: list[HarnessEvent],
) -> list[ContextItem]:
    """Turn supported checks into reusable evidence; never promote raw claims."""
    items: list[ContextItem] = []
    latest_pytest_ref = next(
        (
            candidate.event_id
            for candidate in reversed(recent)
            if isinstance((candidate.process_state or {}).get("pytest"), dict)
            or "pytest" in (candidate.command or "").casefold()
        ),
        None,
    )
    for verdict in verification.get("verdicts") or []:
        if not isinstance(verdict, dict) or verdict.get("status") != "supported":
            continue
        claim = verdict.get("claim") if isinstance(verdict.get("claim"), dict) else {}
        evidence = [str(value) for value in verdict.get("evidence") or [] if str(value)]
        statement = str(claim.get("statement") or "").strip()
        if not statement or not evidence:
            continue
        is_test = any("pytest" in value.casefold() for value in evidence)
        provenance = SourceKind.TEST if is_test else SourceKind.WORKSPACE
        source_refs = [str(claim.get("source_event_id") or event.event_id)]
        if is_test and latest_pytest_ref:
            source_refs.append(latest_pytest_ref)
        elif not is_test:
            source_refs.append(f"workspace_snapshot:{event.event_id}")
        source_refs = list(dict.fromkeys(source_refs))
        items.append(
            ContextItem(
                id=new_id("result_"),
                project_id=project_id,
                goal_id=goal_id,
                kind=ContextKind.RESULT,
                content=f"{statement} Verified by: {', '.join(evidence)}.",
                source_refs=source_refs,
                provenance=provenance,
                confidence=0.95,
                relevance_tags=[
                    str(claim.get("kind") or "verified_result"),
                    "verified",
                    *evidence[:6],
                ],
                valid_from=event.ts,
                sensitivity=Sensitivity.INTERNAL,
                metadata={
                    "verified": True,
                    "status": "supported",
                    "evidence": evidence,
                    "claim": claim,
                    "source_session_id": event.session_id,
                },
            )
        )
    return items


def item_from_event(
    project_id: str,
    goal_id: str | None,
    event: HarnessEvent,
) -> ContextItem | None:
    content = event.message_delta or event.command
    if not content:
        return None
    kind = ContextKind.FACT
    if event.event_type in {EventType.FILE_EDIT, EventType.TOOL_RESULT}:
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
        metadata={
            "files": list(event.file_paths[:16]),
            "source_session_id": event.session_id,
        },
    )
