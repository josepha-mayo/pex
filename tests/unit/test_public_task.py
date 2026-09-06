from datetime import UTC, datetime

import pytest
from pex_protocol.goal import Goal
from pex_supervisor.public_task import fill_empty_goal_lists_from_objective, parse_public_task


@pytest.mark.parametrize("fence", ["```", "~~~", "````", "~~~~"])
def test_public_task_does_not_promote_fenced_examples_to_goal_requirements(fence):
    task = (
        "Implement the actual feature.\n\n"
        f"{fence}markdown\n"
        "Acceptance criteria:\n- Example only, do not implement this\n"
        "Decisions:\n- Example decision, not an adopted choice\n"
        f"{fence}\n\n"
        "Acceptance criteria:\n- The real feature passes its tests\n"
    )
    parsed = parse_public_task(task)
    assert parsed["objective"] == task.strip()
    assert parsed["acceptance_criteria"] == ["The real feature passes its tests"]
    assert parsed["decisions"] == []
    filled = fill_empty_goal_lists_from_objective(_goal(objective=task))
    assert filled.acceptance_criteria == ["The real feature passes its tests"]


def test_fenced_example_requires_matching_character_and_sufficient_closing_length():
    task = (
        "Show this example.\n````markdown\n```\n~~~\n"
        "Constraints:\n- Still example text\n"
        "````\nConstraints:\n- Actual constraint\n"
    )
    assert parse_public_task(task)["constraints"] == ["Actual constraint"]
    assert parse_public_task("Example:\n```\nConstraints:\n- Not adopted")["constraints"] == []


def test_parse_public_task_keeps_unlabeled_blob_as_objective_only():
    parsed = parse_public_task("Implement slugify and run the public tests.")
    assert parsed["title"].startswith("Implement slugify")
    assert parsed["objective"] == "Implement slugify and run the public tests."
    assert parsed["acceptance_criteria"] == []
    assert parsed["constraints"] == []
    assert parsed["non_goals"] == []
    assert parsed["preferences"] == []
    assert parsed["evidence_requirements"] == []
    assert parsed["decisions"] == []
    assert parsed["rejected_approaches"] == []
    assert parsed["unresolved_questions"] == []


def test_parse_public_task_lifts_labeled_lists_without_dropping_trailing_prose():
    task = (
        "Create the release receipt.\n\n"
        "Acceptance criteria:\n\n"
        "- report.txt contains shipped\n"
        "- results.jsonl has 30 rows\n\n"
        "Constraints:\n"
        "- do not rewrite history\n\n"
        "Stop only when that artifact exists."
    )
    parsed = parse_public_task(task)
    assert parsed["objective"] == task.strip()
    assert parsed["acceptance_criteria"] == [
        "report.txt contains shipped",
        "results.jsonl has 30 rows",
    ]
    assert parsed["constraints"] == ["do not rewrite history"]
    assert "Stop only when that artifact exists." not in parsed["acceptance_criteria"]
    assert "Stop only when that artifact exists." in str(parsed["objective"])


def _goal(**kwargs) -> Goal:
    now = datetime.now(UTC)
    return Goal(
        id="g",
        project_id="p",
        title="t",
        objective=kwargs.pop("objective", "Finish eval"),
        created_at=now,
        updated_at=now,
        **kwargs,
    )


def test_fill_empty_goal_lists_extracts_labeled_objective_sections():
    goal = _goal(
        objective=(
            "Create the release receipt.\n\n"
            "Acceptance criteria:\n\n"
            "- report.txt contains shipped\n"
        )
    )
    filled = fill_empty_goal_lists_from_objective(goal)
    assert filled.acceptance_criteria == ["report.txt contains shipped"]
    assert filled.objective == goal.objective


def test_fill_empty_goal_lists_does_not_overwrite_explicit_acceptance():
    goal = _goal(
        objective=(
            "Create the release receipt.\n\n"
            "Acceptance criteria:\n\n"
            "- report.txt contains shipped\n"
        ),
        acceptance_criteria=["tests pass"],
    )
    filled = fill_empty_goal_lists_from_objective(goal)
    assert filled.acceptance_criteria == ["tests pass"]


def test_fill_empty_goal_lists_skips_explicit_empty_patch_fields():
    goal = _goal(
        objective=(
            "Create the release receipt.\n\n"
            "Acceptance criteria:\n\n"
            "- report.txt contains shipped\n"
        ),
        acceptance_criteria=[],
    )
    restored = fill_empty_goal_lists_from_objective(goal)
    assert restored.acceptance_criteria == ["report.txt contains shipped"]
    kept_empty = fill_empty_goal_lists_from_objective(
        goal,
        skip_fields={"acceptance_criteria"},
    )
    assert kept_empty.acceptance_criteria == []


def test_parse_public_task_lifts_preferences():
    parsed = parse_public_task(
        "Ship the evaluator.\n\n"
        "Preferences:\n"
        "- Prefer the smallest reversible change\n"
    )
    assert parsed["preferences"] == ["Prefer the smallest reversible change"]
    filled = fill_empty_goal_lists_from_objective(
        _goal(objective=str(parsed["objective"]))
    )
    assert filled.preferences == ["Prefer the smallest reversible change"]


def test_parse_public_task_lifts_decisions_rejected_and_unresolved():
    parsed = parse_public_task(
        "Migrate the ledger.\n\n"
        "Decisions:\n"
        "- Use PostgreSQL for the durable ledger\n\n"
        "Rejected approaches:\n"
        "- Do not rewrite the evaluator as a new service\n\n"
        "Unresolved questions:\n"
        "- Which checkpoint format should survive the migration?\n"
    )
    assert parsed["decisions"] == ["Use PostgreSQL for the durable ledger"]
    assert parsed["rejected_approaches"] == [
        "Do not rewrite the evaluator as a new service"
    ]
    assert parsed["unresolved_questions"] == [
        "Which checkpoint format should survive the migration?"
    ]
    from pex_supervisor.public_task import extracted_ledger_lists

    lists = extracted_ledger_lists(str(parsed["objective"]))
    assert lists["decisions"] == parsed["decisions"]
    assert lists["rejected_approaches"] == parsed["rejected_approaches"]
    assert lists["unresolved_questions"] == parsed["unresolved_questions"]
