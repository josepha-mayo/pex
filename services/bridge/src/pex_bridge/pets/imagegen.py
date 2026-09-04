"""Credential-scoped image generation for the in-app hatch candidate flow.

Never log api_key. Zen chat is text-only; hatch needs /images/generations.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import ipaddress
import json
import math
import os
import re
from collections.abc import Iterator, Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from pex_supervisor.providers import openai_compat_client_config

IMAGES_PATH = "/images/generations"
EDITS_PATH = "/images/edits"
MAX_IMAGE_API_RESPONSE_BYTES = 36 * 1024 * 1024
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_API_CHUNKS = 4096
MAX_IMAGE_PROMPT_BYTES = 32_768
MAX_IMAGE_MODEL_BYTES = 256
_ALLOWED_IMAGE_SIZES = {"1024x1024", "1536x1024", "1024x1536", "auto"}
_OPENAI_IMAGE_BASE_URL = "https://api.openai.com/v1"
_OPENAI_IMAGE_HOST = "api.openai.com"
_CANONICAL_HTTP_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_SERVICE_PATH = re.compile(r"(?:/[A-Za-z0-9._~-]+)*\Z")


class HatchImageError(RuntimeError):
    """Provider has no usable image endpoint, or a generate call failed."""


class _SecretValue(str):
    """A request credential whose repr is safe in tracebacks and containers."""

    def __repr__(self) -> str:
        return "<redacted>"


class HatchImageConfig(Mapping[str, Any]):
    """Internal image-provider config with a deliberately non-serializing secret.

    Public mapping iteration omits ``api_key``. Internal request code may still use
    ``get('api_key')``; repr/str and ``dict(config)`` cannot disclose it accidentally.
    """

    __slots__ = ("_api_key", "_public")

    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str | None,
        model_id: str,
        timeout: float,
    ) -> None:
        self._public = {
            "provider": provider,
            "base_url": base_url,
            "model_id": model_id,
            "timeout": timeout,
        }
        self._api_key = _SecretValue(api_key) if api_key else None

    def __getitem__(self, key: str) -> Any:
        if key == "api_key":
            return self._api_key
        value = self._public[key]
        return _redact_key_material(str(value), self._api_key) if isinstance(value, str) else value

    def __iter__(self) -> Iterator[str]:
        return iter(self._public)

    def __len__(self) -> int:
        return len(self._public)

    def __repr__(self) -> str:
        public = {key: self[key] for key in self._public}
        public["has_api_key"] = self._api_key is not None
        return f"HatchImageConfig({public!r})"

    __str__ = __repr__

    def _request_value(self, key: str) -> Any:
        """Return raw internal routing data; never use in UI/API/log output."""

        if key == "api_key":
            return self._api_key
        return self._public[key]


def _first_env(*names: str) -> str | None:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if not value or len(value.encode("utf-8")) > 16_384:
            continue
        if "\r" in value or "\n" in value or "\x00" in value:
            continue
        return value
    return None


def _redact_key_material(value: str, api_key: str | None) -> str:
    if api_key:
        return value.replace(str(api_key), "[redacted]")
    return value


def _canonical_dns_host(host: str) -> str | None:
    """Return a bounded ASCII DNS name; reject ambiguous host spellings."""

    try:
        host.encode("ascii")
    except UnicodeEncodeError:
        return None
    lowered = host.lower()
    if not lowered or len(lowered) > 253 or lowered.endswith(".") or ".." in lowered:
        return None
    if re.fullmatch(r"[0-9.]+", lowered) or re.fullmatch(r"0x[0-9a-f]+", lowered):
        return None
    labels = lowered.split(".")
    if not all(_DNS_LABEL.fullmatch(label) for label in labels):
        return None
    return lowered


def _canonical_ip_host(host: str) -> str | None:
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        return None
    canonical = str(parsed).lower()
    return canonical if host.lower() == canonical else None


def _safe_base_url(value: Any) -> str | None:
    """Validate and canonicalize an image API service root.

    Remote cleartext HTTP is never accepted. The only cleartext exception is an
    unambiguous loopback IP literal (127.0.0.1 or ::1). Percent escapes, dot
    segments, endpoint paths, userinfo, and redundant default ports are rejected
    instead of being normalized into a different request target.
    """

    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned.encode("utf-8")) > 2048:
        return None
    if (
        any(ord(char) < 32 or ord(char) == 127 for char in cleaned)
        or "\\" in cleaned
        or "%" in cleaned
    ):
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
    except ValueError:
        return None

    scheme = parsed.scheme.lower()
    raw_host = parsed.hostname
    if raw_host is None or parsed.netloc.endswith(":"):
        return None
    ip_host = _canonical_ip_host(raw_host)
    host = ip_host or _canonical_dns_host(raw_host)
    if not host:
        return None
    if ":" in host and not parsed.netloc.startswith("["):
        return None
    authority = parsed.netloc
    port_text: str | None = None
    if authority.startswith("["):
        close = authority.find("]")
        if close < 0 or authority[close + 1 :] not in {"", f":{port}"}:
            return None
        if authority[close + 1 :].startswith(":"):
            port_text = authority[close + 2 :]
    elif ":" in authority:
        _, port_text = authority.rsplit(":", 1)
    if port_text is not None and (not port_text.isascii() or str(port) != port_text):
        return None
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        return None

    path = parsed.path
    if path.endswith("//"):
        return None
    if path.endswith("/") and path != "/":
        path = path[:-1]
    if path in {"", "/"}:
        path = ""
    else:
        if not _SERVICE_PATH.fullmatch(path):
            return None
        segments = path.split("/")[1:]
        if any(segment in {"", ".", ".."} for segment in segments):
            return None
        if path.lower().endswith((IMAGES_PATH, EDITS_PATH)):
            return None

    if host == _OPENAI_IMAGE_HOST:
        if scheme != "https" or port is not None or path != "/v1":
            return None
        return _OPENAI_IMAGE_BASE_URL

    if scheme == "http" and host not in _CANONICAL_HTTP_LOOPBACK_HOSTS:
        return None

    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc = f"{netloc}:{port}"
    return urlunsplit((scheme, netloc, path, "", ""))


def _is_canonical_openai_image_base(base_url: str) -> bool:
    return base_url == _OPENAI_IMAGE_BASE_URL


def _endpoint_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _same_secret(first: str | None, second: str | None) -> bool:
    if not first or not second:
        return False
    try:
        return hmac.compare_digest(first.encode("utf-8"), second.encode("utf-8"))
    except (TypeError, UnicodeEncodeError):
        return False


def _safe_model_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned.encode("utf-8")) > MAX_IMAGE_MODEL_BYTES:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in cleaned):
        return None
    return cleaned


def _internal_config_value(cfg: Mapping[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(cfg, HatchImageConfig):
        try:
            return cfg._request_value(key)
        except KeyError:
            return default
    return cfg.get(key, default)


def _validated_config(cfg: Any) -> HatchImageConfig:
    if not isinstance(cfg, Mapping):
        raise HatchImageError("image provider configuration is invalid")
    base_url = _safe_base_url(_internal_config_value(cfg, "base_url"))
    model_id = _safe_model_id(_internal_config_value(cfg, "model_id"))
    provider = _safe_model_id(_internal_config_value(cfg, "provider"))
    key = _internal_config_value(cfg, "api_key")
    if key is not None:
        if not isinstance(key, str):
            raise HatchImageError("image provider configuration is invalid")
        key = key.strip()
        if (
            not key
            or len(key.encode("utf-8")) > 16_384
            or "\r" in key
            or "\n" in key
            or "\x00" in key
        ):
            raise HatchImageError("image provider configuration is invalid")
    try:
        timeout = float(_internal_config_value(cfg, "timeout", 90.0))
    except (TypeError, ValueError, OverflowError):
        raise HatchImageError("image provider configuration is invalid") from None
    if not base_url or not model_id or not provider or not math.isfinite(timeout):
        raise HatchImageError("image provider configuration is invalid")
    return HatchImageConfig(
        provider=provider,
        base_url=base_url,
        api_key=key,
        model_id=model_id,
        timeout=min(120.0, max(1.0, timeout)),
    )


def hatch_image_config() -> HatchImageConfig | None:
    """Resolve a credential-bound image endpoint without cross-host key inheritance."""

    hatch_url_was_set = "PEX_HATCH_BASE_URL" in os.environ
    configured_hatch_url = _first_env("PEX_HATCH_BASE_URL")
    hatch_url = _safe_base_url(configured_hatch_url)
    hatch_key = _first_env("PEX_HATCH_API_KEY")
    configured_hatch_model = _first_env("PEX_HATCH_MODEL")
    hatch_model = _safe_model_id(configured_hatch_model) if configured_hatch_model else None
    if hatch_url_was_set:
        # An explicit hatch URL is a distinct trust boundary. It never inherits
        # OPENAI_API_KEY (even when it happens to point at api.openai.com).
        if not hatch_url or not hatch_key or (configured_hatch_model and not hatch_model):
            return None
        return _validated_config(
            {
                "provider": "hatch",
                "base_url": hatch_url,
                "api_key": hatch_key,
                "model_id": hatch_model or "gpt-image-1",
                "timeout": 90.0,
            }
        )
    supervisor = openai_compat_client_config()
    if isinstance(supervisor, Mapping):
        if configured_hatch_model and not hatch_model:
            return None
        supervisor_base = _safe_base_url(supervisor.get("base_url"))
        if not supervisor_base:
            return None
        # Prefer a deliberately scoped hatch key. Otherwise permit the supervisor's
        # own key, except when it was inherited solely from OPENAI_API_KEY and the
        # destination is not the canonical OpenAI Images service root.
        hatch_key = _first_env("PEX_HATCH_API_KEY") or hatch_key
        openai_key = _first_env("OPENAI_API_KEY")
        supervisor_key = supervisor.get("api_key")
        supervisor_key = str(supervisor_key).strip() if supervisor_key else None
        explicit_supervisor_key = _first_env("PEX_SUPERVISOR_API_KEY")
        selected_key = hatch_key or supervisor_key
        inherited_openai_key = (
            not hatch_key
            and not _same_secret(supervisor_key, explicit_supervisor_key)
            and _same_secret(supervisor_key, openai_key)
        )
        if inherited_openai_key and not _is_canonical_openai_image_base(supervisor_base):
            return None
        return _validated_config(
            {
                "provider": supervisor.get("provider"),
                "base_url": supervisor_base,
                "api_key": selected_key,
                "model_id": hatch_model or "gpt-image-1",
                "timeout": 90.0,
            }
        )
    openai_key = _first_env("OPENAI_API_KEY")
    hatch_key = _first_env("PEX_HATCH_API_KEY") or hatch_key
    if hatch_key or openai_key:
        if configured_hatch_model and not hatch_model:
            return None
        return _validated_config(
            {
                "provider": "openai",
                "base_url": _OPENAI_IMAGE_BASE_URL,
                "api_key": hatch_key or openai_key,
                "model_id": hatch_model or "gpt-image-1",
                "timeout": 90.0,
            }
        )
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
        "provider": _public_config_field(cfg, "provider"),
        "model_id": _public_config_field(cfg, "model_id"),
        "has_api_key": bool(cfg.get("api_key")),
        "images_path": IMAGES_PATH,
        "note": "Click Hatch to probe /images/generations. Text-only Zen chat will fail honestly.",
    }


def _public_config_field(cfg: Mapping[str, Any], key: str) -> str:
    return _redact_key_material(str(cfg[key]), cfg.get("api_key"))


def _headers(cfg: Mapping[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = _internal_config_value(cfg, "api_key")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def probe_images_endpoint(
    cfg: Mapping[str, Any] | None = None, client: httpx.Client | None = None
) -> dict[str, Any]:
    """HEAD/GET the images route. 404 means text-only. Never send a billed generate."""
    if cfg is None:
        cfg = hatch_image_config()
        if cfg is None:
            return describe_hatch_backend()
    try:
        cfg = _validated_config(cfg)
    except HatchImageError:
        return {
            "ok": False,
            "has_image_endpoint": False,
            "generation_ready": False,
            "reason": "Image provider configuration is invalid.",
        }
    provider = _public_config_field(cfg, "provider")
    model_id = _public_config_field(cfg, "model_id")
    url = _endpoint_url(_internal_config_value(cfg, "base_url"), IMAGES_PATH)
    own = client is None
    http = client or httpx.Client(timeout=12.0, follow_redirects=False)
    try:
        try:
            stream = getattr(http, "stream", None)
            if callable(stream):
                with stream("GET", url, headers=_headers(cfg)) as response:
                    status = response.status_code
            else:
                response = http.get(url, headers=_headers(cfg))
                status = response.status_code
        except httpx.RequestError as exc:
            return {
                "ok": False,
                "has_image_endpoint": False,
                "provider": provider,
                "reason": f"Could not reach images endpoint: {exc.__class__.__name__}",
            }
        if not isinstance(status, int) or not 100 <= status <= 599:
            return {
                "ok": False,
                "has_image_endpoint": False,
                "generation_ready": False,
                "provider": provider,
                "reason": "Images route returned an invalid HTTP status.",
            }
        if status == 404:
            reason = (
                f"{provider} has no {IMAGES_PATH}. "
                "Set PEX_HATCH_BASE_URL to an image-capable host (OpenAI, OpenRouter image model) "
                "or hatch from the hatch-pet skill."
            )
        elif status in {200, 400, 405}:
            reason = f"Images route responded {status}; generation capability is plausible."
        elif status in {401, 403}:
            reason = f"Images route rejected the configured credentials (HTTP {status})."
        elif status == 429:
            reason = "Images route is currently rate limited (HTTP 429)."
        else:
            reason = f"Images route readiness is unverified (HTTP {status})."
        exists = status != 404
        ready = status in {200, 400, 405}
        return {
            "ok": ready,
            "has_image_endpoint": exists,
            "generation_ready": ready,
            "provider": provider,
            "model_id": model_id,
            "probe_status": status,
            "reason": reason,
        }
    finally:
        if own:
            http.close()


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _response_content_length(response: Any) -> int | None:
    headers = getattr(response, "headers", None)
    if headers is None or not hasattr(headers, "get"):
        return None
    raw = headers.get("content-length")
    if raw is None:
        return None
    try:
        length = int(raw)
    except (TypeError, ValueError):
        raise HatchImageError("image API returned an invalid Content-Length") from None
    if length < 0:
        raise HatchImageError("image API returned an invalid Content-Length")
    return length


def _bounded_json_response(response: Any) -> dict[str, Any]:
    declared = _response_content_length(response)
    if declared is not None and declared > MAX_IMAGE_API_RESPONSE_BYTES:
        raise HatchImageError("image API response exceeded the 36 MiB safety bound")
    headers = getattr(response, "headers", None)
    if headers is not None and hasattr(headers, "get"):
        media_type = str(headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if media_type and media_type != "application/json" and not media_type.endswith("+json"):
            raise HatchImageError("image API did not return JSON")

    iter_bytes = getattr(response, "iter_bytes", None)
    if callable(iter_bytes):
        chunks = bytearray()
        for index, chunk in enumerate(iter_bytes()):
            if index >= MAX_IMAGE_API_CHUNKS:
                raise HatchImageError("image API response exceeded the chunk safety bound")
            if not isinstance(chunk, bytes):
                raise HatchImageError("image API returned a malformed response stream")
            if len(chunks) + len(chunk) > MAX_IMAGE_API_RESPONSE_BYTES:
                raise HatchImageError("image API response exceeded the 36 MiB safety bound")
            chunks.extend(chunk)
        try:
            payload = json.loads(
                bytes(chunks),
                parse_constant=_reject_nonfinite_json,
                object_pairs_hook=_unique_json_object,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
            raise HatchImageError("image API returned invalid JSON") from None
    else:
        content = getattr(response, "content", None)
        if isinstance(content, bytes):
            if len(content) > MAX_IMAGE_API_RESPONSE_BYTES:
                raise HatchImageError("image API response exceeded the 36 MiB safety bound")
            try:
                payload = json.loads(
                    content,
                    parse_constant=_reject_nonfinite_json,
                    object_pairs_hook=_unique_json_object,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
                raise HatchImageError("image API returned invalid JSON") from None
        else:
            response_json = getattr(response, "json", None)
            if not callable(response_json):
                raise HatchImageError("image API returned an unreadable response")
            try:
                payload = response_json()
            except (ValueError, TypeError, RecursionError):
                raise HatchImageError("image API returned invalid JSON") from None
    if not isinstance(payload, dict):
        raise HatchImageError("image API returned a non-object response")
    return payload


def _decode_image_payload(payload: dict[str, Any]) -> bytes:
    data = payload.get("data") or []
    if not isinstance(data, list) or not data or len(data) > 8:
        raise HatchImageError("image API returned malformed image data")
    item = data[0]
    if not isinstance(item, dict):
        raise HatchImageError("image API returned malformed image data")
    b64 = item.get("b64_json") or item.get("b64")
    if b64:
        if not isinstance(b64, (str, bytes)) or len(b64) > MAX_IMAGE_API_RESPONSE_BYTES:
            raise HatchImageError("image API returned invalid base64 image data")
        try:
            decoded = base64.b64decode(b64, validate=True)
        except (binascii.Error, TypeError, ValueError):
            raise HatchImageError("image API returned invalid base64 image data") from None
        if not decoded or len(decoded) > MAX_IMAGE_BYTES:
            raise HatchImageError("decoded image exceeded the 25 MiB safety bound")
        return decoded
    url = item.get("url")
    if url:
        raise HatchImageError(
            "image API ignored response_format=b64_json; external URL downloads are blocked"
        )
    raise HatchImageError("image API returned no base64 image data")


def generate_png(
    prompt: str,
    *,
    size: str = "1024x1024",
    client: httpx.Client | None = None,
    config: Mapping[str, Any] | None = None,
) -> bytes:
    cfg = config
    if cfg is None:
        cfg = hatch_image_config()
        if cfg is None:
            raise HatchImageError(describe_hatch_backend()["reason"])
    cfg = _validated_config(cfg)
    if not isinstance(prompt, str) or not prompt.strip():
        raise HatchImageError("image prompt must be non-empty text")
    if len(prompt.encode("utf-8")) > MAX_IMAGE_PROMPT_BYTES:
        raise HatchImageError("image prompt exceeded the 32 KiB safety bound")
    if size not in _ALLOWED_IMAGE_SIZES:
        raise HatchImageError("unsupported image size")
    provider = _public_config_field(cfg, "provider")
    url = _endpoint_url(_internal_config_value(cfg, "base_url"), IMAGES_PATH)
    body = {
        "model": _internal_config_value(cfg, "model_id"),
        "prompt": prompt,
        "size": size,
        "n": 1,
        "response_format": "b64_json",
    }
    own = client is None
    http = client or httpx.Client(
        timeout=_internal_config_value(cfg, "timeout"), follow_redirects=False
    )
    try:
        stream = getattr(http, "stream", None)
        if callable(stream):
            with stream("POST", url, headers=_headers(cfg), json=body) as response:
                status = response.status_code
                if status == 404:
                    raise HatchImageError(
                        f"{provider} has no {IMAGES_PATH}. "
                        "Your supervisor model is text-only. Set PEX_HATCH_BASE_URL / "
                        "PEX_HATCH_API_KEY to OpenAI Images or another image host."
                    )
                if not isinstance(status, int) or not 200 <= status < 300:
                    safe_status = status if isinstance(status, int) else "invalid"
                    raise HatchImageError(f"image generate failed HTTP {safe_status}")
                payload = _bounded_json_response(response)
        else:
            response = http.post(url, headers=_headers(cfg), json=body)
            status = response.status_code
            if status == 404:
                raise HatchImageError(
                    f"{provider} has no {IMAGES_PATH}. "
                    "Your supervisor model is text-only. Set PEX_HATCH_BASE_URL / "
                    "PEX_HATCH_API_KEY to OpenAI Images or another image host."
                )
            if not isinstance(status, int) or not 200 <= status < 300:
                raise HatchImageError(
                    f"image generate failed HTTP {status if isinstance(status, int) else 'invalid'}"
                )
            payload = _bounded_json_response(response)
        return _decode_image_payload(payload)
    except httpx.RequestError as exc:
        raise HatchImageError(
            f"image generate request failed ({type(exc).__name__})"
        ) from None
    finally:
        if own:
            http.close()
