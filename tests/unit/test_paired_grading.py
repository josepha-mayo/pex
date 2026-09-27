import base64
import hashlib
import json

import pytest

from benchmarks import boundary, paired_grading, paired_preparation
from benchmarks.opencode_executor import worker_observation


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def attempt(tmp_path, monkeypatch):
    root = tmp_path / "experiment"
    profile = {"runtime_sha256": "a" * 64, "settings_sha256": "b" * 64}
    plan = paired_preparation.prepare_experiment(
        root, run_id="grade-fixture", seed="fixed-fixture",
        models={"codex": "pinned", "opencode": "pinned"},
        worker_fingerprints={"codex": profile, "opencode": profile},
    )
    index = next(index for index, row in enumerate(plan["schedule"])
                 if row["harness"] == "opencode" and row["condition"] == "baseline")
    plan_path = root / "controller/plan.json"
    reservation = paired_preparation.reserve_attempt(
        root, index=index, expected_plan_sha256=digest(plan_path),
        worker_profile={"model": "pinned", **profile},
    )
    row = reservation["entry"]
    run = root / "controller" / ("run-" + row["workspace"])
    run.mkdir()
    raw = b"\n".join(json.dumps({"type": kind, "sessionID": "vendor", "part": {
        "sessionID": "vendor", "messageID": "message", **extra,
    }}).encode() for kind, extra in (("step_start", {}), ("step_finish", {"reason": "stop"})))
    stdout = json.dumps({
        "schema": "pex.opencode-worker-output.v1", "turns": [{
            "session_id": "vendor", "stdout_sha256": hashlib.sha256(raw).hexdigest(),
            "stdout_bytes": len(raw), "jsonl_base64": base64.b64encode(raw).decode(),
        }], "actions": [], "followups": [], "followup_limit_reached": False,
    }).encode()
    (run / "stdout.json").write_bytes(stdout)
    (run / "stderr.txt").write_bytes(b"")
    workspace = root / "workers" / row["workspace"]
    outcome = {
        "schema": "pex.opencode-attempt.v1", "status": "worker_completed_unscored",
        "reservation": reservation, "presentation_eligible": False, "quality_measured": False,
        "stdout_sha256": digest(run / "stdout.json"), "stderr_sha256": digest(run / "stderr.txt"),
        "workspace_snapshot_sha256": boundary.workspace_manifest_sha256(workspace, complete=True),
        "worker_observation": worker_observation(stdout, supervised=False, max_followups=0),
        "model_attempts": [{"status": "completed"}], "review_attempts": [],
    }
    write(run / "outcome.json", outcome)
    monkeypatch.setattr(paired_grading.sys, "platform", "linux")
    monkeypatch.setattr(paired_grading.evaluator.linux_sandbox, "_prefix", lambda _: [])
    options = {"index": index, "expected_plan_sha256": digest(plan_path),
               "expected_outcome_sha256": digest(run / "outcome.json")}
    return root, run, workspace, options


@pytest.mark.parametrize("success", [True, False])
def test_grade_records_real_check_result_without_promoting_eligibility(
    attempt, monkeypatch, success,
):
    root, run, workspace, options = attempt
    calls = []

    def evaluate(task, candidate, extra, **kwargs):
        calls.append(task)
        assert candidate == workspace and kwargs == {"require_linux_sandbox": True}
        assert "protected_sha256" in extra
        return {"task": task, "success": success, "reasons": [] if success else ["failed"]}

    monkeypatch.setattr(paired_grading.evaluator, "evaluate", evaluate)
    result = paired_grading.grade_completed_attempt(root, **options)
    assert result["status"] == "graded" and result["task_tests_measured"]
    assert result["result"]["success"] is success and not result["presentation_eligible"]
    assert result["outcome_sha256"] == options["expected_outcome_sha256"]
    path = root / "controller" / ("grade-" + workspace.name + ".json")
    assert paired_grading.read_committed_grade(path) == result
    marker = path.with_name(path.stem + ".committed.json")
    original_marker = marker.read_bytes()
    marker.write_text('{"grade_sha256":"changed"}')
    with pytest.raises(ValueError, match="does not match"):
        paired_grading.read_committed_grade(path)
    marker.write_bytes(original_marker)
    with pytest.raises(FileExistsError):
        paired_grading.grade_completed_attempt(root, **options)
    assert len(calls) == 1


@pytest.mark.parametrize("changed", ["plan", "outcome", "stdout", "stderr", "workspace"])
def test_changed_completion_evidence_is_never_graded(attempt, monkeypatch, changed):
    root, run, workspace, options = attempt
    paths = {"plan": root / "controller/plan.json", "outcome": run / "outcome.json",
             "stdout": run / "stdout.json", "stderr": run / "stderr.txt",
             "workspace": workspace / "TASK.md"}
    with paths[changed].open("ab") as handle:
        handle.write(b"changed")

    def forbidden(*args, **kwargs):
        pytest.fail("changed evidence reached evaluator")

    monkeypatch.setattr(paired_grading.evaluator, "evaluate", forbidden)
    with pytest.raises(ValueError):
        paired_grading.grade_completed_attempt(root, **options)
    assert not list((root / "controller").glob("grade-*.json"))


@pytest.mark.parametrize("failure", ["exception", "candidate_drift", "source_drift"])
def test_uncertain_grading_consumes_slot_and_retains_failure(attempt, monkeypatch, failure):
    root, run, workspace, options = attempt

    def evaluate(*args, **kwargs):
        if failure == "exception":
            raise RuntimeError("grader failed")
        if failure == "candidate_drift":
            (workspace / "TASK.md").write_text("changed")
        else:
            monkeypatch.setattr(paired_grading.runner, "benchmark_sha256", lambda: "c" * 64)
        return {"success": True}

    monkeypatch.setattr(paired_grading.evaluator, "evaluate", evaluate)
    with pytest.raises(RuntimeError if failure == "exception" else ValueError):
        paired_grading.grade_completed_attempt(root, **options)
    files = list((root / "controller").glob("grade-*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text())
    assert saved["status"] == "failed_uncertain" and not saved["task_tests_measured"]
    assert "error_type" in saved


def test_failed_worker_cannot_be_reclassified_for_grading(attempt):
    root, run, workspace, options = attempt
    outcome_path = run / "outcome.json"
    outcome = json.loads(outcome_path.read_text())
    outcome["status"] = "failed_uncertain"
    write(outcome_path, outcome)
    options["expected_outcome_sha256"] = digest(outcome_path)
    with pytest.raises(ValueError, match="incomplete or uncertain"):
        paired_grading.grade_completed_attempt(root, **options)


@pytest.mark.parametrize("relative", [".git/added.py", "__pycache__/added.py", ".coverage"])
def test_completion_snapshot_includes_historically_ignored_files(attempt, relative):
    root, run, workspace, options = attempt
    original_seed_hash = boundary.workspace_manifest_sha256(workspace)
    added = workspace / relative
    added.parent.mkdir(exist_ok=True)
    added.write_text("candidate-readable input")
    assert boundary.workspace_manifest_sha256(workspace) == original_seed_hash
    with pytest.raises(ValueError, match="changed after worker completion"):
        paired_grading.grade_completed_attempt(root, **options)


def test_completion_snapshot_includes_empty_directory_changes(attempt):
    root, run, workspace, options = attempt
    (workspace / ".git").mkdir()
    with pytest.raises(ValueError, match="changed after worker completion"):
        paired_grading.grade_completed_attempt(root, **options)


@pytest.mark.parametrize("failed_sync", [1, 2, 3])
def test_persistence_failure_never_exposes_a_committed_grade(attempt, monkeypatch, failed_sync):
    root, run, workspace, options = attempt
    monkeypatch.setattr(paired_grading.evaluator, "evaluate", lambda *a, **k: {"success": True})
    original = paired_grading.os.fsync
    calls = 0

    def fsync(descriptor):
        nonlocal calls
        calls += 1
        if calls == failed_sync:
            if failed_sync == 3:
                path = root / "controller" / ("grade-" + workspace.name + ".json")
                with pytest.raises(FileNotFoundError):
                    paired_grading.read_committed_grade(path)
            raise OSError("injected persistence failure")
        original(descriptor)

    monkeypatch.setattr(paired_grading.os, "fsync", fsync)
    with pytest.raises(OSError, match="injected persistence failure"):
        paired_grading.grade_completed_attempt(root, **options)
    path = root / "controller" / ("grade-" + workspace.name + ".json")
    saved = json.loads(path.read_text())
    assert saved["status"] == "failed_uncertain" and saved["error_type"] == "OSError"
    with pytest.raises(FileNotFoundError):
        paired_grading.read_committed_grade(path)
    with pytest.raises(FileExistsError):
        paired_grading.grade_completed_attempt(root, **options)


def test_existing_commit_evidence_is_preserved(attempt):
    root, run, workspace, options = attempt
    marker = root / "controller" / ("grade-" + workspace.name + ".committed.json")
    marker.write_text("existing evidence")
    with pytest.raises(FileExistsError):
        paired_grading.grade_completed_attempt(root, **options)
    assert marker.read_text() == "existing evidence"


@pytest.mark.parametrize("uncertain", ["missing", "failed", "baseline_review"])
def test_incomplete_call_accounting_is_not_graded(attempt, uncertain):
    root, run, workspace, options = attempt
    path = run / "outcome.json"
    outcome = json.loads(path.read_text())
    if uncertain == "missing":
        outcome.pop("model_attempts")
    elif uncertain == "failed":
        outcome["model_attempts"] = [{"status": "failed_uncertain"}]
    else:
        outcome["review_attempts"] = [{"status": "completed"}]
    write(path, outcome)
    options["expected_outcome_sha256"] = digest(path)
    with pytest.raises(ValueError):
        paired_grading.grade_completed_attempt(root, **options)
