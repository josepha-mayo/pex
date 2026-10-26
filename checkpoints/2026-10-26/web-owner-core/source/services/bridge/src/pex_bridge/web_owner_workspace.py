"""Bounded owner read projection. No app startup, migration or worker authority.

The path is supplied by server composition, never by an HTTP client. Existing
Store projection rules are reused through read-only connections; no Store.connect
is called. Separate reads are observational, not an atomic cross-row snapshot.
"""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from pex_bridge.store import Store

ROW_LIMIT = 20
MAX_SNAPSHOT_BYTES = 32768
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_COMPLETION = {"uncertain", "in_progress", "verified_complete", "incomplete"}
_REASONS = {
    "goal_not_currently_executable",
    "newer_active_session_work",
    "current_intent_stop_evidence_supported",
    "current_intent_stop_evidence_unsatisfied",
    "active_session_without_terminal_evidence",
    "no_current_supported_completion_evidence",
}


def _identifier(value: object, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("invalid workspace identifier")
    return value


def _timestamp(value: object) -> str:
    if isinstance(value, datetime):
        stamp = value
    elif isinstance(value, str) and len(value) <= 40:
        stamp = datetime.fromisoformat(value)
    else:
        raise ValueError("invalid workspace timestamp")
    if stamp.tzinfo is None:
        raise ValueError("workspace timestamp needs timezone")
    return stamp.astimezone(UTC).isoformat()


class _ReadView(Store):
    """Only the facade below is exposed, not this Store-shaped implementation."""

    async def connect(self) -> None:
        raise RuntimeError("owner view cannot connect or migrate a Store")

    @asynccontextmanager
    async def _pooled_connection(self):
        # Do not use immutable=1: committed data may still be in the WAL.
        async with aiosqlite.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=1) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA query_only=ON")
            await db.execute("PRAGMA busy_timeout=1000")
            # Bound computational work as well as returned rows. A complicated
            # legacy projection fails closed instead of monopolizing a reader.
            remaining = 2000

            def budget():
                nonlocal remaining
                remaining -= 1
                return int(remaining <= 0)

            await db.set_progress_handler(budget, 1000)
            try:
                yield db
            finally:
                await db.rollback()


class OwnerWorkspaceReader:
    """Explicit server-owned path; construction performs no DB or network I/O."""

    def __init__(self, database_path: Path):
        if not isinstance(database_path, Path) or not database_path.is_absolute():
            raise ValueError("explicit absolute workspace database path required")
        self.__view = _ReadView(database_path)

    async def read_workspace(self) -> dict:
        view = self.__view
        # Do not silently omit quarantined rows from the authoritative listing.
        async with view._pooled_connection() as db:
            cursor = await db.execute(
                "SELECT intent_revision, intent_hash FROM goals "
                "ORDER BY json_extract(json, '$.updated_at') DESC, "
                "json_extract(json, '$.created_at') DESC, id DESC LIMIT ?",
                (ROW_LIMIT + 1,),
            )
            if any(row[0] is None or row[1] is None for row in await cursor.fetchall()):
                raise ValueError("workspace goal authority unavailable")
        sessions = await view.list_sessions(limit=ROW_LIMIT + 1)
        goals = await view.list_goal_intent_views_page(limit=ROW_LIMIT + 1)
        projected_sessions = []
        for session in sessions[:ROW_LIMIT]:
            projected_sessions.append(
                {
                    "id": _identifier(session.id),
                    "harness_type": session.harness_type.value,
                    "status": session.status.value,
                    "goal_id": _identifier(session.goal_id, optional=True),
                    "last_activity": _timestamp(session.last_activity)
                    if session.last_activity
                    else None,
                }
            )
        projected_goals = []
        for goal in goals[:ROW_LIMIT]:
            goal_id = _identifier(goal["id"])
            title = goal["title"]
            if (
                not isinstance(title, str)
                or not 1 <= len(title) <= 320
                or any(ord(c) < 32 for c in title)
            ):
                raise ValueError("invalid workspace title")
            completion = await view.goal_completion_projection(goal_id)
            if (
                completion["goal_intent_revision"] != goal["intent_revision"]
                or completion["goal_intent_hash"] != goal["intent_hash"]
                or completion["status"] not in _COMPLETION
                or completion["reason"] not in _REASONS
            ):
                raise ValueError("workspace goal changed or completion unavailable")
            projected_goals.append(
                {
                    "id": goal_id,
                    "title": title,
                    "paused": goal["paused"],
                    "completion": {
                        "status": completion["status"],
                        "reason": completion["reason"],
                        "as_of": _timestamp(completion["as_of"]),
                    },
                }
            )
        result = {
            "schema": "pex.owner-workspace.v1",
            "observed_at": datetime.now(UTC).isoformat(),
            "sessions": projected_sessions,
            "goals": projected_goals,
            "truncated": {"sessions": len(sessions) > ROW_LIMIT, "goals": len(goals) > ROW_LIMIT},
        }
        if (
            len(json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
            > MAX_SNAPSHOT_BYTES
        ):
            raise ValueError("workspace projection too large")
        return result
