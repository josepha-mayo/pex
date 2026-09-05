"""Bounded, request-scoped evidence tools for the Strands supervisor.

These tools are read-only and request scoped. Some inspect the bound workspace
or public web, but none execute worker code, call a harness, mutate PEX state,
or access hidden benchmark material.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterator, MutableSequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pex_protocol.redaction import redact_mapping
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import (
    SupervisorContextItem,
    SupervisorDecisionItem,
    SupervisorRequest,
)
from strands import tool

from pex_supervisor.evidence_observations import (
    EvidenceObservationCollector,
    canonical_arguments,
)

_CONTEXT_PAGE_SIZE = 3
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


@dataclass
class _WorkspaceEvidenceGuard:
    target: str
    check: Callable[[], None]
    active: bool = True


_WORKSPACE_EVIDENCE_GUARD: ContextVar[_WorkspaceEvidenceGuard | None] = ContextVar(
    "pex_workspace_evidence_guard", default=None,
)


def _workspace_target(session: HarnessSession) -> str:
    binding = session.metadata.get("workspace_binding")
    if not isinstance(binding, dict) or not binding:
        raise ValueError("workspace evidence requires an exact selected binding")
    rendered = json.dumps(
        {
            "id": session.id,
            "vendor_session_id": session.vendor_session_id,
            "harness_type": session.harness_type.value,
            "project_id": session.project_id,
            "cwd": session.cwd,
            "workspace_binding": binding,
        },
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    if len(rendered.encode("utf-8")) > 65_536:
        raise ValueError("workspace evidence binding exceeds its bound")
    return rendered


@contextmanager
def workspace_evidence_guard(
    session: HarnessSession, check: Callable[[], None],
) -> Iterator[None]:
    """Install server-owned authority for one local evidence invocation.

    The callback is never reconstructed from request metadata. Context copies
    share revocation, so tasks/threads cannot keep reading after the invocation
    exits. Pre/post samples do not make filesystem reads atomic or undo bytes
    already read by an in-flight thread.
    """
    if not callable(check):
        raise TypeError("workspace evidence guard requires a trusted callback")
    guard = _WorkspaceEvidenceGuard(_workspace_target(session), check)
    token = _WORKSPACE_EVIDENCE_GUARD.set(guard)
    try:
        yield
    finally:
        guard.active = False
        _WORKSPACE_EVIDENCE_GUARD.reset(token)


def _workspace_read_allowed(session: HarnessSession) -> bool:
    guard = _WORKSPACE_EVIDENCE_GUARD.get()
    if guard is None:
        # Existing unbound observations retain their legacy behavior; a copied
        # workspace receipt is not itself permission to open a local path.
        return "workspace_binding" not in session.metadata
    try:
        if not guard.active or guard.target != _workspace_target(session):
            return False
        guard.check()
        return guard.active
    except Exception:
        return False


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


def _page_offset(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _context_item_summary(item: SupervisorContextItem) -> dict[str, object]:
    return {
        "id": item.id,
        "kind": str(getattr(item, "kind", "")),
        "semantic_kind": _clip(getattr(item, "semantic_kind", ""), 120) or None,
        "status": _clip(getattr(item, "status", ""), 120) or None,
        "provenance": str(getattr(item, "provenance", "")),
        "verified": bool(getattr(item, "verified", False)),
        "content_preview": _clip(getattr(item, "content", ""), 240),
        "source_session_id": _clip(getattr(item, "source_session_id", ""), 200)
        or None,
    }


def _context_item_detail(item: SupervisorContextItem) -> dict[str, object]:
    content = str(getattr(item, "content", "") or "")
    source_refs = list(getattr(item, "source_refs", ()) or ())
    tags = list(getattr(item, "relevance_tags", ()) or ())
    return {
        **_context_item_summary(item),
        "content": _clip(content, 1_200),
        "content_truncated": len(content) > 1_200,
        "source_refs": [_clip(value, 200) for value in source_refs[:6]],
        "source_refs_omitted": max(0, len(source_refs) - 6),
        "relevance_tags": [_clip(value, 120) for value in tags[:8]],
        "relevance_tags_omitted": max(0, len(tags) - 8),
        "confidence": getattr(item, "confidence", None),
        "valid_from": item.valid_from.isoformat(),
        "stale_after": (
            item.stale_after.isoformat() if item.stale_after is not None else None
        ),
        "supersedes": _clip(getattr(item, "supersedes", ""), 200) or None,
        "sensitivity": str(getattr(item, "sensitivity", "")),
    }


def _decision_summary(item: SupervisorDecisionItem) -> dict[str, object]:
    return {
        "id": item.id,
        "statement_preview": _clip(getattr(item, "statement", ""), 240),
        "source": str(getattr(item, "source", "")),
        "status": str(getattr(item, "status", "")),
        "confidence": getattr(item, "confidence", None),
        "source_session_id": _clip(getattr(item, "source_session_id", ""), 200)
        or None,
    }


def _decision_detail(item: SupervisorDecisionItem) -> dict[str, object]:
    statement = str(getattr(item, "statement", "") or "")
    rationale = str(getattr(item, "rationale", "") or "")
    alternatives = list(getattr(item, "alternatives_rejected", ()) or ())
    source_refs = list(getattr(item, "source_refs", ()) or ())
    return {
        **_decision_summary(item),
        "statement": _clip(statement, 1_200),
        "statement_truncated": len(statement) > 1_200,
        "rationale": _clip(rationale, 800) or None,
        "rationale_truncated": len(rationale) > 800,
        "alternatives_rejected": [_clip(value, 500) for value in alternatives[:6]],
        "alternatives_omitted": max(0, len(alternatives) - 6),
        "scope": _clip(getattr(item, "scope", ""), 500) or None,
        "created_at": item.created_at.isoformat(),
        "source_refs": [_clip(value, 200) for value in source_refs[:6]],
        "source_refs_omitted": max(0, len(source_refs) - 6),
        "sensitivity": str(getattr(item, "sensitivity", "")),
    }


def build_evidence_tools(
    request: SupervisorRequest,
    used_tools: MutableSequence[str],
    *,
    collector: EvidenceObservationCollector | None = None,
) -> list[object]:
    """Build fresh read-only tools bound to one validated request."""

    if collector is None:
        collector = EvidenceObservationCollector(
            request,
            stage="main",
            invocation_id="pextool_compatibility",
        )

    local_values = tuple(
        value
        for value in (
            request.session.cwd,
            request.session.repo,
            request.session.external_url,
        )
        if value
    )

    def record(
        name: str,
        value: object,
        arguments: dict[str, object] | None = None,
    ) -> str:
        used_tools.append(name)
        # Bound depth/count/width before any recursive masking or redaction so a
        # malformed internal Any value cannot overflow the evidence tool.
        masked = _mask_local_strings(_bounded(value), local_values)
        cleaned, _ = redact_mapping({"evidence": masked})
        raw_arguments = _mask_local_strings(_bounded(arguments or {}), local_values)
        cleaned_arguments, _ = redact_mapping({"arguments": raw_arguments})
        return collector.record(
            tool_name=name,
            arguments_json=canonical_arguments(
                (cleaned_arguments or {}).get("arguments") or {}
            ),
            value=(cleaned or {}).get("evidence"),
        )

    def local_record(
        name: str,
        read: Callable[[], object],
        arguments: dict[str, object] | None = None,
    ) -> str:
        unavailable = {
            "available": False, "observed": False,
            "error": "workspace_authority_unavailable",
        }
        if not _workspace_read_allowed(request.session):
            return record(name, unavailable, arguments)
        try:
            value = read()
        except Exception:
            value = {
                "available": False, "observed": False,
                "error": "local_evidence_read_failed",
            }
        # Recheck even after a failed read. Never collect or return stale bytes
        # (or exception text) from a replaced root or a revoked invocation.
        if not _workspace_read_allowed(request.session):
            value = unavailable
        return record(name, value, arguments)

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
            "Return an index of inspectable evidence and selected durable context. Query "
            "get_context_items, get_decisions, inspect_workspace, inspect_git, inspect_file, "
            "inspect_artifact, inspect_process, run_verification, web_search, and scrape_url."
        ),
    )
    def get_context() -> str:
        features = request.scores.features or {}
        workspace = features.get("prefetched_evidence") or {}
        return record(
            "get_context",
            {
                "query": [
                    "get_context_items",
                    "get_decisions",
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
                "offered_context_count": len(
                    request.supervisor_context.offered_context_ids
                    if request.supervisor_context is not None
                    else ()
                ),
                "context_first_ids": list(
                    request.supervisor_context.offered_context_ids[:_CONTEXT_PAGE_SIZE]
                    if request.supervisor_context is not None
                    else ()
                ),
                "context_next_offset": (
                    _CONTEXT_PAGE_SIZE
                    if request.supervisor_context is not None
                    and len(request.supervisor_context.offered_context_ids)
                    > _CONTEXT_PAGE_SIZE
                    else None
                ),
                "context_next_ids": list(
                    request.supervisor_context.offered_context_ids[
                        _CONTEXT_PAGE_SIZE : _CONTEXT_PAGE_SIZE * 2
                    ]
                    if request.supervisor_context is not None
                    else ()
                ),
                "offered_decision_count": len(
                    request.supervisor_context.offered_decision_ids
                    if request.supervisor_context is not None
                    else ()
                ),
                "decision_first_ids": list(
                    request.supervisor_context.offered_decision_ids[:_CONTEXT_PAGE_SIZE]
                    if request.supervisor_context is not None
                    else ()
                ),
                "decision_next_offset": (
                    _CONTEXT_PAGE_SIZE
                    if request.supervisor_context is not None
                    and len(request.supervisor_context.offered_decision_ids)
                    > _CONTEXT_PAGE_SIZE
                    else None
                ),
                "decision_next_ids": list(
                    request.supervisor_context.offered_decision_ids[
                        _CONTEXT_PAGE_SIZE : _CONTEXT_PAGE_SIZE * 2
                    ]
                    if request.supervisor_context is not None
                    else ()
                ),
            },
        )

    @tool(
        name="get_context_items",
        description=(
            "Page through bounded provenance-bearing durable context, or retrieve one "
            "offered item by exact context_id. Use next_offset until it is null."
        ),
    )
    def get_context_items(context_id: str = "", offset: int = 0) -> str:
        def emit(value: object) -> str:
            return record(
                "get_context_items",
                value,
                {"context_id": context_id, "offset": offset},
            )

        envelope = request.supervisor_context
        if envelope is None:
            return emit({"available": False, "items": []})
        if context_id:
            if offset != 0:
                return emit(
                    {"available": True, "error": "context_id and offset are mutually exclusive"},
                )
            selected = next(
                (item for item in envelope.context_items if item.id == context_id),
                None,
            )
            if selected is None:
                return emit(
                    {
                        "available": True,
                        "mode": "item",
                        "error": "context_id was not offered",
                        "context_id": _clip(context_id, 200),
                    },
                )
            return emit(
                {
                    "available": True,
                    "mode": "item",
                    "observed_at": envelope.observed_at.isoformat(),
                    "item": _context_item_detail(selected),
                },
            )
        start = _page_offset(offset)
        if start is None:
            return emit(
                {"available": True, "error": "offset must be a non-negative integer"},
            )
        page = envelope.context_items[start : start + _CONTEXT_PAGE_SIZE]
        next_offset = start + len(page)
        if next_offset >= len(envelope.context_items):
            next_offset = None
        next_ids = (
            envelope.offered_context_ids[
                next_offset : next_offset + _CONTEXT_PAGE_SIZE
            ]
            if next_offset is not None
            else ()
        )
        return emit(
            {
                "available": True,
                "mode": "page",
                "observed_at": envelope.observed_at.isoformat(),
                "offered_count": len(envelope.context_items),
                "offset": start,
                "items": [_context_item_summary(item) for item in page],
                "next_offset": next_offset,
                "next_ids": list(next_ids),
                "omitted_count": max(0, len(envelope.context_items) - start - len(page)),
            },
        )

    @tool(
        name="get_decisions",
        description=(
            "Page through bounded active or unresolved durable decisions, or retrieve one "
            "offered decision by exact decision_id. Use next_offset until it is null."
        ),
    )
    def get_decisions(decision_id: str = "", offset: int = 0) -> str:
        def emit(value: object) -> str:
            return record(
                "get_decisions",
                value,
                {"decision_id": decision_id, "offset": offset},
            )

        envelope = request.supervisor_context
        if envelope is None:
            return emit({"available": False, "decisions": []})
        if decision_id:
            if offset != 0:
                return emit(
                    {"available": True, "error": "decision_id and offset are mutually exclusive"},
                )
            selected = next(
                (item for item in envelope.decisions if item.id == decision_id),
                None,
            )
            if selected is None:
                return emit(
                    {
                        "available": True,
                        "mode": "item",
                        "error": "decision_id was not offered",
                        "decision_id": _clip(decision_id, 200),
                    },
                )
            return emit(
                {
                    "available": True,
                    "mode": "item",
                    "observed_at": envelope.observed_at.isoformat(),
                    "decision": _decision_detail(selected),
                },
            )
        start = _page_offset(offset)
        if start is None:
            return emit(
                {"available": True, "error": "offset must be a non-negative integer"},
            )
        page = envelope.decisions[start : start + _CONTEXT_PAGE_SIZE]
        next_offset = start + len(page)
        if next_offset >= len(envelope.decisions):
            next_offset = None
        next_ids = (
            envelope.offered_decision_ids[
                next_offset : next_offset + _CONTEXT_PAGE_SIZE
            ]
            if next_offset is not None
            else ()
        )
        return emit(
            {
                "available": True,
                "mode": "page",
                "observed_at": envelope.observed_at.isoformat(),
                "offered_count": len(envelope.decisions),
                "offset": start,
                "decisions": [_decision_summary(item) for item in page],
                "next_offset": next_offset,
                "next_ids": list(next_ids),
                "omitted_count": max(0, len(envelope.decisions) - start - len(page)),
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
            return local_record("inspect_workspace", lambda: workspace)
        cwd = request.session.cwd
        if not cwd:
            return record("inspect_workspace", {"observed": False, "reason": "cwd unavailable"})
        from pex_supervisor.workspace import snapshot

        def read() -> dict:
            raw = snapshot(cwd, run_pytest=False)
            return {
                "observed": not bool(raw.get("error")),
                "error": raw.get("error"),
                "files": list(raw.get("files") or [])[:80],
                "files_truncated": bool(raw.get("files_truncated")),
                "pytest": raw.get("pytest"),
            }

        return local_record("inspect_workspace", read)

    @tool(
        name="inspect_git",
        description="Inspect observed git status and a bounded diff for this workspace.",
    )
    def inspect_git() -> str:
        cwd = request.session.cwd
        if cwd:
            from pex_supervisor.workspace import git_snapshot

            def read() -> dict:
                raw = git_snapshot(Path(cwd))
                return {
                    "available": raw.get("available"),
                    "error": raw.get("error"),
                    "status": _clip(raw.get("status"), 1_500),
                    "diff_stat": _clip(raw.get("diff_stat"), 1_500),
                    "diff": _clip(raw.get("diff"), 2_500),
                }

            return local_record("inspect_git", read)
        git = ((request.scores.features or {}).get("prefetched_evidence") or {}).get("git")
        return local_record(
            "inspect_git", lambda: git or {"available": False, "reason": "git not prefetched"},
        )

    @tool(
        name="inspect_file",
        description="Inspect one visible relative workspace file. Hidden evaluators are refused.",
    )
    def inspect_file(path: str = "") -> str:
        def emit(value: object) -> str:
            return record("inspect_file", value, {"path": path})

        if not _clip(path, 240).strip():
            return emit(
                {"error": "path required", "hint": "relative workspace file such as report.txt"},
            )
        rel = _safe_relpath(path)
        if not rel:
            return emit({"error": "path rejected"})
        cwd = request.session.cwd
        if cwd:
            from pex_supervisor.workspace import read_visible

            return local_record(
                "inspect_file", lambda: read_visible(Path(cwd), rel, limit=1_200),
                {"path": path},
            )
        files = ((request.scores.features or {}).get("prefetched_evidence") or {}).get(
            "files"
        ) or []
        names = [
            str(item.get("path") if isinstance(item, dict) else item)
            for item in files[:80]
        ]
        return local_record(
            "inspect_file", lambda: {
                "path": rel,
                "in_inventory": rel in names or any(name.endswith(rel) for name in names),
                "content": "unavailable_remote",
            },
            {"path": path},
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

            def read() -> dict:
                tails = artifact_tails(Path(cwd), limit=800)
                if rel:
                    match = next((item for item in tails if item.get("path") == rel), None)
                    return match or {"error": "artifact not observed", "path": rel}
                return {"artifacts": tails[:12]}

            return local_record("inspect_artifact", read, {"path": path})
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
            return local_record(
                "inspect_artifact",
                lambda: match or {"error": "artifact not prefetched", "path": rel},
                {"path": path},
            )
        return local_record(
            "inspect_artifact", lambda: {"artifacts": artifacts[:12]}, {"path": path},
        )

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

        return record(
            "web_search",
            search_web(_clip(query, 300), limit=5),
            {"query": query},
        )

    @tool(
        name="scrape_url",
        description=(
            "Fetch a public http(s) page the worker cited. Local, private, "
            "and hidden-evaluator URLs are refused."
        ),
    )
    def scrape_url(url: str = "") -> str:
        from pex_supervisor.search import scrape_url as fetch_url

        return record("scrape_url", fetch_url(_clip(url, 500)), {"url": url})

    return [
        get_goal,
        get_session_state,
        get_recent_events,
        get_scores,
        get_context,
        get_context_items,
        get_decisions,
        inspect_workspace,
        inspect_git,
        inspect_file,
        inspect_artifact,
        inspect_process,
        run_verification,
        web_search,
        scrape_url,
    ]
