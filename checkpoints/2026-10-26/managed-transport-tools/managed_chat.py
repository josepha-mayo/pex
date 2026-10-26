"""Standalone, offline-qualified candidate. Public live invocation is intentionally denied.

No OpenAI/Strands SDK is used: exact OpenAI-compatible JSON travels over an owned
HTTPX stack. This module is not wired into PEX admission. Private execution is
exercised only with synthetic credentials and MockTransport in its test suite.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import math
import re
import socket
from dataclasses import dataclass, replace
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx

Role = Literal["planner", "verifier"]
_ROLE_SYSTEM = {
    "planner": (
        "You are the PEX supervisor planner. Assess the supplied evidence and propose a "
        "decision. Do not treat worker narration as verified evidence."
    ),
    "verifier": (
        "You are the independent PEX supervisor verifier. Assess the supplied proposal "
        "and evidence. Approve only what the evidence supports."
    ),
}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:@+-]{0,255}\Z")
_HOST = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)
_PATH = re.compile(r"(?:/[A-Za-z0-9_-]+)*/chat/completions\Z")


class Refusal(ValueError):
    """Only a constant safe reason code may be supplied."""


def _integer(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _public_unicast(address) -> bool:
    return (
        address.is_global
        and not any(
            (
                address.is_multicast,
                address.is_unspecified,
                address.is_loopback,
                address.is_link_local,
                address.is_reserved,
                getattr(address, "is_site_local", False),
            )
        )
        and getattr(address, "ipv4_mapped", None) is None
    )


def _canonical_endpoint(value: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= 1024:
        raise Refusal("invalid_endpoint")
    if any(ord(c) <= 32 or ord(c) >= 127 for c in value) or any(c in value for c in "%\\@?#"):
        raise Refusal("invalid_endpoint")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise Refusal("invalid_endpoint") from None
    host = parts.hostname or ""
    if parts.scheme != "https" or not _HOST.fullmatch(host) or host.endswith("."):
        raise Refusal("invalid_endpoint")
    if (
        not _PATH.fullmatch(parts.path)
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise Refusal("invalid_endpoint")
    if port is not None and not 1 <= port <= 65535:
        raise Refusal("invalid_endpoint")
    netloc = host if port in (None, 443) else f"{host}:{port}"
    canonical = urlunsplit(("https", netloc, parts.path, "", ""))
    if value != canonical:
        raise Refusal("noncanonical_endpoint")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not _public_unicast(literal):
            raise Refusal("nonpublic_endpoint")
    return canonical


@dataclass(frozen=True, slots=True)
class Limits:
    max_output_tokens: int = 512
    max_request_bytes: int = 131_072
    max_response_bytes: int = 262_144
    max_usage_tokens: int = 1_000_000
    timeout_seconds: float = 30.0

    def __post_init__(self):
        if not _integer(self.max_output_tokens, 1, 4096):
            raise Refusal("invalid_output_cap")
        if not _integer(self.max_request_bytes, 512, 2_097_152):
            raise Refusal("invalid_request_cap")
        if not _integer(self.max_response_bytes, 256, 8_388_608):
            raise Refusal("invalid_response_cap")
        if not _integer(self.max_usage_tokens, self.max_output_tokens, 1_000_000_000):
            raise Refusal("invalid_usage_bound")
        if (
            type(self.timeout_seconds) not in (int, float)
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 120
        ):
            raise Refusal("invalid_timeout")


@dataclass(frozen=True, slots=True)
class Route:
    endpoint: str
    model_id: str
    role: Role
    limits: Limits = Limits()
    output_field: Literal["max_tokens", "max_completion_tokens"] = "max_completion_tokens"

    def __post_init__(self):
        _canonical_endpoint(self.endpoint)
        if type(self.model_id) is not str or not _MODEL.fullmatch(self.model_id):
            raise Refusal("invalid_model_id")
        if self.role not in _ROLE_SYSTEM or type(self.limits) is not Limits:
            raise Refusal("invalid_route")
        if self.output_field not in ("max_tokens", "max_completion_tokens"):
            raise Refusal("invalid_output_field")

    @property
    def fingerprint(self) -> str:
        values = [
            self.endpoint,
            self.model_id,
            self.role,
            self.output_field,
            self.limits.max_output_tokens,
            self.limits.max_request_bytes,
            self.limits.max_response_bytes,
            self.limits.max_usage_tokens,
            self.limits.timeout_seconds,
        ]
        return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Invocation:
    invocation_id: str
    prompt: str

    def __post_init__(self):
        if type(self.invocation_id) is not str or not _ID.fullmatch(self.invocation_id):
            raise Refusal("invalid_invocation_id")
        if type(self.prompt) is not str or not self.prompt or "\x00" in self.prompt:
            raise Refusal("invalid_prompt")

    def __repr__(self):
        return f"Invocation(invocation_id={self.invocation_id!r}, prompt=<redacted>)"


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_details: tuple[tuple[str, int], ...] = ()
    output_details: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class Receipt:
    invocation_id: str
    route_fingerprint: str
    model_id: str
    role: Role
    attempts: int = 0
    dispatch_state: Literal["not_dispatched", "possible", "response_complete"] = "not_dispatched"
    outcome: Literal["pending", "refused", "uncertain", "succeeded"] = "pending"
    reason: str = "pending"
    http_status: int | None = None
    usage: Usage | None = None


@dataclass(frozen=True, slots=True)
class Completion:
    receipt: Receipt
    content: str | None = None

    def __repr__(self):
        return f"Completion(receipt={self.receipt!r}, content=<redacted>)"


class _ScopedCredential:
    __slots__ = ("_value", "_fingerprint")

    def __init__(self, value: str, fingerprint: str):
        if (
            type(value) is not str
            or not 1 <= len(value) <= 16_384
            or any(ord(c) <= 32 or ord(c) >= 127 for c in value)
        ):
            raise Refusal("invalid_credential")
        if value == "workload-identity-auth":
            raise Refusal("unsupported_credential_kind")
        self._value = value
        self._fingerprint = fingerprint

    def __repr__(self):
        return "<ScopedCredential redacted>"


def _strict_json(raw: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Refusal("duplicate_json_key")
            result[key] = value
        return result

    def constant(_):
        raise Refusal("nonfinite_json")

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise Refusal("nonfinite_json")
        return parsed

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
            parse_float=finite_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if type(exc) is Refusal:
            raise
        raise Refusal("invalid_json") from None


def _usage(raw: object, limits: Limits) -> Usage:
    required = {"prompt_tokens", "completion_tokens", "total_tokens"}
    optional = {"prompt_tokens_details", "completion_tokens_details"}
    if type(raw) is not dict or not required <= raw.keys() or raw.keys() - required - optional:
        raise Refusal("invalid_usage_shape")
    counts = tuple(raw[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
    if any(not _integer(value, 1, limits.max_usage_tokens) for value in counts):
        raise Refusal("invalid_usage_counter")
    if counts[0] + counts[1] != counts[2]:
        raise Refusal("inconsistent_usage_total")
    details = []
    allowed = (
        {"cached_tokens", "cache_write_tokens", "audio_tokens"},
        {
            "reasoning_tokens",
            "audio_tokens",
            "accepted_prediction_tokens",
            "rejected_prediction_tokens",
        },
    )
    for key, ceiling, keys in zip(
        ("prompt_tokens_details", "completion_tokens_details"), counts[:2], allowed, strict=True
    ):
        value = raw.get(key)
        if value is None:
            details.append(())
            continue
        if type(value) is not dict or value.keys() - keys:
            raise Refusal("invalid_usage_details")
        if any(not _integer(count, 0, ceiling) for count in value.values()):
            raise Refusal("inconsistent_usage_details")
        # This request has no audio or predicted-output inputs. Cache-write
        # billing semantics are not qualified here; do not invent overlap rules.
        if any(
            value.get(name, 0) != 0
            for name in (
                "audio_tokens",
                "cache_write_tokens",
                "accepted_prediction_tokens",
                "rejected_prediction_tokens",
            )
        ):
            raise Refusal("unsupported_usage_detail")
        details.append(tuple(sorted(value.items())))
    return Usage(*counts, *details)


def _contains_secret(value, secret):
    pending = [value]
    while pending:
        item = pending.pop()
        if type(item) is str and secret in item:
            return True
        if type(item) is dict:
            pending.extend(item.keys())
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
    return False


async def _resolve_public_address(host: str, port: int):
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            answers = await asyncio.to_thread(
                socket.getaddrinfo, host, port, type=socket.SOCK_STREAM
            )
            addresses = {ipaddress.ip_address(answer[4][0]) for answer in answers}
        except (OSError, ValueError):
            raise Refusal("endpoint_resolution_failed") from None
    else:
        addresses = {literal}
    if not addresses or any(not _public_unicast(address) for address in addresses):
        raise Refusal("endpoint_resolution_not_public")
    return min(addresses, key=lambda address: (address.version, int(address)))


def _new_transport() -> httpx.AsyncBaseTransport:
    return httpx.AsyncHTTPTransport(
        retries=0,
        trust_env=False,
        verify=True,
        http2=False,
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
    )


class _GuardedTransport(httpx.AsyncBaseTransport):
    def __init__(self, owner, invocation, credential, body):
        self._owner = owner
        self._invocation = invocation
        self._credential = credential
        self._body = body
        self._inner = _new_transport()
        self._attempted = False

    async def handle_async_request(self, request):
        route = self._owner.route
        if self._attempted:
            raise Refusal("second_dispatch_refused")
        if request.method != "POST" or str(request.url) != route.endpoint:
            raise Refusal("request_route_mismatch")
        expected = self._owner._headers(self._credential, self._body)
        observed = list(request.headers.multi_items())
        if len(observed) != len(expected) or dict(observed) != expected:
            raise Refusal("request_header_mismatch")
        if set(request.extensions) != {"timeout"}:
            raise Refusal("request_extension_mismatch")
        raw = await request.aread()
        if raw != self._body or len(raw) > route.limits.max_request_bytes:
            raise Refusal("request_body_mismatch")
        body = _strict_json(raw)
        if set(body) != self._owner._body_fields():
            raise Refusal("request_field_mismatch")
        if (
            type(body.get(route.output_field)) is not int
            or body[route.output_field] != route.limits.max_output_tokens
        ):
            raise Refusal("request_output_cap_mismatch")
        if (
            body.get("model") != route.model_id
            or body.get("stream") is not False
            or body.get("n") != 1
        ):
            raise Refusal("request_identity_mismatch")
        if self._credential._fingerprint != route.fingerprint:
            raise Refusal("credential_scope_mismatch")
        parts = urlsplit(route.endpoint)
        address = await _resolve_public_address(parts.hostname, parts.port or 443)
        # The original configured endpoint is validated above. Pin TCP while
        # preserving the original Host and verified TLS SNI, with no DNS rebind.
        request.url = request.url.copy_with(host=str(address))
        request.extensions["sni_hostname"] = parts.hostname
        self._attempted = True
        self._owner._mark_dispatch(self._invocation.invocation_id)
        return await self._inner.handle_async_request(request)

    async def aclose(self):
        await self._inner.aclose()


async def _bounded_response(response: httpx.Response, limit: int) -> bytes:
    encodings = response.headers.get_list("content-encoding")
    if encodings and encodings != ["identity"]:
        raise Refusal("response_encoding_refused")
    types = response.headers.get_list("content-type")
    if len(types) != 1 or types[0].split(";", 1)[0].strip().lower() != "application/json":
        raise Refusal("response_content_type_refused")
    lengths = response.headers.get_list("content-length")
    expected = None
    if lengths:
        if len(lengths) != 1 or not re.fullmatch(r"0|[1-9][0-9]*", lengths[0]):
            raise Refusal("invalid_content_length")
        expected = int(lengths[0])
        if expected > limit:
            raise Refusal("response_too_large")
    chunks, size = [], 0
    # MockTransport can return an already buffered response; production uses
    # send(stream=True), and AsyncHTTPTransport supplies an unread byte stream.
    if response.is_stream_consumed:
        raw = response.content
        if len(raw) > limit:
            raise Refusal("response_too_large")
    else:
        async for chunk in response.aiter_raw(chunk_size=min(4096, limit + 1)):
            size += len(chunk)
            if size > limit:
                raise Refusal("response_too_large")
            chunks.append(chunk)
        raw = b"".join(chunks)
    if expected is not None and expected != len(raw):
        raise Refusal("response_length_mismatch")
    return raw


class ManagedChatCandidate:
    """One-call transport candidate; no public live dispatch is authorized.

    Receipts are in-memory only. PEX durable budget/reservation integration,
    Strands/tool-loop integration and real-provider qualification are separate.
    """

    __slots__ = ("_route", "_receipts", "_active")

    def __init__(self, route: Route):
        if type(route) is not Route:
            raise Refusal("unsupported_route_type")
        self._route = route
        self._receipts = {}
        self._active = False

    @property
    def route(self):
        return self._route

    def receipt(self, invocation_id: str) -> Receipt | None:
        return self._receipts.get(invocation_id)

    def _base_receipt(self, invocation):
        return Receipt(
            invocation.invocation_id, self.route.fingerprint, self.route.model_id, self.route.role
        )

    async def invoke(self, invocation: Invocation) -> Completion:
        # No env/provenance flag, supplied credential or class label can open
        # public live dispatch. This literal gate is changed only after review.
        receipt = replace(
            self._base_receipt(invocation), outcome="refused", reason="live_not_authorized"
        )
        return Completion(receipt)

    def _headers(self, credential, body):
        return {
            "host": urlsplit(self.route.endpoint).netloc,
            "accept": "application/json",
            "accept-encoding": "identity",
            "connection": "close",
            "user-agent": "PEX-Managed-Candidate/0",
            "content-type": "application/json",
            "content-length": str(len(body)),
            "authorization": "Bearer " + credential._value,
        }

    def _mark_dispatch(self, invocation_id):
        self._receipts[invocation_id] = replace(
            self._receipts[invocation_id], attempts=1, dispatch_state="possible"
        )

    def _accept_invocation(self, invocation):
        return type(invocation) is Invocation

    def _body_fields(self):
        return {"model", "stream", "n", self.route.output_field, "messages"}

    def _request_payload(self, invocation):
        return {
            "model": self.route.model_id,
            "stream": False,
            "n": 1,
            self.route.output_field: self.route.limits.max_output_tokens,
            "messages": [
                {"role": "system", "content": _ROLE_SYSTEM[self.route.role]},
                {"role": "user", "content": invocation.prompt},
            ],
        }

    def _request_contains_secret(self, invocation, payload, secret):
        return _contains_secret(payload, secret)

    def _response_content(self, raw, credential, invocation):
        choices = raw.get("choices")
        if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
            raise Refusal("invalid_response_choices")
        choice = choices[0]
        if (
            type(choice.get("index")) is not int
            or choice["index"] != 0
            or choice.get("finish_reason") != "stop"
        ):
            raise Refusal("incomplete_response")
        message = choice.get("message")
        if (
            type(message) is not dict
            or message.get("role") != "assistant"
            or message.get("tool_calls") is not None
            or "function_call" in message
            or message.get("refusal") is not None
        ):
            raise Refusal("unsupported_response_message")
        content = message.get("content")
        if (
            type(content) is not str
            or not content
            or "\x00" in content
            or credential._value in content
        ):
            raise Refusal("invalid_response_content")
        try:
            content.encode("utf-8")
        except UnicodeEncodeError:
            raise Refusal("invalid_response_content") from None
        return content

    def _completion(self, receipt, content=None):
        return Completion(receipt, content)

    async def _execute_owned(
        self, invocation: Invocation, credential: _ScopedCredential
    ) -> Completion:
        """Private implementation, exercised only by synthetic offline tests.

        This is not a live-admission API. No client, transport, arbitrary params,
        raw headers, callable credential or provider adapter is accepted.
        """
        if not self._accept_invocation(invocation) or type(credential) is not _ScopedCredential:
            raise Refusal("unsupported_invocation_or_credential")
        if invocation.invocation_id in self._receipts:
            raise Refusal("invocation_reuse_refused")
        if self._active:
            raise Refusal("concurrent_invocation_refused")
        self._active = True
        self._receipts[invocation.invocation_id] = self._base_receipt(invocation)
        reason, content = "local_validation_failed", None
        try:
            if credential._fingerprint != self.route.fingerprint:
                raise Refusal("credential_scope_mismatch")
            payload = self._request_payload(invocation)
            body = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(body) > self.route.limits.max_request_bytes:
                raise Refusal("request_too_large")
            if self._request_contains_secret(invocation, payload, credential._value):
                raise Refusal("credential_in_prompt_refused")
            timeout = httpx.Timeout(self.route.limits.timeout_seconds)
            async with asyncio.timeout(self.route.limits.timeout_seconds):
                async with httpx.AsyncClient(
                    transport=_GuardedTransport(self, invocation, credential, body),
                    trust_env=False,
                    follow_redirects=False,
                    timeout=timeout,
                ) as client:
                    request = client.build_request(
                        "POST",
                        self.route.endpoint,
                        headers=self._headers(credential, body),
                        content=body,
                    )
                    response = await client.send(request, stream=True)
                    try:
                        self._receipts[invocation.invocation_id] = replace(
                            self.receipt(invocation.invocation_id), http_status=response.status_code
                        )
                        if response.status_code != 200:
                            raise Refusal("provider_status_refused")
                        raw = _strict_json(
                            await _bounded_response(response, self.route.limits.max_response_bytes)
                        )
                        if (
                            type(raw) is not dict
                            or raw.get("model") != self.route.model_id
                            or raw.get("object") != "chat.completion"
                        ):
                            raise Refusal("response_identity_mismatch")
                        usage = _usage(raw.get("usage"), self.route.limits)
                        self._receipts[invocation.invocation_id] = replace(
                            self.receipt(invocation.invocation_id), usage=usage
                        )
                        if usage.output_tokens > self.route.limits.max_output_tokens:
                            raise Refusal("observed_output_cap_exceeded")
                        content = self._response_content(raw, credential, invocation)
                        self._receipts[invocation.invocation_id] = replace(
                            self.receipt(invocation.invocation_id),
                            dispatch_state="response_complete",
                            outcome="succeeded",
                            reason="validated_response",
                        )
                        return self._completion(self.receipt(invocation.invocation_id), content)
                    finally:
                        await response.aclose()
        except asyncio.CancelledError:
            self._fail(invocation.invocation_id, "cancelled")
            raise
        except Refusal as exc:
            reason = str(exc)  # Only internal constant reason codes enter Refusal.
        except (TimeoutError, httpx.TimeoutException):
            reason = "transport_timeout"
        except httpx.HTTPError:
            reason = "transport_failure"
        except Exception:
            reason = "internal_failure"
        finally:
            self._active = False
        self._fail(invocation.invocation_id, reason)
        return self._completion(self.receipt(invocation.invocation_id))

    def _fail(self, invocation_id, reason):
        receipt = self.receipt(invocation_id)
        self._receipts[invocation_id] = replace(
            receipt,
            outcome="uncertain" if receipt.attempts else "refused",
            reason=reason,
        )
