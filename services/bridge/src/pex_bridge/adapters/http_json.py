"""Injectable HTTP JSON transport used by OpenCode, Qwen, and tests."""

from __future__ import annotations

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
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=8.0, headers=headers, auth=auth)

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

    async def aclose(self) -> None:
        await self._client.aclose()
