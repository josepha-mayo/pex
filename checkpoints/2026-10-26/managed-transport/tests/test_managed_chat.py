import asyncio
import copy
import gzip
import inspect
import ipaddress
import json
import socket
from dataclasses import FrozenInstanceError, asdict

import httpx
import pytest

import managed_chat as mc

ENDPOINT = "https://managed-fixture.invalid/v1/chat/completions"
MODEL = "fixture/exact-model"
SYNTHETIC_KEY = "fixture-no-provider-credential"
VALID = {
    "id": "fixture-response",
    "object": "chat.completion",
    "created": 1,
    "model": MODEL,
    "choices": [
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "Fixture decision"},
        }
    ],
    "usage": {
        "prompt_tokens": 12,
        "completion_tokens": 3,
        "total_tokens": 15,
        "prompt_tokens_details": {"cached_tokens": 2},
        "completion_tokens_details": {"reasoning_tokens": 1},
    },
}


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks, self.reads, self.closed = chunks, 0, False

    async def __aiter__(self):
        for chunk in self.chunks:
            self.reads += 1
            if isinstance(chunk, BaseException):
                raise chunk
            yield chunk

    async def aclose(self):
        self.closed = True


def response(payload=None, *, status=200, raw=None, headers=None, chunks=None):
    data = (
        raw
        if raw is not None
        else json.dumps(payload if payload is not None else VALID, separators=(",", ":")).encode()
    )
    stream = Chunks(chunks if chunks is not None else [data])
    return httpx.Response(
        status, headers={"content-type": "application/json", **(headers or {})}, stream=stream
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    attempts = []

    def denied(*args, **kwargs):
        attempts.append("forbidden_network_attempt")
        raise AssertionError("No network operation authorized")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    yield
    assert attempts == [], "Caught exceptions must not conceal network attempts"


@pytest.fixture
def rig(monkeypatch):
    class Rig:
        def __init__(self):
            self.calls, self.created, self.closed = [], 0, 0
            self.handler = lambda request: response()
            self.resolutions = 0

        def factory(self):
            self.created += 1
            parent = self

            class OwnedMock(httpx.MockTransport):
                async def aclose(self):
                    parent.closed += 1
                    await super().aclose()

            # Internal constructor substitution only; no production injection API.
            return OwnedMock(self.handle)

        async def handle(self, request):
            self.calls.append(request)
            result = self.handler(request)
            return await result if inspect.isawaitable(result) else result

        async def resolve(self, host, port):
            self.resolutions += 1
            assert host == "managed-fixture.invalid" and port == 443
            return ipaddress.ip_address("93.184.216.34")

    value = Rig()
    monkeypatch.setattr(mc, "_new_transport", value.factory)
    monkeypatch.setattr(mc, "_resolve_public_address", value.resolve)
    return value


def candidate(**limits):
    return mc.ManagedChatCandidate(mc.Route(ENDPOINT, MODEL, "planner", mc.Limits(**limits)))


async def run(c, invocation_id="fixture-1", prompt="Bounded synthetic evidence", key=SYNTHETIC_KEY):
    return await c._execute_owned(
        mc.Invocation(invocation_id, prompt), mc._ScopedCredential(key, c.route.fingerprint)
    )


@pytest.mark.asyncio
async def test_public_invoke_denied_before_credentials_dns_or_transport(rig):
    c = candidate()
    result = await c.invoke(mc.Invocation("public-1", "fixture"))
    assert result.receipt.reason == "live_not_authorized"
    assert result.receipt.attempts == 0 and result.content is None
    assert rig.created == rig.resolutions == len(rig.calls) == 0


@pytest.mark.asyncio
async def test_valid_single_call_exact_identity_fixed_role_usage_and_close(rig):
    c = candidate()
    result = await run(c)
    assert result.content == "Fixture decision"
    assert result.receipt.outcome == "succeeded"
    assert result.receipt.attempts == 1 and result.receipt.dispatch_state == "response_complete"
    assert result.receipt.usage == mc.Usage(
        12, 3, 15, (("cached_tokens", 2),), (("reasoning_tokens", 1),)
    )
    assert rig.created == rig.closed == rig.resolutions == len(rig.calls) == 1
    req = rig.calls[0]
    assert str(req.url) == "https://93.184.216.34/v1/chat/completions"
    assert req.headers["host"] == "managed-fixture.invalid"
    assert req.extensions["sni_hostname"] == "managed-fixture.invalid"
    body = json.loads(req.content)
    assert body["model"] == MODEL and body["stream"] is False and body["n"] == 1
    assert body["max_completion_tokens"] == 512
    assert body["messages"][0] == {"role": "system", "content": mc._ROLE_SYSTEM["planner"]}
    assert body["messages"][1]["role"] == "user"
    assert set(body) == {"model", "stream", "n", "max_completion_tokens", "messages"}


@pytest.mark.asyncio
async def test_ambient_headers_tenant_keys_and_proxy_do_not_enter_owned_request(
    monkeypatch, rig, caplog
):
    for name, value in {
        "OPENAI_API_KEY": "fixture-wrong-key",
        "OPENAI_ADMIN_KEY": "fixture-wrong-admin",
        "OPENAI_ORG_ID": "fixture-wrong-org",
        "OPENAI_PROJECT_ID": "fixture-wrong-project",
        "OPENAI_CUSTOM_HEADERS": (
            "Authorization: Bearer fixture-wrong\nX-Fixture-Header: fixture-wrong"
        ),
        "OPENAI_BASE_URL": "https://wrong.invalid/v1",
        "HTTPS_PROXY": "http://wrong.invalid:3128",
        "SSL_CERT_FILE": "/not/a/certificate",
        "ALL_PROXY": "http://wrong.invalid:3128",
    }.items():
        monkeypatch.setenv(name, value)
    result = await run(candidate())
    assert result.receipt.outcome == "succeeded"
    req = rig.calls[0]
    assert req.headers["authorization"] == "Bearer " + SYNTHETIC_KEY
    assert set(req.headers) == {
        "host",
        "accept",
        "accept-encoding",
        "connection",
        "user-agent",
        "content-type",
        "content-length",
        "authorization",
    }
    assert "fixture-wrong" not in req.content.decode()
    assert SYNTHETIC_KEY not in caplog.text


@pytest.mark.parametrize(
    "field,value",
    [
        ("endpoint", "http://managed-fixture.invalid/v1/chat/completions"),
        ("endpoint", "https://managed-fixture.invalid:443/v1/chat/completions"),
        ("endpoint", "https://managed-fixture.invalid./v1/chat/completions"),
        ("endpoint", "https://MANAGED-fixture.invalid/v1/chat/completions"),
        ("endpoint", "https://user:pass@managed-fixture.invalid/v1/chat/completions"),
        ("endpoint", "https://managed-fixture.invalid/v1/chat/completions?x=1"),
        ("endpoint", "https://managed-fixture.invalid/v1/../chat/completions"),
        ("endpoint", "https://managed-fixture.invalid/%76%31/chat/completions"),
        ("endpoint", "https://127.0.0.1/v1/chat/completions"),
        ("endpoint", "https://managed-fixture.invalid//v1/chat/completions"),
        ("model_id", "fixture\nmodel"),
        ("role", "worker"),
        ("output_field", "extra_body"),
    ],
)
def test_route_refuses_noncanonical_or_unsupported_values(field, value):
    args = {"endpoint": ENDPOINT, "model_id": MODEL, "role": "planner", field: value}
    with pytest.raises(mc.Refusal):
        mc.Route(**args)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_output_tokens": True},
        {"max_output_tokens": 0},
        {"max_output_tokens": 4097},
        {"max_request_bytes": 0},
        {"max_response_bytes": 0},
        {"timeout_seconds": True},
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": 0},
        {"max_usage_tokens": 1},
    ],
)
def test_caps_are_finite_strict_and_bounded(kwargs):
    with pytest.raises(mc.Refusal):
        mc.Limits(**kwargs)


@pytest.mark.parametrize(
    "arg",
    [
        "client",
        "client_args",
        "params",
        "extra_body",
        "http_client",
        "transport",
        "workload_identity",
        "api_key",
    ],
)
def test_constructor_has_no_passthrough_or_client_injection(arg):
    with pytest.raises(TypeError):
        mc.ManagedChatCandidate(mc.Route(ENDPOINT, MODEL, "planner"), **{arg: object()})


@pytest.mark.parametrize(
    "bad", [lambda: SYNTHETIC_KEY, "workload-identity-auth", "fixture\nkey", "", b"fixture"]
)
def test_credential_refuses_callbacks_workload_and_bad_shapes(bad):
    with pytest.raises(mc.Refusal):
        mc._ScopedCredential(bad, "fixture")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "model",
        "route",
        "header",
        "duplicate_header",
        "body_extra",
        "body_stream",
        "body_cap",
        "extension",
    ],
)
async def test_last_mile_refuses_request_mutation_before_dns_or_dispatch(
    monkeypatch, rig, mutation
):
    original = httpx.AsyncClient.build_request

    def changed(self, *args, **kwargs):
        req = original(self, *args, **kwargs)
        if mutation == "route":
            req.url = httpx.URL("https://other.invalid/v1/chat/completions")
        elif mutation == "header":
            req.headers["authorization"] = "Bearer fixture-wrong"
        elif mutation == "duplicate_header":
            req.headers = httpx.Headers(
                list(req.headers.multi_items()) + [("authorization", "Bearer fixture-wrong")]
            )
        elif mutation == "extension":
            req.extensions["sni_hostname"] = "other.invalid"
        else:
            body = json.loads(req.content)
            if mutation == "model":
                body["model"] = "other-model"
            if mutation == "body_extra":
                body["extra_body"] = {"model": "other-model"}
            if mutation == "body_stream":
                body["stream"] = True
            if mutation == "body_cap":
                body["max_completion_tokens"] = 10000
            raw = json.dumps(body).encode()
            req = httpx.Request(
                req.method, req.url, headers=req.headers, content=raw, extensions=req.extensions
            )
        return req

    monkeypatch.setattr(httpx.AsyncClient, "build_request", changed)
    result = await run(candidate())
    assert result.receipt.outcome == "refused" and result.receipt.attempts == 0
    assert rig.resolutions == len(rig.calls) == 0
    assert rig.closed == 1


@pytest.mark.asyncio
async def test_scope_mismatch_before_transport(rig):
    c = candidate()
    result = await c._execute_owned(
        mc.Invocation("wrong-scope", "fixture"), mc._ScopedCredential(SYNTHETIC_KEY, "other")
    )
    assert result.receipt.reason == "credential_scope_mismatch"
    assert rig.created == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 307, 308, 400, 401, 403, 408, 409, 429, 500, 503])
async def test_status_errors_never_retry_or_follow_redirect_and_remain_uncertain(rig, status):
    rig.handler = lambda req: response(
        status=status,
        headers={
            "location": "https://other.invalid/v1/chat/completions",
            "retry-after": "0",
            "x-should-retry": "true",
        },
    )
    result = await run(candidate())
    assert result.receipt.outcome == "uncertain" and result.receipt.dispatch_state == "possible"
    assert result.receipt.attempts == 1 and result.receipt.http_status == status
    assert result.receipt.usage is None and result.content is None
    assert len(rig.calls) == rig.closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.ReadError,
        httpx.RemoteProtocolError,
    ],
)
async def test_transport_failure_one_attempt_usage_unknown_and_sanitized(rig, error, caplog):
    def handler(req):
        raise error("Synthetic provider echo " + SYNTHETIC_KEY, request=req)

    rig.handler = handler
    result = await run(candidate())
    assert result.receipt.outcome == "uncertain" and result.receipt.attempts == 1
    assert result.receipt.usage is None and result.content is None
    assert len(rig.calls) == rig.closed == 1
    assert SYNTHETIC_KEY not in repr(result) + json.dumps(asdict(result.receipt)) + caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("prompt_tokens", True),
        ("prompt_tokens", "12"),
        ("prompt_tokens", 12.0),
        ("prompt_tokens", 12.5),
        ("prompt_tokens", -1),
        ("prompt_tokens", 0),
        ("prompt_tokens", None),
        ("prompt_tokens", 10**20),
        ("completion_tokens", False),
        ("completion_tokens", "3"),
        ("total_tokens", 14),
        ("total_tokens", 15.0),
    ],
)
async def test_raw_usage_types_bounds_and_aggregate_rejected_without_coercion(rig, field, value):
    payload = copy.deepcopy(VALID)
    payload["usage"][field] = value
    rig.handler = lambda req: response(payload)
    result = await run(candidate())
    assert result.receipt.outcome == "uncertain" and result.receipt.usage is None
    assert result.content is None and len(rig.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "missing_usage",
        "missing_counter",
        "duplicate",
        "nan",
        "infinity",
        "unknown_usage",
        "cache_negative",
        "cache_string",
        "cache_bool",
        "cache_over_input",
        "reasoning_over_output",
        "unknown_detail",
        "detail_array",
    ],
)
async def test_raw_usage_shape_cache_and_duplicate_inconsistencies(rig, case):
    payload = copy.deepcopy(VALID)
    if case == "missing_usage":
        payload.pop("usage")
    elif case == "missing_counter":
        payload["usage"].pop("prompt_tokens")
    elif case == "unknown_usage":
        payload["usage"]["hidden_counter"] = 1
    elif case.startswith("cache_"):
        value = {
            "cache_negative": -1,
            "cache_string": "2",
            "cache_bool": True,
            "cache_over_input": 13,
        }[case]
        payload["usage"]["prompt_tokens_details"]["cached_tokens"] = value
    elif case == "reasoning_over_output":
        payload["usage"]["completion_tokens_details"]["reasoning_tokens"] = 4
    elif case == "unknown_detail":
        payload["usage"]["prompt_tokens_details"]["unknown"] = 1
    elif case == "detail_array":
        payload["usage"]["prompt_tokens_details"] = []
    raw = json.dumps(payload).encode()
    if case == "duplicate":
        raw = raw.replace(b'"prompt_tokens": 12', b'"prompt_tokens": 12, "prompt_tokens": 12')
    if case == "nan":
        raw = raw.replace(b'"prompt_tokens": 12', b'"prompt_tokens": NaN')
    if case == "infinity":
        raw = raw.replace(b'"prompt_tokens": 12', b'"prompt_tokens": 1e309')
    rig.handler = lambda req: response(raw=raw)
    result = await run(candidate())
    assert result.receipt.outcome == "uncertain" and result.receipt.usage is None
    assert result.content is None and len(rig.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "wrong_model",
        "alias_model",
        "multi_choice",
        "missing_choice",
        "wrong_index",
        "truncated",
        "tool_call",
        "refusal",
        "wrong_role",
        "secret_echo",
        "malformed_json",
    ],
)
async def test_response_identity_and_content_fail_closed(rig, case):
    payload = copy.deepcopy(VALID)
    choice = payload["choices"][0]
    if case == "wrong_model":
        payload["model"] = "other"
    if case == "alias_model":
        payload["model"] = MODEL + "-version"
    if case == "multi_choice":
        payload["choices"].append(copy.deepcopy(choice))
    if case == "missing_choice":
        payload["choices"] = []
    if case == "wrong_index":
        choice["index"] = False
    if case == "truncated":
        choice["finish_reason"] = "length"
    if case == "tool_call":
        choice["message"]["tool_calls"] = [{"id": "tool", "function": {"arguments": "{}"}}]
    if case == "refusal":
        choice["message"]["refusal"] = "fixture refusal"
    if case == "wrong_role":
        choice["message"]["role"] = "system"
    if case == "secret_echo":
        choice["message"]["content"] = SYNTHETIC_KEY
    rig.handler = lambda req: response(payload, raw=b"{" if case == "malformed_json" else None)
    result = await run(candidate())
    assert result.receipt.outcome == "uncertain" and result.content is None
    assert len(rig.calls) == 1 and SYNTHETIC_KEY not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "oversized_declared",
        "oversized_stream",
        "compressed_bomb",
        "truncated_length",
        "duplicate_length",
        "non_json",
        "broken_stream",
    ],
)
async def test_bounded_raw_response_no_decompression_or_unbounded_read(rig, case):
    if case == "oversized_declared":
        resp = response(headers={"content-length": "9999999"})
    elif case == "oversized_stream":
        resp = response(chunks=[b"x" * 256] * 1000)
    elif case == "compressed_bomb":
        resp = response(raw=gzip.compress(b"x" * 1_000_000), headers={"content-encoding": "gzip"})
    elif case == "truncated_length":
        resp = response(headers={"content-length": "1"})
    elif case == "duplicate_length":
        resp = response(headers={"content-length": "1,1"})
    elif case == "non_json":
        resp = response(headers={"content-type": "text/html"})
    else:
        resp = response(chunks=[b"{", httpx.ReadError("fixture secret " + SYNTHETIC_KEY)])
    stream = resp.stream
    rig.handler = lambda req: resp
    result = await run(candidate(max_response_bytes=1024))
    assert result.receipt.outcome == "uncertain" and result.content is None
    assert len(rig.calls) == rig.closed == 1 and stream.closed
    if case in {"oversized_declared", "compressed_bomb", "duplicate_length", "non_json"}:
        assert stream.reads == 0
    if case == "oversized_stream":
        assert stream.reads < 1000


@pytest.mark.asyncio
async def test_output_overrun_retains_known_usage_but_refuses_content(rig):
    result = await run(candidate(max_output_tokens=2))
    assert (
        result.receipt.outcome == "uncertain"
        and result.receipt.reason == "observed_output_cap_exceeded"
    )
    assert result.receipt.usage.output_tokens == 3 and result.content is None


@pytest.mark.asyncio
async def test_request_bound_and_secret_prompt_refuse_before_transport(rig):
    c = candidate(max_request_bytes=512)
    result = await run(c, prompt="x" * 1000)
    assert result.receipt.reason == "request_too_large" and result.receipt.attempts == 0
    result = await run(c, invocation_id="secret-prompt", prompt=SYNTHETIC_KEY)
    assert result.receipt.reason == "credential_in_prompt_refused" and rig.created == 0


@pytest.mark.asyncio
async def test_cancellation_after_dispatch_preserves_unknown_receipt(rig):
    entered = asyncio.Event()

    async def handler(req):
        entered.set()
        await asyncio.Event().wait()

    rig.handler = handler
    c = candidate()
    task = asyncio.create_task(run(c))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    receipt = c.receipt("fixture-1")
    assert receipt.reason == "cancelled" and receipt.outcome == "uncertain"
    assert receipt.attempts == 1 and receipt.usage is None and rig.closed == 1
    with pytest.raises(mc.Refusal, match="invocation_reuse_refused"):
        await run(c)
    assert len(rig.calls) == 1


@pytest.mark.asyncio
async def test_total_timeout_after_dispatch_one_attempt(rig):
    async def handler(req):
        await asyncio.Event().wait()

    rig.handler = handler
    result = await run(candidate(timeout_seconds=0.02))
    assert result.receipt.reason == "transport_timeout" and result.receipt.outcome == "uncertain"
    assert len(rig.calls) == rig.closed == 1


@pytest.mark.asyncio
async def test_pre_dispatch_resolution_refusal_and_cancellation(monkeypatch, rig):
    async def refused(*args):
        raise mc.Refusal("endpoint_resolution_not_public")

    monkeypatch.setattr(mc, "_resolve_public_address", refused)
    result = await run(candidate())
    assert result.receipt.outcome == "refused" and result.receipt.attempts == 0
    assert not rig.calls and rig.closed == 1


@pytest.mark.asyncio
async def test_concurrent_or_reused_invocations_cannot_double_dispatch(rig):
    entered, finish = asyncio.Event(), asyncio.Event()

    async def handler(req):
        entered.set()
        await finish.wait()
        return response()

    rig.handler = handler
    c = candidate()
    task = asyncio.create_task(run(c))
    await entered.wait()
    with pytest.raises(mc.Refusal, match="invocation_reuse_refused"):
        await run(c)
    with pytest.raises(mc.Refusal, match="concurrent_invocation_refused"):
        await run(c, "other")
    finish.set()
    assert (await task).receipt.outcome == "succeeded"
    assert len(rig.calls) == 1


def test_route_config_and_redacted_representations():
    c = candidate()
    with pytest.raises(FrozenInstanceError):
        c.route.model_id = "other"
    with pytest.raises(AttributeError):
        c.route = mc.Route(ENDPOINT, "other", "planner")
    credential = mc._ScopedCredential(SYNTHETIC_KEY, c.route.fingerprint)
    invocation = mc.Invocation("id", "private synthetic prompt")
    assert SYNTHETIC_KEY not in repr(credential)
    assert "private synthetic prompt" not in repr(invocation)
    assert "openai" not in inspect.getsource(mc._new_transport).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "addresses",
    [
        [],
        ["127.0.0.1"],
        ["93.184.216.34", "10.0.0.1"],
        ["::ffff:93.184.216.34"],
        ["100.64.0.1"],
        ["169.254.169.254"],
    ],
)
async def test_dns_resolution_requires_every_answer_public(monkeypatch, addresses):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 443)) for addr in addresses
        ],
    )
    with pytest.raises(mc.Refusal, match="endpoint_resolution_not_public"):
        await mc._resolve_public_address("synthetic.invalid", 443)


@pytest.mark.asyncio
async def test_dns_resolution_picks_one_validated_public_address(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 443))
            for addr in ["93.184.216.35", "93.184.216.34"]
        ],
    )
    assert str(await mc._resolve_public_address("synthetic.invalid", 443)) == "93.184.216.34"


def test_actual_transport_constructor_has_no_retries_proxy_env_or_keepalive(monkeypatch):
    observed = {}

    def constructor(**kwargs):
        observed.update(kwargs)
        return object()

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", constructor)
    mc._new_transport()
    assert observed["retries"] == 0 and observed["trust_env"] is False
    assert observed["verify"] is True and observed["http2"] is False
    assert (
        observed["limits"].max_connections == 1
        and observed["limits"].max_keepalive_connections == 0
    )
    assert "proxy" not in observed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("tool_calls", False),
        ("tool_calls", []),
        ("tool_calls", 0),
        ("refusal", False),
        ("function_call", {}),
    ],
)
async def test_text_only_candidate_refuses_even_falsy_tool_side_channels(rig, field, value):
    payload = copy.deepcopy(VALID)
    payload["choices"][0]["message"][field] = value
    rig.handler = lambda req: response(payload)
    result = await run(candidate())
    assert result.receipt.outcome == "uncertain" and result.content is None


@pytest.mark.asyncio
async def test_nonfinite_json_anywhere_is_refused_before_usage(rig):
    raw = json.dumps(VALID).encode()[:-1] + b', "unused": 1e309}'
    rig.handler = lambda req: response(raw=raw)
    result = await run(candidate())
    assert result.receipt.reason == "nonfinite_json" and result.receipt.usage is None


@pytest.mark.asyncio
async def test_pre_dispatch_cancellation_receipt_is_not_dispatched(monkeypatch, rig):
    entered = asyncio.Event()

    async def resolving(*args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(mc, "_resolve_public_address", resolving)
    c = candidate()
    task = asyncio.create_task(run(c))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    receipt = c.receipt("fixture-1")
    assert receipt.reason == "cancelled" and receipt.outcome == "refused" and receipt.attempts == 0
    assert not rig.calls and rig.closed == 1


@pytest.mark.parametrize("address", ["224.0.0.1", "239.255.255.250", "ff02::1", "fec0::1"])
def test_public_does_not_mean_multicast_or_site_local(address):
    assert not mc._public_unicast(ipaddress.ip_address(address))


@pytest.mark.parametrize("host", ["224.0.0.1", "239.255.255.250"])
def test_literal_multicast_route_refused(host):
    with pytest.raises(mc.Refusal, match="nonpublic_endpoint"):
        mc.Route(f"https://{host}/v1/chat/completions", MODEL, "planner")


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["224.0.0.1", "239.255.255.250", "ff02::1", "fec0::1"])
async def test_dns_multicast_and_site_local_answers_refused(monkeypatch, address):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (address, 443))],
    )
    with pytest.raises(mc.Refusal, match="endpoint_resolution_not_public"):
        await mc._resolve_public_address("synthetic.invalid", 443)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "section,counter",
    [
        ("prompt_tokens_details", "audio_tokens"),
        ("prompt_tokens_details", "cache_write_tokens"),
        ("completion_tokens_details", "audio_tokens"),
        ("completion_tokens_details", "accepted_prediction_tokens"),
        ("completion_tokens_details", "rejected_prediction_tokens"),
    ],
)
async def test_nonzero_unsupported_usage_details_fail_closed(rig, section, counter):
    payload = copy.deepcopy(VALID)
    payload["usage"][section][counter] = 1
    rig.handler = lambda req: response(payload)
    result = await run(candidate())
    assert result.receipt.reason == "unsupported_usage_detail" and result.receipt.usage is None
    assert result.receipt.outcome == "uncertain" and len(rig.calls) == 1


@pytest.mark.asyncio
async def test_known_zero_unsupported_detail_counts_are_preserved(rig):
    payload = copy.deepcopy(VALID)
    payload["usage"]["prompt_tokens_details"].update(audio_tokens=0, cache_write_tokens=0)
    payload["usage"]["completion_tokens_details"].update(
        audio_tokens=0, accepted_prediction_tokens=0, rejected_prediction_tokens=0
    )
    rig.handler = lambda req: response(payload)
    result = await run(candidate())
    assert result.receipt.outcome == "succeeded"
    assert ("cache_write_tokens", 0) in result.receipt.usage.input_details


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["\ud800", "\udfff", "fixture\x00content"])
async def test_invalid_unicode_or_nul_content_is_not_success(rig, content):
    payload = copy.deepcopy(VALID)
    payload["choices"][0]["message"]["content"] = content
    raw = json.dumps(payload, ensure_ascii=True).encode()
    rig.handler = lambda req: response(raw=raw)
    result = await run(candidate())
    assert result.receipt.reason == "invalid_response_content"
    assert result.receipt.outcome == "uncertain" and result.content is None
    assert result.receipt.usage == mc.Usage(
        12, 3, 15, (("cached_tokens", 2),), (("reasoning_tokens", 1),)
    )
