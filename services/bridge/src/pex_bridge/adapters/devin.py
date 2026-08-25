"""Devin v3 Organization API. Granularity stays Basic even when attached.

Official: https://api.devin.ai/v3/organizations/{orgId}/sessions
PEX does not pretend Devin exposes Cursor-grade tool telemetry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pex_protocol.capabilities import AdapterCapabilities, AdapterSupportLabel, ControlGranularity
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.base import HarnessAdapter
from pex_bridge.adapters.http_json import HttpJsonTransport


class DevinAdapter(HarnessAdapter):
    name = "devin"

    def __init__(self, transport: HttpJsonTransport | None = None, org_id: str = "org") -> None:
        self.transport = transport
        self.org_id = org_id
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.hooks: list[dict] = []

    def attach_transport(self, transport: HttpJsonTransport, org_id: str | None = None) -> None:
        self.transport = transport
        if org_id:
            self.org_id = org_id

    def _sessions_path(self) -> str:
        return f"/v3/organizations/{self.org_id}/sessions"

    async def probe(self) -> AdapterCapabilities:
        connected = self.transport is not None
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
                "Official Devin v3 Organization API (sessions + messages). "
                "Tool-level telemetry is thinner than local harnesses, so the label stays Basic even when attached. "
                + ("Transport attached." if connected else "No API credentials/transport.")
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        if self.transport is None:
            return list(self.sessions.values())
        listed = await self.transport.request("GET", self._sessions_path())
        if isinstance(listed, dict):
            listed = listed.get("sessions") or listed.get("items") or []
        for item in listed or []:
            vendor_id = str(item.get("id") or item.get("session_id"))
            session_id = f"devin:{vendor_id}"
            existing = self.sessions.get(session_id)
            self.sessions[session_id] = HarnessSession(
                id=session_id,
                harness_type=HarnessType.DEVIN,
                vendor_session_id=vendor_id,
                status=SessionStatus.WORKING if item.get("status") in {"running", "working"} else SessionStatus.DISCOVERED,
                last_activity=datetime.now(timezone.utc),
                goal_id=existing.goal_id if existing else None,
                metadata={"title": item.get("title") or item.get("prompt")},
            )
        return list(self.sessions.values())

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        self.inbox.setdefault(session.id, []).append(text)
        if self.transport is None:
            return False
        await self.transport.request(
            "POST",
            f"{self._sessions_path()}/{session.vendor_session_id}/messages",
            json={"message": text},
        )
        return True

    def ingest_hook(self, payload: dict) -> HarnessSession:
        vendor_id = str(payload.get("session_id") or payload.get("id") or uuid4().hex[:12])
        session_id = f"devin:{vendor_id}"
        existing = self.sessions.get(session_id)
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.DEVIN,
            vendor_session_id=vendor_id,
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
