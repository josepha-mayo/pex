"""User-pluggable PEX supervisor backends.

Worker harnesses (Cursor, Codex, …) are a different layer. This module only
loads the LLM that *is* PEX. No vendor is special. No machine-specific key.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import math
import os
import re
import socket
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from pex_supervisor.catalog import catalog

logger = logging.getLogger(__name__)

_DOTENV_LOADED = False
_DOTENV_MAX_BYTES = 1_048_576
_DOTENV_MAX_LINES = 4096
_DOTENV_MAX_LINE_CHARS = 16_384
_DOTENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_CATALOG_MAX_BYTES = 2_097_152
_CATALOG_MAX_CHUNKS = 4096
_CATALOG_MAX_ITEMS = 2000
_CATALOG_MAX_MODELS = 1000
_CATALOG_TEXT_MAX_BYTES = 512
_RUNTIME_CONFIG: SupervisorRuntimeConfig | None = None
_RUNTIME_UNSET = object()
_RUNTIME_SCOPE: ContextVar[Any] = ContextVar(
    "pex_supervisor_runtime_scope", default=_RUNTIME_UNSET
)


@dataclass(frozen=True)
class SupervisorRuntimeConfig:
    """One immutable, audience-bound supervisor routing decision.

    ``api_key`` exists only in process memory.  ``credential_source`` controls
    whether provider-specific environment credentials may be consulted, so a
    custom endpoint can never inherit a vendor key by accident.
    """

    provider: str | None = None
    model_id: str | None = None
    auth_mode: str | None = None
    protocol: str | None = None
    base_url: str | None = None
    credential_source: str = "none"
    api_key: str | None = None

    def __repr__(self) -> str:
        return (
            "SupervisorRuntimeConfig("
            f"provider={self.provider!r}, model_id={self.model_id!r}, "
            f"auth_mode={self.auth_mode!r}, protocol={self.protocol!r}, "
            f"base_url={_public_base_url(self.base_url)!r}, "
            f"credential_source={self.credential_source!r}, api_key=<redacted>)"
        )


def _active_runtime_config() -> SupervisorRuntimeConfig | None:
    scoped = _RUNTIME_SCOPE.get()
    return _RUNTIME_CONFIG if scoped is _RUNTIME_UNSET else scoped


def _load_dotenv() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    root = Path(__file__).resolve().parents[4]
    path = root / ".env"
    _DOTENV_LOADED = True
    if not path.is_file():
        return
    try:
        with path.open("rb") as dotenv:
            raw_bytes = dotenv.read(_DOTENV_MAX_BYTES + 1)
        if len(raw_bytes) > _DOTENV_MAX_BYTES:
            return
        text = raw_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return
    lines = text.splitlines()
    if len(lines) > _DOTENV_MAX_LINES:
        return
    allowed = {
        "PEX_SUPERVISOR_PROVIDER",
        "PEX_SUPERVISOR_MODEL",
        "PEX_SUPERVISOR_API_KEY",
        "PEX_SUPERVISOR_BASE_URL",
        "PEX_SUPERVISOR_AUTH",
        "PEX_SUPERVISOR_DISABLE",
        "PEX_SUPERVISOR_TIMEOUT",
    }
    for spec in PROVIDERS.values():
        allowed.update(spec.key_envs)
    for raw in lines:
        if len(raw) > _DOTENV_MAX_LINE_CHARS:
            continue
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if _DOTENV_KEY.fullmatch(key) and key in allowed and key not in os.environ:
            os.environ[key] = value


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if not value:
            continue
        cleaned = value.strip()
        if not cleaned or len(cleaned.encode("utf-8")) > 16_384:
            continue
        if "\r" in cleaned or "\n" in cleaned or "\x00" in cleaned:
            continue
        return cleaned
    return None


def _local_alive(url: str) -> bool:
    try:
        with httpx.Client(timeout=0.4) as client:
            with client.stream("GET", url) as response:
                return 200 <= response.status_code < 300
    except Exception:
        return False


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    kind: str  # openai_compat | anthropic | google | ollama | bedrock | litellm | llamacpp
    base_url: str | None
    key_envs: tuple[str, ...]
    auth_modes: tuple[str, ...]
    default_model: str | None = None
    login_note: str = ""


PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        "openai",
        "openai_compat",
        "https://api.openai.com/v1",
        ("PEX_SUPERVISOR_API_KEY", "OPENAI_API_KEY"),
        ("api_key",),
        "gpt-5.4-mini",
        ("Use an OpenAI API key. Consumer ChatGPT and Codex CLI sessions are not reused."),
    ),
    "azure_openai": ProviderSpec(
        "azure_openai",
        "openai_compat",
        None,
        ("AZURE_OPENAI_API_KEY", "PEX_SUPERVISOR_API_KEY"),
        ("api_key",),
        None,
        "Azure OpenAI requires an Azure-specific endpoint/deployment contract; not implemented.",
    ),
    "anthropic": ProviderSpec(
        "anthropic",
        "anthropic",
        "https://api.anthropic.com",
        ("PEX_SUPERVISOR_API_KEY", "ANTHROPIC_API_KEY"),
        ("api_key",),
        "claude-sonnet-4-6",
        "Use an Anthropic API key. Consumer Claude sessions are not reused.",
    ),
    "google": ProviderSpec(
        "google",
        "google",
        "https://generativelanguage.googleapis.com",
        ("PEX_SUPERVISOR_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"),
        ("api_key",),
        "gemini-3-flash",
    ),
    "grok": ProviderSpec(
        "grok",
        "openai_compat",
        "https://api.x.ai/v1",
        ("PEX_SUPERVISOR_API_KEY", "XAI_API_KEY", "GROK_API_KEY"),
        ("api_key",),
        "grok-4.6",
        "Use an xAI API key. Grok app sessions are not reused.",
    ),
    "openrouter": ProviderSpec(
        "openrouter",
        "openai_compat",
        "https://openrouter.ai/api/v1",
        ("PEX_SUPERVISOR_API_KEY", "OPENROUTER_API_KEY"),
        ("api_key",),
        "anthropic/claude-sonnet-4.6",
    ),
    "zen": ProviderSpec(
        "zen",
        "openai_compat",
        "https://opencode.ai/zen/v1",
        ("PEX_SUPERVISOR_API_KEY", "PEX_ZEN_API_KEY", "OPENCODE_API_KEY"),
        ("api_key",),
        "laguna-s-2.1-free",
        "Use an OpenCode API key. Not the default product brain.",
    ),
    "opencode_go": ProviderSpec(
        "opencode_go",
        "openai_compat",
        "https://opencode.ai/zen/go/v1",
        ("PEX_SUPERVISOR_API_KEY", "OPENCODE_GO_API_KEY", "OPENCODE_API_KEY"),
        ("api_key",),
        "ox-alpha-free",
    ),
    "hermes": ProviderSpec(
        "hermes",
        "openai_compat",
        None,
        ("PEX_SUPERVISOR_API_KEY", "HERMES_API_KEY", "NOUS_API_KEY"),
        ("api_key",),
        None,
        "Set a Nous/Hermes key and the documented PEX_SUPERVISOR_BASE_URL.",
    ),
    "bedrock": ProviderSpec(
        "bedrock",
        "bedrock",
        None,
        ("AWS_ACCESS_KEY_ID", "AWS_PROFILE"),
        ("aws_sigv4",),
        None,
        "AWS credential chain / SSO / runtime execution role. Hackathon AgentCore path.",
    ),
    "mistral": ProviderSpec(
        "mistral",
        "openai_compat",
        "https://api.mistral.ai/v1",
        ("PEX_SUPERVISOR_API_KEY", "MISTRAL_API_KEY"),
        ("api_key",),
        "mistral-large-latest",
    ),
    "groq": ProviderSpec(
        "groq",
        "openai_compat",
        "https://api.groq.com/openai/v1",
        ("PEX_SUPERVISOR_API_KEY", "GROQ_API_KEY"),
        ("api_key",),
    ),
    "together": ProviderSpec(
        "together",
        "openai_compat",
        "https://api.together.xyz/v1",
        ("PEX_SUPERVISOR_API_KEY", "TOGETHER_API_KEY"),
        ("api_key",),
    ),
    "fireworks": ProviderSpec(
        "fireworks",
        "openai_compat",
        "https://api.fireworks.ai/inference/v1",
        ("PEX_SUPERVISOR_API_KEY", "FIREWORKS_API_KEY"),
        ("api_key",),
    ),
    "deepseek": ProviderSpec(
        "deepseek",
        "openai_compat",
        "https://api.deepseek.com/v1",
        ("PEX_SUPERVISOR_API_KEY", "DEEPSEEK_API_KEY"),
        ("api_key",),
        "deepseek-chat",
    ),
    "moonshot": ProviderSpec(
        "moonshot",
        "openai_compat",
        "https://api.moonshot.ai/v1",
        ("PEX_SUPERVISOR_API_KEY", "MOONSHOT_API_KEY", "KIMI_API_KEY"),
        ("api_key",),
    ),
    "dashscope": ProviderSpec(
        "dashscope",
        "openai_compat",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ("PEX_SUPERVISOR_API_KEY", "DASHSCOPE_API_KEY"),
        ("api_key",),
    ),
    "nvidia": ProviderSpec(
        "nvidia",
        "openai_compat",
        "https://integrate.api.nvidia.com/v1",
        ("PEX_SUPERVISOR_API_KEY", "NVIDIA_API_KEY"),
        ("api_key",),
    ),
    "perplexity": ProviderSpec(
        "perplexity",
        "openai_compat",
        "https://api.perplexity.ai",
        ("PEX_SUPERVISOR_API_KEY", "PERPLEXITY_API_KEY"),
        ("api_key",),
    ),
    "cohere": ProviderSpec(
        "cohere",
        "openai_compat",
        "https://api.cohere.ai/compatibility/v1",
        ("PEX_SUPERVISOR_API_KEY", "COHERE_API_KEY"),
        ("api_key",),
    ),
    "huggingface": ProviderSpec(
        "huggingface",
        "openai_compat",
        "https://router.huggingface.co/v1",
        ("PEX_SUPERVISOR_API_KEY", "HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN"),
        ("api_key",),
    ),
    "ollama": ProviderSpec(
        "ollama",
        "ollama",
        "http://127.0.0.1:11434",
        (),
        ("local",),
        "llama3.3",
    ),
    "lmstudio": ProviderSpec(
        "lmstudio",
        "openai_compat",
        "http://127.0.0.1:1234/v1",
        ("PEX_SUPERVISOR_API_KEY",),
        ("local",),
        "local-model",
    ),
    "llamacpp": ProviderSpec(
        "llamacpp",
        "llamacpp",
        "http://127.0.0.1:8080",
        (),
        ("local",),
    ),
    "vllm": ProviderSpec(
        "vllm",
        "openai_compat",
        "http://127.0.0.1:8000/v1",
        ("PEX_SUPERVISOR_API_KEY",),
        ("local", "custom"),
    ),
    "custom": ProviderSpec(
        "custom",
        "openai_compat",
        None,
        ("PEX_SUPERVISOR_API_KEY",),
        ("custom", "api_key"),
    ),
    "litellm": ProviderSpec(
        "litellm",
        "litellm",
        None,
        ("PEX_SUPERVISOR_API_KEY", "LITELLM_API_KEY"),
        ("api_key", "custom"),
    ),
    "github_models": ProviderSpec(
        "github_models",
        "openai_compat",
        "https://models.github.ai/inference",
        ("PEX_SUPERVISOR_API_KEY", "GITHUB_TOKEN"),
        ("api_key",),
        "openai/gpt-4.1",
        "Set PEX_SUPERVISOR_PROVIDER=github_models. "
        "GITHUB_TOKEN is not auto-detected (too common).",
    ),
    "writer": ProviderSpec(
        "writer",
        "writer",
        None,
        ("PEX_SUPERVISOR_API_KEY", "WRITER_API_KEY"),
        ("api_key",),
        None,
        "Strands WriterModel when installed.",
    ),
    "sagemaker": ProviderSpec(
        "sagemaker",
        "sagemaker",
        None,
        ("PEX_SUPERVISOR_API_KEY", "AWS_ACCESS_KEY_ID", "AWS_PROFILE"),
        ("api_key",),
        None,
        "Strands SageMakerAIModel when installed. Set PEX_SUPERVISOR_PROVIDER=sagemaker.",
    ),
    "llama_api": ProviderSpec(
        "llama_api",
        "llama_api",
        None,
        ("PEX_SUPERVISOR_API_KEY", "LLAMA_API_KEY"),
        ("api_key",),
        None,
        "Strands LlamaAPIModel when installed.",
    ),
}

_AUTO_ORDER = (
    "openai",
    "anthropic",
    "google",
    "openrouter",
    "grok",
    "zen",
    "opencode_go",
    "hermes",
    "groq",
    "together",
    "fireworks",
    "deepseek",
    "moonshot",
    "mistral",
    "bedrock",
    "ollama",
    "lmstudio",
)


def _configured(spec: ProviderSpec) -> bool:
    runtime = _active_runtime_config()
    if spec.kind in {"ollama", "lmstudio", "llamacpp", "vllm"}:
        return True
    if spec.id == "custom":
        return bool(_usable_base_url(_selected_base_url(spec)))
    if spec.id == "bedrock":
        if runtime is not None and runtime.credential_source != "environment":
            return False
        return bool(_first_env("AWS_ACCESS_KEY_ID", "AWS_PROFILE", "AWS_SESSION_TOKEN"))
    return bool(_credential_for(spec))


def _public_base_url(value: str | None) -> str | None:
    """Strip user-info, query parameters, and fragments from displayed endpoints."""

    if not value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "[configured]"
        hostname = parsed.hostname
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        netloc = hostname
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except ValueError:
        return "[configured]"


def _usable_base_url(value: str | None) -> str | None:
    """Return a canonical HTTPS or literal-loopback HTTP service root.

    This is a credential routing boundary, not merely display validation.  It
    rejects URL forms that can hide a second authority or smuggle secrets into
    request targets.  Cleartext is accepted only for exact loopback IP literals.
    """

    if not value:
        return None
    cleaned = value.strip().rstrip("/")
    if not cleaned or len(cleaned.encode("utf-8")) > 2048:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in cleaned):
        return None
    try:
        parsed = urlsplit(cleaned)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            return None
        port = parsed.port
        if port is not None and not 1 <= port <= 65_535:
            return None
        if (parsed.scheme == "https" and port == 443) or (
            parsed.scheme == "http" and port == 80
        ):
            return None
    except ValueError:
        return None
    hostname = parsed.hostname.casefold().rstrip(".")
    if not hostname or hostname == "localhost":
        return None
    if "%" in parsed.path or "\\" in parsed.path:
        return None
    path_segments = parsed.path.split("/")
    if any(segment in {".", ".."} for segment in path_segments):
        return None
    if "//" in parsed.path:
        return None
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        # Reject legacy integer/hex/octal IPv4 spellings.  Normal DNS names must
        # contain an alphabetic label and are protected in transit by HTTPS.
        if not any(char.isalpha() for char in hostname):
            return None
        if parsed.scheme != "https":
            return None
    else:
        if address.version == 6 and getattr(address, "ipv4_mapped", None) is not None:
            return None
        if parsed.scheme == "http" and not address.is_loopback:
            return None
        if parsed.scheme == "https" and not (address.is_loopback or address.is_global):
            return None
    canonical_host = hostname
    try:
        canonical_ip = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        canonical_host = canonical_ip.compressed
        if canonical_ip.version == 6:
            canonical_host = f"[{canonical_host}]"
    netloc = canonical_host if port is None else f"{canonical_host}:{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _canonical_ip(raw: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    address = ipaddress.ip_address(raw)
    mapped = getattr(address, "ipv4_mapped", None)
    return mapped if mapped is not None else address


def resolve_stream_addresses(
    hostname: str, port: int | None
) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    answers = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return {_canonical_ip(answer[4][0]) for answer in answers}


def _pin_https_request_to_literal_ip(
    request: Any,
    hostname: str,
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> None:
    """Bind TCP to the already-validated IP so later DNS cannot rebind the socket.

    TLS still uses the original hostname via httpcore `sni_hostname`; the Host
    header stays the original name for virtual hosting.
    """

    request.url = request.url.copy_with(host=str(address))
    default_port = 443 if str(request.url.scheme) == "https" else 80
    port = request.url.port
    host_header = hostname if port in {None, default_port} else f"{hostname}:{port}"
    request.headers["host"] = host_header
    request.extensions["sni_hostname"] = hostname


def _validate_request_destination(request: Any) -> None:
    hostname = str(request.url.host or "").casefold().rstrip(".")
    if not hostname or hostname.endswith(".invalid"):
        return
    try:
        literal = _canonical_ip(hostname)
    except ValueError:
        try:
            addresses = resolve_stream_addresses(hostname, request.url.port)
        except OSError as exc:
            raise httpx.ConnectError(
                "supervisor endpoint DNS resolution failed",
                request=request,
            ) from exc
        if not addresses or any(not address.is_global for address in addresses):
            raise httpx.ConnectError(
                "supervisor endpoint resolved outside public address space",
                request=request,
            ) from None
        pinned = min(addresses, key=lambda item: item.exploded)
        _pin_https_request_to_literal_ip(request, hostname, pinned)
    else:
        if not (literal.is_global or literal.is_loopback):
            raise httpx.ConnectError(
                "supervisor endpoint address is not allowed",
                request=request,
            )


async def _validate_async_request_destination(request: Any) -> None:
    _validate_request_destination(request)


def credential_safe_http_client(
    *,
    timeout: Any,
    protocol: str = "openai",
    asynchronous: bool = False,
) -> Any:
    kwargs = {
        "timeout": timeout,
        "follow_redirects": False,
        "trust_env": False,
        "event_hooks": {
            "request": [
                _validate_async_request_destination
                if asynchronous
                else _validate_request_destination
            ]
        },
    }
    if protocol == "anthropic":
        import httpx2

        client_type = httpx2.AsyncClient if asynchronous else httpx2.Client
        return client_type(**kwargs)
    client_type = httpx.AsyncClient if asynchronous else httpx.Client
    return client_type(**kwargs)


def validate_runtime_config(config: SupervisorRuntimeConfig) -> SupervisorRuntimeConfig:
    """Canonicalize one config without changing process-wide routing state."""

    provider = (config.provider or "").strip().casefold() or None
    if provider is not None and provider not in PROVIDERS:
        raise ValueError("unknown supervisor provider; use custom + base_url")
    model_id = _catalog_text(config.model_id) or None
    if config.model_id and not model_id:
        raise ValueError("model_id must be a bounded single-line identifier")
    base_url = _usable_base_url(config.base_url) if config.base_url else None
    if config.base_url and not base_url:
        raise ValueError(
            "base_url must be canonical HTTPS or literal-loopback HTTP without "
            "credentials, query, fragment, percent escapes, or ambiguous paths"
        )
    credential_source = config.credential_source.strip().casefold()
    if credential_source not in {"none", "environment", "secret_store"}:
        raise ValueError("credential_source must be none, environment, or secret_store")
    api_key = config.api_key
    if api_key is not None:
        if not 1 <= len(api_key) <= 16_384 or any(
            char in api_key for char in ("\r", "\n", "\x00")
        ):
            raise ValueError("api_key must be a bounded single-line value")
    if credential_source == "secret_store" and not api_key:
        raise ValueError("the configured secret reference did not resolve")
    if credential_source != "secret_store" and api_key is not None:
        raise ValueError("an in-memory api_key requires secret_store credential_source")
    protocol = (config.protocol or "").strip().casefold() or None
    if protocol not in {None, "openai", "anthropic"}:
        raise ValueError("protocol must be openai or anthropic")
    auth_mode = (config.auth_mode or "").strip().casefold() or None
    if auth_mode not in {
        None,
        "api_key",
        "login",
        "local",
        "custom",
        "bedrock",
        "agentcore",
    }:
        raise ValueError("unsupported supervisor auth_mode")
    selected = provider or ("custom" if base_url else None)
    if selected == "custom" and not base_url:
        raise ValueError("custom provider requires base_url")
    if protocol and selected != "custom":
        raise ValueError("protocol override is valid only for the custom provider")
    if selected == "custom" and protocol is None:
        protocol = "openai"
    if auth_mode == "local" and selected not in {"ollama", "lmstudio", "llamacpp", "vllm"}:
        raise ValueError("local auth_mode requires a local runtime provider")
    if auth_mode in {"bedrock", "agentcore"} and selected != "bedrock":
        raise ValueError("bedrock/agentcore auth_mode requires the bedrock provider")
    if auth_mode == "login" and selected in {
        "custom",
        "ollama",
        "lmstudio",
        "llamacpp",
        "vllm",
        "bedrock",
    }:
        raise ValueError("login auth_mode is not supported by the selected provider")
    if selected is not None and auth_mode not in {None, "login", "bedrock", "agentcore"}:
        spec = PROVIDERS[selected]
        if auth_mode not in spec.auth_modes:
            raise ValueError("auth_mode is not supported by the selected provider")
    if base_url and selected != "custom":
        spec = PROVIDERS[selected] if selected else None
        canonical_default = _usable_base_url(spec.base_url) if spec and spec.base_url else None
        is_default = canonical_default is not None and base_url == canonical_default
        if not is_default and (
            spec is None or spec.kind not in {"openai_compat", "ollama", "llamacpp"}
        ):
            raise ValueError(
                "base_url overrides for native providers must use custom + protocol"
            )
    if auth_mode == "login":
        # Login adapters are not implemented.  Retain the choice for an honest
        # degraded status, but model construction must fail closed below.
        credential_source = "none"
        api_key = None
    return SupervisorRuntimeConfig(
        provider=provider,
        model_id=model_id,
        auth_mode=auth_mode,
        protocol=protocol,
        base_url=base_url,
        credential_source=credential_source,
        api_key=api_key,
    )


def configure_runtime(config: SupervisorRuntimeConfig | None) -> dict[str, Any]:
    """Install one validated runtime config without mutating ``os.environ``."""

    global _RUNTIME_CONFIG
    _RUNTIME_CONFIG = validate_runtime_config(config) if config is not None else None
    return describe_backend()


def current_runtime_config() -> SupervisorRuntimeConfig | None:
    return _RUNTIME_CONFIG


def _credential_for(spec: ProviderSpec) -> str | None:
    runtime = _active_runtime_config()
    if runtime is None or runtime.credential_source == "environment":
        selected_base = _selected_base_url(spec)
        canonical_base = _usable_base_url(spec.base_url) if spec.base_url else None
        if spec.id == "custom" or (
            selected_base is not None
            and canonical_base is not None
            and _usable_base_url(selected_base) != canonical_base
        ):
            # Endpoint overrides may consume only the explicitly supervisor-scoped
            # key, never OPENAI_API_KEY or another vendor credential.
            return _first_env("PEX_SUPERVISOR_API_KEY")
        return _first_env(*spec.key_envs) if spec.key_envs else None
    if runtime.credential_source == "secret_store":
        selected = runtime.provider or (
            "custom" if runtime.base_url else None
        )
        if selected != spec.id:
            return None
        return runtime.api_key
    return None


def _selected_base_url(spec: ProviderSpec | None) -> str | None:
    runtime = _active_runtime_config()
    if runtime is not None:
        return runtime.base_url or (spec.base_url if spec else None)
    return os.environ.get("PEX_SUPERVISOR_BASE_URL") or (spec.base_url if spec else None)


def _effective_kind(spec: ProviderSpec) -> str:
    runtime = _active_runtime_config()
    if spec.id == "custom" and runtime is not None:
        return "anthropic" if runtime.protocol == "anthropic" else "openai_compat"
    return spec.kind


def _configured_model_id(spec: ProviderSpec) -> str | None:
    runtime = _active_runtime_config()
    value = (
        runtime.model_id
        if runtime is not None and runtime.model_id
        else os.environ.get("PEX_SUPERVISOR_MODEL")
        if runtime is None
        else None
    ) or spec.default_model
    return _catalog_text(value) or None


def _auth_mode(spec: ProviderSpec) -> str:
    """Return effective auth; unsupported explicit modes never become billable auth."""

    runtime = _active_runtime_config()
    override = (
        (runtime.auth_mode or "")
        if runtime is not None
        else (os.environ.get("PEX_SUPERVISOR_AUTH") or "")
    ).strip().lower()
    if override in {"login", "bedrock", "agentcore"}:
        return override
    return override if override in spec.auth_modes else spec.auth_modes[0]


def resolve_provider_id() -> str | None:
    _load_dotenv()
    runtime = _active_runtime_config()
    configured_base = (
        runtime.base_url
        if runtime is not None
        else os.environ.get("PEX_SUPERVISOR_BASE_URL")
    )
    if configured_base and not _usable_base_url(configured_base):
        raise ValueError(
            "PEX_SUPERVISOR_BASE_URL must be a bounded HTTP(S) service root without "
            "credentials, query parameters, or fragments"
        )
    explicit = (
        (runtime.provider or "")
        if runtime is not None
        else (os.environ.get("PEX_SUPERVISOR_PROVIDER") or "")
    ).strip().lower()
    if explicit:
        if explicit not in PROVIDERS:
            raise ValueError("unknown PEX_SUPERVISOR_PROVIDER; use custom + BASE_URL")
        return explicit
    if configured_base:
        logger.info("Auto-detected supervisor provider=custom from explicit base URL")
        return "custom"
    for pid in _AUTO_ORDER:
        if pid in {"ollama", "lmstudio"}:
            continue
        spec = PROVIDERS[pid]
        unambiguous_envs = tuple(
            name for name in spec.key_envs if name != "PEX_SUPERVISOR_API_KEY"
        )
        if (
            runtime is None
            or runtime.credential_source == "environment"
        ) and _first_env(*unambiguous_envs):
            logger.info("Auto-detected supervisor provider=%s from configured credential", pid)
            return pid
    for pid, probe in (
        ("ollama", "http://127.0.0.1:11434/api/tags"),
        ("lmstudio", "http://127.0.0.1:1234/v1/models"),
    ):
        if _local_alive(probe):
            logger.info("Auto-detected supervisor provider=%s from local health probe", pid)
            return pid
    return None


def describe_backend() -> dict[str, Any]:
    _load_dotenv()
    runtime = _active_runtime_config()
    if os.environ.get("PEX_SUPERVISOR_DISABLE") == "1":
        return {
            "backend": None,
            "has_api_key": False,
            "disabled": True,
            "catalog_size": len(catalog()),
            "providers": sorted(PROVIDERS),
        }
    pid = None
    try:
        pid = resolve_provider_id()
    except ValueError as exc:
        return {
            "backend": None,
            "error": str(exc),
            "has_api_key": False,
            "catalog_size": len(catalog()),
        }
    spec = PROVIDERS.get(pid) if pid else None
    key_present = bool(spec and _credential_for(spec)) if spec else False
    requested = (
        (runtime.auth_mode or "")
        if runtime is not None
        else (os.environ.get("PEX_SUPERVISOR_AUTH") or "")
    ).strip().lower() or None
    login_implemented = bool(spec and "login" in spec.auth_modes)
    login_note = spec.login_note if spec else ""
    if requested == "login" and not login_implemented:
        login_note = (
            "Vendor ChatGPT, Claude, and Grok consumer login are not implemented. "
            "PEX will not reuse a local chat session. Use a BYOK API key, a local "
            "runtime, or a custom endpoint."
        )
    elif not login_note:
        login_note = (
            "This is PEX’s supervisor model, not a worker harness. "
            "Consumer chat login is not implemented. Keys stay in .env."
        )
    return {
        "backend": pid,
        "base_url": _public_base_url(_selected_base_url(spec)),
        "model_id": _configured_model_id(spec) if spec else None,
        "auth_mode": _auth_mode(spec) if spec else None,
        "requested_auth": requested,
        "login_implemented": login_implemented,
        "has_api_key": key_present,
        "credential_source": (
            runtime.credential_source if runtime is not None else "environment"
        ),
        "protocol": (
            runtime.protocol
            if runtime is not None
            else ("anthropic" if spec and spec.kind == "anthropic" else "openai")
        ),
        "login_note": login_note,
        "catalog_size": len(catalog()),
        "providers": sorted(PROVIDERS),
    }


def apply_runtime_choice(
    *, provider: str | None = None, model_id: str | None = None
) -> dict[str, Any]:
    """Select catalog provider/model for this process. Never stores keys."""
    global _RUNTIME_CONFIG
    _RUNTIME_CONFIG = None
    pid: str | None = None
    cleaned_model: str | None = None
    if provider is not None:
        pid = provider.strip().lower()
        if pid and pid not in PROVIDERS:
            raise ValueError("unknown PEX_SUPERVISOR_PROVIDER; use custom + BASE_URL")
    if model_id is not None:
        raw_model = model_id.strip()
        cleaned_model = _catalog_text(raw_model)
        if raw_model and not cleaned_model:
            raise ValueError("model_id must be a bounded single-line identifier")
    if provider is not None:
        if pid:
            os.environ["PEX_SUPERVISOR_PROVIDER"] = pid
            os.environ.pop("PEX_SUPERVISOR_DISABLE", None)
        else:
            os.environ.pop("PEX_SUPERVISOR_PROVIDER", None)
    if model_id is not None:
        if cleaned_model:
            os.environ["PEX_SUPERVISOR_MODEL"] = cleaned_model
        else:
            os.environ.pop("PEX_SUPERVISOR_MODEL", None)
    return describe_backend()


class ModelCatalogRefreshError(RuntimeError):
    """A read-only provider model listing could not be completed safely."""


def _strict_json(raw: bytes) -> Any:
    """Decode a bounded provider response without accepting non-standard numbers."""

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    return json.loads(
        raw.decode("utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"invalid JSON constant {value}")
        ),
        object_pairs_hook=unique_object,
    )


def _declared_content_length(response: Any) -> int | None:
    headers = getattr(response, "headers", None)
    if headers is None or not hasattr(headers, "get"):
        return None
    raw = headers.get("content-length")
    if raw is None:
        return None
    try:
        length = int(raw)
    except (TypeError, ValueError) as exc:
        raise ModelCatalogRefreshError("provider returned an invalid Content-Length") from exc
    if length < 0:
        raise ModelCatalogRefreshError("provider returned an invalid Content-Length")
    return length


def _bounded_response_payload(response: Any) -> Any:
    declared = _declared_content_length(response)
    if declared is not None and declared > _CATALOG_MAX_BYTES:
        raise ModelCatalogRefreshError("provider model listing exceeded the response limit")

    iter_bytes = getattr(response, "iter_bytes", None)
    if callable(iter_bytes):
        chunks: list[bytes] = []
        total = 0
        for index, chunk in enumerate(iter_bytes()):
            if index >= _CATALOG_MAX_CHUNKS:
                raise ModelCatalogRefreshError("provider model listing exceeded the chunk limit")
            if not isinstance(chunk, bytes):
                raise ModelCatalogRefreshError("provider returned a malformed response stream")
            total += len(chunk)
            if total > _CATALOG_MAX_BYTES:
                raise ModelCatalogRefreshError("provider model listing exceeded the response limit")
            chunks.append(chunk)
        return _strict_json(b"".join(chunks))

    content = getattr(response, "content", None)
    if isinstance(content, bytes):
        if len(content) > _CATALOG_MAX_BYTES:
            raise ModelCatalogRefreshError("provider model listing exceeded the response limit")
        return _strict_json(content)

    # A deliberately narrow compatibility path for injected test clients. Real
    # httpx responses always use the bounded byte-stream branches above.
    response_json = getattr(response, "json", None)
    if not callable(response_json):
        raise ModelCatalogRefreshError("provider returned an unreadable model listing")
    return response_json()


def _catalog_get(http: Any, url: str, *, provider: str, **kwargs: Any) -> Any:
    stream = getattr(http, "stream", None)
    if callable(stream):
        with stream("GET", url, **kwargs) as response:
            status_code = getattr(response, "status_code", None)
            if not isinstance(status_code, int):
                raise ModelCatalogRefreshError("provider returned an invalid HTTP status")
            if status_code >= 400:
                raise ModelCatalogRefreshError(
                    f"{provider} model listing returned HTTP {status_code}"
                )
            return _bounded_response_payload(response)

    response = http.get(url, **kwargs)
    status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int):
        raise ModelCatalogRefreshError("provider returned an invalid HTTP status")
    if status_code >= 400:
        raise ModelCatalogRefreshError(f"{provider} model listing returned HTTP {status_code}")
    return _bounded_response_payload(response)


def _catalog_items(payload: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ModelCatalogRefreshError("provider returned a malformed model listing")
    items = payload.get(key)
    if not isinstance(items, list):
        raise ModelCatalogRefreshError("provider returned a malformed model listing")
    if len(items) > _CATALOG_MAX_ITEMS:
        raise ModelCatalogRefreshError("provider returned too many model entries")
    if not all(isinstance(item, dict) for item in items):
        raise ModelCatalogRefreshError("provider returned a malformed model entry")
    return items


def _catalog_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned or len(cleaned.encode("utf-8")) > _CATALOG_TEXT_MAX_BYTES:
        return ""
    if any(ord(char) < 32 or ord(char) == 127 for char in cleaned):
        return ""
    return cleaned


def _live_rows(provider: str, rows: list[tuple[str, str]]) -> list[dict[str, str]]:
    unique: dict[str, str] = {}
    for model_id, label in rows[:_CATALOG_MAX_ITEMS]:
        cleaned = _catalog_text(model_id)
        if cleaned:
            unique.setdefault(cleaned, _catalog_text(label) or cleaned)
        if len(unique) >= _CATALOG_MAX_MODELS:
            break
    return [
        {
            "provider": provider,
            "model_id": model_id,
            "label": unique[model_id],
            "source": "live_provider_list",
            "availability": "listed",
        }
        for model_id in sorted(unique, key=str.casefold)
    ]


def _supervisor_timeout() -> float:
    try:
        timeout = float(os.environ.get("PEX_SUPERVISOR_TIMEOUT", "45"))
    except (TypeError, ValueError):
        return 45.0
    if not math.isfinite(timeout):
        return 45.0
    return min(120.0, max(1.0, timeout))


def refresh_model_catalog(
    provider: str | None = None,
    *,
    client: httpx.Client | None = None,
    bedrock_client: Any | None = None,
) -> dict[str, Any]:
    """List models without invoking one; never return credentials or raw error bodies."""
    _load_dotenv()
    try:
        pid = (provider or resolve_provider_id() or "").strip().lower()
    except ValueError as exc:
        raise ModelCatalogRefreshError(str(exc)) from exc
    if not pid:
        raise ModelCatalogRefreshError("configure or select a supervisor provider first")
    spec = PROVIDERS.get(pid)
    if spec is None:
        raise ModelCatalogRefreshError("unknown supervisor provider")

    kind = _effective_kind(spec)
    if kind == "bedrock":
        try:
            if bedrock_client is None:
                import boto3

                bedrock_client = boto3.client("bedrock")
            payload = bedrock_client.list_foundation_models(byOutputModality="TEXT")
            summaries = _catalog_items(payload, "modelSummaries")
            rows = [
                (item.get("modelId") or "", item.get("modelName") or "")
                for item in summaries
                if isinstance(item.get("modelLifecycle") or {}, dict)
                and (item.get("modelLifecycle") or {}).get("status", "ACTIVE") == "ACTIVE"
            ]
        except ModelCatalogRefreshError:
            raise
        except Exception as exc:
            raise ModelCatalogRefreshError(
                f"Bedrock model listing failed ({type(exc).__name__})"
            ) from exc
        live = _live_rows(pid, rows)
        return {"provider": pid, "catalog": live, "count": len(live), "inference_calls": 0}

    key = _credential_for(spec)
    own = client is None
    http = client or credential_safe_http_client(timeout=12.0)
    try:
        if kind == "google":
            if not key:
                raise ModelCatalogRefreshError("Google model listing requires a configured API key")
            payload = _catalog_get(
                http,
                "https://generativelanguage.googleapis.com/v1beta/models",
                provider="Google",
                params={"key": key, "pageSize": 1000},
            )
            rows = []
            for item in _catalog_items(payload, "models"):
                methods = item.get("supportedGenerationMethods") or []
                if not isinstance(methods, list) or len(methods) > 64:
                    raise ModelCatalogRefreshError(
                        "Google returned a malformed generation-method list"
                    )
                if "generateContent" not in methods:
                    continue
                model_id = item.get("baseModelId") or item.get("name") or ""
                if not isinstance(model_id, str):
                    continue
                if model_id.startswith("models/"):
                    model_id = model_id.removeprefix("models/")
                rows.append((model_id, item.get("displayName") or model_id))
        elif kind == "anthropic":
            if not key:
                raise ModelCatalogRefreshError(
                    "Anthropic model listing requires a configured API key"
                )
            payload = _catalog_get(
                http,
                urljoin((_selected_base_url(spec) or "") + "/", "v1/models"),
                provider="Anthropic",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                params={"limit": 1000},
            )
            rows = [
                (item.get("id") or "", item.get("display_name") or item.get("id") or "")
                for item in _catalog_items(payload, "data")
            ]
        elif kind == "ollama":
            payload = _catalog_get(
                http,
                urljoin((_selected_base_url(spec) or "") + "/", "api/tags"),
                provider="Ollama",
            )
            rows = [
                (item.get("model") or item.get("name") or "", item.get("name") or "")
                for item in _catalog_items(payload, "models")
            ]
        elif kind in {"openai_compat", "llamacpp"}:
            if pid == "azure_openai":
                raise ModelCatalogRefreshError(
                    "Azure OpenAI model listing is not implemented; paste an exact deployment id"
                )
            base_url = _usable_base_url(_selected_base_url(spec))
            if not base_url:
                raise ModelCatalogRefreshError(
                    f"{pid} model listing requires PEX_SUPERVISOR_BASE_URL"
                )
            if spec.auth_modes[0] == "api_key" and not key and pid not in {
                "lmstudio",
                "vllm",
                "llamacpp",
                "custom",
            }:
                raise ModelCatalogRefreshError(
                    f"{pid} model listing requires a configured API key"
                )
            path = "models" if base_url.rstrip("/").endswith("/v1") else "v1/models"
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            payload = _catalog_get(
                http,
                urljoin(base_url.rstrip("/") + "/", path),
                provider=pid,
                headers=headers,
            )
            rows = [
                (item.get("id") or "", item.get("name") or item.get("id") or "")
                for item in _catalog_items(payload, "data")
            ]
        else:
            raise ModelCatalogRefreshError(
                f"live model listing is not implemented for provider {pid!r}; paste an exact id"
            )
    except ModelCatalogRefreshError:
        raise
    except (httpx.HTTPError, ValueError, TypeError, RecursionError) as exc:
        raise ModelCatalogRefreshError(
            f"{pid} model listing failed ({type(exc).__name__})"
        ) from exc
    finally:
        if own:
            http.close()

    live = _live_rows(pid, rows)
    if not live:
        raise ModelCatalogRefreshError(f"{pid} returned no selectable generation models")
    return {"provider": pid, "catalog": live, "count": len(live), "inference_calls": 0}


def _openai_compat_chat_params(spec: ProviderSpec) -> dict[str, Any]:
    """Chat Completions params. Zen follow-up turns reject leftover reasoning."""

    params: dict[str, Any] = {"max_tokens": 1200, "stream": False}
    if spec.id in {"zen", "opencode_go"}:
        params["extra_body"] = {"reasoning": {"exclude": True}}
    return params


def openai_compat_client_config() -> dict[str, Any] | None:
    """Endpoint used by bounded STOP inspect. Never log the api_key."""
    _load_dotenv()
    if os.environ.get("PEX_SUPERVISOR_DISABLE") == "1":
        return None
    try:
        pid = resolve_provider_id()
    except ValueError:
        return None
    if not pid:
        return None
    spec = PROVIDERS[pid]
    if _effective_kind(spec) != "openai_compat" or _auth_mode(spec) == "login":
        return None
    model_id = _configured_model_id(spec)
    base_url = _usable_base_url(_selected_base_url(spec))
    api_key = _credential_for(spec)

    if spec.id in {"lmstudio", "vllm", "ollama", "llamacpp"}:
        api_key = api_key or "local"
    if not model_id or not base_url:
        return None
    if spec.id not in {"ollama", "lmstudio", "vllm", "llamacpp", "custom"} and not api_key:
        return None
    return {
        "provider": pid,
        "base_url": base_url,
        "model_id": model_id,
        "api_key": api_key,
        "timeout": _supervisor_timeout(),
    }


def load_supervisor_model(
    config: SupervisorRuntimeConfig | object = _RUNTIME_UNSET,
) -> Any | None:
    """Build from committed routing or one task-local candidate snapshot."""

    if config is _RUNTIME_UNSET:
        return _load_supervisor_model()
    if not isinstance(config, SupervisorRuntimeConfig):
        raise TypeError("config must be SupervisorRuntimeConfig")
    normalized = validate_runtime_config(config)
    token = _RUNTIME_SCOPE.set(normalized)
    try:
        return _load_supervisor_model()
    finally:
        _RUNTIME_SCOPE.reset(token)


def _load_supervisor_model() -> Any | None:
    """Construct a Strands model for the configured provider, or None."""
    _load_dotenv()
    if os.environ.get("PEX_SUPERVISOR_DISABLE") == "1":
        return None
    try:
        pid = resolve_provider_id()
    except ValueError:
        return None
    if not pid:
        return None
    spec = PROVIDERS[pid]
    model_id = _configured_model_id(spec)
    base_url = _usable_base_url(_selected_base_url(spec))
    api_key = _credential_for(spec)
    kind = _effective_kind(spec)
    if _auth_mode(spec) in {"login", "agentcore"}:
        return None

    def ready(model: Any) -> Any:
        """Attach only safe routing facts to the exact constructed model."""

        provenance = {
            "provider": pid,
            "model_id": model_id,
            "base_url": _public_base_url(base_url),
            "auth_mode": _auth_mode(spec),
        }
        fingerprint_payload = json.dumps(
            {
                **provenance,
                "protocol": (
                    _active_runtime_config().protocol
                    if _active_runtime_config() is not None
                    else None
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        provenance["config_fingerprint"] = hashlib.sha256(
            fingerprint_payload.encode("utf-8")
        ).hexdigest()
        try:
            model._pex_provenance = provenance
        except (AttributeError, TypeError):
            pass
        return model

    if kind == "openai_compat":
        if spec.id == "azure_openai":
            return None
        if (
            spec.id not in {"ollama", "lmstudio", "vllm", "llamacpp"}
            and not api_key
            and spec.id != "custom"
        ):
            return None
        if spec.id == "custom" and _auth_mode(spec) == "api_key" and not api_key:
            return None
        if spec.id in {"azure_openai", "custom", "hermes"} and not base_url:
            return None
        if not model_id:
            return None
        from strands.models.openai import OpenAIModel

        client_args: dict[str, Any] = {}
        if api_key:
            client_args["api_key"] = api_key
        elif spec.id in {"lmstudio", "vllm", "custom"}:
            # The OpenAI SDK otherwise inherits OPENAI_API_KEY.  A harmless,
            # endpoint-scoped placeholder prevents that confused-deputy leak.
            client_args["api_key"] = "pex-no-api-key"
        if base_url:
            client_args["base_url"] = base_url
        client_args["timeout"] = _supervisor_timeout()
        client_args["http_client"] = credential_safe_http_client(
            timeout=_supervisor_timeout(),
            asynchronous=True,
        )
        return ready(
            OpenAIModel(
                client_args=client_args or None,
                model_id=model_id,
                stream=False,
                params=_openai_compat_chat_params(spec),
            )
        )

    if kind == "anthropic":
        if not model_id:
            return None
        if spec.id != "custom" and not api_key:
            return None
        if spec.id == "custom" and _auth_mode(spec) == "api_key" and not api_key:
            return None
        from strands.models.anthropic import AnthropicModel

        client_args: dict[str, Any] = {
            "api_key": api_key or "pex-no-api-key",
            "http_client": credential_safe_http_client(
                timeout=_supervisor_timeout(),
                protocol="anthropic",
                asynchronous=True,
            ),
        }
        if spec.id == "custom" and base_url:
            client_args["base_url"] = base_url
        return ready(
            AnthropicModel(
                client_args=client_args,
                model_id=model_id,
                params={"max_tokens": 4096},
            )
        )

    if kind == "google":
        if not api_key or not model_id:
            return None
        from strands.models.gemini import GeminiModel

        return ready(GeminiModel(client_args={"api_key": api_key}, model_id=model_id))

    if kind == "ollama":
        if not model_id:
            return None
        from strands.models.ollama import OllamaModel

        kwargs: dict[str, Any] = {"model_id": model_id}
        if base_url:
            kwargs["host"] = base_url
        try:
            return ready(OllamaModel(**kwargs))
        except TypeError:
            return ready(OllamaModel(model_id=model_id))

    if kind == "bedrock":
        from strands.models.bedrock import BedrockModel

        kwargs = {}
        if model_id:
            kwargs["model_id"] = model_id
        return ready(BedrockModel(**kwargs) if kwargs else BedrockModel())

    if kind == "llamacpp":
        from strands.models.llamacpp import LlamaCppModel

        return ready(LlamaCppModel(base_url=base_url or "http://127.0.0.1:8080"))

    if kind == "litellm":
        if not model_id:
            return None
        from strands.models.litellm import LiteLLMModel

        client_args: dict[str, Any] = {}
        if api_key:
            client_args["api_key"] = api_key
        if base_url:
            client_args["api_base"] = base_url
        return ready(LiteLLMModel(client_args=client_args or None, model_id=model_id))

    if kind == "writer":
        if not api_key:
            return None
        try:
            from strands.models.writer import WriterModel
        except ImportError:
            return None
        kwargs: dict[str, Any] = {"client_args": {"api_key": api_key}}
        if model_id:
            kwargs["model_id"] = model_id
        return ready(WriterModel(**kwargs))

    if kind == "sagemaker":
        # SageMakerAIModel requires explicit endpoint and payload configs.  The
        # generic provider/model schema cannot construct it truthfully yet.
        return None

    if kind == "llama_api":
        if not api_key:
            return None
        try:
            from strands.models.llamaapi import LlamaAPIModel
        except ImportError:
            return None
        kwargs = {"client_args": {"api_key": api_key}}
        if model_id:
            kwargs["model_id"] = model_id
        return ready(LlamaAPIModel(**kwargs))
    return None
