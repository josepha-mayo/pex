from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pex_bridge.adapters.codex_subscription as subscription_module
import pytest
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.adapters.codex_subscription import (
    SUBSCRIPTION_SCHEMA,
    CodexExistingThreadSubscription,
    CodexSelectedThread,
    CodexSubscriptionAuthorization,
    CodexSubscriptionError,
)


def _thread_response(
    cwd: Path,
    *,
    turns: list[dict[str, Any]] | None = None,
    include_turns: bool = True,
    thread_update: dict[str, Any] | None = None,
    response_update: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thread: dict[str, Any] = {
        "id": "thread-1",
        "sessionId": "root-session-1",
        "projectId": "vendor-project-1",
        "cwd": str(cwd),
        "source": "cli",
        "originator": "codex-cli",
        "model": "gpt-test",
        "modelProvider": "openai",
        "canAcceptDirectInput": True,
        "status": {"type": "idle"},
    }
    if include_turns:
        thread["turns"] = deepcopy(turns if turns is not None else [])
    thread.update(thread_update or {})
    response = {
        "thread": thread,
        "sessionId": thread.get("sessionId"),
        "projectId": thread.get("projectId"),
        "cwd": thread.get("cwd"),
        "source": thread.get("source"),
        "originator": thread.get("originator"),
        "model": thread.get("model"),
        "modelProvider": thread.get("modelProvider"),
        "canAcceptDirectInput": thread.get("canAcceptDirectInput"),
        "status": thread.get("status"),
    }
    response.update(response_update or {})
    return response


class FakeSharedTransport:
    initialized = True
    endpoint_identity = "endpoint-sha256"
    connection_generation = 1

    def __init__(
        self,
        reads: list[dict[str, Any]],
        resume: dict[str, Any],
        *,
        on_resume: Callable[[FakeSharedTransport], None] | None = None,
    ) -> None:
        self.reads = [deepcopy(item) for item in reads]
        self.resume = deepcopy(resume)
        self.on_resume = on_resume
        self.notifications: list[dict[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    async def ensure_ready(self) -> dict[str, Any]:
        return {"serverInfo": {"name": "fake-shared-server"}}

    def connection_token(self) -> tuple[str, int]:
        return self.endpoint_identity, self.connection_generation

    async def request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = dict(params or {})
        self.calls.append((method, payload))
        if method == "thread/read":
            if not self.reads:
                raise AssertionError("unexpected extra thread/read")
            return self.reads.pop(0)
        if method == "thread/resume":
            if self.on_resume is not None:
                self.on_resume(self)
            return deepcopy(self.resume)
        raise AssertionError(f"coordinator dispatched forbidden method {method}")

    def drain_notifications(self, *, limit: int = 256) -> list[dict[str, Any]]:
        result = self.notifications[:limit]
        self.notifications = self.notifications[limit:]
        return result

    async def close(self) -> None:
        self.closed = True
        self.initialized = False
        self.connection_generation += 1
        self.notifications.clear()


async def _inspect(
    coordinator: CodexExistingThreadSubscription,
    cwd: Path,
) -> CodexSelectedThread:
    return await coordinator.inspect_thread(
        pex_session_id="codex:thread-1",
        thread_id="thread-1",
        project_id="pex-project-1",
        cwd=str(cwd),
    )


def _authorization(
    selected: CodexSelectedThread,
    *,
    allow_resume: bool = True,
    update: dict[str, Any] | None = None,
) -> CodexSubscriptionAuthorization:
    values: dict[str, Any] = {
        "authorization_id": "operator-authorization-1",
        "selection_id": selected.selection_id,
        "endpoint_identity": selected.endpoint_identity,
        "connection_generation": selected.connection_generation,
        "pex_session_id": selected.pex_session_id,
        "thread_id": selected.thread_id,
        "project_id": selected.project_id,
        "allow_resume": allow_resume,
    }
    values.update(update or {})
    return CodexSubscriptionAuthorization(**values)


def _notification(
    method: str,
    params: dict[str, Any],
    *,
    generation: int = 1,
    shared_server_request: bool = False,
) -> dict[str, Any]:
    return {
        "method": method,
        "params": params,
        "shared_server_request": shared_server_request,
        "connection_generation": generation,
    }


@pytest.mark.asyncio
async def test_inspection_reads_identity_without_resuming_or_inventing_events(
    tmp_path: Path,
) -> None:
    response = _thread_response(
        tmp_path,
        turns=[{"id": "turn-1", "status": "completed", "items": [{"id": "item-1"}]}],
    )
    transport = FakeSharedTransport([response], _thread_response(tmp_path, include_turns=False))
    coordinator = CodexExistingThreadSubscription(transport)

    selected = await _inspect(coordinator, tmp_path)

    assert transport.calls == [
        ("thread/read", {"threadId": "thread-1", "includeTurns": True})
    ]
    assert selected.root_session_id == "root-session-1"
    assert selected.project_id == "pex-project-1"
    assert selected.vendor_project_id == "vendor-project-1"
    assert len(selected.history_ids) == 2
    assert len(set(selected.history_ids)) == 2
    assert [record.method for record in selected.history_records] == [
        "history/turn",
        "history/item",
    ]
    assert all(record.source == "history" for record in selected.history_records)
    assert all(record.live_sequence is None for record in selected.history_records)
    assert not any(hasattr(record, "timestamp") for record in selected.history_records)


@pytest.mark.asyncio
async def test_subscription_uses_exact_resume_and_reconciles_history_with_live_identity(
    tmp_path: Path,
) -> None:
    initial_turns = [{"id": "turn-1", "status": "inProgress", "items": [{"id": "item-1"}]}]
    post_turns = [
        {
            "id": "turn-1",
            "status": "completed",
            "items": [{"id": "item-1"}, {"id": "item-2"}],
        },
        {"id": "turn-2", "status": "completed", "items": []},
    ]
    completion = _notification(
        "turn/completed",
        {
            "threadId": "thread-1",
            "turn": {"id": "turn-2", "status": "completed", "items": []},
        },
    )

    def during_resume(transport: FakeSharedTransport) -> None:
        transport.notifications.extend([deepcopy(completion), deepcopy(completion)])

    initial = _thread_response(tmp_path, turns=initial_turns)
    transport = FakeSharedTransport(
        [initial, initial, _thread_response(tmp_path, turns=post_turns)],
        _thread_response(tmp_path, include_turns=False),
        on_resume=during_resume,
    )
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)

    state = await coordinator.subscribe(selected, _authorization(selected))

    assert [call for call in transport.calls] == [
        ("thread/read", {"threadId": "thread-1", "includeTurns": True}),
        ("thread/read", {"threadId": "thread-1", "includeTurns": True}),
        ("thread/resume", {"threadId": "thread-1"}),
        ("thread/read", {"threadId": "thread-1", "includeTurns": True}),
    ]
    assert state.receipt.schema == SUBSCRIPTION_SCHEMA
    assert transport.closed is False
    assert state.receipt.observation_only is True
    assert state.receipt.delivery_proven is False
    assert state.receipt.project_id == "pex-project-1"
    assert state.receipt.vendor_project_id == "vendor-project-1"
    assert state.runtime_status == "idle"
    assert state.receipt.history_record_count == 4
    assert state.receipt.reconciliation_live_watermark == 1
    assert len(state.reconciliation_records) == 1
    assert state.reconciliation_records[0].turn_id == "turn-2"
    assert state.reconciliation_records[0].method == "turn/completed"
    assert state.reconciliation_records[0].payload() == completion
    assert state.reconciled_history_shape == (
        ("turn-1", ("item-1", "item-2")),
        ("turn-2", ()),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("allow_resume", "update"),
    [
        (False, None),
        (True, {"selection_id": "foreign-selection"}),
        (True, {"thread_id": "foreign-thread"}),
        (True, {"connection_generation": 2}),
    ],
)
async def test_missing_or_foreign_authorization_never_resumes(
    tmp_path: Path,
    allow_resume: bool,
    update: dict[str, Any] | None,
) -> None:
    response = _thread_response(tmp_path)
    transport = FakeSharedTransport([response], _thread_response(tmp_path, include_turns=False))
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)

    with pytest.raises(CodexSubscriptionError, match="authorized|binding mismatch"):
        await coordinator.subscribe(
            selected,
            _authorization(selected, allow_resume=allow_resume, update=update),
        )

    assert [method for method, _ in transport.calls] == ["thread/read"]


@pytest.mark.asyncio
async def test_resume_identity_mismatch_fails_after_exact_non_mutating_request(
    tmp_path: Path,
) -> None:
    response = _thread_response(tmp_path)
    resume = _thread_response(
        tmp_path, include_turns=False, thread_update={"sessionId": "foreign-root"}
    )
    transport = FakeSharedTransport([response, response], resume)
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)

    with pytest.raises(CodexSubscriptionError, match="identity mismatch"):
        await coordinator.subscribe(selected, _authorization(selected))

    assert transport.calls[-1] == ("thread/resume", {"threadId": "thread-1"})
    assert all(method not in {"turn/start", "thread/start"} for method, _ in transport.calls)
    assert transport.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_post",
    [
        [{"id": "turn-2", "items": []}, {"id": "turn-1", "items": []}],
        [{"id": "turn-1", "items": [], "truncated": True}],
    ],
)
async def test_reordered_or_truncated_reconciliation_never_becomes_live_state(
    tmp_path: Path,
    bad_post: list[dict[str, Any]],
) -> None:
    initial = _thread_response(tmp_path, turns=[{"id": "turn-1", "items": []}])
    if bad_post[0].pop("truncated", False):
        post = _thread_response(
            tmp_path,
            turns=bad_post,
            thread_update={"truncated": True},
        )
    else:
        post = _thread_response(tmp_path, turns=bad_post)
    transport = FakeSharedTransport(
        [initial, initial, post], _thread_response(tmp_path, include_turns=False)
    )
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)

    with pytest.raises(CodexSubscriptionError, match="reordered|truncated"):
        await coordinator.subscribe(selected, _authorization(selected))

    assert coordinator.state is None
    assert transport.closed is True


@pytest.mark.asyncio
async def test_generation_change_during_resume_invalidates_attempt(tmp_path: Path) -> None:
    response = _thread_response(tmp_path)

    def reconnect(transport: FakeSharedTransport) -> None:
        transport.connection_generation += 1

    transport = FakeSharedTransport(
        [response, response],
        _thread_response(tmp_path, include_turns=False),
        on_resume=reconnect,
    )
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)

    with pytest.raises(CodexSubscriptionError, match="generation changed"):
        await coordinator.subscribe(selected, _authorization(selected))

    assert [method for method, _ in transport.calls] == [
        "thread/read",
        "thread/read",
        "thread/resume",
    ]
    assert transport.closed is True


async def _subscribed(
    tmp_path: Path,
) -> tuple[CodexExistingThreadSubscription, FakeSharedTransport]:
    response = _thread_response(tmp_path, turns=[{"id": "turn-1", "items": []}])
    transport = FakeSharedTransport(
        [response, response, response], _thread_response(tmp_path, include_turns=False)
    )
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)
    await coordinator.subscribe(selected, _authorization(selected))
    return coordinator, transport


@pytest.mark.asyncio
async def test_foreign_or_missing_live_identity_invalidates_subscription(tmp_path: Path) -> None:
    coordinator, transport = await _subscribed(tmp_path)
    transport.notifications.append(
        _notification(
            "turn/started",
            {"threadId": "foreign", "turn": {"id": "turn-2"}},
        )
    )

    with pytest.raises(CodexSubscriptionError, match="another thread"):
        await coordinator.drain_live()

    assert coordinator.state is not None
    assert coordinator.state.active is False
    assert coordinator.state.invalidation_reason == "foreign_thread_notification"


@pytest.mark.asyncio
async def test_live_order_and_duplicate_watermarks_are_exact(tmp_path: Path) -> None:
    coordinator, transport = await _subscribed(tmp_path)
    started = _notification(
        "turn/started", {"threadId": "thread-1", "turn": {"id": "turn-2"}}
    )
    completed = _notification(
        "turn/completed", {"threadId": "thread-1", "turn": {"id": "turn-2"}}
    )
    transport.notifications.extend([started, completed, deepcopy(completed)])

    batch = await coordinator.drain_live()

    assert batch.after_live_watermark == 0
    assert batch.live_watermark == 2
    assert [record.live_sequence for record in batch.records] == [1, 2]
    assert [record.method for record in batch.records] == ["turn/started", "turn/completed"]

    transport.notifications.append(deepcopy(started))
    with pytest.raises(CodexSubscriptionError, match="order regressed"):
        await coordinator.drain_live()


@pytest.mark.asyncio
async def test_missing_root_identity_and_history_pagination_fail_closed(tmp_path: Path) -> None:
    missing_root = _thread_response(
        tmp_path,
        thread_update={"sessionId": None},
        response_update={"sessionId": None},
    )
    transport = FakeSharedTransport(
        [missing_root], _thread_response(tmp_path, include_turns=False)
    )
    with pytest.raises(CodexSubscriptionError, match="root session"):
        await _inspect(CodexExistingThreadSubscription(transport), tmp_path)

    paged = _thread_response(tmp_path, response_update={"nextCursor": "more"})
    transport = FakeSharedTransport([paged], _thread_response(tmp_path, include_turns=False))
    with pytest.raises(CodexSubscriptionError, match="truncated"):
        await _inspect(CodexExistingThreadSubscription(transport), tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "notification",
    [
        _notification("turn/started", {"turn": {"id": "turn-2"}}),
        _notification("turn/started", {"threadId": "thread-1"}),
        {
            "method": "turn/started",
            "params": {"threadId": "thread-1", "turn": {"id": "turn-2"}},
            "shared_server_request": False,
        },
        {
            "method": "turn/started",
            "params": {"threadId": "thread-1", "turn": {"id": "turn-2"}},
            "connection_generation": 1,
        },
    ],
)
async def test_malformed_live_identity_or_envelope_invalidates_subscription(
    tmp_path: Path,
    notification: dict[str, Any],
) -> None:
    coordinator, transport = await _subscribed(tmp_path)
    transport.notifications.append(notification)

    with pytest.raises(CodexSubscriptionError):
        await coordinator.drain_live()

    assert coordinator.state is not None
    assert coordinator.state.active is False
    assert coordinator.state.invalidation_reason is not None


@pytest.mark.asyncio
async def test_notification_from_prior_connection_generation_is_never_rebound(
    tmp_path: Path,
) -> None:
    coordinator, transport = await _subscribed(tmp_path)
    transport.notifications.append(
        _notification(
            "turn/started",
            {"threadId": "thread-1", "turn": {"id": "turn-2"}},
            generation=2,
        )
    )

    with pytest.raises(CodexSubscriptionError, match="connection generation"):
        await coordinator.drain_live()

    assert coordinator.state is not None
    assert coordinator.state.active is False
    assert coordinator.state.invalidation_reason == "foreign_notification_generation"


@pytest.mark.asyncio
async def test_notification_retention_overflow_invalidates_without_exposing_records(
    tmp_path: Path,
) -> None:
    coordinator, transport = await _subscribed(tmp_path)
    transport.notifications.extend(
        _notification("account/updated", {}) for _ in range(1_025)
    )

    with pytest.raises(CodexSubscriptionError, match="safety bound"):
        await coordinator.drain_live()

    assert coordinator.state is not None
    assert coordinator.state.active is False
    assert coordinator.state.invalidation_reason == "notification_retention_bound"


@pytest.mark.asyncio
async def test_notification_byte_overflow_invalidates_without_exposing_records(
    tmp_path: Path,
) -> None:
    coordinator, transport = await _subscribed(tmp_path)
    transport.notifications.extend(
        _notification("account/updated", {"value": "x" * 900_000}) for _ in range(5)
    )

    with pytest.raises(CodexSubscriptionError, match="byte bound"):
        await coordinator.drain_live()

    assert coordinator.state is not None
    assert coordinator.state.active is False
    assert coordinator.state.invalidation_reason == "notification_retention_bound"


@pytest.mark.asyncio
async def test_stale_pre_resume_notifications_block_resume(tmp_path: Path) -> None:
    response = _thread_response(tmp_path)
    transport = FakeSharedTransport(
        [response, response], _thread_response(tmp_path, include_turns=False)
    )
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)
    transport.notifications.append(
        _notification(
            "turn/started",
            {"threadId": "thread-1", "turn": {"id": "turn-stale"}},
        )
    )

    with pytest.raises(CodexSubscriptionError, match="queue was not clean"):
        await coordinator.subscribe(selected, _authorization(selected))

    assert [method for method, _ in transport.calls] == ["thread/read", "thread/read"]


@pytest.mark.asyncio
async def test_global_pre_resume_notification_does_not_require_silent_server(
    tmp_path: Path,
) -> None:
    response = _thread_response(tmp_path)
    transport = FakeSharedTransport(
        [response, response, response], _thread_response(tmp_path, include_turns=False)
    )
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)
    transport.notifications.append(_notification("account/updated", {}))

    state = await coordinator.subscribe(selected, _authorization(selected))

    assert state.active is True
    assert [method for method, _ in transport.calls] == [
        "thread/read",
        "thread/read",
        "thread/resume",
        "thread/read",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["generation", "history_payload"])
async def test_forged_selection_cannot_authorize_resume(
    tmp_path: Path,
    tamper: str,
) -> None:
    response = _thread_response(
        tmp_path, turns=[{"id": "turn-1", "items": [{"id": "item-1"}]}]
    )
    transport = FakeSharedTransport(
        [response], _thread_response(tmp_path, include_turns=False)
    )
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)
    if tamper == "generation":
        forged = replace(selected, connection_generation=True)
    else:
        records = list(selected.history_records)
        records[1] = replace(records[1], payload_json='{"forged":true,"id":"item-1"}')
        forged = replace(selected, history_records=tuple(records))

    with pytest.raises(CodexSubscriptionError):
        await coordinator.subscribe(forged, _authorization(forged))

    assert [method for method, _ in transport.calls] == ["thread/read"]


@pytest.mark.asyncio
async def test_delimiter_bearing_vendor_ids_have_distinct_derived_record_ids(
    tmp_path: Path,
) -> None:
    response = _thread_response(
        tmp_path,
        turns=[
            {"id": "a:item:b", "items": []},
            {"id": "a", "items": [{"id": "b"}]},
        ],
    )
    transport = FakeSharedTransport(
        [response], _thread_response(tmp_path, include_turns=False)
    )

    selected = await _inspect(CodexExistingThreadSubscription(transport), tmp_path)

    assert len(selected.history_ids) == 3
    assert len(set(selected.history_ids)) == 3


@pytest.mark.asyncio
async def test_conflicting_direct_input_capability_fails_selection(tmp_path: Path) -> None:
    conflicting = _thread_response(
        tmp_path,
        response_update={"canAcceptDirectInput": False},
    )
    transport = FakeSharedTransport(
        [conflicting], _thread_response(tmp_path, include_turns=False)
    )

    with pytest.raises(CodexSubscriptionError, match="capability conflicted"):
        await _inspect(CodexExistingThreadSubscription(transport), tmp_path)

    assert [method for method, _ in transport.calls] == ["thread/read"]


@pytest.mark.asyncio
async def test_nullable_vendor_project_is_bound_separately_from_pex_project(
    tmp_path: Path,
) -> None:
    response = _thread_response(
        tmp_path,
        thread_update={"projectId": None},
        response_update={"projectId": None},
    )
    transport = FakeSharedTransport(
        [response], _thread_response(tmp_path, include_turns=False)
    )

    selected = await _inspect(CodexExistingThreadSubscription(transport), tmp_path)

    assert selected.project_id == "pex-project-1"
    assert selected.vendor_project_id is None


@pytest.mark.asyncio
async def test_null_vendor_project_remains_bound_across_resume_and_receipt(
    tmp_path: Path,
) -> None:
    null_project = _thread_response(
        tmp_path,
        thread_update={"projectId": None},
        response_update={"projectId": None},
    )
    null_resume = _thread_response(
        tmp_path,
        include_turns=False,
        thread_update={"projectId": None},
        response_update={"projectId": None},
    )
    transport = FakeSharedTransport(
        [null_project, null_project, null_project], null_resume
    )
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)

    state = await coordinator.subscribe(selected, _authorization(selected))

    assert selected.vendor_project_id is None
    assert state.receipt.vendor_project_id is None


@pytest.mark.asyncio
async def test_missing_vendor_project_field_fails_closed(tmp_path: Path) -> None:
    response = _thread_response(tmp_path)
    response["thread"].pop("projectId")
    response.pop("projectId")
    transport = FakeSharedTransport(
        [response], _thread_response(tmp_path, include_turns=False)
    )

    with pytest.raises(CodexSubscriptionError, match="vendor project field"):
        await _inspect(CodexExistingThreadSubscription(transport), tmp_path)


@pytest.mark.asyncio
async def test_expected_vendor_project_mismatch_fails_selection(tmp_path: Path) -> None:
    response = _thread_response(tmp_path)
    transport = FakeSharedTransport(
        [response], _thread_response(tmp_path, include_turns=False)
    )

    with pytest.raises(CodexSubscriptionError, match="vendor project"):
        await CodexExistingThreadSubscription(transport).inspect_thread(
            pex_session_id="codex:thread-1",
            thread_id="thread-1",
            project_id="pex-project-1",
            cwd=str(tmp_path),
            expected_vendor_project_id="foreign-vendor-project",
        )

    assert [method for method, _ in transport.calls] == ["thread/read"]


@pytest.mark.asyncio
async def test_conflicting_duplicate_live_identity_invalidates(tmp_path: Path) -> None:
    coordinator, transport = await _subscribed(tmp_path)
    started = _notification(
        "turn/started",
        {"threadId": "thread-1", "turn": {"id": "turn-2", "status": "running"}},
    )
    conflicting = deepcopy(started)
    conflicting["params"]["turn"]["status"] = "different"
    transport.notifications.extend([started, conflicting])

    with pytest.raises(CodexSubscriptionError, match="conflicting content"):
        await coordinator.drain_live()

    assert coordinator.state is not None
    assert coordinator.state.active is False
    assert coordinator.state.invalidation_reason == "conflicting_duplicate_notification"


@pytest.mark.asyncio
async def test_conflicting_flat_and_nested_live_identity_invalidates(tmp_path: Path) -> None:
    coordinator, transport = await _subscribed(tmp_path)
    transport.notifications.append(
        _notification(
            "turn/started",
            {
                "threadId": "thread-1",
                "turnId": "turn-2",
                "turn": {"id": "turn-foreign"},
            },
        )
    )

    with pytest.raises(CodexSubscriptionError, match="conflicting turn identity"):
        await coordinator.drain_live()

    assert coordinator.state is not None
    assert coordinator.state.active is False
    assert coordinator.state.invalidation_reason == "conflicting_notification_identity"


@pytest.mark.asyncio
async def test_nullable_model_and_originator_remain_honest_selection_fields(
    tmp_path: Path,
) -> None:
    response = _thread_response(tmp_path)
    for field in ("model", "originator"):
        response["thread"].pop(field)
        response.pop(field)
    transport = FakeSharedTransport(
        [response], _thread_response(tmp_path, include_turns=False)
    )

    selected = await _inspect(CodexExistingThreadSubscription(transport), tmp_path)

    assert selected.model is None
    assert selected.originator_json is None


@pytest.mark.asyncio
async def test_unknown_runtime_status_never_becomes_active(tmp_path: Path) -> None:
    unknown = _thread_response(
        tmp_path, thread_update={"status": {"type": "futureStatus"}}
    )
    transport = FakeSharedTransport(
        [unknown, unknown, unknown], _thread_response(tmp_path, include_turns=False)
    )
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)

    state = await coordinator.subscribe(selected, _authorization(selected))

    assert state.runtime_status == "unknown"


@pytest.mark.asyncio
async def test_post_read_runtime_status_is_state_not_selection_identity(
    tmp_path: Path,
) -> None:
    idle = _thread_response(tmp_path, thread_update={"status": {"type": "idle"}})
    active = _thread_response(tmp_path, thread_update={"status": {"type": "active"}})
    transport = FakeSharedTransport(
        [idle, idle, active], _thread_response(tmp_path, include_turns=False)
    )
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)

    state = await coordinator.subscribe(selected, _authorization(selected))

    assert state.runtime_status == "active"
    assert not hasattr(selected, "runtime_status")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flags", "expected_status"),
    [([], "working"), (["waitingOnApproval"], "blocked"), (["futureFlag"], "discovered")],
)
async def test_post_resume_runtime_flags_reach_initial_adapter(
    tmp_path: Path, flags: list[str], expected_status: str
) -> None:
    idle = _thread_response(tmp_path)
    active = _thread_response(
        tmp_path, thread_update={"status": {"type": "active", "activeFlags": flags}}
    )
    transport = FakeSharedTransport([idle, idle, active], idle)
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)

    state = await coordinator.subscribe(selected, _authorization(selected))

    assert state.runtime_status == "active"
    assert state.runtime_flags == tuple(flags)
    assert not hasattr(selected, "runtime_flags")
    assert not hasattr(state.receipt, "runtime_flags")
    adapter = CodexSharedAdapter(coordinator)
    assert adapter.session.status.value == expected_status
    assert adapter.session.last_activity is None
    await transport.close()


@pytest.mark.asyncio
async def test_flags_only_live_change_updates_state_and_clears_on_idle(tmp_path: Path) -> None:
    coordinator, transport = await _subscribed(tmp_path)
    for status, expected_flags in [
        ({"type": "active", "activeFlags": []}, ()),
        ({"type": "active", "activeFlags": ["waitingOnApproval"]}, ("waitingOnApproval",)),
        ({"type": "active", "activeFlags": ["futureFlag"]}, ("futureFlag",)),
        ({"type": "idle"}, ()),
    ]:
        transport.notifications.append(
            _notification("thread/status/changed", {"threadId": "thread-1", "status": status})
        )
        batch = await coordinator.drain_live()
        assert len(batch.records) == 1
        assert coordinator.state is not None
        assert coordinator.state.runtime_status == status["type"]
        assert coordinator.state.runtime_flags == expected_flags
    await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("flags", ["waitingOnApproval", None, {}, True, [1], [None]])
@pytest.mark.parametrize("stage", ["inspect", "post_resume", "live"])
async def test_malformed_runtime_flags_fail_closed(
    tmp_path: Path, flags: object, stage: str
) -> None:
    malformed = _thread_response(
        tmp_path, thread_update={"status": {"type": "active", "activeFlags": flags}}
    )
    normal = _thread_response(tmp_path)
    if stage == "live":
        coordinator, transport = await _subscribed(tmp_path)
        transport.notifications.append(
            _notification(
                "thread/status/changed",
                {"threadId": "thread-1", "status": malformed["thread"]["status"]},
            )
        )
        with pytest.raises(CodexSubscriptionError, match="runtime flags"):
            await coordinator.drain_live()
        assert coordinator.state is not None
        assert not coordinator.state.active
        await transport.close()
        return
    reads = [malformed] if stage == "inspect" else [normal, normal, malformed]
    transport = FakeSharedTransport(reads, normal)
    coordinator = CodexExistingThreadSubscription(transport)
    if stage == "inspect":
        with pytest.raises(CodexSubscriptionError, match="runtime flags"):
            await _inspect(coordinator, tmp_path)
        assert not any(method == "thread/resume" for method, _ in transport.calls)
        await transport.close()
    else:
        selected = await _inspect(coordinator, tmp_path)
        with pytest.raises(CodexSubscriptionError, match="runtime flags"):
            await coordinator.subscribe(selected, _authorization(selected))
        assert coordinator.state is None
        assert transport.closed


@pytest.mark.asyncio
async def test_nested_thread_started_and_status_change_are_preserved_without_turn(
    tmp_path: Path,
) -> None:
    coordinator, transport = await _subscribed(tmp_path)
    transport.notifications.extend(
        [
            _notification("thread/started", {"thread": {"id": "thread-1"}}),
            _notification(
                "thread/status/changed",
                {
                    "thread": {
                        "id": "thread-1",
                        "status": {"type": "active"},
                    }
                },
            ),
        ]
    )

    batch = await coordinator.drain_live()

    assert [record.method for record in batch.records] == [
        "thread/started",
        "thread/status/changed",
    ]
    assert all(record.turn_id == "" and record.item_id is None for record in batch.records)
    assert coordinator.state is not None
    assert coordinator.state.runtime_status == "active"


@pytest.mark.asyncio
async def test_live_identity_lifetime_bound_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subscription_module, "MAX_LIVE_IDENTITIES", 2)
    coordinator, transport = await _subscribed(tmp_path)
    transport.notifications.extend(
        _notification(
            "thread/status/changed",
            {"threadId": "thread-1", "status": {"type": status}},
        )
        for status in ("active", "idle", "active")
    )

    with pytest.raises(CodexSubscriptionError, match="lifetime bound"):
        await coordinator.drain_live()

    assert coordinator.state is not None
    assert coordinator.state.active is False
    assert coordinator.state.invalidation_reason == "live_identity_bound"


@pytest.mark.asyncio
async def test_existing_history_item_content_may_change_during_resume(
    tmp_path: Path,
) -> None:
    initial = _thread_response(
        tmp_path,
        turns=[{"id": "turn-1", "items": [{"id": "item-1", "text": "partial"}]}],
    )
    updated = _thread_response(
        tmp_path,
        turns=[{"id": "turn-1", "items": [{"id": "item-1", "text": "complete"}]}],
    )
    transport = FakeSharedTransport(
        [initial, updated, updated], _thread_response(tmp_path, include_turns=False)
    )
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)

    state = await coordinator.subscribe(selected, _authorization(selected))

    assert selected.history_records[1].payload()["text"] == "partial"
    assert state.reconciled_history_records[1].payload()["text"] == "complete"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["thread/closed", "thread/archived", "thread/deleted"])
async def test_selected_thread_lifecycle_ends_only_observer_connection(
    tmp_path: Path, method: str,
) -> None:
    coordinator, transport = await _subscribed(tmp_path)
    calls_before = deepcopy(transport.calls)
    transport.notifications.extend([
        _notification(method, {"threadId": "thread-1"}),
        _notification("turn/started", {"threadId": "thread-1", "turn": {"id": "later"}}),
    ])

    with pytest.raises(CodexSubscriptionError, match="became unavailable"):
        await coordinator.drain_live()

    assert coordinator.state is not None
    assert not coordinator.state.active
    assert coordinator.state.invalidation_reason == f"vendor_{method.replace('/', '_')}"
    assert transport.closed
    assert transport.calls == calls_before
    with pytest.raises(CodexSubscriptionError, match="not active"):
        await coordinator.drain_live()
    assert transport.calls == calls_before


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["thread/closed", "thread/archived", "thread/deleted"])
async def test_thread_closure_during_reconciliation_never_publishes_subscription(
    tmp_path: Path, method: str,
) -> None:
    response = _thread_response(tmp_path)

    def closed_during_resume(transport: FakeSharedTransport) -> None:
        transport.notifications.append(_notification(method, {"threadId": "thread-1"}))

    transport = FakeSharedTransport(
        [response, response, response],
        _thread_response(tmp_path, include_turns=False),
        on_resume=closed_during_resume,
    )
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await _inspect(coordinator, tmp_path)

    with pytest.raises(CodexSubscriptionError, match="became unavailable"):
        await coordinator.subscribe(selected, _authorization(selected))

    assert coordinator.state is None
    assert transport.closed
    assert [method for method, _ in transport.calls] == [
        "thread/read", "thread/read", "thread/resume", "thread/read",
    ]


@pytest.mark.asyncio
async def test_turn_error_and_warning_do_not_imply_thread_or_connection_closure(
    tmp_path: Path,
) -> None:
    coordinator, transport = await _subscribed(tmp_path)
    transport.notifications.extend([
        _notification("warning", {"threadId": "thread-1", "message": "recoverable"}),
        _notification("error", {
            "threadId": "thread-1", "turnId": "turn-1",
            "error": {"message": "turn failed"},
        }),
        _notification("turn/completed", {
            "threadId": "thread-1", "turn": {
                "id": "turn-1", "status": "failed", "error": {"message": "turn failed"},
            },
        }),
    ])

    batch = await coordinator.drain_live()

    # This coordinator currently projects lifecycle records only. The omitted
    # diagnostics are not a complete raw-event capture or successful completion.
    assert [record.method for record in batch.records] == ["turn/completed"]
    assert batch.records[0].payload()["params"]["turn"]["status"] == "failed"
    assert coordinator.state is not None and coordinator.state.active
    assert not transport.closed
