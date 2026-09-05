from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.executor import ActionExecutor
from pex_bridge.store import Store, utcnow
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import Authority, HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.overlay import Overlay, OverlayDiff
from pex_protocol.session import HarnessSession


def _overlay(session_id: str, overlay_id: str = "ovl_executor") -> Overlay:
    return Overlay(
        id=overlay_id,
        session_id=session_id,
        reason="Keep the verified reproduction pinned while debugging.",
        diff=OverlayDiff(tools_disabled=["WebSearch"], extra={"phase": "debug"}),
        ttl_seconds=60,
    )


def _action(overlay: Overlay, *, goal_id: str = "goal_overlay") -> ProposedAction:
    return ProposedAction(
        type=InterventionType.APPLY_OVERLAY,
        session_id=overlay.session_id,
        goal_id=goal_id,
        payload={"overlay": overlay.model_dump(mode="json")},
        rationale="Use one bounded reversible debug overlay.",
        reversible=True,
    )


def _session(session_id: str = "synthetic:overlay") -> HarnessSession:
    return HarnessSession(
        id=session_id,
        harness_type=HarnessType(session_id.split(":", 1)[0]),
        vendor_session_id=session_id.split(":", 1)[1],
        goal_id="goal_overlay",
        project_id="C:/workspace/overlay",
        cwd="C:/workspace/overlay",
    )


def _operation(
    overlay: Overlay,
    *,
    kind: str,
    state: str = "reserved",
    result: dict | None = None,
    index: int = 0,
) -> dict:
    operation_id = f"overlay_operation_{kind}_{index}_{overlay.id}"
    return {
        "operation_id": operation_id,
        "overlay_id": overlay.id,
        "kind": kind,
        "session_id": overlay.session_id,
        "goal_id": "goal_overlay",
        "vendor_session_id": overlay.session_id.split(":", 1)[1],
        "harness_type": overlay.session_id.split(":", 1)[0],
        "state": state,
        "version": 1,
        "reserved_at": utcnow().isoformat(),
        "dispatch_started_at": None,
        "finished_at": None,
        "payload": {"adapter": overlay.session_id.split(":", 1)[0]},
        "result": result,
    }


def _terminal(operation_id: str, *, state: str, result: dict) -> dict:
    return {
        "operation_id": operation_id,
        "state": state,
        "version": 2,
        "reserved_at": utcnow().isoformat(),
        "dispatch_started_at": utcnow().isoformat(),
        "finished_at": utcnow().isoformat(),
        "result": result,
    }


async def _seed_real_overlay_session(store: Store) -> HarnessSession:
    now = datetime.now(UTC)
    await store.upsert_goal(
        Goal(
            id="goal_overlay",
            project_id="C:/workspace/overlay",
            title="Overlay executor authority",
            objective="Keep each overlay bound to its exact approved intervention.",
            created_at=now,
            updated_at=now,
        )
    )
    session = _session()
    session.status = SessionStatus.WORKING
    session.last_activity = now
    await store.upsert_session(session)
    return session


async def _add_real_overlay_owner(
    store: Store,
    overlay: Overlay,
    *,
    intervention_id: str,
) -> None:
    action = _action(overlay)
    await store.add_intervention(
        Intervention(
            id=intervention_id,
            session_id=action.session_id,
            goal_id=action.goal_id,
            trigger="overlay_executor_authority_test",
            evidence=action.evidence,
            diagnosis="bounded_overlay_is_appropriate",
            proposed_action=action,
            confidence=action.confidence,
            risk=action.risk.value,
            reversible=action.reversible,
            authority_required=Authority.LOCAL_POLICY.value,
            action_taken=InterventionType.APPLY_OVERLAY.value,
            policy_verdict=PolicyVerdict.ALLOW,
            result="delivery_reserved",
            created_at=datetime.now(UTC),
        )
    )


@pytest.mark.asyncio
async def test_real_store_executor_refuses_ownerless_and_mismatched_apply_before_io(
    tmp_path,
):
    store = Store(tmp_path / "overlay-executor-authority.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    adapters.synthetic.probe = AsyncMock(
        side_effect=AssertionError("unauthorized overlay reached capability probe")
    )
    adapters.synthetic.apply_overlay = AsyncMock(
        side_effect=AssertionError("unauthorized overlay reached adapter I/O")
    )
    executor = ActionExecutor(adapters, store)
    session = await _seed_real_overlay_session(store)
    owned_overlay = _overlay(session.id, "ovl_owned_exactly")
    different_overlay = _overlay(session.id, "ovl_not_owned")
    await _add_real_overlay_owner(
        store,
        owned_overlay,
        intervention_id="int_exact_overlay_owner",
    )

    try:
        assert (
            await executor.execute(_action(owned_overlay), PolicyVerdict.ALLOW)
            == "overlay_dispatch_refused"
        )
        assert (
            await executor.execute(
                _action(different_overlay),
                PolicyVerdict.ALLOW,
                operation_owner_id="int_exact_overlay_owner",
            )
            == "overlay_dispatch_refused"
        )
        assert await store.get_overlay_operation(owned_overlay.id, "apply") is None
        assert await store.get_overlay_operation(different_overlay.id, "apply") is None
        assert await store.active_overlays(session.id) == []
        adapters.synthetic.probe.assert_not_awaited()
        adapters.synthetic.apply_overlay.assert_not_awaited()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_apply_reserves_before_probe_and_dispatches_only_canonical_grant():
    adapters = AdapterRegistry()
    session = _session()
    requested = _overlay(session.id)
    canonical = Overlay.model_validate(
        {
            **requested.model_dump(mode="python"),
            "rollback": {
                "adapter": "synthetic",
                "operation": "revert_overlay",
                "overlay_id": requested.id,
            },
        }
    )
    events: list[str] = []
    reserved = _operation(canonical, kind="apply")

    async def reserve(candidate, **_kwargs):
        events.append("reserve")
        assert candidate.rollback == canonical.rollback
        return reserved

    async def probe():
        events.append("probe")
        return SimpleNamespace(modify_config=True, config_scope="session")

    async def start(operation_id, *, store_projected):
        events.append("start")
        assert operation_id == reserved["operation_id"]
        assert store_projected is False
        dispatching = {**reserved, "state": "dispatching", "version": 2}
        return {
            **dispatching,
            "granted": True,
            "replayed": False,
            "operation": dispatching,
            "overlay": canonical,
            "session": session,
            "adapter": "synthetic",
            "rollback": dict(canonical.rollback),
        }

    async def apply(granted_session, granted_overlay):
        events.append("apply")
        assert granted_session is session
        assert granted_overlay is canonical
        return True

    async def finalize(operation_id, *, state, result, now=None):
        del now
        events.append("finalize")
        return _terminal(operation_id, state=state, result=result)

    store = SimpleNamespace(
        reserve_overlay_apply=AsyncMock(side_effect=reserve),
        require_session_workspace_current=AsyncMock(return_value=None),
        get_session=AsyncMock(return_value=session),
        start_overlay_operation=AsyncMock(side_effect=start),
        finalize_overlay_operation=AsyncMock(side_effect=finalize),
    )
    adapters.synthetic.probe = AsyncMock(side_effect=probe)
    adapters.synthetic.apply_overlay = AsyncMock(side_effect=apply)

    result = await ActionExecutor(adapters, store).execute(
        _action(requested),
        PolicyVerdict.ALLOW,
    )

    assert result == "overlay_applied"
    assert events == ["reserve", "probe", "start", "apply", "finalize"]


@pytest.mark.asyncio
async def test_terminal_apply_replay_bypasses_every_mutable_live_gate():
    adapters = AdapterRegistry()
    overlay = _overlay("synthetic:terminal", "ovl_terminal")
    terminal = {
        **_operation(
            overlay,
            kind="apply",
            state="delivered",
            result={"code": "overlay_applied"},
        ),
        "replayed": True,
    }
    store = SimpleNamespace(
        reserve_overlay_apply=AsyncMock(return_value=terminal),
        get_session=AsyncMock(side_effect=AssertionError("live session gate used")),
        start_overlay_operation=AsyncMock(side_effect=AssertionError("start replayed")),
    )
    adapters.synthetic.probe = AsyncMock(side_effect=AssertionError("probe replayed"))
    adapters.synthetic.apply_overlay = AsyncMock(
        side_effect=AssertionError("adapter replayed")
    )

    assert await ActionExecutor(adapters, store).execute(
        _action(overlay),
        PolicyVerdict.ALLOW,
    ) == "overlay_applied"
    store.get_session.assert_not_awaited()
    store.start_overlay_operation.assert_not_awaited()
    adapters.synthetic.probe.assert_not_awaited()
    adapters.synthetic.apply_overlay.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_preflight_refusal_terminalizes_reserved_without_start_or_io():
    adapters = AdapterRegistry()
    session = _session("synthetic:preflight")
    overlay = _overlay(session.id, "ovl_preflight")
    reserved = _operation(overlay, kind="apply")

    async def finalize(operation_id, *, state, result, now=None):
        del now
        assert state == "skipped"
        return _terminal(operation_id, state=state, result=result)

    store = SimpleNamespace(
        reserve_overlay_apply=AsyncMock(return_value=reserved),
        require_session_workspace_current=AsyncMock(return_value=None),
        get_session=AsyncMock(return_value=session),
        finalize_overlay_operation=AsyncMock(side_effect=finalize),
        start_overlay_operation=AsyncMock(side_effect=AssertionError("start must not run")),
    )
    adapters.synthetic.probe = AsyncMock(
        return_value=SimpleNamespace(modify_config=False, config_scope="session")
    )
    adapters.synthetic.apply_overlay = AsyncMock(
        side_effect=AssertionError("apply must not run")
    )

    result = await ActionExecutor(adapters, store).execute(
        _action(overlay),
        PolicyVerdict.ALLOW,
    )

    assert result == "overlay_modify_config_unsupported"
    store.start_overlay_operation.assert_not_awaited()
    adapters.synthetic.apply_overlay.assert_not_awaited()


@pytest.mark.asyncio
async def test_opencode_store_projection_never_calls_overlay_adapter():
    adapters = AdapterRegistry()
    session = _session("opencode:projection")
    requested = _overlay(session.id, "ovl_projection")
    canonical = Overlay.model_validate(
        {
            **requested.model_dump(mode="python"),
            "rollback": {
                "adapter": "opencode",
                "operation": "revert_overlay",
                "overlay_id": requested.id,
                "strategy": "bridge_active_overlay_query",
                "scope": "session",
                "plugin": "pex-opencode-plugin",
                "session_id": session.id,
            },
        }
    )
    reserved = _operation(canonical, kind="apply")
    delivered = {
        **reserved,
        "state": "delivered",
        "result": {"code": "overlay_applied", "mode": "store_projection"},
    }
    store = SimpleNamespace(
        reserve_overlay_apply=AsyncMock(return_value=reserved),
        require_session_workspace_current=AsyncMock(return_value=None),
        get_session=AsyncMock(return_value=session),
        active_overlays=AsyncMock(return_value=[]),
        start_overlay_operation=AsyncMock(
            return_value={
                **delivered,
                "granted": True,
                "replayed": False,
                "operation": delivered,
                "overlay": canonical,
                "session": session,
                "adapter": "opencode",
                "rollback": dict(canonical.rollback),
            }
        ),
    )
    adapters.opencode.probe = AsyncMock(
        return_value=SimpleNamespace(modify_config=True, config_scope="session")
    )
    adapters.opencode.overlay_projection_ready = Mock(return_value=True)
    adapters.opencode.apply_overlay = AsyncMock(
        side_effect=AssertionError("Store projection called adapter apply")
    )

    assert await ActionExecutor(adapters, store).execute(
        _action(requested),
        PolicyVerdict.ALLOW,
    ) == "overlay_applied"
    adapters.opencode.apply_overlay.assert_not_awaited()


@pytest.mark.asyncio
async def test_owned_revert_terminal_replay_returns_path_free_structured_receipt():
    adapters = AdapterRegistry()
    overlay = _overlay("synthetic:owned", "ovl_owned")
    terminal = {
        **_operation(
            overlay,
            kind="revert",
            state="delivered",
            result={
                "code": "overlay_reverted",
                "source_path": "C:/private/project/config.json",
                "rollback": {"strategy": "internal"},
            },
        ),
        "replayed": True,
        "version": 4,
        "finished_at": utcnow().isoformat(),
    }
    store = SimpleNamespace(
        reserve_owned_overlay_revert=AsyncMock(return_value=terminal),
    )

    result = await ActionExecutor(adapters, store).revert_overlay_receipt(
        owned_by_intervention_id="int_overlay_owner",
        authorized_by="local_bridge_operator",
        idempotency_key="overlay-undo-key-0001",
        reason="operator_undo",
    )

    assert result == {
        "ok": True,
        "code": "overlay_already_reverted",
        "state": "delivered",
        "replayed": True,
        "receipt": {
            "operation_id": terminal["operation_id"],
            "state": "delivered",
            "version": 4,
            "reserved_at": terminal["reserved_at"],
            "dispatch_started_at": None,
            "finished_at": terminal["finished_at"],
            "result": {"code": "overlay_reverted"},
        },
    }
    assert "payload" not in result["receipt"]
    assert "rollback" not in result["receipt"]
    assert "source_path" not in result["receipt"]["result"]


@pytest.mark.asyncio
async def test_revert_pending_and_uncertain_receipts_require_zero_io():
    adapters = AdapterRegistry()
    overlay = _overlay("synthetic:pending", "ovl_pending")
    pending = {
        **_operation(overlay, kind="revert", state="dispatching"),
        "replayed": True,
    }
    uncertain = {
        **_operation(
            overlay,
            kind="revert",
            state="delivery_uncertain",
            result={"code": "overlay_revert_delivery_uncertain"},
        ),
        "replayed": True,
    }
    store = SimpleNamespace(
        reserve_overlay_revert=AsyncMock(side_effect=[pending, uncertain]),
        start_overlay_operation=AsyncMock(side_effect=AssertionError("terminal started")),
    )
    adapters.synthetic.revert_overlay = AsyncMock(
        side_effect=AssertionError("terminal replayed")
    )
    executor = ActionExecutor(adapters, store)

    pending_result = await executor.revert_overlay_receipt(overlay.id)
    uncertain_result = await executor.revert_overlay_receipt(overlay.id)

    assert pending_result["state"] == "dispatching"
    assert pending_result["code"] == "overlay_revert_in_progress"
    assert pending_result["replayed"] is True
    assert uncertain_result["state"] == "delivery_uncertain"
    assert uncertain_result["code"] == "overlay_revert_delivery_uncertain"
    store.start_overlay_operation.assert_not_awaited()
    adapters.synthetic.revert_overlay.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_cancellation_retains_finalize_task_before_reraising():
    adapters = AdapterRegistry()
    session = _session("synthetic:cancel")
    overlay = _overlay(session.id, "ovl_cancel_retained")
    reserved = _operation(overlay, kind="apply")
    canonical = Overlay.model_validate(
        {
            **overlay.model_dump(mode="python"),
            "rollback": {
                "adapter": "synthetic",
                "operation": "revert_overlay",
                "overlay_id": overlay.id,
            },
        }
    )
    dispatching = {**reserved, "state": "dispatching", "version": 2}
    adapter_entered = asyncio.Event()
    finalize_entered = asyncio.Event()
    finalize_release = asyncio.Event()
    terminal_persisted = asyncio.Event()

    async def apply(_session, _overlay):
        adapter_entered.set()
        await asyncio.Event().wait()

    async def finalize(operation_id, *, state, result, now=None):
        del now
        assert state == "delivery_uncertain"
        finalize_entered.set()
        await finalize_release.wait()
        terminal_persisted.set()
        return _terminal(operation_id, state=state, result=result)

    store = SimpleNamespace(
        reserve_overlay_apply=AsyncMock(return_value=reserved),
        require_session_workspace_current=AsyncMock(return_value=None),
        get_session=AsyncMock(return_value=session),
        start_overlay_operation=AsyncMock(
            return_value={
                **dispatching,
                "granted": True,
                "replayed": False,
                "operation": dispatching,
                "overlay": canonical,
                "session": session,
                "adapter": "synthetic",
                "rollback": dict(canonical.rollback),
            }
        ),
        finalize_overlay_operation=AsyncMock(side_effect=finalize),
    )
    adapters.synthetic.probe = AsyncMock(
        return_value=SimpleNamespace(modify_config=True, config_scope="session")
    )
    adapters.synthetic.apply_overlay = AsyncMock(side_effect=apply)
    task = asyncio.create_task(
        ActionExecutor(adapters, store).execute(_action(overlay), PolicyVerdict.ALLOW)
    )

    await asyncio.wait_for(adapter_entered.wait(), timeout=2)
    task.cancel()
    await asyncio.wait_for(finalize_entered.wait(), timeout=2)
    assert not task.done()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    finalize_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert terminal_persisted.is_set()
    store.finalize_overlay_operation.assert_awaited_once()


@pytest.mark.asyncio
async def test_two_executor_revert_race_marks_loser_replayed_and_calls_adapter_once():
    adapters = AdapterRegistry()
    session = _session("synthetic:race")
    overlay = Overlay.model_validate(
        {
            **_overlay(session.id, "ovl_race").model_dump(mode="python"),
            "rollback": {
                "adapter": "synthetic",
                "operation": "revert_overlay",
                "overlay_id": "ovl_race",
            },
        }
    )
    reserved = _operation(overlay, kind="revert")
    dispatching = {**reserved, "state": "dispatching", "version": 2}
    both_reserved = asyncio.Event()
    reservation_count = 0
    adapter_entered = asyncio.Event()
    adapter_release = asyncio.Event()

    async def reserve(*_args, **_kwargs):
        nonlocal reservation_count
        reservation_count += 1
        if reservation_count == 2:
            both_reserved.set()
        await both_reserved.wait()
        replayed = asyncio.current_task().get_name() == "overlay-race-loser"
        return {**reserved, "replayed": replayed}

    async def start(_operation_id, *, store_projected):
        assert store_projected is False
        if asyncio.current_task().get_name() == "overlay-race-loser":
            return {
                **dispatching,
                "granted": False,
                # The executor must preserve the replay bit from reservation
                # even if the start response omits it.
                "replayed": False,
                "operation": dispatching,
            }
        return {
            **dispatching,
            "granted": True,
            "replayed": False,
            "operation": dispatching,
            "overlay": overlay,
            "session": session,
            "adapter": "synthetic",
            "rollback": dict(overlay.rollback),
        }

    async def revert(_overlay_id, _rollback):
        adapter_entered.set()
        await adapter_release.wait()
        return True

    async def finalize(operation_id, *, state, result, now=None):
        del now
        return _terminal(operation_id, state=state, result=result)

    store = SimpleNamespace(
        reserve_overlay_revert=AsyncMock(side_effect=reserve),
        start_overlay_operation=AsyncMock(side_effect=start),
        finalize_overlay_operation=AsyncMock(side_effect=finalize),
    )
    adapters.synthetic.revert_overlay = AsyncMock(side_effect=revert)
    first = ActionExecutor(adapters, store)
    second = ActionExecutor(adapters, store)
    winner = asyncio.create_task(
        first.revert_overlay_receipt(
            overlay.id,
            authorized_by="local_bridge_operator",
            idempotency_key="same-overlay-revert-key",
        ),
        name="overlay-race-winner",
    )
    loser = asyncio.create_task(
        second.revert_overlay_receipt(
            overlay.id,
            authorized_by="local_bridge_operator",
            idempotency_key="same-overlay-revert-key",
        ),
        name="overlay-race-loser",
    )

    loser_receipt = await asyncio.wait_for(loser, timeout=2)
    assert loser_receipt["state"] == "dispatching"
    assert loser_receipt["code"] == "overlay_revert_in_progress"
    assert loser_receipt["replayed"] is True
    await asyncio.wait_for(adapter_entered.wait(), timeout=2)
    adapter_release.set()
    winner_receipt = await asyncio.wait_for(winner, timeout=2)
    assert winner_receipt["code"] == "overlay_reverted"
    adapters.synthetic.revert_overlay.assert_awaited_once()


@pytest.mark.asyncio
async def test_expiry_keyset_drains_past_1000_failures_without_same_sweep_retry():
    adapters = AdapterRegistry()
    session = _session("synthetic:expiry")
    now = utcnow()
    overlays = [
        Overlay(
            id=f"ovl_expiry_{index:04d}",
            session_id=session.id,
            reason="Expired bounded overlay.",
            diff=OverlayDiff(tools_disabled=["WebSearch"], extra={"phase": "debug"}),
            ttl_seconds=1,
            applied_at=now - timedelta(seconds=2),
            expires_at=now - timedelta(seconds=1),
            rollback={
                "adapter": "synthetic",
                "operation": "revert_overlay",
                "overlay_id": f"ovl_expiry_{index:04d}",
            },
        )
        for index in range(1001)
    ]
    operations = [
        _operation(item, kind="revert", index=index)
        for index, item in enumerate(overlays)
    ]
    claim_calls: list[tuple[object, object]] = []

    async def claim(_now, *, limit, after_expires_at, after_id):
        assert limit == 1000
        claim_calls.append((after_expires_at, after_id))
        if len(claim_calls) == 1:
            return {
                "operations": operations[:1000],
                "errors": [],
                "next_cursor": {
                    "expires_at": (now - timedelta(seconds=1)).isoformat(),
                    "overlay_id": overlays[999].id,
                },
            }
        return {"operations": operations[1000:], "errors": [], "next_cursor": None}

    overlay_by_operation = {
        operation["operation_id"]: overlay
        for operation, overlay in zip(operations, overlays, strict=True)
    }

    async def start(operation_id, *, store_projected):
        assert store_projected is False
        operation = next(
            item for item in operations if item["operation_id"] == operation_id
        )
        dispatching = {**operation, "state": "dispatching", "version": 2}
        overlay = overlay_by_operation[operation_id]
        return {
            **dispatching,
            "granted": True,
            "replayed": False,
            "operation": dispatching,
            "overlay": overlay,
            "session": session,
            "adapter": "synthetic",
            "rollback": dict(overlay.rollback),
        }

    async def revert(overlay_id, _rollback):
        return overlay_id == overlays[-1].id

    async def finalize(operation_id, *, state, result, now=None):
        del now
        return _terminal(operation_id, state=state, result=result)

    store = SimpleNamespace(
        claim_expired_overlay_reverts=AsyncMock(side_effect=claim),
        start_overlay_operation=AsyncMock(side_effect=start),
        finalize_overlay_operation=AsyncMock(side_effect=finalize),
    )
    adapters.synthetic.revert_overlay = AsyncMock(side_effect=revert)

    outcomes = await ActionExecutor(adapters, store).expire_overlays(now)

    assert len(outcomes) == 1001
    assert outcomes[overlays[0].id] == "overlay_revert_failed"
    assert outcomes[overlays[-1].id] == "overlay_reverted"
    assert adapters.synthetic.revert_overlay.await_count == 1001
    assert store.start_overlay_operation.await_count == 1001
    assert len({call.args[0] for call in store.start_overlay_operation.await_args_list}) == 1001
    assert claim_calls[0] == (None, None)
    assert claim_calls[1][1] == overlays[999].id


@pytest.mark.asyncio
async def test_expiry_coalesced_failed_receipt_is_never_dispatched():
    adapters = AdapterRegistry()
    overlay = _overlay("synthetic:coalesced", "ovl_coalesced")
    failed = {
        **_operation(
            overlay,
            kind="revert",
            state="failed",
            result={"code": "overlay_revert_failed"},
        ),
        "coalesced": True,
        "blocked_by_existing": True,
    }
    store = SimpleNamespace(
        claim_expired_overlay_reverts=AsyncMock(
            return_value={"operations": [failed], "errors": [], "next_cursor": None}
        ),
        start_overlay_operation=AsyncMock(side_effect=AssertionError("failed started")),
    )
    adapters.synthetic.revert_overlay = AsyncMock(
        side_effect=AssertionError("failed replayed")
    )

    outcomes = await ActionExecutor(adapters, store).expire_overlays(utcnow())

    assert outcomes == {overlay.id: "overlay_revert_failed"}
    store.start_overlay_operation.assert_not_awaited()
    adapters.synthetic.revert_overlay.assert_not_awaited()
