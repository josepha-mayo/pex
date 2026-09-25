"""Observation-only completion fence for bounded OpenCode behavioral probes.

Not a task-success evaluator. An idle worker can still have incorrect artifacts.
OpenCode removes idle sessions from /session/status; missing entries count as
idle only within a successfully fetched dictionary, never on transport failure.
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx


async def poll_opencode_get(transport: Any, path: str, *, deadline: float) -> Any:
    """Retry only a timed-out, read-only OpenCode observation within the proof window."""
    for attempt in range(3):
        try:
            return await transport.request("GET", path)
        except httpx.ReadTimeout:
            if attempt == 2 or time.monotonic() >= deadline:
                raise
            await asyncio.sleep(0.25)
    raise AssertionError("unreachable")


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


def review_failed_for_event(
    journal: list[Any], *, event_id: str | None, session_id: str, goal_id: str
) -> bool:
    """Identify a terminal failed review bound to the exact completion event."""
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
    return isinstance(result, dict) and result.get("inference_status") in {"failed", "timeout"}


def _deterministic_review_succeeded(result: Any) -> bool:
    """Recognize the exact no-provider result emitted by local deterministic triage."""
    action = result.get("action") if isinstance(result, dict) else None
    return (
        isinstance(result, dict)
        and result.get("used_llm") is False
        and result.get("diagnosis") == "deterministic_triage_no_supervisor_model"
        and result.get("execution_mode") in {"local", "local_deterministic"}
        and result.get("inference_status") == "not_attempted"
        and result.get("transport_status") == "not_attempted"
        and result.get("model_call_count") == 0
        and result.get("input_tokens") == 0
        and result.get("output_tokens") == 0
        and result.get("provider") is None
        and isinstance(action, dict)
        and action.get("type") == "NOOP"
    )


def deterministic_review_completed_for_event(
    journal: list[Any], *, event_id: str | None, session_id: str, goal_id: str
) -> bool:
    """Bind an exact local deterministic review to the observed completion event."""
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
    return _deterministic_review_succeeded(result)


def deterministic_reviews_succeeded(journal: list[Any]) -> bool:
    """Require every planned review to be an exact local, zero-call NOOP result."""
    completed_review = False
    for row in journal:
        if not isinstance(row, dict):
            return False
        plan = row.get("plan")
        if plan is None:
            continue
        if not isinstance(plan, dict):
            return False
        result = plan.get("supervisor_result")
        if result is None:
            continue
        if not _deterministic_review_succeeded(result):
            return False
        completed_review = True
    return completed_review


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


def recovery_interventions_succeeded(
    rows: Any, followups: Any, *, semantic: bool = True
) -> bool:
    """Require one exact worker-facing correction, helped outcome, then quiet completion."""
    if not isinstance(rows, list) or not isinstance(followups, list) or len(followups) != 1:
        return False
    if not all(isinstance(row, dict) for row in rows):
        return False
    try:
        stamped = [
            (datetime.fromisoformat(row["created_at"]), index, row)
            for index, row in enumerate(rows)
            if isinstance(row.get("created_at"), str)
        ]
    except (KeyError, ValueError):
        return False
    if len(stamped) != len(rows) or len({stamp for stamp, _, _ in stamped}) != len(rows):
        return False
    ordered = [row for _, _, row in sorted(stamped)]
    corrections = [
        (index, row)
        for index, row in enumerate(ordered)
        if row.get("action_taken") != "NOOP"
    ]
    if len(corrections) != 1:
        return False
    correction_index, correction = corrections[0]
    action = correction.get("proposed_action")
    payload = action.get("payload") if isinstance(action, dict) else None
    text = payload.get("text") if isinstance(payload, dict) else None
    metadata = correction.get("metadata")
    verifier = metadata.get("independent_verifier") if isinstance(metadata, dict) else None
    action_taken = correction.get("action_taken")
    expected_result = {
        "SEND_NUDGE": "sent",
        "CONTINUE_SESSION": "continued",
    }.get(action_taken)
    correction_review_valid = (
        metadata.get("used_llm") is True
        and metadata.get("inference_status") == "completed"
        and isinstance(verifier, dict)
        and verifier.get("approved") is True
        and verifier.get("status") == "approved"
        if semantic
        else metadata.get("used_llm") is False
        and metadata.get("inference_status") == "not_attempted"
        and metadata.get("model_call_count") == 0
        and verifier is None
    ) if isinstance(metadata, dict) else False
    if not (
        expected_result is not None
        and isinstance(text, str)
        and bool(text.strip())
        and followups == [text]
        and correction.get("result") == expected_result
        and correction.get("outcome") == "goal_evidence_supported"
        and correction.get("helped") is True
        and isinstance(correction.get("worker_response"), str)
        and bool(correction["worker_response"])
        and isinstance(metadata, dict)
        and correction_review_valid
        and metadata.get("outcome_final") is True
    ):
        return False
    for row in ordered[correction_index + 1 :]:
        metadata = row.get("metadata")
        verification = metadata.get("verification") if isinstance(metadata, dict) else None
        quiet_review_valid = (
            metadata.get("used_llm") is True
            and metadata.get("inference_status") == "completed"
            if semantic
            else metadata.get("used_llm") is False
            and metadata.get("inference_status") == "not_attempted"
            and metadata.get("model_call_count") == 0
        ) if isinstance(metadata, dict) else False
        if (
            row.get("action_taken") == "NOOP"
            and row.get("result") == "noop"
            and isinstance(metadata, dict)
            and quiet_review_valid
            and isinstance(verification, dict)
            and verification.get("acceptance_status") == "supported"
        ):
            return True
    return False


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


def retryable_provider_abort(messages: Any, session_id: str) -> str | None:
    """Classify a terminal worker-provider outage without treating it as task failure.

    Keep the classification intentionally narrow. A malformed response, model
    refusal, or ordinary worker error is not infrastructure evidence. Only the
    newest assistant generation for the selected session may establish a
    retryable HTTP/provider abort, and no provider response body is returned.
    """
    if not isinstance(messages, list) or not isinstance(session_id, str) or not session_id:
        return None
    assistants: list[dict[str, Any]] = []
    for message in messages:
        info = message.get("info") if isinstance(message, dict) else None
        if not isinstance(info, dict) or info.get("sessionID") != session_id:
            continue
        stamp = info.get("time")
        if (
            info.get("role") == "assistant"
            and isinstance(info.get("id"), str)
            and info["id"]
            and isinstance(stamp, dict)
            and _timestamp(stamp.get("created"))
        ):
            assistants.append(info)
    if not assistants:
        return None
    latest = max(assistants, key=lambda info: (info["time"]["created"], info["id"]))
    error = latest.get("error")
    data = error.get("data") if isinstance(error, dict) else None
    status = data.get("statusCode") if isinstance(data, dict) else None
    retryable = data.get("isRetryable") if isinstance(data, dict) else None
    if (
        isinstance(error, dict)
        and error.get("name") == "APIError"
        and type(status) is int
        and status in {408, 425, 429} | set(range(500, 600))
        and retryable is True
    ):
        return "worker_provider_unavailable"
    return None


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
