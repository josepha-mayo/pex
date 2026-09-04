"""Attach live official transports from settings. Never invent Deep without this."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.codex import CodexStdioTransport
from pex_bridge.adapters.codex_bin import resolve_codex_bin
from pex_bridge.adapters.http_json import LiveHttpTransport
from pex_bridge.config import Settings


async def attach_from_settings(adapters: AdapterRegistry, settings: Settings) -> list[str]:
    attached: list[str] = []
    if settings.opencode_url:
        adapters.opencode.attach_transport(
            LiveHttpTransport(
                _loopback_http_origin(settings.opencode_url, "OpenCode"),
                auth=opencode_basic_auth(),
            )
        )
        attached.append("opencode")
    if settings.qwen_url:
        adapters.qwen.attach_transport(
            LiveHttpTransport(
                _loopback_http_origin(settings.qwen_url, "Qwen"),
                token=_bounded_secret(settings.qwen_token),
            )
        )
        attached.append("qwen")
    if settings.devin_url and settings.devin_token:
        org_id = str(settings.devin_org_id or "").strip()
        if (
            not org_id
            or len(org_id) > 256
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in org_id)
        ):
            raise ValueError("PEX_DEVIN_ORG_ID is required and must be at most 256 characters")
        adapters.devin.attach_transport(
            LiveHttpTransport(
                _https_origin(settings.devin_url, "Devin"),
                token=_bounded_secret(settings.devin_token),
            ),
            org_id=org_id,
        )
        attached.append("devin")
    if settings.codex_attach:
        from pathlib import Path

        if settings.codex_bin:
            configured = Path(settings.codex_bin)
            if not configured.is_absolute() or not configured.is_file():
                raise ValueError("PEX_CODEX_BIN must be an existing absolute file")
            binary = str(configured)
        else:
            binary = resolve_codex_bin()
        if binary:
            adapters.codex.attach_transport(CodexStdioTransport(binary))
            attached.append("codex")
    if settings.cursor_attach:
        from pex_bridge.adapters.cursor_hooks import install_user_hooks

        install_user_hooks(mode="observe")
        attached.append("cursor")
    return attached


def _loopback_http_origin(value: str, label: str) -> str:
    parsed = _parse_bare_origin(value, label)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError(f"{label} URL must be a bare loopback HTTP origin")
    return str(value).strip().rstrip("/")


def _https_origin(value: str, label: str) -> str:
    parsed = _parse_bare_origin(value, label)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(f"{label} URL must be a bare HTTPS origin")
    return str(value).strip().rstrip("/")


def _parse_bare_origin(value: str, label: str):
    try:
        parsed = urlparse(str(value or "").strip())
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} URL is malformed") from exc
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError(f"{label} URL must be a bare origin without credentials")
    return parsed


def _bounded_secret(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > 8_192:
        raise ValueError("adapter credential exceeds the safety bound")
    if any(ord(char) < 0x21 or ord(char) > 0x7E for char in cleaned):
        raise ValueError("adapter credential must contain only visible ASCII")
    return cleaned


def opencode_basic_auth(
    username: str | None = None,
    password: str | None = None,
) -> tuple[str, str] | None:
    """Return bounded OpenCode Basic auth from explicit values or its official env."""

    resolved_username = (
        username
        if username is not None
        else os.environ.get("OPENCODE_SERVER_USERNAME") or "opencode"
    ).strip()
    if (
        not resolved_username
        or len(resolved_username) > 256
        or any(ord(char) < 0x21 or ord(char) > 0x7E for char in resolved_username)
    ):
        raise ValueError("OPENCODE_SERVER_USERNAME must be 1 to 256 characters")
    resolved_password = _bounded_secret(
        password if password is not None else os.environ.get("OPENCODE_SERVER_PASSWORD")
    )
    return (resolved_username, resolved_password) if resolved_password else None
