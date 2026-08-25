"""Install PEX Cursor hooks into the user hooks.json without clobbering other hooks."""

from __future__ import annotations

from pathlib import Path

from pex_bridge.adapters.cursor_hooks import install_user_hooks


def install(cursor_dir: Path | None = None) -> Path:
    return install_user_hooks(cursor_dir)


if __name__ == "__main__":
    path = install()
    print(f"Installed PEX Cursor hooks at {path}")
