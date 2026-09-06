"""Opt-in Windows regression for PyInstaller bootloader/payload lifetime."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


def _frozen_bridge() -> Path:
    if os.name != "nt":
        pytest.skip("frozen bridge lifetime regression is Windows-only")
    raw = os.environ.get("PEX_FROZEN_BRIDGE_EXE", "").strip()
    if not raw:
        pytest.skip("set PEX_FROZEN_BRIDGE_EXE to opt into the frozen bridge regression")
    try:
        binary = Path(raw).resolve(strict=True)
    except OSError as exc:
        pytest.fail("PEX_FROZEN_BRIDGE_EXE is not an existing executable", pytrace=False)
        raise AssertionError from exc  # pragma: no cover
    if not binary.is_file() or binary.suffix.lower() != ".exe":
        pytest.fail("PEX_FROZEN_BRIDGE_EXE must name one existing .exe file", pytrace=False)
    return binary


def _unused_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _sanitized_environment(home: Path, port: int, token: str) -> dict[str, str]:
    inherited = ("SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "PATH")
    kept = {name: os.environ[name] for name in inherited if name in os.environ}
    profile = home / "windows-profile"
    appdata = profile / "AppData" / "Roaming"
    local_appdata = profile / "AppData" / "Local"
    temporary = home / "temp"
    for directory in (home, profile, appdata, local_appdata, temporary):
        directory.mkdir(parents=True, exist_ok=True)
    kept.update(
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
    return kept


def _identity_ready(
    port: int, token: str, timeout: float, process: subprocess.Popen[bytes]
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        challenge = secrets.token_hex(32)
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health/identity?challenge={challenge}", timeout=0.5
            ) as response:
                body = response.read(8_193)
                if len(body) > 8_192:
                    return False
                payload = json.loads(body.decode("utf-8"))
        except (OSError, ValueError, urllib.error.URLError):
            time.sleep(0.1)
            continue
        expected = hmac.new(token.encode(), challenge.encode(), hashlib.sha256).hexdigest()
        expected_payload = {
            "ok": True,
            "service": "pex-bridge",
            "challenge": challenge,
            "proof": expected,
        }
        if payload == expected_payload:
            return True
        time.sleep(0.1)
    return False


def _active_processes(job) -> int:
    import win32job

    info = win32job.QueryInformationJobObject(job, win32job.JobObjectBasicAccountingInformation)
    return int(info["ActiveProcesses"])


def _port_closed(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                pass
        except OSError:
            return True
        time.sleep(0.1)
    return False


@pytest.mark.parametrize("case", [1, 2])
def test_frozen_bootloader_death_reaps_payload_without_job_close(tmp_path: Path, case: int) -> None:
    """Keep the job open: zero active processes proves bootloader death reaps payload."""

    binary = _frozen_bridge()
    from pex_protocol.windows_job import CREATE_SUSPENDED, assign_job_and_resume, close_job

    port = _unused_loopback_port()
    token = secrets.token_hex(48)
    home = tmp_path / f"bridge-home-{case}"
    log_path = tmp_path / f"frozen-bridge-{case}.log"
    process: subprocess.Popen[bytes] | None = None
    job = None
    log = log_path.open("wb")
    try:
        process = subprocess.Popen(
            [str(binary), "--host", "127.0.0.1", "--port", str(port)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=_sanitized_environment(home, port, token),
            cwd=tmp_path,
            creationflags=subprocess.CREATE_NO_WINDOW | CREATE_SUSPENDED,
        )
        job = assign_job_and_resume(process)
        assert job is not None
        assert _identity_ready(port, token, timeout=60, process=process), (
            "owned frozen bridge never proved identity"
        )
        assert _active_processes(job) >= 2, (
            "expected PyInstaller bootloader plus payload in owned job"
        )
        process.terminate()
        process.wait(timeout=5)
        log.flush()
        assert token.encode("utf-8") not in log_path.read_bytes(), (
            "owned bridge log contains an operator credential"
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and _active_processes(job) != 0:
            time.sleep(0.1)
        assert _active_processes(job) == 0, (
            "payload survived bootloader death while job remained open"
        )
        assert _port_closed(port, timeout=5), "payload listener survived bootloader death"
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        log.close()
        close_job(job)


def test_frozen_bridge_verify_bundle_is_standalone(tmp_path: Path) -> None:
    binary = _frozen_bridge()
    from pex_protocol.windows_job import CREATE_SUSPENDED, assign_job_and_resume, close_job

    environment = _sanitized_environment(
        tmp_path / "bundle-home", _unused_loopback_port(), secrets.token_hex(48)
    )
    environment.pop("PEX_DESKTOP_PARENT_PID")
    environment.pop("PEX_TOKEN")
    process: subprocess.Popen[bytes] | None = None
    job = None
    try:
        process = subprocess.Popen(
            [str(binary), "--verify-bundle"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=environment,
            cwd=tmp_path,
            creationflags=subprocess.CREATE_NO_WINDOW | CREATE_SUSPENDED,
        )
        job = assign_job_and_resume(process)
        assert job is not None
        output, _ = process.communicate(timeout=60)
        assert process.returncode == 0
    finally:
        if process is not None and process.poll() is None:
            close_job(job)
            job = None
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        close_job(job)
        if process is not None and process.stdout is not None:
            process.stdout.close()
    payload = json.loads(output.decode("utf-8"))
    assert payload.get("version") == 1
    assert tuple(item.get("id") for item in payload.get("pets", [])) == (
        "pex",
        "ledger",
        "mesh",
        "nudge",
        "drift",
        "quiet",
        "ember",
        "von",
    )
