from __future__ import annotations

import asyncio
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
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.context import ContextHandoffRequest, ContextItem
from pex_protocol.enums import (
    Authority,
    ContextKind,
    EventType,
    PolicyVerdict,
    Sensitivity,
    SourceKind,
)
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent

MCP_TOOLS = {
    "pex.get_goal",
    "pex.get_relevant_context",
    "pex.find_agent_with_context",
    "pex.get_project_state",
    "pex.report_progress",
    "pex.request_decision",
    "pex.handoff",
    "pex.verify_claim",
}
_GOAL_CONTROL_SEQUENCE = count(1)


def _goal_control_key(kind: str) -> str:
    return f"mcp-server-{kind}-{next(_GOAL_CONTROL_SEQUENCE):08d}"


async def _attach_request(session_id: str, goal_id: str) -> dict:
    session = await state.store.get_session_control_state(session_id)
    goal = await state.store.get_goal_intent_view(goal_id)
    assert session is not None
    assert goal is not None
    return {
        "idempotency_key": _goal_control_key("attach"),
        "goal_id": goal_id,
        "expected_goal_id": session["session"].goal_id,
        "expected_control_revision": session["control_revision"],
        "expected_goal_intent_revision": goal["intent_revision"],
    }


async def _make_app(tmp_path, *, require_auth: bool = False, token: str | None = None):
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


async def _seed_attached_session(client: AsyncClient) -> tuple[str, str]:
    session = (await client.post("/v1/synthetic/sessions")).json()
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "idempotency_key": _goal_control_key("create"),
                "project_id": "demo",
                "title": "Parser",
                "objective": "Implement the frontend pet atlas with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    attached = await client.post(
        f"/v1/sessions/{session['id']}/attach",
        json=await _attach_request(session["id"], goal["id"]),
    )
    assert attached.status_code == 200
    return session["id"], goal["id"]


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


def _state_intervention(
    intervention_id: str,
    *,
    session_id: str,
    goal_id: str,
    created_at: datetime,
) -> Intervention:
    action = ProposedAction(
        type=InterventionType.NOOP,
        session_id=session_id,
        goal_id=goal_id,
        rationale="No interruption is justified by the observed evidence.",
        evidence=[f"event:{intervention_id}"],
        confidence=0.9,
        risk=RiskLevel.NONE,
        authority_required=Authority.LOCAL_POLICY,
    )
    return Intervention(
        id=intervention_id,
        session_id=session_id,
        goal_id=goal_id,
        trigger="status",
        evidence=action.evidence,
        diagnosis="no_intervention_needed",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="noop",
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_mcp_lists_and_calls_read_only_tools(tmp_path):
    app, store = await _make_app(tmp_path)
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
            ) as http:
                session_id, goal_id = await _seed_attached_session(http)
                now = datetime.now(UTC)
                await state.store.add_context(
                    ContextItem(
                        id=new_id("ctx_"),
                        project_id="demo",
                        goal_id=goal_id,
                        kind=ContextKind.FACT,
                        content=(
                            "The frontend pet atlas lives in "
                            "apps/desktop/src/pets/atlas.tsx."
                        ),
                        source_refs=["event:atlas"],
                        provenance=SourceKind.HARNESS,
                        confidence=0.9,
                        relevance_tags=["frontend", "pet", "atlas"],
                        valid_from=now,
                        sensitivity=Sensitivity.INTERNAL,
                        metadata={"source_session_id": "synthetic:source"},
                    )
                )
                await state.store.add_context(
                    ContextItem(
                        id=new_id("secret_"),
                        project_id="demo",
                        goal_id=goal_id,
                        kind=ContextKind.FACT,
                        content="production database password is hunter2",
                        source_refs=["event:secret"],
                        provenance=SourceKind.HARNESS,
                        confidence=0.9,
                        relevance_tags=["frontend", "pet", "atlas"],
                        valid_from=now,
                        sensitivity=Sensitivity.SECRET,
                        metadata={"source_session_id": "synthetic:source"},
                    )
                )
                source = state.adapters.synthetic.seed_session(vendor_id="source")
                source.project_id = "demo"
                source.goal_id = goal_id
                await state.store.upsert_session(source)
                await state.store.add_context(
                    ContextItem(
                        id=new_id("secret2_"),
                        project_id="demo",
                        goal_id=goal_id,
                        kind=ContextKind.FACT,
                        content="LOCAL_ONLY scratch path C:/Users/me/.pex/scratch",
                        source_refs=["event:local"],
                        provenance=SourceKind.HARNESS,
                        confidence=0.9,
                        relevance_tags=["frontend"],
                        valid_from=now,
                        sensitivity=Sensitivity.LOCAL_ONLY,
                        metadata={"source_session_id": source.id},
                    )
                )
                unattached = state.adapters.synthetic.seed_session(vendor_id="orphan")
                await state.store.upsert_session(unattached)

                async with streamable_http_client(
                    "http://127.0.0.1/mcp/",
                    http_client=http,
                ) as (read_stream, write_stream, _sid):
                    async with ClientSession(read_stream, write_stream) as mcp:
                        await mcp.initialize()
                        listed = await mcp.list_tools()
                        names = {tool.name for tool in listed.tools}
                        assert names == MCP_TOOLS

                        missing = await mcp.call_tool(
                            "pex.get_goal", {"session_id": "missing"}
                        )
                        assert missing.isError is True

                        no_goal = await mcp.call_tool(
                            "pex.get_goal",
                            {"session_id": unattached.id},
                        )
                        assert no_goal.isError is True

                        goal = _structured(
                            await mcp.call_tool(
                                "pex.get_goal", {"session_id": session_id}
                            )
                        )
                        assert goal["session_id"] == session_id
                        assert goal["goal"]["id"] == goal_id
                        assert "atlas" in goal["goal"]["objective"].lower()

                        bundle = _structured(
                            await mcp.call_tool(
                                "pex.get_relevant_context",
                                {
                                    "session_id": session_id,
                                    "token_budget": 2_000,
                                },
                            )
                        )
                        contents = [item["content"] for item in bundle["items"]]
                        assert any("atlas.tsx" in item for item in contents)
                        assert all("hunter2" not in item for item in contents)
                        assert all("LOCAL_ONLY" not in item for item in contents)
                        assert bundle["goal_id"] == goal_id
                        assert bundle["target_session_id"] == session_id

                        found = _structured(
                            await mcp.call_tool(
                                "pex.find_agent_with_context",
                                {
                                    "session_id": session_id,
                                    "query": "frontend pet atlas",
                                },
                            )
                        )
                        assert found["query"] == "frontend pet atlas"
                        assert any(
                            agent["session_id"] == source.id
                            for agent in found["agents"]
                        )
                        for agent in found["agents"]:
                            for item in agent["context"]:
                                assert "hunter2" not in item["content"]

                        project = _structured(
                            await mcp.call_tool(
                                "pex.get_project_state",
                                {"session_id": session_id},
                            )
                        )
                        assert project["goal"]["id"] == goal_id
                        assert "secret" not in project["context_counts"]
                        dumped = str(project)
                        assert "hunter2" not in dumped
                        assert session_id in {row["id"] for row in project["sessions"]}
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_mcp_requires_bearer_and_rejects_query_tokens(tmp_path):
    token = "local-test-token-that-is-at-least-32"
    app, store = await _make_app(tmp_path, require_auth=True, token=token)
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
            ) as client:
                denied = await client.post("/mcp/")
                assert denied.status_code == 401
                leaked = await client.post("/mcp/?token=" + token)
                assert leaked.status_code == 401

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": f"Bearer {token}"},
            ) as authed:
                async with streamable_http_client(
                    "http://127.0.0.1/mcp/",
                    http_client=authed,
                ) as (read_stream, write_stream, _sid):
                    async with ClientSession(read_stream, write_stream) as mcp:
                        await mcp.initialize()
                        listed = await mcp.list_tools()
                        assert {tool.name for tool in listed.tools} == MCP_TOOLS
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_mcp_mutation_tools_use_canonical_pipeline_paths(tmp_path):
    operator_token = "mcp-mutation-operator-token-at-least-32"
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
            ) as http:
                source_id, goal_id = await _seed_attached_session(http)
                target = state.adapters.synthetic.seed_session(vendor_id="target")
                target.project_id = "demo"
                await state.store.upsert_session(target)
                attached = await http.post(
                    f"/v1/sessions/{target.id}/attach",
                    json=await _attach_request(target.id, goal_id),
                )
                assert attached.status_code == 200
                source = await state.store.get_session(source_id)
                assert source is not None
                now = datetime.now(UTC)
                evidence_event = HarnessEvent(
                    event_id=new_id("dataset_"),
                    ts=now,
                    harness_type=source.harness_type,
                    session_id=source_id,
                    project_id="demo",
                    event_type=EventType.AGENT_RESPONSE,
                    message_delta=(
                        "Dataset is at artifacts/prepared_dataset.parquet. "
                        "Do not regenerate it."
                    ),
                )
                await state.store.accept_pipeline_event(
                    evidence_event,
                    session_snapshot=source,
                )
                evidence_context_id = new_id("ctx_")
                await state.store.add_context(
                    ContextItem(
                        id=evidence_context_id,
                        project_id="demo",
                        goal_id=goal_id,
                        kind=ContextKind.FACT,
                        content=(
                            "Dataset is at artifacts/prepared_dataset.parquet. "
                            "Do not regenerate it."
                        ),
                        source_refs=[evidence_event.event_id],
                        provenance=SourceKind.HARNESS,
                        confidence=0.9,
                        relevance_tags=["dataset", "parquet", "frontend", "pet", "atlas"],
                        valid_from=now,
                        sensitivity=Sensitivity.INTERNAL,
                        metadata={"source_session_id": source_id},
                    )
                )
                pytest_event = HarnessEvent(
                    event_id=new_id("pytest_"),
                    ts=now + timedelta(microseconds=1),
                    harness_type=source.harness_type,
                    session_id=source_id,
                    project_id="demo",
                    event_type=EventType.SHELL,
                    command="pytest -q",
                    process_state={
                        "pytest": {"ok": True, "exit_code": 0, "passed": 4}
                    },
                )
                await state.store.accept_pipeline_event(
                    pytest_event,
                    session_snapshot=source,
                )
                credential = await http.post(
                    f"/v1/sessions/{source_id}/mcp-credential"
                )
                assert credential.status_code == 200
                worker_token = credential.json()["token"]

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://127.0.0.1",
                    headers={"Authorization": f"Bearer {worker_token}"},
                ) as worker_http:
                    async with streamable_http_client(
                        "http://127.0.0.1/mcp/",
                        http_client=worker_http,
                    ) as (read_stream, write_stream, _sid):
                        mcp = ClientSession(read_stream, write_stream)
                        await mcp.__aenter__()
                        await mcp.initialize()

                        bare = await mcp.call_tool(
                            "pex.report_progress",
                            {
                                "session_id": source_id,
                                "report": {
                                    "idempotency_key": "progress-empty-evidence-0001",
                                    "summary": "I am done",
                                    "evidence_refs": [],
                                },
                            },
                        )
                        assert bare.isError is True

                        report_payload = {
                            "session_id": source_id,
                            "report": {
                                "idempotency_key": "progress-atlas-wiring-0001",
                                "summary": (
                                    "Wired the frontend pet atlas to the "
                                    "prepared dataset path."
                                ),
                                "evidence_refs": [
                                    {"type": "context", "id": evidence_context_id},
                                    {"type": "event", "id": evidence_event.event_id},
                                ],
                            },
                        }
                        progress = _structured(
                            await mcp.call_tool(
                                "pex.report_progress",
                                report_payload,
                            )
                        )
                        assert progress["ok"] is True
                        assert progress["verified"] is False
                        assert progress["item"]["kind"] == "result"
                        assert progress["item"]["metadata"].get("verified") is not True
                        assert progress["replayed"] is False
                        replayed = _structured(
                            await mcp.call_tool("pex.report_progress", report_payload)
                        )
                        assert replayed["replayed"] is True
                        assert replayed["mutation_id"] == progress["mutation_id"]
                        assert replayed["item"]["id"] == progress["item"]["id"]
                        assert (
                            replayed["intervention"]["id"]
                            == progress["intervention"]["id"]
                        )
                        stored_progress = await state.store.list_context("demo")
                        assert any(
                            item.id == progress["item"]["id"]
                            and not bool(item.metadata.get("verified"))
                            for item in stored_progress
                        )

                        decision_payload = {
                            "session_id": source_id,
                            "request": {
                                "idempotency_key": "decision-atlas-ship-0001",
                                "question": "Ship the atlas now or keep iterating?",
                                "options": ["ship", "iterate"],
                                "urgency": "high",
                            },
                        }
                        decision = _structured(
                            await mcp.call_tool(
                                "pex.request_decision",
                                decision_payload,
                            )
                        )
                        assert decision["auto_resolved"] is False
                        assert decision["replayed"] is False
                        assert decision["session_status"] == "needs_decision"
                        assert (
                            decision["intervention"]["policy_verdict"] == "ask_human"
                        )
                        decision_replay = _structured(
                            await mcp.call_tool(
                                "pex.request_decision",
                                decision_payload,
                            )
                        )
                        assert decision_replay["replayed"] is True
                        assert (
                            decision_replay["intervention"]["id"]
                            == decision["intervention"]["id"]
                        )
                        decision_conflict = await mcp.call_tool(
                            "pex.request_decision",
                            {
                                **decision_payload,
                                "request": {
                                    **decision_payload["request"],
                                    "question": "Ship to production now?",
                                },
                            },
                        )
                        assert decision_conflict.isError is True
                        live = await state.store.get_session(source_id)
                        assert live is not None
                        assert live.status.value == "needs_decision"

                        unauthenticated_resolution = await worker_http.post(
                            "/v1/decisions/"
                            f"{decision['intervention']['id']}/resolve",
                            json={"decision": "iterate"},
                        )
                        assert unauthenticated_resolution.status_code == 401
                        unoffered = await http.post(
                            "/v1/decisions/"
                            f"{decision['intervention']['id']}/resolve",
                            json={"decision": "Iterate"},
                        )
                        assert unoffered.status_code == 422
                        resolved = await http.post(
                            "/v1/decisions/"
                            f"{decision['intervention']['id']}/resolve",
                            json={"decision": "iterate"},
                        )
                        assert resolved.status_code == 200
                        resolved_body = resolved.json()
                        assert resolved_body["ok"] is True
                        assert resolved_body["kind"] == "human_decision"
                        assert resolved_body["resolved"] is True
                        assert resolved_body["delivered"] is True
                        assert resolved_body["delivery_status"] == "delivered"
                        assert resolved_body["resolution"]["status"] == "delivered"
                        assert resolved_body["replayed"] is False
                        resolved_replay = await http.post(
                            "/v1/decisions/"
                            f"{decision['intervention']['id']}/resolve",
                            json={"decision": "iterate"},
                        )
                        assert resolved_replay.status_code == 200
                        assert resolved_replay.json()["replayed"] is True
                        conflicting_resolution = await http.post(
                            "/v1/decisions/"
                            f"{decision['intervention']['id']}/resolve",
                            json={"decision": "ship"},
                        )
                        assert conflicting_resolution.status_code == 409
                        pending_context = await state.store.get_context(
                            decision["pending_context"]["id"]
                        )
                        assert pending_context is not None
                        assert pending_context.metadata["status"] == "resolved"
                        assert pending_context.stale_after is not None

                        handed = _structured(
                            await mcp.call_tool(
                                "pex.handoff",
                                {
                                    "session_id": source_id,
                                    "request": {
                                        "idempotency_key": "mcp-handoff-atlas-0001",
                                        "target_session_id": target.id,
                                    },
                                },
                            )
                        )
                        assert handed["ok"] is True
                        assert "bundle" not in handed
                        assert handed["bundle_receipt"]["schema"] == (
                            "pex.handoff-bundle-receipt.v1"
                        )
                        assert handed["bundle_receipt"]["context_item_ids"]
                        assert "prepared_dataset" not in str(handed)
                        assert state.adapters.synthetic.inbox[target.id]
                        assert "prepared_dataset" in state.adapters.synthetic.inbox[
                            target.id
                        ][0]
                        self_target = await mcp.call_tool(
                            "pex.handoff",
                            {
                                "session_id": source_id,
                                "request": {
                                    "idempotency_key": "mcp-handoff-self-0001",
                                    "target_session_id": source_id,
                                },
                            },
                        )
                        assert self_target.isError is True

                        uncertain = _structured(
                            await mcp.call_tool(
                                "pex.verify_claim",
                                {
                                    "session_id": source_id,
                                    "request": {
                                        "idempotency_key": "mcp-server-done-0001",
                                        "claim": "I am done.",
                                    },
                                },
                            )
                        )
                        assert uncertain["status"] == "uncertain"
                        assert uncertain["verified"] is False

                        verified = _structured(
                            await mcp.call_tool(
                                "pex.verify_claim",
                                {
                                    "session_id": source_id,
                                    "request": {
                                        "idempotency_key": "mcp-server-tests-0001",
                                        "claim": "All tests passed.",
                                    },
                                },
                            )
                        )
                        assert verified["status"] == "verified"
                        assert verified["verified"] is True
                        assert verified["verified_items"]
                        assert all(
                            item["metadata"].get("verified") is True
                            for item in verified["verified_items"]
                        )
                        await mcp.__aexit__(None, None, None)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_project_state_uses_goal_scoped_queries_before_bounding(
    tmp_path,
    monkeypatch,
):
    app, store = await _make_app(tmp_path)
    try:
        async with app.state.pex_mcp.session_manager.run():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://127.0.0.1",
            ) as http:
                session_id, goal_id = await _seed_attached_session(http)
                now = datetime.now(UTC)
                for item in (
                    ContextItem(
                        id="ctx-visible",
                        project_id="demo",
                        goal_id=goal_id,
                        kind=ContextKind.FACT,
                        content="The atlas implementation exists.",
                        valid_from=now,
                        sensitivity=Sensitivity.INTERNAL,
                    ),
                    ContextItem(
                        id="ctx-secret",
                        project_id="demo",
                        goal_id=goal_id,
                        kind=ContextKind.WARNING,
                        content="secret material",
                        valid_from=now,
                        sensitivity=Sensitivity.SECRET,
                    ),
                    ContextItem(
                        id="ctx-local",
                        project_id="demo",
                        goal_id=goal_id,
                        kind=ContextKind.RESULT,
                        content="local-only material",
                        valid_from=now,
                        sensitivity=Sensitivity.LOCAL_ONLY,
                    ),
                ):
                    await store.add_context(item)

                relevant = [
                    _state_intervention(
                        "int-relevant-old",
                        session_id=session_id,
                        goal_id=goal_id,
                        created_at=now - timedelta(minutes=2),
                    ),
                    _state_intervention(
                        "int-relevant-new",
                        session_id=session_id,
                        goal_id=goal_id,
                        created_at=now - timedelta(minutes=1),
                    ),
                ]
                decoy_goal = Goal(
                    id="goal-decoy",
                    project_id="demo",
                    title="Unrelated goal",
                    objective="Prove goal-scoped intervention pagination.",
                    created_at=now,
                    updated_at=now,
                )
                await store.upsert_goal(decoy_goal)
                decoy_session = state.adapters.synthetic.seed_session(
                    vendor_id="decoy",
                    project_id="demo",
                    goal_id=decoy_goal.id,
                )
                await store.upsert_session(decoy_session)
                decoys = [
                    _state_intervention(
                        f"int-decoy-{index}",
                        session_id=decoy_session.id,
                        goal_id=decoy_goal.id,
                        created_at=now + timedelta(seconds=index),
                    )
                    for index in range(55)
                ]
                for row in [*relevant, *decoys]:
                    await store.add_intervention(row)

                async def reject_legacy_scan(*_args, **_kwargs):
                    raise AssertionError("project state used an unscoped Store scan")

                monkeypatch.setattr(store, "list_sessions", reject_legacy_scan)
                monkeypatch.setattr(store, "list_context", reject_legacy_scan)
                monkeypatch.setattr(store, "list_interventions", reject_legacy_scan)

                async with streamable_http_client(
                    "http://127.0.0.1/mcp/",
                    http_client=http,
                ) as (read_stream, write_stream, _sid):
                    async with ClientSession(read_stream, write_stream) as mcp:
                        await mcp.initialize()
                        project = _structured(
                            await mcp.call_tool(
                                "pex.get_project_state",
                                {"session_id": session_id},
                            )
                        )

                assert [row["id"] for row in project["recent_interventions"]] == [
                    "int-relevant-new",
                    "int-relevant-old",
                ]
                assert project["context_counts"] == {"fact": 1}
                assert [row["id"] for row in project["sessions"]] == [session_id]
                assert "secret material" not in str(project)
                assert "local-only material" not in str(project)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_mcp_handoff_honors_pause_cooldown_and_exact_replay(
    tmp_path,
    monkeypatch,
):
    operator_token = "mcp-handoff-operator-token-at-least-32"
    operator_headers = {"Authorization": f"Bearer {operator_token}"}
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
                headers=operator_headers,
            ) as http:
                source_id, goal_id = await _seed_attached_session(http)
                target = state.adapters.synthetic.seed_session(vendor_id="guarded-target")
                target.project_id = "demo"
                await state.store.upsert_session(target)
                attached = await http.post(
                    f"/v1/sessions/{target.id}/attach",
                    json=await _attach_request(target.id, goal_id),
                )
                assert attached.status_code == 200
                await state.store.add_context(
                    ContextItem(
                        id=new_id("ctx_"),
                        project_id="demo",
                        goal_id=goal_id,
                        kind=ContextKind.FACT,
                        content="Use artifacts/guarded_dataset.parquet for the atlas.",
                        source_refs=["event:guarded-dataset"],
                        provenance=SourceKind.HARNESS,
                        confidence=0.9,
                        relevance_tags=["dataset", "frontend", "atlas"],
                        valid_from=datetime.now(UTC),
                        sensitivity=Sensitivity.INTERNAL,
                        metadata={"source_session_id": source_id},
                    )
                )
                credential = await http.post(
                    f"/v1/sessions/{source_id}/mcp-credential"
                )
                assert credential.status_code == 200
                credential_body = credential.json()
                http.headers["Authorization"] = (
                    f"Bearer {credential_body['token']}"
                )

                async with streamable_http_client(
                    "http://127.0.0.1/mcp/",
                    http_client=http,
                ) as (read_stream, write_stream, _sid):
                    async with ClientSession(read_stream, write_stream) as mcp:
                        await mcp.initialize()

                        async def call_handoff(*, token_budget: int = 2_000):
                            return await mcp.call_tool(
                                "pex.handoff",
                                {
                                    "session_id": source_id,
                                    "request": {
                                        "idempotency_key": "mcp-handoff-guarded-0001",
                                        "target_session_id": target.id,
                                        "token_budget": token_budget,
                                    },
                                },
                            )

                        event_count = len(await state.store.latest_events(1_000))

                        paused = await http.post(
                            f"/v1/sessions/{source_id}/pause-supervision",
                            headers=operator_headers,
                        )
                        assert paused.status_code == 200
                        assert (await call_handoff()).isError is True
                        await http.post(
                            f"/v1/sessions/{source_id}/resume-supervision",
                            headers=operator_headers,
                        )

                        paused = await http.post(
                            f"/v1/sessions/{target.id}/pause-supervision",
                            headers=operator_headers,
                        )
                        assert paused.status_code == 200
                        assert (await call_handoff()).isError is True
                        await http.post(
                            f"/v1/sessions/{target.id}/resume-supervision",
                            headers=operator_headers,
                        )

                        paused_goal = await http.patch(
                            f"/v1/goals/{goal_id}",
                            json={
                                "idempotency_key": _goal_control_key("update"),
                                "paused": True,
                                "expected_intent_revision": 1,
                            },
                            headers=operator_headers,
                        )
                        assert paused_goal.status_code == 200
                        assert (await call_handoff()).isError is True
                        resumed_goal = await http.patch(
                            f"/v1/goals/{goal_id}",
                            json={
                                "idempotency_key": _goal_control_key("update"),
                                "paused": False,
                                "expected_intent_revision": paused_goal.json()[
                                    "intent_revision"
                                ],
                            },
                            headers=operator_headers,
                        )
                        assert resumed_goal.status_code == 200

                        state.pipeline.supervision_paused = True
                        assert (await call_handoff()).isError is True
                        state.pipeline.supervision_paused = False

                        assert state.adapters.synthetic.inbox[target.id] == []
                        assert await state.store.list_interventions(target.id) == []
                        assert len(await state.store.latest_events(1_000)) == event_count

                        delivered = _structured(await call_handoff())
                        assert delivered["ok"] is True
                        assert delivered["replayed"] is False
                        assert delivered["cooldown_seconds"] == 120
                        assert "bundle" not in delivered
                        assert delivered["bundle_receipt"]["schema"] == (
                            "pex.handoff-bundle-receipt.v1"
                        )
                        assert "guarded_dataset" not in str(
                            delivered["intervention"]["proposed_action"]["payload"]
                        )
                        assert len(state.adapters.synthetic.inbox[target.id]) == 1
                        assert "guarded_dataset" in state.adapters.synthetic.inbox[target.id][0]
                        effect = await store.get_operator_effect(delivered["effect"]["effect_id"])
                        assert effect is not None
                        assert effect["principal_id"].startswith("mcp_handoff_")
                        assert effect["principal_id"] != credential_body["principal_id"]
                        event_count = len(await state.store.latest_events(1_000))

                        # The replay receipt is durable, not an in-memory lock artifact.
                        state.pipeline = Pipeline(
                            store,
                            state.adapters,
                            state.bus,
                            state.settings,
                        )
                        replayed = _structured(await call_handoff())
                        assert replayed["ok"] is True
                        assert replayed["replayed"] is True
                        assert replayed["intervention"]["id"] == delivered["intervention"]["id"]
                        assert replayed["bundle_receipt"] == delivered["bundle_receipt"]
                        assert "bundle" not in replayed
                        assert len(state.adapters.synthetic.inbox[target.id]) == 1
                        assert len(await state.store.latest_events(1_000)) == event_count

                        changed_request = await call_handoff(token_budget=3_000)
                        assert changed_request.isError is True
                        assert "context_handoff_idempotency_conflict" in str(
                            changed_request.content
                        )
                        assert len(state.adapters.synthetic.inbox[target.id]) == 1
                        rows = await state.store.list_interventions(target.id)
                        assert len(rows) == 1
                        assert rows[0].result == "handoff_injected"
                        assert rows[0].metadata["handoff_delivery_status"] == "delivered"

                        concurrent_target = state.adapters.synthetic.seed_session(
                            vendor_id="concurrent-target"
                        )
                        concurrent_target.project_id = "demo"
                        await state.store.upsert_session(concurrent_target)
                        attached = await http.post(
                            f"/v1/sessions/{concurrent_target.id}/attach",
                            json=await _attach_request(concurrent_target.id, goal_id),
                            headers=operator_headers,
                        )
                        assert attached.status_code == 200
                        source = await state.store.get_session(source_id)
                        concurrent_target = await state.store.get_session(
                            concurrent_target.id
                        )
                        assert source is not None
                        assert concurrent_target is not None
                        concurrent = await asyncio.gather(
                            state.pipeline.request_context_handoff(
                                source,
                                principal_id="mcp-handoff-concurrency-test",
                                request=ContextHandoffRequest(
                                    idempotency_key="mcp-handoff-concurrent-0001",
                                    target_session_id=concurrent_target.id,
                                ),
                            ),
                            state.pipeline.request_context_handoff(
                                source,
                                principal_id="mcp-handoff-concurrency-test",
                                request=ContextHandoffRequest(
                                    idempotency_key="mcp-handoff-concurrent-0001",
                                    target_session_id=concurrent_target.id,
                                ),
                            ),
                        )
                        assert sorted(result["replayed"] for result in concurrent) == [
                            False,
                            True,
                        ]
                        assert len(
                            state.adapters.synthetic.inbox[concurrent_target.id]
                        ) == 1
                        concurrent_rows = await state.store.list_interventions(
                            concurrent_target.id
                        )
                        assert len(concurrent_rows) == 1

                        terminal_replay = _structured(await call_handoff())
                        assert terminal_replay["status"] == "delivered"
                        assert terminal_replay["replayed"] is True
                        assert len(state.adapters.synthetic.inbox[target.id]) == 1
                        assert len(await state.store.list_interventions(target.id)) == 1

                        uncertain_target = state.adapters.synthetic.seed_session(
                            vendor_id="uncertain-target"
                        )
                        uncertain_target.project_id = "demo"
                        await state.store.upsert_session(uncertain_target)
                        attached = await http.post(
                            f"/v1/sessions/{uncertain_target.id}/attach",
                            json=await _attach_request(uncertain_target.id, goal_id),
                            headers=operator_headers,
                        )
                        assert attached.status_code == 200

                        async def stalled_delivery(_session, _bundle):
                            await asyncio.Event().wait()
                            return True

                        monkeypatch.setattr(
                            "pex_bridge.pipeline.HANDOFF_ADAPTER_TIMEOUT_SECONDS",
                            0.01,
                        )
                        monkeypatch.setattr(
                            state.adapters.synthetic,
                            "inject_context",
                            stalled_delivery,
                        )
                        uncertain_payload = {
                            "session_id": source_id,
                            "request": {
                                "idempotency_key": "mcp-handoff-uncertain-0001",
                                "target_session_id": uncertain_target.id,
                            },
                        }
                        uncertain = _structured(
                            await mcp.call_tool("pex.handoff", uncertain_payload)
                        )
                        assert uncertain["ok"] is False
                        assert uncertain["status"] == "delivery_uncertain"
                        assert uncertain["effect"]["result"] == {
                            "status": "delivery_uncertain",
                            "reason": "handoff_adapter_timeout_after_dispatch_started",
                        }
                        uncertain_replay = _structured(
                            await mcp.call_tool("pex.handoff", uncertain_payload)
                        )
                        assert uncertain_replay["status"] == "delivery_uncertain"
                        assert uncertain_replay["replayed"] is True
    finally:
        state.pipeline.supervision_paused = False
        await store.close()
