"""Worker-cwd observation. Does not import the hidden PexBench evaluator."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

HIDDEN = ("evaluator.py", "metadata.yaml", "hidden_evaluator", "INVALID_LEAKED_RUNS_DO_NOT_USE")
ARTIFACT_TAILS = (
    "results.json",
    "results.jsonl",
    "junit.xml",
    "pytest.xml",
    "test-results.xml",
)


def _hidden(path: Path, root: Path) -> bool:
    lowered = str(path).replace("\\", "/").lower()
    if any(marker in lowered for marker in HIDDEN) or path.name in {"evaluator.py", "metadata.yaml"}:
        return True
    return False


def snapshot(workspace: str | Path, *, run_pytest: bool = False) -> dict[str, Any]:
    root = Path(workspace).resolve()
    if not root.is_dir():
        return {"workspace": str(root), "files": [], "pytest": None, "error": "cwd missing"}
    files: list[str] = []
    file_meta: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith(".") or ".pytest_cache" in path.parts:
            continue
        if _hidden(path, root):
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        files.append(rel)
        try:
            stat = path.stat()
            file_meta.append({"path": rel, "bytes": stat.st_size, "mtime": int(stat.st_mtime)})
        except OSError:
            file_meta.append({"path": rel})
        if len(files) >= 400:
            break
    result: dict[str, Any] = {
        "workspace": str(root),
        "files": files,
        "file_meta": file_meta,
        "pytest": None,
        "git": git_snapshot(root),
        "artifacts": artifact_tails(root),
    }
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


def git_snapshot(root: Path) -> dict[str, Any]:
    def _run(args: list[str]) -> str:
        try:
            proc = subprocess.run(
                args,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        raw = (proc.stdout or proc.stderr or "")[:8000]
        for marker in HIDDEN:
            if marker.lower() in raw.lower():
                raw = "\n".join(
                    line for line in raw.splitlines() if marker.lower() not in line.lower()
                )
        return raw

    if not (root / ".git").exists():
        return {"available": False}
    return {
        "available": True,
        "status": _run(["git", "status", "--porcelain"]),
        "diff_stat": _run(["git", "diff", "--stat"]),
        "diff": _run(["git", "diff"]),
    }


def read_visible(root: Path, relpath: str, limit: int = 12000) -> dict[str, Any]:
    target = (root / relpath).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return {"error": "path escapes workspace"}
    if not target.is_file():
        return {"error": "missing", "path": relpath}
    if _hidden(target, root):
        return {"error": "hidden"}
    try:
        data = target.read_bytes()[:limit]
    except OSError as exc:
        return {"error": str(exc)}
    return {"path": relpath, "bytes": target.stat().st_size, "text": data.decode("utf-8", "replace")}


def artifact_tails(root: Path, limit: int = 4000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in ARTIFACT_TAILS:
        path = root / name
        if path.is_file() and not _hidden(path, root):
            try:
                text = path.read_bytes()[:limit].decode("utf-8", "replace")
            except OSError:
                continue
            out.append({"path": name, "bytes": path.stat().st_size, "tail": text})
    return out
