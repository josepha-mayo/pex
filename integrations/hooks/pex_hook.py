from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BRIDGE = os.environ.get("PEX_BRIDGE_URL", "http://127.0.0.1:7420")
HARNESS = os.environ.get("PEX_HARNESS", "claude_code")
TOKEN_PATH = Path(os.environ.get("PEX_HOME", Path.home() / ".pex")) / "bridge.token"


def _token() -> str:
    env = os.environ.get("PEX_TOKEN")
    if env:
        return env
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    return ""


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        payload = {"raw": raw, "hook_event_name": "unknown"}
    if "hook_event_name" not in payload:
        payload["hook_event_name"] = payload.get("hook") or payload.get("type") or "unknown"
    token = _token()
    req = urllib.request.Request(
        f"{BRIDGE}/v1/hooks/{HARNESS}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8")
            sys.stdout.write(body if body.strip() else "{}")
    except urllib.error.URLError:
        sys.stdout.write("{}")


if __name__ == "__main__":
    main()
