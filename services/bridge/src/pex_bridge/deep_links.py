"""Allowlisted cloud session URLs for Open agent (build spec §6.5).

Local windows still use adapter focus. Cloud harnesses may expose a deep link
to the existing session. This module never invents a host and never opens
http, javascript, or credentialed URLs.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

MAX_URL_CHARS = 2_048
_DEVIN_HOST = "app.devin.ai"
_SESSION_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_RESERVED_SESSION_IDS = {"new", "create", ".", ".."}


def safe_external_url(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw or len(raw) > MAX_URL_CHARS:
        return None
    parsed = urlparse(raw)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return None
    if parsed.query or parsed.fragment or parsed.params:
        return None
    host = (parsed.hostname or "").casefold()
    if host != _DEVIN_HOST:
        return None
    path = parsed.path or ""
    prefix = "/sessions/"
    if not path.startswith(prefix):
        return None
    session_id = path[len(prefix) :].rstrip("/")
    if (
        "/" in session_id
        or session_id in _RESERVED_SESSION_IDS
        or session_id.startswith(".")
        or not _SESSION_ID.fullmatch(session_id)
    ):
        return None
    return f"https://{_DEVIN_HOST}/sessions/{session_id}"


def devin_session_url(*, vendor_id: str, provided: str | None = None) -> str | None:
    cleaned = safe_external_url(provided)
    if cleaned:
        return cleaned
    if not _SESSION_ID.fullmatch(vendor_id) or vendor_id in _RESERVED_SESSION_IDS:
        return None
    return safe_external_url(f"https://{_DEVIN_HOST}/sessions/{vendor_id}")
