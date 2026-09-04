from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import EventPhase, EventType, HarnessType, PolicyVerdict
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession


async def test_codex_pump_ingests_stop_permission_and_agent_message():
    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_pump", "preview": "pump thread", "cwd": "C:/proj"}]
    adapter = CodexAdapter(transport)
    ingested: list = []

    async def ingest(event, session):
        ingested.append((event, session))

    transport.pending_approvals["req_pump"] = {
        "id": "req_pump",
        "method": "item/commandExecution/requestApproval",
        "params": {"threadId": "thr_pump", "command": "pytest", "cwd": "C:/proj"},
    }
    transport.notifications.append(
        {
            "method": "item/completed",
            "params": {
                "threadId": "thr_pump",
                "cwd": "C:/proj",
                "item": {"id": "item_msg", "type": "agentMessage", "text": "working on it"},
            },
        }
    )
    transport.notifications.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": "thr_pump",
                "cwd": "C:/proj",
                "turn": {"id": "t_pump", "status": "completed", "items": []},
            },
        }
    )

    task = adapter.start_pipeline_pump(ingest)
    try:
        wanted = {
            EventType.PERMISSION_REQUEST.value,
            EventType.AGENT_RESPONSE.value,
            EventType.STOP.value,
        }
        for _ in range(40):
            types = {event.event_type.value for event, _ in ingested}
            if wanted <= types:
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    types = {event.event_type.value for event, _ in ingested}
    assert EventType.PERMISSION_REQUEST.value in types
    assert EventType.AGENT_RESPONSE.value in types
    assert EventType.STOP.value in types
    session = adapter.sessions.get("codex:thr_pump")
    assert session is not None
    assert session.cwd == "C:/proj"


async def test_codex_pump_uses_official_items_once_and_preserves_pytest_failure():
    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_pytest", "preview": "pytest thread", "cwd": "C:/proj"}]
    adapter = CodexAdapter(transport)
    ingested: list = []

    async def ingest(event, session):
        ingested.append((event, session))

    command_item = {
        "id": "item_cmd",
        "type": "commandExecution",
        "command": "pytest -q",
        "cwd": "C:/proj",
        "commandActions": [],
        "aggregatedOutput": "FAILED tests/test_parser.py::test_nested_array\n1 failed",
        "exitCode": 1,
        "status": "failed",
    }
    file_item = {
        "id": "item_file",
        "type": "fileChange",
        "changes": [{"path": "src/parser.py", "kind": "update"}],
        "status": "completed",
    }
    message_item = {
        "id": "item_msg",
        "type": "agentMessage",
        "text": "All tests passed. I am done.",
        "phase": "final_answer",
    }
    for item in (command_item, file_item, message_item):
        transport.notifications.append(
            {
                "method": "item/completed",
                "params": {
                    "threadId": "thr_pytest",
                    "turnId": "t_pytest",
                    "item": item,
                },
            }
        )
    transport.notifications.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": "thr_pytest",
                "turn": {
                    "id": "t_pytest",
                    "status": "completed",
                    "items": [command_item, file_item, message_item],
                },
            },
        }
    )

    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(40):
            types = {event.event_type.value for event, _ in ingested}
            if {EventType.SHELL.value, EventType.FILE_EDIT.value, EventType.STOP.value} <= types:
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    shells = [event for event, _ in ingested if event.event_type == EventType.SHELL]
    assert len(shells) == 1
    assert shells[0].message_delta is None
    assert shells[0].command == "pytest -q"
    assert shells[0].process_state is not None
    assert shells[0].process_state["pytest"]["ok"] is False
    assert shells[0].process_state["pytest"]["failed"] == "tests/test_parser.py::test_nested_array"
    files = [event for event, _ in ingested if event.event_type == EventType.FILE_EDIT]
    assert len(files) == 1
    assert "src/parser.py" in files[0].file_paths
    messages = [event for event, _ in ingested if event.event_type == EventType.AGENT_RESPONSE]
    assert len(messages) == 1
    assert messages[0].message_delta == "All tests passed. I am done."
    stops = [event for event, _ in ingested if event.event_type == EventType.STOP]
    assert len(stops) == 1
    assert stops[0].message_delta is None
    assert stops[0].metadata["turn_status"] == "completed"


def test_codex_normalize_item_keeps_shell_output_out_of_claims():
    from pex_protocol.enums import HarnessType, SessionStatus
    from pex_protocol.session import HarnessSession

    session = HarnessSession(
        id="codex:thr_n",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thr_n",
        status=SessionStatus.WORKING,
        cwd="C:/proj",
    )
    adapter = CodexAdapter()
    session.project_id = session.cwd
    adapter.sessions[session.id] = session
    event = adapter.normalize_item(
        session,
        {
            "id": "item_cmd",
            "type": "commandExecution",
            "command": {"command": "pytest -q"},
            "aggregatedOutput": "All tests passed\n1 passed",
            "exitCode": 0,
            "status": "completed",
        },
    )
    assert event.event_type == EventType.SHELL
    assert event.message_delta is None
    assert event.command == "pytest -q"
    assert event.process_state is not None
    assert event.process_state["pytest"]["ok"] is True
    assert event.process_state["pytest"]["exit_code"] == 0


def test_codex_item_turn_identity_cannot_override_enclosing_turn():
    assert CodexAdapter._vendor_turn_id(
        {"turn": {"id": "turn_outer"}},
        {"turnId": "turn_inner"},
    ) is None
    assert (
        CodexAdapter._vendor_turn_id(
            {"turn": {"id": "turn_outer"}},
            {"turnId": "turn_outer"},
        )
        == "turn_outer"
    )


async def test_official_codex_failure_flows_through_pipeline_to_exact_nudge(tmp_path):
    worker = tmp_path / "worker"
    worker.mkdir()
    transport = CodexAppServerTransport()
    adapter = CodexAdapter(transport)
    registry = AdapterRegistry()
    registry.bind("codex", adapter)
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    transport.threads.append({"id": "thr_closed_loop", "cwd": str(worker)})
    session = next(
        item
        for item in await adapter.discover_sessions()
        if item.vendor_session_id == "thr_closed_loop"
    )
    now = datetime.now(UTC)
    goal = Goal(
        id="goal_closed_loop",
        project_id=str(worker),
        title="Fix parser",
        objective="Fix the parser and make the tests pass",
        acceptance_criteria=["tests pass"],
        created_at=now,
        updated_at=now,
    )
    session.goal_id = goal.id
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    transport.threads = [{"id": session.vendor_session_id, "cwd": str(worker)}]
    failed = {
        "id": "item_failed_pytest",
        "type": "commandExecution",
        "command": "pytest -q",
        "cwd": str(worker),
        "commandActions": [],
        "aggregatedOutput": "FAILED tests/test_parser.py::test_nested_array\n1 failed",
        "exitCode": 1,
        "status": "failed",
    }
    claim = {
        "id": "item_false_claim",
        "type": "agentMessage",
        "text": "All tests passed. I am done.",
        "phase": "final_answer",
    }
    for item in (failed, claim):
        transport.notifications.append(
            {
                "method": "item/completed",
                "params": {
                    "threadId": session.vendor_session_id,
                    "turnId": "turn_closed_loop",
                    "item": item,
                },
            }
        )
    transport.notifications.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": session.vendor_session_id,
                "turn": {
                    "id": "turn_closed_loop",
                    "items": [failed, claim],
                    "status": "completed",
                },
            },
        }
    )
    pipeline = Pipeline(store, registry, EventBus(), Settings(home=tmp_path))
    task = adapter.start_pipeline_pump(pipeline.ingest_event)
    try:
        for _ in range(80):
            interventions = await store.list_interventions(session.id)
            if any(
                item.action_taken == "SEND_NUDGE"
                and item.result != "delivery_reserved"
                for item in interventions
            ):
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    try:
        interventions = await store.list_interventions(session.id)
        nudges = [item for item in interventions if item.action_taken == "SEND_NUDGE"]
        assert len(nudges) == 1
        text = str(nudges[0].proposed_action.payload.get("text") or "")
        assert "tests/test_parser.py::test_nested_array" in text
        assert not text.startswith("PEX:")
        events = await store.recent_events(session.id, 20)
        assert (
            len(
                [
                    event
                    for event in events
                    if event.event_id == f"{session.id}:item:{failed['id']}"
                ]
            )
            == 1
        )
        assert adapter.inbox[session.id][-1] == text
        assert nudges[0].result == "sent"
        assert transport.turns, "SEND_NUDGE must start an App Server turn, not only fill inbox"
        followup = transport.turns[-1]
        assert followup["threadId"] == session.vendor_session_id
        assert followup["threadId"] != "desktop"
        texts = [
            block.get("text")
            for block in (followup.get("input") or [])
            if isinstance(block, dict)
        ]
        assert text in texts
        assert not any(str(item).startswith("PEX:") for item in texts)
    finally:
        await store.close()


async def test_official_codex_passing_pytest_is_noop_on_the_same_thread(tmp_path):
    worker = tmp_path / "complete-worker"
    worker.mkdir()
    transport = CodexAppServerTransport()
    adapter = CodexAdapter(transport)
    registry = AdapterRegistry()
    registry.bind("codex", adapter)
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    transport.threads = [{"id": "thr_genuine", "cwd": str(worker)}]
    session = next(
        item
        for item in await adapter.discover_sessions()
        if item.vendor_session_id == "thr_genuine"
    )
    now = datetime.now(UTC)
    goal = Goal(
        id="goal_genuine",
        project_id=str(worker),
        title="Parser",
        objective="Implement the parser with passing tests",
        acceptance_criteria=["tests pass"],
        created_at=now,
        updated_at=now,
    )
    session.goal_id = goal.id
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    passed = {
        "id": "item_passed_pytest",
        "type": "commandExecution",
        "command": "pytest -q",
        "cwd": str(worker),
        "commandActions": [],
        "aggregatedOutput": "4 passed",
        "exitCode": 0,
        "status": "completed",
    }
    claim = {
        "id": "item_true_claim",
        "type": "agentMessage",
        "text": "All tests passed. I am done.",
        "phase": "final_answer",
    }
    for item in (passed, claim):
        transport.notifications.append(
            {
                "method": "item/completed",
                "params": {
                    "threadId": session.vendor_session_id,
                    "turnId": "turn_genuine",
                    "item": item,
                },
            }
        )
    transport.notifications.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": session.vendor_session_id,
                "turn": {
                    "id": "turn_genuine",
                    "items": [passed, claim],
                    "status": "completed",
                },
            },
        }
    )
    pipeline = Pipeline(store, registry, EventBus(), Settings(home=tmp_path))
    task = adapter.start_pipeline_pump(pipeline.ingest_event)
    try:
        for _ in range(80):
            interventions = await store.list_interventions(session.id)
            if any(item.trigger == EventType.STOP.value for item in interventions):
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    try:
        interventions = await store.list_interventions(session.id)
        stops = [item for item in interventions if item.trigger == EventType.STOP.value]
        assert stops
        assert stops[-1].action_taken == "NOOP"
        assert (stops[-1].metadata or {}).get("verification", {}).get("status") == "supported"
        assert adapter.inbox.get(session.id, []) == []
        assert transport.turns == []
        assert not str(stops[-1].worker_response or "").startswith("PEX:")
    finally:
        await store.close()


async def test_official_codex_missing_artifact_nudges_the_same_thread(tmp_path):
    worker = tmp_path / "premature-worker"
    worker.mkdir()
    transport = CodexAppServerTransport()
    adapter = CodexAdapter(transport)
    registry = AdapterRegistry()
    registry.bind("codex", adapter)
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    transport.threads = [{"id": "thr_report", "cwd": str(worker)}]
    session = next(
        item
        for item in await adapter.discover_sessions()
        if item.vendor_session_id == "thr_report"
    )
    now = datetime.now(UTC)
    goal = Goal(
        id="goal_report",
        project_id=str(worker),
        title="report",
        objective="Create report.txt containing exactly the word shipped.",
        acceptance_criteria=["report.txt contains shipped"],
        evidence_requirements=["report.txt"],
        created_at=now,
        updated_at=now,
    )
    session.goal_id = goal.id
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    transport.notifications.append(
        {
            "method": "item/completed",
            "params": {
                "threadId": session.vendor_session_id,
                "item": {
                    "id": "item_done",
                    "type": "agentMessage",
                    "text": "I am done.",
                    "phase": "final_answer",
                },
            },
        }
    )
    transport.notifications.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": session.vendor_session_id,
                "turn": {"id": "turn_report", "status": "completed", "items": []},
            },
        }
    )
    pipeline = Pipeline(store, registry, EventBus(), Settings(home=tmp_path))
    task = adapter.start_pipeline_pump(pipeline.ingest_event)
    try:
        for _ in range(80):
            interventions = await store.list_interventions(session.id)
            if any(
                item.action_taken == "SEND_NUDGE"
                and item.result != "delivery_reserved"
                for item in interventions
            ):
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    try:
        interventions = await store.list_interventions(session.id)
        nudges = [item for item in interventions if item.action_taken == "SEND_NUDGE"]
        assert len(nudges) == 1
        text = str(nudges[0].proposed_action.payload.get("text") or "")
        assert "report.txt" in text
        assert "missing" in text.lower()
        assert not text.startswith("PEX:")
        assert nudges[0].result == "sent"
        followup = transport.turns[-1]
        assert followup["threadId"] == session.vendor_session_id
        assert followup["threadId"] != "desktop"
        texts = [
            block.get("text")
            for block in (followup.get("input") or [])
            if isinstance(block, dict)
        ]
        assert text in texts
        assert adapter.inbox[session.id][-1] == text
    finally:
        await store.close()


async def test_codex_pump_processes_notification_appended_during_ingest():
    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_append", "cwd": "C:/proj"}]
    adapter = CodexAdapter(transport)
    ingested_ids: list[str] = []

    async def ingest(event, _session):
        ingested_ids.append(event.event_id)
        if event.event_id.endswith(":item:first"):
            transport.notifications.append(
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": "thr_append",
                        "item": {
                            "id": "second",
                            "type": "agentMessage",
                            "text": "second",
                        },
                    },
                }
            )
            await asyncio.sleep(0)

    transport.notifications.append(
        {
            "method": "item/completed",
            "params": {
                "threadId": "thr_append",
                "item": {"id": "first", "type": "agentMessage", "text": "first"},
            },
        }
    )
    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(40):
            if len(ingested_ids) == 2:
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert ingested_ids == [
        "codex:thr_append:item:first",
        "codex:thr_append:item:second",
    ]
    assert transport.notifications == []


async def test_codex_pump_retries_exact_notification_after_ingest_failure():
    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_retry", "cwd": "C:/proj"}]
    adapter = CodexAdapter(transport)
    attempts: dict[str, int] = {}
    completed: list[str] = []

    async def ingest(event, _session):
        attempts[event.event_id] = attempts.get(event.event_id, 0) + 1
        if event.event_id.endswith(":item:first") and attempts[event.event_id] == 1:
            raise RuntimeError("transient store failure")
        completed.append(event.event_id)

    for item_id in ("first", "second"):
        transport.notifications.append(
            {
                "method": "item/completed",
                "params": {
                    "threadId": "thr_retry",
                    "item": {
                        "id": item_id,
                        "type": "agentMessage",
                        "text": item_id,
                    },
                },
            }
        )
    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(40):
            if len(completed) == 2:
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    first_id = "codex:thr_retry:item:first"
    second_id = "codex:thr_retry:item:second"
    assert attempts[first_id] == 2
    assert attempts[second_id] == 1
    assert completed == [first_id, second_id]
    assert transport.notifications == []


async def test_codex_pump_retries_approval_after_ingest_failure():
    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_approval_retry", "cwd": "C:/proj"}]
    transport.pending_approvals["approval_retry"] = {
        "id": "approval_retry",
        "method": "item/commandExecution/requestApproval",
        "params": {"threadId": "thr_approval_retry", "command": "pytest"},
    }
    adapter = CodexAdapter(transport)
    attempts = 0
    completed: list[str] = []

    async def ingest(event, _session):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient store failure")
        completed.append(event.event_id)

    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(40):
            if completed:
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert attempts == 2
    assert len(completed) == 1
    assert completed[0].startswith("codex:thr_approval_retry:approval:approval_retry:")


async def test_codex_waiter_reads_completion_after_pipeline_pump_acknowledges_queue():
    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_wait_cache", "cwd": "C:/proj"}]
    adapter = CodexAdapter(transport)
    session = next(
        item
        for item in await adapter.discover_sessions()
        if item.vendor_session_id == "thr_wait_cache"
    )
    transport.notifications.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": session.vendor_session_id,
                "turn": {"id": "turn_cached", "status": "completed", "items": []},
            },
        }
    )

    async def ingest(_event, _session):
        return None

    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(40):
            if not transport.notifications:
                break
            await asyncio.sleep(0.05)
        assert transport.notifications == []
        completed = await adapter.wait_for_turn_completion(
            session,
            "turn_cached",
            timeout=0.2,
        )
        assert completed["status"] == "completed"
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def test_codex_item_dedupe_is_scoped_to_thread():
    transport = CodexAppServerTransport()
    transport.threads = [
        {"id": "thr_item_one", "cwd": "C:/one"},
        {"id": "thr_item_two", "cwd": "C:/two"},
    ]
    adapter = CodexAdapter(transport)
    ingested: list[str] = []

    async def ingest(event, _session):
        ingested.append(event.event_id)

    for thread_id in ("thr_item_one", "thr_item_two"):
        transport.notifications.append(
            {
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "item": {"id": "item_1", "type": "agentMessage", "text": thread_id},
                },
            }
        )
    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(40):
            if len(ingested) == 2:
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert ingested == [
        "codex:thr_item_one:item:item_1",
        "codex:thr_item_two:item:item_1",
    ]


async def test_codex_idless_turn_item_is_stable_when_stop_ingest_retries():
    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_idless", "cwd": "C:/proj"}]
    adapter = CodexAdapter(transport)
    ingested_items: list[str] = []
    stop_attempts = 0

    async def ingest(event, _session):
        nonlocal stop_attempts
        if event.event_type == EventType.STOP:
            stop_attempts += 1
            if stop_attempts == 1:
                raise RuntimeError("transient stop store failure")
            return
        if event.event_type == EventType.AGENT_RESPONSE:
            ingested_items.append(event.event_id)

    transport.notifications.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": "thr_idless",
                "turn": {
                    "id": "turn_idless",
                    "status": "completed",
                    "items": [{"type": "agentMessage", "text": "done"}],
                },
            },
        }
    )
    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(40):
            if stop_attempts == 2 and not transport.notifications:
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert stop_attempts == 2
    assert len(ingested_items) == 1
    assert ":item:anonymous:turn_idless:" in ingested_items[0]
    assert transport.notifications == []


async def test_codex_reused_approval_id_gets_a_new_audit_identity():
    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_approval_reuse", "cwd": "C:/proj"}]
    adapter = CodexAdapter(transport)
    events: list[tuple[str, str | None]] = []

    async def ingest(event, _session):
        events.append((event.event_id, event.command))

    transport.pending_approvals["7"] = {
        "id": "7",
        "method": "item/commandExecution/requestApproval",
        "params": {"threadId": "thr_approval_reuse", "command": "pytest"},
    }
    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(40):
            if len(events) == 1:
                break
            await asyncio.sleep(0.05)
        transport.pending_approvals.pop("7")
        await asyncio.sleep(0.1)
        transport.pending_approvals["7"] = {
            "id": "7",
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thr_approval_reuse", "command": "ruff check ."},
        }
        for _ in range(40):
            if len(events) == 2:
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert [command for _, command in events] == ["pytest", "ruff check ."]
    assert events[0][0] != events[1][0]


async def test_codex_pump_reclaims_successful_prefix_before_poison_retry():
    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_poison", "cwd": "C:/proj"}]
    adapter = CodexAdapter(transport)
    completed: list[str] = []

    async def ingest(event, _session):
        if event.event_id.endswith(":item:poison"):
            raise RuntimeError("persistent poison")
        completed.append(event.event_id)

    for item_id in ("first", "poison", "tail"):
        transport.notifications.append(
            {
                "method": "item/completed",
                "params": {
                    "threadId": "thr_poison",
                    "item": {"id": item_id, "type": "agentMessage", "text": item_id},
                },
            }
        )
    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(40):
            if adapter.last_pump_error == "RuntimeError":
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert completed == ["codex:thr_poison:item:first"]
    assert len(transport.notifications) == 2
    assert transport.notifications[0]["params"]["item"]["id"] == "poison"


async def test_codex_pump_reclaims_consumed_notifications_across_retention_bound():
    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_long", "cwd": "C:/proj"}]
    adapter = CodexAdapter(transport)
    completed: list[str] = []

    async def ingest(event, _session):
        completed.append(event.event_id)

    task = adapter.start_pipeline_pump(ingest)
    try:
        for batch in range(2):
            for index in range(700):
                item_id = f"batch_{batch}_{index}"
                transport.notifications.append(
                    {
                        "method": "item/completed",
                        "params": {
                            "threadId": "thr_long",
                            "item": {
                                "id": item_id,
                                "type": "agentMessage",
                                "text": item_id,
                            },
                        },
                    }
                )
            target = (batch + 1) * 700
            for _ in range(80):
                if len(completed) == target and not transport.notifications:
                    break
                await asyncio.sleep(0.05)
            assert len(completed) == target
            assert transport.notifications == []
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert len(completed) == 1_400
    assert adapter.last_pump_error is None


async def test_codex_recovery_observes_same_thread_outcome_appended_during_stop(tmp_path):
    worker = tmp_path / "recovered-worker"
    worker.mkdir()

    class RepairingTransport(CodexAppServerTransport):
        async def request(self, method, params=None):
            if method == "turn/start":
                (worker / "report.txt").write_text("shipped\n", encoding="utf-8")
            return await super().request(method, params)

    transport = RepairingTransport()
    adapter = CodexAdapter(transport)
    registry = AdapterRegistry()
    registry.bind("codex", adapter)
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    transport.threads = [{"id": "thr_recovered", "cwd": str(worker)}]
    session = next(
        item
        for item in await adapter.discover_sessions()
        if item.vendor_session_id == "thr_recovered"
    )
    now = datetime.now(UTC)
    goal = Goal(
        id="goal_recovered",
        project_id=str(worker),
        title="report",
        objective="Create report.txt containing exactly the word shipped.",
        acceptance_criteria=["report.txt contains shipped"],
        evidence_requirements=["report.txt"],
        created_at=now,
        updated_at=now,
    )
    session.goal_id = goal.id
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    transport.notifications.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": session.vendor_session_id,
                "turn": {"id": "turn_incomplete", "status": "completed", "items": []},
            },
        }
    )
    pipeline = Pipeline(store, registry, EventBus(), Settings(home=tmp_path))
    task = adapter.start_pipeline_pump(pipeline.ingest_event)
    try:
        for _ in range(80):
            rows = await store.list_interventions(session.id)
            stop_rows = [row for row in rows if row.trigger == EventType.STOP.value]
            if len(stop_rows) >= 2:
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    try:
        rows = await store.list_interventions(session.id)
        stop_rows = [row for row in rows if row.trigger == EventType.STOP.value]
        assert len(stop_rows) == 2
        nudge = next(row for row in stop_rows if row.action_taken == "SEND_NUDGE")
        noop = next(row for row in stop_rows if row.action_taken == "NOOP")
        assert nudge.result == "sent"
        assert nudge.outcome == "goal_evidence_supported"
        assert nudge.helped is True
        assert (nudge.metadata or {})["worker_delivery_receipt"] == {
            "schema": "pex.worker-delivery.codex-turn.v1",
            "target_session_id": session.id,
            "vendor_session_id": session.vendor_session_id,
            "vendor_turn_id": "turn_1",
        }
        assert noop.result == "noop"
        assert (
            (noop.metadata or {}).get("verification", {}).get("acceptance_status")
            == "supported"
        )
        assert (worker / "report.txt").read_text(encoding="utf-8").strip() == "shipped"
        assert len(transport.turns) == 1
        assert transport.turns[0]["threadId"] == session.vendor_session_id
        stored_events = await store.recent_events(session.id, 20)
        assert len([event for event in stored_events if event.event_type == EventType.STOP]) == 2
        followup_stop = next(
            event
            for event in stored_events
            if (event.metadata or {}).get("vendor_turn_id") == "turn_1"
        )
        assert '"turn_id":"turn_1"' in str(followup_stop.raw_event_ref)
    finally:
        await store.close()


async def test_codex_outcome_waits_for_the_exact_delivered_turn(tmp_path):
    worker = tmp_path / "turn-bound-worker"
    worker.mkdir()

    class InterleavingTransport(CodexAppServerTransport):
        async def request(self, method, params=None):
            if method != "turn/start":
                return await super().request(method, params)
            params = params or {}
            self.turns.append(params)
            (worker / "report.txt").write_text("shipped\n", encoding="utf-8")
            self.notifications.append(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": params.get("threadId"),
                        "turn": {
                            "id": "turn_unrelated",
                            "status": "completed",
                            "items": [],
                        },
                    },
                }
            )
            return {
                "turn": {
                    "id": "turn_pex_followup",
                    "status": "inProgress",
                    "items": [],
                }
            }

    transport = InterleavingTransport()
    adapter = CodexAdapter(transport)
    registry = AdapterRegistry()
    registry.bind("codex", adapter)
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    transport.threads = [{"id": "thr_turn_bound", "cwd": str(worker)}]
    session = next(
        item
        for item in await adapter.discover_sessions()
        if item.vendor_session_id == "thr_turn_bound"
    )
    now = datetime.now(UTC)
    goal = Goal(
        id="goal_turn_bound",
        project_id=str(worker),
        title="Turn-bound report",
        objective="Create report.txt containing exactly the word shipped.",
        acceptance_criteria=["report.txt contains shipped"],
        evidence_requirements=["report.txt"],
        created_at=now,
        updated_at=now,
    )
    session.goal_id = goal.id
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    transport.notifications.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": session.vendor_session_id,
                "turn": {"id": "turn_initial", "status": "completed", "items": []},
            },
        }
    )
    pipeline = Pipeline(store, registry, EventBus(), Settings(home=tmp_path))
    task = adapter.start_pipeline_pump(pipeline.ingest_event)
    try:
        unrelated_id = f"{session.id}:turn:turn_unrelated"
        nudge = None
        for _ in range(100):
            if await store.get_event(unrelated_id) is not None:
                rows = await store.list_interventions(session.id)
                nudge = next(
                    (row for row in rows if row.action_taken == "SEND_NUDGE"),
                    None,
                )
                if nudge is not None and nudge.result == "sent":
                    break
            await asyncio.sleep(0.05)
        assert nudge is not None
        assert (nudge.metadata or {})["worker_delivery_receipt"][
            "vendor_turn_id"
        ] == "turn_pex_followup"
        assert nudge.helped is None
        assert not (nudge.metadata or {}).get("outcome_final")
        assert unrelated_id not in (nudge.metadata or {}).get("outcome_event_ids", [])

        forged = HarnessEvent(
            event_id=f"{session.id}:turn:forged",
            ts=datetime.now(UTC),
            harness_type=HarnessType.CODEX,
            session_id=session.id,
            project_id=session.project_id,
            event_type=EventType.STOP,
            phase=EventPhase.TERMINAL,
            raw_event_ref=(
                '{"schema":"pex.codex-event-ref.v1","thread_id":"'
                + session.vendor_session_id
                + '","turn_id":"turn_unrelated"}'
            ),
            metadata={"vendor_turn_id": "turn_pex_followup"},
        )
        assert pipeline._event_matches_worker_delivery(nudge, session, forged) is False

        transport.notifications.append(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": session.vendor_session_id,
                    "turn": {
                        "id": "turn_pex_followup",
                        "status": "completed",
                        "items": [],
                    },
                },
            }
        )
        matching_id = f"{session.id}:turn:turn_pex_followup"
        for _ in range(100):
            rows = await store.list_interventions(session.id)
            nudge = next(row for row in rows if row.action_taken == "SEND_NUDGE")
            if (nudge.metadata or {}).get("outcome_final"):
                break
            await asyncio.sleep(0.05)
        assert nudge.outcome == "goal_evidence_supported"
        assert nudge.helped is True
        assert (nudge.metadata or {}).get("outcome_event_ids") == [matching_id]
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await store.close()


async def test_codex_human_decision_outcome_requires_the_exact_delivered_turn(tmp_path):
    worker = tmp_path / "human-decision-turn-worker"
    worker.mkdir()
    registry = AdapterRegistry()
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        now = datetime.now(UTC)
        goal = Goal(
            id="goal_human_decision_turn",
            project_id=str(worker),
            title="Human decision causality",
            objective="Create report.txt containing shipped after the human choice.",
            acceptance_criteria=["report.txt contains shipped"],
            evidence_requirements=["report.txt"],
            created_at=now,
            updated_at=now,
        )
        session = HarnessSession(
            id="codex:thr_human_decision_turn",
            harness_type=HarnessType.CODEX,
            vendor_session_id="thr_human_decision_turn",
            cwd=str(worker),
            project_id=str(worker),
            goal_id=goal.id,
        )
        await store.upsert_goal(goal)
        await store.upsert_session(session)
        action = ProposedAction(
            type=InterventionType.ASK_HUMAN,
            session_id=session.id,
            goal_id=goal.id,
            payload={"question": "Which implementation?", "options": ["safe", "fast"]},
            rationale="Only the human can choose the tradeoff.",
            evidence=["decision_required"],
        )
        intervention = Intervention(
            id="int_human_decision_turn",
            session_id=session.id,
            goal_id=goal.id,
            trigger=EventType.PERMISSION_REQUEST.value,
            evidence=list(action.evidence),
            diagnosis="A product choice is required.",
            proposed_action=action,
            confidence=action.confidence,
            risk=action.risk.value,
            reversible=action.reversible,
            authority_required=action.authority_required.value,
            action_taken=action.type.value,
            policy_verdict=PolicyVerdict.ASK_HUMAN,
            result="human_decision_delivered",
            outcome="human_decision_delivered",
            created_at=now,
            metadata={
                "worker_delivery_receipt": {
                    "schema": "pex.worker-delivery.codex-turn.v1",
                    "target_session_id": session.id,
                    "vendor_session_id": session.vendor_session_id,
                    "vendor_turn_id": "turn_human_choice",
                }
            },
        )
        await store.add_intervention(intervention)
        pipeline = Pipeline(store, registry, EventBus(), Settings(home=tmp_path))

        unrelated = HarnessEvent(
            event_id=f"{session.id}:turn:turn_unrelated",
            ts=datetime.now(UTC),
            harness_type=HarnessType.CODEX,
            session_id=session.id,
            project_id=session.project_id,
            event_type=EventType.STOP,
            phase=EventPhase.TERMINAL,
            raw_event_ref=(
                '{"schema":"pex.codex-event-ref.v1","thread_id":"'
                + session.vendor_session_id
                + '","turn_id":"turn_unrelated"}'
            ),
            metadata={"vendor_turn_id": "turn_unrelated"},
        )
        updates = await pipeline._observe_prior_intervention(
            session,
            unrelated,
            verification={"status": "supported", "acceptance_status": "supported"},
        )
        assert updates == []
        unchanged = await store.get_intervention(intervention.id)
        assert unchanged is not None
        assert unchanged.helped is None
        assert not (unchanged.metadata or {}).get("outcome_final")

        matching = HarnessEvent(
            event_id=f"{session.id}:turn:turn_human_choice",
            ts=datetime.now(UTC),
            harness_type=HarnessType.CODEX,
            session_id=session.id,
            project_id=session.project_id,
            event_type=EventType.STOP,
            phase=EventPhase.TERMINAL,
            raw_event_ref=(
                '{"schema":"pex.codex-event-ref.v1","thread_id":"'
                + session.vendor_session_id
                + '","turn_id":"turn_human_choice"}'
            ),
            metadata={"vendor_turn_id": "turn_human_choice"},
        )
        updates = await pipeline._observe_prior_intervention(
            session,
            matching,
            verification={"status": "supported", "acceptance_status": "supported"},
        )
        assert len(updates) == 1
        observed = updates[0]
        assert observed.id == intervention.id
        assert observed.outcome == "goal_evidence_supported"
        assert observed.helped is True
        assert (observed.metadata or {}).get("outcome_final") is True
        assert (observed.metadata or {}).get("outcome_event_ids") == [matching.event_id]
    finally:
        await store.close()


async def test_codex_legacy_and_corrupt_delivery_receipts_finish_without_false_credit(
    tmp_path,
):
    worker = tmp_path / "legacy-receipt-worker"
    worker.mkdir()
    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_legacy_receipt", "cwd": str(worker)}]
    adapter = CodexAdapter(transport)
    registry = AdapterRegistry()
    registry.bind("codex", adapter)
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session = next(
            item
            for item in await adapter.discover_sessions()
            if item.vendor_session_id == "thr_legacy_receipt"
        )
        now = datetime.now(UTC)
        goal = Goal(
            id="goal_legacy_receipt",
            project_id=str(worker),
            title="Legacy receipt",
            objective="Keep causal attribution honest.",
            created_at=now,
            updated_at=now,
        )
        session.goal_id = goal.id
        await store.upsert_goal(goal)
        await store.upsert_session(session)
        pipeline = Pipeline(store, registry, EventBus(), Settings(home=tmp_path))

        def delivered_intervention(intervention_id: str) -> Intervention:
            action = ProposedAction(
                type=InterventionType.SEND_NUDGE,
                session_id=session.id,
                goal_id=goal.id,
                payload={"text": "Continue from the observed gap."},
                rationale="The required artifact is missing.",
                evidence=["missing:report.txt"],
            )
            return Intervention(
                id=intervention_id,
                session_id=session.id,
                goal_id=goal.id,
                trigger=EventType.STOP.value,
                evidence=list(action.evidence),
                diagnosis="The required artifact is missing.",
                proposed_action=action,
                confidence=action.confidence,
                risk=action.risk.value,
                reversible=action.reversible,
                authority_required=action.authority_required.value,
                action_taken=action.type.value,
                policy_verdict=PolicyVerdict.ALLOW,
                result="sent",
                created_at=now,
            )

        legacy = delivered_intervention("int_codex_legacy_receipt")
        corrupt = delivered_intervention("int_codex_corrupt_receipt")
        corrupt.metadata["worker_delivery_receipt"] = {
            "schema": "pex.worker-delivery.codex-turn.v0",
            "target_session_id": session.id,
            "vendor_session_id": session.vendor_session_id,
            "vendor_turn_id": "turn_observed",
        }
        await store.add_intervention(legacy)
        await store.add_intervention(corrupt)
        event = HarnessEvent(
            event_id=f"{session.id}:turn:turn_observed",
            ts=datetime.now(UTC),
            harness_type=HarnessType.CODEX,
            session_id=session.id,
            project_id=session.project_id,
            event_type=EventType.STOP,
            phase=EventPhase.TERMINAL,
            raw_event_ref=(
                '{"schema":"pex.codex-event-ref.v1","thread_id":"'
                + session.vendor_session_id
                + '","turn_id":"turn_observed"}'
            ),
            metadata={"vendor_turn_id": "turn_observed"},
        )

        updates = await pipeline._observe_prior_intervention(
            session,
            event,
            verification={"status": "supported", "acceptance_status": "supported"},
        )
        by_id = {item.id: item for item in updates}
        assert by_id[legacy.id].outcome == "worker_delivery_causality_unavailable_legacy"
        assert by_id[legacy.id].helped is None
        assert (by_id[legacy.id].metadata or {}).get("outcome_final") is True
        assert by_id[corrupt.id].outcome == "worker_delivery_receipt_corrupt"
        assert by_id[corrupt.id].helped is None
        assert (by_id[corrupt.id].metadata or {}).get("outcome_final") is True

        stored = {item.id: item for item in await store.list_interventions(session.id)}
        assert stored[legacy.id].helped is None
        assert stored[corrupt.id].helped is None
    finally:
        await store.close()


async def test_codex_raw_capture_survives_pipeline_pump():
    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_raw", "preview": "raw capture", "cwd": "C:/proj"}]
    adapter = CodexAdapter(transport)
    ingested: list = []

    async def ingest(event, session):
        ingested.append((event, session))

    transport._append_notification(
        {
            "method": "turn/started",
            "params": {
                "threadId": "thr_raw",
                "cwd": "C:/proj",
                "turn": {"id": "t_raw", "status": "in_progress", "items": []},
            },
        }
    )
    transport._append_notification(
        {
            "method": "turn/completed",
            "params": {
                "threadId": "thr_raw",
                "cwd": "C:/proj",
                "turn": {"id": "t_raw", "status": "completed", "items": []},
            },
        }
    )

    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(40):
            if not transport.notifications:
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert transport.notifications == []
    methods = [message["method"] for message in transport.raw_capture]
    assert methods == ["turn/started", "turn/completed"]
    assert any(event.event_type.value == EventType.STOP.value for event, _ in ingested)
