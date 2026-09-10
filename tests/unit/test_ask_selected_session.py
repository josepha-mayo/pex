"""Selected-session Ask HTTP scope remains Store-authoritative and fail closed."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge import app as app_module
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import ProjectIdentityBlockedError, Store
from pex_protocol.context import ContextItem
from pex_protocol.enums import ContextKind, HarnessType, SessionStatus, SourceKind
from pex_protocol.session import HarnessSession
from test_workspace_continuity_pipeline import bound_pipeline as bound_pipeline


@pytest.fixture
async def ask_client(tmp_path, monkeypatch):
    settings = Settings.for_test(require_auth=False, home=tmp_path, autonomy="observe")
    store = Store(tmp_path / "pex.sqlite")
    pipeline = Pipeline(store, AdapterRegistry(), EventBus(), settings)
    await store.connect()
    monkeypatch.setattr(pipeline, "refresh_desktop_sessions", AsyncMock())
    monkeypatch.setattr(app_module.state, "settings", settings)
    monkeypatch.setattr(app_module.state, "store", store)
    monkeypatch.setattr(app_module.state, "pipeline", pipeline)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://127.0.0.1"
    ) as client:
        yield client
    await store.close()


async def _goal(client: AsyncClient, title: str) -> dict:
    response = await client.post(
        "/v1/goals",
        json={"project_id": "ask-selected-demo", "title": title, "objective": title},
    )
    assert response.status_code == 200
    return response.json()


async def _opencode_session(
    goal: dict | None,
    vendor: str,
    status: SessionStatus,
) -> HarnessSession:
    session = HarnessSession(
        id=f"opencode:{vendor}",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id=vendor,
        project_id="ask-selected-demo",
        goal_id=goal["id"] if goal else None,
        cwd=None,
        status=status,
        last_activity=datetime.now(UTC),
    )
    await state.store.upsert_session(session)
    return session


async def _harness_session(
    goal: dict,
    harness_type: HarnessType,
    vendor: str,
    status: SessionStatus,
) -> HarnessSession:
    session = HarnessSession(
        id=f"{harness_type.value}:{vendor}",
        harness_type=harness_type,
        vendor_session_id=vendor,
        project_id="ask-selected-demo",
        goal_id=goal["id"],
        cwd=None,
        status=status,
        last_activity=datetime.now(UTC),
    )
    await state.store.upsert_session(session)
    return session


@pytest.mark.asyncio
async def test_ask_selected_opencode_does_not_fall_back_to_older_session(ask_client):
    older_goal = await _goal(ask_client, "older stopped goal")
    fresh_goal = await _goal(ask_client, "fresh selected goal")
    await _opencode_session(older_goal, "older", SessionStatus.STOPPED)
    fresh = await _opencode_session(fresh_goal, "fresh", SessionStatus.WORKING)

    response = await ask_client.post(
        "/v1/ask",
        json={"question": "what is Opencode doing?", "session_id": fresh.id},
    )

    assert response.status_code == 200
    answer = response.json()["answer"].lower()
    assert "opencode is working" in answer
    assert "stopped" not in answer
    assert "fresh selected goal" in answer
    assert "older stopped goal" not in answer


@pytest.mark.asyncio
async def test_ask_selected_keeps_only_different_harness_same_goal_context(ask_client):
    selected_goal = await _goal(ask_client, "selected shared goal")
    other_goal = await _goal(ask_client, "unrelated goal")
    selected = await _opencode_session(selected_goal, "selected", SessionStatus.WORKING)
    await _opencode_session(selected_goal, "older", SessionStatus.STOPPED)
    codex_peer = await _harness_session(
        selected_goal, HarnessType.CODEX, "peer", SessionStatus.WORKING
    )
    other_peer = await _harness_session(
        other_goal, HarnessType.CODEX, "other", SessionStatus.STOPPED
    )
    now = datetime.now(UTC)
    await state.store.add_context(
        ContextItem(
            id="selected-goal-codex-context",
            project_id="ask-selected-demo",
            goal_id=selected_goal["id"],
            kind=ContextKind.FACT,
            content="Codex peer observed the selected goal receipt.",
            source_refs=[codex_peer.id],
            provenance=SourceKind.HARNESS,
            valid_from=now,
            metadata={"source_session_id": codex_peer.id},
        )
    )
    await state.store.add_context(
        ContextItem(
            id="other-goal-codex-context",
            project_id="ask-selected-demo",
            goal_id=other_goal["id"],
            kind=ContextKind.FACT,
            content="Other goal context must not be available.",
            source_refs=[other_peer.id],
            provenance=SourceKind.HARNESS,
            valid_from=now,
            metadata={"source_session_id": other_peer.id},
        )
    )

    knowledge = await ask_client.post(
        "/v1/ask",
        json={
            "question": "What does Codex know that Opencode doesn't have?",
            "session_id": selected.id,
        },
    )
    doing = await ask_client.post(
        "/v1/ask",
        json={"question": "what is Opencode doing?", "session_id": selected.id},
    )

    assert knowledge.status_code == doing.status_code == 200
    assert "Codex peer observed the selected goal receipt." in knowledge.json()["answer"]
    assert "Other goal context" not in knowledge.json()["answer"]
    assert "opencode is working" in doing.json()["answer"].lower()
    assert "stopped" not in doing.json()["answer"].lower()


@pytest.mark.asyncio
async def test_ask_selected_goal_less_session_is_truthful_and_completion_is_not_borrowed(
    ask_client,
):
    await _goal(ask_client, "unrelated complete goal")
    discovered = await _opencode_session(None, "discovered", SessionStatus.DISCOVERED)

    doing = await ask_client.post(
        "/v1/ask",
        json={"question": "what is Opencode doing?", "session_id": discovered.id},
    )
    completion = await ask_client.post(
        "/v1/ask",
        json={"question": "is the task complete?", "session_id": discovered.id},
    )

    assert doing.status_code == 200
    assert "opencode is discovered" in doing.json()["answer"].lower()
    assert completion.status_code == 200
    assert "not attached to an active goal" in completion.json()["answer"].lower()
    assert "completion" not in completion.json()


@pytest.mark.asyncio
async def test_ask_selected_missing_or_revoked_session_fails_without_fallback(
    ask_client, monkeypatch,
):
    goal = await _goal(ask_client, "available fallback goal")
    await _opencode_session(goal, "available", SessionStatus.WORKING)

    missing = await ask_client.post(
        "/v1/ask",
        json={"question": "what is Opencode doing?", "session_id": "opencode:missing"},
    )
    assert missing.status_code == 404
    assert "answer" not in missing.json()

    monkeypatch.setattr(
        state.store,
        "get_session_for_authority",
        AsyncMock(
            side_effect=ProjectIdentityBlockedError(
                "session project identity changed", code="artifact_project_identity_changed"
            )
        ),
    )
    revoked = await ask_client.post(
        "/v1/ask",
        json={"question": "what is Opencode doing?", "session_id": "opencode:available"},
    )
    assert revoked.status_code == 409
    assert "answer" not in revoked.json()
    assert revoked.json()["detail"]["code"] == "artifact_project_identity_changed"


@pytest.mark.asyncio
async def test_ask_selected_completion_uses_only_selected_goal(ask_client, monkeypatch):
    other_goal = await _goal(ask_client, "other goal")
    selected_goal = await _goal(ask_client, "selected goal")
    await _opencode_session(other_goal, "other", SessionStatus.STOPPED)
    selected = await _opencode_session(selected_goal, "selected", SessionStatus.WORKING)
    projected_goal_ids = []

    async def selected_projection(goal_id: str) -> dict:
        projected_goal_ids.append(goal_id)
        return {"status": "in_progress"}

    monkeypatch.setattr(state.store, "goal_completion_projection", selected_projection)
    response = await ask_client.post(
        "/v1/ask",
        json={"question": "is the task complete?", "session_id": selected.id},
    )

    assert response.status_code == 200
    assert projected_goal_ids == [selected_goal["id"]]
    assert response.json()["completion"] == {"status": "in_progress"}
    assert response.json()["answer"] == "Not yet. Newer work is active on this goal."


@pytest.mark.asyncio
async def test_ask_selected_bound_workspace_runs_guard_for_selected_session(
    bound_pipeline, monkeypatch,
):
    bound = bound_pipeline
    checked_session_ids = []
    original_require_current = bound.store.require_session_workspace_current

    async def record_workspace_guard(session):
        checked_session_ids.append(session.id)
        return await original_require_current(session)

    async def no_discovery():
        return None

    monkeypatch.setattr(bound.pipeline, "refresh_desktop_sessions", no_discovery)
    monkeypatch.setattr(
        bound.store, "require_session_workspace_current", record_workspace_guard
    )
    monkeypatch.setattr(app_module.state, "settings", bound.pipeline.settings)
    monkeypatch.setattr(app_module.state, "store", bound.store)
    monkeypatch.setattr(app_module.state, "pipeline", bound.pipeline)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post(
            "/v1/ask",
            json={
                "question": "what is Codex doing?",
                "session_id": bound.adapter.session.id,
            },
        )

    assert response.status_code == 200
    assert checked_session_ids
    assert set(checked_session_ids) == {bound.adapter.session.id}
