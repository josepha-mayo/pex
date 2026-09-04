"""Locate Grok Build CLI. Never treat this binary as Cursor ACP (D9)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_grok_build() -> str | None:
    env = os.environ.get("PEX_GROK_BUILD")
    if env:
        path = Path(env)
        if path.is_absolute() and path.is_file():
            return str(path)
        return None
    home = Path.home()
    candidates = [
        home / ".grok" / "bin" / "grok.exe",
        home / ".grok" / "bin" / "grok",
    ]
    which = shutil.which("grok")
    if which and Path(which).is_absolute() and Path(which).is_file():
        candidates.insert(0, Path(which))
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def acp_command(binary: str) -> list[str]:
    """Official Grok Build ACP: `grok agent stdio` (docs.x.ai/build/cli/headless-scripting)."""
    path = Path(binary)
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Grok Build binary must be an existing absolute file")
    return [str(path), "agent", "stdio"]
