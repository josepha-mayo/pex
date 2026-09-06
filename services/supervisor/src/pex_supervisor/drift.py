"""Detect broad work that does not serve the attached ledger."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from pex_protocol.enums import EventType
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent

from pex_supervisor.verify import required_files

_REFACTOR = re.compile(
    r"\b(?:refactor(?:ing)?|restructure|rename\s+all|cleanup\s+all|reformat\s+all)\b",
    re.I,
)
_FILE_TOKEN = re.compile(r"[A-Za-z0-9._-]+\.[A-Za-z0-9]{1,12}")
_ROUTINE_TEST = re.compile(r"\b(?:pytest|npm\s+test|cargo\s+test|go\s+test)\b", re.I)
_BROAD_UNRELATED = 4


def goal_path_names(goal: Goal | None) -> set[str]:
    if goal is None:
        return set()
    names = {
        PurePosixPath(str(name).replace("\\", "/")).name.casefold()
        for name in required_files(goal)
    }
    haystack = " ".join(
        [
            goal.objective,
            *goal.acceptance_criteria,
            *goal.evidence_requirements,
        ]
    )
    names.update(match.casefold() for match in _FILE_TOKEN.findall(haystack))
    return {name for name in names if name}


def unrelated_refactor(event: HarnessEvent, goal: Goal | None) -> str | None:
    """Return a broad-work candidate; lexical mismatch cannot establish irrelevance."""
    if goal is None:
        return None
    if event.event_type not in {
        EventType.FILE_EDIT,
        EventType.SHELL,
        EventType.TOOL_CALL,
        EventType.AGENT_RESPONSE,
    }:
        return None
    relevant = goal_path_names(goal)
    paths = [str(path).replace("\\", "/") for path in event.file_paths if str(path).strip()]
    unrelated = [
        path
        for path in paths
        if PurePosixPath(path).name.casefold() not in relevant
    ]
    command = str(event.command or event.message_delta or "").strip()
    named_required = bool(
        relevant and any(name in command.casefold().replace("\\", "/") for name in relevant)
    )
    if named_required or (paths and len(unrelated) < len(paths)):
        return None
    if len(unrelated) >= _BROAD_UNRELATED:
        return ", ".join(PurePosixPath(path).name for path in unrelated[:4])
    if _REFACTOR.search(command) and not named_required:
        return command[:200]
    return None


def _observed_paths(event: HarnessEvent) -> set[str]:
    return {
        str(PurePosixPath(str(path).replace("\\", "/")))
        for path in event.file_paths
        if str(path).strip()
    }


def duplicate_sibling_work(
    event: HarnessEvent,
    siblings: list[tuple[str, str, list[HarnessEvent]]],
) -> dict[str, str] | None:
    """Return overlap candidates, not proof of duplicate or completed work."""
    if event.event_type not in {EventType.FILE_EDIT, EventType.SHELL, EventType.TOOL_CALL}:
        return None
    current_paths = _observed_paths(event)
    command = str(event.command or "").strip()
    if _ROUTINE_TEST.search(command):
        command = ""
    if not current_paths and not command:
        return None
    for session_id, harness, events in siblings:
        if session_id == event.session_id:
            continue
        for prior in events:
            if (
                prior.session_id != session_id
                or prior.event_type not in {
                    EventType.FILE_EDIT, EventType.SHELL, EventType.TOOL_CALL,
                }
                or prior.ts.utcoffset() is None
                or event.ts.utcoffset() is None
                or prior.ts > event.ts
            ):
                continue
            provenance = {
                "sibling_session_id": session_id,
                "harness": harness,
                "source_event_id": prior.event_id,
                "current_event_id": event.event_id,
                "basis": "observed_overlap_candidate",
            }
            overlap = sorted(current_paths & _observed_paths(prior))
            if overlap:
                return {
                    **provenance,
                    "path": overlap[0],
                }
            prior_cmd = str(prior.command or "").strip()
            if (
                command
                and prior_cmd
                and command == prior_cmd
                and not _ROUTINE_TEST.search(prior_cmd)
            ):
                return {
                    **provenance,
                    "command": command[:200],
                }
    return None
