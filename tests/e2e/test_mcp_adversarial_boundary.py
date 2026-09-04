from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from itertools import count

import pytest
from httpx import ASGITransport, AsyncClient
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pets import PetSettings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store, new_id
from pex_protocol.context import ContextItem
from pex_protocol.enums import ContextKind, EventType, Sensitivity, SourceKind
from pex_protocol.session import HarnessEvent

_GOAL_CONTROL_SEQUENCE = count(1)


async def _make_app(
    tmp_path,
    *,
    require_auth: bool = False,
    token: str | None = None,
):
    settings = (
        Settings(require_auth=True, home=tmp_path, autonomy="manage")
        if require_auth
        else Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage")
    )
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = token
    state.pet_settings = PetSettings()
    state.pet_path = tmp_path / "pet.json"
    await store.connect()
    return create_app(), store


async def _create_goal(client: AsyncClient) -> dict:
    response = await client.post(
        "/v1/goals",
        json={
            "idempotency_key": f"mcp-boundary-goal-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "project_id": "demo",
            "title": "Adversarial MCP boundary",
            "objective": "Accept only provenance-bound worker mutations",
            "acceptance_criteria": ["unauthorized mutations leave no durable rows"],
        },
    )
    assert response.status_code == 200
    return response.json()


async def _seed_session_for_goal(client: AsyncClient, goal_id: str) -> str:
    created = await client.post("/v1/synthetic/sessions")
    assert created.status_code == 200
    session_id = created.json()["id"]
    goal = await state.store.get_goal_intent_view(goal_id)
    assert goal is not None
    attached = await client.post(
        f"/v1/sessions/{session_id}/attach",
        json={
            "idempotency_key": f"mcp-boundary-attach-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "goal_id": goal_id,
            "expected_goal_id": None,
            "expected_control_revision": 0,
            "expected_goal_intent_revision": goal["intent_revision"],
        },
    )
    assert attached.status_code == 200
    return session_id


async def _seed_two_sessions(client: AsyncClient) -> tuple[str, str, str]:
    goal = await _create_goal(client)
    source_id = await _seed_session_for_goal(client, goal["id"])
    sibling = state.adapters.synthetic.seed_session(
        vendor_id=new_id("adversarial_sibling_")
    )
    sibling.project_id = "demo"
    await state.store.upsert_session(sibling)
    attached = await client.post(
        f"/v1/sessions/{sibling.id}/attach",
        json={
            "idempotency_key": f"mcp-boundary-attach-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "goal_id": goal["id"],
            "expected_goal_id": None,
            "expected_control_revision": 0,
            "expected_goal_intent_revision": goal["intent_revision"],
        },
    )
    assert attached.status_code == 200
    assert sibling.id != source_id
    return source_id, sibling.id, goal["id"]


async def _issue_worker_token(client: AsyncClient, session_id: str) -> str:
    response = await client.post(f"/v1/sessions/{session_id}/mcp-credential")
    assert response.status_code == 200
    return response.json()["token"]


def _structured(result) -> dict:
    assert result.isError is False
    payload = result.structuredContent
    if payload is None:
        texts = [
            block.text
            for block in (result.content or [])
            if getattr(block, "text", None)
        ]
        assert texts, "MCP tool returned neither structured content nor text"
        payload = json.loads(texts[0])
    if (
        isinstance(payload, dict)
        and set(payload) == {"result"}
        and isinstance(payload["result"], dict)
    ):
        payload = payload["result"]
    assert isinstance(payload, dict)
    return payload


async def _durable_snapshot(store: Store) -> dict[str, object]:
    counts: dict[str, int] = {}
    for table in (
        "events",
        "context_items",
        "interventions",
        "intervention_audit",
        "mcp_mutations",
    ):
        cursor = await store.db.execute(f"SELECT COUNT(*) AS count FROM {table}")
        counts[table] = int((await cursor.fetchone())["count"])
    audit = (
        store.audit_path.read_text(encoding="utf-8")
        if store.audit_path.exists()
        else ""
    )
    return {"counts": counts, "audit": audit}


def _error_text(result) -> str:
    return "\n".join(
        str(block.text)
        for block in (result.content or [])
        if getattr(block, "text", None)
    )


async def _call_rejected_mutations(
    mcp: ClientSession,
    session_id: str,
    *,
    error_fragment: str,
) -> None:
    calls = [
        (
            "pex.report_progress",
            {
                "session_id": session_id,
                "report": {
                    "idempotency_key": "read-only-report-0001",
                    "summary": "This caller must not be allowed to report progress.",
                    "evidence_refs": [{"type": "event", "id": "evt-missing"}],
                },
            },
        ),
        (
            "pex.request_decision",
            {
                "session_id": session_id,
                "request": {
                    "idempotency_key": "read-only-decision-0001",
                    "question": "This caller must not open a decision.",
                },
            },
        ),
        (
            "pex.handoff",
            {
                "session_id": session_id,
                "request": {
                    "idempotency_key": "read-only-handoff-0001",
                    "target_session_id": session_id,
                },
            },
        ),
        (
            "pex.verify_claim",
            {
                "session_id": session_id,
                "request": {
                    "idempotency_key": "read-only-verify-0001",
                    "claim": "This caller must not create verified context.",
                },
            },
        ),
    ]
    for tool, arguments in calls:
        result = await mcp.call_tool(tool, arguments)
        assert result.isError is True, tool
        assert error_fragment.casefold() in _error_text(result).casefold(), tool


@pytest.mark.asyncio
async def test_anonymous_principal_is_read_only_across_all_mutation_tools(tmp_path):
    app, store = await _make_app(tmp_path)
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
            ) as http:
                goal = await _create_goal(http)
                session_id = await _seed_session_for_goal(http, goal["id"])
                before = await _durable_snapshot(store)
                async with streamable_http_client(
                    "http://127.0.0.1/mcp/",
                    http_client=http,
                ) as (read_stream, write_stream, _sid):
                    async with ClientSession(read_stream, write_stream) as mcp:
                        await mcp.initialize()
                        await _call_rejected_mutations(
                            mcp,
                            session_id,
                            error_fragment="scope",
                        )

                assert await _durable_snapshot(store) == before
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_global_operator_principal_is_read_only_across_all_mutation_tools(
    tmp_path,
):
    operator_token = "adversarial-mcp-operator-token-at-least-32"
    app, store = await _make_app(
        tmp_path,
        require_auth=True,
        token=operator_token,
    )
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": f"Bearer {operator_token}"},
            ) as operator:
                goal = await _create_goal(operator)
                session_id = await _seed_session_for_goal(operator, goal["id"])
                before = await _durable_snapshot(store)
                async with streamable_http_client(
                    "http://127.0.0.1/mcp/",
                    http_client=operator,
                ) as (read_stream, write_stream, _sid):
                    async with ClientSession(read_stream, write_stream) as mcp:
                        await mcp.initialize()
                        await _call_rejected_mutations(
                            mcp,
                            session_id,
                            error_fragment="scope",
                        )

                assert await _durable_snapshot(store) == before
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_session_principal_cannot_mutate_a_sibling_session(tmp_path):
    operator_token = "cross-session-mcp-operator-token-at-least-32"
    app, store = await _make_app(
        tmp_path,
        require_auth=True,
        token=operator_token,
    )
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": f"Bearer {operator_token}"},
            ) as operator:
                source_id, sibling_id, _goal_id = await _seed_two_sessions(operator)
                worker_token = await _issue_worker_token(operator, source_id)
                before = await _durable_snapshot(store)

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://127.0.0.1",
                    headers={"Authorization": f"Bearer {worker_token}"},
                ) as worker_http:
                    async with streamable_http_client(
                        "http://127.0.0.1/mcp/",
                        http_client=worker_http,
                    ) as (read_stream, write_stream, _sid):
                        async with ClientSession(read_stream, write_stream) as mcp:
                            await mcp.initialize()
                            await _call_rejected_mutations(
                                mcp,
                                sibling_id,
                                error_fragment="not bound",
                            )

                assert await _durable_snapshot(store) == before
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_report_progress_rejects_untrusted_evidence_without_durable_deltas(
    tmp_path,
):
    operator_token = "evidence-mcp-operator-token-at-least-32"
    app, store = await _make_app(
        tmp_path,
        require_auth=True,
        token=operator_token,
    )
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": f"Bearer {operator_token}"},
            ) as operator:
                source_id, sibling_id, goal_id = await _seed_two_sessions(operator)
                source = await store.get_session(source_id)
                sibling = await store.get_session(sibling_id)
                assert source is not None
                assert sibling is not None
                now = datetime.now(UTC)

                foreign_event = HarnessEvent(
                    event_id=new_id("foreign_evt_"),
                    ts=now,
                    harness_type=sibling.harness_type,
                    session_id=sibling.id,
                    project_id="demo",
                    goal_id=goal_id,
                    event_type=EventType.AGENT_RESPONSE,
                    message_delta="A sibling reported this evidence.",
                )
                await store.add_event(foreign_event)

                contexts = [
                    ContextItem(
                        id=new_id("foreign_ctx_"),
                        project_id="demo",
                        goal_id=goal_id,
                        kind=ContextKind.FACT,
                        content="A sibling owns this context.",
                        provenance=SourceKind.HARNESS,
                        valid_from=now,
                        metadata={"source_session_id": sibling.id},
                    ),
                    ContextItem(
                        id=new_id("secret_ctx_"),
                        project_id="demo",
                        goal_id=goal_id,
                        kind=ContextKind.FACT,
                        content="Private evidence must not authorize progress.",
                        provenance=SourceKind.HARNESS,
                        valid_from=now,
                        sensitivity=Sensitivity.SECRET,
                        metadata={"source_session_id": source.id},
                    ),
                    ContextItem(
                        id=new_id("stale_ctx_"),
                        project_id="demo",
                        goal_id=goal_id,
                        kind=ContextKind.FACT,
                        content="Expired evidence must not authorize progress.",
                        provenance=SourceKind.HARNESS,
                        valid_from=now - timedelta(hours=2),
                        stale_after=now - timedelta(hours=1),
                        metadata={"source_session_id": source.id},
                    ),
                ]
                for item in contexts:
                    await store.add_context(item)

                worker_token = await _issue_worker_token(operator, source_id)
                cases = [
                    ("missing-event", {"type": "event", "id": "evt-does-not-exist"}),
                    (
                        "foreign-event",
                        {"type": "event", "id": foreign_event.event_id},
                    ),
                    ("foreign-context", {"type": "context", "id": contexts[0].id}),
                    ("secret-context", {"type": "context", "id": contexts[1].id}),
                    ("stale-context", {"type": "context", "id": contexts[2].id}),
                ]
                before = await _durable_snapshot(store)

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://127.0.0.1",
                    headers={"Authorization": f"Bearer {worker_token}"},
                ) as worker_http:
                    async with streamable_http_client(
                        "http://127.0.0.1/mcp/",
                        http_client=worker_http,
                    ) as (read_stream, write_stream, _sid):
                        async with ClientSession(read_stream, write_stream) as mcp:
                            await mcp.initialize()
                            for index, (label, evidence_ref) in enumerate(cases):
                                result = await mcp.call_tool(
                                    "pex.report_progress",
                                    {
                                        "session_id": source_id,
                                        "report": {
                                            "idempotency_key": (
                                                f"rejected-{index:02d}-{label}"
                                            ),
                                            "summary": (
                                                "This report must not survive its "
                                                f"{label} evidence."
                                            ),
                                            "evidence_refs": [evidence_ref],
                                        },
                                    },
                                )
                                assert result.isError is True, label
                                assert "evidence" in _error_text(result).casefold(), label
                                assert await _durable_snapshot(store) == before
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_report_progress_exact_retry_replays_and_changed_payload_conflicts(
    tmp_path,
):
    operator_token = "replay-mcp-operator-token-at-least-32"
    app, store = await _make_app(
        tmp_path,
        require_auth=True,
        token=operator_token,
    )
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": f"Bearer {operator_token}"},
            ) as operator:
                goal = await _create_goal(operator)
                source_id = await _seed_session_for_goal(operator, goal["id"])
                source = await store.get_session(source_id)
                assert source is not None
                evidence = HarnessEvent(
                    event_id=new_id("owned_evt_"),
                    ts=datetime.now(UTC),
                    harness_type=source.harness_type,
                    session_id=source.id,
                    project_id="demo",
                    goal_id=goal["id"],
                    event_type=EventType.AGENT_RESPONSE,
                    message_delta="The implementation and its test output are present.",
                )
                await store.add_event(evidence)
                worker_token = await _issue_worker_token(operator, source_id)
                payload = {
                    "session_id": source_id,
                    "report": {
                        "idempotency_key": "exact-replay-progress-0001",
                        "summary": "Implemented and tested the bounded MCP mutation.",
                        "evidence_refs": [
                            {"type": "event", "id": evidence.event_id}
                        ],
                    },
                }

                before = await _durable_snapshot(store)
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://127.0.0.1",
                    headers={"Authorization": f"Bearer {worker_token}"},
                ) as worker_http:
                    async with streamable_http_client(
                        "http://127.0.0.1/mcp/",
                        http_client=worker_http,
                    ) as (read_stream, write_stream, _sid):
                        async with ClientSession(read_stream, write_stream) as mcp:
                            await mcp.initialize()
                            created = _structured(
                                await mcp.call_tool("pex.report_progress", payload)
                            )
                            assert created["replayed"] is False
                            after_create = await _durable_snapshot(store)
                            before_counts = before["counts"]
                            after_counts = after_create["counts"]
                            assert isinstance(before_counts, dict)
                            assert isinstance(after_counts, dict)
                            for table in (
                                "events",
                                "context_items",
                                "interventions",
                                "intervention_audit",
                                "mcp_mutations",
                            ):
                                assert after_counts[table] == before_counts[table] + 1

                            replayed = _structured(
                                await mcp.call_tool("pex.report_progress", payload)
                            )
                            assert replayed["replayed"] is True
                            assert replayed["mutation_id"] == created["mutation_id"]
                            assert replayed["item"]["id"] == created["item"]["id"]
                            assert (
                                replayed["intervention"]["id"]
                                == created["intervention"]["id"]
                            )
                            assert await _durable_snapshot(store) == after_create

                            changed = {
                                **payload,
                                "report": {
                                    **payload["report"],
                                    "summary": (
                                        "A materially different report reused the key."
                                    ),
                                },
                            }
                            conflict = await mcp.call_tool(
                                "pex.report_progress",
                                changed,
                            )
                            assert conflict.isError is True
                            assert "reused with new content" in _error_text(
                                conflict
                            ).casefold()
                            assert await _durable_snapshot(store) == after_create
    finally:
        await store.close()
