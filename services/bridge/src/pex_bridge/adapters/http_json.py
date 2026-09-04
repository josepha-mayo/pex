"""Injectable HTTP JSON transport used by OpenCode, Qwen, and tests."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from pex_bridge.adapters.base import DeliveryUncertainError, bounded_observed_mapping
from pex_bridge.adapters.strict_json import strict_json_loads

MAX_HTTP_RESPONSE_BYTES = 8_388_608
MAX_HTTP_EVENTS = 1_024
MAX_SSE_LINE_CHARS = 1_048_576
MAX_SSE_FRAME_CHARS = 1_048_576
MAX_SSE_STREAMS = 1_024
MAX_HTTP_PATH_CHARS = 8_192
MAX_HTTP_SECRET_CHARS = 8_192


class HttpJsonTransport(Protocol):
    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any: ...


class MemoryHttpTransport:
    """In-process protocol stand-in for deterministic offline adapter tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.sessions: list[dict[str, Any]] = [
            {"id": "sess_demo", "title": "demo", "cwd": "C:/fake"}
        ]
        self.prompts: list[dict[str, Any]] = []
        self.permissions: list[dict[str, Any]] = []
        self.config_patches: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []
        self.session_details: dict[str, dict[str, Any]] = {}
        self.connected_sse_paths: set[str] = set()
        self.forks: list[dict[str, Any]] = []

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append((method.upper(), path, json))
        method = method.upper()
        route = path.split("?", 1)[0]
        if method == "GET" and (
            route in {"/session", "/sessions", "/global/health"}
            or route.rstrip("/").endswith("/sessions")
        ):
            if route == "/global/health":
                return {"healthy": True, "version": "fake"}
            if "/v3/organizations/" in route:
                return {
                    "items": list(self.sessions),
                    "end_cursor": None,
                    "has_next_page": False,
                    "total": len(self.sessions),
                }
            if route.startswith("/workspace/"):
                return {"sessions": list(self.sessions), "nextCursor": None}
            query = path.split("?", 1)[1] if "?" in path else ""
            if "directory=" in query:
                from urllib.parse import parse_qs, unquote

                directory = unquote(parse_qs(query).get("directory", [""])[0])
                return [
                    item
                    for item in self.sessions
                    if str(item.get("cwd") or item.get("directory") or "") == directory
                ]
            return [
                item for item in self.sessions if not item.get("isolated_project")
            ]
        if method == "GET" and path == "/capabilities":
            return {
                "v": 1,
                "workspaceCwd": "C:/fake",
                "features": [
                    "capabilities",
                    "session_list",
                    "session_prompt",
                    "session_events",
                    "session_permission_vote",
                    "permission_mediation",
                ],
            }
        if method == "GET" and route.endswith("/messages"):
            if "/v3/organizations/" in route:
                return {
                    "items": list(self.messages),
                    "end_cursor": None,
                    "has_next_page": False,
                    "total": len(self.messages),
                }
            return {"messages": list(self.messages)}
        if method == "GET" and route.startswith("/session/") and route.endswith("/message"):
            return list(self.messages)
        if method == "GET" and "/v3/organizations/" in route and "/sessions/" in route:
            sid = route.rstrip("/").rsplit("/", 1)[-1]
            return dict(self.session_details.get(sid) or {"session_id": sid, "status": "running"})
        if method == "GET" and path.startswith("/session/") and path.endswith("/status"):
            return {"id": path.split("/")[2], "status": "idle"}
        if method == "POST" and path in {"/session", "/sessions"}:
            created = {"id": "sess_new", "title": (json or {}).get("title"), "cwd": None}
            self.sessions.append(created)
            return created
        if method == "POST" and route.startswith("/session/") and route.endswith("/fork"):
            parent_id = route.rstrip("/").split("/")[2]
            parent = next(
                (
                    item
                    for item in self.sessions
                    if isinstance(item, dict) and item.get("id") == parent_id
                ),
                None,
            )
            created = {
                "id": f"sess_fork_{len(self.sessions)}",
                "title": "fork",
                "cwd": (parent or {}).get("cwd"),
                "parentID": parent_id,
            }
            self.sessions.append(created)
            self.forks.append({"path": path, "body": json, "created": created})
            return created
        if method == "POST" and path.startswith("/session/") and path.endswith("/prompt"):
            self.prompts.append({"path": path, "body": json})
            return {"promptId": f"prompt-{len(self.prompts)}", "lastEventId": None}
        if method == "POST" and (
            "/message" in path or "/prompt" in path or "/prompt_async" in path
        ):
            self.prompts.append({"path": path, "body": json})
            text = ""
            parts = (json or {}).get("parts") if isinstance(json, dict) else None
            if isinstance(parts, list):
                for part in parts:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text = str(part.get("text") or "")
                        break
            if "/prompt_async" in path and text:
                self.messages.append(
                    {
                        "info": {
                            "id": f"msg_prompt_{len(self.prompts)}",
                            "role": "user",
                            "sessionID": route.split("/")[2],
                        },
                        "parts": [{"type": "text", "text": text}],
                    }
                )
            return {"ok": True}
        if method == "POST" and "permission" in path:
            self.permissions.append({"path": path, "body": json})
            return True
        if method == "PATCH" and path == "/config":
            self.config_patches.append(json or {})
            return json or {}
        raise RuntimeError(f"fake transport has no route for {method} {path}")

    async def ensure_sse(self, path: str = "/event") -> None:
        self.connected_sse_paths.add(path)


class LiveHttpTransport:
    def __init__(
        self, base_url: str, *, auth: tuple[str, str] | None = None, token: str | None = None
    ) -> None:
        self.base_url = _validated_base_url(base_url)
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {_validated_secret(token, 'token')}"
        if auth is not None:
            auth = (
                _validated_secret(auth[0], "HTTP username"),
                _validated_secret(auth[1], "HTTP password"),
            )
        self._headers = headers
        self._auth = auth
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=8.0, headers=headers, auth=auth
        )
        self.events: deque[dict[str, Any]] = deque(maxlen=MAX_HTTP_EVENTS)
        self._event_cursor = 0
        self._sse_tasks: dict[str, asyncio.Task] = {}
        self.connected_sse_paths: set[str] = set()

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any:
        path = _validated_request_path(path)
        method = str(method).upper()
        mutating = method not in {"GET", "HEAD", "OPTIONS"}
        request = self._client.build_request(method, path, json=json)
        response: httpx.Response | None = None
        accepted = False
        try:
            response = await self._client.send(request, stream=True)
            response.raise_for_status()
            accepted = True
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_HTTP_RESPONSE_BYTES:
                    raise RuntimeError("HTTP adapter response exceeded the safety bound")
            if response.status_code == 204 or not body:
                return {"ok": True}
            if "application/json" in response.headers.get("content-type", ""):
                return strict_json_loads(bytes(body))
            encoding = response.encoding or "utf-8"
            return {"raw": bytes(body).decode(encoding, errors="replace")}
        except httpx.HTTPStatusError:
            # An explicit HTTP error is a verified rejection, not an uncertain
            # successful mutation.
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if mutating and (accepted or isinstance(exc, httpx.TransportError)):
                raise DeliveryUncertainError(
                    "HTTP mutation delivery is uncertain because its receipt was not verified"
                ) from exc
            raise
        finally:
            if response is not None:
                await response.aclose()

    async def ensure_sse(self, path: str = "/event") -> None:
        path = _validated_request_path(path)
        existing = self._sse_tasks.get(path)
        if existing is not None and not existing.done():
            return
        if len(self._sse_tasks) >= MAX_SSE_STREAMS:
            raise RuntimeError("HTTP SSE stream safety bound reached")
        self._sse_tasks[path] = asyncio.create_task(self._read_sse(path), name="http-sse")

    async def _read_sse(self, path: str) -> None:
        client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=8.0, read=60.0, write=8.0, pool=8.0),
            headers={**self._headers, "Accept": "text/event-stream"},
            auth=self._auth,
        )
        try:
            while True:
                try:
                    async with client.stream("GET", path) as response:
                        response.raise_for_status()
                        self.connected_sse_paths.add(path)
                        data_lines: list[str] = []
                        frame_chars = 0
                        discarding_frame = False
                        async for line in _bounded_sse_lines(response):
                            if line == "":
                                if not discarding_frame:
                                    payload = _decode_sse_data(data_lines, path)
                                    if payload is not None:
                                        self.events.append(payload)
                                        self._event_cursor += 1
                                data_lines = []
                                frame_chars = 0
                                discarding_frame = False
                                continue
                            if discarding_frame:
                                continue
                            frame_chars += len(line)
                            if frame_chars > MAX_SSE_FRAME_CHARS:
                                # A malformed local daemon must not grow the bridge
                                # process without bound while withholding a frame.
                                data_lines = []
                                discarding_frame = True
                                continue
                            if line.startswith("data:"):
                                data_lines.append(line[5:].lstrip(" "))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.connected_sse_paths.discard(path)
                    await asyncio.sleep(1.0)
        finally:
            self.connected_sse_paths.discard(path)
            await client.aclose()

    async def aclose(self) -> None:
        tasks = list(self._sse_tasks.values())
        self._sse_tasks.clear()
        self.connected_sse_paths.clear()
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        await self._client.aclose()

    def events_since(self, cursor: int) -> tuple[int, list[dict[str, Any]], int]:
        """Return retained events after an absolute cursor without unbounded storage."""
        latest = self._event_cursor
        if cursor >= latest:
            return latest, [], 0
        earliest = latest - len(self.events)
        dropped = max(0, earliest - cursor)
        start = max(cursor, earliest) - earliest
        return latest, list(self.events)[start:], dropped


def transport_events_since(
    transport: object,
    cursor: int,
) -> tuple[int, list[dict[str, Any]], int]:
    if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
        raise ValueError("HTTP event cursor must be a non-negative integer")
    reader = getattr(transport, "events_since", None)
    if callable(reader):
        latest, events, dropped = reader(cursor)
        if (
            not isinstance(latest, int)
            or isinstance(latest, bool)
            or latest < cursor
            or not isinstance(dropped, int)
            or isinstance(dropped, bool)
            or dropped < 0
            or not isinstance(events, list)
        ):
            return cursor, [], 0
        retained = [
            cleaned
            for item in events[:MAX_HTTP_EVENTS]
            if (cleaned := bounded_observed_mapping(item)) is not None
        ]
        return latest, retained, dropped
    events = getattr(transport, "events", [])
    if not isinstance(events, list):
        return cursor, [], 0
    latest = len(events)
    earliest = max(0, latest - MAX_HTTP_EVENTS)
    dropped = max(0, earliest - cursor)
    start = max(cursor, earliest)
    retained = [
        cleaned
        for item in events[start:latest]
        if (cleaned := bounded_observed_mapping(item)) is not None
    ]
    return latest, retained, dropped


async def _bounded_sse_lines(response: httpx.Response) -> AsyncIterator[str]:
    """Split a UTF-8 SSE stream without buffering an unbounded unterminated line."""
    pending = ""
    discarding = False
    async for chunk in response.aiter_text():
        cursor = 0
        while cursor < len(chunk):
            newline = chunk.find("\n", cursor)
            if newline < 0:
                if not discarding:
                    pending += chunk[cursor:]
                    if len(pending) > MAX_SSE_LINE_CHARS:
                        pending = ""
                        discarding = True
                break
            if not discarding:
                pending += chunk[cursor:newline]
                if len(pending) <= MAX_SSE_LINE_CHARS:
                    yield pending.removesuffix("\r")
            pending = ""
            discarding = False
            cursor = newline + 1


def _decode_sse_data(data_lines: list[str], path: str) -> dict[str, Any] | None:
    """Decode one SSE frame, including CRLF and multi-line data fields."""
    if not data_lines:
        return None
    data = "\n".join(data_lines).strip()
    if not data:
        return None
    try:
        payload = strict_json_loads(data)
    except (ValueError, RecursionError):
        return None
    if not isinstance(payload, dict):
        return None
    payload = bounded_observed_mapping(payload)
    if payload is None:
        return None
    # Session stream envelopes can omit sessionId. Preserve the exact source
    # route so an adapter can bind rather than guess a different session.
    payload.setdefault("_pex_sse_path", path)
    return payload


def _validated_request_path(path: object) -> str:
    value = str(path or "")
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "#" in value
        or len(value) > MAX_HTTP_PATH_CHARS
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        raise ValueError("HTTP adapter request path is unsafe")
    return value


def _validated_base_url(value: object) -> str:
    raw = str(value or "").strip()
    try:
        parsed = urlparse(raw)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("HTTP adapter base URL is invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or (parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"})
    ):
        raise ValueError("HTTP adapter base URL is unsafe")
    return raw.rstrip("/")


def _validated_secret(value: object, field: str) -> str:
    secret = str(value or "")
    if (
        not secret
        or len(secret) > MAX_HTTP_SECRET_CHARS
        or any(ord(char) < 0x21 or ord(char) > 0x7E for char in secret)
    ):
        raise ValueError(f"{field} must be bounded, non-empty visible ASCII")
    return secret
