from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.executor import ActionExecutor
from pex_bridge.store import Store, utcnow
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import PolicyVerdict
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.overlay import MAX_OVERLAY_TTL_SECONDS, Overlay, OverlayDiff
from pydantic import ValidationError


def _overlay(session_id: str, overlay_id: str = "ovl_test", ttl_seconds: int = 60) -> Overlay:
    return Overlay(
        id=overlay_id,
        session_id=session_id,
        reason="Pin the verified reproduction while debugging.",
        diff=OverlayDiff(
            tools_disabled=["WebSearch"],
            extra={"phase": "debug"},
        ),
        ttl_seconds=ttl_seconds,
    )


def _action(overlay: Overlay, *, session_id: str | None = None) -> ProposedAction:
    return ProposedAction(
        type=InterventionType.APPLY_OVERLAY,
        session_id=session_id or overlay.session_id,
        goal_id="goal_overlay",
        payload={"overlay": overlay.model_dump(mode="json")},
        rationale="Repeated failures justify a temporary debug configuration.",
        reversible=True,
    )


async def _seed_overlay_session(store: Store, adapters: AdapterRegistry, vendor_id: str):
    now = utcnow()
    await store.upsert_goal(
        Goal(
            id="goal_overlay",
            project_id="demo",
            title="Exercise the bounded overlay ledger",
            objective="Apply and revert only exact Store-bound session overlays.",
            created_at=now,
            updated_at=now,
        )
    )
    session = adapters.synthetic.seed_session(
        vendor_id=vendor_id,
        project_id="demo",
        goal_id="goal_overlay",
    )
    await store.upsert_session(session)
    return session


async def _add_overlay_owner(
    store: Store,
    action: ProposedAction,
    *,
    owner_intervention_id: str | None = None,
) -> str:
    raw_overlay = action.payload.get("overlay")
    overlay_id = str(raw_overlay.get("id") if isinstance(raw_overlay, dict) else "")
    owner_intervention_id = owner_intervention_id or f"int_owner_{overlay_id}"
    if await store.get_intervention(owner_intervention_id) is None:
        await store.add_intervention(
            Intervention(
                id=owner_intervention_id,
                session_id=action.session_id,
                goal_id=action.goal_id,
                trigger="test_overlay_lifecycle",
                evidence=action.evidence,
                diagnosis="bounded_test_overlay",
                proposed_action=action,
                confidence=action.confidence,
                risk=action.risk.value,
                reversible=action.reversible,
                authority_required=action.authority_required.value,
                action_taken=InterventionType.APPLY_OVERLAY.value,
                policy_verdict=PolicyVerdict.ALLOW,
                result="delivery_reserved",
                created_at=utcnow(),
            )
        )
    return owner_intervention_id


async def _execute_owned_overlay(
    executor: ActionExecutor,
    store: Store,
    action: ProposedAction,
    *,
    owner_intervention_id: str | None = None,
) -> str:
    owner_intervention_id = await _add_overlay_owner(
        store,
        action,
        owner_intervention_id=owner_intervention_id,
    )
    return await executor.execute(
        action,
        PolicyVerdict.ALLOW,
        operation_owner_id=owner_intervention_id,
    )


@pytest.mark.asyncio
async def test_overlay_apply_is_persisted_with_bounded_ttl_and_rollback(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = await _seed_overlay_session(store, adapters, "overlay-success")
    adapters.synthetic.apply_overlay = AsyncMock(return_value=True)
    adapters.synthetic.revert_overlay = AsyncMock(return_value=True)
    executor = ActionExecutor(adapters, store)
    overlay = _overlay(session.id)

    try:
        result = await _execute_owned_overlay(executor, store, _action(overlay))
        assert result == "overlay_applied"
        stored = await store.get_overlay(overlay.id)
        assert stored is not None
        assert stored.applied_at is not None
        assert stored.expires_at == stored.applied_at + timedelta(seconds=stored.ttl_seconds)
        assert stored.rollback == {
            "adapter": "synthetic",
            "operation": "revert_overlay",
            "overlay_id": overlay.id,
        }
        assert [item.id for item in await store.active_overlays(session.id)] == [overlay.id]

        duplicate = await _execute_owned_overlay(executor, store, _action(overlay))
        assert duplicate == "overlay_applied"
        assert adapters.synthetic.apply_overlay.await_count == 1

        outcomes = await executor.expire_overlays(stored.expires_at)
        assert outcomes == {overlay.id: "overlay_reverted"}
        reverted = await store.get_overlay(overlay.id)
        assert reverted is not None
        assert reverted.reverted_at == stored.expires_at
        assert reverted.revert_reason == "ttl_expired"
        assert await store.active_overlays(session.id) == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_failed_apply_keeps_terminal_receipt_and_never_blindly_rolls_back(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = await _seed_overlay_session(store, adapters, "overlay-failure")
    executor = ActionExecutor(adapters, store)

    try:
        adapters.synthetic.apply_overlay = AsyncMock(return_value=False)
        adapters.synthetic.revert_overlay = AsyncMock(return_value=True)
        failed = _overlay(session.id, "ovl_apply_failed")
        assert await _execute_owned_overlay(executor, store, _action(failed)) == "overlay_failed"
        stored = await store.get_overlay(failed.id)
        assert stored is not None and stored.applied_at is None
        receipt = await store.get_overlay_operation(failed.id, "apply")
        assert receipt is not None and receipt["state"] == "failed"
        assert receipt["result"] == {"code": "overlay_failed"}
        assert await _execute_owned_overlay(executor, store, _action(failed)) == "overlay_failed"
        assert adapters.synthetic.apply_overlay.await_count == 1
        adapters.synthetic.revert_overlay.assert_not_awaited()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_known_failed_ttl_revert_gets_a_new_durable_attempt(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = await _seed_overlay_session(store, adapters, "overlay-retry")
    adapters.synthetic.apply_overlay = AsyncMock(return_value=True)
    adapters.synthetic.revert_overlay = AsyncMock(return_value=False)
    executor = ActionExecutor(adapters, store)
    overlay = _overlay(session.id, "ovl_retry", ttl_seconds=1)

    try:
        assert await _execute_owned_overlay(executor, store, _action(overlay)) == "overlay_applied"
        stored = await store.get_overlay(overlay.id)
        assert stored is not None and stored.expires_at is not None
        outcomes = await executor.expire_overlays(stored.expires_at)
        assert outcomes == {overlay.id: "overlay_revert_failed"}
        assert [item.id for item in await store.active_overlays(session.id)] == [overlay.id]
        assert [item.id for item in await store.expired_overlays(stored.expires_at)] == [overlay.id]

        adapters.synthetic.revert_overlay = AsyncMock(return_value=True)
        retried = await executor.expire_overlays(stored.expires_at + timedelta(seconds=1))
        assert retried == {overlay.id: "overlay_reverted"}
        adapters.synthetic.revert_overlay.assert_awaited_once()
        receipt = await store.get_overlay_operation(overlay.id, "revert")
        assert receipt is not None and receipt["state"] == "delivered"
        assert receipt["attempt_count"] == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_apply_is_durable_before_adapter_io_and_binds_exact_owner(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = await _seed_overlay_session(store, adapters, "overlay-durable")
    executor = ActionExecutor(adapters, store)
    overlay = _overlay(session.id, "ovl_durable")

    async def inspect_durable_boundary(_session, candidate):
        receipt = await store.get_overlay_operation(candidate.id, "apply")
        stored = await store.get_overlay(candidate.id)
        assert receipt is not None and receipt["state"] == "dispatching"
        assert receipt["owner_intervention_id"] == "int_overlay_owner"
        assert receipt["payload"]["session_binding"]["session_id"] == session.id
        assert stored is not None and stored.applied_at is None
        return True

    adapters.synthetic.apply_overlay = AsyncMock(side_effect=inspect_durable_boundary)
    try:
        assert (
            await _execute_owned_overlay(
                executor,
                store,
                _action(overlay),
                owner_intervention_id="int_overlay_owner",
            )
            == "overlay_applied"
        )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_apply_timeout_is_uncertain_without_blind_revert_or_replay(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = await _seed_overlay_session(store, adapters, "overlay-timeout")
    adapters.synthetic.apply_overlay = AsyncMock(side_effect=TimeoutError)
    adapters.synthetic.revert_overlay = AsyncMock(return_value=True)
    executor = ActionExecutor(adapters, store)
    overlay = _overlay(session.id, "ovl_timeout")

    try:
        assert await _execute_owned_overlay(executor, store, _action(overlay)) == (
            "overlay_apply_delivery_uncertain"
        )
        receipt = await store.get_overlay_operation(overlay.id, "apply")
        assert receipt is not None and receipt["state"] == "delivery_uncertain"
        assert await _execute_owned_overlay(executor, store, _action(overlay)) == (
            "overlay_apply_delivery_uncertain"
        )
        assert adapters.synthetic.apply_overlay.await_count == 1
        adapters.synthetic.revert_overlay.assert_not_awaited()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_changed_overlay_content_conflicts_before_adapter_io(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = await _seed_overlay_session(store, adapters, "overlay-collision")
    adapters.synthetic.apply_overlay = AsyncMock(return_value=True)
    executor = ActionExecutor(adapters, store)
    first = _overlay(session.id, "ovl_collision")
    changed = Overlay.model_validate(
        {
            **first.model_dump(mode="python"),
            "reason": "Different content under the same identifier.",
        }
    )

    try:
        assert await _execute_owned_overlay(executor, store, _action(first)) == "overlay_applied"
        assert await _execute_owned_overlay(executor, store, _action(changed)) == (
            "overlay_id_conflict"
        )
        assert adapters.synthetic.apply_overlay.await_count == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_apply_cancellation_after_dispatch_is_uncertain_without_rollback(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = await _seed_overlay_session(store, adapters, "overlay-cancel")
    entered = asyncio.Event()

    async def block_after_dispatch(_session, _overlay):
        entered.set()
        await asyncio.Event().wait()

    adapters.synthetic.apply_overlay = AsyncMock(side_effect=block_after_dispatch)
    adapters.synthetic.revert_overlay = AsyncMock(return_value=True)
    executor = ActionExecutor(adapters, store)
    overlay = _overlay(session.id, "ovl_cancel")
    task = asyncio.create_task(_execute_owned_overlay(executor, store, _action(overlay)))

    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        receipt = await store.get_overlay_operation(overlay.id, "apply")
        assert receipt is not None and receipt["state"] == "delivery_uncertain"
        adapters.synthetic.revert_overlay.assert_not_awaited()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_revert_timeout_is_uncertain_and_never_redelivered(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = await _seed_overlay_session(store, adapters, "revert-timeout")
    adapters.synthetic.apply_overlay = AsyncMock(return_value=True)
    executor = ActionExecutor(adapters, store)
    overlay = _overlay(session.id, "ovl_revert_timeout", ttl_seconds=1)

    try:
        assert await _execute_owned_overlay(executor, store, _action(overlay)) == "overlay_applied"
        adapters.synthetic.revert_overlay = AsyncMock(side_effect=TimeoutError)
        assert await executor.revert_overlay(overlay.id) == ("overlay_revert_delivery_uncertain")
        assert await executor.revert_overlay(overlay.id) == ("overlay_revert_delivery_uncertain")
        assert adapters.synthetic.revert_overlay.await_count == 1
        receipt = await store.get_overlay_operation(overlay.id, "revert")
        assert receipt is not None and receipt["state"] == "delivery_uncertain"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_two_store_instances_grant_only_one_overlay_apply_dispatch(tmp_path):
    database = tmp_path / "pex.sqlite"
    first_store = Store(database, process_boot_id="boot_overlay_first")
    second_store = Store(database, process_boot_id="boot_overlay_second")
    await first_store.connect()
    await second_store.connect()
    adapters = AdapterRegistry()
    session = await _seed_overlay_session(first_store, adapters, "overlay-race")
    entered = asyncio.Event()
    release = asyncio.Event()

    async def one_dispatch(_session, _overlay):
        entered.set()
        await release.wait()
        return True

    adapters.synthetic.apply_overlay = AsyncMock(side_effect=one_dispatch)
    first = ActionExecutor(adapters, first_store)
    second = ActionExecutor(adapters, second_store)
    overlay = _overlay(session.id, "ovl_race")
    first_task = asyncio.create_task(_execute_owned_overlay(first, first_store, _action(overlay)))

    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        second_result = await _execute_owned_overlay(second, second_store, _action(overlay))
        release.set()
        first_result = await first_task
        assert first_result == "overlay_applied"
        assert second_result == "overlay_apply_in_progress"
        assert adapters.synthetic.apply_overlay.await_count == 1
    finally:
        release.set()
        if not first_task.done():
            await first_task
        await second_store.close()
        await first_store.close()


@pytest.mark.asyncio
async def test_nonowner_intervention_cannot_revert_a_delivered_overlay(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = await _seed_overlay_session(store, adapters, "overlay-owner")
    adapters.synthetic.apply_overlay = AsyncMock(return_value=True)
    adapters.synthetic.revert_overlay = AsyncMock(return_value=True)
    executor = ActionExecutor(adapters, store)
    overlay = _overlay(session.id, "ovl_owned")

    try:
        assert (
            await _execute_owned_overlay(
                executor,
                store,
                _action(overlay),
                owner_intervention_id="int_overlay_winner",
            )
            == "overlay_applied"
        )
        assert (
            await executor.revert_overlay(
                overlay.id,
                required_owner_intervention_id="int_overlay_loser",
                trigger_intervention_id="int_overlay_loser",
            )
            == "overlay_owner_mismatch"
        )
        adapters.synthetic.revert_overlay.assert_not_awaited()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_overlay_final_cas_rejects_a_session_paused_after_reservation(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = await _seed_overlay_session(store, adapters, "overlay-pause")
    overlay = Overlay.model_validate(
        {
            **_overlay(session.id, "ovl_pause").model_dump(mode="python"),
            "rollback": {
                "adapter": "synthetic",
                "operation": "revert_overlay",
                "overlay_id": "ovl_pause",
            },
        }
    )

    try:
        owner_intervention_id = await _add_overlay_owner(store, _action(overlay))
        operation = await store.reserve_overlay_apply(
            overlay,
            adapter_name="synthetic",
            owner_intervention_id=owner_intervention_id,
        )
        session.supervision_paused = True
        await store.upsert_session(session, allow_supervision_change=True)
        with pytest.raises(PermissionError, match="binding changed|paused"):
            await store.start_overlay_operation(operation["operation_id"])
        current = await store.get_overlay_operation(overlay.id, "apply")
        assert current is not None and current["state"] == "reserved"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_overlay_rejects_cross_session_and_implicit_promotion(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    session = await _seed_overlay_session(store, adapters, "overlay-guard")
    adapters.synthetic.apply_overlay = AsyncMock(return_value=True)
    executor = ActionExecutor(adapters, store)

    try:
        wrong_session = _overlay("synthetic:someone-else", "ovl_wrong_session")
        result = await executor.execute(
            _action(wrong_session, session_id=session.id),
            PolicyVerdict.ALLOW,
        )
        assert result == "overlay_session_mismatch"

        promoted = _overlay(session.id, "ovl_promoted")
        promoted.promoted = True
        result = await executor.execute(_action(promoted), PolicyVerdict.ALLOW)
        assert result == "overlay_promotion_requires_explicit_user"
        adapters.synthetic.apply_overlay.assert_not_awaited()
    finally:
        await store.close()


def test_overlay_schema_requires_a_diff_and_positive_bounded_ttl():
    with pytest.raises(ValidationError, match="at least one change"):
        OverlayDiff()
    with pytest.raises(ValidationError):
        _overlay("synthetic:test", ttl_seconds=0)
    with pytest.raises(ValidationError):
        _overlay("synthetic:test", ttl_seconds=MAX_OVERLAY_TTL_SECONDS + 1)


def test_overlay_derives_expiry_when_loading_legacy_applied_record():
    applied_at = utcnow()
    overlay = Overlay(
        id="ovl_legacy",
        session_id="synthetic:legacy",
        reason="Legacy durable record.",
        diff=OverlayDiff(extra={"phase": "debug"}),
        ttl_seconds=30,
        applied_at=applied_at,
    )
    assert overlay.expires_at == applied_at + timedelta(seconds=30)


def test_overlay_rejects_expiry_beyond_its_bounded_ttl():
    applied_at = utcnow()
    with pytest.raises(ValidationError, match="bounded TTL"):
        Overlay(
            id="ovl_unbounded_expiry",
            session_id="synthetic:legacy",
            reason="Invalid durable record.",
            diff=OverlayDiff(extra={"phase": "debug"}),
            ttl_seconds=30,
            applied_at=applied_at,
            expires_at=applied_at + timedelta(hours=2),
        )


def test_overlay_tool_names_are_individually_bounded():
    with pytest.raises(ValidationError):
        OverlayDiff(tools_enabled=["x" * 513])
