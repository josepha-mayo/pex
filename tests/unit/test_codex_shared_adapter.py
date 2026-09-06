"""Actual shared adapter pump with an in-memory vendor, never a live worker."""

import asyncio

import pytest
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.verification import (
    PytestInvocationScope,
    VerificationProbe,
    VerificationProbeKind,
    classify_pytest_invocation,
)
from test_codex_subscription import _notification, _subscribed


async def eventually(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(wait(), timeout=2)


@pytest.mark.asyncio
async def test_shared_completed_powershell_pytest_keeps_exact_target_scope(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    command = (
        r'"C:\runtime\pwsh.exe" -Command '
        "'C:/workspace/.venv/Scripts/python.exe -m pytest -q test_normalizer.py'"
    )
    for turn_id, item_id, output, exit_code in (
        ("turn-failed", "pytest-failed", "FAILED test_normalizer.py::test_trim\n4 failed", 1),
        ("turn-passed", "pytest-passed", "4 passed in 0.31s", 0),
    ):
        transport.notifications.append(
            _notification(
                "turn/started",
                {"threadId": "thread-1", "turn": {"id": turn_id}},
            )
        )
        transport.notifications.append(
            _notification(
                "item/completed",
                {
                    "threadId": "thread-1",
                    "turnId": turn_id,
                    "item": {
                        "id": item_id,
                        "type": "commandExecution",
                        "command": command,
                        "cwd": adapter.session.cwd,
                        "aggregatedOutput": output,
                        "exitCode": exit_code,
                        "status": "completed" if exit_code == 0 else "failed",
                    },
                },
            )
        )
    try:
        events = [adapter._event(record) for record in (await coordinator.drain_live()).records]
        shells = [
            event
            for event in events
            if event is not None and event.event_type == EventType.SHELL
        ]
        assert len(shells) == 2
        assert shells[0].process_state["pytest"]["ok"] is False
        assert shells[0].process_state["pytest"]["exit_code"] == 1
        assert shells[1].process_state["pytest"]["ok"] is True
        assert shells[1].process_state["pytest"]["exit_code"] == 0
        assert shells[1].process_state["pytest"]["passed"] == 4
        assert shells[1].process_state["pytest"]["execution_cwd"] == adapter.session.cwd

        invocation = classify_pytest_invocation(shells[1].command)
        assert invocation is not None
        assert invocation.scope == PytestInvocationScope.TARGETED
        assert invocation.relative_targets == ("test_normalizer.py",)
        exact_probe = VerificationProbe(
            id="probe-shared-targeted-pytest",
            kind=VerificationProbeKind.PYTEST,
            harness_type=HarnessType.CODEX,
            session_id=adapter.session.id,
            project_id=adapter.session.project_id,
            goal_id="goal-shared-targeted-pytest",
            request_event_id="request-stop",
            cwd=adapter.session.cwd,
            relative_targets=("test_normalizer.py",),
        )
        full_probe = exact_probe.model_copy(update={"relative_targets": ()})
        assert exact_probe.matches_pytest_invocation(invocation) is True
        assert full_probe.matches_pytest_invocation(invocation) is False
    finally:
        await transport.close()


@pytest.mark.parametrize("command_directory", ["missing", "other"])
async def test_shared_full_suite_pass_outside_bound_cwd_is_not_pytest_evidence(
    tmp_path, command_directory,
):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    item = {
        "id": "pytest-unbound", "type": "commandExecution",
        "command": "python -m pytest -q", "aggregatedOutput": "4 passed in 0.31s",
        "exitCode": 0, "status": "completed",
    }
    if command_directory == "other":
        item["cwd"] = str(tmp_path / "different-workspace")
    transport.notifications.extend([
        _notification("turn/started", {"threadId": "thread-1", "turn": {"id": "turn-test"}}),
        _notification("item/completed", {
            "threadId": "thread-1", "turnId": "turn-test", "item": item,
        }),
    ])
    try:
        events = [adapter._event(record) for record in (await coordinator.drain_live()).records]
        shells = [event for event in events if event and event.event_type == EventType.SHELL]
        assert len(shells) == 1
        assert shells[0].session_id == adapter.session.id
        assert shells[0].command == item["command"]
        assert "pytest" not in shells[0].process_state
        assert shells[0].process_state["pytest_unavailable_reason"] == (
            "command_cwd_missing" if command_directory == "missing" else "command_cwd_mismatch"
        )
    finally:
        await transport.close()


@pytest.mark.parametrize("terminal_status", ["completed", "interrupted", "failed"])
async def test_older_turn_completion_cannot_clear_newer_active_turn(tmp_path, terminal_status):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    transport.notifications.extend([
        _notification("turn/started", {"threadId": "thread-1", "turn": {"id": "old"}}),
        _notification("turn/started", {"threadId": "thread-1", "turn": {"id": "new"}}),
        _notification("turn/completed", {
            "threadId": "thread-1", "turn": {"id": "old", "status": terminal_status},
        }),
    ])
    try:
        records = (await coordinator.drain_live()).records
        events = [adapter._event(record) for record in records]
        assert adapter.active_turn_id == "new"
        # Keep the old terminal observation; do not manufacture a terminal event
        # for the current turn or suppress useful historical evidence.
        assert events[-1].event_type == EventType.STOP
        assert events[-1].metadata["turn_status"] == terminal_status
        transport.notifications.append(_notification("turn/completed", {
            "threadId": "thread-1", "turn": {"id": "new", "status": "completed"},
        }))
        for record in (await coordinator.drain_live()).records:
            adapter._event(record)
        assert adapter.active_turn_id is None
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_closed_thread_is_a_durable_local_gap_not_fake_worker_completion(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    events = []

    async def ingest(event, session):
        events.append((event, session))

    task = adapter.start_pipeline_pump(ingest, lifecycle_ingest=ingest)
    transport.notifications.append(_notification("thread/closed", {"threadId": "thread-1"}))
    await asyncio.wait_for(task, timeout=2)
    assert len(events) == 1
    event, session = events[0]
    assert event.event_type == EventType.STATUS
    assert event.metadata["source"] == "pex_observer_lifecycle"
    assert event.metadata["worker_stopped"] is False
    assert session.status == SessionStatus.DETACHED
    assert session.last_activity is None
    assert session.capabilities["observe_messages"] is False
    coverage = event.metadata["observation_coverage"]
    assert coverage["state"] == "disconnected"
    assert coverage["reason"] == "vendor_thread_closed"
    assert coverage["raw_stream_complete"] is False
    assert coverage["unobserved_event_count"] is None
    assert transport.closed


@pytest.mark.asyncio
async def test_disconnect_preserves_unknown_pending_observations(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    entered = asyncio.Event()
    events = []

    async def ingest(event, session):
        if event.metadata.get("source") != "pex_observer_lifecycle":
            entered.set()
            await asyncio.Event().wait()
        events.append((event, session))

    task = adapter.start_pipeline_pump(ingest, lifecycle_ingest=ingest)
    transport.notifications.extend(
        [
            _notification("turn/started", {"threadId": "thread-1", "turn": {"id": "t1"}}),
            _notification("turn/started", {"threadId": "thread-1", "turn": {"id": "t2"}}),
        ]
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    await eventually(lambda: adapter.ingress_sequence == 2)
    activity = adapter.session.last_activity
    transport.notifications.append(_notification("thread/closed", {"threadId": "thread-1"}))
    await asyncio.wait_for(task, timeout=2)
    assert len(events) == 1
    coverage = events[0][0].metadata["observation_coverage"]
    assert coverage["last_observed_live_sequence"] == 2
    assert coverage["last_ingested_live_sequence"] == 0
    assert coverage["pending_normalized_events"] == 2
    assert events[0][1].last_activity == activity


@pytest.mark.asyncio
async def test_failed_gap_ingestion_is_not_reported_as_durable_success(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)

    async def unavailable(event, session):
        raise RuntimeError("fixture store is unavailable")

    transport.notifications.append(_notification("thread/closed", {"threadId": "thread-1"}))
    await asyncio.wait_for(
        adapter.start_pipeline_pump(unavailable, lifecycle_ingest=unavailable), timeout=2
    )
    assert adapter.last_pump_error == "disconnect_receipt_RuntimeError"
    assert not adapter._connected()
    assert adapter.session.status == SessionStatus.DETACHED


@pytest.mark.asyncio
async def test_turn_completion_items_are_not_fabricated_as_live_item_events(tmp_path):
    coordinator, transport = await _subscribed(tmp_path)
    adapter = CodexSharedAdapter(coordinator)
    events = []

    async def ingest(event, session):
        events.append(event)

    task = adapter.start_pipeline_pump(ingest, lifecycle_ingest=ingest)
    transport.notifications.append(
        _notification(
            "turn/completed",
            {
                "threadId": "thread-1",
                "turn": {
                    "id": "turn-1",
                    "status": "completed",
                    "items": [
                        {
                            "type": "userMessage",
                            "id": "u1",
                            "content": [{"type": "text", "text": "input"}],
                        }
                    ],
                },
            },
        )
    )
    try:
        await eventually(lambda: len(events) == 1)
        assert events[0].event_type == EventType.STOP
        assert events[0].metadata["sequence_scope"] == "retained_lifecycle_records_not_raw_frames"
        assert adapter.input_revision == 0
        assert adapter.session.metadata["observation_coverage"]["raw_stream_complete"] is False
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
