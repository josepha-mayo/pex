from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge.agentcore import cloud_request
from pex_bridge.supervisor_context import build_supervisor_context
from pex_protocol.context import ContextItem
from pex_protocol.enums import (
    ContextKind,
    DecisionSource,
    DecisionStatus,
    EventPhase,
    EventType,
    HarnessType,
    Sensitivity,
    SessionStatus,
    SourceKind,
)
from pex_protocol.goal import Decision, Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorContextEnvelope, SupervisorRequest
from pex_supervisor.evidence_tools import build_evidence_tools
from pydantic import ValidationError


def _bound(now: datetime) -> tuple[HarnessSession, Goal, HarnessEvent]:
    session = HarnessSession(
        id="codex:thread-one",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-one",
        project_id=r"C:\Work\PEX",
        goal_id="goal-one",
        cwd=r"C:\Work\PEX",
        status=SessionStatus.STOPPED,
        last_activity=now,
    )
    goal = Goal(
        id="goal-one",
        project_id="c:/work/pex/",
        title="Finish evidence",
        objective="Produce the verified report.",
        created_at=now - timedelta(days=1),
        updated_at=now,
    )
    event = HarnessEvent(
        event_id="event-one",
        ts=now,
        harness_type=HarnessType.CODEX,
        session_id=session.id,
        project_id=session.project_id,
        goal_id=goal.id,
        event_type=EventType.STOP,
        phase=EventPhase.TERMINAL,
        message_delta="done",
    )
    return session, goal, event


def _context(
    now: datetime,
    item_id: str,
    *,
    project_id: str = "c:/work/pex",
    goal_id: str | None = "goal-one",
    content: str = "The sibling verified report.json against the schema.",
    sensitivity: Sensitivity = Sensitivity.INTERNAL,
    stale_after: datetime | None = None,
    supersedes: str | None = None,
    valid_from: datetime | None = None,
    metadata: dict | None = None,
) -> ContextItem:
    return ContextItem(
        id=item_id,
        project_id=project_id,
        goal_id=goal_id,
        kind=ContextKind.RESULT,
        content=content,
        source_refs=[f"event:{item_id}"],
        provenance=SourceKind.TEST,
        confidence=0.95,
        relevance_tags=["report", "verification"],
        valid_from=valid_from or now - timedelta(minutes=5),
        stale_after=stale_after,
        supersedes=supersedes,
        sensitivity=sensitivity,
        metadata={
            "verified": True,
            "kind": "verified_sibling_result",
            "source_session_id": "cursor:sibling",
            **(metadata or {}),
        },
    )


def _decision(
    now: datetime,
    decision_id: str,
    *,
    goal_id: str = "goal-one",
    status: DecisionStatus = DecisionStatus.ACTIVE,
    sensitivity: Sensitivity = Sensitivity.INTERNAL,
    created_at: datetime | None = None,
) -> Decision:
    return Decision(
        id=decision_id,
        goal_id=goal_id,
        statement="Use schema.json as the source of truth.",
        rationale="The prior README path was rejected after verification.",
        alternatives_rejected=["Reuse the obsolete README example."],
        scope="report generation",
        confidence=1.0,
        source=DecisionSource.HUMAN,
        status=status,
        created_at=created_at or now - timedelta(minutes=10),
        sensitivity=sensitivity,
        metadata={
            "source_event_id": "event:human-decision",
            "source_session_id": "cursor:sibling",
        },
    )


def test_build_supervisor_context_exposes_useful_provenance_and_rejected_approach():
    now = datetime(2026, 9, 5, 12, tzinfo=UTC)
    session, goal, event = _bound(now)
    envelope = build_supervisor_context(
        session,
        [_context(now, "ctx-result"), _context(now, "ctx-project", goal_id=None)],
        [_decision(now, "decision-schema")],
        now=now,
    )

    assert envelope.offered_context_ids == ("ctx-result", "ctx-project")
    assert envelope.offered_decision_ids == ("decision-schema",)
    assert envelope.context_items[0].verified is True
    assert envelope.context_items[0].semantic_kind == "verified_sibling_result"
    assert envelope.context_items[0].source_session_id == "cursor:sibling"
    assert envelope.decisions[0].alternatives_rejected == (
        "Reuse the obsolete README example.",
    )

    request = SupervisorRequest(
        session=session,
        goal=goal,
        event=event,
        recent_events=[event],
        supervisor_context=envelope,
    )
    used: list[str] = []
    tools = {item.tool_name: item for item in build_evidence_tools(request, used)}
    context_payload = json.loads(tools["get_context_items"]())
    decision_payload = json.loads(tools["get_decisions"]())
    assert [item["id"] for item in context_payload["items"]] == [
        "ctx-result",
        "ctx-project",
    ]
    assert [item["id"] for item in decision_payload["decisions"]] == [
        "decision-schema"
    ]
    decision_detail = json.loads(
        tools["get_decisions"](decision_id="decision-schema")
    )
    assert "obsolete README" in decision_detail["decision"]["alternatives_rejected"][0]
    assert used == ["get_context_items", "get_decisions", "get_decisions"]


def test_selector_drops_expired_superseded_sensitive_future_and_foreign_records():
    now = datetime(2026, 9, 5, 12, tzinfo=UTC)
    session, _, _ = _bound(now)
    items = [
        _context(now, "old"),
        _context(now, "replacement", supersedes="old"),
        _context(now, "stale", stale_after=now),
        _context(now, "future", valid_from=now + timedelta(seconds=1)),
        _context(now, "secret", sensitivity=Sensitivity.SECRET),
        _context(now, "local", sensitivity=Sensitivity.LOCAL_ONLY),
        _context(now, "foreign-project", project_id="C:/other"),
        _context(now, "foreign-goal", goal_id="goal-two"),
    ]
    decisions = [
        _decision(now, "active"),
        _decision(now, "superseded", status=DecisionStatus.SUPERSEDED),
        _decision(now, "secret-decision", sensitivity=Sensitivity.SECRET),
        _decision(now, "foreign-decision", goal_id="goal-two"),
        _decision(now, "future-decision", created_at=now + timedelta(seconds=1)),
    ]

    envelope = build_supervisor_context(session, items, decisions, now=now)

    assert envelope.offered_context_ids == ("replacement",)
    assert envelope.offered_decision_ids == ("active",)
    assert tuple(item.id for item in envelope.context_items) == ("replacement",)
    assert tuple(item.id for item in envelope.decisions) == ("active",)


def test_remote_context_is_preserved_redacted_and_project_opaque():
    now = datetime(2026, 9, 5, 12, tzinfo=UTC)
    session, goal, event = _bound(now)
    internal = _context(
        now,
        "ctx-safe",
        content=(
            r"Read C:\Work\PEX\schema.json. "
            "Authorization: Bearer top-secret-token"
        ),
    )
    secret = _context(
        now,
        "ctx-secret",
        content="password=do-not-send-this-value",
        sensitivity=Sensitivity.SECRET,
    )
    envelope = build_supervisor_context(
        session,
        [internal, secret],
        [_decision(now, "decision-schema")],
        now=now,
    )
    request = SupervisorRequest(
        session=session,
        goal=goal,
        event=event,
        recent_events=[event],
        supervisor_context=envelope,
    )

    remote = cloud_request(request)
    rendered = remote.model_dump_json()
    assert remote.supervisor_context is not None
    assert remote.supervisor_context.offered_context_ids == ("ctx-safe",)
    assert remote.supervisor_context.offered_decision_ids == ("decision-schema",)
    assert remote.supervisor_context.project_id == remote.session.project_id
    assert remote.supervisor_context.context_items[0].project_id == remote.session.project_id
    assert "ctx-secret" not in rendered
    assert "top-secret-token" not in rendered
    assert "C:\\Work\\PEX" not in rendered
    assert "[REDACTED:" in rendered


def test_request_rejects_cross_bound_context_and_empty_packet_remains_valid():
    now = datetime(2026, 9, 5, 12, tzinfo=UTC)
    session, goal, event = _bound(now)
    empty = build_supervisor_context(session, [], [], now=now)
    request = SupervisorRequest(
        session=session,
        goal=goal,
        event=event,
        supervisor_context=empty,
    )
    assert request.supervisor_context is not None
    assert request.supervisor_context.context_items == ()
    assert request.supervisor_context.decisions == ()

    wrong = empty.model_dump(mode="json", by_alias=True)
    wrong["target_session_id"] = "codex:other"
    with pytest.raises(ValidationError, match="context/session identity"):
        SupervisorRequest(
            session=session,
            goal=goal,
            event=event,
            supervisor_context=SupervisorContextEnvelope.model_validate(wrong),
        )


def test_secret_replacement_suppresses_predecessor_without_disclosing_replacement():
    now = datetime(2026, 9, 5, 12, tzinfo=UTC)
    session, _, _ = _bound(now)
    envelope = build_supervisor_context(
        session,
        [
            _context(now, "old-public"),
            _context(
                now,
                "new-secret",
                supersedes="old-public",
                sensitivity=Sensitivity.SECRET,
            ),
        ],
        [],
        now=now,
    )
    assert envelope.offered_context_ids == ()
    assert envelope.context_items == ()


def test_harness_metadata_cannot_upgrade_self_report_to_verified_context():
    now = datetime(2026, 9, 5, 12, tzinfo=UTC)
    session, _, _ = _bound(now)
    self_report = _context(
        now,
        "worker-claim",
        metadata={"verified": True, "status": "supported"},
    )
    self_report.provenance = SourceKind.HARNESS

    envelope = build_supervisor_context(session, [self_report], [], now=now)

    assert envelope.context_items[0].provenance == SourceKind.HARNESS
    assert envelope.context_items[0].status == "supported"
    assert envelope.context_items[0].verified is False


def test_evidence_tools_page_and_retrieve_offered_records_beyond_first_page():
    now = datetime(2026, 9, 5, 12, tzinfo=UTC)
    session, goal, event = _bound(now)
    contexts = [
        _context(
            now,
            f"ctx-{index:02d}",
            content=f"marker-context-{index:02d} " + ("x" * 1_750),
            valid_from=now - timedelta(minutes=index + 1),
        )
        for index in range(14)
    ]
    decisions = [_decision(now, f"decision-{index:02d}") for index in range(14)]
    for index, decision in enumerate(decisions):
        decision.statement = f"marker-decision-{index:02d} " + ("y" * 530)
        decision.rationale = "r" * 200
    envelope = build_supervisor_context(
        session,
        contexts,
        decisions,
        now=now,
    )
    request = SupervisorRequest(
        session=session,
        goal=goal,
        event=event,
        recent_events=[event],
        supervisor_context=envelope,
    )
    used: list[str] = []
    tools = {item.tool_name: item for item in build_evidence_tools(request, used)}

    context_page = json.loads(tools["get_context_items"]())
    decision_page = json.loads(tools["get_decisions"]())
    assert context_page["mode"] == "page"
    assert context_page["offered_count"] == 14
    assert context_page["next_offset"] == 3
    assert context_page["omitted_count"] == 11
    assert context_page["next_ids"] == list(envelope.offered_context_ids[3:6])
    assert decision_page["mode"] == "page"
    assert decision_page["offered_count"] == 14
    assert decision_page["next_offset"] == 3
    assert decision_page["omitted_count"] == 11
    assert decision_page["next_ids"] == list(envelope.offered_decision_ids[3:6])

    context_id = envelope.offered_context_ids[-1]
    decision_id = envelope.offered_decision_ids[-1]
    assert context_id not in {item["id"] for item in context_page["items"]}
    assert decision_id not in {item["id"] for item in decision_page["decisions"]}

    context_detail_raw = tools["get_context_items"](context_id=context_id)
    decision_detail_raw = tools["get_decisions"](decision_id=decision_id)
    context_detail = json.loads(context_detail_raw)
    decision_detail = json.loads(decision_detail_raw)
    assert context_detail.get("truncated") is not True
    assert context_detail["item"]["id"] == context_id
    assert context_detail["item"]["content"].startswith("marker-context-")
    assert context_detail["item"]["content_truncated"] is True
    assert decision_detail.get("truncated") is not True
    assert decision_detail["decision"]["id"] == decision_id
    assert decision_detail["decision"]["statement"].startswith("marker-decision-")
    assert decision_detail["decision"]["statement_truncated"] is False
    assert len(context_detail_raw) < 8_000
    assert len(decision_detail_raw) < 8_000
