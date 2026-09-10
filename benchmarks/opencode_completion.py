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


def belongs_to_case(event: Any, session: Any, expected_session_id: str | None) -> bool:
    """Keep a global SSE stream from contaminating an isolated case's pipeline.

    Before the case session and goal are stored, no event is eligible. Require
    both the event and adapter-provided session to agree with the selected case.
    """
    return (
        isinstance(expected_session_id, str)
        and bool(expected_session_id)
        and getattr(event, "session_id", None) == expected_session_id
        and getattr(session, "id", None) == expected_session_id
    )


def review_completed_for_event(
    journal: list[Any], *, event_id: str | None, session_id: str, goal_id: str
) -> bool:
    """Bind a completed model review to the exact observed completion event."""
    if not all(isinstance(value, str) and value for value in (event_id, session_id, goal_id)):
        return False
    matches = [
        row for row in journal if isinstance(row, dict) and row.get("event_id") == event_id
    ]
    if len(matches) != 1:
        return False
    row = matches[0]
    if (
        row.get("session_id") != session_id
        or row.get("goal_id") != goal_id
        or row.get("state") != "complete"
    ):
        return False
    plan = row.get("plan")
    result = plan.get("supervisor_result") if isinstance(plan, dict) else None
    return (
        isinstance(result, dict)
        and result.get("used_llm") is True
        and result.get("inference_status") == "completed"
    )


def semantic_reviews_succeeded(journal: list[Any]) -> bool:
    """A prior success must not hide a later setup/reconciliation failure.

    Ordinary deterministic triage is not an inference attempt. Failed setup can
    nevertheless report used_llm=False, so inspect every recorded result before
    deciding whether this was a clean model-backed quiet case.
    """
    completed_model_review = False
    for row in journal:
        if not isinstance(row, dict):
            return False
        plan = row.get("plan")
        if plan is None:
            continue  # Record-only events have no supervisor plan.
        if not isinstance(plan, dict):
            return False
        result = plan.get("supervisor_result")
        if result is None:
            continue
        if not isinstance(result, dict):
            return False
        used_llm = result.get("used_llm")
        status = result.get("inference_status")
        if used_llm is True and status == "completed":
            completed_model_review = True
        elif used_llm is False and status == "not_attempted":
            continue
        else:
            return False
    return completed_model_review


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
