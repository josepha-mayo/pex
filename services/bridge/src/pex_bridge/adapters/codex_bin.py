"""Locate the real Codex CLI. Do not treat PATH `agent` as Codex."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_codex_bin() -> str | None:
    env = os.environ.get("PEX_CODEX_BIN")
    if env:
        path = Path(env)
        if path.is_absolute() and path.is_file():
            return str(path)
        # An explicit operator selection is an identity constraint.  Falling back to
        # an unrelated PATH/home install would silently attach a different harness.
        return None
    which = shutil.which("codex")
    if which and Path(which).is_absolute() and Path(which).is_file():
        return str(Path(which))
    home = Path.home()
    local_app = os.environ.get("LOCALAPPDATA")
    extra: list[Path] = []
    if local_app:
        try:
            for index, path in enumerate(
                (Path(local_app) / "OpenAI" / "Codex" / "bin").glob("*/codex.exe")
            ):
                if index >= 64:
                    break
                extra.append(path)
        except OSError:
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
    path = Path(binary)
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Codex binary must be an existing absolute file")
    return [str(path), "app-server", "--listen", "stdio://"]
