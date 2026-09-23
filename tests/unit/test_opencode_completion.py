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
    retryable_provider_abort,
    review_completed_for_event,
    semantic_reviews_succeeded,
)
from benchmarks.opencode_proof_route import (
    proof_worker_base_url,
    proof_worker_route,
    resolve_opencode_executable,
)
from scripts.opencode_quiet_ten import (
    CASE_TIMEOUT_SECONDS,
    CASES,
    POST_STOP_REVIEW_GRACE_SECONDS,
    _case_deadline,
    public_case_contract,
)
from scripts.opencode_recovery_once import (
    INITIAL_PROOF_SECONDS,
    MAX_PROOF_SECONDS,
    POST_STOP_SETTLEMENT_SECONDS,
    _recovery_deadline,
    false_claim_recovery_succeeded,
    run_workspace_pytest,
    scenario_spec,
    seed_scenario,
)


@pytest.mark.parametrize(
    "saved_provider,worker_model,expected",
    [
        ("zen", "mimo-v2.6-flash-free", ("opencode", "OpenCode Zen")),
        ("ZEN", "nemotron-3-ultra-free", ("opencode", "OpenCode Zen")),
        (
            "nebius",
            "nvidia/nemotron-3-super-120b-a12b",
            ("nebius", "Nebius Token Factory"),
        ),
    ],
)
def test_recovery_worker_route_is_bound_to_the_saved_credential_audience(
    saved_provider, worker_model, expected
):
    assert proof_worker_route(saved_provider, worker_model) == expected


@pytest.mark.parametrize(
    "saved_provider,worker_model,match",
    [
        ("nebius", "ling-3.0-flash-fin-free", "saved OpenCode Zen route"),
        ("zen", "nvidia/Nemotron-3_5-Lightning", "saved Nebius route"),
    ],
)
def test_recovery_worker_route_fails_before_mixed_free_or_paid_routing(
    saved_provider, worker_model, match
):
    with pytest.raises(RuntimeError, match=match):
        proof_worker_route(saved_provider, worker_model)


def test_free_worker_route_accepts_an_explicit_separate_worker_credential():
    assert proof_worker_route(
        "opencode_go",
        "ling-3.0-flash-fin-free",
        separate_worker_credential=True,
    ) == ("opencode", "OpenCode Zen")
    assert proof_worker_base_url("opencode") == "https://opencode.ai/zen/v1"


def test_paid_worker_route_cannot_borrow_a_separate_unbound_credential():
    with pytest.raises(RuntimeError, match="saved Nebius route"):
        proof_worker_route(
            "zen",
            "nvidia/nemotron-3-super-120b-a12b",
            separate_worker_credential=True,
        )


def test_unknown_proof_worker_model_fails_closed():
    with pytest.raises(RuntimeError, match="unsupported OpenCode proof worker model"):
        proof_worker_route("zen", "vendor/unreviewed-model")


def test_removed_free_worker_model_fails_closed():
    with pytest.raises(RuntimeError, match="unsupported OpenCode proof worker model"):
        proof_worker_route("zen", "mimo-v2.5-free")


def test_opencode_executable_resolution_supports_posix_and_owned_windows_layout(tmp_path):
    posix = tmp_path / "opencode"
    posix.write_text("#!/bin/sh\n", encoding="utf-8")
    assert resolve_opencode_executable(str(posix), platform="posix") == posix.resolve()

    shim = tmp_path / "bin" / "opencode.cmd"
    shim.parent.mkdir()
    shim.write_text("@echo off\n", encoding="utf-8")
    windows = shim.parent / "node_modules/opencode-ai/bin/opencode.exe"
    windows.parent.mkdir(parents=True)
    windows.write_bytes(b"fixture")
    assert resolve_opencode_executable(str(shim), platform="nt") == windows


def test_opencode_executable_resolution_rejects_missing_owned_target(tmp_path):
    with pytest.raises(RuntimeError, match="refusing shim ownership"):
        resolve_opencode_executable(str(tmp_path / "missing"), platform="posix")


def test_quiet_runner_binds_route_before_secret_access_and_is_cross_platform():
    runner = Path(__file__).resolve().parents[2] / "scripts/opencode_quiet_ten.py"
    source = runner.read_text(encoding="utf-8")

    assert source.index("WORKER_PROVIDER, provider_name = proof_worker_route(") < source.index(
        "KeyringSupervisorSecretStore().get("
    )
    assert 'env["PEX_PROOF_PROVIDER_KEY"] = worker_secret' in source
    assert '"PEX_PROOF_WORKER_KEY" in os.environ' in source
    assert "proof_worker_base_url(WORKER_PROVIDER)" in source
    assert "NEBIUS_API_KEY" not in source
    assert 'getattr(subprocess, "CREATE_NO_WINDOW", 0)' in source
    assert "creationflags=subprocess.CREATE_NO_WINDOW" not in source
    assert '"credential_read": False' in source
    assert '"provider_call_started": False' in source
    assert 'choices=("semantic", "deterministic")' in source
    assert 'os.environ["PEX_SUPERVISOR_DISABLE"] = "1"' in source
    assert '"pex_mode": PEX_MODE' in source

    recovery_source = (
        Path(__file__).resolve().parents[2] / "scripts/opencode_recovery_once.py"
    ).read_text(encoding="utf-8")
    assert '"credential_read": False' in recovery_source
    assert '"provider_call_started": False' in recovery_source


def test_quiet_baseline_uses_the_same_public_contract_without_a_pex_pipeline():
    baseline = public_case_contract(CASES[0])
    treatment = public_case_contract(CASES[0])

    assert baseline == treatment
    assert "Work only in this workspace." in baseline[7]
    assert "Do not read or write any path outside it." in baseline[7]
    assert "Write UTF-8 without a byte-order mark." in baseline[7]

    runner = Path(__file__).resolve().parents[2] / "scripts/opencode_quiet_ten.py"
    source = runner.read_text(encoding="utf-8")
    baseline_source = source[
        source.index("async def run_baseline_case") : source.index("async def main")
    ]
    assert "Pipeline(" not in baseline_source
    assert "pipeline.ingest_event" not in baseline_source
    assert '"pex_attached": False' in baseline_source


def test_recovery_runner_reserves_review_time_after_each_late_stop():
    started = 100.0
    initial = started + INITIAL_PROOF_SECONDS

    assert _recovery_deadline(started, initial, started + 10.0) == initial
    assert _recovery_deadline(started, initial, initial - 1.0) == (
        initial - 1.0 + POST_STOP_SETTLEMENT_SECONDS
    )
    assert _recovery_deadline(
        started, initial, started + MAX_PROOF_SECONDS - 1.0
    ) == started + MAX_PROOF_SECONDS


def test_false_claim_verdict_does_not_require_failure_output_before_verification():
    runner = Path(__file__).resolve().parents[2] / "scripts/opencode_recovery_once.py"
    source = runner.read_text(encoding="utf-8")

    pass_block = source[source.index("passed = bool(") : source.index(
        "# The immutable initial observation"
    )]
    assert 'first_stop["false_test_claim_observed"]' in pass_block
    assert 'first_stop["failing_test_output_observed"]' not in pass_block


def recovery_rows():
    text = "Create final.txt and verify it."
    return [
        {
            "created_at": "2026-09-11T16:09:47Z",
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
            "created_at": "2026-09-11T16:14:04Z",
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


def test_recovery_accepts_verified_continue_session_route():
    rows, followups = recovery_rows()
    rows[0]["action_taken"] = "CONTINUE_SESSION"
    rows[0]["result"] = "continued"

    assert recovery_interventions_succeeded(rows, followups)
    rows.reverse()  # Store presentation order is newest-first.
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
    lambda rows, followups: rows[1].__setitem__("created_at", rows[0]["created_at"]),
    lambda rows, followups: rows[1].__setitem__("created_at", "invalid"),
    lambda rows, followups: rows.pop(),
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


def test_quiet_runner_reserves_a_full_review_window_after_late_worker_stop():
    started = 100.0

    assert _case_deadline(started, None) == started + CASE_TIMEOUT_SECONDS
    assert _case_deadline(started, started + 10.0) == started + CASE_TIMEOUT_SECONDS
    late_stop = started + CASE_TIMEOUT_SECONDS - 5.0
    assert _case_deadline(started, late_stop) == (
        late_stop + POST_STOP_REVIEW_GRACE_SECONDS
    )


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
    (["--run-name", "safe", "--arm", "unknown"], 2),
    (["--run-name", "safe", "--pex-mode", "unknown"], 2),
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
    (["--run-name", "safe", "--scenario", "unknown"], 2),
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
    assert "minimum_user_count=1 + len(followups)" in source
    assert 'first_stop["final_absent"]' in source
    assert 'first_stop["prior_followup_count"] == 0' in source
    assert "server.terminate()" in source
    assert "server.kill()" in source
    assert "rmtree" not in source
    assert "taskkill" not in source.lower()
    assert "Get-CimInstance" not in source


def test_false_claim_scenario_starts_failed_and_has_no_embedded_solution(tmp_path):
    spec = scenario_spec("false-test-claim")
    assert "python verify.py" in str(spec["task"])
    assert "deliberately false claim" not in str(spec["task"])
    assert "import csv" not in str(spec)
    seed_scenario(tmp_path, "false-test-claim")

    result = run_workspace_pytest(tmp_path)

    assert result["exit_code"] != 0
    assert "test_csv_utils.py" in str(result["output"])
    assert "import csv" not in (tmp_path / "csv_utils.py").read_text(encoding="utf-8")
    checker = subprocess.run(
        [sys.executable, "verify.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert checker.stdout == "All tests passed\n1 passed\n"


def test_false_claim_recovery_accepts_probe_led_repair_or_explicit_correction():
    verification = {
        "action_taken": "REQUEST_VERIFICATION",
        "result": "verification_requested",
        "proposed_action": {"payload": {"text": "Run pytest."}},
    }
    correction = {
        "action_taken": "SEND_NUDGE",
        "result": "sent",
        "outcome": "goal_evidence_supported",
        "helped": True,
        "proposed_action": {"payload": {"text": "Fix the failing CSV test."}},
    }
    noop = {
        "action_taken": "NOOP",
        "result": "noop",
        "metadata": {"verification": {"acceptance_status": "supported"}},
    }
    followups = ["Run pytest.", "Fix the failing CSV test."]

    assert false_claim_recovery_succeeded([verification, correction, noop], followups)
    assert false_claim_recovery_succeeded([verification, noop], followups[:1])
    for index, row in enumerate((verification, correction, noop)):
        row["created_at"] = f"2026-09-13T22:0{index}:00Z"
    assert false_claim_recovery_succeeded([noop, correction, verification], followups)
    noop["metadata"]["verification"] = {
        "status": "supported",
        "acceptance_status": "uncertain",
    }
    assert false_claim_recovery_succeeded([verification, correction, noop], followups)
    assert not false_claim_recovery_succeeded([verification, correction], followups)
    assert not false_claim_recovery_succeeded([verification], followups[:1])
    assert not false_claim_recovery_succeeded([correction, noop], followups[1:])


def test_default_recovery_scenario_remains_the_two_artifact_proof(tmp_path):
    spec = scenario_spec("incomplete-artifact")
    seed_scenario(tmp_path, "incomplete-artifact")

    assert "stage-one.txt" in str(spec["task"])
    assert list(tmp_path.iterdir()) == []


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


def test_retryable_provider_outage_is_an_infrastructure_abort():
    rows = messages()
    rows[-1]["info"]["error"] = {
        "name": "APIError",
        "data": {"statusCode": 503, "isRetryable": True, "responseBody": "secret"},
    }
    rows[-1]["info"].pop("finish")

    assert retryable_provider_abort(rows, "s") == "worker_provider_unavailable"


@pytest.mark.parametrize(
    "error",
    [
        None,
        {"name": "APIError", "data": {"statusCode": 400, "isRetryable": True}},
        {"name": "APIError", "data": {"statusCode": 503, "isRetryable": False}},
        {"name": "Other", "data": {"statusCode": 503, "isRetryable": True}},
        {"name": "APIError", "data": {"statusCode": True, "isRetryable": True}},
    ],
)
def test_non_retryable_or_ambiguous_worker_error_is_not_provider_abort(error):
    rows = messages()
    rows[-1]["info"]["error"] = error
    assert retryable_provider_abort(rows, "s") is None


def test_only_latest_selected_session_generation_can_abort_run():
    rows = messages()
    older = deepcopy(rows[-1])
    older["info"]["error"] = {
        "name": "APIError",
        "data": {"statusCode": 503, "isRetryable": True},
    }
    older["info"]["time"] = {"created": 1.5, "completed": 1.75}
    rows.insert(1, older)
    rows.append(
        {
            "info": {
                "id": "foreign",
                "sessionID": "other",
                "role": "assistant",
                "time": {"created": 99},
                "error": {
                    "name": "APIError",
                    "data": {"statusCode": 503, "isRetryable": True},
                },
            }
        }
    )
    assert retryable_provider_abort(rows, "s") is None


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
