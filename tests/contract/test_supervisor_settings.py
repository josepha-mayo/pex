from __future__ import annotations

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_bridge.supervisor_config import (
    SupervisorSecretStoreError,
    load_supervisor_choice,
)


class FakeSecretStore:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, str]] = {}
        self.deleted: list[str] = []

    def put(self, value: str, *, audience: str) -> str:
        reference = f"sec_{len(self.values) + 1:032x}"
        self.values[reference] = (audience, value)
        return reference

    def get(self, reference: str, *, audience: str) -> str | None:
        stored = self.values.get(reference)
        if stored is None:
            return None
        if stored[0] != audience:
            raise SupervisorSecretStoreError("audience mismatch")
        return stored[1]

    def delete(self, reference: str) -> None:
        self.deleted.append(reference)
        self.values.pop(reference, None)


@pytest.fixture
async def supervisor_client(tmp_path):
    from pex_supervisor.providers import configure_runtime

    configure_runtime(None)
    previous = (
        state.settings,
        state.store,
        state.adapters,
        state.bus,
        state.pipeline,
        state.supervisor_choice,
        state.supervisor_error,
        state.supervisor_secret_store,
    )
    settings = Settings.for_test(require_auth=False, home=tmp_path)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    secret_store = FakeSecretStore()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.supervisor_choice = None
    state.supervisor_error = None
    state.supervisor_secret_store = secret_store
    await store.connect()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        yield client, secret_store, tmp_path
    await store.close()
    configure_runtime(None)
    (
        state.settings,
        state.store,
        state.adapters,
        state.bus,
        state.pipeline,
        state.supervisor_choice,
        state.supervisor_error,
        state.supervisor_secret_store,
    ) = previous


def _custom_payload(**updates):
    payload = {
        "expected_revision": 0,
        "provider": "custom",
        "model_id": "winner-model",
        "auth_mode": "custom",
        "protocol": "openai",
        "base_url": "https://models.example.invalid/v1",
    }
    payload.update(updates)
    return payload


@pytest.mark.asyncio
async def test_settings_read_exposes_explicit_first_run_and_committed_revisions(supervisor_client):
    client, _secret_store, _home = supervisor_client
    initial = await client.get("/v1/supervisor")
    assert initial.status_code == 200
    assert initial.json()["revision"] == 0
    assert state.supervisor_choice is None

    saved = await client.patch("/v1/supervisor", json=_custom_payload())
    assert saved.status_code == 200
    current = await client.get("/v1/supervisor")
    assert current.status_code == 200
    assert current.json()["revision"] == saved.json()["revision"] == 1


@pytest.mark.asyncio
async def test_named_byok_constructs_with_exact_vault_key_and_canonical_endpoint(
    supervisor_client, monkeypatch
):
    client, _secret_store, _home = supervisor_client
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    captured = {}

    class FakeOpenAIModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("strands.models.openai.OpenAIModel", FakeOpenAIModel)
    canary = "or-vault-bound-canary"

    response = await client.patch(
        "/v1/supervisor",
        json={
            "expected_revision": 0,
            "provider": "openrouter",
            "model_id": "anthropic/claude-sonnet-4.6",
            "auth_mode": "api_key",
            "api_key": canary,
        },
    )

    assert response.status_code == 200
    assert response.json()["model_loaded"] is True
    assert canary not in response.text
    assert captured["client_args"]["api_key"] == canary
    assert captured["client_args"]["base_url"] == "https://openrouter.ai/api/v1"
    assert state.supervisor_choice is not None
    assert state.supervisor_choice.base_url == "https://openrouter.ai/api/v1"


@pytest.mark.asyncio
@pytest.mark.parametrize("keep_override", [True, False])
async def test_named_provider_key_rotation_uses_explicit_displayed_endpoint(
    supervisor_client, monkeypatch, keep_override
):
    client, _secret_store, _home = supervisor_client
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    captured = []

    class FakeOpenAIModel:
        def __init__(self, **kwargs):
            captured.append(kwargs)

    monkeypatch.setattr("strands.models.openai.OpenAIModel", FakeOpenAIModel)
    override = "https://alternate.example.test/v1"
    initial = await client.patch("/v1/supervisor", json={
        "expected_revision": 0,
        "provider": "groq",
        "auth_mode": "api_key",
        "model_id": "fixture-model",
        "base_url": override,
        "api_key": "fixture-old-key",
    })
    assert initial.status_code == 200
    observed = await client.get("/v1/supervisor")
    assert observed.json()["base_url"] == override

    rotated = await client.patch("/v1/supervisor", json={
        "expected_revision": observed.json()["revision"],
        "provider": "groq",
        "auth_mode": "api_key",
        "model_id": "fixture-model",
        "base_url": observed.json()["base_url"] if keep_override else None,
        "api_key": "fixture-new-key",
    })
    assert rotated.status_code == 200
    expected_endpoint = override if keep_override else "https://api.groq.com/openai/v1"
    assert rotated.json()["base_url"] == expected_endpoint
    assert captured[-1]["client_args"]["base_url"] == expected_endpoint
    assert captured[-1]["client_args"]["api_key"] == "fixture-new-key"
    assert "fixture-new-key" not in rotated.text


@pytest.mark.asyncio
async def test_byok_is_write_only_audience_bound_and_restart_complete(supervisor_client):
    client, secret_store, home = supervisor_client
    canary = "sk-win-canary-do-not-echo"

    response = await client.patch(
        "/v1/supervisor",
        json=_custom_payload(api_key=canary),
    )

    assert response.status_code == 200
    body = response.json()
    dumped = json.dumps(body)
    assert canary not in dumped
    assert "sec_" not in dumped
    assert body["credential_source"] == "secret_store"
    assert body["credential_configured"] is True
    assert body["has_api_key"] is True
    assert body["revision"] == 1

    config_path = home / "supervisor.json"
    persisted_text = config_path.read_text(encoding="utf-8")
    assert canary not in persisted_text
    persisted = load_supervisor_choice(config_path)
    assert persisted is not None
    assert persisted.secret_ref is not None
    assert secret_store.get(
        persisted.secret_ref,
        audience=persisted.credential_audience(),
    ) == canary

    # Re-resolve the exact persisted snapshot as startup does; no environment
    # fallback is involved and no secret/ref enters the public representation.
    from pex_bridge.app import _activate_supervisor_choice

    info, _model = _activate_supervisor_choice(persisted)
    assert info.get("disabled") is True  # unit tests never spend a live key
    public = persisted.public_dict(has_api_key=True)
    assert canary not in json.dumps(public)
    assert "secret_ref" not in public


@pytest.mark.asyncio
async def test_model_only_patch_keeps_secret_but_endpoint_change_clears_it(
    supervisor_client,
):
    client, secret_store, home = supervisor_client
    created = await client.patch(
        "/v1/supervisor",
        json=_custom_payload(api_key="bound-secret"),
    )
    assert created.status_code == 200
    original = load_supervisor_choice(home / "supervisor.json")
    assert original is not None and original.secret_ref

    model_only = await client.patch(
        "/v1/supervisor",
        json={"expected_revision": 1, "model_id": "winner-model-v2"},
    )
    assert model_only.status_code == 200
    retained = load_supervisor_choice(home / "supervisor.json")
    assert retained is not None
    assert retained.secret_ref == original.secret_ref
    assert retained.revision == 2
    assert original.secret_ref not in secret_store.deleted

    rerouted = await client.patch(
        "/v1/supervisor",
        json={
            "expected_revision": 2,
            "base_url": "https://other.example.invalid/v1",
        },
    )
    assert rerouted.status_code == 200
    cleared = load_supervisor_choice(home / "supervisor.json")
    assert cleared is not None
    assert cleared.credential_source == "none"
    assert cleared.secret_ref is None
    assert original.secret_ref in secret_store.deleted


@pytest.mark.asyncio
async def test_stale_revision_loses_without_mutating_committed_config(supervisor_client):
    client, _secret_store, home = supervisor_client
    first = await client.patch("/v1/supervisor", json=_custom_payload())
    assert first.status_code == 200
    before = (home / "supervisor.json").read_bytes()

    stale = await client.patch(
        "/v1/supervisor",
        json={"expected_revision": 0, "model_id": "stale-writer"},
    )

    assert stale.status_code == 409
    assert (home / "supervisor.json").read_bytes() == before
    assert state.supervisor_choice is not None
    assert state.supervisor_choice.model_id == "winner-model"


@pytest.mark.asyncio
async def test_invalid_secret_validation_never_echoes_input(supervisor_client):
    client, _secret_store, home = supervisor_client
    canary = "sk-secret-validation-canary"
    invalid = canary * 800

    response = await client.patch(
        "/v1/supervisor",
        json=_custom_payload(api_key=invalid),
    )

    assert response.status_code == 422
    assert canary not in response.text
    assert not (home / "supervisor.json").exists()


@pytest.mark.asyncio
async def test_secret_store_failure_rolls_back_without_config_or_echo(supervisor_client):
    client, secret_store, home = supervisor_client
    canary = "sk-store-failure-canary"

    def fail_put(_value: str, *, audience: str) -> str:
        assert len(audience) == 64
        raise SupervisorSecretStoreError("backend contained " + canary)

    secret_store.put = fail_put  # type: ignore[method-assign]
    response = await client.patch(
        "/v1/supervisor",
        json=_custom_payload(api_key=canary),
    )

    assert response.status_code == 503
    assert canary not in response.text
    assert not (home / "supervisor.json").exists()
    assert state.supervisor_choice is None


@pytest.mark.asyncio
async def test_secret_rotation_and_explicit_clear_retire_previous_values(supervisor_client):
    client, secret_store, home = supervisor_client
    first = await client.patch(
        "/v1/supervisor", json=_custom_payload(api_key="first-secret")
    )
    assert first.status_code == 200
    original = load_supervisor_choice(home / "supervisor.json")
    assert original is not None and original.secret_ref

    rotated = await client.patch(
        "/v1/supervisor",
        json={"expected_revision": 1, "api_key": "second-secret"},
    )
    assert rotated.status_code == 200
    replacement = load_supervisor_choice(home / "supervisor.json")
    assert replacement is not None and replacement.secret_ref
    assert replacement.secret_ref != original.secret_ref
    assert original.secret_ref in secret_store.deleted
    assert secret_store.get(
        replacement.secret_ref,
        audience=replacement.credential_audience(),
    ) == "second-secret"

    cleared = await client.patch(
        "/v1/supervisor",
        json={"expected_revision": 2, "clear_api_key": True},
    )
    assert cleared.status_code == 200
    final = load_supervisor_choice(home / "supervisor.json")
    assert final is not None
    assert final.credential_source == "none"
    assert final.secret_ref is None
    assert replacement.secret_ref in secret_store.deleted


@pytest.mark.asyncio
async def test_config_write_failure_deletes_staged_secret_and_keeps_prior_state(
    supervisor_client, monkeypatch
):
    client, secret_store, home = supervisor_client
    first = await client.patch(
        "/v1/supervisor", json=_custom_payload(api_key="committed-secret")
    )
    assert first.status_code == 200
    before = (home / "supervisor.json").read_bytes()
    committed = state.supervisor_choice
    assert committed is not None and committed.secret_ref

    def fail_save(*_args, **_kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr("pex_bridge.app.save_supervisor_choice", fail_save)
    failed = await client.patch(
        "/v1/supervisor",
        json={"expected_revision": 1, "api_key": "uncommitted-secret"},
    )

    assert failed.status_code == 503
    assert (home / "supervisor.json").read_bytes() == before
    assert state.supervisor_choice == committed
    assert committed.secret_ref in secret_store.values
    assert any(reference != committed.secret_ref for reference in secret_store.deleted)


@pytest.mark.asyncio
async def test_model_constructor_failure_rolls_back_and_never_logs_secret(
    supervisor_client, monkeypatch, caplog
):
    client, secret_store, home = supervisor_client
    first = await client.patch("/v1/supervisor", json=_custom_payload())
    assert first.status_code == 200
    before = (home / "supervisor.json").read_bytes()
    canary = "sk-constructor-failure-canary"

    def fail_model(_config):
        raise RuntimeError("provider failure containing " + canary)

    monkeypatch.setattr("pex_supervisor.providers.load_supervisor_model", fail_model)
    failed = await client.patch(
        "/v1/supervisor",
        json={"expected_revision": 1, "api_key": canary},
    )

    assert failed.status_code == 409
    assert canary not in failed.text
    assert canary not in caplog.text
    assert (home / "supervisor.json").read_bytes() == before
    assert state.supervisor_choice is not None
    assert state.supervisor_choice.revision == 1
    assert secret_store.values == {}
    assert secret_store.deleted


@pytest.mark.asyncio
async def test_missing_restart_secret_fails_closed_without_ambient_fallback(
    supervisor_client, monkeypatch
):
    client, secret_store, home = supervisor_client
    created = await client.patch(
        "/v1/supervisor", json=_custom_payload(api_key="restart-secret")
    )
    assert created.status_code == 200
    persisted = load_supervisor_choice(home / "supervisor.json")
    assert persisted is not None and persisted.secret_ref
    secret_store.values.pop(persisted.secret_ref)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ambient-must-not-recover")

    from pex_bridge.app import _activate_supervisor_choice

    with pytest.raises(ValueError, match="did not resolve"):
        _activate_supervisor_choice(persisted)


@pytest.mark.asyncio
async def test_concurrent_compare_and_swap_allows_exactly_one_writer(supervisor_client):
    client, _secret_store, home = supervisor_client
    first = await client.patch("/v1/supervisor", json=_custom_payload())
    assert first.status_code == 200

    left, right = await asyncio.gather(
        client.patch(
            "/v1/supervisor",
            json={"expected_revision": 1, "model_id": "left-model"},
        ),
        client.patch(
            "/v1/supervisor",
            json={"expected_revision": 1, "model_id": "right-model"},
        ),
    )

    assert sorted((left.status_code, right.status_code)) == [200, 409]
    persisted = load_supervisor_choice(home / "supervisor.json")
    assert persisted is not None
    assert persisted.revision == 2
    assert persisted.model_id in {"left-model", "right-model"}
