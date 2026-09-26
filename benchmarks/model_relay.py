"""Bounded controller IPC for pinned non-streaming model requests.

No ambient provider settings or credentials are loaded. A trusted controller
explicitly configures the backend; harness HTTP/streaming integration and backend
receipts remain separate requirements before any benchmark can become eligible.
"""
from __future__ import annotations

import asyncio
import hashlib
import math
import os
import re
import socket
import stat
import struct
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads

SCHEMA = "pex.model-relay.v1"
MAX_REQUEST_BYTES = 262_144
MAX_RESPONSE_BYTES = 1_048_576
_BODY_FIELDS = {"model", "messages", "max_tokens", "temperature", "tools", "tool_choice", "stream"}


class PinnedChatBackend:
    """Controller-only HTTPS client. One POST, no redirects or automatic retry."""

    def __init__(
        self, *, endpoint: str, model: str, api_key: str, timeout: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or not parsed.path.endswith("/chat/completions")):
            raise ValueError("backend requires a fixed HTTPS chat-completions endpoint")
        if not isinstance(model, str) or not model or len(model) > 256:
            raise ValueError("backend requires a bounded pinned model")
        if (not isinstance(api_key, str) or not api_key or len(api_key) > 16_384
                or any(ord(char) < 33 or ord(char) > 126 for char in api_key)):
            raise ValueError("backend requires a bounded credential")
        if type(timeout) not in {int, float} or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("backend timeout must be finite and between zero and 60 seconds")
        self.endpoint, self.model, self.timeout = endpoint, model, timeout
        self._api_key, self._transport = api_key, transport

    async def __call__(self, body: dict) -> dict:
        if (not isinstance(body, dict) or set(body) - _BODY_FIELDS
                or body.get("model") != self.model or body.get("stream", False) is not False
                or type(body.get("max_tokens")) is not int
                or not 1 <= body["max_tokens"] <= 16_384):
            raise ValueError("backend request does not match its pinned contract")
        encoded = strict_json_dumps(body).encode("utf-8")
        if len(encoded) > MAX_REQUEST_BYTES:
            raise ValueError("backend request exceeds bound")
        transport = self._transport or httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        async with httpx.AsyncClient(
            transport=transport, timeout=self.timeout, follow_redirects=False, trust_env=False,
        ) as client:
            async with client.stream(
                "POST", self.endpoint, content=encoded,
                headers={"Authorization": f"Bearer {self._api_key}",
                         "Content-Type": "application/json", "Accept": "application/json",
                         "Accept-Encoding": "identity"},
            ) as response:
                if response.status_code != 200:
                    raise RuntimeError("backend did not return a successful response")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise ValueError("backend compression is outside the bounded wire contract")
                data = bytearray()
                async for chunk in response.aiter_raw():
                    if len(data) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise ValueError("backend response exceeds bound")
                    data.extend(chunk)
        result = strict_json_loads(data)
        if not isinstance(result, dict) or result.get("model") != self.model:
            raise ValueError("backend response does not bind the pinned model")
        choices = result.get("choices")
        if not isinstance(choices, list) or not 1 <= len(choices) <= 16 or any(
            not isinstance(choice, dict) or not isinstance(choice.get("message"), dict)
            or choice["message"].get("role") != "assistant" for choice in choices
        ):
            raise ValueError("backend response has no bounded assistant completion")
        return result


class PinnedModelRelay:
    def __init__(
        self, *, model: str, max_calls: int, deadline: float,
        backend: Callable[[dict], Awaitable[dict]],
    ) -> None:
        if not isinstance(model, str) or not model or len(model) > 256:
            raise ValueError("relay requires a bounded pinned model")
        if type(max_calls) is not int or not 1 <= max_calls <= 1000:
            raise ValueError("relay call budget must be between 1 and 1000")
        if type(deadline) not in {int, float} or not math.isfinite(deadline):
            raise ValueError("relay requires a finite absolute deadline")
        self.model, self.max_calls, self.deadline = model, max_calls, deadline
        self.backend = backend
        self.audit: list[dict] = []
        self._ids: set[str] = set()
        self._connections = 0

    def _validate(self, payload: object) -> tuple[str, dict]:
        if not isinstance(payload, dict) or set(payload) != {"schema", "request_id", "body"}:
            raise ValueError("invalid request envelope")
        request_id = payload["request_id"]
        if payload["schema"] != SCHEMA or not isinstance(request_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}", request_id,
        ):
            raise ValueError("invalid request identity")
        body = payload["body"]
        if (not isinstance(body, dict) or set(body) - _BODY_FIELDS
                or body.get("model") != self.model):
            raise ValueError("request does not match pinned model contract")
        if body.get("stream", False) is not False:
            raise ValueError("streaming is not implemented")
        messages = body.get("messages")
        if not isinstance(messages, list) or not 1 <= len(messages) <= 256:
            raise ValueError("request requires bounded messages")
        for message in messages:
            if not isinstance(message, dict) or message.get("role") not in {
                "system", "user", "assistant", "tool",
            } or set(message) - {"role", "content", "tool_calls", "tool_call_id", "name"}:
                raise ValueError("invalid model message")
        tokens = body.get("max_tokens")
        if type(tokens) is not int or not 1 <= tokens <= 16_384:
            raise ValueError("request requires a bounded output token limit")
        return request_id, body

    async def dispatch(self, raw: bytes) -> dict:
        request_id = None
        try:
            if not 0 < len(raw) <= MAX_REQUEST_BYTES:
                raise ValueError("request frame exceeds bound")
            request_id, body = self._validate(strict_json_loads(raw))
        except (ValueError, TypeError, RecursionError, UnicodeError):
            return {"schema": SCHEMA, "ok": False, "error": "invalid_request"}
        # No await before reservation: concurrent connections cannot exceed the
        # shared call cap or dispatch the same request ID twice.
        if request_id in self._ids:
            error = "duplicate_request"
        elif len(self._ids) >= self.max_calls:
            error = "call_budget_exhausted"
        elif time.perf_counter() >= self.deadline:
            error = "deadline_expired"
        else:
            error = None
        if error:
            return {"schema": SCHEMA, "request_id": request_id, "ok": False, "error": error}
        self._ids.add(request_id)
        receipt = {"request_id": request_id, "request_sha256": hashlib.sha256(raw).hexdigest(),
                   "status": "reserved"}
        self.audit.append(receipt)
        try:
            response = await asyncio.wait_for(
                self.backend(body), timeout=max(0, self.deadline - time.perf_counter()),
            )
            if not isinstance(response, dict):
                raise ValueError("invalid backend response")
            result = {"schema": SCHEMA, "request_id": request_id, "ok": True, "body": response}
            encoded = strict_json_dumps(result).encode("utf-8")
            if len(encoded) > MAX_RESPONSE_BYTES:
                raise ValueError("backend response exceeds bound")
            receipt.update(status="completed", response_sha256=hashlib.sha256(encoded).hexdigest())
            return result
        except asyncio.CancelledError:
            receipt["status"] = "cancelled_uncertain"
            raise
        except Exception:
            # An attempted call consumes its reservation even on lost response.
            # Never reveal provider exception text or retry a potentially billed call.
            receipt["status"] = "failed_uncertain"
            return {"schema": SCHEMA, "request_id": request_id, "ok": False,
                    "error": "backend_failed_uncertain"}

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._connections >= 4:
            writer.close()
            return
        self._connections += 1
        try:
            timeout = min(5, max(0, self.deadline - time.perf_counter()))
            header = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
            size = struct.unpack("!I", header)[0]
            if not 0 < size <= MAX_REQUEST_BYTES:
                return
            raw = await asyncio.wait_for(
                reader.readexactly(size),
                timeout=min(5, max(0, self.deadline - time.perf_counter())),
            )
            result = await self.dispatch(raw)
            encoded = strict_json_dumps(result).encode("utf-8")
            writer.write(struct.pack("!I", len(encoded)) + encoded)
            await asyncio.wait_for(writer.drain(), timeout=1)
        except (TimeoutError, OSError, asyncio.IncompleteReadError):
            pass
        finally:
            self._connections -= 1
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=1)
            except (TimeoutError, OSError):
                pass

    async def listen(self, path: Path) -> asyncio.AbstractServer:
        parent = path.parent.resolve(strict=True)
        metadata = parent.stat()
        if parent != path.parent.absolute() or metadata.st_uid != os.getuid() or (
            stat.S_IMODE(metadata.st_mode) != 0o700
        ) or path.exists() or path.is_symlink():
            raise ValueError("relay requires a fresh socket in an owner-only unlinked directory")
        listener = socket.socket(socket.AF_UNIX)
        try:
            listener.bind(str(path))
            path.chmod(0o600)
            listener.listen(4)
            listener.setblocking(False)
            return await asyncio.start_unix_server(self.handle, sock=listener)
        except BaseException:
            listener.close()
            raise
