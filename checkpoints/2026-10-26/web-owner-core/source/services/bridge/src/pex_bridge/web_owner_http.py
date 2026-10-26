"""Standalone auth-only ASGI surface, NOT a deployable owner app.

Nothing mounts this factory into the bridge. It exposes only login/session/logout,
never private data, provider settings, adapters, MCP/hooks, or WebSockets. It does
not import bridge startup, inspect credentials/environment, or trust forwarded
headers. A future server must separately establish trustworthy HTTPS scope; this
module cannot attest a server/proxy's scheme provenance or TLS configuration.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from pex_bridge.web_owner_auth import OwnerAuthError, OwnerSessions, RawHeaders

MAX_LOGIN_BODY_BYTES = 1024
MAX_BODY_EVENTS = 128
BODY_TIMEOUT_SECONDS = 5.0
_ROUTES = {
    "/owner/auth/login": "POST",
    "/owner/auth/session": "GET",
    "/owner/auth/logout": "POST",
}
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class _ClientDisconnected(Exception):
    pass


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("non-JSON constant")


def _login_secret(body: bytes) -> str:
    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=_invalid_constant,
        )
        if not isinstance(value, dict) or set(value) != {"owner_secret"}:
            raise ValueError
        supplied = value["owner_secret"]
        if not isinstance(supplied, str) or len(supplied) != 43:
            raise ValueError
    except (ValueError, UnicodeError, RecursionError):
        raise OwnerAuthError(400, "owner_login_body_invalid") from None
    return supplied


def _body_headers(headers: RawHeaders, *, limit: int, login: bool) -> int | None:
    values: dict[bytes, list[bytes]] = {}
    for name, value in headers:
        values.setdefault(name.lower(), []).append(value)
    if b"content-encoding" in values:
        raise OwnerAuthError(415, "owner_content_encoding_denied")
    if login:
        types = values.get(b"content-type", [])
        if len(types) != 1 or types[0].lower() not in {
            b"application/json",
            b"application/json; charset=utf-8",
        }:
            raise OwnerAuthError(415, "owner_content_type_denied")
    lengths = values.get(b"content-length", [])
    if not lengths:
        return None
    if (
        len(lengths) != 1
        or b"transfer-encoding" in values
        or not 1 <= len(lengths[0]) <= 10
        or not lengths[0].isdigit()
    ):
        raise OwnerAuthError(400, "owner_content_length_invalid")
    length = int(lengths[0])
    if length > limit:
        raise OwnerAuthError(413, "owner_body_too_large")
    return length


async def _read_body(receive: Receive, *, limit: int, declared: int | None) -> bytes:
    body = bytearray()
    try:
        async with asyncio.timeout(BODY_TIMEOUT_SECONDS):
            for _ in range(MAX_BODY_EVENTS):
                message = await receive()
                if message.get("type") == "http.disconnect":
                    raise _ClientDisconnected
                if message.get("type") != "http.request":
                    raise OwnerAuthError(400, "owner_body_invalid")
                chunk = message.get("body", b"")
                more = message.get("more_body", False)
                if not isinstance(chunk, bytes) or type(more) is not bool:
                    raise OwnerAuthError(400, "owner_body_invalid")
                if len(body) + len(chunk) > limit:
                    raise OwnerAuthError(413, "owner_body_too_large")
                body.extend(chunk)
                if not more:
                    if declared is not None and len(body) != declared:
                        raise OwnerAuthError(400, "owner_content_length_invalid")
                    return bytes(body)
    except TimeoutError:
        raise OwnerAuthError(408, "owner_body_timeout") from None
    raise OwnerAuthError(413, "owner_body_event_limit")


async def _respond(
    send: Send, status: int, payload: dict[str, Any], *, set_cookie: str | None = None
) -> None:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(body)).encode("ascii")),
        (b"cache-control", b"no-store"),
        (b"pragma", b"no-cache"),
        (b"x-content-type-options", b"nosniff"),
        (b"referrer-policy", b"no-referrer"),
        (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
    ]
    if set_cookie is not None:
        headers.append((b"set-cookie", set_cookie.encode("ascii")))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class _OwnerAuthApp:
    def __init__(self, sessions: OwnerSessions) -> None:
        self._sessions = sessions

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        kind = scope.get("type")
        if kind == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if kind == "lifespan":
            # No application startup, environment/credential reads or resources.
            while True:
                event = await receive()
                if event["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif event["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
                else:
                    raise ValueError("unsupported owner lifespan event")
        if kind != "http":
            raise ValueError("unsupported owner ASGI scope")
        try:
            if scope.get("scheme") != "https":
                raise OwnerAuthError(403, "owner_https_required")
            headers = scope.get("headers", [])
            method = scope.get("method", "")
            # Before any request body or credential is read. The eventual core
            # call checks again after awaits/configuration changes.
            self._sessions.check_request_boundary(headers, origin_required=method != "GET")
            if scope.get("query_string", b""):
                raise OwnerAuthError(400, "owner_query_denied")
            path = scope.get("path", "")
            if path not in _ROUTES or scope.get("raw_path", path.encode("ascii")) != path.encode(
                "ascii"
            ):
                raise OwnerAuthError(404, "owner_route_denied")
            if method != _ROUTES[path]:
                raise OwnerAuthError(405, "owner_method_denied")
            login = path == "/owner/auth/login"
            if not login:
                self._sessions.authorize(method, headers)
            declared = _body_headers(
                headers, limit=MAX_LOGIN_BODY_BYTES if login else 0, login=login
            )
            body = await _read_body(
                receive, limit=MAX_LOGIN_BODY_BYTES if login else 0, declared=declared
            )
            if login:
                result = self._sessions.login(headers, _login_secret(body))
                payload = {
                    "authenticated": True,
                    "principal_id": "web-owner",
                    "csrf_token": result.csrf_token,
                    "expires_in_seconds": result.expires_in_seconds,
                }
                cookie = result.set_cookie
            elif path == "/owner/auth/session":
                status = self._sessions.session_status(headers)
                payload = {
                    "authenticated": True,
                    "principal_id": status.principal_id,
                    "csrf_token": status.csrf_token,
                    "expires_in_seconds": status.expires_in_seconds,
                }
                cookie = None
            else:
                cookie = self._sessions.logout(headers)
                payload = {"authenticated": False}
        except _ClientDisconnected:
            return
        except OwnerAuthError as exc:
            await _respond(send, exc.status_code, {"error": exc.code})
            return
        # No await separates the final session check/action from entering send.
        # This factory grants no private-data or delayed write authority.
        await _respond(send, 200, payload, set_cookie=cookie)


def create_web_owner_auth_app(sessions: OwnerSessions) -> _OwnerAuthApp:
    """Explicit injection only: no defaults, automatic mounting or real secrets.

    The complete route inventory is three exact paths. There are no automatic
    docs/schema endpoints, slash redirects, CORS handling or fallback routes.
    """
    if type(sessions) is not OwnerSessions:
        raise ValueError("owner sessions must be explicitly constructed")
    return _OwnerAuthApp(sessions)
