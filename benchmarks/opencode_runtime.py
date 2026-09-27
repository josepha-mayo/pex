"""Curate and measure the public runtime before OpenCode attempt admission."""

import hashlib
import json
import re
import shutil
from pathlib import Path

from benchmarks import boundary, linux_sandbox
from benchmarks.opencode_worker import worker_settings

PUBLIC_MODULES = (
    "async_budget.py", "opencode_cli.py", "opencode_session.py", "opencode_worker.py",
    "opencode_review_client.py", "worker_model_proxy.py",
)
ROOT = Path(__file__).resolve().parent


def build_runtime(destination: Path, *, binary: Path, expected_binary_sha256: str) -> Path:
    """Copy a pinned binary and only public worker modules into a fresh runtime."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_binary_sha256):
        raise ValueError("a pinned OpenCode binary digest is required")
    source = binary.absolute()
    if source.resolve(strict=True) != source or not source.is_file():
        raise ValueError("OpenCode binary must be an unlinked regular file")
    if boundary.sha256_file(source, max_bytes=256 * 1024 * 1024) != expected_binary_sha256:
        raise ValueError("OpenCode binary differs from its pinned digest")
    destination = destination.absolute()
    if destination.parent.resolve(strict=True) != destination.parent:
        raise ValueError("runtime parent cannot contain links")
    destination.mkdir(mode=0o700, exist_ok=False)
    package = destination / "benchmarks"
    package.mkdir(mode=0o700)
    (package / "__init__.py").write_bytes(b"")
    shutil.copyfile(source, destination / "opencode")
    (destination / "opencode").chmod(0o555)
    if boundary.sha256_file(destination / "opencode") != expected_binary_sha256:
        raise ValueError("OpenCode binary changed while copying; retain the failed runtime")
    for name in PUBLIC_MODULES:
        (package / name).write_bytes((ROOT / name).read_bytes())
    return destination


def measure_profile(runtime: Path, *, model: str) -> dict[str, str]:
    """Measure exact binary/modules and normalized common worker configuration.

    The ephemeral loopback port is normalized to 1; the controller separately
    owns and verifies the mounted relay socket. All other settings are pinned.
    """
    runtime = linux_sandbox._audited_directory(runtime, "public OpenCode runtime")
    expected = {"opencode", "benchmarks/__init__.py"} | {
        "benchmarks/" + name for name in PUBLIC_MODULES
    }
    observed = {item.relative_to(runtime).as_posix()
                for item in runtime.rglob("*") if item.is_file()}
    if observed != expected or (runtime / "benchmarks/__init__.py").read_bytes() != b"":
        raise ValueError("runtime contains unexpected or missing public files")
    hashes = {}
    for name in sorted(expected):
        hashes[name] = boundary.sha256_file(
            runtime / name, max_bytes=256 * 1024 * 1024 if name == "opencode" else 1024 * 1024,
        )
    for name in PUBLIC_MODULES:
        if hashes["benchmarks/" + name] != boundary.sha256_file(ROOT / name):
            raise ValueError("public runtime module differs from current controller sources")
    encoded = json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    settings = json.dumps(worker_settings(model, 1), sort_keys=True, separators=(",", ":")).encode()
    return {"model": model, "runtime_sha256": hashlib.sha256(encoded).hexdigest(),
            "settings_sha256": hashlib.sha256(settings).hexdigest()}
