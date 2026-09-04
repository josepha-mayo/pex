"""Small ASGI request-body guard for the local bridge control plane."""

from __future__ import annotations

import json
from collections import deque
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_HTTP_REQUEST_BYTES = 4 * 1024 * 1024
MAX_HTTP_BODY_CHUNKS = 4096


def _reject_nonfinite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _content_types(scope: Scope) -> list[str]:
    return [
        value.decode("ascii", "ignore").split(";", 1)[0].strip().casefold()
        for name, value in scope.get("headers", [])
        if name.lower() == b"content-type"
    ]


class RequestBodyLimitMiddleware:
    """Reject oversized bodies, including chunked requests, before JSON parsing.

    Checking ``Content-Length`` alone is insufficient because a client can omit
    it and stream a chunked body.  This middleware buffers at most the configured
    bound and then replays the original ASGI request messages to FastAPI.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_HTTP_REQUEST_BYTES) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        lengths = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"content-length"
        ]
        expected_length: int | None = None
        if lengths:
            try:
                parsed = [int(value.decode("ascii")) for value in lengths]
            except (UnicodeDecodeError, ValueError):
                await _send_error(send, 400, "invalid Content-Length")
                return
            if any(value < 0 for value in parsed) or len(set(parsed)) != 1:
                await _send_error(send, 400, "invalid Content-Length")
                return
            if parsed[0] > self.max_bytes:
                await _send_error(send, 413, "request body too large")
                return
            expected_length = parsed[0]

        buffered: deque[Message] = deque()
        total = 0
        chunk_count = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk_count += 1
            if chunk_count > MAX_HTTP_BODY_CHUNKS:
                await _send_error(send, 413, "request body has too many chunks")
                return
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                await _send_error(send, 413, "request body too large")
                return
            buffered.append(message)
            if not message.get("more_body", False):
                break
        if expected_length is not None and total != expected_length:
            await _send_error(send, 400, "Content-Length does not match request body")
            return
        content_types = _content_types(scope)
        if len(content_types) > 1:
            await _send_error(send, 400, "invalid Content-Type")
            return
        raw_body = b"".join(message.get("body", b"") for message in buffered)
        json_content_type = bool(content_types) and (
            content_types[0] == "application/json" or content_types[0].endswith("+json")
        )
        headerless_json_object = not content_types and raw_body.lstrip()[:1] in {b"{", b"["}
        if total and (json_content_type or headerless_json_object):
            try:
                json.loads(
                    raw_body.decode("utf-8"),
                    parse_constant=_reject_nonfinite_json_constant,
                    object_pairs_hook=_unique_json_object,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
                await _send_error(send, 400, "invalid JSON body")
                return

        async def replay_receive() -> Message:
            if buffered:
                return buffered.popleft()
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)


async def _send_error(send: Send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}, separators=(",", ":")).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
