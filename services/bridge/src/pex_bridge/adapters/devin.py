"""Devin v3 Organization API. Granularity stays Basic even when attached.

Official: https://api.devin.ai/v3/organizations/{orgId}/sessions
Poll GET session until status is exit|error|suspended, then inspect.
POST .../messages to nudge. PEX does not pretend Devin exposes Cursor-grade tool telemetry.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from pex_protocol.capabilities import AdapterCapabilities, AdapterSupportLabel, ControlGranularity
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.base import HarnessAdapter
from pex_bridge.adapters.http_json import HttpJsonTransport

_TERMINAL = {"exit", "error", "suspended"}


class DevinAdapter(HarnessAdapter):
    name = "devin"

    def __init__(self, transport: HttpJsonTransport | None = None, org_id: str = "org") -> None:
        self.transport = transport
        self.org_id = org_id
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.hooks: list[dict] = []
        self._pump_task: asyncio.Task | None = None
        self._seen_terminal: set[str] = set()
        self._seen_messages: dict[str, int] = {}

    def attach_transport(self, transport: HttpJsonTransport, org_id: str | None = None) -> None:
        self.transport = transport
        if org_id:
            self.org_id = org_id

    def _sessions_path(self) -> str:
        return f"/v3/organizations/{self.org_id}/sessions"

    async def probe(self) -> AdapterCapabilities:
        connected = self.transport is not None
        pumping = self._pump_task is not None and not self._pump_task.done()
        return AdapterCapabilities(
            observe_messages=connected,
            observe_session_status=connected,
            send_message=connected,
            inject_context=connected,
            start=connected,
            control_granularity=ControlGranularity.SESSION,
            trust_level=0.55 if connected else 0.0,
            support_label=AdapterSupportLabel.BASIC if connected else AdapterSupportLabel.UNAVAILABLE,
            notes=(
                "Official Devin v3 Organization API "
                "(GET /v3/organizations/{org}/sessions/{id}, POST .../messages). "
                "Terminal statuses: exit, error, suspended. Label stays Basic. "
                + (
                    "Transport attached."
                    + (" Status poll running." if pumping else " Start the session poll to inspect exit.")
                    if connected
                    else "No API credentials/transport."
                )
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        if self.transport is None:
            return list(self.sessions.values())
        listed = await self.transport.request("GET", self._sessions_path())
        if isinstance(listed, dict):
            listed = listed.get("sessions") or listed.get("items") or []
        for item in listed or []:
            vendor_id = str(item.get("session_id") or item.get("id") or "")
            if not vendor_id:
                continue
            session_id = f"devin:{vendor_id}"
            existing = self.sessions.get(session_id)
            status = str(item.get("status") or "")
            self.sessions[session_id] = HarnessSession(
                id=session_id,
                harness_type=HarnessType.DEVIN,
                vendor_session_id=vendor_id,
                status=SessionStatus.WORKING if status in {"running", "claimed", "new", "resuming"} else SessionStatus.DISCOVERED,
                last_activity=datetime.now(timezone.utc),
                goal_id=existing.goal_id if existing else None,
                metadata={"title": item.get("title") or item.get("prompt"), "status": status},
            )
        return list(self.sessions.values())

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        if self.transport is None:
            return False
        try:
            await self.transport.request(
                "POST",
                f"{self._sessions_path()}/{session.vendor_session_id}/messages",
                json={"message": text},
            )
        except Exception:
            return False
        self.inbox.setdefault(session.id, []).append(text)
        return True

    def ingest_hook(self, payload: dict) -> HarnessSession:
        vendor_id = str(payload.get("session_id") or payload.get("id") or uuid4().hex[:12])
        session_id = f"devin:{vendor_id}"
        existing = self.sessions.get(session_id)
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.DEVIN,
            vendor_session_id=vendor_id,
            cwd=payload.get("cwd"),
            status=SessionStatus.WORKING,
            last_activity=datetime.now(timezone.utc),
            goal_id=existing.goal_id if existing else None,
        )
        self.sessions[session_id] = session
        self.hooks.append(payload)
        return session

    def emit_status(self, session: HarnessSession, message: str) -> HarnessEvent:
        return HarnessEvent(
            event_id=uuid4().hex,
            ts=datetime.now(timezone.utc),
            harness_type=HarnessType.DEVIN,
            session_id=session.id,
            event_type=EventType.STATUS,
            message_delta=message,
        )

    async def pump_into_pipeline(self, ingest) -> None:
        while True:
            try:
                if self.transport is None:
                    await asyncio.sleep(0.25)
                    continue
                try:
                    await self.discover_sessions()
                except Exception:
                    pass
                for session in list(self.sessions.values()):
                    vendor_id = session.vendor_session_id
                    try:
                        detail = await self.transport.request(
                            "GET",
                            f"{self._sessions_path()}/{vendor_id}",
                        )
                    except Exception:
                        continue
                    if not isinstance(detail, dict):
                        continue
                    status = str(detail.get("status") or "")
                    try:
                        listed = await self.transport.request(
                            "GET",
                            f"{self._sessions_path()}/{vendor_id}/messages",
                        )
                    except Exception:
                        listed = {}
                    rows = listed.get("messages") if isinstance(listed, dict) else listed
                    rows = rows if isinstance(rows, list) else []
                    seen = self._seen_messages.get(vendor_id, 0)
                    for item in rows[seen:]:
                        if not isinstance(item, dict):
                            continue
                        text = item.get("message") or item.get("content") or item.get("text")
                        event = HarnessEvent(
                            event_id=uuid4().hex,
                            ts=datetime.now(timezone.utc),
                            harness_type=HarnessType.DEVIN,
                            session_id=session.id,
                            event_type=EventType.AGENT_RESPONSE,
                            phase=EventPhase.AFTER,
                            message_delta=str(text or ""),
                            metadata={"devin_status": status, "replay": False},
                        )
                        await ingest(event, session)
                    self._seen_messages[vendor_id] = len(rows)
                    if status in _TERMINAL and vendor_id not in self._seen_terminal:
                        self._seen_terminal.add(vendor_id)
                        last = rows[-1] if rows else {}
                        text = ""
                        if isinstance(last, dict):
                            text = str(
                                last.get("message") or last.get("content") or last.get("text") or ""
                            )
                        event = HarnessEvent(
                            event_id=uuid4().hex,
                            ts=datetime.now(timezone.utc),
                            harness_type=HarnessType.DEVIN,
                            session_id=session.id,
                            event_type=EventType.STOP,
                            phase=EventPhase.TERMINAL,
                            message_delta=text or status,
                            metadata={"devin_status": status, "replay": False},
                        )
                        await ingest(event, session)
                await asyncio.sleep(0.2)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(0.5)

    def start_pipeline_pump(self, ingest) -> asyncio.Task:
        existing = self._pump_task
        if existing is not None and not existing.done():
            return existing
        self._pump_task = asyncio.create_task(
            self.pump_into_pipeline(ingest),
            name="devin-org-api-poll",
        )
        return self._pump_task
