"""Optional local startup timings: fixed phase names, no workspace or credentials."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from uuid import uuid4

PHASES = frozenset(
    {
        "python_entry",
        "app_import_begin",
        "app_import_ready",
        "routes_begin",
        "routes_ready",
        "store_begin",
        "store_ready",
        "pets_begin",
        "pets_ready",
        "adapters_ready",
        "recovery_begin",
        "recovery_ready",
        "ready",
    }
)
_path: Path | None = None
_started = 0.0
_seen: set[str] = set()


def start_startup_trace(home: Path) -> None:
    """Opt-in native diagnostic. Failure must never prevent bridge startup."""
    global _path, _started, _seen
    _path = None
    _seen = set()
    _started = time.monotonic()
    try:
        root = home / "startup-traces"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"startup-{os.getpid()}-{uuid4().hex}.jsonl"
        with path.open("x", encoding="utf-8"):
            pass
        _path = path
        mark_startup_phase("python_entry")
    except OSError:
        _path = None


def mark_startup_phase(phase: str) -> None:
    global _path
    if _path is None or phase not in PHASES or phase in _seen:
        return
    _seen.add(phase)
    row = {
        "schema": "pex.startup-timing.v1",
        "phase": phase,
        "elapsed_seconds": round(max(0.0, time.monotonic() - _started), 6),
    }
    try:
        with _path.open("a", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError:
        _path = None
