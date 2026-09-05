"""Actual Ask HTTP/evidence path; temporary Store and fake answers only."""

import asyncio
import json
import sqlite3
import threading
from types import SimpleNamespace

import httpx
import pytest
from pex_bridge import app as app_module
from pex_bridge import ask as ask_module
from pex_supervisor import workspace as workspace_module
from pex_supervisor.ask_review import _review_request
from pex_supervisor.evidence_observations import EvidenceObservationCollector
from pex_supervisor.evidence_tools import build_evidence_tools
from test_workspace_continuity_pipeline import _change_workspace
from test_workspace_continuity_pipeline import bound_pipeline as bound_pipeline


@pytest.fixture
async def ask_client(bound_pipeline, monkeypatch):
    bound = bound_pipeline
    async def no_discovery():
        return None

    monkeypatch.setattr(bound.pipeline, "refresh_desktop_sessions", no_discovery)
    monkeypatch.setattr(bound.pipeline, "model", object())
    monkeypatch.setattr(app_module.state, "store", bound.store)
    monkeypatch.setattr(app_module.state, "pipeline", bound.pipeline)
    monkeypatch.setattr(app_module.state, "settings", bound.pipeline.settings)
    # The subscription fixture intentionally invents no last_activity. Isolate
    # Ask authority from its recent-activity display filter; retain the actual
    # Store-authorized rows and their original receipt without forging activity.
    monkeypatch.setattr(app_module, "collapse_promptable_agents", lambda rows, now: rows)
    calls, reads, outputs, collectors = [], [], [], []

    def read_visible(*args, **kwargs):
        reads.append(args)
        return {"path": "report.txt", "text": "TEST_WORKSPACE_CONTENT"}

    monkeypatch.setattr(workspace_module, "read_visible", read_visible)

    def inspect(sessions, interventions, goals):
        request = _review_request(sessions, goals, interventions)
        assert request is not None
        collector = EvidenceObservationCollector(request, stage="main", invocation_id="ask-test")
        collectors.append(collector)
        tools = {tool.tool_name: tool for tool in build_evidence_tools(
            request, [], collector=collector,
        )}
        output = tools["inspect_file"](path="report.txt")
        outputs.append(output)
        return output

    def answer(question, sessions, interventions, goals, model, *, context=None):
        calls.append(model)
        return inspect(sessions, interventions, goals)

    monkeypatch.setattr(ask_module, "answer_question", answer)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_module.create_app()), base_url="http://127.0.0.1",
    ) as client:
        yield SimpleNamespace(
            bound=bound, client=client, calls=calls, reads=reads,
            outputs=outputs, collectors=collectors, inspect=inspect,
        )


def _revoke(case, change):
    if change != "locator":
        _change_workspace(case.bound, change)
    else:
        # The fake answer runs synchronously in its own thread. Use its own
        # temporary SQLite connection, never the fixture's asynchronous handle.
        with sqlite3.connect(case.bound.store.path) as connection:
            connection.execute(
                "DELETE FROM project_locators WHERE fingerprint = ?",
                (case.bound.workspace_binding.locator.fingerprint,),
            )


@pytest.mark.asyncio
async def test_ask_valid_published_workspace_reads_under_matching_request_guard(ask_client):
    case = ask_client
    response = await case.client.post("/v1/ask", json={"question": "Inspect the report"})
    assert response.status_code == 200
    assert "TEST_WORKSPACE_CONTENT" in response.json()["answer"]
    assert len(case.calls) == len(case.reads) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["directory", "origin", "locator"])
async def test_ask_stale_before_answer_never_calls_answer_or_reads(ask_client, change):
    case = ask_client
    _revoke(case, change)
    response = await case.client.post("/v1/ask", json={"question": "Inspect the report"})
    assert response.status_code == 200
    assert "changed" in response.json()["answer"]
    assert case.calls == [] and case.reads == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["directory", "origin", "locator"])
async def test_ask_revocation_during_answer_blocks_tool_and_stale_response(
    ask_client, monkeypatch, change,
):
    case = ask_client
    def revoked_answer(question, sessions, interventions, goals, model, *, context=None):
        case.calls.append(model)
        _revoke(case, change)
        case.inspect(sessions, interventions, goals)
        return "STALE_ANSWER_CONTENT"

    monkeypatch.setattr(ask_module, "answer_question", revoked_answer)
    response = await case.client.post("/v1/ask", json={"question": "Inspect the report"})
    assert response.status_code == 200
    assert "changed" in response.json()["answer"]
    assert "STALE_ANSWER_CONTENT" not in response.text
    assert len(case.calls) == 1 and case.reads == []
    assert json.loads(case.outputs[0])["error"] == "workspace_authority_unavailable"
    assert "TEST_WORKSPACE_CONTENT" not in "".join(
        item.output for collector in case.collectors for item in collector.observations
    )


async def _wait_event(event):
    async def wait():
        while not event.is_set():
            await asyncio.sleep(0.01)
    await asyncio.wait_for(wait(), timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize("end", ["timeout", "cancel"])
async def test_ask_ended_scope_denies_surviving_answer_thread_reads(
    ask_client, monkeypatch, end,
):
    case = ask_client
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def held_answer(question, sessions, interventions, goals, model, *, context=None):
        if model is None:
            return "Canonical fallback without model or inspection"
        case.calls.append(model)
        started.set()
        try:
            assert release.wait(timeout=5)
            return case.inspect(sessions, interventions, goals)
        finally:
            finished.set()

    monkeypatch.setattr(ask_module, "answer_question", held_answer)
    if end == "timeout":
        # The real worker-entry Store check must finish before the answer-spy
        # barrier. This is a test-only bound, not the product timeout.
        monkeypatch.setattr(app_module, "ASK_MODEL_TIMEOUT_SECONDS", 1.0)
    task = asyncio.create_task(case.client.post("/v1/ask", json={"question": "Inspect the report"}))
    try:
        await _wait_event(started)
        if end == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            response = await task
            assert response.status_code == 200
            assert "Canonical fallback" in response.json()["answer"]
        assert not finished.is_set()
        release.set()
        await _wait_event(finished)
        assert len(case.calls) == 1 and case.reads == []
        assert json.loads(case.outputs[0])["error"] == "workspace_authority_unavailable"
        assert "TEST_WORKSPACE_CONTENT" not in "".join(
            item.output for collector in case.collectors for item in collector.observations
        )
    finally:
        release.set()
        if started.is_set():
            await _wait_event(finished)
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("filtered", [False, True])
async def test_completion_guard_covers_attached_sessions_hidden_by_activity_filter(
    ask_client, monkeypatch, filtered,
):
    case = ask_client
    if filtered:
        # Use the real filter: this newly subscribed fixture has no invented
        # last_activity and is intentionally absent from the promptable deck.
        from pex_bridge.pipeline import collapse_promptable_agents
        monkeypatch.setattr(app_module, "collapse_promptable_agents", collapse_promptable_agents)
    projections = []

    async def supported_projection(goal_id):
        # Spy isolates whether the guard runs before consuming a completion
        # projection; it is not a fabricated persisted completion receipt.
        projections.append(goal_id)
        return {"status": "verified_complete"}

    monkeypatch.setattr(case.bound.store, "goal_completion_projection", supported_projection)
    _revoke(case, "origin")
    response = await case.client.post("/v1/ask", json={"question": "Is my goal done?"})
    assert response.status_code == 200
    assert projections == []
    assert "uncertain" in response.json()["answer"].lower()
    assert "completion" not in response.json()
    assert case.calls == [] and case.reads == []


@pytest.mark.asyncio
async def test_completion_guard_rechecks_after_projection_await(ask_client, monkeypatch):
    case = ask_client
    async def changed_projection(goal_id):
        _revoke(case, "origin")
        await asyncio.sleep(0)
        return {"status": "verified_complete"}

    monkeypatch.setattr(case.bound.store, "goal_completion_projection", changed_projection)
    response = await case.client.post("/v1/ask", json={"question": "Is my goal done?"})
    assert response.status_code == 200
    assert "uncertain" in response.json()["answer"].lower()
    assert "completion" not in response.json()
    assert case.calls == [] and case.reads == []


@pytest.mark.asyncio
async def test_ask_queued_answer_checks_authority_when_thread_starts(ask_client, monkeypatch):
    case = ask_client
    queued, release = asyncio.Event(), asyncio.Event()
    original_to_thread = asyncio.to_thread

    async def delayed_dispatch(function, *args, **kwargs):
        queued.set()
        await release.wait()
        return await original_to_thread(function, *args, **kwargs)

    monkeypatch.setattr(app_module.asyncio, "to_thread", delayed_dispatch)
    task = asyncio.create_task(case.client.post("/v1/ask", json={"question": "Inspect the report"}))
    try:
        await asyncio.wait_for(queued.wait(), timeout=5)
        _revoke(case, "origin")
        release.set()
        response = await task
        assert response.status_code == 200
        assert "changed" in response.json()["answer"]
        assert case.calls == [] and case.reads == []
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_ask_cancelled_during_worker_entry_check_never_starts_answer(
    ask_client, monkeypatch,
):
    from pex_bridge import workspace_access

    case = ask_client
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_factory = workspace_access.workspace_read_check
    original_to_thread = asyncio.to_thread

    def held_check_factory(*args, **kwargs):
        original_check = original_factory(*args, **kwargs)

        def check():
            original_check()
            started.set()
            assert release.wait(timeout=5)

        return check

    async def observed_dispatch(function, *args, **kwargs):
        def run():
            try:
                return function(*args, **kwargs)
            finally:
                finished.set()

        return await original_to_thread(run)

    monkeypatch.setattr(workspace_access, "workspace_read_check", held_check_factory)
    monkeypatch.setattr(app_module.asyncio, "to_thread", observed_dispatch)
    task = asyncio.create_task(case.client.post("/v1/ask", json={"question": "Inspect the report"}))
    try:
        await _wait_event(started)
        assert case.calls == []
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not finished.is_set()
        release.set()
        await _wait_event(finished)
        assert case.calls == [] and case.reads == [] and case.collectors == []
    finally:
        release.set()
        if started.is_set():
            await _wait_event(finished)
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
