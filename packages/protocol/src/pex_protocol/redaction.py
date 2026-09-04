from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}")),
    (
        "aws_secret",
        re.compile(r"(?i)aws(.{0,20})?(secret|access).{0,20}['\"][A-Za-z0-9/+=]{40}['\"]"),
    ),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*")),
    # Environment dumps and shell output commonly expose unquoted KEY=value
    # assignments.  Requiring quotes here silently leaked the most common form.
    (
        "credential_assignment",
        re.compile(
            r"(?i)\b(?:[a-z][a-z0-9]*[_-])*(?:api[_-]?key|authorization|credential|password|"
            r"private[_-]?key|client[_-]?secret|secret(?:[_-]?access[_-]?key)?|"
            r"session[_-]?token|access[_-]?token|refresh[_-]?token|token)\b\s*[:=]\s*"
            r"(?:['\"][^'\"\r\n]{8,}['\"]|[^\s,;}\]\r\n]{8,})"
        ),
    ),
    (
        "url_credentials",
        re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s/@:]+:[^\s/@]+@"),
    ),
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?P<label>(?:RSA |EC |OPENSSH )?PRIVATE KEY)-----.*?"
            r"-----END (?P=label)-----",
            re.DOTALL,
        ),
    ),
    ("github_pat", re.compile(r"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("gitlab_pat", re.compile(r"glpat-[A-Za-z0-9_-]{20,}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("huggingface_token", re.compile(r"hf_[A-Za-z0-9]{20,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}")),
    (
        "provider_api_key",
        re.compile(
            r"\b(?:sk-(?:proj-|ant-[A-Za-z0-9]+-)?|gsk_|xai-)"
            r"[A-Za-z0-9_-]{16,}\b"
        ),
    ),
    ("npm_token", re.compile(r"npm_[A-Za-z0-9]{20,}")),
    ("stripe_secret", re.compile(r"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}")),
    (
        "slack_webhook",
        re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]{20,}"),
    ),
]


def _sensitive_key(key: str) -> bool:
    """Recognize snake, kebab, and camel-case secrets without hiding token metrics."""

    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return normalized.endswith(
        (
            "apikey",
            "authorization",
            "credential",
            "credentials",
            "password",
            "privatekey",
            "clientsecret",
            "secretkey",
            "secretaccesskey",
            "accesstoken",
            "refreshtoken",
            "sessiontoken",
            "token",
        )
    ) or normalized == "secret"


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
    if key and _sensitive_key(key) and value not in (None, ""):
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
