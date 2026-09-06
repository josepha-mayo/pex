from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from datetime import timedelta

import pytest
from pex_bridge.store import (
    ProjectIdentityBlockedError,
    Store,
    _validate_event_observation_update,
    event_semantic_hash,
    stable_event_artifact_id,
    stable_event_effect_id,
    utcnow,
)
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.context import ContextItem
from pex_protocol.enums import (
    ContextKind,
    DecisionSource,
    EventType,
    HarnessType,
    PolicyVerdict,
    SessionStatus,
    SourceKind,
)
from pex_protocol.goal import Decision, Goal
from pex_protocol.intervention import Intervention
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessEvent, HarnessSession


def _event(
    event_id: str,
    *,
    session_id: str = "codex:recovery",
    message: str = "working",
    seconds: int = 0,
    goal_id: str | None = None,
) -> HarnessEvent:
    return HarnessEvent(
        event_id=event_id,
        ts=utcnow() + timedelta(seconds=seconds),
        harness_type=HarnessType.CODEX,
        session_id=session_id,
        project_id="C:/repo",
        goal_id=goal_id,
        event_type=EventType.AGENT_RESPONSE,
        message_delta=message,
        tool_name="shell",
        file_paths=["src/app.py"],
        metadata={"vendor_ts": "2026-08-30T01:02:03Z", "attempt": 1},
    )


async def _bound_event(store: Store, event_id: str) -> tuple[HarnessEvent, HarnessSession]:
    now = utcnow()
    goal = Goal(
        id="goal-recovery",
        project_id="C:/repo",
        title="Recovery",
        objective="Finish the exact recovery task.",
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    session = HarnessSession(
        id="codex:recovery",
        harness_type=HarnessType.CODEX,
        vendor_session_id="recovery",
        project_id=goal.project_id,
        goal_id=goal.id,
        status=SessionStatus.WORKING,
        capabilities={"send_message": True},
        last_activity=now,
    )
    await store.upsert_session(session)
    return _event(event_id, goal_id=goal.id), session


def _planned_intervention(event: HarnessEvent) -> Intervention:
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=event.session_id,
        goal_id=event.goal_id,
        payload={"message": "Continue with the acceptance criteria."},
        rationale="Observed evidence shows unfinished work.",
        evidence=[event.event_id],
        confidence=0.8,
        risk=RiskLevel.LOW,
        reversible=False,
        requires_capability="send_message",
    )
    return Intervention(
        id=stable_event_artifact_id(event.event_id, "intervention"),
        session_id=event.session_id,
        goal_id=event.goal_id,
        trigger=event.event_type.value,
        evidence=action.evidence,
        diagnosis="unfinished_work",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="delivery_reserved",
        created_at=event.ts,
        metadata={"trigger_event_id": event.event_id},
    )


def _plan_envelope(
    event: HarnessEvent,
    *,
    intervention: Intervention | None = None,
    effect_kind: str | None = None,
    required_capability: str | None = None,
    context_ids: list[str] | None = None,
    decision_ids: list[str] | None = None,
    intervention_update_ids: list[str] | None = None,
    **extra,
) -> dict:
    return {
        "schema": "pex.event-plan.v1",
        "event_id": event.event_id,
        "session_id": event.session_id,
        "goal_id": event.goal_id,
        "project_id": event.project_id,
        "effect_kind": effect_kind,
        "intervention_id": intervention.id if intervention is not None else None,
        "action": (
            intervention.proposed_action.model_dump(mode="json")
            if intervention is not None
            else None
        ),
        "required_capability": required_capability,
        "context_ids": context_ids or [],
        "decision_ids": decision_ids or [],
        "intervention_update_ids": intervention_update_ids or [],
        **extra,
    }


async def _register_event_project_identity(store: Store, event: HarnessEvent) -> str:
    registration = await store.register_project_locator(
        legacy_project_id=str(event.project_id),
        locator=ProjectLocator.path(
            f"/work/{event.event_id}/identity-a",
            platform=PathPlatform.POSIX,
            origin=ProjectOrigin(namespace="machine", host="event-identity-test-host"),
        ),
    )
    assert registration["outcome"] == "created"
    return registration["identity"].id


async def _reresolve_event_project_identity(store: Store, event: HarnessEvent) -> str:
    registration = await store.register_project_locator(
        legacy_project_id=str(event.project_id),
        locator=ProjectLocator.path(
            f"/work/{event.event_id}/identity-b",
            platform=PathPlatform.POSIX,
            origin=ProjectOrigin(namespace="machine", host="event-identity-test-host"),
        ),
    )
    assert registration["outcome"] == "quarantined"
    selected_identity_id = registration["identity"].id
    await store.resolve_project_identity_conflict(
        resolution_id=f"resolve-{event.event_id}-to-identity-b",
        legacy_project_id=str(event.project_id),
        selected_identity_id=selected_identity_id,
        resolved_by="test_operator",
        rationale="Select the newly verified physical checkout.",
    )
    return selected_identity_id


async def _commit_worker_plan(
    store: Store,
    event: HarnessEvent,
    session: HarnessSession,
    *,
    owner: str,
) -> dict:
    intervention = _planned_intervention(event)
    payload = {
        "action": intervention.proposed_action.model_dump(mode="json"),
        "required_capability": "send_message",
        "event_id": event.event_id,
        "intervention_id": intervention.id,
    }
    request_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return await store.commit_event_plan(
        event_id=event.event_id,
        owner=owner,
        plan=_plan_envelope(
            event,
            intervention=intervention,
            effect_kind="worker_action",
            required_capability="send_message",
        ),
        session=session,
        intervention=intervention,
        main_effect={
            "effect_key": "main",
            "kind": "worker_action",
            "target_session_id": session.id,
            "payload": payload,
            "request_hash": request_hash,
        },
    )


@pytest.mark.asyncio
async def test_migration_marks_preexisting_events_legacy_complete(tmp_path):
    path = tmp_path / "pex.sqlite"
    legacy = _event("legacy-event")
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE events(event_id TEXT PRIMARY KEY, session_id TEXT, "
            "ts TEXT, json TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO events(event_id, session_id, ts, json) VALUES (?, ?, ?, ?)",
            (
                legacy.event_id,
                legacy.session_id,
                legacy.ts.isoformat(),
                legacy.model_dump_json(),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    store = Store(path)
    await store.connect()
    try:
        processing = await store.get_event_processing(legacy.event_id)
        assert processing is not None
        assert processing["mode"] == "legacy"
        assert processing["state"] == "legacy_complete"
        assert await store.list_recoverable_event_processing() == []

        replay = await store.accept_pipeline_event(
            legacy.model_copy(update={"ts": utcnow()})
        )
        assert replay["created"] is False
        assert replay["processing"]["state"] == "legacy_complete"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_direct_event_writer_is_record_only_and_never_recoverable(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    event = _event("record-only")
    try:
        assert await store.add_event(event) is True
        processing = await store.get_event_processing(event.event_id)
        assert processing is not None
        assert processing["mode"] == "record_only"
        assert processing["state"] == "record_only_complete"
        assert await store.list_recoverable_event_processing() == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_acceptance_rolls_back_event_when_processing_upgrade_fails(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    event = _event("rollback")
    try:
        await store.db.execute(
            "CREATE TRIGGER reject_pipeline_upgrade BEFORE UPDATE OF mode "
            "ON event_processing WHEN NEW.mode = 'pipeline' "
            "BEGIN SELECT RAISE(ABORT, 'fault injection'); END"
        )
        await store.db.commit()
        with pytest.raises(sqlite3.IntegrityError, match="fault injection"):
            await store.accept_pipeline_event(event)
        assert await store.get_event(event.event_id) is None
        assert await store.get_event_processing(event.event_id) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_semantic_duplicate_excludes_only_top_level_timestamp(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    event = _event("semantic")
    try:
        accepted = await store.accept_pipeline_event(event)
        assert accepted["created"] is True
        canonical = accepted["event"]
        assert accepted["processing"]["semantic_hash"] == event_semantic_hash(event)

        timestamp_replay = event.model_copy(update={"ts": utcnow() + timedelta(days=1)})
        replay = await store.accept_pipeline_event(timestamp_replay)
        assert replay["created"] is False
        assert replay["event"] == canonical
        assert replay["processing"]["accept_seq"] == accepted["processing"]["accept_seq"]

        collisions = [
            event.model_copy(update={"message_delta": "changed"}),
            event.model_copy(update={"tool_name": "changed"}),
            event.model_copy(update={"file_paths": ["src/other.py"]}),
            event.model_copy(update={"goal_id": "goal-other"}),
            event.model_copy(update={"project_id": "C:/other"}),
            event.model_copy(update={"metadata": {**event.metadata, "attempt": 2}}),
            event.model_copy(
                update={
                    "metadata": {
                        **event.metadata,
                        "vendor_ts": "2026-08-30T01:02:04Z",
                    }
                }
            ),
        ]
        for collision in collisions:
            with pytest.raises(ValueError, match="different content"):
                await store.accept_pipeline_event(collision)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_acceptance_order_blocks_later_event_and_freezes_recent_prefix(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    first = _event("accepted-first", message="first", seconds=30)
    second = _event("accepted-second", message="second", seconds=-30)
    try:
        first_acceptance = await store.accept_pipeline_event(first)
        second_acceptance = await store.accept_pipeline_event(second)
        assert first_acceptance["processing"]["accept_seq"] < second_acceptance[
            "processing"
        ]["accept_seq"]

        blocked = await store.claim_event_processing(second.event_id, owner="worker-b")
        assert blocked["outcome"] == "blocked_by_earlier_event"
        assert blocked["blocking_event_id"] == first.event_id

        prefix = await store.recent_events_through(
            session_id=first.session_id,
            event_id=first.event_id,
        )
        assert [item.event_id for item in prefix] == [first.event_id]

        claimed = await store.claim_event_processing(first.event_id, owner="worker-a")
        assert claimed["outcome"] == "claimed"
        assert claimed["processing"]["state"] == "planning"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_unrelated_sessions_claim_independently(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    left = _event("left", session_id="codex:left")
    right = _event("right", session_id="codex:right")
    try:
        await store.accept_pipeline_event(left)
        await store.accept_pipeline_event(right)
        left_claim, right_claim = await asyncio.gather(
            store.claim_event_processing(left.event_id, owner="worker-left"),
            store.claim_event_processing(right.event_id, owner="worker-right"),
        )
        assert left_claim["outcome"] == "claimed"
        assert right_claim["outcome"] == "claimed"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_two_store_instances_claim_once_and_stale_dispatch_is_uncertain(tmp_path):
    path = tmp_path / "pex.sqlite"
    first = Store(path, process_boot_id="boot-first")
    second = Store(path, process_boot_id="boot-second")
    await first.connect()
    await second.connect()
    event = _event("claim-once")
    try:
        await first.accept_pipeline_event(event)
        claims = await asyncio.gather(
            first.claim_event_processing(event.event_id, owner="owner-first"),
            second.claim_event_processing(event.event_id, owner="owner-second"),
        )
        assert sum(item["outcome"] == "claimed" for item in claims) == 1
        assert sum(item["outcome"] == "busy" for item in claims) == 1
        winner = next(item for item in claims if item["outcome"] == "claimed")
        owner = str(winner["processing"]["lease_owner"])
        payload = {"event_id": event.event_id, "request": "decide"}
        request_hash = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        await first.reserve_event_effect(
            event_id=event.event_id,
            effect_key="planner",
            kind="supervisor_decision",
            target_session_id=event.session_id,
            payload=payload,
            request_hash=request_hash,
            owner=owner,
        )
        grants = await asyncio.gather(
            first.start_event_effect_dispatch(
                event_id=event.event_id,
                effect_key="planner",
                owner=owner,
                semantic_dispatch_limit=1,
            ),
            second.start_event_effect_dispatch(
                event_id=event.event_id,
                effect_key="planner",
                owner=owner,
                semantic_dispatch_limit=1,
            ),
        )
        assert sum(item["granted"] for item in grants) == 1
        with sqlite3.connect(path) as inspection:
            assert inspection.execute(
                "SELECT COUNT(*) FROM supervisor_dispatch_reservations"
            ).fetchone()[0] == 1

        recovery = Store(path, process_boot_id="boot-recovery")
        await recovery.connect()
        recovered = await recovery.recover_dispatching_event_effects()
        assert len(recovered) == 1
        assert recovered[0]["state"] == "delivery_uncertain"
        processing = await recovery.get_event_processing(event.event_id)
        assert processing is not None
        assert processing["state"] == "plan_generation_uncertain"

        later = _event("after-uncertain")
        await recovery.accept_pipeline_event(later)
        blocked = await recovery.claim_event_processing(later.event_id, owner="later")
        assert blocked["outcome"] == "blocked_by_earlier_event"
        assert blocked["blocking_state"] == "plan_generation_uncertain"
        attempts = processing["attempt_count"]
        reconciliation = await recovery.claim_event_processing(
            event.event_id,
            owner="must-not-be-granted",
        )
        assert reconciliation["outcome"] == "requires_reconciliation"
        assert reconciliation["processing"]["attempt_count"] == attempts + 1
        assert reconciliation["processing"]["lease_owner"] == "must-not-be-granted"
        competing = await first.claim_event_processing(
            event.event_id,
            owner="competing-reconciler",
        )
        assert competing["outcome"] == "busy"
        assert competing["processing"]["lease_owner"] == "must-not-be-granted"
        await recovery.close()
    finally:
        await second.close()
        await first.close()


def test_stable_effect_id_uses_unambiguous_tuple_encoding():
    assert stable_event_effect_id("a:b", "c") != stable_event_effect_id("a", "b:c")


@pytest.mark.asyncio
async def test_same_owner_reentrant_claim_is_not_a_second_grant(tmp_path):
    path = tmp_path / "pex.sqlite"
    first = Store(path, process_boot_id="boot-first")
    second = Store(path, process_boot_id="boot-second")
    await first.connect()
    await second.connect()
    event = _event("same-owner")
    try:
        await first.accept_pipeline_event(event)
        claims = await asyncio.gather(
            first.claim_event_processing(event.event_id, owner="attempt-unique"),
            second.claim_event_processing(event.event_id, owner="attempt-unique"),
        )
        assert sorted(item["outcome"] for item in claims) == [
            "already_owned",
            "claimed",
        ]
        processing = await first.get_event_processing(event.event_id)
        assert processing is not None
        assert processing["attempt_count"] == 1
    finally:
        await second.close()
        await first.close()


@pytest.mark.asyncio
async def test_effect_dispatch_requires_live_lease_and_matching_processing_state(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot-test")
    await store.connect()
    planner_event = _event("expired-planner")
    main_event = _event("main-too-early", session_id="codex:other")
    try:
        await store.accept_pipeline_event(planner_event)
        await store.claim_event_processing(planner_event.event_id, owner="planner-owner")
        planner_payload = {"event_id": planner_event.event_id}
        planner_hash = hashlib.sha256(
            json.dumps(planner_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        await store.reserve_event_effect(
            event_id=planner_event.event_id,
            effect_key="planner",
            kind="supervisor_decision",
            target_session_id=planner_event.session_id,
            payload=planner_payload,
            request_hash=planner_hash,
            owner="planner-owner",
        )
        await store.db.execute(
            "UPDATE event_processing SET lease_expires_at = ? WHERE event_id = ?",
            ((utcnow() - timedelta(seconds=1)).isoformat(), planner_event.event_id),
        )
        await store.db.commit()
        expired = await store.start_event_effect_dispatch(
            event_id=planner_event.event_id,
            effect_key="planner",
            owner="planner-owner",
        )
        assert expired == {"granted": False, "reason": "processing_lease_expired"}

        await store.accept_pipeline_event(main_event)
        await store.claim_event_processing(main_event.event_id, owner="main-owner")
        main_payload = {"event_id": main_event.event_id}
        main_hash = hashlib.sha256(
            json.dumps(main_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with pytest.raises(ValueError, match="stable planner effect"):
            await store.reserve_event_effect(
                event_id=main_event.event_id,
                effect_key="main",
                kind="worker_action",
                target_session_id=main_event.session_id,
                payload=main_payload,
                request_hash=main_hash,
                ordinal=1,
                owner="main-owner",
            )
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_state", ["delivered", "failed", "skipped"])
async def test_terminal_planner_receipt_is_reused_without_redispatch(
    tmp_path,
    terminal_state,
):
    store = Store(tmp_path / f"{terminal_state}.sqlite", process_boot_id="boot-test")
    await store.connect()
    event = _event(f"planner-{terminal_state}")
    payload = {"event_id": event.event_id, "request": "decide"}
    request_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    result = {"status": terminal_state, "decision": "NOOP"}
    try:
        await store.accept_pipeline_event(event)
        await store.claim_event_processing(event.event_id, owner="attempt")
        await store.reserve_event_effect(
            event_id=event.event_id,
            effect_key="planner",
            kind="supervisor_decision",
            target_session_id=event.session_id,
            payload=payload,
            request_hash=request_hash,
            owner="attempt",
        )
        if terminal_state == "skipped":
            await store.finalize_event_effect(
                event_id=event.event_id,
                effect_key="planner",
                state=terminal_state,
                result=result,
            )
        else:
            granted = await store.start_event_effect_dispatch(
                event_id=event.event_id,
                effect_key="planner",
                owner="attempt",
            )
            assert granted["granted"] is True
            await store.finalize_event_effect(
                event_id=event.event_id,
                effect_key="planner",
                state=terminal_state,
                result=result,
                downstream_operation_id="planner-operation",
            )

        replayed = await store.reserve_event_effect(
            event_id=event.event_id,
            effect_key="planner",
            kind="supervisor_decision",
            target_session_id=event.session_id,
            payload=payload,
            request_hash=request_hash,
            owner="attempt",
        )
        assert replayed["created"] is False
        assert replayed["effect"]["state"] == terminal_state
        assert replayed["effect"]["result"] == result
        redispatch = await store.start_event_effect_dispatch(
            event_id=event.event_id,
            effect_key="planner",
            owner="attempt",
        )
        assert redispatch["granted"] is False
        assert redispatch["reason"] == f"effect_already_{terminal_state}"

        downstream_id = None if terminal_state == "skipped" else "planner-operation"
        assert (
            await store.finalize_event_effect(
                event_id=event.event_id,
                effect_key="planner",
                state=terminal_state,
                result=result,
                downstream_operation_id=downstream_id,
            )
        )["result"] == result
        with pytest.raises(ValueError, match="receipt cannot change"):
            await store.finalize_event_effect(
                event_id=event.event_id,
                effect_key="planner",
                state=terminal_state,
                result=result,
                downstream_operation_id="different-operation",
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_plan_projects_locally_and_finalizes_main_effect_atomically(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot-plan")
    await store.connect()
    try:
        event, session = await _bound_event(store, "planned-main")
        await store.accept_pipeline_event(event)
        await store.claim_event_processing(event.event_id, owner="plan-attempt")
        context = ContextItem(
            id=stable_event_artifact_id(event.event_id, "event_context"),
            project_id="C:/repo",
            goal_id=event.goal_id,
            kind=ContextKind.FACT,
            content="Observed recoverable event.",
            source_refs=[event.event_id],
            provenance=SourceKind.HARNESS,
            valid_from=event.ts,
        )
        decision = Decision(
            id=stable_event_artifact_id(event.event_id, "decision"),
            goal_id=str(event.goal_id),
            statement="Keep processing in acceptance order.",
            source=DecisionSource.PEX,
            created_at=event.ts,
            metadata={
                "session_id": event.session_id,
                "trigger_event_id": event.event_id,
            },
        )
        intervention = _planned_intervention(event)
        effect_payload = {
            "action": intervention.proposed_action.model_dump(mode="json"),
            "required_capability": "send_message",
            "effect_kind": "worker_action",
            "event_id": event.event_id,
            "intervention_id": intervention.id,
        }
        effect_hash = hashlib.sha256(
            json.dumps(
                effect_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        plan = _plan_envelope(
            event,
            intervention=intervention,
            effect_kind="worker_action",
            required_capability="send_message",
            context_ids=[context.id],
            decision_ids=[decision.id],
            auto_handoff="auto_handoff_deferred_until_multi_effect_recovery",
        )
        committed = await store.commit_event_plan(
            event_id=event.event_id,
            owner="plan-attempt",
            plan=plan,
            session=session,
            context_items=[context],
            decisions=[decision],
            intervention=intervention,
            main_effect={
                "effect_key": "main",
                "kind": "worker_action",
                "target_session_id": session.id,
                "payload": effect_payload,
                "request_hash": effect_hash,
            },
        )
        assert committed["state"] == "planned"
        assert committed["plan"] == plan
        assert await store.get_context(context.id) == context
        assert (await store.list_decisions(str(event.goal_id)))[0] == decision
        assert (await store.list_interventions(session.id))[0] == intervention
        with pytest.raises(ValueError, match="restricted to the planner"):
            await store.start_event_effect_dispatch(
                event_id=event.event_id,
                effect_key="main",
                owner="plan-attempt",
            )
        with pytest.raises(ValueError, match="restricted to the planner"):
            await store.finalize_event_effect(
                event_id=event.event_id,
                effect_key="main",
                state="skipped",
                result={"status": "skipped"},
            )
        with pytest.raises(ValueError, match="stored projections"):
            await store.commit_event_plan(
                event_id=event.event_id,
                owner="plan-attempt",
                plan=plan,
                session=session,
                context_items=[context.model_copy(update={"content": "changed"})],
            )

        dispatch = await store.claim_main_event_effect(
            event_id=event.event_id,
            owner="plan-attempt",
        )
        assert dispatch["granted"] is True
        delivered = intervention.model_copy(update={"result": "sent"})
        receipt = {
            "schema": "pex.event-processing.receipt.v1",
            "event_id": event.event_id,
            "status": "complete",
            "effect_state": "delivered",
            "effect_result": {"outcome": "sent"},
            "effect_id": stable_event_effect_id(event.event_id, "main"),
            "downstream_operation_id": "vendor-message-1",
            "intervention": delivered.model_dump(mode="json"),
        }
        final = await store.finalize_event_processing(
            event_id=event.event_id,
            effect_state="delivered",
            effect_result={"outcome": "sent"},
            intervention=delivered,
            receipt=receipt,
            session=session,
            downstream_operation_id="vendor-message-1",
        )
        assert final["state"] == "complete"
        assert final["receipt"] == receipt

        replay = await store.accept_pipeline_event(
            event.model_copy(update={"ts": utcnow()})
        )
        assert replay["processing"]["receipt"] == receipt
        exact = await store.finalize_event_processing(
            event_id=event.event_id,
            effect_state="delivered",
            effect_result={"outcome": "sent"},
            intervention=delivered,
            receipt=receipt,
            session=session,
            downstream_operation_id="vendor-message-1",
        )
        assert exact["receipt"] == receipt

        audit_cursor = await store.db.execute(
            "SELECT record_type FROM intervention_audit "
            "WHERE intervention_id = ? ORDER BY id",
            (intervention.id,),
        )
        assert [row["record_type"] for row in await audit_cursor.fetchall()] == [
            "delivery_reserved",
            "delivery_delivered",
        ]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_recovered_main_dispatch_has_an_exact_sealable_uncertain_result(tmp_path):
    path = tmp_path / "recovered-main.sqlite"
    first = Store(path, process_boot_id="boot-before-crash")
    await first.connect()
    try:
        event, session = await _bound_event(first, "recovered-main")
        await first.accept_pipeline_event(event, session_snapshot=session)
        await first.claim_event_processing(event.event_id, owner="first-owner")
        intervention = _planned_intervention(event)
        effect_payload = {
            "schema": "pex.worker-effect.v1",
            "event_id": event.event_id,
            "intervention_id": intervention.id,
            "action": intervention.proposed_action.model_dump(mode="json"),
            "required_capability": "send_message",
        }
        effect_hash = hashlib.sha256(
            json.dumps(
                effect_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        plan = _plan_envelope(
            event,
            intervention=intervention,
            effect_kind="worker_action",
            required_capability="send_message",
        )
        await first.commit_event_plan(
            event_id=event.event_id,
            owner="first-owner",
            plan=plan,
            session=session,
            intervention=intervention,
            main_effect={
                "effect_key": "main",
                "kind": "worker_action",
                "target_session_id": session.id,
                "payload": effect_payload,
                "request_hash": effect_hash,
            },
        )
        dispatch = await first.claim_main_event_effect(
            event_id=event.event_id,
            owner="first-owner",
        )
        assert dispatch["granted"] is True
    finally:
        await first.close()

    recovery = Store(path, process_boot_id="boot-after-crash")
    await recovery.connect()
    try:
        recovered = await recovery.recover_dispatching_event_effects()
        assert len(recovered) == 1
        effect = recovered[0]
        assert effect["kind"] == "worker_action"
        assert effect["result"] == {
            "status": "delivery_uncertain",
            "outcome": "worker_delivery_uncertain",
            "code": "process_restarted_after_dispatch_started",
            "effect_id": stable_event_effect_id(event.event_id, "main"),
        }
        processing = await recovery.get_event_processing(event.event_id)
        assert processing is not None
        assert processing["state"] == "planned"
    finally:
        await recovery.close()


@pytest.mark.asyncio
async def test_plan_rejects_cross_bound_projection_and_main_target(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        event, session = await _bound_event(store, "cross-bound")
        await store.accept_pipeline_event(event, session_snapshot=session)
        await store.claim_event_processing(event.event_id, owner="attempt")
        cross_context = ContextItem(
            id="cross-context",
            project_id="C:/other",
            goal_id=event.goal_id,
            kind=ContextKind.FACT,
            content="Wrong project.",
            source_refs=[event.event_id],
            valid_from=event.ts,
        )
        receipt = {
            "schema": "pex.event-processing.receipt.v1",
            "event_id": event.event_id,
            "status": "complete",
            "intervention": None,
        }
        with pytest.raises(ValueError, match="context project binding"):
            await store.commit_event_plan(
                event_id=event.event_id,
                owner="attempt",
                plan=_plan_envelope(event, context_ids=[cross_context.id]),
                session=session,
                context_items=[cross_context],
                receipt=receipt,
            )

        intervention = _planned_intervention(event)
        payload = {
            "action": intervention.proposed_action.model_dump(mode="json"),
            "required_capability": "send_message",
            "intervention_id": intervention.id,
        }
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with pytest.raises(ValueError, match="target binding"):
            await store.commit_event_plan(
                event_id=event.event_id,
                owner="attempt",
                plan=_plan_envelope(
                    event,
                    intervention=intervention,
                    effect_kind="worker_action",
                    required_capability="send_message",
                ),
                session=session,
                intervention=intervention,
                main_effect={
                    "effect_key": "main",
                    "kind": "worker_action",
                    "target_session_id": "codex:other",
                    "payload": payload,
                    "request_hash": request_hash,
                },
            )
        processing = await store.get_event_processing(event.event_id)
        assert processing is not None
        assert processing["state"] == "planning"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_event_plan_preserves_concurrently_newer_session_state(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        event, accepted_session = await _bound_event(store, "newer-session")
        await store.accept_pipeline_event(event, session_snapshot=accepted_session)
        await store.claim_event_processing(event.event_id, owner="attempt")
        newer = accepted_session.model_copy(deep=True)
        newer.last_activity = accepted_session.last_activity + timedelta(minutes=5)
        newer.status = SessionStatus.DRIFTING
        newer.capabilities = {"send_message": False, "resume": True}
        newer.metadata = {
            "capabilities_adapter": "new-adapter",
            "current_task": "newer task",
            "external_marker": "preserve-me",
        }
        await store.upsert_session(newer)

        stale_projection = accepted_session.model_copy(deep=True)
        stale_projection.status = SessionStatus.STOPPED
        stale_projection.capabilities = {"send_message": True}
        stale_projection.metadata = {
            "current_task": "stale task",
            "external_marker": "stale",
        }
        receipt = {
            "schema": "pex.event-processing.receipt.v1",
            "event_id": event.event_id,
            "status": "complete",
            "intervention": None,
        }
        await store.commit_event_plan(
            event_id=event.event_id,
            owner="attempt",
            plan=_plan_envelope(event),
            session=stale_projection,
            receipt=receipt,
        )
        stored = await store.get_session(accepted_session.id)
        assert stored is not None
        assert stored.status == SessionStatus.DRIFTING
        assert stored.capabilities == {"send_message": False, "resume": True}
        assert stored.metadata["current_task"] == "newer task"
        assert stored.metadata["external_marker"] == "preserve-me"
        assert stored.last_activity == newer.last_activity
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_failure_refuses_dispatching_and_skips_safe_reserved_planner(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        safe, _ = await _bound_event(store, "safe-failure")
        await store.accept_pipeline_event(safe)
        await store.claim_event_processing(safe.event_id, owner="safe-attempt")
        payload = {"event_id": safe.event_id}
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        await store.reserve_event_effect(
            event_id=safe.event_id,
            effect_key="planner",
            kind="supervisor_decision",
            target_session_id=safe.session_id,
            payload=payload,
            request_hash=request_hash,
            owner="safe-attempt",
        )
        failed = await store.fail_event_processing(
            event_id=safe.event_id,
            owner="safe-attempt",
            code="safe_plan_failure",
        )
        assert failed["state"] == "failed"
        effect = await store.get_event_effect(safe.event_id, "planner")
        assert effect is not None and effect["state"] == "skipped"

        dispatching = _event("unsafe-failure", session_id="codex:unsafe")
        await store.accept_pipeline_event(dispatching)
        await store.claim_event_processing(dispatching.event_id, owner="unsafe-attempt")
        unsafe_payload = {"event_id": dispatching.event_id}
        unsafe_hash = hashlib.sha256(
            json.dumps(
                unsafe_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        await store.reserve_event_effect(
            event_id=dispatching.event_id,
            effect_key="planner",
            kind="supervisor_decision",
            target_session_id=dispatching.session_id,
            payload=unsafe_payload,
            request_hash=unsafe_hash,
            owner="unsafe-attempt",
        )
        granted = await store.start_event_effect_dispatch(
            event_id=dispatching.event_id,
            effect_key="planner",
            owner="unsafe-attempt",
        )
        assert granted["granted"] is True
        with pytest.raises(ValueError, match="before external dispatch"):
            await store.fail_event_processing(
                event_id=dispatching.event_id,
                owner="unsafe-attempt",
                code="must_not_hide_dispatch",
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_plan_projection_collision_rolls_back_every_projection(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        event, session = await _bound_event(store, "plan-rollback")
        await store.accept_pipeline_event(event)
        await store.claim_event_processing(event.event_id, owner="plan-attempt")
        collision_id = stable_event_artifact_id(event.event_id, "collision")
        existing = ContextItem(
            id=collision_id,
            project_id="C:/repo",
            goal_id=event.goal_id,
            kind=ContextKind.FACT,
            content="Existing content.",
            source_refs=[event.event_id],
            valid_from=event.ts,
        )
        await store.add_context(existing)
        inserted_before_collision = ContextItem(
            id=stable_event_artifact_id(event.event_id, "would_rollback"),
            project_id="C:/repo",
            goal_id=event.goal_id,
            kind=ContextKind.FACT,
            content="Must roll back.",
            source_refs=[event.event_id],
            valid_from=event.ts,
        )
        collision = existing.model_copy(update={"content": "Different content."})
        receipt = {
            "schema": "pex.event-processing.receipt.v1",
            "event_id": event.event_id,
            "status": "complete",
            "intervention": None,
        }
        with pytest.raises(ValueError, match="context id collision"):
            await store.commit_event_plan(
                event_id=event.event_id,
                owner="plan-attempt",
                plan=_plan_envelope(
                    event,
                    context_ids=[inserted_before_collision.id, collision.id],
                ),
                session=session,
                context_items=[inserted_before_collision, collision],
                receipt=receipt,
            )
        assert await store.get_context(inserted_before_collision.id) is None
        processing = await store.get_event_processing(event.event_id)
        assert processing is not None
        assert processing["state"] == "planning"
        assert processing["plan"] is None
        assert processing["receipt"] is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_main_effect_revalidation_skips_without_dispatch_marker(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        event, session = await _bound_event(store, "paused-before-cas")
        await store.accept_pipeline_event(event)
        await store.claim_event_processing(event.event_id, owner="plan-attempt")
        intervention = _planned_intervention(event)
        effect_payload = {
            "action": intervention.proposed_action.model_dump(mode="json"),
            "required_capability": "send_message",
            "event_id": event.event_id,
            "intervention_id": intervention.id,
        }
        effect_hash = hashlib.sha256(
            json.dumps(
                effect_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        await store.commit_event_plan(
            event_id=event.event_id,
            owner="plan-attempt",
            plan=_plan_envelope(
                event,
                intervention=intervention,
                effect_kind="worker_action",
                required_capability="send_message",
            ),
            session=session,
            intervention=intervention,
            main_effect={
                "effect_key": "main",
                "kind": "worker_action",
                "target_session_id": session.id,
                "payload": effect_payload,
                "request_hash": effect_hash,
            },
        )
        paused = session.model_copy(update={"supervision_paused": True})
        await store.upsert_session(paused, allow_supervision_change=True)
        refused = await store.claim_main_event_effect(
            event_id=event.event_id,
            owner="plan-attempt",
        )
        assert refused["granted"] is False
        assert refused["reason"] == "session_supervision_paused"
        effect = await store.get_event_effect(event.event_id, "main")
        assert effect is not None
        assert effect["state"] == "reserved"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_plan_requires_complete_envelope_exact_project_and_live_lease(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        event, session = await _bound_event(store, "strict-envelope")
        await store.accept_pipeline_event(event, session_snapshot=session)
        await store.claim_event_processing(event.event_id, owner="attempt")
        receipt = {
            "schema": "pex.event-processing.receipt.v1",
            "event_id": event.event_id,
            "status": "complete",
            "intervention": None,
        }
        with pytest.raises(ValueError, match="envelope is incomplete"):
            await store.commit_event_plan(
                event_id=event.event_id,
                owner="attempt",
                plan={"schema": "pex.event-plan.v1"},
                session=session,
                receipt=receipt,
            )
        with pytest.raises(ValueError, match="project binding mismatch"):
            await store.commit_event_plan(
                event_id=event.event_id,
                owner="attempt",
                plan=_plan_envelope(event),
                session=session.model_copy(update={"project_id": None}),
                receipt=receipt,
            )
        await store.db.execute(
            "UPDATE event_processing SET lease_expires_at = ? WHERE event_id = ?",
            ((utcnow() - timedelta(seconds=1)).isoformat(), event.event_id),
        )
        await store.db.commit()
        with pytest.raises(PermissionError, match="plan lease expired"):
            await store.commit_event_plan(
                event_id=event.event_id,
                owner="attempt",
                plan=_plan_envelope(event),
                session=session,
                receipt=receipt,
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_observation_update_cannot_rewrite_reserved_proposal(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        event, session = await _bound_event(store, "observe-current")
        prior_event = event.model_copy(update={"event_id": "observe-prior"})
        prior = _planned_intervention(prior_event).model_copy(update={"result": "sent"})
        await store.add_intervention(prior)
        await store.accept_pipeline_event(event, session_snapshot=session)
        await store.claim_event_processing(event.event_id, owner="attempt")

        rewritten_action = prior.proposed_action.model_copy(
            update={"rationale": "Rewritten after delivery."}
        )
        observed = prior.model_copy(
            deep=True,
            update={"proposed_action": rewritten_action, "outcome": "worker_responded"},
        )
        observed.metadata["outcome_event_ids"] = [event.event_id]
        receipt = {
            "schema": "pex.event-processing.receipt.v1",
            "event_id": event.event_id,
            "status": "complete",
            "intervention": None,
        }
        with pytest.raises(ValueError, match="cannot change its proposed action"):
            await store.commit_event_plan(
                event_id=event.event_id,
                owner="attempt",
                plan=_plan_envelope(
                    event,
                    intervention_update_ids=[prior.id],
                ),
                session=session,
                intervention_updates=[observed],
                receipt=receipt,
            )
        assert (await store.list_interventions(session.id))[0] == prior
    finally:
        await store.close()


def test_observation_causal_negative_is_narrow_and_monotonic():
    event = _event("causal-negative")
    prior = _planned_intervention(event).model_copy(update={"result": "sent"}, deep=True)
    observed = prior.model_copy(deep=True)
    observed.metadata["causal_continuation_proven"] = False
    _validate_event_observation_update(prior, observed)

    forged_true = prior.model_copy(deep=True)
    forged_true.metadata["causal_continuation_proven"] = True
    with pytest.raises(ValueError, match="cannot rewrite causal continuation proof"):
        _validate_event_observation_update(prior, forged_true)

    frozen_false = observed.model_copy(deep=True)
    erased = frozen_false.model_copy(deep=True)
    erased.metadata.pop("causal_continuation_proven")
    with pytest.raises(ValueError, match="cannot rewrite causal continuation proof"):
        _validate_event_observation_update(frozen_false, erased)

    frozen_true = forged_true.model_copy(deep=True)
    downgraded = frozen_true.model_copy(deep=True)
    downgraded.metadata["causal_continuation_proven"] = False
    with pytest.raises(ValueError, match="cannot rewrite causal continuation proof"):
        _validate_event_observation_update(frozen_true, downgraded)


@pytest.mark.asyncio
async def test_main_claim_rechecks_effect_ordinal_and_hash(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        event, session = await _bound_event(store, "corrupt-main-effect")
        await store.accept_pipeline_event(event, session_snapshot=session)
        await store.claim_event_processing(event.event_id, owner="attempt")
        intervention = _planned_intervention(event)
        payload = {
            "action": intervention.proposed_action.model_dump(mode="json"),
            "required_capability": "send_message",
            "intervention_id": intervention.id,
        }
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        await store.commit_event_plan(
            event_id=event.event_id,
            owner="attempt",
            plan=_plan_envelope(
                event,
                intervention=intervention,
                effect_kind="worker_action",
                required_capability="send_message",
            ),
            session=session,
            intervention=intervention,
            main_effect={
                "effect_key": "main",
                "kind": "worker_action",
                "target_session_id": session.id,
                "payload": payload,
                "request_hash": request_hash,
            },
        )
        await store.db.execute(
            "UPDATE event_effects SET ordinal = 2, request_hash = ? "
            "WHERE event_id = ? AND effect_key = 'main'",
            ("0" * 64, event.event_id),
        )
        await store.db.commit()
        refused = await store.claim_main_event_effect(
            event_id=event.event_id,
            owner="attempt",
        )
        assert refused["granted"] is False
        assert refused["reason"] == "effect_identity_binding_corrupt"
        effect = await store.get_event_effect(event.event_id, "main")
        assert effect is not None and effect["state"] == "reserved"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_plan_commit_rejects_project_identity_reresolved_after_acceptance(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        identity_a = await _register_event_project_identity(
            store,
            _event("plan-identity-reresolved"),
        )
        event, session = await _bound_event(store, "plan-identity-reresolved")
        accepted = await store.accept_pipeline_event(event, session_snapshot=session)
        assert accepted["processing"]["accepted_project_binding"] == (
            f"identity:{identity_a}"
        )
        assert (
            await store.claim_event_processing(event.event_id, owner="attempt")
        )["outcome"] == "claimed"

        identity_b = await _reresolve_event_project_identity(store, event)
        assert identity_b != identity_a
        receipt = {
            "schema": "pex.event-processing.receipt.v1",
            "event_id": event.event_id,
            "status": "complete",
            "intervention": None,
        }
        with pytest.raises(
            PermissionError,
            match="project identity changed after acceptance",
        ):
            await store.commit_event_plan(
                event_id=event.event_id,
                owner="attempt",
                plan=_plan_envelope(event),
                session=session,
                receipt=receipt,
            )

        processing = await store.get_event_processing(event.event_id)
        assert processing is not None
        assert processing["state"] == "planning"
        assert processing["plan"] is None
        assert processing["receipt"] is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_goal_less_stale_session_cannot_accept_event_after_project_rebind(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        event = _event("goal-less-session-rebound")
        await _register_event_project_identity(store, event)
        session = HarnessSession(
            id=event.session_id,
            harness_type=event.harness_type,
            vendor_session_id="goal-less-session-rebound",
            project_id=event.project_id,
            status=SessionStatus.WORKING,
            last_activity=event.ts,
        )
        await store.upsert_session(session)
        await _reresolve_event_project_identity(store, event)

        with pytest.raises(ProjectIdentityBlockedError) as pipeline_block:
            await store.accept_pipeline_event(event, session_snapshot=session)
        assert pipeline_block.value.code == "artifact_project_identity_changed"
        with pytest.raises(ProjectIdentityBlockedError) as legacy_block:
            await store.add_event(event.model_copy(update={"event_id": "goal-less-legacy"}))
        assert legacy_block.value.code == "artifact_project_identity_changed"
        assert await store.get_event(event.event_id) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_stale_goal_cannot_authorize_event_first_accepted_after_project_rebind(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        seed = _event("goal-first-accepted-after-rebind")
        await _register_event_project_identity(store, seed)
        event, session = await _bound_event(store, seed.event_id)
        await _reresolve_event_project_identity(store, event)

        with pytest.raises(ProjectIdentityBlockedError) as blocked:
            await store.accept_pipeline_event(event, session_snapshot=session)
        assert blocked.value.code == "artifact_project_identity_changed"
        assert await store.get_event(event.event_id) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_main_claim_rejects_project_identity_reresolved_after_plan(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        identity_a = await _register_event_project_identity(
            store,
            _event("dispatch-identity-reresolved"),
        )
        event, session = await _bound_event(store, "dispatch-identity-reresolved")
        accepted = await store.accept_pipeline_event(event, session_snapshot=session)
        assert accepted["processing"]["accepted_project_binding"] == (
            f"identity:{identity_a}"
        )
        assert await store.recent_events_for_authority(
            session.id,
            goal_id=str(event.goal_id),
            project_id=str(event.project_id),
            harness_type=event.harness_type,
        ) == [event]
        assert await store.recent_events_through_for_authority(
            session.id,
            event.event_id,
            goal_id=str(event.goal_id),
            project_id=str(event.project_id),
            harness_type=event.harness_type,
        ) == [event]
        await store.claim_event_processing(event.event_id, owner="attempt")
        await _commit_worker_plan(store, event, session, owner="attempt")

        identity_b = await _reresolve_event_project_identity(store, event)
        assert identity_b != identity_a
        refused = await store.claim_main_event_effect(
            event_id=event.event_id,
            owner="attempt",
        )
        assert refused["granted"] is False
        assert refused["reason"] == "event_project_identity_changed"
        effect = await store.get_event_effect(event.event_id, "main")
        assert effect is not None
        assert effect["state"] == "reserved"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_plan_commit_rejects_project_typed_after_untyped_acceptance(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        event, session = await _bound_event(store, "plan-untyped-to-typed")
        accepted = await store.accept_pipeline_event(event, session_snapshot=session)
        assert accepted["processing"]["accepted_project_binding"].startswith("legacy:")
        await store.claim_event_processing(event.event_id, owner="attempt")
        await _register_event_project_identity(store, event)
        receipt = {
            "schema": "pex.event-processing.receipt.v1",
            "event_id": event.event_id,
            "status": "complete",
            "intervention": None,
        }

        with pytest.raises(
            PermissionError,
            match="project identity changed after acceptance",
        ):
            await store.commit_event_plan(
                event_id=event.event_id,
                owner="attempt",
                plan=_plan_envelope(event),
                session=session,
                receipt=receipt,
            )
        processing = await store.get_event_processing(event.event_id)
        assert processing is not None
        assert processing["state"] == "planning"
        assert processing["plan"] is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_main_claim_rejects_project_typed_after_untyped_plan(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        event, session = await _bound_event(store, "dispatch-untyped-to-typed")
        accepted = await store.accept_pipeline_event(event, session_snapshot=session)
        assert accepted["processing"]["accepted_project_binding"].startswith("legacy:")
        await store.claim_event_processing(event.event_id, owner="attempt")
        await _commit_worker_plan(store, event, session, owner="attempt")

        await _register_event_project_identity(store, event)
        refused = await store.claim_main_event_effect(
            event_id=event.event_id,
            owner="attempt",
        )
        assert refused["granted"] is False
        assert refused["reason"] == "event_project_identity_changed"
        effect = await store.get_event_effect(event.event_id, "main")
        assert effect is not None
        assert effect["state"] == "reserved"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_unchanged_typed_project_commits_and_claims_main_effect(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        identity_a = await _register_event_project_identity(
            store,
            _event("unchanged-typed-project"),
        )
        event, session = await _bound_event(store, "unchanged-typed-project")
        accepted = await store.accept_pipeline_event(event, session_snapshot=session)
        assert accepted["processing"]["accepted_project_binding"] == (
            f"identity:{identity_a}"
        )
        await store.claim_event_processing(event.event_id, owner="attempt")

        committed = await _commit_worker_plan(store, event, session, owner="attempt")
        assert committed["state"] == "planned"
        dispatch = await store.claim_main_event_effect(
            event_id=event.event_id,
            owner="attempt",
        )
        assert dispatch["granted"] is True
        assert dispatch["effect"]["state"] == "dispatching"
    finally:
        await store.close()
