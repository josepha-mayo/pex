from __future__ import annotations

from pex_bridge.adapters.base import HarnessAdapter
from pex_bridge.adapters.claude_code import ClaudeCodeAdapter
from pex_bridge.adapters.codex import CodexAdapter
from pex_bridge.adapters.cursor import CursorAdapter
from pex_bridge.adapters.devin import DevinAdapter
from pex_bridge.adapters.fleet import DeclaredAdapter, fleet
from pex_bridge.adapters.grok_bot import GrokBotAdapter
from pex_bridge.adapters.grok_build import GrokBuildAdapter
from pex_bridge.adapters.acp_harness import HermesAdapter, KimiAdapter, OmpAdapter
from pex_bridge.adapters.opencode import OpenCodeAdapter
from pex_bridge.adapters.qwen import QwenAdapter
from pex_bridge.adapters.synthetic import SyntheticAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self.synthetic = SyntheticAdapter()
        self.cursor = CursorAdapter()
        self.codex = CodexAdapter()
        self.opencode = OpenCodeAdapter()
        self.qwen = QwenAdapter()
        self.devin = DevinAdapter()
        self.grok_build = GrokBuildAdapter()
        self.grok_bot = GrokBotAdapter()
        self.claude_code = ClaudeCodeAdapter()
        self.kimi = KimiAdapter()
        self.hermes = HermesAdapter()
        self.omp = OmpAdapter()
        self.named: dict[str, DeclaredAdapter] = fleet()
        self._by_name: dict[str, HarnessAdapter] = {
            self.synthetic.name: self.synthetic,
            self.cursor.name: self.cursor,
            self.codex.name: self.codex,
            self.opencode.name: self.opencode,
            self.qwen.name: self.qwen,
            self.devin.name: self.devin,
            self.grok_build.name: self.grok_build,
            self.grok_bot.name: self.grok_bot,
            self.claude_code.name: self.claude_code,
            self.kimi.name: self.kimi,
            self.hermes.name: self.hermes,
            self.omp.name: self.omp,
            **self.named,
        }

    def bind(self, name: str, adapter: HarnessAdapter) -> None:
        self._by_name[name] = adapter
        if name == "codex":
            self.codex = adapter  # type: ignore[assignment]
        elif name == "cursor":
            self.cursor = adapter  # type: ignore[assignment]

    def get(self, name: str) -> HarnessAdapter | None:
        return self._by_name.get(name)

    def for_session(self, session_id: str) -> HarnessAdapter | None:
        prefix = session_id.split(":", 1)[0]
        aliases = {
            "claude": "claude_code",
            "oh-my-pi": "omp",
            "grokbuild": "grok_build",
            "grokbot": "grok_bot",
            "prime-agent": "prime",
            "kimi-code": "kimi",
            "qwen-code": "qwen",
        }
        prefix = aliases.get(prefix, prefix)
        if prefix == "cursor":
            return self.cursor
        if prefix == "synthetic":
            return self.synthetic
        if prefix == "codex":
            return self.codex
        return self._by_name.get(prefix)

    def all(self) -> list[HarnessAdapter]:
        return list(self._by_name.values())

    REQUIRED_HARNESSES = (
        "cursor",
        "codex",
        "claude_code",
        "devin",
        "grok_bot",
        "grok_build",
        "pi",
        "opencode",
        "hermes",
        "omp",
        "prime",
        "zcode",
        "kimi",
        "deepseek",
        "qwen",
    )
