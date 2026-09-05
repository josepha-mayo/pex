"""Real temporary SQLite/workspace provenance. No worker or provider launches."""

import copy
import hashlib
import json
import sqlite3

import pytest
from pex_bridge import codex_correction
from pex_bridge.store import Store, stable_event_effect_id, utcnow
from pex_protocol.actions import InterventionType
from pex_protocol.enums import EventType
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent
from test_event_processing_store import (
    _bound_event,
    _plan_envelope,
    _planned_intervention,
)
from test_workspace_publication import publication as _publication_fixture
from test_workspace_publication import publish

publication = _publication_fixture
OWNER = "correction-owner"


@pytest.fixture
async def bound(publication):
    store, session, _, _ = publication
    session.metadata["connection_kind"] = "codex_shared"
    session.metadata["subscription_receipt"] = {
        "schema": "pex.codex-existing-thread-subscription.v1",
        "authorization_id": "subscription-1", "selection_id": "selection-1",
        "endpoint_identity": "fixture-endpoint", "connection_generation": 1,
        "pex_session_id": session.id, "thread_id": session.vendor_session_id,
        "root_session_id": "workspace-root", "project_id": session.project_id,
        "vendor_project_id": None, "cwd": session.cwd,
        "history_mode": "includeTurns", "history_identity_digest": "a" * 64,
        "history_record_count": 0, "reconciliation_live_watermark": 0,
        "observation_only": True, "delivery_proven": False,
    }
    await publish(publication)
    goal = Goal(
        id="correction-goal", project_id=session.project_id, title="Finish",
        objective="Finish the exact task", created_at=utcnow(), updated_at=utcnow(),
    )
    await store.upsert_goal(goal)
    await store.attach_session_goal(session.id, goal.id, expected_goal_id=None)
    current = await store.get_session(session.id)
    current.capabilities["send_message"] = True  # Test-only; product remains observe-only.
    await store.upsert_session(current)
    return store, await store.get_session(session.id), publication


async def prepare(bound, *, event_id="correction-trigger", text="  Verify the actual result.\n"):
    store, session, _ = bound
    event = HarnessEvent(
        event_id=event_id, session_id=session.id, harness_type=session.harness_type,
        project_id=session.project_id, goal_id=session.goal_id, ts=utcnow(),
        event_type=EventType.STOP, message_delta="Done.",
    )
    await store.accept_pipeline_event(event, session_snapshot=session)
    await store.claim_event_processing(event.event_id, owner=OWNER)
    intervention = _planned_intervention(event)
    intervention.proposed_action.payload = {"text": text}
    payload = await store.prepare_main_effect_payload(
        event_id=event.event_id, intervention_id=intervention.id,
        action=intervention.proposed_action.model_dump(mode="json"),
        required_capability="send_message",
    )
    return event, intervention, payload


async def commit(bound, prepared, *, payload=None):
    store, session, _ = bound
    event, intervention, original = prepared
    chosen = original if payload is None else payload
    return await store.commit_event_plan(
        event_id=event.event_id, owner=OWNER, session=session, intervention=intervention,
        plan=_plan_envelope(
            event, intervention=intervention, effect_kind="worker_action",
            required_capability=chosen["required_capability"],
        ),
        main_effect={
            "effect_key": "main", "kind": "worker_action", "target_session_id": session.id,
            "payload": chosen,
            "request_hash": hashlib.sha256(
                codex_correction.canonical(chosen).encode("utf-8")
            ).hexdigest(),
        },
    )


async def attempt(bound, prepared):
    await commit(bound, prepared)
    result = await bound[0].claim_main_event_effect(event_id=prepared[0].event_id, owner=OWNER)
    assert result["granted"], result
    return result["effect"]


async def test_preparation_exact_text_deterministic_and_no_reservation(bound):
    store, session, _ = bound
    event, intervention, payload = await prepare(bound)
    correction = payload["codex_correction"]
    assert correction["effect_id"] == stable_event_effect_id(event.event_id, "main")
    assert correction["content"] == [{
        "type": "text", "text": "  Verify the actual result.\n", "text_elements": [],
    }]
    assert correction["subscription_receipt"] == session.metadata["subscription_receipt"]
    assert correction["workspace_binding"] == session.metadata["workspace_binding"]
    again = await store.prepare_main_effect_payload(
        event_id=event.event_id, intervention_id=intervention.id,
        action=intervention.proposed_action.model_dump(mode="json"),
        required_capability="send_message",
    )
    assert payload == again
    assert await store.get_event_effect(event.event_id, "main") is None
    assert await store.list_codex_correction_attributions(session) == ()


async def test_commit_replay_and_reserved_has_no_attribution(bound):
    store, session, _ = bound
    prepared = await prepare(bound)
    processing = await commit(bound, prepared)
    event, _, _ = prepared
    effect = await store.get_event_effect(event.event_id, "main")
    assert effect["payload"] == prepared[2]
    assert await store.list_codex_correction_attributions(session) == ()
    assert await store.commit_event_plan(
        event_id=event.event_id, owner=OWNER, plan=processing["plan"], session=session,
    ) == processing
    assert await store.get_event_effect(event.event_id, "main") == effect


@pytest.mark.parametrize("change", [
    "missing", "correlation", "content", "thread", "epoch", "workspace", "extra",
])
async def test_forged_or_missing_contract_rolls_back_all_projections(bound, change):
    store, _, _ = bound
    prepared = await prepare(bound)
    payload = copy.deepcopy(prepared[2])
    correction = payload["codex_correction"]
    if change == "missing":
        del payload["codex_correction"]
    elif change == "correlation":
        correction["client_message_id"] = "pex-correction-forged"
    elif change == "content":
        correction["content"][0]["text"] = "Different instruction"
    elif change == "thread":
        correction["thread_id"] = "another-thread"
    elif change == "epoch":
        correction["subscription_receipt"]["connection_generation"] += 1
    elif change == "workspace":
        correction["workspace_binding"]["directory"]["cwd"] += "-other"
    else:
        correction["extra"] = "unreviewed"
    with pytest.raises(ValueError, match="Codex correction payload"):
        await commit(bound, prepared, payload=payload)
    assert await store.get_event_effect(prepared[0].event_id, "main") is None
    assert await store.get_intervention(prepared[1].id) is None
    assert (await store.get_event_processing(prepared[0].event_id))["state"] == "planning"


@pytest.mark.parametrize(
    "text", ["", " ", "a\x00b", "é" * 32769, False],
    ids=["empty", "whitespace", "nul", "utf8_overflow", "boolean"],
)
async def test_invalid_text_is_not_coerced(bound, text):
    with pytest.raises(ValueError, match="bounded exact text"):
        await prepare(bound, text=text)


@pytest.mark.parametrize("key", ["clientUserMessageId", "client_message_id", "codex_correction"])
async def test_model_supplied_correlation_rejected(bound, key):
    event, intervention, _ = await prepare(bound)
    intervention.proposed_action.payload[key] = "untrusted"
    with pytest.raises(ValueError, match="action binding"):
        await bound[0].prepare_main_effect_payload(
            event_id=event.event_id, intervention_id=intervention.id,
            action=intervention.proposed_action.model_dump(mode="json"),
            required_capability="send_message",
        )


@pytest.mark.parametrize("field", ["payload_json", "request_hash", "target_session_id"])
async def test_correction_authority_immutable_but_lifecycle_writable(bound, field):
    store, session, _ = bound
    prepared = await prepare(bound)
    effect = await attempt(bound, prepared)
    value = "{}" if field == "payload_json" else "changed"
    with pytest.raises(sqlite3.IntegrityError, match="authority is immutable"):
        await store.db.execute(
            f"UPDATE event_effects SET {field} = ? WHERE effect_id = ?",
            (value, effect["effect_id"]),
        )
    await store.db.rollback()
    await store.db.execute(
        "UPDATE event_effects SET state='delivery_uncertain', version=version+1, "
        "result_json=? WHERE effect_id=?", ('{"outcome":"timeout"}', effect["effect_id"]),
    )
    await store.db.commit()
    records = await store.list_codex_correction_attributions(session)
    assert len(records) == 1
    assert json.loads(records[0])["effect_state"] == "delivery_uncertain"


async def test_database_uniqueness_prevents_two_effects_owning_correlation(bound):
    store, _, _ = bound
    prepared = await prepare(bound)
    await commit(bound, prepared)
    effect = await store.get_event_effect(prepared[0].event_id, "main")
    # Independent SQL duplicate proves the index, not just deterministic Python generation.
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        await store.db.execute(
            "INSERT INTO event_effects(effect_id,event_id,effect_key,kind,target_session_id,"
            "request_hash,state,reserved_at,updated_at,payload_json) "
            "VALUES(?,?,'other','worker_action',?,?,'reserved',?,?,?)",
            ("other-effect", prepared[0].event_id, bound[1].id, effect["request_hash"],
             utcnow().isoformat(), utcnow().isoformat(), effect["payload_json"]),
        )
    await store.db.rollback()


@pytest.mark.parametrize("state", ["dispatching", "delivered", "delivery_uncertain", "failed"])
async def test_attempt_states_are_historical_records_not_dispatch_grants(bound, state):
    store, session, _ = bound
    prepared = await prepare(bound)
    effect = await attempt(bound, prepared)
    await store.db.execute(
        "UPDATE event_effects SET state=? WHERE effect_id=?", (state, effect["effect_id"]),
    )
    await store.db.commit()
    result = await store.list_codex_correction_attributions(session)
    assert isinstance(result, tuple) and isinstance(result[0], str)
    assert json.loads(result[0]) == {
        "correction": prepared[2]["codex_correction"], "effect_state": state,
        "effect_version": effect["version"],
    }


async def test_skipped_plan_is_not_an_attempt(bound):
    store, session, _ = bound
    prepared = await prepare(bound)
    await commit(bound, prepared)
    await store.db.execute(
        "UPDATE event_effects SET state='skipped' WHERE event_id=?", (prepared[0].event_id,),
    )
    await store.db.commit()
    assert await store.list_codex_correction_attributions(session) == ()


async def test_loader_survives_restart_and_new_epoch_without_reviving_authority(bound):
    store, session, publication_fixture = bound
    prepared = await prepare(bound)
    await attempt(bound, prepared)
    current = await store.get_session(session.id)
    current.metadata["subscription_receipt"]["authorization_id"] = "subscription-2"
    current.metadata["subscription_receipt"]["connection_generation"] = 2
    revision = (await store.get_session_control_state(session.id))["control_revision"]
    current = await publish(publication_fixture, session=current, expected_revision=revision)
    reopened = Store(store.path, process_boot_id="later-boot")
    await reopened.connect()
    try:
        records = await reopened.list_codex_correction_attributions(current)
        assert len(records) == 1
        old_receipt = json.loads(records[0])["correction"]["subscription_receipt"]
        assert old_receipt["connection_generation"] == 1
        grant = await reopened.validate_main_event_effect_dispatch(
            event_id=prepared[0].event_id, owner=OWNER,
            effect_id=prepared[2]["codex_correction"]["effect_id"], effect_version=1,
            expected_action=prepared[2]["action"],
        )
        assert not grant["granted"]
    finally:
        await reopened.close()


@pytest.mark.parametrize("bound_name", ["MAX_ATTRIBUTION_RECORDS", "MAX_ATTRIBUTION_BYTES"])
async def test_loader_never_silently_truncates(bound, monkeypatch, bound_name):
    prepared = await prepare(bound)
    await attempt(bound, prepared)
    monkeypatch.setattr(codex_correction, bound_name, 0)
    with pytest.raises(ValueError, match="coverage exceeds"):
        await bound[0].list_codex_correction_attributions(bound[1])


async def test_stale_workspace_prevents_commit_and_historical_read(bound):
    store, session, publication_fixture = bound
    prepared = await prepare(bound)
    workspace = publication_fixture[3].parent / "workspace"
    workspace.rename(workspace.with_name("old-workspace"))
    workspace.mkdir()
    with pytest.raises(ValueError, match="workspace authority changed"):
        await commit(bound, prepared)
    assert await store.get_event_effect(prepared[0].event_id, "main") is None
    with pytest.raises(ValueError, match="workspace authority changed"):
        await store.list_codex_correction_attributions(session)


async def test_legacy_effect_payload_remains_unchanged(tmp_path):
    store = Store(tmp_path / "legacy.sqlite")
    await store.connect()
    try:
        event, _ = await _bound_event(store, "legacy-correction")
        session = await store.get_session(event.session_id)
        await store.accept_pipeline_event(event, session_snapshot=session)
        intervention = _planned_intervention(event)
        payload = await store.prepare_main_effect_payload(
            event_id=event.event_id, intervention_id=intervention.id,
            action=intervention.proposed_action.model_dump(mode="json"),
            required_capability="send_message",
        )
        assert "codex_correction" not in payload
        assert payload["schema"] == "pex.worker-effect.v1"
    finally:
        await store.close()


@pytest.mark.parametrize("action_type", [
    InterventionType.SEND_NUDGE, InterventionType.INJECT_CONTEXT,
    InterventionType.REQUEST_VERIFICATION, InterventionType.CONTINUE_SESSION,
])
async def test_all_supported_actions_bind_exact_supplied_text(bound, action_type):
    store, session, publication_fixture = bound
    event, intervention, _ = await prepare(bound)
    capability = "resume" if action_type == InterventionType.CONTINUE_SESSION else "send_message"
    intervention.proposed_action.type = action_type
    intervention.proposed_action.requires_capability = capability
    intervention.action_taken = action_type.value
    intervention.proposed_action.payload["text"] = " Verify café.\n"
    payload = await store.prepare_main_effect_payload(
        event_id=event.event_id, intervention_id=intervention.id,
        action=intervention.proposed_action.model_dump(mode="json"),
        required_capability=capability,
    )
    if capability == "resume":
        session.capabilities["resume"] = True
        await store.upsert_session(session)
    await commit((store, session, publication_fixture), (event, intervention, payload))
    assert payload["codex_correction"]["content"][0]["text"] == " Verify café.\n"


async def test_continue_without_supplied_text_never_invents_prompt(bound):
    event, intervention, _ = await prepare(bound)
    intervention.proposed_action.type = InterventionType.CONTINUE_SESSION
    intervention.proposed_action.payload = {}
    with pytest.raises(ValueError, match="bounded exact text"):
        await bound[0].prepare_main_effect_payload(
            event_id=event.event_id, intervention_id=intervention.id,
            action=intervention.proposed_action.model_dump(mode="json"),
            required_capability="resume",
        )


async def test_insert_fault_rolls_back_intervention_and_effect(bound):
    store, _, _ = bound
    prepared = await prepare(bound)
    await store.db.execute(
        "CREATE TRIGGER correction_insert_fault BEFORE INSERT ON event_effects "
        "BEGIN SELECT RAISE(ABORT, 'correction insert fault'); END",
    )
    await store.db.commit()
    with pytest.raises(sqlite3.IntegrityError, match="correction insert fault"):
        await commit(bound, prepared)
    assert await store.get_intervention(prepared[1].id) is None
    assert await store.get_event_effect(prepared[0].event_id, "main") is None
    await store.db.execute("DROP TRIGGER correction_insert_fault")
    await store.db.commit()
    await commit(bound, prepared)


async def test_changed_subscription_between_prepare_and_commit_is_rejected(bound):
    store, session, publication_fixture = bound
    prepared = await prepare(bound)
    current = await store.get_session(session.id)
    current.metadata["subscription_receipt"]["authorization_id"] = "replacement-subscription"
    revision = (await store.get_session_control_state(session.id))["control_revision"]
    await publish(publication_fixture, session=current, expected_revision=revision)
    with pytest.raises(ValueError, match="workspace authority changed"):
        await commit(bound, prepared)
    assert await store.get_event_effect(prepared[0].event_id, "main") is None


async def test_changed_human_goal_keeps_old_correction_attribution(bound):
    store, session, _ = bound
    prepared = await prepare(bound)
    await attempt(bound, prepared)
    goal = await store.get_goal(session.goal_id)
    goal.objective = "A new explicit instruction"
    await store.upsert_goal(goal)
    assert len(await store.list_codex_correction_attributions(session)) == 1


@pytest.mark.parametrize("field", ["root_session_id", "endpoint_identity"])
async def test_different_worker_scope_never_matches_old_correction(bound, field):
    store, session, publication_fixture = bound
    prepared = await prepare(bound)
    await attempt(bound, prepared)
    current = await store.get_session(session.id)
    current.metadata["subscription_receipt"]["authorization_id"] = "replacement-subscription"
    current.metadata["subscription_receipt"][field] = "different-worker"
    revision = (await store.get_session_control_state(session.id))["control_revision"]
    current = await publish(publication_fixture, session=current, expected_revision=revision)
    assert await store.list_codex_correction_attributions(current) == ()


@pytest.mark.parametrize("corrupt", ["hash", "missing_marker", "wrong_plan"])
async def test_loader_rejects_corrupt_attempt_without_partial_results(bound, corrupt):
    store, session, _ = bound
    prepared = await prepare(bound)
    effect = await attempt(bound, prepared)
    if corrupt == "hash":
        # Simulated external corruption; normal updates are independently trigger-blocked.
        await store.db.execute("DROP TRIGGER trg_codex_correction_authority_immutable")
        await store.db.execute(
            "UPDATE event_effects SET request_hash='corrupt' WHERE effect_id=?",
            (effect["effect_id"],),
        )
    elif corrupt == "missing_marker":
        await store.db.execute(
            "UPDATE event_effects SET dispatch_started_at=NULL WHERE effect_id=?",
            (effect["effect_id"],),
        )
    else:
        await store.db.execute(
            "UPDATE event_processing SET plan_json='{}' WHERE event_id=?", (prepared[0].event_id,),
        )
    await store.db.commit()
    with pytest.raises(ValueError, match="attribution binding is corrupt"):
        await store.list_codex_correction_attributions(session)


async def test_planner_cannot_poison_correction_provenance(bound):
    store, session, _ = bound
    event, _, payload = await prepare(bound)
    with pytest.raises(ValueError, match="reserved for main worker effects"):
        await store.reserve_event_effect(
            event_id=event.event_id, effect_key="planner", kind="supervisor_decision",
            target_session_id=session.id, payload=payload, owner=OWNER,
            request_hash=hashlib.sha256(
                codex_correction.canonical(payload).encode("utf-8"),
            ).hexdigest(),
        )
    assert await store.get_event_effect(event.event_id, "planner") is None
