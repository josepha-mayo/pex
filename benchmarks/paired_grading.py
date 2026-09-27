"""Once-only controller grading of pinned completed attempts, never retries."""

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

from pex_bridge.adapters.strict_json import strict_json_loads

from benchmarks import boundary, evaluator, runner
from benchmarks.opencode_executor import MAX_OUTPUT, worker_observation


def _digest(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("independently pinned digest is required")


def _read(path: Path, bound: int) -> bytes:
    metadata = path.lstat()
    if (path.resolve(strict=True) != path.absolute() or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1):
        raise ValueError("controller evidence must be an unlinked regular file")
    with path.open("rb") as handle:
        raw = handle.read(bound + 1)
    if len(raw) > bound:
        raise ValueError("controller evidence exceeds its bound")
    return raw


def grade_completed_attempt(
    destination: Path, *, index: int, expected_plan_sha256: str,
    expected_outcome_sha256: str,
) -> dict:
    """Grade a completed OpenCode candidate through the required Linux boundary.

    The caller pins controller outcome bytes when execution completes. A grade
    consumes its slot before evaluation, including uncertain failures. Neither
    this task score nor controlled-backend scores establish comparative quality,
    supervisor isolation, provider provenance or presentation eligibility.
    """
    if sys.platform != "linux":
        raise RuntimeError("paired grading requires Linux")
    _digest(expected_plan_sha256)
    _digest(expected_outcome_sha256)
    root = destination.absolute()
    if root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError("experiment path cannot contain links")
    control = root / "controller"
    plan_raw = _read(control / "plan.json", 1_000_000)
    if hashlib.sha256(plan_raw).hexdigest() != expected_plan_sha256:
        raise ValueError("prepared plan differs from its pinned digest")
    plan = strict_json_loads(plan_raw)
    if not isinstance(plan, dict) or plan.get("schema") != "pex.paired-preparation.v2":
        raise ValueError("unsupported preparation plan")
    if type(index) is not int or not 0 <= index < len(plan["schedule"]):
        raise ValueError("attempt index is outside the prepared schedule")
    row = plan["schedule"][index]
    name = row["workspace"]
    _digest(name)
    if row["harness"] != "opencode" or row["condition"] not in {"baseline", "pex"}:
        raise ValueError("grading backend requires an OpenCode attempt")
    fingerprint = runner.benchmark_sha256()
    if fingerprint != plan["benchmark_sha256"]:
        raise ValueError("benchmark sources differ from the prepared plan")
    reservation_raw = _read(control / f"attempt-{name}.json", 1_000_000)
    reservation = strict_json_loads(reservation_raw)
    if (not isinstance(reservation, dict)
            or reservation.get("schema") != "pex.paired-attempt-reservation.v1"
            or reservation.get("status") != "reserved"
            or reservation.get("entry") != row
            or reservation.get("schedule_index") != index
            or reservation.get("run_id") != plan["run_id"]
            or reservation.get("plan_sha256") != expected_plan_sha256
            or reservation.get("benchmark_sha256") != fingerprint
            or reservation.get("budget") != plan["budget"]
            or reservation.get("worker_profile_sha256") != row["worker_profile_sha256"]):
        raise ValueError("attempt reservation differs from the prepared plan")
    run = control / ("run-" + name)
    outcome_raw = _read(run / "outcome.json", 1_000_000)
    if hashlib.sha256(outcome_raw).hexdigest() != expected_outcome_sha256:
        raise ValueError("worker outcome differs from its pinned digest")
    outcome = strict_json_loads(outcome_raw)
    if (not isinstance(outcome, dict) or outcome.get("schema") != "pex.opencode-attempt.v1"
            or outcome.get("status") != "worker_completed_unscored"
            or outcome.get("reservation") != reservation or "error_type" in outcome
            or outcome.get("quality_measured") is not False
            or outcome.get("presentation_eligible") is not False):
        raise ValueError("worker outcome is incomplete or uncertain")
    stdout = _read(run / "stdout.json", MAX_OUTPUT)
    stderr = _read(run / "stderr.txt", MAX_OUTPUT)
    if (hashlib.sha256(stdout).hexdigest() != outcome.get("stdout_sha256")
            or hashlib.sha256(stderr).hexdigest() != outcome.get("stderr_sha256")):
        raise ValueError("worker capture differs from its completion receipt")
    observation = worker_observation(
        stdout, supervised=row["condition"] == "pex",
        max_followups=plan["budget"]["max_pex_followups"] if row["condition"] == "pex" else 0,
    )
    if observation != outcome.get("worker_observation"):
        raise ValueError("worker observation differs from its captured natural stops")
    models, reviews = outcome.get("model_attempts"), outcome.get("review_attempts")
    if (not isinstance(models, list)
            or not 1 <= len(models) <= plan["budget"]["max_worker_model_calls"]
            or any(not isinstance(item, dict) or item.get("status") != "completed"
                   for item in models)
            or not isinstance(reviews, list)):
        raise ValueError("worker model accounting is incomplete or uncertain")
    if row["condition"] == "baseline":
        if reviews:
            raise ValueError("baseline attempt contains supervision")
    elif (len(reviews) != len(observation["turns"])
          or any(not isinstance(item, dict) or item.get("status") != "completed"
                 or item.get("vendor_session_id") != observation["turns"][0]["session_id"]
                 for item in reviews)):
        raise ValueError("worker review accounting is incomplete or uncertain")
    workspace = root / "workers" / name
    manifest = boundary.workspace_manifest_sha256(workspace, complete=True)
    if manifest != outcome.get("workspace_snapshot_sha256"):
        raise ValueError("candidate workspace changed after worker completion")
    # No private evaluation occurs until all completion evidence is bound and
    # the candidate passes the enforced mount/path preflight.
    evaluator.linux_sandbox._prefix(workspace)
    grade = {
        "schema": "pex.paired-task-grade.v1", "status": "failed_uncertain",
        "plan_sha256": expected_plan_sha256, "outcome_sha256": expected_outcome_sha256,
        "reservation_sha256": hashlib.sha256(reservation_raw).hexdigest(),
        "benchmark_sha256": fingerprint, "schedule_index": index, "entry": row,
        "workspace_snapshot_sha256": manifest, "presentation_eligible": False,
        "persistence_marker_required": True,
        "task_tests_measured": False,
    }
    # An exclusive file consumes the grade slot even when evaluation or writing
    # fails. Never erase the slot to rerun a candidate or replace a bad outcome.
    marker = control / f"grade-{name}.committed.json"
    pending = control / f"grade-{name}.pending.json"
    if any(path.exists() or path.is_symlink() for path in (marker, pending)):
        raise FileExistsError("grade commit marker already exists")
    marker_created = False
    pending_created = False
    with (control / f"grade-{name}.json").open("x", encoding="utf-8", newline="\n") as handle:

        def persist():
            handle.seek(0)
            handle.truncate()
            encoded = json.dumps(grade, sort_keys=True, allow_nan=False) + "\n"
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            return hashlib.sha256(encoded.encode()).hexdigest()

        try:
            persist()
            result = evaluator.evaluate(
                row["task"], workspace, {"protected_sha256": row["protected_sha256"]},
                require_linux_sandbox=True,
            )
            if boundary.workspace_manifest_sha256(workspace, complete=True) != manifest:
                raise ValueError("candidate workspace changed during grading")
            if runner.benchmark_sha256() != fingerprint:
                raise ValueError("benchmark sources changed during grading")
            grade.update(status="graded", task_tests_measured=True, result=result)
            committed_hash = persist()
            # Readers must require this matching marker, not only a `graded`
            # payload that might have failed its final flush or fsync.
            with pending.open("x", encoding="utf-8", newline="\n") as committed:
                pending_created = True
                committed.write(json.dumps({"grade_sha256": committed_hash}) + "\n")
                committed.flush()
                os.fsync(committed.fileno())
            # Atomic, exclusive publication occurs only after marker bytes have
            # settled. While the pending hard link exists, readers also reject
            # the marker's link count; unlinking it completes publication.
            os.link(pending, marker)
            marker_created = True
            pending.unlink()
            pending_created = False
        except BaseException as error:
            grade.update(status="failed_uncertain", task_tests_measured=False)
            grade.pop("result", None)
            grade["error_type"] = type(error).__name__
            try:
                if marker_created:
                    marker.unlink(missing_ok=True)
                if pending_created:
                    pending.unlink(missing_ok=True)
                persist()
            except OSError:
                # The consumed slot remains. Missing/mismatched commit evidence
                # is uncertain even if recovery persistence also fails.
                pass
            raise
    return grade


def read_committed_grade(path: Path) -> dict:
    """Reject incomplete writes and grade payloads lacking matching commit evidence."""
    raw = _read(path, 1_000_000)
    marker = path.with_name(path.stem + ".committed.json")
    commit = strict_json_loads(_read(marker, 1_000))
    if commit != {"grade_sha256": hashlib.sha256(raw).hexdigest()}:
        raise ValueError("grade persistence marker does not match its payload")
    grade = strict_json_loads(raw)
    if (not isinstance(grade, dict) or grade.get("schema") != "pex.paired-task-grade.v1"
            or grade.get("status") != "graded" or grade.get("task_tests_measured") is not True
            or grade.get("persistence_marker_required") is not True or "error_type" in grade):
        raise ValueError("grade is incomplete or uncertain")
    return grade
