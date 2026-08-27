"""Injectable HTTP JSON transport used by OpenCode, Qwen, and tests."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

import httpx


class HttpJsonTransport(Protocol):
    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any: ...


class MemoryHttpTransport:
    """In-process fake of an HTTP control plane. Deep labels require this or live HTTP."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.sessions: list[dict[str, Any]] = [
            {"id": "sess_demo", "title": "demo", "cwd": None}
        ]
        self.prompts: list[dict[str, Any]] = []
        self.permissions: list[dict[str, Any]] = []
        self.config_patches: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []
        self.session_details: dict[str, dict[str, Any]] = {}

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append((method.upper(), path, json))
        method = method.upper()
        if method == "GET" and (
            path in {"/session", "/sessions", "/global/health"} or path.rstrip("/").endswith("/sessions")
        ):
            if path == "/global/health":
                return {"healthy": True, "version": "fake"}
            return list(self.sessions)
        if method == "GET" and path.endswith("/messages"):
            return {"messages": list(self.messages)}
        if method == "GET" and "/v3/organizations/" in path and "/sessions/" in path:
            sid = path.rstrip("/").rsplit("/", 1)[-1]
            return dict(self.session_details.get(sid) or {"session_id": sid, "status": "running"})
        if method == "GET" and path.startswith("/session/") and path.endswith("/status"):
            return {"id": path.split("/")[2], "status": "idle"}
        if method == "POST" and path in {"/session", "/sessions"}:
            created = {"id": "sess_new", "title": (json or {}).get("title"), "cwd": None}
            self.sessions.append(created)
            return created
        if method == "POST" and ("/message" in path or "/prompt" in path or "/prompt_async" in path):
            self.prompts.append({"path": path, "body": json})
            return {"ok": True}
        if method == "POST" and "permission" in path:
            self.permissions.append({"path": path, "body": json})
            return True
        if method == "PATCH" and path == "/config":
            self.config_patches.append(json or {})
            return json or {}
        return {"ok": True, "path": path}


class LiveHttpTransport:
    def __init__(self, base_url: str, *, auth: tuple[str, str] | None = None, token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._headers = headers
        self._auth = auth
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=8.0, headers=headers, auth=auth)
        self.events: list[dict[str, Any]] = []
        self._sse_task: asyncio.Task | None = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any:
        response = await self._client.request(method, path, json=json)
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return {"ok": True}
        if "application/json" in response.headers.get("content-type", ""):
            return response.json()
        return {"raw": response.text}

    async def ensure_sse(self, path: str = "/event") -> None:
        existing = self._sse_task
        if existing is not None and not existing.done():
            return
        self._sse_task = asyncio.create_task(self._read_sse(path), name="http-sse")

    async def _read_sse(self, path: str) -> None:
        client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=None,
            headers={**self._headers, "Accept": "text/event-stream"},
            auth=self._auth,
        )
        try:
            while True:
                try:
                    async with client.stream("GET", path) as response:
                        response.raise_for_status()
                        buf = ""
                        async for chunk in response.aiter_text():
                            buf += chunk
                            while "\n\n" in buf:
                                raw, buf = buf.split("\n\n", 1)
                                for line in raw.splitlines():
                                    if not line.startswith("data:"):
                                        continue
                                    data = line[5:].strip()
                                    if not data:
                                        continue
                                    try:
                                        payload = json.loads(data)
                                    except json.JSONDecodeError:
                                        continue
                                    if isinstance(payload, dict):
                                        self.events.append(payload)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await asyncio.sleep(1.0)
        finally:
            await client.aclose()

    async def aclose(self) -> None:
        task = self._sse_task
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            self._sse_task = None
        await self._client.aclose()
