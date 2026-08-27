from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BRIDGE = os.environ.get("PEX_BRIDGE_URL", "http://127.0.0.1:7420")
TOKEN_PATH = Path(os.environ.get("PEX_HOME", Path.home() / ".pex")) / "bridge.token"

# Routine worker tools must never freeze the session. PEX asks only on
# destructive shell. Editor/read/search tools pass through immediately.
_PRE_PERMISSION = {
    "preToolUse",
    "beforeShellExecution",
    "beforeMCPExecution",
    "beforeReadFile",
}
_DESTRUCTIVE = (
    "rm -rf",
    "rm --recursive",
    "git push --force",
    "git push -f",
    "drop table",
    "kubectl delete",
    "terraform destroy",
    "chmod 777",
)


def _token() -> str:
    env = os.environ.get("PEX_TOKEN")
    if env:
        return env
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    return ""


def cursor_stop_drop_dir() -> Path:
    override = os.environ.get("PEX_CURSOR_STOP_DROP")
    if override:
        return Path(override)
    return Path(os.environ.get("PEX_HOME", Path.home() / ".pex")) / "pexbench" / "stops"


def record_stop_drop(payload: dict) -> None:
    hook_name = str(payload.get("hook_event_name") or "")
    if hook_name not in {"stop", "Stop"}:
        return
    try:
        dest = cursor_stop_drop_dir()
        dest.mkdir(parents=True, exist_ok=True)
        name = f"{time.time_ns()}_{os.getpid()}.json"
        (dest / name).write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        return


def parse_payload(raw: str, argv: list[str] | None = None) -> dict:
    fallback = (argv or [""])[1] if argv and len(argv) > 1 else "unknown"
    text = (raw or "").strip().lstrip("\ufeff")
    data: dict | None = None
    if text:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                    if isinstance(parsed, dict):
                        data = parsed
                except json.JSONDecodeError:
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
    return any(token in blob for token in _DESTRUCTIVE)


def _safe_hook_stdout(raw_body: str, hook_name: str, payload: dict | None = None) -> str:
    """Pass through bridge policy. Never freeze routine editor work."""
    try:
        body = json.loads((raw_body or "").strip() or "{}")
    except json.JSONDecodeError:
        return "{}"
    if not isinstance(body, dict):
        return "{}"
    if hook_name in _PRE_PERMISSION:
        perm = body.get("permission")
        if perm not in {"allow", "deny", "ask"}:
            perm = "ask" if payload and _is_destructive(payload) else "allow"
        if perm == "ask" and payload and not _is_destructive(payload):
            perm = "allow"
        return json.dumps({"permission": perm})
    if hook_name == "beforeSubmitPrompt":
        if body.get("continue") is False:
            question = str(body.get("user_message") or "").strip()
            out: dict[str, object] = {"continue": False}
            if question:
                out["user_message"] = question
            return json.dumps(out)
        return json.dumps({"continue": True})
    if hook_name in {"stop", "Stop"}:
        text = str(body.get("followup_message") or "").strip()
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
        if _is_destructive(payload):
            return json.dumps({"permission": "ask"})
        return json.dumps({"permission": "allow"})
    if hook_name == "beforeSubmitPrompt":
        return json.dumps({"continue": True})
    return "{}"


def _fail_open(hook_name: str) -> str:
    """Bridge unreachable. Never freeze the worker."""
    return _pass_through(hook_name, {})


def _post(req: urllib.request.Request, timeout: float) -> str:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def main() -> None:
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    payload = parse_payload(sys.stdin.read(), sys.argv)
    hook_name = str(payload.get("hook_event_name") or "")
    record_stop_drop(payload)
    # Fast path: keep the worker moving unless the command is destructive.
    if hook_name in _PRE_PERMISSION and not _is_destructive(payload):
        sys.stdout.write(json.dumps({"permission": "allow"}))
        # Best-effort notify; never block the editor on this.
        try:
            token = _token()
            req = urllib.request.Request(
                f"{BRIDGE}/v1/hooks/cursor",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=0.4).read()
        except Exception:
            pass
        return
    token = _token()
    req = urllib.request.Request(
        f"{BRIDGE}/v1/hooks/cursor",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    if hook_name in _PRE_PERMISSION and _is_destructive(payload):
        timeout = 4
    elif hook_name in {"stop", "Stop"}:
        timeout = 8
    elif hook_name == "beforeSubmitPrompt":
        timeout = 2
    else:
        timeout = 0.4
    try:
        body = _post(req, timeout)
        sys.stdout.write(_safe_hook_stdout(body, hook_name, payload))
    except Exception:
        sys.stdout.write(_pass_through(hook_name, payload))


if __name__ == "__main__":
    main()
