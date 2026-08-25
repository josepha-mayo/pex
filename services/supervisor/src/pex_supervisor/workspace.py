"""Worker-cwd observation. Does not import the hidden PexBench evaluator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

HIDDEN = ("evaluator.py", "metadata.yaml", "hidden_evaluator", "INVALID_LEAKED_RUNS_DO_NOT_USE")


def snapshot(workspace: str | Path, *, run_pytest: bool = False) -> dict[str, Any]:
    root = Path(workspace).resolve()
    if not root.is_dir():
        return {"workspace": str(root), "files": [], "pytest": None, "error": "cwd missing"}
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith(".") or ".pytest_cache" in path.parts:
            continue
        lowered = str(path).replace("\\", "/").lower()
        if any(marker in lowered for marker in HIDDEN) or path.name in {
            "evaluator.py",
            "metadata.yaml",
        }:
            continue
        files.append(str(path.relative_to(root)).replace("\\", "/"))
    result: dict[str, Any] = {"workspace": str(root), "files": files, "pytest": None}
    if run_pytest:
        result["pytest"] = {
            "ok": False,
            "skipped": True,
            "reason": (
                "PEX never executes untrusted workspace code inside the bridge process. "
                "Use harness-observed test output instead."
            ),
        }
    return result
