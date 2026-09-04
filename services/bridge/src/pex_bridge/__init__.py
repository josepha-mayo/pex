from __future__ import annotations

from typing import Any

__all__ = ["create_app", "main", "state"]


def create_app() -> Any:
    from pex_bridge.app import create_app as _create_app

    return _create_app()


def main() -> None:
    from pex_bridge.main import main as _main

    _main()


def __getattr__(name: str) -> Any:
    """Keep package import side-effect free, especially for frozen self-checks."""

    if name == "state":
        from pex_bridge.app import state

        return state
    raise AttributeError(name)
