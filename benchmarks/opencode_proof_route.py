"""Fail-closed provider routing for isolated OpenCode proof workers."""

import hashlib
import os
from pathlib import Path

FREE_OPENCODE_MODELS = (
    "ling-3.0-flash-fin-free",
    "mimo-v2.6-flash-free",
    "nemotron-3-ultra-free",
    "nemotron-3.5-lightning-free",
)

NEBIUS_MODELS = (
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "nvidia/Nemotron-3_5-Lightning",
    "nvidia/nemotron-3-super-120b-a12b",
)

WORKER_BASE_URLS = {
    "opencode": "https://opencode.ai/zen/v1",
    "nebius": "https://api.tokenfactory.nebius.com/v1",
}

PROOF_WORKER_MODELS = FREE_OPENCODE_MODELS + NEBIUS_MODELS


class ProofRouteError(RuntimeError):
    """The requested worker model does not belong to the saved BYOK route."""


def proof_worker_route(
    saved_provider: str,
    worker_model: str,
    *,
    separate_worker_credential: bool = False,
    native_free: bool = False,
) -> tuple[str, str]:
    """Bind a worker model to the saved credential audience before secret access."""

    provider = saved_provider.casefold()
    if native_free and (separate_worker_credential or worker_model not in FREE_OPENCODE_MODELS):
        raise ProofRouteError("native worker route requires a listed free OpenCode model")
    if worker_model in NEBIUS_MODELS:
        if provider != "nebius":
            raise ProofRouteError("NVIDIA proof workers require the saved Nebius route")
        if separate_worker_credential:
            raise ProofRouteError("paid Nebius workers cannot use a separate worker credential")
        return "nebius", "Nebius Token Factory"
    if worker_model not in FREE_OPENCODE_MODELS:
        raise ProofRouteError("unsupported OpenCode proof worker model")
    if provider != "zen" and not separate_worker_credential and not native_free:
        raise ProofRouteError("free proof workers require the saved OpenCode Zen route")
    return "opencode", "OpenCode Zen"


def proof_worker_config(
    worker_provider: str, worker_model: str, provider_name: str, *, native_free: bool,
) -> dict:
    """Pin a free native route without fabricating an API credential."""

    config = {
        "$schema": "https://opencode.ai/config.json",
        "model": f"{worker_provider}/{worker_model}",
        "small_model": f"{worker_provider}/{worker_model}",
    }
    if native_free:
        if worker_provider != "opencode" or worker_model not in FREE_OPENCODE_MODELS:
            raise ProofRouteError("native worker route requires a listed free OpenCode model")
        return config
    config["provider"] = {
        worker_provider: {
            "npm": "@ai-sdk/openai-compatible",
            "name": provider_name,
            "options": {
                "baseURL": proof_worker_base_url(worker_provider),
                "apiKey": "{env:PEX_PROOF_PROVIDER_KEY}",
            },
            "models": {
                worker_model: {
                    "name": "PEX OpenCode worker model",
                    "reasoning": True,
                    "interleaved": {"field": "reasoning_content"},
                },
            },
        }
    }
    return config


def proof_worker_base_url(worker_provider: str) -> str:
    """Return the reviewed endpoint for one already validated worker route."""

    try:
        return WORKER_BASE_URLS[worker_provider]
    except KeyError as exc:
        raise ProofRouteError("unsupported OpenCode proof worker provider") from exc


def native_free_worker_environment(host: dict[str, str], root: Path) -> dict[str, str]:
    """Give a native free worker OS launch settings and fresh, credential-free homes."""

    environment = {
        key: value for key, value in host.items()
        if key.upper() in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC"}
    }
    homes = {
        "HOME": root / "home",
        "USERPROFILE": root / "home",
        "APPDATA": root / "appdata",
        "LOCALAPPDATA": root / "localappdata",
        "TEMP": root / "temp",
        "TMP": root / "temp",
        "XDG_CONFIG_HOME": root / "config",
        "XDG_CACHE_HOME": root / "cache",
        "XDG_DATA_HOME": root / "data",
        "XDG_STATE_HOME": root / "state",
    }
    for key, path in homes.items():
        path.mkdir(parents=True, exist_ok=True)
        environment[key] = str(path)
    return environment


def executable_sha256(path: Path) -> str:
    """Fingerprint the actual OpenCode executable used by a proof run."""

    with path.open("rb") as binary:
        return hashlib.file_digest(binary, "sha256").hexdigest()


def resolve_opencode_executable(shim: str, *, platform: str | None = None) -> Path:
    """Resolve the owned OpenCode launcher without assuming a Windows suffix."""

    platform = os.name if platform is None else platform
    discovered = Path(shim)
    if platform == "nt":
        parent = discovered.resolve().parent
        candidates = [parent / "node_modules/opencode-ai/bin/opencode.exe"]
        if parent.name == ".bin":
            candidates.append(parent.parent / "opencode-ai/bin/opencode.exe")
        executable = next((item for item in candidates if item.is_file()), candidates[0])
    else:
        executable = discovered.resolve()
    if not executable.is_file():
        raise RuntimeError("direct OpenCode executable is unavailable; refusing shim ownership")
    return executable
