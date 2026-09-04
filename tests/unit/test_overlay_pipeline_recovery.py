from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store, stable_event_artifact_id
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import (
    Authority,
    EventPhase,
    EventType,
    HarnessType,
    PolicyVerdict,
    SessionStatus,
)
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.overlay import Overlay, OverlayDiff
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessEvent, HarnessSession

_ORIGIN = ProjectOrigin(namespace="machine", host="overlay-pipeline-recovery")


async def _seed_planned_overlay(
    store: Store,
    *,
    suffix: str,
) -> tuple[Goal, HarnessSession, HarnessEvent, Intervention, Overlay, dict]:
    project_id = f"overlay-pipeline-{suffix}"
    registration = await store.register_project_locator(
        legacy_project_id=project_id,
        locator=ProjectLocator.path(
            f"/work/{suffix}-a",
            platform=PathPlatform.POSIX,
            origin=_ORIGIN,
        ),
    )
    assert registration["outcome"] == "created"
    now = datetime.now(UTC)
    goal = Goal(
        id=f"goal-overlay-pipeline-{suffix}",
        project_id=project_id,
        title="Recover an exact overlay child",
        objective="Never redispatch a known overlay operation.",
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    session = HarnessSession(
        id=f"synthetic:overlay-pipeline-{suffix}",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id=f"overlay-pipeline-{suffix}",
        project_id=project_id,
        goal_id=goal.id,
        status=SessionStatus.WORKING,
        capabilities={"modify_config": True},
        last_activity=now,
    )
    await store.upsert_session(session)
    event = HarnessEvent(
        event_id=f"event-overlay-pipeline-{suffix}",
        ts=now,
        harness_type=session.harness_type,
        session_id=session.id,
        project_id=project_id,
        goal_id=goal.id,
        event_type=EventType.AGENT_RESPONSE,
        phase=EventPhase.AFTER,
        message_delta="Repeated evidence shows the current harness needs a bounded overlay.",
    )
    overlay = Overlay(
        id=f"overlay-pipeline-{suffix}",
        session_id=session.id,
        reason="Pin the exact verified reproduction.",
        diff=OverlayDiff(tools_disabled=["WebSearch"], extra={"phase": "debug"}),
        ttl_seconds=600,
        rollback={
            "adapter": "synthetic",
            "operation": "revert_overlay",
            "overlay_id": f"overlay-pipeline-{suffix}",
        },
    )
    action = ProposedAction(
        type=InterventionType.APPLY_OVERLAY,
        session_id=session.id,
        goal_id=goal.id,
        payload={"overlay": overlay.model_dump(mode="json")},
        rationale="Use an exact reversible overlay for the current debugging phase.",
        evidence=[event.event_id],
        confidence=0.9,
        risk=RiskLevel.LOW,
        reversible=True,
        authority_required=Authority.LOCAL_POLICY,
        requires_capability="modify_config",
    )
    intervention = Intervention(
        id=stable_event_artifact_id(event.event_id, "intervention"),
        session_id=session.id,
        goal_id=goal.id,
        trigger=event.event_type.value,
        evidence=action.evidence,
        diagnosis="overlay_needed",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=True,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="delivery_reserved",
        created_at=event.ts,
        metadata={"trigger_event_id": event.event_id},
    )
    owner = f"owner-{suffix}"
    await store.accept_pipeline_event(event, session_snapshot=session)
    claim = await store.claim_event_processing(event.event_id, owner=owner)
    assert claim["outcome"] == "claimed"
    effect_payload = {
        "schema": "pex.worker-effect.v1",
        "event_id": event.event_id,
        "intervention_id": intervention.id,
        "action": action.model_dump(mode="json"),
        "required_capability": "modify_config",
    }
    effect_json = json.dumps(
        effect_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    plan = {
        "schema": "pex.event-plan.v1",
        "event_id": event.event_id,
        "session_id": session.id,
        "goal_id": goal.id,
        "project_id": project_id,
        "effect_kind": "worker_action",
        "intervention_id": intervention.id,
        "action": action.model_dump(mode="json"),
        "required_capability": "modify_config",
        "context_ids": [],
        "decision_ids": [],
        "intervention_update_ids": [],
        "verification": {},
    }
    await store.commit_event_plan(
        event_id=event.event_id,
        owner=owner,
        plan=plan,
        session=session,
        intervention=intervention,
        main_effect={
            "effect_key": "main",
            "kind": "worker_action",
            "target_session_id": session.id,
            "payload": effect_payload,
            "request_hash": hashlib.sha256(effect_json.encode()).hexdigest(),
        },
    )
    parent = await store.claim_main_event_effect(event_id=event.event_id, owner=owner)
    assert parent["granted"] is True
    return goal, session, event, intervention, overlay, parent["effect"]


async def _pause_and_rebind(
    store: Store,
    goal: Goal,
    session: HarnessSession,
    *,
    suffix: str,
) -> None:
    goal.paused = True
    goal.updated_at = datetime.now(UTC)
    await store.upsert_goal(goal)
    session.supervision_paused = True
    await store.upsert_session(session)
    conflict = await store.register_project_locator(
        legacy_project_id=goal.project_id,
        locator=ProjectLocator.path(
            f"/work/{suffix}-b",
            platform=PathPlatform.POSIX,
            origin=_ORIGIN,
        ),
    )
    assert conflict["outcome"] == "quarantined"
    await store.resolve_project_identity_conflict(
        resolution_id=f"resolve-overlay-pipeline-{suffix}",
        legacy_project_id=goal.project_id,
        selected_identity_id=conflict["identity"].id,
        resolved_by="overlay-pipeline-test",
        rationale="Select the deliberately different physical checkout.",
    )


def _pipeline(tmp_path, store: Store) -> tuple[Pipeline, AsyncMock]:
    executor = AsyncMock()
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    pipeline.executor = SimpleNamespace(execute=executor)
    pipeline.supervisor = SimpleNamespace(
        decide=AsyncMock(side_effect=AssertionError("supervisor must not run")),
        agentcore=None,
    )
    return pipeline, executor


@pytest.mark.asyncio
async def test_apply_parent_rejects_exactly_linked_revert_child(tmp_path):
    store = Store(tmp_path / "opposite-child-kind.sqlite")
    await store.connect()
    try:
        _, session, event, intervention, overlay, parent = await _seed_planned_overlay(
            store,
            suffix="opposite-child-kind",
        )
        apply = await store.reserve_overlay_apply(
            overlay,
            adapter_name="synthetic",
            owner_intervention_id=intervention.id,
        )
        grant = await store.start_overlay_operation(apply["operation_id"])
        assert grant["granted"] is True
        await store.finalize_overlay_operation(
            apply["operation_id"],
            state="delivered",
            result={"code": "overlay_applied"},
        )

        with pytest.raises(PermissionError, match="parent effect binding is invalid"):
            await store.reserve_overlay_revert(
                overlay.id,
                expected_session_id=session.id,
                required_owner_intervention_id=intervention.id,
                trigger_intervention_id=intervention.id,
                parent_effect_id=parent["effect_id"],
                authorized_by="overlay-pipeline-test",
                idempotency_key="opposite-child-kind",
                reason="prove that an apply parent cannot adopt a revert child",
            )

        effect = await store.get_event_effect(event.event_id, "main")
        assert effect is not None
        assert effect["state"] == "dispatching"
        assert effect["downstream_operation_id"] is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_terminal_overlay_child_reconciles_after_pause_and_rebind_without_io(tmp_path):
    store = Store(tmp_path / "delivered-child.sqlite", process_boot_id="overlay-child-boot")
    await store.connect()
    pipeline = None
    try:
        goal, session, event, intervention, overlay, parent = await _seed_planned_overlay(
            store,
            suffix="delivered-child",
        )
        reserved = await store.reserve_overlay_apply(
            overlay,
            adapter_name="synthetic",
            owner_intervention_id=intervention.id,
            parent_effect_id=parent["effect_id"],
        )
        grant = await store.start_overlay_operation(reserved["operation_id"])
        assert grant["granted"] is True
        await store.finalize_overlay_operation(
            reserved["operation_id"],
            state="delivered",
            result={"code": "overlay_applied"},
        )
        await _pause_and_rebind(store, goal, session, suffix="delivered-child")
        pipeline, executor = _pipeline(tmp_path, store)

        processing = await store.get_event_processing(event.event_id)
        assert processing is not None
        await pipeline._resume_planned_event(processing, owner="retry-owner")
        await pipeline._resume_planned_event(processing, owner="retry-owner")

        final = await store.get_event_processing(event.event_id)
        assert final is not None and final["state"] == "complete"
        assert final["receipt"]["effect_state"] == "delivered"
        assert final["receipt"]["downstream_operation_id"] == reserved["operation_id"]
        assert final["receipt"]["effect_result"]["code"] == "overlay_applied"
        assert final["receipt"]["intervention"]["result"] == "overlay_applied"
        executor.assert_not_awaited()
    finally:
        if pipeline is not None:
            await pipeline.close_presentations()
        await store.close()


@pytest.mark.asyncio
async def test_current_boot_skipped_child_reconciles_exact_parent_without_io(tmp_path):
    store = Store(tmp_path / "skipped-child.sqlite", process_boot_id="skipped-child-boot")
    await store.connect()
    pipeline = None
    try:
        goal, session, event, intervention, overlay, parent = await _seed_planned_overlay(
            store,
            suffix="skipped-child",
        )
        reserved = await store.reserve_overlay_apply(
            overlay,
            adapter_name="synthetic",
            owner_intervention_id=intervention.id,
            parent_effect_id=parent["effect_id"],
        )
        child_result = {"code": "overlay_apply_not_supported"}
        await store.finalize_overlay_operation(
            reserved["operation_id"],
            state="skipped",
            result=child_result,
        )
        await _pause_and_rebind(store, goal, session, suffix="skipped-child")
        pipeline, executor = _pipeline(tmp_path, store)

        processing = await store.get_event_processing(event.event_id)
        assert processing is not None
        await pipeline._resume_planned_event(processing, owner="retry-owner")

        final = await store.get_event_processing(event.event_id)
        effect = await store.get_event_effect(event.event_id, "main")
        assert final is not None and final["state"] == "complete"
        assert effect is not None and effect["state"] == "skipped"
        assert effect["downstream_operation_id"] == reserved["operation_id"]
        assert final["receipt"]["effect_state"] == "skipped"
        assert final["receipt"]["effect_result"] == {
            **child_result,
            "status": "skipped",
            "effect_id": parent["effect_id"],
            "outcome": "overlay_apply_not_supported",
            "downstream_operation_id": reserved["operation_id"],
        }
        assert final["receipt"]["intervention"]["result"] == "overlay_apply_not_supported"
        executor.assert_not_awaited()
    finally:
        if pipeline is not None:
            await pipeline.close_presentations()
        await store.close()


@pytest.mark.asyncio
async def test_startup_replays_terminal_no_child_parent_before_live_gates(tmp_path):
    path = tmp_path / "no-child-crash.sqlite"
    first = Store(path, process_boot_id="overlay-parent-before-crash")
    await first.connect()
    try:
        goal, session, event, _, _, _ = await _seed_planned_overlay(
            first,
            suffix="no-child-crash",
        )
        await _pause_and_rebind(first, goal, session, suffix="no-child-crash")
    finally:
        await first.close()

    recovered = Store(path, process_boot_id="overlay-parent-after-crash")
    await recovered.connect()
    pipeline, executor = _pipeline(tmp_path, recovered)
    try:
        assert await pipeline.recover_unfinished_events() == [event.event_id]
        final = await recovered.get_event_processing(event.event_id)
        assert final is not None and final["state"] == "complete"
        assert final["receipt"]["effect_state"] == "delivery_uncertain"
        assert final["receipt"]["downstream_operation_id"] is None
        assert (
            final["receipt"]["effect_result"]["code"] == "process_restarted_after_dispatch_started"
        )
        executor.assert_not_awaited()
        assert await pipeline.recover_unfinished_events() == []
        executor.assert_not_awaited()
    finally:
        await pipeline.close_presentations()
        await recovered.close()


@pytest.mark.asyncio
async def test_current_boot_parent_without_child_is_never_stolen_or_redispatched(tmp_path):
    store = Store(tmp_path / "current-boot.sqlite", process_boot_id="current-overlay-boot")
    await store.connect()
    pipeline = None
    try:
        goal, session, event, _, _, _ = await _seed_planned_overlay(
            store,
            suffix="current-boot",
        )
        await _pause_and_rebind(store, goal, session, suffix="current-boot")
        pipeline, executor = _pipeline(tmp_path, store)
        processing = await store.get_event_processing(event.event_id)
        assert processing is not None

        await pipeline._resume_planned_event(processing, owner="different-owner")
        await pipeline._resume_planned_event(processing, owner="different-owner")

        current = await store.get_event_processing(event.event_id)
        effect = await store.get_event_effect(event.event_id, "main")
        assert current is not None and current["state"] == "planned"
        assert effect is not None and effect["state"] == "dispatching"
        assert effect["downstream_operation_id"] is None
        executor.assert_not_awaited()
    finally:
        if pipeline is not None:
            await pipeline.close_presentations()
        await store.close()


@pytest.mark.asyncio
async def test_repeated_cancellation_cannot_cancel_retained_parent_seal(
    tmp_path,
    monkeypatch,
):
    store = Store(tmp_path / "double-cancel.sqlite")
    await store.connect()
    pipeline, _ = _pipeline(tmp_path, store)
    started = asyncio.Event()
    release = asyncio.Event()
    child_cancelled = False

    async def delayed_reconciliation(_processing: dict, _effect: dict) -> bool:
        nonlocal child_cancelled
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            child_cancelled = True
            raise
        return True

    monkeypatch.setattr(
        pipeline,
        "_reconcile_overlay_child_before_live_gates",
        delayed_reconciliation,
    )
    task = asyncio.create_task(
        pipeline._durably_reconcile_overlay_child(
            {"event_id": "double-cancel-event"},
            {"effect_id": "double-cancel-effect"},
        )
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert child_cancelled is False
        assert not pipeline._overlay_reconciliation_tasks
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await pipeline.close_presentations()
        await store.close()
