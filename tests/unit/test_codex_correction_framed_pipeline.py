"""Complete local shared-Codex correction composition with fake vendor I/O.

This proves local wiring only: the supervisor decision and in-memory App Server
are fixtures. It is not live Codex, provider, model, or submission evidence.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
import test_workspace_continuity_pipeline as continuity_fixture
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.codex_shared import CodexSharedAppServerTransport
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.adapters.codex_subscription import (
    CodexExistingThreadSubscription,
    CodexSubscriptionAuthorization,
)
from pex_bridge.bus import EventBus
from pex_bridge.codex_received_journal import CodexReceivedJournal
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, EventType
from pex_protocol.supervisor import SupervisorResult
from test_codex_correction_pipeline import CorrectionSupervisor
from test_codex_shared_claimed_dispatch import ClaimedDispatchChannel
from test_workspace_continuity_pipeline import bound_pipeline as _bound_pipeline_fixture


class EchoingClaimedDispatchChannel(ClaimedDispatchChannel):
    """Fake vendor that ACKs once and echoes the exact accepted user item."""

    async def write(self, data: bytes) -> None:
        before = len(self.messages)
        await super().write(data)
        for message in self.messages[before:]:
            method = message.get("method")
            if method not in {"turn/start", "turn/steer"} or self.hold_dispatch_response:
                continue
            params = message["params"]
            turn_id = params.get("expectedTurnId") or "turn-new"
            item = {
                "id": f"echo-{message['id']}",
                "type": "userMessage",
                "clientId": params["clientUserMessageId"],
                "content": deepcopy(params["input"]),
            }
            if method == "turn/start":
                self.turns.append({
                    "id": turn_id,
                    "status": "inProgress",
                    "itemsView": "full",
                    "items": [deepcopy(item)],
                })
                await self.emit({
                    "method": "turn/started",
                    "params": {
                        "threadId": params["threadId"],
                        "turn": {"id": turn_id},
                    },
                })
            else:
                active = next(turn for turn in self.turns if turn["id"] == turn_id)
                active["items"].append(deepcopy(item))
            await self.emit({
                "method": "item/completed",
                "params": {
                    "threadId": params["threadId"],
                    "turnId": turn_id,
                    "item": item,
                },
            })
            await self.emit({
                "method": "item/completed",
                "params": {
                    "threadId": params["threadId"],
                    "turnId": turn_id,
                    "item": {
                        "id": f"outcome-{message['id']}",
                        "type": "agentMessage",
                        "text": "Completed the missing rows and verified the public artifact.",
                    },
                },
            })


class OneCorrectionSupervisor:
    """One explicit semantic fixture decision; later lifecycle events are NOOP."""

    agentcore = None

    def __init__(self) -> None:
        self.calls = 0
        self.correction_calls = 0
        self._correction = CorrectionSupervisor()

    async def decide(self, request, *, local_model):
        self.calls += 1
        if (
            request.event.event_type == EventType.AGENT_RESPONSE
            and request.event.message_delta == "The public artifact is incomplete."
        ):
            self.correction_calls += 1
            return await self._correction.decide(request, local_model=local_model)
        return SupervisorResult(
            action=ProposedAction(
                type=InterventionType.NOOP,
                session_id=request.session.id,
                goal_id=request.session.goal_id,
                rationale="Fixture lifecycle observation needs no intervention.",
                evidence=[request.event.event_id],
                confidence=0.9,
                risk=RiskLevel.NONE,
                authority_required=Authority.LOCAL_POLICY,
            ),
            diagnosis="fixture_lifecycle_noop",
        )


async def enable_grant(store: Store, session_id: str) -> dict:
    status = await store.get_autonomous_correction_grant_status(session_id)
    assert status["enabled"] is False and status["scope"] is not None
    scope = status["scope"]
    return await store.set_session_autonomous_corrections(
        session_id,
        enabled=True,
        expected_control_revision=scope["control_revision"],
        expected_goal_id=scope["goal_id"],
        expected_goal_intent_revision=scope["goal_intent_revision"],
        expected_goal_intent_hash=scope["goal_intent_hash"],
        expected_project_binding=scope["project_binding"],
        expected_workspace_sha256=scope["workspace_sha256"],
        expected_subscription_authorization_id=scope["subscription_authorization_id"],
        expected_connection_generation=scope["connection_generation"],
        principal_id="local_bridge_operator",
        actor_assurance="bridge_bearer",
        idempotency_key="framed-pipeline-explicit-grant",
    )


@pytest.fixture
async def framed_pipeline(tmp_path, monkeypatch, request):
    active = bool(getattr(request, "param", False))
    channel_slot = []

    async def subscribed(workspace):
        channel = EchoingClaimedDispatchChannel(workspace, active=active)
        channel_slot.append(channel)
        executable = tmp_path / "codex.exe"
        endpoint = tmp_path / "codex.sock"
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
            request_timeout_s=1,
            receive_journal=journal,
        )
        coordinator = CodexExistingThreadSubscription(transport)
        selected = await coordinator.inspect_thread(
            pex_session_id="codex:thr_exact",
            thread_id="thr_exact",
            project_id="pex-project-1",
            cwd=str(workspace),
        )
        authorization = CodexSubscriptionAuthorization(
            authorization_id="framed-local-authorization",
            selection_id=selected.selection_id,
            endpoint_identity=selected.endpoint_identity,
            connection_generation=selected.connection_generation,
            pex_session_id=selected.pex_session_id,
            thread_id=selected.thread_id,
            project_id=selected.project_id,
            allow_resume=True,
        )
        await coordinator.subscribe(selected, authorization)
        return coordinator, transport

    original_start = CodexSharedAdapter.start_pipeline_pump

    def start_with_store_provenance(adapter, ingest, **kwargs):
        kwargs["provenance_loader"] = ingest.__self__.store.list_codex_correction_attributions
        return original_start(adapter, ingest, **kwargs)

    monkeypatch.setattr(continuity_fixture, "_subscribed", subscribed)
    monkeypatch.setattr(CodexSharedAdapter, "start_pipeline_pump", start_with_store_provenance)
    generator = _bound_pipeline_fixture.__wrapped__(tmp_path, monkeypatch)
    bound = await anext(generator)
    bound.pipeline.supervisor = OneCorrectionSupervisor()
    channel = channel_slot[0]

    async def wait_for_baseline():
        while bound.adapter._input_baseline is None:
            if bound.task.done():
                raise AssertionError(f"pump stopped: {bound.adapter.last_pump_error}")
            await asyncio.sleep(0.005)

    await asyncio.wait_for(wait_for_baseline(), 3)
    grant = await enable_grant(bound.store, bound.adapter.session.id)
    current = await bound.store.get_session(bound.adapter.session.id)
    bound.adapter.session = current
    bound.adapter.sessions[current.id] = current
    bound.adapter._normalizer.sessions[current.id] = current
    try:
        yield SimpleNamespace(bound=bound, channel=channel, grant=grant, active=active)
    finally:
        await generator.aclose()


async def emit_trigger(case) -> None:
    await case.channel.emit({
        "method": "item/completed",
        "params": {
            "threadId": case.bound.adapter.session.vendor_session_id,
            "turnId": "turn-existing",
            "item": {
                "id": "agent-trigger",
                "type": "agentMessage",
                "text": "The public artifact is incomplete.",
            },
        },
    })


async def initial_settled(case):
    async def wait():
        while True:
            events = await case.bound.store.recent_events(case.bound.adapter.session.id)
            for event in events:
                if event.event_type != EventType.AGENT_RESPONSE:
                    continue
                processing = await case.bound.store.get_event_processing(event.event_id)
                if processing and processing["state"] == "complete":
                    effect = await case.bound.store.get_event_effect(event.event_id, "main")
                    if effect is not None:
                        return event, processing, effect
            if case.bound.task.done():
                state = case.bound.adapter.subscription.state
                raise AssertionError(
                    f"pump stopped: {case.bound.adapter.last_pump_error}; "
                    f"reason={state and state.invalidation_reason}"
                )
            await asyncio.sleep(0.01)

    return await asyncio.wait_for(wait(), 8)


async def correction_echo_settled(case, effect_id: str):
    async def wait():
        events = await case.bound.store.recent_events(case.bound.adapter.session.id)
        for event in events:
            marker = event.metadata.get("pex_correction_observation") or {}
            if marker.get("effect_id") == effect_id:
                processing = await case.bound.store.get_event_processing(event.event_id)
                if processing and processing["state"] == "record_only_complete":
                    return event, processing
        if case.bound.task.done():
            raise AssertionError(f"pump stopped: {case.bound.adapter.last_pump_error}")
        return None

    async with asyncio.timeout(8):
        while True:
            result = await wait()
            if result is not None:
                return result
            await asyncio.sleep(0.01)


async def outcome_settled(case):
    async with asyncio.timeout(8):
        while True:
            for event in await case.bound.store.recent_events(
                case.bound.adapter.session.id
            ):
                if event.message_delta != (
                    "Completed the missing rows and verified the public artifact."
                ):
                    continue
                processing = await case.bound.store.get_event_processing(event.event_id)
                if processing and processing["state"] == "complete":
                    return event, processing
            if case.bound.task.done():
                raise AssertionError(f"pump stopped: {case.bound.adapter.last_pump_error}")
            await asyncio.sleep(0.01)


@pytest.mark.parametrize("framed_pipeline", [False, True], indirect=True)
async def test_idle_start_or_active_steer_is_durable_and_exactly_echoed(framed_pipeline):
    case = framed_pipeline
    await emit_trigger(case)
    event, processing, effect = await initial_settled(case)
    writes = [
        message for message in case.channel.messages
        if message.get("method") in {"turn/start", "turn/steer"}
    ]
    assert len(writes) == 1
    assert writes[0]["method"] == ("turn/steer" if case.active else "turn/start")
    assert effect["state"] == "delivered"
    assert processing["receipt"]["effect_state"] == "delivered"
    receipt = effect["result"]["worker_delivery_receipt"]
    assert receipt["target_session_id"] == case.bound.adapter.session.id
    assert receipt["vendor_session_id"] == case.bound.adapter.session.vendor_session_id
    assert receipt["vendor_turn_id"] == ("turn-existing" if case.active else "turn-new")
    correction = effect["payload"]["codex_correction"]
    assert writes[0]["params"]["clientUserMessageId"] == correction["client_message_id"]
    assert writes[0]["params"]["input"] == correction["content"]
    echoed, echo_processing = await correction_echo_settled(case, effect["effect_id"])
    assert echo_processing["mode"] == "record_only"
    assert echoed.event_type == EventType.STATUS
    assert case.bound.pipeline.supervisor.correction_calls == 1
    assert await case.bound.store.get_event_effect(echoed.event_id, "planner") is None
    outcome, outcome_processing = await outcome_settled(case)
    assert outcome.event_type == EventType.AGENT_RESPONSE
    assert outcome_processing["receipt"]["terminal_reason"] == "no_action"
    assert case.bound.pipeline.supervisor.correction_calls == 1
    assert len([
        message for message in case.channel.messages
        if message.get("method") in {"turn/start", "turn/steer"}
    ]) == 1
    assert event.event_id != echoed.event_id


async def test_lost_ack_is_recovered_uncertain_without_redelivery(
    framed_pipeline, tmp_path,
):
    case = framed_pipeline
    case.channel.hold_dispatch_response = True
    await emit_trigger(case)
    await asyncio.wait_for(case.channel.dispatch_written.wait(), 5)
    await asyncio.wait_for(asyncio.shield(case.bound.task), 8)

    events = [
        event for event in await case.bound.store.recent_events(case.bound.adapter.session.id)
        if event.event_type == EventType.AGENT_RESPONSE
    ]
    assert len(events) == 1
    event = events[0]
    processing = await case.bound.store.get_event_processing(event.event_id)
    effect = await case.bound.store.get_event_effect(event.event_id, "main")
    assert processing["state"] == "complete"
    assert processing["receipt"]["effect_state"] == "delivery_uncertain"
    assert processing["receipt"]["intervention"]["result"] in {
        "codex_delivery_uncertain",
        "worker_delivery_uncertain",
    }
    assert processing["receipt"]["intervention"]["outcome"] == (
        "worker_delivery_uncertain"
    )
    assert effect["state"] == "delivery_uncertain"

    restarted_store = Store(case.bound.store.path, process_boot_id="framed-restart")
    await restarted_store.connect()
    restarted = Pipeline(
        restarted_store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(home=tmp_path / "restart", require_auth=False),
    )
    try:
        # The original pump may finish its deferred follow-ups before the
        # disconnect is observed. Otherwise restart drains that same event;
        # neither ordering may reclaim or redeliver its sealed main effect.
        recovered = await restarted.recover_unfinished_events()
        assert recovered in ([], [event.event_id])
        terminal = await restarted_store.get_event_processing(event.event_id)
        assert terminal["state"] == "complete"
        assert terminal["receipt"]["effect_state"] == "delivery_uncertain"
        assert terminal["receipt"] == processing["receipt"]
        await restarted._resume_planned_event(terminal, owner="restart-review")
        assert len([
            message for message in case.channel.messages
            if message.get("method") in {"turn/start", "turn/steer"}
        ]) == 1
        assert (await restarted_store.get_event_effect(event.event_id, "main"))["state"] == (
            "delivery_uncertain"
        )
    finally:
        await restarted.close_presentations()
        await restarted_store.close()
