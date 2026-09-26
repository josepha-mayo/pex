"""Credential-free chat transport for a controller-owned Unix socket relay."""

from __future__ import annotations

import asyncio
import math
import struct
import uuid

import httpx
from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads

_SCHEMA = "pex.model-relay.v1"
_REQUEST_LIMIT = 262_144
_RESPONSE_LIMIT = 1_048_576


def relay_supervisor_model(*, socket_path: str, model: str, timeout: float = 30):
    """Build PEX's real chat adapter with explicit IPC routing and no ambient key."""
    from pex_supervisor.openai_chat import OpenAIChatModel

    # Validate before constructing the SDK adapter or opening any socket.
    UnixChatRelayTransport(socket_path=socket_path, model=model, timeout=timeout)
    result = OpenAIChatModel(
        model_id=model,
        stream=False,
        params={"max_tokens": 1200, "stream": False},
        client_args={
            "api_key": "pex-relay-no-credential",
            "base_url": "http://pex-relay.invalid/v1",
            "max_retries": 0,
            "timeout": timeout,
        },
        http_client_factory=lambda: httpx.AsyncClient(
            transport=UnixChatRelayTransport(socket_path=socket_path, model=model, timeout=timeout),
            trust_env=False,
            follow_redirects=False,
        ),
    )
    result._pex_provenance = {
        "provider": "controller-relay",
        "model_id": model,
        "auth_mode": "controller-held",
        "generation_api": "chat",
        "base_url": "http://pex-relay.invalid/v1",
    }
    return result


class UnixChatRelayTransport(httpx.AsyncBaseTransport):
    """Map a fixed SDK chat route to framed IPC. SDK callers must set max_retries=0."""

    def __init__(self, *, socket_path: str, model: str, timeout: float = 30) -> None:
        if (
            not isinstance(socket_path, str)
            or not socket_path.startswith("/")
            or "\x00" in socket_path
        ):
            raise ValueError("relay socket must be an absolute Unix path")
        if not isinstance(model, str) or not model or len(model) > 256:
            raise ValueError("relay requires a bounded pinned model")
        if type(timeout) not in {int, float} or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("relay timeout must be finite and bounded")
        self.socket_path, self.model, self.timeout = socket_path, model, timeout

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if (
            request.method != "POST"
            or str(request.url) != "http://pex-relay.invalid/v1/chat/completions"
        ):
            raise httpx.UnsupportedProtocol(
                "relay only supports its fixed chat route", request=request
            )
        request_id = uuid.uuid4().hex
        try:
            body_bytes = bytearray()
            async for chunk in request.stream:
                if len(body_bytes) + len(chunk) > _REQUEST_LIMIT:
                    raise ValueError("request exceeds bound")
                body_bytes.extend(chunk)
            body = strict_json_loads(body_bytes)
            if (
                not isinstance(body, dict)
                or body.get("model") != self.model
                or body.get("stream", False) is not False
            ):
                raise ValueError("request does not match relay model")
            raw = strict_json_dumps(
                {"schema": _SCHEMA, "request_id": request_id, "body": body}
            ).encode()
            if len(raw) > _REQUEST_LIMIT:
                raise ValueError("envelope exceeds bound")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise httpx.RequestError("invalid bounded relay request", request=request) from None

        async def exchange() -> dict:
            reader, writer = await asyncio.open_unix_connection(self.socket_path)
            try:
                writer.write(struct.pack("!I", len(raw)) + raw)
                await writer.drain()
                size = struct.unpack("!I", await reader.readexactly(4))[0]
                if not 0 < size <= _RESPONSE_LIMIT:
                    raise ValueError("response frame exceeds bound")
                response = strict_json_loads(await reader.readexactly(size))
                if (
                    not isinstance(response, dict)
                    or response.get("schema") != _SCHEMA
                    or response.get("request_id") != request_id
                    or response.get("ok") is not True
                    or not isinstance(response.get("body"), dict)
                    or response["body"].get("model") != self.model
                ):
                    raise ValueError("relay did not return a bound completion")
                return response["body"]
            finally:
                writer.close()
                # Closing must not extend a spent inference deadline indefinitely.
                try:
                    await asyncio.wait_for(writer.wait_closed(), timeout=1)
                except (OSError, TimeoutError):
                    pass

        try:
            result = await asyncio.wait_for(exchange(), timeout=self.timeout)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Unknown provider outcomes must never be retried by this transport.
            raise httpx.RequestError(
                "relay completion unavailable; outcome uncertain", request=request
            ) from None
        return httpx.Response(
            200,
            content=strict_json_dumps(result).encode(),
            headers={"Content-Type": "application/json"},
            request=request,
        )
