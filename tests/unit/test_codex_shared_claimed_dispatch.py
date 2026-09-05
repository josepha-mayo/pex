from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pex_bridge.adapters.codex_shared import (
    CodexSharedAppServerTransport,
    SharedCodexDeliveryUncertainError,
    SharedCodexTextDispatchCancelled,
    SharedCodexTextDispatchRejected,
)
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.adapters.codex_subscription import (
    CodexExistingThreadSubscription,
    CodexSubscriptionAuthorization,
)
from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads
from pex_bridge.codex_correction import canonical
from pex_bridge.codex_input_baseline import CodexInputBaseline
from pex_bridge.codex_input_provenance import CodexInputProvenance
from pex_bridge.codex_received_journal import CodexReceivedJournal
from test_codex_shared_transport import MemoryAppServerChannel


def user_item(item_id: str, text: str, *, client_id: str | None = None) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "userMessage",
        "clientId": client_id,
        "content": [{"type": "text", "text": text, "text_elements": []}],
    }


def thread_response(
    cwd: Path,
    turns: list[dict[str, Any]],
    *,
    include_turns: bool = True,
) -> dict[str, Any]:
    thread: dict[str, Any] = {
        "id": "thr_exact",
        "sessionId": "root-exact",
        "projectId": "vendor-project",
        "cwd": str(cwd),
        "source": "cli",
        "originator": "codex-cli",
        "model": "gpt-test",
        "modelProvider": "openai",
        "canAcceptDirectInput": True,
        "status": {
            "type": "active" if any(turn["status"] == "inProgress" for turn in turns) else "idle",
            **(
                {"activeFlags": []}
                if any(turn["status"] == "inProgress" for turn in turns)
                else {}
            ),
        },
    }
    if include_turns:
        thread["turns"] = deepcopy(turns)
    return {
        "thread": thread,
        **{key: thread[key] for key in (
            "sessionId", "projectId", "cwd", "source", "originator", "model",
            "modelProvider", "canAcceptDirectInput", "status",
        )},
    }


class ClaimedDispatchChannel(MemoryAppServerChannel):
    """Real framed transport with explicit fake App Server I/O."""

    def __init__(self, cwd: Path, *, active: bool = False) -> None:
        super().__init__(withhold={"thread/read", "thread/resume", "turn/start", "turn/steer"})
        self.cwd = cwd
        self.turns = [{
            "id": "turn-existing",
            "status": "inProgress" if active else "completed",
            "itemsView": "full",
            "items": [user_item("human-1", "original human goal")],
        }]
        self.dispatch_written = asyncio.Event()
        self.hold_dispatch_response = False
        self.hold_control_read = False
        self.control_read_entered = asyncio.Event()
        self.release_control_read = asyncio.Event()

    async def write(self, data: bytes) -> None:
        before = len(self.messages)
        await super().write(data)
        for message in self.messages[before:]:
            method = message.get("method")
            if "id" not in message:
                continue
            if method == "thread/read":
                if self.hold_control_read:
                    self.control_read_entered.set()
                    await self.release_control_read.wait()
                result = thread_response(self.cwd, self.turns)
            elif method == "thread/resume":
                result = thread_response(self.cwd, self.turns, include_turns=False)
            elif method in {"turn/start", "turn/steer"}:
                self.dispatch_written.set()
                if self.hold_dispatch_response:
                    continue
                if method == "turn/start":
                    result = {
                        "turn": {"id": "turn-new", "status": "inProgress", "items": []}
                    }
                else:
                    result = {"turnId": message["params"]["expectedTurnId"]}
            else:
                continue
            await self.emit({"id": message["id"], "result": result})


async def attached(
    tmp_path: Path,
    *,
    active: bool = False,
    request_timeout_s: float = 1,
) -> tuple[CodexSharedAdapter, ClaimedDispatchChannel]:
    channel = ClaimedDispatchChannel(tmp_path, active=active)
    executable, endpoint = tmp_path / "codex.exe", tmp_path / "codex.sock"
    executable.write_bytes(b"fake executable")
    endpoint.write_bytes(b"fake endpoint")
    journal = CodexReceivedJournal(
        tmp_path / "received.sqlite3",
        inspection_id=uuid4().hex,
        provenance={"fixture": True, "requested_thread": "thr_exact"},
    )

    async def factory(_argv):
        return channel

    transport = CodexSharedAppServerTransport(
        executable,
        endpoint,
        "thr_exact",
        channel_factory=factory,
        endpoint_validator=lambda _executable, _endpoint: None,
        connect_timeout_s=1,
        request_timeout_s=request_timeout_s,
        receive_journal=journal,
    )
    coordinator = CodexExistingThreadSubscription(transport)
    selected = await coordinator.inspect_thread(
        pex_session_id="codex:thr_exact",
        thread_id="thr_exact",
        project_id="pex-project",
        cwd=str(tmp_path),
    )
    authorization = CodexSubscriptionAuthorization(
        authorization_id="authorization-exact",
        selection_id=selected.selection_id,
        endpoint_identity=selected.endpoint_identity,
        connection_generation=selected.connection_generation,
        pex_session_id=selected.pex_session_id,
        thread_id=selected.thread_id,
        project_id=selected.project_id,
        allow_resume=True,
    )
    await coordinator.subscribe(selected, authorization)
    adapter = CodexSharedAdapter(coordinator)
    initial = CodexInputProvenance.from_store_records(
        (), session_id=adapter.session.id, thread_id=adapter.session.vendor_session_id
    )
    adapter._input_provenance = initial
    adapter._input_baseline = CodexInputBaseline.from_selected(selected, initial)
    adapter._input_bootstrap_complete = True
    return adapter, channel


def correction_and_records(adapter: CodexSharedAdapter) -> tuple[str, tuple[str, ...]]:
    receipt = adapter.session.metadata["subscription_receipt"]
    correction = {
        "schema": "pex.codex-correction.v1",
        "event_id": "event-exact",
        "effect_id": "effect-exact",
        "intervention_id": "intervention-exact",
        "client_message_id": "pex-correction-exact",
        "content": [{
            "type": "text",
            "text": "The artifact has 27 rows; criterion 3 requires 30. Complete it.",
            "text_elements": [],
        }],
        "session_id": adapter.session.id,
        "thread_id": adapter.session.vendor_session_id,
        "root_session_id": adapter._selected.root_session_id,
        "vendor_project_id": adapter._selected.vendor_project_id,
        "project_binding": "identity:fixture-project",
        "workspace_binding": {
            "project_id": "pex-project", "project_binding": "identity:fixture-project"
        },
        "subscription_receipt": receipt,
    }
    encoded = canonical(correction)
    return encoded, (canonical({
        "correction": correction, "effect_state": "dispatching", "effect_version": 1,
    }),)


def dispatch_args(adapter: CodexSharedAdapter) -> dict[str, Any]:
    correction, records = correction_and_records(adapter)
    return {
        "correction_json": correction,
        "attribution_records": records,
        "accepted_baseline": adapter._input_baseline.snapshot(),
        "final_authority_check": lambda: None,
    }


def dispatch_writes(channel: ClaimedDispatchChannel) -> list[dict[str, Any]]:
    return [
        message for message in channel.messages
        if message.get("method") in {"turn/start", "turn/steer"}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("active", [False, True])
async def test_real_coordinator_transport_dispatches_idle_start_or_active_steer(
    tmp_path: Path, active: bool,
) -> None:
    adapter, channel = await attached(tmp_path, active=active)
    before_revision = adapter._input_baseline.snapshot().revision
    try:
        result = await adapter._dispatch_claimed_text(**dispatch_args(adapter))
        write = dispatch_writes(channel)
        assert len(write) == 1
        assert write[0]["method"] == ("turn/steer" if active else "turn/start")
        assert write[0]["params"]["clientUserMessageId"] == "pex-correction-exact"
        assert result.accepted is True
        assert result.vendor_session_id == "thr_exact"
        assert result.vendor_turn_id == ("turn-existing" if active else "turn-new")
        assert adapter._input_baseline.snapshot().revision == before_revision + 1
    finally:
        await adapter.transport.close()


@pytest.mark.asyncio
async def test_exact_current_correction_must_be_registered_as_attempted(tmp_path: Path) -> None:
    adapter, channel = await attached(tmp_path)
    args = dispatch_args(adapter)
    args["attribution_records"] = ()
    try:
        with pytest.raises(SharedCodexTextDispatchRejected):
            await adapter._dispatch_claimed_text(**args)
        assert dispatch_writes(channel) == []
    finally:
        await adapter.transport.close()


@pytest.mark.asyncio
async def test_new_input_while_fresh_read_waits_refuses_without_dispatch(tmp_path: Path) -> None:
    adapter, channel = await attached(tmp_path)
    channel.hold_control_read = True
    task = asyncio.create_task(adapter._dispatch_claimed_text(**dispatch_args(adapter)))
    try:
        await asyncio.wait_for(channel.control_read_entered.wait(), 1)
        adapter._input_baseline.observe_item(
            turn_id="turn-later",
            item=user_item("human-later", "new human direction"),
            completed=True,
        )
        channel.turns.append({
            "id": "turn-later", "status": "completed", "itemsView": "full",
            "items": [user_item("human-later", "new human direction")],
        })
        channel.release_control_read.set()
        with pytest.raises(SharedCodexTextDispatchRejected):
            await task
        assert dispatch_writes(channel) == []
    finally:
        channel.release_control_read.set()
        await asyncio.gather(task, return_exceptions=True)
        await adapter.transport.close()


@pytest.mark.asyncio
async def test_final_authority_mutation_is_rechecked_before_enqueue(tmp_path: Path) -> None:
    adapter, channel = await attached(tmp_path)
    args = dispatch_args(adapter)

    def mutate_ledger() -> None:
        adapter._input_baseline.observe_item(
            turn_id="turn-race",
            item=user_item("human-race", "late human direction"),
            completed=True,
        )

    args["final_authority_check"] = mutate_ledger
    try:
        with pytest.raises(SharedCodexTextDispatchRejected):
            await adapter._dispatch_claimed_text(**args)
        assert dispatch_writes(channel) == []
    finally:
        await adapter.transport.close()


@pytest.mark.asyncio
async def test_new_input_while_transport_write_lock_waits_refuses_before_enqueue(
    tmp_path: Path, monkeypatch,
) -> None:
    adapter, channel = await attached(tmp_path)
    transport = adapter.transport
    original = transport._dispatch_text
    entered, release = asyncio.Event(), asyncio.Event()

    async def dispatch_behind_owned_lock(**kwargs):
        await transport._protocol_lock.acquire()
        sending = asyncio.create_task(original(**kwargs))
        entered.set()
        try:
            await release.wait()
        finally:
            transport._protocol_lock.release()
        return await sending

    monkeypatch.setattr(transport, "_dispatch_text", dispatch_behind_owned_lock)
    task = asyncio.create_task(adapter._dispatch_claimed_text(**dispatch_args(adapter)))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        adapter._input_baseline.observe_item(
            turn_id="turn-lock-race",
            item=user_item("human-lock-race", "new input before locked write"),
            completed=True,
        )
        release.set()
        with pytest.raises(SharedCodexTextDispatchRejected):
            await task
        assert dispatch_writes(channel) == []
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await transport.close()


@pytest.mark.asyncio
async def test_lost_ack_remains_delivery_uncertain_and_is_not_resent(tmp_path: Path) -> None:
    adapter, channel = await attached(tmp_path, request_timeout_s=0.1)
    channel.hold_dispatch_response = True
    with pytest.raises(SharedCodexDeliveryUncertainError):
        await adapter._dispatch_claimed_text(**dispatch_args(adapter))
    assert len(dispatch_writes(channel)) == 1
    assert channel.closed


@pytest.mark.asyncio
async def test_post_enqueue_cancellation_keeps_transport_uncertainty(tmp_path: Path) -> None:
    adapter, channel = await attached(tmp_path)
    channel.hold_dispatch_response = True
    task = asyncio.create_task(adapter._dispatch_claimed_text(**dispatch_args(adapter)))
    try:
        await asyncio.wait_for(channel.dispatch_written.wait(), 1)
        task.cancel()
        with pytest.raises(SharedCodexTextDispatchCancelled):
            await task
        assert len(dispatch_writes(channel)) == 1
        assert channel.closed
    finally:
        await asyncio.gather(task, return_exceptions=True)
        await adapter.transport.close()


@pytest.mark.asyncio
async def test_generic_mutation_methods_remain_disabled(tmp_path: Path) -> None:
    adapter, channel = await attached(tmp_path)
    try:
        assert await adapter.send_message(adapter.session, "generic mutation") is False
        assert await adapter.continue_or_resume(adapter.session, "generic mutation") is False
        assert await adapter.respond_permission(adapter.session, "request", "allow") is False
        capabilities = await adapter.probe()
        assert capabilities.send_message is False
        assert capabilities.resume is False
        assert capabilities.approve is False
        assert capabilities.deny is False
        assert dispatch_writes(channel) == []
    finally:
        await adapter.transport.close()


@pytest.mark.asyncio
async def test_noncanonical_correction_and_receipt_mutation_write_nothing(tmp_path: Path) -> None:
    adapter, channel = await attached(tmp_path)
    args = dispatch_args(adapter)
    decoded = strict_json_loads(args["correction_json"])
    decoded["subscription_receipt"] = {
        **decoded["subscription_receipt"], "authorization_id": "other"
    }
    args["correction_json"] = strict_json_dumps(decoded)
    try:
        with pytest.raises(SharedCodexTextDispatchRejected):
            await adapter._dispatch_claimed_text(**args)
        assert dispatch_writes(channel) == []
    finally:
        await adapter.transport.close()
