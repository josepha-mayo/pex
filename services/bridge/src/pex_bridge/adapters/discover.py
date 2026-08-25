"""Loopback discovery of harnesses the user already started — desktops first, then CLIs."""

from __future__ import annotations

import shutil

import httpx

from pex_bridge.adapters.codex_bin import resolve_codex_bin
from pex_bridge.adapters.connect import annotate
from pex_bridge.adapters.desktop import list_desktop_apps
from pex_bridge.adapters.grok_build_bin import resolve_grok_build
from pex_bridge.adapters.hermes_bin import resolve_hermes

PROBES = (
    ("opencode", "http://127.0.0.1:4096/global/health"),
    ("opencode", "http://127.0.0.1:4097/global/health"),
    ("opencode", "http://127.0.0.1:4096/session"),
    ("qwen", "http://127.0.0.1:4170/global/health"),
    ("qwen", "http://127.0.0.1:4170/session"),
)


async def probe_local_harnesses(timeout: float = 0.35) -> list[dict]:
    found: dict[str, dict] = {item["name"]: item for item in list_desktop_apps()}
    async with httpx.AsyncClient(timeout=timeout) as client:
        for name, url in PROBES:
            if name in found:
                continue
            try:
                response = await client.get(url)
            except Exception:
                continue
            if response.status_code < 500:
                found[name] = {
                    "name": name,
                    "kind": "http",
                    "base_url": url.rsplit("/", 1)[0],
                }
    if "codex" not in found:
        binary = resolve_codex_bin()
        if binary:
            found["codex"] = {
                "name": "codex",
                "kind": "stdio",
                "connect": "app-server-stdio",
                "bin": binary,
                "surface": "codex app-server --listen stdio://",
            }
    if "grok_build" not in found:
        grok_bin = resolve_grok_build()
        if grok_bin:
            found["grok_build"] = {
                "name": "grok_build",
                "kind": "cli",
                "connect": "acp-stdio",
                "bin": grok_bin,
                "surface": (
                    "Grok Build CLI. Official ACP: `grok agent stdio`. "
                    "One-shot headless: `grok -p`. Not Grok Bot. Do not spawn unless asked."
                ),
            }
    if "hermes" not in found:
        hermes_bin = resolve_hermes()
        if hermes_bin:
            found["hermes"] = {
                "name": "hermes",
                "kind": "acp",
                "connect": "acp-stdio",
                "bin": hermes_bin,
                "surface": "hermes acp (CLI). Do not launch Hermes desktop.",
            }
    if "opencode" not in found:
        opencode_bin = shutil.which("opencode")
        if opencode_bin:
            found["opencode"] = {
                "name": "opencode",
                "kind": "cli",
                "connect": "http",
                "bin": opencode_bin,
                "surface": "OpenCode CLI. Deep only after `opencode serve` HTTP attach. Do not treat a TUI process as the API.",
            }
    return [annotate(item) for item in found.values()]
