"""Pytest defaults: never accidentally spend a live supervisor key during unit tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_supervisor_llm(request, monkeypatch):
    if request.node.get_closest_marker("live_llm"):
        monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
        monkeypatch.setenv("PYTHONUTF8", "1")
        monkeypatch.setenv("PYTHONIOENCODING", "utf-8")
    else:
        monkeypatch.setenv("PEX_SUPERVISOR_DISABLE", "1")
    if not request.node.get_closest_marker("live_codex"):
        monkeypatch.setenv("PEX_CODEX_ATTACH", "0")


@pytest.fixture(autouse=True)
def _quiet_desktop_processes(request, monkeypatch):
    """Keep unit probes independent of whichever coding apps are open locally."""

    if request.node.get_closest_marker("live_desktop"):
        return
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: set(),
    )
    from pex_bridge.adapters.desktop import DesktopProcessSnapshot

    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.capture_running_image_snapshot",
        lambda: DesktopProcessSnapshot(
            names=frozenset(),
            available=True,
            captured_at=0.0,
        ),
    )
