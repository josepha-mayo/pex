"""Bounded, request-scoped evidence tools for the Strands supervisor.

These tools never read the filesystem, execute code, call a harness, or mutate
PEX state. The bridge gathers and redacts evidence before inference; a fresh
tool set exposes only that immutable request snapshot to one fresh Agent.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import MutableSequence
from pathlib import Path
from typing import Any

from pex_protocol.redaction import redact_mapping
from pex_protocol.session import HarnessEvent
from pex_protocol.supervisor import SupervisorRequest
from strands import tool

_TOOL_JSON_LIMIT = 8_000
_SCORE_FEATURES = {
    "event_count",
    "repeated_command_count",
    "repeated_tool_count",
    "unique_tool_count",
    "tool_count",
    "file_touch_count",
    "error_count",
    "identical_error_count",
    "stops",
    "tests_run",
    "success_claims",
    "edits",
    "span_seconds",
    "pytest_failed",
}


def _clip(value: object, limit: int) -> str:
    return str(value or "").encode("utf-8", "replace").decode("utf-8")[:limit]


def _bounded(value: object, *, depth: int = 0) -> object:
    if depth >= 5:
        return "[truncated]"
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return min((1 << 63) - 1, max(-(1 << 63), value))
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return _clip(value, 1_200)
    if isinstance(value, dict):
        return {
            _clip(key, 80): _bounded(item, depth=depth + 1)
            for key, item in list(value.items())[:40]
        }
    if isinstance(value, (list, tuple)):
        return [_bounded(item, depth=depth + 1) for item in list(value)[:40]]
    return _clip(value, 300)


def _safe_relpath(path: str) -> str | None:
    rel = _clip(path, 240).replace("\\", "/").strip()
    if not rel or rel.startswith("/") or rel.startswith("\\") or ":" in rel[:3]:
        return None
    parts = [item for item in rel.split("/") if item and item != "."]
    if not parts or any(item == ".." for item in parts):
        return None
    return "/".join(parts)


def _tool_json(value: object) -> str:
    rendered = json.dumps(
        _bounded(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    if len(rendered) <= _TOOL_JSON_LIMIT:
        return rendered
    return json.dumps(
        {"truncated": True, "preview": rendered[: _TOOL_JSON_LIMIT - 80]},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _mask_local_strings(value: object, local_values: tuple[str, ...]) -> object:
    if isinstance(value, str):
        rendered = value
        for local in sorted(local_values, key=len, reverse=True):
            for variant in {local, local.replace("\\", "/"), local.replace("/", "\\")}:
                rendered = re.sub(
                    re.escape(variant),
                    "<workspace>",
                    rendered,
                    flags=re.IGNORECASE,
                )
        return rendered
    if isinstance(value, dict):
        return {
            _mask_local_strings(key, local_values): _mask_local_strings(item, local_values)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_mask_local_strings(item, local_values) for item in value]
    return value


def _event_view(event: HarnessEvent) -> dict[str, Any]:
    return {
        "event_id": _clip(event.event_id, 200),
        "ts": event.ts.isoformat(),
        "event_type": event.event_type.value,
        "phase": event.phase.value,
        "message": _clip(event.message_delta, 800) or None,
        "command": _clip(event.command, 500) or None,
        "tool_name": _clip(event.tool_name, 120) or None,
        "file_paths": [_clip(path, 300) for path in event.file_paths[:20]],
        "error": _clip(event.error, 500) or None,
        "cost": event.cost,
    }


def build_evidence_tools(
    request: SupervisorRequest,
    used_tools: MutableSequence[str],
) -> list[object]:
    """Build fresh zero-side-effect tools bound to one validated request."""

    local_values = tuple(
        value
        for value in (
            request.session.cwd,
            request.session.repo,
            request.session.external_url,
        )
        if value
    )

    def record(name: str, value: object) -> str:
        used_tools.append(name)
        # Bound depth/count/width before any recursive masking or redaction so a
        # malformed internal Any value cannot overflow the evidence tool.
        masked = _mask_local_strings(_bounded(value), local_values)
        cleaned, _ = redact_mapping({"evidence": masked})
        return _tool_json((cleaned or {}).get("evidence"))

    @tool(
        name="get_goal",
        description="Return the persistent goal and explicit acceptance contract for this session.",
    )
    def get_goal() -> str:
        goal = request.goal
        if goal is None:
            return record("get_goal", {"attached": False})
        return record(
            "get_goal",
            {
                "attached": True,
                "id": _clip(goal.id, 200),
                "title": _clip(goal.title, 500),
                "objective": _clip(goal.objective, 4_000),
                "acceptance_criteria": [
                    _clip(item, 1_000) for item in goal.acceptance_criteria[:40]
                ],
                "constraints": [_clip(item, 1_000) for item in goal.constraints[:40]],
                "forbidden_outcomes": [
                    _clip(item, 1_000) for item in goal.forbidden_outcomes[:40]
                ],
                "non_goals": [_clip(item, 1_000) for item in goal.non_goals[:40]],
                "evidence_requirements": [
                    _clip(item, 1_000) for item in goal.evidence_requirements[:40]
                ],
                "paused": goal.paused,
            },
        )

    @tool(
        name="get_session_state",
        description="Return the normalized session status and negotiated capability flags.",
    )
    def get_session_state() -> str:
        session = request.session
        return record(
            "get_session_state",
            {
                "id": _clip(session.id, 200),
                "harness_type": session.harness_type.value,
                "goal_id": _clip(session.goal_id, 200) or None,
                "status": session.status.value,
                "context_health": session.context_health,
                "last_activity": (
                    session.last_activity.isoformat() if session.last_activity else None
                ),
                "supervision_paused": session.supervision_paused,
                "capabilities": {
                    _clip(key, 80): value
                    for key, value in list(session.capabilities.items())[:50]
                    if isinstance(value, (bool, int, float))
                },
            },
        )

    @tool(
        name="get_recent_events",
        description="Return the latest normalized observable worker events, oldest to newest.",
    )
    def get_recent_events() -> str:
        return record(
            "get_recent_events",
            [_event_view(event) for event in request.recent_events[-16:]],
        )

    @tool(
        name="get_scores",
        description="Return deterministic trajectory scores and their bounded feature receipts.",
    )
    def get_scores() -> str:
        scores = request.scores
        return record(
            "get_scores",
            {
                "drift": scores.drift,
                "stagnation": scores.stagnation,
                "premature_completion": scores.premature_completion,
                "claim_contradiction": scores.claim_contradiction,
                "features": {
                    key: value
                    for key, value in scores.features.items()
                    if key in _SCORE_FEATURES and isinstance(value, (bool, int, float))
                },
            },
        )

    @tool(
        name="get_context",
        description=(
            "Return an index of inspectable evidence. Query inspect_workspace, inspect_git, "
            "inspect_file, inspect_artifact, inspect_process, run_verification, web_search, "
            "and scrape_url for state."
        ),
    )
    def get_context() -> str:
        features = request.scores.features or {}
        workspace = features.get("prefetched_evidence") or {}
        return record(
            "get_context",
            {
                "query": [
                    "inspect_workspace",
                    "inspect_git",
                    "inspect_file",
                    "inspect_artifact",
                    "inspect_process",
                    "run_verification",
                    "web_search",
                    "scrape_url",
                ],
                "claims_present": bool(features.get("claims")),
                "verification_present": bool(features.get("verification")),
                "workspace_prefetched": bool(workspace),
            },
        )

    @tool(
        name="inspect_workspace",
        description="Inspect the observed file inventory for this worker workspace.",
    )
    def inspect_workspace() -> str:
        features = request.scores.features or {}
        workspace = features.get("prefetched_evidence")
        if isinstance(workspace, dict) and workspace:
            return record("inspect_workspace", workspace)
        cwd = request.session.cwd
        if not cwd:
            return record("inspect_workspace", {"observed": False, "reason": "cwd unavailable"})
        from pex_supervisor.workspace import snapshot

        raw = snapshot(cwd, run_pytest=False)
        return record(
            "inspect_workspace",
            {
                "observed": not bool(raw.get("error")),
                "error": raw.get("error"),
                "files": list(raw.get("files") or [])[:80],
                "files_truncated": bool(raw.get("files_truncated")),
                "pytest": raw.get("pytest"),
            },
        )

    @tool(
        name="inspect_git",
        description="Inspect observed git status and a bounded diff for this workspace.",
    )
    def inspect_git() -> str:
        cwd = request.session.cwd
        if cwd:
            from pex_supervisor.workspace import git_snapshot

            raw = git_snapshot(Path(cwd))
            return record(
                "inspect_git",
                {
                    "available": raw.get("available"),
                    "error": raw.get("error"),
                    "status": _clip(raw.get("status"), 1_500),
                    "diff_stat": _clip(raw.get("diff_stat"), 1_500),
                    "diff": _clip(raw.get("diff"), 2_500),
                },
            )
        git = ((request.scores.features or {}).get("prefetched_evidence") or {}).get("git")
        return record("inspect_git", git or {"available": False, "reason": "git not prefetched"})

    @tool(
        name="inspect_file",
        description="Inspect one visible relative workspace file. Hidden evaluators are refused.",
    )
    def inspect_file(path: str = "") -> str:
        if not _clip(path, 240).strip():
            return record(
                "inspect_file",
                {"error": "path required", "hint": "relative workspace file such as report.txt"},
            )
        rel = _safe_relpath(path)
        if not rel:
            return record("inspect_file", {"error": "path rejected"})
        cwd = request.session.cwd
        if cwd:
            from pex_supervisor.workspace import read_visible

            return record("inspect_file", read_visible(Path(cwd), rel, limit=1_200))
        files = ((request.scores.features or {}).get("prefetched_evidence") or {}).get(
            "files"
        ) or []
        names = [
            str(item.get("path") if isinstance(item, dict) else item)
            for item in files[:80]
        ]
        return record(
            "inspect_file",
            {
                "path": rel,
                "in_inventory": rel in names or any(name.endswith(rel) for name in names),
                "content": "unavailable_remote",
            },
        )

    @tool(
        name="inspect_artifact",
        description="Inspect a bounded tail of an observed result artifact such as results.jsonl.",
    )
    def inspect_artifact(path: str = "") -> str:
        rel = _safe_relpath(path) if path else None
        cwd = request.session.cwd
        if cwd:
            from pex_supervisor.workspace import artifact_tails

            tails = artifact_tails(Path(cwd), limit=800)
            if rel:
                match = next((item for item in tails if item.get("path") == rel), None)
                return record(
                    "inspect_artifact",
                    match or {"error": "artifact not observed", "path": rel},
                )
            return record("inspect_artifact", {"artifacts": tails[:12]})
        artifacts = (
            ((request.scores.features or {}).get("prefetched_evidence") or {}).get("artifacts")
            or []
        )
        if rel:
            match = next(
                (
                    item
                    for item in artifacts
                    if isinstance(item, dict) and item.get("path") == rel
                ),
                None,
            )
            return record(
                "inspect_artifact",
                match or {"error": "artifact not prefetched", "path": rel},
            )
        return record("inspect_artifact", {"artifacts": artifacts[:12]})

    @tool(
        name="inspect_process",
        description="Inspect the observed background process table evidence for this STOP.",
    )
    def inspect_process() -> str:
        abandoned = (request.scores.features or {}).get("abandoned_background")
        return record(
            "inspect_process",
            abandoned
            or {"observed": False, "reason": "no abandoned background job on this STOP"},
        )

    @tool(
        name="run_verification",
        description=(
            "Return the immutable local verification receipt for this event. "
            "This never executes workspace code or reads hidden evaluators."
        ),
    )
    def run_verification() -> str:
        return record(
            "run_verification",
            (request.scores.features or {}).get("verification")
            or {"status": "unavailable", "reason": "no local verification receipt"},
        )

    @tool(
        name="web_search",
        description=(
            "Search the public web to check a worker-cited claim. "
            "Never used to read hidden evaluators or benchmark oracles."
        ),
    )
    def web_search(query: str = "") -> str:
        from pex_supervisor.search import web_search as search_web

        return record("web_search", search_web(_clip(query, 300), limit=5))

    @tool(
        name="scrape_url",
        description=(
            "Fetch a public http(s) page the worker cited. Local, private, "
            "and hidden-evaluator URLs are refused."
        ),
    )
    def scrape_url(url: str = "") -> str:
        from pex_supervisor.search import scrape_url as fetch_url

        return record("scrape_url", fetch_url(_clip(url, 500)))

    return [
        get_goal,
        get_session_state,
        get_recent_events,
        get_scores,
        get_context,
        inspect_workspace,
        inspect_git,
        inspect_file,
        inspect_artifact,
        inspect_process,
        run_verification,
        web_search,
        scrape_url,
    ]
