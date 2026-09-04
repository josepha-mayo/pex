from __future__ import annotations

import os
import subprocess
import sys

from pex_supervisor.background import confirm_abandoned_background, pid_running


def test_pid_running_sees_this_process():
    assert pid_running(os.getpid()) is True


def test_pid_running_rejects_exited_process():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=10)
    assert pid_running(proc.pid) is False


def test_confirm_abandoned_background_drops_dead_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=10)
    assert (
        confirm_abandoned_background(
            {"command": "python train.py --full", "pid": proc.pid, "event_id": "e1"}
        )
        is None
    )


def test_confirm_abandoned_background_keeps_live_pid():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    try:
        confirmed = confirm_abandoned_background(
            {"command": "python train.py --full", "pid": proc.pid, "event_id": "e1"}
        )
        assert confirmed is not None
        assert confirmed["process_table"] == "running"
        assert confirmed["pid"] == proc.pid
    finally:
        proc.kill()
        proc.wait(timeout=10)
