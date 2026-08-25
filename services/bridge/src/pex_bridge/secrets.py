from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "aws_secret",
        re.compile(r"(?i)aws(.{0,20})?(secret|access).{0,20}['\"][A-Za-z0-9/+=]{40}['\"]"),
    ),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*")),
    (
        "generic_key",
        re.compile(r"(?i)(api[_-]?key|secret|token)['\"]?\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
    ),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("github_pat", re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("openai", re.compile(r"sk-[A-Za-z0-9]{20,}")),
]
_SECRET_KEY = re.compile(
    r"(?i)(?:^|[_-])(api[_-]?key|authorization|credential|password|private[_-]?key|secret|token)(?:$|[_-])"
)


def redact_text(text: str | None) -> tuple[str | None, list[str]]:
    if not text:
        return text, []
    found: list[str] = []
    redacted = text
    for name, pattern in _SECRET_PATTERNS:
        if pattern.search(redacted):
            found.append(name)
            redacted = pattern.sub(f"[REDACTED:{name}]", redacted)
    return redacted, found


def _redact_value(value: Any, key: str | None = None) -> tuple[Any, list[str]]:
    if key and _SECRET_KEY.search(key) and value not in (None, ""):
        return f"[REDACTED:{key}]", [f"key:{key}"]
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return redact_mapping(value)
    if isinstance(value, list):
        cleaned: list[Any] = []
        found: list[str] = []
        for item in value:
            redacted, hits = _redact_value(item)
            cleaned.append(redacted)
            found.extend(hits)
        return cleaned, found
    if isinstance(value, tuple):
        cleaned, found = _redact_value(list(value))
        return tuple(cleaned), found
    return value, []


def redact_mapping(data: dict | None) -> tuple[dict | None, list[str]]:
    if not data:
        return data, []
    found: list[str] = []
    out: dict = {}
    for key, value in data.items():
        cleaned, hits = _redact_value(value, str(key))
        out[key] = cleaned
        found.extend(hits)
    return out, found
