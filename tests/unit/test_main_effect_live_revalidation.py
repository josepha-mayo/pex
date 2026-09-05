"""Final current-authority samples use real temporary Store, never worker I/O."""

import asyncio
import copy
import json
import sqlite3
from datetime import timedelta

import pytest
import test_event_processing_store as event_helpers
from pex_bridge import store as store_module
from pex_bridge.store import Store, utcnow
from pex_protocol.enums import EventType, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from test_event_processing_store import (
    _bound_event,
    _commit_worker_plan,
    _event,
    _register_event_project_identity,
    _reresolve_event_project_identity,
)
from test_workspace_continuity_store_review import _invalidate as invalidate_workspace
from test_workspace_publication import publication as _publication_fixture
from test_workspace_publication import publish

publication = _publication_fixture
OWNER = "live-effect-owner"


@pytest.fixture
async def claimed(tmp_path):
    store = Store(tmp_path / "live-effect.sqlite", process_boot_id="live-effect-boot")
    await store.connect()
    try:
        yield await prepare_claim(store)
    finally:
        await store.close()


async def prepare_claim(store, *, no_goal=False):
    event, session = await _bound_event(store, "live-effect-trigger")
    if no_goal:
        event.goal_id = None
        session.goal_id = None
        await store.upsert_session(session, allow_goal_change=True)
    await store.accept_pipeline_event(event, session_snapshot=session)
    await store.claim_event_processing(event.event_id, owner=OWNER)
    await _commit_worker_plan(store, event, session, owner=OWNER)
    result = await store.claim_main_event_effect(event_id=event.event_id, owner=OWNER)
    assert result["granted"]
    return store, event, session, result["effect"]


def arguments(fixture, **overrides):
    _, event, _, effect = fixture
    return {
        "event_id": event.event_id,
        "owner": OWNER,
        "effect_id": effect["effect_id"],
        "effect_version": effect["version"],
        "expected_action": copy.deepcopy(effect["payload"]["action"]),
        **overrides,
    }


async def validate(fixture, **overrides):
    return await fixture[0].validate_main_event_effect_dispatch(**arguments(fixture, **overrides))


async def refused(fixture, reason, **overrides):
    store, event, _, _ = fixture
    before = await store.get_event_effect(event.event_id, "main")
    result = await validate(fixture, **overrides)
    assert result["granted"] is False
    assert result["reason"] == reason
    assert await store.get_event_effect(event.event_id, "main") == before
    return result


@pytest.mark.asyncio
async def test_repeated_positive_validation_leaves_all_durable_markers_unchanged(claimed):
    store, event, session, effect = claimed
    processing = await store.get_event_processing(event.event_id)
    interventions = await store.list_interventions(session.id)
    for _ in range(3):
        result = await validate(claimed)
        assert result == {"granted": True, "effect": effect}
        assert await store.get_event_effect(event.event_id, "main") == effect
        assert await store.get_event_processing(event.event_id) == processing
        assert await store.list_interventions(session.id) == interventions
    second_claim = await store.claim_main_event_effect(event_id=event.event_id, owner=OWNER)
    assert not second_claim["granted"]


@pytest.mark.asyncio
@pytest.mark.parametrize("override, reason", [
    ({"owner": "other-owner"}, "processing_claim_not_owned"),
    ({"effect_id": "different-effect"}, "dispatch_effect_id_mismatch"),
    ({"effect_version": 9000}, "dispatch_effect_version_mismatch"),
    ({"global_supervision_paused": True}, "global_supervision_paused"),
])
async def test_exact_owner_effect_version_and_global_pause(claimed, override, reason):
    await refused(claimed, reason, **override)


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [
    {"effect_version": True}, {"effect_version": -1}, {"effect_version": "1"},
    {"expected_action": []}, {"global_supervision_paused": 0},
])
async def test_validator_does_not_loosen_argument_types(claimed, override):
    with pytest.raises(ValueError):
        await validate(claimed, **override)


@pytest.mark.asyncio
async def test_effect_dispatch_boot_must_match_current_process(claimed):
    store, _, _, _ = claimed
    other_process = Store(store.path, process_boot_id="other-process-boot")
    result = await other_process.validate_main_event_effect_dispatch(**arguments(claimed))
    assert result["granted"] is False
    assert result["reason"] == "dispatch_process_boot_mismatch"
    assert (await validate(claimed))["granted"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("expiry", [None, "invalid timestamp", "2000-01-01T00:00:00+00:00"])
async def test_expired_or_missing_processing_lease_cannot_validate(claimed, expiry):
    store, event, _, _ = claimed
    await store.db.execute(
        "UPDATE event_processing SET lease_expires_at=? WHERE event_id=?", (expiry, event.event_id)
    )
    await store.db.commit()
    await refused(claimed, "processing_lease_expired")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state", ["reserved", "delivered", "failed", "delivery_uncertain", "skipped"]
)
async def test_reserved_or_terminal_effect_never_validates(claimed, state):
    store, event, _, _ = claimed
    await store.db.execute(
        "UPDATE event_effects SET state=? WHERE event_id=?", (state, event.event_id)
    )
    await store.db.commit()
    await refused(claimed, f"effect_already_{state}")


@pytest.mark.asyncio
@pytest.mark.parametrize("restore", [False, True])
async def test_goal_intent_change_and_aba_after_claim_are_rejected(claimed, restore):
    store, event, _, _ = claimed
    original = await store.get_goal(event.goal_id)
    await store.upsert_goal(original.model_copy(update={"objective": "Changed human intent"}))
    if restore:
        await store.upsert_goal(original)
    await refused(claimed, "goal_intent_changed_before_dispatch")


@pytest.mark.asyncio
@pytest.mark.parametrize("restore", [False, True])
async def test_goal_pause_and_resume_cannot_restore_an_old_action(claimed, restore):
    store, event, _, _ = claimed
    original = await store.get_goal(event.goal_id)
    await store.upsert_goal(original.model_copy(update={"paused": True}))
    if restore:
        await store.upsert_goal(original)
    await refused(
        claimed, "goal_intent_changed_before_dispatch" if restore else "goal_paused_before_dispatch"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("change, reason", [
    ({"capabilities": {"send_message": False}}, "missing_capability:send_message"),
    ({"status": SessionStatus.DETACHED}, "session_detached_before_dispatch"),
])
async def test_lost_worker_capability_or_detachment_refuses_old_action(claimed, change, reason):
    store, _, session, _ = claimed
    await store.upsert_session(session.model_copy(update=change))
    await refused(claimed, reason)


@pytest.mark.asyncio
@pytest.mark.parametrize("restore", [False, True])
async def test_session_pause_and_pause_resume_after_claim_are_rejected(claimed, restore):
    store, _, session, _ = claimed
    await store.upsert_session(
        session.model_copy(update={"supervision_paused": True}), allow_supervision_change=True
    )
    if restore:
        await store.upsert_session(session, allow_supervision_change=True)
    await refused(
        claimed,
        "session_authority_changed_before_dispatch" if restore else "session_supervision_paused",
    )


@pytest.mark.asyncio
async def test_working_target_aba_after_claim_does_not_restore_authority(claimed):
    store, _, session, _ = claimed
    await store.upsert_session(session.model_copy(update={"cwd": "C:/other"}))
    await store.upsert_session(session)
    await refused(claimed, "session_authority_changed_before_dispatch")


@pytest.mark.asyncio
async def test_vendor_target_cannot_be_changed_to_another_worker(claimed):
    store, _, session, _ = claimed
    with pytest.raises(ValueError, match="cannot change vendor identity"):
        await store.upsert_session(session.model_copy(update={"vendor_session_id": "other"}))
    assert (await validate(claimed))["granted"]


@pytest.mark.asyncio
@pytest.mark.parametrize("record_only", [False, True])
async def test_new_accepted_human_input_blocks_old_action_without_vendor_clock_order(
    claimed, record_only
):
    store, event, session, _ = claimed
    prompt = _event("new-human", goal_id=event.goal_id).model_copy(update={
        "event_type": EventType.USER_PROMPT,
        "message_delta": "Updated human instruction",
        "ts": event.ts - timedelta(days=1),
    })
    if record_only:
        await store.add_event(prompt)
    else:
        await store.accept_pipeline_event(prompt, session_snapshot=session)
    await refused(claimed, "newer_human_input_before_dispatch")


@pytest.mark.asyncio
@pytest.mark.parametrize("field, value", [
    ("goal_id", "forged-goal"), ("session_id", "codex:forged"), ("reversible", 0),
])
async def test_expected_action_exact_binding_including_json_boolean_types(claimed, field, value):
    action = arguments(claimed)["expected_action"]
    action[field] = value
    await refused(claimed, "dispatch_action_mismatch", expected_action=action)


async def mutate_intervention(store, event, change):
    processing = await store.get_event_processing(event.event_id)
    intervention_id = processing["plan"]["intervention_id"]
    cursor = await store.db.execute("SELECT json FROM interventions WHERE id=?", (intervention_id,))
    envelope = json.loads((await cursor.fetchone())["json"])
    payload = envelope.get("payload", envelope)
    payload.update(change)
    await store.db.execute(
        "UPDATE interventions SET json=? WHERE id=?", (json.dumps(envelope), intervention_id)
    )
    await store.db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", ["deny", "ask_human"])
async def test_reserved_intervention_policy_must_still_allow(tmp_path, monkeypatch, verdict):
    original = event_helpers._planned_intervention

    def intervention(event):
        return original(event).model_copy(update={"policy_verdict": PolicyVerdict(verdict)})

    monkeypatch.setattr(event_helpers, "_planned_intervention", intervention)
    store = Store(tmp_path / "nonallow.sqlite")
    await store.connect()
    try:
        fixture = await prepare_claim(store)
        await refused(fixture, "intervention_policy_not_allowed")
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_reserved_intervention_cannot_substitute_another_goal(claimed):
    store, event, _, _ = claimed
    with pytest.raises(sqlite3.IntegrityError, match="intervention binding is immutable"):
        await mutate_intervention(store, event, {"goal_id": "forged-goal"})
    await store.db.rollback()
    assert (await validate(claimed))["granted"]


@pytest.mark.asyncio
async def test_corrupt_effect_request_hash_is_checked_again(claimed):
    store, event, _, _ = claimed
    await store.db.execute(
        "UPDATE event_effects SET request_hash=? WHERE event_id=?", ("0" * 64, event.event_id)
    )
    await store.db.commit()
    await refused(claimed, "effect_identity_binding_corrupt")


@pytest.mark.asyncio
async def test_presentation_changes_and_new_worker_event_do_not_revoke_valid_action(claimed):
    store, event, session, _ = claimed
    await store.upsert_session(session.model_copy(update={"status": SessionStatus.IDLE}))
    await store.accept_pipeline_event(_event("worker-progress", goal_id=event.goal_id))
    assert (await validate(claimed))["granted"]


@pytest.mark.asyncio
async def test_lease_expiring_during_live_checks_is_not_renewed(claimed, monkeypatch):
    store, _, _, _ = claimed
    original = store_module._require_processing_workspace_current

    async def expire_after_check(transaction, processing):
        await original(transaction, processing)
        monkeypatch.setattr(store_module, "utcnow", lambda: utcnow() + timedelta(hours=1))

    monkeypatch.setattr(store_module, "_require_processing_workspace_current", expire_after_check)
    await refused(claimed, "processing_lease_expired")


@pytest.mark.asyncio
async def test_caller_action_is_frozen_before_asynchronous_authority_read(claimed, monkeypatch):
    store, _, _, _ = claimed
    action = arguments(claimed)["expected_action"]
    entered, release = asyncio.Event(), asyncio.Event()
    original = store_module._configure_connection

    async def held(connection):
        entered.set()
        await release.wait()
        await original(connection)

    monkeypatch.setattr(store_module, "_configure_connection", held)
    task = asyncio.create_task(validate(claimed, expected_action=action))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        action["payload"]["message"] = "Changed caller object"
        release.set()
        assert (await task)["granted"]
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_project_identity_reresolution_after_claim_is_rejected(tmp_path):
    store = Store(tmp_path / "project-identity.sqlite")
    await store.connect()
    try:
        event = _event("identity-revalidation")
        await _register_event_project_identity(store, event)
        event, session = await _bound_event(store, "identity-revalidation")
        await store.accept_pipeline_event(event, session_snapshot=session)
        await store.claim_event_processing(event.event_id, owner=OWNER)
        await _commit_worker_plan(store, event, session, owner=OWNER)
        claim = await store.claim_main_event_effect(event_id=event.event_id, owner=OWNER)
        assert claim["granted"]
        await _reresolve_event_project_identity(store, event)
        result = await validate((store, event, session, claim["effect"]))
        assert not result["granted"]
        assert "project" in result["reason"]
        assert await store.get_event_effect(event.event_id, "main") == claim["effect"]
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["origin", "directory", "locator"])
async def test_actual_bound_workspace_loss_after_claim_refuses_without_marker_write(
    publication, change
):
    store, session, _, _ = publication
    await publish(publication)
    now = utcnow()
    goal = Goal(
        id="workspace-main-goal", project_id=session.project_id, title="Worker goal",
        objective="Finish the real selected task.", created_at=now, updated_at=now,
    )
    await store.upsert_goal(goal)
    await store.attach_session_goal(session.id, goal.id, expected_goal_id=None)
    session = await store.get_session(session.id)
    session.capabilities["send_message"] = True
    await store.upsert_session(session)
    event = _event("workspace-main-trigger", session_id=session.id, goal_id=goal.id).model_copy(
        update={"project_id": session.project_id}
    )
    await store.accept_pipeline_event(event, session_snapshot=session)
    await store.claim_event_processing(event.event_id, owner=OWNER)
    await _commit_worker_plan(store, event, session, owner=OWNER)
    claim = await store.claim_main_event_effect(event_id=event.event_id, owner=OWNER)
    assert claim["granted"]
    fixture = store, event, session, claim["effect"]
    assert (await validate(fixture))["granted"]
    await invalidate_workspace(publication, change)
    result = await validate(fixture)
    assert not result["granted"]
    assert "workspace" in result["reason"]
    assert await store.get_event_effect(event.event_id, "main") == claim["effect"]


@pytest.mark.asyncio
async def test_autonomous_action_without_canonical_goal_cannot_validate(tmp_path):
    store = Store(tmp_path / "no-goal.sqlite")
    await store.connect()
    try:
        with pytest.raises(ValueError, match="requires a persistent goal binding"):
            await prepare_claim(store, no_goal=True)
        assert await store.get_event_effect("live-effect-trigger", "main") is None
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change, reason", [
    ({"mode": "record_only"}, "event_not_pipeline"),
    ({"state": "complete"}, "event_already_terminal"),
    ({"state": "planning"}, "event_plan_not_dispatchable"),
    ({"lease_owner": "other"}, "processing_claim_not_owned"),
])
async def test_processing_authority_cannot_be_relabelled_after_claim(claimed, change, reason):
    store, event, _, _ = claimed
    column, value = next(iter(change.items()))
    assert column in {"mode", "state", "lease_owner"}
    await store.db.execute(
        f"UPDATE event_processing SET {column}=? WHERE event_id=?", (value, event.event_id)
    )
    await store.db.commit()
    await refused(claimed, reason)


@pytest.mark.asyncio
async def test_plan_action_keeps_exact_json_types_after_claim(claimed):
    store, event, _, _ = claimed
    processing = await store.get_event_processing(event.event_id)
    plan = processing["plan"]
    assert plan["action"]["reversible"] is False
    plan["action"]["reversible"] = 0
    await store.db.execute(
        "UPDATE event_processing SET plan_json=? WHERE event_id=?",
        (json.dumps(plan), event.event_id),
    )
    await store.db.commit()
    await refused(claimed, "dispatch_plan_action_mismatch")


@pytest.mark.asyncio
async def test_validation_cancellation_does_not_advance_or_settle_effect(claimed, monkeypatch):
    store, event, _, effect = claimed
    entered = asyncio.Event()
    original = store_module._require_processing_workspace_current

    async def held(transaction, processing):
        await original(transaction, processing)
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(store_module, "_require_processing_workspace_current", held)
    task = asyncio.create_task(validate(claimed))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await store.get_event_effect(event.event_id, "main") == effect
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
