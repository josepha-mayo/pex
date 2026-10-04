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
