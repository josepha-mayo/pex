from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import _authorize_hook_route, create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.hook_auth import (
    OPENCODE_OVERLAY_ROUTE,
    HookPrincipal,
    digest_hook_token,
    mint_hook_token,
)
from pex_bridge.mcp_server import build_mcp_server
from pex_bridge.pets import PetSettings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.project_identity import (
    PathPlatform,
    PhysicalIdentityProof,
    ProjectLocator,
    ProjectOrigin,
)
from pex_protocol.session import HarnessEvent, HarnessSession

_ORIGIN = ProjectOrigin(namespace="machine", host="authority-consumer-test")


async def _app(tmp_path):
    settings = Settings(require_auth=True, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = "authority-consumer-operator-token"
    state.pet_settings = PetSettings()
    state.pet_path = tmp_path / "pet.json"
    await store.connect()
    return create_app(), store


def _structured(result) -> dict:
    assert result.isError is False
    payload = result.structuredContent
    if payload is None:
        texts = [
            block.text
            for block in (result.content or [])
            if getattr(block, "text", None)
        ]
        assert texts
        payload = json.loads(texts[0])
    if isinstance(payload, dict) and set(payload) == {"result"}:
        payload = payload["result"]
    assert isinstance(payload, dict)
    return payload


@pytest.mark.asyncio
async def test_action_and_ask_consumers_reject_forensic_goal_after_typing(tmp_path):
    app, store = await _app(tmp_path)
    headers = {"Authorization": f"Bearer {state.token}"}
    state.pipeline.refresh_desktop_sessions = AsyncMock()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=headers,
        ) as client:
            created = await client.post(
                "/v1/goals",
                json={
                    "idempotency_key": "authority-consumer-goal-create-0001",
                    "project_id": "demo",
                    "title": "Identity-bound goal",
                    "objective": "Never reuse evidence across project identities.",
                },
            )
            assert created.status_code == 200
            goal_id = created.json()["id"]

            session = await client.post("/v1/synthetic/sessions")
            assert session.status_code == 200
            session_id = session.json()["id"]
            attached = await client.post(
                f"/v1/sessions/{session_id}/attach",
                json={
                    "idempotency_key": "authority-consumer-goal-attach-0001",
                    "goal_id": goal_id,
                    "expected_goal_id": None,
                    "expected_control_revision": 0,
                    "expected_goal_intent_revision": created.json()["intent_revision"],
                },
            )
            assert attached.status_code == 200

            await store.register_project_locator(
                legacy_project_id="demo",
                locator=ProjectLocator.path(
                    "/workspace/typed-demo",
                    platform=PathPlatform.POSIX,
                    origin=_ORIGIN,
                ),
            )

            history = await client.get(f"/v1/goals/{goal_id}")
            history_decisions = await client.get(f"/v1/goals/{goal_id}/decisions")
            assert history.status_code == 200
            assert history_decisions.status_code == 200

            for response in (
                await client.patch(
                    f"/v1/goals/{goal_id}",
                    json={
                        "idempotency_key": "authority-consumer-goal-update-0001",
                        "objective": "This stale goal must not be changed.",
                        "expected_intent_revision": created.json()["intent_revision"],
                    },
                ),
                await client.post(
                    f"/v1/sessions/{session_id}/mcp-credential",
                ),
                await client.post(
                    "/v1/ask",
                    json={"question": "What evidence should the worker use?"},
                ),
            ):
                assert response.status_code == 409
                assert response.json()["detail"]["code"] == ("artifact_project_identity_changed")
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_pipeline_missing_goal_fails_before_accepting_event_or_session(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    bus = EventBus()
    pipeline = Pipeline(
        store,
        adapters,
        bus,
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    session = adapters.synthetic.seed_session(
        vendor_id="missing-goal",
        project_id="demo",
        goal_id="goal-does-not-exist",
    )
    event = HarnessEvent(
        event_id="event-missing-goal",
        ts=session.last_activity,
        harness_type=session.harness_type,
        session_id=session.id,
        goal_id=session.goal_id,
        project_id=session.project_id,
        event_type=EventType.AGENT_RESPONSE,
        phase=EventPhase.AFTER,
        message_delta="Do not persist this event.",
    )
    try:
        with pytest.raises(ValueError, match="session goal not found"):
            await pipeline._prepare_event_acceptance(event, session)

        assert await store.get_event(event.event_id) is None
        assert await store.get_session(session.id) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_typed_aliases_work_for_mcp_and_bound_hook_authorization(tmp_path):
    app, store = await _app(tmp_path)
    headers = {"Authorization": f"Bearer {state.token}"}
    proof = PhysicalIdentityProof(
        provider="posix-stat",
        volume_id="authority-alias-volume",
        object_id="authority-alias-object",
    )
    alias_a = "/workspace/authority-alias-a"
    alias_b = "/workspace/authority-alias-b"
    try:
        first = await store.register_project_locator(
            legacy_project_id=alias_a,
            locator=ProjectLocator.path(
                alias_a,
                platform=PathPlatform.POSIX,
                origin=_ORIGIN,
                physical=proof,
            ),
        )
        second = await store.register_project_locator(
            legacy_project_id=alias_b,
            locator=ProjectLocator.path(
                alias_b,
                platform=PathPlatform.POSIX,
                origin=_ORIGIN,
                physical=proof,
            ),
        )
        assert second["identity"].id == first["identity"].id

        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers=headers,
            ) as operator:
                created = await operator.post(
                    "/v1/goals",
                    json={
                        "idempotency_key": "authority-alias-goal-create-0001",
                        "project_id": alias_a,
                        "title": "Alias-bound goal",
                        "objective": "Treat typed aliases as one physical project.",
                    },
                )
                assert created.status_code == 200
                goal_id = created.json()["id"]
                session = state.adapters.synthetic.seed_session(
                    vendor_id="typed-alias",
                    project_id=alias_b,
                )
                await store.upsert_session(session)
                attached = await operator.post(
                    f"/v1/sessions/{session.id}/attach",
                    json={
                        "idempotency_key": "authority-alias-goal-attach-0001",
                        "goal_id": goal_id,
                        "expected_goal_id": None,
                        "expected_control_revision": 0,
                        "expected_goal_intent_revision": created.json()["intent_revision"],
                    },
                )
                assert attached.status_code == 200
                credential = await operator.post(
                    f"/v1/sessions/{session.id}/mcp-credential"
                )
                assert credential.status_code == 200

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://127.0.0.1",
                    headers={
                        "Authorization": f"Bearer {credential.json()['token']}"
                    },
                ) as worker:
                    async with streamable_http_client(
                        "http://127.0.0.1/mcp/",
                        http_client=worker,
                    ) as (read_stream, write_stream, _sid):
                        async with ClientSession(read_stream, write_stream) as mcp:
                            await mcp.initialize()
                            payload = _structured(
                                await mcp.call_tool(
                                    "pex.get_goal",
                                    {"session_id": session.id},
                                )
                            )
                            assert payload["goal"]["id"] == goal_id

        hook_session = HarnessSession(
            id="opencode:typed-alias",
            harness_type=HarnessType.OPENCODE,
            vendor_session_id="typed-alias",
            project_id=alias_b,
            cwd=alias_b,
            status=SessionStatus.WORKING,
        )
        await store.upsert_session(hook_session)
        raw_hook_token = mint_hook_token()
        issued_at = datetime.now(UTC)
        hook_record = await store.issue_hook_credential(
            credential_id="hook-typed-alias",
            session_id=hook_session.id,
            project_id=alias_b,
            vendor_session_id=hook_session.vendor_session_id,
            harness_type=hook_session.harness_type.value,
            allowed_routes=[OPENCODE_OVERLAY_ROUTE],
            token_digest=digest_hook_token(raw_hook_token),
            issued_at=issued_at,
            expires_at=issued_at + timedelta(hours=1),
        )
        hook_principal = HookPrincipal.from_store_record(
            hook_record,
            now=issued_at,
        )
        await _authorize_hook_route(
            hook_principal,
            route=OPENCODE_OVERLAY_ROUTE,
            harness_type=HarnessType.OPENCODE,
            session_id=hook_session.id,
            vendor_session_id=hook_session.vendor_session_id,
            project_id=alias_a,
        )

        foreign = "/workspace/authority-foreign"
        await store.register_project_locator(
            legacy_project_id=foreign,
            locator=ProjectLocator.path(
                foreign,
                platform=PathPlatform.POSIX,
                origin=_ORIGIN,
            ),
        )
        with pytest.raises(HTTPException) as denied:
            await _authorize_hook_route(
                hook_principal,
                route=OPENCODE_OVERLAY_ROUTE,
                harness_type=HarnessType.OPENCODE,
                session_id=hook_session.id,
                vendor_session_id=hook_session.vendor_session_id,
                project_id=foreign,
            )
        assert denied.value.status_code == 403
    finally:
        await store.close()


def test_planner_and_mcp_sources_have_no_forensic_evidence_fallbacks():
    planner = inspect.getsource(Pipeline._build_and_commit_event_plan)
    mcp = inspect.getsource(build_mcp_server)

    assert not hasattr(Pipeline, "_ingest_event_legacy_unrecoverable")

    assert "list_context_for_authority" in planner
    assert "list_decisions_for_authority" in planner
    assert "recent_events_through_for_authority" in planner
    assert "list_context(" not in planner
    assert "list_decisions(" not in planner
    assert "recent_events_through(" not in planner

    assert "list_context_for_authority" in mcp
    assert "context_kind_counts_for_authority" in mcp
    assert "recent_events_for_authority" in mcp
    assert "list_context(" not in mcp
    assert "context_kind_counts_for_goal(" not in mcp
    assert "recent_events_for_binding(" not in mcp
