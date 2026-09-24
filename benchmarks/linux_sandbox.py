"""Optional Linux boundary for executing benchmark candidate code.

This isolates the *evaluator's* child process. It does not isolate a coding
worker or PEX, so enabling it alone never makes a presentation run eligible.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def enabled() -> bool:
    value = os.environ.get("PEX_BENCH_EVALUATOR_SANDBOX", "")
    if value not in {"", "linux-bwrap"}:
        raise ValueError("PEX_BENCH_EVALUATOR_SANDBOX must be linux-bwrap or unset")
    return value == "linux-bwrap"


def _runtime_python() -> Path:
    """Use a system Python whose complete runtime is in the mounted /usr tree."""
    configured = os.environ.get("PEX_BENCH_SANDBOX_PYTHON", "/usr/bin/python3")
    python = Path(configured)
    if not python.is_absolute() or not python.is_file():
        raise RuntimeError("sandbox Python must be an existing absolute executable")
    resolved = python.resolve()
    if not resolved.is_relative_to(Path("/usr")):
        raise RuntimeError("sandbox Python must resolve inside /usr")
    return python


def _prefix(workspace: Path, checker: Path | None = None) -> list[str]:
    if sys.platform != "linux":
        raise RuntimeError("Linux bubblewrap evaluator selected on another platform")
    binary = Path("/usr/bin/bwrap")
    if not binary.is_file() or binary.resolve() != binary:
        raise RuntimeError("Linux bubblewrap evaluator requires /usr/bin/bwrap")
    metadata = binary.stat()
    if metadata.st_uid != 0 or metadata.st_mode & 0o022:
        raise RuntimeError("Linux bubblewrap evaluator requires a trusted root-owned binary")
    root = workspace.resolve(strict=True)
    if root != workspace.absolute() or not root.is_dir() or os.path.ismount(root):
        raise RuntimeError("candidate workspace must be a real, unlinked directory")
    entries = 0
    for current, directories, files in os.walk(root, followlinks=False):
        for name in (*directories, *files):
            entries += 1
            if entries > 20_000:
                raise RuntimeError("candidate workspace exceeds the sandbox entry limit")
            item = Path(current) / name
            if item.is_symlink() or os.path.ismount(item):
                raise RuntimeError("candidate workspace contains a link or mount")
            if name in files and item.stat(follow_symlinks=False).st_nlink > 1:
                raise RuntimeError("candidate workspace contains a hard-linked file")
    command = [
        str(binary),
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--setenv",
        "HOME",
        "/tmp",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "PYTHONNOUSERSITE",
        "1",
        "--ro-bind",
        "/usr",
        "/usr",
    ]
    for library in ("/lib", "/lib64"):
        if Path(library).exists():
            command.extend(("--ro-bind", library, library))
    command.extend(
        (
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--ro-bind",
            str(root),
            "/workspace",
        )
    )
    if checker is not None:
        source = checker.resolve(strict=True)
        if source != checker.absolute() or not source.is_file():
            raise RuntimeError("private checker must be a real, unlinked file")
        command.extend(("--ro-bind", str(source), "/checker.py"))
    command.extend(("--chdir", "/workspace", "--"))
    return command


def hidden_command(workspace: Path, checker: Path, module: str, function: str) -> list[str]:
    return [
        *_prefix(workspace, checker),
        str(_runtime_python()),
        "-I",
        "-B",
        "/checker.py",
        "/workspace",
        module,
        function,
    ]


def public_pytest_command(workspace: Path, files: list[str]) -> list[str]:
    if not files or any(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.py", name) is None or ".." in name
        for name in files
    ):
        raise ValueError("public test filenames must be plain workspace basenames")
    return [
        *_prefix(workspace),
        str(_runtime_python()),
        "-I",
        "-B",
        "-X",
        "pycache_prefix=/tmp/pycache",
        "-m",
        "pytest",
        "-q",
        "--tb=line",
        "-p",
        "no:cacheprovider",
        "--confcutdir",
        "/workspace",
        "-c",
        "/dev/null",
        "-o",
        "testpaths=",
        "-o",
        "addopts=",
        *files,
    ]
