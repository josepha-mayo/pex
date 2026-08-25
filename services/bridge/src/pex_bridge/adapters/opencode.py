"""OpenCode via official `opencode serve` HTTP API.

Deep only when a transport is attached (live server or in-process fake).
Hooks remain a fallback ingest path. We do not scrape the TUI.
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


class OpenCodeAdapter(HarnessAdapter):
    name = "opencode"

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
            observe_file_edits=connected,
            observe_permissions=connected,
            send_message=connected,
            inject_context=connected,
            approve=connected,
            deny=connected,
            start=connected,
            resume=connected,
            fork=connected,
            modify_config=connected,
            control_granularity=ControlGranularity.EVENT if connected else ControlGranularity.SESSION,
            trust_level=0.9 if connected else 0.0,
            support_label=AdapterSupportLabel.DEEP if connected else AdapterSupportLabel.UNAVAILABLE,
            notes=(
                "Official surface: `opencode serve` HTTP+SSE "
                "(GET /session, POST /session/:id/prompt_async, POST /session/:id/permissions/:id, PATCH /config). "
                + ("Transport attached." if connected else "No live server; label stays Unavailable.")
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        if self.transport is None:
            return list(self.sessions.values())
        listed = await self.transport.request("GET", "/session")
        for item in listed or []:
            vendor_id = str(item.get("id"))
            session_id = f"opencode:{vendor_id}"
            existing = self.sessions.get(session_id)
            self.sessions[session_id] = HarnessSession(
                id=session_id,
                harness_type=HarnessType.OPENCODE,
                vendor_session_id=vendor_id,
                cwd=item.get("cwd") or item.get("directory"),
                status=SessionStatus.WORKING if existing else SessionStatus.DISCOVERED,
                last_activity=datetime.now(timezone.utc),
                goal_id=existing.goal_id if existing else None,
                metadata={"title": item.get("title")},
            )
        return list(self.sessions.values())

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        self.inbox.setdefault(session.id, []).append(text)
        if self.transport is None:
            return False
        await self.transport.request(
            "POST",
            f"/session/{session.vendor_session_id}/prompt_async",
            json={"parts": [{"type": "text", "text": text}]},
        )
        return True

    async def respond_permission(self, session: HarnessSession, request_id: str, decision: str) -> bool:
        if self.transport is None:
            return False
        response = "allow" if decision in {"allow", "once", "always"} else "deny"
        await self.transport.request(
            "POST",
            f"/session/{session.vendor_session_id}/permissions/{request_id}",
            json={"response": response},
        )
        return True

    async def apply_overlay(self, session: HarnessSession, overlay) -> bool:
        if self.transport is None:
            return False
        diff = overlay.diff
        patch: dict[str, Any] = {}
        if diff.system_instructions:
            patch["instructions"] = diff.system_instructions
        if diff.model:
            patch["model"] = diff.model
        if diff.permission_policy:
            patch["permission"] = diff.permission_policy
        if not patch:
            return True
        await self.transport.request("PATCH", "/config", json=patch)
        return True

    def ingest_hook(self, payload: dict) -> HarnessSession:
        vendor_id = str(payload.get("session_id") or payload.get("id") or uuid4().hex[:12])
        session_id = f"opencode:{vendor_id}"
        existing = self.sessions.get(session_id)
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.OPENCODE,
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
            harness_type=HarnessType.OPENCODE,
            session_id=session.id,
            event_type=EventType.STATUS,
            message_delta=message,
        )

    def normalize_sse(self, session: HarnessSession, payload: dict) -> HarnessEvent:
        kind = str(payload.get("type") or payload.get("event") or "status")
        mapping = {
            "message.updated": EventType.AGENT_RESPONSE,
            "session.idle": EventType.STOP,
            "session.deleted": EventType.SESSION_END,
            "permission.asked": EventType.PERMISSION_REQUEST,
            "file.edited": EventType.FILE_EDIT,
        }
        return HarnessEvent(
            event_id=uuid4().hex,
            ts=datetime.now(timezone.utc),
            harness_type=HarnessType.OPENCODE,
            session_id=session.id,
            event_type=mapping.get(kind, EventType.STATUS),
            message_delta=str(payload.get("text") or payload.get("message") or kind),
            metadata={"sse_type": kind, "replay": False},
        )
