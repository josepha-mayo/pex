"""Cursor ACP CLI is optional extra. Never auto-discover a leftover `cursor-agent` install.

Desktop Cursor is controlled via `~/.cursor/hooks.json`. PATH `agent` is Grok Build (D9).
"""

from __future__ import annotations

import os
from pathlib import Path

GROK_AGENT_MARKERS = (
    ".grok\\bin\\agent.exe",
    ".grok/bin/agent.exe",
    ".grok\\bin\\grok.exe",
    ".grok/bin/grok.exe",
)


def resolve_cursor_agent() -> str | None:
    """Only an explicit PEX_CURSOR_AGENT path. Never scan %LOCALAPPDATA%\\cursor-agent."""
    env = os.environ.get("PEX_CURSOR_AGENT")
    if env:
        path = Path(env)
        if path.is_absolute() and path.is_file() and not _is_grok(env):
            return str(path)
    return None


def acp_command(binary: str) -> list[str]:
    path = Path(binary)
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Cursor ACP binary must be an existing absolute file")
    sibling = path.parent / "index.js"
    if path.name.lower() == "node.exe" and sibling.is_file():
        return [str(path), str(sibling), "acp"]
    if path.suffix.lower() == ".cmd":
        raise ValueError("Cursor ACP .cmd shims are not accepted; provide the real executable")
    return [str(path), "acp"]


def _is_grok(path: str) -> bool:
    lowered = path.replace("/", "\\").lower()
    return any(marker.lower() in lowered for marker in GROK_AGENT_MARKERS)
