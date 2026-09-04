from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime

import pytest
from pex_bridge.context.mesh import build_bundle
from pex_bridge.store import (
    OperatorEffectConflictError,
    ProjectIdentityBlockedError,
    Store,
    stable_operator_artifact_id,
    stable_operator_effect_id,
)
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.context import ContextItem
from pex_protocol.enums import (
    ContextKind,
    EventPhase,
    EventType,
    HarnessType,
    PolicyVerdict,
    Sensitivity,
    SessionStatus,
    SourceKind,
)
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessEvent, HarnessSession

PRINCIPAL = "local_bridge_operator"
KEY = "handoff-operator-0001"


async def _seed(store: Store, project_id: str = "handoff-project"):
    now = datetime.now(UTC)
    goal = Goal(
        id="handoff-goal",
        project_id=project_id,
        title="Share one verified artifact",
        objective="Move the minimum provenance-backed context exactly once.",
        created_at=now,
        updated_at=now,
    )
    source = HarnessSession(
        id="synthetic:handoff-source",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="handoff-source",
        project_id=project_id,
        goal_id=goal.id,
        status=SessionStatus.WORKING,
        capabilities={"inject_context": True},
    )
    target = HarnessSession(
        id="synthetic:handoff-target",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="handoff-target",
        project_id=project_id,
        goal_id=goal.id,
        status=SessionStatus.WORKING,
        capabilities={"inject_context": True},
    )
    await store.upsert_goal(goal)
    await store.upsert_session(source)
    await store.upsert_session(target)
    return goal, source, target


def _synthetic_delivery_result(
    session: HarnessSession, *, turn_id: str = "syn-turn-0001"
) -> dict:
    return {
        "status": "delivered",
        "worker_delivery_receipt": {
            "schema": "pex.worker-delivery.v1",
            "target_session_id": session.id,
            "vendor_session_id": session.vendor_session_id,
            "vendor_turn_id": turn_id,
        },
    }


def _artifacts(
    goal: Goal,
    source: HarnessSession,
    target: HarnessSession,
    key: str = KEY,
    *,
    item_project_id: str | None = None,
    bundle_target_project_id: str | None = None,
):
    now = datetime.now(UTC)
    item = ContextItem(
        id="ctx-handoff-verified",
        project_id=item_project_id or goal.project_id,
        goal_id=goal.id,
        kind=ContextKind.RESULT,
        content="The verified parser artifact is artifacts/parser.json.",
        source_refs=["event-parser-verified"],
        provenance=SourceKind.HARNESS,
        confidence=0.95,
        relevance_tags=["verified", "parser"],
        valid_from=now,
        sensitivity=Sensitivity.INTERNAL,
        metadata={"source_session_id": source.id, "verified": True},
    )
    bundle_target = (
        target.model_copy(update={"project_id": bundle_target_project_id})
        if bundle_target_project_id is not None
        else target
    )
    bundle = build_bundle(
        goal,
        bundle_target,
        [item],
        [],
        [source.id],
        token_budget=2_000,
    )
    effect_id = stable_operator_effect_id(PRINCIPAL, "context_handoff", key)
    event = HarnessEvent(
        event_id=stable_operator_artifact_id(effect_id, "event"),
        ts=now,
        harness_type=source.harness_type,
        session_id=source.id,
        project_id=goal.project_id,
        goal_id=goal.id,
        event_type=EventType.USER_PROMPT,
        phase=EventPhase.AFTER,
        message_delta="Operator requested a context handoff.",
    )
    action = ProposedAction(
        type=InterventionType.FRESH_HANDOFF,
        session_id=target.id,
        goal_id=goal.id,
        payload={"bundle": bundle.model_dump(mode="json")},
        rationale="Share one provenance-backed result with the sibling worker.",
        evidence=item.source_refs,
        confidence=0.9,
        risk=RiskLevel.LOW,
        reversible=False,
        expected_benefit="Avoid duplicate verified work.",
        cooldown_seconds=120,
        requires_capability="inject_context",
    )
    intervention = Intervention(
        id=stable_operator_artifact_id(effect_id, "intervention"),
        session_id=target.id,
        goal_id=goal.id,
        trigger=event.event_type.value,
        evidence=action.evidence,
        diagnosis="operator_requested_context_handoff",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=InterventionType.NOOP.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="handoff_delivery_reserved",
        outcome="handoff_delivery_reserved",
        created_at=now,
        metadata={"trigger_event_id": event.event_id},
    )
    return item, bundle, event, intervention


@pytest.mark.asyncio
async def test_handoff_reservation_is_atomic_replayable_and_finalizes_one_receipt(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_handoff_one")
    await store.connect()
    try:
        goal, source, target = await _seed(store)
        item, bundle, event, intervention = _artifacts(goal, source, target)
        intervention.metadata["human_requested"] = True
        await store.add_context(item)
        first = await store.reserve_operator_handoff(
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
        replay = await store.reserve_operator_handoff(
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
        found = await store.find_operator_handoff(
            principal_id=PRINCIPAL,
            idempotency_key=KEY,
            source_session_id=source.id,
            target_session_id=target.id,
            token_budget=2_000,
        )

        assert first["created"] is True
        assert replay["created"] is False
        assert found is not None
        assert replay["effect"] == found["effect"] == first["effect"]
        cursor = await store.db.execute(
            "SELECT (SELECT COUNT(*) FROM operator_effects) AS effects, "
            "(SELECT COUNT(*) FROM interventions) AS interventions, "
            "(SELECT COUNT(*) FROM intervention_audit) AS audits, "
            "(SELECT COUNT(*) FROM events WHERE event_id = ?) AS events",
            (event.event_id,),
        )
        counts = await cursor.fetchone()
        assert dict(counts) == {
            "effects": 1,
            "interventions": 1,
            "audits": 1,
            "events": 1,
        }

        dispatch = await store.start_operator_handoff_dispatch(first["effect"]["effect_id"])
        assert dispatch["granted"] is True
        assert dispatch["effect"]["state"] == "dispatching"
        with pytest.raises(ValueError, match="not a direct session message"):
            await store.finalize_operator_effect(
                effect_id=first["effect"]["effect_id"],
                state="delivered",
                result={"status": "delivered"},
            )
        unchanged = await store.get_operator_effect(first["effect"]["effect_id"])
        assert unchanged is not None and unchanged["state"] == "dispatching"
        final = await store.finalize_operator_handoff(
            effect_id=first["effect"]["effect_id"],
            state="delivered",
            result=_synthetic_delivery_result(target),
        )
        assert final["effect"]["state"] == "delivered"
        assert final["intervention"].result == "handoff_injected"
        assert final["intervention"].action_taken == InterventionType.FRESH_HANDOFF.value
        actor_cursor = await store.db.execute(
            "SELECT COUNT(*) FROM human_operator_terminal_actions WHERE effect_id = ?",
            (first["effect"]["effect_id"],),
        )
        assert (await actor_cursor.fetchone())[0] == 1
        metrics = await store.attention_metrics()
        assert metrics["human_interventions"]["source_counts"][
            "operator_context_handoff"
        ] == 1
        assert metrics["human_interventions"]["unverified_operator_action_counts"][
            "operator_handoff"
        ] == 0
        refused = await store.start_operator_handoff_dispatch(first["effect"]["effect_id"])
        assert refused["granted"] is False
        assert refused["reason"] == "effect_already_delivered"
        intervention_cursor = await store.db.execute(
            "SELECT json FROM interventions WHERE id = ?",
            (intervention.id,),
        )
        intervention_row = await intervention_cursor.fetchone()
        assert intervention_row is not None
        envelope = json.loads(intervention_row["json"])
        with pytest.raises(sqlite3.IntegrityError, match="binding is immutable"):
            await store.db.execute(
                "UPDATE interventions SET json = ? WHERE id = ?",
                (json.dumps(envelope["payload"]), intervention.id),
            )
        await store.db.rollback()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_find_handoff_uses_one_snapshot_during_concurrent_finalization(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_handoff_snapshot")
    await store.connect()
    try:
        goal, source, target = await _seed(store)
        item, bundle, event, intervention = _artifacts(goal, source, target)
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
        )
        effect_id = reserved["effect"]["effect_id"]
        await store.start_operator_handoff_dispatch(effect_id)

        snapshot_started = asyncio.Event()
        continue_read = asyncio.Event()
        original_validate = store._validate_operator_handoff_effect

        async def pause_snapshot(connection, effect, **kwargs):
            if effect["state"] == "dispatching" and not snapshot_started.is_set():
                snapshot_started.set()
                await continue_read.wait()
            return await original_validate(connection, effect, **kwargs)

        monkeypatch.setattr(store, "_validate_operator_handoff_effect", pause_snapshot)
        read_task = asyncio.create_task(
            store.find_operator_handoff(
                principal_id=PRINCIPAL,
                idempotency_key=KEY,
                source_session_id=source.id,
                target_session_id=target.id,
                token_budget=2_000,
            )
        )
        await snapshot_started.wait()
        delivered = await store.finalize_operator_handoff(
            effect_id=effect_id,
            state="delivered",
            result=_synthetic_delivery_result(target),
        )
        continue_read.set()
        historical = await read_task

        assert historical is not None
        assert historical["effect"]["state"] == "dispatching"
        assert historical["intervention"].result == "handoff_delivery_in_progress"
        assert delivered["effect"]["state"] == "delivered"
        current = await store.find_operator_handoff(
            principal_id=PRINCIPAL,
            idempotency_key=KEY,
            source_session_id=source.id,
            target_session_id=target.id,
            token_budget=2_000,
        )
        assert current is not None and current["effect"]["state"] == "delivered"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_actor_receipt_failure_rolls_back_handoff_effect_intervention_and_audit(
    tmp_path,
):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_handoff_actor_fail")
    await store.connect()
    try:
        goal, source, target = await _seed(store)
        key = "handoff-actor-failure-0001"
        item, bundle, event, intervention = _artifacts(goal, source, target, key=key)
        intervention.metadata["human_requested"] = True
        await store.add_context(item)
        reserved = await store.reserve_operator_handoff(
            principal_id=PRINCIPAL,
            idempotency_key=key,
            source_session_id=source.id,
            target_session_id=target.id,
            token_budget=2_000,
            bundle=bundle,
            event=event,
            intervention=intervention,
            actor_assurance="bridge_bearer",
        )
        effect_id = reserved["effect"]["effect_id"]
        await store.start_operator_handoff_dispatch(effect_id)
        await store.db.execute(
            "CREATE TRIGGER fail_handoff_actor_receipt BEFORE INSERT ON "
            "human_operator_terminal_actions BEGIN SELECT RAISE(ABORT, "
            "'forced handoff actor receipt failure'); END"
        )
        await store.db.commit()

        with pytest.raises(sqlite3.IntegrityError, match="forced handoff actor receipt"):
            await store.finalize_operator_handoff(
                effect_id=effect_id,
                state="delivered",
                result=_synthetic_delivery_result(target),
            )
        effect = await store.get_operator_effect(effect_id)
        assert effect is not None and effect["state"] == "dispatching"
        intervention_cursor = await store.db.execute(
            "SELECT json FROM interventions WHERE id = ?",
            (intervention.id,),
        )
        stored = json.loads((await intervention_cursor.fetchone())["json"])["payload"]
        assert stored["result"] == "handoff_delivery_in_progress"
        audit_cursor = await store.db.execute(
            "SELECT COUNT(*) FROM intervention_audit WHERE intervention_id = ? "
            "AND record_type = 'handoff_delivery_delivered'",
            (intervention.id,),
        )
        assert (await audit_cursor.fetchone())[0] == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_codex_handoff_store_requires_exact_turn_receipt(tmp_path):
    store = Store(tmp_path / "pex-codex-handoff.sqlite")
    await store.connect()
    try:
        goal, source, synthetic_target = await _seed(store)
        target = synthetic_target.model_copy(
            update={
                "id": "codex:handoff-target",
                "harness_type": HarnessType.CODEX,
                "vendor_session_id": "thread-handoff-target",
            }
        )
        await store.upsert_session(target)
        key = "handoff-codex-receipt-0001"
        item, bundle, event, intervention = _artifacts(goal, source, target, key=key)
        await store.add_context(item)
        reserved = await store.reserve_operator_handoff(
            principal_id=PRINCIPAL,
            idempotency_key=key,
            source_session_id=source.id,
            target_session_id=target.id,
            token_budget=2_000,
            bundle=bundle,
            event=event,
            intervention=intervention,
        )
        await store.start_operator_handoff_dispatch(reserved["effect"]["effect_id"])

        with pytest.raises(ValueError, match="requires an exact turn receipt"):
            await store.finalize_operator_handoff(
                effect_id=reserved["effect"]["effect_id"],
                state="delivered",
                result={"status": "delivered"},
            )
        pending = await store.get_operator_effect(reserved["effect"]["effect_id"])
        assert pending is not None and pending["state"] == "dispatching"

        receipt = {
            "schema": "pex.worker-delivery.codex-turn.v1",
            "target_session_id": target.id,
            "vendor_session_id": target.vendor_session_id,
            "vendor_turn_id": "turn-handoff-target",
        }
        rebound = target.model_copy(update={"vendor_session_id": "thread-after-handoff"})
        await store.db.execute(
            "UPDATE sessions SET vendor_session_id = ?, json = ? WHERE id = ?",
            (rebound.vendor_session_id, rebound.model_dump_json(), rebound.id),
        )
        await store.db.commit()
        result = {"status": "delivered", "worker_delivery_receipt": receipt}
        final = await store.finalize_operator_handoff(
            effect_id=reserved["effect"]["effect_id"],
            state="delivered",
            result=result,
        )
        assert final["effect"]["result"]["worker_delivery_receipt"] == receipt
        assert final["intervention"].metadata["worker_delivery_receipt"] == receipt
        replay = await store.finalize_operator_handoff(
            effect_id=reserved["effect"]["effect_id"],
            state="delivered",
            result=result,
        )
        assert replay["effect"] == final["effect"]

        await store.db.execute(
            "UPDATE operator_effects SET result_json = ? WHERE effect_id = ?",
            (
                json.dumps({"status": "delivered"}),
                reserved["effect"]["effect_id"],
            ),
        )
        await store.db.commit()
        with pytest.raises(RuntimeError, match="delivery receipt"):
            await store.get_operator_effect(reserved["effect"]["effect_id"])
        with pytest.raises(RuntimeError, match="delivery receipt"):
            await store.find_operator_handoff(
                principal_id=PRINCIPAL,
                idempotency_key=key,
                source_session_id=source.id,
                target_session_id=target.id,
                token_budget=2_000,
            )
        with pytest.raises(RuntimeError, match="delivery receipt"):
            await store.handoff_assimilation_status(reserved["effect"]["effect_id"])
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_handoff_same_key_changed_target_conflicts_before_live_lookup(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        goal, source, target = await _seed(store)
        item, bundle, event, intervention = _artifacts(goal, source, target)
        await store.add_context(item)
        await store.reserve_operator_handoff(
            principal_id=PRINCIPAL,
            idempotency_key=KEY,
            source_session_id=source.id,
            target_session_id=target.id,
            token_budget=2_000,
            bundle=bundle,
            event=event,
            intervention=intervention,
        )
        with pytest.raises(OperatorEffectConflictError):
            await store.find_operator_handoff(
                principal_id=PRINCIPAL,
                idempotency_key=KEY,
                source_session_id=source.id,
                target_session_id="synthetic:a-different-target",
                token_budget=2_000,
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_handoff_quarantine_after_reservation_blocks_dispatch_and_can_seal_skip(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    project_id = "handoff-quarantine-project"
    try:
        goal, source, target = await _seed(store, project_id)
        item, bundle, event, intervention = _artifacts(goal, source, target)
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
        )
        origin = ProjectOrigin(namespace="machine", host="handoff-test-host")
        await store.register_project_locator(
            legacy_project_id=project_id,
            locator=ProjectLocator.path(
                "/work/one",
                platform=PathPlatform.POSIX,
                origin=origin,
            ),
        )
        await store.register_project_locator(
            legacy_project_id=project_id,
            locator=ProjectLocator.path(
                "/work/two",
                platform=PathPlatform.POSIX,
                origin=origin,
            ),
        )
        with pytest.raises(ProjectIdentityBlockedError):
            await store.start_operator_handoff_dispatch(reserved["effect"]["effect_id"])
        skipped = await store.finalize_operator_handoff(
            effect_id=reserved["effect"]["effect_id"],
            state="skipped",
            result={"status": "skipped", "reason": "project_identity_quarantined"},
        )
        assert skipped["effect"]["state"] == "skipped"
        assert skipped["intervention"].result == "project_identity_quarantined"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_handoff_restart_recovery_couples_effect_intervention_and_audit(tmp_path):
    path = tmp_path / "pex.sqlite"
    first_store = Store(path, process_boot_id="boot_handoff_before_restart")
    await first_store.connect()
    goal, source, target = await _seed(first_store)
    item, bundle, event, intervention = _artifacts(goal, source, target)
    await first_store.add_context(item)
    reserved = await first_store.reserve_operator_handoff(
        principal_id=PRINCIPAL,
        idempotency_key=KEY,
        source_session_id=source.id,
        target_session_id=target.id,
        token_budget=2_000,
        bundle=bundle,
        event=event,
        intervention=intervention,
    )
    dispatch = await first_store.start_operator_handoff_dispatch(
        reserved["effect"]["effect_id"]
    )
    assert dispatch["granted"] is True
    await first_store.close()

    recovered_store = Store(path, process_boot_id="boot_handoff_after_restart")
    await recovered_store.connect()
    try:
        assert await recovered_store.recover_interrupted_operator_effects() == 1
        found = await recovered_store.find_operator_handoff(
            principal_id=PRINCIPAL,
            idempotency_key=KEY,
            source_session_id=source.id,
            target_session_id=target.id,
            token_budget=2_000,
        )
        assert found is not None
        assert found["effect"]["state"] == "delivery_uncertain"
        assert found["effect"]["result"] == {
            "status": "delivery_uncertain",
            "reason": "process_restarted_after_dispatch_started",
        }
        assert found["intervention"].result == "handoff_delivery_uncertain"
        assert (
            found["intervention"].metadata["handoff_delivery_status"]
            == "delivery_uncertain"
        )
        replay = await recovered_store.start_operator_handoff_dispatch(
            reserved["effect"]["effect_id"]
        )
        assert replay["granted"] is False
        assert replay["reason"] == "effect_already_delivery_uncertain"
        cursor = await recovered_store.db.execute(
            "SELECT record_type FROM intervention_audit WHERE intervention_id = ? "
            "ORDER BY id",
            (intervention.id,),
        )
        assert [row["record_type"] for row in await cursor.fetchall()] == [
            "handoff_delivery_reserved",
            "handoff_delivery_dispatching",
            "handoff_delivery_delivery_uncertain",
        ]
    finally:
        await recovered_store.close()


@pytest.mark.asyncio
async def test_handoff_restart_recovery_rejects_corrupt_dispatch_authority(tmp_path):
    path = tmp_path / "pex-corrupt-recovery.sqlite"
    owner = Store(path, process_boot_id="boot_handoff_corrupt_before")
    await owner.connect()
    goal, source, target = await _seed(owner)
    item, bundle, event, intervention = _artifacts(goal, source, target)
    await owner.add_context(item)
    reserved = await owner.reserve_operator_handoff(
        principal_id=PRINCIPAL,
        idempotency_key=KEY,
        source_session_id=source.id,
        target_session_id=target.id,
        token_budget=2_000,
        bundle=bundle,
        event=event,
        intervention=intervention,
    )
    effect_id = reserved["effect"]["effect_id"]
    await owner.start_operator_handoff_dispatch(effect_id)
    await owner.db.execute("DROP TRIGGER trg_handoff_dispatch_watermark_immutable")
    await owner.db.execute(
        "UPDATE handoff_dispatch_watermarks SET json = ? WHERE effect_id = ?",
        (json.dumps({"schema": "forged"}), effect_id),
    )
    await owner.db.commit()
    await owner.close()

    recovery = Store(path, process_boot_id="boot_handoff_corrupt_after")
    await recovery.connect()
    try:
        with pytest.raises(RuntimeError, match="watermark schema"):
            await recovery.recover_interrupted_operator_effects()
        effect = await recovery.get_operator_effect(effect_id)
        stored_intervention = await recovery.get_intervention(intervention.id)
        assert effect is not None and effect["state"] == "dispatching"
        assert stored_intervention is not None
        assert stored_intervention.result == "handoff_delivery_in_progress"
        cursor = await recovery.db.execute(
            "SELECT COUNT(*) AS count FROM intervention_audit "
            "WHERE intervention_id = ? AND record_type = ?",
            (intervention.id, "handoff_delivery_delivery_uncertain"),
        )
        assert (await cursor.fetchone())["count"] == 0
    finally:
        await recovery.close()


@pytest.mark.asyncio
async def test_handoff_different_keys_cannot_reserve_the_same_target_items(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        goal, source, target = await _seed(store)
        item, bundle, event, intervention = _artifacts(goal, source, target)
        await store.add_context(item)
        await store.reserve_operator_handoff(
            principal_id=PRINCIPAL,
            idempotency_key=KEY,
            source_session_id=source.id,
            target_session_id=target.id,
            token_budget=2_000,
            bundle=bundle,
            event=event,
            intervention=intervention,
        )

        second_key = "handoff-operator-0002"
        _, second_bundle, second_event, second_intervention = _artifacts(
            goal,
            source,
            target,
            second_key,
        )
        with pytest.raises(
            ValueError,
            match="handoff bundle is not the canonical stored projection",
        ):
            await store.reserve_operator_handoff(
                principal_id=PRINCIPAL,
                idempotency_key=second_key,
                source_session_id=source.id,
                target_session_id=target.id,
                token_budget=2_000,
                bundle=second_bundle,
                event=second_event,
                intervention=second_intervention,
            )
        cursor = await store.db.execute("SELECT COUNT(*) AS count FROM operator_effects")
        assert (await cursor.fetchone())["count"] == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_handoff_project_reresolution_cannot_cross_reserved_physical_identity(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    project_id = "handoff-reresolution-project"
    try:
        origin = ProjectOrigin(namespace="machine", host="handoff-test-host")
        first_registration = await store.register_project_locator(
            legacy_project_id=project_id,
            locator=ProjectLocator.path(
                "/work/identity-a",
                platform=PathPlatform.POSIX,
                origin=origin,
            ),
        )
        goal, source, target = await _seed(store, project_id)
        item, bundle, event, intervention = _artifacts(goal, source, target)
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
        )
        second_registration = await store.register_project_locator(
            legacy_project_id=project_id,
            locator=ProjectLocator.path(
                "/work/identity-b",
                platform=PathPlatform.POSIX,
                origin=origin,
            ),
        )
        assert second_registration["outcome"] == "quarantined"
        assert (
            second_registration["identity"].id
            != first_registration["identity"].id
        )
        await store.resolve_project_identity_conflict(
            resolution_id="resolve-handoff-to-identity-b",
            legacy_project_id=project_id,
            selected_identity_id=second_registration["identity"].id,
            resolved_by="test_operator",
            rationale="Select the newly verified physical checkout.",
        )
        with pytest.raises(PermissionError, match="physical project binding changed"):
            await store.start_operator_handoff_dispatch(
                reserved["effect"]["effect_id"]
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_handoff_rejects_same_vendor_thread_without_partial_receipts(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        goal, source, target = await _seed(store)
        await store.db.execute("DELETE FROM sessions WHERE id = ?", (target.id,))
        await store.db.commit()
        target = target.model_copy(
            update={"vendor_session_id": source.vendor_session_id}
        )
        await store.upsert_session(target)
        item, bundle, event, intervention = _artifacts(goal, source, target)
        await store.add_context(item)
        with pytest.raises(PermissionError, match="alias one vendor session"):
            await store.reserve_operator_handoff(
                principal_id=PRINCIPAL,
                idempotency_key=KEY,
                source_session_id=source.id,
                target_session_id=target.id,
                token_budget=2_000,
                bundle=bundle,
                event=event,
                intervention=intervention,
            )
        cursor = await store.db.execute(
            "SELECT (SELECT COUNT(*) FROM operator_effects) AS effects, "
            "(SELECT COUNT(*) FROM interventions) AS interventions, "
            "(SELECT COUNT(*) FROM intervention_audit) AS audits, "
            "(SELECT COUNT(*) FROM events) AS events"
        )
        assert dict(await cursor.fetchone()) == {
            "effects": 0,
            "interventions": 0,
            "audits": 0,
            "events": 0,
        }
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_handoff_canonical_projection_accepts_typed_nonlexical_aliases(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    source_project = "handoff-alias-source"
    target_project = "handoff-alias-target"
    try:
        origin = ProjectOrigin(namespace="machine", host="handoff-alias-host")
        locator = ProjectLocator.path(
            "/work/shared-physical-checkout",
            platform=PathPlatform.POSIX,
            origin=origin,
        )
        source_registration = await store.register_project_locator(
            legacy_project_id=source_project,
            locator=locator,
        )
        target_registration = await store.register_project_locator(
            legacy_project_id=target_project,
            locator=locator,
        )
        assert (
            source_registration["identity"].id
            == target_registration["identity"].id
        )

        now = datetime.now(UTC)
        goal = Goal(
            id="handoff-alias-goal",
            project_id=source_project,
            title="Share across verified aliases",
            objective="Preserve immutable physical identity across raw aliases.",
            created_at=now,
            updated_at=now,
        )
        source = HarnessSession(
            id="synthetic:handoff-alias-source",
            harness_type=HarnessType.SYNTHETIC,
            vendor_session_id="handoff-alias-source",
            project_id=source_project,
            goal_id=goal.id,
            status=SessionStatus.WORKING,
            capabilities={"inject_context": True},
        )
        target = HarnessSession(
            id="synthetic:handoff-alias-target",
            harness_type=HarnessType.SYNTHETIC,
            vendor_session_id="handoff-alias-target",
            project_id=target_project,
            goal_id=goal.id,
            status=SessionStatus.WORKING,
            capabilities={"inject_context": True},
        )
        await store.upsert_goal(goal)
        await store.upsert_session(source)
        await store.upsert_session(target)
        item, bundle, event, intervention = _artifacts(
            goal,
            source,
            target,
            bundle_target_project_id=source_project,
        )
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
        )

        assert reserved["created"] is True
        assert reserved["effect"]["state"] == "reserved"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_handoff_rejects_stale_creation_identity_before_reservation(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    project_id = "handoff-stale-creation-project"
    try:
        origin = ProjectOrigin(namespace="machine", host="handoff-stale-host")
        await store.register_project_locator(
            legacy_project_id=project_id,
            locator=ProjectLocator.path(
                "/work/handoff-identity-a",
                platform=PathPlatform.POSIX,
                origin=origin,
            ),
        )
        goal, source, target = await _seed(store, project_id)
        item, bundle, event, intervention = _artifacts(goal, source, target)
        await store.add_context(item)
        conflict = await store.register_project_locator(
            legacy_project_id=project_id,
            locator=ProjectLocator.path(
                "/work/handoff-identity-b",
                platform=PathPlatform.POSIX,
                origin=origin,
            ),
        )
        await store.resolve_project_identity_conflict(
            resolution_id="resolve-stale-handoff-to-b",
            legacy_project_id=project_id,
            selected_identity_id=conflict["identity"].id,
            resolved_by="test_operator",
            rationale="Select the new physical checkout.",
        )

        with pytest.raises(ProjectIdentityBlockedError):
            await store.reserve_operator_handoff(
                principal_id=PRINCIPAL,
                idempotency_key=KEY,
                source_session_id=source.id,
                target_session_id=target.id,
                token_budget=2_000,
                bundle=bundle,
                event=event,
                intervention=intervention,
            )
        cursor = await store.db.execute(
            "SELECT (SELECT COUNT(*) FROM operator_effects) AS effects, "
            "(SELECT COUNT(*) FROM interventions) AS interventions, "
            "(SELECT COUNT(*) FROM events) AS events"
        )
        assert dict(await cursor.fetchone()) == {
            "effects": 0,
            "interventions": 0,
            "events": 0,
        }
    finally:
        await store.close()
