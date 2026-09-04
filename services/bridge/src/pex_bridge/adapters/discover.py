"""Loopback discovery of harnesses the user already started — desktops first, then CLIs."""

from __future__ import annotations

import math
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from pex_bridge.adapters.codex_bin import resolve_codex_bin
from pex_bridge.adapters.connect import annotate
from pex_bridge.adapters.desktop import list_desktop_apps
from pex_bridge.adapters.grok_build_bin import resolve_grok_build
from pex_bridge.adapters.hermes_bin import resolve_hermes
from pex_bridge.adapters.strict_json import strict_json_loads

PROBES = (
    ("opencode", "http://127.0.0.1:4096/global/health", "opencode_health"),
    ("opencode", "http://127.0.0.1:4097/global/health", "opencode_health"),
    ("opencode", "http://127.0.0.1:4096/session", "opencode_sessions"),
    ("qwen", "http://127.0.0.1:4170/capabilities", "qwen_capabilities"),
)

# Prefer a live control surface over process-observe when both are present.
_KIND_PRIORITY = ("http", "stdio", "acp", "cli", "desktop")

MAX_DISCOVERY_RESPONSE_BYTES = 1_048_576


def _resolved_cli(name: str) -> str | None:
    """Return only a concrete executable inventory path, never a PATH token."""

    candidate = shutil.which(name)
    if not candidate:
        return None
    path = Path(candidate)
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return str(resolved) if resolved.is_absolute() and resolved.is_file() else None


def _matches_probe(contract: str, payload: object) -> bool:
    if contract == "opencode_health":
        return isinstance(payload, dict) and payload.get("healthy") is True
    if contract == "opencode_sessions":
        return isinstance(payload, list) and all(isinstance(item, dict) for item in payload)
    if contract == "qwen_capabilities":
        return (
            isinstance(payload, dict)
            and payload.get("v") == 1
            and isinstance(payload.get("features"), list)
            and "session_list" in payload["features"]
        )
    return False


def _has(items: list[dict], name: str, kind: str) -> bool:
    return any(item["name"] == name and item.get("kind") == kind for item in items)


def prefer_attach_match(found: list[dict], name: str, kind: object = None) -> dict | None:
    """Pick a discovered surface.

    An omitted kind prefers HTTP/ACP over desktop observe, except Codex: omitted
    kind never selects isolated App Server stdio. That attach is explicit.
    """

    candidates = [item for item in found if item.get("name") == name]
    if kind:
        return next((item for item in candidates if item.get("kind") == kind), None)
    if name == "codex":
        return next((item for item in candidates if item.get("kind") == "desktop"), None)
    ranked = sorted(
        candidates,
        key=lambda item: (
            _KIND_PRIORITY.index(item["kind"])
            if item.get("kind") in _KIND_PRIORITY
            else len(_KIND_PRIORITY)
        ),
    )
    return ranked[0] if ranked else None


async def probe_local_harnesses(timeout: float = 0.35) -> list[dict]:
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or not 0 < float(timeout) <= 5.0
    ):
        raise ValueError("discovery timeout must be between zero and five seconds")
    items: list[dict] = list(list_desktop_apps())
    async with httpx.AsyncClient(timeout=timeout) as client:
        for name, url, contract in PROBES:
            if _has(items, name, "http"):
                continue
            try:
                async with client.stream("GET", url) as response:
                    if not 200 <= response.status_code < 300:
                        continue
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_DISCOVERY_RESPONSE_BYTES:
                            raise RuntimeError("discovery response exceeded the safety bound")
                payload = strict_json_loads(bytes(body))
            except Exception:
                continue
            if _matches_probe(contract, payload):
                items.append(
                    {
                        "name": name,
                        "kind": "http",
                        "base_url": _origin(url),
                    }
                )
    binary = resolve_codex_bin()
    if binary:
        items.append(
            {
                "name": "codex",
                "kind": "stdio",
                "connect": "app-server-stdio",
                "bin": binary,
                "surface": (
                    "Isolated `codex app-server --listen stdio://`. "
                    "Not ChatGPT.exe. Attach explicitly; do not auto-spawn from the "
                    "desktop process."
                ),
            }
        )
    if not _has(items, "grok_build", "cli") and not _has(items, "grok_build", "acp"):
        grok_bin = resolve_grok_build()
        if grok_bin:
            items.append(
                {
                    "name": "grok_build",
                    "kind": "cli",
                    "connect": "acp-stdio",
                    "bin": grok_bin,
                    "surface": (
                        "Grok Build CLI. Official ACP: `grok agent stdio`. "
                        "One-shot headless: `grok -p`. Not Grok Bot. Do not spawn unless asked."
                    ),
                }
            )
    if not _has(items, "hermes", "acp"):
        hermes_bin = resolve_hermes()
        if hermes_bin:
            items.append(
                {
                    "name": "hermes",
                    "kind": "acp",
                    "connect": "acp-stdio",
                    "bin": hermes_bin,
                    "surface": (
                        "hermes acp (CLI). Lists beside an already-running Hermes desktop. "
                        "Do not launch Hermes to attach."
                    ),
                }
            )
    if not _has(items, "opencode", "cli"):
        opencode_bin = _resolved_cli("opencode")
        if opencode_bin:
            items.append(
                {
                    "name": "opencode",
                    "kind": "cli",
                    "connect": "http",
                    "bin": opencode_bin,
                    "surface": (
                        "OpenCode CLI. Deep only after `opencode serve` HTTP attach. "
                        "A running TUI is listed separately; do not treat it as the API."
                    ),
                }
            )
    if not _has(items, "omp", "acp"):
        omp_bin = _resolved_cli("omp")
        if omp_bin:
            items.append(
                {
                    "name": "omp",
                    "kind": "acp",
                    "connect": "acp-stdio",
                    "bin": omp_bin,
                    "surface": "omp acp (CLI). Do not spawn unless asked.",
                }
            )
    if not _has(items, "kimi", "acp"):
        kimi_bin = _resolved_cli("kimi")
        if kimi_bin:
            items.append(
                {
                    "name": "kimi",
                    "kind": "acp",
                    "connect": "acp-stdio",
                    "bin": kimi_bin,
                    "surface": "kimi acp is available but not attached. Do not spawn unless asked.",
                }
            )
    if not _has(items, "qwen", "cli"):
        qwen_bin = _resolved_cli("qwen")
        if qwen_bin:
            items.append(
                {
                    "name": "qwen",
                    "kind": "cli",
                    "connect": "http",
                    "bin": qwen_bin,
                    "surface": (
                        "Qwen CLI is installed but not attached. `qwen serve` plus a verified "
                        "capability response and session SSE stream is required."
                    ),
                }
            )
    return [annotate(item) for item in items]


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"
