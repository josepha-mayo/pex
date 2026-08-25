from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite
from pex_protocol.context import ContextItem
from pex_protocol.goal import Decision, Goal
from pex_protocol.intervention import Intervention
from pex_protocol.overlay import Overlay
from pex_protocol.session import HarnessEvent, HarnessSession

SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
  id TEXT PRIMARY KEY,
  json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
  id TEXT PRIMARY KEY,
  goal_id TEXT,
  json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS context_items (
  id TEXT PRIMARY KEY,
  project_id TEXT,
  json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  vendor_session_id TEXT,
  harness_type TEXT,
  json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  session_id TEXT,
  ts TEXT,
  json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interventions (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  ts TEXT,
  json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS overlays (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fingerprints (
  key TEXT PRIMARY KEY,
  json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_session_ts ON events(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_sessions_vendor ON sessions(vendor_session_id);
"""


def _dump(model: Any) -> str:
    return model.model_dump_json()


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("store is not connected")
        return self._db

    async def upsert_goal(self, goal: Goal) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO goals(id, json) VALUES (?, ?)",
            (goal.id, _dump(goal)),
        )
        await self.db.commit()

    async def get_goal(self, goal_id: str) -> Goal | None:
        cur = await self.db.execute("SELECT json FROM goals WHERE id = ?", (goal_id,))
        row = await cur.fetchone()
        return Goal.model_validate_json(row["json"]) if row else None

    async def list_goals(self) -> list[Goal]:
        cur = await self.db.execute("SELECT json FROM goals")
        rows = await cur.fetchall()
        return [Goal.model_validate_json(r["json"]) for r in rows]

    async def upsert_session(self, session: HarnessSession) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO sessions(id, vendor_session_id, harness_type, json) VALUES (?, ?, ?, ?)",
            (session.id, session.vendor_session_id, session.harness_type.value, _dump(session)),
        )
        await self.db.commit()

    async def get_session(self, session_id: str) -> HarnessSession | None:
        cur = await self.db.execute("SELECT json FROM sessions WHERE id = ?", (session_id,))
        row = await cur.fetchone()
        return HarnessSession.model_validate_json(row["json"]) if row else None

    async def find_session_by_vendor(self, vendor_session_id: str) -> HarnessSession | None:
        cur = await self.db.execute(
            "SELECT json FROM sessions WHERE vendor_session_id = ?",
            (vendor_session_id,),
        )
        row = await cur.fetchone()
        return HarnessSession.model_validate_json(row["json"]) if row else None

    async def list_sessions(self) -> list[HarnessSession]:
        cur = await self.db.execute("SELECT json FROM sessions")
        rows = await cur.fetchall()
        return [HarnessSession.model_validate_json(r["json"]) for r in rows]

    async def add_event(self, event: HarnessEvent) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO events(event_id, session_id, ts, json) VALUES (?, ?, ?, ?)",
            (event.event_id, event.session_id, event.ts.isoformat(), _dump(event)),
        )
        await self.db.commit()

    async def recent_events(self, session_id: str, limit: int = 80) -> list[HarnessEvent]:
        cur = await self.db.execute(
            "SELECT json FROM events WHERE session_id = ? ORDER BY ts DESC LIMIT ?",
            (session_id, limit),
        )
        rows = await cur.fetchall()
        events = [HarnessEvent.model_validate_json(r["json"]) for r in rows]
        events.reverse()
        return events

    async def add_intervention(self, intervention: Intervention) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO interventions(id, session_id, ts, json) VALUES (?, ?, ?, ?)",
            (intervention.id, intervention.session_id, intervention.created_at.isoformat(), _dump(intervention)),
        )
        await self.db.commit()

    async def list_interventions(self, session_id: str | None = None) -> list[Intervention]:
        if session_id:
            cur = await self.db.execute(
                "SELECT json FROM interventions WHERE session_id = ? ORDER BY ts DESC",
                (session_id,),
            )
        else:
            cur = await self.db.execute("SELECT json FROM interventions ORDER BY ts DESC")
        rows = await cur.fetchall()
        return [Intervention.model_validate_json(r["json"]) for r in rows]

    async def add_context(self, item: ContextItem) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO context_items(id, project_id, json) VALUES (?, ?, ?)",
            (item.id, item.project_id, _dump(item)),
        )
        await self.db.commit()

    async def list_context(self, project_id: str) -> list[ContextItem]:
        cur = await self.db.execute(
            "SELECT json FROM context_items WHERE project_id = ?",
            (project_id,),
        )
        rows = await cur.fetchall()
        return [ContextItem.model_validate_json(r["json"]) for r in rows]

    async def add_decision(self, decision: Decision) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO decisions(id, goal_id, json) VALUES (?, ?, ?)",
            (decision.id, decision.goal_id, _dump(decision)),
        )
        await self.db.commit()

    async def list_decisions(self, goal_id: str) -> list[Decision]:
        cur = await self.db.execute("SELECT json FROM decisions WHERE goal_id = ?", (goal_id,))
        rows = await cur.fetchall()
        return [Decision.model_validate_json(r["json"]) for r in rows]

    async def upsert_overlay(self, overlay: Overlay) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO overlays(id, session_id, json) VALUES (?, ?, ?)",
            (overlay.id, overlay.session_id, _dump(overlay)),
        )
        await self.db.commit()

    async def get_overlay(self, overlay_id: str) -> Overlay | None:
        cur = await self.db.execute("SELECT json FROM overlays WHERE id = ?", (overlay_id,))
        row = await cur.fetchone()
        return Overlay.model_validate_json(row["json"]) if row else None

    async def active_overlays(self, session_id: str) -> list[Overlay]:
        cur = await self.db.execute("SELECT json FROM overlays WHERE session_id = ?", (session_id,))
        rows = await cur.fetchall()
        overlays = [Overlay.model_validate_json(r["json"]) for r in rows]
        return [o for o in overlays if o.applied_at and not o.reverted_at]


def new_id(prefix: str = "") -> str:
    value = uuid4().hex
    return f"{prefix}{value}" if prefix else value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def json_dumps(data: Any) -> str:
    return json.dumps(data, default=str)
