from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType
from pex_protocol.enums import EventType, SessionStatus

_OPERATOR_TOKEN = "test-operator-token-0123456789abcdef"


@pytest.fixture
async def client(tmp_path):
    settings = Settings(
        require_auth=True,
        token=_OPERATOR_TOKEN,
        home=tmp_path,
        autonomy="manage",
    )
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.token = _OPERATOR_TOKEN
    state.store = store
    state.adapters = adapters
    state.pipeline = Pipeline(store, adapters, bus, settings)
    await store.connect()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {_OPERATOR_TOKEN}"},
    ) as ac:
        state.pipeline.model = None
        yield ac
    await store.close()


@pytest.mark.asyncio
async def test_competing_approaches_ask_human_before_forking_then_keep_winner(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "probe-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(
        vendor_id="speculative-parent",
        project_id="demo",
        cwd=str(worker),
    )
    await state.store.upsert_session(session)
    created = await client.post(
        "/v1/goals",
        json={
            "idempotency_key": "goal-create-speculative-index-0001",
            "project_id": "demo",
            "title": "Pick an index",
            "objective": "Choose the cheaper index approach.",
            "unresolved_questions": [
                "Try an in-memory index first",
                "Try a sqlite index first",
            ],
        },
    )
    assert created.status_code == 200, created.text
    attached = await client.post(
        f"/v1/sessions/{session.id}/attach",
        json={
            "goal_id": created.json()["id"],
            "expected_goal_id": None,
            "expected_control_revision": 0,
            "expected_goal_intent_revision": created.json()["intent_revision"],
            "idempotency_key": "goal-attach-speculative-index-0001",
        },
    )
    assert attached.status_code == 200, attached.text

    first = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "Need to pick an index approach.",
        },
    )
    assert first.status_code == 200, first.text
    intervention = first.json()["intervention"]
    assert intervention["action_taken"] == InterventionType.FORK_PROBE.value
    assert intervention["result"] == "awaiting_human"
    assert intervention["policy_verdict"] == "ask_human"
    assert len(adapter.sessions) == 1
    pending = await state.store.get_session(session.id)
    assert pending is not None
    assert pending.status == SessionStatus.NEEDS_DECISION

    resolved = await client.post(
        f"/v1/decisions/{intervention['id']}/resolve",
        json={"decision": "allow"},
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["executed"] is True
    child_id = body["session"]["metadata"]["speculative"]["sibling_session_id"]
    assert body["resolution"]["delivery_result"] == f"probe_forked:{child_id}"
    assert child_id != session.id
    assert child_id in adapter.sessions
    parent_probe = adapter.inbox[session.id][-1]
    child_probe = adapter.inbox[child_id][-1]

    def assigned(text: str) -> set[str]:
        found: set[str] = set()
        if "Try only this approach: Try an in-memory index first" in text:
            found.add("in-memory")
        if "Try only this approach: Try a sqlite index first" in text:
            found.add("sqlite")
        return found

    assert assigned(parent_probe) | assigned(child_probe) == {"in-memory", "sqlite"}
    assert assigned(parent_probe) != assigned(child_probe)
    assert not parent_probe.startswith("PEX:")
    assert "PEX:" not in child_probe.split("Next objective:", 1)[-1][:80]

    parent_fail = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {"pytest": {"ok": False, "exit_code": 1, "failed": 1}},
        },
    )
    assert parent_fail.status_code == 200, parent_fail.text
    parent_stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "Probe budget reached.",
        },
    )
    assert parent_stop.json()["intervention"]["action_taken"] == InterventionType.NOOP.value

    child_pass = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": child_id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {"pytest": {"ok": True, "exit_code": 0, "passed": 2}},
        },
    )
    assert child_pass.status_code == 200, child_pass.text
    child_stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": child_id,
            "event_type": EventType.STOP.value,
            "message": "Probe budget reached.",
        },
    )
    child_intervention = child_stop.json()["intervention"]
    assert child_intervention["action_taken"] == InterventionType.SEND_NUDGE.value
    text = adapter.inbox[child_id][-1]
    assert "in-memory" in text.lower()
    assert "sqlite" in text.lower()
    assert not text.startswith("PEX:")

    dispose = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "Probe budget reached.",
        },
    )
    loser = dispose.json()["intervention"]
    assert loser["action_taken"] == InterventionType.STOP_AGENT.value
    assert loser["result"] == "awaiting_human"
    assert loser["policy_verdict"] == "ask_human"
    assert len(adapter.sessions) == 2
