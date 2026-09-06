"""Workspace observation PEX is allowed to make.

PEX may inspect the worker's own cwd. It must not read hidden evaluator files,
stressor metadata, or anything outside that workspace.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
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
_MAX_MANIFEST_FILE_BYTES = 64 * 1024 * 1024
_MAX_MANIFEST_TOTAL_BYTES = 512 * 1024 * 1024
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


def _file_digest(path: Path) -> tuple[str, int]:
    """Hash a workspace file without loading an attacker-sized file into RAM."""
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
            size_bytes += len(chunk)
            if size_bytes > _MAX_MANIFEST_FILE_BYTES:
                raise ValueError(
                    f"workspace file exceeds the 64 MiB observation bound: {path.name}"
                )
    return digest.hexdigest(), size_bytes


def _public_file_manifest(root: Path) -> list[dict[str, Any]]:
    """Hash only ordinary files contained by the observed workspace."""
    rows: list[dict[str, Any]] = []
    total_bytes = 0
    for directory, names, filenames in os.walk(root, topdown=True, followlinks=False):
        base = Path(directory)
        names[:] = sorted(
            name
            for name in names
            if name not in IGNORED_PARTS
            and not (base / name).is_symlink()
            and not is_hidden_path(base / name)
        )
        for filename in sorted(filenames):
            path = base / filename
            if (
                path.is_symlink()
                or filename in IGNORED_FILES
                or filename.casefold().startswith(".env")
                or is_hidden_path(path)
            ):
                continue
            safe_path = assert_readable(root, path)
            try:
                relative_path = safe_path.relative_to(root)
                declared_size = safe_path.stat().st_size
            except (OSError, ValueError) as exc:
                raise ValueError("workspace changed while it was being observed") from exc
            if declared_size > _MAX_MANIFEST_FILE_BYTES:
                raise ValueError(
                    f"workspace file exceeds the 64 MiB observation bound: {filename}"
                )
            if len(rows) >= _MAX_MANIFEST_FILES:
                raise ValueError("workspace exceeds the 10000-file observation bound")
            sha256, size_bytes = _file_digest(safe_path)
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
    manifest = _public_file_manifest(root)
    return {
        "workspace": str(root),
        "files": [row["path"] for row in manifest],
        "file_manifest": manifest,
        "public_workspace_sha256": _manifest_sha256(manifest),
        "pytest": pytest_result,
    }
