from __future__ import annotations

import json
from datetime import UTC, datetime

import aiosqlite
import pytest
from pex_bridge.store import ProjectIdentityBlockedError, Store
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessSession


def _goal_and_session(project_id: str = "operator-project") -> tuple[Goal, HarnessSession]:
    now = datetime.now(UTC)
    goal = Goal(
        id="operator-goal",
        project_id=project_id,
        title="Deliver exactly once",
        objective="Send one direct operator message without replaying ambiguous I/O.",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id="synthetic:operator-worker",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="operator-worker",
        project_id=project_id,
        goal_id=goal.id,
        status=SessionStatus.WORKING,
    )
    return goal, session


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


async def _seed(store: Store, *, project_id: str = "operator-project") -> HarnessSession:
    goal, session = _goal_and_session(project_id)
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    return session


@pytest.mark.asyncio
async def test_operator_message_exact_replay_and_changed_body_conflict(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_operator_one")
    await store.connect()
    try:
        session = await _seed(store)
        first = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-message-0001",
            session_id=session.id,
            text="Continue with the verified parser.",
        )
        replay = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-message-0001",
            session_id=session.id,
            text="Continue with the verified parser.",
        )

        assert first["created"] is True
        assert replay["created"] is False
        assert replay["effect"] == first["effect"]
        with pytest.raises(ValueError, match="reused with different content"):
            await store.reserve_operator_message(
                principal_id="local_bridge_operator",
                idempotency_key="operator-message-0001",
                session_id=session.id,
                text="Send a different instruction.",
            )

        dispatch = await store.start_operator_message_dispatch(first["effect"]["effect_id"])
        assert dispatch["granted"] is True
        assert dispatch["effect"]["state"] == "dispatching"
        delivered = await store.finalize_operator_effect(
            effect_id=first["effect"]["effect_id"],
            state="delivered",
            result=_synthetic_delivery_result(session),
        )
        terminal_replay = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-message-0001",
            session_id=session.id,
            text="Continue with the verified parser.",
        )
        redispatch = await store.start_operator_message_dispatch(first["effect"]["effect_id"])

        assert delivered["state"] == "delivered"
        assert terminal_replay["effect"] == delivered
        assert redispatch["granted"] is False
        assert redispatch["reason"] == "effect_already_delivered"

        origin = ProjectOrigin(namespace="machine", host="operator-replay-host")
        await store.register_project_locator(
            legacy_project_id="operator-project",
            locator=ProjectLocator.path(
                "/work/replay-one",
                platform=PathPlatform.POSIX,
                origin=origin,
            ),
        )
        await store.register_project_locator(
            legacy_project_id="operator-project",
            locator=ProjectLocator.path(
                "/work/replay-two",
                platform=PathPlatform.POSIX,
                origin=origin,
            ),
        )
        replay_after_quarantine = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-message-0001",
            session_id=session.id,
            text="Continue with the verified parser.",
        )
        assert replay_after_quarantine["effect"] == delivered
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_actor_assured_operator_message_receipt_is_atomic_and_counted_once(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_operator_actor")
    await store.connect()
    try:
        session = await _seed(store)
        reserved = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-actor-0001",
            session_id=session.id,
            text="Continue with the authenticated correction.",
            actor_assurance="bridge_bearer",
        )
        effect_id = reserved["effect"]["effect_id"]
        assert reserved["effect"]["payload"]["schema"] == (
            "pex.operator-effect.session-message.v2"
        )
        assert reserved["effect"]["payload"]["project_binding"].startswith(
            ("legacy:", "identity:")
        )
        await store.start_operator_message_dispatch(effect_id)
        delivered = await store.finalize_operator_effect(
            effect_id=effect_id,
            state="delivered",
            result=_synthetic_delivery_result(session),
        )
        replay = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-actor-0001",
            session_id=session.id,
            text="Continue with the authenticated correction.",
            actor_assurance="bridge_bearer",
        )
        cursor = await store.db.execute(
            "SELECT json FROM human_operator_terminal_actions WHERE effect_id = ?",
            (effect_id,),
        )
        rows = await cursor.fetchall()
        assert len(rows) == 1
        receipt = json.loads(rows[0]["json"])
        assert receipt["effect_id"] == effect_id
        assert receipt["actor_assurance"] == "bridge_bearer"
        assert "text" not in receipt
        assert replay["effect"] == delivered
        reservation_cursor = await store.db.execute(
            "SELECT COUNT(*) FROM human_operator_action_reservations "
            "WHERE effect_id = ?",
            (effect_id,),
        )
        assert (await reservation_cursor.fetchone())[0] == 1

        metrics = await store.attention_metrics()
        assert metrics["human_interventions"]["source_counts"][
            "direct_operator_message"
        ] == 1
        assert metrics["human_interventions"]["observed_count"] == 1
        assert metrics["human_interventions"]["unverified_operator_action_counts"][
            "operator_message"
        ] == 0
        assert metrics["human_interventions"]["value"] is None

        with pytest.raises(aiosqlite.IntegrityError, match="immutable"):
            await store.db.execute(
                "UPDATE human_operator_terminal_actions SET result_hash = ? "
                "WHERE effect_id = ?",
                ("0" * 64, effect_id),
            )
        await store.db.rollback()
        with pytest.raises(aiosqlite.IntegrityError, match="append-only"):
            await store.db.execute(
                "DELETE FROM human_operator_terminal_actions WHERE effect_id = ?",
                (effect_id,),
            )
        await store.db.rollback()
        with pytest.raises(aiosqlite.IntegrityError, match="authority is immutable"):
            await store.db.execute(
                "UPDATE operator_effects SET payload_json = json_set(payload_json, "
                "'$.schema', 'pex.operator-effect.session-message.v1') "
                "WHERE effect_id = ?",
                (effect_id,),
            )
        await store.db.rollback()
        with pytest.raises(aiosqlite.IntegrityError, match="immutable"):
            await store.db.execute(
                "UPDATE human_operator_action_reservations SET project_binding = ? "
                "WHERE effect_id = ?",
                ("legacy:" + "0" * 64, effect_id),
            )
        await store.db.rollback()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_actor_receipt_insert_failure_rolls_back_message_terminalization(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_operator_actor_fail")
    await store.connect()
    try:
        session = await _seed(store)
        reserved = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-actor-fail-0001",
            session_id=session.id,
            text="Do not lose the terminal receipt transaction.",
            actor_assurance="bridge_bearer",
        )
        effect_id = reserved["effect"]["effect_id"]
        await store.start_operator_message_dispatch(effect_id)
        await store.db.execute(
            "CREATE TRIGGER fail_actor_receipt BEFORE INSERT ON "
            "human_operator_terminal_actions BEGIN SELECT RAISE(ABORT, "
            "'forced actor receipt failure'); END"
        )
        await store.db.commit()

        with pytest.raises(aiosqlite.IntegrityError, match="forced actor receipt failure"):
            await store.finalize_operator_effect(
                effect_id=effect_id,
                state="delivered",
                result=_synthetic_delivery_result(session),
            )
        effect = await store.get_operator_effect(effect_id)
        assert effect is not None and effect["state"] == "dispatching"
        cursor = await store.db.execute(
            "SELECT COUNT(*) FROM human_operator_terminal_actions WHERE effect_id = ?",
            (effect_id,),
        )
        assert (await cursor.fetchone())[0] == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_unassured_operator_message_remains_legacy_unverified(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_operator_unassured")
    await store.connect()
    try:
        session = await _seed(store)
        reserved = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-unassured-0001",
            session_id=session.id,
            text="An internal principal string is not actor evidence.",
        )
        effect_id = reserved["effect"]["effect_id"]
        await store.start_operator_message_dispatch(effect_id)
        await store.finalize_operator_effect(
            effect_id=effect_id,
            state="delivered",
            result=_synthetic_delivery_result(session),
        )
        metrics = await store.attention_metrics()
        assert metrics["human_interventions"]["source_counts"][
            "direct_operator_message"
        ] == 0
        assert metrics["human_interventions"]["unverified_operator_action_counts"][
            "operator_message"
        ] == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_assured_operator_message_fails_closed_when_actor_ledgers_are_corrupt(
    tmp_path,
):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_operator_actor_corrupt")
    await store.connect()
    try:
        session = await _seed(store)
        missing = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-actor-corrupt-0001",
            session_id=session.id,
            text="Require the frozen actor reservation.",
            actor_assurance="bridge_bearer",
        )
        missing_id = missing["effect"]["effect_id"]
        await store.db.execute(
            "DROP TRIGGER trg_human_operator_action_reservation_no_delete"
        )
        await store.db.execute(
            "DELETE FROM human_operator_action_reservations WHERE effect_id = ?",
            (missing_id,),
        )
        await store.db.commit()
        with pytest.raises(RuntimeError, match="missing its actor reservation"):
            await store.start_operator_message_dispatch(missing_id)
        await store.db.execute(
            "DELETE FROM operator_effects WHERE effect_id = ?",
            (missing_id,),
        )
        await store.db.commit()

        delivered = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-actor-corrupt-0002",
            session_id=session.id,
            text="Reject a corrupted terminal actor receipt.",
            actor_assurance="bridge_bearer",
        )
        delivered_id = delivered["effect"]["effect_id"]
        await store.start_operator_message_dispatch(delivered_id)
        await store.finalize_operator_effect(
            effect_id=delivered_id,
            state="delivered",
            result=_synthetic_delivery_result(session),
        )
        await store.db.execute(
            "DROP TRIGGER trg_human_operator_terminal_action_immutable"
        )
        await store.db.execute(
            "UPDATE human_operator_terminal_actions SET result_hash = ? "
            "WHERE effect_id = ?",
            ("0" * 64, delivered_id),
        )
        await store.db.commit()
        with pytest.raises(RuntimeError, match="terminal action receipt is corrupt"):
            await store.get_operator_effect(delivered_id)
        with pytest.raises(RuntimeError, match="terminal action receipt is corrupt"):
            await store.attention_metrics()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_quarantine_between_message_reservation_and_dispatch_sends_nothing(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_operator_quarantine")
    await store.connect()
    project_id = "operator-quarantine-project"
    origin = ProjectOrigin(namespace="machine", host="operator-test-host")
    try:
        session = await _seed(store, project_id=project_id)
        reserved = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-quarantine-0001",
            session_id=session.id,
            text="This must not cross the quarantine boundary.",
        )
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

        with pytest.raises(ProjectIdentityBlockedError) as caught:
            await store.start_operator_message_dispatch(reserved["effect"]["effect_id"])
        assert caught.value.code == "project_identity_quarantined"
        still_reserved = await store.get_operator_effect(reserved["effect"]["effect_id"])
        assert still_reserved is not None and still_reserved["state"] == "reserved"
        skipped = await store.finalize_operator_effect(
            effect_id=reserved["effect"]["effect_id"],
            state="skipped",
            result={"status": "skipped", "reason": caught.value.code},
        )
        assert skipped["state"] == "skipped"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_corrupt_goal_authority_cannot_grant_operator_message_dispatch(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_operator_corrupt_goal")
    await store.connect()
    try:
        session = await _seed(store)
        reserved = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-corrupt-goal-0001",
            session_id=session.id,
            text="This send must remain reserved when intent authority is corrupt.",
        )
        authority = await store.db.execute(
            "SELECT intent_revision, intent_hash FROM goals WHERE id = ?",
            (session.goal_id,),
        )
        row = await authority.fetchone()
        assert row is not None
        forged = "f" * 64 if row["intent_hash"] != "f" * 64 else "e" * 64
        await store.db.execute(
            "UPDATE goals SET intent_revision = ?, intent_hash = ? WHERE id = ?",
            (int(row["intent_revision"]) + 1, forged, session.goal_id),
        )
        await store.db.commit()

        with pytest.raises(RuntimeError, match="intent hash is corrupt"):
            await store.start_operator_message_dispatch(reserved["effect"]["effect_id"])
        effect = await store.get_operator_effect(reserved["effect"]["effect_id"])
        assert effect is not None
        assert effect["state"] == "reserved"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_operator_message_serializes_session_dispatches_without_losing_reservation(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_operator_serial")
    await store.connect()
    try:
        session = await _seed(store)
        first = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-serial-0001",
            session_id=session.id,
            text="First message.",
        )
        second = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-serial-0002",
            session_id=session.id,
            text="Second message.",
        )
        assert (await store.start_operator_message_dispatch(first["effect"]["effect_id"]))[
            "granted"
        ] is True
        blocked = await store.start_operator_message_dispatch(second["effect"]["effect_id"])
        assert blocked["granted"] is False
        assert blocked["reason"] == "session_dispatch_busy"
        assert blocked["effect"]["state"] == "reserved"

        await store.finalize_operator_effect(
            effect_id=first["effect"]["effect_id"],
            state="delivered",
            result=_synthetic_delivery_result(session),
        )
        assert (await store.start_operator_message_dispatch(second["effect"]["effect_id"]))[
            "granted"
        ] is True
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_prior_boot_dispatch_becomes_terminal_uncertain_and_never_restarts(tmp_path):
    path = tmp_path / "pex.sqlite"
    first = Store(path, process_boot_id="boot_operator_before_crash")
    await first.connect()
    session = await _seed(first)
    reserved = await first.reserve_operator_message(
        principal_id="local_bridge_operator",
        idempotency_key="operator-restart-0001",
        session_id=session.id,
        text="The transport may accept this before the process exits.",
        actor_assurance="bridge_bearer",
    )
    dispatch = await first.start_operator_message_dispatch(reserved["effect"]["effect_id"])
    assert dispatch["granted"] is True
    await first.close()

    recovery = Store(path, process_boot_id="boot_operator_after_crash")
    await recovery.connect()
    try:
        assert await recovery.recover_interrupted_operator_effects() == 1
        effect = await recovery.get_operator_effect(reserved["effect"]["effect_id"])
        assert effect is not None
        assert effect["state"] == "delivery_uncertain"
        assert effect["result"] == {
            "status": "delivery_uncertain",
            "reason": "process_restarted_after_dispatch_started",
        }
        replay = await recovery.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-restart-0001",
            session_id=session.id,
            text="The transport may accept this before the process exits.",
            actor_assurance="bridge_bearer",
        )
        assert replay["created"] is False
        assert replay["effect"]["state"] == "delivery_uncertain"
        redispatch = await recovery.start_operator_message_dispatch(effect["effect_id"])
        assert redispatch["granted"] is False
        assert redispatch["reason"] == "effect_already_delivery_uncertain"
        receipt_cursor = await recovery.db.execute(
            "SELECT COUNT(*) FROM human_operator_terminal_actions WHERE effect_id = ?",
            (effect["effect_id"],),
        )
        assert (await receipt_cursor.fetchone())[0] == 0
        metrics = await recovery.attention_metrics()
        assert metrics["human_interventions"]["source_counts"][
            "direct_operator_message"
        ] == 0
        assert metrics["human_interventions"][
            "actor_assured_operator_message_outcomes"
        ]["delivery_uncertain"] == 1
    finally:
        await recovery.close()


@pytest.mark.asyncio
async def test_second_store_connect_does_not_rewrite_a_live_dispatch(tmp_path):
    path = tmp_path / "pex.sqlite"
    owner = Store(path, process_boot_id="boot_operator_live_owner")
    await owner.connect()
    observer: Store | None = None
    try:
        session = await _seed(owner)
        reserved = await owner.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-live-owner-0001",
            session_id=session.id,
            text="Remain dispatching while another Store opens for read/write tests.",
        )
        assert (await owner.start_operator_message_dispatch(reserved["effect"]["effect_id"]))[
            "granted"
        ] is True

        observer = Store(path, process_boot_id="boot_operator_live_observer")
        await observer.connect()
        unchanged = await observer.get_operator_effect(reserved["effect"]["effect_id"])
        assert unchanged is not None and unchanged["state"] == "dispatching"
        await owner.finalize_operator_effect(
            effect_id=reserved["effect"]["effect_id"],
            state="delivered",
            result=_synthetic_delivery_result(session),
        )
    finally:
        if observer is not None:
            await observer.close()
        await owner.close()


@pytest.mark.asyncio
async def test_codex_operator_message_store_requires_exact_turn_receipt(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_operator_codex")
    await store.connect()
    try:
        goal, synthetic = _goal_and_session()
        session = synthetic.model_copy(
            update={
                "id": "codex:operator-worker",
                "harness_type": HarnessType.CODEX,
                "vendor_session_id": "thread-operator-worker",
            }
        )
        await store.upsert_goal(goal)
        await store.upsert_session(session)
        reserved = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-codex-receipt-0001",
            session_id=session.id,
            text="Continue on the exact accepted Codex turn.",
        )
        await store.start_operator_message_dispatch(reserved["effect"]["effect_id"])

        with pytest.raises(ValueError, match="requires an exact turn receipt"):
            await store.finalize_operator_effect(
                effect_id=reserved["effect"]["effect_id"],
                state="delivered",
                result={"status": "delivered"},
            )
        still_dispatching = await store.get_operator_effect(reserved["effect"]["effect_id"])
        assert still_dispatching is not None and still_dispatching["state"] == "dispatching"

        receipt = {
            "schema": "pex.worker-delivery.codex-turn.v1",
            "target_session_id": session.id,
            "vendor_session_id": session.vendor_session_id,
            "vendor_turn_id": "turn-operator-worker",
        }
        delivered = await store.finalize_operator_effect(
            effect_id=reserved["effect"]["effect_id"],
            state="delivered",
            result={"status": "delivered", "worker_delivery_receipt": receipt},
        )
        assert delivered["result"]["worker_delivery_receipt"] == receipt
        with pytest.raises(ValueError, match="does not match the target session"):
            await store.finalize_operator_effect(
                effect_id=reserved["effect"]["effect_id"],
                state="delivered",
                result={
                    "status": "delivered",
                    "worker_delivery_receipt": {
                        **receipt,
                        "vendor_session_id": "another-thread",
                    },
                },
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_synthetic_operator_message_store_requires_generic_turn_receipt(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_operator_synthetic")
    await store.connect()
    try:
        session = await _seed(store)
        reserved = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-synthetic-receipt-0001",
            session_id=session.id,
            text="Continue on the exact accepted synthetic turn.",
        )
        await store.start_operator_message_dispatch(reserved["effect"]["effect_id"])

        with pytest.raises(ValueError, match="requires an exact turn receipt"):
            await store.finalize_operator_effect(
                effect_id=reserved["effect"]["effect_id"],
                state="delivered",
                result={"status": "delivered"},
            )
        delivered = await store.finalize_operator_effect(
            effect_id=reserved["effect"]["effect_id"],
            state="delivered",
            result=_synthetic_delivery_result(session),
        )
        assert delivered["result"]["worker_delivery_receipt"]["schema"] == (
            "pex.worker-delivery.v1"
        )
        with pytest.raises(ValueError, match="does not match the target session"):
            await store.finalize_operator_effect(
                effect_id=reserved["effect"]["effect_id"],
                state="delivered",
                result={
                    "status": "delivered",
                    "worker_delivery_receipt": {
                        **delivered["result"]["worker_delivery_receipt"],
                        "schema": "pex.worker-delivery.codex-turn.v1",
                    },
                },
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_codex_operator_terminal_receipt_is_read_validated_and_not_downgradable(
    tmp_path,
):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_operator_codex_read")
    await store.connect()
    try:
        goal, synthetic = _goal_and_session()
        session = synthetic.model_copy(
            update={
                "id": "codex:operator-read-worker",
                "harness_type": HarnessType.CODEX,
                "vendor_session_id": "thread-operator-read-worker",
            }
        )
        await store.upsert_goal(goal)
        await store.upsert_session(session)
        reserved = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-codex-read-0001",
            session_id=session.id,
            text="Persist one exact receipt.",
        )
        effect_id = reserved["effect"]["effect_id"]
        await store.start_operator_message_dispatch(effect_id)
        receipt = {
            "schema": "pex.worker-delivery.codex-turn.v1",
            "target_session_id": session.id,
            "vendor_session_id": session.vendor_session_id,
            "vendor_turn_id": "turn-operator-read-worker",
        }
        await store.finalize_operator_effect(
            effect_id=effect_id,
            state="delivered",
            result={"status": "delivered", "worker_delivery_receipt": receipt},
        )
        with pytest.raises(aiosqlite.IntegrityError, match="contract is immutable"):
            await store.db.execute(
                "UPDATE operator_effects SET delivery_contract_version = 1 "
                "WHERE effect_id = ?",
                (effect_id,),
            )
        await store.db.rollback()
        await store.db.execute(
            "UPDATE operator_effects SET result_json = ? WHERE effect_id = ?",
            (json.dumps({"status": "delivered"}), effect_id),
        )
        await store.db.commit()

        with pytest.raises(RuntimeError, match="delivery receipt"):
            await store.get_operator_effect(effect_id)
        with pytest.raises(RuntimeError, match="delivery receipt"):
            await store.reserve_operator_message(
                principal_id="local_bridge_operator",
                idempotency_key="operator-codex-read-0001",
                session_id=session.id,
                text="Persist one exact receipt.",
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_codex_operator_finalize_and_replay_use_frozen_vendor_binding(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot_operator_frozen")
    await store.connect()
    try:
        goal, synthetic = _goal_and_session()
        session = synthetic.model_copy(
            update={
                "id": "codex:operator-frozen-worker",
                "harness_type": HarnessType.CODEX,
                "vendor_session_id": "thread-operator-frozen-worker",
            }
        )
        await store.upsert_goal(goal)
        await store.upsert_session(session)
        reserved = await store.reserve_operator_message(
            principal_id="local_bridge_operator",
            idempotency_key="operator-codex-frozen-0001",
            session_id=session.id,
            text="Finalize against the dispatch target.",
        )
        effect_id = reserved["effect"]["effect_id"]
        await store.start_operator_message_dispatch(effect_id)
        rebound = session.model_copy(update={"vendor_session_id": "thread-after-dispatch"})
        await store.db.execute(
            "UPDATE sessions SET vendor_session_id = ?, json = ? WHERE id = ?",
            (rebound.vendor_session_id, rebound.model_dump_json(), rebound.id),
        )
        await store.db.commit()
        receipt = {
            "schema": "pex.worker-delivery.codex-turn.v1",
            "target_session_id": session.id,
            "vendor_session_id": session.vendor_session_id,
            "vendor_turn_id": "turn-operator-frozen-worker",
        }
        result = {"status": "delivered", "worker_delivery_receipt": receipt}

        delivered = await store.finalize_operator_effect(
            effect_id=effect_id,
            state="delivered",
            result=result,
        )
        replay = await store.finalize_operator_effect(
            effect_id=effect_id,
            state="delivered",
            result=result,
        )

        assert delivered["result"] == result
        assert replay == delivered
    finally:
        await store.close()
