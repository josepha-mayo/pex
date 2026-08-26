"""User-pluggable PEX supervisor backends.

Worker harnesses (Cursor, Codex, …) are a different layer. This module only
loads the LLM that *is* PEX. No vendor is special. No machine-specific key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from pex_supervisor.catalog import catalog


def _load_dotenv() -> None:
    root = Path(__file__).resolve().parents[4]
    path = root / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _local_alive(url: str) -> bool:
    try:
        with httpx.Client(timeout=0.4) as client:
            response = client.get(url)
        return response.status_code < 500
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
        (
            "Use an OpenAI API key. Consumer ChatGPT and Codex CLI sessions are not reused."
        ),
    ),
    "azure_openai": ProviderSpec(
        "azure_openai",
        "openai_compat",
        None,
        ("AZURE_OPENAI_API_KEY", "PEX_SUPERVISOR_API_KEY"),
        ("api_key",),
    ),
    "anthropic": ProviderSpec(
        "anthropic",
        "anthropic",
        None,
        ("PEX_SUPERVISOR_API_KEY", "ANTHROPIC_API_KEY"),
        ("api_key",),
        "claude-sonnet-4-6",
        "Use an Anthropic API key. Consumer Claude sessions are not reused.",
    ),
    "google": ProviderSpec(
        "google",
        "google",
        None,
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
        ("api_key",),
        None,
        "AWS credentials / SSO. Hackathon AgentCore path, not exclusive.",
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
        "Set PEX_SUPERVISOR_PROVIDER=github_models. GITHUB_TOKEN is not auto-detected (too common).",
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
    if spec.kind in {"ollama", "lmstudio", "llamacpp", "vllm"}:
        return True
    if spec.id == "custom":
        return bool(os.environ.get("PEX_SUPERVISOR_BASE_URL"))
    if spec.id == "bedrock":
        return bool(_first_env("AWS_ACCESS_KEY_ID", "AWS_PROFILE", "AWS_SESSION_TOKEN"))
    return bool(_first_env(*spec.key_envs))


def resolve_provider_id() -> str | None:
    _load_dotenv()
    explicit = (os.environ.get("PEX_SUPERVISOR_PROVIDER") or "").strip().lower()
    if explicit:
        if explicit not in PROVIDERS:
            raise ValueError(f"unknown PEX_SUPERVISOR_PROVIDER {explicit!r}; use custom + BASE_URL")
        return explicit
    if os.environ.get("PEX_SUPERVISOR_BASE_URL"):
        return "custom"
    for pid in _AUTO_ORDER:
        if pid in {"ollama", "lmstudio"}:
            continue
        if _configured(PROVIDERS[pid]) and _first_env(*PROVIDERS[pid].key_envs):
            return pid
    for pid, probe in (
        ("ollama", "http://127.0.0.1:11434/api/tags"),
        ("lmstudio", "http://127.0.0.1:1234/v1/models"),
    ):
        if _local_alive(probe):
            return pid
    return None


def describe_backend() -> dict[str, Any]:
    _load_dotenv()
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
    key_present = bool(spec and _first_env(*spec.key_envs)) if spec else False
    return {
        "backend": pid,
        "base_url": os.environ.get("PEX_SUPERVISOR_BASE_URL") or (spec.base_url if spec else None),
        "model_id": os.environ.get("PEX_SUPERVISOR_MODEL")
        or (spec.default_model if spec else None),
        "auth_mode": os.environ.get("PEX_SUPERVISOR_AUTH")
        or (spec.auth_modes[0] if spec else None),
        "has_api_key": key_present,
        "login_note": spec.login_note if spec else "",
        "catalog_size": len(catalog()),
        "providers": sorted(PROVIDERS),
    }


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
    if spec.kind != "openai_compat":
        return None
    model_id = os.environ.get("PEX_SUPERVISOR_MODEL") or spec.default_model
    base_url = os.environ.get("PEX_SUPERVISOR_BASE_URL") or spec.base_url
    api_key = _first_env(*spec.key_envs) if spec.key_envs else None
    if spec.id in {"lmstudio", "vllm", "ollama", "llamacpp"}:
        api_key = api_key or "local"
    if not model_id or not base_url:
        return None
    if spec.id not in {"ollama", "lmstudio", "vllm", "llamacpp", "custom"} and not api_key:
        return None
    try:
        timeout = float(os.environ.get("PEX_SUPERVISOR_TIMEOUT", "45"))
    except ValueError:
        timeout = 45.0
    return {
        "provider": pid,
        "base_url": base_url,
        "model_id": model_id,
        "api_key": api_key,
        "timeout": timeout,
    }


def load_supervisor_model() -> Any | None:
    """Construct a Strands model for the configured provider, or None."""
    _load_dotenv()
    if os.environ.get("PEX_SUPERVISOR_DISABLE") == "1":
        return None
    pid = resolve_provider_id()
    if not pid:
        return None
    spec = PROVIDERS[pid]
    model_id = os.environ.get("PEX_SUPERVISOR_MODEL") or spec.default_model
    base_url = os.environ.get("PEX_SUPERVISOR_BASE_URL") or spec.base_url
    api_key = _first_env(*spec.key_envs) if spec.key_envs else None

    if spec.kind == "openai_compat":
        if (
            spec.id not in {"ollama", "lmstudio", "vllm", "llamacpp"}
            and not api_key
            and spec.id != "custom"
        ):
            return None
        if spec.id in {"azure_openai", "custom", "hermes"} and not base_url:
            return None
        if not model_id:
            return None
        from strands.models.openai import OpenAIModel

        client_args: dict[str, Any] = {}
        if api_key:
            client_args["api_key"] = api_key
        elif spec.id in {"lmstudio", "vllm"}:
            client_args["api_key"] = api_key or "local"
        if base_url:
            client_args["base_url"] = base_url
        client_args["timeout"] = float(os.environ.get("PEX_SUPERVISOR_TIMEOUT", "45"))
        return OpenAIModel(
            client_args=client_args or None,
            model_id=model_id,
            stream=False,
            params={"max_tokens": 700, "stream": False},
        )

    if spec.kind == "anthropic":
        if not api_key or not model_id:
            return None
        from strands.models.anthropic import AnthropicModel

        return AnthropicModel(
            client_args={"api_key": api_key},
            model_id=model_id,
            params={"max_tokens": 4096},
        )

    if spec.kind == "google":
        if not api_key or not model_id:
            return None
        from strands.models.gemini import GeminiModel

        return GeminiModel(client_args={"api_key": api_key}, model_id=model_id)

    if spec.kind == "ollama":
        if not model_id:
            return None
        from strands.models.ollama import OllamaModel

        kwargs: dict[str, Any] = {"model_id": model_id}
        if base_url:
            kwargs["host"] = base_url
        try:
            return OllamaModel(**kwargs)
        except TypeError:
            return OllamaModel(model_id=model_id)

    if spec.kind == "bedrock":
        from strands.models.bedrock import BedrockModel

        kwargs = {}
        if model_id:
            kwargs["model_id"] = model_id
        return BedrockModel(**kwargs) if kwargs else BedrockModel()

    if spec.kind == "llamacpp":
        from strands.models.llamacpp import LlamaCppModel

        return LlamaCppModel(base_url=base_url or "http://127.0.0.1:8080")

    if spec.kind == "litellm":
        if not model_id:
            return None
        from strands.models.litellm import LiteLLMModel

        return LiteLLMModel(model_id=model_id)

    if spec.kind == "writer":
        if not api_key:
            return None
        try:
            from strands.models.writer import WriterModel
        except ImportError:
            return None
        kwargs: dict[str, Any] = {"api_key": api_key}
        if model_id:
            kwargs["model_id"] = model_id
        return WriterModel(**kwargs)

    if spec.kind == "sagemaker":
        try:
            from strands.models.sagemaker import SageMakerAIModel
        except ImportError:
            try:
                from strands.models.sagemaker import SageMakerModel as SageMakerAIModel
            except ImportError:
                return None
        kwargs = {}
        if model_id:
            kwargs["model_id"] = model_id
        return SageMakerAIModel(**kwargs)

    if spec.kind == "llama_api":
        if not api_key:
            return None
        try:
            from strands.models.llamaapi import LlamaAPIModel
        except ImportError:
            return None
        kwargs = {"api_key": api_key}
        if model_id:
            kwargs["model_id"] = model_id
        return LlamaAPIModel(**kwargs)
    return None
