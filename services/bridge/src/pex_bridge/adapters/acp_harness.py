"""Shared ACP-capable harness adapter.

Kimi (`kimi acp`), Hermes (`hermes acp`), and Oh My Pi (`omp acp`) share ACP.
Grok Build ACP is `grok agent stdio`, not `grok acp`. Deep only after handshake.
STOP inspect comes from official `session/update` idle / end_turn, not a canned hook.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from pex_protocol.capabilities import AdapterCapabilities, AdapterSupportLabel, ControlGranularity
from pex_protocol.enums import EventPhase, EventType, HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.intervention import Intervention
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
        self._pump_task: asyncio.Task | None = None

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
        pumping = self._pump_task is not None and not self._pump_task.done()
        return AdapterCapabilities(
            observe_messages=True,
            observe_tool_calls=True,
            observe_session_status=True,
            send_message=deep,
            inject_context=deep,
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
                + (" session/update pump running." if pumping else " Start the session/update pump to inspect STOP.")
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
        if self.acp is None:
            return False
        try:
            await self.acp.prompt(session.vendor_session_id, text)
        except Exception:
            return False
        self.inbox.setdefault(session.id, []).append(text)
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

    def _params(self, payload: dict) -> dict:
        params = payload.get("params")
        return params if isinstance(params, dict) else {}

    def _session_for(self, payload: dict) -> HarnessSession:
        params = self._params(payload)
        vendor_id = str(
            params.get("sessionId")
            or params.get("session_id")
            or payload.get("sessionId")
            or "unknown"
        )
        session_id = f"{self.name}:{vendor_id}"
        existing = self.sessions.get(session_id)
        if existing:
            return existing
        session = HarnessSession(
            id=session_id,
            harness_type=self.harness_type,
            vendor_session_id=vendor_id,
            status=SessionStatus.WORKING,
            last_activity=datetime.now(timezone.utc),
        )
        self.sessions[session_id] = session
        return session

    def normalize_acp(self, session: HarnessSession, payload: dict) -> HarnessEvent | None:
        method = str(payload.get("method") or "")
        if method != "session/update":
            return None
        params = self._params(payload)
        update = params.get("update") if isinstance(params.get("update"), dict) else params
        kind = str(update.get("sessionUpdate") or update.get("session_update") or "")
        state = str(update.get("state") or "")
        stop = str(update.get("stopReason") or update.get("stop_reason") or "")
        content = update.get("content")
        text = ""
        if isinstance(content, dict):
            text = str(content.get("text") or "")
        elif isinstance(content, str):
            text = content
        if not text:
            text = str(update.get("text") or update.get("title") or stop or kind or state)
        if kind in {"state_update", "stateUpdate"} and (state == "idle" or stop):
            event_type = EventType.STOP
            phase = EventPhase.TERMINAL
        elif kind in {"agent_message_chunk", "agentMessageChunk"}:
            event_type = EventType.AGENT_RESPONSE
            phase = EventPhase.AFTER
        elif kind in {"agent_thought_chunk", "agentThoughtChunk"}:
            event_type = EventType.AGENT_THOUGHT
            phase = EventPhase.DURING
        elif kind in {"tool_call", "toolCall"}:
            event_type = EventType.TOOL_CALL
            phase = EventPhase.DURING
        elif kind in {"tool_call_update", "toolCallUpdate"}:
            status = str(update.get("status") or "")
            event_type = (
                EventType.TOOL_RESULT if status in {"completed", "failed"} else EventType.TOOL_CALL
            )
            phase = EventPhase.AFTER
        else:
            event_type = EventType.STATUS
            phase = EventPhase.AFTER
        return HarnessEvent(
            event_id=str(payload.get("id") or uuid4().hex),
            ts=datetime.now(timezone.utc),
            harness_type=self.harness_type,
            session_id=session.id,
            project_id=session.project_id,
            event_type=event_type,
            phase=phase,
            message_delta=text,
            metadata={
                "acp_method": method,
                "session_update": kind,
                "stop_reason": stop,
                "replay": False,
            },
        )

    async def pump_into_pipeline(self, ingest) -> None:
        seen = 0
        while True:
            try:
                transport = getattr(self.acp, "transport", None) if self.acp is not None else None
                if transport is None:
                    await asyncio.sleep(0.25)
                    continue
                events = getattr(transport, "events", [])
                for payload in events[seen:]:
                    if not isinstance(payload, dict):
                        continue
                    session = self._session_for(payload)
                    event = self.normalize_acp(session, payload)
                    if event is None:
                        continue
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
            name=f"{self.name}-acp-pipeline-pump",
        )
        return self._pump_task


class KimiAdapter(AcpHarnessAdapter):
    name = "kimi"
    harness_type = HarnessType.KIMI
    notes_base = "Official `kimi acp`: initialize, session/new|load|resume|prompt, session/request_permission."


class HermesAdapter(AcpHarnessAdapter):
    name = "hermes"
    harness_type = HarnessType.HERMES
    notes_base = (
        "Official Hermes ACP (`hermes acp`) plus plugin hooks "
        "(pre_tool_call block/approve, pre_llm_call {context} inject, on_session_end observe). "
        "Do not launch Hermes desktop."
    )

    HOOK_EVENT_MAP = {
        "pre_tool_call": EventType.TOOL_CALL,
        "post_tool_call": EventType.TOOL_RESULT,
        "pre_llm_call": EventType.USER_PROMPT,
        "post_llm_call": EventType.AGENT_RESPONSE,
        "on_session_start": EventType.SESSION_START,
        "on_session_end": EventType.STOP,
        "on_session_finalize": EventType.SESSION_END,
        "pre_approval_request": EventType.PERMISSION_REQUEST,
        "subagent_stop": EventType.STOP,
    }

    def __init__(self, acp=None) -> None:
        super().__init__(acp)
        self.pending_context: dict[str, str] = {}

    async def probe(self):
        caps = await super().probe()
        if caps.support_label == AdapterSupportLabel.DEEP:
            return caps
        return caps.model_copy(
            update={
                "send_message": True,
                "inject_context": True,
                "notes": caps.notes
                + " Strong injects via official pre_llm_call {context}. Deep adds ACP session/prompt.",
            }
        )

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        if self.acp is not None:
            ok = await super().send_message(session, text, attachments)
            if ok:
                return True
        cleaned = (text or "").strip()
        if cleaned.startswith("PEX:"):
            return False
        if not cleaned:
            return False
        self.pending_context[session.id] = cleaned
        self.inbox.setdefault(session.id, []).append(cleaned)
        return True

    def normalize_hook(self, payload: dict, session: HarnessSession) -> HarnessEvent:
        hook_name = str(payload.get("hook_event_name") or payload.get("hook") or "unknown")
        args = payload.get("args") if isinstance(payload.get("args"), dict) else None
        text = (
            payload.get("assistant_response")
            or payload.get("user_message")
            or payload.get("text")
            or payload.get("message")
            or payload.get("result")
        )
        return HarnessEvent(
            event_id=uuid4().hex,
            ts=datetime.now(timezone.utc),
            harness_type=HarnessType.HERMES,
            session_id=session.id,
            event_type=self.HOOK_EVENT_MAP.get(hook_name, EventType.STATUS),
            phase=EventPhase.TERMINAL if hook_name in {"on_session_end", "on_session_finalize"} else EventPhase.BEFORE,
            message_delta=str(text) if text else None,
            tool_name=payload.get("tool_name"),
            tool_input=args,
            command=(args or {}).get("command") if args else payload.get("command"),
            metadata={"hook_event_name": hook_name},
        )

    def hook_response(self, session: HarnessSession, payload: dict, intervention: Intervention | None) -> dict:
        hook_name = str(payload.get("hook_event_name") or payload.get("hook") or "")
        if hook_name == "pre_tool_call":
            if intervention and intervention.policy_verdict == PolicyVerdict.DENY:
                return {
                    "action": "block",
                    "message": intervention.diagnosis or "PEX policy deny",
                }
            if intervention and intervention.policy_verdict == PolicyVerdict.ASK_HUMAN:
                return {
                    "action": "approve",
                    "message": intervention.diagnosis or "needs a human decision",
                }
            return {}
        if hook_name == "pre_llm_call":
            context = self.pending_context.pop(session.id, None)
            if not context and intervention and intervention.action_taken in {
                "CONTINUE_SESSION",
                "SEND_NUDGE",
                "REQUEST_VERIFICATION",
            }:
                context = str(intervention.proposed_action.payload.get("text") or intervention.diagnosis or "")
            context = (context or "").strip()
            if context.startswith("PEX:"):
                return {}
            if context:
                return {"context": context}
            return {}
        return {}


class OmpAdapter(AcpHarnessAdapter):
    name = "omp"
    harness_type = HarnessType.OMP
    notes_base = (
        "Oh My Pi official `omp acp` JSON-RPC; session/request_permission gates destructive tools. "
        "STOP inspect from session/update idle with stopReason."
    )
