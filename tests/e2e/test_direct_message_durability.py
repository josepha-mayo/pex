from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pex_bridge.app as app_module
import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.base import AdapterMessageResult, HarnessAdapter
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.enums import HarnessType
from pex_protocol.goal import Goal
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessSession


class _TypedCodexAdapter(HarnessAdapter):
    name = "codex"

    def __init__(self, result: AdapterMessageResult) -> None:
        self.result = result
        self.calls = 0

    async def probe(self) -> AdapterCapabilities:
        return AdapterCapabilities(send_message=True)

    async def discover_sessions(self) -> list[HarnessSession]:
        return []

    async def send_message(self, session, text, attachments=None):
        self.calls += 1
        return self.result


@pytest.fixture
async def direct_message_runtime(tmp_path):
    settings = Settings(require_auth=True, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_direct_message_e2e")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings, model=None)
    state.token = "direct-message-operator-token-0001"
    await store.connect()
    now = datetime.now(UTC)
    goal = Goal(
        id="direct-message-goal",
        project_id="direct-message-project",
        title="Durable direct control",
        objective="Send the operator instruction once.",
        created_at=now,
        updated_at=now,
    )
    session = adapters.synthetic.seed_session(
        vendor_id="direct-message-worker",
        project_id=goal.project_id,
        goal_id=goal.id,
    )
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {state.token}"},
    ) as client:
        yield client, store, adapters, session
    await store.close()


@pytest.mark.asyncio
async def test_direct_message_operator_auth_failures_precede_store_access(
    direct_message_runtime,
    monkeypatch,
):
    client, store, _adapters, session = direct_message_runtime
    touched = False

    async def forbidden_reservation(**_kwargs):
        nonlocal touched
        touched = True
        raise AssertionError("auth denial must precede Store access")

    monkeypatch.setattr(store, "reserve_operator_message", forbidden_reservation)
    path = f"/v1/sessions/{session.id}/message"
    body = {
        "idempotency_key": "direct-message-auth-0001",
        "text": "Do not dispatch without operator authentication.",
    }
    missing = await client.post(path, json=body, headers={"Authorization": ""})
    wrong = await client.post(
        path,
        json=body,
        headers={"Authorization": "Bearer wrong"},
    )
    token = state.token
    state.token = None
    unavailable = await client.post(path, json=body, headers={"Authorization": ""})
    state.token = token

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert unavailable.status_code == 503
    assert touched is False


@pytest.mark.asyncio
async def test_direct_message_refuses_test_only_no_auth_before_store_access(
    tmp_path,
    monkeypatch,
):
    settings = Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "no-auth.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings, model=None)
    state.token = None
    await store.connect()
    try:
        touched = False

        async def forbidden_reservation(**_kwargs):
            nonlocal touched
            touched = True
            raise AssertionError("auth denial must precede Store access")

        monkeypatch.setattr(store, "reserve_operator_message", forbidden_reservation)
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://127.0.0.1",
        ) as client:
            response = await client.post(
                "/v1/sessions/synthetic:any/message",
                json={
                    "idempotency_key": "direct-message-no-auth-0001",
                    "text": "This must be denied.",
                },
            )
        assert response.status_code == 403
        assert touched is False
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_direct_message_requires_key_and_exact_replay_sends_once(direct_message_runtime):
    client, store, adapters, session = direct_message_runtime
    missing = await client.post(
        f"/v1/sessions/{session.id}/message",
        json={"text": "Continue."},
    )
    assert missing.status_code == 422

    request = {
        "idempotency_key": "direct-message-e2e-0001",
        "text": "Continue with the verified parser.",
    }
    first = await client.post(f"/v1/sessions/{session.id}/message", json=request)
    replay = await client.post(f"/v1/sessions/{session.id}/message", json=request)
    changed = await client.post(
        f"/v1/sessions/{session.id}/message",
        json={**request, "text": "A different instruction."},
    )

    assert first.status_code == 200
    assert first.json()["status"] == "delivered"
    assert first.json()["replayed"] is False
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["receipt"] == first.json()["receipt"]
    assert changed.status_code == 409
    assert len(adapters.synthetic.inbox[session.id]) == 1
    cursor = await store.db.execute(
        "SELECT COUNT(*) FROM human_operator_terminal_actions"
    )
    assert (await cursor.fetchone())[0] == 1
    metrics = await store.attention_metrics()
    assert metrics["human_interventions"]["source_counts"][
        "direct_operator_message"
    ] == 1
    assert metrics["human_interventions"]["unverified_operator_action_counts"][
        "operator_message"
    ] == 0


@pytest.mark.asyncio
async def test_direct_message_timeout_is_terminal_uncertain_and_never_resent(
    direct_message_runtime,
    monkeypatch,
):
    client, _store, adapters, session = direct_message_runtime
    calls = 0

    async def accepted_then_stalled(bound_session, text, attachments=None):
        nonlocal calls
        calls += 1
        await asyncio.Event().wait()
        return True

    monkeypatch.setattr(adapters.synthetic, "send_message", accepted_then_stalled)
    monkeypatch.setattr(app_module, "ADAPTER_MESSAGE_TIMEOUT_SECONDS", 0.01)
    request = {
        "idempotency_key": "direct-message-timeout-0001",
        "text": "This transport outcome will be ambiguous.",
    }

    first = await client.post(f"/v1/sessions/{session.id}/message", json=request)
    replay = await client.post(f"/v1/sessions/{session.id}/message", json=request)

    assert first.status_code == 502
    assert first.json()["status"] == "delivery_uncertain"
    assert first.json()["receipt"]["result"]["reason"] == (
        "adapter_timeout_after_dispatch_started"
    )
    assert replay.status_code == 502
    assert replay.json()["replayed"] is True
    assert calls == 1


@pytest.mark.asyncio
async def test_direct_message_quarantine_race_yields_skipped_receipt_without_adapter_io(
    direct_message_runtime,
    monkeypatch,
):
    client, store, adapters, session = direct_message_runtime
    original_start = store.start_operator_message_dispatch
    origin = ProjectOrigin(namespace="machine", host="direct-message-e2e-host")
    calls = 0

    async def should_not_send(bound_session, text, attachments=None):
        nonlocal calls
        calls += 1
        return True

    async def quarantine_before_start(
        effect_id: str,
        *,
        global_supervision_paused: bool = False,
    ):
        await store.register_project_locator(
            legacy_project_id=str(session.project_id),
            locator=ProjectLocator.path(
                "/work/first",
                platform=PathPlatform.POSIX,
                origin=origin,
            ),
        )
        await store.register_project_locator(
            legacy_project_id=str(session.project_id),
            locator=ProjectLocator.path(
                "/work/second",
                platform=PathPlatform.POSIX,
                origin=origin,
            ),
        )
        return await original_start(
            effect_id,
            global_supervision_paused=global_supervision_paused,
        )

    monkeypatch.setattr(adapters.synthetic, "send_message", should_not_send)
    monkeypatch.setattr(store, "start_operator_message_dispatch", quarantine_before_start)
    response = await client.post(
        f"/v1/sessions/{session.id}/message",
        json={
            "idempotency_key": "direct-message-quarantine-0001",
            "text": "Do not cross the identity conflict.",
        },
    )

    assert response.status_code == 409
    assert response.json()["status"] == "skipped"
    assert response.json()["receipt"]["result"] == {
        "status": "skipped",
        "reason": "project_identity_quarantined",
    }
    assert calls == 0


@pytest.mark.asyncio
async def test_direct_message_global_pause_is_final_dispatch_gate(direct_message_runtime):
    client, _store, adapters, session = direct_message_runtime
    state.pipeline.supervision_paused = True
    try:
        response = await client.post(
            f"/v1/sessions/{session.id}/message",
            json={
                "idempotency_key": "direct-message-global-pause-0001",
                "text": "This must remain local while global supervision is paused.",
            },
        )
    finally:
        state.pipeline.supervision_paused = False

    assert response.status_code == 409
    assert response.json()["status"] == "skipped"
    assert response.json()["receipt"]["result"] == {
        "status": "skipped",
        "reason": "operator_message_binding_rejected",
    }
    assert adapters.synthetic.inbox[session.id] == []


@pytest.mark.asyncio
async def test_direct_codex_message_persists_exact_turn_and_rejects_cross_session(
    direct_message_runtime,
):
    client, store, adapters, source = direct_message_runtime
    exact_session = HarnessSession(
        id="codex:direct-exact",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-direct-exact",
        project_id=source.project_id,
        goal_id=source.goal_id,
    )
    await store.upsert_session(exact_session)
    exact_adapter = _TypedCodexAdapter(
        AdapterMessageResult(
            accepted=True,
            vendor_session_id=exact_session.vendor_session_id,
            vendor_turn_id="turn-direct-exact",
        )
    )
    adapters.bind("codex", exact_adapter)
    exact_request = {
        "idempotency_key": "direct-message-codex-exact-0001",
        "text": "Continue on the exact bound Codex turn.",
    }

    delivered = await client.post(
        f"/v1/sessions/{exact_session.id}/message",
        json=exact_request,
    )
    replay = await client.post(
        f"/v1/sessions/{exact_session.id}/message",
        json=exact_request,
    )

    assert delivered.status_code == 200
    assert delivered.json()["receipt"]["result"]["worker_delivery_receipt"] == {
        "schema": "pex.worker-delivery.codex-turn.v1",
        "target_session_id": exact_session.id,
        "vendor_session_id": exact_session.vendor_session_id,
        "vendor_turn_id": "turn-direct-exact",
    }
    assert replay.json()["receipt"] == delivered.json()["receipt"]
    assert exact_adapter.calls == 1

    wrong_session = HarnessSession(
        id="codex:direct-wrong",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-direct-wrong",
        project_id=source.project_id,
        goal_id=source.goal_id,
    )
    await store.upsert_session(wrong_session)
    wrong_adapter = _TypedCodexAdapter(
        AdapterMessageResult(
            accepted=True,
            vendor_session_id="another-thread",
            vendor_turn_id="turn-direct-wrong",
        )
    )
    adapters.bind("codex", wrong_adapter)
    wrong_request = {
        "idempotency_key": "direct-message-codex-wrong-0001",
        "text": "Never claim a cross-session receipt was delivered.",
    }
    uncertain = await client.post(
        f"/v1/sessions/{wrong_session.id}/message",
        json=wrong_request,
    )
    uncertain_replay = await client.post(
        f"/v1/sessions/{wrong_session.id}/message",
        json=wrong_request,
    )

    assert uncertain.status_code == 502
    assert uncertain.json()["status"] == "delivery_uncertain"
    assert uncertain.json()["receipt"]["result"] == {
        "status": "delivery_uncertain",
        "reason": "invalid_adapter_receipt",
    }
    assert uncertain_replay.json()["receipt"] == uncertain.json()["receipt"]
    assert wrong_adapter.calls == 1
