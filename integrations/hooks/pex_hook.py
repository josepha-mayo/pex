from __future__ import annotations

import argparse
import http.client
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BRIDGE = os.environ.get("PEX_BRIDGE_URL", "http://127.0.0.1:7420")
HARNESS = os.environ.get("PEX_HARNESS", "claude_code")
ALLOWED_HARNESSES = {"claude_code", "qwen"}
MAX_PAYLOAD_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 65_536
MAX_TOKEN_CHARS = 512
STANDARD_CLIENT_TIMEOUT_SECONDS = 7.0
STOP_CLIENT_TIMEOUT_SECONDS = 42.0


def _strict_json_loads(value: str | bytes) -> object:
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result

    def finite(raw: str) -> float:
        parsed = float(raw)
        if not math.isfinite(parsed):
            raise ValueError("non-finite JSON number")
        return parsed

    return json.loads(
        value,
        object_pairs_hook=unique,
        parse_constant=lambda _raw: (_ for _ in ()).throw(ValueError("non-finite JSON")),
        parse_float=finite,
    )


def _token() -> str:
    def validated(value: str) -> str:
        cleaned = value.strip()
        if (
            not cleaned
            or len(cleaned) > MAX_TOKEN_CHARS
            or any(ord(char) < 0x21 or ord(char) > 0x7E for char in cleaned)
        ):
            return ""
        return cleaned

    return validated(os.environ.get("PEX_HOOK_TOKEN") or "")


def _endpoint() -> str | None:
    try:
        parsed = urllib.parse.urlparse(BRIDGE)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme != "http" or hostname not in {"127.0.0.1", "localhost", "::1"}:
        return None
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        return None
    if HARNESS not in ALLOWED_HARNESSES:
        return None
    normalized_host = "127.0.0.1" if hostname == "localhost" else hostname
    authority = f"[{normalized_host}]" if normalized_host == "::1" else normalized_host
    if port is not None:
        authority += f":{port}"
    return f"http://{authority}/v1/hooks/{HARNESS}"


def _safe_response(raw: bytes) -> dict:
    if len(raw) > MAX_RESPONSE_BYTES:
        return {}
    try:
        value = _strict_json_loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return {}
    if not isinstance(value, dict):
        return {}
    allowed = {
        "continue",
        "stopReason",
        "suppressOutput",
        "systemMessage",
        "decision",
        "reason",
        "hookSpecificOutput",
    }
    return {key: _bounded_output(value[key]) for key in allowed if key in value}


def _bounded_output(value, depth: int = 0):
    if depth > 5:
        return None
    if isinstance(value, str):
        return value[:4_096]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list):
        return [_bounded_output(item, depth + 1) for item in value[:64]]
    if isinstance(value, dict):
        result = {}
        for key, item in list(value.items())[:64]:
            if not isinstance(key, str) or len(key) > 128:
                continue
            result[key] = _bounded_output(item, depth + 1)
        return result
    return None


def _client_timeout(payload: dict) -> float:
    hook_name = str(payload.get("hook_event_name") or "")
    return (
        STOP_CLIENT_TIMEOUT_SECONDS
        if hook_name in {"Stop", "stop"}
        else STANDARD_CLIENT_TIMEOUT_SECONDS
    )


def _selected_harness() -> str:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--harness", choices=sorted(ALLOWED_HARNESSES))
    args = parser.parse_args()
    return str(args.harness or os.environ.get("PEX_HARNESS", "claude_code"))


def main() -> None:
    global HARNESS
    HARNESS = _selected_harness()
    raw_bytes = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES + 1)
    endpoint = _endpoint()
    if len(raw_bytes) > MAX_PAYLOAD_BYTES or endpoint is None:
        sys.stdout.write("{}")
        return
    try:
        raw = raw_bytes.decode("utf-8")
        payload = _strict_json_loads(raw or "{}")
    except (UnicodeDecodeError, ValueError, RecursionError):
        sys.stdout.write("{}")
        return
    if not isinstance(payload, dict):
        sys.stdout.write("{}")
        return
    if "hook_event_name" not in payload:
        payload["hook_event_name"] = payload.get("hook") or payload.get("type") or "unknown"
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        sys.stdout.write("{}")
        return
    if len(encoded) > MAX_PAYLOAD_BYTES:
        sys.stdout.write("{}")
        return
    token = _token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        endpoint,
        data=encoded,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_client_timeout(payload)) as resp:
            body = _safe_response(resp.read(MAX_RESPONSE_BYTES + 1))
            sys.stdout.write(json.dumps(body, allow_nan=False, separators=(",", ":")))
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError):
        sys.stdout.write("{}")


if __name__ == "__main__":
    main()
