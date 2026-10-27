"""Read-only controller metadata, not independently verified benchmark results.

Only an explicit server-owned event file is accepted. Never opens report.json or
projects grades, prompts, reasoning, arbitrary strings or private test details.
"""

from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

LIMIT = 262144
PHASES = {
    "arm_started",
    "isolated_workspace_created",
    "worker_natural_stop",
    "review_started",
    "review_finished",
    "arm_terminal",
    "paired_terminal",
    "paired_results_available",
    "cleanup_unconfirmed",
}
TERMINALS = {
    "natural_stop",
    "no_intervention",
    "verifier_rejected",
    "budget_terminal_inconclusive",
    "supervisor_budget_terminal_inconclusive",
    "worker_budget_terminal_inconclusive",
    "infrastructure_error",
    "infrastructure_inconclusive",
    "grading_inconclusive",
}
WORKERS = {"opencode/deepseek-v4.1-flash-free", "nebius/deepseek-ai/DeepSeek-V4.1-Flash-1017"}
SUPERVISORS = {"nvidia/nemotron-3-super-120b-a12b"}


def read_evidence(path: Path | None) -> dict:
    if path is None:
        return {"state": "not_configured"}
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("explicit absolute event path required")
    try:
        # Nonblocking prevents special files hanging the owner request. No final
        # symlink following; deployment must keep parent directories server-owned.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("regular event file required")
            raw = stream.read(LIMIT + 1)
        if not raw:
            return {"state": "empty"}
        if len(raw) > LIMIT or not raw.endswith(b"\n"):
            raise ValueError("incomplete or oversized event file")
        lines = raw.splitlines()
        if len(lines) > 512:
            raise ValueError("event limit")
        arms = {
            name: {"status": "not_started", "worker_calls": None} for name in ("baseline", "pex")
        }
        paired = False
        worker = supervisor = None
        phase = observed = None
        for line in lines:
            if len(line) > 8192:
                raise ValueError("record limit")
            event = json.loads(line)
            if not isinstance(event, dict) or event.get("event") not in PHASES:
                raise ValueError("unknown phase")
            if (
                event.get("worker_model") not in WORKERS
                or event.get("supervisor_model") not in SUPERVISORS
            ):
                raise ValueError("unknown model")
            if worker is not None and (
                worker != event["worker_model"] or supervisor != event["supervisor_model"]
            ):
                raise ValueError("model changed")
            worker, supervisor = event["worker_model"], event["supervisor_model"]
            stamp = event.get("ts")
            if (
                not isinstance(stamp, str)
                or len(stamp) > 40
                or datetime.fromisoformat(stamp).tzinfo is None
            ):
                raise ValueError("timestamp required")
            phase, observed = (
                event["event"],
                datetime.fromisoformat(stamp).astimezone(UTC).isoformat(),
            )
            arm = event.get("arm")
            if arm is not None and arm not in arms:
                raise ValueError("unknown arm")
            if phase in {
                "arm_started",
                "isolated_workspace_created",
                "worker_natural_stop",
                "review_started",
                "review_finished",
                "arm_terminal",
            }:
                if arm is None or arms[arm]["status"] in TERMINALS:
                    raise ValueError("invalid arm sequence")
                arms[arm]["status"] = "running"
                if "worker_calls" in event:
                    calls = event["worker_calls"]
                    if (
                        type(calls) is not int
                        or not 0 <= calls <= 1000
                        or calls < (arms[arm]["worker_calls"] or 0)
                    ):
                        raise ValueError("invalid call count")
                    arms[arm]["worker_calls"] = calls
                if phase == "arm_terminal":
                    if event.get("terminal") not in TERMINALS:
                        raise ValueError("unknown terminal")
                    arms[arm]["status"] = event["terminal"]
            if phase in {"paired_terminal", "paired_results_available"}:
                if not all(a["status"] in TERMINALS for a in arms.values()):
                    raise ValueError("premature paired terminal")
                paired = True
        return {
            "state": "recorded",
            "phase": phase,
            "observed_at": observed,
            "worker_model": worker,
            "supervisor_model": supervisor,
            "paired_terminal": paired,
            "arms": arms,
        }
    except (OSError, ValueError, TypeError, RecursionError):
        # Do not leak paths, provider error strings or stale metadata.
        return {"state": "unavailable"}
