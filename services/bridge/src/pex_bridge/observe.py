"""Workspace observation PEX is allowed to make.

PEX may inspect the worker's own cwd. It must not read hidden evaluator files,
stressor metadata, or anything outside that workspace.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

HIDDEN_NAME_MARKERS = (
    "evaluator.py",
    "metadata.yaml",
    "hidden_evaluator",
    "INVALID_LEAKED_RUNS_DO_NOT_USE",
    "PEX_CORE_SPEC",
    "PEX_BUILD_SPEC",
)


def is_hidden_path(path: Path) -> bool:
    text = str(path).replace("\\", "/").lower()
    name = path.name.lower()
    if name in {"evaluator.py", "metadata.yaml"}:
        return True
    return any(marker.lower() in text for marker in HIDDEN_NAME_MARKERS)


def assert_readable(root: Path, target: Path) -> Path:
    root = root.resolve()
    target = target.resolve()
    if is_hidden_path(target):
        raise PermissionError(f"PEX may not read hidden benchmark material: {target}")
    if not target.is_relative_to(root):
        raise PermissionError(f"PEX may not read outside the worker workspace: {target}")
    return target


def snapshot(workspace: Path, *, run_pytest: bool = True) -> dict[str, Any]:
    """Observe files and visible tests in the worker workspace only."""
    root = workspace.resolve()
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith(".") or ".pytest_cache" in path.parts:
            continue
        if is_hidden_path(path):
            continue
        files.append(str(path.relative_to(root)).replace("\\", "/"))
    result: dict[str, Any] = {"workspace": str(root), "files": files, "pytest": None}
    if run_pytest and any(name.startswith("test_") and name.endswith(".py") for name in files):
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=line", "-o", "testpaths=", "-o", "addopts="],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        out = ((proc.stdout or "") + (proc.stderr or ""))[-1500:]
        result["pytest"] = {"ok": proc.returncode == 0, "output": out}
    return result
