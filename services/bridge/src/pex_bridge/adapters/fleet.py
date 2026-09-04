"""Registered but unresolved harness targets.

These entries remain visible in the product registry but expose no observation
or control surface until a provider-specific integration is implemented.
"""

from __future__ import annotations

from pex_protocol.capabilities import AdapterCapabilities, AdapterSupportLabel, ControlGranularity
from pex_protocol.enums import HarnessType
from pex_protocol.session import HarnessSession

from pex_bridge.adapters.base import HarnessAdapter


class DeclaredAdapter(HarnessAdapter):
    accepts_hooks = False

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
            control_granularity=self._granularity,
            trust_level=0.0,
            support_label=AdapterSupportLabel.UNAVAILABLE,
            notes=(
                self.notes
                + f" Intended classification: {self.label.value}."
                + " No authenticated provider-specific adapter surface is implemented."
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        return list(self.sessions.values())

    def ingest_hook(self, payload: dict) -> HarnessSession:
        _ = payload
        raise RuntimeError(f"{self.name} has no verified hook integration")

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        _ = (session, text, attachments)
        return False


def fleet() -> dict[str, DeclaredAdapter]:
    return {
        # Claude, Kimi, Hermes, OMP, OpenCode, Qwen, Devin, Grok Build, Grok Bot are first-class.
        "pi": DeclaredAdapter(
            "pi",
            HarnessType.PI,
            label=AdapterSupportLabel.BASIC,
            observe=True,
            message=False,
            notes="Pi emits tool events. No session message API yet; do not fake control.",
        ),
        "prime": DeclaredAdapter(
            "prime",
            HarnessType.PRIME,
            label=AdapterSupportLabel.EXPERIMENTAL,
            observe=True,
            notes=(
                "Inspect Prime Intellect prime-agent runtime; use extension/session APIs "
                "when present."
            ),
        ),
        "zcode": DeclaredAdapter(
            "zcode",
            HarnessType.ZCODE,
            label=AdapterSupportLabel.EXPERIMENTAL,
            notes=(
                "Ambiguous public name. Bound to the user's actual ZCode harness once "
                "identified. No proprietary scrape."
            ),
        ),
        "deepseek": DeclaredAdapter(
            "deepseek",
            HarnessType.DEEPSEEK,
            label=AdapterSupportLabel.EXPERIMENTAL,
            notes=(
                "Resolve the exact first-party or user-selected DeepSeek harness before "
                "claiming control."
            ),
        ),
        # Qwen is first-class in AdapterRegistry (HTTP daemon).
    }
