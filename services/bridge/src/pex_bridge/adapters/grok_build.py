"""Grok Build CLI. Not Grok Bot.

Official surfaces (docs.x.ai/build):
- TUI: `grok`
- Headless one-shot: `grok -p` with `--output-format plain|json|streaming-json`
- ACP: `grok agent stdio` (JSON-RPC on stdin/stdout)

Deep only after a live `grok agent stdio` handshake succeeds.
"""

from pex_protocol.enums import HarnessType

from pex_bridge.adapters.acp_harness import AcpHarnessAdapter


class GrokBuildAdapter(AcpHarnessAdapter):
    name = "grok_build"
    harness_type = HarnessType.GROK_BUILD
    notes_base = (
        "Grok Build CLI (`grok agent stdio` for ACP; `grok -p` for one-shot headless). "
        "Separate from Grok Bot desktop. Deep only after a live ACP handshake."
    )
