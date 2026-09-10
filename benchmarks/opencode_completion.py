"""Observation-only completion fence for bounded OpenCode behavioral probes.

Not a task-success evaluator. An idle worker can still have incorrect artifacts.
OpenCode removes idle sessions from /session/status; missing entries count as
idle only within a successfully fetched dictionary, never on transport failure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


def _timestamp(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def completed_generation(
    messages: Any, statuses: Any, session_id: str, *, minimum_user_count: int = 1
) -> tuple[str, str] | None:
    """Return newest user/assistant IDs only for an idle, successful generation.

    Do not let a previous successful reply satisfy a newly delivered follow-up.
    Reject ambiguous/malformed observations rather than manufacturing completion.
    """
    if not isinstance(statuses, dict) or not isinstance(messages, list):
        return None
    status = statuses.get(session_id, {"type": "idle"})
    if not isinstance(status, dict) or status.get("type") != "idle":
        return None
    infos = []
    for message in messages:
        info = message.get("info") if isinstance(message, dict) else None
        if not isinstance(info, dict) or info.get("sessionID") != session_id:
            return None
        stamp = info.get("time")
        if (
            not isinstance(stamp, dict)
            or not _timestamp(stamp.get("created"))
            or not isinstance(info.get("id"), str)
            or not info["id"]
        ):
            return None
        infos.append(info)
    if len({info["id"] for info in infos}) != len(infos):
        return None
    users = [info for info in infos if info.get("role") == "user"]
    if len(users) < max(1, minimum_user_count):
        return None

    # OpenCode IDs are time-sortable; use ID as a deterministic same-ms tie break.
    def latest(info):
        return info["time"]["created"], info["id"]

    user = max(users, key=latest)
    assistants = [info for info in infos if info.get("role") == "assistant"]
    if not assistants:
        return None
    assistant = max(assistants, key=latest)
    completed = assistant["time"].get("completed")
    if (
        assistant.get("parentID") != user["id"]
        or assistant["time"]["created"] < user["time"]["created"]
        or not _timestamp(completed)
        or completed < assistant["time"]["created"]
        or assistant.get("finish") != "stop"
        or assistant.get("error") is not None
    ):
        return None
    return user["id"], assistant["id"]


@dataclass
class QuietCompletionFence:
    """Reset quiescence on new generation, event, action, or unsettled work."""

    seconds: float = 12.0
    _identity: tuple[Any, ...] | None = None
    _since: float | None = None

    def observe(
        self,
        *,
        now: float,
        generation: tuple[str, str] | None,
        event_ids: tuple[str, ...],
        followup_count: int,
        reviews_present: bool,
        journal_complete: bool,
    ) -> bool:
        if not (generation and event_ids and reviews_present and journal_complete):
            self._identity = None
            self._since = None
            return False
        identity = (generation, tuple(sorted(event_ids)), followup_count)
        if identity != self._identity or self._since is None or now < self._since:
            self._identity = identity
            self._since = now
        return now - self._since >= self.seconds
