from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta

from pex_protocol.enums import EventType, HarnessType
from pex_protocol.session import HarnessEvent
from pex_supervisor.background import (
    confirm_abandoned_background,
    find_abandoned_background,
    pid_running,
)


def _job_event(index, *, pid=None, running=True, command="python train.py"):
    state = {"running": running}
    if pid is not None:
        state["pid"] = pid
    return HarnessEvent(
        event_id=f"e{index}", ts=datetime(2026, 9, 6, tzinfo=UTC) + timedelta(seconds=index),
        harness_type=HarnessType.SYNTHETIC, session_id="synthetic:jobs",
        event_type=EventType.SHELL, command=command, process_state=state,
    )


def test_background_jobs_can_finish_out_of_launch_order():
    events = [_job_event(0, pid=101), _job_event(1, pid=102),
              _job_event(2, pid=101, running=False), _job_event(3, pid=102, running=False)]
    assert find_abandoned_background(events) is None


def test_unidentified_command_exit_does_not_finish_an_identified_job():
    events = [_job_event(0, pid=101),
              _job_event(1, running=False, command="git status")]
    assert find_abandoned_background(events)["pid"] == 101


def test_unidentified_job_requires_matching_command_to_finish():
    events = [_job_event(0), _job_event(1, running=False, command="git status")]
    assert find_abandoned_background(events) is not None
    events.append(_job_event(2, running=False))
    assert find_abandoned_background(events) is None


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
