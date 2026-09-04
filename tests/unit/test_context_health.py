from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pex_bridge.context.health import assess_context_health
from pex_protocol.context import ContextItem
from pex_protocol.enums import ContextKind, EventType, HarnessType, Sensitivity, SourceKind
from pex_protocol.session import HarnessEvent


def _item(
    item_id: str,
    content: str,
    now: datetime,
    *,
    kind: ContextKind = ContextKind.ARTIFACT,
    files: list[str] | None = None,
    status: str | None = None,
    stale_after: datetime | None = None,
    sensitivity: Sensitivity = Sensitivity.INTERNAL,
) -> ContextItem:
    metadata: dict = {"files": files or [], "source_session_id": "synthetic:s1"}
    if status:
        metadata["status"] = status
    return ContextItem(
        id=item_id,
        project_id="demo",
        goal_id="goal_1",
        kind=kind,
        content=content,
        source_refs=[f"event:{item_id}"],
        provenance=SourceKind.HARNESS,
        confidence=0.9,
        relevance_tags=["parser"],
        valid_from=now,
        stale_after=stale_after,
        sensitivity=sensitivity,
        metadata=metadata,
    )


def _event(
    event_id: str,
    event_type: EventType,
    ts: datetime,
    *,
    file_paths: list[str] | None = None,
    token_usage: dict | None = None,
    message_delta: str = "observed",
) -> HarnessEvent:
    return HarnessEvent(
        event_id=event_id,
        ts=ts,
        harness_type=HarnessType.SYNTHETIC,
        session_id="synthetic:s1",
        event_type=event_type,
        message_delta=message_delta,
        file_paths=file_paths or [],
        token_usage=token_usage,
    )


def test_unmeasured_health_stays_healthy_and_nulls_unobserved_fields() -> None:
    now = datetime.now(UTC)
    report = assess_context_health([], [], now=now)
    assert report.score == 1.0
    assert report.degraded is False
    assert report.forgotten_facts == []
    assert report.signals["token_utilization"] is None
    assert report.signals["summary_depth"] is None
    assert report.signals["compaction_count"] == 0
    assert report.signals["context_to_progress_ratio"] is None


def test_repeated_forgotten_fact_after_compaction_lowers_health() -> None:
    now = datetime.now(UTC)
    artifact = _item(
        "schema",
        "schema.json is the source of truth for the parser.",
        now - timedelta(minutes=10),
        files=["src/schema.json"],
    )
    schema = ["src/schema.json"]
    events = [
        _event("edit", EventType.FILE_EDIT, now - timedelta(minutes=9), file_paths=schema),
        _event("compact", EventType.COMPACTION, now - timedelta(minutes=4)),
        _event("read-1", EventType.FILE_READ, now - timedelta(minutes=3), file_paths=schema),
        _event("read-2", EventType.FILE_READ, now - timedelta(minutes=1), file_paths=schema),
    ]
    report = assess_context_health(events, [artifact], now=now)
    assert report.score < 0.9
    assert report.degraded is True
    assert artifact.content in report.forgotten_facts
    assert report.signals["compaction_count"] == 1
    assert report.signals["forgotten_fact_count"] == 1
    assert report.signals["token_utilization"] is None
    features = report.planner_features()
    assert features["forgotten_facts"] == [artifact.content]


def test_post_compaction_edit_is_not_a_forgotten_fact() -> None:
    now = datetime.now(UTC)
    artifact = _item(
        "schema",
        "schema.json is the source of truth for the parser.",
        now - timedelta(minutes=10),
        files=["src/schema.json"],
    )
    schema = ["src/schema.json"]
    events = [
        _event("compact", EventType.COMPACTION, now - timedelta(minutes=4)),
        _event("edit", EventType.FILE_EDIT, now - timedelta(minutes=3), file_paths=schema),
        _event("read-1", EventType.FILE_READ, now - timedelta(minutes=2), file_paths=schema),
        _event("read-2", EventType.FILE_READ, now - timedelta(minutes=1), file_paths=schema),
    ]
    report = assess_context_health(events, [artifact], now=now)
    assert artifact.content not in report.forgotten_facts
    assert report.signals["forgotten_fact_count"] == 0


def test_secret_items_are_excluded_from_forgotten_facts() -> None:
    now = datetime.now(UTC)
    secret = _item(
        "secret",
        "api_key=super-secret",
        now - timedelta(minutes=10),
        files=["secrets.env"],
        sensitivity=Sensitivity.SECRET,
    )
    secret_path = ["secrets.env"]
    events = [
        _event("compact", EventType.COMPACTION, now - timedelta(minutes=4)),
        _event("read-1", EventType.FILE_READ, now - timedelta(minutes=3), file_paths=secret_path),
        _event("read-2", EventType.FILE_READ, now - timedelta(minutes=1), file_paths=secret_path),
    ]
    report = assess_context_health(events, [secret], now=now)
    assert report.forgotten_facts == []
    assert "super-secret" not in str(report.planner_features())


def test_token_utilization_and_stale_decisions_are_measured_when_exposed() -> None:
    now = datetime.now(UTC)
    stale = _item(
        "decision",
        "Use the v1 parser schema.",
        now - timedelta(days=2),
        kind=ContextKind.DECISION,
        stale_after=now - timedelta(hours=1),
    )
    contradicted = _item(
        "claim",
        "Tests passed.",
        now - timedelta(hours=1),
        kind=ContextKind.CLAIM,
        status="contradicted",
    )
    events = [
        _event(
            "usage",
            EventType.AGENT_RESPONSE,
            now,
            token_usage={"total_tokens": 90_000, "context_window": 100_000},
        )
    ]
    report = assess_context_health(events, [stale, contradicted], now=now)
    assert report.signals["token_utilization"] == 0.9
    assert report.signals["stale_decision_count"] == 1
    assert report.signals["contradiction_count"] == 1
    assert report.score < 1.0
    assert report.signals["summary_depth"] is None


def test_same_timestamp_compaction_sequence_still_detects_forgotten_facts() -> None:
    now = datetime.now(UTC)
    artifact = _item(
        "schema",
        "schema.json is the source of truth for the parser.",
        now,
        files=["src/schema.json"],
    )
    events = [
        _event(
            "edit",
            EventType.FILE_EDIT,
            now,
            file_paths=["src/schema.json"],
            message_delta=artifact.content,
        ),
        _event("compact", EventType.COMPACTION, now),
        _event("read-1", EventType.FILE_READ, now, file_paths=["src/schema.json"]),
        _event("read-2", EventType.FILE_READ, now, file_paths=["src/schema.json"]),
    ]
    report = assess_context_health(events, [artifact], now=now)
    assert artifact.content in report.forgotten_facts
    assert report.signals["compaction_count"] == 1
