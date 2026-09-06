"""Workspace-bound live observation with real Pipeline/Store and no real models.

Only temporary directories and the in-memory vendor are used. Workspace snapshot
and supervisor calls are spies; no native subprocess or provider is invoked.
"""

import asyncio
import threading
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pex_bridge import pipeline as pipeline_module
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.local_origin_config import load_local_origin_choice, save_local_origin_choice
from pex_bridge.local_workspace import measure_local_directory
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_bridge.workspace_binding import WorkspaceAuthorityError, WorkspaceBinding
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, EventType
from pex_protocol.goal import Goal
from pex_protocol.project_identity import ProjectLocator, ProjectOrigin
from pex_protocol.supervisor import SupervisorResult
from test_codex_subscription import _notification, _subscribed

FIXTURE_CLEANUP_TIMEOUT_SECONDS = 5


def _task_location(task: asyncio.Task) -> str:
    state = "cancelled" if task.cancelled() else "done" if task.done() else "pending"
    frames = task.get_stack(limit=3)
    if not frames:
        return f"{state}:no Python stack"
    location = " -> ".join(
        f"{frame.f_code.co_name}:{frame.f_lineno}" for frame in frames
    )
    return f"{state}:{location}"


def _pump_cleanup_locations(adapter) -> str:
    cleanup = getattr(adapter, "_cleanup_task", None)
    if not isinstance(cleanup, asyncio.Task):
        return "cleanup=absent"
    locations = [f"cleanup={_task_location(cleanup)}"]
    for frame in cleanup.get_stack(limit=1):
        for label in ("receiver", "consumer"):
            child = frame.f_locals.get(label)
            if isinstance(child, asyncio.Task):
                locations.append(f"{label}={_task_location(child)}")
    return ", ".join(locations)


async def _cleanup_bound_pipeline(*, task, adapter, transport, pipeline, store) -> None:
    """Bound fixture cleanup that attempts every resource after an earlier failure."""

    failures: list[str] = []
    first_join_timed_out = False
    unsettled: list[tuple[str, asyncio.Task]] = []

    async def join_pump() -> bool:
        done, _ = await asyncio.wait({task}, timeout=FIXTURE_CLEANUP_TIMEOUT_SECONDS)
        if not done:
            return False
        try:
            task.result()
        except asyncio.CancelledError:
            # The owned pump normally re-raises cancellation after its shielded cleanup.
            pass
        except Exception as exc:
            failures.append(f"pump={type(exc).__name__}")
        return True

    task.cancel()
    if not await join_pump():
        first_join_timed_out = True

    async def attempt(label, cleanup) -> None:
        cleanup_task = asyncio.create_task(cleanup(), name=f"fixture-cleanup-{label}")
        done, _ = await asyncio.wait(
            {cleanup_task}, timeout=FIXTURE_CLEANUP_TIMEOUT_SECONDS
        )
        if not done:
            cleanup_task.cancel()
            unsettled.append((label, cleanup_task))
            failures.append(f"{label}=TimeoutError ({_task_location(cleanup_task)})")
            return
        try:
            cleanup_task.result()
        except asyncio.CancelledError:
            failures.append(f"{label}=CancelledError")
        except Exception as exc:
            failures.append(f"{label}={type(exc).__name__}")

    # Closing the transport can release a pump that is settling an uncertain write.
    await attempt("transport", transport.close)
    if first_join_timed_out:
        if not task.done():
            task.cancel()
        if not await join_pump():
            failures.append(
                "pump=TimeoutError "
                f"({_task_location(task)}; {_pump_cleanup_locations(adapter)})"
            )
    await attempt("presentations", pipeline.close_presentations)
    await attempt("store", store.close)

    # Production cleanup deliberately shields its own ledger finalizer. Once all
    # resource closes have been attempted, a failed fixture must explicitly reap
    # that owned child rather than return it to pytest's event-loop finalizer.
    if not task.done():
        owned_cleanup = getattr(adapter, "_cleanup_task", None)
        if isinstance(owned_cleanup, asyncio.Task):
            if not owned_cleanup.done():
                owned_cleanup.cancel()
                done, _ = await asyncio.wait(
                    {owned_cleanup}, timeout=FIXTURE_CLEANUP_TIMEOUT_SECONDS
                )
            else:
                done = {owned_cleanup}
            if done:
                try:
                    owned_cleanup.result()
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    failures.append(f"pump_cleanup={type(exc).__name__}")
            else:
                failures.append(
                    f"pump_cleanup=TimeoutError ({_task_location(owned_cleanup)})"
                )
        task.cancel()
        if not await join_pump():
            failures.append(f"pump_final=TimeoutError ({_task_location(task)})")

    if unsettled:
        done, pending = await asyncio.wait(
            {cleanup_task for _, cleanup_task in unsettled},
            timeout=FIXTURE_CLEANUP_TIMEOUT_SECONDS,
        )
        labels = {cleanup_task: label for label, cleanup_task in unsettled}
        for cleanup_task in done:
            try:
                cleanup_task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                failures.append(
                    f"{labels[cleanup_task]}_late={type(exc).__name__}"
                )
        for cleanup_task in pending:
            cleanup_task.cancel()
        if pending:
            reaped, still_pending = await asyncio.wait(
                pending, timeout=FIXTURE_CLEANUP_TIMEOUT_SECONDS
            )
            for cleanup_task in reaped:
                try:
                    cleanup_task.result()
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    failures.append(
                        f"{labels[cleanup_task]}_late={type(exc).__name__}"
                    )
            for cleanup_task in still_pending:
                failures.append(
                    f"{labels[cleanup_task]}_unreaped=TimeoutError "
                    f"({_task_location(cleanup_task)})"
                )

    if failures:
        prefix = "pump needed transport close; " if first_join_timed_out else ""
        raise AssertionError(f"bounded fixture cleanup failed: {prefix}{'; '.join(failures)}")


@pytest.mark.asyncio
async def test_bound_fixture_cleanup_releases_pump_then_attempts_every_stage(monkeypatch):
    monkeypatch.setattr(
        __import__(__name__), "FIXTURE_CLEANUP_TIMEOUT_SECONDS", 0.02
    )
    release = asyncio.Event()
    started = asyncio.Event()
    attempted: list[str] = []

    async def pump() -> None:
        started.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                # Model a production pump settling shielded delivery cleanup.
                continue

    async def close_transport() -> None:
        attempted.append("transport")
        release.set()

    async def close_presentations() -> None:
        attempted.append("presentations")

    async def close_store() -> None:
        attempted.append("store")

    task = asyncio.create_task(pump())
    await started.wait()
    await _cleanup_bound_pipeline(
        task=task,
        adapter=SimpleNamespace(_cleanup_task=None),
        transport=SimpleNamespace(close=close_transport),
        pipeline=SimpleNamespace(close_presentations=close_presentations),
        store=SimpleNamespace(close=close_store),
    )
    assert task.done()
    assert attempted == ["transport", "presentations", "store"]


@pytest.mark.asyncio
async def test_bound_fixture_cleanup_attempts_later_stages_after_failures():
    attempted: list[str] = []

    async def pump() -> None:
        raise RuntimeError("pump")

    def failing_cleanup(label):
        async def cleanup() -> None:
            attempted.append(label)
            raise RuntimeError(label)

        return cleanup

    task = asyncio.create_task(pump())
    await asyncio.sleep(0)
    with pytest.raises(
        AssertionError,
        match="pump=RuntimeError.*transport=RuntimeError.*presentations=RuntimeError",
    ):
        await _cleanup_bound_pipeline(
            task=task,
            adapter=SimpleNamespace(_cleanup_task=None),
            transport=SimpleNamespace(close=failing_cleanup("transport")),
            pipeline=SimpleNamespace(
                close_presentations=failing_cleanup("presentations")
            ),
            store=SimpleNamespace(close=failing_cleanup("store")),
        )
    assert attempted == ["transport", "presentations", "store"]


@pytest.mark.asyncio
async def test_bound_fixture_cleanup_reaps_initially_cancellation_resistant_stage(
    monkeypatch,
):
    monkeypatch.setattr(
        __import__(__name__), "FIXTURE_CLEANUP_TIMEOUT_SECONDS", 0.02
    )
    release = asyncio.Event()
    attempted: list[str] = []

    async def pump() -> None:
        await asyncio.Event().wait()

    async def close_transport() -> None:
        attempted.append("transport")
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                continue

    async def close_presentations() -> None:
        attempted.append("presentations")
        release.set()

    async def close_store() -> None:
        attempted.append("store")

    task = asyncio.create_task(pump())
    with pytest.raises(AssertionError, match="transport=TimeoutError"):
        await _cleanup_bound_pipeline(
            task=task,
            adapter=SimpleNamespace(_cleanup_task=None),
            transport=SimpleNamespace(close=close_transport),
            pipeline=SimpleNamespace(close_presentations=close_presentations),
            store=SimpleNamespace(close=close_store),
        )
    assert attempted == ["transport", "presentations", "store"]
    assert not [
        pending
        for pending in asyncio.all_tasks()
        if pending.get_name() == "fixture-cleanup-transport" and not pending.done()
    ]


@pytest.mark.asyncio
async def test_bound_fixture_reports_already_finished_cleanup_error(monkeypatch):
    monkeypatch.setattr(__import__(__name__), "FIXTURE_CLEANUP_TIMEOUT_SECONDS", 0.02)
    started = asyncio.Event()

    async def pump():
        started.set()
        cancellations = 0
        while cancellations < 3:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancellations += 1

    async def failed_cleanup():
        raise RuntimeError("owned cleanup failed before fixture inspection")

    async def close():
        return None

    task = asyncio.create_task(pump())
    owned_cleanup = asyncio.create_task(failed_cleanup())
    await started.wait()
    await asyncio.wait({owned_cleanup}, timeout=1)
    try:
        with pytest.raises(AssertionError, match="pump_cleanup=RuntimeError"):
            await _cleanup_bound_pipeline(
                task=task, adapter=SimpleNamespace(_cleanup_task=owned_cleanup),
                transport=SimpleNamespace(close=close),
                pipeline=SimpleNamespace(close_presentations=close),
                store=SimpleNamespace(close=close),
            )
        assert task.done()
    finally:
        # Reap both owned tasks even when testing a regressed cleanup helper.
        for _ in range(3):
            if task.done():
                break
            task.cancel()
            await asyncio.wait({task}, timeout=0.1)
        for child in (task, owned_cleanup):
            if child.done():
                try:
                    child.result()
                except (asyncio.CancelledError, RuntimeError):
                    pass


@pytest.fixture
async def bound_pipeline(tmp_path, monkeypatch):
    transport = adapter = store = pipeline = task = None
    try:
        workspace = tmp_path / "worker-workspace"
        workspace.mkdir()
        origin_path = tmp_path / "local-origin.json"
        choice = save_local_origin_choice(
            origin_path, ProjectOrigin(namespace="machine", host="continuity-fixture"),
            expected_revision=None, expected_choice_id=None,
        )
        directory = measure_local_directory(str(workspace))
        coordinator, transport = await _subscribed(workspace)
        adapter = CodexSharedAdapter(coordinator)
        locator = ProjectLocator.path(
            str(workspace), platform=directory.platform, origin=choice.origin,
            physical=directory.physical,
        )
        store = Store(tmp_path / "continuity.sqlite")
        await store.connect()
        await store.register_project_locator(
            legacy_project_id=adapter.session.project_id, locator=locator,
        )
        binding = await store.project_binding_for_authority(adapter.session.project_id)
        workspace_binding = WorkspaceBinding(
            project_id=adapter.session.project_id, project_binding=binding,
            origin_choice=choice, directory=directory, locator=locator,
        )
        adapter.session.metadata["workspace_binding"] = workspace_binding.model_dump(mode="json")
        now = datetime.now(UTC)
        goal = Goal(
            id="workspace-continuity-goal", project_id=adapter.session.project_id,
            title="Observe the selected worker", objective="Inspect only the selected workspace.",
            created_at=now, updated_at=now,
        )
        await store.upsert_goal(goal)
        canonical = await store.publish_observer_session(
            adapter.session, expected_control_revision=None,
            expected_project_binding=binding, expected_workspace=workspace_binding,
            local_origin_path=origin_path,
        )
        # The observer cannot assign human controls; attach the actual goal through
        # the separate user-control transaction after observation publication.
        await store.attach_session_goal(canonical.id, goal.id, expected_goal_id=None)
        canonical = await store.get_session(canonical.id)
        adapter.session = canonical
        adapter.sessions[canonical.id] = canonical
        adapter._normalizer.sessions[canonical.id] = canonical
        registry = AdapterRegistry()
        registry.bind("codex", adapter)
        pipeline = Pipeline(
            store, registry, EventBus(), Settings.for_test(home=tmp_path, require_auth=False),
        )
        snapshots, supervisor_calls = [], []

        def snapshot_spy(cwd, *, run_pytest=False):
            assert run_pytest is False
            snapshots.append(measure_local_directory(cwd))
            return {"files": [], "git_diff": ""}

        class NoopSupervisorSpy:
            agentcore = None

            async def decide(self, request, *, local_model):
                supervisor_calls.append(request.model_copy(deep=True))
                return SupervisorResult(
                    action=ProposedAction(
                        type=InterventionType.NOOP, session_id=request.session.id,
                        goal_id=request.session.goal_id,
                        rationale="Test spy observed no reason to intervene.",
                        evidence=[request.event.event_id], confidence=0.9,
                        risk=RiskLevel.NONE, authority_required=Authority.LOCAL_POLICY,
                    ),
                    diagnosis="test_spy_noop",
                )

        monkeypatch.setattr(pipeline_module, "snapshot", snapshot_spy)
        pipeline.supervisor = NoopSupervisorSpy()
        task = adapter.start_pipeline_pump(
            pipeline.ingest_shared_codex_event,
            lifecycle_ingest=pipeline.ingest_observer_lifecycle,
            retention_ingest=pipeline.retain_shared_codex_observations,
        )
        yield SimpleNamespace(
            pipeline=pipeline, store=store, adapter=adapter, transport=transport,
            task=task, workspace=workspace, origin_path=origin_path,
            directory=directory, snapshots=snapshots, supervisor_calls=supervisor_calls,
            workspace_binding=workspace_binding,
        )
    finally:
        if task is not None:
            await _cleanup_bound_pipeline(
                task=task, adapter=adapter, transport=transport,
                pipeline=pipeline, store=store,
            )
        else:
            async def noop() -> None:
                return None

            settled = asyncio.create_task(noop())
            await settled
            await _cleanup_bound_pipeline(
                task=settled,
                adapter=adapter or SimpleNamespace(_cleanup_task=None),
                transport=transport or SimpleNamespace(close=noop),
                pipeline=pipeline or SimpleNamespace(close_presentations=noop),
                store=store or SimpleNamespace(close=noop),
            )


@pytest.mark.asyncio
async def test_bound_fixture_closes_partial_resources_after_setup_failure(
    tmp_path, monkeypatch,
):
    transports = []
    stores_closed = []
    original_subscribed = _subscribed
    original_store_close = Store.close

    async def observed_subscribed(workspace):
        coordinator, transport = await original_subscribed(workspace)
        transports.append(transport)
        return coordinator, transport

    async def fail_registration(self, **_kwargs):
        raise RuntimeError("injected base fixture setup failure")

    async def observed_store_close(self):
        stores_closed.append(self)
        await original_store_close(self)

    monkeypatch.setattr(__import__(__name__), "_subscribed", observed_subscribed)
    monkeypatch.setattr(Store, "register_project_locator", fail_registration)
    monkeypatch.setattr(Store, "close", observed_store_close)
    fixture = bound_pipeline.__wrapped__(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="injected base fixture setup failure"):
        await anext(fixture)
    assert len(transports) == 1 and transports[0].closed is True
    assert len(stores_closed) == 1


def _change_origin(bound):
    choice = load_local_origin_choice(bound.origin_path)
    save_local_origin_choice(
        bound.origin_path, choice.origin,
        expected_revision=choice.revision, expected_choice_id=choice.choice_id,
    )


def _change_workspace(bound, change):
    if change == "origin":
        _change_origin(bound)
        return
    original = bound.workspace.with_name("preserved-original-workspace")
    bound.workspace.rename(original)
    bound.workspace.mkdir()
    assert measure_local_directory(str(original)).physical == bound.directory.physical


async def _terminal_observation(bound):
    bound.transport.notifications.append(_notification("turn/completed", {
        "threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"},
    }))

    async def wait():
        while True:
            events = await bound.store.recent_events(bound.adapter.session.id)
            for event in events:
                if event.event_type == EventType.STOP:
                    processing = await bound.store.get_event_processing(event.event_id)
                    if processing["state"] in {"complete", "failed", "record_only_complete"}:
                        return event, processing
            await asyncio.sleep(0.01)

    try:
        return await asyncio.wait_for(wait(), timeout=10)
    except TimeoutError:
        states = []
        for event in await bound.store.recent_events(bound.adapter.session.id):
            if event.event_type == EventType.STOP:
                processing = await bound.store.get_event_processing(event.event_id)
                planner = await bound.store.get_event_effect(event.event_id, "planner")
                states.append((processing["state"], planner and planner["state"]))
        pytest.fail(
            f"STOP did not settle: states={states}, "
            f"pump_error={bound.adapter.last_pump_error}, "
            f"model_calls={len(bound.supervisor_calls)}"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["directory", "origin"])
async def test_changed_attached_workspace_retains_stop_without_evidence_or_model(
    bound_pipeline, change,
):
    bound = bound_pipeline
    _change_workspace(bound, change)
    event, processing = await _terminal_observation(bound)
    assert bound.snapshots == []
    assert bound.supervisor_calls == []
    assert processing["state"] in {"record_only_complete", "failed"}
    assert await bound.store.get_event(event.event_id) is not None
    assert await bound.store.list_interventions(bound.adapter.session.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["directory", "origin"])
async def test_change_during_snapshot_rejects_result_before_supervisor(
    bound_pipeline, monkeypatch, change,
):
    bound = bound_pipeline
    original_snapshot = pipeline_module.snapshot

    def changed_after_snapshot(cwd, *, run_pytest=False):
        result = original_snapshot(cwd, run_pytest=run_pytest)
        # This runs in the snapshot worker thread, after collecting its result
        # but before the awaiting Pipeline can use it as current evidence.
        _change_workspace(bound, change)
        return result

    monkeypatch.setattr(pipeline_module, "snapshot", changed_after_snapshot)
    event, processing = await _terminal_observation(bound)
    assert bound.snapshots == [bound.directory]
    assert bound.supervisor_calls == []
    assert processing["mode"] == "pipeline" and processing["state"] == "failed"
    assert processing["receipt"]["intervention"] is None
    assert await bound.store.get_event(event.event_id) is not None
    planner = await bound.store.get_event_effect(event.event_id, "planner")
    assert planner is None or planner["state"] == "skipped"
    assert await bound.store.list_interventions(bound.adapter.session.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["directory", "origin"])
async def test_change_during_supervisor_preserves_call_receipt_without_downstream_effects(
    bound_pipeline, monkeypatch, change,
):
    bound = bound_pipeline
    original_decide = bound.pipeline.supervisor.decide

    async def changed_during_call(request, *, local_model):
        result = await original_decide(request, local_model=local_model)
        _change_workspace(bound, change)
        await asyncio.sleep(0)
        return result

    monkeypatch.setattr(bound.pipeline.supervisor, "decide", changed_during_call)
    event, processing = await _terminal_observation(bound)
    assert bound.snapshots == [bound.directory]
    assert len(bound.supervisor_calls) == 1  # It happened; never claim no model call.
    planner = await bound.store.get_event_effect(event.event_id, "planner")
    assert planner is not None and planner["state"] in {"delivered", "delivery_uncertain"}
    assert planner["result"] is not None
    assert processing["state"] in {"failed", "complete"}
    assert processing["receipt"]["intervention"] is None
    assert "workspace" in str(processing["receipt"]).lower()
    assert await bound.store.list_interventions(bound.adapter.session.id) == []
    effects = await bound.store.db.execute(
        "SELECT effect_key FROM event_effects WHERE event_id = ?", (event.event_id,),
    )
    assert [row["effect_key"] for row in await effects.fetchall()] == ["planner"]
    # The observed STOP survives even though its planner output lost authority.
    assert await bound.store.get_event(event.event_id) is not None
    assert await bound.pipeline._drain_event_processing(event.event_id) is None
    assert len(bound.supervisor_calls) == 1
    assert await bound.store.get_event_effect(event.event_id, "planner") == planner


@pytest.mark.asyncio
async def test_removed_selected_locator_retains_stop_without_workspace_inspection(bound_pipeline):
    bound = bound_pipeline
    await bound.store.db.execute(
        "DELETE FROM project_locators WHERE fingerprint = ?",
        (bound.workspace_binding.locator.fingerprint,),
    )
    await bound.store.db.commit()
    event, processing = await _terminal_observation(bound)
    assert bound.snapshots == []
    assert bound.supervisor_calls == []
    assert processing["state"] in {"record_only_complete", "failed"}
    assert await bound.store.get_event(event.event_id) is not None
    assert await bound.store.list_interventions(bound.adapter.session.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("edit", [False, True])
async def test_unchanged_directory_identity_still_processes_real_stop(bound_pipeline, edit):
    bound = bound_pipeline
    if edit:
        (bound.workspace / "ordinary-new-subdirectory").mkdir()
    _, processing = await _terminal_observation(bound)
    assert processing["mode"] == "pipeline" and processing["state"] == "complete"
    assert bound.snapshots == [bound.directory]
    assert len(bound.supervisor_calls) == 1


@pytest.mark.asyncio
async def test_origin_change_after_acceptance_terminalizes_without_planner(
    bound_pipeline, monkeypatch,
):
    bound = bound_pipeline
    original = bound.pipeline._build_and_commit_event_plan

    async def changed_before_plan(processing, **kwargs):
        _change_origin(bound)
        return await original(processing, **kwargs)

    monkeypatch.setattr(bound.pipeline, "_build_and_commit_event_plan", changed_before_plan)
    event, processing = await _terminal_observation(bound)
    assert bound.snapshots == []
    assert bound.supervisor_calls == []
    assert processing["mode"] == "pipeline" and processing["state"] == "failed"
    assert processing["receipt"]["intervention"] is None
    assert await bound.store.get_event(event.event_id) is not None
    assert await bound.pipeline._drain_event_processing(event.event_id) is None
    assert bound.snapshots == [] and bound.supervisor_calls == []


@pytest.mark.asyncio
async def test_typed_workspace_loss_exits_adapter_retry_and_retains_pending_record(
    bound_pipeline, monkeypatch,
):
    bound = bound_pipeline
    attempts = 0

    async def revoked_acceptance(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise WorkspaceAuthorityError("injected pre-accept workspace revocation")

    monkeypatch.setattr(bound.store, "accept_pipeline_event", revoked_acceptance)
    _, processing = await _terminal_observation(bound)
    await asyncio.wait_for(asyncio.shield(bound.task), timeout=5)
    assert attempts == 1
    assert bound.adapter._invalid and bound.transport.closed
    assert processing["mode"] == "record_only"
    assert processing["state"] == "record_only_complete"
    assert bound.snapshots == [] and bound.supervisor_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["directory", "origin"])
async def test_queued_snapshot_checks_workspace_when_read_actually_starts(
    bound_pipeline, monkeypatch, change,
):
    bound = bound_pipeline
    queued, release = asyncio.Event(), asyncio.Event()
    original_to_thread = asyncio.to_thread

    async def delayed_thread(function, *args, **kwargs):
        queued.set()
        await release.wait()
        return await original_to_thread(function, *args, **kwargs)

    # Hold dispatch before the worker closure starts, exactly where the initial
    # async Store sample alone would leave an executor-queue race.
    monkeypatch.setattr(pipeline_module.asyncio, "to_thread", delayed_thread)
    observation = asyncio.create_task(_terminal_observation(bound))
    try:
        await asyncio.wait_for(queued.wait(), timeout=5)
        _change_workspace(bound, change)
        release.set()
        event, processing = await observation
        assert bound.snapshots == [] and bound.supervisor_calls == []
        assert processing["state"] == "failed"
        assert processing["receipt"]["intervention"] is None
        assert await bound.store.get_event(event.event_id) is not None
    finally:
        release.set()
        if not observation.done():
            observation.cancel()
        await asyncio.gather(observation, return_exceptions=True)


@pytest.mark.asyncio
async def test_snapshot_cancellation_settles_owned_read_before_return(
    bound_pipeline, monkeypatch,
):
    bound = bound_pipeline
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_snapshot = pipeline_module.snapshot

    def held_snapshot(cwd, *, run_pytest=False):
        started.set()
        try:
            if not release.wait(timeout=5):
                raise AssertionError("test did not release the owned snapshot read")
            return original_snapshot(cwd, run_pytest=run_pytest)
        finally:
            finished.set()

    monkeypatch.setattr(pipeline_module, "snapshot", held_snapshot)
    operation = asyncio.create_task(bound.pipeline._snapshot_for_session(bound.adapter.session))
    try:
        async def wait_for_start():
            while not started.is_set():
                await asyncio.sleep(0.01)

        await asyncio.wait_for(wait_for_start(), timeout=5)
        operation.cancel()
        await asyncio.sleep(0.02)
        assert not operation.done() and not finished.is_set()
        # Repeated cancellation must not let the surviving filesystem thread
        # escape the operation's ownership either.
        operation.cancel()
        await asyncio.sleep(0.02)
        assert not operation.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(operation, timeout=5)
        assert finished.is_set()
        assert bound.snapshots == [bound.directory]
        assert bound.supervisor_calls == []
    finally:
        release.set()
        await asyncio.gather(operation, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["directory", "origin"])
async def test_queued_supervisor_rechecks_before_actual_invocation(
    bound_pipeline, monkeypatch, change,
):
    bound = bound_pipeline
    original_invoke = bound.pipeline._invoke_supervisor
    changed = asyncio.Event()

    async def queued_invocation(*args, **kwargs):
        def revoke_before_scheduled_model():
            _change_workspace(bound, change)
            changed.set()

        # wait_for schedules the supervisor coroutine as another task. This
        # callback runs first, after the Store sample but before that task starts.
        asyncio.get_running_loop().call_soon(revoke_before_scheduled_model)
        return await original_invoke(*args, **kwargs)

    monkeypatch.setattr(bound.pipeline, "_invoke_supervisor", queued_invocation)
    event, processing = await _terminal_observation(bound)
    assert changed.is_set()
    assert bound.snapshots == [bound.directory]
    assert bound.supervisor_calls == []
    planner = await bound.store.get_event_effect(event.event_id, "planner")
    assert planner["state"] == "failed"
    assert planner["result"] == {
        "status": "failed", "code": WorkspaceAuthorityError.code, "provider_started": False,
    }
    assert processing["state"] == "failed"
    assert processing["receipt"]["intervention"] is None
    assert await bound.store.get_event(event.event_id) is not None
