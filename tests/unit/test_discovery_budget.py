"""Discovery deadlines with in-memory peers, no app or live process probes."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from pex_bridge.adapters import discover


@pytest.fixture
def isolated_discovery(monkeypatch):
    monkeypatch.setattr(discover, "list_desktop_apps", lambda: [])
    monkeypatch.setattr(discover, "resolve_codex_bin", lambda: None)
    monkeypatch.setattr(discover, "resolve_grok_build", lambda: None)
    monkeypatch.setattr(discover, "resolve_hermes", lambda: None)
    monkeypatch.setattr(discover, "_resolved_cli", lambda _name: None)
    monkeypatch.setattr(discover, "PROBES", (discover.PROBES[0],))
    real_client = httpx.AsyncClient

    def install(handler):
        options = []

        def client(**kwargs):
            options.append(kwargs)
            return real_client(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(discover.httpx, "AsyncClient", client)
        return options

    return install


@pytest.mark.asyncio
@pytest.mark.parametrize("stall", ["headers", "body"])
async def test_discovery_bounds_the_complete_probe_and_closes_stalled_peer(
    isolated_discovery, stall
):
    cancelled = asyncio.Event()
    closed = asyncio.Event()

    class StalledBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"{"  # A peer can make progress without ever finishing JSON.
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def aclose(self):
            closed.set()

    async def handle(_request):
        if stall == "headers":
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        return httpx.Response(200, stream=StalledBody())

    isolated_discovery(handle)
    found = await asyncio.wait_for(discover.probe_local_harnesses(0.02), timeout=0.5)
    assert found == []
    assert cancelled.is_set()
    if stall == "body":
        assert closed.is_set()


@pytest.mark.asyncio
async def test_discovery_keeps_valid_local_health_and_refuses_proxy_or_redirect_routes(
    isolated_discovery,
):
    options = isolated_discovery(lambda _request: httpx.Response(200, json={"healthy": True}))
    found = await discover.probe_local_harnesses()
    assert any(item["name"] == "opencode" and item["kind"] == "http" for item in found)
    assert options[0]["trust_env"] is False
    assert options[0]["follow_redirects"] is False


@pytest.mark.asyncio
async def test_discovery_timeout_does_not_swallow_caller_cancellation(isolated_discovery):
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def handle(_request):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    isolated_discovery(handle)
    pending = asyncio.create_task(discover.probe_local_harnesses(5))
    await asyncio.wait_for(entered.wait(), timeout=0.5)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_discovery_continues_to_healthy_peer_after_one_probe_times_out(
    isolated_discovery, monkeypatch
):
    monkeypatch.setattr(discover, "PROBES", (
        ("opencode", "http://127.0.0.1:4096/global/health", "opencode_health"),
        ("opencode", "http://127.0.0.1:4097/global/health", "opencode_health"),
    ))
    seen = []

    async def handle(request):
        seen.append(request.url.port)
        if request.url.port == 4096:
            await asyncio.Event().wait()
        return httpx.Response(200, json={"healthy": True})

    isolated_discovery(handle)
    found = await asyncio.wait_for(discover.probe_local_harnesses(0.02), timeout=0.5)
    assert seen == [4096, 4097]
    assert found[0]["base_url"] == "http://127.0.0.1:4097"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"x" * 65, b"not-json", b'{"healthy":true,"healthy":false}'])
async def test_discovery_rejects_oversized_or_malformed_probe_bodies(
    isolated_discovery, monkeypatch, body
):
    monkeypatch.setattr(discover, "MAX_DISCOVERY_RESPONSE_BYTES", 64)
    isolated_discovery(lambda _request: httpx.Response(200, content=body))
    assert await discover.probe_local_harnesses() == []


@pytest.mark.asyncio
async def test_discovery_deadline_is_not_extended_by_continuous_body_progress(
    isolated_discovery,
):
    closed = asyncio.Event()

    class TricklingBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            # Every gap is shorter than the 20ms read budget, but completion is not.
            for _ in range(20):
                await asyncio.sleep(0.005)
                yield b" "
            yield b'{"healthy":true}'

        async def aclose(self):
            closed.set()

    isolated_discovery(lambda _request: httpx.Response(200, stream=TricklingBody()))
    assert await discover.probe_local_harnesses(0.02) == []
    assert closed.is_set()
