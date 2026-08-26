"""Bounded OpenAI-compat inspect. Strands Agent() can stream-hang past STOP."""

from __future__ import annotations

import json
from typing import Any

import httpx

from pex_supervisor.providers import openai_compat_client_config

PROPOSE_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_typed_action",
        "description": (
            "Commit PEX's single typed intervention. "
            "action_type must be a valid InterventionType. "
            "evidence is pipe-separated observable facts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action_type": {"type": "string"},
                "rationale": {"type": "string"},
                "evidence": {"type": "string"},
                "message": {"type": "string"},
                "payload_json": {"type": "string"},
                "request_id": {"type": "string"},
                "decision": {"type": "string"},
                "overlay_id": {"type": "string"},
                "confidence": {"type": "number"},
                "risk": {"type": "string"},
            },
            "required": ["action_type", "rationale", "evidence"],
        },
    },
}


class InspectUnavailable(RuntimeError):
    """No OpenAI-compatible supervisor endpoint is configured."""


_FALLBACK_MODELS = ("hy3-free", "laguna-s-2.1-free", "big-pickle")


def _model_unsupported(status: int, body: str) -> bool:
    if status not in {400, 401, 404}:
        return False
    lowered = body.lower()
    return "not supported" in lowered or "model_not_found" in lowered or "does not exist" in lowered


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
            decoded = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(decoded, dict):
            return decoded
        last_error = ValueError("supervisor content was not an object")
    if last_error:
        raise last_error
    raise ValueError("supervisor content was not a proposal object")


def parse_proposal_args(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("supervisor returned no choices")
    message = choices[0].get("message") or {}
    calls = message.get("tool_calls") or []
    if calls:
        raw = ((calls[0].get("function") or {}).get("arguments")) or "{}"
        if isinstance(raw, dict):
            return raw
        text = str(raw).strip()
        if not text:
            raise ValueError("empty tool arguments")
        return _loads_object(text)
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(
            str(part.get("text") or "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return _loads_object(str(content))


def usage_tokens(payload: dict[str, Any]) -> dict[str, int]:
    usage = payload.get("usage") or {}
    return {
        "input_tokens": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
    }


def complete_typed_action(system: str, user: str) -> tuple[dict[str, Any], dict[str, int], str]:
    cfg = openai_compat_client_config()
    if cfg is None:
        raise InspectUnavailable("no openai-compat supervisor")
    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    json_system = (
        system
        + "\nReturn only JSON with keys action_type, rationale, evidence, message. No markdown."
    )
    timeout = httpx.Timeout(18.0, connect=6.0)
    models: list[str] = []
    for model in (cfg["model_id"], *_FALLBACK_MODELS):
        if model and model not in models:
            models.append(model)
    last_error = "no supervisor model"
    with httpx.Client(timeout=timeout) as client:
        for model in models[:2]:
            payload = {
                "model": model,
                "stream": False,
                "max_tokens": 400,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": json_system},
                    {"role": "user", "content": user},
                ],
            }
            try:
                response = client.post(url, headers=headers, json=payload, timeout=timeout)
            except httpx.TimeoutException:
                last_error = f"model {model} timed out"
                continue
            if _skip_model(response.status_code, response.text):
                last_error = f"model {model} unavailable"
                continue
            try:
                response.raise_for_status()
                data = response.json()
                parsed = parse_proposal_args(data)
            except (ValueError, json.JSONDecodeError, httpx.HTTPError) as exc:
                last_error = f"model {model} {exc.__class__.__name__}"
                continue
            action = str(parsed.get("action_type") or "NOOP")
            return parsed, usage_tokens(data), f"propose_typed_action:{action}"
    raise RuntimeError(last_error)
