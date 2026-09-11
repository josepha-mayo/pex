"""Prove a frozen PEX bridge exposes safe fresh-install supervisor settings.

This smoke is deliberately local and configuration-only: it disables cloud
reasoning and worker attachment, uses a random bearer, and owns the frozen
process in a kill-on-close Windows job.
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
            payload = _read_json(
                f"http://127.0.0.1:{port}/health/identity?challenge={challenge}"
            )
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


def _write_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    binary = args.exe.resolve(strict=True)
    if os.name != "nt" or binary.suffix.lower() != ".exe" or not binary.is_file():
        parser.error("--exe must name an existing Windows executable")

    from pex_protocol.windows_job import CREATE_SUSPENDED, assign_job_and_resume, close_job

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
                    creationflags=subprocess.CREATE_NO_WINDOW | CREATE_SUSPENDED,
                )
                job = assign_job_and_resume(process)
                if job is None:
                    raise RuntimeError("failed to contain the frozen bridge in a Windows job")
                _wait_for_identity(port, token, process)
                settings = _read_json(
                    f"http://127.0.0.1:{port}/v1/supervisor", token=token
                )
                catalog = settings.get("catalog")
                if not isinstance(catalog, list) or not catalog:
                    raise RuntimeError("supervisor catalog is empty or malformed")
                zen_catalog = [
                    row
                    for row in catalog
                    if isinstance(row, dict) and row.get("provider") == "zen"
                ]
                if not zen_catalog:
                    raise RuntimeError("supervisor catalog has no Zen entries")
                first_zen = zen_catalog[0]
                dispatch_cap = settings.get("max_dispatches_per_session")
                if dispatch_cap != 3:
                    raise RuntimeError(
                        f"fresh packaged dispatch cap is {dispatch_cap!r}, not 3"
                    )
                if (first_zen.get("provider"), first_zen.get("model_id")) != (
                    "zen",
                    "muse-spark-1.3-contributor-free",
                ):
                    raise RuntimeError(
                        "first packaged Zen hint is not the expected free Muse model"
                    )
                result = {
                    "schema": "pex.packaged-settings-smoke.v1",
                    "bridge_sha256": _sha256(binary),
                    "identity_verified": True,
                    "authenticated_supervisor_read": True,
                    "max_dispatches_per_session": 3,
                    "first_catalog_provider": "zen",
                    "first_catalog_model": "muse-spark-1.3-contributor-free",
                    "cloud_reasoning": False,
                    "worker_attachment": False,
                    "provider_calls": 0,
                }
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
