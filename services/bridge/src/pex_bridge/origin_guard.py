from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from starlette.responses import Response

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
_TEST_HOSTS = frozenset({"test", "testserver"})


def _trusted_host(value: bytes, *, allow_test_hosts: bool) -> bool:
    if not value or len(value) > 255:
        return False
    try:
        host = value.decode("ascii")
    except UnicodeDecodeError:
        return False
    if host != host.strip() or any(ord(char) < 0x21 or ord(char) == 0x7F for char in host):
        return False

    hostname: str
    port_text = ""
    if host.startswith("["):
        closing = host.find("]")
        if closing < 0 or host[: closing + 1].casefold() != "[::1]":
            return False
        hostname = "[::1]"
        remainder = host[closing + 1 :]
        if remainder:
            if not remainder.startswith(":"):
                return False
            port_text = remainder[1:]
    else:
        if host.count(":") > 1:
            return False
        hostname, separator, port_text = host.partition(":")
        hostname = hostname.casefold()
        allowed = _LOOPBACK_HOSTS | (_TEST_HOSTS if allow_test_hosts else frozenset())
        if hostname not in allowed:
            return False
        if not separator:
            port_text = ""

    if not port_text:
        if host.startswith("["):
            return ":" not in host[host.rfind("]") + 1 :]
        return not host.endswith(":")
    return port_text.isascii() and port_text.isdigit() and 1 <= int(port_text) <= 65_535


class TrustedLoopbackHostMiddleware:
    """Reject DNS-rebinding and malformed Host headers before bridge routing."""

    def __init__(self, app: Any, *, allow_test_hosts: bool = False) -> None:
        self.app = app
        self.allow_test_hosts = allow_test_hosts

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        hosts = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"host"
        ]
        if len(hosts) == 1 and _trusted_host(hosts[0], allow_test_hosts=self.allow_test_hosts):
            await self.app(scope, receive, send)
            return
        if scope.get("type") == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        response = Response(
            content=json.dumps({"detail": "untrusted host"}, separators=(",", ":")),
            status_code=400,
            media_type="application/json",
        )
        await response(scope, receive, send)


class TrustedMutationOriginMiddleware:
    """Reject browser mutations from origins outside the packaged UI allowlist.

    Native hook and CLI clients normally send no Origin header and remain subject
    to their bearer checks. A browser cannot opt out of its Origin header for a
    cross-origin JSON mutation, so an explicit untrusted value fails before any
    route or dependency can mutate state.
    """

    def __init__(self, app: Any, *, allowed_origins: Iterable[str]) -> None:
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("method") not in _MUTATING_METHODS:
            await self.app(scope, receive, send)
            return
        origins = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"origin"
        ]
        trusted = True
        if origins:
            trusted = len(origins) == 1
            try:
                origin = origins[0].decode("ascii")
            except UnicodeDecodeError:
                trusted = False
                origin = ""
            trusted = trusted and origin in self.allowed_origins
        if trusted:
            await self.app(scope, receive, send)
            return
        response = Response(
            content=json.dumps(
                {"detail": "untrusted mutation origin"},
                separators=(",", ":"),
            ),
            status_code=403,
            media_type="application/json",
        )
        await response(scope, receive, send)
