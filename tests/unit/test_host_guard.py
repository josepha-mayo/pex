from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.origin_guard import TrustedLoopbackHostMiddleware
from starlette.responses import PlainTextResponse


async def _ok_app(scope, receive, send) -> None:
    await PlainTextResponse("ok")(scope, receive, send)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1",
        "http://127.0.0.1:7420",
        "http://localhost",
        "http://localhost:7420",
        "http://[::1]",
        "http://[::1]:7420",
    ],
)
async def test_host_guard_accepts_only_canonical_loopback_hosts(base_url: str) -> None:
    guarded = TrustedLoopbackHostMiddleware(_ok_app)
    async with AsyncClient(transport=ASGITransport(app=guarded), base_url=base_url) as client:
        response = await client.get("/")
    assert response.status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "0.0.0.0:7420",
        "127.0.0.2:7420",
        "localhost.",
        "localhost:",
        "localhost:0",
        "localhost:65536",
        "::1",
        "[::1]:",
        "[::ffff:127.0.0.1]:7420",
        " user@localhost",
    ],
)
async def test_host_guard_rejects_wrong_or_malformed_hosts(host: str) -> None:
    guarded = TrustedLoopbackHostMiddleware(_ok_app)
    async with AsyncClient(
        transport=ASGITransport(app=guarded),
        base_url="http://127.0.0.1",
    ) as client:
        response = await client.get("/", headers={"Host": host})
    assert response.status_code == 400
    assert response.json() == {"detail": "untrusted host"}


async def test_host_guard_rejects_duplicate_and_non_ascii_hosts() -> None:
    guarded = TrustedLoopbackHostMiddleware(_ok_app)
    async with AsyncClient(
        transport=ASGITransport(app=guarded),
        base_url="http://127.0.0.1",
    ) as client:
        duplicate = await client.get(
            "/",
            headers=[("Host", "127.0.0.1"), ("Host", "localhost")],
        )
        non_ascii = await client.get("/", headers=[(b"host", b"\xff")])
    assert duplicate.status_code == 400
    assert non_ascii.status_code == 400


async def test_host_guard_rejects_a_missing_host_header() -> None:
    guarded = TrustedLoopbackHostMiddleware(_ok_app)
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    await guarded(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [],
        },
        receive,
        send,
    )

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 400


async def test_test_hosts_require_an_explicit_process_local_allowance() -> None:
    strict = TrustedLoopbackHostMiddleware(_ok_app)
    allowed = TrustedLoopbackHostMiddleware(_ok_app, allow_test_hosts=True)
    async with AsyncClient(transport=ASGITransport(app=strict), base_url="http://test") as client:
        assert (await client.get("/")).status_code == 400
    async with AsyncClient(transport=ASGITransport(app=allowed), base_url="http://test") as client:
        assert (await client.get("/")).status_code == 200
