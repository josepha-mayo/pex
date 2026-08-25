"""Qwen Code via official `qwen serve` HTTP + SSE daemon.

Deep only when a transport is attached. Documented routes:
POST /session, POST /session/:id/prompt, GET /session/:id/events,
POST /permission/:requestId. Default daemon port 4170.
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


class QwenAdapter(HarnessAdapter):
    name = "qwen"

    def __init__(self, transport: HttpJsonTransport | None = None) -> None:
        self.transport = transport
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.hooks: list[dict] = []

    def attach_transport(self, transport: HttpJsonTransport) -> None:
        self.transport = transport

    async def probe(self) -> AdapterCapabilities:
        connected = self.transport is not None
        return AdapterCapabilities(
            observe_messages=connected,
            observe_tool_calls=connected,
            observe_session_status=connected,
            observe_permissions=connected,
            send_message=connected,
            inject_context=connected,
            approve=connected,
            deny=connected,
            start=connected,
            resume=connected,
            modify_config=connected,
            control_granularity=ControlGranularity.EVENT if connected else ControlGranularity.SESSION,
            trust_level=0.88 if connected else 0.0,
            support_label=AdapterSupportLabel.DEEP if connected else AdapterSupportLabel.UNAVAILABLE,
            notes=(
                "Official surface: `qwen serve` HTTP+SSE "
                "(POST /session, POST /session/:id/prompt, GET /session/:id/events, POST /permission/:requestId). "
                + ("Transport attached." if connected else "No live daemon; label stays Unavailable.")
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        if self.transport is None:
            return list(self.sessions.values())
        listed = await self.transport.request("GET", "/session")
        if isinstance(listed, dict):
            listed = listed.get("sessions") or listed.get("items") or []
        for item in listed or []:
            vendor_id = str(item.get("id") or item.get("sessionId"))
            session_id = f"qwen:{vendor_id}"
            existing = self.sessions.get(session_id)
            self.sessions[session_id] = HarnessSession(
                id=session_id,
                harness_type=HarnessType.QWEN,
                vendor_session_id=vendor_id,
                cwd=item.get("cwd") or item.get("workspaceCwd"),
                status=SessionStatus.WORKING if item.get("hasActivePrompt") else SessionStatus.DISCOVERED,
                last_activity=datetime.now(timezone.utc),
                goal_id=existing.goal_id if existing else None,
            )
        return list(self.sessions.values())

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        self.inbox.setdefault(session.id, []).append(text)
        if self.transport is None:
            return False
        await self.transport.request(
            "POST",
            f"/session/{session.vendor_session_id}/prompt",
            json={"prompt": text},
        )
        return True

    async def respond_permission(self, session: HarnessSession, request_id: str, decision: str) -> bool:
        if self.transport is None:
            return False
        await self.transport.request(
            "POST",
            f"/permission/{request_id}",
            json={"decision": decision, "sessionId": session.vendor_session_id},
        )
        return True

    def ingest_hook(self, payload: dict) -> HarnessSession:
        vendor_id = str(payload.get("session_id") or payload.get("id") or uuid4().hex[:12])
        session_id = f"qwen:{vendor_id}"
        existing = self.sessions.get(session_id)
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.QWEN,
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
            harness_type=HarnessType.QWEN,
            session_id=session.id,
            event_type=EventType.STATUS,
            message_delta=message,
        )
