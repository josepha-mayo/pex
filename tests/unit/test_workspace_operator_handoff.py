"""Operator handoff finalization uses actual bound Store state and fake delivery."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.base import AdapterMessageResult
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.local_origin_config import save_local_origin_choice
from pex_bridge.pipeline import Pipeline
from pex_protocol.enums import SessionStatus
from pex_protocol.goal import Goal
from test_operator_handoff_effects import KEY, PRINCIPAL, _artifacts
from test_workspace_publication import publication as publication
from test_workspace_publication import publish


@pytest.mark.parametrize("revocation", [None, "directory", "origin", "source", "target"])
async def test_operator_handoff_revocation_after_marker_has_terminal_receipt(
    publication,
    tmp_path,
    monkeypatch,
    revocation,
):
    store, source, binding, origin_path = publication
    source.status = SessionStatus.WORKING
    # Fake boundary capability only; no real shared adapter control is enabled.
    source.capabilities = {"inject_context": True}
    await publish(publication)
    target = source.model_copy(deep=True)
    target.id = "codex:operator-handoff-target"
    target.vendor_session_id = "operator-handoff-target"
    target.metadata["subscription_receipt"]["authorization_id"] = "target-subscription"
    await store.publish_observer_session(
        target,
        expected_control_revision=None,
        expected_project_binding=binding.project_binding,
        expected_workspace=binding,
        local_origin_path=origin_path,
    )
    now = datetime.now(UTC)
    goal = Goal(
        id="handoff-goal",
        project_id=source.project_id,
        title="Bound handoff",
        objective="Transfer one exact context receipt",
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    await store.attach_session_goal(source.id, goal.id, expected_goal_id=None)
    await store.attach_session_goal(target.id, goal.id, expected_goal_id=None)
    source = await store.get_session(source.id)
    target = await store.get_session(target.id)
    item, bundle, event, intervention = _artifacts(goal, source, target)
    intervention.metadata["human_requested"] = True
    await store.add_context(item)
    reserved = await store.reserve_operator_handoff(
        principal_id=PRINCIPAL,
        idempotency_key=KEY,
        source_session_id=source.id,
        target_session_id=target.id,
        token_budget=2_000,
        bundle=bundle,
        event=event,
        intervention=intervention,
        actor_assurance="bridge_bearer",
    )
    fake = SimpleNamespace(
        inject_context=AsyncMock(
            return_value=AdapterMessageResult(
                True,
                target.vendor_session_id,
                "fake-handoff-turn",
            )
        )
    )
    adapters = AdapterRegistry()
    adapters.bind("codex", fake)
    pipeline = Pipeline(
        store, adapters, EventBus(), Settings.for_test(home=tmp_path, require_auth=False),
    )
    original = store.start_operator_handoff_dispatch
    grants = []

    async def start_then_revoke(*args, **kwargs):
        dispatch = await original(*args, **kwargs)
        assert dispatch["granted"] is True
        assert dispatch["effect"]["state"] == "dispatching"
        grants.append(dispatch)
        if revocation == "directory":
            root = Path(binding.directory.cwd)
            root.rename(root.with_name("preserved-original"))
            root.mkdir()
        elif revocation == "origin":
            choice = binding.origin_choice
            save_local_origin_choice(
                origin_path,
                choice.origin,
                expected_revision=choice.revision,
                expected_choice_id=choice.choice_id,
            )
        elif revocation in {"source", "target"}:
            endpoint = source if revocation == "source" else target
            detached = endpoint.model_copy(deep=True)
            detached.status = SessionStatus.DETACHED
            control = await store.get_session_control_state(endpoint.id)
            await store.publish_observer_session(
                detached,
                expected_control_revision=control["control_revision"],
                expected_project_binding=binding.project_binding,
            )
        return dispatch

    monkeypatch.setattr(store, "start_operator_handoff_dispatch", start_then_revoke)
    try:
        response = await pipeline._dispatch_operator_handoff(reserved, replayed=False)
        assert len(grants) == 1
        terminal = await store.get_operator_effect(reserved["effect"]["effect_id"])
        assert terminal["dispatch_started_at"] is not None
        assert terminal["finished_at"] is not None
        stored_intervention = await store.get_intervention(intervention.id)
        if revocation is None:
            assert response["ok"] is True and response["status"] == "delivered"
            fake.inject_context.assert_awaited_once()
            assert terminal["state"] == "delivered"
            receipt = terminal["result"]["worker_delivery_receipt"]
            assert receipt["target_session_id"] == target.id
            assert receipt["vendor_turn_id"] == "fake-handoff-turn"
            assert stored_intervention.metadata["worker_delivery_receipt"] == receipt
        else:
            fake.inject_context.assert_not_awaited()
            assert response["ok"] is False and response["status"] == "failed"
            assert terminal["state"] == "failed"
            assert terminal["result"] == {
                "status": "failed",
                "reason": "workspace_authority_changed",
                "adapter_started": False,
            }
            assert "worker_delivery_receipt" not in stored_intervention.metadata
        replay_record = await store.find_operator_handoff(
            principal_id=PRINCIPAL,
            idempotency_key=KEY,
            source_session_id=source.id,
            target_session_id=target.id,
            token_budget=2_000,
        )
        replay = await pipeline._dispatch_operator_handoff(replay_record, replayed=True)
        assert replay["replayed"] is True
        assert replay["effect"] == response["effect"]
        assert len(grants) == 1
        assert fake.inject_context.await_count == (1 if revocation is None else 0)
    finally:
        await pipeline.close_presentations()
