from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge.store import ProjectIdentityBlockedError, Store
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.overlay import Overlay, OverlayDiff
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessSession

ORIGIN = ProjectOrigin(namespace="machine", host="overlay-store-test")


def _goal(goal_id: str, project_id: str) -> Goal:
    now = datetime.now(UTC)
    return Goal(
        id=goal_id,
        project_id=project_id,
        title=goal_id,
        objective="Keep this overlay bound to one exact project and session.",
        created_at=now,
        updated_at=now,
    )


def _session(goal: Goal, *, suffix: str = "one") -> HarnessSession:
    return HarnessSession(
        id=f"synthetic:overlay-{suffix}",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id=f"overlay-{suffix}",
        project_id=goal.project_id,
        goal_id=goal.id,
        status=SessionStatus.WORKING,
        last_activity=datetime.now(UTC),
    )


def _overlay(session: HarnessSession, overlay_id: str, *, ttl: int = 3600) -> Overlay:
    return Overlay(
        id=overlay_id,
        session_id=session.id,
        reason="Pin the exact verified reproduction.",
        diff=OverlayDiff(tools_disabled=["WebSearch"], extra={"phase": "debug"}),
        ttl_seconds=ttl,
        rollback={
            "adapter": "synthetic",
            "operation": "revert_overlay",
            "overlay_id": overlay_id,
        },
    )


async def _seed_bound_session(
    store: Store,
    *,
    project_id: str = "overlay-project",
    suffix: str = "one",
    typed_path: str | None = None,
) -> tuple[Goal, HarnessSession]:
    if typed_path is not None:
        await store.register_project_locator(
            legacy_project_id=project_id,
            locator=ProjectLocator.path(
                typed_path,
                platform=PathPlatform.POSIX,
                origin=ORIGIN,
            ),
        )
    goal = _goal(f"goal-overlay-{suffix}", project_id)
    await store.upsert_goal(goal)
    session = _session(goal, suffix=suffix)
    await store.upsert_session(session)
    return goal, session


async def _add_overlay_owner(
    store: Store,
    overlay: Overlay,
    *,
    owner_intervention_id: str | None = None,
    policy_verdict: PolicyVerdict = PolicyVerdict.ALLOW,
) -> str:
    owner_intervention_id = owner_intervention_id or f"owner-{overlay.id}"
    action = ProposedAction(
        type=InterventionType.APPLY_OVERLAY,
        session_id=overlay.session_id,
        goal_id=(await store.get_session(overlay.session_id)).goal_id,
        payload={"overlay": overlay.model_dump(mode="json")},
        rationale="Apply this exact bounded test overlay.",
        evidence=["test:overlay-authority"],
        confidence=0.9,
        risk=RiskLevel.LOW,
        reversible=True,
        authority_required=Authority.LOCAL_POLICY,
    )
    await store.add_intervention(
        Intervention(
            id=owner_intervention_id,
            session_id=overlay.session_id,
            goal_id=action.goal_id,
            trigger="test_overlay_authority",
            evidence=action.evidence,
            diagnosis="bounded_test_overlay",
            proposed_action=action,
            confidence=action.confidence,
            risk=action.risk.value,
            reversible=True,
            authority_required=action.authority_required.value,
            action_taken=InterventionType.APPLY_OVERLAY.value,
            policy_verdict=policy_verdict,
            result="overlay_applied",
            created_at=datetime.now(UTC),
        )
    )
    return owner_intervention_id


async def _deliver_apply(
    store: Store,
    overlay: Overlay,
    *,
    delivered_at: datetime | None = None,
) -> dict:
    owner_intervention_id = await _add_overlay_owner(store, overlay)
    reserved = await store.reserve_overlay_apply(
        overlay,
        adapter_name="synthetic",
        owner_intervention_id=owner_intervention_id,
    )
    started = await store.start_overlay_operation(reserved["operation_id"])
    assert started["granted"] is True
    assert started["overlay"] == overlay
    assert started["session"].id == overlay.session_id
    return await store.finalize_overlay_operation(
        reserved["operation_id"],
        state="delivered",
        result={"code": "overlay_applied"},
        now=delivered_at,
    )


async def _rebind_to_b(store: Store, project_id: str) -> None:
    conflict = await store.register_project_locator(
        legacy_project_id=project_id,
        locator=ProjectLocator.path(
            f"/work/{project_id}-b",
            platform=PathPlatform.POSIX,
            origin=ORIGIN,
        ),
    )
    assert conflict["outcome"] == "quarantined"
    await store.resolve_project_identity_conflict(
        resolution_id=f"resolve-{project_id}-b",
        legacy_project_id=project_id,
        selected_identity_id=conflict["identity"].id,
        resolved_by="overlay-test",
        rationale="Select the second deliberately distinct checkout.",
    )


@pytest.mark.asyncio
async def test_runtime_blocks_rebind_but_exact_revert_and_terminal_replay_survive(tmp_path):
    path = tmp_path / "pex.sqlite"
    store = Store(path, process_boot_id="overlay-boot-a")
    await store.connect()
    goal, session = await _seed_bound_session(
        store,
        typed_path="/work/overlay-project-a",
    )
    overlay = _overlay(session, "overlay-bound-revert")
    try:
        await _deliver_apply(store, overlay)
        assert [item.id for item in await store.runtime_overlays(session.id)] == [overlay.id]

        await _rebind_to_b(store, goal.project_id)
        assert await store.runtime_overlays(session.id) == []
        with pytest.raises(ProjectIdentityBlockedError):
            await store.get_overlay_for_authority(overlay.id)
        apply_receipt = await store.get_overlay_operation(overlay.id, "apply")
        assert apply_receipt is not None
        apply_replay = await store.start_overlay_operation(apply_receipt["operation_id"])
        assert apply_replay["granted"] is False
        assert apply_replay["replayed"] is True
        assert apply_replay["state"] == "delivered"

        reserved = await store.reserve_overlay_revert(
            overlay.id,
            expected_session_id=session.id,
            required_owner_intervention_id=f"owner-{overlay.id}",
            authorized_by="operator-one",
            idempotency_key="undo-request-one",
            reason="operator_undo",
        )
        assert reserved["state"] == "reserved"
        grant = await store.start_overlay_operation(reserved["operation_id"])
        assert grant["granted"] is True
        assert grant["adapter"] == "synthetic"
        assert grant["session"].vendor_session_id == session.vendor_session_id
        await store.finalize_overlay_operation(
            reserved["operation_id"],
            state="delivered",
            result={"code": "overlay_reverted"},
        )
        owner = await store.get_intervention(f"owner-{overlay.id}")
        assert owner is not None
        assert owner.result == "overlay_reverted"
        assert owner.outcome == "overlay_reverted_by_human"
        assert owner.metadata["undo_result"] == "overlay_reverted"
        assert owner.metadata["overlay_revert_operation_id"] == reserved["operation_id"]
        assert owner.metadata["undo_receipt"]["operation_id"] == reserved["operation_id"]
        assert owner.metadata["undo_receipt"]["state"] == "delivered"
        audit_cursor = await store.db.execute(
            "SELECT COUNT(*) AS count FROM intervention_audit "
            "WHERE intervention_id = ? AND record_type = 'intervention_undo'",
            (owner.id,),
        )
        audit_row = await audit_cursor.fetchone()
        assert audit_row is not None
        assert int(audit_row["count"]) == 1
    finally:
        await store.close()

    restarted = Store(path, process_boot_id="overlay-boot-b")
    await restarted.connect()
    try:
        replay = await restarted.start_overlay_operation(reserved["operation_id"])
        assert replay["granted"] is False
        assert replay["replayed"] is True
        assert replay["state"] == "delivered"
        assert replay["session"].vendor_session_id == session.vendor_session_id
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_overlay_triggers_and_loader_reject_scalar_and_request_tamper(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    _, session = await _seed_bound_session(store, suffix="tamper")
    overlay = _overlay(session, "overlay-tamper")
    try:
        await _add_overlay_owner(
            store,
            overlay,
            owner_intervention_id="owner-overlay-tamper",
        )
        reserved = await store.reserve_overlay_apply(
            overlay,
            adapter_name="synthetic",
            owner_intervention_id="owner-overlay-tamper",
        )
        with pytest.raises(sqlite3.IntegrityError):
            await store.db.execute(
                "UPDATE overlay_operations SET vendor_session_id = 'substitute', "
                "state = 'skipped', version = version + 1, "
                "payload_json = json_set(payload_json, '$.state', 'skipped', "
                "'$.version', version + 1) WHERE operation_id = ?",
                (reserved["operation_id"],),
            )
        await store.db.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            await store.db.execute(
                "UPDATE overlay_operations SET state = 'skipped', version = version + 1, "
                "payload_json = json_set(payload_json, '$.state', 'skipped', "
                "'$.version', version + 1, '$.overlay.reason', 'tampered') "
                "WHERE operation_id = ?",
                (reserved["operation_id"],),
            )
        await store.db.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            await store.db.execute(
                "UPDATE overlays SET project_binding = 'identity:substitute', "
                "version = version + 1 WHERE id = ?",
                (overlay.id,),
            )
        await store.db.rollback()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_apply_requires_attached_goal_and_exact_harness_adapter(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    goal_less = HarnessSession(
        id="synthetic:goal-less-overlay",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="goal-less-overlay",
        project_id="goal-less-project",
        status=SessionStatus.WORKING,
        last_activity=datetime.now(UTC),
    )
    await store.upsert_session(goal_less)
    try:
        with pytest.raises(PermissionError, match="attached persistent goal"):
            await store.reserve_overlay_apply(
                _overlay(goal_less, "overlay-goal-less"),
                adapter_name="synthetic",
            )

        _, bound = await _seed_bound_session(store, suffix="adapter-mismatch")
        with pytest.raises(PermissionError, match="adapter does not match"):
            await store.reserve_overlay_apply(
                _overlay(bound, "overlay-adapter-mismatch"),
                adapter_name="opencode",
            )

        ownerless = _overlay(bound, "overlay-ownerless")
        with pytest.raises(PermissionError, match="requires an owner intervention"):
            await store.reserve_overlay_apply(ownerless, adapter_name="synthetic")

        owned = _overlay(bound, "overlay-owned-proposal")
        owner_id = await _add_overlay_owner(store, owned)
        substituted = _overlay(bound, "overlay-substituted-proposal")
        with pytest.raises(PermissionError, match="differs from its owner"):
            await store.reserve_overlay_apply(
                substituted,
                adapter_name="synthetic",
                owner_intervention_id=owner_id,
            )
        assert await store.get_overlay(substituted.id) is None

        denied = _overlay(bound, "overlay-denied-owner")
        denied_owner = await _add_overlay_owner(
            store,
            denied,
            policy_verdict=PolicyVerdict.DENY,
        )
        with pytest.raises(PermissionError, match="differs from its owner"):
            await store.reserve_overlay_apply(
                denied,
                adapter_name="synthetic",
                owner_intervention_id=denied_owner,
            )
        assert await store.get_overlay(denied.id) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_reserved_apply_cannot_replay_or_start_after_owner_disappears(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    _, session = await _seed_bound_session(store, suffix="orphaned-owner")
    overlay = _overlay(session, "overlay-orphaned-owner")
    owner_id = await _add_overlay_owner(store, overlay)
    try:
        reserved = await store.reserve_overlay_apply(
            overlay,
            adapter_name="synthetic",
            owner_intervention_id=owner_id,
        )
        await store.db.execute("DELETE FROM interventions WHERE id = ?", (owner_id,))
        await store.db.commit()

        with pytest.raises(PermissionError, match="owner intervention is missing"):
            await store.reserve_overlay_apply(
                overlay,
                adapter_name="synthetic",
                owner_intervention_id=owner_id,
            )
        with pytest.raises(PermissionError, match="owner intervention is missing"):
            await store.start_overlay_operation(reserved["operation_id"])
        current = await store.get_overlay_operation(overlay.id, "apply")
        assert current is not None and current["state"] == "reserved"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_start_is_one_winner_and_restart_recovery_is_exactly_once(tmp_path):
    path = tmp_path / "pex.sqlite"
    first = Store(path, process_boot_id="overlay-race-a")
    second = Store(path, process_boot_id="overlay-race-a")
    await first.connect()
    _, session = await _seed_bound_session(first, suffix="race")
    overlay = _overlay(session, "overlay-race")
    await _add_overlay_owner(
        first,
        overlay,
        owner_intervention_id="owner-overlay-race",
    )
    reserved = await first.reserve_overlay_apply(
        overlay,
        adapter_name="synthetic",
        owner_intervention_id="owner-overlay-race",
    )
    await second.connect()
    try:
        one, two = await asyncio.gather(
            first.start_overlay_operation(reserved["operation_id"]),
            second.start_overlay_operation(reserved["operation_id"]),
        )
        assert sum(item["granted"] is True for item in (one, two)) == 1
        current = await first.get_overlay_operation(overlay.id, "apply")
        assert current is not None and current["state"] == "dispatching"
        assert current["version"] == 1
        assert await first.recover_interrupted_overlay_operations() == 0
    finally:
        await second.close()
        await first.close()

    recovered = Store(path, process_boot_id="overlay-race-b")
    await recovered.connect()
    try:
        current = await recovered.get_overlay_operation(overlay.id, "apply")
        assert current is not None
        assert current["state"] == "delivery_uncertain"
        assert current["version"] == 2
        assert await recovered.recover_interrupted_overlay_operations() == 0
        replay = await recovered.start_overlay_operation(reserved["operation_id"])
        assert replay["granted"] is False and replay["state"] == "delivery_uncertain"
    finally:
        await recovered.close()


@pytest.mark.asyncio
async def test_revert_idempotency_replays_same_key_and_fresh_key_retries_known_failure(
    tmp_path,
):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    _, session = await _seed_bound_session(store, suffix="undo-idempotency")
    overlay = _overlay(session, "overlay-undo-idempotency")
    try:
        await _deliver_apply(store, overlay)
        first = await store.reserve_owned_overlay_revert(
            f"owner-{overlay.id}",
            authorized_by="operator-idempotency",
            idempotency_key="undo-key-one",
            reason="operator_undo",
        )
        started = await store.start_overlay_operation(first["operation_id"])
        assert started["granted"] is True
        await store.finalize_overlay_operation(
            first["operation_id"],
            state="failed",
            result={"code": "overlay_revert_failed"},
        )

        replay = await store.reserve_owned_overlay_revert(
            f"owner-{overlay.id}",
            authorized_by="operator-idempotency",
            idempotency_key="undo-key-one",
            reason="operator_undo",
        )
        assert replay["replayed"] is True
        assert replay["operation_id"] == first["operation_id"]
        assert replay["state"] == "failed"
        with pytest.raises(ValueError, match="idempotency key collision"):
            await store.reserve_owned_overlay_revert(
                f"owner-{overlay.id}",
                authorized_by="operator-idempotency",
                idempotency_key="undo-key-one",
                reason="changed_reason",
            )

        retry = await store.reserve_owned_overlay_revert(
            f"owner-{overlay.id}",
            authorized_by="operator-idempotency",
            idempotency_key="undo-key-two",
            reason="operator_undo",
        )
        assert retry["replayed"] is False
        assert retry["state"] == "reserved"
        assert retry["attempt_count"] == 1
        retry_started = await store.start_overlay_operation(retry["operation_id"])
        assert retry_started["granted"] is True
        await store.finalize_overlay_operation(
            retry["operation_id"],
            state="delivery_uncertain",
            result={"code": "overlay_revert_delivery_uncertain"},
        )
        assert await store.runtime_overlays(session.id) == []

        duplicate_owner = _overlay(session, "overlay-duplicate-owner")
        with pytest.raises(PermissionError, match="differs from its owner"):
            await store.reserve_overlay_apply(
                duplicate_owner,
                adapter_name="synthetic",
                owner_intervention_id=f"owner-{overlay.id}",
            )
        assert await store.get_overlay(duplicate_owner.id) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_expiry_keyset_advances_past_one_thousand_forensic_poison_rows(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    _, session = await _seed_bound_session(store, suffix="expiry")
    due = datetime.now(UTC) - timedelta(minutes=5)
    valid = _overlay(session, "zz-overlay-valid-expiry", ttl=1)
    await _deliver_apply(store, valid, delivered_at=due - timedelta(seconds=2))
    try:
        await store.db.execute("DROP TRIGGER trg_overlays_bound_insert")
        await store.db.execute("DROP TRIGGER trg_overlay_operations_bound_insert")
        for index in range(1001):
            overlay_id = f"aa-poison-{index:04d}"
            operation_id = f"poison-operation-{index:04d}"
            await store.db.execute(
                "INSERT INTO overlays(id, session_id, applied_at, expires_at, json) "
                "VALUES (?, ?, ?, ?, '{}')",
                (
                    overlay_id,
                    session.id,
                    "2000-01-01T00:00:00Z",
                    "2000-01-01T00:00:01Z",
                ),
            )
            await store.db.execute(
                "INSERT INTO overlay_operations("
                "operation_id, overlay_id, kind, session_id, request_hash, state, "
                "reserved_at, updated_at, payload_json) "
                "VALUES (?, ?, 'apply', ?, 'poison', 'delivered', ?, ?, '{}')",
                (operation_id, overlay_id, session.id, due.isoformat(), due.isoformat()),
            )
        await store.db.commit()
        await store._migrate_overlay_operations()

        first = await store.claim_expired_overlay_reverts(due, limit=1000)
        assert first["operations"] == []
        assert len(first["errors"]) == 1000
        assert first["next_cursor"] is not None
        cursor = first["next_cursor"]
        second = await store.claim_expired_overlay_reverts(
            due,
            limit=1000,
            after_expires_at=datetime.fromisoformat(cursor["expires_at"].replace("Z", "+00:00")),
            after_id=cursor["overlay_id"],
        )
        assert len(second["errors"]) == 1
        assert [item["overlay_id"] for item in second["operations"]] == [valid.id]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_expiry_claim_race_one_attempt_and_later_sweep_retries_known_failure(tmp_path):
    path = tmp_path / "pex.sqlite"
    first = Store(path)
    second = Store(path)
    await first.connect()
    _, session = await _seed_bound_session(first, suffix="expiry-race")
    due = datetime.now(UTC) - timedelta(minutes=2)
    overlay = _overlay(session, "overlay-expiry-race", ttl=1)
    await _deliver_apply(first, overlay, delivered_at=due - timedelta(seconds=2))
    await second.connect()
    a_selected = asyncio.Event()
    b_selected = asyncio.Event()
    release_b = asyncio.Event()
    reserve_a = first.reserve_overlay_revert
    reserve_b = second.reserve_overlay_revert

    async def delayed_a(*args, **kwargs):
        a_selected.set()
        await b_selected.wait()
        return await reserve_a(*args, **kwargs)

    async def delayed_b(*args, **kwargs):
        b_selected.set()
        await release_b.wait()
        return await reserve_b(*args, **kwargs)

    first.reserve_overlay_revert = delayed_a  # type: ignore[method-assign]
    second.reserve_overlay_revert = delayed_b  # type: ignore[method-assign]
    try:
        sweep_a = asyncio.create_task(first.claim_expired_overlay_reverts(due, limit=10))
        await a_selected.wait()
        sweep_b_started = due + timedelta(seconds=1)
        sweep_b = asyncio.create_task(
            second.claim_expired_overlay_reverts(sweep_b_started, limit=10)
        )
        await b_selected.wait()
        one = await sweep_a
        assert len(one["operations"]) == 1
        operation_id = one["operations"][0]["operation_id"]
        await first.start_overlay_operation(
            operation_id,
            now=due + timedelta(seconds=1, microseconds=500_000),
        )
        await first.finalize_overlay_operation(
            operation_id,
            state="failed",
            result={"code": "overlay_revert_failed"},
            now=due + timedelta(seconds=2),
        )
        release_b.set()
        two = await sweep_b
        assert len(two["operations"]) == 1
        coalesced = two["operations"][0]
        assert coalesced["operation_id"] == operation_id
        assert coalesced["state"] == "failed"
        assert coalesced["coalesced"] is True
        latest = await first.get_overlay_operation(overlay.id, "revert")
        assert latest is not None and latest["attempt_count"] == 0

        later = await first.claim_expired_overlay_reverts(
            due + timedelta(seconds=3),
            limit=10,
        )
        assert len(later["operations"]) == 1
        retry = later["operations"][0]
        assert retry["attempt_count"] == 1
        assert retry["operation_id"] != operation_id
    finally:
        await second.close()
        await first.close()
