from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta

import aiosqlite
import pex_bridge.store as store_module
import pytest
from pex_bridge.store import Store, utcnow
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessSession


async def _seed_ask_human(store: Store, *, intervention_id: str) -> Intervention:
    now = utcnow()
    project_id = "attention-project"
    goal_id = "goal-attention"
    session_id = "synthetic:attention"
    await store.register_project_locator(
        legacy_project_id=project_id,
        locator=ProjectLocator.path(
            "/work/attention-project",
            platform=PathPlatform.POSIX,
            origin=ProjectOrigin(namespace="machine", host="attention-test"),
        ),
        now=now,
    )
    await store.upsert_goal(
        Goal(
            id=goal_id,
            project_id=project_id,
            title="Attention metrics",
            objective="Keep attention claims backed by exact durable evidence.",
            created_at=now,
            updated_at=now,
        )
    )
    await store.upsert_session(
        HarnessSession(
            id=session_id,
            harness_type=HarnessType.SYNTHETIC,
            vendor_session_id="attention",
            project_id=project_id,
            cwd=project_id,
            goal_id=goal_id,
            status=SessionStatus.NEEDS_DECISION,
        )
    )
    action = ProposedAction(
        type=InterventionType.ASK_HUMAN,
        session_id=session_id,
        goal_id=goal_id,
        rationale="The evidence requires a human judgment.",
        evidence=["event:attention"],
        confidence=0.8,
        risk=RiskLevel.LOW,
        authority_required=Authority.HUMAN,
    )
    intervention = Intervention(
        id=intervention_id,
        session_id=session_id,
        goal_id=goal_id,
        trigger="decision",
        evidence=action.evidence,
        diagnosis="human judgment required",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ASK_HUMAN,
        result="awaiting_human",
        created_at=now,
    )
    await store.add_intervention(intervention)
    return intervention


def _attention_goal(goal_id: str, *, objective: str, supersedes: str | None = None) -> Goal:
    now = utcnow()
    return Goal(
        id=goal_id,
        project_id="attention-project",
        title="Goal-control attention",
        objective=objective,
        created_at=now,
        updated_at=now,
        supersedes=supersedes,
    )


def _goal_operation_authority(key: str, request: dict) -> dict:
    return {
        "principal_id": "local_bridge_operator",
        "actor_assurance": "bridge_bearer",
        "idempotency_key": key,
        "request_payload": request,
    }


@pytest.mark.asyncio
async def test_attention_metrics_empty_snapshot_preserves_unmeasured_nulls(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        metrics = await store.attention_metrics()
    finally:
        await store.close()

    assert metrics["schema"] == "pex.attention-metrics.v1"
    assert metrics["window"]["aggregate_truncated"] is False
    assert metrics["window"]["records_considered"] == 0
    assert [
        row["action_kind"]
        for row in metrics["coverage"]["actor_assured_action_coverage"]
    ] == [
        "context_handoff",
        "goal_override",
        "goal_update",
        "pause_supervision",
        "resume_supervision",
        "session_goal_attach",
        "session_message",
    ]
    assert metrics["human_interventions"] == {
        "value": None,
        "measured": False,
        "observed_count": 0,
        "coverage_complete": False,
        "source_counts": {
            "human_decision_delivery": 0,
            "permission_delivery": 0,
            "lifecycle_delivery": 0,
            "overlay_reversal": 0,
            "cleanup_restore": 0,
            "project_identity_resolution": 0,
            "supervision_control": 0,
            "direct_operator_message": 0,
            "operator_context_handoff": 0,
            "goal_control_attention": 0,
        },
        "unverified_operator_action_counts": {
            "operator_message": 0,
            "operator_handoff": 0,
        },
        "unverified_goal_control_action_counts": {
            "precoverage_changed_operations": 0,
        },
        "actor_assured_operator_message_outcomes": {
            "delivered": 0,
            "failed": 0,
            "skipped": 0,
            "delivery_uncertain": 0,
        },
        "actor_assured_operator_handoff_outcomes": {
            "delivered": 0,
            "failed": 0,
            "skipped": 0,
            "delivery_uncertain": 0,
        },
        "null_reason": "not_all_human_action_routes_have_durable_receipts",
        "unmeasured_action_kinds": [
            "manual_context_copy_outside_pex",
            "manual_verification_outside_pex",
        ],
    }
    assert metrics["decisions"]["requested"] == 0
    assert metrics["decisions"]["resolved"] == 0
    assert metrics["decisions"]["pending"] == 0
    assert metrics["current_pending"]["count"] == 0
    assert metrics["current_pending"]["items_truncated"] is False
    assert metrics["human_active_seconds"]["value"] is None
    assert metrics["human_active_seconds"]["consent"] == "not_configured"
    assert metrics["unnecessary_alert_rate"]["value"] is None
    assert metrics["unnecessary_alert_rate"]["denominator"] == 0
    assert metrics["average_auto_resolution_confidence"]["value"] is None
    assert metrics["reversals"]["completed"] == 0
    assert metrics["benchmark_evidence"] is False


@pytest.mark.asyncio
async def test_goal_control_attention_counts_only_mutation_time_execution_effects(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _seed_ask_human(store, intervention_id="attention-goal-control-source")
        attached = await store.get_goal_for_authority("goal-attention")
        assert attached is not None
        attached_update = attached.model_copy(
            update={
                "objective": "A changed objective for the attached live worker.",
                "updated_at": utcnow(),
            }
        )
        changed = await store.patch_goal_with_ledger_receipt(
            attached,
            attached_update,
            [],
            expected_intent_revision=1,
            **_goal_operation_authority(
                "attention-attached-update-0001",
                {"goal_id": attached.id, "objective": attached_update.objective},
            ),
        )
        assert changed.changed is True

        unattached = _attention_goal(
            "goal-attention-unattached",
            objective="An unattached setup goal.",
        )
        await store.create_goal_with_ledger(unattached, [])
        unattached_update = unattached.model_copy(
            update={"objective": "An unattached edit.", "updated_at": utcnow()}
        )
        excluded = await store.patch_goal_with_ledger_receipt(
            unattached,
            unattached_update,
            [],
            expected_intent_revision=1,
            **_goal_operation_authority(
                "attention-unattached-update-0001",
                {"goal_id": unattached.id, "objective": unattached_update.objective},
            ),
        )
        assert excluded.changed is True
        noop = await store.patch_goal_with_ledger_receipt(
            unattached_update,
            unattached_update.model_copy(update={"updated_at": utcnow()}),
            [],
            expected_intent_revision=2,
            **_goal_operation_authority(
                "attention-unattached-noop-0001",
                {"goal_id": unattached.id, "objective": unattached_update.objective},
            ),
        )
        assert noop.changed is False

        metrics = await store.attention_metrics()
        assert metrics["human_interventions"]["source_counts"][
            "goal_control_attention"
        ] == 1
        assert metrics["human_interventions"]["observed_count"] == 1
        assert metrics["human_interventions"]["value"] is None
        assert "goal_mutation" not in metrics["coverage"]["unmeasured_action_kinds"]
        cursor = await store.db.execute(
            "SELECT action_kind, eligible, eligibility_reason, live_session_count "
            "FROM goal_control_attention_receipts ORDER BY rowid"
        )
        assert [tuple(row) for row in await cursor.fetchall()] == [
            ("goal_update", 1, "attached_live_goal_update", 1),
            ("goal_update", 0, "unattached_goal_update", 0),
            ("goal_update", 0, "semantic_noop", 0),
        ]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_changed_goal_attachment_counts_once_and_replay_does_not_multiply(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _seed_ask_human(store, intervention_id="attention-attach-source")
        goal = _attention_goal("goal-attention-attach", objective="Attach this goal.")
        await store.create_goal_with_ledger(goal, [])
        session = HarnessSession(
            id="synthetic:attention-attach",
            harness_type=HarnessType.SYNTHETIC,
            vendor_session_id="attention-attach",
            project_id="attention-project",
            status=SessionStatus.WORKING,
        )
        await store.upsert_session(session)
        request = {"session_id": session.id, "goal_id": goal.id}
        first = await store.attach_session_goal(
            session.id,
            goal.id,
            expected_goal_id=None,
            expected_control_revision=0,
            expected_goal_intent_revision=1,
            **_goal_operation_authority("attention-goal-attach-0001", request),
        )
        replay = await store.attach_session_goal(
            session.id,
            goal.id,
            expected_goal_id=None,
            expected_control_revision=0,
            expected_goal_intent_revision=1,
            **_goal_operation_authority("attention-goal-attach-0001", request),
        )
        assert first["changed"] is True
        assert replay["replayed"] is True

        metrics = await store.attention_metrics()
        assert metrics["human_interventions"]["source_counts"][
            "goal_control_attention"
        ] == 1
        cursor = await store.db.execute(
            "SELECT COUNT(*) FROM goal_control_attention_receipts"
        )
        assert int((await cursor.fetchone())[0]) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_changed_attachment_to_paused_session_is_not_attention_eligible(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _seed_ask_human(store, intervention_id="attention-paused-attach-source")
        goal = _attention_goal("goal-attention-paused-attach", objective="Attach while paused.")
        await store.create_goal_with_ledger(goal, [])
        session = HarnessSession(
            id="synthetic:attention-paused-attach",
            harness_type=HarnessType.SYNTHETIC,
            vendor_session_id="attention-paused-attach",
            project_id="attention-project",
            status=SessionStatus.WORKING,
            supervision_paused=True,
        )
        await store.upsert_session(session)
        result = await store.attach_session_goal(
            session.id,
            goal.id,
            expected_goal_id=None,
            expected_control_revision=0,
            expected_goal_intent_revision=1,
            **_goal_operation_authority(
                "attention-paused-goal-attach-0001",
                {"session_id": session.id, "goal_id": goal.id},
            ),
        )
        assert result["changed"] is True

        metrics = await store.attention_metrics()
        assert metrics["human_interventions"]["source_counts"][
            "goal_control_attention"
        ] == 0
        cursor = await store.db.execute(
            "SELECT eligible, eligibility_reason FROM goal_control_attention_receipts"
        )
        assert tuple(await cursor.fetchone()) == (
            0,
            "changed_nonlive_session_goal_attach",
        )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_goal_override_with_multiple_live_sessions_counts_once(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _seed_ask_human(store, intervention_id="attention-override-source")
        await store.upsert_session(
            HarnessSession(
                id="synthetic:attention-second",
                harness_type=HarnessType.SYNTHETIC,
                vendor_session_id="attention-second",
                project_id="attention-project",
                goal_id="goal-attention",
                status=SessionStatus.WORKING,
            )
        )
        current = await store.get_goal_for_authority("goal-attention")
        assert current is not None
        replacement = current.model_copy(
            update={
                "id": "goal-attention-successor",
                "objective": "Supersede one intent across both live workers.",
                "supersedes": current.id,
                "created_at": utcnow(),
                "updated_at": utcnow(),
            }
        )
        receipt = await store.supersede_goal_with_ledger_receipt(
            current,
            replacement,
            [],
            expected_intent_revision=1,
            **_goal_operation_authority(
                "attention-goal-override-0001",
                {"goal_id": current.id, "objective": replacement.objective},
            ),
        )

        assert set(receipt.reattached_session_ids) == {
            "synthetic:attention",
            "synthetic:attention-second",
        }
        metrics = await store.attention_metrics()
        assert metrics["human_interventions"]["source_counts"][
            "goal_control_attention"
        ] == 1
        cursor = await store.db.execute(
            "SELECT eligible, eligibility_reason, live_session_count "
            "FROM goal_control_attention_receipts"
        )
        row = await cursor.fetchone()
        assert tuple(row) == (1, "attached_live_goal_override", 2)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_goal_control_attention_migration_does_not_backfill_prior_operations(tmp_path):
    database = tmp_path / "pex.sqlite"
    store = Store(database)
    await store.connect()
    try:
        await _seed_ask_human(store, intervention_id="attention-precoverage-source")
        current = await store.get_goal_for_authority("goal-attention")
        assert current is not None
        updated = current.model_copy(
            update={"objective": "A pre-coverage mutation.", "updated_at": utcnow()}
        )
        await store.patch_goal_with_ledger_receipt(
            current,
            updated,
            [],
            expected_intent_revision=1,
            **_goal_operation_authority(
                "attention-precoverage-update-0001",
                {"goal_id": current.id, "objective": updated.objective},
            ),
        )
        for trigger in (
            "trg_goal_control_attention_receipt_no_delete",
            "trg_goal_control_attention_coverage_no_delete",
            "trg_goal_control_attention_migration_no_delete",
        ):
            await store.db.execute(f"DROP TRIGGER {trigger}")
        await store.db.execute("DELETE FROM goal_control_attention_receipts")
        await store.db.execute("DELETE FROM goal_control_attention_coverage")
        await store.db.execute("DELETE FROM goal_control_attention_migration_state")
        await store.db.commit()
    finally:
        await store.close()

    reopened = Store(database)
    await reopened.connect()
    try:
        metrics = await reopened.attention_metrics()
        assert metrics["human_interventions"]["source_counts"][
            "goal_control_attention"
        ] == 0
        assert metrics["human_interventions"]["unverified_goal_control_action_counts"] == {
            "precoverage_changed_operations": 1,
        }
        marker_cursor = await reopened.db.execute(
            "SELECT legacy_operation_count FROM goal_control_attention_migration_state"
        )
        assert int((await marker_cursor.fetchone())[0]) == 1
        legacy_cursor = await reopened.db.execute(
            "SELECT operation_id FROM goal_control_attention_legacy_operations"
        )
        assert (await legacy_cursor.fetchone())[0] is not None
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_goal_control_attention_receipt_failure_rolls_back_mutation(
    tmp_path,
    monkeypatch,
):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _seed_ask_human(store, intervention_id="attention-receipt-rollback")
        current = await store.get_goal_for_authority("goal-attention")
        assert current is not None
        updated = current.model_copy(
            update={"objective": "This mutation must roll back.", "updated_at": utcnow()}
        )

        async def reject_receipt(*_args, **_kwargs):
            raise RuntimeError("forced attention receipt failure")

        monkeypatch.setattr(
            store_module,
            "_insert_goal_control_attention_receipt",
            reject_receipt,
        )
        with pytest.raises(RuntimeError, match="forced attention receipt failure"):
            await store.patch_goal_with_ledger_receipt(
                current,
                updated,
                [],
                expected_intent_revision=1,
                **_goal_operation_authority(
                    "attention-receipt-rollback-0001",
                    {"goal_id": current.id, "objective": updated.objective},
                ),
            )

        assert await store.get_goal_for_authority(current.id) == current
        operation_cursor = await store.db.execute(
            "SELECT COUNT(*) FROM goal_control_operations"
        )
        receipt_cursor = await store.db.execute(
            "SELECT COUNT(*) FROM goal_control_attention_receipts"
        )
        assert int((await operation_cursor.fetchone())[0]) == 0
        assert int((await receipt_cursor.fetchone())[0]) == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_attention_metrics_fail_closed_when_prospective_receipt_is_missing(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _seed_ask_human(store, intervention_id="attention-missing-receipt")
        current = await store.get_goal_for_authority("goal-attention")
        assert current is not None
        updated = current.model_copy(
            update={"objective": "Create a qualifying receipt.", "updated_at": utcnow()}
        )
        await store.patch_goal_with_ledger_receipt(
            current,
            updated,
            [],
            expected_intent_revision=1,
            **_goal_operation_authority(
                "attention-missing-receipt-0001",
                {"goal_id": current.id, "objective": updated.objective},
            ),
        )
        await store.db.execute("DROP TRIGGER trg_goal_control_attention_receipt_no_delete")
        await store.db.execute("DELETE FROM goal_control_attention_receipts")
        await store.db.commit()

        with pytest.raises(RuntimeError, match="goal control attention receipt is missing"):
            await store.attention_metrics()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_attention_metrics_count_only_assured_changed_supervision_actions(tmp_path):
    database = tmp_path / "pex.sqlite"
    store = Store(database)
    await store.connect()
    try:
        await _seed_ask_human(store, intervention_id="attention-pause-source")
        control = await store.get_session_control_state("synthetic:attention")
        assert control is not None
        paused = await store.set_session_supervision_paused(
            "synthetic:attention",
            paused=True,
            expected_control_revision=control["control_revision"],
            principal_id="local_bridge_operator",
            actor_assurance="bridge_bearer",
        )
        replay = await store.set_session_supervision_paused(
            "synthetic:attention",
            paused=True,
            expected_control_revision=control["control_revision"],
            principal_id="local_bridge_operator",
            actor_assurance="bridge_bearer",
        )
        assert replay["changed"] is False

        metrics = await store.attention_metrics()
        assert metrics["human_interventions"]["source_counts"][
            "supervision_control"
        ] == 1
        assert metrics["human_interventions"]["observed_count"] == 1
        assert "pause_resume" not in metrics["coverage"]["unmeasured_action_kinds"]
        assert "pause_resume" not in metrics["human_interventions"][
            "unmeasured_action_kinds"
        ]
        assert metrics["authority"]["watermarks"][
            "human_session_control_actions"
        ] == 1
        assert metrics["authority"]["watermarks"][
            "human_session_control_coverage"
        ] == 2
        assert paused["human_action_receipt"]["project_binding"] is not None
        assert paused["human_action_receipt"]["before_supervision_paused"] is False
        assert paused["human_action_receipt"]["after_supervision_paused"] is True
    finally:
        await store.close()

    reopened = Store(database)
    await reopened.connect()
    try:
        recovered = await reopened.attention_metrics()
        assert recovered["human_interventions"]["source_counts"][
            "supervision_control"
        ] == 1
        assert recovered["authority"]["watermarks"] == metrics["authority"][
            "watermarks"
        ]
        assert recovered["coverage"]["actor_assured_action_coverage"] == metrics[
            "coverage"
        ]["actor_assured_action_coverage"]
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_attention_metrics_coverage_survives_wall_clock_rollback(
    tmp_path,
    monkeypatch,
):
    """The schema boundary, not wall-clock ordering, makes new receipts prospective."""

    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _seed_ask_human(store, intervention_id="attention-clock-rollback")
        initial = await store.attention_metrics()
        coverage_started_at = initial["coverage"]["actor_assured_action_coverage"][0][
            "coverage_started_at"
        ]
        rewound = datetime.fromisoformat(coverage_started_at) - timedelta(days=1)
        monkeypatch.setattr(store_module, "utcnow", lambda: rewound)

        control = await store.get_session_control_state("synthetic:attention")
        assert control is not None
        paused = await store.set_session_supervision_paused(
            "synthetic:attention",
            paused=True,
            expected_control_revision=control["control_revision"],
            principal_id="local_bridge_operator",
            actor_assurance="bridge_bearer",
        )
        assert datetime.fromisoformat(
            paused["human_action_receipt"]["occurred_at"]
        ) < datetime.fromisoformat(coverage_started_at)

        metrics = await store.attention_metrics()
        assert metrics["human_interventions"]["source_counts"][
            "supervision_control"
        ] == 1
        assert metrics["human_interventions"]["observed_count"] == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_attention_metrics_fail_closed_on_malformed_human_action_receipt(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _seed_ask_human(store, intervention_id="attention-corrupt-action")
        control = await store.get_session_control_state("synthetic:attention")
        assert control is not None
        paused = await store.set_session_supervision_paused(
            "synthetic:attention",
            paused=True,
            expected_control_revision=control["control_revision"],
            principal_id="local_bridge_operator",
            actor_assurance="bridge_bearer",
        )
        receipt = paused["human_action_receipt"]
        await store.db.execute(
            "INSERT INTO human_session_control_actions(id, action_kind, principal_id, "
            "actor_assurance, session_id, goal_id, project_id, project_binding, "
            "before_control_revision, after_control_revision, occurred_at, json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "human_action_malformed",
                "resume_supervision",
                "local_bridge_operator",
                "bridge_bearer",
                receipt["session_id"],
                receipt["goal_id"],
                receipt["project_id"],
                receipt["project_binding"],
                98,
                99,
                receipt["occurred_at"],
                "{}",
            ),
        )
        await store.db.commit()

        with pytest.raises(RuntimeError, match="human action receipt is corrupt"):
            await store.attention_metrics()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_attention_metrics_reject_self_consistent_future_control_receipt(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _seed_ask_human(store, intervention_id="attention-forged-action")
        control = await store.get_session_control_state("synthetic:attention")
        assert control is not None
        paused = await store.set_session_supervision_paused(
            "synthetic:attention",
            paused=True,
            expected_control_revision=control["control_revision"],
            principal_id="local_bridge_operator",
            actor_assurance="bridge_bearer",
        )
        source = paused["human_action_receipt"]
        forged_key = store_module._canonical_json(
            {
                "action_kind": "resume_supervision",
                "after_control_revision": 101,
                "principal_id": "local_bridge_operator",
                "session_id": source["session_id"],
            }
        )
        forged_id = (
            "human_action_"
            + hashlib.sha256(forged_key.encode("utf-8")).hexdigest()[:40]
        )
        forged = {
            **source,
            "id": forged_id,
            "action_kind": "resume_supervision",
            "before_control_revision": 100,
            "after_control_revision": 101,
            "before_supervision_paused": True,
            "after_supervision_paused": False,
            "before_session_sha256": "1" * 64,
            "after_session_sha256": "2" * 64,
        }
        await store.db.execute(
            "INSERT INTO human_session_control_actions(id, action_kind, principal_id, "
            "actor_assurance, session_id, goal_id, project_id, project_binding, "
            "before_control_revision, after_control_revision, occurred_at, json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                forged_id,
                forged["action_kind"],
                forged["principal_id"],
                forged["actor_assurance"],
                forged["session_id"],
                forged["goal_id"],
                forged["project_id"],
                forged["project_binding"],
                forged["before_control_revision"],
                forged["after_control_revision"],
                forged["occurred_at"],
                store_module._canonical_json(forged),
            ),
        )
        await store.db.commit()

        with pytest.raises(RuntimeError, match="human action receipt is corrupt"):
            await store.attention_metrics()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_attention_metrics_exclude_valid_unbound_containment_pause(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        session = HarnessSession(
            id="synthetic:unbound-attention",
            harness_type=HarnessType.SYNTHETIC,
            vendor_session_id="unbound-attention",
            project_id="unbound-attention-project",
            cwd="unbound-attention-project",
            status=SessionStatus.WORKING,
        )
        await store.upsert_session(session)
        await store.db.execute(
            "UPDATE sessions SET project_binding = NULL WHERE id = ?",
            (session.id,),
        )
        await store.db.commit()
        control = await store.get_session_control_state(session.id)
        assert control is not None
        assert control["project_binding"] is None
        paused = await store.set_session_supervision_paused(
            session.id,
            paused=True,
            expected_control_revision=control["control_revision"],
            principal_id="local_bridge_operator",
            actor_assurance="bridge_bearer",
        )
        assert paused["human_action_receipt"]["project_binding"] is None

        metrics = await store.attention_metrics()
        assert metrics["human_interventions"]["source_counts"][
            "supervision_control"
        ] == 0
        assert metrics["coverage"]["excluded_legacy_or_unbound_source_rows"] >= 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_attention_metrics_ignore_detail_page_limits_and_survive_restart(tmp_path):
    database = tmp_path / "pex.sqlite"
    resolved_at = utcnow().isoformat()
    legacy_resolution = {
        "intervention_id": "attention-000",
        "session_id": "synthetic:attention",
        "goal_id": "goal-attention",
        "choice": "continue",
        "status": "delivered",
        "source": "human",
        "project_binding": "identity:legacy-attention-metric",
        "decision_id": "decision-attention",
        "context_id": "context-attention",
        "resolved_at": resolved_at,
    }
    legacy = await aiosqlite.connect(database)
    try:
        await legacy.execute(
            "CREATE TABLE human_decision_resolutions ("
            "intervention_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
            "goal_id TEXT NOT NULL, choice TEXT NOT NULL, "
            "decision_id TEXT NOT NULL UNIQUE, context_id TEXT NOT NULL UNIQUE, "
            "resolved_at TEXT NOT NULL, json TEXT NOT NULL)"
        )
        await legacy.execute(
            "INSERT INTO human_decision_resolutions("
            "intervention_id, session_id, goal_id, choice, decision_id, context_id, "
            "resolved_at, json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                legacy_resolution["intervention_id"],
                legacy_resolution["session_id"],
                legacy_resolution["goal_id"],
                legacy_resolution["choice"],
                legacy_resolution["decision_id"],
                legacy_resolution["context_id"],
                resolved_at,
                json.dumps(legacy_resolution, separators=(",", ":")),
            ),
        )
        await legacy.commit()
    finally:
        await legacy.close()
    store = Store(database)
    await store.connect()
    try:
        first = await _seed_ask_human(store, intervention_id="attention-000")
        cursor = await store.db.execute(
            "SELECT * FROM interventions WHERE id = ?",
            (first.id,),
        )
        template = await cursor.fetchone()
        assert template is not None
        envelope = json.loads(template["json"])
        rows = []
        for index in range(1, 205):
            intervention_id = f"attention-{index:03d}"
            cloned = copy.deepcopy(envelope)
            cloned["payload"]["id"] = intervention_id
            rows.append(
                (
                    intervention_id,
                    template["session_id"],
                    template["goal_id"],
                    template["project_id"],
                    template["project_binding"],
                    template["vendor_session_id"],
                    template["harness_type"],
                    template["action_hash"],
                    template["version"],
                    template["ts"],
                    json.dumps(cloned, separators=(",", ":")),
                )
            )
        await store.db.executemany(
            "INSERT INTO interventions(id, session_id, goal_id, project_id, "
            "project_binding, vendor_session_id, harness_type, action_hash, version, ts, json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        await store.db.commit()

        assert len(await store.list_interventions(limit=40)) == 40
        assert len(await store.list_interventions(limit=200)) == 200
        metrics = await store.attention_metrics()
        assert metrics["window"]["records_considered"] == 205
        assert metrics["human_intervention_requests"]["value"] == 205
        assert metrics["decisions"]["requested"] == 205
        assert metrics["decisions"]["resolved"] == 1
        assert metrics["decisions"]["pending"] == 204
        assert metrics["current_pending"]["count"] == 204
        assert len(metrics["current_pending"]["items"]) == 200
        assert metrics["current_pending"]["items_truncated"] is True
        assert metrics["current_pending"]["unexplained_session_count"] == 0
        assert metrics["human_interventions"]["value"] is None
        assert metrics["human_interventions"]["observed_count"] == 1
        assert metrics["window"]["aggregate_truncated"] is False
    finally:
        await store.close()

    reopened = Store(database)
    await reopened.connect()
    try:
        recovered = await reopened.attention_metrics()
    finally:
        await reopened.close()

    assert recovered["window"]["records_considered"] == 205
    assert recovered["human_intervention_requests"]["value"] == 205
    assert recovered["decisions"]["resolved"] == 1
    assert recovered["decisions"]["pending"] == 204
    assert recovered["current_pending"]["count"] == 204
    assert recovered["human_interventions"]["observed_count"] == 1
    assert recovered["authority"]["watermarks"] == metrics["authority"]["watermarks"]


@pytest.mark.asyncio
async def test_attention_metrics_keep_history_but_exclude_rebound_pending_authority(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _seed_ask_human(store, intervention_id="attention-rebound")
        before = await store.attention_metrics()
        assert before["human_intervention_requests"]["value"] == 1
        assert before["current_pending"]["count"] == 1

        conflict = await store.register_project_locator(
            legacy_project_id="attention-project",
            locator=ProjectLocator.path(
                "/work/attention-project-rebound",
                platform=PathPlatform.POSIX,
                origin=ProjectOrigin(namespace="machine", host="attention-test"),
            ),
        )
        assert conflict["outcome"] == "quarantined"
        quarantined = await store.attention_metrics()
        assert quarantined["human_intervention_requests"]["value"] == 1
        assert quarantined["decisions"]["pending"] == 1
        assert quarantined["current_pending"]["count"] == 0

        await store.resolve_project_identity_conflict(
            resolution_id="attention-resolve-rebound",
            legacy_project_id="attention-project",
            selected_identity_id=conflict["identity"].id,
            resolved_by="local_bridge_operator",
            rationale="Select the intentionally different current checkout.",
        )
        rebound = await store.attention_metrics()
        assert rebound["human_intervention_requests"]["value"] == 1
        assert rebound["current_pending"]["count"] == 0
        assert rebound["human_interventions"]["observed_count"] == 1
        assert rebound["human_interventions"]["source_counts"][
            "project_identity_resolution"
        ] == 1
    finally:
        await store.close()
