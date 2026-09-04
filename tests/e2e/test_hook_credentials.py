from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.hook_auth import (
    QWEN_HOOK_ROUTE,
    digest_hook_token,
    mint_hook_token,
)
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store, new_id, utcnow
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.session import HarnessSession

OPERATOR_TOKEN = "hook-test-operator-token-that-is-at-least-32"


async def _make_app(tmp_path):
    settings = Settings(require_auth=True, home=tmp_path, codex_attach=False)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = OPERATOR_TOKEN
    await store.connect()
    return create_app(), store


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _bootstrap(
    client: AsyncClient,
    *,
    harness: str,
    project: str,
) -> dict:
    response = await client.post(
        "/v1/hook-credentials/bootstrap",
        json={"harness_type": harness, "project_id": project},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    return response.json()


@pytest.mark.asyncio
async def test_bootstrap_binds_first_cursor_session_and_rejects_session_and_project_spoof(
    tmp_path,
):
    app, store = await _make_app(tmp_path)
    state.pipeline.ingest_event = AsyncMock(return_value=None)
    project = "C:\\work\\project-a"
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=_headers(OPERATOR_TOKEN),
        ) as operator:
            receipt = await _bootstrap(operator, harness="cursor", project=project)
        token = receipt["token"]
        rows = await store.db.execute_fetchall("SELECT json FROM hook_credentials")
        assert rows and all(token not in str(row["json"]) for row in rows)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=_headers(token),
        ) as hook:
            accepted = await hook.post(
                "/v1/hooks/cursor",
                json={
                    "conversation_id": "conversation-one",
                    "cwd": project,
                    "hook_event_name": "afterAgentThought",
                    "text": "working",
                },
            )
            assert accepted.status_code == 200, accepted.text

            record = await store.get_hook_credential_by_digest(
                digest_hook_token(token)
            )
            assert record is not None
            assert record["session_id"] == "cursor:conversation-one"
            assert record["vendor_session_id"] == "conversation-one"

            wrong_session = await hook.post(
                "/v1/hooks/cursor",
                json={
                    "conversation_id": "conversation-two",
                    "cwd": project,
                    "hook_event_name": "afterAgentThought",
                },
            )
            assert wrong_session.status_code == 403

            wrong_project = await hook.post(
                "/v1/hooks/cursor",
                json={
                    "conversation_id": "conversation-one",
                    "cwd": "C:\\work\\project-b",
                    "hook_event_name": "afterAgentThought",
                },
            )
            assert wrong_project.status_code == 403

        assert await store.get_session("cursor:conversation-two") is None
        assert "cursor:conversation-two" not in state.adapters.cursor.sessions
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("harness", "vendor_id", "hook_name"),
    [
        ("claude_code", "claude-one", "UserPromptSubmit"),
        ("qwen", "qwen-one", "UserPromptSubmit"),
        ("hermes", "hermes-one", "post_llm_call"),
    ],
)
async def test_each_named_worker_bootstrap_authenticates_its_first_hook(
    tmp_path,
    harness,
    vendor_id,
    hook_name,
):
    app, store = await _make_app(tmp_path)
    state.pipeline.ingest_event = AsyncMock(return_value=None)
    project = f"C:\\work\\{harness}"
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=_headers(OPERATOR_TOKEN),
        ) as operator:
            receipt = await _bootstrap(
                operator,
                harness=harness,
                project=project,
            )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=_headers(receipt["token"]),
        ) as worker:
            accepted = await worker.post(
                f"/v1/hooks/{harness}",
                json={
                    "session_id": vendor_id,
                    "cwd": project,
                    "hook_event_name": hook_name,
                    "text": "working",
                },
            )
            assert accepted.status_code == 200, accepted.text
        record = await store.get_hook_credential_by_digest(
            digest_hook_token(receipt["token"])
        )
        assert record is not None
        assert record["session_id"] == f"{harness}:{vendor_id}"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_hook_token_cannot_escalate_to_operator_rest_mcp_or_another_harness(
    tmp_path,
):
    app, store = await _make_app(tmp_path)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=_headers(OPERATOR_TOKEN),
        ) as operator:
            receipt = await _bootstrap(
                operator,
                harness="cursor",
                project="C:\\work\\project-a",
            )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=_headers(receipt["token"]),
        ) as worker:
            assert (await worker.get("/v1/goals")).status_code == 401
            assert (
                await worker.post("/v1/hook-credentials/bootstrap", json={})
            ).status_code == 401
            assert (await worker.post("/mcp/", content=b"{}")).status_code == 401
            decision = await worker.post(
                "/v1/decisions/nonexistent-decision/resolve",
                json={"decision": "iterate"},
            )
            assert decision.status_code == 401
            cross_harness = await worker.post(
                "/v1/hooks/qwen",
                json={
                    "session_id": "worker-one",
                    "cwd": "C:\\work\\project-a",
                    "hook_event_name": "Stop",
                },
            )
            assert cross_harness.status_code == 403
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_hook_credential_expiry_revocation_rotation_and_terminal_issue_gate(tmp_path):
    app, store = await _make_app(tmp_path)
    project = "C:\\work\\project-a"
    live = HarnessSession(
        id="cursor:live",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="live",
        project_id=project,
        cwd=project,
        status=SessionStatus.WORKING,
        last_activity=utcnow(),
    )
    expired_session = HarnessSession(
        id="qwen:expired",
        harness_type=HarnessType.QWEN,
        vendor_session_id="expired",
        project_id=project,
        cwd=project,
        status=SessionStatus.WORKING,
        last_activity=utcnow(),
    )
    terminal = HarnessSession(
        id="cursor:terminal",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="terminal",
        project_id=project,
        cwd=project,
        status=SessionStatus.STOPPED,
        last_activity=utcnow(),
    )
    await store.upsert_session(live)
    await store.upsert_session(expired_session)
    await store.upsert_session(terminal)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=_headers(OPERATOR_TOKEN),
        ) as operator:
            issued = await operator.post("/v1/sessions/cursor%3Alive/hook-credential")
            assert issued.status_code == 200, issued.text
            body = issued.json()
            revoked = await operator.delete(
                f"/v1/hook-credentials/{body['credential_id']}"
            )
            assert revoked.status_code == 200
            terminal_issue = await operator.post(
                "/v1/sessions/cursor%3Aterminal/hook-credential"
            )
            assert terminal_issue.status_code == 409

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=_headers(body["token"]),
        ) as revoked_worker:
            assert (
                await revoked_worker.post(
                    "/v1/hooks/cursor",
                    json={
                        "conversation_id": "live",
                        "cwd": project,
                        "hook_event_name": "afterAgentThought",
                    },
                )
            ).status_code == 401

        expired_token = mint_hook_token()
        now = utcnow()
        await store.issue_hook_credential(
            credential_id=new_id("hook_credential_"),
            session_id=expired_session.id,
            project_id=project,
            vendor_session_id=expired_session.vendor_session_id,
            harness_type=HarnessType.QWEN.value,
            allowed_routes=[QWEN_HOOK_ROUTE],
            token_digest=digest_hook_token(expired_token),
            issued_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
        assert (
            await store.get_hook_credential_by_digest(
                digest_hook_token(expired_token),
                now=now,
            )
            is None
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=_headers(expired_token),
        ) as expired_worker:
            assert (
                await expired_worker.post(
                    "/v1/hooks/qwen",
                    json={
                        "session_id": "expired",
                        "cwd": project,
                        "hook_event_name": "Stop",
                    },
                )
            ).status_code == 401

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=_headers(OPERATOR_TOKEN),
        ) as operator:
            first = await _bootstrap(operator, harness="hermes", project=project)
            second = await _bootstrap(operator, harness="hermes", project=project)
        assert first["token"] != second["token"]
        assert (
            await store.get_hook_credential_by_digest(
                digest_hook_token(first["token"])
            )
            is None
        )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_opencode_bootstrap_binds_on_first_session_runtime_request(tmp_path):
    app, store = await _make_app(tmp_path)
    project = "C:\\work\\opencode"
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=_headers(OPERATOR_TOKEN),
        ) as operator:
            receipt = await _bootstrap(operator, harness="opencode", project=project)
        token = receipt["token"]
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=_headers(token),
        ) as plugin:
            heartbeat = await plugin.post(
                "/v1/adapters/opencode/plugin-heartbeat",
                json={
                    "source": "pex-opencode-plugin",
                    "version": "1.0.0",
                    "directory": project,
                },
            )
            assert heartbeat.status_code == 200
            before = await store.get_hook_credential_by_digest(digest_hook_token(token))
            assert before is not None and before["session_id"] is None

            assert (
                await plugin.get(
                    "/v1/sessions/opencode%3Asession-one/overlay-runtime"
                )
            ).status_code == 403
            bound_heartbeat = await plugin.post(
                "/v1/adapters/opencode/plugin-heartbeat",
                json={
                    "source": "pex-opencode-plugin",
                    "version": "1.0.0",
                    "directory": project,
                    "session_id": "session-one",
                },
            )
            assert bound_heartbeat.status_code == 200, bound_heartbeat.text

            runtime = await plugin.get(
                "/v1/sessions/opencode%3Asession-one/overlay-runtime"
            )
            assert runtime.status_code == 200, runtime.text
            after = await store.get_hook_credential_by_digest(digest_hook_token(token))
            assert after is not None
            assert after["session_id"] == "opencode:session-one"
            assert (
                await plugin.post(
                    "/v1/adapters/opencode/plugin-heartbeat",
                    json={
                        "source": "pex-opencode-plugin",
                        "directory": project,
                        "session_id": "session-two",
                    },
                )
            ).status_code == 403
            assert (
                await plugin.get(
                    "/v1/sessions/opencode%3Asession-two/overlay-runtime"
                )
            ).status_code == 403
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_untrusted_origin_is_rejected_before_mutation(tmp_path):
    app, store = await _make_app(tmp_path)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=_headers(OPERATOR_TOKEN),
        ) as operator:
            denied = await operator.post(
                "/v1/hook-credentials/bootstrap",
                headers={"Origin": "https://evil.example"},
                json={"harness_type": "cursor", "project_id": "C:\\work\\a"},
            )
            assert denied.status_code == 403
            count = await store.db.execute_fetchall(
                "SELECT COUNT(*) AS count FROM hook_credentials"
            )
            assert int(count[0]["count"]) == 0

            trusted = await operator.post(
                "/v1/hook-credentials/bootstrap",
                headers={"Origin": "https://tauri.localhost"},
                json={"harness_type": "cursor", "project_id": "C:\\work\\a"},
            )
            assert trusted.status_code == 200, trusted.text
    finally:
        await store.close()
