from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType
from pex_protocol.enums import EventType


@pytest.fixture
async def client(tmp_path):
    settings = Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.pipeline = Pipeline(store, adapters, bus, settings)
    await store.connect()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as ac:
        state.pipeline.model = None
        yield ac, tmp_path
    await store.close()


def _inbox(tmp_path):
    path = tmp_path / "channels" / "inbox.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.mark.asyncio
async def test_channels_status_is_honest_and_fork_probe_writes_inbox(client):
    ac, tmp_path = client
    listed = await ac.get("/v1/channels")
    assert listed.status_code == 200
    body = listed.json()
    assert body["attention_policy"] == "human_decisions_only"
    by_id = {row["id"]: row for row in body["channels"]}
    assert by_id["file"]["connected"] is True
    assert by_id["telegram"]["connected"] is False
    assert by_id["discord"]["connected"] is False
    assert by_id["whatsapp"]["connected"] is False
    assert by_id["slack"]["connected"] is False

    worker = tmp_path / "probe-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(
        vendor_id="channel-parent",
        project_id="demo",
        cwd=str(worker),
    )
    await state.store.upsert_session(session)
    created = await ac.post(
        "/v1/goals",
        json={
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
    attached = await ac.post(
        f"/v1/sessions/{session.id}/attach",
        json={"goal_id": created.json()["id"]},
    )
    assert attached.status_code == 200, attached.text

    first = await ac.post(
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
    assert intervention["metadata"]["remote_notify"] == "notified:file"
    rows = _inbox(tmp_path)
    assert len(rows) == 1
    assert rows[0]["kind"] == "decision"
    assert rows[0]["text"].startswith("PEX: Synthetic has two cheap approaches")
    assert "channel-parent" not in rows[0]["text"]
    assert session.id not in rows[0]["text"]
    assert adapter.inbox[session.id] == []
    followup = await state.store.db.execute(
        "SELECT state, result_json FROM event_followups "
        "WHERE event_id = ? AND kind = 'human_attention'",
        (intervention["metadata"]["trigger_event_id"],),
    )
    followup_row = await followup.fetchone()
    assert followup_row is not None
    assert followup_row["state"] == "complete"
    assert json.loads(followup_row["result_json"])["delivery"] == "notified:file"


@pytest.mark.asyncio
async def test_worker_nudge_does_not_fan_out_to_remote_inbox(client):
    ac, tmp_path = client
    worker = tmp_path / "nudge-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="channel-nudge", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await ac.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "report",
                "objective": "Create report.txt containing exactly the word shipped.",
                "acceptance_criteria": ["report.txt contains shipped"],
                "evidence_requirements": ["report.txt"],
            },
        )
    ).json()
    attached = await ac.post(
        f"/v1/sessions/{session.id}/attach",
        json={"goal_id": goal["id"]},
    )
    assert attached.status_code == 200
    first = await ac.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "I am done.",
        },
    )
    intervention = first.json()["intervention"]
    assert intervention["action_taken"] == "SEND_NUDGE"
    assert "remote_notify" not in (intervention.get("metadata") or {})
    text = adapter.inbox[session.id][-1]
    assert not text.startswith("PEX:")
    assert not _inbox(tmp_path)
