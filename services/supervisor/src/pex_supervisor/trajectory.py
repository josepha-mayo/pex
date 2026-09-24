"""Conservative material-review candidates, never intervention verdicts."""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass

from pex_protocol.enums import EventPhase, EventType, HarnessType
from pex_protocol.session import HarnessEvent
from pex_protocol.supervisor import SupervisorRequest


@dataclass(frozen=True)
class TrajectoryReviewCandidate:
    key: str
    event_ids: tuple[str, ...]
    kind: str = "repeated_observed_command_failure"


def observed_command_exit_code(event: HarnessEvent) -> int | None:
    values = [value for value in (
        (event.process_state or {}).get("exit_code"),
        event.metadata.get("command_exit_code"),
    ) if value is not None]
    if not values or any(type(value) is not int for value in values):
        return None
    return values[0] if all(value == values[0] for value in values) else None


def _opencode_tool_failure_candidate(
    request: SupervisorRequest, events: list[HarnessEvent]
) -> TrajectoryReviewCandidate | None:
    """Review three distinct, identical tool errors in one live worker turn.

    An error update for the same OpenCode call can arrive more than once. The
    call and parent-message identities prevent duplicated SSE frames or errors
    across separate user turns from manufacturing a stall signal.
    """
    current = request.event
    goal = request.goal
    if (
        request.session.harness_type != HarnessType.OPENCODE
        or current.event_type != EventType.TOOL_FAILURE
        or current.phase != EventPhase.AFTER
        or goal is None
    ):
        return None
    lineage = current.metadata.get("opencode_message_lineage")
    if not isinstance(lineage, dict) or lineage.get("stream_contiguous") is not True:
        return None
    parent = lineage.get("parent_message_id")
    call = current.metadata.get("opencode_tool_call_id")
    signature = (current.tool_name, current.error)
    if not all(isinstance(value, str) and value for value in (*signature, parent, call)):
        return None
    failures: list[HarnessEvent] = []
    seen_calls: set[str] = set()
    for event in events:
        if (
            event.session_id != request.session.id
            or event.project_id != request.session.project_id
            or event.harness_type != HarnessType.OPENCODE
            or event.goal_id != goal.id
            or event.ts < goal.updated_at
            or event.event_type != EventType.TOOL_FAILURE
            or event.phase != EventPhase.AFTER
            or (event.tool_name, event.error) != signature
            or event.metadata.get("opencode_tool_status") != "error"
        ):
            continue
        source = event.metadata.get("opencode_message_lineage")
        event_call = event.metadata.get("opencode_tool_call_id")
        if (
            not isinstance(source, dict)
            or source.get("stream_contiguous") is not True
            or source.get("parent_message_id") != parent
            or not isinstance(event_call, str)
            or not event_call
            or event_call in seen_calls
        ):
            continue
        seen_calls.add(event_call)
        failures.append(event)
    if (
        len(failures) < 3
        or failures[-1].event_id != current.event_id
        or (current.ts - failures[-3].ts).total_seconds() > 600
    ):
        return None
    scope = {
        "kind": "repeated_opencode_tool_failure",
        "session_id": request.session.id,
        "workspace_binding": request.session.metadata.get("workspace_binding"),
        "goal": goal.model_dump(mode="json"),
        "parent_message_id": parent,
        "failure": signature,
    }
    try:
        encoded = json.dumps(scope, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError):
        return None
    return TrajectoryReviewCandidate(
        key=hashlib.sha256(encoded).hexdigest(),
        event_ids=tuple(event.event_id for event in failures[-3:]),
        kind="repeated_opencode_tool_failure",
    )


def trajectory_review_candidate(request: SupervisorRequest) -> TrajectoryReviewCandidate | None:
    goal = request.goal
    current = request.event
    if (not request.trajectory_review_enabled or goal is None or goal.paused
            or request.session.supervision_paused or current.goal_id != goal.id):
        return None
    events = list(request.recent_events)
    ids = [event.event_id for event in events]
    if len(ids) != len(set(ids)):
        return None
    matching = [event for event in events if event.event_id == current.event_id]
    if matching and matching[0] != current:
        return None
    if not matching:
        events.append(current)
    # Future or ambiguous history must not authorize a review of an older event.
    if any(event.ts > current.ts for event in events):
        return None
    events.sort(key=lambda event: event.ts)
    if events[-1].event_id != current.event_id:
        return None
    tool_candidate = _opencode_tool_failure_candidate(request, events)
    if tool_candidate is not None:
        return tool_candidate
    command_types = {EventType.SHELL, EventType.TOOL_RESULT, EventType.TOOL_FAILURE}
    material_times = Counter(
        event.ts for event in events
        if event.goal_id == goal.id and event.ts >= goal.updated_at
        and (event.event_type == EventType.FILE_EDIT or (
            event.command and event.phase in {EventPhase.AFTER, EventPhase.TERMINAL}
            and event.event_type in command_types
        ))
    )
    failures = []
    signature = None
    progress_anchor = None
    for event in events:
        if material_times[event.ts] > 1:
            # No sequence field disambiguates equal-time material observations.
            # Never let input order place a failure after possibly newer progress.
            failures = []
            signature = None
            progress_anchor = f"ambiguous:{event.ts.isoformat()}"
            continue
        if event.goal_id != goal.id or event.ts < goal.updated_at:
            failures = []
            signature = None
            continue
        if event.event_type == EventType.FILE_EDIT:
            failures = []
            signature = None
            progress_anchor = event.event_id
            continue
        if (not event.command or event.phase not in {EventPhase.AFTER, EventPhase.TERMINAL}
                or event.event_type not in command_types):
            continue
        exit_code = observed_command_exit_code(event)
        failed = exit_code is not None and exit_code != 0
        if not failed:
            failures = []
            signature = None
            progress_anchor = event.event_id
            continue
        observed = (event.command, exit_code, event.error or event.message_delta)
        if observed != signature:
            failures = []
            signature = observed
        failures.append(event)
    if (len(failures) < 3 or failures[-1].event_id != current.event_id
            or (current.ts - failures[-3].ts).total_seconds() > 600):
        return None
    scope = {
        "kind": "repeated_observed_command_failure",
        "session_id": request.session.id,
        "cwd": request.session.cwd,
        "workspace_binding": request.session.metadata.get("workspace_binding"),
        "goal": goal.model_dump(mode="json"),
        "failure": signature,
        "progress_anchor": progress_anchor,
    }
    try:
        encoded = json.dumps(scope, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError):
        return None
    key = hashlib.sha256(encoded).hexdigest()
    return TrajectoryReviewCandidate(key=key, event_ids=tuple(e.event_id for e in failures[-3:]))
