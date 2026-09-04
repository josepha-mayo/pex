from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from pex_protocol.enums import HarnessType

HOOK_TOKEN_PREFIX: Final = "pex_hook_"
HOOK_CREDENTIAL_TTL_SECONDS: Final = 28_800
MAX_HOOK_TOKEN_CHARS: Final = 512

CURSOR_HOOK_ROUTE: Final = "hook:cursor"
CLAUDE_HOOK_ROUTE: Final = "hook:claude_code"
QWEN_HOOK_ROUTE: Final = "hook:qwen"
HERMES_HOOK_ROUTE: Final = "hook:hermes"
OPENCODE_HEARTBEAT_ROUTE: Final = "opencode:heartbeat"
OPENCODE_OVERLAY_ROUTE: Final = "opencode:overlay-runtime"

HOOK_ROUTES_BY_HARNESS: Final[dict[HarnessType, frozenset[str]]] = {
    HarnessType.CURSOR: frozenset({CURSOR_HOOK_ROUTE}),
    HarnessType.CLAUDE_CODE: frozenset({CLAUDE_HOOK_ROUTE}),
    HarnessType.QWEN: frozenset({QWEN_HOOK_ROUTE}),
    HarnessType.HERMES: frozenset({HERMES_HOOK_ROUTE}),
    HarnessType.OPENCODE: frozenset(
        {OPENCODE_HEARTBEAT_ROUTE, OPENCODE_OVERLAY_ROUTE}
    ),
}

_TOKEN_PATTERN = re.compile(r"^pex_hook_[A-Za-z0-9_-]{64}$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def mint_hook_token() -> str:
    """Create a worker-visible bearer carrying only hook-ingest authority."""

    return f"{HOOK_TOKEN_PREFIX}{secrets.token_urlsafe(48)}"


def digest_hook_token(raw_token: object) -> str:
    token = str(raw_token or "")
    if (
        len(token) > MAX_HOOK_TOKEN_CHARS
        or _TOKEN_PATTERN.fullmatch(token) is None
    ):
        raise ValueError("invalid hook credential")
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def allowed_hook_routes(harness_type: HarnessType) -> frozenset[str]:
    return HOOK_ROUTES_BY_HARNESS.get(harness_type, frozenset())


def _aware_utc(value: object, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"hook credential {field} is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"hook credential {field} must be timezone-aware")
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class HookPrincipal:
    credential_id: str
    token_digest: str
    session_id: str | None
    vendor_session_id: str | None
    harness_type: HarnessType
    project_id: str
    project_binding: str
    allowed_routes: frozenset[str]
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        from pex_bridge.store import validate_project_binding

        object.__setattr__(
            self,
            "project_binding",
            validate_project_binding(self.project_binding),
        )

    @classmethod
    def from_store_record(
        cls,
        record: dict[str, Any],
        *,
        now: datetime,
    ) -> HookPrincipal:
        from pex_bridge.store import validate_project_binding

        if not isinstance(record, dict):
            raise ValueError("hook credential record is invalid")
        project_binding = validate_project_binding(record.get("project_binding"))
        if record.get("revoked_at") is not None:
            raise ValueError("hook credential is revoked")
        issued_at = _aware_utc(record.get("issued_at"), field="issued_at")
        expires_at = _aware_utc(record.get("expires_at"), field="expires_at")
        if now.tzinfo is None:
            raise ValueError("hook credential check time must be timezone-aware")
        checked_at = now.astimezone(UTC)
        if not issued_at <= checked_at < expires_at:
            raise ValueError("hook credential is not active")
        try:
            harness_type = HarnessType(str(record["harness_type"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("hook credential harness is invalid") from exc
        routes_value = record.get("allowed_routes")
        if not isinstance(routes_value, list) or not routes_value:
            raise ValueError("hook credential routes are invalid")
        routes = frozenset(str(route) for route in routes_value)
        allowed = allowed_hook_routes(harness_type)
        if len(routes) != len(routes_value) or not routes.issubset(allowed):
            raise ValueError("hook credential routes exceed harness authority")
        values: dict[str, str] = {}
        for field in ("credential_id", "project_id"):
            value = record.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 4096:
                raise ValueError(f"hook credential {field} is invalid")
            values[field] = value
        digest = record.get("token_digest")
        if not isinstance(digest, str) or _DIGEST_PATTERN.fullmatch(digest) is None:
            raise ValueError("hook credential digest is invalid")
        session_id = record.get("session_id")
        vendor_session_id = record.get("vendor_session_id")
        if (session_id is None) != (vendor_session_id is None):
            raise ValueError("hook credential has a partial session binding")
        for field, value in (
            ("session_id", session_id),
            ("vendor_session_id", vendor_session_id),
        ):
            if value is not None and (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > 4096
            ):
                raise ValueError(f"hook credential {field} is invalid")
        return cls(
            credential_id=values["credential_id"],
            token_digest=digest,
            session_id=session_id,
            vendor_session_id=vendor_session_id,
            harness_type=harness_type,
            project_id=values["project_id"],
            project_binding=project_binding,
            allowed_routes=routes,
            issued_at=issued_at,
            expires_at=expires_at,
        )

    def authorizes(self, route: str) -> bool:
        return route in self.allowed_routes

    @property
    def is_bound(self) -> bool:
        return self.session_id is not None and self.vendor_session_id is not None
