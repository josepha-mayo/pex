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
