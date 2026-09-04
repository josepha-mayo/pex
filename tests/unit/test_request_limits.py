from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient
from pex_bridge.app import (
    GoalIn,
    _attach_verified_acp,
    _attach_verified_http_transport,
    _replace_http_transport,
)
from pex_bridge.request_limits import RequestBodyLimitMiddleware
from pex_protocol.capabilities import AdapterCapabilities


def _limited_app(max_bytes: int) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=max_bytes)

    @app.post("/")
    async def echo(request: Request):
        return {"size": len(await request.body())}

    return app


@pytest.mark.asyncio
async def test_request_limit_accepts_exact_bound_and_rejects_content_length() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_limited_app(16)),
        base_url="http://test",
    ) as client:
        accepted = await client.post("/", content=b"x" * 16)
        rejected = await client.post("/", content=b"x" * 17)

    assert accepted.status_code == 200
    assert accepted.json() == {"size": 16}
    assert rejected.status_code == 413
    assert rejected.json() == {"detail": "request body too large"}


@pytest.mark.asyncio
async def test_request_limit_rejects_chunked_body_without_content_length() -> None:
    async def chunks():
        yield b"a" * 9
        yield b"b" * 8

    async with AsyncClient(
        transport=ASGITransport(app=_limited_app(16)),
        base_url="http://test",
    ) as client:
        response = await client.post("/", content=chunks())

    assert response.status_code == 413
    assert response.json() == {"detail": "request body too large"}


@pytest.mark.asyncio
async def test_request_limit_applies_to_nonstandard_get_bodies() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_limited_app(16)),
        base_url="http://test",
    ) as client:
        response = await client.request("GET", "/", content=b"x" * 17)

    assert response.status_code == 413
    assert response.json() == {"detail": "request body too large"}


@pytest.mark.asyncio
async def test_request_boundary_rejects_ambiguous_or_nonfinite_json() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_limited_app(256)),
        base_url="http://test",
    ) as client:
        duplicate = await client.post(
            "/",
            content=b'{"decision":"deny","decision":"allow"}',
            headers={"Content-Type": "application/json"},
        )
        nonfinite = await client.post(
            "/",
            content=b'{"confidence":NaN}',
            headers={"Content-Type": "application/json"},
        )
        headerless_duplicate = await client.post(
            "/",
            content=b'{"decision":"deny","decision":"allow"}',
        )

    assert duplicate.status_code == 400
    assert duplicate.json() == {"detail": "invalid JSON body"}
    assert nonfinite.status_code == 400
    assert nonfinite.json() == {"detail": "invalid JSON body"}
    assert headerless_duplicate.status_code == 400
    assert headerless_duplicate.json() == {"detail": "invalid JSON body"}


def test_goal_control_model_bounds_nested_lists_and_items() -> None:
    base = {"project_id": "p", "title": "t", "objective": "o"}

    with pytest.raises(ValueError):
        GoalIn.model_validate({**base, "acceptance_criteria": ["x"] * 129})
    with pytest.raises(ValueError):
        GoalIn.model_validate({**base, "acceptance_criteria": ["x" * 8193]})
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        GoalIn.model_validate({**base, "unrecognized_control": True})


class _ClosableTransport:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_failed_http_transport_swap_closes_unowned_candidate() -> None:
    candidate = _ClosableTransport()

    class RejectingAdapter:
        transport = object()

        def attach_transport(self, transport) -> None:
            raise RuntimeError("active transport")

    with pytest.raises(RuntimeError, match="active transport"):
        await _replace_http_transport(RejectingAdapter(), candidate)

    assert candidate.closed is True


@pytest.mark.asyncio
async def test_successful_http_transport_swap_closes_replaced_transport() -> None:
    previous = _ClosableTransport()
    candidate = _ClosableTransport()

    class Adapter:
        def __init__(self) -> None:
            self.transport = previous

        def attach_transport(self, transport) -> None:
            self.transport = transport

    adapter = Adapter()
    await _replace_http_transport(adapter, candidate)

    assert adapter.transport is candidate
    assert previous.closed is True
    assert candidate.closed is False


@pytest.mark.asyncio
async def test_unavailable_http_candidate_is_discarded_without_losing_previous_transport() -> None:
    previous = _ClosableTransport()
    candidate = _ClosableTransport()

    class Adapter:
        name = "bounded-test"

        def __init__(self) -> None:
            self.transport = previous

        def attach_transport(self, transport) -> None:
            self.transport = transport

        async def probe(self) -> AdapterCapabilities:
            return AdapterCapabilities(notes="unavailable")

    adapter = Adapter()
    with pytest.raises(HTTPException, match="candidate was discarded"):
        await _attach_verified_http_transport(adapter, candidate)

    assert adapter.transport is previous
    assert previous.closed is False
    assert candidate.closed is True


@pytest.mark.asyncio
async def test_failed_acp_candidate_restores_previous_client(monkeypatch) -> None:
    previous_transport = _ClosableTransport()
    candidate = _ClosableTransport()

    class Adapter:
        def __init__(self) -> None:
            self.acp = SimpleNamespace(transport=previous_transport)

        def attach_acp(self, transport) -> None:
            self.acp = SimpleNamespace(transport=transport)

    adapter = Adapter()
    previous = adapter.acp

    async def fail_finish(current, _body):
        await current.acp.transport.aclose()
        current.acp = None
        raise HTTPException(502, "candidate verification failed")

    monkeypatch.setattr("pex_bridge.app._finish_acp_attach", fail_finish)
    with pytest.raises(HTTPException, match="candidate verification failed"):
        await _attach_verified_acp(adapter, candidate, {})

    assert adapter.acp is previous
    assert previous_transport.closed is False
    assert candidate.closed is True
