from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.app import MCPTokenMiddleware, state
from pex_bridge.config import Settings
from pex_bridge.mcp_auth import (
    MCP_PRINCIPAL_SCOPE_KEY,
    MCP_SESSION_SCOPES,
    digest_mcp_session_token,
    mint_mcp_session_token,
)
from pex_bridge.store import Store
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.project_identity import (
    PathPlatform,
    PhysicalIdentityProof,
    ProjectLocator,
    ProjectOrigin,
)
from pex_protocol.session import HarnessSession
from starlette.responses import Response


@pytest.fixture
async def mcp_auth_state(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    state.settings = Settings(require_auth=True, home=tmp_path)
    state.store = store
    state.token = "operator-bridge-token-that-is-long-enough"
    now = datetime.now(UTC)
    proof = PhysicalIdentityProof(
        provider="windows-file-id",
        volume_id="mcp-auth-volume",
        object_id="mcp-auth-object",
    )
    origin = ProjectOrigin(namespace="machine", host="mcp-auth-test")
    await store.register_project_locator(
        legacy_project_id="C:/work/demo",
        locator=ProjectLocator.path(
            "C:/work/demo",
            platform=PathPlatform.WINDOWS,
            origin=origin,
            physical=proof,
        ),
    )
    await store.register_project_locator(
        legacy_project_id="C:\\work\\demo",
        locator=ProjectLocator.path(
            "C:\\work\\demo",
            platform=PathPlatform.WINDOWS,
            origin=origin,
            physical=proof,
        ),
    )
    goal = Goal(
        id="goal-auth",
        project_id="C:/work/demo",
        title="Bound MCP caller",
        objective="Bind every MCP caller to its exact worker session",
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    session = HarnessSession(
        id="synthetic:auth",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="auth",
        project_id="C:\\work\\demo",
        cwd="C:\\work\\demo",
        goal_id=goal.id,
        status=SessionStatus.WORKING,
    )
    await store.upsert_session(session, allow_goal_change=True)
    try:
        yield store, session, goal
    finally:
        await store.close()


async def _issue(store: Store, session: HarnessSession, goal: Goal) -> tuple[str, dict]:
    token = mint_mcp_session_token()
    issued_at = datetime.now(UTC)
    record = await store.issue_mcp_principal(
        principal_id="mcp_principal_auth",
        session_id=session.id,
        goal_id=goal.id,
        project_id=session.project_id or goal.project_id,
        vendor_session_id=session.vendor_session_id,
        harness_type=session.harness_type.value,
        scopes=sorted(MCP_SESSION_SCOPES),
        token_digest=digest_mcp_session_token(token),
        issued_at=issued_at,
        expires_at=issued_at + timedelta(hours=1),
    )
    return token, record


def _principal_echo_app(seen: list):
    async def echo(scope, receive, send):
        principal = scope[MCP_PRINCIPAL_SCOPE_KEY]
        seen.append(principal)
        response = Response(
            json.dumps(principal.model_dump(mode="json")),
            media_type="application/json",
        )
        await response(scope, receive, send)

    return echo


@pytest.mark.asyncio
async def test_middleware_distinguishes_read_only_operator_and_bound_session_principal(
    mcp_auth_state,
):
    store, session, goal = mcp_auth_state
    session_token, _ = await _issue(store, session, goal)
    seen = []
    app = MCPTokenMiddleware(_principal_echo_app(seen))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1",
    ) as client:
        operator = await client.get(
            "/",
            headers={"Authorization": f"Bearer {state.token}"},
        )
        worker = await client.get(
            "/",
            headers={"Authorization": f"Bearer {session_token}"},
        )

    assert operator.status_code == 200
    assert operator.json()["kind"] == "operator"
    assert operator.json()["scopes"] == ["mcp:read"]
    assert worker.status_code == 200
    assert worker.json()["kind"] == "session"
    assert worker.json()["session_id"] == session.id
    assert worker.json()["goal_id"] == goal.id
    assert set(worker.json()["scopes"]) == MCP_SESSION_SCOPES
    assert len(seen) == 2
    assert all("token" not in principal.model_dump() for principal in seen)


@pytest.mark.asyncio
async def test_middleware_no_auth_mode_is_always_anonymous_read_only(mcp_auth_state):
    store, session, goal = mcp_auth_state
    session_token, _ = await _issue(store, session, goal)
    state.settings = Settings.for_test(require_auth=False, home=store.path.parent)
    seen = []
    app = MCPTokenMiddleware(_principal_echo_app(seen))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1",
    ) as client:
        response = await client.get(
            "/",
            headers={"Authorization": f"Bearer {session_token}"},
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "anonymous"
    assert response.json()["scopes"] == ["mcp:read"]
    assert response.json()["session_id"] is None


@pytest.mark.asyncio
async def test_middleware_rejects_revoked_and_live_binding_mismatched_credentials(
    mcp_auth_state,
):
    store, session, goal = mcp_auth_state
    first_token, _ = await _issue(store, session, goal)
    await store.revoke_mcp_principals_for_session(
        session.id,
        revoked_at=datetime.now(UTC),
    )
    seen = []
    app = MCPTokenMiddleware(_principal_echo_app(seen))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1",
    ) as client:
        revoked = await client.get(
            "/",
            headers={"Authorization": f"Bearer {first_token}"},
        )

        second_token = mint_mcp_session_token()
        issued_at = datetime.now(UTC)
        await store.issue_mcp_principal(
            principal_id="mcp_principal_goal_change",
            session_id=session.id,
            goal_id=goal.id,
            project_id=session.project_id or goal.project_id,
            vendor_session_id=session.vendor_session_id,
            harness_type=session.harness_type.value,
            scopes=sorted(MCP_SESSION_SCOPES),
            token_digest=digest_mcp_session_token(second_token),
            issued_at=issued_at,
            expires_at=issued_at + timedelta(hours=1),
        )
        replacement = goal.model_copy(
            update={
                "id": "goal-auth-replacement",
                "created_at": issued_at,
                "updated_at": issued_at,
                "supersedes": None,
            }
        )
        await store.upsert_goal(replacement)
        session.goal_id = replacement.id
        await store.upsert_session(session, allow_goal_change=True)
        stale_binding = await client.get(
            "/",
            headers={"Authorization": f"Bearer {second_token}"},
        )

    assert revoked.status_code == 401
    assert stale_binding.status_code == 401
    assert seen == []


@pytest.mark.asyncio
async def test_middleware_rejects_missing_and_malformed_credentials(mcp_auth_state):
    seen = []
    app = MCPTokenMiddleware(_principal_echo_app(seen))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1",
    ) as client:
        missing = await client.get("/")
        malformed = await client.get(
            "/",
            headers={"Authorization": "Bearer pex_mcp_short"},
        )

    assert missing.status_code == 401
    assert malformed.status_code == 401
    assert seen == []
