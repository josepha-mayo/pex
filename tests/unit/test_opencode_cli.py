import asyncio
import hashlib
import json
import time
from copy import deepcopy

import pytest

from benchmarks import opencode_cli
from benchmarks.opencode_cli import completed_turn


def events():
    return [
        {"type": "step_start", "sessionID": "s", "part": {"sessionID": "s", "messageID": "m"}},
        {"type": "text", "sessionID": "s",
         "part": {"sessionID": "s", "messageID": "m", "text": "Done."}},
        {"type": "step_finish", "sessionID": "s",
         "part": {"sessionID": "s", "messageID": "m", "reason": "stop"}},
    ]


def encode(rows):
    return b"".join(json.dumps(row).encode() + b"\n" for row in rows)


def test_complete_cli_turn_binds_current_session_and_exact_bytes():
    raw = encode(events())
    result = completed_turn(raw, exit_code=0, expected_session="s")
    assert result.session_id == "s"
    assert result.messages == ("Done.",)
    assert result.event_count == 3
    assert result.stdout_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.stdout_bytes == len(raw)


@pytest.mark.parametrize("mutation", [
    lambda rows: rows.pop(),
    lambda rows: rows[2]["part"].update(reason="tool-calls"),
    lambda rows: rows[1].update(sessionID="other"),
    lambda rows: rows[1]["part"].update(sessionID="other"),
    lambda rows: rows[2]["part"].update(messageID="previous"),
    lambda rows: rows.pop(0),
    lambda rows: rows[1].update(type="error"),
    lambda rows: rows[1]["part"].update(text=None),
])
def test_cli_completion_refuses_ambiguous_or_failed_current_turn(mutation):
    rows = deepcopy(events())
    mutation(rows)
    with pytest.raises(ValueError):
        completed_turn(encode(rows), exit_code=0)


@pytest.mark.parametrize("raw", [b"", b"not-json\n", b"[]\n", b"\n",
                                  b'{"type":"error","type":"step_finish"}\n',
                                  b'{"timestamp":NaN}\n'])
def test_cli_completion_refuses_invalid_exact_log(raw):
    with pytest.raises(ValueError):
        completed_turn(raw, exit_code=0)


def test_a_previous_valid_cli_log_cannot_satisfy_failed_or_other_session_turn():
    with pytest.raises(ValueError):
        completed_turn(encode(events()), exit_code=1)
    with pytest.raises(ValueError, match="session"):
        completed_turn(encode(events()), exit_code=0, expected_session="next-session")


def test_old_message_stop_cannot_complete_a_newer_started_step():
    rows = events()
    rows.insert(2, {"type": "step_start", "sessionID": "s",
                    "part": {"sessionID": "s", "messageID": "newer"}})
    with pytest.raises(ValueError, match="terminal stop"):
        completed_turn(encode(rows), exit_code=0)


def test_cli_log_rejects_exponent_overflow_and_non_utf8_bytes():
    raw = encode(events()).replace(b'"type": "text"', b'"timestamp": 1e999, "type": "text"')
    with pytest.raises(ValueError, match="non-finite"):
        completed_turn(raw, exit_code=0)
    with pytest.raises(ValueError):
        completed_turn(encode(events()).decode().encode("utf-16"), exit_code=0)


@pytest.mark.parametrize("bound,value", [("MAX_EVENTS", 2), ("MAX_LINE_BYTES", 4),
                                        ("MAX_OUTPUT_BYTES", 1)])
def test_cli_completion_enforces_each_capture_bound(monkeypatch, bound, value):
    monkeypatch.setattr(opencode_cli, bound, value)
    with pytest.raises(ValueError):
        completed_turn(encode(events()), exit_code=0)


async def test_executor_uses_explicit_environment_and_retains_exact_log(tmp_path, monkeypatch):
    monkeypatch.setattr(opencode_cli.sys, "platform", "linux")
    raw = encode(events())

    class Process:
        returncode = None
        pid = 12345

        def __init__(self):
            self.stdout = asyncio.StreamReader()
            self.stdout.feed_data(raw)
            self.stdout.feed_eof()
            self.stderr = asyncio.StreamReader()
            self.stderr.feed_eof()

        async def wait(self):
            self.returncode = 0
            return 0

    async def launch(*args, **kwargs):
        assert args[-3:] == ("s", "--", "--this is prompt text")
        assert kwargs["env"] == {"PUBLIC_CONFIG": "explicit"}
        assert kwargs["start_new_session"] is True
        return Process()

    monkeypatch.setattr(opencode_cli.asyncio, "create_subprocess_exec", launch)
    def absent_group(pid, signal):
        assert signal == 0
        raise ProcessLookupError

    monkeypatch.setattr(opencode_cli.os, "killpg", absent_group, raising=False)
    stdout = tmp_path / "stdout.jsonl"
    result = await opencode_cli.run_turn(
        executable=tmp_path / "opencode", workspace=tmp_path, model="controlled/pinned",
        prompt="--this is prompt text", environment={"PUBLIC_CONFIG": "explicit"},
        stdout_path=stdout, stderr_path=tmp_path / "stderr", deadline=time.monotonic() + 5,
        session_id="s",
    )
    assert stdout.read_bytes() == raw
    assert result.session_id == "s"


async def test_executor_timeout_kills_and_reaps_live_owned_group(tmp_path, monkeypatch):
    monkeypatch.setattr(opencode_cli.sys, "platform", "linux")
    cleanup = []
    stopped = asyncio.Event()

    class Process:
        returncode = None
        pid = 12345
        stdout = asyncio.StreamReader()
        stderr = asyncio.StreamReader()

        async def wait(self):
            await stopped.wait()
            cleanup.append("reaped")
            return self.returncode

    process = Process()

    async def launch(*args, **kwargs):
        return process

    def kill_group(pid, signal):
        assert pid == process.pid
        cleanup.append("killed")
        process.returncode = -9
        stopped.set()

    monkeypatch.setattr(opencode_cli.asyncio, "create_subprocess_exec", launch)
    monkeypatch.setattr(opencode_cli.os, "killpg", kill_group, raising=False)
    monkeypatch.setattr(opencode_cli.signal, "SIGKILL", 9, raising=False)
    with pytest.raises(TimeoutError):
        await opencode_cli.run_turn(
            executable=tmp_path / "opencode", workspace=tmp_path, model="controlled/pinned",
            prompt="Fix the task", environment={}, stdout_path=tmp_path / "stdout.jsonl",
            stderr_path=tmp_path / "stderr", deadline=time.monotonic() + 0.03,
        )
    assert cleanup == ["killed", "reaped"]


async def test_expired_executor_never_launches_or_overwrites_existing_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(opencode_cli.sys, "platform", "linux")
    stdout = tmp_path / "stdout.jsonl"
    stdout.write_bytes(b"historical log")

    async def forbidden_launch(*args, **kwargs):
        pytest.fail("expired turn must not launch")

    monkeypatch.setattr(opencode_cli.asyncio, "create_subprocess_exec", forbidden_launch)
    with pytest.raises(TimeoutError):
        await opencode_cli.run_turn(
            executable=tmp_path / "opencode", workspace=tmp_path, model="controlled/pinned",
            prompt="Fix the task", environment={}, stdout_path=stdout,
            stderr_path=tmp_path / "stderr", deadline=0,
        )
    assert stdout.read_bytes() == b"historical log"


async def test_executor_refuses_surviving_group_without_signalling_reaped_leader(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(opencode_cli.sys, "platform", "linux")
    probes = []

    class Process:
        returncode = None
        pid = 12345

        def __init__(self):
            self.stdout = asyncio.StreamReader()
            self.stdout.feed_data(encode(events()))
            self.stdout.feed_eof()
            self.stderr = asyncio.StreamReader()
            self.stderr.feed_eof()

        async def wait(self):
            self.returncode = 0
            return 0

    async def launch(*args, **kwargs):
        return Process()

    def surviving_group(pid, signal):
        probes.append((pid, signal))
        assert signal == 0, "a reaped leader cannot safely identify a group to kill"

    monkeypatch.setattr(opencode_cli.asyncio, "create_subprocess_exec", launch)
    monkeypatch.setattr(opencode_cli.os, "killpg", surviving_group, raising=False)
    with pytest.raises(RuntimeError, match="process-group exit is unproven"):
        await opencode_cli.run_turn(
            executable=tmp_path / "opencode", workspace=tmp_path, model="controlled/pinned",
            prompt="Fix the task", environment={}, stdout_path=tmp_path / "stdout.jsonl",
            stderr_path=tmp_path / "stderr", deadline=time.monotonic() + 5,
        )
    assert probes == [(12345, 0)]
