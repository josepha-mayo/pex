import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.opencode_completion import (
    QuietCompletionFence,
    belongs_to_case,
    completed_generation,
    recovery_interventions_succeeded,
    review_completed_for_event,
    semantic_reviews_succeeded,
)


def recovery_rows():
    text = "Create final.txt and verify it."
    return [
        {
            "action_taken": "SEND_NUDGE",
            "result": "sent",
            "outcome": "goal_evidence_supported",
            "helped": True,
            "worker_response": "assistant",
            "proposed_action": {"payload": {"text": text}},
            "metadata": {
                "used_llm": True,
                "inference_status": "completed",
                "outcome_final": True,
                "independent_verifier": {"approved": True, "status": "approved"},
            },
        },
        {
            "action_taken": "NOOP",
            "result": "noop",
            "metadata": {
                "used_llm": True,
                "inference_status": "completed",
                "verification": {"acceptance_status": "supported"},
            },
        },
    ], [text]


def test_recovery_requires_exact_helped_correction_then_supported_noop():
    rows, followups = recovery_rows()
    assert recovery_interventions_succeeded(rows, followups)


@pytest.mark.parametrize("mutation", [
    lambda rows, followups: followups.append("again"),
    lambda rows, followups: followups.__setitem__(0, "different"),
    lambda rows, followups: rows[0].__setitem__("action_taken", "CONTINUE"),
    lambda rows, followups: rows[0].__setitem__("outcome", "worker_responded"),
    lambda rows, followups: rows[0].__setitem__("helped", None),
    lambda rows, followups: rows[0].__setitem__("worker_response", ""),
    lambda rows, followups: rows[0]["metadata"].__setitem__("outcome_final", False),
    lambda rows, followups: rows[0]["metadata"]["independent_verifier"].__setitem__(
        "approved", False
    ),
    lambda rows, followups: rows[1]["metadata"]["verification"].__setitem__(
        "acceptance_status", "unknown"
    ),
    lambda rows, followups: rows.reverse(),
])
def test_recovery_rejects_missing_or_ambiguous_causal_proof(mutation):
    rows, followups = recovery_rows()
    mutation(rows, followups)
    assert not recovery_interventions_succeeded(rows, followups)


@pytest.mark.parametrize("expected,event_session,observed_session,accepted", [
    (None, "case", "case", False),
    ("", "", "", False),
    ("case", "case", "case", True),
    ("case", "previous-case", "previous-case", False),
    ("case", "previous-case", "case", False),
    ("case", "case", "previous-case", False),
    ("case", None, "case", False),
    ("case", "case", None, False),
])
def test_global_events_are_bound_to_the_ready_case(
    expected, event_session, observed_session, accepted
):
    assert belongs_to_case(
        SimpleNamespace(session_id=event_session),
        SimpleNamespace(id=observed_session),
        expected,
    ) is accepted


def test_missing_event_or_session_is_not_a_case_observation():
    assert not belongs_to_case(None, None, "case")


def test_runner_filters_before_capture_and_ingestion_and_binds_before_prompt():
    runner = Path(__file__).resolve().parents[2] / "scripts/opencode_quiet_ten.py"
    source = runner.read_text(encoding="utf-8")
    guard = source.index("if not belongs_to_case(event, observed_session, case_session_id):")
    assert guard < source.index('if event.event_type.value == "stop"')
    assert guard < source.index("await pipeline.ingest_event(event, observed_session)")
    assert source.index("await store.upsert_session(session)") < source.index(
        "case_session_id = session.id"
    ) < source.index('f"/session/{vendor}/prompt_async"')


def review(used_llm=True, status="completed"):
    return {"plan": {"supervisor_result": {
        "used_llm": used_llm, "inference_status": status,
    }}}


def test_quiet_case_requires_a_real_completed_review():
    assert not semantic_reviews_succeeded([])
    assert not semantic_reviews_succeeded([{"plan": None}, review(False, "not_attempted")])
    assert semantic_reviews_succeeded([review(), {"plan": None}, review(False, "not_attempted")])


@pytest.mark.parametrize("used_llm", [True, False])
@pytest.mark.parametrize("status", ["failed", "timeout"])
def test_prior_success_cannot_hide_inference_failure(used_llm, status):
    failed = review(used_llm, status)
    assert not semantic_reviews_succeeded([review(), failed])
    assert not semantic_reviews_succeeded([failed, review()])


@pytest.mark.parametrize("invalid", [
    None, {"plan": "bad"}, {"plan": {"supervisor_result": "bad"}},
    review(False, "completed"), review(True, "not_attempted"),
    review("true", "completed"), review(True, None), review(True, "unknown"),
])
def test_malformed_or_contradictory_reviews_cannot_be_hidden(invalid):
    assert not semantic_reviews_succeeded([review(), invalid])


def test_runner_audits_unfiltered_journal_not_only_used_llm_rows():
    runner = Path(__file__).resolve().parents[2] / "scripts/opencode_quiet_ten.py"
    source = runner.read_text(encoding="utf-8")
    assert "semantic_completed = semantic_reviews_succeeded(journal)" in source


def completion_review(**changes):
    row = review()
    row.update(event_id="stop", session_id="session", goal_id="goal", state="complete")
    row.update(changes)
    return row


def bound_review(journal, event_id="stop"):
    return review_completed_for_event(
        journal, event_id=event_id, session_id="session", goal_id="goal"
    )


def test_earlier_success_does_not_prove_completion_event_review():
    earlier = completion_review(event_id="progress")
    assert not bound_review([earlier])
    assert bound_review([earlier, completion_review()])
    assert not bound_review([earlier, completion_review(plan=None)])
    assert not bound_review([completion_review(), completion_review()])


@pytest.mark.parametrize("changes", [
    {"session_id": "other"}, {"goal_id": "other"}, {"state": "planned"},
    {"state": "record_only_complete"}, {"plan": "bad"},
    {"plan": review(False, "not_attempted")["plan"]},
    {"plan": review(True, "failed")["plan"]},
])
def test_completion_review_requires_exact_binding_and_finished_inference(changes):
    assert not bound_review([completion_review(**changes)])


@pytest.mark.parametrize("event_id", [None, "", 1])
def test_completion_event_must_be_observed(event_id):
    assert not bound_review([completion_review()], event_id)


@pytest.mark.parametrize("args,code", [
    (["--help"], 0),
    ([], 2),
    (["--run-name", "../outside"], 2),
    (["--run-name", "safe", "--case-count", "0"], 2),
    (["--run-name", "safe", "--case-count", "11"], 2),
])
def test_live_runner_requires_explicit_valid_run_name_before_any_work(args, code):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/opencode_quiet_ten.py"), *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == code
    assert "usage:" in result.stdout + result.stderr


@pytest.mark.parametrize("args,code", [
    (["--help"], 0),
    ([], 2),
    (["--run-name", "../outside"], 2),
])
def test_recovery_runner_requires_explicit_valid_run_name_before_any_work(args, code):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/opencode_recovery_once.py"), *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == code
    assert "usage:" in result.stdout + result.stderr


def test_recovery_runner_uses_strict_causal_proof_and_owned_cleanup_only():
    root = Path(__file__).resolve().parents[2]
    source = (root / "scripts/opencode_recovery_once.py").read_text(encoding="utf-8")
    assert "recovery_interventions_succeeded(serialized_rows, followups)" in source
    assert 'minimum_user_count=2' in source
    assert 'first_stop["final_absent"]' in source
    assert 'first_stop["prior_followup_count"] == 0' in source
    assert "server.terminate()" in source
    assert "server.kill()" in source
    assert "rmtree" not in source
    assert "taskkill" not in source.lower()
    assert "Get-CimInstance" not in source


def messages():
    return [
        {"info": {"id": "u1", "sessionID": "s", "role": "user", "time": {"created": 1}}},
        {
            "info": {
                "id": "a1",
                "sessionID": "s",
                "role": "assistant",
                "parentID": "u1",
                "time": {"created": 2, "completed": 3},
                "finish": "stop",
            }
        },
    ]


@pytest.mark.parametrize("statuses", [{}, {"s": {"type": "idle"}}])
def test_current_completed_generation(statuses):
    assert completed_generation(messages(), statuses, "s") == ("u1", "a1")


def test_admitted_followup_missing_from_http_history_cannot_complete():
    assert completed_generation(messages(), {}, "s", minimum_user_count=2) is None


@pytest.mark.parametrize(
    "statuses",
    [
        None,
        [],
        {"s": None},
        {"s": {"type": "busy"}},
        {"s": {"type": "retry"}},
        {"s": {"type": "unknown"}},
    ],
)
def test_unavailable_or_nonidle_status_never_completes(statuses):
    assert completed_generation(messages(), statuses, "s") is None


def test_previous_success_does_not_complete_followup():
    rows = messages()
    rows.append({"info": {"id": "u2", "sessionID": "s", "role": "user", "time": {"created": 4}}})
    assert completed_generation(rows, {}, "s") is None
    rows.append(
        {
            "info": {
                "id": "a2",
                "sessionID": "s",
                "role": "assistant",
                "parentID": "u2",
                "time": {"created": 5},
            }
        }
    )
    assert completed_generation(rows, {}, "s") is None
    rows[-1]["info"].update(time={"created": 5, "completed": 6}, finish="stop")
    assert completed_generation(rows, {}, "s") == ("u2", "a2")


@pytest.mark.parametrize(
    "field,value",
    [
        ("parentID", "wrong"),
        ("sessionID", "other"),
        ("error", {}),
        ("error", {"name": "APIError"}),
        ("finish", "tool-calls"),
        ("finish", None),
        ("time", {"created": 2}),
        ("time", {"created": 2, "completed": 1}),
        ("time", {"created": 2, "completed": True}),
        ("time", {"created": 2, "completed": float("nan")}),
    ],
)
def test_invalid_latest_response(field, value):
    rows = messages()
    rows[-1]["info"][field] = value
    assert completed_generation(rows, {}, "s") is None


@pytest.mark.parametrize("rows", [None, [], [None], [{"info": None}]])
def test_malformed_messages(rows):
    assert completed_generation(rows, {}, "s") is None


def test_newer_incomplete_assistant_supersedes_finished_assistant():
    rows = messages()
    newer = deepcopy(rows[-1])
    newer["info"].update(id="a2", time={"created": 4})
    rows.append(newer)
    assert completed_generation(rows, {}, "s") is None


def observation(**changes):
    result = dict(
        now=0,
        generation=("u1", "a1"),
        event_ids=("e1",),
        followup_count=0,
        reviews_present=True,
        journal_complete=True,
    )
    result.update(changes)
    return result


def test_full_quiet_interval_required():
    fence = QuietCompletionFence()
    assert not fence.observe(**observation())
    assert not fence.observe(**observation(now=11))
    assert fence.observe(**observation(now=12))


@pytest.mark.parametrize(
    "changes",
    [
        {"generation": None},
        {"journal_complete": False},
        {"reviews_present": False},
        {"event_ids": ()},
        {"generation": ("u2", "a2")},
        {"event_ids": ("e1", "e2")},
        {"followup_count": 1},
    ],
)
def test_activity_resets_interval(changes):
    fence = QuietCompletionFence()
    assert not fence.observe(**observation())
    assert not fence.observe(**observation(now=11, **changes))
    assert not fence.observe(**observation(now=12))
    assert fence.observe(**observation(now=24))
