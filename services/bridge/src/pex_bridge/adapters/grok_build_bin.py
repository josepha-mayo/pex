"""Locate Grok Build CLI. Never treat this binary as Cursor ACP (D9)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_grok_build() -> str | None:
    env = os.environ.get("PEX_GROK_BUILD")
    if env and Path(env).is_file():
        return env
    home = Path.home()
    candidates = [
        home / ".grok" / "bin" / "grok.exe",
        home / ".grok" / "bin" / "grok",
        home / ".grok" / "bin" / "agent.exe",
        home / ".grok" / "bin" / "agent",
    ]
    which = shutil.which("grok")
    if which:
        candidates.insert(0, Path(which))
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def acp_command(binary: str) -> list[str]:
    """Official Grok Build ACP: `grok agent stdio` (docs.x.ai/build/cli/headless-scripting)."""
    return [binary, "agent", "stdio"]
