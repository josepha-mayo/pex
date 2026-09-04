"""PexBench information boundary.

The controller may seed and score. PEX and the worker may not see hidden
evaluator material, stressor labels, or treatment-only prompts.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
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
IGNORED_WORKSPACE_PARTS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__"}
IGNORED_WORKSPACE_FILES = {".coverage"}
_HASH_CHUNK_BYTES = 1024 * 1024
_MAX_PUBLIC_PROMPT_BYTES = 512_000
_MAX_WORKSPACE_FILES = 10_000
_MAX_WORKSPACE_ENTRIES = 20_000
_MAX_WORKSPACE_FILE_BYTES = 64 * 1024 * 1024
_MAX_WORKSPACE_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_RELATIVE_PATH_CHARS = 1_024


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path, *, max_bytes: int | None = None) -> str:
    """Hash a worker file with bounded memory."""
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_BYTES):
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise ValueError(f"file exceeds the {max_bytes}-byte hash bound: {path.name}")
            digest.update(chunk)
    return digest.hexdigest()


def public_prompt(task_id: str) -> str:
    tasks = (ROOT / "tasks").resolve()
    path = (tasks / task_id / "prompt.md").resolve()
    if not path.is_relative_to(tasks) or not path.is_file():
        raise ValueError("invalid public benchmark task id")
    with path.open("rb") as handle:
        raw = handle.read(_MAX_PUBLIC_PROMPT_BYTES + 1)
    if len(raw) > _MAX_PUBLIC_PROMPT_BYTES:
        raise ValueError("public benchmark prompt exceeds the size bound")
    try:
        return raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("public benchmark prompt is not UTF-8") from exc


def assert_public_prompt(task_id: str, prompt: str) -> None:
    expected = public_prompt(task_id)
    if prompt != expected:
        raise AssertionError("worker prompt differs from the frozen public task prompt")


def workspace_manifest_sha256(workspace: Path) -> str:
    rows: list[tuple[str, str]] = []
    is_junction = getattr(workspace, "is_junction", None)
    if workspace.is_symlink() or bool(is_junction and is_junction()):
        raise ValueError("worker workspace root cannot be linked")
    root = workspace.resolve()
    if not root.is_dir():
        raise ValueError("worker workspace is not a directory")
    total_bytes = 0
    total_entries = 0
    ignored_parts = {part.casefold() for part in IGNORED_WORKSPACE_PARTS}
    ignored_files = {name.casefold() for name in IGNORED_WORKSPACE_FILES}

    def walk_error(error: OSError) -> None:
        raise error

    def link_like(path: Path) -> bool:
        is_junction = getattr(path, "is_junction", None)
        return path.is_symlink() or bool(is_junction and is_junction())

    for directory, names, filenames in os.walk(
        root,
        topdown=True,
        onerror=walk_error,
        followlinks=False,
    ):
        base = Path(directory)
        total_entries += len(names) + len(filenames)
        if total_entries > _MAX_WORKSPACE_ENTRIES:
            raise ValueError("worker workspace exceeds the 20000-entry fingerprint bound")
        kept_names: list[str] = []
        for name in sorted(names):
            path = base / name
            relative = path.relative_to(root)
            if link_like(path):
                raise AssertionError(f"link present in worker workspace: {relative}")
            if name.casefold() not in ignored_parts:
                kept_names.append(name)
        names[:] = kept_names
        for filename in sorted(filenames):
            path = base / filename
            relative_path = path.relative_to(root)
            if link_like(path):
                raise AssertionError(f"link present in worker workspace: {relative_path}")
            if filename.casefold() in ignored_files or not path.is_file():
                continue
            relative = str(relative_path).replace("\\", "/")
            if len(relative) > _MAX_RELATIVE_PATH_CHARS:
                raise ValueError("worker workspace path exceeds the fingerprint bound")
            if any(marker.casefold() in relative.casefold() for marker in PRIVATE_MARKERS):
                raise AssertionError(f"private marker present in worker workspace: {relative}")
            if len(rows) >= _MAX_WORKSPACE_FILES:
                raise ValueError("worker workspace exceeds the 10000-file fingerprint bound")
            size = path.stat().st_size
            if size > _MAX_WORKSPACE_FILE_BYTES:
                raise ValueError(f"worker file exceeds the 64 MiB fingerprint bound: {relative}")
            total_bytes += size
            if total_bytes > _MAX_WORKSPACE_TOTAL_BYTES:
                raise ValueError("worker workspace exceeds the 512 MiB fingerprint bound")
            rows.append((relative, sha256_file(path, max_bytes=_MAX_WORKSPACE_FILE_BYTES)))
    rows.sort()
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
    # The prompt is bound separately by prompt_sha256. Keeping it in the
    # configuration hash would make the allegedly pinned config differ for
    # every task and conceal real settings drift behind task text.
    normalized.pop("input", None)
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
