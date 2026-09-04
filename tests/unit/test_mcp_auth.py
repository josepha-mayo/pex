from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pex_bridge.mcp_auth import (
    MCP_PRINCIPAL_SCOPE_KEY,
    MCP_READ_ONLY_SCOPES,
    MCP_SESSION_SCOPES,
    MCPPrincipal,
    digest_mcp_session_token,
    mint_mcp_session_token,
    principal_from_scope,
    request_principal,
)
from pex_protocol.enums import HarnessType
from pydantic import ValidationError


def _session_record(**changes):
    now = datetime.now(UTC)
    record = {
        "principal_id": "mcp_principal_test",
        "session_id": "synthetic:test",
        "goal_id": "goal_test",
        "project_id": "C:/work/project",
        "project_binding": "legacy:" + "0" * 64,
        "vendor_session_id": "vendor-test",
        "harness_type": HarnessType.SYNTHETIC.value,
        "scopes": sorted(MCP_SESSION_SCOPES),
        "issued_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "revoked_at": None,
        "token_digest": "0" * 64,
    }
    record.update(changes)
    return record, now


def test_session_tokens_are_opaque_high_entropy_and_digest_stable():
    first = mint_mcp_session_token()
    second = mint_mcp_session_token()

    assert first.startswith("pex_mcp_")
    assert len(first) == 72
    assert first != second
    assert digest_mcp_session_token(first) == digest_mcp_session_token(first)
    assert digest_mcp_session_token(first) != digest_mcp_session_token(second)
    assert first not in digest_mcp_session_token(first)

    for malformed in ("", "pex_mcp_short", "pex_mcp_" + "a" * 63, "x" * 72):
        with pytest.raises(ValueError, match="invalid MCP session token"):
            digest_mcp_session_token(malformed)


def test_principal_model_is_frozen_bounded_and_never_keeps_digest():
    record, now = _session_record()
    principal = MCPPrincipal.from_store_record(record, now=now)

    assert principal.kind == "session"
    assert principal.session_id == record["session_id"]
    assert principal.harness_type == HarnessType.SYNTHETIC
    assert principal.project_binding == record["project_binding"]
    assert principal.scopes == MCP_SESSION_SCOPES
    assert "token_digest" not in principal.model_dump()
    with pytest.raises(ValidationError, match="frozen"):
        principal.session_id = "synthetic:other"

    with pytest.raises(ValidationError):
        MCPPrincipal(
            principal_id="x" * 513,
            kind="operator",
            scopes=MCP_READ_ONLY_SCOPES,
        )
    with pytest.raises(ValidationError, match="unknown scope"):
        changed = dict(record)
        changed["scopes"] = ["mcp:read", "mcp:admin"]
        MCPPrincipal.from_store_record(changed, now=now)
    with pytest.raises(ValueError, match="project binding is invalid"):
        MCPPrincipal.from_store_record(
            {**record, "project_binding": "identity:contains spaces"},
            now=now,
        )


def test_store_principal_lifetime_and_revocation_fail_closed():
    record, now = _session_record()

    with pytest.raises(ValueError, match="not active"):
        MCPPrincipal.from_store_record(
            {**record, "expires_at": (now - timedelta(seconds=1)).isoformat()},
            now=now,
        )
    with pytest.raises(ValueError, match="revoked"):
        MCPPrincipal.from_store_record(
            {**record, "revoked_at": now.isoformat()},
            now=now,
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        MCPPrincipal.from_store_record(
            {**record, "issued_at": datetime.now().isoformat()},
            now=now,
        )


def test_request_principal_accepts_only_middleware_model_in_request_scope():
    principal = MCPPrincipal.operator()
    scope = {MCP_PRINCIPAL_SCOPE_KEY: principal}
    context = SimpleNamespace(
        request_context=SimpleNamespace(request=SimpleNamespace(scope=scope))
    )

    assert principal_from_scope(scope) is principal
    assert request_principal(context) is principal

    with pytest.raises(PermissionError, match="principal is unavailable"):
        principal_from_scope({MCP_PRINCIPAL_SCOPE_KEY: {"kind": "operator"}})
    with pytest.raises(PermissionError, match="request context is unavailable"):
        request_principal(SimpleNamespace(request_context=None))
