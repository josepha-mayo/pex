from __future__ import annotations

import importlib.util
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pex_bridge.observe as observe
import pex_supervisor.workspace as workspace
import pytest


def _evaluator():
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "evaluator.py"
    spec = importlib.util.spec_from_file_location("pexbench_evaluator_cleanup", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _DeadProcess:
    pid = 424242

    def poll(self):
        return 0

    def kill(self):  # pragma: no cover - a dead root must never be killed
        raise AssertionError("dead process was killed")


@pytest.mark.parametrize("module", [observe, workspace])
def test_windows_tree_cleanup_never_taskkills_a_dead_cached_pid(module, monkeypatch):
    run = Mock()
    monkeypatch.setattr(module.os, "name", "nt")
    monkeypatch.setattr(module.subprocess, "run", run)

    started = time.monotonic()
    module._terminate_process_tree(_DeadProcess())

    assert time.monotonic() - started < 0.25
    run.assert_not_called()


def test_evaluator_windows_tree_cleanup_never_taskkills_a_dead_cached_pid(monkeypatch):
    evaluator = _evaluator()
    run = Mock()
    monkeypatch.setattr(evaluator.os, "name", "nt")
    monkeypatch.setattr(evaluator.subprocess, "run", run)

    started = time.monotonic()
    evaluator._terminate_process_tree(_DeadProcess())

    assert time.monotonic() - started < 0.25
    run.assert_not_called()


class _EofPipe:
    closed = False

    def read(self, _size=-1):
        return b""

    def close(self):
        self.closed = True


class _BlockingInput:
    closed = False

    def write(self, _value):
        threading.Event().wait(30)

    def flush(self):
        return None

    def close(self):
        self.closed = True


class _NonReadingProcess:
    pid = 515151

    def __init__(self):
        self.stdin = _BlockingInput()
        self.stdout = _EofPipe()

    def poll(self):
        return None

    def wait(self, timeout=None):
        if timeout is None:
            return 0
        raise subprocess.TimeoutExpired("worker", timeout)

    def kill(self):
        return None


def test_evaluator_never_blocks_writing_maximum_input_to_a_nonreader(tmp_path, monkeypatch):
    evaluator = _evaluator()
    process = _NonReadingProcess()
    monkeypatch.setattr(evaluator.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(evaluator, "_terminate_process_tree", lambda _process: None)
    result: list[object] = []

    worker = threading.Thread(
        target=lambda: result.append(
            evaluator._run_bounded(
                ["worker"],
                cwd=tmp_path,
                timeout=0.05,
                input_text="x" * evaluator._MAX_SUBPROCESS_INPUT,
            )
        ),
        daemon=True,
    )
    started = time.monotonic()
    worker.start()
    worker.join(timeout=0.5)

    assert time.monotonic() - started < 1
    assert not worker.is_alive(), "stdin backpressure bypassed the subprocess timeout"


class _FailedTerminationProcess:
    pid = 616161
    stdin = None

    def __init__(self):
        self.stdout = _EofPipe()
        self.wait_calls: list[float | None] = []

    def poll(self):
        return None

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if timeout is None:
            threading.Event().wait(30)
        raise subprocess.TimeoutExpired("worker", timeout)

    def kill(self):
        return None


def test_windows_job_assignment_failure_reaps_root_and_closes_pipes(monkeypatch):
    import win32job
    from pex_protocol.windows_job import assign_job_and_resume

    process = _NonReadingProcess()
    process._handle = 123
    process.wait = Mock(return_value=0)
    process.kill = Mock()
    monkeypatch.setattr(
        win32job,
        "AssignProcessToJobObject",
        Mock(side_effect=OSError("forced assignment failure")),
    )

    with pytest.raises(OSError, match="forced assignment failure"):
        assign_job_and_resume(process)

    process.kill.assert_called_once()
    process.wait.assert_called_once_with(timeout=2)
    assert process.stdin.closed is True
    assert process.stdout.closed is True


def test_evaluator_failed_termination_never_falls_back_to_unbounded_wait(tmp_path, monkeypatch):
    evaluator = _evaluator()
    process = _FailedTerminationProcess()
    monkeypatch.setattr(evaluator.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(evaluator, "_terminate_process_tree", lambda _process: None)
    errors: list[BaseException] = []

    def invoke():
        try:
            evaluator._run_bounded(["worker"], cwd=tmp_path, timeout=0.05)
        except BaseException as exc:  # the failure mode may be surfaced, but must be bounded
            errors.append(exc)

    worker = threading.Thread(target=invoke, daemon=True)
    started = time.monotonic()
    worker.start()
    worker.join(timeout=0.5)

    assert time.monotonic() - started < 1
    assert not worker.is_alive(), "failed termination entered an unbounded process wait"
    assert None not in process.wait_calls
