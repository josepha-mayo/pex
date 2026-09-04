from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.attach import attach_from_settings
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store


@pytest.fixture
async def attach_client(tmp_path):
    settings = Settings.for_test(require_auth=False, home=tmp_path, codex_attach=False)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    await store.connect()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://127.0.0.1",
        ) as client:
            yield client
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://attacker.example",
        "http://attacker.example",
        "http://127.0.0.1:4096/private/path",
        "http://user:password@127.0.0.1:4096",
        "http://127.0.0.1:4096?redirect=https://attacker.example",
    ],
)
async def test_manual_local_http_attach_rejects_non_loopback_or_non_origin_urls(
    attach_client,
    url,
):
    for name in ("opencode", "qwen"):
        response = await attach_client.post(f"/v1/adapters/{name}/attach", json={"url": url})
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_opencode_manual_attach_never_misroutes_bearer_credentials(attach_client):
    response = await attach_client.post(
        "/v1/adapters/opencode/attach",
        json={"url": "http://127.0.0.1:4096", "token": "secret"},
    )
    assert response.status_code == 400
    assert "Basic auth" in response.json()["detail"]


@pytest.mark.asyncio
async def test_devin_manual_attach_requires_bare_https_explicit_token_and_org(attach_client):
    cases = [
        {"url": "http://api.devin.ai", "token": "token", "org_id": "org"},
        {"url": "https://api.devin.ai/v3", "token": "token", "org_id": "org"},
        {"url": "https://api.devin.ai", "org_id": "org"},
        {"url": "https://api.devin.ai", "token": "token"},
        {"url": "https://api.devin.ai", "token": "token", "org_id": "x" * 257},
    ]
    for body in cases:
        response = await attach_client.post("/v1/adapters/devin/attach", json=body)
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_unverified_adapter_cannot_receive_a_generic_http_transport(attach_client):
    response = await attach_client.post(
        "/v1/adapters/claude_code/attach",
        json={"url": "http://127.0.0.1:9999"},
    )
    assert response.status_code == 400
    assert "no verified HTTP attach path" in response.json()["detail"]


@pytest.mark.asyncio
async def test_manual_stdio_attach_rejects_caller_selected_binary(
    attach_client,
    tmp_path,
    monkeypatch,
):
    discovered = tmp_path / "codex-discovered.exe"
    requested = tmp_path / "caller-selected.exe"
    discovered.write_bytes(b"trusted inventory path")
    requested.write_bytes(b"arbitrary executable path")
    monkeypatch.setattr(
        "pex_bridge.adapters.codex_bin.resolve_codex_bin",
        lambda: str(discovered),
    )

    response = await attach_client.post(
        "/v1/adapters/codex/attach",
        json={"bin": str(requested)},
    )
    assert response.status_code == 400
    assert "only the discovered binary" in response.json()["detail"]


@pytest.mark.asyncio
async def test_settings_attach_does_not_fallback_from_an_invalid_explicit_codex_binary(
    tmp_path,
    monkeypatch,
):
    fallback = tmp_path / "fallback-codex.exe"
    fallback.write_bytes(b"fallback")
    monkeypatch.setattr(
        "pex_bridge.adapters.attach.resolve_codex_bin",
        lambda: str(fallback),
    )
    settings = Settings(
        home=tmp_path,
        codex_attach=True,
        codex_bin="relative-codex.exe",
    )
    with pytest.raises(ValueError, match="existing absolute file"):
        await attach_from_settings(AdapterRegistry(), settings)
