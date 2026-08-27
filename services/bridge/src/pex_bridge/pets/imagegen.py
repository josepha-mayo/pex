"""Image generation for in-app hatch, using the same credentials as PEX inspect.

Never log api_key. Zen chat is text-only; hatch needs /images/generations.
"""

from __future__ import annotations

import base64
import os
from typing import Any
from urllib.parse import urljoin

import httpx

from pex_supervisor.providers import openai_compat_client_config

IMAGES_PATH = "/images/generations"
EDITS_PATH = "/images/edits"


class HatchImageError(RuntimeError):
    """Provider has no usable image endpoint, or a generate call failed."""


def _first_env(*names: str) -> str | None:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return None


def hatch_image_config() -> dict[str, Any] | None:
    """Prefer explicit hatch env, then the supervisor OpenAI-compat backend, then OpenAI."""
    hatch_url = _first_env("PEX_HATCH_BASE_URL")
    hatch_key = _first_env("PEX_HATCH_API_KEY", "OPENAI_API_KEY")
    hatch_model = _first_env("PEX_HATCH_MODEL")
    if hatch_url:
        return {
            "provider": "hatch",
            "base_url": hatch_url.rstrip("/"),
            "api_key": hatch_key,
            "model_id": hatch_model or "gpt-image-1",
            "timeout": 90.0,
        }
    supervisor = openai_compat_client_config()
    if supervisor:
        return {
            "provider": supervisor["provider"],
            "base_url": str(supervisor["base_url"]).rstrip("/"),
            "api_key": supervisor.get("api_key"),
            "model_id": hatch_model or os.environ.get("PEX_HATCH_MODEL") or "gpt-image-1",
            "timeout": 90.0,
        }
    openai_key = _first_env("OPENAI_API_KEY")
    if openai_key:
        return {
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": openai_key,
            "model_id": hatch_model or "gpt-image-1",
            "timeout": 90.0,
        }
    return None


def describe_hatch_backend() -> dict[str, Any]:
    cfg = hatch_image_config()
    if not cfg:
        return {
            "ok": False,
            "has_image_endpoint": False,
            "reason": (
                "No image provider. Set PEX_HATCH_BASE_URL and PEX_HATCH_API_KEY "
                "(OpenAI Images or another /v1/images/generations host), or OPENAI_API_KEY. "
                "The current supervisor chat backend is not enough."
            ),
        }
    return {
        "ok": True,
        "provider": cfg["provider"],
        "base_url": cfg["base_url"],
        "model_id": cfg["model_id"],
        "has_api_key": bool(cfg.get("api_key")),
        "images_path": IMAGES_PATH,
        "note": "Click Hatch to probe /images/generations. Text-only Zen chat will fail honestly.",
    }


def _headers(cfg: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = cfg.get("api_key")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def probe_images_endpoint(cfg: dict[str, Any] | None = None, client: httpx.Client | None = None) -> dict[str, Any]:
    """HEAD/GET the images route. 404 means text-only. Never send a billed generate."""
    cfg = cfg or hatch_image_config()
    if not cfg:
        return describe_hatch_backend()
    url = urljoin(cfg["base_url"] + "/", IMAGES_PATH.lstrip("/"))
    own = client is None
    http = client or httpx.Client(timeout=12.0)
    try:
        try:
            response = http.get(url, headers=_headers(cfg))
        except httpx.RequestError as exc:
            return {
                "ok": False,
                "has_image_endpoint": False,
                "provider": cfg["provider"],
                "reason": f"Could not reach images endpoint: {exc.__class__.__name__}",
            }
        status = response.status_code
        exists = status != 404
        if status == 404:
            reason = (
                f"{cfg['provider']} has no {IMAGES_PATH}. "
                "Set PEX_HATCH_BASE_URL to an image-capable host (OpenAI, OpenRouter image model) "
                "or hatch from the hatch-pet skill."
            )
        elif exists:
            reason = f"Images route responded {status}; Hatch will try generate next."
        else:
            reason = f"Unexpected images probe status {status}."
        return {
            "ok": exists,
            "has_image_endpoint": exists,
            "provider": cfg["provider"],
            "base_url": cfg["base_url"],
            "model_id": cfg["model_id"],
            "probe_status": status,
            "reason": reason,
        }
    finally:
        if own:
            http.close()


def _decode_image_payload(payload: dict[str, Any]) -> bytes:
    data = payload.get("data") or []
    if not data:
        raise HatchImageError("image API returned no data")
    item = data[0]
    b64 = item.get("b64_json") or item.get("b64")
    if b64:
        return base64.b64decode(b64)
    url = item.get("url")
    if not url:
        raise HatchImageError("image API returned neither b64_json nor url")
    with httpx.Client(timeout=60.0) as http:
        downloaded = http.get(url)
        downloaded.raise_for_status()
        return downloaded.content


def generate_png(prompt: str, *, size: str = "1024x1024", client: httpx.Client | None = None) -> bytes:
    cfg = hatch_image_config()
    if not cfg:
        raise HatchImageError(describe_hatch_backend()["reason"])
    url = urljoin(cfg["base_url"] + "/", IMAGES_PATH.lstrip("/"))
    body = {
        "model": cfg["model_id"],
        "prompt": prompt,
        "size": size,
        "n": 1,
    }
    own = client is None
    http = client or httpx.Client(timeout=cfg["timeout"])
    try:
        response = http.post(url, headers=_headers(cfg), json=body)
        if response.status_code == 404:
            raise HatchImageError(
                f"{cfg['provider']} has no {IMAGES_PATH}. "
                "Your supervisor model is text-only. Set PEX_HATCH_BASE_URL / PEX_HATCH_API_KEY "
                "to OpenAI Images or another image host."
            )
        if response.status_code >= 400:
            text = (response.text or "")[:240]
            raise HatchImageError(f"image generate failed HTTP {response.status_code}: {text}")
        return _decode_image_payload(response.json())
    finally:
        if own:
            http.close()
