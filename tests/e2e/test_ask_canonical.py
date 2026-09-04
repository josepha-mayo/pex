from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.context import ContextItem
from pex_protocol.enums import (
    ContextKind,
    EventType,
    HarnessType,
    Sensitivity,
    SessionStatus,
    SourceKind,
)
from pex_protocol.session import HarnessSession


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
        yield ac
    await store.close()


async def _live(
    harness: HarnessType,
    vendor: str,
    *,
    status: SessionStatus = SessionStatus.WORKING,
    goal_id: str | None = None,
):
    now = datetime.now(UTC)
    session = HarnessSession(
        id=f"{harness.value}:{vendor}",
        harness_type=harness,
        vendor_session_id=vendor,
        project_id="demo",
        goal_id=goal_id,
        status=status,
        last_activity=now,
    )
    await state.store.upsert_session(session)
    return session


@pytest.mark.asyncio
async def test_ask_answers_spec_questions_from_canonical_state_without_interrupting(
    client: AsyncClient,
    tmp_path,
):
    codex_goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Shared schema work",
                "objective": "Coordinate the schema freeze across attached workers.",
            },
        )
    ).json()
    devin_goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Schema review",
                "objective": "Review the schema freeze evidence independently.",
            },
        )
    ).json()
    codex = await _live(HarnessType.CODEX, "live", goal_id=codex_goal["id"])
    await _live(HarnessType.DEVIN, "live", goal_id=devin_goal["id"])
    now = datetime.now(UTC)
    await state.store.add_context(
        ContextItem(
            id="ctx-devin-schema",
            project_id="demo",
            goal_id=devin_goal["id"],
            kind=ContextKind.FACT,
            content="The schema freeze is already signed.",
            source_refs=["event:devin-schema"],
            provenance=SourceKind.HARNESS,
            confidence=0.9,
            valid_from=now,
            sensitivity=Sensitivity.INTERNAL,
            metadata={"source_session_id": "devin:live"},
        )
    )

    doing = await client.post("/v1/ask", json={"question": "what is Codex doing?"})
    assert doing.status_code == 200
    assert "codex is working" in doing.json()["answer"].lower()

    gap = await client.post(
        "/v1/ask",
        json={"question": "what does Devin know that Codex doesn't?"},
    )
    assert "schema freeze is already signed" in gap.json()["answer"]
    assert "codex does not have that item" in gap.json()["answer"].lower()

    guess = await client.post("/v1/ask", json={"question": "which approach looks better?"})
    assert "will not guess" in guess.json()["answer"].lower()

    missing = await client.post("/v1/ask", json={"question": "did the eval actually finish?"})
    assert "one specific active goal or agent name" in missing.json()["answer"].lower()
    assert "will not combine evidence across goals" in missing.json()["answer"].lower()

    adapter = state.adapters.synthetic
    worker_dir = tmp_path / "eval-complete"
    worker_dir.mkdir()
    worker = adapter.seed_session(vendor_id="eval-complete", cwd=str(worker_dir))
    await state.store.upsert_session(worker)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Parser",
                "objective": "Implement the parser with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    attached = await client.post(
        f"/v1/sessions/{worker.id}/attach",
        json={"goal_id": goal["id"]},
    )
    assert attached.status_code == 200
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": worker.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {"pytest": {"ok": True, "exit_code": 0, "passed": 4}},
        },
    )
    stopped = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": worker.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    assert stopped.json()["intervention"]["metadata"]["verification"]["status"] == "supported"
    finished = await client.post("/v1/ask", json={"question": "did the eval actually finish?"})
    assert "supports completion" in finished.json()["answer"].lower()
    assert adapter.inbox.get(codex.id, []) == []
    assert adapter.inbox.get(worker.id, []) == []


@pytest.mark.asyncio
async def test_ask_never_falls_back_to_forensic_intervention_scan(
    client: AsyncClient,
    monkeypatch,
):
    created = await client.post(
        "/v1/goals",
        json={
            "project_id": "demo",
            "title": "Authority-bound Ask",
            "objective": "Exclude stale intervention artifacts from Ask answers.",
        },
    )
    assert created.status_code == 200
    goal_id = created.json()["id"]
    session = await _live(HarnessType.CODEX, "authority-ask", goal_id=goal_id)

    raw_calls = 0
    authority_calls = 0
    authority_query = state.store.list_interventions_for_goal_for_authority

    async def reject_forensic_scan(*_args, **_kwargs):
        nonlocal raw_calls
        raw_calls += 1
        raise AssertionError("Ask must not scan forensic intervention history")

    async def observe_authority_query(*args, **kwargs):
        nonlocal authority_calls
        authority_calls += 1
        return await authority_query(*args, **kwargs)

    monkeypatch.setattr(state.store, "list_interventions", reject_forensic_scan)
    monkeypatch.setattr(
        state.store,
        "list_interventions_for_goal_for_authority",
        observe_authority_query,
    )

    response = await client.post(
        "/v1/ask",
        json={"question": "what is Codex doing?"},
    )

    assert response.status_code == 200
    assert "codex is working" in response.json()["answer"].lower()
    assert raw_calls == 0
    assert authority_calls == 1
    assert state.adapters.for_session(session.id) is not None
