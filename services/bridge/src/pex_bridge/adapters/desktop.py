"""Detect coding-agent desktop apps that are already running.

PEX attaches to these first. CLI binaries are a fallback, not the product.
Never launch a second copy of a running editor to attach.
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime

from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.session import HarnessSession

# Starter desktop inventory (CORE §9 / BUILD §12.1–12.4, §12.10). Grok Bot stays
# a registered adapter but is not listed here.
DESKTOP_APPS = (
    {
        "name": "cursor",
        "images": ("Cursor.exe",),
        "kind": "desktop",
        "connect": "hooks",
        "surface": (
            "An already-running Cursor.exe. PEX lists it without restarting the editor. "
            "Hooks are optional control, not required to discover an open session. "
            "Never spawn another Cursor to attach."
        ),
    },
    {
        "name": "codex",
        "images": ("ChatGPT.exe",),
        "kind": "desktop",
        "connect": "observe-process",
        "surface": (
            "ChatGPT.exe is observe/focus only. Private desktop JSON-RPC is unproven. "
            "Isolated `codex app-server --listen stdio://` is a separate attach."
        ),
    },
    {
        "name": "opencode",
        "images": ("OpenCode.exe", "opencode.exe"),
        "kind": "desktop",
        "connect": "observe-process",
        "surface": (
            "An already-running OpenCode desktop or TUI. Observe/focus only until "
            "`opencode serve` HTTP is attached. Do not spawn serve to list the session."
        ),
    },
    {
        "name": "hermes",
        "images": ("Hermes.exe", "NousHermes.exe"),
        "kind": "desktop",
        "connect": "observe-process",
        "surface": (
            "An already-running Hermes desktop. Observe/focus only until `hermes acp` "
            "or plugin hooks attach. Do not launch Hermes to discover it."
        ),
    },
    {
        "name": "claude_code",
        "images": ("claude.exe",),
        "kind": "desktop",
        "connect": "hooks",
        "surface": (
            "An already-running Claude Code CLI. User-started sessions attach through "
            "settings.json hooks without restarting Claude Code. Hooks are not "
            "auto-installed on discover."
        ),
    },
)

_SCOPED_SNAPSHOT_MAX_AGE_SECONDS = 5.0


@dataclass(frozen=True)
class DesktopProcessSnapshot:
    names: frozenset[str]
    available: bool
    captured_at: float


_PROCESS_SNAPSHOT: ContextVar[DesktopProcessSnapshot | None] = ContextVar(
    "pex_desktop_process_snapshot",
    default=None,
)


def capture_running_image_snapshot() -> DesktopProcessSnapshot:
    names = _read_running_image_names()
    return DesktopProcessSnapshot(
        names=frozenset(names) if names is not None else frozenset(),
        available=names is not None,
        captured_at=time.monotonic(),
    )


@contextmanager
def scoped_running_image_snapshot(
    snapshot: DesktopProcessSnapshot,
) -> Iterator[None]:
    token = _PROCESS_SNAPSHOT.set(snapshot)
    try:
        yield
    finally:
        _PROCESS_SNAPSHOT.reset(token)


def _active_process_snapshot() -> DesktopProcessSnapshot | None:
    snapshot = _PROCESS_SNAPSHOT.get()
    if snapshot is None:
        return None
    if time.monotonic() - snapshot.captured_at > _SCOPED_SNAPSHOT_MAX_AGE_SECONDS:
        return None
    return snapshot

def desktop_process_running(image: str, running: set[str] | None = None) -> bool:
    names = {name.lower() for name in (running if running is not None else running_image_names())}
    return image.lower() in names


def matching_desktop_image(
    images: tuple[str, ...] | str,
    running: set[str] | None = None,
) -> str | None:
    names = {name.lower() for name in (running if running is not None else running_image_names())}
    candidates = (images,) if isinstance(images, str) else images
    for image in candidates:
        if image.lower() in names:
            return image
    return None


def is_desktop_observe_session(session: HarnessSession | None) -> bool:
    """True for generic process-inventory tiles, never a vendor thread/conversation."""

    if session is None:
        return False
    source = (session.metadata or {}).get("source")
    return (
        session.vendor_session_id == "desktop"
        or source == "desktop"
        or str(session.id).endswith(":desktop")
    )


def upsert_desktop_observe_session(
    sessions: dict[str, HarnessSession],
    *,
    harness: HarnessType,
    process: str | tuple[str, ...],
    skip_if_other_sessions: bool = False,
) -> None:
    """Register an already-open desktop app. Never launches it. Drops it when it exits."""

    session_id = f"{harness.value}:desktop"
    if skip_if_other_sessions and any(key != session_id for key in sessions):
        sessions.pop(session_id, None)
        return
    snapshot = _active_process_snapshot()
    if snapshot is not None and not snapshot.available:
        return
    hit = matching_desktop_image(process)
    if not hit:
        sessions.pop(session_id, None)
        return
    existing = sessions.get(session_id)
    sessions[session_id] = HarnessSession(
        id=session_id,
        harness_type=harness,
        vendor_session_id="desktop",
        status=SessionStatus.DISCOVERED,
        last_activity=datetime.now(UTC),
        goal_id=None,
        supervision_paused=existing.supervision_paused if existing else False,
        metadata={
            "source": "desktop",
            "process": hit,
            "existing_session": True,
        },
    )


def running_image_names() -> set[str]:
    snapshot = _active_process_snapshot()
    if snapshot is not None:
        return set(snapshot.names)
    return _read_running_image_names() or set()


def _read_running_image_names() -> set[str] | None:
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        raw = subprocess.check_output(
            ["tasklist", "/fo", "csv", "/nh"],
            text=True,
            errors="replace",
            timeout=3.0,
            **kwargs,
        )
    except Exception:
        return None
    if len(raw) > 2_097_152:
        return None
    names: set[str] = set()
    for row in csv.reader(io.StringIO(raw)):
        if row:
            names.add(row[0])
    return names


def list_desktop_apps(running: set[str] | None = None) -> list[dict]:
    images = {name.lower() for name in (running if running is not None else running_image_names())}
    found: list[dict] = []
    for app in DESKTOP_APPS:
        hit = next((image for image in app["images"] if image.lower() in images), None)
        if hit:
            found.append(
                {
                    "name": app["name"],
                    "kind": "desktop",
                    "connect": app["connect"],
                    "process": hit,
                    "surface": app["surface"],
                }
            )
    return found


def desktop_process_inventory(running: set[str] | None = None) -> dict:
    found = list_desktop_apps(running)
    present = {item["name"] for item in found}
    return {
        "running": found,
        "not_running": [app["name"] for app in DESKTOP_APPS if app["name"] not in present],
    }
