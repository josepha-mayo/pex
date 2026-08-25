"""Locate Hermes CLI (`hermes acp`). Desktop process is preferred when running."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_hermes() -> str | None:
    env = os.environ.get("PEX_HERMES")
    if env and Path(env).is_file():
        return env
    local_app = Path(os.environ.get("LOCALAPPDATA") or "")
    home = Path.home()
    candidates = [
        local_app / "hermes" / "hermes-agent" / "bin" / "hermes.exe",
        local_app / "hermes" / "hermes-agent" / "bin" / "hermes",
        home / ".local" / "bin" / "hermes",
        Path("/usr/local/bin/hermes"),
    ]
    which = shutil.which("hermes")
    if which:
        candidates.insert(0, Path(which))
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def acp_command(binary: str) -> list[str]:
    return [binary, "acp"]
