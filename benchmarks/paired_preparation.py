"""Prepare fresh OpenCode/Codex pairs without rewriting historical experiments.

This records a prospective schedule and public seeds. Execution isolation,
provider accounting, hidden evaluation and comparative results are separate.
"""

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from pex_bridge.adapters.strict_json import strict_json_loads

from benchmarks import boundary, evaluator, runner


def prepare_experiment(
    destination: Path, *, run_id: str, seed: str, models: dict[str, str],
    worker_fingerprints: dict[str, dict[str, str]], task_wall_seconds: int = 600,
    max_model_calls: int = 100, max_followups: int = 2, review_seconds: int = 180,
) -> dict:
    """Create all pairs before execution; refuse reuse, including partial runs."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", run_id):
        raise ValueError("invalid experiment identity")
    if not isinstance(seed, str) or not 1 <= len(seed) <= 512 or any(
        ord(char) < 32 for char in seed
    ):
        raise ValueError("a bounded randomization seed is required")
    if set(models) != {"codex", "opencode"} or any(
        not isinstance(value, str) or not value.strip() or len(value) > 256
        or any(ord(char) < 33 for char in value) for value in models.values()
    ):
        raise ValueError("both harnesses require pinned model identifiers")
    if set(worker_fingerprints) != set(models) or any(
        not isinstance(profile, dict) or set(profile) != {"runtime_sha256", "settings_sha256"}
        or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
               for value in profile.values()) for profile in worker_fingerprints.values()
    ):
        raise ValueError("both harnesses require runtime and settings fingerprints")
    if (type(task_wall_seconds) is not int or not 1 <= task_wall_seconds <= 86_400
            or type(max_model_calls) is not int or not 1 <= max_model_calls <= 1000
            or type(max_followups) is not int or not 0 <= max_followups <= 10
            or type(review_seconds) is not int or not 1 <= review_seconds <= task_wall_seconds):
        raise ValueError("invalid shared execution budget")
    profiles = {harness: {"model": models[harness], **worker_fingerprints[harness]}
                for harness in sorted(models)}
    profile_hashes = {harness: hashlib.sha256(json.dumps(
        profile, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest() for harness, profile in profiles.items()}
    destination = destination.absolute()
    parent = destination.parent.resolve(strict=True)
    if parent != destination.parent or destination.exists() or runner._is_link_like(destination):
        raise ValueError("experiment requires a fresh directory below an unlinked parent")
    # Validate all task packages before reserving any workspace.
    task_ids = tuple(evaluator.task_ids())
    for task_id in task_ids:
        boundary.assert_public_prompt(task_id, boundary.public_prompt(task_id))
    fingerprint = runner.benchmark_sha256()

    def order_key(value: str) -> str:
        return hashlib.sha256((seed + "\0" + value).encode()).hexdigest()

    schedule = []
    for harness, task_id in sorted(
        ((harness, task_id) for harness in sorted(models) for task_id in task_ids),
        key=lambda block: order_key(":".join(block)),
    ):
        for condition in sorted(("baseline", "pex"), key=lambda name: order_key(
            f"{harness}:{task_id}:{name}"
        )):
            schedule.append({"harness": harness, "task": task_id, "condition": condition,
                             "model": models[harness],
                             "worker_profile_sha256": profile_hashes[harness]})
    destination.mkdir(mode=0o700)
    workers = destination / "workers"
    workers.mkdir(mode=0o700)
    control = destination / "controller"
    control.mkdir(mode=0o700)
    pairs = {}
    rows = []
    for item in schedule:
        identity = f"{item['harness']}:{item['task']}:{item['condition']}"
        name = hashlib.sha256((run_id + "\0" + identity).encode()).hexdigest()
        workspace = workers / name
        seeded = evaluator.seed_workspace(item["task"], workspace)
        manifest = boundary.workspace_manifest_sha256(workspace)
        prompt = boundary.sha256_file(workspace / "TASK.md")
        pair = (item["harness"], item["task"])
        signatures = (manifest, prompt, seeded["protected_sha256"])
        if pair in pairs and pairs[pair] != signatures:
            raise RuntimeError("paired public seeds do not match; retain this aborted preparation")
        pairs[pair] = signatures
        rows.append({**item, "workspace": name, "seed_manifest_sha256": manifest,
                     "prompt_sha256": prompt, "protected_sha256": seeded["protected_sha256"]})
    if runner.benchmark_sha256() != fingerprint:
        raise RuntimeError("benchmark sources changed during preparation; retain this aborted run")
    plan = {
        "schema": "pex.paired-preparation.v2", "run_id": run_id,
        "randomization_seed": seed, "order_algorithm": "sha256_paired_blocks_v1",
        "benchmark_sha256": fingerprint, "schedule": rows,
        "worker_profiles": profiles,
        "budget": {"task_wall_seconds": task_wall_seconds, "includes_worker_and_pex": True,
                   "max_worker_model_calls": max_model_calls, "max_pex_followups": max_followups,
                   "max_review_seconds": review_seconds, "evaluator_outside_task_budget": True},
        "execution_boundary_verified": False, "presentation_eligible": False,
        "scope": "Prospective public-seed preparation only; no worker or evaluator executed.",
    }
    encoded = json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    with (control / "plan.json").open("x", encoding="utf-8", newline="\n") as target:
        target.write(encoded)
        target.flush()
        os.fsync(target.fileno())
    return plan


def reserve_attempt(
    destination: Path, *, index: int, expected_plan_sha256: str, worker_profile: dict[str, str],
) -> dict:
    """Consume one prepared attempt before launch, without proving isolation.

    The controller must independently pin the plan digest after preparation and
    measure the actual worker profile. Supplying declared hashes as measurements
    does not verify a runtime. A reservation is never reusable after launch failure.
    """
    root = destination.absolute()
    if root.resolve(strict=True) != root:
        raise ValueError("experiment path cannot contain links")
    control = root / "controller"
    path = control / "plan.json"
    if control.resolve(strict=True) != control or runner._is_link_like(path):
        raise ValueError("controller plan cannot be linked")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_plan_sha256):
        raise ValueError("independently pinned plan digest is required")
    with path.open("rb") as handle:
        raw = handle.read(1_000_001)
    if len(raw) > 1_000_000 or hashlib.sha256(raw).hexdigest() != expected_plan_sha256:
        raise ValueError("prepared plan differs from its pinned digest")
    plan = strict_json_loads(raw)
    if not isinstance(plan, dict) or plan.get("schema") != "pex.paired-preparation.v2":
        raise ValueError("unsupported preparation plan")
    schedule = plan["schedule"]
    if type(index) is not int or not 0 <= index < len(schedule):
        raise ValueError("attempt index is outside the prepared schedule")
    row = schedule[index]
    profile = plan["worker_profiles"][row["harness"]]
    if worker_profile != profile:
        raise ValueError("measured worker profile differs from the prepared profile")
    fingerprint = runner.benchmark_sha256()
    if fingerprint != plan["benchmark_sha256"]:
        raise ValueError("benchmark sources differ from the prepared plan")
    name = row["workspace"]
    if not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{64}", name):
        raise ValueError("invalid prepared workspace identity")
    workspace = root / "workers" / name
    if workspace.resolve(strict=True) != workspace:
        raise ValueError("worker path cannot contain links")
    if boundary.workspace_manifest_sha256(workspace) != row["seed_manifest_sha256"]:
        raise ValueError("public workspace changed before attempt admission")
    if runner.benchmark_sha256() != fingerprint:
        raise ValueError("benchmark sources changed during attempt admission")
    receipt = {
        "schema": "pex.paired-attempt-reservation.v1", "status": "reserved",
        "reserved_at": datetime.now(UTC).isoformat(), "run_id": plan["run_id"],
        "plan_sha256": expected_plan_sha256, "schedule_index": index,
        "entry": row, "budget": plan["budget"],
        "worker_profile_sha256": row["worker_profile_sha256"],
        "execution_boundary_verified": False, "presentation_eligible": False,
    }
    # Exclusive creation makes simultaneous admission and uncertain launch retries
    # consume the same durable slot. Never delete this receipt to retry an arm.
    encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    with (control / f"attempt-{name}.json").open("x", encoding="utf-8", newline="\n") as target:
        target.write(encoded)
        target.flush()
        os.fsync(target.fileno())
    return receipt
