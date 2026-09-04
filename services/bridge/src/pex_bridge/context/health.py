"""Build spec §15.5 context health from observed events and durable items.

Unmeasured fields stay null. The score is written onto HarnessSession.context_health.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from pex_protocol.context import ContextItem
from pex_protocol.enums import ContextKind, EventType, Sensitivity
from pex_protocol.session import HarnessEvent

_SECRET = {Sensitivity.SECRET, Sensitivity.LOCAL_ONLY}
_DURABLE_KINDS = {
    ContextKind.ARTIFACT,
    ContextKind.RESULT,
    ContextKind.FACT,
    ContextKind.DECISION,
    ContextKind.CONSTRAINT,
}
_CONTRADICTED = {"contradicted", "conflict", "conflicting", "acceptance_gap"}
_PROGRESS_EVENTS = {
    EventType.FILE_EDIT,
    EventType.TOOL_RESULT,
    EventType.STOP,
}


@dataclass(frozen=True)
class ContextHealthReport:
    score: float
    signals: dict[str, Any]
    forgotten_facts: list[str]
    degraded: bool

    def planner_features(self) -> dict[str, Any]:
        return {
            "context_health": self.score,
            "compaction_count": int(self.signals.get("compaction_count") or 0),
            "forgotten_facts": list(self.forgotten_facts),
            "forgotten_fact_count": int(self.signals.get("forgotten_fact_count") or 0),
        }


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _file_names(paths: object) -> set[str]:
    names: set[str] = set()
    if not isinstance(paths, (list, tuple)):
        return names
    for path in paths:
        name = PurePosixPath(str(path).replace("\\", "/")).name.casefold()
        if name:
            names.add(name)
    return names


def _item_files(item: ContextItem) -> set[str]:
    return _file_names(item.metadata.get("files"))


def _safe_content(item: ContextItem) -> str:
    if item.sensitivity in _SECRET:
        return ""
    text = (item.content or "").strip()
    return text[:400]


def _token_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    return float(value)


def _token_utilization(events: list[HarnessEvent]) -> float | None:
    for event in reversed(events):
        usage = event.token_usage
        if not isinstance(usage, dict):
            continue
        used = (
            _token_number(usage.get("total_tokens"))
            or _token_number(usage.get("prompt_tokens"))
            or _token_number(usage.get("input_tokens"))
        )
        window = (
            _token_number(usage.get("context_window"))
            or _token_number(usage.get("max_context_tokens"))
            or _token_number(usage.get("context_limit"))
        )
        if used is None or window is None:
            continue
        return round(min(1.0, used / window), 4)
    return None


def _repeated_reads(events: list[HarnessEvent]) -> int:
    names: list[str] = []
    for event in events:
        if event.event_type != EventType.FILE_READ:
            continue
        names.extend(_file_names(event.file_paths))
    return sum(count - 1 for count in Counter(names).values() if count > 1)


def _contradiction_count(items: list[ContextItem]) -> int:
    count = 0
    for item in items:
        status = str(item.metadata.get("status") or "").casefold()
        if status in _CONTRADICTED:
            count += 1
            continue
        if item.kind == ContextKind.CLAIM and status in {"false", "rejected"}:
            count += 1
    return count


def _stale_decision_count(items: list[ContextItem], now: datetime) -> int:
    count = 0
    for item in items:
        if item.kind != ContextKind.DECISION:
            continue
        if item.stale_after is None:
            continue
        if _as_utc(item.stale_after) <= now:
            count += 1
    return count


def _ordered_events(events: list[HarnessEvent]) -> list[HarnessEvent]:
    return [
        event
        for _, event in sorted(
            enumerate(events),
            key=lambda pair: (_as_utc(pair[1].ts), pair[0]),
        )
    ]


def _forgotten_facts(
    events: list[HarnessEvent],
    items: list[ContextItem],
) -> list[str]:
    """Durable facts re-read twice after compaction without an edit of that file."""

    ordered = _ordered_events(events)
    durable = [
        item
        for item in items
        if item.kind in _DURABLE_KINDS and item.sensitivity not in _SECRET
    ]
    seen: list[str] = []
    for index, compact in enumerate(ordered):
        if compact.event_type != EventType.COMPACTION:
            continue
        known: dict[str, str] = {}
        for item in durable:
            if _as_utc(item.valid_from) > _as_utc(compact.ts):
                continue
            content = _safe_content(item)
            for name in _item_files(item):
                if content:
                    known.setdefault(name, content)
        for prior in ordered[:index]:
            if prior.event_type != EventType.FILE_EDIT:
                continue
            content = (prior.message_delta or prior.command or "").strip()[:400]
            for name in _file_names(prior.file_paths):
                if content:
                    known.setdefault(name, content)
        if not known:
            continue
        reads: Counter[str] = Counter()
        edited: set[str] = set()
        for event in ordered[index + 1 :]:
            names = _file_names(event.file_paths)
            if event.event_type == EventType.FILE_EDIT:
                edited.update(names)
                continue
            if event.event_type != EventType.FILE_READ:
                continue
            for name in names:
                if name in known and name not in edited:
                    reads[name] += 1
        for name, count in reads.items():
            if count < 2:
                continue
            content = known[name]
            if content and content not in seen:
                seen.append(content)
    return seen[:8]


def assess_context_health(
    events: list[HarnessEvent],
    items: list[ContextItem],
    *,
    now: datetime | None = None,
) -> ContextHealthReport:
    instant = now or datetime.now(UTC)
    ordered = _ordered_events(events)
    forgotten = _forgotten_facts(ordered, items)
    compaction_count = sum(
        1 for event in ordered if event.event_type == EventType.COMPACTION
    )
    repeated_read_count = _repeated_reads(ordered)
    contradiction_count = _contradiction_count(items)
    stale_decision_count = _stale_decision_count(items, instant)
    token_utilization = _token_utilization(ordered)
    progress_events = sum(1 for event in ordered if event.event_type in _PROGRESS_EVENTS)
    context_n = len(items)
    context_to_progress = (
        round(progress_events / context_n, 4) if context_n else None
    )

    score = 1.0
    score -= min(0.36, 0.12 * compaction_count)
    score -= min(0.24, 0.12 * len(forgotten))
    score -= min(0.20, 0.10 * contradiction_count)
    score -= min(0.15, 0.05 * repeated_read_count)
    score -= min(0.16, 0.08 * stale_decision_count)
    if token_utilization is not None:
        if token_utilization >= 0.85:
            score -= 0.15
        elif token_utilization >= 0.70:
            score -= 0.08
    if (
        context_to_progress is not None
        and context_n >= 8
        and context_to_progress < 0.25
    ):
        score -= 0.10
    score = round(max(0.0, min(1.0, score)), 4)
    degraded = score < 0.6 or bool(forgotten)

    signals = {
        "token_utilization": token_utilization,
        "compaction_count": compaction_count,
        "forgotten_fact_count": len(forgotten),
        "contradiction_count": contradiction_count,
        "repeated_read_count": repeated_read_count,
        "stale_decision_count": stale_decision_count,
        "summary_depth": None,
        "context_to_progress_ratio": context_to_progress,
    }
    return ContextHealthReport(
        score=score,
        signals=signals,
        forgotten_facts=forgotten,
        degraded=degraded,
    )
