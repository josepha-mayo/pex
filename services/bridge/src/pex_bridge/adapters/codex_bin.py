"""Locate the real Codex CLI. Do not treat PATH `agent` as Codex."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_codex_bin() -> str | None:
    env = os.environ.get("PEX_CODEX_BIN")
    if env:
        path = Path(env)
        if path.is_file():
            return str(path)
    which = shutil.which("codex")
    if which:
        return which
    home = Path.home()
    local_app = Path(os.environ.get("LOCALAPPDATA") or "")
    extra: list[Path] = []
    try:
        extra.extend((local_app / "OpenAI" / "Codex" / "bin").glob("*/codex.exe"))
    except Exception:
        pass
    candidates = [
        *extra,
        home / ".codex" / "plugins" / ".plugin-appserver" / "codex.exe",
        home / ".codex" / "plugins" / ".plugin-appserver" / "codex",
        home / ".local" / "bin" / "codex",
        Path("/usr/local/bin/codex"),
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def app_server_command(binary: str) -> list[str]:
    """Windows has no app-server daemon; stdio is the supported local transport."""
    return [binary, "app-server", "--listen", "stdio://"]
