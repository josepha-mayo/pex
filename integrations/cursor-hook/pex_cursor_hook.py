from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

BRIDGE = os.environ.get("PEX_BRIDGE_URL", "http://127.0.0.1:7420")

# These client deadlines intentionally exceed the bridge's matching pipeline
# deadlines.  Cursor must not give up before the bridge can return a policy
# verdict or an evidenced same-thread stop follow-up.
PERMISSION_CLIENT_TIMEOUT_SECONDS = 7.0
SUBMIT_CLIENT_TIMEOUT_SECONDS = 6.0
STOP_CLIENT_TIMEOUT_SECONDS = 42.0
PASSIVE_CLIENT_TIMEOUT_SECONDS = 0.4
MAX_PAYLOAD_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 65_536
MAX_TOKEN_CHARS = 512
MAX_UI_MESSAGE_CHARS = 4_096
MAX_DROP_TEXT_CHARS = 65_536
# A hook invocation handles one stop. Keep its receipt in memory so an incoming
# payload or an edited drop file cannot supply the parent of a delivery receipt.
_pending_stop_receipt: dict | None = None

# Permission-bearing actions stay behind the bridge policy boundary.
# Ordinary editor reads/writes must never freeze the agent: credential-shaped
# paths stay held, everything else fail-opens. Cursor cannot `ask` on
# beforeReadFile/preToolUse, so those hooks must not wait on the bridge for
# routine work.
_PRE_PERMISSION = {
    "preToolUse",
    "beforeShellExecution",
    "beforeMCPExecution",
    "beforeReadFile",
}
_DENY_ONLY_PERMISSION = {"preToolUse", "beforeReadFile"}
_DANGEROUS = (
    re.compile(r"\brm\s+(?:-[a-z]*r[a-z]*f|--recursive)\b", re.I),
    re.compile(r"\bremove-item\b.*(?:-recurse|-force)", re.I),
    re.compile(r"\b(?:del|erase|rmdir|rd)\b.*(?:/s|/q)", re.I),
    re.compile(r"\bgit\s+push\b.*(?:--force|-f)\b", re.I),
    re.compile(r"\bgit\s+reset\s+--hard\b", re.I),
    re.compile(r"\bgit\s+clean\b.*\s-[a-z]*f", re.I),
    re.compile(r"\bdrop\s+table\b", re.I),
    re.compile(r"\bkubectl\s+delete\b", re.I),
    re.compile(r"\bterraform\s+destroy\b", re.I),
    re.compile(r"\baws\b.*\bdelete\b", re.I),
    re.compile(r"\bchmod\s+777\b", re.I),
    re.compile(r"\b(?:npm|pnpm|yarn)\s+publish\b", re.I),
    re.compile(r"\b(?:vercel|netlify|wrangler)\b.*\b(?:--prod|deploy|publish)\b", re.I),
    re.compile(r"\bcurl\b.*\|\s*(?:ba)?sh\b", re.I),
)
_SENSITIVE = re.compile(
    r"(?:^|[\s\"'=:\\/])(?:"
    r"\.env(?:\.|\b)|\.npmrc\b|\.pypirc\b|\.netrc\b|\.git-credentials\b|"
    r"\.ssh(?:[\\/]|\b)|id_(?:rsa|dsa|ecdsa|ed25519)(?:\.|\b)|"
    r"auth\.json\b|bridge\.token\b|credentials(?:\.|\b)|secrets?(?:\.|\b)|"
    r"private[_-]?key|[^\s\\/]+\.(?:pem|p12|pfx)\b)",
    re.I,
)
_SHELL_CONTROL = re.compile(r"(?:\r|\n|&&|\|\||[;|&<>]|`|\$\()")
_DROP_SECRETS = (
    re.compile(
        r"(?i)\b(?:[a-z][a-z0-9]*[_-])*(?:api[_-]?key|authorization|credential|"
        r"password|private[_-]?key|client[_-]?secret|secret|session[_-]?token|"
        r"access[_-]?token|refresh[_-]?token|token)\b\s*[:=]\s*"
        r"(?:['\"][^'\"\r\n]{8,}['\"]|[^\s,;}\]\r\n]{8,})"
    ),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(
        r"-----BEGIN (?P<label>(?:RSA |EC |OPENSSH )?PRIVATE KEY)-----.*?"
        r"-----END (?P=label)-----",
        re.DOTALL,
    ),
    re.compile(r"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"\b(?:sk-(?:proj-|ant-[A-Za-z0-9]+-)?|gsk_|xai-)[A-Za-z0-9_-]{16,}\b"),
    re.compile(
        r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://"
        r"[^\s/@:]+:[^\s/@]+@"
    ),
)


def _strict_json_loads(value: str | bytes) -> object:
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result

    def finite(raw: str) -> float:
        parsed = float(raw)
        if not math.isfinite(parsed):
            raise ValueError("non-finite JSON number")
        return parsed

    return json.loads(
        value,
        object_pairs_hook=unique,
        parse_constant=lambda _raw: (_ for _ in ()).throw(ValueError("non-finite JSON")),
        parse_float=finite,
    )


def _redact_drop_text(value: object) -> str:
    cleaned = str(value)[:MAX_DROP_TEXT_CHARS]
    for pattern in _DROP_SECRETS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    return cleaned


def _valid_token(value: str) -> str:
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned) > MAX_TOKEN_CHARS
        or any(ord(char) < 0x21 or ord(char) > 0x7E for char in cleaned)
    ):
        return ""
    return cleaned


def _token() -> str:
    return _valid_token(
        os.environ.get("PEX_CURSOR_HOOK_TOKEN")
        or os.environ.get("PEX_HOOK_TOKEN")
        or ""
    )


def _endpoint() -> str | None:
    try:
        parsed = urllib.parse.urlparse(BRIDGE)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "http"
        or hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        return None
    normalized_host = "127.0.0.1" if hostname == "localhost" else hostname
    authority = f"[{normalized_host}]" if normalized_host == "::1" else normalized_host
    if port is not None:
        authority += f":{port}"
    return f"http://{authority}/v1/hooks/cursor"


def cursor_stop_drop_dir() -> Path:
    override = os.environ.get("PEX_CURSOR_STOP_DROP")
    if override:
        return Path(override)
    return Path(os.environ.get("PEX_HOME", Path.home() / ".pex")) / "pexbench" / "stops"


def _payload_cwd(payload: dict) -> Path | None:
    value = payload.get("cwd") or payload.get("workspace")
    roots = payload.get("workspace_roots")
    if not value and isinstance(roots, list) and roots:
        value = roots[0]
    if not value:
        return None
    try:
        return Path(str(value)).expanduser().resolve()
    except (OSError, ValueError):
        return None


def _cwd_in_isolated_workspace_tree(payload: dict) -> bool:
    cwd = _payload_cwd(payload)
    if cwd is None:
        return False
    base = Path(
        os.environ.get(
            "PEX_BENCH_WORKSPACE_ROOT",
            Path(os.environ.get("PEX_HOME", Path.home() / ".pex")) / "pexbench" / "workspaces",
        )
    ).expanduser()
    try:
        return cwd.is_relative_to(base.resolve())
    except (OSError, ValueError):
        return False


def _isolated_control_search_dirs() -> list[Path]:
    dirs: list[Path] = []
    override = os.environ.get("PEX_CURSOR_ISOLATED_CONTROL")
    if override:
        dirs.append(Path(override))
    dirs.append(
        Path(__file__).resolve().parents[2] / "benchmarks" / "results" / "_scratch" / "_control"
    )
    dirs.append(
        Path(os.environ.get("PEX_HOME", Path.home() / ".pex")) / "pexbench" / "control"
    )
    return dirs


def _load_isolated_control(payload: dict) -> dict | None:
    cwd = _payload_cwd(payload)
    if cwd is None:
        return None
    name = cwd.name
    if not name or len(name) > 256:
        return None
    expected_script = (
        Path(__file__).resolve().parents[2] / "benchmarks" / "cursor_isolated_stop.py"
    )
    try:
        expected_script = expected_script.resolve()
    except (OSError, ValueError):
        return None
    for directory in _isolated_control_search_dirs():
        path = directory / f"{name}.json"
        try:
            if not path.is_file():
                continue
            raw = path.read_bytes()
        except OSError:
            continue
        if len(raw) > MAX_PAYLOAD_BYTES:
            continue
        try:
            control = _strict_json_loads(raw.decode("utf-8"))
        except (ValueError, RecursionError, UnicodeError):
            continue
        if not isinstance(control, dict):
            continue
        try:
            listed = Path(str(control.get("workspace") or "")).expanduser().resolve()
        except (OSError, ValueError):
            continue
        if listed != cwd:
            continue
        arm = str(control.get("arm") or "")
        isolated = control.get("isolated_supervisor") is True
        if arm == "cursor" and isolated:
            continue
        if arm == "cursor_pex" and not isolated:
            continue
        if arm not in {"cursor", "cursor_pex"}:
            continue
        if not isolated:
            return control
        try:
            python = Path(str(control.get("python") or "")).expanduser().resolve()
            script = Path(str(control.get("script") or "")).expanduser().resolve()
            control_dir = Path(str(control.get("control_dir") or "")).expanduser().resolve()
            timeout = float(control.get("decision_timeout") or 0)
        except (OSError, TypeError, ValueError):
            continue
        if (
            not python.is_file()
            or not script.is_file()
            or script != expected_script
            or not control_dir.is_dir()
            or not math.isfinite(timeout)
            or not 0 < timeout <= 180
        ):
            continue
        control["python"] = str(python)
        control["script"] = str(script)
        control["control_dir"] = str(control_dir)
        control["workspace"] = str(listed)
        control["_control_path"] = str(path.resolve())
        return control
    return None


def _run_isolated_supervisor(control: dict, payload: dict) -> str:
    timeout = min(float(control["decision_timeout"]), STOP_CLIENT_TIMEOUT_SECONDS)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > MAX_PAYLOAD_BYTES:
        return "{}"
    try:
        control_path = str(Path(control.get("_control_path") or ""))
        completed = subprocess.run(
            [control["python"], "-I", control["script"], control_path],
            input=encoded,
            capture_output=True,
            timeout=timeout,
            check=False,
            cwd=str(Path(control["workspace"])),
            env={
                key: value
                for key, value in os.environ.items()
                if not any(
                    marker in key.upper()
                    for marker in (
                        "EVALUATOR",
                        "PEX_BENCH",
                        "PYTEST_CURRENT_TEST",
                        "STRESSOR",
                        "TASK_ID",
                        "PYTHONPATH",
                        "PYTHONHOME",
                    )
                )
            },
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return "{}"
    if completed.returncode != 0:
        return "{}"
    try:
        return _safe_hook_stdout(completed.stdout.decode("utf-8"), "stop", payload)
    except (UnicodeError, ValueError):
        return "{}"


def _is_benchmark_workspace(payload: dict) -> bool:
    # An explicit drop directory is an operator opt-in. Otherwise only the
    # opaque isolated benchmark workspace tree may produce drop files.
    if os.environ.get("PEX_CURSOR_STOP_DROP"):
        return True
    return _cwd_in_isolated_workspace_tree(payload)


def _sanitized_stop_drop(payload: dict) -> dict:
    allowed = (
        "hook_event_name",
        "conversation_id",
        "session_id",
        "composer_id",
        "cwd",
        "workspace",
        "workspace_roots",
        "completion",
        "text",
        "message",
        "last_assistant_message",
        "model",
        "model_id",
        "cursor_version",
    )
    result: dict[str, object] = {}
    for key in allowed:
        if key not in payload:
            continue
        value = payload[key]
        if key in {
            "completion",
            "text",
            "message",
            "last_assistant_message",
        }:
            result[key] = _redact_drop_text(value)
        elif key == "workspace_roots":
            result[key] = (
                [str(item)[:4_096] for item in value[:64]] if isinstance(value, list) else []
            )
        elif isinstance(value, str):
            result[key] = value[:4_096]
        else:
            result[key] = value
    return result


def _write_stop_drop(payload: dict, *, metadata: dict | None = None) -> dict | None:
    dest = cursor_stop_drop_dir()
    dest.mkdir(parents=True, exist_ok=True)
    # Never use a vendor-supplied stop_id as a filesystem path or trust its clock.
    body = {
        **_sanitized_stop_drop(payload),
        **(metadata or {}),
        "stop_id": uuid.uuid4().hex,
        "receipt_schema": "pex.cursor-hook-receipt.v1",
        "captured_at_ns": time.time_ns(),
        # Python 3.11 on Windows uses coarse GetTickCount64 for monotonic().
        # perf_counter is host-wide and monotonic, with sub-millisecond resolution.
        "captured_monotonic_ns": time.perf_counter_ns(),
    }
    # Canonical UTF-8 JSON, excluding this hash field. This is content integrity,
    # not authentication: the shared local filesystem is not an OS sandbox.
    canonical = json.dumps(
        body, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    body["receipt_sha256"] = hashlib.sha256(canonical).hexdigest()
    encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_PAYLOAD_BYTES:
        return None
    path = dest / f"{body['stop_id']}.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return body


def record_stop_drop(payload: dict) -> str | None:
    global _pending_stop_receipt
    _pending_stop_receipt = None
    hook_name = str(payload.get("hook_event_name") or "")
    if hook_name not in {"stop", "Stop"} or not _is_benchmark_workspace(payload):
        return None
    try:
        _pending_stop_receipt = _write_stop_drop(payload, metadata={"kind": "stop"})
        return _pending_stop_receipt["stop_id"] if _pending_stop_receipt else None
    except Exception:
        return None


def record_stop_delivery(payload: dict, stdout: str, initial_stop_id: str | None) -> str | None:
    """Record flushed hook stdout, not a Cursor acceptance acknowledgment."""

    global _pending_stop_receipt
    initial = _pending_stop_receipt
    if (
        not initial_stop_id
        or not _is_benchmark_workspace(payload)
        or initial is None
        or initial["stop_id"] != initial_stop_id
        or _sanitized_stop_drop(payload) != _sanitized_stop_drop(initial)
    ):
        return None
    try:
        body = _strict_json_loads((stdout or "").strip() or "{}")
    except (ValueError, RecursionError):
        return None
    if not isinstance(body, dict):
        return None
    followup = body.get("followup_message")
    if (
        not isinstance(followup, str)
        or not followup.strip()
        or len(followup) > MAX_UI_MESSAGE_CHARS
        or followup.lstrip().startswith("PEX:")
    ):
        return None
    _pending_stop_receipt = None
    try:
        redacted_followup = _redact_drop_text(followup)
        receipt = _write_stop_drop(
            payload,
            metadata={
                "kind": "followup_delivery",
                "initial_stop_id": initial_stop_id,
                "initial_receipt_sha256": initial["receipt_sha256"],
                "delivery_evidence": "hook_stdout_flushed",
                "pex_followup_message": redacted_followup,
                "followup_redacted": redacted_followup != followup,
                "followup_sha256": hashlib.sha256(followup.encode("utf-8")).hexdigest(),
            },
        )
        return receipt["stop_id"] if receipt else None
    except Exception:
        return None


def parse_payload(raw: str, argv: list[str] | None = None) -> dict:
    fallback = (argv or [""])[1] if argv and len(argv) > 1 else "unknown"
    text = (raw or "").strip().lstrip("\ufeff")
    data: dict | None = None
    if text:
        try:
            parsed = _strict_json_loads(text)
            if isinstance(parsed, dict):
                data = parsed
        except (ValueError, RecursionError):
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = _strict_json_loads(text[start : end + 1])
                    if isinstance(parsed, dict):
                        data = parsed
                except (ValueError, RecursionError):
                    data = None
    if data is None:
        data = {"stdin_preview": text[:2000]} if text else {"stdin_empty": True}
    data["hook_event_name"] = (
        data.get("hook_event_name")
        or data.get("hook")
        or data.get("event")
        or fallback
        or "unknown"
    )
    return data


def _command_blob(payload: dict) -> str:
    parts: list[str] = []
    for key in ("command", "cmd", "script"):
        value = payload.get(key)
        if value:
            parts.append(str(value))
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("command", "cmd", "script"):
            value = tool_input.get(key)
            if value:
                parts.append(str(value))
    return " ".join(parts).lower()


def _is_destructive(payload: dict) -> bool:
    blob = _command_blob(payload)
    return any(pattern.search(blob) for pattern in _DANGEROUS)


def _has_sensitive_path(payload: dict) -> bool:
    values: list[str] = []
    for key in ("path", "file_path", "command", "cmd", "script"):
        value = payload.get(key)
        if value:
            values.append(str(value))
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("path", "file_path", "command", "cmd", "script"):
            value = tool_input.get(key)
            if value:
                values.append(str(value))
    raw_paths = payload.get("file_paths") or []
    if isinstance(raw_paths, list):
        values.extend(str(value) for value in raw_paths[:256] if value)
    return any(_SENSITIVE.search(value.replace("\\", "/")) for value in values)


def _tool_name(payload: dict) -> str:
    for key in ("tool_name", "tool", "toolName"):
        value = payload.get(key)
        if value:
            return str(value)
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        value = tool_input.get("tool_name") or tool_input.get("tool")
        if value:
            return str(value)
    return ""


def _is_routine_safe(hook_name: str, payload: dict) -> bool:
    """True when the worker must keep moving if the bridge is down.

    Destructive commands, deletes, and credential-shaped paths stay fail-closed.
    Ordinary reads, writes, MCP, and non-destructive shell fail open.
    """
    if _is_destructive(payload) or _has_sensitive_path(payload):
        return False
    blob = _command_blob(payload)
    if blob and (_SHELL_CONTROL.search(blob) or _is_destructive({"command": blob})):
        return False
    if hook_name == "beforeReadFile":
        return True
    if hook_name == "beforeShellExecution":
        return bool(blob)
    if hook_name == "preToolUse":
        return "delete" not in _tool_name(payload).casefold()
    if hook_name == "beforeMCPExecution":
        return True
    return False


def _safe_hook_stdout(raw_body: str, hook_name: str, payload: dict | None = None) -> str:
    """Pass through bridge policy. Never freeze routine editor work."""
    try:
        body = _strict_json_loads((raw_body or "").strip() or "{}")
    except (ValueError, RecursionError):
        return "{}"
    if not isinstance(body, dict):
        return "{}"
    if hook_name in _PRE_PERMISSION:
        perm = body.get("permission")
        if perm not in {"allow", "deny", "ask"}:
            perm = "allow" if payload and _is_routine_safe(hook_name, payload) else "ask"
        if perm == "ask" and payload and _is_routine_safe(hook_name, payload):
            perm = "allow"
        if perm == "ask" and hook_name in _DENY_ONLY_PERMISSION:
            return json.dumps(
                {
                    "permission": "deny",
                    "user_message": (
                        "PEX held this action because this Cursor hook does not support an "
                        "enforced ask response. Review it explicitly before retrying."
                    ),
                    "agent_message": "PEX policy requires explicit human review for this action.",
                }
            )
        return json.dumps({"permission": perm})
    if hook_name == "beforeSubmitPrompt":
        cont = body.get("continue") is not False
        out: dict[str, object] = {"continue": cont}
        question = str(body.get("user_message") or "").strip()[:MAX_UI_MESSAGE_CHARS]
        if question:
            out["user_message"] = question
        return json.dumps(out)
    if hook_name in {"stop", "Stop"}:
        text = str(body.get("followup_message") or "").strip()[:MAX_UI_MESSAGE_CHARS]
        if text and not text.startswith("PEX:"):
            return json.dumps({"followup_message": text})
    return "{}"


_PRE_HOOKS = {
    "preToolUse",
    "beforeShellExecution",
    "beforeMCPExecution",
    "beforeReadFile",
    "beforeSubmitPrompt",
}


def _pass_through(hook_name: str, payload: dict) -> str:
    if hook_name in _PRE_PERMISSION:
        if _is_routine_safe(hook_name, payload):
            return json.dumps({"permission": "allow"})
        if hook_name in _DENY_ONLY_PERMISSION:
            return json.dumps(
                {
                    "permission": "deny",
                    "user_message": "PEX is unavailable, so this non-routine action was held.",
                    "agent_message": "PEX could not verify local policy; ask the user to retry.",
                }
            )
        return json.dumps({"permission": "ask"})
    if hook_name == "beforeSubmitPrompt":
        return json.dumps({"continue": True})
    return "{}"


def _fail_open(hook_name: str, payload: dict | None = None) -> str:
    """Bridge unreachable. Never freeze routine editor work."""
    return _pass_through(hook_name, payload or {})


def _post(req: urllib.request.Request, timeout: float) -> str:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("bridge response exceeded limit")
    return raw.decode("utf-8")


def _request(payload: dict) -> urllib.request.Request | None:
    endpoint = _endpoint()
    if endpoint is None:
        return None
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        return None
    if len(encoded) > MAX_PAYLOAD_BYTES:
        return None
    token = _token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(endpoint, data=encoded, headers=headers, method="POST")


def main() -> None:
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raw = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES + 1)
    if len(raw) > MAX_PAYLOAD_BYTES:
        payload = parse_payload("", sys.argv)
    else:
        payload = parse_payload(raw.decode("utf-8", "replace"), sys.argv)
    hook_name = str(payload.get("hook_event_name") or "")
    inbound_stop_id = record_stop_drop(payload)
    if hook_name in {"stop", "Stop"}:
        control = _load_isolated_control(payload)
        if control is not None:
            if control.get("isolated_supervisor") is True:
                stdout = _run_isolated_supervisor(control, payload)
            else:
                stdout = "{}"
            sys.stdout.write(stdout)
            sys.stdout.flush()
            record_stop_delivery(payload, stdout, inbound_stop_id)
            return
        if _cwd_in_isolated_workspace_tree(payload):
            sys.stdout.write("{}")
            return
    req = _request(payload)
    if hook_name in _PRE_PERMISSION and _is_routine_safe(hook_name, payload):
        sys.stdout.write(json.dumps({"permission": "allow"}))
        if req is not None:
            try:
                urllib.request.urlopen(req, timeout=PASSIVE_CLIENT_TIMEOUT_SECONDS).read(
                    MAX_RESPONSE_BYTES
                )
            except Exception:
                pass
        return
    if req is None:
        sys.stdout.write(_pass_through(hook_name, payload))
        return
    if hook_name in _PRE_PERMISSION:
        timeout = PERMISSION_CLIENT_TIMEOUT_SECONDS
    elif hook_name in {"stop", "Stop"}:
        timeout = STOP_CLIENT_TIMEOUT_SECONDS
    elif hook_name == "beforeSubmitPrompt":
        timeout = SUBMIT_CLIENT_TIMEOUT_SECONDS
    else:
        timeout = PASSIVE_CLIENT_TIMEOUT_SECONDS
    try:
        body = _post(req, timeout)
        stdout = _safe_hook_stdout(body, hook_name, payload)
    except Exception:
        stdout = _pass_through(hook_name, payload)
    sys.stdout.write(stdout)
    if hook_name in {"stop", "Stop"}:
        sys.stdout.flush()
        record_stop_delivery(payload, stdout, inbound_stop_id)


if __name__ == "__main__":
    main()
