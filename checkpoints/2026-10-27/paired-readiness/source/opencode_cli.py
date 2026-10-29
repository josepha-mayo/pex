"""Bounded OpenCode CLI turns for an already isolated Linux worker.

This executor does not create the worker boundary or evaluate task success.
The controller must provide that boundary, an explicit environment, a shared
deadline, and fresh log paths. Configuration is never inherited from the host.
"""

import asyncio
import hashlib
import json
import math
import os
import signal
import sqlite3
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path

MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_EVENTS = 10_000
COMPLETION_POLL_SECONDS = 0.05
PROCESS_CLEANUP_SECONDS = 1.0


@dataclass(frozen=True)
class CliTurn:
    session_id: str
    messages: tuple[str, ...]
    event_count: int
    stdout_sha256: str
    stdout_bytes: int
    completion_kind: str = "process_exit_zero"
    actual_process_exit_code: int | None = None
    committed_terminal_sha256: str | None = None
    terminal_observed_before_shutdown: bool = False
    owned_process_group_exit_confirmed: bool = False


class CliCleanupUnconfirmed(RuntimeError):
    """Bounded owned-process cleanup failed; never a natural-stop receipt."""


def _group_absent(pid):
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return True
    return False


def _consume(task):
    if not task.cancelled():
        task.exception()


async def _stop_owned_process(process, tasks):
    """Kill only our new-session process group, and never await it unboundedly.

    A one-second cleanup-only grace is not extra worker/model time. A receipt
    still requires the original deadline, drained bounded captures, reaping,
    and group absence. Escaped pipe holders therefore fail closed, not hang.
    """
    sent = False
    try:
        os.killpg(process.pid, signal.SIGKILL)
        sent = True
    except ProcessLookupError:
        pass
    end = time.monotonic() + PROCESS_CLEANUP_SECONDS
    confirmed = False
    try:
        while True:
            if (process.returncode is not None and all(task.done() for task in tasks)
                    and _group_absent(process.pid)):
                confirmed = True
                return sent
            left = end - time.monotonic()
            if left <= 0:
                raise CliCleanupUnconfirmed("owned CLI process/capture exit unconfirmed")
            pending = {task for task in tasks if not task.done()}
            if pending:
                await asyncio.wait(pending, timeout=min(COMPLETION_POLL_SECONDS, left))
            else:
                await asyncio.sleep(min(COMPLETION_POLL_SECONDS, left))
    finally:
        if not confirmed:
            # Closing our subprocess transport releases only our pipe handles
            # and owned parent. It is not proof that an escaped descendant died.
            transport = getattr(process, "_transport", None)
            if transport is not None:
                transport.close()
        for task in tasks:
            if not task.done():
                task.cancel()
            task.add_done_callback(_consume)


def _save_process_evidence(path, value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate CLI event field")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("non-finite CLI event value")


def _float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite CLI event value")
    return parsed


def completed_turn(
    raw: bytes, *, exit_code: int, expected_session: str | None = None
) -> CliTurn:
    """Validate a natural stop in this invocation, never a previous turn's log."""
    if exit_code != 0 or not raw or len(raw) > MAX_OUTPUT_BYTES:
        raise ValueError(
            "OpenCode turn exited unsuccessfully or exceeded its output bound"
        )
    events = []
    messages = []
    session_id = None
    started = set()
    latest_message = None
    for line in raw.splitlines():
        if not line or len(line) > MAX_LINE_BYTES or len(events) >= MAX_EVENTS:
            raise ValueError("OpenCode CLI event stream exceeded its bounds")
        event = json.loads(
            line.decode("utf-8"),
            object_pairs_hook=_object,
            parse_constant=_constant,
            parse_float=_float,
        )
        if not isinstance(event, dict) or event.get("type") == "error":
            raise ValueError("OpenCode CLI event is malformed or reports an error")
        vendor = event.get("sessionID")
        if not isinstance(vendor, str) or not vendor or len(vendor) > 256:
            raise ValueError("OpenCode CLI session identity is missing")
        if (session_id is not None and session_id != vendor) or (
            expected_session is not None and expected_session != vendor
        ):
            raise ValueError("OpenCode CLI turn crossed session identities")
        session_id = vendor
        part = event.get("part")
        if not isinstance(part, dict) or part.get("sessionID") != vendor:
            raise ValueError("OpenCode CLI part is not bound to its session")
        message = part.get("messageID")
        if not isinstance(message, str) or not message or len(message) > 256:
            raise ValueError("OpenCode CLI message identity is missing")
        if event.get("type") == "step_start":
            started.add(message)
            latest_message = message
        elif message not in started:
            raise ValueError("OpenCode CLI event lacks its step start")
        if event.get("type") == "text":
            text = part.get("text")
            if not isinstance(text, str):
                raise ValueError("OpenCode CLI text is malformed")
            messages.append(text)
        events.append(event)
    if (
        not events
        or events[-1].get("type") != "step_finish"
        or (
            events[-1]["part"].get("reason") != "stop"
            or events[-1]["part"].get("messageID") != latest_message
        )
    ):
        raise ValueError("OpenCode CLI turn lacks a natural terminal stop")
    return CliTurn(
        session_id,
        tuple(messages),
        len(events),
        hashlib.sha256(raw).hexdigest(),
        len(raw),
    )


async def run_turn(
    *,
    executable: Path,
    workspace: Path,
    model: str,
    prompt: str,
    environment: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    deadline: float,
    session_id: str | None = None,
    standalone: bool = True,
    agent: str | None = None,
    terminal_database: Path | None = None,
) -> CliTurn:
    """Own one CLI process group and retain exact, exclusive output artifacts."""
    if sys.platform != "linux":
        raise RuntimeError("isolated OpenCode CLI execution requires Linux")
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("OpenCode CLI deadline must be finite")
    if not executable.is_absolute() or not workspace.is_absolute():
        raise ValueError("OpenCode executable and workspace must be absolute")
    for value, limit in ((model, 256), (prompt, 20_000), (session_id or "", 256)):
        if not isinstance(value, str) or len(value) > limit or "\x00" in value:
            raise ValueError("OpenCode CLI argument is invalid")
    if not model or not prompt.strip():
        raise ValueError("OpenCode CLI model and prompt must be nonempty")

    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError("OpenCode CLI exhausted the shared task deadline")
        return value

    async def capture(reader, handle):
        total = 0
        digest = hashlib.sha256()
        while chunk := await reader.read(64 * 1024):
            total += len(chunk)
            if total > MAX_OUTPUT_BYTES:
                raise ValueError("OpenCode CLI output exceeded its byte bound")
            handle.write(chunk)
            digest.update(chunk)
        return digest.hexdigest(), total

    if type(standalone) is not bool or (
        agent is not None
        and (
            not isinstance(agent, str)
            or not agent
            or len(agent) > 128
            or "\x00" in agent
        )
    ):
        raise ValueError("invalid explicit OpenCode runtime mode")
    command = [str(executable), "run", "--format", "json", "--model", model]
    if standalone:
        command.append("--standalone")
    if agent is not None:
        command.extend(["--agent", agent])
    if session_id:
        command.extend(["--session", session_id])
    if terminal_database is not None:
        from opencode_v2_receipt import prior_sequence

        if not standalone or prompt.startswith("-"):
            raise ValueError("CLI2 receipt requires standalone and non-option prompt")
        before_sequence = prior_sequence(terminal_database, session_id)
        # CLI2 positional rendering quotes multiword arguments; use stdin so
        # the stored user message remains byte-for-byte the admitted prompt.
    else:
        command.extend(["--", prompt])
    remaining()
    process = None
    tasks = []
    candidate = None
    shutdown_sent = False
    cleanup_confirmed = False
    failure_type = None
    pre_shutdown_exit = None
    # Unbuffered writes let the trusted-terminal probe inspect captured bytes,
    # not an unflushed renderer buffer. pread never moves the writer's offset.
    with stdout_path.open("x+b", buffering=0) as stdout, stderr_path.open("xb", buffering=0) as stderr:
        os.fchmod(stdout.fileno(), 0o600)
        os.fchmod(stderr.fileno(), 0o600)
        try:
            remaining()
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=workspace,
                env=dict(environment),
                stdin=asyncio.subprocess.PIPE
                if terminal_database is not None
                else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            tasks = [
                asyncio.create_task(capture(process.stdout, stdout)),
                asyncio.create_task(capture(process.stderr, stderr)),
                asyncio.create_task(process.wait()),
            ]
            if terminal_database is not None:
                process.stdin.write(prompt.encode("utf-8"))
                await asyncio.wait_for(process.stdin.drain(), timeout=remaining())
                process.stdin.close()
            while True:
                for task in tasks:
                    if task.done():
                        task.result()  # Capture errors must not become terminals.
                if all(task.done() for task in tasks):
                    break
                if terminal_database is not None and process.returncode in (None, 0):
                    from opencode_v2_receipt import committed_turn_v2

                    try:
                        probe = os.pread(stdout.fileno(), MAX_OUTPUT_BYTES + 1, 0)
                        candidate = committed_turn_v2(
                            probe, expected_session=session_id, database=terminal_database,
                            prompt=prompt, after_sequence=before_sequence,
                        )
                    except (ValueError, OSError, sqlite3.Error, UnicodeError):
                        candidate = None  # A partial/busy/invalid DB is not completion.
                    if candidate is not None:
                        remaining()  # Never salvage a completion after expiry.
                        break
                await asyncio.wait(
                    {task for task in tasks if not task.done()},
                    timeout=min(COMPLETION_POLL_SECONDS, remaining()),
                    return_when=asyncio.FIRST_COMPLETED,
                )
            remaining()
        except BaseException as error:
            failure_type = type(error).__name__
            raise
        finally:
            try:
                if process is not None:
                    pre_shutdown_exit = process.returncode
                    shutdown_sent = await _stop_owned_process(process, tasks)
                    cleanup_confirmed = True
            except BaseException as error:
                failure_type = type(error).__name__
                raise
            finally:
                stdout.flush()
                stderr.flush()
                retained_stdout = os.pread(stdout.fileno(), MAX_OUTPUT_BYTES + 1, 0)
                _save_process_evidence(stdout_path.with_name(stdout_path.name + ".process.json"), {
                    "schema": "pex.cli-owned-completion.v1", "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "expected_session": session_id, "after_sequence": before_sequence if terminal_database is not None else None,
                    "trusted_terminal_observed_before_shutdown": candidate is not None,
                    "committed_terminal_sha256": None if candidate is None else candidate.committed_terminal_sha256,
                    "terminal_session_id": None if candidate is None else candidate.session_id,
                    "captured_stdout_sha256": hashlib.sha256(retained_stdout).hexdigest(),
                    "captured_stdout_bytes": len(retained_stdout),
                    "pre_shutdown_exit_code": pre_shutdown_exit,
                    "actual_process_exit_code": None if process is None else process.returncode,
                    "owned_group_SIGKILL_sent": shutdown_sent if cleanup_confirmed else None,
                    "owned_process_group_exit_confirmed": cleanup_confirmed,
                    "capture_tasks_completed": bool(tasks) and all(task.done() and not task.cancelled() for task in tasks[:2]),
                    "failure_type": failure_type, "qualification": "process_evidence_only_not_task_success",
                })
        captured = [task.result() for task in tasks]
        descriptor = os.fstat(stdout.fileno())
        path = stdout_path.lstat()
        if (descriptor.st_dev, descriptor.st_ino) != (path.st_dev, path.st_ino):
            raise ValueError("OpenCode CLI output path changed")
        raw = os.pread(stdout.fileno(), MAX_OUTPUT_BYTES + 1, 0)
        if terminal_database is not None:
            from opencode_v2_receipt import committed_turn_v2, completed_turn_v2

            options = {"expected_session": session_id, "database": terminal_database,
                       "prompt": prompt, "after_sequence": before_sequence}
            if candidate is None:
                turn = completed_turn_v2(raw, exit_code=process.returncode, **options)
            else:
                if process.returncode != 0 and not (
                        shutdown_sent and pre_shutdown_exit is None and process.returncode == -signal.SIGKILL):
                    raise ValueError("CLI2 exited unsuccessfully before committed shutdown")
                turn = committed_turn_v2(raw, **options)
                if turn.committed_terminal_sha256 != candidate.committed_terminal_sha256:
                    raise ValueError("CLI2 committed terminal changed during owned shutdown")
                turn = replace(turn, completion_kind="committed_terminal_before_owned_shutdown",
                               terminal_observed_before_shutdown=True)
        else:
            turn = completed_turn(
                raw, exit_code=process.returncode, expected_session=session_id
            )
        if (turn.stdout_sha256, turn.stdout_bytes) != captured[0]:
            raise ValueError("OpenCode CLI captured output changed")
        remaining()
        return replace(turn, actual_process_exit_code=process.returncode,
                       owned_process_group_exit_confirmed=cleanup_confirmed)
