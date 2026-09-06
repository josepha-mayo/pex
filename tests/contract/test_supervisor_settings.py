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
    SupervisorChoice,
    SupervisorSecretStoreError,
    load_supervisor_choice,
)


class FakeSecretStore:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, str]] = {}
        self.deleted: list[str] = []
        self.next_reference = 1

    def put(self, value: str, *, audience: str) -> str:
        reference = f"sec_{self.next_reference:032x}"
        self.next_reference += 1
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
        state.supervisor_api_key_present,
        state.supervisor_credential_status,
        state.supervisor_secret_store,
        state.supervisor_config_lock,
        state.supervisor_config_generation,
        state.supervisor_config_task,
        state.supervisor_config_operation,
    )
    previous_background_tasks = set(state.background_tasks)
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
    state.supervisor_api_key_present = False
    state.supervisor_credential_status = "not_configured"
    state.supervisor_secret_store = secret_store
    state.supervisor_config_lock = asyncio.Lock()
    state.supervisor_config_generation = 0
    state.supervisor_config_task = None
    state.supervisor_config_operation = None
    await store.connect()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        yield client, secret_store, tmp_path
    operation = state.supervisor_config_operation
    active = state.supervisor_config_task
    if operation is not None:
        operation.abandoned.set()
        if not operation.commit.done():
            operation.commit.set_result(False)
    if active is not None:
        try:
            await asyncio.wait_for(asyncio.shield(active), timeout=1.25)
        except TimeoutError:
            active.cancel()
            await asyncio.gather(active, return_exceptions=True)
        except asyncio.CancelledError:
            await asyncio.gather(active, return_exceptions=True)
        except Exception:
            pass
        async with state.supervisor_config_lock:
            if state.supervisor_config_task is active:
                state.supervisor_config_task = None
                state.supervisor_config_operation = None
    assert state.supervisor_config_task is None
    assert state.supervisor_config_operation is None
    fixture_background = state.background_tasks - previous_background_tasks
    if fixture_background:
        try:
            await asyncio.wait_for(
                asyncio.gather(*fixture_background, return_exceptions=True),
                timeout=1.25,
            )
        except TimeoutError:
            for task in fixture_background:
                task.cancel()
            await asyncio.gather(*fixture_background, return_exceptions=True)
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
        state.supervisor_api_key_present,
        state.supervisor_credential_status,
        state.supervisor_secret_store,
        state.supervisor_config_lock,
        state.supervisor_config_generation,
        state.supervisor_config_task,
        state.supervisor_config_operation,
    ) = previous


async def _wait_until(predicate, *, attempts: int = 100) -> None:
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(0.01)
    assert predicate()


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
async def test_settings_read_never_calls_blocking_secret_store(supervisor_client, monkeypatch):
    client, secret_store, _home = supervisor_client
    saved = await client.patch(
        "/v1/supervisor", json=_custom_payload(api_key="stored-secret")
    )
    assert saved.status_code == 200

    def forbidden_get(*_args, **_kwargs):
        raise AssertionError("settings read must not enter the OS credential backend")

    monkeypatch.setattr(secret_store, "get", forbidden_get)
    current, health = await asyncio.gather(
        client.get("/v1/supervisor"),
        client.get("/health"),
    )

    assert current.status_code == health.status_code == 200
    assert current.json()["has_api_key"] is True
    assert current.json()["credential_status"] == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_phase", ["hung_vault", "constructor_error"])
async def test_saved_supervisor_activation_cannot_block_bridge_health(
    supervisor_client, monkeypatch, failure_phase
):
    from pex_bridge.app import _activate_saved_supervisor_choice

    client, secret_store, _home = supervisor_client
    choice = SupervisorChoice(
        provider="custom",
        model_id="startup-model",
        auth_mode="api_key" if failure_phase == "hung_vault" else "custom",
        protocol="openai",
        base_url="https://models.example.invalid/v1",
        credential_source="secret_store" if failure_phase == "hung_vault" else "none",
        secret_ref=("sec_" + "1" * 32) if failure_phase == "hung_vault" else None,
    )
    entered = __import__("threading").Event()
    release = __import__("threading").Event()
    if failure_phase == "hung_vault":
        monkeypatch.setattr("pex_bridge.app._SUPERVISOR_CONFIG_TIMEOUT_SECONDS", 0.02)

        def blocking_get(*_args, **_kwargs):
            entered.set()
            release.wait()
            return "startup-secret"

        monkeypatch.setattr(secret_store, "get", blocking_get)
    else:

        def broken_constructor(_config):
            entered.set()
            raise RuntimeError("constructor exploded")

        monkeypatch.setattr("pex_supervisor.providers.load_supervisor_model", broken_constructor)

    state.supervisor_choice = choice
    state.pipeline.model = None
    state.supervisor_error = "SupervisorLoading"
    state.supervisor_credential_status = (
        "configured_unverified" if failure_phase == "hung_vault" else "not_configured"
    )
    state.supervisor_config_generation += 1
    generation = state.supervisor_config_generation
    activation = asyncio.create_task(
        _activate_saved_supervisor_choice(choice, generation),
        name=f"supervisor-startup:{generation}",
    )
    state.track_background(activation)
    try:
        assert await asyncio.to_thread(entered.wait, 0.5)
        health = await asyncio.wait_for(client.get("/health"), timeout=0.2)
        settings = await asyncio.wait_for(client.get("/v1/supervisor"), timeout=0.2)
        assert health.status_code == settings.status_code == 200
        assert settings.json()["has_api_key"] is False
        assert settings.json()["credential_configured"] is (
            failure_phase == "hung_vault"
        )
        assert settings.json()["credential_status"] == (
            "configured_unverified"
            if failure_phase == "hung_vault"
            else "not_configured"
        )
        await asyncio.wait_for(activation, timeout=0.2)
        if failure_phase == "constructor_error":
            assert state.supervisor_error == "RuntimeError"
            assert state.pipeline.model is None
        else:
            assert state.supervisor_error == "SupervisorActivationTimeout"
    finally:
        release.set()
        if not activation.done():
            activation.cancel()
        await asyncio.gather(activation, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "startup_source", ["saved_secret", "environment_auto", "environment_success"]
)
async def test_lifespan_exits_while_supervisor_activation_remains_hung(
    tmp_path, monkeypatch, startup_source
):
    from pex_supervisor.providers import configure_runtime

    previous = (
        state.settings,
        state.store,
        state.adapters,
        state.bus,
        state.pipeline,
        state.supervisor_choice,
        state.supervisor_error,
        state.supervisor_api_key_present,
        state.supervisor_credential_status,
        state.supervisor_secret_store,
        state.supervisor_config_lock,
        state.supervisor_config_generation,
        state.supervisor_config_task,
        state.supervisor_config_operation,
    )
    settings = Settings.for_test(require_auth=False, home=tmp_path)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    secret_store = FakeSecretStore()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.supervisor_choice = None
    state.supervisor_error = None
    state.supervisor_api_key_present = False
    state.supervisor_credential_status = "not_configured"
    state.supervisor_secret_store = secret_store
    state.supervisor_config_lock = asyncio.Lock()
    state.supervisor_config_generation = 0
    state.supervisor_config_task = None
    state.supervisor_config_operation = None
    configure_runtime(None)
    choice = (
        SupervisorChoice(
            provider="custom",
            model_id="startup-model",
            auth_mode="api_key",
            protocol="openai",
            base_url="https://models.example.invalid/v1",
            credential_source="secret_store",
            secret_ref="sec_" + "2" * 32,
        )
        if startup_source == "saved_secret"
        else None
    )
    entered = __import__("threading").Event()
    release = __import__("threading").Event()
    loaded_model = object()

    def blocking_get(*_args, **_kwargs):
        entered.set()
        release.wait()
        return "startup-secret"

    if startup_source == "saved_secret":
        monkeypatch.setattr(secret_store, "get", blocking_get)
    elif startup_source == "environment_auto":
        monkeypatch.setattr(
            "pex_supervisor.providers.load_supervisor_model", lambda: blocking_get()
        )
    else:

        def load_environment_model():
            entered.set()
            return loaded_model

        monkeypatch.setattr(
            "pex_supervisor.providers.load_supervisor_model", load_environment_model
        )
    monkeypatch.setattr("pex_bridge.app.load_supervisor_choice", lambda _path: choice)
    monkeypatch.setattr("pex_bridge.app._SUPERVISOR_CONFIG_TIMEOUT_SECONDS", 60.0)
    app = create_app()

    async def enter_and_exit() -> None:
        async with app.router.lifespan_context(app):
            assert await asyncio.to_thread(entered.wait, 0.5)
            if startup_source == "environment_success":
                await _wait_until(lambda: state.pipeline.model is loaded_model)
                assert state.supervisor_error is None

    try:
        await asyncio.wait_for(enter_and_exit(), timeout=3.0)
        assert not release.is_set()
    finally:
        release.set()
        configure_runtime(None)
        (
            state.settings,
            state.store,
            state.adapters,
            state.bus,
            state.pipeline,
            state.supervisor_choice,
            state.supervisor_error,
            state.supervisor_api_key_present,
            state.supervisor_credential_status,
            state.supervisor_secret_store,
            state.supervisor_config_lock,
            state.supervisor_config_generation,
            state.supervisor_config_task,
            state.supervisor_config_operation,
        ) = previous


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
    await _wait_until(lambda: original.secret_ref in secret_store.deleted)


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
    await _wait_until(lambda: original.secret_ref in secret_store.deleted)
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
    await _wait_until(lambda: replacement.secret_ref in secret_store.deleted)


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
async def test_malformed_vault_reference_is_retired_before_patch_fails(
    supervisor_client, monkeypatch
):
    client, secret_store, home = supervisor_client

    def malformed_put(value: str, *, audience: str) -> str:
        reference = "malformed-reference"
        secret_store.values[reference] = (audience, value)
        return reference

    monkeypatch.setattr(secret_store, "put", malformed_put)
    failed = await client.patch(
        "/v1/supervisor",
        json=_custom_payload(api_key="must-be-retired"),
    )

    assert failed.status_code == 400
    assert not (home / "supervisor.json").exists()
    assert state.supervisor_choice is None
    assert "malformed-reference" in secret_store.deleted
    assert secret_store.values == {}


@pytest.mark.asyncio
async def test_published_abandoned_ref_delete_starts_before_background_cancellation(
    supervisor_client
):
    from pex_bridge.app import (
        _abandon_supervisor_operation,
        _SupervisorConfigOperation,
    )

    _client, secret_store, _home = supervisor_client
    loop = asyncio.get_running_loop()
    operation = _SupervisorConfigOperation(
        generation=99,
        prepared=loop.create_future(),
        commit=loop.create_future(),
    )
    reference = secret_store.put("staged", audience="a" * 64)
    assert operation.publish_staged_reference(reference) is False

    observer = _abandon_supervisor_operation(operation, secret_store)
    assert observer is not None
    observer.cancel()
    await asyncio.gather(observer, return_exceptions=True)
    await _wait_until(lambda: reference in secret_store.deleted)
    assert reference not in secret_store.values


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
    # Construction now happens before vault staging, so this failure has no
    # uncommitted credential to retire.
    assert secret_store.deleted == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hostile_error", [SystemExit, KeyboardInterrupt, asyncio.CancelledError]
)
async def test_hostile_constructor_base_exception_is_sanitized_and_rolled_back(
    supervisor_client, monkeypatch, caplog, hostile_error
):
    from pex_supervisor.providers import current_runtime_config

    client, secret_store, home = supervisor_client
    first = await client.patch("/v1/supervisor", json=_custom_payload())
    assert first.status_code == 200
    before_file = (home / "supervisor.json").read_bytes()
    before_choice = state.supervisor_choice
    before_model = state.pipeline.model
    before_runtime = current_runtime_config()

    def fail_model(_config):
        raise hostile_error("hostile worker exit")

    monkeypatch.setattr("pex_supervisor.providers.load_supervisor_model", fail_model)
    failed = await client.patch(
        "/v1/supervisor",
        json={"expected_revision": 1, "api_key": "must-not-leak"},
    )

    assert failed.status_code == 409
    assert (await client.get("/health")).status_code == 200
    assert (home / "supervisor.json").read_bytes() == before_file
    assert state.supervisor_choice == before_choice
    assert state.pipeline.model is before_model
    assert current_runtime_config() == before_runtime
    assert secret_store.values == {}
    assert "Task exception was never retrieved" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hostile_error", [SystemExit, KeyboardInterrupt, asyncio.CancelledError]
)
async def test_hostile_vault_base_exception_is_sanitized_and_rolled_back(
    supervisor_client, monkeypatch, caplog, hostile_error
):
    from pex_supervisor.providers import current_runtime_config

    client, secret_store, home = supervisor_client
    first = await client.patch("/v1/supervisor", json=_custom_payload())
    assert first.status_code == 200
    before_file = (home / "supervisor.json").read_bytes()
    before_choice = state.supervisor_choice
    before_model = state.pipeline.model
    before_runtime = current_runtime_config()

    def fail_put(_value: str, *, audience: str) -> str:
        assert audience
        raise hostile_error("hostile vault exit")

    monkeypatch.setattr(secret_store, "put", fail_put)
    failed = await client.patch(
        "/v1/supervisor",
        json={"expected_revision": 1, "api_key": "must-not-leak"},
    )

    assert failed.status_code == 409
    assert (await client.get("/health")).status_code == 200
    assert (home / "supervisor.json").read_bytes() == before_file
    assert state.supervisor_choice == before_choice
    assert state.pipeline.model is before_model
    assert current_runtime_config() == before_runtime
    assert secret_store.values == {}
    assert "Task exception was never retrieved" not in caplog.text


@pytest.mark.asyncio
async def test_model_constructor_timeout_quarantines_until_worker_finishes(
    supervisor_client, monkeypatch
):
    client, secret_store, home = supervisor_client
    first = await client.patch("/v1/supervisor", json=_custom_payload())
    assert first.status_code == 200
    before = (home / "supervisor.json").read_bytes()
    entered = __import__("threading").Event()
    release = __import__("threading").Event()

    def block_model(_config):
        entered.set()
        release.wait(1)
        return object()

    monkeypatch.setattr("pex_supervisor.providers.load_supervisor_model", block_model)
    monkeypatch.setattr("pex_bridge.app._SUPERVISOR_CONFIG_TIMEOUT_SECONDS", 0.02)
    timed_out = await client.patch(
        "/v1/supervisor",
        json={"expected_revision": 1, "api_key": "timeout-secret"},
    )
    assert entered.is_set()
    assert timed_out.status_code == 504
    assert (await asyncio.wait_for(client.get("/health"), 0.25)).status_code == 200
    refused = await client.patch(
        "/v1/supervisor",
        json={"expected_revision": 1, "model_id": "must-not-overlap"},
    )
    assert refused.status_code == 503
    assert (home / "supervisor.json").read_bytes() == before
    assert secret_store.values == {}

    release.set()
    for _ in range(100):
        if state.supervisor_config_task is None:
            break
        await asyncio.sleep(0.01)
    assert state.supervisor_config_task is None


@pytest.mark.asyncio
async def test_cancelled_model_construction_never_commits_or_stages_secret(
    supervisor_client, monkeypatch
):
    client, secret_store, home = supervisor_client
    first = await client.patch("/v1/supervisor", json=_custom_payload())
    assert first.status_code == 200
    before = (home / "supervisor.json").read_bytes()
    entered = __import__("threading").Event()
    release = __import__("threading").Event()

    def block_model(_config):
        entered.set()
        release.wait(1)
        return object()

    monkeypatch.setattr("pex_supervisor.providers.load_supervisor_model", block_model)
    request = asyncio.create_task(client.patch(
        "/v1/supervisor",
        json={"expected_revision": 1, "api_key": "cancelled-secret"},
    ))
    assert await asyncio.to_thread(entered.wait, 0.25)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    refused = await client.patch(
        "/v1/supervisor",
        json={"expected_revision": 1, "model_id": "must-not-overlap"},
    )
    assert refused.status_code == 503
    assert (home / "supervisor.json").read_bytes() == before
    assert secret_store.values == {}

    release.set()
    for _ in range(100):
        if state.supervisor_config_task is None:
            break
        await asyncio.sleep(0.01)
    assert state.supervisor_config_task is None


@pytest.mark.asyncio
async def test_cancelled_vault_write_is_cleaned_before_quarantine_releases(
    supervisor_client, monkeypatch
):
    client, secret_store, home = supervisor_client
    first = await client.patch("/v1/supervisor", json=_custom_payload())
    assert first.status_code == 200
    before = (home / "supervisor.json").read_bytes()
    entered = __import__("threading").Event()
    release = __import__("threading").Event()
    original_put = secret_store.put

    def block_put(value: str, *, audience: str) -> str:
        entered.set()
        release.wait(1)
        return original_put(value, audience=audience)

    monkeypatch.setattr(secret_store, "put", block_put)
    request = asyncio.create_task(client.patch(
        "/v1/supervisor",
        json={"expected_revision": 1, "api_key": "cancelled-vault-secret"},
    ))
    assert await asyncio.to_thread(entered.wait, 0.25)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert (await client.patch(
        "/v1/supervisor",
        json={"expected_revision": 1, "model_id": "must-not-overlap"},
    )).status_code == 503

    release.set()
    for _ in range(100):
        if state.supervisor_config_task is None:
            break
        await asyncio.sleep(0.01)
    assert state.supervisor_config_task is None
    assert (home / "supervisor.json").read_bytes() == before
    assert secret_store.values == {}
    assert secret_store.deleted


@pytest.mark.asyncio
@pytest.mark.parametrize("blocking_phase", ["constructor", "vault"])
async def test_lifespan_shutdown_abandons_active_supervisor_transaction(
    tmp_path, monkeypatch, blocking_phase
):
    from pex_supervisor.providers import configure_runtime

    previous = (
        state.settings,
        state.store,
        state.adapters,
        state.bus,
        state.pipeline,
        state.supervisor_choice,
        state.supervisor_error,
        state.supervisor_api_key_present,
        state.supervisor_credential_status,
        state.supervisor_secret_store,
        state.supervisor_config_lock,
        state.supervisor_config_generation,
        state.supervisor_config_task,
        state.supervisor_config_operation,
    )
    settings = Settings.for_test(require_auth=False, home=tmp_path)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    secret_store = FakeSecretStore()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.supervisor_choice = None
    state.supervisor_error = None
    state.supervisor_api_key_present = False
    state.supervisor_credential_status = "not_configured"
    state.supervisor_secret_store = secret_store
    state.supervisor_config_lock = asyncio.Lock()
    state.supervisor_config_generation = 0
    state.supervisor_config_task = None
    state.supervisor_config_operation = None
    configure_runtime(None)
    home = tmp_path
    entered = __import__("threading").Event()
    release = __import__("threading").Event()
    monkeypatch.setattr("pex_bridge.app.TRANSPORT_CLOSE_TIMEOUT_SECONDS", 0.05)

    if blocking_phase == "constructor":

        def block_model(_config):
            entered.set()
            release.wait()
            return object()

        monkeypatch.setattr("pex_supervisor.providers.load_supervisor_model", block_model)
    else:
        original_put = secret_store.put

        def block_put(value: str, *, audience: str) -> str:
            entered.set()
            release.wait()
            return original_put(value, audience=audience)

        monkeypatch.setattr(secret_store, "put", block_put)

    app = create_app()
    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://127.0.0.1"
            ) as client:
                before_file = (
                    (home / "supervisor.json").read_bytes()
                    if (home / "supervisor.json").exists()
                    else None
                )
                before_choice = state.supervisor_choice
                request = asyncio.create_task(
                    client.patch(
                        "/v1/supervisor",
                        json=_custom_payload(api_key="shutdown-secret"),
                    )
                )
                assert await asyncio.to_thread(entered.wait, 0.5)
        release.set()
        response = await request
        assert response.status_code in {409, 503, 504}
        after_file = (
            (home / "supervisor.json").read_bytes()
            if (home / "supervisor.json").exists()
            else None
        )
        assert after_file == before_file
        assert state.supervisor_choice == before_choice
        assert secret_store.values == {}
        if blocking_phase == "vault":
            assert secret_store.deleted
        assert state.supervisor_config_task is None
        assert state.supervisor_config_operation is None
    finally:
        release.set()
        configure_runtime(None)
        (
            state.settings,
            state.store,
            state.adapters,
            state.bus,
            state.pipeline,
            state.supervisor_choice,
            state.supervisor_error,
            state.supervisor_api_key_present,
            state.supervisor_credential_status,
            state.supervisor_secret_store,
            state.supervisor_config_lock,
            state.supervisor_config_generation,
            state.supervisor_config_task,
            state.supervisor_config_operation,
        ) = previous


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
@pytest.mark.parametrize("activation_failure", ["missing_secret", "constructor_value_error"])
async def test_missing_saved_secret_preserves_revision_and_rotates_exact_reference(
    supervisor_client, monkeypatch, activation_failure
):
    from pex_bridge.app import _activate_saved_supervisor_choice

    client, secret_store, home = supervisor_client
    created = await client.patch(
        "/v1/supervisor", json=_custom_payload(api_key="old-secret")
    )
    assert created.status_code == 200
    persisted = load_supervisor_choice(home / "supervisor.json")
    assert persisted is not None and persisted.secret_ref
    old_reference = persisted.secret_ref
    if activation_failure == "missing_secret":
        secret_store.values.pop(old_reference)
    else:
        monkeypatch.setattr(
            "pex_supervisor.providers.load_supervisor_model",
            lambda _config: (_ for _ in ()).throw(ValueError("invalid constructor args")),
        )

    state.supervisor_choice = persisted
    state.supervisor_api_key_present = False
    state.supervisor_credential_status = "configured_unverified"
    state.supervisor_error = "SupervisorLoading"
    state.supervisor_config_generation += 1
    await _activate_saved_supervisor_choice(
        persisted, state.supervisor_config_generation
    )

    unavailable = await client.get("/v1/supervisor")
    assert unavailable.status_code == 200
    assert unavailable.json()["revision"] == persisted.revision
    assert unavailable.json()["credential_configured"] is True
    assert unavailable.json()["credential_status"] == (
        "missing"
        if activation_failure == "missing_secret"
        else "configured_unverified"
    )
    assert unavailable.json()["has_api_key"] is False
    assert state.supervisor_choice == persisted

    monkeypatch.undo()
    rotated = await client.patch(
        "/v1/supervisor",
        json={
            **_custom_payload(api_key="replacement-secret"),
            "expected_revision": persisted.revision,
        },
    )
    assert rotated.status_code == 200
    assert rotated.json()["revision"] == persisted.revision + 1
    await _wait_until(lambda: old_reference in secret_store.deleted)
    replacement = load_supervisor_choice(home / "supervisor.json")
    assert replacement is not None
    assert replacement.secret_ref != old_reference


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
