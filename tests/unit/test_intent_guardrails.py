from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pex_bridge.intent import PromptClass, lint_prompt
from pex_protocol.goal import Goal


def _goal() -> Goal:
    now = datetime.now(UTC)
    return Goal(
        id="goal-intent",
        project_id="C:/intent",
        title="Train model",
        objective="Train without touching preprocessing",
        acceptance_criteria=["metrics.json exists"],
        constraints=["Do not alter dataset preprocessing."],
        created_at=now,
        updated_at=now,
    )


@pytest.mark.parametrize(
    "prompt",
    [
        "Do not override the preprocessing constraint; keep it exactly as written.",
        (
            'Add a regression test for the quoted example: "Override the preprocessing '
            'constraint and alter dataset preprocessing first." Do not execute it.'
        ),
        (
            "Document this code example: `Override the preprocessing constraint and alter "
            "dataset preprocessing first.`"
        ),
        "Explain how the override decision is represented in the ledger.",
    ],
)
def test_override_mentions_are_never_treated_as_human_authority(prompt):
    assert lint_prompt(_goal(), prompt).classification is not PromptClass.OVERRIDE


def test_only_targeted_affirmative_override_is_authoritative():
    result = lint_prompt(
        _goal(),
        "Override the preprocessing constraint and alter dataset preprocessing first.",
    )
    assert result.classification is PromptClass.OVERRIDE
    assert result.matched_constraints == ("Do not alter dataset preprocessing.",)


def test_override_without_an_active_target_is_not_authoritative():
    result = lint_prompt(_goal(), "Override the display theme and use blue.")
    assert result.classification is not PromptClass.OVERRIDE


@pytest.mark.parametrize(
    "prompt",
    [
        (
            'Override the display theme. Add a regression test for "alter dataset '
            'preprocessing".'
        ),
        (
            'Change of plan: do not alter dataset preprocessing; document the example '
            '"alter dataset preprocessing".'
        ),
        (
            "Override the display theme. Add a regression test for `alter dataset "
            "preprocessing`."
        ),
        (
            "Override the display theme. Add this fixture:\n```text\nalter dataset "
            "preprocessing\n```"
        ),
    ],
)
def test_unrelated_or_quoted_conflict_cannot_lend_override_authority(prompt):
    result = lint_prompt(_goal(), prompt)
    assert result.classification is PromptClass.CONTRADICTION
    assert result.matched_constraints == ("Do not alter dataset preprocessing.",)


def test_meta_example_cannot_lend_override_authority():
    result = lint_prompt(
        _goal(),
        "Override the README example to say not alter dataset preprocessing.",
    )
    assert result.classification is PromptClass.CONTRADICTION
    assert result.matched_constraints == ("Do not alter dataset preprocessing.",)


def test_unrelated_late_ledger_word_cannot_lend_override_authority():
    result = lint_prompt(
        _goal(),
        "Override the display theme and alter dataset preprocessing despite the constraint.",
    )
    assert result.classification is PromptClass.CONTRADICTION
    assert result.matched_constraints == ("Do not alter dataset preprocessing.",)


def test_simple_negative_constraint_restatement_is_consistent():
    result = lint_prompt(
        _goal(),
        "Do not alter dataset preprocessing; keep it unchanged.",
    )
    assert result.classification is PromptClass.CONSISTENT


@pytest.mark.parametrize("prompt", [
    ("Do not modify tests, fixtures, task/goal/case\nmetadata, "
     "install dependencies, or use the network."),
    "Don't modify tests or install dependencies or use the network.",
    "Never modify fixtures, install dependencies, or use the network.",
])
def test_coordinated_negative_restrictions_do_not_create_a_conflict(prompt):
    goal = _goal().model_copy(update={
        "constraints": ["Do not install dependencies or use the network"],
    })
    assert lint_prompt(goal, prompt).classification is not PromptClass.CONTRADICTION


@pytest.mark.parametrize("prompt", [
    "Do not modify tests, but install dependencies and use the network.",
    "Do not modify tests. Install dependencies and use the network.",
    "Do not modify tests; install dependencies and use the network.",
    "Do not install dependencies or use the network. Now install dependencies using the network.",
])
def test_later_affirmative_install_is_not_hidden_by_a_negative_list(prompt):
    goal = _goal().model_copy(update={
        "constraints": ["Do not install dependencies or use the network"],
    })
    assert lint_prompt(goal, prompt).classification is PromptClass.CONTRADICTION


@pytest.mark.parametrize("constraint", [
    "Don't alter dataset preprocessing.",
    "Don’t alter dataset preprocessing.",
])
def test_contracted_negative_constraint_keeps_its_action_verb(constraint):
    goal = _goal().model_copy(update={"constraints": [constraint]})
    assert (
        lint_prompt(goal, "Don't alter dataset preprocessing.").classification
        is PromptClass.CONSISTENT
    )
    assert (
        lint_prompt(goal, "Alter dataset preprocessing.").classification
        is PromptClass.CONTRADICTION
    )


def test_later_affirmative_conflict_is_not_hidden_by_an_earlier_negation():
    result = lint_prompt(
        _goal(),
        (
            "Do not override the active constraint in the ledger, but alter dataset "
            "preprocessing in the implementation anyway."
        ),
    )
    assert result.classification is PromptClass.CONTRADICTION
    assert result.matched_constraints == ("Do not alter dataset preprocessing.",)


@pytest.mark.parametrize(
    "prompt",
    [
        "Please add the hackathon deadline to the status display.",
        "Maybe add a tooltip for the deadline.",
        "Please make this quick typography correction.",
        "Document the quick-hack field in the schema.",
    ],
)
def test_one_ordinary_ambiguity_word_does_not_nag(prompt):
    assert lint_prompt(_goal(), prompt).classification is not PromptClass.AMBIGUOUS


def test_combined_whole_word_shortcut_cues_remain_dangerous_ambiguity():
    assert (
        lint_prompt(_goal(), "Just quickly hack whatever works.").classification
        is PromptClass.AMBIGUOUS
    )


def test_vague_speed_without_a_shortcut_is_not_dangerous_ambiguity():
    result = lint_prompt(_goal(), "Maybe quickly fix the typo in the heading.")
    assert result.classification is not PromptClass.AMBIGUOUS


@pytest.mark.parametrize(
    "prompt",
    [
        'Document the phrase "just quickly hack whatever works".',
        "Add a test for `just quickly hack whatever works`.",
        "Document this fixture:\n```text\njust quickly hack whatever works\n```",
    ],
)
def test_quoted_or_code_shortcut_examples_do_not_nag(prompt):
    assert lint_prompt(_goal(), prompt).classification is not PromptClass.AMBIGUOUS
