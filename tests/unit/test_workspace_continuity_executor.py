"""Actual temporary publication authority, fake adapter effects only."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.base import AdapterMessageResult
from pex_bridge.executor import ActionExecutionResult, ActionExecutor
from pex_bridge.local_origin_config import save_local_origin_choice
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.context import ContextBundle
from pex_protocol.enums import HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from test_lifecycle_actions import _reserve_lifecycle_dispatch
from test_overlay_executor_ledger import _action, _add_real_overlay_owner, _overlay
from test_workspace_publication import publication as publication
from test_workspace_publication import publish


@pytest.fixture
async def runtime(publication):
    store, session, binding, origin_path = publication
    session.status = SessionStatus.WORKING
    # Fake boundary capabilities; this does not enable shared Codex adapter control.
    session.capabilities = AdapterCapabilities(
        send_message=True,
        resume=True,
        stop=True,
        start=True,
        fork=True,
        permission_response_mode="async",
    ).model_dump(mode="json")
    await publish(publication)
    now = datetime.now(UTC)
    await store.upsert_goal(
        Goal(
            id="goal-1",
            project_id=session.project_id,
            title="Goal",
            objective="Test bounded dispatch",
            created_at=now,
            updated_at=now,
        )
    )
    await store.attach_session_goal(session.id, "goal-1", expected_goal_id=None)
    session = await store.get_session(session.id)
    calls = []

    async def message(target, *args):
        calls.append("message")
        return AdapterMessageResult(True, target.vendor_session_id, "accepted-turn")

    async def permission(*args):
        calls.append("permission")
        return True

    async def focus(*args):
        calls.append("focus")
        return True

    async def probe():
        calls.append("probe")
        return AdapterCapabilities(start=True, stop=True, fork=True)

    async def stop(*args):
        calls.append("stop")
        return True

    adapter = SimpleNamespace(
        send_message=message,
        continue_or_resume=message,
        inject_context=message,
        respond_permission=permission,
        focus_ui=focus,
        probe=probe,
        stop=stop,
    )
    registry = SimpleNamespace(for_session=lambda _: adapter)
    executor = ActionExecutor(registry, store)
    return store, session, binding, origin_path, adapter, executor, calls


def action(runtime, kind):
    return ProposedAction(
        type=kind,
        session_id=runtime[1].id,
        goal_id=runtime[1].goal_id,
        payload={
            "text": "Exact bounded request",
            "request_id": "permission-1",
            "decision": "allow",
        },
        rationale="Observed evidence requires this action",
    )


def change(runtime, kind):
    if kind == "directory":
        root = Path(runtime[2].directory.cwd)
        root.rename(root.with_name("preserved-original"))
        root.mkdir()
    else:
        choice = runtime[2].origin_choice
        save_local_origin_choice(
            runtime[3],
            choice.origin,
            expected_revision=choice.revision,
            expected_choice_id=choice.choice_id,
        )


KINDS = [
    InterventionType.SEND_NUDGE,
    InterventionType.REQUEST_VERIFICATION,
    InterventionType.CONTINUE_SESSION,
    InterventionType.FRESH_HANDOFF,
    InterventionType.RESPOND_PERMISSION,
    InterventionType.FOCUS_UI,
]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("changed", ["directory", "origin"])
async def test_stale_workspace_refuses_before_any_adapter_call(runtime, kind, changed):
    change(runtime, changed)
    before = await runtime[0].get_session(runtime[1].id)
    assert (
        await runtime[5].execute(action(runtime, kind), PolicyVerdict.ALLOW)
        == "workspace_authority_changed"
    )
    assert runtime[6] == []
    assert await runtime[0].get_session(runtime[1].id) == before


@pytest.mark.parametrize("kind", KINDS)
async def test_valid_workspace_keeps_existing_delivery_receipt(runtime, kind):
    result = await runtime[5].execute(action(runtime, kind), PolicyVerdict.ALLOW)
    assert len(runtime[6]) == 1
    if kind in {InterventionType.RESPOND_PERMISSION, InterventionType.FOCUS_UI}:
        assert result in {"permission_allow", "focused"}
    else:
        assert isinstance(result, ActionExecutionResult)
        assert result.worker_delivery_receipt["vendor_turn_id"] == "accepted-turn"


@pytest.mark.parametrize("verdict", [PolicyVerdict.ALLOW, PolicyVerdict.ASK_HUMAN])
async def test_stale_workspace_does_not_project_human_control(runtime, verdict):
    change(runtime, "origin")
    before = await runtime[0].get_session(runtime[1].id)
    result = await runtime[5].execute(action(runtime, InterventionType.ASK_HUMAN), verdict)
    assert result == "workspace_authority_changed"
    assert await runtime[0].get_session(runtime[1].id) == before


async def test_refusal_inside_queued_dispatch_is_not_delivery_uncertainty(runtime, monkeypatch):
    original = runtime[5]._workspace_dispatch
    entered = []

    async def queue_gap(*args, **kwargs):
        entered.append(True)
        if len(entered) == 2:
            change(runtime, "directory")
        return await original(*args, **kwargs)

    monkeypatch.setattr(runtime[5], "_workspace_dispatch", queue_gap)
    result = await runtime[5].execute(
        action(runtime, InterventionType.SEND_NUDGE), PolicyVerdict.ALLOW
    )
    assert result == "workspace_authority_changed"
    assert len(entered) == 2
    assert runtime[6] == []


@pytest.mark.parametrize("raises", [False, True])
async def test_change_after_adapter_entry_preserves_delivery_or_uncertainty(runtime, raises):
    async def sent(target, text):
        runtime[6].append("message")
        change(runtime, "directory")
        if raises:
            raise OSError("lost acknowledgement")
        return AdapterMessageResult(True, target.vendor_session_id, "accepted-turn")

    runtime[4].send_message = sent
    result = await runtime[5].execute(
        action(runtime, InterventionType.SEND_NUDGE), PolicyVerdict.ALLOW
    )
    assert runtime[6] == ["message"]
    if raises:
        assert result == "send_delivery_uncertain"
    else:
        assert isinstance(result, ActionExecutionResult)
        assert result.outcome == "sent"
        assert result.worker_delivery_receipt["vendor_turn_id"] == "accepted-turn"


async def test_handoff_rechecks_after_awaited_source_lookup(runtime, monkeypatch):
    store, session, binding, origin_path, *_ = runtime
    source = session.model_copy(deep=True)
    source.id = "codex:source-thread"
    source.vendor_session_id = "source-thread"
    source.goal_id = None
    await store.publish_observer_session(
        source,
        expected_control_revision=None,
        expected_project_binding=binding.project_binding,
        expected_workspace=binding,
        local_origin_path=origin_path,
    )
    await store.attach_session_goal(source.id, session.goal_id, expected_goal_id=None)
    original = store.get_session

    async def lookup(session_id):
        result = await original(session_id)
        if session_id == source.id:
            change(runtime, "origin")
        return result

    monkeypatch.setattr(store, "get_session", lookup)
    proposed = action(runtime, InterventionType.FRESH_HANDOFF)
    proposed.payload = {
        "bundle": ContextBundle(
            goal_id=session.goal_id,
            target_session_id=session.id,
            source_session_ids=[source.id],
            goal_summary="Exact bound context",
            created_at=datetime.now(UTC),
        ).model_dump(mode="json")
    }
    assert await runtime[5].execute(proposed, PolicyVerdict.ALLOW) == "workspace_authority_changed"
    assert runtime[6] == []


async def test_lifecycle_rechecks_after_probe_before_stop(runtime):
    proposed = action(runtime, InterventionType.STOP_AGENT)
    resolution = await _reserve_lifecycle_dispatch(runtime[0], proposed)

    async def changed_probe():
        runtime[6].append("probe")
        change(runtime, "origin")
        return AdapterCapabilities(stop=True)

    runtime[4].probe = changed_probe
    result = await runtime[5].execute(
        proposed,
        PolicyVerdict.ALLOW,
        human_authorized=True,
        lifecycle_resolution_id=resolution,
    )
    assert result == "workspace_authority_changed"
    assert runtime[6] == ["probe"]


async def test_noop_and_denial_do_not_need_a_current_workspace(runtime):
    change(runtime, "origin")
    assert (
        await runtime[5].execute(action(runtime, InterventionType.NOOP), PolicyVerdict.ALLOW)
        == "noop"
    )
    assert (
        await runtime[5].execute(action(runtime, InterventionType.SEND_NUDGE), PolicyVerdict.DENY)
        == "denied_by_policy"
    )
    assert runtime[6] == []


async def test_final_sample_rejects_change_after_store_witness_return(runtime, monkeypatch):
    original = runtime[0].require_session_workspace_current
    calls = []

    async def changed_after_validation(session):
        witness = await original(session)
        calls.append(True)
        if len(calls) == 2:
            change(runtime, "directory")
        return witness

    monkeypatch.setattr(runtime[0], "require_session_workspace_current", changed_after_validation)
    result = await runtime[5].execute(
        action(runtime, InterventionType.SEND_NUDGE), PolicyVerdict.ALLOW,
    )
    assert result == "workspace_authority_changed"
    assert len(calls) == 2
    assert runtime[6] == []


async def test_workspace_check_failure_cannot_become_uncertain_delivery(runtime, monkeypatch):
    async def unavailable(session):
        raise OSError("authority store unavailable")

    monkeypatch.setattr(runtime[0], "require_session_workspace_current", unavailable)
    result = await runtime[5].execute(
        action(runtime, InterventionType.SEND_NUDGE), PolicyVerdict.ALLOW,
    )
    assert result == "workspace_authority_changed"
    assert runtime[6] == []


async def test_overlay_queued_revocation_seals_dispatching_operation(publication, monkeypatch):
    store, session, binding, origin_path = publication
    session.id = "synthetic:workspace-overlay"
    session.vendor_session_id = "workspace-overlay"
    session.harness_type = HarnessType.SYNTHETIC
    session.status = SessionStatus.WORKING
    capabilities = AdapterCapabilities(modify_config=True, config_scope="session")
    session.capabilities = capabilities.model_dump(mode="json")
    await publish(publication)
    now = datetime.now(UTC)
    await store.upsert_goal(Goal(
        id="goal_overlay", project_id=session.project_id, title="Overlay",
        objective="Bounded reversible overlay", created_at=now, updated_at=now,
    ))
    await store.attach_session_goal(session.id, "goal_overlay", expected_goal_id=None)
    adapters = AdapterRegistry()
    adapters.synthetic.probe = AsyncMock(return_value=capabilities)
    adapters.synthetic.apply_overlay = AsyncMock(side_effect=AssertionError("revoked overlay I/O"))
    overlay = _overlay(session.id, "revoked-after-overlay-dispatch")
    owner_id = "int_workspace_overlay_owner"
    await _add_real_overlay_owner(store, overlay, intervention_id=owner_id)
    original = store.start_overlay_operation
    grants = []

    async def revoke_after_dispatch(*args, **kwargs):
        grant = await original(*args, **kwargs)
        assert grant["granted"] is True
        assert grant["operation"]["state"] == "dispatching"
        grants.append(grant)
        choice = binding.origin_choice
        save_local_origin_choice(
            origin_path, choice.origin,
            expected_revision=choice.revision, expected_choice_id=choice.choice_id,
        )
        return grant

    monkeypatch.setattr(store, "start_overlay_operation", revoke_after_dispatch)
    result = await ActionExecutor(adapters, store).execute(
        _action(overlay), PolicyVerdict.ALLOW, operation_owner_id=owner_id,
    )
    assert result == "workspace_authority_changed"
    assert len(grants) == 1
    adapters.synthetic.apply_overlay.assert_not_awaited()
    terminal = await store.get_overlay_operation(overlay.id, "apply")
    assert terminal["state"] == "skipped"
    assert terminal["result"]["code"] == "workspace_authority_changed"
    assert terminal["dispatch_started_at"] is not None
    assert await store.active_overlays(session.id) == []
