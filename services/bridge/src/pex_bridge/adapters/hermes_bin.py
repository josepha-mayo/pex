"""Locate the Hermes CLI for an explicit `hermes acp` attach; never launch desktop."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_hermes() -> str | None:
    env = os.environ.get("PEX_HERMES")
    if env:
        path = Path(env)
        if path.is_absolute() and path.is_file():
            return str(path)
        return None
    local_app = os.environ.get("LOCALAPPDATA")
    home = Path.home()
    candidates = [
        home / ".local" / "bin" / "hermes",
        Path("/usr/local/bin/hermes"),
    ]
    if local_app:
        candidates[:0] = [
            Path(local_app) / "hermes" / "hermes-agent" / "bin" / "hermes.exe",
            Path(local_app) / "hermes" / "hermes-agent" / "bin" / "hermes",
        ]
    which = shutil.which("hermes")
    if which and Path(which).is_absolute() and Path(which).is_file():
        candidates.insert(0, Path(which))
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def acp_command(binary: str) -> list[str]:
    path = Path(binary)
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Hermes binary must be an existing absolute file")
    return [str(path), "acp"]
