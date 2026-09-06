"""Observe launched background jobs that the worker later stopped monitoring."""

from __future__ import annotations

import os
import re
from hashlib import sha256
from typing import Any

from pex_protocol.enums import EventType
from pex_protocol.session import HarnessEvent

_BACKGROUND_LAUNCH = re.compile(
    r"(?:nohup\b|\bstart\s+/b\b|\bstart-process\b|\b--daemon\b|\bdaemonize\b|"
    r"(?:^|[\s;|&])&\s*$)",
    re.I,
)
_TEST_COMMAND = re.compile(
    r"\b(?:pytest|npm\s+test|cargo\s+test|go\s+test)\b",
    re.I,
)
_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5
# Conservative portable lookup bound; unsupported identities remain unknown.
_MAX_OBSERVED_PID = 2**31 - 1


def _valid_pid(value: object) -> bool:
    return type(value) is int and 0 < value <= _MAX_OBSERVED_PID


def _command_identity(command: str) -> str:
    return sha256(command.encode("utf-8", "surrogatepass")).hexdigest()


def find_abandoned_background(events: list[HarnessEvent]) -> dict[str, Any] | None:
    """Return the latest observed background launch that never finished.

    Evidence is the command and optional pid. Silence is not treated as a job.
    """
    ordered = sorted(events, key=lambda item: item.ts)
    launches: list[dict[str, Any]] = []
    for event in ordered:
        launch = _launch_from(event)
        if launch is not None:
            launches.append(launch)
            continue
        if not launches:
            continue
        # Jobs need not finish in reverse launch order. Remove only the latest
        # matching launch; an unrelated terminal event cannot settle a job.
        for index in range(len(launches) - 1, -1, -1):
            if _finishes(event, launches[index]):
                launches.pop(index)
                break
    return launches[-1] if launches else None


def confirm_abandoned_background(abandoned: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop event-only jobs whose pid is gone from the process table."""
    if not abandoned:
        return None
    pid = abandoned.get("pid")
    if not isinstance(pid, int):
        return abandoned
    observed = pid_running(pid)
    if observed is False:
        return None
    confirmed = dict(abandoned)
    confirmed["process_table"] = "running" if observed is True else "unobserved"
    return confirmed


def pid_running(pid: int) -> bool | None:
    """Return whether *pid* is alive. None means the table could not be read."""
    if not _valid_pid(pid):
        return None
    if os.name == "nt":
        return _windows_pid_running(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def _windows_pid_running(pid: int) -> bool | None:
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            err = int(kernel32.GetLastError() or 0)
            if err == _ERROR_ACCESS_DENIED:
                return True
            return False
        code = wintypes.DWORD()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        if not ok:
            return None
        return int(code.value) == _STILL_ACTIVE
    except Exception:
        return None


def _launch_from(event: HarnessEvent) -> dict[str, Any] | None:
    if event.event_type not in {EventType.SHELL, EventType.TOOL_CALL}:
        return None
    command = str(event.command or "").strip()
    state = event.process_state if isinstance(event.process_state, dict) else {}
    if _TEST_COMMAND.search(command):
        return None
    if state.get("running") is False or state.get("exit_code") is not None:
        return None
    explicit = any(state.get(key) is True for key in ("background", "detached", "daemon"))
    running = state.get("running") is True
    marked = bool(_BACKGROUND_LAUNCH.search(command))
    if not explicit and not running and not marked:
        return None
    pid = _observed_pid(state)
    return {
        "command": command[:200],
        "command_identity": _command_identity(command),
        "pid": pid,
        "event_id": event.event_id,
    }


def _observed_pid(state: dict[str, Any]) -> int | None:
    for key in ("pid", "process_id"):
        raw = state.get(key)
        if _valid_pid(raw):
            return raw
        if isinstance(raw, str):
            text = raw.strip()
            if 1 <= len(text) <= 10 and text.isascii() and text.isdecimal():
                parsed = int(text)
                if _valid_pid(parsed):
                    return parsed
    return None


def _finishes(event: HarnessEvent, launch: dict[str, Any]) -> bool:
    state = event.process_state if isinstance(event.process_state, dict) else {}
    if state.get("running") is not False and state.get("exit_code") is None:
        return False
    if launch.get("pid") is not None:
        return _observed_pid(state) == launch["pid"]
    command = str(event.command or "").strip()
    return bool(command) and _command_identity(command) == launch.get("command_identity")
