"""Deterministic trajectory features. LLM reasoning is not used here."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime

from pex_protocol.enums import EventType
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent
from pex_protocol.supervisor import TrajectoryScores

# Phrase-level only. Bare "done" matches ordinary chat and is not a completion claim.
SUCCESS_CLAIM_RE = re.compile(
    r"\b("
    r"all tests passed|tests passed|tests pass|"
    r"completed successfully|deployment complete|evaluation done|"
    r"i am done|i'm done|we're done|all done"
    r")\b",
    re.IGNORECASE,
)


def _now() -> datetime:
    return datetime.now(UTC)


def extract_features(events: list[HarnessEvent]) -> dict:
    ordered_events = sorted(events, key=lambda event: event.ts)
    commands: list[str] = []
    tools: list[str] = []
    files: list[str] = []
    errors: list[str] = []
    stops = 0
    tests_run = 0
    success_claims = 0
    edits = 0
    latest_pytest_ok: bool | None = None
    for event in ordered_events:
        is_test_event = False
        if event.command:
            commands.append(event.command.strip())
            lowered = event.command.lower()
            if any(token in lowered for token in ("pytest", "npm test", "cargo test", "go test")):
                is_test_event = True
        if event.tool_name:
            tools.append(event.tool_name)
        files.extend(event.file_paths)
        if event.error:
            errors.append(event.error)
        if event.event_type == EventType.STOP:
            stops += 1
        if event.event_type == EventType.FILE_EDIT:
            edits += 1
        if isinstance(event.process_state, dict):
            pytest_info = event.process_state.get("pytest")
            if isinstance(pytest_info, dict):
                if pytest_info.get("ok") is True:
                    is_test_event = True
                    latest_pytest_ok = True
                elif pytest_info.get("ok") is False:
                    is_test_event = True
                    latest_pytest_ok = False
        if is_test_event:
            tests_run += 1
        worker_narration = event.event_type in {
            EventType.AGENT_RESPONSE,
            EventType.STOP,
        }
        if worker_narration and SUCCESS_CLAIM_RE.search(event.message_delta or ""):
            success_claims += 1

    command_counts = Counter(commands)
    repeated_commands = sum(count - 1 for count in command_counts.values() if count > 1)
    tool_counts = Counter(tools)
    repeated_tools = sum(count - 1 for count in tool_counts.values() if count > 1)
    repeated_errors = sum(count - 1 for count in Counter(errors).values() if count > 1)
    unique_tools = len(set(tools))
    last_ts = ordered_events[-1].ts if ordered_events else _now()
    first_ts = ordered_events[0].ts if ordered_events else last_ts
    span = max((last_ts - first_ts).total_seconds(), 1.0)

    return {
        "event_count": len(events),
        "repeated_command_count": repeated_commands,
        "repeated_tool_count": repeated_tools,
        "unique_tool_count": unique_tools,
        "tool_count": len(tools),
        "file_touch_count": len(set(files)),
        "error_count": len(errors),
        "identical_error_count": repeated_errors,
        "stops": stops,
        "tests_run": tests_run,
        "success_claims": success_claims,
        "edits": edits,
        "span_seconds": span,
        "pytest_failed": latest_pytest_ok is False,
    }


def score_trajectory(events: list[HarnessEvent], goal: Goal | None) -> TrajectoryScores:
    """Features only. Missing a pytest event is uncertainty, not a contradiction."""
    features = extract_features(events)
    action_count = max(features["tool_count"] + features["event_count"], 1)
    repeated_low_info = (
        features["repeated_command_count"] + features["repeated_tool_count"]
    ) / action_count
    verified_progress = min(1.0, (features["edits"] + features["tests_run"]) / 8)
    error_loop = min(1.0, float(features["identical_error_count"]) / 3.0)
    drift = max(
        0.0,
        min(
            1.0,
            0.4 * repeated_low_info
            + 0.5 * error_loop
            - 0.35 * verified_progress,
        ),
    )
    stagnation = max(
        0.0,
        min(
            1.0,
            0.4 * repeated_low_info
            + 0.4 * (features["identical_error_count"] / max(features["error_count"], 1))
            + 0.2 * (1.0 if features["edits"] == 0 and features["tool_count"] > 6 else 0.0),
        ),
    )
    premature = 0.0
    if features.get("pytest_failed") and features["stops"]:
        premature = 0.88
    contradiction = 0.0
    if features["success_claims"] and features.get("pytest_failed"):
        contradiction = 0.85

    return TrajectoryScores(
        drift=round(drift, 4),
        stagnation=round(stagnation, 4),
        premature_completion=round(premature, 4),
        claim_contradiction=round(contradiction, 4),
        features=features,
    )
