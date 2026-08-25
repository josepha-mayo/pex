from pex_supervisor.providers import (
    PROVIDERS,
    describe_backend,
    load_supervisor_model,
    resolve_provider_id,
)


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
    assert "github_models" not in PROVIDERS


def test_custom_base_url_wins_without_named_provider(monkeypatch):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.delenv("PEX_SUPERVISOR_PROVIDER", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "k")
    assert resolve_provider_id() == "custom"


def test_openai_provider_constructs_with_installed_dependency(monkeypatch):
    monkeypatch.delenv("PEX_SUPERVISOR_DISABLE", raising=False)
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    model = load_supervisor_model()
    assert model is not None


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
