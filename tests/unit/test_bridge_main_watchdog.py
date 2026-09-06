from __future__ import annotations

import importlib
import os
import queue
import subprocess
import sys
import threading
import types

import pytest

bridge_main = importlib.import_module("pex_bridge.main")


def test_frozen_windows_watches_desktop_and_distinct_bootloader() -> None:
    assert bridge_main._desktop_watchdog_pids(
        101, frozen=True, runtime_parent_pid=202, platform="nt"
    ) == (101, 202)


def test_frozen_windows_deduplicates_same_desktop_parent() -> None:
    assert bridge_main._desktop_watchdog_pids(
        101, frozen=True, runtime_parent_pid=101, platform="nt"
    ) == (101,)


def test_nonfrozen_and_nonwindows_keep_existing_single_parent_behavior() -> None:
    assert bridge_main._desktop_watchdog_pids(
        101, frozen=False, runtime_parent_pid=202, platform="nt"
    ) == (101,)
    assert bridge_main._desktop_watchdog_pids(
        101, frozen=True, runtime_parent_pid=202, platform="posix"
    ) == (101,)


@pytest.mark.parametrize("desktop_pid", [0, -1, True, "101"])
def test_invalid_desktop_parent_is_rejected(desktop_pid) -> None:
    with pytest.raises(ValueError, match="PEX_DESKTOP_PARENT_PID"):
        bridge_main._desktop_watchdog_pids(desktop_pid, frozen=False, platform="nt")


@pytest.mark.parametrize("bootloader_pid", [0, -1, True, "202"])
def test_frozen_windows_rejects_unretainable_bootloader_parent(bootloader_pid) -> None:
    with pytest.raises(ValueError, match="bootloader"):
        bridge_main._desktop_watchdog_pids(
            101, frozen=True, runtime_parent_pid=bootloader_pid, platform="nt"
        )


def test_all_selected_parents_are_registered(monkeypatch) -> None:
    watched: list[int] = []
    monkeypatch.setattr(bridge_main, "_desktop_watchdog_pids", lambda _pid: (101, 202))
    monkeypatch.setattr(bridge_main, "_start_parent_watchdog", watched.append)
    bridge_main._start_desktop_parent_watchdogs(101)
    assert watched == [101, 202]


def test_frozen_verify_bundle_exits_without_desktop_parent(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(bridge_main.os, "name", "nt")
    monkeypatch.delenv("PEX_DESKTOP_PARENT_PID", raising=False)
    monkeypatch.setattr(sys, "argv", ["pex-bridge", "--verify-bundle"])
    monkeypatch.setattr(bridge_main, "bundled_pet_inventory", lambda: {"version": 1})
    bridge_main.main()
    assert capsys.readouterr().out.strip() == '{"version":1}'


def _forbid_app_import(monkeypatch) -> list[str]:
    imported: list[str] = []
    original = __import__

    def guarded(name, *args, **kwargs):
        imported.append(name)
        if name in {"uvicorn", "pex_bridge.config", "pex_bridge.app"}:
            raise AssertionError("heavy app import must not occur")
        return original(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded)
    return imported


def test_frozen_serving_without_parent_fails_before_app_import(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(bridge_main.os, "name", "nt")
    monkeypatch.delenv("PEX_DESKTOP_PARENT_PID", raising=False)
    monkeypatch.setattr(sys, "argv", ["pex-bridge"])
    imported = _forbid_app_import(monkeypatch)
    with pytest.raises(SystemExit):
        bridge_main.main()
    assert "pex_bridge.app" not in imported


def test_watchdog_failure_prevents_app_import(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(bridge_main.os, "name", "nt")
    monkeypatch.setenv("PEX_DESKTOP_PARENT_PID", "101")
    monkeypatch.setattr(sys, "argv", ["pex-bridge"])
    def fail_watchdog(_pid):
        raise OSError("no handle")

    monkeypatch.setattr(bridge_main, "_start_desktop_parent_watchdogs", fail_watchdog)
    imported = _forbid_app_import(monkeypatch)
    with pytest.raises(SystemExit):
        bridge_main.main()
    assert "pex_bridge.app" not in imported


def test_valid_watchdog_registration_precedes_heavy_app_import(monkeypatch) -> None:
    order: list[str] = []
    uvicorn_module = types.ModuleType("uvicorn")
    uvicorn_module.run = lambda *_args, **_kwargs: order.append("run")
    config_module = types.ModuleType("pex_bridge.config")
    config_module.normalize_loopback_host = lambda value: value
    app_module = types.ModuleType("pex_bridge.app")
    app_module.create_app = lambda: object()
    app_module.state = types.SimpleNamespace(
        token=None,
        settings=types.SimpleNamespace(host="127.0.0.1", port=7420),
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(bridge_main.os, "name", "nt")
    monkeypatch.setenv("PEX_DESKTOP_PARENT_PID", "101")
    monkeypatch.setattr(sys, "argv", ["pex-bridge"])
    def record_watchdog(_pid):
        order.append("watch")

    monkeypatch.setattr(bridge_main, "_start_desktop_parent_watchdogs", record_watchdog)
    original = __import__

    def tracked(name, *args, **kwargs):
        modules = {
            "uvicorn": uvicorn_module,
            "pex_bridge.config": config_module,
            "pex_bridge.app": app_module,
        }
        if name in modules:
            order.append(name.rsplit(".", maxsplit=1)[-1])
            return modules[name]
        return original(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", tracked)
    bridge_main.main()
    assert order == ["watch", "uvicorn", "app", "config", "run"]


@pytest.mark.skipif(os.name != "nt", reason="Windows HANDLE watchdog behavior")
@pytest.mark.parametrize("terminated_parent", [0, 1])
def test_windows_parent_handle_watchdog_exits_when_owned_parent_dies(
    terminated_parent: int,
) -> None:
    """Exercise the real Windows OpenProcess/WaitForSingleObject watcher only.

    All three processes are direct test children. Cleanup is restricted to their
    retained Popen handles, never a PID lookup, image-name query, or port scan.
    """

    sentinels: list[subprocess.Popen] = []
    watcher: subprocess.Popen | None = None
    reader: threading.Thread | None = None
    watcher_script = "\n".join(
        [
            "import sys, time",
            "from pex_bridge.main import _start_parent_watchdog",
            "for pid in sys.argv[1:]: _start_parent_watchdog(int(pid))",
            "print('ready', flush=True)",
            "time.sleep(60)",
        ]
    )
    try:
        for _ in range(2):
            sentinels.append(
                subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            )
        watcher = subprocess.Popen(
            [sys.executable, "-c", watcher_script, *(str(child.pid) for child in sentinels)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert watcher.stdout is not None
        lines: queue.Queue[str] = queue.Queue()
        reader = threading.Thread(target=lambda: lines.put(watcher.stdout.readline()), daemon=True)
        reader.start()
        assert lines.get(timeout=5).strip() == "ready"
        sentinels[terminated_parent].terminate()
        assert sentinels[terminated_parent].wait(timeout=5) is not None
        assert watcher.wait(timeout=5) == 0
    finally:
        for child in ([watcher] if watcher is not None else []) + sentinels:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=2)
        if watcher is not None:
            if watcher.stdout is not None:
                watcher.stdout.close()
            if watcher.stderr is not None:
                watcher.stderr.close()
        if reader is not None:
            reader.join(timeout=1)
