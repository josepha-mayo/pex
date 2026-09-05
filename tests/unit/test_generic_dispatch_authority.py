"""Real Store regressions; no provider, harness, or worker effects are invoked."""

from datetime import timedelta

import pytest
from pex_bridge.store import Store
from pex_protocol.enums import EventType, SessionStatus
from test_event_processing_store import _bound_event, _commit_worker_plan, _event


@pytest.fixture
async def planned(tmp_path):
    store = Store(tmp_path / "authority.sqlite")
    await store.connect()
    try:
        event, session = await _bound_event(store, "authority-trigger")
        await store.accept_pipeline_event(event, session_snapshot=session)
        await store.claim_event_processing(event.event_id, owner="authority-review")
        await _commit_worker_plan(store, event, session, owner="authority-review")
        yield store, event, session
    finally:
        await store.close()


async def _claim(store, event):
    return await store.claim_main_event_effect(
        event_id=event.event_id, owner="authority-review"
    )


async def _assert_denied(store, event, reason):
    result = await _claim(store, event)
    assert result["granted"] is False
    assert result["reason"] == reason
    effect = await store.get_event_effect(event.event_id, "main")
    assert effect["state"] == "reserved"
    assert effect["dispatch_started_at"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("restore_original", [False, True])
async def test_same_goal_intent_change_invalidates_older_action(planned, restore_original):
    store, event, _ = planned
    original = await store.get_goal(event.goal_id)
    await store.upsert_goal(original.model_copy(update={"objective": "A new human objective"}))
    if restore_original:
        await store.upsert_goal(original)
    await _assert_denied(store, event, "goal_intent_changed_before_dispatch")


@pytest.mark.asyncio
async def test_pause_resume_invalidates_older_action(planned):
    store, event, session = planned
    await store.upsert_session(
        session.model_copy(update={"supervision_paused": True}), allow_supervision_change=True
    )
    await store.upsert_session(session, allow_supervision_change=True)
    await _assert_denied(store, event, "session_authority_changed_before_dispatch")


@pytest.mark.asyncio
@pytest.mark.parametrize("record_only", [False, True])
async def test_newer_prompt_invalidates_action_even_with_older_vendor_timestamp(
    planned, record_only
):
    store, event, session = planned
    prompt = _event("later-human-input", goal_id=event.goal_id).model_copy(
        update={
            "event_type": EventType.USER_PROMPT,
            "message_delta": "Wait, do something else.",
            "ts": event.ts - timedelta(days=1),
        }
    )
    if record_only:
        await store.add_event(prompt)
    else:
        await store.accept_pipeline_event(prompt, session_snapshot=session)
    await _assert_denied(store, event, "newer_human_input_before_dispatch")


@pytest.mark.asyncio
async def test_routine_discovery_refresh_does_not_invalidate_current_authority(planned):
    store, event, session = planned
    await store.upsert_session(
        session.model_copy(update={"metadata": {"discovery_generation": "next-ui-refresh"}})
    )
    assert (await _claim(store, event))["granted"] is True


@pytest.mark.asyncio
async def test_presentation_only_update_does_not_invalidate_current_authority(planned):
    store, event, session = planned
    await store.upsert_session(session.model_copy(update={"status": SessionStatus.IDLE}))
    assert (await _claim(store, event))["granted"] is True
    assert (await _claim(store, event))["granted"] is False


@pytest.mark.asyncio
async def test_duplicate_acceptance_does_not_refresh_stale_authority(planned):
    store, event, session = planned
    before = await store.get_event_processing(event.event_id)
    await store.upsert_session(
        session.model_copy(update={"supervision_paused": True}), allow_supervision_change=True
    )
    await store.upsert_session(session, allow_supervision_change=True)
    replay = await store.accept_pipeline_event(event, session_snapshot=session)
    assert replay["created"] is False
    assert (
        replay["processing"]["accepted_session_authority"]
        == before["accepted_session_authority"]
    )
    await _assert_denied(store, event, "session_authority_changed_before_dispatch")


@pytest.mark.asyncio
async def test_migration_does_not_backfill_authority_for_old_unfinished_plans(planned):
    store, event, _ = planned
    await store.db.execute("ALTER TABLE event_processing DROP COLUMN accepted_session_authority")
    await store.db.commit()
    await store._migrate_event_processing()
    processing = await store.get_event_processing(event.event_id)
    assert processing["accepted_session_authority"] is None
    await _assert_denied(store, event, "accepted_session_authority_missing")


@pytest.mark.asyncio
async def test_plan_commit_does_not_refresh_acceptance_authority(tmp_path):
    store = Store(tmp_path / "before-plan.sqlite")
    await store.connect()
    try:
        event, session = await _bound_event(store, "changed-before-planning")
        await store.accept_pipeline_event(event, session_snapshot=session)
        await store.upsert_session(
            session.model_copy(update={"supervision_paused": True}), allow_supervision_change=True
        )
        await store.upsert_session(session, allow_supervision_change=True)
        await store.claim_event_processing(event.event_id, owner="authority-review")
        await _commit_worker_plan(store, event, session, owner="authority-review")
        await _assert_denied(store, event, "session_authority_changed_before_dispatch")
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_later_worker_activity_does_not_count_as_new_human_intent(planned):
    store, event, session = planned
    await store.accept_pipeline_event(
        _event("later-worker-activity", goal_id=event.goal_id), session_snapshot=session
    )
    assert (await _claim(store, event))["granted"] is True


@pytest.mark.asyncio
async def test_other_session_prompt_does_not_block_this_worker(planned):
    store, event, session = planned
    other = session.model_copy(update={"id": "codex:other", "vendor_session_id": "other"})
    await store.upsert_session(other)
    await store.accept_pipeline_event(
        _event("other-human-input", session_id=other.id, goal_id=event.goal_id).model_copy(
            update={"event_type": EventType.USER_PROMPT}
        ),
        session_snapshot=other,
    )
    assert (await _claim(store, event))["granted"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("change_before_plan", [False, True])
async def test_working_target_cannot_be_restored_by_aba_or_stale_plan(tmp_path, change_before_plan):
    store = Store(tmp_path / "target.sqlite")
    await store.connect()
    try:
        event, session = await _bound_event(store, "target-change")
        session.cwd = "C:/repo"
        await store.upsert_session(session)
        initial = await store.get_session_control_state(session.id)
        await store.accept_pipeline_event(event, session_snapshot=session)
        await store.claim_event_processing(event.event_id, owner="authority-review")
        changed = session.model_copy(update={"cwd": "C:/different-target"})
        if change_before_plan:
            await store.upsert_session(changed)
            await _commit_worker_plan(store, event, session, owner="authority-review")
            live = await store.get_session(session.id)
            assert live.cwd == changed.cwd
        else:
            await _commit_worker_plan(store, event, session, owner="authority-review")
            await store.upsert_session(changed)
            await store.upsert_session(session)
            live = await store.get_session(session.id)
            assert live.cwd == session.cwd
        current = await store.get_session_control_state(session.id)
        assert current["control_revision"] > initial["control_revision"]
        await _assert_denied(store, event, "session_authority_changed_before_dispatch")
    finally:
        await store.close()
