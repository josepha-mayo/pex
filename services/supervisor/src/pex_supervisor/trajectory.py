"""Conservative material-review candidates, never intervention verdicts."""

import hashlib
import json
from dataclasses import dataclass

from pex_protocol.enums import EventPhase, EventType
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
    failures = []
    signature = None
    progress_anchor = None
    for event in events:
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
                or event.event_type not in {
                    EventType.SHELL, EventType.TOOL_RESULT, EventType.TOOL_FAILURE,
                }):
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
