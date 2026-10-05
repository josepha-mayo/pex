"""Worker-cwd observation. Does not import the hidden PexBench evaluator."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import threading
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from math import isfinite
from pathlib import Path
from typing import Any, BinaryIO

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
MAX_INVENTORY_ENTRIES = 4_000
MAX_INVENTORY_SECONDS = 2.0
MAX_FINGERPRINT_BYTES = 1_000_000
MAX_VISIBLE_READ_BYTES = 1_000_000
MAX_SEALED_ACCEPTANCE_FILE_BYTES = 64_000
MAX_SEALED_ACCEPTANCE_TOTAL_BYTES = 256_000
MAX_SEALED_ACCEPTANCE_FILES = 64
_ACCEPTANCE_DIR_NAMES = {
    "__mocks__",
    "__tests__",
    "fixture",
    "fixtures",
    "spec",
    "test",
    "tests",
}
# Runner/injection config: adding one of these after the baseline can
# deselect tests, autoload code, or swap test dependencies — flagged on add.
_ACCEPTANCE_CONFIG_NAMES = {
    ".coveragerc",
    ".mocharc",
    ".mocharc.json",
    ".mocharc.yml",
    "conftest.py",
    "jest.config.cjs",
    "jest.config.js",
    "jest.config.mjs",
    "jest.config.ts",
    "karma.conf.cjs",
    "karma.conf.js",
    "makefile",
    "noxfile.py",
    "package.json",
    "playwright.config.js",
    "playwright.config.ts",
    "pyproject.toml",
    "pytest.ini",
    "setup.cfg",
    "setup.py",
    "sitecustomize.py",
    "tox.ini",
    "usercustomize.py",
    "vitest.config.js",
    "vitest.config.mts",
    "vitest.config.ts",
}
# Surface-only test files: fingerprinted, but adding them is not a flag.
_ACCEPTANCE_FILE_NAMES = _ACCEPTANCE_CONFIG_NAMES | {
    "test.py",
    "tests.py",
}
_ACCEPTANCE_NAME_RE = re.compile(
    r"(?:test_[^/]*\.[^./]+|.*_test\.[^./]+|.*\.(?:test|spec)\.[^./]+)$",
    re.I,
)
_ACCEPTANCE_CONFIG_RE = re.compile(
    r"(?:babel\.config\.[^./]+|cypress\.config\.[^./]+"
    r"|requirements[^./]*\.txt|pipfile(?:\.lock)?|poetry\.lock|uv\.lock"
    r"|package-lock\.json)$",
    re.I,
)


def is_acceptance_config(relpath: str) -> bool:
    """Whether a path configures the test runner rather than adding cases.

    New test files after the baseline are weak signal; new runner
    configuration is not — ``conftest.py``/``pytest.ini``-style additions can
    deselect the very tests a claim relies on.
    """

    name = str(relpath).replace("\\", "/").rsplit("/", 1)[-1].casefold()
    return (
        name in _ACCEPTANCE_CONFIG_NAMES
        or _ACCEPTANCE_CONFIG_RE.fullmatch(name) is not None
    )
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def is_acceptance_surface(relpath: str) -> bool:
    """Whether one workspace-relative path shapes the declared acceptance surface.

    Test sources, fixtures directories, and test-runner configuration all
    decide what a reported green run actually proves, so a supervisor that
    verifies completion claims must treat changes to any of them as material.
    """

    parts = [part for part in str(relpath).replace("\\", "/").split("/") if part]
    if not parts:
        return False
    name = parts[-1].casefold()
    if name in _ACCEPTANCE_FILE_NAMES:
        return True
    if any(part.casefold() in _ACCEPTANCE_DIR_NAMES for part in parts[:-1]):
        return True
    return (
        _ACCEPTANCE_NAME_RE.fullmatch(name) is not None
        or _ACCEPTANCE_CONFIG_RE.fullmatch(name) is not None
    )


def _fingerprint_observed_file(
    path: Path, expected: os.stat_result
) -> tuple[str | None, str | None]:
    """Hash one file only while it provably stays the observed directory entry."""

    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or not os.path.samestat(expected, opened)
            ):
                return None, "changed"
            if opened.st_size > MAX_FINGERPRINT_BYTES:
                return None, "size_cap"
            data = handle.read(MAX_FINGERPRINT_BYTES + 1)
            after = os.fstat(handle.fileno())
            if (
                len(data) > MAX_FINGERPRINT_BYTES
                or after.st_size != opened.st_size
                or after.st_mtime_ns != opened.st_mtime_ns
                or not os.path.samestat(opened, after)
            ):
                return None, "changed"
            return hashlib.sha256(data).hexdigest(), None
    except OSError:
        return None, "unreadable"


def acceptance_fingerprints(
    workspace: dict[str, Any],
) -> dict[str, str | None] | None:
    """Return the observed acceptance-surface hashes from one snapshot dict."""

    if not isinstance(workspace, dict) or workspace.get("error"):
        return None
    file_meta = workspace.get("file_meta")
    if not isinstance(file_meta, list):
        return None
    out: dict[str, str | None] = {}
    for entry in file_meta:
        if not isinstance(entry, dict) or "sha256" not in entry:
            continue
        path = str(entry.get("path") or "").replace("\\", "/")
        if not path:
            continue
        digest = entry.get("sha256")
        out[path] = (
            digest
            if isinstance(digest, str) and _SHA256_RE.fullmatch(digest) is not None
            else None
        )
    return out


def _sealed_content_candidate(root: Path, relpath: str) -> Path | None:
    parts = [
        part for part in str(relpath).replace("\\", "/").split("/") if part
    ]
    if not parts or any(part == ".." for part in parts):
        return None
    try:
        resolved = root.joinpath(*parts).resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(root):
        return None
    return resolved


def captured_flagged_contents(
    workspace: dict[str, Any],
    paths: list[str],
) -> dict[str, str]:
    """Capture the exact bytes a flag was raised on, digest-bound to the scan.

    The incident that names ``tests/test_core.py`` as modified is stronger
    when it carries the observed text — the diff then shows what the worker
    actually weakened, even after the workspace is gone. Bytes are kept only
    when their sha256 equals the digest this snapshot recorded, so the
    captured text provably is what the flag compared against the baseline.
    """

    if not isinstance(workspace, dict) or workspace.get("error"):
        return {}
    file_meta = workspace.get("file_meta")
    if not isinstance(file_meta, list):
        return {}
    digests: dict[str, str] = {}
    for entry in file_meta:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "").replace("\\", "/")
        digest = entry.get("sha256")
        if path and isinstance(digest, str) and _SHA256_RE.fullmatch(digest):
            digests[path] = digest
    try:
        root = Path(str(workspace.get("workspace") or "")).resolve()
    except OSError:
        return {}
    captured: dict[str, str] = {}
    for relpath in paths[:MAX_SEALED_ACCEPTANCE_FILES]:
        digest = digests.get(str(relpath).replace("\\", "/"))
        if digest is None:
            continue
        candidate = _sealed_content_candidate(root, relpath)
        if candidate is None:
            continue
        try:
            data = candidate.read_bytes()
        except OSError:
            continue
        if (
            len(data) > MAX_SEALED_ACCEPTANCE_FILE_BYTES
            or hashlib.sha256(data).hexdigest() != digest
        ):
            continue
        try:
            captured[str(relpath).replace("\\", "/")] = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return captured


def sealed_acceptance_contents(
    workspace: str | Path,
    files: Mapping[str, str | None],
) -> dict[str, str]:
    """Return acceptance-file text whose bytes provably equal the sealed digest.

    Baseline digests come from a workspace snapshot; re-reading for the seal
    could race a worker write, so content is kept only when its sha256 equals
    the sealed digest for that path. Files that moved, changed, exceed the
    cap, or are not UTF-8 text are omitted — the evidence either shows the
    exact sealed bytes or stays digest-only.
    """

    try:
        root = Path(workspace).resolve()
    except OSError:
        return {}
    contents: dict[str, str] = {}
    total = 0
    for relpath, digest in files.items():
        if len(contents) >= MAX_SEALED_ACCEPTANCE_FILES:
            break
        if total >= MAX_SEALED_ACCEPTANCE_TOTAL_BYTES:
            break
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            continue
        candidate = _sealed_content_candidate(root, relpath)
        if candidate is None:
            continue
        try:
            data = candidate.read_bytes()
        except OSError:
            continue
        if (
            len(data) > MAX_SEALED_ACCEPTANCE_FILE_BYTES
            or total + len(data) > MAX_SEALED_ACCEPTANCE_TOTAL_BYTES
            or hashlib.sha256(data).hexdigest() != digest
        ):
            continue
        try:
            contents[relpath] = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        total += len(data)
    return contents
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


def _finite_json_float(value: str) -> float:
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"non-finite JSON number {value}")
    return parsed


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


def _workspace_inventory(
    root: Path,
) -> tuple[list[str], list[dict[str, Any]], bool, str | None]:
    """Build a deterministic, cooperative, mutation-aware workspace inventory."""

    files: list[str] = []
    file_meta: list[dict[str, Any]] = []
    pending = [root]
    entries_seen = 0
    deadline = time.monotonic() + MAX_INVENTORY_SECONDS
    incomplete_reason: str | None = None
    files_capped = False
    # Surface completeness is tracked separately from the inventory cap: the
    # walk continues past MAX_INVENTORY_FILES, but only far enough to
    # fingerprint acceptance-surface files. A truncated general listing must
    # not silently truncate the integrity baseline as well.
    surface_complete = True

    while pending:
        if time.monotonic() >= deadline:
            return files, file_meta, True, "time_bound", False
        directory = pending.pop()
        try:
            before = directory.stat(follow_symlinks=False)
            if (
                not stat.S_ISDIR(before.st_mode)
                or directory.resolve(strict=True) != directory
                or not directory.is_relative_to(root)
            ):
                return files, file_meta, True, "directory_identity_changed", False
            directories: list[Path] = []
            filenames: list[tuple[str, os.stat_result]] = []
            with os.scandir(directory) as entries:
                for entry in entries:
                    if time.monotonic() >= deadline:
                        return files, file_meta, True, "time_bound", False
                    entries_seen += 1
                    if entries_seen > MAX_INVENTORY_ENTRIES:
                        return files, file_meta, True, "entry_bound", False
                    path = directory / entry.name
                    is_junction = getattr(entry, "is_junction", lambda: False)()
                    if entry.is_symlink() or is_junction:
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if (
                            entry.name not in PRUNED_DIRECTORIES
                            and not _hidden(path, root)
                            and _inside_workspace(path, root)
                        ):
                            directories.append(path)
                    elif (
                        entry.is_file(follow_symlinks=False)
                        and not entry.name.startswith(".")
                        and not _hidden(path, root)
                        and _inside_workspace(path, root)
                    ):
                        # Windows DirEntry.stat can omit link/identity fields;
                        # capture through the concrete path for the later fence.
                        expected_file = path.stat(follow_symlinks=False)
                        if not stat.S_ISREG(expected_file.st_mode) or expected_file.st_nlink != 1:
                            incomplete_reason = incomplete_reason or "file_identity_unavailable"
                            # Hardlinked/identity-light acceptance files are
                            # still surface: record them unhashed so the
                            # verifier flags them instead of skipping silently.
                            rel_probe = str(path.relative_to(root)).replace("\\", "/")
                            if is_acceptance_surface(rel_probe):
                                file_meta.append(
                                    {
                                        "path": rel_probe,
                                        "bytes": expected_file.st_size,
                                        "mtime": int(expected_file.st_mtime),
                                        "sha256": None,
                                    }
                                )
                            continue
                        filenames.append((entry.name, expected_file))
            after = directory.stat(follow_symlinks=False)
            if (
                not os.path.samestat(before, after)
                or before.st_mtime_ns != after.st_mtime_ns
                or directory.resolve(strict=True) != directory
            ):
                return files, file_meta, True, "directory_changed_during_scan", False
        except OSError:
            return files, file_meta, True, "directory_unavailable", False

        pending.extend(sorted(directories, key=lambda item: item.name.casefold(), reverse=True))
        for filename, expected_file in sorted(filenames, key=lambda item: item[0].casefold()):
            if time.monotonic() >= deadline:
                return files, file_meta, True, "time_bound", False
            path = directory / filename
            rel = str(path.relative_to(root)).replace("\\", "/")
            surface = is_acceptance_surface(rel)
            if len(files) >= MAX_INVENTORY_FILES:
                files_capped = True
                if not surface:
                    continue
            try:
                observed = path.stat(follow_symlinks=False)
                if (
                    not stat.S_ISREG(observed.st_mode)
                    or observed.st_nlink != 1
                    or not os.path.samestat(expected_file, observed)
                    or expected_file.st_size != observed.st_size
                    or expected_file.st_mtime_ns != observed.st_mtime_ns
                    or path.resolve(strict=True) != path
                ):
                    return files, file_meta, True, "file_changed_during_scan", False
            except OSError:
                return files, file_meta, True, "file_metadata_unavailable", False
            meta: dict[str, Any] = {
                "path": rel,
                "bytes": observed.st_size,
                "mtime": int(observed.st_mtime),
            }
            if surface:
                digest, problem = _fingerprint_observed_file(path, expected_file)
                if problem == "changed":
                    return files, file_meta, True, "file_changed_during_scan", False
                if problem == "unreadable":
                    return files, file_meta, True, "fingerprint_unreadable", False
                meta["sha256"] = digest
                if problem == "size_cap":
                    incomplete_reason = incomplete_reason or "fingerprint_size_cap"
            if not files_capped:
                files.append(rel)
            file_meta.append(meta)

    return (
        files,
        file_meta,
        files_capped or incomplete_reason is not None,
        "file_bound" if files_capped else incomplete_reason,
        surface_complete,
    )


def snapshot(workspace: str | Path, *, run_pytest: bool = False) -> dict[str, Any]:
    root = Path(workspace).resolve()
    if not root.is_dir():
        return {"workspace": str(root), "files": [], "pytest": None, "error": "cwd missing"}
    files, file_meta, files_truncated, inventory_reason, surface_complete = (
        _workspace_inventory(root)
    )
    result: dict[str, Any] = {
        "workspace": str(root),
        "files": files,
        "file_meta": file_meta,
        "files_truncated": files_truncated,
        "inventory_reason": inventory_reason,
        "surface_complete": surface_complete,
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


@contextmanager
def _open_observed_file(path: Path):
    """Bind validation to the opened file, not a path a worker can swap later."""
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("non-regular file rejected")
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise ValueError("linked or non-regular file rejected")
        if (
            not os.path.samestat(before, opened)
            or not os.path.samestat(path.stat(), opened)
            or path.resolve() != path
        ):
            raise ValueError("file changed during observation")
        yield handle, opened


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
        with _open_observed_file(target) as (handle, opened):
            size = opened.st_size
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
            relative = path.relative_to(resolved_root)
            if not path.is_file() or _hidden(path, resolved_root):
                continue
            if any(part.startswith(".") or part.casefold() in PRUNED_DIRECTORIES
                   for part in relative.parts):
                continue
            with _open_observed_file(path) as (handle, opened):
                size = opened.st_size
                handle.seek(max(0, size - bounded_limit))
                text = handle.read(bounded_limit).decode("utf-8", "replace")
                # Count from the same checked descriptor as the preview: never
                # reopen a worker-controlled path after returning its bytes.
                row_count, count_complete = _artifact_row_count_from_handle(
                    handle, path.suffix.casefold(), MAX_ARTIFACT_COUNT_BYTES,
                )
        except (OSError, ValueError, OverflowError):
            continue
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

    Read at most the capped byte limit plus one overflow byte, even if a worker
    grows the file after stat. Larger or malformed documents remain unknown
    instead of producing a false acceptance verdict.
    """
    bounded_limit = _bounded_limit(json_limit, MAX_ARTIFACT_COUNT_BYTES)
    try:
        with _open_observed_file(path.resolve()) as (handle, _opened):
            return _artifact_row_count_from_handle(handle, path.suffix.casefold(), bounded_limit)
    except (OSError, ValueError):
        return None, False


def _artifact_row_count_from_handle(
    handle: BinaryIO, suffix: str, bounded_limit: int,
) -> tuple[int | None, bool]:
    try:
        if suffix not in {".json", ".jsonl"} or os.fstat(handle.fileno()).st_size > bounded_limit:
            return None, False
        handle.seek(0)
        payload = handle.read(bounded_limit + 1)
        if len(payload) > bounded_limit:
            return None, False
        if suffix == ".jsonl":
            count = 0
            for line in payload.split(b"\n"):
                if not line.strip():
                    continue
                json.loads(
                    line,
                    parse_constant=_reject_nonfinite_json_constant,
                    parse_float=_finite_json_float,
                    object_pairs_hook=_unique_json_object,
                )
                count += 1
            return count, True
        data = json.loads(
            payload.decode("utf-8"),
            parse_constant=_reject_nonfinite_json_constant,
            parse_float=_finite_json_float,
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
