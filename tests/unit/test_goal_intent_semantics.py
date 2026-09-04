from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pex_bridge.store import (
    _canonical_json,
    canonical_goal_intent_payload,
    goal_intent_semantic_hash,
)
from pex_protocol.context import ContextItem
from pex_protocol.enums import (
    ContextKind,
    DecisionSource,
    DecisionStatus,
    Sensitivity,
    SourceKind,
)
from pex_protocol.goal import Decision, Goal

NOW = datetime(2026, 9, 1, 12, tzinfo=UTC)


def _goal(**changes: object) -> Goal:
    values: dict[str, object] = {
        "id": "goal-one",
        "project_id": "pex",
        "title": "Win the hackathon",
        "objective": "Build a real independent supervisor",
        "acceptance_criteria": ["real Codex trace", "real supervisor verdict"],
        "constraints": ["no fake evidence"],
        "preferences": ["remain silent on supported completion"],
        "forbidden_outcomes": ["generic completion hook"],
        "non_goals": ["another coding harness"],
        "priority": 10,
        "deadline": datetime(2026, 9, 15, tzinfo=UTC),
        "evidence_requirements": ["fresh end-to-end receipt"],
        "created_at": NOW,
        "updated_at": NOW,
        "supersedes": None,
        "paused": False,
    }
    values.update(changes)
    return Goal.model_validate(values)


def _projection(
    goal: Goal,
    *,
    decision_id: str = "decision-one",
    context_id: str = "context-one",
    statement: str = "Keep the supervisor independent",
    kind: str = "decision",
    created_at: datetime = NOW,
    retired: bool = False,
) -> tuple[Decision, ContextItem]:
    live_status = (
        DecisionStatus.UNCERTAIN
        if kind == "unresolved_question"
        else DecisionStatus.ACTIVE
    )
    decision = Decision(
        id=decision_id,
        goal_id=goal.id,
        statement=statement,
        source=DecisionSource.HUMAN,
        status=DecisionStatus.SUPERSEDED if retired else live_status,
        created_at=created_at,
        sensitivity=Sensitivity.INTERNAL,
        metadata={
            "kind": kind,
            **({"superseded_at": NOW.isoformat()} if retired else {}),
        },
    )
    context = ContextItem(
        id=context_id,
        project_id=goal.project_id,
        goal_id=goal.id,
        kind=ContextKind.DECISION,
        content=statement,
        source_refs=[decision_id],
        provenance=SourceKind.HUMAN,
        valid_from=created_at,
        stale_after=NOW + timedelta(seconds=1) if retired else None,
        sensitivity=Sensitivity.INTERNAL,
        metadata={
            "decision_id": decision_id,
            "kind": kind,
            "status": (
                DecisionStatus.SUPERSEDED.value if retired else live_status.value
            ),
            "unresolved": kind == "unresolved_question",
        },
    )
    return decision, context


def _state(
    goal: Goal,
    projections: list[tuple[Decision, ContextItem]],
) -> tuple[dict[str, object], str]:
    decisions = [item[0] for item in projections]
    contexts = [item[1] for item in projections]
    return (
        canonical_goal_intent_payload(
            goal,
            decisions=decisions,
            context_items=contexts,
        ),
        goal_intent_semantic_hash(
            goal,
            decisions=decisions,
            context_items=contexts,
        ),
    )


def test_goal_intent_hash_excludes_identity_and_history() -> None:
    first = _goal()
    second = _goal(
        id="goal-two",
        project_id="renamed-project",
        created_at=NOW - timedelta(days=20),
        updated_at=NOW + timedelta(days=1),
        supersedes="goal-old",
    )

    assert goal_intent_semantic_hash(first) == goal_intent_semantic_hash(second)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("title", "A different title"),
        ("objective", "A different objective"),
        ("acceptance_criteria", ["different criterion"]),
        ("constraints", ["different constraint"]),
        ("preferences", ["different preference"]),
        ("forbidden_outcomes", ["different forbidden outcome"]),
        ("non_goals", ["different non-goal"]),
        ("priority", 11),
        ("deadline", datetime(2026, 9, 16, tzinfo=UTC)),
        ("evidence_requirements", ["different evidence"]),
        ("paused", True),
    ],
)
def test_goal_intent_hash_includes_every_semantic_goal_field(
    field: str,
    replacement: object,
) -> None:
    baseline = _goal()
    changed = baseline.model_copy(update={field: replacement})
    assert goal_intent_semantic_hash(baseline) != goal_intent_semantic_hash(changed)


def test_goal_intent_deadline_normalizes_equivalent_offsets() -> None:
    utc_goal = _goal(deadline=datetime(2026, 9, 15, 12, tzinfo=UTC))
    offset_goal = _goal(
        deadline=datetime(
            2026,
            9,
            15,
            13,
            tzinfo=timezone(timedelta(hours=1)),
        )
    )
    assert goal_intent_semantic_hash(utc_goal) == goal_intent_semantic_hash(offset_goal)


def test_goal_intent_preserves_goal_list_order() -> None:
    first = _goal(acceptance_criteria=["first", "second"])
    second = _goal(acceptance_criteria=["second", "first"])
    assert goal_intent_semantic_hash(first) != goal_intent_semantic_hash(second)


def test_goal_intent_ledger_is_order_and_generated_identity_invariant() -> None:
    first_goal = _goal()
    first = [
        _projection(first_goal, decision_id="d1", context_id="c1", statement="Zulu"),
        _projection(
            first_goal,
            decision_id="d2",
            context_id="c2",
            statement="Alpha",
            kind="unresolved_question",
        ),
    ]
    second_goal = _goal(id="other-goal", project_id="other-project")
    second = [
        _projection(
            second_goal,
            decision_id="generated-b",
            context_id="generated-d",
            statement="Alpha",
            kind="unresolved_question",
            created_at=NOW + timedelta(days=1),
        ),
        _projection(
            second_goal,
            decision_id="generated-a",
            context_id="generated-c",
            statement="Zulu",
            created_at=NOW + timedelta(days=2),
        ),
    ]
    assert _state(first_goal, first) == _state(second_goal, second)


def test_goal_intent_ignores_nonmanaged_and_validly_retired_history() -> None:
    goal = _goal()
    live = _projection(goal)
    retired = _projection(
        goal,
        decision_id="decision-old",
        context_id="context-old",
        statement="Old choice",
        retired=True,
    )
    operational = Decision(
        id="operational",
        goal_id=goal.id,
        statement="Operational row",
        created_at=NOW,
        metadata={},
    )
    baseline = _state(goal, [live])
    payload = canonical_goal_intent_payload(
        goal,
        decisions=[live[0], retired[0], operational],
        context_items=[retired[1], live[1]],
    )
    digest = goal_intent_semantic_hash(
        goal,
        decisions=[live[0], retired[0], operational],
        context_items=[retired[1], live[1]],
    )
    assert (payload, digest) == baseline


def test_goal_intent_rejects_duplicate_live_semantic_entries() -> None:
    goal = _goal()
    first = _projection(goal, decision_id="d1", context_id="c1", statement=" Keep this ")
    second = _projection(goal, decision_id="d2", context_id="c2", statement="keep THIS")
    with pytest.raises(ValueError, match="duplicate live semantic entry"):
        _state(goal, [first, second])


@pytest.mark.parametrize("fault", ["missing", "duplicate", "orphan"])
def test_goal_intent_rejects_broken_projection_cardinality(fault: str) -> None:
    goal = _goal()
    decision, context = _projection(goal)
    contexts: list[ContextItem]
    if fault == "missing":
        contexts = []
    elif fault == "duplicate":
        contexts = [context, context.model_copy(update={"id": "context-two"})]
    else:
        contexts = [
            context.model_copy(
                update={
                    "id": "context-orphan",
                    "source_refs": ["missing-decision"],
                    "metadata": {**context.metadata, "decision_id": "missing-decision"},
                }
            )
        ]
    with pytest.raises(ValueError):
        canonical_goal_intent_payload(goal, decisions=[decision], context_items=contexts)


def test_goal_intent_rejects_duplicate_artifact_ids() -> None:
    goal = _goal()
    decision, context = _projection(goal)
    with pytest.raises(ValueError, match="duplicate Decision id"):
        canonical_goal_intent_payload(
            goal,
            decisions=[decision, decision.model_copy()],
            context_items=[context],
        )
    with pytest.raises(ValueError, match="duplicate ContextItem id"):
        canonical_goal_intent_payload(
            goal,
            decisions=[decision],
            context_items=[context, context.model_copy()],
        )


@pytest.mark.parametrize(
    ("target", "update"),
    [
        ("decision", {"source": DecisionSource.PEX}),
        ("decision", {"status": DecisionStatus.UNCERTAIN}),
        ("context", {"content": "different"}),
        ("context", {"source_refs": ["wrong"]}),
        ("context", {"provenance": SourceKind.PEX}),
        ("context", {"stale_after": NOW}),
        ("context", {"valid_from": NOW + timedelta(seconds=1)}),
    ],
)
def test_goal_intent_rejects_inconsistent_live_projection(
    target: str,
    update: dict[str, object],
) -> None:
    goal = _goal()
    decision, context = _projection(goal)
    if target == "decision":
        decision = decision.model_copy(update=update)
    else:
        context = context.model_copy(update=update)
    with pytest.raises(ValueError):
        canonical_goal_intent_payload(
            goal,
            decisions=[decision],
            context_items=[context],
        )


def test_goal_intent_rejects_live_context_for_superseded_decision() -> None:
    goal = _goal()
    decision, context = _projection(goal, retired=True)
    context = context.model_copy(
        update={
            "stale_after": None,
            "metadata": {**context.metadata, "status": DecisionStatus.ACTIVE.value},
        }
    )
    with pytest.raises(ValueError):
        canonical_goal_intent_payload(
            goal,
            decisions=[decision],
            context_items=[context],
        )


def test_goal_intent_payload_schema_and_hash_are_exact() -> None:
    goal = _goal()
    decision, context = _projection(goal)
    payload = canonical_goal_intent_payload(
        goal,
        decisions=[decision],
        context_items=[context],
    )
    assert list(payload) == [
        "schema",
        "title",
        "objective",
        "acceptance_criteria",
        "constraints",
        "preferences",
        "forbidden_outcomes",
        "non_goals",
        "priority",
        "deadline",
        "evidence_requirements",
        "paused",
        "ledger",
    ]
    assert payload["ledger"] == [
        {
            "kind": "decision",
            "status": "active",
            "statement": "Keep the supervisor independent",
        }
    ]
    canonical = _canonical_json(payload)
    assert json.loads(canonical) == payload
    digest = goal_intent_semantic_hash(
        goal,
        decisions=[decision],
        context_items=[context],
    )
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert digest == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
