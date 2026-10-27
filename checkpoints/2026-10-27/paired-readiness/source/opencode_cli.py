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
import sys
import time
from dataclasses import dataclass
from pathlib import Path

MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_EVENTS = 10_000


@dataclass(frozen=True)
class CliTurn:
    session_id: str
    messages: tuple[str, ...]
    event_count: int
    stdout_sha256: str
    stdout_bytes: int


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


def completed_turn(raw: bytes, *, exit_code: int, expected_session: str | None = None) -> CliTurn:
    """Validate a natural stop in this invocation, never a previous turn's log."""
    if exit_code != 0 or not raw or len(raw) > MAX_OUTPUT_BYTES:
        raise ValueError("OpenCode turn exited unsuccessfully or exceeded its output bound")
    events = []
    messages = []
    session_id = None
    started = set()
    latest_message = None
    for line in raw.splitlines():
        if not line or len(line) > MAX_LINE_BYTES or len(events) >= MAX_EVENTS:
            raise ValueError("OpenCode CLI event stream exceeded its bounds")
        event = json.loads(line.decode("utf-8"), object_pairs_hook=_object,
                           parse_constant=_constant, parse_float=_float)
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
    if not events or events[-1].get("type") != "step_finish" or (
        events[-1]["part"].get("reason") != "stop"
        or events[-1]["part"].get("messageID") != latest_message
    ):
        raise ValueError("OpenCode CLI turn lacks a natural terminal stop")
    return CliTurn(
        session_id, tuple(messages), len(events), hashlib.sha256(raw).hexdigest(), len(raw),
    )


async def run_turn(
    *, executable: Path, workspace: Path, model: str, prompt: str,
    environment: dict[str, str], stdout_path: Path, stderr_path: Path,
    deadline: float, session_id: str | None = None,
    standalone: bool = True, agent: str | None = None,
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

    if type(standalone) is not bool or (agent is not None and (not isinstance(agent, str) or not agent or len(agent) > 128 or "\x00" in agent)):
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
        before_sequence = prior_sequence(terminal_database)
        # CLI2 positional rendering quotes multiword arguments; use stdin so
        # the stored user message remains byte-for-byte the admitted prompt.
    else:
        command.extend(["--", prompt])
    remaining()
    process = None
    tasks = []
    with stdout_path.open("x+b") as stdout, stderr_path.open("xb") as stderr:
        try:
            remaining()
            process = await asyncio.create_subprocess_exec(
                *command, cwd=workspace, env=dict(environment),
                stdin=asyncio.subprocess.PIPE if terminal_database is not None else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            if terminal_database is not None:
                process.stdin.write(prompt.encode("utf-8"))
                await process.stdin.drain()
                process.stdin.close()
            tasks = [asyncio.create_task(capture(process.stdout, stdout)),
                     asyncio.create_task(capture(process.stderr, stderr)),
                     asyncio.create_task(process.wait())]
            wait_budget = remaining()
            captured = await asyncio.wait_for(asyncio.gather(*tasks), timeout=wait_budget)
            remaining()
        finally:
            if process is not None and process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            stdout.flush()
            stderr.flush()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError("OpenCode CLI process-group exit is unproven")
        descriptor = os.fstat(stdout.fileno())
        path = stdout_path.lstat()
        if (descriptor.st_dev, descriptor.st_ino) != (path.st_dev, path.st_ino):
            raise ValueError("OpenCode CLI output path changed")
        stdout.seek(0)
        raw = stdout.read(MAX_OUTPUT_BYTES + 1)
        if terminal_database is not None:
            from opencode_v2_receipt import completed_turn_v2
            turn = completed_turn_v2(raw, exit_code=process.returncode, expected_session=session_id,
                database=terminal_database, prompt=prompt, after_sequence=before_sequence)
        else:
            turn = completed_turn(raw, exit_code=process.returncode, expected_session=session_id)
        if (turn.stdout_sha256, turn.stdout_bytes) != captured[0]:
            raise ValueError("OpenCode CLI captured output changed")
        remaining()
        return turn
