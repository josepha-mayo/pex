from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from pex_protocol.capabilities import (
    AdapterCapabilities,
    AdapterSupportLabel,
    ControlGranularity,
    PermissionResponseMode,
)
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.base import (
    AdapterMessageResult,
    HarnessAdapter,
    bounded_adapter_id,
    bounded_adapter_text,
    session_binding_matches,
)

MAX_SYNTHETIC_RECORDS = 10_000


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
        vendor_id = bounded_adapter_id(vendor_id, field="synthetic session id")
        if len(self.sessions) >= 1_024 and f"synthetic:{vendor_id}" not in self.sessions:
            raise ValueError("synthetic session safety bound reached")
        session = HarnessSession(
            id=f"synthetic:{vendor_id}",
            harness_type=HarnessType.SYNTHETIC,
            vendor_session_id=vendor_id,
            project_id=project_id,
            goal_id=goal_id,
            cwd=cwd,
            status=SessionStatus.WORKING,
            last_activity=datetime.now(UTC),
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
        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.SYNTHETIC
        ):
            raise ValueError("synthetic event session binding mismatch")
        event_id = uuid4().hex
        turn_number = len(self.inbox.get(session.id, []))
        turn_id = f"syn-turn-{turn_number:04d}" if turn_number else None
        metadata = dict(kwargs.pop("metadata", {}) or {})
        if turn_id is not None:
            metadata["vendor_turn_id"] = turn_id
        return HarnessEvent(
            event_id=event_id,
            ts=datetime.now(UTC),
            harness_type=HarnessType.SYNTHETIC,
            session_id=session.id,
            project_id=session.project_id,
            event_type=event_type,
            phase=kwargs.pop("phase", EventPhase.DURING),
            metadata=metadata,
            raw_event_ref=(
                json.dumps(
                    {
                        "schema": "pex.synthetic-event-ref.v1",
                        "session_id": session.id,
                        "turn_id": turn_id,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                if turn_id is not None
                else None
            ),
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
            permission_response_mode=PermissionResponseMode.ASYNC,
            start=True,
            stop=True,
            resume=True,
            fork=True,
            summarize=False,
            modify_config=True,
            config_scope="session",
            modify_system_instructions=False,
            modify_tools=False,
            modify_mcp=False,
            modify_model=False,
            modify_reasoning_effort=False,
            focus_ui=True,
            control_granularity=ControlGranularity.EVENT,
            trust_level=1.0,
            support_label=AdapterSupportLabel.DEEP,
            notes=(
                "In-process test/demo adapter. Event, message, permission, session seed, "
                "overlay, and isolated lifecycle simulation are implemented."
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        return list(self.sessions.values())

    async def send_message(
        self, session: HarnessSession, text: str, attachments=None
    ) -> bool | AdapterMessageResult:
        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.SYNTHETIC
        ):
            return False
        try:
            cleaned = bounded_adapter_text(text).strip()
        except ValueError:
            return False
        inbox = self.inbox.setdefault(session.id, [])
        if len(inbox) >= MAX_SYNTHETIC_RECORDS:
            return False
        inbox.append(cleaned)
        bound = self.sessions[session.id]
        bound.status = SessionStatus.WORKING
        bound.last_activity = datetime.now(UTC)
        return AdapterMessageResult(
            accepted=True,
            vendor_session_id=session.vendor_session_id,
            vendor_turn_id=f"syn-turn-{len(inbox):04d}",
        )

    async def respond_permission(
        self, session: HarnessSession, request_id: str, decision: str
    ) -> bool:
        if (
            not session_binding_matches(
                self.sessions.get(session.id), session, harness_type=HarnessType.SYNTHETIC
            )
            or decision not in {"allow", "deny"}
        ):
            return False
        try:
            request_id = bounded_adapter_id(request_id, field="permission request id")
        except ValueError:
            return False
        records = self.permissions.setdefault(session.id, [])
        if len(records) >= MAX_SYNTHETIC_RECORDS:
            return False
        records.append(
            {"request_id": request_id, "decision": decision}
        )
        return True

    async def continue_or_resume(
        self, session: HarnessSession, message: str | None = None
    ) -> bool | AdapterMessageResult:
        if not message or not str(message).strip():
            return False
        return await self.send_message(session, message)

    async def start_session(
        self,
        project: str,
        prompt: str,
        config: dict | None = None,
    ) -> HarnessSession | None:
        try:
            project = bounded_adapter_text(project, field="project", max_chars=4_096).strip()
            prompt = bounded_adapter_text(prompt, field="prompt").strip()
        except ValueError:
            return None
        config = config or {}
        session = self.seed_session(
            vendor_id=f"started-{uuid4().hex[:12]}",
            project_id=project,
            cwd=str(config.get("cwd") or project),
            goal_id=str(config.get("goal_id") or "") or None,
        )
        session.metadata.update({"source": "pex_lifecycle", "started_by_pex": True})
        await self.send_message(session, prompt)
        return session

    async def stop(self, session: HarnessSession) -> bool:
        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.SYNTHETIC
        ):
            return False
        bound = self.sessions[session.id]
        bound.status = SessionStatus.STOPPED
        bound.last_activity = datetime.now(UTC)
        return True

    async def fork_or_fresh_handoff(self, session, context_bundle):
        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.SYNTHETIC
        ):
            return None
        child = self.seed_session(
            vendor_id=f"fork-{uuid4().hex[:12]}",
            project_id=session.project_id or "demo",
            cwd=session.cwd,
            goal_id=session.goal_id,
        )
        child.metadata.update(
            {
                "source": "pex_lifecycle",
                "forked_from": session.id,
                "probe": True,
            }
        )
        await self.inject_context(child, context_bundle)
        return child

    async def apply_overlay(self, session: HarnessSession, overlay) -> bool:
        if (
            not session_binding_matches(
                self.sessions.get(session.id), session, harness_type=HarnessType.SYNTHETIC
            )
            or getattr(overlay, "session_id", None) != session.id
        ):
            return False
        records = self.overlays.setdefault(session.id, [])
        if len(records) >= MAX_SYNTHETIC_RECORDS:
            return False
        records.append(getattr(overlay, "id", str(overlay)))
        return True

    async def revert_overlay(self, overlay_id: str, rollback: dict | None = None) -> bool:
        for session_id, overlay_ids in self.overlays.items():
            if overlay_id not in overlay_ids:
                continue
            overlay_ids.remove(overlay_id)
            self.overlays[session_id] = overlay_ids
            return True
        return False

    async def focus_ui(self, session: HarnessSession) -> bool:
        return session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.SYNTHETIC
        )
