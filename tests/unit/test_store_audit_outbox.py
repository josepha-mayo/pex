from __future__ import annotations

import json

import pytest
from pex_bridge.store import Store, utcnow
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, HarnessType, PolicyVerdict
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessSession
from pydantic import ValidationError


def _intervention(intervention_id: str = "int_audit") -> Intervention:
    action = ProposedAction(
        type=InterventionType.NOOP,
        session_id="codex:audit",
        goal_id="goal-audit",
        rationale="The observed event does not justify interrupting the worker.",
        evidence=["event:audit"],
        confidence=0.9,
        risk=RiskLevel.NONE,
        authority_required=Authority.LOCAL_POLICY,
    )
    return Intervention(
        id=intervention_id,
        session_id=action.session_id,
        goal_id=action.goal_id,
        trigger="status",
        evidence=action.evidence,
        diagnosis="no_intervention_needed",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        authority_required=action.authority_required.value,
        action_taken=InterventionType.NOOP.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="noop",
        created_at=utcnow(),
    )


async def _bind_audit_session(store: Store) -> None:
    now = utcnow()
    goal = Goal(
        id="goal-audit",
        project_id="audit-project",
        title="Audit durability",
        objective="Keep intervention audit records durable and replayable.",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id="codex:audit",
        harness_type=HarnessType.CODEX,
        vendor_session_id="audit",
        project_id=goal.project_id,
        goal_id=goal.id,
        last_activity=now,
    )
    await store.upsert_goal(goal)
    await store.upsert_session(session)


def test_intervention_rejects_a_conflicting_action_snapshot() -> None:
    action = ProposedAction(
        type=InterventionType.NOOP,
        session_id="codex:audit",
        rationale="No intervention is justified.",
        evidence=["event:audit"],
    )
    with pytest.raises(ValidationError, match="evidence mismatch"):
        Intervention(
            id="int_conflicting_snapshot",
            session_id=action.session_id,
            trigger="status",
            evidence=[],
            diagnosis="no_intervention_needed",
            proposed_action=action,
            risk=action.risk.value,
            authority_required=action.authority_required.value,
            action_taken=action.type.value,
            policy_verdict=PolicyVerdict.ALLOW,
            created_at=utcnow(),
        )


@pytest.mark.asyncio
async def test_store_connections_use_full_sqlite_synchronization(tmp_path) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        cursor = await store.db.execute("PRAGMA synchronous")
        assert (await cursor.fetchone())[0] == 2
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_failed_jsonl_projection_remains_durable_and_is_repaired(tmp_path, monkeypatch):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    await _bind_audit_session(store)
    original = store._append_missing_audit_rows

    def fail_projection(rows):
        del rows
        raise OSError("simulated projection failure")

    monkeypatch.setattr(store, "_append_missing_audit_rows", fail_projection)
    await store.add_intervention(_intervention())

    cursor = await store.db.execute("SELECT id, record_type FROM intervention_audit")
    durable = await cursor.fetchall()
    assert [(row["id"], row["record_type"]) for row in durable] == [(1, "created")]
    assert not store.audit_path.exists()

    monkeypatch.setattr(store, "_append_missing_audit_rows", original)
    await store.close()

    records = [
        json.loads(line)
        for line in store.audit_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [(row["audit_id"], row["record_type"]) for row in records] == [
        (1, "created")
    ]


@pytest.mark.asyncio
async def test_audit_projection_replay_is_idempotent_across_restart(tmp_path):
    path = tmp_path / "pex.sqlite"
    store = Store(path)
    await store.connect()
    await _bind_audit_session(store)
    intervention = _intervention()
    await store.add_intervention(intervention)

    # Simulate losing only the in-memory receipt after the line was durably appended.
    store._projected_audit_ids = None
    await store._sync_intervention_audit()
    await store.close()

    reopened = Store(path)
    await reopened.connect()
    intervention.outcome = "later_observation"
    await reopened.update_intervention(intervention)
    await reopened.close()

    records = [
        json.loads(line)
        for line in reopened.audit_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [(row["audit_id"], row["record_type"]) for row in records] == [
        (1, "created"),
        (2, "outcome_observed"),
    ]


@pytest.mark.asyncio
async def test_intervention_listing_has_stable_bounded_pagination(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    await _bind_audit_session(store)
    try:
        for index in range(5):
            await store.add_intervention(_intervention(f"int_{index}"))

        first = await store.list_interventions(limit=2)
        second = await store.list_interventions(limit=2, offset=2)
        assert [item.id for item in first] == ["int_4", "int_3"]
        assert [item.id for item in second] == ["int_2", "int_1"]
        with pytest.raises(ValueError, match="positive"):
            await store.list_interventions(limit=0)
        with pytest.raises(ValueError, match="negative"):
            await store.list_interventions(offset=-1)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_intervention_ids_cannot_overwrite_or_create_through_update(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    await _bind_audit_session(store)
    original = _intervention("int_immutable")
    try:
        await store.add_intervention(original)
        conflicting = original.model_copy(deep=True)
        conflicting.diagnosis = "different content"
        with pytest.raises(ValueError, match="already exists"):
            await store.add_intervention(conflicting)
        with pytest.raises(LookupError, match="not found"):
            await store.update_intervention(_intervention("int_missing"))

        saved = await store.get_intervention(original.id)
        assert saved == original
        cursor = await store.db.execute(
            "SELECT record_type FROM intervention_audit ORDER BY id"
        )
        assert [row["record_type"] for row in await cursor.fetchall()] == ["created"]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_forged_jsonl_audit_id_cannot_suppress_durable_revision(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    await _bind_audit_session(store)
    try:
        store.audit_path.write_text(
            '{"audit_id":1,"record_type":"forged"}\n',
            encoding="utf-8",
        )
        await store.add_intervention(_intervention("int_real"))

        records = [
            json.loads(line)
            for line in store.audit_path.read_text(encoding="utf-8").splitlines()
        ]
        assert records[0] == {"audit_id": 1, "record_type": "forged"}
        assert records[-1]["audit_id"] == 1
        assert records[-1]["intervention_id"] == "int_real"
        assert records[-1]["record_type"] == "created"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_duplicate_jsonl_keys_cannot_suppress_durable_revision(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    await _bind_audit_session(store)
    try:
        await store.add_intervention(_intervention("int_duplicate_key"))
        canonical = store.audit_path.read_text(encoding="utf-8").strip()
        assert canonical.endswith(',"audit_id":1}')
        forged = canonical.replace(
            ',"audit_id":1}',
            ',"audit_id":999,"audit_id":1}',
            1,
        )
        store.audit_path.write_text(forged + "\n", encoding="utf-8")

        await store._sync_intervention_audit()

        lines = store.audit_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert lines[0] == forged
        repaired = json.loads(lines[1])
        assert repaired["audit_id"] == 1
        assert repaired["intervention_id"] == "int_duplicate_key"
    finally:
        await store.close()
