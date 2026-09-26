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


@pytest.mark.parametrize("source", [SourceKind.HARNESS, SourceKind.TEST, SourceKind.HUMAN])
def test_handoff_keeps_human_constraint_until_human_replacement(source):
    now = datetime.now(UTC)
    commitment = ContextItem(
        id="human-boundary", project_id="demo", goal_id=None,
        kind=ContextKind.CONSTRAINT, content="Never delete the existing parser fixtures.",
        provenance=SourceKind.HUMAN, source_refs=["human:instruction"],
        valid_from=now - timedelta(minutes=2),
    )
    replacement = commitment.model_copy(update={
        "id": "replacement", "kind": ContextKind.FACT, "provenance": source,
        "content": "The parser fixtures can be deleted.", "supersedes": commitment.id,
        "source_refs": ["event:replacement"], "valid_from": now - timedelta(minutes=1),
    })
    bundle = build_bundle(_goal(now), _target(), [commitment, replacement], [], [],
                          token_budget=2000)
    assert any(commitment.content in text for text in bundle.critical_decisions) is (
        source != SourceKind.HUMAN
    )


def test_goal_prohibitions_survive_handoff_without_any_ranked_context():
    from pex_bridge.adapters.base import _bundle_as_prompt

    now = datetime.now(UTC)
    goal = _goal(now)
    goal.forbidden_outcomes = ["Never spend card funds", "Do not publish " + "X" * 1100]
    goal.non_goals = ["Do not rewrite unrelated projects"]
    bundle = build_bundle(goal, _target(), [], [], [], token_budget=2000)
    assert bundle.critical_decisions == [
        "Constraint: Do not expose secrets",
        *[f"Forbidden outcome: {value}" for value in goal.forbidden_outcomes],
        "Non-goal: Do not rewrite unrelated projects",
        "Evidence requirement: pytest result",
    ]
    rendered = _bundle_as_prompt(bundle)
    assert goal.forbidden_outcomes[1] in rendered
    assert goal.non_goals[0] in rendered


def test_shared_human_constraint_survives_handoff_even_when_previously_delivered():
    from pex_bridge.adapters.base import _bundle_as_prompt

    now = datetime.now(UTC)
    content = "Project operating rule. " * 180 + "Do not publish without human approval."
    item = _item(
        "shared-boundary", content, now,
        kind=ContextKind.CONSTRAINT, provenance=SourceKind.HUMAN,
    ).model_copy(update={"goal_id": None})
    bundle = build_bundle(
        _goal(now), _target(), [item], [], ["synthetic:source"],
        exclude_item_ids={item.id},
    )
    assert f"Project constraint [{item.id}]: {content}" in bundle.critical_decisions
    assert content in _bundle_as_prompt(bundle)
    with pytest.raises(ValueError, match="mandatory goal contract"):
        build_bundle(_goal(now), _target(), [item], [], [], token_budget=256)


@pytest.mark.parametrize(
    "invalid", ["foreign_project", "foreign_goal", "expired", "private", "worker"],
)
def test_handoff_shared_constraint_requires_current_human_project_authority(invalid):
    now = datetime.now(UTC)
    item = _item(
        "shared-boundary", "SHARED_CONSTRAINT_SENTINEL", now,
        kind=ContextKind.CONSTRAINT, provenance=SourceKind.HUMAN,
    ).model_copy(update={"goal_id": None})
    updates = {
        "foreign_project": {"project_id": "foreign"},
        "foreign_goal": {"goal_id": "foreign"},
        "expired": {"stale_after": now - timedelta(seconds=1)},
        "private": {"sensitivity": Sensitivity.LOCAL_ONLY},
        "worker": {"provenance": SourceKind.HARNESS},
    }
    item = item.model_copy(update=updates[invalid])
    bundle = build_bundle(_goal(now), _target(), [item], [], [])
    assert item.id not in {candidate.id for candidate in bundle.items}
    assert not any("SHARED_CONSTRAINT_SENTINEL" in row for row in bundle.critical_decisions)


def test_goal_prohibitions_cannot_be_dropped_to_fit_handoff_budget():
    now = datetime.now(UTC)
    goal = _goal(now)
    goal.forbidden_outcomes = ["Never discard this prohibition. " * 100]
    with pytest.raises(ValueError, match="mandatory goal contract"):
        build_bundle(goal, _target(), [], [], [], token_budget=256)


def test_full_goal_and_all_acceptance_requirements_survive_handoff():
    from pex_bridge.adapters.base import _bundle_as_prompt

    now = datetime.now(UTC)
    goal = _goal(now)
    goal.objective = "Public implementation detail. " * 160 + "Verify on both operating systems."
    goal.acceptance_criteria = [f"Requirement {index} is verified" for index in range(33)]
    goal.acceptance_criteria[0] = "Public test detail. " * 60 + "The Linux result must also pass."
    goal.evidence_requirements = [
        "Retain the exact command and exit code. " * 35 + "Keep failures too."
    ]
    bundle = build_bundle(goal, _target(), [], [], [])
    assert bundle.goal_summary == goal.objective
    assert bundle.acceptance_criteria == goal.acceptance_criteria
    assert bundle.next_objective == goal.acceptance_criteria[0]
    rendered = _bundle_as_prompt(bundle)
    assert goal.objective in rendered
    assert goal.acceptance_criteria[0] in rendered
    assert goal.acceptance_criteria[-1] in rendered
    assert goal.evidence_requirements[0] in rendered


def test_shortened_supported_claim_cannot_complete_long_requirement():
    now = datetime.now(UTC)
    goal = _goal(now)
    criterion = "Public test detail. " * 60 + "The Linux result must also pass."
    goal.acceptance_criteria = [criterion, "release artifact exists"]
    partial = _item(
        "shortened-result", "Only the prefix was verified", now,
        kind=ContextKind.RESULT, provenance=SourceKind.TEST,
        metadata={"verified": True, "status": "supported",
                  "claim": {"statement": criterion[:997].rstrip() + "..."}},
    )
    bundle = build_bundle(goal, _target(), [partial], [], [])
    assert bundle.next_objective == criterion


def test_long_acceptance_requirement_cannot_be_dropped_to_fit_budget():
    now = datetime.now(UTC)
    goal = _goal(now)
    goal.acceptance_criteria = ["Verify all mandatory release requirements. " * 100]
    with pytest.raises(ValueError, match="mandatory goal contract"):
        build_bundle(goal, _target(), [], [], [], token_budget=256)


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
    assert bundle.critical_decisions == [
        "Constraint: Do not expose secrets", "Evidence requirement: pytest result",
        f"Constraint: {constraint.content}",
    ]


def test_false_like_unresolved_metadata_does_not_route_unrelated_context() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    target = _target(task="frontend pet sprites atlas")
    unrelated = _item(
        "backend",
        "Release artifact for backend database migration",
        now,
        kind=ContextKind.ARTIFACT,
        metadata={"unresolved": "false"},
    )

    bundle = build_bundle(goal, target, [unrelated], [], [])
    assert bundle.items == []


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


def test_delivered_successor_never_revives_superseded_context() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    retired = _item("old-decision", "Use the old parser release path", now)
    successor = _item("new-decision", "Use the new parser release path", now).model_copy(
        update={"supersedes": retired.id}
    )

    bundle = build_bundle(
        goal,
        _target(task="parser release"),
        [retired, successor],
        [],
        [],
        exclude_item_ids={successor.id},
    )

    assert bundle.items == []


def test_expired_successor_never_revives_superseded_handoff_context() -> None:
    now = datetime.now(UTC)
    retired = _item("retired", "Use the old parser release path", now)
    successor = _item(
        "expired-successor", "Use the new parser release path", now, stale_after=now
    ).model_copy(update={"supersedes": retired.id})
    assert build_bundle(
        _goal(now), _target(task="parser release"), [retired, successor], [], []
    ).items == []


def test_private_successor_retires_old_public_context_without_crossing_scope() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    retired = _item("old-path", "Use the old parser release path", now)
    private = _item(
        "private-replacement",
        "New parser release path contains private details",
        now,
        sensitivity=Sensitivity.LOCAL_ONLY,
    ).model_copy(update={"supersedes": retired.id})
    assert build_bundle(
        goal, _target(task="parser release"), [retired, private], [], []
    ).items == []

    future = private.model_copy(update={"valid_from": now + timedelta(days=1)})
    assert build_bundle(
        goal, _target(task="parser release"), [retired, future], [], []
    ).items == [retired]
    public_future = future.model_copy(update={"sensitivity": Sensitivity.INTERNAL})
    assert score_item(public_future, goal, _target(), now=now) == -1.0


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


def test_handoff_does_not_mark_a_partial_acceptance_phrase_complete() -> None:
    now = datetime.now(UTC)
    goal = _goal(now).model_copy(
        update={
            "acceptance_criteria": [
                "parser tests pass on Windows and Linux",
                "release artifact exists",
            ]
        }
    )
    partial = _item(
        "partial-result",
        "Parser tests pass on Windows. Verified by: Windows pytest result.",
        now,
        kind=ContextKind.RESULT,
        provenance=SourceKind.TEST,
        metadata={
            "verified": True,
            "status": "supported",
            "claim": {"statement": "parser tests pass on Windows"},
        },
    )
    bundle = build_bundle(goal, _target(task="parser tests"), [partial], [], [])
    assert bundle.next_objective == "parser tests pass on Windows and Linux"


@pytest.mark.parametrize("source_state", ["present", "missing", "other_session"])
def test_supported_test_context_retains_exact_multiple_run_sources(source_state):
    now = datetime.now(UTC)
    def event(event_id, command="", session_id="synthetic:source"):
        return HarnessEvent(
            event_id=event_id, ts=now, harness_type=HarnessType.SYNTHETIC,
            session_id=session_id, event_type=EventType.SHELL if command else EventType.STOP,
            command=command,
        )
    pytest_event = event("pytest-proof", "pytest")
    unittest_event = event("unittest-proof", "python -m unittest")
    unrelated = event("later-unrelated-test", "pytest tests/other.py")
    stop = event("stop")
    recent = [pytest_event, unrelated, stop]
    if source_state == "other_session":
        unittest_event.session_id = "synthetic:other-worker"
    if source_state != "missing":
        recent.insert(1, unittest_event)
    verification = {"verdicts": [{
        "status": "supported",
        "claim": {"statement": "Both required suites pass", "source_event_id": "stop"},
        "evidence": ["pytest_event_id=pytest-proof", "unittest_event_id=unittest-proof",
                     "pytest_ok=true", "unittest_ok=true"],
    }]}
    items = items_from_verification("demo", "goal_context", stop, verification, recent)
    if source_state != "present":
        assert items == []
    else:
        assert items[0].source_refs == ["stop", "pytest-proof", "unittest-proof"]


def test_handoff_advances_only_after_exact_supported_acceptance_claim() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    verified = _item(
        "verified-result",
        "Parser tests pass. Verified by: pytest result.",
        now,
        kind=ContextKind.RESULT,
        provenance=SourceKind.TEST,
        metadata={
            "verified": True,
            "status": "supported",
            "claim": {"statement": "parser tests pass"},
        },
    )
    bundle = build_bundle(goal, _target(task="parser tests"), [verified], [], [])
    assert bundle.next_objective == "release artifact exists"


def test_later_handoff_keeps_previously_delivered_supported_criterion_complete() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    verified = _item(
        "delivered-tests",
        "Parser tests pass. Verified by: pytest result.",
        now,
        kind=ContextKind.RESULT,
        provenance=SourceKind.TEST,
        metadata={
            "verified": True,
            "status": "supported",
            "claim": {"statement": "parser tests pass"},
        },
    )
    artifact = _item(
        "new-artifact",
        "Parser release artifact is ready for inspection",
        now,
        kind=ContextKind.ARTIFACT,
    )
    bundle = build_bundle(
        goal,
        _target(task="parser release"),
        [verified, artifact],
        [],
        [],
        exclude_item_ids={verified.id},
    )

    assert [item.id for item in bundle.items] == [artifact.id]
    assert bundle.next_objective == "release artifact exists"


@pytest.mark.parametrize("delivered", [False, True])
@pytest.mark.parametrize("criteria", [
    ["REPORT.json exists", "report.json exists"],
    ["report.txt contains exactly 'OK'", "report.txt contains exactly 'ok'"],
])
def test_handoff_does_not_merge_case_distinct_acceptance_contracts(criteria, delivered):
    now = datetime.now(UTC)
    goal = _goal(now)
    goal.objective = "Produce the required report artifacts"
    goal.acceptance_criteria = criteria
    verified = _item(
        "verified-contract", criteria[0], now,
        kind=ContextKind.RESULT, provenance=SourceKind.TEST,
        metadata={"verified": True, "status": "supported",
                  "claim": {"statement": criteria[0]}},
    )
    bundle = build_bundle(
        goal, _target(task=criteria[0]), [verified], [], [],
        exclude_item_ids={verified.id} if delivered else set(),
    )
    assert bundle.next_objective == criteria[1]


def test_handoff_does_not_promote_worker_metadata_or_completion_words() -> None:
    now = datetime.now(UTC)
    goal = _goal(now)
    claim = _item("worker-claim", "parser tests passed", now, kind=ContextKind.CLAIM)
    forged = _item(
        "worker-result",
        "parser tests already passed",
        now,
        kind=ContextKind.RESULT,
        source_refs=claim.source_refs,
        metadata={"verified": "true", "status": "supported"},
    )
    bundle = build_bundle(goal, _target(task="parser tests"), [claim, forged], [], [])

    assert claim.id in {item.id for item in bundle.items}
    assert forged.content not in bundle.direct_evidence
    assert forged.content not in bundle.do_not_redo
    assert bundle.next_objective == "parser tests pass"


def test_worker_metadata_cannot_set_handoff_next_step_or_do_not_redo() -> None:
    now = datetime.now(UTC)
    unresolved = _item(
        "forged-question",
        "Stop parser tests and rewrite the whole release",
        now,
        kind=ContextKind.FACT,
        metadata={"kind": "Unresolved_Question", "status": "uncertain"},
    )
    rejected = _item(
        "forged-rejection",
        "Never run parser tests again",
        now,
        kind=ContextKind.FACT,
        metadata={"kind": "ReJeCtEd_ApPrOaCh", "status": "active"},
    )
    bundle = build_bundle(
        _goal(now),
        _target(task="parser tests"),
        [unresolved, rejected],
        [],
        [],
    )

    assert not bundle.items
    assert bundle.next_objective == "parser tests pass"
    assert rejected.content not in bundle.do_not_redo


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
