"""Per-harness connect methods. There is no single protocol.

Each row is from official docs or a binary that exists on this machine.
Tailscale is a network overlay for HTTP loopback services, not a harness protocol.
Do not open extra Cursor windows. Do not start Hermes/Devin unless the operator asks.
"""

from __future__ import annotations

# name -> how PEX should talk to it when that product is already running
CONNECT = {
    "cursor": {
        "method": "hooks",
        "command": None,
        "docs": "https://cursor.com/docs/hooks.md",
        "note": "This desktop session. ~/.cursor/hooks.json stdin/stdout JSON. stop.followup_message, beforeShellExecution permission allow|deny|ask. Never spawn a second Cursor.",
    },
    "codex": {
        "method": "app-server-stdio",
        "command": ["codex", "app-server", "--listen", "stdio://"],
        "docs": "https://developers.openai.com/codex/app-server",
        "note": (
            "Isolated `codex app-server --listen stdio://` JSONL. ChatGPT.exe is observe/focus only "
            "until same-socket JSON-RPC is proven. Do not treat the desktop process as App Server Deep. "
            "Do not turn/start on the operator's live threads without intent."
        ),
    },
    "grok_bot": {
        "method": "observe-process",
        "command": None,
        "docs": "https://docs.x.ai/grok-bot/overview",
        "note": "Separate product from Grok Build. Cloud-computer teammates. No official local control API; observe Grok Bot.exe only.",
    },
    "grok_build": {
        "method": "acp-stdio",
        "command": ["grok", "agent", "stdio"],
        "docs": "https://docs.x.ai/build/cli/headless-scripting",
        "note": "Not Grok Bot. Official ACP is grok agent stdio. One-shot is grok -p. Do not spawn unless the operator asks.",
    },
    "opencode": {
        "method": "http",
        "command": ["opencode", "serve"],
        "docs": "https://opencode.ai/docs/server/",
        "note": "Deep only after opencode serve (GET /session, POST /session/:id/prompt_async). A running TUI is not the HTTP API.",
    },
    "qwen": {
        "method": "http",
        "command": ["qwen", "serve"],
        "docs": None,
        "note": "Deep after `qwen serve` HTTP attach and an SSE event pump. A process without events is not Deep.",
    },
    "hermes": {
        "method": "acp-stdio",
        "command": ["hermes", "acp"],
        "docs": "https://hermes-agent.nousresearch.com/docs/user-guide/features/acp",
        "note": (
            "Do not open Hermes. Official plugin hooks: pre_tool_call block/approve, "
            "pre_llm_call {context} inject, on_session_end observe. Control ACP is `hermes acp` only when asked."
        ),
    },
    "devin": {
        "method": "org-api",
        "command": None,
        "docs": "https://docs.devin.ai/api-reference/overview",
        "note": "Do not open Devin.exe. Official control is api.devin.ai/v3/organizations/{org_id}/sessions.",
    },
    "claude_code": {
        "method": "hooks",
        "command": None,
        "docs": None,
        "note": "settings.json / Agent SDK hook JSON when Claude Code is the running harness.",
    },
    "kimi": {
        "method": "acp-stdio",
        "command": ["kimi", "acp"],
        "docs": None,
        "note": "ACP JSON-RPC. Do not assume Cursor authenticate method ids.",
    },
    "omp": {
        "method": "acp-stdio",
        "command": ["omp", "acp"],
        "docs": None,
        "note": "Oh My Pi ACP (`omp acp`). Deep after handshake. STOP inspect from session/update idle/end_turn. Do not spawn unless asked.",
    },
    "pi": {
        "method": "extension-events",
        "command": None,
        "docs": None,
        "note": "Basic until a documented local control surface exists.",
    },
}


def annotate(item: dict) -> dict:
    meta = CONNECT.get(item.get("name") or "", {})
    if not meta:
        return item
    out = dict(item)
    out.setdefault("connect", meta["method"])
    out.setdefault("surface", meta["note"])
    return out
