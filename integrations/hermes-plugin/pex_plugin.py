"""Hermes Agent plugin: official ctx.register_hook surface.

Drop this folder into a Hermes plugins path when asked. Do not launch Hermes.
Hook calls fail open within a bounded deadline so the worker is not frozen.
on_session_end is observe-only. pre_llm_call forwards context only when the
bridge returns an actual non-generic context value for that active hook.
"""

from __future__ import annotations

import http.client
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request

BRIDGE = os.environ.get(
    "PEX_BRIDGE_URL", os.environ.get("PEX_BRIDGE", "http://127.0.0.1:7420")
).rstrip("/")
MAX_RESPONSE_BYTES = 65_536
MAX_PAYLOAD_BYTES = 1_048_576
MAX_TOKEN_CHARS = 512
STANDARD_CLIENT_TIMEOUT_SECONDS = 7.0
PASSIVE_CLIENT_TIMEOUT_SECONDS = 0.5
MAX_HARNESS_TEXT_CHARS = 4_096


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


def _token() -> str:
    def validated(raw_value: str) -> str:
        cleaned = raw_value.strip()
        if (
            not cleaned
            or len(cleaned) > MAX_TOKEN_CHARS
            or any(ord(char) < 0x21 or ord(char) > 0x7E for char in cleaned)
        ):
            return ""
        return cleaned

    value = os.environ.get("PEX_HERMES_HOOK_TOKEN") or os.environ.get("PEX_HOOK_TOKEN")
    return validated(value or "")


def _post(hook_event_name: str, payload: dict, timeout: float) -> dict:
    endpoint = _endpoint()
    if endpoint is None:
        return {}
    body = {**payload, "hook_event_name": hook_event_name}
    try:
        encoded = json.dumps(body, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        return {}
    if len(encoded) > MAX_PAYLOAD_BYTES:
        return {}
    headers = {"Content-Type": "application/json"}
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        endpoint,
        data=encoded,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError):
        return {}
    if len(raw) > MAX_RESPONSE_BYTES:
        return {}
    try:
        parsed = _strict_json_loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _endpoint() -> str | None:
    try:
        parsed = urllib.parse.urlparse(BRIDGE)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        return None
    hostname = parsed.hostname
    normalized_host = "127.0.0.1" if hostname == "localhost" else hostname
    authority = f"[{normalized_host}]" if normalized_host == "::1" else normalized_host
    if port is not None:
        authority += f":{port}"
    return f"http://{authority}/v1/hooks/hermes"


def pre_tool_call(tool_name: str, args: dict | None = None, task_id: str | None = None, **kwargs):
    body = _post(
        "pre_tool_call",
        {
            "tool_name": tool_name,
            "args": args or {},
            "session_id": kwargs.get("session_id"),
            "task_id": task_id or kwargs.get("task_id"),
            "cwd": kwargs.get("cwd"),
        },
        timeout=STANDARD_CLIENT_TIMEOUT_SECONDS,
    )
    action = body.get("action")
    if action == "block":
        message = str(body.get("message") or "PEX policy")[:MAX_HARNESS_TEXT_CHARS]
        return {"action": action, "message": message}
    return None


def pre_llm_call(session_id: str, user_message: str | None = None, **kwargs):
    body = _post(
        "pre_llm_call",
        {
            "session_id": session_id,
            "user_message": user_message,
            "cwd": kwargs.get("cwd"),
        },
        timeout=STANDARD_CLIENT_TIMEOUT_SECONDS,
    )
    context = body.get("context")
    if isinstance(context, str) and context.strip() and not context.startswith("PEX:"):
        return {"context": context[:MAX_HARNESS_TEXT_CHARS]}
    return None


def on_session_end(session_id: str, completed: bool | None = None, **kwargs):
    _post(
        "on_session_end",
        {
            "session_id": session_id,
            "completed": completed,
            "text": kwargs.get("assistant_response") or kwargs.get("text") or "session ended",
            "cwd": kwargs.get("cwd"),
        },
        # Hermes ignores on_session_end return values, so do not hold its
        # lifecycle for the named-hook Stop analysis budget.
        timeout=PASSIVE_CLIENT_TIMEOUT_SECONDS,
    )
    return None


def post_llm_call(session_id: str, assistant_response: str | None = None, **kwargs):
    _post(
        "post_llm_call",
        {
            "session_id": session_id,
            "assistant_response": assistant_response,
            "cwd": kwargs.get("cwd"),
        },
        timeout=PASSIVE_CLIENT_TIMEOUT_SECONDS,
    )
    return None


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("on_session_end", on_session_end)
    ctx.register_hook("post_llm_call", post_llm_call)
