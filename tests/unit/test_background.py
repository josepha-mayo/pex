from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest
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


def test_repeated_running_observations_do_not_duplicate_a_pid_bound_job():
    events = [_job_event(0, pid=101), _job_event(1, pid=101),
              _job_event(2, pid=101, running=False)]
    assert find_abandoned_background(events) is None


def test_foreign_session_terminal_event_cannot_settle_a_job():
    foreign = _job_event(1, pid=101, running=False).model_copy(
        update={"session_id": "synthetic:other"},
    )
    result = find_abandoned_background([_job_event(0, pid=101), foreign])
    assert result is not None
    assert result["event_id"] == "e0"


def test_same_pid_observations_in_different_sessions_do_not_replace_each_other():
    foreign_launch = _job_event(1, pid=101).model_copy(
        update={"session_id": "synthetic:other"},
    )
    foreign_exit = _job_event(2, pid=101, running=False).model_copy(
        update={"session_id": "synthetic:other"},
    )
    result = find_abandoned_background([_job_event(0, pid=101), foreign_launch, foreign_exit])
    assert result is not None
    assert result["event_id"] == "e0"


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


def test_long_background_command_matches_its_terminal_event_without_prefix_alias():
    command = "python train.py --label " + "x" * 220
    events = [_job_event(0, command=command),
              _job_event(1, command=command + "other", running=False)]
    assert find_abandoned_background(events) is not None
    events.append(_job_event(2, command=command, running=False))
    assert find_abandoned_background(events) is None


@pytest.mark.parametrize("pid", [True, False, -1, 0, 2**80, "²", "9" * 5000],
                         ids=["true", "false", "negative", "zero", "huge", "unicode", "long"])
def test_invalid_observed_pid_is_unknown_not_a_process_identity(pid):
    launch = find_abandoned_background([_job_event(0, pid=pid)])
    assert launch is not None
    assert launch["pid"] is None


@pytest.mark.parametrize("pid", [True, False, -1, 0, 2**80])
def test_invalid_pid_never_reaches_native_process_lookup(pid, monkeypatch):
    def unexpected(*args):
        raise AssertionError("invalid PID reached OS lookup")

    monkeypatch.setattr("pex_supervisor.background._windows_pid_running", unexpected)
    monkeypatch.setattr("pex_supervisor.background.os.kill", unexpected)
    assert pid_running(pid) is None


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
