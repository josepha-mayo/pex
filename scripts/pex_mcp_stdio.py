"""Stdio MCP shim: expose a running PEX bridge's ``/mcp/`` server to MCP
clients that only support local (stdio) servers.

``opencode serve`` connects remote MCP servers but does not register their
tools into sessions (verified on 1.18.32 and 1.19.0); local MCP servers do
register. Pointing the worker's ``opencode.json`` at this shim puts the
same scoped PEX tool surface on a transport the worker actually uses — the
shim only forwards JSON-RPC, so every read/scope check still runs on the
bridge.

When ``--token-file`` points at a file that exists, each ``tools/call`` opens
a fresh connection carrying ``Authorization: Bearer <token>`` — the demo
mint writes the file after the session exists, so a shim spawned at server
start picks the credential up lazily. ``tools/list`` stays on the anonymous
connection: the tool surface itself is public read metadata.

Usage (as an MCP ``type: "local"`` command):

    python scripts/pex_mcp_stdio.py --url http://127.0.0.1:7420/mcp/
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import mcp.types as types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server


@asynccontextmanager
async def _remote_session(url: str, token_file: Path | None):
    """One streamable-http session; Bearer auth only if the file exists."""
    token = None
    if token_file is not None and token_file.is_file():
        token = token_file.read_text(encoding="utf-8").strip() or None
    headers = {"Authorization": f"Bearer {token}"} if token else None
    async with (
        streamablehttp_client(url, headers=headers) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session


async def _serve(url: str, token_file: Path | None) -> None:
    async with (
        streamablehttp_client(url) as (read, write, _),
        ClientSession(read, write) as remote,
        stdio_server() as (local_read, local_write),
    ):
        await remote.initialize()
        server: Server = Server("pex-stdio-bridge")

        @server.list_tools()
        async def list_tools() -> list[types.Tool]:
            return (await remote.list_tools()).tools

        @server.call_tool()
        async def call_tool(name: str, arguments: dict) -> types.CallToolResult:
            # Forward the whole result: PEX tools emit structured_output, so
            # dropping structuredContent would fail the client's validation.
            if token_file is not None and token_file.is_file():
                async with _remote_session(url, token_file) as authed:
                    return await authed.call_tool(name, arguments)
            return await remote.call_tool(name, arguments)

        await server.run(local_read, local_write, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="bridge /mcp/ endpoint")
    parser.add_argument(
        "--token-file",
        default=None,
        help="optional file whose contents become the Bearer token per call",
    )
    args = parser.parse_args()
    asyncio.run(_serve(args.url, Path(args.token_file) if args.token_file else None))


if __name__ == "__main__":
    main()
