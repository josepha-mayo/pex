"""Bounded OpenAI-compatible completion used only by the bridge review answer.

Supervisor interventions run through :mod:`pex_supervisor.loop` and its
validated Strands ``SupervisorDecision`` output. This module deliberately does
not expose an alternate action-proposal path.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from pex_supervisor.providers import credential_safe_http_client, openai_compat_client_config
from pex_supervisor.review_authority import require_review_authority


class InspectUnavailable(RuntimeError):
    """No OpenAI-compatible review endpoint is configured."""


_FALLBACK_MODELS = ("hy3-free", "laguna-s-2.1-free", "big-pickle")
_MAX_RESPONSE_BYTES = 262_144
_MAX_RESPONSE_CHUNKS = 4_096


def _reject_nonfinite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _bounded_count(value: object) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return min(1_000_000_000, max(0, parsed))


def _model_unsupported(status: int, body: str) -> bool:
    if status == 404:
        return True
    if status not in {400, 401, 404}:
        return False
    lowered = body.lower()
    return "not supported" in lowered or "model_not_found" in lowered or "does not exist" in lowered


def _candidate_models(cfg: dict[str, Any]) -> list[str]:
    """Zen free IDs are not OpenRouter/OpenAI model ids. Do not send them there."""
    models: list[str] = []
    primary = str(cfg.get("model_id") or "").strip()[:512]
    if primary:
        models.append(primary)
    if cfg.get("provider") == "zen":
        for item in _FALLBACK_MODELS:
            if item and item not in models:
                models.append(item)
    return models


def _rate_limited(status: int, body: str) -> bool:
    if status == 429:
        return True
    lowered = body.lower()
    return "rate limit" in lowered or "freeusagelimit" in lowered


def _skip_model(status: int, body: str) -> bool:
    if status >= 500:
        return True
    if _rate_limited(status, body) or _model_unsupported(status, body):
        return True
    lowered = body.lower()
    return "unavailable" in lowered or "endpoint is unavailable" in lowered


def _loads_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if len(raw.encode("utf-8", "replace")) > 65_536:
        raise ValueError("review content exceeds the parser limit")
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    candidates = [raw]
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1])
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            decoded = json.loads(
                candidate,
                parse_constant=_reject_nonfinite_json_constant,
                object_pairs_hook=_unique_json_object,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            continue
        if isinstance(decoded, dict):
            return decoded
        last_error = ValueError("review content was not an object")
    if last_error:
        raise last_error
    raise ValueError("review content was not an object")


def _parse_response_object(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("review model returned no choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("review model returned an invalid message")
    if message.get("tool_calls"):
        raise ValueError("review content may not contain tool calls")
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(
            (str(part.get("text") or "") if isinstance(part, dict) else str(part))[:4_000]
            for part in content[:32]
        )
    elif not isinstance(content, str):
        raise ValueError("review model returned invalid content")
    return _loads_object(str(content))


def usage_tokens(payload: dict[str, Any]) -> dict[str, int]:
    usage = payload.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    return {
        "input_tokens": _bounded_count(
            usage.get("prompt_tokens") or usage.get("input_tokens")
        ),
        "output_tokens": _bounded_count(
            usage.get("completion_tokens") or usage.get("output_tokens")
        ),
    }


def _read_response_text(response: httpx.Response) -> str:
    body = bytearray()
    for index, chunk in enumerate(response.iter_bytes()):
        if index >= _MAX_RESPONSE_CHUNKS:
            raise ValueError("review response contained too many chunks")
        if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
            raise ValueError("review response exceeds the byte limit")
        body.extend(chunk)
    return bytes(body).decode("utf-8")


def _chat_json(
    system: str, user: str, *, max_tokens: int = 400
) -> tuple[dict[str, Any], dict[str, int]]:
    cfg = openai_compat_client_config()
    if cfg is None:
        raise InspectUnavailable("no openai-compat supervisor")
    if not 1 <= max_tokens <= 1_000:
        raise ValueError("max_tokens must be between 1 and 1000")
    if len(system.encode("utf-8", "replace")) > 16_384:
        raise ValueError("review system prompt exceeds the byte limit")
    if len(user.encode("utf-8", "replace")) > 65_536:
        raise ValueError("review user prompt exceeds the byte limit")
    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    timeout = httpx.Timeout(18.0, connect=6.0)
    models = _candidate_models(cfg)
    last_error = "no supervisor model"
    with credential_safe_http_client(timeout=timeout) as client:
        for model in models:
            payload = {
                "model": model,
                "stream": False,
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            try:
                require_review_authority()
                with client.stream(
                    "POST", url, headers=headers, json=payload, timeout=timeout
                ) as response:
                    response_text = _read_response_text(response)
                    status_code = response.status_code
                    content_type = response.headers.get("content-type", "").split(";", 1)[
                        0
                    ].strip().casefold()
                    if _skip_model(status_code, response_text):
                        last_error = f"model {model} unavailable"
                        continue
                    response.raise_for_status()
                    if content_type != "application/json":
                        raise ValueError("review endpoint did not return application/json")
                    data = json.loads(
                        response_text,
                        parse_constant=_reject_nonfinite_json_constant,
                        object_pairs_hook=_unique_json_object,
                    )
                    if not isinstance(data, dict):
                        raise ValueError("review endpoint returned a non-object response")
                    parsed = _parse_response_object(data)
            except httpx.TimeoutException:
                last_error = f"model {model} timed out"
                continue
            except (
                UnicodeDecodeError,
                ValueError,
                json.JSONDecodeError,
                httpx.HTTPError,
            ) as exc:
                last_error = f"model {model} {exc.__class__.__name__}"
                continue
            return parsed, usage_tokens(data)
    raise RuntimeError(last_error)


def complete_review_answer(system: str, user: str) -> tuple[str, dict[str, int], str]:
    json_system = system + "\nReturn only JSON with key answer (a string). No markdown."
    parsed, usage = _chat_json(json_system, user, max_tokens=350)
    if set(parsed) != {"answer"}:
        raise ValueError("review payload must contain only answer")
    raw_answer = parsed["answer"]
    if not isinstance(raw_answer, str):
        raise ValueError("review answer must be a string")
    answer = raw_answer.strip()
    if not answer or len(answer) > 4_000:
        raise ValueError("review answer must contain 1 to 4000 characters")
    return answer, usage, "review_answer"
