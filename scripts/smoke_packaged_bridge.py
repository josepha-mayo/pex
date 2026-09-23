"""Prove a packaged PEX bridge exposes safe fresh-install supervisor settings.

This smoke is deliberately local and configuration-only: it disables cloud
reasoning and worker attachment, uses a random bearer, and terminates the owned
process after the check.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _unused_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _environment(home: Path, port: int, token: str) -> dict[str, str]:
    inherited = ("SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "PATH")
    environment = {name: os.environ[name] for name in inherited if name in os.environ}
    profile = home / "windows-profile"
    appdata = profile / "AppData" / "Roaming"
    local_appdata = profile / "AppData" / "Local"
    temporary = home / "temp"
    for directory in (home, profile, appdata, local_appdata, temporary):
        directory.mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "PEX_HOME": str(home),
            "PEX_HOST": "127.0.0.1",
            "PEX_PORT": str(port),
            "PEX_REQUIRE_AUTH": "true",
            "PEX_TOKEN": token,
            "PEX_DESKTOP_PARENT_PID": str(os.getpid()),
            "PEX_CLOUD_REASONING": "false",
            "PEX_CODEX_ATTACH": "false",
            "USERPROFILE": str(profile),
            "APPDATA": str(appdata),
            "LOCALAPPDATA": str(local_appdata),
            "TEMP": str(temporary),
            "TMP": str(temporary),
        }
    )
    return environment


def _read_json(url: str, *, token: str | None = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=1.0) as response:
        body = response.read(1_048_577)
    if len(body) > 1_048_576:
        raise RuntimeError("bridge response exceeded the smoke limit")
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("bridge returned a non-object JSON response")
    return payload


def _wait_for_identity(port: int, token: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"frozen bridge exited early with {process.returncode}")
        challenge = secrets.token_hex(32)
        try:
            payload = _read_json(f"http://127.0.0.1:{port}/health/identity?challenge={challenge}")
        except (OSError, ValueError, urllib.error.URLError):
            time.sleep(0.1)
            continue
        expected = hmac.new(token.encode(), challenge.encode(), hashlib.sha256).hexdigest()
        if payload == {
            "ok": True,
            "service": "pex-bridge",
            "challenge": challenge,
            "proof": expected,
        }:
            return
        time.sleep(0.1)
    raise RuntimeError("frozen bridge did not prove its identity within 60 seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wait_for_closed_port(port: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                pass
        except OSError:
            return
        time.sleep(0.1)
    raise RuntimeError("owned frozen bridge listener survived shutdown")


def _process_sample(process_id: int) -> dict[str, int]:
    """Read bounded Windows resource counters without adding a runtime dependency."""
    import win32api
    import win32con
    import win32process

    handle = win32api.OpenProcess(
        win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
        False,
        process_id,
    )
    try:
        memory = win32process.GetProcessMemoryInfo(handle)
        times = win32process.GetProcessTimes(handle)
    finally:
        handle.Close()
    return {
        "working_set_bytes": int(memory["WorkingSetSize"]),
        "private_bytes": int(memory["PagefileUsage"]),
        "cpu_100ns": int(times["KernelTime"]) + int(times["UserTime"]),
    }


def _soak_bridge(
    *,
    port: int,
    token: str,
    process: subprocess.Popen[bytes],
    seconds: float,
    interval: float,
) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + seconds
    samples: list[dict[str, int]] = []
    identity_checks = 0
    settings_checks = 0
    next_settings_check = started
    while True:
        if process.poll() is not None:
            raise RuntimeError(f"frozen bridge exited during soak with {process.returncode}")
        now = time.monotonic()
        challenge = secrets.token_hex(32)
        identity = _read_json(f"http://127.0.0.1:{port}/health/identity?challenge={challenge}")
        expected = hmac.new(token.encode(), challenge.encode(), hashlib.sha256).hexdigest()
        if identity != {
            "ok": True,
            "service": "pex-bridge",
            "challenge": challenge,
            "proof": expected,
        }:
            raise RuntimeError("frozen bridge lost its authenticated identity during soak")
        identity_checks += 1
        if now >= next_settings_check:
            settings = _read_json(f"http://127.0.0.1:{port}/v1/supervisor", token=token)
            if settings.get("max_dispatches_per_session") != 3:
                raise RuntimeError("supervisor settings changed during soak")
            settings_checks += 1
            next_settings_check = now + 10.0
        samples.append(_process_sample(process.pid))
        if now >= deadline:
            break
        time.sleep(min(interval, max(0.0, deadline - now)))

    first = samples[0]
    last = samples[-1]
    return {
        "requested_seconds": seconds,
        "observed_seconds": round(time.monotonic() - started, 3),
        "sample_interval_seconds": interval,
        "samples": len(samples),
        "identity_checks": identity_checks,
        "settings_checks": settings_checks,
        "peak_working_set_bytes": max(row["working_set_bytes"] for row in samples),
        "peak_private_bytes": max(row["private_bytes"] for row in samples),
        "working_set_delta_bytes": last["working_set_bytes"] - first["working_set_bytes"],
        "private_delta_bytes": last["private_bytes"] - first["private_bytes"],
        "cpu_seconds": round((last["cpu_100ns"] - first["cpu_100ns"]) / 10_000_000, 6),
    }


def _write_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--soak-seconds", type=float, default=0.0)
    parser.add_argument("--sample-interval", type=float, default=1.0)
    args = parser.parse_args()
    if not 0.0 <= args.soak_seconds <= 3600.0:
        parser.error("--soak-seconds must be between 0 and 3600")
    if not 0.2 <= args.sample_interval <= 60.0:
        parser.error("--sample-interval must be between 0.2 and 60")
    binary = args.exe.resolve(strict=True)
    expected_name = "pex-bridge.exe" if os.name == "nt" else "pex-bridge"
    if binary.name != expected_name or not binary.is_file():
        parser.error(f"--exe must name an existing packaged {expected_name} executable")
    internal = binary.parent / "_internal"
    runtime_libraries = (
        [internal / "python312.dll"]
        if os.name == "nt"
        else [*internal.glob("libpython*.so*"), *internal.glob("libpython*.dylib")]
    )
    if not any(path.is_file() for path in runtime_libraries):
        parser.error("--exe must name a packaged one-directory bridge with its Python runtime")

    if os.name == "nt":
        from pex_protocol.windows_job import CREATE_SUSPENDED, assign_job_and_resume, close_job
    else:
        CREATE_SUSPENDED = 0

        def assign_job_and_resume(_process: subprocess.Popen[bytes]) -> None:
            return None

        def close_job(_job: None) -> None:
            return None

    port = _unused_loopback_port()
    token = secrets.token_hex(48)
    process: subprocess.Popen[bytes] | None = None
    job = None
    with tempfile.TemporaryDirectory(prefix="pex-packaged-settings-smoke-") as raw_home:
        home = Path(raw_home)
        log_path = home / "bridge.log"
        with log_path.open("wb") as log:
            try:
                process = subprocess.Popen(
                    [str(binary), "--host", "127.0.0.1", "--port", str(port)],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=_environment(home, port, token),
                    cwd=home,
                    creationflags=(subprocess.CREATE_NO_WINDOW | CREATE_SUSPENDED)
                    if os.name == "nt"
                    else 0,
                )
                job = assign_job_and_resume(process)
                if os.name == "nt" and job is None:
                    raise RuntimeError("failed to contain the frozen bridge in a Windows job")
                _wait_for_identity(port, token, process)
                settings = _read_json(f"http://127.0.0.1:{port}/v1/supervisor", token=token)
                catalog = settings.get("catalog")
                if not isinstance(catalog, list) or not catalog:
                    raise RuntimeError("supervisor catalog is empty or malformed")
                zen_catalog = [
                    row for row in catalog if isinstance(row, dict) and row.get("provider") == "zen"
                ]
                if not zen_catalog:
                    raise RuntimeError("supervisor catalog has no Zen entries")
                first_zen = zen_catalog[0]
                dispatch_cap = settings.get("max_dispatches_per_session")
                if dispatch_cap != 3:
                    raise RuntimeError(f"fresh packaged dispatch cap is {dispatch_cap!r}, not 3")
                if not isinstance(first_zen.get("model_id"), str) or not first_zen["model_id"]:
                    raise RuntimeError("first packaged Zen hint has no model ID")
                if any(
                    isinstance(row.get("model_id"), str)
                    and row["model_id"].casefold().endswith("-free")
                    for row in zen_catalog
                ):
                    raise RuntimeError("packaged Zen catalog suggests an OpenCode-only free model")
                result = {
                    "schema": "pex.packaged-settings-smoke.v1",
                    "bridge_sha256": _sha256(binary),
                    "identity_verified": True,
                    "authenticated_supervisor_read": True,
                    "max_dispatches_per_session": 3,
                    "first_catalog_provider": "zen",
                    "first_catalog_model": first_zen["model_id"],
                    "cloud_reasoning": False,
                    "worker_attachment": False,
                    "provider_calls": 0,
                }
                if args.soak_seconds:
                    result["soak"] = _soak_bridge(
                        port=port,
                        token=token,
                        process=process,
                        seconds=args.soak_seconds,
                        interval=args.sample_interval,
                    )
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                close_job(job)
        _wait_for_closed_port(port)
        if token.encode() in log_path.read_bytes():
            raise RuntimeError("bridge log exposed the random bearer")
    if args.output is not None:
        _write_result(args.output.resolve(), result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
