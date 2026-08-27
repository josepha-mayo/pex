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
    items: list[dict] = list(list_desktop_apps())
    seen = {item["name"] for item in items}
    async with httpx.AsyncClient(timeout=timeout) as client:
        for name, url in PROBES:
            if name in seen:
                continue
            try:
                response = await client.get(url)
            except Exception:
                continue
            if response.status_code < 500:
                seen.add(name)
                items.append(
                    {
                        "name": name,
                        "kind": "http",
                        "base_url": url.rsplit("/", 1)[0],
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
                    "Not ChatGPT.exe. Attach explicitly; do not auto-spawn from the desktop process."
                ),
            }
        )
    if "grok_build" not in seen:
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
    if "hermes" not in seen:
        hermes_bin = resolve_hermes()
        if hermes_bin:
            items.append(
                {
                    "name": "hermes",
                    "kind": "acp",
                    "connect": "acp-stdio",
                    "bin": hermes_bin,
                    "surface": "hermes acp (CLI). Do not launch Hermes desktop.",
                }
            )
    if "opencode" not in seen:
        opencode_bin = shutil.which("opencode")
        if opencode_bin:
            items.append(
                {
                    "name": "opencode",
                    "kind": "cli",
                    "connect": "http",
                    "bin": opencode_bin,
                    "surface": "OpenCode CLI. Deep only after `opencode serve` HTTP attach. Do not treat a TUI process as the API.",
                }
            )
    if "omp" not in seen:
        omp_bin = shutil.which("omp")
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
    return [annotate(item) for item in items]
