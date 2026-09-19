from __future__ import annotations

import subprocess

import pytest
from pex_bridge.adapters import desktop
from pex_bridge.adapters.acp_harness import HermesAdapter
from pex_bridge.adapters.claude_code import ClaudeCodeAdapter
from pex_bridge.adapters.cursor import CursorAdapter
from pex_bridge.adapters.opencode import OpenCodeAdapter


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_posix_process_inventory_uses_names_only_without_windows_commands(monkeypatch, platform):
    monkeypatch.setattr(desktop.sys, "platform", platform)

    def inventory(command, **options):
        assert command == ["ps", "-A", "-o", "comm="]
        assert options["timeout"] == 3.0
        assert "creationflags" not in options
        return "  /usr/bin/opencode\n  cursor\n  claude\n  codex\n\n"

    monkeypatch.setattr(desktop.subprocess, "check_output", inventory)
    names = desktop._read_running_image_names()
    assert names == {"opencode", "cursor", "claude", "codex"}
    found = {app["name"]: app for app in desktop.list_desktop_apps(names)}
    assert set(found) == {"opencode", "cursor", "claude_code"}
    assert found["opencode"]["process"] == "opencode"
    assert not desktop.desktop_process_running("ChatGPT.exe", names)
    assert "window focus is unavailable" in found["opencode"]["surface"]


def test_windows_inventory_keeps_csv_names_and_hidden_process(monkeypatch):
    monkeypatch.setattr(desktop.sys, "platform", "win32")

    def inventory(command, **options):
        assert command == ["tasklist", "/fo", "csv", "/nh"]
        assert "creationflags" in options
        return '"OpenCode.exe","123","Console","1","20,000 K"\n'

    monkeypatch.setattr(desktop.subprocess, "check_output", inventory)
    assert desktop._read_running_image_names() == {"OpenCode.exe"}


@pytest.mark.live_desktop
def test_failed_posix_inventory_is_unavailable_not_an_empty_success(monkeypatch):
    monkeypatch.setattr(desktop.sys, "platform", "linux")

    def failed(*args, **kwargs):
        raise subprocess.TimeoutExpired("ps", 3)

    monkeypatch.setattr(desktop.subprocess, "check_output", failed)
    assert desktop._read_running_image_names() is None
    assert desktop.capture_running_image_snapshot().available is False


@pytest.mark.parametrize(
    "factory", [OpenCodeAdapter, CursorAdapter, ClaudeCodeAdapter, HermesAdapter]
)
async def test_linux_process_hints_never_claim_windows_focus_or_worker_control(
    monkeypatch, factory
):
    monkeypatch.setattr(desktop.sys, "platform", "linux")
    monkeypatch.setattr(
        desktop, "running_image_names", lambda: {"opencode", "cursor", "claude", "hermes"}
    )
    adapter = factory()
    sessions = await adapter.discover_sessions()
    assert sessions
    capabilities = await adapter.probe()
    assert capabilities.observe_session_status
    assert not capabilities.focus_ui
    assert not capabilities.send_message
