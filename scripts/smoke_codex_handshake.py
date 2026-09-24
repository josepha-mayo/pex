"""Check the installed Codex App Server connection without starting a model turn."""

from __future__ import annotations

import asyncio

from pex_bridge.adapters.codex import CodexStdioTransport
from pex_bridge.adapters.codex_bin import resolve_codex_bin


async def smoke() -> None:
    binary = resolve_codex_bin()
    if not binary:
        raise RuntimeError("Codex executable is unavailable")

    transport = CodexStdioTransport(binary)
    try:
        async with asyncio.timeout(15):
            await transport.ensure_ready()
            listed = await transport.request(
                "thread/list", {"limit": 1, "useStateDbOnly": True}
            )
        threads = listed.get("data", listed.get("threads")) if isinstance(listed, dict) else None
        if not transport.initialized or not isinstance(threads, list):
            raise RuntimeError("Codex App Server did not confirm thread listing")
        print("Codex App Server handshake passed; no model turn started")
    finally:
        await transport.close()


if __name__ == "__main__":
    asyncio.run(smoke())
