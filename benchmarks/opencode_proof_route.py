"""Fail-closed provider routing for isolated OpenCode proof workers."""

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
) -> tuple[str, str]:
    """Bind a worker model to the saved credential audience before secret access."""

    provider = saved_provider.casefold()
    if worker_model in NEBIUS_MODELS:
        if provider != "nebius":
            raise ProofRouteError("NVIDIA proof workers require the saved Nebius route")
        return "nebius", "Nebius Token Factory"
    if worker_model not in FREE_OPENCODE_MODELS:
        raise ProofRouteError("unsupported OpenCode proof worker model")
    if provider != "zen" and not separate_worker_credential:
        raise ProofRouteError("free proof workers require the saved OpenCode Zen route")
    return "opencode", "OpenCode Zen"


def proof_worker_base_url(worker_provider: str) -> str:
    """Return the reviewed endpoint for one already validated worker route."""

    try:
        return WORKER_BASE_URLS[worker_provider]
    except KeyError as exc:
        raise ProofRouteError("unsupported OpenCode proof worker provider") from exc


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
