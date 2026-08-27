"""Hermes Agent plugin: official ctx.register_hook surface.

Drop this folder into a Hermes plugins path when asked. Do not launch Hermes.
pre_tool_call fails open in 0.4s so the worker is not frozen.
on_session_end is observe-only; nudges inject on the next pre_llm_call {context}.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BRIDGE = os.environ.get("PEX_BRIDGE", "http://127.0.0.1:7420").rstrip("/")
TOKEN = os.environ.get("PEX_BRIDGE_TOKEN", "")


def _post(hook_event_name: str, payload: dict, timeout: float) -> dict:
    body = {"hook_event_name": hook_event_name, **payload}
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(
        f"{BRIDGE}/v1/hooks/hermes",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def pre_tool_call(tool_name: str, args: dict | None = None, session_id: str | None = None, **kwargs):
    body = _post(
        "pre_tool_call",
        {
            "tool_name": tool_name,
            "args": args or {},
            "session_id": session_id or kwargs.get("session_id"),
            "cwd": kwargs.get("cwd"),
        },
        timeout=0.4,
    )
    action = body.get("action")
    if action in {"block", "approve"}:
        return {"action": action, "message": body.get("message") or "PEX policy"}
    return None


def pre_llm_call(session_id: str, user_message: str | None = None, **kwargs):
    body = _post(
        "pre_llm_call",
        {
            "session_id": session_id,
            "user_message": user_message,
            "cwd": kwargs.get("cwd"),
        },
        timeout=0.4,
    )
    context = body.get("context")
    if isinstance(context, str) and context.strip() and not context.startswith("PEX:"):
        return {"context": context}
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
        timeout=8.0,
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
        timeout=0.4,
    )
    return None


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("on_session_end", on_session_end)
    ctx.register_hook("post_llm_call", post_llm_call)
