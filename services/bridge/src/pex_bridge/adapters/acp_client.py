"""Agent Client Protocol (JSON-RPC over a transport).

Used for Cursor CLI `agent acp`. Transports are injectable so tests never spawn
the real binary. On this machine the PATH `agent` command is Grok's binary, not
Cursor — callers must pass an explicit Cursor agent path.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any, Protocol


PermissionHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class AcpTransport(Protocol):
    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None: ...

    async def close(self) -> None: ...


class FakeAcpTransport:
    """In-process ACP stand-in for tests and demos."""

    def __init__(self) -> None:
        self.prompts: list[dict[str, Any]] = []
        self.sessions: list[dict[str, Any]] = [
            {"sessionId": "cursor-acp-demo", "cwd": "C:/proj", "title": "demo"}
        ]
        self.closed = False
        self.initialized = False
        self.authed = False
        self.loaded: list[str] = []
        self.permission_replies: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        if method == "initialize":
            self.initialized = True
            return {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True, "sessionCapabilities": {"list": {}}},
                "authMethods": [{"id": "cursor_login"}],
            }
        if method == "authenticate":
            self.authed = True
            return {}
        if method == "session/list":
            return {"sessions": list(self.sessions)}
        if method == "session/load":
            self.loaded.append(str(params.get("sessionId")))
            return {"sessionId": params.get("sessionId")}
        if method == "session/new":
            sid = "cursor-acp-new"
            self.sessions.append({"sessionId": sid, "cwd": params.get("cwd")})
            return {"sessionId": sid}
        if method == "session/prompt":
            self.prompts.append(params)
            return {"stopReason": "end_turn"}
        if method == "session/cancel":
            return {}
        raise KeyError(method)

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


class StdioAcpTransport:
    def __init__(self, command: list[str]) -> None:
        self.command = command
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id = 1
        self._reader_task: asyncio.Task | None = None
        self.on_permission: PermissionHandler | None = None
        self.events: list[dict[str, Any]] = []

    async def start(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                fut = self._pending.pop(int(msg["id"]), None)
                if fut and not fut.done():
                    if "error" in msg:
                        fut.set_exception(RuntimeError(str(msg["error"])))
                    else:
                        fut.set_result(msg.get("result") or {})
                continue
            if msg.get("method") == "session/request_permission" and "id" in msg:
                decision = {"outcome": {"outcome": "selected", "optionId": "allow-once"}}
                if self.on_permission:
                    decision = await self.on_permission(msg.get("params") or {})
                await self._write({"jsonrpc": "2.0", "id": msg["id"], "result": decision})
                continue
            if msg.get("method"):
                self.events.append(msg)

    async def _write(self, payload: dict[str, Any]) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._proc is None:
            await self.start()
        req_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut
        await self._write({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
        return await asyncio.wait_for(fut, timeout=30)

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self._write({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self._proc:
            self._proc.kill()
            await self._proc.wait()
            self._proc = None


class AcpClient:
    def __init__(self, transport: AcpTransport) -> None:
        self.transport = transport
        self.ready = False

    async def handshake(self) -> dict[str, Any]:
        init = await self.transport.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                },
                "clientInfo": {"name": "pex", "title": "PEX", "version": "0.1.0"},
            },
        )
        methods = {
            str(item.get("id"))
            for item in (init.get("authMethods") or [])
            if isinstance(item, dict) and item.get("id")
        }
        method_id = None
        if "cursor_login" in methods:
            method_id = "cursor_login"
        elif "cached_token" in methods:
            method_id = "cached_token"
        elif "xai.api_key" in methods and os.environ.get("XAI_API_KEY"):
            method_id = "xai.api_key"
        if method_id:
            params: dict[str, Any] = {"methodId": method_id}
            if method_id in {"cached_token", "xai.api_key"}:
                params["_meta"] = {"headless": True}
            await self.transport.request("authenticate", params)
        elif methods:
            raise RuntimeError("ACP authenticate required but no usable method")
        self.ready = True
        return init

    async def list_sessions(self) -> list[dict[str, Any]]:
        if not self.ready:
            await self.handshake()
        try:
            result = await self.transport.request("session/list", {})
        except Exception:
            return []
        return list(result.get("sessions") or [])

    async def load(self, session_id: str) -> dict[str, Any]:
        if not self.ready:
            await self.handshake()
        return await self.transport.request("session/load", {"sessionId": session_id})

    async def prompt(self, session_id: str, text: str) -> dict[str, Any]:
        if not self.ready:
            await self.handshake()
        return await self.transport.request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]},
        )
