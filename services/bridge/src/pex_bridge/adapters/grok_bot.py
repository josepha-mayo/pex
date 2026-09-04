"""Grok Bot desktop. Separate from Grok Build CLI. Observe-only."""

from __future__ import annotations

from pex_protocol.capabilities import AdapterSupportLabel, ControlGranularity
from pex_protocol.enums import HarnessType
from pex_protocol.session import HarnessSession

from pex_bridge.adapters.base import session_binding_matches
from pex_bridge.adapters.desktop import desktop_process_running, upsert_desktop_observe_session
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
                "process. No official local control API; label stays observe-only."
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        upsert_desktop_observe_session(
            self.sessions,
            harness=HarnessType.GROK_BOT,
            process="Grok Bot.exe",
        )
        return list(self.sessions.values())

    async def probe(self):
        caps = await super().probe()
        running = desktop_process_running("Grok Bot.exe")
        return caps.model_copy(
            update={
                "observe_session_status": running,
                "focus_ui": running,
                "trust_level": 0.45 if running else 0.0,
                "support_label": (
                    AdapterSupportLabel.OBSERVE_ONLY if running else AdapterSupportLabel.UNAVAILABLE
                ),
                "notes": caps.notes
                + (" Process heartbeat confirmed." if running else " Process is not running."),
            }
        )

    async def focus_ui(self, session: HarnessSession) -> bool:
        from pex_bridge.adapters.winfocus import focus_harness

        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.GROK_BOT
        ):
            return False
        return focus_harness("grok_bot")
