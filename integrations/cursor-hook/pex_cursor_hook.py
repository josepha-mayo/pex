from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

BRIDGE = os.environ.get("PEX_BRIDGE_URL", "http://127.0.0.1:7420")
TOKEN_PATH = Path(os.environ.get("PEX_HOME", Path.home() / ".pex")) / "bridge.token"


def _token() -> str:
    env = os.environ.get("PEX_TOKEN")
    if env:
        return env
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    return ""


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


def _safe_hook_stdout(raw_body: str, hook_name: str) -> str:
    """Fail-open on pre-tools. Stop may return a specific follow-up, never a canned PEX: line."""
    try:
        body = json.loads((raw_body or "").strip() or "{}")
    except json.JSONDecodeError:
        return "{}"
    if not isinstance(body, dict):
        return "{}"
    if hook_name in {"preToolUse", "beforeShellExecution", "beforeMCPExecution", "beforeReadFile"}:
        perm = body.get("permission")
        if perm not in {"allow", "deny", "ask"}:
            perm = "allow"
        return json.dumps({"permission": perm})
    if hook_name == "beforeSubmitPrompt":
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


def _fail_open(hook_name: str) -> str:
    if hook_name in {"preToolUse", "beforeShellExecution", "beforeMCPExecution", "beforeReadFile"}:
        return json.dumps({"permission": "allow"})
    if hook_name == "beforeSubmitPrompt":
        return json.dumps({"continue": True})
    return "{}"


def _post_async(req: urllib.request.Request) -> None:
    def _run() -> None:
        try:
            urllib.request.urlopen(req, timeout=2).read()
        except Exception:
            return

    threading.Thread(target=_run, daemon=True).start()


def main() -> None:
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    payload = parse_payload(sys.stdin.read(), sys.argv)
    hook_name = str(payload.get("hook_event_name") or "")
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
    if hook_name in _PRE_HOOKS:
        _post_async(req)
        sys.stdout.write(_fail_open(hook_name))
        return
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            sys.stdout.write(_safe_hook_stdout(body, hook_name))
    except Exception:
        sys.stdout.write(_fail_open(hook_name))


if __name__ == "__main__":
    main()
