"""Worker-cwd observation. Does not import the hidden PexBench evaluator."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pex_protocol.windows_job import CREATE_SUSPENDED, assign_job_and_resume, close_job

HIDDEN = (
    "evaluator.py",
    "metadata.yaml",
    "stressor.yaml",
    "expected_artifacts.yaml",
    "hidden_evaluator",
    "INVALID_LEAKED_RUNS_DO_NOT_USE",
)
ARTIFACT_TAILS = (
    "results.json",
    "results.jsonl",
    "junit.xml",
    "pytest.xml",
    "test-results.xml",
)


def _assign_windows_job(process: subprocess.Popen[bytes]):
    return assign_job_and_resume(process)


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    job = getattr(process, "_pex_job", None)
    if job is not None:
        close_job(job)
        process._pex_job = None
    elif os.name != "nt" and process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
    elif process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass


MAX_INVENTORY_FILES = 400
MAX_VISIBLE_READ_BYTES = 1_000_000
MAX_ARTIFACT_TAIL_BYTES = 64_000
MAX_ARTIFACT_COUNT_BYTES = 4_000_000
MAX_GIT_OUTPUT_BYTES = 8000
PRUNED_DIRECTORIES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}


def _reject_nonfinite_json_constant(value: str) -> None:
    """Reject Python's permissive NaN/Infinity extension to JSON."""

    raise ValueError(f"non-finite JSON constant {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _hidden(path: Path, root: Path) -> bool:
    lowered = str(path).replace("\\", "/").lower()
    if any(marker in lowered for marker in HIDDEN) or path.name in {
        "evaluator.py",
        "metadata.yaml",
    }:
        return True
    return False


def _inside_workspace(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _bounded_limit(value: object, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return min(maximum, max(0, parsed))


def snapshot(workspace: str | Path, *, run_pytest: bool = False) -> dict[str, Any]:
    root = Path(workspace).resolve()
    if not root.is_dir():
        return {"workspace": str(root), "files": [], "pytest": None, "error": "cwd missing"}
    files: list[str] = []
    file_meta: list[dict[str, Any]] = []
    files_truncated = False
    inventory_full = False
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            (
                name
                for name in dirnames
                if name not in PRUNED_DIRECTORIES
                and not _hidden(Path(directory) / name, root)
            ),
            key=str.casefold,
        )
        for filename in sorted(filenames, key=str.casefold):
            path = Path(directory) / filename
            if (
                filename.startswith(".")
                or _hidden(path, root)
                or not _inside_workspace(path, root)
            ):
                continue
            if len(files) >= MAX_INVENTORY_FILES:
                files_truncated = True
                inventory_full = True
                break
            rel = str(path.relative_to(root)).replace("\\", "/")
            files.append(rel)
            try:
                stat = path.stat()
                file_meta.append(
                    {"path": rel, "bytes": stat.st_size, "mtime": int(stat.st_mtime)}
                )
            except OSError:
                file_meta.append({"path": rel})
        if inventory_full:
            break
    result: dict[str, Any] = {
        "workspace": str(root),
        "files": files,
        "file_meta": file_meta,
        "files_truncated": files_truncated,
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
    git_path = shutil.which("git")
    if not git_path:
        return {"available": False, "error": "git unavailable"}
    resolved_git = Path(git_path).resolve()
    if _inside_workspace(resolved_git, root):
        return {"available": False, "error": "workspace git executable rejected"}
    git_path = str(resolved_git)
    git_env = {
        name: value
        for name in (
            "COMSPEC",
            "LANG",
            "LC_ALL",
            "PATHEXT",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "TMPDIR",
            "WINDIR",
        )
        if (value := os.environ.get(name))
    }
    safe_path = [str(resolved_git.parent)]
    system_root = os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR")
    if system_root:
        safe_path.append(str(Path(system_root) / "System32"))
    git_env["PATH"] = os.pathsep.join(safe_path)
    git_env.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )

    def _run(args: list[str]) -> str:
        command = [
            git_path,
            "--no-pager",
            "-c",
            "core.fsmonitor=false",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "diff.external=",
            *args,
        ]
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        creation_flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if os.name == "nt":
            creation_flags |= CREATE_SUSPENDED
        process: subprocess.Popen[bytes] | None = None
        job = None
        try:
            process = subprocess.Popen(
                command,
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=git_env,
                creationflags=creation_flags,
                start_new_session=os.name != "nt",
                bufsize=0,
            )
            job = _assign_windows_job(process)
            process._pex_job = job
            if process.stdout is None:
                raise OSError("git output pipe unavailable")

            def _read_output() -> bytes:
                output = bytearray()
                while len(output) <= MAX_GIT_OUTPUT_BYTES:
                    chunk = process.stdout.read(
                        min(4096, MAX_GIT_OUTPUT_BYTES + 1 - len(output))
                    )
                    if not chunk:
                        break
                    output.extend(chunk)
                return bytes(output)

            captured: list[bytes] = []
            reader = threading.Thread(
                target=lambda: captured.append(_read_output()),
                name="pex-git-output",
                daemon=True,
            )
            reader.start()
            reader.join(timeout=4)
            if reader.is_alive():
                _terminate_process_tree(process)
                job = None
                process.stdout.close()
                reader.join(timeout=2)
                return ""
            raw = captured[0] if captured else b""
            if len(raw) > MAX_GIT_OUTPUT_BYTES and process.poll() is None:
                _terminate_process_tree(process)
                job = None
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                _terminate_process_tree(process)
                job = None
                process.wait(timeout=1)
            return raw[:MAX_GIT_OUTPUT_BYTES].decode("utf-8", "replace")
        except (OSError, subprocess.SubprocessError):
            return ""
        finally:
            if process is not None:
                if process.poll() is None:
                    _terminate_process_tree(process)
                    job = None
                    try:
                        process.wait(timeout=1)
                    except (OSError, subprocess.SubprocessError):
                        pass
                if process.stdout is not None:
                    process.stdout.close()
                if job is not None:
                    _terminate_process_tree(process)

    def _visible_lines(raw: str) -> str:
        for marker in HIDDEN:
            if marker.lower() in raw.lower():
                raw = "\n".join(
                    line for line in raw.splitlines() if marker.lower() not in line.lower()
                )
        return raw

    def _visible_diff(raw: str) -> str:
        visible: list[str] = []
        hidden_section = False
        for line in raw.splitlines():
            if line.startswith("diff --git "):
                lowered = line.lower()
                hidden_section = any(marker.lower() in lowered for marker in HIDDEN)
            if not hidden_section:
                visible.append(line)
        return "\n".join(visible)

    if not (root / ".git").exists():
        return {"available": False}
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="pex-git-snapshot") as pool:
        status_future = pool.submit(_run, ["status", "--porcelain"])
        stat_future = pool.submit(
            _run,
            [
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--ignore-submodules=all",
                "--stat",
            ],
        )
        diff_future = pool.submit(
            _run,
            [
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--ignore-submodules=all",
                "--no-renames",
                "--unified=1",
            ],
        )
        status = status_future.result()
        diff_stat = stat_future.result()
        diff = diff_future.result()
    return {
        "available": True,
        "status": _visible_lines(status),
        "diff_stat": _visible_lines(diff_stat),
        "diff": _visible_diff(diff),
    }


def read_visible(root: Path, relpath: str, limit: int = 12000) -> dict[str, Any]:
    try:
        root = root.resolve()
        target = (root / relpath).resolve()
        target.relative_to(root.resolve())
    except (OSError, ValueError):
        return {"error": "path escapes workspace"}
    if not target.is_file():
        return {"error": "missing", "path": relpath}
    if _hidden(target, root):
        return {"error": "hidden"}
    bounded_limit = _bounded_limit(limit, MAX_VISIBLE_READ_BYTES)
    try:
        size = target.stat().st_size
        with target.open("rb") as handle:
            data = handle.read(bounded_limit)
    except (OSError, ValueError, OverflowError) as exc:
        return {"error": str(exc)}
    return {
        "path": relpath,
        "bytes": size,
        "text": data.decode("utf-8", "replace"),
    }


def artifact_tails(root: Path, limit: int = 4000) -> list[dict[str, Any]]:
    bounded_limit = _bounded_limit(limit, MAX_ARTIFACT_TAIL_BYTES)
    out: list[dict[str, Any]] = []
    try:
        resolved_root = root.resolve(strict=True)
    except (OSError, ValueError):
        return out
    for name in ARTIFACT_TAILS:
        try:
            path = (resolved_root / name).resolve(strict=True)
            path.relative_to(resolved_root)
            if not path.is_file() or _hidden(path, resolved_root):
                continue
            size = path.stat().st_size
            with path.open("rb") as handle:
                handle.seek(max(0, size - bounded_limit))
                text = handle.read(bounded_limit).decode("utf-8", "replace")
        except (OSError, ValueError, OverflowError):
            continue
        row_count, count_complete = artifact_row_count(path)
        out.append(
            {
                "path": name,
                "bytes": size,
                "tail": text,
                "row_count": row_count,
                "row_count_complete": count_complete,
            }
        )
    return out


def artifact_row_count(
    path: Path,
    json_limit: int = MAX_ARTIFACT_COUNT_BYTES,
) -> tuple[int | None, bool]:
    """Count a complete artifact without mistaking a truncated preview for the file.

    JSONL can be counted as a stream. JSON is parsed only under a bounded size;
    larger or malformed documents remain unknown instead of producing a false
    acceptance verdict.
    """
    try:
        size = path.stat().st_size
        if size > json_limit:
            return None, False
        if path.suffix.casefold() == ".jsonl":
            count = 0
            with path.open("rb") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    json.loads(
                        line,
                        parse_constant=_reject_nonfinite_json_constant,
                        object_pairs_hook=_unique_json_object,
                    )
                    count += 1
            return count, True
        if path.suffix.casefold() != ".json":
            return None, False
        data = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite_json_constant,
            object_pairs_hook=_unique_json_object,
        )
    except (OSError, UnicodeError, ValueError, RecursionError):
        return None, False
    if isinstance(data, list):
        return len(data), True
    if isinstance(data, dict):
        for key in ("rows", "items", "records", "results", "data"):
            if isinstance(data.get(key), list):
                return len(data[key]), True
    return None, False
