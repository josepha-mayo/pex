from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge.context.mesh import build_bundle, items_from_verification, score_item
from pex_protocol.context import ContextItem
from pex_protocol.enums import (
    ContextKind,
    EventType,
    HarnessType,
    Sensitivity,
    SourceKind,
)
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession


def _goal(now: datetime) -> Goal:
    return Goal(
        id="goal_context",
        project_id="demo",
        title="Parser",
        objective="Implement the parser and verify its tests and release artifact",
        acceptance_criteria=["parser tests pass", "release artifact exists"],
        constraints=["Do not expose secrets"],
        evidence_requirements=["pytest result"],
        created_at=now,
        updated_at=now,
    )


def _target(**metadata: object) -> HarnessSession:
    return HarnessSession(
        id="synthetic:target",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="target",
        project_id="demo",
        goal_id="goal_context",
        metadata=dict(metadata),
    )


def _item(
    item_id: str,
    content: str,
    now: datetime,
    *,
    kind: ContextKind = ContextKind.FACT,
    provenance: SourceKind = SourceKind.HARNESS,
    sensitivity: Sensitivity = Sensitivity.INTERNAL,
    goal_id: str = "goal_context",
    project_id: str = "demo",
    source_refs: list[str] | None = None,
    stale_after: datetime | None = None,
    metadata: dict | None = None,
) -> ContextItem:
    return ContextItem(
        id=item_id,
        project_id=project_id,
        goal_id=goal_id,
        kind=kind,
        content=content,
        source_refs=source_refs if source_refs is not None else [f"event:{item_id}"],
        provenance=provenance,
        confidence=0.9,
        relevance_tags=["parser", "tests"],
        valid_from=now,
        stale_after=stale_after,
        sensitivity=sensitivity,
        metadata={"source_session_id": "synthetic:source", **(metadata or {})},
    )


@pytest.mark.parametrize(
    "left,right",
    [
        ("/work/PEX", "/work/pex"),
        ("project:PEX", "project:pex"),
        ("C:/work/straße", "C:/work/strasse"),
        ("C:/", "C:"),
    ],
)
@pytest.mark.parametrize("boundary", ["goal", "target"])
def test_context_project_boundaries_do_not_merge_distinct_ids(
    left: str,
    right: str,
    boundary: str,
) -> None:
    now = datetime.now(UTC)
    item = _item("foreign", "parser tests passed", now, project_id=left)
    goal = _goal(now).model_copy(update={"project_id": right if boundary == "goal" else left})
    target = _target().model_copy(update={"project_id": right if boundary == "target" else left})
    assert score_item(item, goal, target, now=now) == -1.0
    assert build_bundle(goal, target, [item], [], ["synthetic:source"]).items == []


def test_bundle_separates_claims_from_verified_direct_evidence() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    claim = _item(
        "claim",
        "The parser tests passed according to the worker.",
        now,
        kind=ContextKind.CLAIM,
        source_refs=["worker-stop"],
    )
    result = _item(
        "result",
        "Parser tests passed. Verified by: pytest_ok=true.",
        now,
        kind=ContextKind.RESULT,
        provenance=SourceKind.TEST,
        source_refs=["pytest-event"],
        metadata={"verified": True, "status": "supported"},
    )
    excluded = [
        _item("secret", "parser API_KEY=hidden", now, sensitivity=Sensitivity.SECRET),
        _item("local", "local parser scratch", now, sensitivity=Sensitivity.LOCAL_ONLY),
        _item(
            "stale",
            "old parser result",
            now - timedelta(days=2),
            stale_after=now - timedelta(seconds=1),
        ),
        _item("other-goal", "parser result", now, goal_id="goal_other"),
        _item("other-project", "parser result", now, project_id="other"),
        _item("untraced", "parser result", now, source_refs=[]),
    ]

    bundle = build_bundle(goal, _target(task="parser tests"), [claim, result, *excluded], [], [])

    assert claim in bundle.items
    assert result in bundle.items
    assert claim.content not in bundle.direct_evidence
    assert bundle.direct_evidence == [result.content]
    assert bundle.do_not_redo == [result.content]
    assert not ({item.id for item in excluded} & {item.id for item in bundle.items})


def test_declared_target_task_excludes_goal_relevant_but_phase_irrelevant_items() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    frontend = _item(
        "frontend",
        "release artifact for frontend pet sprites atlas",
        now,
        kind=ContextKind.ARTIFACT,
    )
    backend = _item(
        "backend",
        "release artifact for backend database migration",
        now,
        kind=ContextKind.ARTIFACT,
    )
    target = _target(task="frontend pet sprites atlas")

    assert score_item(frontend, goal, target, now=now) > score_item(backend, goal, target, now=now)
    bundle = build_bundle(goal, target, [backend, frontend], [], [])
    assert [item.id for item in bundle.items] == ["frontend"]


def test_declared_target_keeps_goal_wide_constraints_and_unresolved_dependencies() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    target = _target(task="frontend pet sprites atlas")
    constraint = _item(
        "constraint",
        "Never publish credentials from the workspace",
        now,
        kind=ContextKind.CONSTRAINT,
    )
    blocker = _item(
        "blocker",
        "Backend migration dependency is unresolved",
        now,
        metadata={"unresolved": True},
    )
    unrelated = _item(
        "unrelated",
        "Backend database migration artifact is complete",
        now,
        kind=ContextKind.ARTIFACT,
    )

    bundle = build_bundle(goal, target, [unrelated, constraint, blocker], [], [])

    assert {item.id for item in bundle.items} == {"constraint", "blocker"}
    assert bundle.critical_decisions == [f"Constraint: {constraint.content}"]


def test_target_without_declared_work_uses_goal_relevance_fallback() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    frontend = _item("frontend", "release artifact for frontend pet sprites atlas", now)
    backend = _item("backend", "release artifact for backend database migration", now)

    bundle = build_bundle(goal, _target(), [frontend, backend], [], [])

    assert {item.id for item in bundle.items} == {"frontend", "backend"}


def test_oversized_item_does_not_block_smaller_relevant_item() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    huge = _item(
        "huge",
        "parser tests release artifact " * 200,
        now,
        kind=ContextKind.RESULT,
        provenance=SourceKind.TEST,
        metadata={"verified": True},
    )
    small = _item("small", "parser tests passed", now, kind=ContextKind.RESULT)

    bundle = build_bundle(goal, _target(task="parser"), [huge, small], [], [], token_budget=256)

    assert huge not in bundle.items
    assert small in bundle.items
    assert bundle.token_estimate <= 256
    serialized_tokens = (len(bundle.model_dump_json().encode("utf-8")) + 3) // 4
    assert abs(bundle.token_estimate - serialized_tokens) <= 1


def test_excluded_delivery_ids_also_remove_semantic_repeats() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    delivered = _item("old", "verified parser release artifact path", now)
    repeated = _item("new", "verified parser release artifact path", now)

    bundle = build_bundle(
        goal,
        _target(task="parser release"),
        [delivered, repeated],
        [],
        [],
        exclude_item_ids={delivered.id},
    )

    assert bundle.items == []


def test_bundle_carries_only_selected_provenance_and_redacts_again_at_boundary() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    selected = _item(
        "selected",
        "Parser artifact verified with token=super-secret-value",
        now,
        kind=ContextKind.ARTIFACT,
        source_refs=["relevant-event"],
        metadata={
            "files": ["artifacts/parser.json?token=super-secret-value"],
            "notes": "arbitrary metadata must not cross the handoff",
        },
    )
    relevant = HarnessEvent(
        event_id="relevant-event",
        ts=now,
        harness_type=HarnessType.SYNTHETIC,
        session_id="synthetic:source",
        project_id="demo",
        event_type=EventType.AGENT_RESPONSE,
        message_delta="Parser artifact is ready; token=super-secret-value",
    )
    unrelated = HarnessEvent(
        event_id="unrelated-event",
        ts=now,
        harness_type=HarnessType.SYNTHETIC,
        session_id="synthetic:source",
        project_id="demo",
        event_type=EventType.AGENT_RESPONSE,
        message_delta=("UNRELATED_TRANSCRIPT_SENTINEL password=another-secret-value"),
    )

    bundle = build_bundle(
        goal,
        _target(task="parser artifact"),
        [selected],
        [unrelated, relevant],
        ["synthetic:source"],
    )
    serialized = bundle.model_dump_json()

    assert len(bundle.items) == 1
    assert bundle.recent_progress == ["Parser artifact is ready; [REDACTED:credential_assignment]"]
    assert "super-secret-value" not in serialized
    assert "another-secret-value" not in serialized
    assert "UNRELATED_TRANSCRIPT_SENTINEL" not in serialized
    assert "arbitrary metadata" not in serialized
    assert "[REDACTED:credential_assignment]" in serialized


def test_context_project_matching_normalizes_windows_path_spelling() -> None:
    now = datetime.now(UTC)
    goal = _goal(now).model_copy(update={"project_id": "C:/Work/PEX"})
    target = _target(task="parser").model_copy(update={"project_id": "c:\\work\\pex\\"})
    item = _item(
        "normalized-project",
        "parser tests passed",
        now,
        project_id="c:/WORK/pex/",
    )

    assert score_item(item, goal, target, now=now) > 0
    assert build_bundle(goal, target, [item], [], []).items == [item]


def test_bundle_cannot_rebind_another_workers_observation_to_the_source() -> None:
    now = datetime.now(UTC)
    source_item = _item(
        "source-item",
        "parser tests passed in the source worker",
        now,
        metadata={"source_session_id": "synthetic:source"},
    )
    sibling_item = _item(
        "sibling-item",
        "parser release artifact exists in a different worker",
        now,
        metadata={"source_session_id": "synthetic:sibling"},
    )

    bundle = build_bundle(
        _goal(now),
        _target(task="parser tests and release"),
        [source_item, sibling_item],
        [],
        ["synthetic:source"],
    )

    assert [item.id for item in bundle.items] == ["source-item"]
    assert bundle.items[0].metadata["source_session_id"] == "synthetic:source"


def test_supported_verification_becomes_traceable_test_evidence() -> None:
    now = datetime.now(UTC)
    pytest_event = HarnessEvent(
        event_id="pytest-event",
        ts=now - timedelta(seconds=1),
        harness_type=HarnessType.SYNTHETIC,
        session_id="synthetic:source",
        project_id="demo",
        event_type=EventType.SHELL,
        command="pytest -q",
        process_state={"pytest": {"ok": True}},
    )
    stop_event = HarnessEvent(
        event_id="stop-event",
        ts=now,
        harness_type=HarnessType.SYNTHETIC,
        session_id="synthetic:source",
        project_id="demo",
        event_type=EventType.STOP,
        message_delta="All parser tests passed.",
    )
    verification = {
        "status": "supported",
        "verdicts": [
            {
                "status": "supported",
                "claim": {
                    "kind": "tests_pass",
                    "statement": "All parser tests passed.",
                    "source_event_id": "stop-event",
                },
                "evidence": ["pytest_ok=true"],
            }
        ],
    }

    items = items_from_verification(
        "demo",
        "goal_context",
        stop_event,
        verification,
        [pytest_event, stop_event],
    )

    assert len(items) == 1
    assert items[0].provenance == SourceKind.TEST
    assert items[0].source_refs == ["stop-event", "pytest-event"]
    assert items[0].metadata["verified"] is True
    bundle = build_bundle(_goal(now), _target(task="parser tests"), items, [], [])
    assert bundle.direct_evidence == [items[0].content]


def test_rejected_approach_and_unresolved_question_shape_the_handoff_bundle() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    rejected = _item(
        "rejected",
        "Do not rewrite the evaluator as a new service",
        now,
        kind=ContextKind.DECISION,
        provenance=SourceKind.HUMAN,
        metadata={"kind": "rejected_approach", "status": "active"},
    )
    unresolved = _item(
        "unresolved",
        "Which checkpoint format should survive the migration?",
        now,
        kind=ContextKind.DECISION,
        provenance=SourceKind.HUMAN,
        metadata={"kind": "unresolved_question", "status": "uncertain", "unresolved": True},
    )
    artifact = _item(
        "artifact",
        "parser tests release artifact path",
        now,
        kind=ContextKind.ARTIFACT,
        metadata={"files": ["artifacts/parser.json"]},
    )
    frontend_noise = _item(
        "noise",
        "release artifact for frontend pet sprites atlas",
        now,
        kind=ContextKind.ARTIFACT,
    )

    bundle = build_bundle(
        goal,
        _target(task="parser tests"),
        [frontend_noise, rejected, unresolved, artifact],
        [],
        [],
    )

    assert rejected.content in bundle.do_not_redo
    assert bundle.next_objective == unresolved.content
    assert "artifacts/parser.json" in bundle.deep_links
    assert "Continue the attached goal" not in bundle.next_objective
    serialized = bundle.model_dump_json()
    assert '"kind":"rejected_approach"' in serialized or "rejected_approach" in serialized


def test_superseded_decision_context_is_excluded_even_without_stale_timestamp() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    target = _target(task="parser tests")
    retired = _item(
        "retired-decision",
        "Use the obsolete parser decision",
        now,
        kind=ContextKind.DECISION,
        provenance=SourceKind.HUMAN,
        metadata={"kind": "decision", "status": "superseded"},
    )
    active = _item(
        "active-decision",
        "Use the current parser decision",
        now,
        kind=ContextKind.DECISION,
        provenance=SourceKind.HUMAN,
        metadata={"kind": "decision", "status": "active"},
    )

    assert score_item(retired, goal, target, now=now) == -1.0
    bundle = build_bundle(goal, target, [retired, active], [], [])
    assert retired.id not in {item.id for item in bundle.items}
    assert active.id in {item.id for item in bundle.items}
