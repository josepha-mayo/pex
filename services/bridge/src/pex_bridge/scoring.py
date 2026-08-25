"""Deterministic trajectory features. LLM reasoning is not used here."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from pex_protocol.enums import EventType
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent
from pex_protocol.supervisor import TrajectoryScores

SUCCESS_CLAIM_MARKERS = (
    "tests pass",
    "all tests passed",
    "done",
    "completed successfully",
    "fixed",
    "deployment complete",
    "evaluation done",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def extract_features(events: list[HarnessEvent]) -> dict:
    commands: list[str] = []
    tools: list[str] = []
    files: list[str] = []
    errors: list[str] = []
    stops = 0
    tests_run = 0
    success_claims = 0
    edits = 0
    for event in events:
        if event.command:
            commands.append(event.command.strip())
            lowered = event.command.lower()
            if any(token in lowered for token in ("pytest", "npm test", "cargo test", "go test")):
                tests_run += 1
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
                    tests_run += 1
                elif pytest_info.get("ok") is False:
                    tests_run += 1
                    errors.append("pytest_failed")
        text = (event.message_delta or "").lower()
        if any(marker in text for marker in SUCCESS_CLAIM_MARKERS):
            success_claims += 1

    command_counts = Counter(commands)
    repeated_commands = sum(count - 1 for count in command_counts.values() if count > 1)
    unique_tools = len(set(tools))
    last_ts = events[-1].ts if events else _now()
    first_ts = events[0].ts if events else last_ts
    span = max((last_ts - first_ts).total_seconds(), 1.0)

    return {
        "event_count": len(events),
        "repeated_command_count": repeated_commands,
        "unique_tool_count": unique_tools,
        "tool_count": len(tools),
        "file_touch_count": len(set(files)),
        "error_count": len(errors),
        "identical_error_count": sum(1 for _, n in Counter(errors).items() if n > 1),
        "stops": stops,
        "tests_run": tests_run,
        "success_claims": success_claims,
        "edits": edits,
        "span_seconds": span,
        "pytest_failed": any(item == "pytest_failed" for item in errors),
    }


def score_trajectory(events: list[HarnessEvent], goal: Goal | None) -> TrajectoryScores:
    features = extract_features(events)
    tool_count = max(features["tool_count"], 1)
    repeated_low_info = features["repeated_command_count"] / tool_count
    verified_progress = min(1.0, (features["edits"] + features["tests_run"]) / 8)
    criterion_neglect = 0.0
    if goal and goal.acceptance_criteria:
        needs_tests = any("test" in item.lower() for item in goal.acceptance_criteria)
        if needs_tests and features["tests_run"] == 0 and features["stops"] > 0:
            criterion_neglect = 1.0
    drift = max(
        0.0,
        min(
            1.0,
            0.35 * repeated_low_info
            + 0.25 * (1.0 if features["identical_error_count"] else 0.0)
            + 0.25 * criterion_neglect
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
    if features["stops"] and criterion_neglect:
        premature = 0.9
    elif features.get("pytest_failed") and features["stops"]:
        premature = 0.88
    elif features["success_claims"] and features["tests_run"] == 0 and goal:
        needs_tests = any("test" in item.lower() for item in goal.acceptance_criteria + goal.evidence_requirements)
        if needs_tests:
            premature = 0.85
    elif features["stops"] and features["error_count"]:
        premature = 0.8
    contradiction = 0.0
    if features["success_claims"] and (features["tests_run"] == 0 or features["error_count"] > 0):
        contradiction = 0.8 if features["tests_run"] == 0 else 0.6

    return TrajectoryScores(
        drift=round(drift, 4),
        stagnation=round(stagnation, 4),
        premature_completion=round(premature, 4),
        claim_contradiction=round(contradiction, 4),
        features=features,
    )
