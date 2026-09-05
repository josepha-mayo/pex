from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.codex_shared_attach import (
    SharedCodexAttachments,
    SharedCodexConfirm,
    SharedCodexSelection,
)
from pex_bridge.config import Settings
from pex_bridge.local_origin_config import save_local_origin_choice
from pex_bridge.store import Store
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessSession
from test_codex_subscription import FakeSharedTransport, _notification, _thread_response


@pytest.fixture
async def shared_client(tmp_path, monkeypatch):
    import pex_bridge.codex_shared_attach as module

    store = Store(tmp_path / "attach.sqlite")
    await store.connect()
    save_local_origin_choice(
        tmp_path / "local-origin.json",
        ProjectOrigin(namespace="machine", host="attachment-fixture"),
        expected_revision=None,
        expected_choice_id=None,
    )
    await store.register_project_locator(
        legacy_project_id="pex-project-namespace",
        locator=ProjectLocator.path(
            str(tmp_path),
            platform=PathPlatform.WINDOWS if os.name == "nt" else PathPlatform.POSIX,
            origin=ProjectOrigin(namespace="machine", host="attachment-fixture"),
        ),
    )
    manager = SharedCodexAttachments()
    adapters = AdapterRegistry()
    events = []

    async def ingest(event, session):
        events.append(event)

    async def ingest_shared(event, session):
        # Fake callback for attachment tests; authenticated runtime behavior is
        # exercised separately through the actual Pipeline callback tests.
        return await state.pipeline.ingest_event(event, session)

    async def retain_shared(observations, session):
        # Attachment wiring only; record-only durability/authority is covered
        # by test_codex_observation_retention with actual Pipeline and Store.
        events.extend(event for event, _ in observations)

    transports = []

    def transport_factory(*args, **kwargs):
        response = _thread_response(tmp_path, thread_update={"status": {"type": "idle"}})
        transport = FakeSharedTransport([response] * 3, response)
        transport.receive_journal = kwargs["receive_journal"]
        transports.append(transport)
        return transport

    monkeypatch.setattr(module, "resolve_codex_bin", lambda: "C:/fake/codex.exe")
    monkeypatch.setattr(module, "CodexSharedAppServerTransport", transport_factory)
    monkeypatch.setattr(state, "codex_shared_attachments", manager)
    monkeypatch.setattr(state, "adapters", adapters)
    monkeypatch.setattr(state, "store", store)
    monkeypatch.setattr(
        state,
        "pipeline",
        SimpleNamespace(
            ingest_event=ingest,
            ingest_shared_codex_event=ingest_shared,
            ingest_observer_lifecycle=ingest,
            retain_shared_codex_observations=retain_shared,
        ),
    )
    monkeypatch.setattr(state, "settings", Settings(home=tmp_path, require_auth=True, token=None))
    monkeypatch.setattr(state, "token", "fixture-only-shared-connection-token")
    body = {
        "socket_path": str(tmp_path / "existing.sock"),
        "thread_id": "thread-1",
        "project_id": "pex-project-namespace",
        "cwd": str(tmp_path),
    }
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://127.0.0.1",
            headers={"Authorization": "Bearer fixture-only-shared-connection-token"},
        ) as client:
            yield client, body, transports, adapters, events, manager
    finally:
        await manager.close_pending()
        for adapter in adapters.all():
            task = getattr(adapter, "_pump_task", None)
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        for transport in transports:
            await transport.close()
        await store.close()


async def _inspect(client, body):
    response = await client.post("/v1/adapters/codex/shared/inspect", json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def _confirm(client, selection):
    return await client.post(
        "/v1/adapters/codex/shared/confirm",
        json={
            "inspection_id": selection["inspection_id"],
            "selection_id": selection["selection_id"],
            "allow_resume": True,
        },
    )


async def _eventually(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(wait(), timeout=2)


@pytest.mark.asyncio
async def test_inspection_is_authenticated_and_does_not_subscribe(shared_client):
    client, body, transports, adapters, _, _ = shared_client
    unauthorized = await client.post(
        "/v1/adapters/codex/shared/inspect", json=body, headers={"Authorization": "Bearer bad"}
    )
    assert unauthorized.status_code == 401
    assert transports == []
    selected = await _inspect(client, body)
    assert selected["project_id"] == "pex-project-namespace"
    assert selected["vendor_project_id"] == "vendor-project-1"
    assert selected["subscribed"] is False
    assert [method for method, _ in transports[0].calls] == ["thread/read"]
    assert adapters.codex.transport is None


@pytest.mark.asyncio
async def test_confirmation_requires_explicit_exact_selection(shared_client):
    client, body, transports, _, _, _ = shared_client
    selected = await _inspect(client, body)
    for change, expected in [({"allow_resume": False}, 400), ({"selection_id": "0" * 64}, 409)]:
        response = await client.post(
            "/v1/adapters/codex/shared/confirm",
            json={
                "inspection_id": selected["inspection_id"],
                "selection_id": selected["selection_id"],
                "allow_resume": True,
                **change,
            },
        )
        assert response.status_code == expected
    assert [method for method, _ in transports[0].calls] == ["thread/read"]


@pytest.mark.asyncio
async def test_confirm_is_idempotent_and_does_not_replay_history(shared_client):
    client, body, transports, adapters, events, _ = shared_client
    selected = await _inspect(client, body)
    response = await _confirm(client, selected)
    assert response.status_code == 200, response.text
    assert response.json()["worker_delivery_enabled"] is False
    again = await _confirm(client, selected)
    assert again.json() == response.json()
    assert [method for method, _ in transports[0].calls].count("thread/resume") == 1
    await asyncio.sleep(0.04)
    assert events == []
    sessions = await adapters.codex.discover_sessions()
    assert sessions[0].last_activity is None
    assert sessions[0].status == SessionStatus.IDLE
    assert (await adapters.codex.probe()).send_message is False


@pytest.mark.asyncio
async def test_live_completed_user_content_and_terminal_error_reach_pipeline(shared_client):
    client, body, transports, adapters, events, _ = shared_client
    selected = await _inspect(client, body)
    assert (await _confirm(client, selected)).status_code == 200
    transport = transports[0]
    transport.notifications.extend(
        [
            _notification("turn/started", {"threadId": "thread-1", "turn": {"id": "turn-1"}}),
            _notification(
                "item/started",
                {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": {
                        "id": "user-1",
                        "type": "userMessage",
                        "content": [{"type": "text", "text": "partial"}],
                    },
                },
            ),
            _notification(
                "item/completed",
                {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": {
                        "id": "user-1",
                        "type": "userMessage",
                        "content": [{"type": "text", "text": "full intent"}],
                    },
                },
            ),
            _notification(
                "turn/completed",
                {
                    "threadId": "thread-1",
                    "turn": {
                        "id": "turn-1",
                        "status": "failed",
                        "error": {"message": "worker failed"},
                    },
                },
            ),
        ]
    )
    await _eventually(lambda: len(events) == 4)
    prompts = [event for event in events if event.event_type == EventType.USER_PROMPT]
    assert [event.message_delta for event in prompts] == ["full intent"]
    assert events[-1].event_type == EventType.STOP
    assert events[-1].phase.value == "terminal"
    assert events[-1].metadata["turn_status"] == "failed"
    assert events[-1].error == "worker failed"
    assert adapters.codex.input_revision == 2
    assert adapters.codex.last_pump_error is None


@pytest.mark.asyncio
async def test_failed_confirmation_preserves_prior_adapter_and_closes_candidate(shared_client):
    client, body, transports, adapters, _, manager = shared_client
    old = adapters.codex
    selected = await _inspect(client, body)
    transports[0].resume["thread"]["id"] = "foreign-thread"
    response = await _confirm(client, selected)
    assert response.status_code == 409
    assert adapters.codex is old
    assert transports[0].closed
    assert manager.pending == {}


@pytest.mark.asyncio
async def test_detach_closes_only_selected_shared_subscription(shared_client):
    client, body, transports, adapters, _, _ = shared_client
    selected = await _inspect(client, body)
    assert (await _confirm(client, selected)).status_code == 200
    response = await client.post(
        "/v1/adapters/codex/shared/detach",
        json={"inspection_id": selected["inspection_id"], "selection_id": selected["selection_id"]},
    )
    assert response.status_code == 200
    assert response.json()["worker_stopped"] is False
    assert transports[0].closed
    assert adapters.codex.transport is None
    assert not any(method.startswith("turn/") for method, _ in transports[0].calls)


@pytest.mark.asyncio
async def test_pending_inspection_expires_and_releases_connection(shared_client, monkeypatch):
    monkeypatch.setattr("pex_bridge.codex_shared_attach.SELECTION_TTL_SECONDS", 0.01)
    client, body, transports, _, _, manager = shared_client
    selected = await _inspect(client, body)
    await _eventually(lambda: transports[0].closed)
    assert manager.pending == {}
    assert (await _confirm(client, selected)).status_code == 409


@pytest.mark.asyncio
async def test_no_replacement_of_an_existing_transport(shared_client):
    client, body, transports, adapters, _, _ = shared_client
    selected = await _inspect(client, body)
    previous = object()
    adapters.codex.transport = previous
    assert (await _confirm(client, selected)).status_code == 409
    assert adapters.codex.transport is previous
    assert not any(method == "thread/resume" for method, _ in transports[0].calls)


@pytest.mark.asyncio
async def test_bounded_backpressure_preserves_a_batch_larger_than_queue(shared_client):
    client, body, transports, adapters, events, _ = shared_client
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked_ingest(event, session):
        entered.set()
        await release.wait()
        events.append(event)

    state.pipeline.ingest_event = blocked_ingest
    selected = await _inspect(client, body)
    assert (await _confirm(client, selected)).status_code == 200
    transports[0].notifications.extend(
        [
            _notification("turn/started", {"threadId": "thread-1", "turn": {"id": f"turn-{i}"}})
            for i in range(300)
        ]
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    await _eventually(lambda: adapters.codex._pending.full())
    assert not adapters.codex._pump_task.done()
    release.set()
    await _eventually(lambda: len(events) == 300)
    assert [event.metadata["vendor_turn_id"] for event in events] == [
        f"turn-{i}" for i in range(300)
    ]
    assert adapters.codex.last_pump_error is None


@pytest.mark.asyncio
async def test_transient_ingest_failure_retries_the_exact_event(shared_client):
    client, body, transports, adapters, events, _ = shared_client
    attempts = []

    async def flaky_ingest(event, session):
        attempts.append(event.model_dump(mode="json"))
        if len(attempts) == 1:
            raise RuntimeError("fixture transient storage failure")
        events.append(event)

    state.pipeline.ingest_event = flaky_ingest
    selected = await _inspect(client, body)
    assert (await _confirm(client, selected)).status_code == 200
    transports[0].notifications.append(
        _notification("turn/started", {"threadId": "thread-1", "turn": {"id": "turn-1"}})
    )
    await _eventually(lambda: len(events) == 1)
    assert attempts[0] == attempts[1]
    assert adapters.codex.last_pump_error is None


@pytest.mark.asyncio
async def test_operator_mutations_reject_disabled_auth(shared_client, monkeypatch):
    client, body, transports, adapters, _, _ = shared_client
    selected = await _inspect(client, body)
    monkeypatch.setattr(
        state, "settings", Settings.for_test(home=state.settings.home, require_auth=False)
    )
    assert (await _confirm(client, selected)).status_code == 403
    response = await client.post(
        "/v1/adapters/codex/shared/detach",
        json={key: selected[key] for key in ("inspection_id", "selection_id")},
    )
    assert response.status_code == 403
    assert adapters.codex.transport is None
    assert not any(method == "thread/resume" for method, _ in transports[0].calls)


@pytest.mark.asyncio
async def test_inspection_rejects_unbound_project_label(shared_client):
    client, body, transports, adapters, _, manager = shared_client
    response = await client.post(
        "/v1/adapters/codex/shared/inspect", json={**body, "project_id": "unbound"}
    )
    assert response.status_code == 409
    assert transports == []  # Reject workspace authority before creating a connector.
    assert manager.pending == {}
    assert adapters.codex.transport is None


@pytest.mark.asyncio
async def test_expiry_while_authority_read_is_in_flight_cannot_resume(shared_client, monkeypatch):
    client, body, transports, _, _, manager = shared_client
    selected = await _inspect(client, body)
    original = state.store.project_id_matches_binding

    async def expire_during_read(*args, **kwargs):
        manager.pending[selected["inspection_id"]].deadline = 0
        return await original(*args, **kwargs)

    monkeypatch.setattr(state.store, "project_id_matches_binding", expire_during_read)
    assert (await _confirm(client, selected)).status_code == 409
    assert transports[0].closed
    assert not any(method == "thread/resume" for method, _ in transports[0].calls)


@pytest.mark.asyncio
async def test_detach_exact_retry_is_idempotent(shared_client):
    client, body, transports, adapters, _, _ = shared_client
    selected = await _inspect(client, body)
    assert (await _confirm(client, selected)).status_code == 200
    request = {key: selected[key] for key in ("inspection_id", "selection_id")}
    first = await client.post("/v1/adapters/codex/shared/detach", json=request)
    replacement = adapters.codex
    count = len(transports[0].calls)
    second = await client.post("/v1/adapters/codex/shared/detach", json=request)
    assert first.status_code == second.status_code == 200
    assert second.json() == {**first.json(), "replayed": True}
    assert adapters.codex is replacement
    assert len(transports[0].calls) == count
    stale = await client.post(
        "/v1/adapters/codex/shared/detach", json={**request, "selection_id": "0" * 64}
    )
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_shutdown_retires_active_and_pending_connections(shared_client):
    client, body, transports, _, _, manager = shared_client
    selected = await _inspect(client, body)
    assert (await _confirm(client, selected)).status_code == 200
    await _inspect(client, body)
    active_adapter = manager.active[2]
    await manager.close_pending()
    assert manager.pending == {} and manager.active is None
    assert all(transport.closed for transport in transports)
    assert active_adapter._pump_task.done()
    assert (await _confirm(client, selected)).status_code == 409
    response = await client.post("/v1/adapters/codex/shared/inspect", json=body)
    assert response.status_code == 409
    assert len(transports) == 2


@pytest.mark.asyncio
async def test_confirmation_rejects_registry_change_during_authority_read(
    shared_client, monkeypatch
):
    from pex_bridge.adapters.codex import CodexAdapter

    client, body, transports, adapters, _, _ = shared_client
    selected = await _inspect(client, body)
    original = state.store.project_id_matches_binding
    replacement = CodexAdapter()

    async def replace_during_read(*args, **kwargs):
        adapters.bind("codex", replacement)
        return await original(*args, **kwargs)

    monkeypatch.setattr(state.store, "project_id_matches_binding", replace_during_read)
    assert (await _confirm(client, selected)).status_code == 409
    assert adapters.codex is replacement
    assert not any(method == "thread/resume" for method, _ in transports[0].calls)


@pytest.mark.asyncio
async def test_attachment_publishes_over_historical_activity_without_inventing_new_activity(
    shared_client,
):
    client, body, _, adapters, events, _ = shared_client
    observed_at = datetime(2026, 1, 1, tzinfo=UTC)
    historical = HarnessSession(
        id="codex:thread-1",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-1",
        project_id=body["project_id"],
        cwd=body["cwd"],
        status=SessionStatus.DETACHED,
        last_activity=observed_at,
        supervision_paused=True,
    )
    await state.store.upsert_session(historical)
    selected = await _inspect(client, body)
    response = await _confirm(client, selected)
    assert response.status_code == 200, response.text
    canonical = await state.store.get_session_for_authority(historical.id)
    assert canonical.status == SessionStatus.IDLE
    assert canonical.last_activity == observed_at
    assert canonical.supervision_paused is True
    assert (
        canonical.metadata["subscription_receipt"]["authorization_id"] == selected["inspection_id"]
    )
    assert adapters.codex.session == canonical
    assert adapters.codex.sessions[canonical.id] is adapters.codex.session
    assert adapters.codex._normalizer.sessions[canonical.id] is adapters.codex.session
    assert events == []


@pytest.mark.asyncio
async def test_pause_during_resume_invalidates_attachment_cas(shared_client, monkeypatch):
    client, body, transports, adapters, _, _ = shared_client
    historical = HarnessSession(
        id="codex:thread-1",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-1",
        project_id=body["project_id"],
        cwd=body["cwd"],
        status=SessionStatus.DETACHED,
    )
    await state.store.upsert_session(historical)
    old = adapters.codex
    selected = await _inspect(client, body)
    original = transports[0].request

    async def pause_during_resume(method, params):
        if method == "thread/resume":
            historical.supervision_paused = True
            await state.store.upsert_session(historical, allow_supervision_change=True)
        return await original(method, params)

    monkeypatch.setattr(transports[0], "request", pause_during_resume)
    response = await _confirm(client, selected)
    assert response.status_code == 409
    assert adapters.codex is old
    assert transports[0].closed
    canonical = await state.store.get_session_for_authority(historical.id)
    assert canonical.supervision_paused is True
    assert canonical.status == SessionStatus.DETACHED
    assert "subscription_receipt" not in canonical.metadata


@pytest.mark.asyncio
async def test_detach_storage_failure_is_secret_free_and_retryable(shared_client, monkeypatch):
    client, body, transports, adapters, _, manager = shared_client
    selected = await _inspect(client, body)
    assert (await _confirm(client, selected)).status_code == 200
    original = state.store.publish_observer_session

    async def fail_publication(*args, **kwargs):
        raise ValueError("fixture-private-exception")

    request = {key: selected[key] for key in ("inspection_id", "selection_id")}
    monkeypatch.setattr(state.store, "publish_observer_session", fail_publication)
    failed = await client.post("/v1/adapters/codex/shared/detach", json=request)
    assert failed.status_code == 409
    assert "fixture-private-exception" not in failed.text
    assert transports[0].closed
    assert manager.active is not None and manager.active[2] is adapters.codex
    monkeypatch.setattr(state.store, "publish_observer_session", original)
    retry = await client.post("/v1/adapters/codex/shared/detach", json=request)
    assert retry.status_code == 200, retry.text
    assert manager.active is None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["confirm", "detach"])
async def test_cancel_after_commit_settles_publication_before_releasing_lock(
    shared_client, monkeypatch, operation
):
    client, body, transports, adapters, _, manager = shared_client
    selected = await _inspect(client, body)
    if operation == "detach":
        assert (await _confirm(client, selected)).status_code == 200
    previous = adapters.codex
    previous_task = None
    if operation == "confirm":
        started = asyncio.Event()

        async def local_discovery_only():
            started.set()
            return []

        monkeypatch.setattr(previous, "discover_sessions", local_discovery_only)
        previous_task = previous.start_pipeline_pump(state.pipeline.ingest_event)
        await asyncio.wait_for(started.wait(), 2)
    original = state.store.publish_observer_session
    committed, release = asyncio.Event(), asyncio.Event()

    async def delayed_return(*args, **kwargs):
        result = await original(*args, **kwargs)
        committed.set()
        await release.wait()
        return result

    monkeypatch.setattr(state.store, "publish_observer_session", delayed_return)
    selection = {key: selected[key] for key in ("inspection_id", "selection_id")}
    request = (
        manager.confirm(
            SharedCodexConfirm(
                **selection,
                allow_resume=True,
            ),
            state,
        )
        if operation == "confirm"
        else manager.detach(SharedCodexSelection(**selection), state)
    )
    task = asyncio.create_task(request)
    await asyncio.wait_for(committed.wait(), 2)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    assert manager.lock.locked()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    if operation == "confirm":
        assert manager.active is not None
        assert manager.active[2] is adapters.codex
        assert not transports[0].closed
        assert previous._pump_task is previous_task
        assert previous_task.done()
        assert (await _confirm(client, selected)).status_code == 200
    else:
        assert manager.active is None
        assert adapters.codex.transport is None
        assert transports[0].closed
        retry = await client.post("/v1/adapters/codex/shared/detach", json=selection)
        assert retry.status_code == 200
        assert retry.json()["replayed"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["store", "cancel", "registry_replaced"])
async def test_failed_shared_publication_restores_only_its_stopped_bare_pump(
    shared_client, monkeypatch, failure
):
    from pex_bridge.adapters.codex import CodexAdapter

    client, body, transports, adapters, _, manager = shared_client
    old = adapters.codex
    entered = asyncio.Event()

    async def local_discovery_only():
        entered.set()
        return []

    # Exercise the real pump loop, with no desktop session/process inspection.
    monkeypatch.setattr(old, "discover_sessions", local_discovery_only)
    old_task = old.start_pipeline_pump(state.pipeline.ingest_event)
    await asyncio.wait_for(entered.wait(), 2)
    selected = await _inspect(client, body)
    replacement = CodexAdapter()
    original_publication = state.store.publish_observer_session

    async def fail_publication(*args, **kwargs):
        assert old_task.done()
        if failure == "registry_replaced":
            adapters.bind("codex", replacement)
        if failure == "cancel":
            raise asyncio.CancelledError
        if failure == "store":
            import aiosqlite

            async def fail_commit(connection):
                raise ValueError("fixture commit refused")

            with monkeypatch.context() as isolated:
                isolated.setattr(aiosqlite.Connection, "commit", fail_commit)
                return await original_publication(*args, **kwargs)
        raise ValueError("fixture publication refused")

    monkeypatch.setattr(state.store, "publish_observer_session", fail_publication)
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await manager.confirm(
                SharedCodexConfirm(
                    inspection_id=selected["inspection_id"],
                    selection_id=selected["selection_id"],
                    allow_resume=True,
                ),
                state,
            )
    else:
        assert (await _confirm(client, selected)).status_code == 409
    assert transports[0].closed
    assert manager.active is None
    assert await state.store.get_session("codex:thread-1") is None
    assert old_task.done()
    if failure == "registry_replaced":
        assert adapters.codex is replacement
        assert old._pump_task is old_task
    else:
        assert adapters.codex is old
        assert old.transport is None
        assert old._pump_task is not old_task
        assert not old._pump_task.done()
