from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pex_protocol.overlay import Overlay

MAX_ACTIVE_OVERLAYS = 64
MAX_DISABLED_TOOLS = 128
MAX_PLUGIN_STRING_CHARS = 128
MAX_SYSTEM_INSTRUCTIONS_CHARS = 32_768
_SUPPORTED_METADATA_KEYS = {"phase", "pin", "fingerprint_overlay"}


def compile_overlay_runtime(
    overlays: list[Overlay],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compile durable session overlays into the narrow OpenCode plugin contract."""
    now = now or datetime.now(UTC)
    active = [
        item
        for item in overlays
        if item.applied_at is not None
        and item.reverted_at is None
        and not item.promoted
        and not item.is_expired(now)
    ]
    active.sort(key=lambda item: (_timestamp(item.applied_at), item.id))
    if len(active) > MAX_ACTIVE_OVERLAYS:
        raise ValueError("OpenCode overlay runtime exceeds 64 active overlays")

    system_blocks: list[str] = []
    disabled_tools: set[str] = set()
    items: list[dict[str, Any]] = []
    for overlay in active:
        if len(overlay.id) > MAX_PLUGIN_STRING_CHARS:
            raise ValueError("OpenCode overlay id exceeds the plugin contract")
        diff = overlay.diff
        if any(
            value is not None
            for value in (
                diff.tools_enabled,
                diff.mcp_servers,
                diff.model,
                diff.reasoning_effort,
                diff.permission_policy,
            )
        ) or set(diff.extra) - _SUPPORTED_METADATA_KEYS:
            raise ValueError("OpenCode overlay contains unsupported runtime fields")
        instructions = (diff.system_instructions or "").strip()
        phase = str(diff.extra.get("phase") or "").strip()
        pin = str(diff.extra.get("pin") or "").strip()
        block = [instructions] if instructions else []
        if phase:
            block.append(f"Current PEX work phase: {phase}.")
        if pin:
            block.append(f"Pinned reproduction or evidence: {pin}")
        if block:
            system_blocks.append("\n".join(block))
        for raw_tool in diff.tools_disabled or []:
            tool = str(raw_tool).strip()
            if not tool:
                continue
            if len(tool) > MAX_PLUGIN_STRING_CHARS:
                raise ValueError("OpenCode disabled tool name exceeds the plugin contract")
            disabled_tools.add(tool)
        if len(disabled_tools) > MAX_DISABLED_TOOLS:
            raise ValueError("OpenCode overlay runtime exceeds 128 disabled tools")
        items.append(
            {
                "id": overlay.id,
                "expires_at": overlay.expires_at.isoformat() if overlay.expires_at else None,
            }
        )

    compiled_instructions = "\n\n".join(system_blocks)
    if len(compiled_instructions) > MAX_SYSTEM_INSTRUCTIONS_CHARS:
        raise ValueError("OpenCode overlay instructions exceed the plugin contract")

    return {
        "active": bool(active),
        "scope": "session",
        "overlay_ids": [item.id for item in active],
        "system_instructions": compiled_instructions,
        "disabled_tools": sorted(disabled_tools, key=str.casefold),
        "overlays": items,
    }


def _timestamp(value: datetime | None) -> float:
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()
