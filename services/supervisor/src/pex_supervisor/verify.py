"""Check extracted worker claims against observed events and workspace state.

A STOP with no contradicting evidence stays uncertain. Uncertain is silence.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pex_protocol.enums import EventType
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent
from pex_protocol.verification import (
    PytestInvocation,
    PytestInvocationScope,
    VerificationProbeKind,
    classify_pytest_invocation,
)

from pex_supervisor.workspace import HIDDEN, artifact_row_count

FILE_TOKEN = re.compile(
    r"^(?![A-Za-z]:)(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9._/-]{1,240}\.[A-Za-z0-9]{1,12}$"
)
FILE_CONTAINS = re.compile(
    r"(?P<path>(?![A-Za-z]:)(?!/)[A-Za-z0-9._/-]{1,240}\.[A-Za-z0-9]{1,12})"
    r"\s+(?:contains?|containing)\s+(?P<expected>.+?)(?:[.;]|$)",
    re.I,
)
FILE_ROWS = re.compile(
    r"(?P<path>(?![A-Za-z]:)(?!/)(?!.*(?:^|/)\.\.(?:/|$))"
    r"[A-Za-z0-9._/-]{1,240}\.(?:jsonl?|csv))\s+"
    r"(?:has|contains?)\s+(?P<count>\d+)\s+rows\b",
    re.I,
)
FILE_EXISTS = re.compile(
    r"(?P<path>(?![A-Za-z]:)(?!/)(?!.*(?:^|/)\.\.(?:/|$))"
    r"[A-Za-z0-9._/-]{1,240}\.[A-Za-z0-9]{1,12})"
    r"\s+(?:exists|is present|is required|must exist)\b",
    re.I,
)
ROW_RE = re.compile(r"(\d+)\s+(?:[A-Za-z]+\s+)*rows", re.I)
FAILED_NODE = re.compile(r"FAILED\s+(\S+)")
_COMPLETION_KINDS = {"tests_pass", "evaluation_complete", "deployment_complete", "complete"}
_SPECIFIC_COMPLETION_KINDS = {"tests_pass", "evaluation_complete", "deployment_complete"}
_GENERIC_DONE = re.compile(
    r"\bi(?:['’]m| am) done\b|\bwe(?:['’]re| are) done\b|\ball done\b",
    re.I,
)
MAX_EXPECTED_ROWS = 1_000_000_000
MAX_EXPECTED_TESTS = 1_000_000_000
_PYTEST_REQUIREMENT = re.compile(
    r"\b(?:pytest|test\s+suite|tests?\s+(?:pass|passing|green|succeed))\b",
    re.I,
)
_SERVICE_HEALTH_REQUIREMENT = re.compile(
    r"\b(?:health(?:check)?|readyz|livez|/health)\b",
    re.I,
)
_COMMAND_EXIT_REQUIREMENT = re.compile(
    r"(?P<path>(?![A-Za-z]:)(?!/)(?!.*(?:^|/)\.\.(?:/|$))"
    r"[A-Za-z0-9._/-]{1,240}\.(?:py|sh|ps1|js|mjs))\b",
    re.I,
)
_COUNT_NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,10})"
_VALID_TEST_COUNT = re.compile(
    rf"(?<![0-9,.-])"
    rf"(?:(?P<prefix>exactly|exact|all|at\s+least|minimum(?:\s+of)?|"
    rf"no\s+fewer\s+than|more\s+than|over)\s+)?"
    rf"(?P<count>{_COUNT_NUMBER})"
    rf"(?P<or_more>\s+or\s+more)?\s+"
    rf"(?:(?:pytest\s+)?tests?\s+(?P<metric>pass(?:ed|ing)?|succeed(?:ed|ing)?|green|collected)"
    rf"|(?P<pytest_passed>passed))\b",
    re.I,
)
_LOOSE_TEST_COUNT = re.compile(
    r"(?<![0-9A-Za-z])(?P<count>[0-9][0-9,.-]{0,24})\s+(?:or\s+more\s+)?"
    r"(?:(?:pytest\s+)?tests?\s+(?:pass(?:ed|ing)?|succeed(?:ed|ing)?|green|collected)"
    r"|passed)\b",
    re.I,
)
_AMBIGUOUS_TEST_COUNT_CONTEXT = re.compile(
    r"\b(?:at\s+most|up\s+to|no\s+more\s+than|less\s+than|under|about|around|"
    r"approximately|roughly|between|from|previously|formerly|used\s+to|"
    r"do\s+not|don't|not\s+require)\b|(?:<=|<)\s*$|[0-9]\s*[-–—]\s*$",
    re.I,
)


@dataclass(frozen=True)
class _TestCountConstraint:
    metric: str
    comparator: str
    count: int


@dataclass(frozen=True)
class _TestCountRequirement:
    status: str
    constraints: tuple[_TestCountConstraint, ...] = ()


def _visible_goal_path(path: str) -> bool:
    normalized = path.replace("\\", "/").casefold()
    parts = normalized.split("/")
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[a-z]:", normalized)
        or any(part in {"", ".", ".."} for part in parts)
    ):
        return False
    return not any(marker.casefold() in normalized for marker in HIDDEN)


def _reject_nonfinite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _pytest_info(event: HarnessEvent) -> tuple[dict[str, Any], PytestInvocation] | None:
    invocation = classify_pytest_invocation(event.command)
    if invocation is None:
        return None
    state = event.process_state if isinstance(event.process_state, dict) else {}
    info = state.get("pytest") if isinstance(state.get("pytest"), dict) else None
    payload = dict(info or {})
    if event.error and "error" not in payload:
        payload["error"] = event.error
    if "ok" not in payload and event.error:
        payload["ok"] = False
    return payload, invocation


def _latest_pytest(
    events: list[HarnessEvent],
) -> tuple[HarnessEvent, dict[str, Any], int, PytestInvocation] | None:
    found: tuple[HarnessEvent, dict[str, Any], int, PytestInvocation] | None = None
    for index, event in enumerate(events):
        evidence = _pytest_info(event)
        if evidence is None:
            continue
        info, invocation = evidence
        found = (event, info, index, invocation)
    return found


def _failed_node(info: dict[str, Any], event: HarnessEvent) -> str | None:
    for key in ("failed", "nodeid", "failed_tests"):
        value = info.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value:
            return str(value[0])
    blob = " ".join(
        str(part) for part in (info.get("output"), info.get("stdout"), event.error) if part
    )
    match = FAILED_NODE.search(blob)
    return match.group(1) if match else None


def _later_edits(events: list[HarnessEvent], after: int) -> list[str]:
    """Describe subsequent edits, retaining events whose path was not reported."""
    paths: list[str] = []
    for event in events[after + 1 :]:
        if event.event_type == EventType.FILE_EDIT:
            # Missing path metadata is not evidence that the workspace stayed
            # unchanged. This descriptive fallback is never used for file I/O.
            paths.extend(event.file_paths or ["a file with an unreported path"])
    return paths


def _expected_rows(goal: Goal | None) -> int | None:
    if goal is None:
        return None
    blob = " ".join([goal.objective, *goal.acceptance_criteria, *goal.evidence_requirements])
    match = ROW_RE.search(blob)
    return _parse_expected_rows(match.group(1)) if match else None


def _parse_expected_rows(value: str) -> int | None:
    if len(value) > 10:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if 0 <= parsed <= MAX_EXPECTED_ROWS else None


def _test_count_requirement(goal: Goal | None) -> _TestCountRequirement:
    """Parse only bounded, explicit test-count constraints from persistent goal text.

    ``absent`` and ``ambiguous`` are intentionally distinct. An unsupported,
    conflicting, negated, historical, ranged, or malformed count must never be
    interpreted as an unconstrained passing suite.
    """

    if goal is None:
        return _TestCountRequirement("absent")
    parsed: list[_TestCountConstraint] = []
    ambiguous = False
    for raw in [goal.objective, *goal.acceptance_criteria, *goal.evidence_requirements]:
        text = str(raw or "")
        valid_spans: list[tuple[int, int]] = []
        for match in _VALID_TEST_COUNT.finditer(text):
            prefix_context = text[max(0, match.start() - 40) : match.start()]
            if _AMBIGUOUS_TEST_COUNT_CONTEXT.search(prefix_context):
                ambiguous = True
                continue
            number = match.group("count")
            try:
                count = int(number.replace(",", ""))
            except (TypeError, ValueError, OverflowError):  # pragma: no cover - regex invariant
                ambiguous = True
                continue
            if count <= 0 or count > MAX_EXPECTED_TESTS:
                ambiguous = True
                continue
            qualifier = str(match.group("prefix") or "").casefold()
            if match.group("or_more") or qualifier in {
                "at least",
                "minimum",
                "minimum of",
                "no fewer than",
            }:
                comparator = "gte"
            elif qualifier in {"more than", "over"}:
                comparator = "gte"
                count += 1
                if count > MAX_EXPECTED_TESTS:
                    ambiguous = True
                    continue
            else:
                comparator = "eq"
            metric = "passed"
            if str(match.group("metric") or "").casefold() == "collected":
                metric = "collected"
            parsed.append(_TestCountConstraint(metric, comparator, count))
            valid_spans.append(match.span())
        for loose in _LOOSE_TEST_COUNT.finditer(text):
            if not any(start <= loose.start() and loose.end() <= end for start, end in valid_spans):
                ambiguous = True
    if ambiguous:
        return _TestCountRequirement("ambiguous")
    if not parsed:
        return _TestCountRequirement("absent")

    merged: list[_TestCountConstraint] = []
    for metric in ("passed", "collected"):
        relevant = [item for item in parsed if item.metric == metric]
        if not relevant:
            continue
        exact = {item.count for item in relevant if item.comparator == "eq"}
        minimum = max(
            (item.count for item in relevant if item.comparator == "gte"),
            default=None,
        )
        if len(exact) > 1:
            return _TestCountRequirement("ambiguous")
        if exact:
            count = next(iter(exact))
            if minimum is not None and count < minimum:
                return _TestCountRequirement("ambiguous")
            merged.append(_TestCountConstraint(metric, "eq", count))
        elif minimum is not None:
            merged.append(_TestCountConstraint(metric, "gte", minimum))
    return _TestCountRequirement("valid", tuple(merged))


def _expected_test_count(goal: Goal | None) -> int | None:
    """Compatibility helper for one unambiguous exact passing-test count."""

    requirement = _test_count_requirement(goal)
    if requirement.status != "valid" or len(requirement.constraints) != 1:
        return None
    constraint = requirement.constraints[0]
    if constraint.metric != "passed" or constraint.comparator != "eq":
        return None
    return constraint.count


def _observed_pytest_count(info: dict[str, Any]) -> int | None:
    value = info.get("passed")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _observed_pytest_metric(info: dict[str, Any], metric: str) -> int | None:
    key = "passed" if metric == "passed" else "collected"
    value = info.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _test_count_violations(
    requirement: _TestCountRequirement,
    info: dict[str, Any],
) -> tuple[list[_TestCountConstraint], list[_TestCountConstraint]]:
    missing: list[_TestCountConstraint] = []
    violated: list[_TestCountConstraint] = []
    for constraint in requirement.constraints:
        observed = _observed_pytest_metric(info, constraint.metric)
        if observed is None:
            missing.append(constraint)
        elif constraint.comparator == "eq" and observed != constraint.count:
            violated.append(constraint)
        elif constraint.comparator == "gte" and observed < constraint.count:
            violated.append(constraint)
    return missing, violated


def _pytest_supports_goal(
    info: dict[str, Any],
    invocation: PytestInvocation,
    *,
    edits: list[str],
    goal: Goal | None,
) -> bool:
    exit_code = info.get("exit_code")
    if (
        info.get("ok") is not True
        or not isinstance(exit_code, int)
        or isinstance(exit_code, bool)
        or exit_code != 0
        or invocation.scope != PytestInvocationScope.FULL_SUITE
        or edits
    ):
        return False
    deselected = info.get("deselected")
    if isinstance(deselected, int) and not isinstance(deselected, bool) and deselected > 0:
        return False
    passed = _observed_pytest_count(info)
    nonpassing_results = sum(
        value
        for key in ("skipped", "xfailed", "xpassed")
        if isinstance((value := info.get(key)), int) and not isinstance(value, bool) and value > 0
    )
    if nonpassing_results > 0 and (passed is None or passed == 0):
        return False
    requirement = _test_count_requirement(goal)
    if requirement.status == "ambiguous":
        return False
    missing, violated = _test_count_violations(requirement, info)
    return not missing and not violated


def _count_rows(text: str, path: str) -> int | None:
    stripped = text.strip()
    if not stripped:
        return 0
    if path.endswith(".jsonl"):
        lines = [line for line in stripped.splitlines() if line.strip()]
        try:
            for line in lines:
                json.loads(
                    line,
                    parse_constant=_reject_nonfinite_json_constant,
                    object_pairs_hook=_unique_json_object,
                )
        except (ValueError, RecursionError):
            return None
        return len(lines)
    try:
        data = json.loads(
            stripped,
            parse_constant=_reject_nonfinite_json_constant,
            object_pairs_hook=_unique_json_object,
        )
    except (ValueError, RecursionError):
        # A generic text preview cannot establish whether a CSV header counts
        # as a row; keep the verdict uncertain rather than overclaiming.
        return None
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("rows", "items", "records", "results", "data"):
            if isinstance(data.get(key), list):
                return len(data[key])
    return None


def _artifact_rows(
    goal: Goal | None,
    workspace: dict[str, Any],
    required_path: str | None = None,
) -> tuple[str | None, int | None]:
    required = (
        [required_path]
        if required_path
        else [
            path
            for path in _required_files(goal)
            if path.casefold().endswith((".json", ".jsonl", ".csv"))
        ]
    )
    if not required:
        return None, None
    wanted = str(required[0]).replace("\\", "/")
    if not _visible_goal_path(wanted):
        return wanted, None
    for item in workspace.get("artifacts") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").replace("\\", "/")
        if path.casefold() != wanted.casefold():
            continue
        if item.get("row_count_complete") is True and isinstance(item.get("row_count"), int):
            return path, int(item["row_count"])
        # Compatibility with externally supplied complete artifact snapshots.
        if item.get("tail_complete") is True:
            return path, _count_rows(str(item.get("tail") or ""), path)
        return path, None
    # The exact required artifact may be nested and therefore absent from the
    # compact root-artifact preview. Read only that goal-declared path.
    root_raw = workspace.get("workspace")
    try:
        root = Path(str(root_raw)).resolve() if root_raw else None
        target = (root / wanted).resolve() if root is not None else None
        if root is None or target is None:
            return wanted, None
        target.relative_to(root)
        if not target.is_file():
            return wanted, None
        if target.suffix.casefold() in {".json", ".jsonl"}:
            count, complete = artifact_row_count(target)
            return wanted, count if complete else None
        if target.stat().st_size > 4_000_000:
            return wanted, None
        return wanted, _count_rows(target.read_text(encoding="utf-8"), wanted)
    except (OSError, UnicodeError, ValueError):
        return wanted, None


def _observed_files(workspace: dict[str, Any]) -> set[str] | None:
    if workspace.get("error") or not workspace.get("workspace"):
        return None
    files = workspace.get("files")
    if not isinstance(files, list):
        return None
    return {str(name).replace("\\", "/").casefold() for name in files}


def _required_files(goal: Goal | None) -> list[str]:
    if goal is None:
        return []
    names: list[str] = []
    for raw in list(goal.evidence_requirements or []) + list(goal.acceptance_criteria or []):
        name = str(raw or "").strip()
        if FILE_TOKEN.fullmatch(name) and _visible_goal_path(name):
            names.append(name.replace("\\", "/"))
            continue
        row_check = _expected_file_rows(name)
        if row_check is not None:
            names.append(row_check[0])
            continue
        content_check = _expected_content(name)
        if content_check is not None:
            names.append(content_check[0])
            continue
        exists_check = _expected_exists(name)
        if exists_check is not None:
            names.append(exists_check)
    return list(dict.fromkeys(names))


def required_files(goal: Goal | None) -> list[str]:
    return _required_files(goal)


def missing_required_files(goal: Goal | None, workspace: dict[str, Any]) -> list[str] | None:
    return _missing_required_files(goal, workspace)


def _missing_required_files(goal: Goal | None, workspace: dict[str, Any]) -> list[str] | None:
    observed = _observed_files(workspace)
    if observed is None:
        return None
    root_raw = workspace.get("workspace")
    try:
        root = Path(str(root_raw)).resolve() if root_raw else None
    except (OSError, ValueError):
        root = None
    missing: list[str] = []
    for name in _required_files(goal):
        if name.casefold() in observed:
            continue
        exists = False
        if root is not None:
            try:
                target = (root / name).resolve()
                target.relative_to(root)
                exists = target.is_file()
            except (OSError, ValueError):
                exists = False
        if not exists:
            missing.append(name)
    return missing


def _tests_pass_verdict(
    claim: dict[str, Any],
    events: list[HarnessEvent],
    goal: Goal | None,
) -> dict[str, Any]:
    latest = _latest_pytest(events)
    if latest is None:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": ["no_pytest_observed"],
            "correction": None,
        }
    event, info, index, invocation = latest
    ok = info.get("ok")
    exit_code = info.get("exit_code")
    valid_exit = isinstance(exit_code, int) and not isinstance(exit_code, bool)
    count_requirement = _test_count_requirement(goal)
    observed_count = _observed_pytest_count(info)
    node = _failed_node(info, event)
    edits = _later_edits(events, index)
    provenance = [
        f"pytest_event_id={event.event_id}",
        f"pytest_scope={invocation.scope.value}",
    ]
    if valid_exit:
        provenance.append(f"pytest_exit_code={exit_code}")
    if observed_count is not None:
        provenance.append(f"pytest_passed={observed_count}")
    for constraint in count_requirement.constraints:
        provenance.append(
            f"pytest_expected_{constraint.metric}_{constraint.comparator}={constraint.count}"
        )
        if constraint.metric == "passed" and constraint.comparator == "eq":
            provenance.append(f"pytest_expected_passed={constraint.count}")
    decisively_failed = (valid_exit and exit_code != 0) or bool(event.error or node)
    if decisively_failed:
        if edits:
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [
                    *provenance,
                    f"pytest_ok={ok}",
                    *([f"failed:{node}"] if node else []),
                    f"later_edit:{edits[-1]}",
                ],
                "correction": None,
                "probe": (
                    f"The latest pytest run failed, then {edits[-1]} changed. "
                    "Observe a new pytest result before deciding whether the claim is true."
                ),
            }
        bits = ["The latest observed pytest run failed"]
        if valid_exit:
            bits.append(f"(exit {exit_code})")
        detail = " ".join(bits) + "."
        if node:
            detail += f" Failing test: {node}."
        detail += " Continue from that failure."
        evidence = [
            *provenance,
            f"pytest_ok={ok}",
            *([f"failed:{node}"] if node else []),
        ]
        return {
            "claim": claim,
            "status": "contradicted",
            "evidence": evidence,
            "correction": f"You said the test suite passes. {detail}",
        }
    if ok is True and edits:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": [*provenance, "pytest_ok=true", f"later_edit:{edits[-1]}"],
            "correction": None,
        }
    if ok is True and (not valid_exit or exit_code != 0):
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": [*provenance, "pytest_terminal_exit_unavailable_or_inconsistent"],
            "correction": None,
            "probe": "Observe a terminal full-suite pytest exit before supporting this claim.",
        }
    if ok is True:
        if invocation.scope != PytestInvocationScope.FULL_SUITE:
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [*provenance, "pytest_ok=true"],
                "correction": None,
                "probe": "Observe a full-suite pytest result before supporting this claim.",
            }
        if count_requirement.status == "ambiguous":
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [*provenance, "pytest_count_requirement_ambiguous"],
                "correction": None,
                "probe": (
                    "Clarify the conflicting, unsupported, or malformed test-count "
                    "requirement before deciding whether the suite satisfies the goal."
                ),
            }
        missing_counts, violated_counts = _test_count_violations(count_requirement, info)
        if missing_counts:
            labels = ", ".join(
                f"{item.metric} {item.comparator} {item.count}" for item in missing_counts
            )
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [*provenance, "pytest_required_count_unavailable"],
                "correction": None,
                "probe": (
                    "Observe a terminal full-suite pytest result containing the required "
                    f"count evidence ({labels}) before supporting this claim."
                ),
            }
        if violated_counts:
            required = ", ".join(
                (
                    f"{item.count} passing tests"
                    if item.metric == "passed" and item.comparator == "eq"
                    else f"exactly {item.count} collected tests"
                    if item.comparator == "eq"
                    else f"at least {item.count} {item.metric} tests"
                )
                for item in violated_counts
            )
            observed = ", ".join(
                f"{item.metric}={_observed_pytest_metric(info, item.metric)}"
                for item in violated_counts
            )
            return {
                "claim": claim,
                "status": "contradicted",
                "evidence": provenance,
                "correction": (
                    "You said the test suite passes, but the persistent goal requires "
                    f"{required} and the latest full-suite run observed {observed}. "
                    "Verify collection and satisfy the declared test count."
                ),
            }
        if not _pytest_supports_goal(info, invocation, edits=edits, goal=goal):
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [*provenance, "pytest_evidence_inconsistent"],
                "correction": None,
            }
        return {
            "claim": claim,
            "status": "supported",
            "evidence": [*provenance, "pytest_ok=true"],
            "correction": None,
        }
    return {
        "claim": claim,
        "status": "uncertain",
        "evidence": [*provenance, "pytest_observed_without_exit"],
        "correction": None,
    }


def _evaluation_verdict(
    claim: dict[str, Any],
    goal: Goal | None,
    workspace: dict[str, Any],
) -> dict[str, Any]:
    expected = _expected_rows(goal)
    files = _observed_files(workspace)
    if expected is None:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": ["no_row_requirement"],
            "correction": None,
        }
    if files is None:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": ["workspace_unobserved"],
            "correction": None,
        }
    path, count = _artifact_rows(goal, workspace)
    if path is None:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": [f"expected_rows={expected}", "no_declared_row_artifact"],
            "correction": None,
        }
    if count is None:
        missing = _missing_required_files(goal, workspace)
        if missing is None:
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [f"expected_rows={expected}", f"row_count_unavailable:{path}"],
                "correction": None,
            }
        if path.casefold() not in {item.casefold() for item in missing}:
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [f"expected_rows={expected}", f"row_count_unavailable:{path}"],
                "correction": None,
            }
        return {
            "claim": claim,
            "status": "contradicted",
            "evidence": [f"expected_rows={expected}", f"missing:{path}"],
            "correction": (
                f"You marked the evaluation complete, but acceptance requires {expected} rows. "
                f"{path} is missing from the workspace. Produce the full "
                "evaluation file before stopping."
            ),
        }
    if count < expected:
        return {
            "claim": claim,
            "status": "contradicted",
            "evidence": [f"expected_rows={expected}", f"{path}_rows={count}"],
            "correction": (
                f"You marked the task complete, but acceptance requires {expected} "
                f"evaluation rows. {path} currently contains {count}. Resume the "
                "evaluation and verify the final row count before stopping."
            ),
        }
    return {
        "claim": claim,
        "status": "supported",
        "evidence": [f"{path}_rows={count}"],
        "correction": None,
    }


def _missing_file_verdict(
    claim: dict[str, Any] | None,
    goal: Goal | None,
    workspace: dict[str, Any],
) -> dict[str, Any] | None:
    missing = _missing_required_files(goal, workspace)
    if missing is None:
        return None
    if not missing:
        return None
    name = missing[0]
    return {
        "claim": claim,
        "status": "unsatisfied" if claim is None else "contradicted",
        "basis": "acceptance_criterion" if claim is None else "worker_claim",
        "evidence": [f"missing:{item}" for item in missing],
        "correction": (
            f"{name} is missing from the workspace. Complete the attached objective "
            "and verify this required artifact before stopping."
        ),
    }


def _expected_content(raw: str) -> tuple[str, str] | None:
    match = FILE_CONTAINS.search(raw.strip())
    if match is None:
        return None
    expected = match.group("expected").strip().strip("`\"'")
    expected = re.sub(r"^exactly\s+", "", expected, flags=re.I)
    expected = re.sub(r"^the\s+word\s+", "", expected, flags=re.I)
    expected = expected.strip().strip("`\"'")
    if not expected:
        return None
    path = match.group("path").replace("\\", "/")
    return (path, expected) if _visible_goal_path(path) else None


def _expected_file_rows(raw: str) -> tuple[str, int] | None:
    match = FILE_ROWS.search(raw.strip())
    if match is None:
        return None
    path = match.group("path").replace("\\", "/")
    count = _parse_expected_rows(match.group("count"))
    return (path, count) if count is not None and _visible_goal_path(path) else None


def _expected_exists(raw: str) -> str | None:
    match = FILE_EXISTS.search(raw.strip())
    if match is None:
        return None
    path = match.group("path").replace("\\", "/")
    return path if _visible_goal_path(path) else None


def _read_goal_file(
    workspace: dict[str, Any],
    relpath: str,
    limit: int = 4_000_000,
) -> tuple[str, bool] | None:
    root_raw = workspace.get("workspace")
    if not root_raw or not _visible_goal_path(relpath):
        return None
    try:
        root = Path(str(root_raw)).resolve()
        target = (root / relpath).resolve()
        target.relative_to(root)
        if not target.is_file():
            return None
        for attempt in range(10):
            try:
                with target.open("rb") as handle:
                    data = handle.read(limit + 1)
                complete = len(data) <= limit
                return data[:limit].decode("utf-8", "replace"), complete
            except PermissionError:
                if attempt == 9:
                    return None
                # Some Windows harness commands release their final file handle
                # just after the turn-completed event. Bound the settle window.
                time.sleep(0.05)
        return None
    except (OSError, ValueError):
        return None


def _goal_file_verdict(
    claim: dict[str, Any] | None,
    goal: Goal | None,
    workspace: dict[str, Any],
) -> dict[str, Any]:
    if goal is None:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": ["goal_unattached"],
            "correction": None,
        }
    missing_verdict = _missing_file_verdict(claim, goal, workspace)
    if missing_verdict is not None:
        return missing_verdict
    required = _required_files(goal)
    if not required:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": ["no_file_acceptance_requirement"],
            "correction": None,
        }

    evidence = [f"exists:{name}" for name in required]
    unresolved: list[str] = []
    checks: list[tuple[str, str]] = []
    row_checks: list[tuple[str, int]] = []
    for raw in goal.acceptance_criteria:
        criterion = str(raw or "").strip()
        if not criterion:
            continue
        if FILE_TOKEN.fullmatch(criterion):
            continue
        row_check = _expected_file_rows(criterion)
        content_check = _expected_content(criterion)
        if row_check is not None:
            row_checks.append(row_check)
        elif content_check is not None:
            checks.append(content_check)
        else:
            unresolved.append(criterion)
    for raw in goal.evidence_requirements:
        requirement = str(raw or "").strip()
        if requirement and not FILE_TOKEN.fullmatch(requirement):
            unresolved.append(requirement)

    for path, expected in checks:
        observed_content = _read_goal_file(workspace, path)
        if observed_content is None:
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [f"temporarily_unreadable:{path}"],
                "correction": None,
                "probe": f"Retry a bounded read of {path} before deciding completion.",
            }
        content, complete = observed_content
        if expected not in content:
            if not complete:
                return {
                    "claim": claim,
                    "status": "uncertain",
                    "evidence": [f"content_check_incomplete:{path}"],
                    "correction": None,
                    "probe": (
                        f"{path} exceeds the bounded content verifier. Observe an exact "
                        "targeted check before deciding completion."
                    ),
                }
            return {
                "claim": claim,
                "status": "unsatisfied" if claim is None else "contradicted",
                "basis": "acceptance_criterion" if claim is None else "worker_claim",
                "evidence": [f"content_missing:{path}:{expected}"],
                "correction": (
                    f"{path} exists but does not contain {expected!r}. "
                    "Correct the file and verify it before stopping."
                ),
            }
        evidence.append(f"contains:{path}:{expected}")
    for path, expected_rows in row_checks:
        _, count = _artifact_rows(goal, workspace, path)
        if count is None:
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [f"row_count_unavailable:{path}"],
                "correction": None,
                "probe": f"Observe a complete row count for {path} before deciding completion.",
            }
        if count < expected_rows:
            return {
                "claim": claim,
                "status": "unsatisfied" if claim is None else "contradicted",
                "basis": "acceptance_criterion" if claim is None else "worker_claim",
                "evidence": [f"expected_rows={expected_rows}", f"{path}_rows={count}"],
                "correction": (
                    f"{path} contains {count} rows; acceptance requires {expected_rows}. "
                    "Complete the artifact and verify its final row count before stopping."
                ),
            }
        evidence.append(f"{path}_rows={count}")
    if unresolved:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": [*evidence, *(f"unchecked:{item}" for item in unresolved)],
            "correction": None,
        }
    return {
        "claim": claim,
        "status": "supported",
        "evidence": evidence,
        "correction": None,
    }


def _effective_verdicts(verdicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ignore only redundant, uncheckable generic completion in the same event.

    A verified specific claim such as ``tests_pass`` is not weakened by the
    worker appending "I am done" to that same response. Contradictions and
    acceptance gaps are never ignored, and generic completion on its own stays
    uncertain.
    """
    supported_sources = {
        str(claim.get("source_event_id"))
        for verdict in verdicts
        if verdict.get("status") == "supported"
        and isinstance((claim := verdict.get("claim")), dict)
        and claim.get("kind") in _SPECIFIC_COMPLETION_KINDS
        and claim.get("source_event_id")
    }
    effective: list[dict[str, Any]] = []
    for verdict in verdicts:
        claim = verdict.get("claim")
        is_redundant_generic = (
            verdict.get("status") == "uncertain"
            and isinstance(claim, dict)
            and claim.get("kind") == "complete"
            and bool(_GENERIC_DONE.search(str(claim.get("statement") or "")))
            and str(claim.get("source_event_id") or "") in supported_sources
        )
        if not is_redundant_generic:
            effective.append(verdict)
    return effective


def _unfinished_pytest_verdict(
    events: list[HarnessEvent], goal: Goal | None
) -> dict[str, Any] | None:
    """A STOP with a still-failing pytest is unfinished work, even without a tests-pass claim."""
    latest = _latest_pytest(events)
    if latest is None:
        return None
    event, info, index, invocation = latest
    ok = info.get("ok")
    node = _failed_node(info, event)
    if _later_edits(events, index):
        return None
    if ok is False or (ok is None and (event.error or node)):
        bits = ["The latest observed pytest run failed"]
        if info.get("exit_code") not in (None, ""):
            bits.append(f"(exit {info.get('exit_code')})")
        detail = " ".join(bits) + "."
        if node:
            detail += f" Failing test: {node}."
        detail += " Continue from that failure."
        return {
            "claim": None,
            "status": "unsatisfied",
            "basis": "acceptance_criterion",
            "evidence": [
                f"pytest_event_id={event.event_id}",
                f"pytest_scope={invocation.scope.value}",
                f"pytest_ok={ok}",
                *([f"failed:{node}"] if node else []),
            ],
            "correction": detail,
        }
    exit_code = info.get("exit_code")
    if (
        ok is not True
        or not isinstance(exit_code, int)
        or isinstance(exit_code, bool)
        or exit_code != 0
        or invocation.scope != PytestInvocationScope.FULL_SUITE
    ):
        return None
    requirement = _test_count_requirement(goal)
    if requirement.status != "valid":
        return None
    _missing, violated = _test_count_violations(requirement, info)
    if not violated:
        return None
    expected = ", ".join(
        f"{item.metric} {item.comparator} {item.count}" for item in violated
    )
    observed = ", ".join(
        f"{item.metric}={_observed_pytest_metric(info, item.metric)}" for item in violated
    )
    return {
        "claim": None,
        "status": "unsatisfied",
        "basis": "acceptance_criterion",
        "evidence": [
            f"pytest_event_id={event.event_id}",
            f"pytest_scope={invocation.scope.value}",
            f"pytest_count_requirement={expected}",
            f"pytest_observed_counts={observed}",
        ],
        "correction": (
            "The latest full-suite pytest run exited successfully but did not satisfy "
            f"the persistent test-count requirement ({expected}; observed {observed}). "
            "Restore the missing collection or tests and run the full suite again."
        ),
    }


def _goal_requirement_text(goal: Goal | None) -> str:
    if goal is None:
        return ""
    return " ".join(
        [goal.objective, *goal.acceptance_criteria, *goal.evidence_requirements]
    )


def _command_exit_targets(goal: Goal | None) -> list[str]:
    names: list[str] = []
    sources = [
        *(goal.evidence_requirements if goal else ()),
        *(goal.acceptance_criteria if goal else ()),
    ]
    for raw in sources:
        for match in _COMMAND_EXIT_REQUIREMENT.finditer(str(raw or "")):
            path = match.group("path").replace("\\", "/")
            if (
                FILE_TOKEN.fullmatch(path)
                or path.endswith((".sh", ".ps1", ".js", ".mjs", ".py"))
            ) and _visible_goal_path(path):
                names.append(path)
    return list(dict.fromkeys(names))


def _artifact_tail_targets(goal: Goal | None) -> list[str]:
    names: list[str] = []
    if goal is None:
        return names
    for raw in list(goal.acceptance_criteria or []) + list(goal.evidence_requirements or []):
        row_check = _expected_file_rows(str(raw or ""))
        if row_check is not None:
            names.append(row_check[0])
            continue
        content_check = _expected_content(str(raw or ""))
        if content_check is not None:
            names.append(content_check[0])
    return list(dict.fromkeys(names))


def verification_probe_targets(
    kind: VerificationProbeKind | None,
    goal: Goal | None,
) -> tuple[str, ...]:
    """Select contained relative targets for a bridge-minted probe."""

    if kind == VerificationProbeKind.FILE_COUNT:
        return tuple(_required_files(goal)[:256])
    if kind == VerificationProbeKind.ARTIFACT_TAIL:
        return tuple(_artifact_tail_targets(goal)[:256])
    if kind == VerificationProbeKind.COMMAND_EXIT:
        return tuple(_command_exit_targets(goal)[:256])
    return ()


def required_verification_probe_kind(
    claims: list[dict[str, Any]],
    events: list[HarnessEvent],
    goal: Goal | None,
    verification: dict[str, Any],
) -> VerificationProbeKind | None:
    """Select a closed probe only when missing evidence can answer the uncertainty."""

    if verification.get("status") not in {"uncertain", "no_claims"}:
        return None
    claims_require_pytest = any(
        item.get("polarity") != "denied" and item.get("kind") == "tests_pass"
        for item in claims
    )
    goal_requires_pytest = _PYTEST_REQUIREMENT.search(_goal_requirement_text(goal)) is not None
    if claims_require_pytest or goal_requires_pytest:
        if _test_count_requirement(goal).status == "ambiguous":
            # Another pytest run cannot resolve contradictory or unsupported goal
            # language; require semantic/human clarification instead of looping.
            return None
        latest = _latest_pytest(events)
        if latest is None:
            return VerificationProbeKind.PYTEST
        _event, info, index, invocation = latest
        edits = _later_edits(events, index)
        if _pytest_supports_goal(info, invocation, edits=edits, goal=goal):
            return None
        return VerificationProbeKind.PYTEST

    evidence = [
        str(item)
        for verdict in verification.get("verdicts") or []
        if isinstance(verdict, dict)
        for item in verdict.get("evidence") or []
    ]
    if any(
        item.startswith("row_count_unavailable:")
        or item.startswith("content_check_incomplete:")
        for item in evidence
    ) and _artifact_tail_targets(goal):
        return VerificationProbeKind.ARTIFACT_TAIL
    if any(item.startswith("temporarily_unreadable:") for item in evidence) and _required_files(
        goal
    ):
        return VerificationProbeKind.FILE_COUNT
    if _SERVICE_HEALTH_REQUIREMENT.search(_goal_requirement_text(goal)):
        return VerificationProbeKind.SERVICE_HEALTH
    if any(item == "no_external_check" for item in evidence) and _command_exit_targets(goal):
        return VerificationProbeKind.COMMAND_EXIT
    return None


def verify_claims(
    claims: list[dict[str, Any]],
    events: list[HarnessEvent],
    goal: Goal | None,
    workspace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace = workspace or {}
    asserted = [item for item in claims if item.get("polarity") != "denied"]
    verdicts: list[dict[str, Any]] = []
    for claim in asserted:
        kind = str(claim.get("kind") or "")
        if kind == "tests_pass":
            verdicts.append(_tests_pass_verdict(claim, events, goal))
        elif kind in {"evaluation_complete", "complete"}:
            eval_verdict = _evaluation_verdict(claim, goal, workspace)
            verdicts.append(
                _goal_file_verdict(claim, goal, workspace)
                if eval_verdict["status"] == "uncertain"
                else eval_verdict
            )
        elif kind in _COMPLETION_KINDS:
            file_verdict = _missing_file_verdict(claim, goal, workspace)
            verdicts.append(
                file_verdict
                or {
                    "claim": claim,
                    "status": "uncertain",
                    "evidence": ["no_external_check"],
                    "correction": None,
                }
            )
    acceptance_gap = _goal_file_verdict(None, goal, workspace)
    acceptance_status = acceptance_gap.get("status")
    if acceptance_gap.get("status") == "supported":
        acceptance_gap = None
    if (
        acceptance_gap
        and acceptance_gap.get("status") != "uncertain"
        and not any(
            set(item.get("evidence") or []) & set(acceptance_gap.get("evidence") or [])
            for item in verdicts
        )
    ):
        verdicts.append(acceptance_gap)
    pytest_gap = _unfinished_pytest_verdict(events, goal)
    if pytest_gap and not any(
        str(item).startswith("pytest_ok=")
        for verdict in verdicts
        for item in (verdict.get("evidence") or [])
    ):
        verdicts.append(pytest_gap)
    contradicted = [item for item in verdicts if item["status"] == "contradicted"]
    unsatisfied = [item for item in verdicts if item["status"] == "unsatisfied"]
    effective = _effective_verdicts(verdicts)
    supported = [item for item in effective if item["status"] == "supported"]
    if contradicted:
        status = "contradicted"
    elif unsatisfied:
        status = "acceptance_gap"
    elif asserted and supported and len(supported) == len(effective):
        status = "supported"
    elif not asserted:
        status = "no_claims"
    else:
        status = "uncertain"
    chosen = contradicted[0] if contradicted else unsatisfied[0] if unsatisfied else None
    latest_pytest = _latest_pytest(events)
    pytest_provenance = (
        None
        if latest_pytest is None
        else {
            "event_id": latest_pytest[0].event_id,
            "scope": latest_pytest[3].scope.value,
        }
    )
    # Observed command facts remain useful even when claim extraction yields no
    # tests_pass claim. Do not conflate these facts with goal acceptance or an
    # independently executed check, and never include arbitrary output text.
    pytest_observation = None
    if latest_pytest is not None:
        pytest_event, pytest_info, pytest_index, invocation = latest_pytest
        pytest_observation = {
            "event_id": pytest_event.event_id,
            "scope": invocation.scope.value,
            "basis": "observed_worker_command",
            "later_file_edits_observed": any(
                item.event_type == EventType.FILE_EDIT for item in events[pytest_index + 1 :]
            ),
            "ok": pytest_info.get("ok") if type(pytest_info.get("ok")) is bool else None,
            "exit_code": (
                pytest_info.get("exit_code")
                if type(pytest_info.get("exit_code")) is int else None
            ),
        }
        for metric in ("passed", "failed_count", "skipped", "errors", "collected"):
            value = pytest_info.get(metric)
            if type(value) is int and 0 <= value <= 2**53 - 1:
                pytest_observation[metric] = value
    return {
        "status": status,
        "acceptance_status": acceptance_status,
        "verdicts": verdicts,
        "correction": None if chosen is None else chosen.get("correction"),
        "evidence": [] if chosen is None else list(chosen.get("evidence") or []),
        "pytest_event_id": None if latest_pytest is None else latest_pytest[0].event_id,
        "pytest_scope": None if latest_pytest is None else latest_pytest[3].scope.value,
        "latest_pytest": pytest_provenance,
        "pytest_observation": pytest_observation,
        "missing_files": [
            item[8:]
            for item in (chosen.get("evidence") or [] if chosen else [])
            if str(item).startswith("missing:")
        ],
    }
