from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.codex import CodexAdapter
from pex_bridge.app import create_app, state
from pex_bridge.codex_shared_attach import SharedCodexAttachments
from pex_bridge.config import Settings
from pex_protocol.capabilities import AdapterCapabilities, AdapterSupportLabel


@pytest.fixture
async def attachment(tmp_path, monkeypatch):
    import pex_bridge.app as module

    registry = AdapterRegistry()
    manager = SharedCodexAttachments()
    constructed = []
    probes = []
    pumps = []
    probe_started = asyncio.Event()
    probe_release = asyncio.Event()
    probe_release.set()
    result = SimpleNamespace(fail=False, pump_fail=False)

    class Transport:
        initialized = False

        def __init__(self, binary):
            self.binary = binary
            self.closed = False
            constructed.append(self)

        async def close(self):
            self.closed = True

    async def probe(adapter):
        probes.append(adapter)
        probe_started.set()
        await probe_release.wait()
        if result.fail:
            return AdapterCapabilities()
        adapter.transport.initialized = True
        return AdapterCapabilities(support_label=AdapterSupportLabel.BASIC, send_message=True)

    def pump(adapter, ingest):
        if result.pump_fail and adapter is not original:
            raise RuntimeError("fake pump failure")
        adapter._pump_task = asyncio.create_task(asyncio.Event().wait())
        pumps.append(adapter._pump_task)
        return adapter._pump_task

    async def found():
        return [{"name": "codex", "kind": "stdio", "bin": "C:/fake/codex.exe"}]

    original = registry.codex
    monkeypatch.setattr(state, "adapters", registry)
    monkeypatch.setattr(state, "codex_shared_attachments", manager)
    monkeypatch.setattr(state, "pipeline", SimpleNamespace(ingest_event=None))
    monkeypatch.setattr(state, "settings", Settings.for_test(home=tmp_path, require_auth=False))
    monkeypatch.setattr(module, "_resolved_attach_binary", lambda *args: "C:/fake/codex.exe")
    monkeypatch.setattr(module, "_bounded_adapter_probe", probe)
    monkeypatch.setattr("pex_bridge.adapters.codex.CodexStdioTransport", Transport)
    monkeypatch.setattr("pex_bridge.adapters.codex_bin.resolve_codex_bin", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.probe_local_harnesses", found)
    monkeypatch.setattr(CodexAdapter, "start_pipeline_pump", pump)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://127.0.0.1"
    ) as client:
        yield SimpleNamespace(
            client=client,
            registry=registry,
            manager=manager,
            constructed=constructed,
            probes=probes,
            pumps=pumps,
            original=original,
            probe_started=probe_started,
            probe_release=probe_release,
            result=result,
            start_pump=pump,
        )
    for task in pumps:
        task.cancel()
    await asyncio.gather(*pumps, return_exceptions=True)


@pytest.fixture(params=["manual", "discovery"])
def endpoint(request):
    if request.param == "manual":
        return "/v1/adapters/codex/attach", {}
    return "/v1/discover/attach", {"name": "codex", "kind": "stdio"}


async def post(fixture, endpoint):
    path, body = endpoint
    return await fixture.client.post(path, json=body)


@pytest.mark.asyncio
async def test_waiting_attach_has_no_side_effects_and_refreshes_registry(attachment, endpoint):
    f = attachment
    await f.manager.lock.acquire()
    request = asyncio.create_task(post(f, endpoint))
    try:
        await asyncio.sleep(0.02)
        assert not request.done()
        assert f.constructed == f.probes == []
        replacement = SimpleNamespace(name="codex", transport=object())
        f.registry.bind("codex", replacement)
    finally:
        f.manager.lock.release()
    response = await request
    assert response.status_code == 409
    assert f.registry.get("codex") is replacement
    assert f.constructed == []


@pytest.mark.asyncio
@pytest.mark.parametrize("active", [False, True])
async def test_existing_connection_is_preserved(attachment, endpoint, active):
    f = attachment
    transport = object()
    if active:
        # A shared adapter has no legacy attach_transport method.
        prior = SimpleNamespace(name="codex", transport=transport)
        f.registry.bind("codex", prior)
        f.manager.active = ("inspection", "selection", prior)
    else:
        prior = f.original
        prior.transport = transport
    response = await post(f, endpoint)
    assert response.status_code == 409
    assert f.registry.get("codex") is prior
    assert prior.transport is transport
    assert f.constructed == f.probes == []


@pytest.mark.asyncio
async def test_bare_adapter_publishes_verified_candidate_and_labels_isolation(attachment, endpoint):
    f = attachment
    old_pump = f.start_pump(f.original, None)
    response = await post(f, endpoint)
    assert response.status_code == 200
    assert response.json()["isolated"] is True
    assert response.json()["existing_worker"] is False
    assert response.json()["support"] == "basic"
    candidate = f.registry.get("codex")
    assert candidate is not f.original
    assert candidate.transport is f.constructed[0]
    assert not candidate.transport.closed
    assert old_pump.cancelled()
    assert candidate._pump_task is not None
    assert f.original.transport is None


@pytest.mark.asyncio
async def test_failed_probe_discards_candidate_without_stopping_prior_pump(attachment, endpoint):
    f = attachment
    old_pump = f.start_pump(f.original, None)
    f.result.fail = True
    response = await post(f, endpoint)
    assert response.status_code == 502
    assert f.registry.get("codex") is f.original
    assert not old_pump.done()
    assert f.constructed[0].closed
    assert f.original.transport is None


@pytest.mark.asyncio
async def test_cancelled_probe_discards_candidate_without_stopping_prior_pump(attachment, endpoint):
    f = attachment
    old_pump = f.start_pump(f.original, None)
    f.probe_release.clear()
    request = asyncio.create_task(post(f, endpoint))
    await asyncio.wait_for(f.probe_started.wait(), 1)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert f.registry.get("codex") is f.original
    assert not old_pump.done()
    assert f.constructed[0].closed
    assert f.original.transport is None


@pytest.mark.asyncio
async def test_pump_start_failure_rolls_back_and_restarts_prior_pump(attachment, endpoint):
    f = attachment
    old_pump = f.start_pump(f.original, None)
    f.result.pump_fail = True
    with pytest.raises(RuntimeError, match="fake pump failure"):
        await post(f, endpoint)
    assert old_pump.cancelled()
    assert f.registry.get("codex") is f.original
    assert f.original._pump_task is not old_pump
    assert not f.original._pump_task.done()
    assert f.constructed[0].closed


@pytest.mark.asyncio
async def test_second_legacy_route_cannot_replace_first_attachment(attachment):
    f = attachment
    f.probe_release.clear()
    first = asyncio.create_task(post(f, ("/v1/adapters/codex/attach", {})))
    await asyncio.wait_for(f.probe_started.wait(), 1)
    second = asyncio.create_task(
        post(f, ("/v1/discover/attach", {"name": "codex", "kind": "stdio"}))
    )
    await asyncio.sleep(0.02)
    assert len(f.constructed) == 1
    f.probe_release.set()
    assert (await first).status_code == 200
    assert (await second).status_code == 409
    assert len(f.constructed) == 1


@pytest.mark.asyncio
async def test_closed_manager_refuses_attachment_before_construction(attachment, endpoint):
    f = attachment
    await f.manager.close_pending()
    response = await post(f, endpoint)
    assert response.status_code == 409
    assert f.constructed == []


@pytest.mark.asyncio
async def test_registry_change_during_probe_is_not_overwritten(attachment, endpoint):
    f = attachment
    f.probe_release.clear()
    request = asyncio.create_task(post(f, endpoint))
    await asyncio.wait_for(f.probe_started.wait(), 1)
    replacement = SimpleNamespace(name="codex", transport=object())
    f.registry.bind("codex", replacement)
    f.probe_release.set()
    response = await request
    assert response.status_code == 409
    assert f.registry.get("codex") is replacement
    assert f.constructed[0].closed


@pytest.mark.asyncio
async def test_cancellation_during_prior_pump_join_restores_prior_pump(attachment, endpoint):
    f = attachment
    running = asyncio.Event()
    stopping = asyncio.Event()

    async def old_worker():
        running.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            stopping.set()
            await asyncio.Event().wait()

    old_pump = asyncio.create_task(old_worker())
    f.pumps.append(old_pump)
    f.original._pump_task = old_pump
    await asyncio.wait_for(running.wait(), 1)
    request = asyncio.create_task(post(f, endpoint))
    await asyncio.wait_for(stopping.wait(), 1)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert f.registry.get("codex") is f.original
    assert f.original._pump_task is not old_pump
    assert not f.original._pump_task.done()
    assert f.constructed[0].closed


@pytest.mark.asyncio
@pytest.mark.parametrize("closed", [False, True])
async def test_lifespan_refreshes_only_closed_attachment_manager(attachment, monkeypatch, closed):
    from pex_bridge.app import lifespan

    f = attachment
    f.manager.closed = closed

    async def unavailable_store():
        # Stop before any real startup, provider, adapter, or process work.
        raise RuntimeError("fixture store unavailable")

    async def close_store():
        pass

    monkeypatch.setattr(
        state,
        "store",
        SimpleNamespace(
            path=state.settings.home / "fixture.sqlite",
            connect=unavailable_store,
            close=close_store,
        ),
    )
    with pytest.raises(RuntimeError, match="fixture store unavailable"):
        async with lifespan(None):
            pytest.fail("fixture must stop before runtime startup")
    assert (state.codex_shared_attachments is f.manager) is (not closed)
    assert not state.codex_shared_attachments.closed
