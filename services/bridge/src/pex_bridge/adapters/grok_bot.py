"""Grok Bot desktop. Separate from Grok Build CLI. Observe-only."""

from __future__ import annotations

from datetime import datetime, timezone

from pex_protocol.capabilities import AdapterSupportLabel, ControlGranularity
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.session import HarnessSession

from pex_bridge.adapters.desktop import running_image_names
from pex_bridge.adapters.fleet import DeclaredAdapter


class GrokBotAdapter(DeclaredAdapter):
    def __init__(self) -> None:
        super().__init__(
            "grok_bot",
            HarnessType.GROK_BOT,
            label=AdapterSupportLabel.OBSERVE_ONLY,
            observe=True,
            granularity=ControlGranularity.SESSION,
            notes=(
                "Grok Bot desktop is not Grok Build. When the app is running we observe the "
                "process. No official control API was found on this machine; label stays observe-only."
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        names = {n.lower() for n in running_image_names()}
        if "grok bot.exe" in names:
            session_id = "grok_bot:desktop"
            existing = self.sessions.get(session_id)
            self.sessions[session_id] = HarnessSession(
                id=session_id,
                harness_type=HarnessType.GROK_BOT,
                vendor_session_id="desktop",
                status=SessionStatus.WORKING,
                last_activity=datetime.now(timezone.utc),
                goal_id=existing.goal_id if existing else None,
                metadata={"source": "desktop", "process": "Grok Bot.exe"},
            )
        return list(self.sessions.values())
