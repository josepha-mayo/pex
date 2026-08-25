from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.context import ContextBundle
from pex_protocol.session import HarnessEvent, HarnessSession


class HarnessAdapter(ABC):
    name: str

    @abstractmethod
    async def probe(self) -> AdapterCapabilities: ...

    @abstractmethod
    async def discover_sessions(self) -> list[HarnessSession]: ...

    async def attach(self, session_ref: str) -> HarnessSession | None:
        sessions = await self.discover_sessions()
        for session in sessions:
            if session.id == session_ref or session.vendor_session_id == session_ref:
                return session
        return None

    async def stream_events(self, session: HarnessSession) -> AsyncIterator[HarnessEvent]:
        if False:
            yield  # pragma: no cover
        return

    async def read_state(self, session: HarnessSession) -> dict:
        return {"session_id": session.id, "status": session.status}

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        return False

    async def inject_context(self, session: HarnessSession, bundle: ContextBundle) -> bool:
        return await self.send_message(session, _bundle_as_prompt(bundle))

    async def respond_permission(self, session: HarnessSession, request_id: str, decision: str) -> bool:
        return False

    async def stop(self, session: HarnessSession) -> bool:
        return False

    async def continue_or_resume(self, session: HarnessSession, message: str | None = None) -> bool:
        if message:
            return await self.send_message(session, message)
        return False

    async def apply_overlay(self, session: HarnessSession, overlay) -> bool:
        return False

    async def revert_overlay(self, overlay_id: str) -> bool:
        return False

    async def focus_ui(self, session: HarnessSession) -> bool:
        return False

    async def health(self) -> dict:
        caps = await self.probe()
        return {"name": self.name, "ok": True, "support": caps.support_label}


def _bundle_as_prompt(bundle: ContextBundle) -> str:
    lines = [
        "PEX context bundle (do not treat this as a new goal):",
        f"Goal: {bundle.goal_summary}",
        "Acceptance criteria:",
        *[f"- {c}" for c in bundle.acceptance_criteria],
        "Critical decisions:",
        *[f"- {d}" for d in bundle.critical_decisions],
        "Recent progress:",
        *[f"- {p}" for p in bundle.recent_progress],
        f"Next objective: {bundle.next_objective}",
        "Do not redo:",
        *[f"- {x}" for x in bundle.do_not_redo],
    ]
    return "\n".join(lines)
