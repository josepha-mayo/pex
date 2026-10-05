from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from scripts import demo


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _port_accepts(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def _wait_for(predicate, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return predicate()


class _OkHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_args) -> None:
        pass


def test_wait_http_true_when_server_answers() -> None:
    server = HTTPServer(("127.0.0.1", 0), _OkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        assert demo._wait_http(f"http://127.0.0.1:{port}", timeout=5.0) is True
    finally:
        server.shutdown()
        server.server_close()


def test_wait_http_false_when_nothing_listens() -> None:
    port = _free_port()
    assert demo._wait_http(f"http://127.0.0.1:{port}", timeout=0.5) is False


def test_wait_http_stops_early_when_child_exits() -> None:
    port = _free_port()
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    try:
        assert _wait_for(lambda: child.poll() is not None, timeout=10.0)
        started = time.monotonic()
        assert demo._wait_http(f"http://127.0.0.1:{port}", timeout=45.0, child=child) is False
        assert time.monotonic() - started < 5.0
    finally:
        if child.poll() is None:
            child.kill()


def test_terminate_tree_kills_grandchildren() -> None:
    """A wrapper child's own children must die with it.

    npm/vite spawn the real worker beneath the direct child; signalling only
    the wrapper leaks the port-holding grandchild. This mirrors the launcher:
    the parent is spawned with the same session options ``main`` uses.
    """

    port = _free_port()
    grandchild = (
        "import socket, time; "
        "s = socket.socket(); "
        "s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); "
        f"s.bind(('127.0.0.1', {port})); "
        "s.listen(1); "
        "time.sleep(120)"
    )
    parent = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}]); "
        "time.sleep(120)"
    )

    child = subprocess.Popen(
        [sys.executable, "-c", parent],
        start_new_session=(os.name != "nt"),
    )
    try:
        assert _wait_for(lambda: _port_accepts(port), timeout=15.0), (
            "grandchild never bound its port"
        )
        demo._terminate_tree(child)
        child.wait(timeout=10)
        assert _wait_for(lambda: not _port_accepts(port), timeout=15.0), (
            "grandchild survived the tree kill and still holds its port"
        )
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)


def test_live_prepare_run_seeds_an_isolated_free_worker(tmp_path, monkeypatch) -> None:
    import json

    from scripts import demo_live

    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "must-not-leak")
    workspace, env = demo_live.prepare_run(tmp_path / "run", "nemotron-3-ultra-free")
    # Its own git root, so OpenCode never adopts an enclosing repo/AGENTS.md.
    assert (workspace / ".git").is_dir()
    assert {"csv_utils.py", "test_csv_utils.py", "verify.py"} <= {
        p.name for p in workspace.iterdir()
    }
    config = json.loads((tmp_path / "run" / "opencode.json").read_text(encoding="utf-8"))
    assert config["model"] == "opencode/nemotron-3-ultra-free"
    assert "provider" not in config  # native free route: no fabricated credential
    assert "PEX_SUPERVISOR_API_KEY" not in env
    assert env["HOME"].startswith(str(tmp_path))


def test_live_prepare_run_rejects_paid_models(tmp_path) -> None:
    import pytest

    from scripts import demo_live

    with pytest.raises(ValueError, match="free OpenCode model"):
        demo_live.prepare_run(tmp_path / "run", "nvidia/nemotron-3-super-120b-a12b")
    assert not (tmp_path / "run").exists()


def test_live_goal_requires_real_pytest(tmp_path) -> None:
    from scripts import demo_live

    goal = demo_live.goal_payload(tmp_path)
    assert goal["project_id"] == str(tmp_path)
    assert goal["acceptance_criteria"] == ["python -m pytest -q exits successfully"]


def test_live_opencode_binding_is_loopback_only(tmp_path, monkeypatch) -> None:
    from pathlib import Path

    from scripts import demo_live

    command = demo_live.opencode_command(Path("opencode"), 4096)
    assert command[command.index("--hostname") + 1] == "127.0.0.1"
    assert "--pure" in command
    missing = tmp_path / "nope.exe"
    monkeypatch.setenv("PEX_OPENCODE_BIN", str(missing))
    assert demo_live.resolve_opencode() is None
    missing.write_bytes(b"")
    assert demo_live.resolve_opencode() == missing


def test_live_session_seeds_an_idle_handoff_target(tmp_path, monkeypatch) -> None:
    import urllib.parse

    from scripts import demo_live

    calls = []
    vendor_ids = iter(["vendor-main", "vendor-sibling"])

    def fake_call(method, url, body=None, timeout=30):
        calls.append((method, url, body))
        if url.startswith("http://x/session?") or "/session?" in url:
            return {"id": next(vendor_ids)}
        if url.endswith("/v1/goals"):
            return {"goal": {"id": "goal-1"}}
        if "/v1/sessions/" in url and method == "GET":
            return {"id": urllib.parse.unquote(url.rsplit("/", 1)[-1])}
        return {}

    monkeypatch.setattr(demo_live, "_call", fake_call)
    monkeypatch.setattr(demo_live, "_poll", lambda fn, timeout, what: fn())
    monkeypatch.setattr(
        demo_live, "goal_payload", lambda workspace, scenario="false-claim": {"x": 1}
    )

    ids = demo_live.start_supervised_session(tmp_path, bridge="http://b", opencode="http://x")
    assert ids == {
        "session_id": "opencode:vendor-main",
        "goal_id": "goal-1",
        "sibling_id": "opencode:vendor-sibling",
    }
    attaches = [
        body["goal_id"]
        for method, url, body in calls
        if method == "POST" and url.endswith("/attach")
    ]
    assert attaches == ["goal-1", "goal-1"]


def test_live_session_survives_a_missing_handoff_target(tmp_path, monkeypatch) -> None:
    import urllib.parse

    from scripts import demo_live

    vendor_ids = iter(["vendor-main"])

    def fake_call(method, url, body=None, timeout=30):
        if "/session?" in url and method == "POST":
            return {"id": next(vendor_ids)}
        if url.endswith("/v1/goals"):
            return {"goal": {"id": "goal-1"}}
        if "/v1/sessions/" in url and method == "GET":
            return {"id": urllib.parse.unquote(url.rsplit("/", 1)[-1])}
        return {}

    monkeypatch.setattr(demo_live, "_call", fake_call)
    monkeypatch.setattr(demo_live, "_poll", lambda fn, timeout, what: fn())

    ids = demo_live.start_supervised_session(tmp_path, bridge="http://b", opencode="http://x")
    assert ids["sibling_id"] is None
