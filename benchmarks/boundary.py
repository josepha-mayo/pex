"""PexBench information boundary.

The controller may seed and score. PEX and the worker may not see hidden
evaluator material, stressor labels, or treatment-only prompts.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
HIDDEN_FILES = (ROOT / "evaluator.py",)
STRESSOR_GLOBS = ("tasks/*/metadata.yaml",)
PRIVATE_MARKERS = (
    "evaluator.py",
    "hidden_evaluator",
    "INVALID_LEAKED_RUNS_DO_NOT_USE",
    "metadata.yaml",
    "pexbench_",
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def public_prompt(task_id: str) -> str:
    path = ROOT / "tasks" / task_id / "prompt.md"
    return path.read_text(encoding="utf-8")


def assert_public_prompt(task_id: str, prompt: str) -> None:
    expected = public_prompt(task_id)
    if prompt != expected:
        raise AssertionError("worker prompt differs from the frozen public task prompt")


def workspace_manifest_sha256(workspace: Path) -> str:
    rows: list[tuple[str, str]] = []
    for path in sorted(workspace.rglob("*")):
        if not path.is_file() or ".pytest_cache" in path.parts:
            continue
        relative = str(path.relative_to(workspace)).replace("\\", "/")
        if any(marker.lower() in relative.lower() for marker in PRIVATE_MARKERS):
            raise AssertionError(f"private marker present in worker workspace: {relative}")
        rows.append((relative, hashlib.sha256(path.read_bytes()).hexdigest()))
    return sha256_text(json.dumps(rows, separators=(",", ":")))


def assert_public_intervention(text: str) -> None:
    lowered = text.replace("\\", "/").lower()
    for marker in PRIVATE_MARKERS:
        if marker.lower() in lowered:
            raise AssertionError(f"private benchmark marker in PEX intervention: {marker}")
    for phrase in (
        "handoff fact:",
        "schema.json is the source of truth",
        "do not stop until pytest passes",
    ):
        if phrase in lowered:
            raise AssertionError(f"treatment-only instruction in PEX intervention: {phrase}")


def worker_config_sha256(turn_params: dict) -> str:
    normalized = copy.deepcopy(turn_params)
    normalized.pop("threadId", None)
    normalized.pop("cwd", None)
    sandbox = normalized.get("sandboxPolicy")
    if isinstance(sandbox, dict) and "writableRoots" in sandbox:
        sandbox["writableRoots"] = ["<workspace>"]
    return sha256_text(json.dumps(normalized, sort_keys=True, default=str))


def opaque_workspace_name(run_id: str, arm: str, task_id: str) -> str:
    digest = hashlib.sha256(f"{run_id}:{arm}:{task_id}".encode()).hexdigest()[:16]
    return f"ws_{digest}"


def four_arm_source() -> str:
    return (ROOT / "four_arm.py").read_text(encoding="utf-8")


def forbids_treatment_suffix(source: str) -> None:
    forbidden = (
        "PEX_NUDGE",
        "Handoff fact:",
        "schema.json is the source of truth",
        "Do not stop until pytest passes",
        "append_better_prompt",
    )
    for token in forbidden:
        if token in source:
            raise AssertionError(f"treatment leakage token present in four_arm.py: {token!r}")


def supervisor_has_no_task_id_branches(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    text = path.read_text(encoding="utf-8")
    for needle in ("premature_stop", "permission_spam", "false_claim", "pexbench_"):
        if needle in text:
            raise AssertionError(f"{path} mentions benchmark identity {needle!r}")
    _ = tree
