"""Optional Linux boundaries for benchmark candidate code and worker tools.

The evaluator child and writable-worker primitive have distinct mounts. Live
coding-harness/model transport and isolated PEX integration are still missing,
so enabling this module alone never makes a presentation run eligible.
"""

from __future__ import annotations

import os
import stat
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


def _audited_directory(directory: Path, label: str) -> Path:
    root = directory.resolve(strict=True)
    if root != directory.absolute() or not root.is_dir() or os.path.ismount(root):
        raise RuntimeError(f"{label} must be a real, unlinked directory")
    entries = 0
    for current, directories, files in os.walk(root, followlinks=False):
        for name in (*directories, *files):
            entries += 1
            if entries > 20_000:
                raise RuntimeError(f"{label} exceeds the sandbox entry limit")
            item = Path(current) / name
            if item.is_symlink() or os.path.ismount(item):
                raise RuntimeError(f"{label} contains a link or mount")
            metadata = item.stat(follow_symlinks=False)
            if name in files:
                if not stat.S_ISREG(metadata.st_mode):
                    raise RuntimeError(f"{label} contains a special file")
                if metadata.st_nlink > 1:
                    raise RuntimeError(f"{label} contains a hard-linked file")
    return root


def _prefix(
    workspace: Path, checker: Path | None = None, *, writable_worker: bool = False,
) -> list[str]:
    if writable_worker and checker is not None:
        raise ValueError("a worker boundary must never mount the private checker")
    if sys.platform != "linux":
        raise RuntimeError("Linux bubblewrap evaluator selected on another platform")
    binary = Path("/usr/bin/bwrap")
    if not binary.is_file() or binary.resolve() != binary:
        raise RuntimeError("Linux bubblewrap evaluator requires /usr/bin/bwrap")
    metadata = binary.stat()
    if metadata.st_uid != 0 or metadata.st_mode & 0o022:
        raise RuntimeError("Linux bubblewrap evaluator requires a trusted root-owned binary")
    root = _audited_directory(workspace, "candidate workspace")
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
            "--bind" if writable_worker else "--ro-bind",
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


def worker_command(workspace: Path, command: list[str]) -> list[str]:
    """Run worker tools with only the task writable and no host network.

    This primitive is not a live coding-harness integration. A model transport
    and isolated PEX process still require their own verified boundaries.
    """
    if not command or any(not isinstance(arg, str) or "\x00" in arg for arg in command):
        raise ValueError("worker command must be a nonempty argument vector")
    return [*_prefix(workspace, writable_worker=True), *command]


def worker_relay_command(workspace: Path, command: list[str], relay_socket: Path) -> list[str]:
    """Expose one controller-owned IPC socket without sharing host networking.

    This is an IPC primitive, not a model relay implementation. The listener
    must separately enforce model-only requests, limits and backend receipts.
    Neither this socket mount nor a successful echo makes a run eligible.
    """
    base = worker_command(workspace, command)
    socket_path = _relay_socket(workspace, relay_socket)
    # Insert before chdir/--, retaining every existing mount/network boundary.
    boundary = base.index("--")
    return [
        *base[:boundary - 2],
        "--ro-bind", str(socket_path), "/model-relay.sock",
        "--setenv", "PEX_MODEL_RELAY_SOCKET", "/model-relay.sock",
        *base[boundary - 2:],
    ]


def _relay_socket(workspace: Path, relay_socket: Path) -> Path:
    socket_path = relay_socket.resolve(strict=True)
    if socket_path != relay_socket.absolute():
        raise ValueError("worker relay socket must be an absolute unlinked path")
    metadata = socket_path.stat(follow_symlinks=False)
    if (
        not stat.S_ISSOCK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
    ):
        raise ValueError("worker relay must be an owner-only, single-link Unix socket")
    if socket_path.is_relative_to(workspace.resolve(strict=True)):
        raise ValueError("worker relay socket must be outside the writable task")
    return socket_path


def supervisor_command(workspace: Path, runtime: Path, control: Path) -> list[str]:
    """Isolate an offline PEX child with a controller-curated public runtime.

    Runtime packaging, payload rebinding and live model transport are separate
    requirements. This primitive never makes a presentation run eligible.
    """
    prefix = _prefix(workspace)
    runtime_root = _audited_directory(runtime, "supervisor runtime")
    control_root = _audited_directory(control, "supervisor control")
    roots = [workspace.resolve(strict=True), runtime_root, control_root]
    for index, root in enumerate(roots):
        for other in roots[index + 1:]:
            if root.is_relative_to(other) or other.is_relative_to(root):
                raise ValueError("supervisor workspace, runtime and control must be disjoint")
    if not (runtime_root / "pex_supervisor_process.py").is_file():
        raise ValueError("supervisor runtime must contain its public process entry")
    if {item.name for item in control_root.iterdir()} != {"request.json"}:
        raise ValueError("supervisor control must contain only a fresh request.json")
    request = control_root / "request.json"
    if not request.is_file() or request.stat().st_size > 512_000:
        raise ValueError("supervisor request must be a bounded regular file")
    return [
        *prefix[:-3],
        "--ro-bind", str(runtime_root), "/runtime",
        "--bind", str(control_root), "/control",
        "--ro-bind", str(request), "/control/request.json",
        "--setenv", "PEX_SUPERVISOR_DISABLE", "1",
        "--setenv", "PEX_HOME", "/tmp/pex",
        *prefix[-3:],
        str(_runtime_python()), "-I", "-B",
        "/runtime/pex_supervisor_process.py", "/control/request.json", "/control/response.json",
    ]


def supervisor_relay_command(
    workspace: Path, runtime: Path, control: Path, relay_socket: Path, model: str,
) -> list[str]:
    """Route isolated PEX inference through a single controller-owned socket.

    The runtime must contain its locked model dependencies. Controller budget
    enforcement and action-time receipts remain necessary for eligible runs.
    """
    if not isinstance(model, str) or not model or len(model) > 256 or "\x00" in model:
        raise ValueError("supervisor relay requires a bounded pinned model")
    socket_path = _relay_socket(workspace, relay_socket)
    if any(socket_path.is_relative_to(root.resolve(strict=True)) for root in (runtime, control)):
        raise ValueError("supervisor relay socket must be outside runtime and control")
    command = supervisor_command(workspace, runtime, control)
    disabled = command.index("PEX_SUPERVISOR_DISABLE")
    command[disabled + 1] = "0"
    boundary = command.index("--")
    return [
        *command[:boundary - 2],
        "--ro-bind", str(socket_path), "/model-relay.sock",
        "--setenv", "PEX_MODEL_RELAY_SOCKET", "/model-relay.sock",
        "--setenv", "PEX_MODEL_RELAY_MODEL", model,
        *command[boundary - 2:],
    ]


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
    from pex_protocol.isolated_pytest import isolated_pytest_argv

    argv = isolated_pytest_argv("/usr/bin/python3", files)
    argv[0] = str(_runtime_python())
    prefix = _prefix(workspace)
    return [
        *prefix[:-3],
        "--setenv", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1",
        *prefix[-3:],
        *argv,
    ]
