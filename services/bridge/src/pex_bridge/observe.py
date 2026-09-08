"""Workspace observation PEX is allowed to make.

PEX may inspect the worker's own cwd. It must not read hidden evaluator files,
stressor metadata, or anything outside that workspace.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pex_protocol.redaction import redact_text
from pex_protocol.windows_job import CREATE_SUSPENDED, assign_job_and_resume, close_job


def _assign_windows_job(proc: subprocess.Popen[bytes]):
    return assign_job_and_resume(proc)


def _terminate_process_tree(proc: subprocess.Popen[bytes]) -> None:
    job = getattr(proc, "_pex_job", None)
    if job is not None:
        close_job(job)
        proc._pex_job = None
    elif os.name != "nt" and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
    elif proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass

HIDDEN_NAME_MARKERS = (
    "evaluator.py",
    "metadata.yaml",
    "hidden_evaluator",
    "INVALID_LEAKED_RUNS_DO_NOT_USE",
    "PEX_CORE_SPEC",
    "PEX_BUILD_SPEC",
)
IGNORED_PARTS = {
    ".aws",
    ".azure",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".ssh",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}
IGNORED_FILES = {".coverage", ".npmrc", ".pypirc", "auth.json", "credentials.json"}
_MAX_PYTEST_OUTPUT = 1500
_HASH_CHUNK_BYTES = 1024 * 1024
_MAX_MANIFEST_FILES = 10_000
_MAX_MANIFEST_ENTRIES = 20_000
_MAX_MANIFEST_FILE_BYTES = 64 * 1024 * 1024
_MAX_MANIFEST_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_MANIFEST_SECONDS = 5.0
_MAX_PUBLIC_TEST_FILES = 256
_PYTEST_TIMEOUT_SECONDS = 60
_PUBLIC_ENV_KEYS = {
    "CI",
    "COMSPEC",
    "LANG",
    "LC_ALL",
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TMP",
    "WINDIR",
}


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


def _check_observation_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise ValueError("workspace observation exceeded its time budget")


def _file_digest(path: Path, *, deadline: float | None = None) -> tuple[str, int]:
    """Hash a workspace file without loading an attacker-sized file into RAM."""
    _check_observation_deadline(deadline)
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError("linked or non-regular workspace file rejected")
    if path.resolve(strict=True) != path:
        raise ValueError("workspace file changed before observation")
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise ValueError("linked or non-regular workspace file rejected")
        if (
            not os.path.samestat(before, opened)
            or not os.path.samestat(path.stat(follow_symlinks=False), opened)
            or path.resolve(strict=True) != path
        ):
            raise ValueError("workspace file changed during observation")
        while True:
            _check_observation_deadline(deadline)
            chunk = handle.read(_HASH_CHUNK_BYTES)
            _check_observation_deadline(deadline)
            if not chunk:
                break
            digest.update(chunk)
            size_bytes += len(chunk)
            if size_bytes > _MAX_MANIFEST_FILE_BYTES:
                raise ValueError(
                    f"workspace file exceeds the 64 MiB observation bound: {path.name}"
                )
        after = os.fstat(handle.fileno())
        if (
            after.st_nlink != 1
            or after.st_size != size_bytes
            or after.st_size != opened.st_size
            or after.st_mtime_ns != opened.st_mtime_ns
            or not os.path.samestat(path.stat(follow_symlinks=False), after)
            or path.resolve(strict=True) != path
        ):
            raise ValueError("workspace file changed during observation")
    return digest.hexdigest(), size_bytes


def _bounded_workspace_files(root: Path, deadline: float) -> Iterator[tuple[Path, list[str]]]:
    """Enumerate incrementally: os.walk builds an unbounded directory list first."""
    pending = [(root, root.stat(follow_symlinks=False))]
    entries_seen = 0
    while pending:
        _check_observation_deadline(deadline)
        base, expected = pending.pop()
        current = base.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(current.st_mode)
            or not os.path.samestat(expected, current)
            or base.resolve(strict=True) != base
            or not base.is_relative_to(root)
        ):
            raise ValueError("workspace directory changed during observation")
        directories: list[tuple[Path, os.stat_result]] = []
        filenames: list[str] = []
        with os.scandir(base) as entries:
            if (
                not os.path.samestat(current, base.stat(follow_symlinks=False))
                or base.resolve(strict=True) != base
            ):
                raise ValueError("workspace directory changed during observation")
            for entry in entries:
                _check_observation_deadline(deadline)
                entries_seen += 1
                if entries_seen > _MAX_MANIFEST_ENTRIES:
                    raise ValueError("workspace exceeds the 20000-entry observation bound")
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    path = base / entry.name
                    if entry.name.casefold() not in IGNORED_PARTS and not is_hidden_path(path):
                        # Windows DirEntry.stat can omit the file identity fields.
                        directories.append((path, path.stat(follow_symlinks=False)))
                else:
                    filenames.append(entry.name)
        _check_observation_deadline(deadline)
        if (
            not os.path.samestat(current, base.stat(follow_symlinks=False))
            or base.resolve(strict=True) != base
        ):
            raise ValueError("workspace directory changed during observation")
        pending.extend(sorted(directories, key=lambda item: item[0].name, reverse=True))
        yield base, sorted(filenames)


def _public_file_manifest(root: Path) -> list[dict[str, Any]]:
    """Hash only ordinary files contained by the observed workspace."""
    # Cooperative checks bound further work; they cannot interrupt a blocked OS read.
    deadline = time.monotonic() + _MAX_MANIFEST_SECONDS
    rows: list[dict[str, Any]] = []
    total_bytes = 0
    for base, filenames in _bounded_workspace_files(root, deadline):
        _check_observation_deadline(deadline)
        for filename in filenames:
            _check_observation_deadline(deadline)
            path = base / filename
            if (
                path.is_symlink()
                or filename.casefold() in IGNORED_FILES
                or filename.casefold().startswith(".env")
                or is_hidden_path(path)
            ):
                continue
            safe_path = assert_readable(root, path)
            try:
                relative_path = safe_path.relative_to(root)
                declared = safe_path.stat(follow_symlinks=False)
                declared_size = declared.st_size
            except (OSError, ValueError) as exc:
                raise ValueError("workspace changed while it was being observed") from exc
            if not stat.S_ISREG(declared.st_mode) or declared.st_nlink != 1:
                raise ValueError("linked or non-regular workspace file rejected")
            if declared_size > _MAX_MANIFEST_FILE_BYTES:
                raise ValueError(
                    f"workspace file exceeds the 64 MiB observation bound: {filename}"
                )
            if len(rows) >= _MAX_MANIFEST_FILES:
                raise ValueError("workspace exceeds the 10000-file observation bound")
            if total_bytes + declared_size > _MAX_MANIFEST_TOTAL_BYTES:
                raise ValueError("workspace exceeds the 512 MiB observation bound")
            sha256, size_bytes = _file_digest(safe_path, deadline=deadline)
            _check_observation_deadline(deadline)
            total_bytes += size_bytes
            if total_bytes > _MAX_MANIFEST_TOTAL_BYTES:
                raise ValueError("workspace exceeds the 512 MiB observation bound")
            rows.append(
                {
                    "path": str(relative_path).replace("\\", "/"),
                    "sha256": sha256,
                    "size_bytes": size_bytes,
                }
            )
    _check_observation_deadline(deadline)
    return rows


def _manifest_sha256(rows: list[dict[str, Any]]) -> str:
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _public_pytest(root: Path, files: list[str]) -> dict[str, Any] | None:
    tests = [name for name in files if Path(name).name.startswith("test_") and name.endswith(".py")]
    if not tests:
        return None
    if len(tests) > _MAX_PUBLIC_TEST_FILES:
        raise ValueError("workspace exceeds the 256-test-file observation bound")
    # The worker tests are untrusted input.  Never copy the bridge process's
    # provider tokens, auth material, or arbitrary environment into them.
    env = {key: os.environ[key] for key in _PUBLIC_ENV_KEYS if key in os.environ}
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    creation_flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if os.name == "nt":
        creation_flags |= CREATE_SUSPENDED
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=line",
            "-p",
            "no:cacheprovider",
            "--confcutdir",
            str(root),
            "-o",
            "testpaths=",
            "-o",
            "addopts=",
            *tests,
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=creation_flags,
        start_new_session=os.name != "nt",
        bufsize=0,
    )
    job = _assign_windows_job(proc)
    proc._pex_job = job
    if proc.stdout is None:  # pragma: no cover - PIPE guarantees this
        raise RuntimeError("public pytest output pipe was not created")
    tail = bytearray()

    def drain() -> None:
        try:
            while chunk := proc.stdout.read(4096):
                tail.extend(chunk)
                if len(tail) > 16_384:
                    del tail[:-16_384]
        except (OSError, ValueError):
            pass

    reader = threading.Thread(target=drain, name="pex-public-pytest-output", daemon=True)
    reader.start()
    timed_out = False
    try:
        try:
            exit_code = proc.wait(timeout=_PYTEST_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_tree(proc)
            job = None
            exit_code = proc.wait(timeout=5)
        reader.join(timeout=2)
        output = bytes(tail).decode("utf-8", errors="replace")[-_MAX_PYTEST_OUTPUT:]
        output, _ = redact_text(output)
        output = output or ""
        if any(marker.lower() in output.lower() for marker in HIDDEN_NAME_MARKERS):
            output = "[public pytest output withheld: hidden benchmark marker detected]"
        if timed_out:
            output = f"[public pytest timed out after {_PYTEST_TIMEOUT_SECONDS}s]\n{output}".strip()
        return {
            "ok": not timed_out and exit_code == 0,
            "exit_code": exit_code,
            "output": output,
            "timed_out": timed_out,
        }
    finally:
        if proc.poll() is None:
            _terminate_process_tree(proc)
            job = None
            try:
                proc.wait(timeout=5)
            except subprocess.SubprocessError:
                pass
        # Popen does not close caller-owned PIPE handles after wait(). Closing
        # also releases a blocked reader if an exceptional path interrupted us.
        proc.stdout.close()
        reader.join(timeout=1)
        if job is not None:
            _terminate_process_tree(proc)


def snapshot(workspace: Path, *, run_pytest: bool = False) -> dict[str, Any]:
    """Observe public state; execute workspace tests only after explicit authorization."""
    root = workspace.resolve()
    if not root.is_dir():
        raise ValueError(f"workspace is not a directory: {root}")
    before = _public_file_manifest(root)
    pytest_result = _public_pytest(root, [row["path"] for row in before]) if run_pytest else None
    # Public tests can legitimately write artifacts. Re-scan afterward so the
    # fingerprint describes the state actually presented to the supervisor.
    manifest = _public_file_manifest(root) if run_pytest else before
    return {
        "workspace": str(root),
        "files": [row["path"] for row in manifest],
        "file_manifest": manifest,
        "public_workspace_sha256": _manifest_sha256(manifest),
        "pytest": pytest_result,
    }
