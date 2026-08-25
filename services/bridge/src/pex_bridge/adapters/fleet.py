"""Named harness adapters with honest capability labels.

Each adapter encodes the official surface we will deepen. None pretend to be
Deep without a live protocol. Inbox + optional HTTP/process hooks let tests
and later live probes share one contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pex_protocol.capabilities import AdapterCapabilities, AdapterSupportLabel, ControlGranularity
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.base import HarnessAdapter


class DeclaredAdapter(HarnessAdapter):
    def __init__(
        self,
        name: str,
        harness_type: HarnessType,
        *,
        label: AdapterSupportLabel,
        notes: str,
        observe: bool = False,
        message: bool = False,
        approve: bool = False,
        overlay: bool = False,
        granularity: ControlGranularity = ControlGranularity.SESSION,
    ) -> None:
        self.name = name
        self.harness_type = harness_type
        self.label = label
        self.notes = notes
        self._observe = observe
        self._message = message
        self._approve = approve
        self._overlay = overlay
        self._granularity = granularity
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.hooks: list[dict] = []

    async def probe(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            observe_messages=self._observe,
            observe_tool_calls=self._observe,
            observe_session_status=self._observe,
            send_message=self._message,
            inject_context=self._message,
            approve=self._approve,
            deny=self._approve,
            modify_config=self._overlay,
            control_granularity=self._granularity,
            trust_level=0.7 if self.label == AdapterSupportLabel.STRONG else 0.35 if self._observe else 0.0,
            support_label=self.label,
            notes=self.notes,
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        return list(self.sessions.values())

    def ingest_hook(self, payload: dict) -> HarnessSession:
        vendor_id = str(
            payload.get("session_id")
            or payload.get("conversation_id")
            or payload.get("id")
            or uuid4().hex[:12]
        )
        session_id = f"{self.name}:{vendor_id}"
        existing = self.sessions.get(session_id)
        session = HarnessSession(
            id=session_id,
            harness_type=self.harness_type,
            vendor_session_id=vendor_id,
            cwd=payload.get("cwd") or (payload.get("workspace_roots") or [None])[0],
            status=SessionStatus.WORKING,
            last_activity=datetime.now(timezone.utc),
            goal_id=existing.goal_id if existing else None,
            metadata={"hook": payload.get("hook_event_name") or payload.get("type")},
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

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        if not self._message:
            return False
        self.inbox.setdefault(session.id, []).append(text)
        return True


def fleet() -> dict[str, DeclaredAdapter]:
    return {
        # Claude, Kimi, Hermes, OMP, OpenCode, Qwen, Devin, Grok Build, Grok Bot are first-class.
        "pi": DeclaredAdapter(
            "pi",
            HarnessType.PI,
            label=AdapterSupportLabel.BASIC,
            observe=True,
            message=True,
            notes="Pi extension/package to emit tool events. No permission popups by design; policy intercepts tools.",
        ),
        "prime": DeclaredAdapter(
            "prime",
            HarnessType.PRIME,
            label=AdapterSupportLabel.EXPERIMENTAL,
            observe=True,
            notes="Inspect Prime Intellect prime-agent runtime; use extension/session APIs when present.",
        ),
        "zcode": DeclaredAdapter(
            "zcode",
            HarnessType.ZCODE,
            label=AdapterSupportLabel.EXPERIMENTAL,
            notes="Ambiguous public name. Bound to the user's actual ZCode harness once identified. No proprietary scrape.",
        ),
        "deepseek": DeclaredAdapter(
            "deepseek",
            HarnessType.DEEPSEEK,
            label=AdapterSupportLabel.EXPERIMENTAL,
            notes="Resolve the exact first-party or user-selected DeepSeek harness before claiming control.",
        ),
        # Qwen is first-class in AdapterRegistry (HTTP daemon).
    }
