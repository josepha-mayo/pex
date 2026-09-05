"""Executor wiring with real workspace/adapter identity and explicit fake Store grants.

These tests do not prove grant eligibility, vendor delivery or model inference.
The separate Store and framed-transport suites exercise those local boundaries.
"""

import asyncio
import threading
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pex_bridge.adapters.base import AdapterMessageResult
from pex_bridge.adapters.codex_shared import SharedCodexTextDispatchRejected
from pex_bridge.executor import ActionExecutionResult, ClaimedMainEffect
from pex_bridge.store import utcnow
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import EventType, PolicyVerdict
from pex_protocol.session import HarnessEvent
from test_workspace_continuity_pipeline import _change_origin
from test_workspace_continuity_pipeline import bound_pipeline as bound_pipeline


@pytest.fixture
async def case(bound_pipeline, monkeypatch):
    bound = bound_pipeline
    executor = bound.pipeline.executor
    session = await bound.store.get_session(bound.adapter.session.id)
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE, session_id=session.id, goal_id=session.goal_id,
        payload={"text": "Check the missing public artifact."},
        rationale="Explicit test-only decision", evidence=["fixture-event"], confidence=0.9,
    )
    baseline = {
        "schema": "pex.codex-input-baseline.v1", "complete": True,
        "digest": "a" * 64, "revision": 4, "external_count": 1,
        "pending_count": 0, "reason": None,
    }
    event = HarnessEvent(
        event_id="fixture-event", session_id=session.id, harness_type=session.harness_type,
        ts=utcnow(), event_type=EventType.AGENT_RESPONSE,
        goal_id=session.goal_id, metadata={"pex_observer_snapshot": {"input_baseline": baseline}},
    )
    correction = {"fixture": "not a production correction; adapter boundary is mocked"}
    grant = {"granted": True, "effect": {"payload": {"codex_correction": correction}}}
    validation_threads = []

    async def validate(**kwargs):
        validation_threads.append(threading.get_ident())
        assert kwargs["event_id"] == event.event_id
        assert kwargs["effect_id"] == "fixture-effect"
        assert kwargs["effect_version"] == 2
        assert kwargs["owner"] == "fixture-owner"
        assert kwargs["expected_action"] == action.model_dump(mode="json")
        return grant

    validator = AsyncMock(side_effect=validate)
    monkeypatch.setattr(bound.store, "validate_main_event_effect_dispatch", validator)
    monkeypatch.setattr(bound.store, "get_event", AsyncMock(return_value=event))
    monkeypatch.setattr(
        bound.store, "list_codex_correction_attributions", AsyncMock(return_value=()),
    )
    writes = []

    async def dispatch(**kwargs):
        try:
            kwargs["final_authority_check"]()
        except Exception as exc:
            raise SharedCodexTextDispatchRejected("fixture pre-enqueue refusal") from exc
        writes.append(kwargs)
        return AdapterMessageResult(True, session.vendor_session_id, "fixture-turn")

    sender = AsyncMock(side_effect=dispatch)
    monkeypatch.setattr(bound.adapter, "_dispatch_claimed_text", sender, raising=False)
    generic_send = AsyncMock(side_effect=AssertionError("generic send forbidden"))
    monkeypatch.setattr(bound.adapter, "send_message", generic_send)
    control = {"paused": False}
    checks = []

    def check_local():
        checks.append(True)
        if control["paused"]:
            raise ValueError("fixture pause")

    context = ClaimedMainEffect(event.event_id, "fixture-owner", "fixture-effect", 2, check_local)
    return SimpleNamespace(
        bound=bound, executor=executor, session=session, action=action, event=event,
        context=context, validator=validator, validation_threads=validation_threads,
        grant=grant, sender=sender, dispatch=dispatch, writes=writes, control=control,
        checks=checks, generic_send=generic_send,
    )


async def execute(case, **kwargs):
    return await case.executor.execute(
        case.action, PolicyVerdict.ALLOW, main_effect_context=case.context, **kwargs,
    )


@pytest.mark.parametrize("kind,outcome", [
    (InterventionType.SEND_NUDGE, "sent"),
    (InterventionType.INJECT_CONTEXT, "sent"),
    (InterventionType.REQUEST_VERIFICATION, "verification_requested"),
    (InterventionType.CONTINUE_SESSION, "continued"),
])
async def test_private_route_revalidates_in_independent_loop_and_returns_exact_receipt(
    case, kind, outcome,
):
    case.action.type = kind
    result = await execute(case)
    assert isinstance(result, ActionExecutionResult)
    assert result.outcome == outcome
    assert result.worker_delivery_receipt == {
        "schema": "pex.worker-delivery.codex-turn.v1", "target_session_id": case.session.id,
        "vendor_session_id": case.session.vendor_session_id, "vendor_turn_id": "fixture-turn",
    }
    assert len(case.writes) == 1
    assert case.validator.await_count == 2
    assert case.validation_threads[0] == threading.get_ident()
    assert case.validation_threads[1] != threading.get_ident()
    assert len(case.checks) == 3
    case.generic_send.assert_not_awaited()


async def test_generic_execution_without_claim_cannot_send(case):
    result = await case.executor.execute(case.action, PolicyVerdict.ALLOW)
    assert result == "codex_claimed_dispatch_required"
    case.sender.assert_not_awaited()
    case.generic_send.assert_not_awaited()


@pytest.mark.parametrize("change", ["pause", "registry", "workspace", "grant", "correction"])
async def test_change_after_preparation_is_refused_before_write(case, change):
    async def dispatch(**kwargs):
        if change == "pause":
            case.control["paused"] = True
        elif change == "registry":
            case.bound.pipeline.adapters.bind("codex", SimpleNamespace(name="codex"))
        elif change == "workspace":
            _change_origin(case.bound)
        elif change == "grant":
            case.grant["granted"] = False
        else:
            case.grant["effect"]["payload"]["codex_correction"] = {"changed": True}
        return await case.dispatch(**kwargs)

    case.sender.side_effect = dispatch
    assert await execute(case) == "codex_dispatch_refused"
    assert not case.writes
    case.generic_send.assert_not_awaited()


@pytest.mark.parametrize("change", ["missing", "incomplete", "malformed", "wrong_goal"])
async def test_accepted_trigger_baseline_is_required(case, change):
    marker = case.event.metadata["pex_observer_snapshot"]
    if change == "missing":
        marker.pop("input_baseline")
    elif change == "incomplete":
        marker["input_baseline"].update(complete=False, digest=None, reason="fixture gap")
    elif change == "malformed":
        marker["input_baseline"]["revision"] = True
    else:
        case.event.goal_id = "another-goal"
    assert (await execute(case)) in {
        "codex_dispatch_preparation_refused", "codex_dispatch_input_incomplete",
        "codex_dispatch_trigger_mismatch",
    }
    case.sender.assert_not_awaited()


async def test_failed_initial_authority_does_not_enter_adapter(case):
    case.grant["granted"] = False
    assert await execute(case) == "codex_dispatch_authority_refused"
    case.sender.assert_not_awaited()


async def test_no_local_checker_is_not_a_claim(case):
    case.context = replace(case.context, check_local_authority=None)
    assert await execute(case) == "codex_claimed_dispatch_required"
    case.sender.assert_not_awaited()


@pytest.mark.parametrize("failure", [TimeoutError, RuntimeError, asyncio.CancelledError])
async def test_uncertain_or_cancelled_dispatch_is_never_retried(case, failure):
    case.sender.side_effect = failure("fixture lost outcome")
    if failure is asyncio.CancelledError:
        with pytest.raises(asyncio.CancelledError):
            await execute(case)
    else:
        assert await execute(case) == "codex_delivery_uncertain"
    case.sender.assert_awaited_once()
    case.generic_send.assert_not_awaited()
