from __future__ import annotations

import hashlib
import re
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pex_protocol.enums import HarnessType
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MCP_PRINCIPAL_SCOPE_KEY = "pex_mcp_principal"
MCP_READ_SCOPE = "mcp:read"
MCP_REPORT_PROGRESS_SCOPE = "pex.report_progress"
MCP_REQUEST_DECISION_SCOPE = "pex.request_decision"
MCP_HANDOFF_SCOPE = "pex.handoff"
MCP_VERIFY_CLAIM_SCOPE = "pex.verify_claim"

MCP_SESSION_SCOPES = frozenset(
    {
        MCP_READ_SCOPE,
        MCP_REPORT_PROGRESS_SCOPE,
        MCP_REQUEST_DECISION_SCOPE,
        MCP_HANDOFF_SCOPE,
        MCP_VERIFY_CLAIM_SCOPE,
    }
)
MCP_READ_ONLY_SCOPES = frozenset({MCP_READ_SCOPE})

_SESSION_TOKEN_PREFIX = "pex_mcp_"
_SESSION_TOKEN_PATTERN = re.compile(r"^pex_mcp_[A-Za-z0-9_-]{64}$")
_BoundedPrincipalId = Annotated[str, Field(min_length=1, max_length=512)]
_BoundedSessionId = Annotated[str, Field(min_length=1, max_length=512)]
_BoundedGoalId = Annotated[str, Field(min_length=1, max_length=512)]
_BoundedProjectId = Annotated[str, Field(min_length=1, max_length=4096)]
_BoundedVendorSessionId = Annotated[str, Field(min_length=1, max_length=512)]
_BoundedScope = Annotated[str, Field(min_length=1, max_length=128)]


class MCPPrincipal(BaseModel):
    """Authenticated MCP caller identity placed on the transport request.

    The model intentionally contains no bearer or token digest. A tool may use
    this immutable identity, but it must never be able to recover a credential
    from request state, logs, or an intervention receipt.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    principal_id: _BoundedPrincipalId
    kind: Literal["anonymous", "operator", "session"]
    scopes: frozenset[_BoundedScope] = Field(min_length=1, max_length=16)
    session_id: _BoundedSessionId | None = None
    goal_id: _BoundedGoalId | None = None
    project_id: _BoundedProjectId | None = None
    project_binding: str | None = None
    vendor_session_id: _BoundedVendorSessionId | None = None
    harness_type: HarnessType | None = None
    issued_at: datetime | None = None
    expires_at: datetime | None = None

    @field_validator("project_binding")
    @classmethod
    def require_canonical_project_binding(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from pex_bridge.store import validate_project_binding

        return validate_project_binding(value)

    @field_validator("issued_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("MCP principal timestamps must be timezone-aware")
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode="after")
    def require_kind_bindings(self) -> MCPPrincipal:
        bindings = (
            self.session_id,
            self.goal_id,
            self.project_id,
            self.project_binding,
            self.vendor_session_id,
            self.harness_type,
            self.issued_at,
            self.expires_at,
        )
        if self.kind == "session":
            if any(value is None for value in bindings):
                raise ValueError("session MCP principal is missing an identity binding")
            if self.issued_at is not None and self.expires_at is not None:
                if self.expires_at <= self.issued_at:
                    raise ValueError("session MCP principal expiry is invalid")
            if MCP_READ_SCOPE not in self.scopes:
                raise ValueError("session MCP principal is missing read scope")
            if not self.scopes.issubset(MCP_SESSION_SCOPES):
                raise ValueError("session MCP principal contains an unknown scope")
        elif any(value is not None for value in bindings):
            raise ValueError("non-session MCP principal cannot carry session bindings")
        elif self.scopes != MCP_READ_ONLY_SCOPES:
            raise ValueError("non-session MCP principal must be read-only")
        return self

    @classmethod
    def anonymous(cls) -> MCPPrincipal:
        return cls(
            principal_id="anonymous:local-mcp",
            kind="anonymous",
            scopes=MCP_READ_ONLY_SCOPES,
        )

    @classmethod
    def operator(cls) -> MCPPrincipal:
        return cls(
            principal_id="operator:bridge-token",
            kind="operator",
            scopes=MCP_READ_ONLY_SCOPES,
        )

    @classmethod
    def from_store_record(
        cls,
        record: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> MCPPrincipal:
        """Validate an active Store record without retaining its token digest."""

        from pex_bridge.store import validate_project_binding

        project_binding = validate_project_binding(record.get("project_binding"))
        principal = cls(
            principal_id=record.get("principal_id"),
            kind="session",
            scopes=frozenset(record.get("scopes") or ()),
            session_id=record.get("session_id"),
            goal_id=record.get("goal_id"),
            project_id=record.get("project_id"),
            project_binding=project_binding,
            vendor_session_id=record.get("vendor_session_id"),
            harness_type=record.get("harness_type"),
            issued_at=record.get("issued_at"),
            expires_at=record.get("expires_at"),
        )
        checked_at = now or datetime.now(UTC)
        if checked_at.tzinfo is None:
            raise ValueError("MCP principal validation time must be timezone-aware")
        checked_at = checked_at.astimezone(UTC)
        if principal.issued_at is None or principal.expires_at is None:
            raise ValueError("session MCP principal lifetime is missing")
        if not principal.issued_at <= checked_at < principal.expires_at:
            raise ValueError("session MCP principal is not active")
        if record.get("revoked_at") is not None:
            raise ValueError("session MCP principal is revoked")
        return principal

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def mint_mcp_session_token() -> str:
    """Mint a 384-bit opaque bearer suitable for one session principal."""

    token = _SESSION_TOKEN_PREFIX + secrets.token_urlsafe(48)
    if not _SESSION_TOKEN_PATTERN.fullmatch(token):  # pragma: no cover - stdlib invariant
        raise RuntimeError("generated MCP session token has an invalid shape")
    return token


def digest_mcp_session_token(token: str) -> str:
    """Return the stable digest stored by the bridge, never the raw bearer."""

    if not isinstance(token, str) or not _SESSION_TOKEN_PATTERN.fullmatch(token):
        raise ValueError("invalid MCP session token")
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def principal_from_scope(scope: Mapping[str, Any]) -> MCPPrincipal:
    """Extract only a middleware-authenticated principal, failing closed."""

    principal = scope.get(MCP_PRINCIPAL_SCOPE_KEY)
    if not isinstance(principal, MCPPrincipal):
        raise PermissionError("authenticated MCP principal is unavailable")
    return principal


def request_principal(context: object) -> MCPPrincipal:
    """Safely extract the principal from an injected FastMCP Context object."""

    request_context = getattr(context, "request_context", None)
    request = getattr(request_context, "request", None)
    scope = getattr(request, "scope", None)
    if not isinstance(scope, Mapping):
        raise PermissionError("authenticated MCP request context is unavailable")
    return principal_from_scope(scope)
