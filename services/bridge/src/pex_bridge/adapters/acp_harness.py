"""Shared ACP-capable harness adapter.

Kimi (`kimi acp`), Hermes (`hermes acp`), and Oh My Pi (`omp acp`) share ACP.
Grok Build ACP is `grok agent stdio`, not `grok acp`. Deep only after handshake.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pex_protocol.capabilities import AdapterCapabilities, AdapterSupportLabel, ControlGranularity
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.acp_client import AcpClient, AcpTransport
from pex_bridge.adapters.base import HarnessAdapter


class AcpHarnessAdapter(HarnessAdapter):
    name = "acp"
    harness_type = HarnessType.UNKNOWN
    notes_base = "ACP JSON-RPC."
    idle_label = AdapterSupportLabel.STRONG

    def __init__(self, acp: AcpClient | None = None) -> None:
        self.acp = acp
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.hooks: list[dict] = []

    def attach_acp(self, transport: AcpTransport) -> None:
        self.acp = AcpClient(transport)

    def attach_transport(self, transport: AcpTransport) -> None:
        self.attach_acp(transport)

    async def probe(self) -> AdapterCapabilities:
        deep = False
        if self.acp is not None:
            try:
                if not self.acp.ready:
                    await self.acp.handshake()
                deep = True
            except Exception:
                deep = False
        return AdapterCapabilities(
            observe_messages=True,
            observe_tool_calls=True,
            observe_session_status=True,
            send_message=True,
            inject_context=True,
            approve=deep,
            deny=deep,
            start=deep,
            resume=True,
            control_granularity=ControlGranularity.EVENT,
            trust_level=0.88 if deep else 0.7,
            support_label=AdapterSupportLabel.DEEP if deep else self.idle_label,
            notes=self.notes_base
            + (
                " ACP handshake succeeded."
                if deep
                else " Hook ingest until a live ACP handshake succeeds."
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        if self.acp is not None:
            try:
                listed = await self.acp.list_sessions()
            except Exception:
                listed = []
            for item in listed:
                vendor_id = str(item.get("sessionId") or "")
                if not vendor_id:
                    continue
                session_id = f"{self.name}:{vendor_id}"
                existing = self.sessions.get(session_id)
                self.sessions[session_id] = HarnessSession(
                    id=session_id,
                    harness_type=self.harness_type,
                    vendor_session_id=vendor_id,
                    cwd=item.get("cwd"),
                    status=SessionStatus.IDLE,
                    last_activity=datetime.now(timezone.utc),
                    goal_id=existing.goal_id if existing else None,
                )
        return list(self.sessions.values())

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        self.inbox.setdefault(session.id, []).append(text)
        if self.acp is not None:
            try:
                await self.acp.prompt(session.vendor_session_id, text)
            except Exception:
                return True
        return True

    def ingest_hook(self, payload: dict) -> HarnessSession:
        vendor_id = str(payload.get("session_id") or payload.get("id") or uuid4().hex[:12])
        session_id = f"{self.name}:{vendor_id}"
        existing = self.sessions.get(session_id)
        session = HarnessSession(
            id=session_id,
            harness_type=self.harness_type,
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
            harness_type=self.harness_type,
            session_id=session.id,
            event_type=EventType.STATUS,
            message_delta=message,
        )


class KimiAdapter(AcpHarnessAdapter):
    name = "kimi"
    harness_type = HarnessType.KIMI
    notes_base = "Official `kimi acp`: initialize, session/new|load|resume|prompt, session/request_permission."


class HermesAdapter(AcpHarnessAdapter):
    name = "hermes"
    harness_type = HarnessType.HERMES
    notes_base = (
        "Official Hermes ACP (`hermes acp`) plus plugin hooks "
        "(pre_tool_call block, pre_llm_call inject)."
    )


class OmpAdapter(AcpHarnessAdapter):
    name = "omp"
    harness_type = HarnessType.OMP
    notes_base = "Oh My Pi official `omp acp` JSON-RPC; session/request_permission gates destructive tools."
