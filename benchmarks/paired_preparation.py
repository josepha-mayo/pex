"""Prepare fresh OpenCode/Codex pairs without rewriting historical experiments.

This records a prospective schedule and public seeds. Execution isolation,
provider accounting, hidden evaluation and comparative results are separate.
"""

import hashlib
import json
import os
import re
from pathlib import Path

from benchmarks import boundary, evaluator, runner


def prepare_experiment(
    destination: Path, *, run_id: str, seed: str, models: dict[str, str],
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
                             "model": models[harness]})
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
        "schema": "pex.paired-preparation.v1", "run_id": run_id,
        "randomization_seed": seed, "order_algorithm": "sha256_paired_blocks_v1",
        "benchmark_sha256": fingerprint, "schedule": rows,
        "execution_boundary_verified": False, "presentation_eligible": False,
        "scope": "Prospective public-seed preparation only; no worker or evaluator executed.",
    }
    encoded = json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    with (control / "plan.json").open("x", encoding="utf-8", newline="\n") as target:
        target.write(encoded)
        target.flush()
        os.fsync(target.fileno())
    return plan
