import asyncio
import json
import os

import httpx
import pytest
from pex_supervisor.catalog import catalog
from pex_supervisor.providers import (
    PROVIDERS,
    ModelCatalogRefreshError,
    SupervisorRuntimeConfig,
    _local_alive,
    _validate_request_destination,
    configure_runtime,
    describe_backend,
    load_supervisor_model,
    openai_compat_client_config,
    refresh_model_catalog,
    resolve_provider_id,
)


def test_local_auto_detection_requires_successful_http_status(monkeypatch):
    class Response:
        def __init__(self, status_code):
            self.status_code = status_code

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class Client:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def stream(self, method, url):
            assert method == "GET"
            return Response(404 if "wrong" in url else 200)

    monkeypatch.setattr("pex_supervisor.providers.httpx.Client", Client)
    assert _local_alive("http://127.0.0.1/wrong") is False
    assert _local_alive("http://127.0.0.1/right") is True


def test_dotenv_loader_refuses_oversized_files(monkeypatch, tmp_path):
    import pex_supervisor.providers as providers

    marker = "PEX_OVERSIZED_DOTENV_MARKER"
    monkeypatch.delenv(marker, raising=False)
    (tmp_path / ".env").write_bytes(
        f"{marker}=must-not-load\n".encode() + (b"x" * 1_048_576)
    )

    class ModulePath:
        def resolve(self):
            return self

        @property
        def parents(self):
            return [tmp_path, tmp_path, tmp_path, tmp_path, tmp_path]

    monkeypatch.setattr(providers, "Path", lambda _value: ModulePath())
    monkeypatch.setattr(providers, "_DOTENV_LOADED", False)

    providers._load_dotenv()

    assert marker not in os.environ


def test_login_auth_is_declared_unimplemented_and_does_not_become_the_live_mode(monkeypatch):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "openai")
    monkeypatch.setenv("PEX_SUPERVISOR_AUTH", "login")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-login-session")
    info = describe_backend()
    assert info["auth_mode"] == "login"
    assert info["requested_auth"] == "login"
    assert info["login_implemented"] is False
    assert "not implemented" in info["login_note"].casefold()
    assert "chat session" in info["login_note"].casefold()
    assert load_supervisor_model() is None


def test_explicit_provider_and_disable(monkeypatch):
    monkeypatch.setenv("PEX_SUPERVISOR_DISABLE", "1")
    assert describe_backend()["disabled"] is True
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    assert resolve_provider_id() == "openrouter"
    info = describe_backend()
    assert info["backend"] == "openrouter"
    assert info["base_url"] == "https://openrouter.ai/api/v1"
    assert info["has_api_key"] is True
    assert "zen" in PROVIDERS
    assert "openai" in PROVIDERS
    assert "github_models" in PROVIDERS
    assert "writer" in PROVIDERS
    assert "sagemaker" in PROVIDERS
    assert "llama_api" in PROVIDERS


def test_custom_base_url_wins_without_named_provider(monkeypatch):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.delenv("PEX_SUPERVISOR_PROVIDER", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "k")
    assert resolve_provider_id() == "custom"


def test_bedrock_provenance_does_not_claim_an_anthropic_endpoint(monkeypatch):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.delenv("PEX_SUPERVISOR_BASE_URL", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "bedrock")

    info = describe_backend()

    assert info["backend"] == "bedrock"
    assert info["base_url"] is None
    assert info["auth_mode"] == "aws_sigv4"


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("anthropic", "https://api.anthropic.com"),
        ("google", "https://generativelanguage.googleapis.com"),
    ],
)
def test_native_provider_provenance_records_its_real_service_endpoint(
    monkeypatch, provider, expected
):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.delenv("PEX_SUPERVISOR_BASE_URL", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", provider)

    assert describe_backend()["base_url"] == expected


def test_described_base_url_rejects_credentials_query_and_fragment(monkeypatch):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "custom")
    monkeypatch.setenv(
        "PEX_SUPERVISOR_BASE_URL",
        "https://user:fake-password@example.invalid:8443/v1?api_key=fake#private",
    )
    info = describe_backend()
    assert info["backend"] is None
    assert "service root" in info["error"]
    assert "user" not in str(info)
    assert "fake-password" not in str(info)


def test_constructed_model_refuses_endpoint_credentials(monkeypatch):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "custom")
    monkeypatch.setenv("PEX_SUPERVISOR_MODEL", "test-model")
    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "test-key")
    monkeypatch.setenv(
        "PEX_SUPERVISOR_BASE_URL",
        "https://user:password@example.invalid/v1?api_key=secret#private",
    )

    model = load_supervisor_model()

    assert model is None


def test_constructed_model_records_safe_custom_endpoint_provenance(monkeypatch):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "custom")
    monkeypatch.setenv("PEX_SUPERVISOR_MODEL", "test-model")
    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "test-key")
    monkeypatch.setenv("PEX_SUPERVISOR_BASE_URL", "https://example.invalid/v1")

    model = load_supervisor_model()

    assert model is not None
    assert model._pex_provenance["base_url"] == "https://example.invalid/v1"


def test_openai_provider_constructs_with_installed_dependency(monkeypatch):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    model = load_supervisor_model()
    assert model is not None


def test_zen_openai_compat_excludes_reasoning_on_follow_up_turns(monkeypatch):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "zen")
    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "test-key")
    captured: dict = {}

    class FakeOpenAIModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("strands.models.openai.OpenAIModel", FakeOpenAIModel)
    model = load_supervisor_model()
    assert model is not None
    assert captured["params"]["extra_body"] == {"reasoning": {"exclude": True}}
    http_client = captured["client_args"]["http_client"]
    asyncio.run(http_client.aclose())


def test_azure_and_hermes_refuse_missing_base_url(monkeypatch):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.delenv("PEX_SUPERVISOR_BASE_URL", raising=False)
    for provider, key_name in (
        ("azure_openai", "AZURE_OPENAI_API_KEY"),
        ("hermes", "HERMES_API_KEY"),
    ):
        monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", provider)
        monkeypatch.setenv(key_name, "test-key")
        monkeypatch.setenv("PEX_SUPERVISOR_MODEL", "test-model")
        assert load_supervisor_model() is None
        monkeypatch.delenv(key_name)


def test_apply_runtime_choice_sets_catalog_model(monkeypatch):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "openai")
    monkeypatch.setenv("PEX_SUPERVISOR_MODEL", "gpt-5.4-mini")
    from pex_supervisor.providers import apply_runtime_choice

    info = apply_runtime_choice(provider="openrouter", model_id="anthropic/claude-sonnet-4.6")
    assert info["backend"] == "openrouter"
    assert info["model_id"] == "anthropic/claude-sonnet-4.6"
    assert info.get("disabled") is not True
    try:
        apply_runtime_choice(provider="not-a-vendor")
        raise AssertionError("expected unknown provider")
    except ValueError:
        pass


def test_apply_runtime_choice_can_return_to_auto_detection(monkeypatch):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.delenv("PEX_SUPERVISOR_BASE_URL", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "openrouter")
    monkeypatch.setenv("PEX_SUPERVISOR_MODEL", "stale-model")
    monkeypatch.setenv("OPENAI_API_KEY", "available")
    monkeypatch.delenv("PEX_SUPERVISOR_API_KEY", raising=False)

    from pex_supervisor.providers import apply_runtime_choice

    info = apply_runtime_choice(provider="", model_id="")
    assert "PEX_SUPERVISOR_PROVIDER" not in os.environ
    assert "PEX_SUPERVISOR_MODEL" not in os.environ
    assert info["backend"] == "openai"


@pytest.mark.parametrize("model_id", ["bad\nmodel", "x" * 513])
def test_apply_runtime_choice_rejects_unsafe_model_identifier(monkeypatch, model_id):
    from pex_supervisor.providers import apply_runtime_choice

    monkeypatch.delenv("PEX_SUPERVISOR_MODEL", raising=False)
    with pytest.raises(ValueError, match="bounded single-line"):
        apply_runtime_choice(model_id=model_id)
    assert "PEX_SUPERVISOR_MODEL" not in os.environ


@pytest.mark.parametrize(
    "base_url",
    [
        "file:///tmp/provider",
        "https://user:password@example.invalid/v1",
        "https://example.invalid/v1?api_key=secret",
        "https://example.invalid/v1#private",
        "https://example.invalid/\nheader",
        "https://example.invalid/" + ("x" * 2048),
    ],
)
def test_provider_resolution_rejects_unsafe_service_roots(monkeypatch, base_url):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "custom")
    monkeypatch.setenv("PEX_SUPERVISOR_BASE_URL", base_url)
    with pytest.raises(ValueError, match=r"HTTP\(S\) service root"):
        resolve_provider_id()


def test_static_catalog_is_deduplicated_and_truthfully_unverified():
    rows = catalog()
    keys = {(row["provider"], row["model_id"]) for row in rows}
    assert len(keys) == len(rows)
    assert len(rows) >= 50
    assert {row["availability"] for row in rows} == {"unverified"}
    assert {row["source"] for row in rows} == {"static_hint"}


def test_live_openai_compatible_catalog_is_marked_listed(monkeypatch):
    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "secret-not-returned")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-not-returned")

    class Response:
        status_code = 200

        def json(self):
            return {"data": [{"id": "z-model"}, {"id": "a-model"}, {"id": "a-model"}]}

    class Client:
        def get(self, url, headers=None):
            assert url == "https://api.openai.com/v1/models"
            assert headers == {"Authorization": "Bearer secret-not-returned"}
            return Response()

    result = refresh_model_catalog("openai", client=Client())
    assert result["inference_calls"] == 0
    assert [row["model_id"] for row in result["catalog"]] == ["a-model", "z-model"]
    assert {row["availability"] for row in result["catalog"]} == {"listed"}
    assert "secret-not-returned" not in str(result)


def test_live_anthropic_catalog_uses_absolute_official_endpoint(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-not-returned")
    monkeypatch.delenv("PEX_SUPERVISOR_API_KEY", raising=False)

    class Response:
        status_code = 200

        def json(self):
            return {"data": [{"id": "claude-test", "display_name": "Claude Test"}]}

    class Client:
        def get(self, url, headers=None, params=None):
            assert url == "https://api.anthropic.com/v1/models"
            assert headers == {
                "x-api-key": "secret-not-returned",
                "anthropic-version": "2023-06-01",
            }
            assert params == {"limit": 1000}
            return Response()

    result = refresh_model_catalog("anthropic", client=Client())

    assert result["catalog"][0]["model_id"] == "claude-test"
    assert "secret-not-returned" not in str(result)


def test_live_catalog_failure_does_not_expose_response_body(monkeypatch):
    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "secret")

    class Response:
        status_code = 401
        text = "secret provider diagnostic"

    class Client:
        def get(self, url, headers=None):
            return Response()

    with pytest.raises(ModelCatalogRefreshError, match="HTTP 401") as raised:
        refresh_model_catalog("openai", client=Client())
    assert "provider diagnostic" not in str(raised.value)


def test_live_catalog_stream_is_bounded_before_json_decode(monkeypatch):
    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "secret")

    class Response:
        status_code = 200
        headers = {"content-length": str(2_097_153)}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def iter_bytes(self):
            raise AssertionError("declared oversized bodies must not be read")

    class Client:
        def stream(self, method, url, headers=None):
            assert method == "GET"
            return Response()

    with pytest.raises(ModelCatalogRefreshError, match="response limit"):
        refresh_model_catalog("openai", client=Client())


def test_live_catalog_rejects_excessive_empty_chunks(monkeypatch):
    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "secret")

    class Response:
        status_code = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def iter_bytes(self):
            yield from (b"" for _ in range(4097))

    class Client:
        def stream(self, method, url, headers=None):
            assert method == "GET"
            return Response()

    with pytest.raises(ModelCatalogRefreshError, match="chunk limit"):
        refresh_model_catalog("openai", client=Client())


def test_live_catalog_rejects_duplicate_json_keys(monkeypatch):
    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "secret")

    class Response:
        status_code = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def iter_bytes(self):
            yield b'{"data":[],"data":[{"id":"spoofed"}]}'

    class Client:
        def stream(self, method, url, headers=None):
            assert method == "GET"
            return Response()

    with pytest.raises(ModelCatalogRefreshError, match="model listing failed"):
        refresh_model_catalog("openai", client=Client())


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"data": "not-a-list"},
        {"data": ["not-an-object"]},
        {"data": [{"id": "x"}] * 2001},
    ],
)
def test_live_catalog_rejects_malformed_or_excessive_entries(monkeypatch, payload):
    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "secret")

    class Response:
        status_code = 200

        def json(self):
            return payload

    class Client:
        def get(self, url, headers=None):
            return Response()

    with pytest.raises(ModelCatalogRefreshError):
        refresh_model_catalog("openai", client=Client())


def test_live_catalog_drops_unsafe_or_oversized_model_identifiers(monkeypatch):
    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "secret")

    class Response:
        status_code = 200

        def json(self):
            return {
                "data": [
                    {"id": "safe-model", "name": "Safe Model"},
                    {"id": "bad\nmodel"},
                    {"id": "x" * 513},
                    {"id": 12345},
                ]
            }

    class Client:
        def get(self, url, headers=None):
            return Response()

    result = refresh_model_catalog("openai", client=Client())
    assert [(row["model_id"], row["label"]) for row in result["catalog"]] == [
        ("safe-model", "Safe Model")
    ]


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("nan", 45.0), ("inf", 45.0), ("-5", 1.0), ("999", 120.0), ("broken", 45.0)],
)
def test_openai_compatible_timeout_is_finite_and_bounded(monkeypatch, configured, expected):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("PEX_SUPERVISOR_TIMEOUT", configured)

    config = openai_compat_client_config()

    assert config is not None
    assert config["timeout"] == expected


@pytest.fixture
def isolated_runtime():
    configure_runtime(None)
    try:
        yield
    finally:
        configure_runtime(None)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/v1",
        "http://2130706433/v1",
        "http://0x7f000001/v1",
        "http://[::ffff:127.0.0.1]/v1",
        "https://example.invalid/%2e%2e/admin",
        "https://example.invalid/a//b",
        "https://example.invalid:443/v1",
    ],
)
def test_runtime_config_rejects_ambiguous_or_unsafe_endpoints(
    isolated_runtime, base_url
):
    with pytest.raises(ValueError, match="base_url"):
        configure_runtime(
            SupervisorRuntimeConfig(
                provider="custom",
                model_id="model",
                auth_mode="custom",
                protocol="openai",
                base_url=base_url,
            )
        )


def test_request_destination_rejects_mixed_public_private_dns(monkeypatch):
    monkeypatch.setattr(
        "pex_supervisor.providers.socket.getaddrinfo",
        lambda *_args, **_kwargs: [
            (2, 1, 6, "", ("8.8.8.8", 443)),
            (2, 1, 6, "", ("169.254.169.254", 443)),
        ],
    )
    request = httpx.Request("POST", "https://models.example.test/v1/chat/completions")
    with pytest.raises(httpx.ConnectError, match="outside public address space"):
        _validate_request_destination(request)


def test_request_destination_pins_global_dns_so_later_answers_cannot_rebind(monkeypatch):
    calls = {"n": 0}

    def fake_getaddrinfo(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return [(2, 1, 6, "", ("8.8.8.8", 443))]
        return [(2, 1, 6, "", ("169.254.169.254", 443))]

    monkeypatch.setattr("pex_supervisor.providers.socket.getaddrinfo", fake_getaddrinfo)
    request = httpx.Request("POST", "https://models.example.test:8443/v1/chat/completions")
    _validate_request_destination(request)
    assert calls["n"] == 1
    assert request.url.host == "8.8.8.8"
    assert request.url.port == 8443
    assert request.headers["host"] == "models.example.test:8443"
    assert request.extensions["sni_hostname"] == "models.example.test"
    _validate_request_destination(request)
    assert calls["n"] == 1
    assert request.url.host == "8.8.8.8"


def test_custom_without_key_never_inherits_ambient_openai_key(
    monkeypatch, isolated_runtime
):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ambient-must-not-cross")
    captured = {}

    class FakeOpenAIModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("strands.models.openai.OpenAIModel", FakeOpenAIModel)
    config = SupervisorRuntimeConfig(
        provider="custom",
        model_id="model",
        auth_mode="custom",
        protocol="openai",
        base_url="https://models.example.invalid/v1",
        credential_source="none",
    )

    model = load_supervisor_model(config)

    assert model is not None
    assert captured["client_args"]["api_key"] == "pex-no-api-key"
    secure_client = captured["client_args"]["http_client"]
    assert isinstance(secure_client, httpx.AsyncClient)
    assert secure_client.follow_redirects is False
    assert secure_client.trust_env is False
    assert "sk-ambient-must-not-cross" not in repr(captured)
    asyncio.run(secure_client.aclose())


def test_named_provider_override_never_retargets_inherited_vendor_key(
    monkeypatch, isolated_runtime
):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.delenv("PEX_SUPERVISOR_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-vendor-only")
    config = SupervisorRuntimeConfig(
        provider="openai",
        model_id="model",
        auth_mode="api_key",
        base_url="https://attacker.example.invalid/v1",
        credential_source="environment",
    )

    assert load_supervisor_model(config) is None


def test_custom_anthropic_uses_exact_endpoint_and_secret(monkeypatch, isolated_runtime):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    captured = {}

    class FakeAnthropicModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("strands.models.anthropic.AnthropicModel", FakeAnthropicModel)
    config = SupervisorRuntimeConfig(
        provider="custom",
        model_id="claude-compatible",
        auth_mode="custom",
        protocol="anthropic",
        base_url="https://anthropic.example.invalid/v1",
        credential_source="secret_store",
        api_key="secret-bound-to-this-endpoint",
    )

    model = load_supervisor_model(config)

    assert model is not None
    secure_client = captured["client_args"].pop("http_client")
    assert captured["client_args"] == {
        "api_key": "secret-bound-to-this-endpoint",
        "base_url": "https://anthropic.example.invalid/v1",
    }
    assert secure_client.follow_redirects is False
    assert secure_client.trust_env is False
    asyncio.run(secure_client.aclose())
    assert model._pex_provenance["auth_mode"] == "custom"
    assert len(model._pex_provenance["config_fingerprint"]) == 64
    assert "secret-bound-to-this-endpoint" not in json.dumps(model._pex_provenance)


def test_explicit_login_is_degraded_and_never_constructs_api_key_model(
    monkeypatch, isolated_runtime
):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-be-used-for-login")

    def forbidden(**_kwargs):
        raise AssertionError("login must not construct an API-key model")

    monkeypatch.setattr("strands.models.openai.OpenAIModel", forbidden)
    config = SupervisorRuntimeConfig(
        provider="openai",
        model_id="model",
        auth_mode="login",
        credential_source="environment",
    )

    assert load_supervisor_model(config) is None


@pytest.mark.parametrize(
    ("provider", "auth_mode"),
    [("openai", "custom"), ("anthropic", "custom"), ("custom", "local")],
)
def test_provider_auth_matrix_fails_closed(isolated_runtime, provider, auth_mode):
    with pytest.raises(ValueError, match="auth_mode"):
        configure_runtime(
            SupervisorRuntimeConfig(
                provider=provider,
                model_id="model",
                auth_mode=auth_mode,
                protocol="openai" if provider == "custom" else None,
                base_url=(
                    "https://models.example.invalid/v1" if provider == "custom" else None
                ),
            )
        )


def test_custom_anthropic_catalog_uses_anthropic_path_and_headers(isolated_runtime):
    config = SupervisorRuntimeConfig(
        provider="custom",
        model_id="claude-compatible",
        auth_mode="custom",
        protocol="anthropic",
        base_url="https://anthropic.example.invalid/root",
        credential_source="secret_store",
        api_key="catalog-secret",
    )
    configure_runtime(config)

    class Response:
        status_code = 200

        def json(self):
            return {"data": [{"id": "claude-compatible", "display_name": "Claude"}]}

    class Client:
        def get(self, url, headers=None, params=None):
            assert url == "https://anthropic.example.invalid/root/v1/models"
            assert headers == {
                "x-api-key": "catalog-secret",
                "anthropic-version": "2023-06-01",
            }
            assert params == {"limit": 1000}
            return Response()

    result = refresh_model_catalog("custom", client=Client())

    assert result["count"] == 1
    assert result["catalog"][0]["model_id"] == "claude-compatible"
    assert "catalog-secret" not in repr(result)


def test_agentcore_auth_does_not_silently_construct_bedrock(monkeypatch, isolated_runtime):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)

    def forbidden(**_kwargs):
        raise AssertionError("AgentCore must not silently become a Bedrock model")

    monkeypatch.setattr("strands.models.bedrock.BedrockModel", forbidden)
    config = SupervisorRuntimeConfig(
        provider="bedrock",
        model_id="model",
        auth_mode="agentcore",
        credential_source="environment",
    )

    assert load_supervisor_model(config) is None


@pytest.mark.parametrize(
    ("provider", "auth_mode", "protocol", "key"),
    [
        ("custom", "custom", "openai", "fixture-first-key"),
        ("custom", "custom", "anthropic", "fixture-first-key"),
        ("groq", "api_key", None, "fixture-first-key"),
        ("custom", "custom", "openai", None),
        ("lmstudio", "local", None, None),
    ],
)
def test_catalog_refresh_keeps_one_runtime_during_concurrent_settings_change(
    monkeypatch, isolated_runtime, provider, auth_mode, protocol, key
):
    import pex_supervisor.providers as providers

    first = SupervisorRuntimeConfig(
        provider=provider,
        model_id="fixture-model",
        auth_mode=auth_mode,
        protocol=protocol,
        base_url="https://first.example.test/v1",
        credential_source="secret_store" if key else "none",
        api_key=key,
    )
    second = SupervisorRuntimeConfig(
        provider="custom",
        model_id="other-model",
        auth_mode="custom",
        protocol="anthropic" if protocol != "anthropic" else "openai",
        base_url="https://second.example.test/v1",
        credential_source="secret_store",
        api_key="fixture-second-key",
    )
    configure_runtime(first)
    captured = []

    def receive(request):
        captured.append(request)
        return httpx.Response(200, json={"data": [{"id": "fixture-model"}]})

    def switch_config_between_key_and_destination(**_kwargs):
        # This is the real refresh path's client-construction boundary: the
        # credential has been read but its destination has not. No network.
        configure_runtime(second)
        return httpx.Client(transport=httpx.MockTransport(receive))

    monkeypatch.setattr(
        providers, "credential_safe_http_client", switch_config_between_key_and_destination
    )
    result = refresh_model_catalog()

    assert result["provider"] == provider
    assert len(captured) == 1
    request = captured[0]
    assert request.url.host == "first.example.test"
    if protocol == "anthropic":
        assert request.headers.get("x-api-key") == key
        assert "authorization" not in request.headers
    else:
        assert request.headers.get("authorization") == (f"Bearer {key}" if key else None)
        assert "x-api-key" not in request.headers
    assert providers.current_runtime_config() == second
    assert providers._active_runtime_config() == second


def test_catalog_refresh_restores_enclosing_runtime_scope_after_failure(
    monkeypatch, isolated_runtime
):
    import pex_supervisor.providers as providers

    outer = SupervisorRuntimeConfig(
        provider="custom",
        auth_mode="custom",
        protocol="openai",
        base_url="https://outer.example.test/v1",
    )
    initial_scope = providers._RUNTIME_SCOPE.get()
    token = providers._RUNTIME_SCOPE.set(outer)
    try:
        def fail(_request):
            return httpx.Response(503, json={"error": "fixture failure"})

        def client_factory(**_kwargs):
            return httpx.Client(transport=httpx.MockTransport(fail))

        monkeypatch.setattr(providers, "credential_safe_http_client", client_factory)
        with pytest.raises(ModelCatalogRefreshError):
            refresh_model_catalog()
        assert providers._RUNTIME_SCOPE.get() is outer
    finally:
        providers._RUNTIME_SCOPE.reset(token)
    assert providers._RUNTIME_SCOPE.get() is initial_scope


def test_catalog_refresh_keeps_environment_mode_when_first_config_is_committed(
    monkeypatch, isolated_runtime
):
    import pex_supervisor.providers as providers

    monkeypatch.setattr(providers, "_load_dotenv", lambda: None)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "custom")
    monkeypatch.setenv("PEX_SUPERVISOR_AUTH", "custom")
    monkeypatch.setenv("PEX_SUPERVISOR_BASE_URL", "https://environment.example.test/v1")
    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "fixture-environment-key")
    configured = SupervisorRuntimeConfig(
        provider="custom",
        auth_mode="custom",
        protocol="openai",
        base_url="https://configured.example.test/v1",
    )
    captured = []

    def receive(request):
        captured.append(request)
        return httpx.Response(200, json={"data": [{"id": "fixture-model"}]})

    def commit_first_config(**_kwargs):
        configure_runtime(configured)
        return httpx.Client(transport=httpx.MockTransport(receive))

    monkeypatch.setattr(providers, "credential_safe_http_client", commit_first_config)
    assert refresh_model_catalog()["count"] == 1
    assert len(captured) == 1
    assert captured[0].url.host == "environment.example.test"
    assert captured[0].headers["authorization"] == "Bearer fixture-environment-key"
    assert providers._active_runtime_config() == configured


@pytest.mark.parametrize("requested_provider", ["openrouter", "lmstudio", "bedrock"])
def test_catalog_refresh_rejects_unsaved_provider_before_creating_client(
    monkeypatch, isolated_runtime, requested_provider
):
    import pex_supervisor.providers as providers

    configure_runtime(SupervisorRuntimeConfig(
        provider="groq",
        model_id="fixture-model",
        auth_mode="api_key",
        base_url="https://groq-override.example.test/v1",
        credential_source="secret_store",
        api_key="fixture-groq-key",
    ))

    def forbidden_client(*_args, **_kwargs):
        raise AssertionError("mismatched provider must not construct any client")

    monkeypatch.setattr(providers, "credential_safe_http_client", forbidden_client)
    monkeypatch.setattr("boto3.client", forbidden_client)
    with pytest.raises(ModelCatalogRefreshError, match="save the selected provider"):
        refresh_model_catalog(requested_provider)


@pytest.mark.parametrize("committed_auto", [False, True])
def test_catalog_refresh_preserves_explicit_environment_provider_selection(
    monkeypatch, isolated_runtime, committed_auto
):
    import pex_supervisor.providers as providers

    monkeypatch.setattr(providers, "_load_dotenv", lambda: None)
    monkeypatch.delenv("PEX_SUPERVISOR_BASE_URL", raising=False)
    monkeypatch.delenv("PEX_SUPERVISOR_API_KEY", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "groq")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-openrouter-key")
    if committed_auto:
        configure_runtime(SupervisorRuntimeConfig(credential_source="environment"))
    captured = []

    def receive(request):
        captured.append(request)
        return httpx.Response(200, json={"data": [{"id": "fixture-model"}]})

    with httpx.Client(transport=httpx.MockTransport(receive)) as client:
        result = refresh_model_catalog("openrouter", client=client)
    assert result["provider"] == "openrouter"
    assert len(captured) == 1
    assert captured[0].url.host == "openrouter.ai"
    correct_credential = (
        captured[0].headers.get("authorization") == "Bearer fixture-openrouter-key"
    )
    assert correct_credential, "catalog request must use only the fixture credential"
