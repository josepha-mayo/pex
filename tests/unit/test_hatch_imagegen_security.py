from __future__ import annotations

import json

import httpx
import pytest
from pex_bridge.pets import imagegen

_KEY_ENV_NAMES = (
    "PEX_HATCH_BASE_URL",
    "PEX_HATCH_API_KEY",
    "PEX_HATCH_MODEL",
    "PEX_SUPERVISOR_API_KEY",
    "OPENAI_API_KEY",
)


@pytest.fixture(autouse=True)
def _isolated_provider_environment(monkeypatch):
    for name in _KEY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    # Configuration tests must never discover or probe a real local/provider backend.
    monkeypatch.setattr(imagegen, "openai_compat_client_config", lambda: None)


def _config(
    base_url: str,
    *,
    api_key: str = "hatch-secret",
    provider: str = "test-provider",
    model_id: str = "test-image-model",
) -> dict[str, object]:
    return {
        "provider": provider,
        "base_url": base_url,
        "api_key": api_key,
        "model_id": model_id,
        "timeout": 1,
    }


class _StatusResponse:
    def __init__(self, status_code: int, *, headers=None, content: bytes = b""):
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content


class _GetClient:
    def __init__(self, response: _StatusResponse):
        self.response = response
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url, headers=None):
        self.calls.append((url, dict(headers or {})))
        return self.response


class _PostClient:
    def __init__(self, response: _StatusResponse):
        self.response = response
        self.calls: list[tuple[str, dict[str, str], dict[str, object]]] = []

    def post(self, url, headers=None, json=None):
        self.calls.append((url, dict(headers or {}), dict(json or {})))
        return self.response


def test_custom_hatch_url_never_inherits_openai_key(monkeypatch):
    openai_canary = "OPENAI-CANARY-MUST-NOT-LEAVE"
    monkeypatch.setenv("PEX_HATCH_BASE_URL", "https://images.example.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", openai_canary)

    assert imagegen.hatch_image_config() is None
    assert openai_canary not in repr(imagegen.describe_hatch_backend())

    hatch_key = "EXPLICIT-HATCH-KEY"
    monkeypatch.setenv("PEX_HATCH_API_KEY", hatch_key)
    cfg = imagegen.hatch_image_config()
    assert cfg is not None
    client = _GetClient(_StatusResponse(405))
    result = imagegen.probe_images_endpoint(cfg, client=client)

    assert result["generation_ready"] is True
    assert client.calls == [
        (
            "https://images.example.test/v1/images/generations",
            {"Content-Type": "application/json", "Authorization": f"Bearer {hatch_key}"},
        )
    ]
    assert openai_canary not in repr(client.calls)


def test_even_canonical_openai_explicit_hatch_url_requires_hatch_key(monkeypatch):
    monkeypatch.setenv("PEX_HATCH_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "OPENAI-ONLY-CANARY")

    assert imagegen.hatch_image_config() is None

    monkeypatch.setenv("PEX_HATCH_API_KEY", "HATCH-SCOPED-CANARY")
    cfg = imagegen.hatch_image_config()
    assert cfg is not None
    assert cfg["base_url"] == "https://api.openai.com/v1"


def test_openai_key_is_inherited_for_canonical_openai_only(monkeypatch):
    canary = "OPENAI-CANONICAL-ONLY-CANARY"
    monkeypatch.setenv("OPENAI_API_KEY", canary)

    cfg = imagegen.hatch_image_config()

    assert cfg is not None
    assert cfg["base_url"] == "https://api.openai.com/v1"
    assert canary not in repr(cfg)
    assert canary not in str(cfg)
    assert canary not in json.dumps(dict(cfg), sort_keys=True)
    assert "api_key" not in dict(cfg)


def test_supervisor_override_cannot_retarget_inherited_openai_key(monkeypatch):
    canary = "SUPERVISOR-OPENAI-EXFIL-CANARY"
    monkeypatch.setenv("OPENAI_API_KEY", canary)
    monkeypatch.setattr(
        imagegen,
        "openai_compat_client_config",
        lambda: {
            "provider": "openai",
            "base_url": "https://attacker.example.test/v1",
            "api_key": canary,
            "model_id": "ignored",
        },
    )

    assert imagegen.hatch_image_config() is None

    monkeypatch.setattr(
        imagegen,
        "openai_compat_client_config",
        lambda: {
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": canary,
            "model_id": "ignored",
        },
    )
    cfg = imagegen.hatch_image_config()
    assert cfg is not None
    assert cfg["base_url"] == "https://api.openai.com/v1"


def test_openai_lookalike_host_uses_only_explicit_hatch_key(monkeypatch):
    monkeypatch.setenv("PEX_HATCH_BASE_URL", "https://api.openai.com.evil.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "OPENAI-LOOKALIKE-CANARY")
    monkeypatch.setenv("PEX_HATCH_API_KEY", "LOOKALIKE-EXPLICIT-KEY")

    cfg = imagegen.hatch_image_config()
    assert cfg is not None
    client = _GetClient(_StatusResponse(405))
    imagegen.probe_images_endpoint(cfg, client=client)

    assert client.calls[0][0] == "https://api.openai.com.evil.test/v1/images/generations"
    assert client.calls[0][1]["Authorization"] == "Bearer LOOKALIKE-EXPLICIT-KEY"
    assert "OPENAI-LOOKALIKE-CANARY" not in repr(client.calls)


@pytest.mark.parametrize(
    ("base_url", "canonical"),
    [
        ("https://api.openai.com/v1/", "https://api.openai.com/v1"),
        ("HTTPS://API.OPENAI.COM/v1", "https://api.openai.com/v1"),
        ("https://images.example.test/v1", "https://images.example.test/v1"),
        (
            "https://images.example.test:8443/custom/v1/",
            "https://images.example.test:8443/custom/v1",
        ),
        ("http://127.0.0.1:8080/v1", "http://127.0.0.1:8080/v1"),
        ("http://[::1]:8080/v1", "http://[::1]:8080/v1"),
    ],
)
def test_provider_service_root_acceptance_matrix(base_url, canonical):
    cfg = imagegen._validated_config(_config(base_url))

    assert cfg["base_url"] == canonical


@pytest.mark.parametrize(
    "base_url",
    [
        "http://images.example.test/v1",
        "http://localhost:8080/v1",
        "http://127.0.0.2:8080/v1",
        "http://127.1:8080/v1",
        "http://2130706433:8080/v1",
        "http://0x7f000001:8080/v1",
        "http://[0:0:0:0:0:0:0:1]:8080/v1",
        "http://127.0.0.1:08080/v1",
        "https://api.openai.com:443/v1",
        "https://api.openai.com:8443/v1",
        "https://api.openai.com/v1/other",
        "https://images.example.test:443/v1",
        "https://images.example.test:/v1",
        "https://images.example.test:0/v1",
        "https://images.example.test:65536/v1",
        "https://user:password@images.example.test/v1",
        "https://images.example.test/v1?api_key=secret",
        "https://images.example.test/v1#secret",
        "https://images.example.test/v1%2Fimages",
        "https://images.example.test/v1/../admin",
        "https://images.example.test/v1//",
        "https://images.example.test/v1\\@api.openai.com",
        "https://images.example.test./v1",
        "https://imáges.example.test/v1",
        "file:///tmp/images",
        "//images.example.test/v1",
        "https://images.example.test/v1/images/generations",
    ],
)
def test_malformed_or_unsafe_service_roots_fail_before_any_client_call(base_url):
    canary = "INVALID-CONFIG-KEY-CANARY"
    cfg = _config(
        base_url,
        api_key=canary,
        provider=f"provider-{canary}",
        model_id=f"model-{canary}",
    )

    result = imagegen.probe_images_endpoint(cfg, client=object())
    assert result == {
        "ok": False,
        "has_image_endpoint": False,
        "generation_ready": False,
        "reason": "Image provider configuration is invalid.",
    }
    assert canary not in repr(result)
    with pytest.raises(imagegen.HatchImageError, match="configuration is invalid") as caught:
        imagegen.generate_png("pet", client=object(), config=cfg)
    assert caught.value.__cause__ is None
    assert canary not in repr(caught.value)


def test_explicit_empty_config_never_falls_back_to_ambient_credentials(monkeypatch):
    def ambient_config_must_not_run():
        raise AssertionError("explicit config must not invoke ambient credential discovery")

    monkeypatch.setattr(imagegen, "hatch_image_config", ambient_config_must_not_run)

    probe = imagegen.probe_images_endpoint({}, client=object())
    assert probe == {
        "ok": False,
        "has_image_endpoint": False,
        "generation_ready": False,
        "reason": "Image provider configuration is invalid.",
    }
    with pytest.raises(imagegen.HatchImageError, match="configuration is invalid"):
        imagegen.generate_png("pet", client=object(), config={})


def test_secret_bearing_config_and_public_descriptions_are_repr_safe(monkeypatch):
    canary = "CONFIG-REPRESENTATION-CANARY"
    cfg = imagegen._validated_config(
        _config(
            "https://images.example.test/v1",
            api_key=canary,
            provider=f"provider-{canary}",
            model_id=f"model-{canary}",
        )
    )

    public_copies = [repr(cfg), str(cfg), repr(dict(cfg)), repr(list(cfg.items()))]
    assert all(canary not in value for value in public_copies)
    assert "api_key" not in dict(cfg)

    monkeypatch.setattr(imagegen, "hatch_image_config", lambda: cfg)
    description = imagegen.describe_hatch_backend()
    assert canary not in repr(description)
    assert description["has_api_key"] is True
    assert description["provider"] == "provider-[redacted]"
    assert description["model_id"] == "model-[redacted]"


def test_probe_never_returns_key_or_untrusted_response_metadata():
    canary = "PROBE-RESPONSE-CANARY"
    cfg = _config(
        "https://images.example.test/v1",
        api_key=canary,
        provider=f"provider-{canary}",
        model_id=f"model-{canary}",
    )
    client = _GetClient(
        _StatusResponse(
            302,
            headers={"location": f"https://attacker.test/?key={canary}"},
            content=f"provider echoed {canary}".encode(),
        )
    )

    result = imagegen.probe_images_endpoint(cfg, client=client)

    assert result["ok"] is False
    assert result["generation_ready"] is False
    assert result["probe_status"] == 302
    assert canary not in repr(result)
    assert "attacker.test" not in repr(result)


def test_generate_refuses_redirect_and_sanitizes_error_body():
    canary = "GENERATE-REDIRECT-BODY-CANARY"
    response = _StatusResponse(
        302,
        headers={"location": f"https://attacker.test/{canary}"},
        content=f'{{"error":"{canary}"}}'.encode(),
    )
    client = _PostClient(response)

    with pytest.raises(imagegen.HatchImageError) as caught:
        imagegen.generate_png(
            "pet", client=client, config=_config("https://images.example.test/v1", api_key=canary)
        )

    assert str(caught.value) == "image generate failed HTTP 302"
    assert caught.value.__cause__ is None
    assert canary not in repr(caught.value)
    assert len(client.calls) == 1


def test_generate_refuses_result_url_without_downloading_it():
    canary = "RESULT-URL-CANARY"
    payload = json.dumps(
        {"data": [{"url": f"https://cdn.attacker.test/image.png?token={canary}"}]}
    ).encode()
    client = _PostClient(
        _StatusResponse(200, headers={"content-type": "application/json"}, content=payload)
    )

    with pytest.raises(imagegen.HatchImageError) as caught:
        imagegen.generate_png(
            "pet", client=client, config=_config("https://images.example.test/v1")
        )

    assert "external URL downloads are blocked" in str(caught.value)
    assert canary not in repr(caught.value)
    assert len(client.calls) == 1


def test_generate_uses_exact_validated_path_and_b64_only():
    response = _StatusResponse(
        200,
        headers={"content-type": "application/json"},
        content=b'{"data":[{"b64_json":"eA=="}]}',
    )
    client = _PostClient(response)

    result = imagegen.generate_png(
        "pet",
        client=client,
        config=_config("https://images.example.test/custom/v1", api_key="scoped-key"),
    )

    assert result == b"x"
    assert client.calls[0][0] == "https://images.example.test/custom/v1/images/generations"
    assert client.calls[0][1]["Authorization"] == "Bearer scoped-key"
    assert client.calls[0][2]["response_format"] == "b64_json"


def test_request_exception_message_and_cause_cannot_echo_key():
    canary = "REQUEST-EXCEPTION-CANARY"

    class FailingClient:
        def post(self, *_args, **_kwargs):
            request = httpx.Request("POST", "https://images.example.test/v1/images/generations")
            raise httpx.ConnectError(f"transport echoed {canary}", request=request)

    with pytest.raises(imagegen.HatchImageError) as caught:
        imagegen.generate_png(
            "pet",
            client=FailingClient(),
            config=_config("https://images.example.test/v1", api_key=canary),
        )

    assert str(caught.value) == "image generate request failed (ConnectError)"
    assert caught.value.__cause__ is None
    assert canary not in repr(caught.value)
