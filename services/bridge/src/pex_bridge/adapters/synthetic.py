from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pex_protocol.capabilities import AdapterCapabilities, AdapterSupportLabel, ControlGranularity
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.base import HarnessAdapter


class SyntheticAdapter(HarnessAdapter):
    """In-process harness used for tests, demos, and M0 acceptance."""

    name = "synthetic"

    def __init__(self) -> None:
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.permissions: dict[str, list[dict]] = {}
        self.overlays: dict[str, list[str]] = {}

    def seed_session(
        self,
        vendor_id: str = "synth-1",
        project_id: str = "demo",
        cwd: str | None = None,
        goal_id: str | None = None,
    ) -> HarnessSession:
        session = HarnessSession(
            id=f"synthetic:{vendor_id}",
            harness_type=HarnessType.SYNTHETIC,
            vendor_session_id=vendor_id,
            project_id=project_id,
            goal_id=goal_id,
            cwd=cwd,
            status=SessionStatus.WORKING,
            last_activity=datetime.now(timezone.utc),
        )
        self.sessions[session.id] = session
        self.inbox.setdefault(session.id, [])
        return session

    def emit(
        self,
        session: HarnessSession,
        event_type: EventType,
        **kwargs,
    ) -> HarnessEvent:
        return HarnessEvent(
            event_id=uuid4().hex,
            ts=datetime.now(timezone.utc),
            harness_type=HarnessType.SYNTHETIC,
            session_id=session.id,
            project_id=session.project_id,
            event_type=event_type,
            phase=kwargs.pop("phase", EventPhase.DURING),
            **kwargs,
        )

    async def probe(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            observe_messages=True,
            observe_thought_events=True,
            observe_tool_calls=True,
            observe_file_edits=True,
            observe_shell=True,
            observe_context_compaction=True,
            observe_tokens=True,
            observe_permissions=True,
            observe_session_status=True,
            send_message=True,
            inject_context=True,
            approve=True,
            deny=True,
            start=True,
            stop=True,
            resume=True,
            fork=True,
            summarize=True,
            modify_config=True,
            modify_system_instructions=True,
            modify_tools=True,
            modify_mcp=False,
            modify_model=True,
            modify_reasoning_effort=True,
            focus_ui=True,
            control_granularity=ControlGranularity.EVENT,
            trust_level=1.0,
            support_label=AdapterSupportLabel.DEEP,
            notes="In-process test/demo adapter with full control surface.",
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        return list(self.sessions.values())

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        self.inbox.setdefault(session.id, []).append(text)
        session.status = SessionStatus.WORKING
        session.last_activity = datetime.now(timezone.utc)
        return True

    async def respond_permission(self, session: HarnessSession, request_id: str, decision: str) -> bool:
        self.permissions.setdefault(session.id, []).append(
            {"request_id": request_id, "decision": decision}
        )
        return True

    async def continue_or_resume(self, session: HarnessSession, message: str | None = None) -> bool:
        text = message or "PEX: continue. Acceptance criteria are not yet evidenced."
        return await self.send_message(session, text)

    async def apply_overlay(self, session: HarnessSession, overlay) -> bool:
        self.overlays.setdefault(session.id, []).append(getattr(overlay, "id", str(overlay)))
        return True

    async def revert_overlay(self, overlay_id: str) -> bool:
        return True

    async def focus_ui(self, session: HarnessSession) -> bool:
        return True
