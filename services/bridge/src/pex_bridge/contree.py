"""Nebius ConTree (Token Factory Sandboxes) backend for public pytest evidence.

When ``PEX_PUBLIC_PYTEST_BACKEND=contree`` is set, public pytest runs execute
inside a disposable, network-isolated Nebius VM instead of a local subprocess.
Only files already admitted by the public workspace manifest are uploaded, and
each upload is re-verified against the fingerprinted sha256: the sandbox sees
exactly the bytes the observation receipt describes.

Every operational failure (missing credentials, auth rejection, malformed or
incomplete API responses, dispatch deadline) yields an honest result dict with
``error_type`` set and ``ok`` false. Infrastructure errors are never presented
as test outcomes, and an unavailable sandbox never silently downgrades to
local execution of untrusted workspace code.

Live access requires a Nebius API key with Sandboxes (ConTree) beta access and
the project id it is scoped to:

    PEX_PUBLIC_PYTEST_BACKEND=contree
    PEX_CONTREE_API_KEY or NEBIUS_API_KEY
    PEX_CONTREE_PROJECT or NEBIUS_PROJECT_ID

Optional overrides:

    PEX_CONTREE_BASE_URL (default https://api.tokenfactory.nebius.com/sandboxes/v1)
    PEX_CONTREE_IMAGE (default tag:python:3.12-slim; the image must ship pytest)
    PEX_CONTREE_PYTHON (default /usr/local/bin/python3)
    PEX_CONTREE_TIMEOUT_SECONDS (default 90, cap 300)
    PEX_CONTREE_MAX_UPLOAD_BYTES (default 32 MiB, cap 512 MiB)
    PEX_CONTREE_MAX_FILES (default 512, cap 10_000)
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import time
import uuid as uuidlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pex_protocol.isolated_pytest import isolated_pytest_argv
from pex_protocol.redaction import redact_text

from pex_bridge.observe import (
    _MAX_PYTEST_OUTPUT,
    HIDDEN_NAME_MARKERS,
    assert_readable,
)

EXECUTOR = "nebius-contree-public-pytest-v1"
DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/sandboxes/v1"
DEFAULT_IMAGE = "tag:python:3.12-slim"
DEFAULT_PYTHON = "/usr/local/bin/python3"
_WORKSPACE_ROOT = "/workspace"

_DEFAULT_TIMEOUT_SECONDS = 90
_MAX_TIMEOUT_SECONDS = 300
_DEFAULT_MAX_UPLOAD_BYTES = 32 * 1024 * 1024
_ABSOLUTE_MAX_UPLOAD_BYTES = 512 * 1024 * 1024
_DEFAULT_MAX_FILES = 512
_ABSOLUTE_MAX_FILES = 10_000
_POLL_FLOOR_SECONDS = 0.25
_POLL_CEILING_SECONDS = 5.0
_MAX_ERROR_CHARS = 512

_TERMINAL_STATUSES = {"SUCCESS", "FAILED", "CANCELLED"}
_PENDING_STATUSES = {"PENDING", "ASSIGNED", "EXECUTING"}
_MISSING_PYTEST_MARKERS = ("no module named pytest", "can't find '__main__' module")


class ContreeError(RuntimeError):
    """A sandbox operation failed before a truthful test result existed."""

    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type


@dataclass(frozen=True)
class ContreeConfig:
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    project: str = ""
    image: str = DEFAULT_IMAGE
    python: str = DEFAULT_PYTHON
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS
    max_upload_bytes: int = _DEFAULT_MAX_UPLOAD_BYTES
    max_files: int = _DEFAULT_MAX_FILES

    def missing_reasons(self) -> list[str]:
        reasons = []
        if not self.api_key:
            reasons.append("PEX_CONTREE_API_KEY/NEBIUS_API_KEY unset")
        if not self.project:
            reasons.append("PEX_CONTREE_PROJECT/NEBIUS_PROJECT_ID unset")
        return reasons


def contree_config(env: dict[str, str] | None = None) -> ContreeConfig:
    source = os.environ if env is None else env
    return ContreeConfig(
        base_url=(source.get("PEX_CONTREE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
        api_key=(source.get("PEX_CONTREE_API_KEY") or source.get("NEBIUS_API_KEY") or ""),
        project=(source.get("PEX_CONTREE_PROJECT") or source.get("NEBIUS_PROJECT_ID") or ""),
        image=(source.get("PEX_CONTREE_IMAGE") or DEFAULT_IMAGE),
        python=(source.get("PEX_CONTREE_PYTHON") or DEFAULT_PYTHON),
        timeout_seconds=_bounded_int(
            source.get("PEX_CONTREE_TIMEOUT_SECONDS"),
            _DEFAULT_TIMEOUT_SECONDS,
            _MAX_TIMEOUT_SECONDS,
        ),
        max_upload_bytes=_bounded_int(
            source.get("PEX_CONTREE_MAX_UPLOAD_BYTES"),
            _DEFAULT_MAX_UPLOAD_BYTES,
            _ABSOLUTE_MAX_UPLOAD_BYTES,
        ),
        max_files=_bounded_int(
            source.get("PEX_CONTREE_MAX_FILES"), _DEFAULT_MAX_FILES, _ABSOLUTE_MAX_FILES
        ),
    )


def _bounded_int(raw: str | None, default: int, ceiling: int) -> int:
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < 1:
        return default
    return min(value, ceiling)


def public_pytest_backend(env: dict[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    return (source.get("PEX_PUBLIC_PYTEST_BACKEND") or "").strip().lower()


@dataclass(frozen=True)
class TransportResponse:
    status: int
    headers: dict[str, str]
    body: Any


class ContreeTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> TransportResponse: ...


class HttpxContreeTransport:
    """Production transport: sync httpx with fixed bounds and explicit auth."""

    def __init__(self, config: ContreeConfig) -> None:
        import httpx

        base = config.base_url
        if not base.startswith("https://") and not base.startswith("http://localhost"):
            raise ContreeError("unconfigured", "contree base URL must be https")
        self._client = httpx.Client(
            base_url=base,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Project": config.project,
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> TransportResponse:
        try:
            response = self._client.request(
                method,
                path,
                json=json_body,
                content=content,
                headers=headers,
            )
        except Exception as exc:  # httpx.ConnectError, timeouts, TLS, ...
            raise ContreeError("network", f"contree request failed: {type(exc).__name__}") from exc
        body: Any = None
        if response.content:
            try:
                body = response.json()
            except ValueError:
                body = None
        return TransportResponse(
            status=response.status_code,
            headers={key.lower(): value for key, value in response.headers.items()},
            body=body,
        )


@dataclass
class _SandboxClient:
    config: ContreeConfig
    transport: ContreeTransport

    def _checked(self, response: TransportResponse, expect: tuple[int, ...]) -> Any:
        status = response.status
        if status in expect:
            return response.body
        raise ContreeError(
            _status_error_type(status),
            _error_message(response.body, status),
        )

    def file_uuid_for(self, sha256: str, content: bytes) -> str:
        """Return the server file uuid, uploading only when the digest is absent."""

        try:
            found = self.transport.request("GET", f"/files/{sha256}")
        except ContreeError:
            raise
        if found.status == 200:
            body = self._checked(found, (200,))
            file_uuid = _require_uuid(body, "uuid", "file lookup")
            if isinstance(body, dict) and body.get("sha256") != sha256:
                raise ContreeError("malformed", "file lookup returned a mismatched sha256")
            return file_uuid
        if found.status != 404:
            raise ContreeError(
                _status_error_type(found.status), _error_message(found.body, found.status)
            )
        uploaded = self._checked(
            self.transport.request(
                "POST",
                "/files",
                content=content,
                headers={"Content-Type": "application/octet-stream"},
            ),
            (201,),
        )
        file_uuid = _require_uuid(uploaded, "uuid", "file upload")
        if not isinstance(uploaded, dict) or uploaded.get("sha256") != sha256:
            raise ContreeError("malformed", "file upload returned a mismatched sha256")
        return file_uuid

    def spawn(self, payload: dict[str, Any]) -> tuple[str, str]:
        """Spawn an instance; return (instance_uuid, operation_uuid)."""

        response = self.transport.request("POST", "/instances", json_body=payload)
        body = self._checked(response, (201,))
        instance_uuid = _require_uuid(body, "uuid", "instance spawn")
        location = response.headers.get("location", "")
        operation_uuid = location.rstrip("/").rsplit("/", 1)[-1]
        try:
            uuidlib.UUID(operation_uuid)
        except (ValueError, AttributeError):
            raise ContreeError(
                "malformed", "instance spawn response carried no operation Location"
            ) from None
        return instance_uuid, operation_uuid

    def operation(self, operation_uuid: str) -> dict[str, Any]:
        response = self.transport.request("GET", f"/operations/{operation_uuid}")
        body = self._checked(response, (200,))
        if not isinstance(body, dict):
            raise ContreeError("malformed", "operation status was not an object")
        return body

    def cancel(self, operation_uuid: str) -> None:
        try:
            self.transport.request("DELETE", f"/operations/{operation_uuid}")
        except ContreeError:
            pass


def _status_error_type(status: int) -> str:
    if status == 401:
        return "auth"
    if status == 403:
        return "forbidden"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limited"
    if 500 <= status < 600:
        return "server"
    return "http_error"


def _error_message(body: Any, status: int) -> str:
    text = ""
    if isinstance(body, dict):
        error = body.get("error")
        text = error if isinstance(error, str) else str(error or "")
    return (text or f"HTTP {status}")[:_MAX_ERROR_CHARS]


def _require_uuid(body: Any, key: str, context: str) -> str:
    value = body.get(key) if isinstance(body, dict) else None
    if not isinstance(value, str):
        raise ContreeError("malformed", f"{context} response missing {key}")
    try:
        uuidlib.UUID(value)
    except ValueError:
        raise ContreeError("malformed", f"{context} response carried an invalid {key}") from None
    return value


def _decode_stream(stream: Any) -> str:
    if not isinstance(stream, dict):
        return ""
    value = stream.get("value")
    encoding = stream.get("encoding")
    if not isinstance(value, str):
        return ""
    if encoding == "base64":
        try:
            raw = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            raise ContreeError("malformed", "stream payload was not valid base64") from None
    elif encoding == "ascii":
        raw = value.encode("ascii", errors="replace")
    else:
        raise ContreeError("malformed", f"stream payload used unknown encoding {encoding!r}")
    return raw.decode("utf-8", errors="replace")


def _manifest_bytes(root: Path, row: dict[str, Any]) -> bytes:
    """Read one manifested file, refusing bytes that drifted since fingerprinting."""

    relative = row.get("path")
    declared_sha = row.get("sha256")
    declared_size = row.get("size_bytes")
    if (
        not isinstance(relative, str)
        or not relative
        or relative.startswith("/")
        or ".." in relative.split("/")
        or not isinstance(declared_sha, str)
        or len(declared_sha) != 64
        or not isinstance(declared_size, int)
        or declared_size < 0
    ):
        raise ContreeError("workspace_drift", "manifest row is not a trusted file entry")
    target = assert_readable(root, root.joinpath(*relative.split("/")))
    try:
        content = target.read_bytes()
    except OSError as exc:
        raise ContreeError("workspace_drift", f"manifest file unreadable: {relative}") from exc
    if len(content) != declared_size or hashlib.sha256(content).hexdigest() != declared_sha:
        raise ContreeError(
            "workspace_drift",
            f"workspace file changed since the observation receipt: {relative}",
        )
    return content


def _upload_workspace(
    client: _SandboxClient,
    root: Path,
    manifest: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    total = 0
    for row in manifest:
        if len(files) >= client.config.max_files:
            raise ContreeError("workspace_bound", "workspace exceeds the sandbox file upload bound")
        content = _manifest_bytes(root, row)
        total += len(content)
        if total > client.config.max_upload_bytes:
            raise ContreeError("workspace_bound", "workspace exceeds the sandbox upload byte bound")
        file_uuid = client.file_uuid_for(row["sha256"], content)
        files[f"{_WORKSPACE_ROOT}/{row['path']}"] = {"uuid": file_uuid, "mode": "0644"}
    return files


def _check_deadline(deadline: float | None, monotonic: Callable[[], float]) -> None:
    if deadline is not None and monotonic() >= deadline:
        raise ContreeError("timeout", "sandbox dispatch budget expired")


@dataclass
class _SandboxRun:
    exit_code: int | None
    timed_out: bool
    output: str
    error_type: str | None = None
    error: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


def _wait_for_terminal(
    client: _SandboxClient,
    operation_uuid: str,
    *,
    deadline: float | None,
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
) -> dict[str, Any]:
    """Poll until a terminal status; cancel best-effort when our budget expires."""

    while True:
        if deadline is not None and monotonic() >= deadline:
            client.cancel(operation_uuid)
            raise ContreeError("timeout", "sandbox dispatch budget expired")
        response = client.transport.request("GET", f"/operations/{operation_uuid}")
        if response.status != 200:
            raise ContreeError(
                _status_error_type(response.status),
                _error_message(response.body, response.status),
            )
        body = response.body
        if not isinstance(body, dict):
            raise ContreeError("malformed", "operation status was not an object")
        status = body.get("status")
        if status in _TERMINAL_STATUSES:
            return body
        if status not in _PENDING_STATUSES:
            raise ContreeError("malformed", f"unknown operation status {status!r}")
        try:
            retry_after = float(response.headers.get("retry-after") or 1.0)
        except (TypeError, ValueError):
            retry_after = 1.0
        pause = min(max(retry_after, _POLL_FLOOR_SECONDS), _POLL_CEILING_SECONDS)
        if deadline is not None:
            remaining = deadline - monotonic()
            if remaining <= 0:
                client.cancel(operation_uuid)
                raise ContreeError("timeout", "sandbox dispatch budget expired")
            pause = min(pause, remaining)
        sleeper(pause)


def _pytest_output(stdout: str, stderr: str, timed_out: bool, wait_seconds: float) -> str:
    output = (stdout + "\n" + stderr).strip() if stderr else stdout
    output = output[-_MAX_PYTEST_OUTPUT:]
    output, _ = redact_text(output)
    output = output or ""
    if any(marker.lower() in output.lower() for marker in HIDDEN_NAME_MARKERS):
        output = "[public pytest output withheld: hidden benchmark marker detected]"
    if timed_out:
        output = f"[public pytest timed out after {wait_seconds:g}s]\n{output}".strip()
    return output


def run_public_pytest_contree(
    root: Path,
    manifest: list[dict[str, Any]],
    tests: list[str],
    *,
    deadline: float | None = None,
    transport: ContreeTransport | None = None,
    config: ContreeConfig | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute the isolated public-pytest argv inside a disposable Nebius VM.

    The returned dict mirrors the local public-pytest shape plus executor and
    sandbox provenance. Any operational failure returns ``ok: False`` with an
    ``error_type`` and no ``exit_code`` — infra trouble is never test evidence.
    """

    started = monotonic()
    config = config or contree_config()
    argv = isolated_pytest_argv(config.python, tests)
    base = {
        "ok": False,
        "exit_code": None,
        "output": "",
        "timed_out": False,
        "executor": EXECUTOR,
        "argv": argv,
    }

    def fail(error_type: str, message: str, **extra: Any) -> dict[str, Any]:
        return {
            **base,
            "error_type": error_type,
            "error": message[:_MAX_ERROR_CHARS],
            **extra,
        }

    missing = config.missing_reasons()
    if missing:
        return fail("unconfigured", "; ".join(missing))

    try:
        client = _SandboxClient(
            config=config,
            transport=transport if transport is not None else HttpxContreeTransport(config),
        )
        _check_deadline(deadline, monotonic)
        files = _upload_workspace(client, root, manifest)
        _check_deadline(deadline, monotonic)
        remaining = None if deadline is None else max(1.0, deadline - monotonic())
        timeout_seconds = config.timeout_seconds
        if remaining is not None:
            timeout_seconds = max(1, min(timeout_seconds, int(remaining) or 1))
        instance_uuid, operation_uuid = client.spawn(
            {
                "command": argv[0],
                "args": argv[1:],
                "shell": False,
                "image": config.image,
                "cwd": _WORKSPACE_ROOT,
                "env": {
                    "CI": "1",
                    "HOME": "/tmp",
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONPYCACHEPREFIX": "/tmp/pycache",
                },
                "networking": {"enabled": False},
                "disposable": True,
                "timeout": timeout_seconds,
                "truncate_output_at": 65_536,
                "files": files,
            }
        )
        operation = _wait_for_terminal(
            client,
            operation_uuid,
            deadline=deadline,
            monotonic=monotonic,
            sleeper=sleeper,
        )
    except ContreeError as exc:
        return fail(exc.error_type, str(exc), timed_out=exc.error_type == "timeout")

    provenance = {
        "operation_uuid": operation_uuid,
        "instance_uuid": instance_uuid,
        "image": config.image,
        "image_uuid": operation.get("image_uuid"),
        "result_image_uuid": operation.get("result_image_uuid"),
        "duration_seconds": operation.get("duration"),
        "consumed_cpu": operation.get("consumed_cpu"),
        "consumed_memory": operation.get("consumed_memory"),
    }
    status = operation.get("status")
    result = operation.get("result")
    if status != "SUCCESS" or not isinstance(result, dict):
        return fail(
            "operation_failed",
            str(operation.get("error") or f"operation ended as {status}"),
            sandbox=provenance,
        )
    state = result.get("state") if isinstance(result.get("state"), dict) else {}
    try:
        stdout = _decode_stream(result.get("stdout"))
        stderr = _decode_stream(result.get("stderr"))
    except ContreeError as exc:
        return fail(exc.error_type, str(exc), sandbox=provenance)
    exit_code = state.get("exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        return fail(
            "malformed",
            "operation result carried no process exit code",
            sandbox=provenance,
        )
    timed_out = state.get("timed_out") is True
    combined = stdout + ("\n" + stderr if stderr else "")
    if exit_code != 0 and any(marker in combined.lower() for marker in _MISSING_PYTEST_MARKERS):
        return fail(
            "sandbox_image_missing_pytest",
            "sandbox image does not provide pytest; configure PEX_CONTREE_IMAGE",
            exit_code=exit_code,
            sandbox=provenance,
        )
    wait_seconds = monotonic() - started
    return {
        "ok": exit_code == 0 and not timed_out,
        "exit_code": exit_code,
        "output": _pytest_output(
            stdout,
            stderr,
            timed_out,
            timeout_seconds if timed_out else wait_seconds,
        ),
        "timed_out": timed_out,
        "executor": EXECUTOR,
        "argv": argv,
        "sandbox": provenance,
    }
