"""Exact correction echoes through real temporary SQLite and workspace publication."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import sqlite3
from datetime import timedelta
from types import SimpleNamespace

import pytest
from pex_bridge import store as store_module
from pex_bridge.codex_correction import canonical
from pex_bridge.local_origin_config import load_local_origin_choice, save_local_origin_choice
from pex_bridge.store import Store, utcnow
from pex_bridge.workspace_binding import WorkspaceAuthorityError
from pex_protocol.enums import EventType
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent
from test_codex_correction_store import OWNER, attempt, prepare
from test_codex_correction_store import bound as bound
from test_codex_correction_store import publication as publication
from test_workspace_publication import publish


def marker(correction, item, turn_id):
    entry = {
        "turn_id": turn_id, "item_id": item["id"], "client_id": item["clientId"],
        "content": item["content"],
    }
    return {
        "schema": "pex.codex-correction-observation.v1",
        "effect_id": correction["effect_id"],
        "client_message_id": correction["client_message_id"],
        "vendor_item_id": item["id"],
        "input_sha256": hashlib.sha256(canonical(entry).encode()).hexdigest(),
    }


def observation(session, correction, *, event_id="correction-echo", turn_id="echo-turn"):
    item = {
        "type": "userMessage", "id": "echo-item",
        "clientId": correction["client_message_id"],
        "content": copy.deepcopy(correction["content"]),
    }
    receipt = session.metadata["subscription_receipt"]
    event = HarnessEvent(
        event_id=event_id, ts=utcnow(), harness_type=session.harness_type,
        session_id=session.id, project_id=session.project_id, event_type=EventType.STATUS,
        metadata={
            "source": "codex_shared_live_notification", "raw_method": "item/completed",
            "vendor_turn_id": turn_id, "subscription_id": receipt["authorization_id"],
            "endpoint_identity": receipt["endpoint_identity"],
            "connection_generation": receipt["connection_generation"],
            "ingress_sequence": 1,
            "sequence_scope": "retained_lifecycle_records_not_raw_frames",
            "delivery_proven": False,
            "pex_correction_observation": marker(correction, item, turn_id),
        },
    )
    return event, item, turn_id


@pytest.fixture
async def echo(bound):
    store, session, fixture = bound
    prepared = await prepare(bound)
    effect = await attempt(bound, prepared)
    correction = prepared[2]["codex_correction"]
    event, item, turn = observation(session, correction)
    return SimpleNamespace(
        store=store, session=session, fixture=fixture, prepared=prepared,
        effect=effect, correction=correction, event=event, item=item, turn=turn,
    )


async def record(echo, *, store=None, event=None, session=None, item=None, turn=None):
    return await (store or echo.store).record_codex_correction_observation(
        echo.event if event is None else event,
        echo.session if session is None else session,
        raw_item=echo.item if item is None else item,
        turn_id=echo.turn if turn is None else turn,
    )


async def assert_absent(echo):
    assert await echo.store.get_event(echo.event.event_id) is None
    assert await echo.store.get_event_processing(echo.event.event_id) is None
    cursor = await echo.store.db.execute(
        "SELECT COUNT(*) AS total FROM event_publications WHERE event_id=?",
        (echo.event.event_id,),
    )
    assert (await cursor.fetchone())["total"] == 0


async def test_exact_echo_is_record_only_and_does_not_change_worker_goal_or_effect(echo):
    control = await echo.store.get_session_control_state(echo.session.id)
    goal = await echo.store.get_goal(echo.session.goal_id)
    interventions = await echo.store.list_interventions(echo.session.id)
    saved = await record(echo)
    assert saved.goal_id == echo.session.goal_id
    assert saved.project_id == echo.session.project_id
    assert saved.event_type == EventType.STATUS and saved.message_delta is None
    assert echo.correction["content"][0]["text"] not in canonical(saved.model_dump(mode="json"))
    processing = await echo.store.get_event_processing(saved.event_id)
    assert processing["mode"] == "record_only"
    assert processing["state"] == "record_only_complete"
    assert processing["plan"] is None
    assert await echo.store.get_event_effect(saved.event_id, "planner") is None
    assert await echo.store.get_event_effect(saved.event_id, "main") is None
    assert await echo.store.get_session_control_state(echo.session.id) == control
    assert await echo.store.get_goal(echo.session.goal_id) == goal
    assert await echo.store.list_interventions(echo.session.id) == interventions
    assert await echo.store.get_event_effect(echo.prepared[0].event_id, "main") == echo.effect


async def test_replay_preserves_original_event_timestamp_goal_and_publication(echo):
    first = await record(echo)
    processing = await echo.store.get_event_processing(first.event_id)
    goal = Goal(
        id="next-human-goal", project_id=echo.session.project_id, title="New goal",
        objective="The next explicit human instruction", created_at=utcnow(), updated_at=utcnow(),
    )
    await echo.store.upsert_goal(goal)
    changed = await echo.store.attach_session_goal(
        echo.session.id, goal.id, expected_goal_id=echo.session.goal_id,
        replace_existing=True,
    )
    assert changed["changed"]
    current = await echo.store.get_session(echo.session.id)
    replay = echo.event.model_copy(deep=True)
    replay.ts += timedelta(seconds=1)
    replay.goal_id = "caller-goal"
    repeated = await record(echo, event=replay, session=current)
    assert repeated == first
    assert await echo.store.get_event_processing(first.event_id) == processing
    cursor = await echo.store.db.execute(
        "SELECT COUNT(*) AS total FROM event_publications WHERE event_id=?", (first.event_id,),
    )
    assert (await cursor.fetchone())["total"] == 1
    assert (await echo.store.get_session(echo.session.id)).goal_id == goal.id


@pytest.mark.parametrize("change", [
    "unknown_client", "spoofed_prefix", "changed_content", "truncated", "wrong_marker_id",
    "wrong_marker_hash", "missing_marker", "wrong_subscription", "wrong_epoch", "wrong_turn",
    "user_prompt", "message_body", "wrong_project", "wrong_sequence_scope",
    "claims_delivery", "wrong_endpoint",
])
async def test_forged_or_incomplete_echo_cannot_enter_record_only_path(echo, change):
    event, item = echo.event.model_copy(deep=True), copy.deepcopy(echo.item)
    if change == "unknown_client":
        item["clientId"] = "unknown-client"
    elif change == "spoofed_prefix":
        item["clientId"] = "pex-correction-" + "f" * 64
    elif change == "changed_content":
        item["content"][0]["text"] = "A different human instruction"
    elif change == "truncated":
        item["truncated"] = True
    elif change == "wrong_marker_id":
        event.metadata["pex_correction_observation"]["effect_id"] = "forged-effect"
    elif change == "wrong_marker_hash":
        event.metadata["pex_correction_observation"]["input_sha256"] = "0" * 64
    elif change == "missing_marker":
        del event.metadata["pex_correction_observation"]
    elif change == "wrong_subscription":
        event.metadata["subscription_id"] = "other-subscription"
    elif change == "wrong_epoch":
        event.metadata["connection_generation"] += 1
    elif change == "wrong_turn":
        event.metadata["vendor_turn_id"] = "other-turn"
    elif change == "user_prompt":
        event.event_type = EventType.USER_PROMPT
    elif change == "message_body":
        event.message_delta = "Untrusted message copied into the event"
    elif change == "wrong_project":
        event.project_id = "other-project"
    elif change == "wrong_sequence_scope":
        event.metadata["sequence_scope"] = "raw_frames"
    elif change == "claims_delivery":
        event.metadata["delivery_proven"] = True
    else:
        event.metadata["endpoint_identity"] = "other-endpoint"
    with pytest.raises(ValueError):
        await record(echo, event=event, item=item)
    await assert_absent(echo)


@pytest.mark.parametrize("change", ["directory", "origin"])
async def test_workspace_loss_prevents_echo_recording(echo, change):
    if change == "directory":
        workspace = echo.fixture[3].parent / "workspace"
        workspace.rename(workspace.with_name("preserved-workspace"))
        workspace.mkdir()
    else:
        path = echo.fixture[3]
        old = load_local_origin_choice(path)
        save_local_origin_choice(
            path, old.origin, expected_revision=old.revision, expected_choice_id=old.choice_id,
        )
    with pytest.raises(WorkspaceAuthorityError):
        await record(echo)
    await assert_absent(echo)


async def test_new_epoch_after_restart_can_attribute_old_attempt_but_not_dispatch(echo):
    current = await echo.store.get_session(echo.session.id)
    current.metadata["subscription_receipt"]["authorization_id"] = "new-attachment"
    current.metadata["subscription_receipt"]["connection_generation"] = 2
    revision = (await echo.store.get_session_control_state(current.id))["control_revision"]
    current = await publish(echo.fixture, session=current, expected_revision=revision)
    event, item, turn = observation(current, echo.correction)
    reopened = Store(echo.store.path, process_boot_id="new-observer-boot")
    await reopened.connect()
    try:
        saved = await record(
            echo, store=reopened, session=current, event=event, item=item, turn=turn,
        )
        assert saved.metadata["connection_generation"] == 2
        assert saved.metadata["pex_correction_observation"]["effect_id"] == echo.effect["effect_id"]
        historical = await reopened.get_event_effect(echo.prepared[0].event_id, "main")
        assert historical["payload"]["codex_correction"]["subscription_receipt"][
            "connection_generation"
        ] == 1
        assert historical == echo.effect
        grant = await reopened.validate_main_event_effect_dispatch(
            event_id=echo.prepared[0].event_id, owner=OWNER,
            effect_id=echo.effect["effect_id"], effect_version=echo.effect["version"],
            expected_action=echo.prepared[2]["action"],
        )
        assert not grant["granted"]
        assert (await reopened.get_event_processing(saved.event_id))["mode"] == "record_only"
    finally:
        await reopened.close()


async def test_insert_failure_rolls_back_event_processing_and_publication(echo):
    await echo.store.db.execute(
        "CREATE TRIGGER correction_echo_insert_fault BEFORE INSERT ON event_processing "
        "WHEN NEW.mode='record_only' "
        "BEGIN SELECT RAISE(ABORT, 'fixture echo processing failure'); END",
    )
    await echo.store.db.commit()
    with pytest.raises(sqlite3.IntegrityError, match="fixture echo processing failure"):
        await record(echo)
    await assert_absent(echo)
    await echo.store.db.execute("DROP TRIGGER correction_echo_insert_fault")
    await echo.store.db.commit()
    assert (await record(echo)).event_id == echo.event.event_id


@pytest.mark.parametrize("change", ["version", "state"])
async def test_attempt_race_between_loader_and_transaction_does_not_record(
    echo, monkeypatch, change,
):
    original = echo.store.list_codex_correction_attributions

    async def load_then_change(session):
        records = await original(session)
        update = "version=version+1" if change == "version" else "state='delivery_uncertain'"
        await echo.store.db.execute(
            f"UPDATE event_effects SET {update} WHERE effect_id=?", (echo.effect["effect_id"],),
        )
        await echo.store.db.commit()
        return records

    monkeypatch.setattr(echo.store, "list_codex_correction_attributions", load_then_change)
    with pytest.raises(ValueError, match="attempt changed"):
        await record(echo)
    await assert_absent(echo)
    monkeypatch.setattr(echo.store, "list_codex_correction_attributions", original)
    assert (await record(echo)).event_id == echo.event.event_id


async def test_workspace_revoked_after_initial_transaction_sample_is_not_committed(
    echo, monkeypatch,
):
    original = store_module._load_bound_session
    changed = False

    async def load_then_replace(*args, **kwargs):
        nonlocal changed
        result = await original(*args, **kwargs)
        if not changed:
            changed = True
            workspace = echo.fixture[3].parent / "workspace"
            workspace.rename(workspace.with_name("preserved-workspace"))
            workspace.mkdir()
        return result

    monkeypatch.setattr(store_module, "_load_bound_session", load_then_replace)
    with pytest.raises(WorkspaceAuthorityError):
        await record(echo)
    assert changed
    await assert_absent(echo)


@pytest.mark.parametrize("change", ["item", "turn"])
async def test_same_attempt_cannot_own_a_second_vendor_input(echo, change):
    first = await record(echo)
    event, item, turn = observation(
        echo.session, echo.correction, event_id="second-observation",
        turn_id="different-turn" if change == "turn" else echo.turn,
    )
    if change == "item":
        item["id"] = "different-item"
    event.metadata["pex_correction_observation"] = marker(echo.correction, item, turn)
    with pytest.raises(ValueError, match="different vendor input"):
        await record(echo, event=event, item=item, turn=turn)
    assert await echo.store.get_event(event.event_id) is None
    assert await echo.store.get_event_processing(event.event_id) is None
    assert await echo.store.get_event(first.event_id) == first
    assert await record(echo) == first


async def test_same_vendor_input_with_new_observation_id_is_still_record_only(echo):
    await record(echo)
    repeated = echo.event.model_copy(deep=True)
    repeated.event_id = "same-item-new-observation"
    repeated.metadata["ingress_sequence"] = 2
    saved = await record(echo, event=repeated)
    assert saved.event_id == repeated.event_id
    assert (await echo.store.get_event_processing(saved.event_id))["mode"] == "record_only"


async def test_competing_exact_echoes_commit_only_one_vendor_input(echo, monkeypatch):
    original = echo.store.list_codex_correction_attributions
    both_loaded = asyncio.Event()
    loaded = 0

    async def load_together(session):
        nonlocal loaded
        records = await original(session)
        loaded += 1
        if loaded == 2:
            both_loaded.set()
        await asyncio.wait_for(both_loaded.wait(), timeout=5)
        return records

    monkeypatch.setattr(echo.store, "list_codex_correction_attributions", load_together)
    second, item, turn = observation(echo.session, echo.correction, event_id="competing-echo")
    item["id"] = "competing-vendor-item"
    second.metadata["pex_correction_observation"] = marker(echo.correction, item, turn)
    results = await asyncio.gather(
        record(echo), record(echo, event=second, item=item, turn=turn),
        return_exceptions=True,
    )
    assert loaded == 2
    assert sum(isinstance(result, HarnessEvent) for result in results) == 1
    refused = [result for result in results if isinstance(result, ValueError)]
    assert len(refused) == 1 and "different vendor input" in str(refused[0])
    for event, result in zip((echo.event, second), results, strict=True):
        saved = await echo.store.get_event(event.event_id)
        processing = await echo.store.get_event_processing(event.event_id)
        if isinstance(result, HarnessEvent):
            assert saved == result
            assert processing["state"] == "record_only_complete"
        else:
            assert saved is None and processing is None
