"""Qwen Code via official `qwen serve` HTTP + SSE daemon.

Deep only when a transport is attached *and* events can be pumped.
Documented routes: POST /session, POST /session/:id/prompt,
GET /session/:id/events, POST /permission/:requestId. Default daemon port 4170.
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


class QwenAdapter(HarnessAdapter):
    name = "qwen"

    def __init__(self, transport: HttpJsonTransport | None = None) -> None:
        self.transport = transport
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.hooks: list[dict] = []
        self._pump_task: asyncio.Task | None = None

    def attach_transport(self, transport: HttpJsonTransport) -> None:
        self.transport = transport

    def _pumping(self) -> bool:
        task = self._pump_task
        return task is not None and not task.done()

    async def probe(self) -> AdapterCapabilities:
        connected = self.transport is not None
        deep = connected and self._pumping()
        label = (
            AdapterSupportLabel.DEEP
            if deep
            else AdapterSupportLabel.STRONG
            if connected
            else AdapterSupportLabel.UNAVAILABLE
        )
        return AdapterCapabilities(
            observe_messages=deep,
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
            control_granularity=ControlGranularity.EVENT if deep else ControlGranularity.SESSION,
            trust_level=0.88 if deep else 0.7 if connected else 0.0,
            support_label=label,
            notes=(
                "Official surface: `qwen serve` HTTP+SSE "
                "(POST /session, POST /session/:id/prompt, GET /session/:id/events, POST /permission/:requestId). "
                + (
                    "SSE pump running."
                    if deep
                    else "Transport attached; Strong until the SSE pump is started."
                    if connected
                    else "No live daemon; label stays Unavailable."
                )
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
        if self.transport is None:
            return False
        try:
            await self.transport.request(
                "POST",
                f"/session/{session.vendor_session_id}/prompt",
                json={"prompt": text},
            )
        except Exception:
            return False
        self.inbox.setdefault(session.id, []).append(text)
        return True

    async def respond_permission(self, session: HarnessSession, request_id: str, decision: str) -> bool:
        if self.transport is None:
            return False
        try:
            await self.transport.request(
                "POST",
                f"/permission/{request_id}",
                json={"decision": decision, "sessionId": session.vendor_session_id},
            )
        except Exception:
            return False
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

    def _vendor_id(self, payload: dict) -> str | None:
        for key in ("sessionID", "sessionId", "session_id", "id"):
            value = payload.get(key)
            if isinstance(value, str) and value and not value.startswith("evt_"):
                if key == "id":
                    continue
                return value
        props = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
        for key in ("sessionID", "sessionId", "session_id"):
            value = props.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _session_for(self, payload: dict) -> HarnessSession:
        vendor_id = self._vendor_id(payload) or next(iter(self.sessions.values()), None)
        if isinstance(vendor_id, HarnessSession):
            return vendor_id
        vendor_id = vendor_id or "unknown"
        session_id = f"qwen:{vendor_id}"
        existing = self.sessions.get(session_id)
        if existing:
            return existing
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.QWEN,
            vendor_session_id=vendor_id,
            status=SessionStatus.WORKING,
            last_activity=datetime.now(timezone.utc),
        )
        self.sessions[session_id] = session
        return session

    def normalize_sse(self, session: HarnessSession, payload: dict) -> HarnessEvent:
        kind = str(payload.get("type") or payload.get("event") or "status")
        mapping = {
            "message.updated": EventType.AGENT_RESPONSE,
            "message.part.updated": EventType.AGENT_RESPONSE,
            "assistant": EventType.AGENT_RESPONSE,
            "session.idle": EventType.STOP,
            "session.deleted": EventType.SESSION_END,
            "permission.asked": EventType.PERMISSION_REQUEST,
            "file.edited": EventType.FILE_EDIT,
        }
        text = payload.get("text") or payload.get("message") or kind
        if isinstance(text, dict):
            text = text.get("text") or kind
        return HarnessEvent(
            event_id=str(payload.get("id") or uuid4().hex),
            ts=datetime.now(timezone.utc),
            harness_type=HarnessType.QWEN,
            session_id=session.id,
            project_id=session.project_id,
            event_type=mapping.get(kind, EventType.STATUS),
            phase=EventPhase.TERMINAL if kind in {"session.idle", "session.deleted"} else EventPhase.AFTER,
            message_delta=str(text),
            metadata={"sse_type": kind, "replay": False},
        )

    async def pump_into_pipeline(self, ingest) -> None:
        seen = 0
        while True:
            try:
                transport = self.transport
                if transport is None:
                    await asyncio.sleep(0.25)
                    continue
                try:
                    await self.discover_sessions()
                except Exception:
                    pass
                ensure = getattr(transport, "ensure_sse", None)
                if ensure is not None:
                    vendor = next(
                        (session.vendor_session_id for session in self.sessions.values() if session.vendor_session_id),
                        None,
                    )
                    await ensure(f"/session/{vendor}/events" if vendor else "/event")
                events = getattr(transport, "events", [])
                for payload in events[seen:]:
                    if not isinstance(payload, dict):
                        continue
                    kind = str(payload.get("type") or "")
                    if kind in {"server.connected", "server.heartbeat"}:
                        continue
                    session = self._session_for(payload)
                    event = self.normalize_sse(session, payload)
                    await ingest(event, session)
                seen = len(events)
                await asyncio.sleep(0.05)
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
            name="qwen-pipeline-pump",
        )
        return self._pump_task
