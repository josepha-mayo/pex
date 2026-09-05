"""Real Ask answer selection with fake inspect/provider boundaries only."""

import asyncio
import threading

import pytest
from pex_bridge import ask as ask_module
from pex_bridge.ask import answer_question as real_answer_question
from pex_protocol.enums import SessionStatus
from pex_supervisor import ask_review, inspect_http
from test_workspace_continuity_ask import _revoke, _wait_event
from test_workspace_continuity_ask import ask_client as ask_client
from test_workspace_continuity_pipeline import bound_pipeline as bound_pipeline


def _real_answer_with_fake_providers(monkeypatch):
    calls = []
    monkeypatch.setattr(ask_module, "answer_question", real_answer_question)
    monkeypatch.setattr(ask_module, "_can_inspect_review", lambda model: True)

    def fallback(*args, **kwargs):
        calls.append("fallback-model")
        return "FAKE_PROVIDER_ANSWER", None, None

    monkeypatch.setattr(inspect_http, "complete_review_answer", fallback)
    return calls


@pytest.mark.asyncio
async def test_current_workspace_real_answer_can_use_fallback_provider(ask_client, monkeypatch):
    calls = _real_answer_with_fake_providers(monkeypatch)
    monkeypatch.setattr(ask_review, "complete_inspect_review", lambda *args, **kwargs: None)
    response = await ask_client.client.post("/v1/ask", json={"question": "Inspect the report"})
    assert response.status_code == 200
    assert response.json()["answer"] == "FAKE_PROVIDER_ANSWER"
    assert calls == ["fallback-model"]


@pytest.mark.asyncio
async def test_origin_revoked_inside_inspect_prevents_real_answer_fallback(ask_client, monkeypatch):
    calls = _real_answer_with_fake_providers(monkeypatch)

    def revoked_inspection(*args, **kwargs):
        _revoke(ask_client, "origin")
        return None

    monkeypatch.setattr(ask_review, "complete_inspect_review", revoked_inspection)
    response = await ask_client.client.post("/v1/ask", json={"question": "Inspect the report"})
    assert response.status_code == 200
    assert "changed" in response.json()["answer"]
    assert calls == []


@pytest.mark.asyncio
async def test_timed_out_real_answer_thread_cannot_start_fallback(ask_client, monkeypatch):
    from pex_bridge import app as app_module

    calls = _real_answer_with_fake_providers(monkeypatch)
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_to_thread = asyncio.to_thread

    def held_inspection(*args, **kwargs):
        started.set()
        assert release.wait(timeout=5)
        return None

    async def observed_dispatch(function, *args, **kwargs):
        # Keep the actual queued app invocation; only observe when its owned
        # thread settles so the negative provider assertion cannot race it.
        def run():
            try:
                return function(*args, **kwargs)
            finally:
                finished.set()

        return await original_to_thread(run)

    monkeypatch.setattr(ask_review, "complete_inspect_review", held_inspection)
    monkeypatch.setattr(app_module, "ASK_MODEL_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(app_module.asyncio, "to_thread", observed_dispatch)
    task = asyncio.create_task(
        ask_client.client.post("/v1/ask", json={"question": "Inspect the report"})
    )
    try:
        await _wait_event(started)
        response = await task
        assert response.status_code == 200
        assert "FAKE_PROVIDER_ANSWER" not in response.json()["answer"]
        assert not finished.is_set()
        release.set()
        await _wait_event(finished)
        assert calls == []
    finally:
        release.set()
        if started.is_set():
            await _wait_event(finished)
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("with_history", [False, True])
async def test_detached_history_does_not_hide_current_same_goal_progress(
    ask_client, with_history,
):
    bound = ask_client.bound
    current = bound.adapter.session.model_copy(deep=True)
    current.status = SessionStatus.WORKING
    await bound.store.upsert_session(current)
    if with_history:
        # Publish a separate internal test observation, then detach it through
        # the normal authority-reducing path. No worker activity is generated.
        old = current.model_copy(deep=True)
        old.id = "codex:historical-fixture"
        old.vendor_session_id = "historical-fixture"
        old.goal_id = None
        old.status = SessionStatus.DISCOVERED
        old.metadata["subscription_receipt"] = {"authorization_id": "historical-fixture"}
        await bound.store.publish_observer_session(
            old, expected_control_revision=None,
            expected_project_binding=bound.workspace_binding.project_binding,
            expected_workspace=bound.workspace_binding,
            local_origin_path=bound.origin_path,
        )
        await bound.store.attach_session_goal(old.id, current.goal_id, expected_goal_id=None)
        old = await bound.store.get_session(old.id)
        controls = await bound.store.get_session_control_state(old.id)
        old.status = SessionStatus.DETACHED
        old.capabilities = {"send_message": False, "observe_messages": False}
        await bound.store.publish_observer_session(
            old, expected_control_revision=controls["control_revision"],
            expected_project_binding=bound.workspace_binding.project_binding,
        )
    projection = await bound.store.goal_completion_projection(current.goal_id)
    assert projection["status"] == "in_progress"
    assert projection["active_session_ids"] == [current.id]
    response = await ask_client.client.post("/v1/ask", json={"question": "Is my goal done?"})
    assert response.status_code == 200
    assert response.json().get("completion", {}).get("status") == "in_progress"
    assert ask_client.calls == [] and ask_client.reads == []
