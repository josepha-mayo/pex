"""Check extracted worker claims against observed events and workspace state.

A STOP with no contradicting evidence stays uncertain. Uncertain is silence.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pex_protocol.enums import EventType
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent

FILE_TOKEN = re.compile(r"^[A-Za-z0-9._-]{1,72}\.[A-Za-z0-9]{1,8}$")
ROW_RE = re.compile(r"(\d+)\s+rows", re.I)
FAILED_NODE = re.compile(r"FAILED\s+(\S+)")
_COMPLETION_KINDS = {"tests_pass", "evaluation_complete", "deployment_complete", "complete"}


def _pytest_info(event: HarnessEvent) -> dict[str, Any] | None:
    state = event.process_state if isinstance(event.process_state, dict) else {}
    info = state.get("pytest") if isinstance(state.get("pytest"), dict) else None
    command = (event.command or "").lower()
    if info is None and "pytest" not in command and event.event_type not in {EventType.SHELL, EventType.TOOL_RESULT}:
        return None
    if info is None and "pytest" not in command:
        return None
    payload = dict(info or {})
    if event.error and "error" not in payload:
        payload["error"] = event.error
    if "ok" not in payload and event.error:
        payload["ok"] = False
    return payload


def _latest_pytest(events: list[HarnessEvent]) -> tuple[HarnessEvent, dict[str, Any], int] | None:
    found: tuple[HarnessEvent, dict[str, Any], int] | None = None
    for index, event in enumerate(events):
        info = _pytest_info(event)
        if info is None:
            continue
        found = (event, info, index)
    return found


def _failed_node(info: dict[str, Any], event: HarnessEvent) -> str | None:
    for key in ("failed", "nodeid", "failed_tests"):
        value = info.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value:
            return str(value[0])
    blob = " ".join(str(part) for part in (info.get("output"), info.get("stdout"), event.error) if part)
    match = FAILED_NODE.search(blob)
    return match.group(1) if match else None


def _later_edits(events: list[HarnessEvent], after: int) -> list[str]:
    paths: list[str] = []
    for event in events[after + 1 :]:
        if event.event_type == EventType.FILE_EDIT:
            paths.extend(event.file_paths or [])
    return paths


def _expected_rows(goal: Goal | None) -> int | None:
    if goal is None:
        return None
    blob = " ".join(
        [goal.objective, *goal.acceptance_criteria, *goal.evidence_requirements]
    )
    match = ROW_RE.search(blob)
    return int(match.group(1)) if match else None


def _count_rows(text: str, path: str) -> int | None:
    stripped = text.strip()
    if not stripped:
        return 0
    if path.endswith(".jsonl"):
        return len([line for line in stripped.splitlines() if line.strip()])
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return len([line for line in stripped.splitlines() if line.strip()]) or None
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("rows", "items", "records", "results", "data"):
            if isinstance(data.get(key), list):
                return len(data[key])
    return None


def _artifact_rows(workspace: dict[str, Any]) -> tuple[str | None, int | None]:
    for item in workspace.get("artifacts") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        if not path:
            continue
        lowered = path.lower()
        if not lowered.endswith((".json", ".jsonl")):
            continue
        count = _count_rows(str(item.get("tail") or ""), path)
        return path, count
    return None, None


def _observed_files(workspace: dict[str, Any]) -> set[str] | None:
    if workspace.get("error") or not workspace.get("workspace"):
        return None
    files = workspace.get("files")
    if not isinstance(files, list):
        return None
    return {str(name).replace("\\", "/") for name in files}


def _required_files(goal: Goal | None) -> list[str]:
    if goal is None:
        return []
    names: list[str] = []
    for raw in list(goal.evidence_requirements or []) + list(goal.acceptance_criteria or []):
        name = str(raw or "").strip()
        if FILE_TOKEN.fullmatch(name):
            names.append(name)
    return names


def _tests_pass_verdict(
    claim: dict[str, Any],
    events: list[HarnessEvent],
) -> dict[str, Any]:
    latest = _latest_pytest(events)
    if latest is None:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": ["no_pytest_observed"],
            "correction": None,
        }
    event, info, index = latest
    ok = info.get("ok")
    node = _failed_node(info, event)
    edits = _later_edits(events, index)
    if ok is False or (ok is None and (event.error or node)):
        last_edit = edits[-1] if edits else (event.file_paths[0] if event.file_paths else None)
        bits = ["The latest observed pytest run failed"]
        if info.get("exit_code") not in (None, ""):
            bits.append(f"(exit {info.get('exit_code')})")
        if last_edit:
            bits.append(f"after the edit to {last_edit}")
        detail = " ".join(bits) + "."
        if node:
            detail += f" Failing test: {node}."
        detail += " Continue from that failure."
        evidence = [f"pytest_ok={ok}", *( [f"failed:{node}"] if node else [] ), *( [f"edit:{last_edit}"] if last_edit else [] )]
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
            "evidence": [f"pytest_ok=true", f"later_edit:{edits[-1]}"],
            "correction": None,
        }
    if ok is True:
        return {
            "claim": claim,
            "status": "supported",
            "evidence": ["pytest_ok=true"],
            "correction": None,
        }
    return {
        "claim": claim,
        "status": "uncertain",
        "evidence": ["pytest_observed_without_exit"],
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
    path, count = _artifact_rows(workspace)
    if path is None or count is None:
        return {
            "claim": claim,
            "status": "contradicted",
            "evidence": [f"expected_rows={expected}", "artifact_missing"],
            "correction": (
                f"You marked the evaluation complete, but acceptance requires {expected} rows. "
                "results.jsonl is missing from the workspace. Produce the full evaluation file before stopping."
            ),
        }
    if count < expected:
        return {
            "claim": claim,
            "status": "contradicted",
            "evidence": [f"expected_rows={expected}", f"{path}_rows={count}"],
            "correction": (
                f"You marked the task complete, but acceptance requires {expected} evaluation rows. "
                f"{path} currently contains {count}. Resume the evaluation and verify the final row count before stopping."
            ),
        }
    return {
        "claim": claim,
        "status": "supported",
        "evidence": [f"{path}_rows={count}"],
        "correction": None,
    }


def _missing_file_verdict(
    claim: dict[str, Any],
    goal: Goal | None,
    workspace: dict[str, Any],
) -> dict[str, Any] | None:
    files = _observed_files(workspace)
    if files is None:
        return None
    missing = [name for name in _required_files(goal) if name not in files]
    if not missing:
        return None
    name = missing[0]
    return {
        "claim": claim,
        "status": "contradicted",
        "evidence": [f"missing:{item}" for item in missing],
        "correction": (
            f"{name} is missing from the workspace. "
            f"{(goal.objective if goal else '') or f'Create {name}.'}".strip()
        ),
    }


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
            verdicts.append(_tests_pass_verdict(claim, events))
        elif kind in {"evaluation_complete", "complete"}:
            eval_verdict = _evaluation_verdict(claim, goal, workspace)
            if eval_verdict["status"] == "uncertain":
                file_verdict = _missing_file_verdict(claim, goal, workspace)
                verdicts.append(file_verdict or eval_verdict)
            else:
                verdicts.append(eval_verdict)
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
    contradicted = [item for item in verdicts if item["status"] == "contradicted"]
    supported = [item for item in verdicts if item["status"] == "supported"]
    if contradicted:
        status = "contradicted"
    elif asserted and supported and len(supported) == len(verdicts):
        status = "supported"
    elif not asserted:
        status = "no_claims"
    else:
        status = "uncertain"
    chosen = contradicted[0] if contradicted else None
    return {
        "status": status,
        "verdicts": verdicts,
        "correction": None if chosen is None else chosen.get("correction"),
        "evidence": [] if chosen is None else list(chosen.get("evidence") or []),
        "missing_files": [
            item[8:]
            for item in (chosen.get("evidence") or [] if chosen else [])
            if str(item).startswith("missing:")
        ],
    }
