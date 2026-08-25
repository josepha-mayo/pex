"""Attach live official transports from settings. Never invent Deep without this."""

from __future__ import annotations

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.codex import CodexStdioTransport
from pex_bridge.adapters.codex_bin import resolve_codex_bin
from pex_bridge.adapters.http_json import LiveHttpTransport
from pex_bridge.config import Settings


async def attach_from_settings(adapters: AdapterRegistry, settings: Settings) -> list[str]:
    attached: list[str] = []
    if settings.opencode_url:
        adapters.opencode.attach_transport(LiveHttpTransport(settings.opencode_url))
        attached.append("opencode")
    if settings.qwen_url:
        adapters.qwen.attach_transport(
            LiveHttpTransport(settings.qwen_url, token=settings.qwen_token)
        )
        attached.append("qwen")
    if settings.devin_url and settings.devin_token:
        adapters.devin.attach_transport(
            LiveHttpTransport(settings.devin_url, token=settings.devin_token),
            org_id=settings.devin_org_id,
        )
        attached.append("devin")
    if settings.codex_attach:
        from pathlib import Path

        binary = None
        if settings.codex_bin and Path(settings.codex_bin).is_file():
            binary = settings.codex_bin
        else:
            binary = resolve_codex_bin()
        if binary:
            adapters.codex.attach_transport(CodexStdioTransport(binary))
            attached.append("codex")
    if settings.cursor_attach:
        from pex_bridge.adapters.cursor_hooks import install_user_hooks

        install_user_hooks()
        attached.append("cursor")
    return attached
