"""Durable observer publication, using a real Store and no live harness."""

import asyncio
from datetime import UTC, datetime

import aiosqlite
import pytest
from pex_bridge.store import Store, _merge_event_session_projection
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession


@pytest.fixture
async def observer(tmp_path):
    store = Store(tmp_path / "observer.sqlite")
    await store.connect()
    session = HarnessSession(
        id="codex:thread-observer",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-observer",
        project_id=str(tmp_path),
        cwd=str(tmp_path),
        status=SessionStatus.IDLE,
        metadata={"connection_kind": "codex_shared", "subscription_receipt": {"id": "new"}},
        capabilities={"send_message": False, "observe_messages": True},
    )
    binding = await store.project_binding_for_authority(session.project_id)
    try:
        yield store, session, binding
    finally:
        await store.close()


async def _publish(store, session, binding, revision=None):
    return await store.publish_observer_session(
        session,
        expected_control_revision=revision,
        expected_project_binding=binding,
    )


@pytest.mark.asyncio
async def test_new_observer_has_no_invented_activity_and_rejects_concurrent_insert(observer):
    store, session, binding = observer
    results = await asyncio.gather(
        _publish(store, session, binding),
        _publish(store, session, binding),
        return_exceptions=True,
    )
    assert sum(isinstance(value, HarnessSession) for value in results) == 1
    assert sum(isinstance(value, ValueError) for value in results) == 1
    saved = await store.get_session(session.id)
    assert saved.last_activity is None
    assert saved.metadata["subscription_receipt"] == {"id": "new"}


@pytest.mark.asyncio
async def test_attachment_receipt_replaces_older_observer_without_new_activity(observer):
    store, session, binding = observer
    actual_activity = datetime(2026, 9, 1, tzinfo=UTC)
    old = session.model_copy(deep=True)
    old.last_activity = actual_activity
    old.supervision_paused = True
    old.branch = "keep-human-branch"
    old.metadata = {
        "connection_kind": "old",
        "human_decision_attention": "keep",
        "unrelated": "keep",
    }
    old.capabilities = {"send_message": True}
    await store.upsert_session(old)
    before = await store.get_session_control_state(old.id)
    # Reproduce why the normal discovery API is not an attachment commit.
    await store.upsert_session(session.model_copy(deep=True))
    assert (await store.get_session(old.id)).metadata["connection_kind"] == "old"
    saved = await _publish(store, session, binding, before["control_revision"])
    assert saved == await store.get_session(old.id)
    assert saved.last_activity == actual_activity
    assert saved.supervision_paused is True
    assert saved.branch == "keep-human-branch"
    assert saved.metadata["human_decision_attention"] == "keep"
    assert saved.metadata["unrelated"] == "keep"
    assert saved.metadata["connection_kind"] == "codex_shared"
    assert saved.capabilities["send_message"] is False
    assert session.last_activity is None  # caller's observation stays untouched
    assert (await store.get_session_control_state(old.id))["control_revision"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["pause", "cwd", "cwd_aba"])
async def test_stale_publication_cannot_rollback_control_or_target(observer, change, tmp_path):
    store, session, binding = observer
    await store.upsert_session(session)
    before = await store.get_session_control_state(session.id)
    changed = session.model_copy(deep=True)
    if change == "pause":
        changed.supervision_paused = True
        await store.upsert_session(changed, allow_supervision_change=True)
    else:
        changed.cwd = str(tmp_path / "different-target")
        await store.upsert_session(changed)
        if change == "cwd_aba":
            await store.upsert_session(session)
    durable_before = await store.get_session_control_state(session.id)
    with pytest.raises(ValueError, match="control changed"):
        await _publish(store, session, binding, before["control_revision"])
    assert await store.get_session_control_state(session.id) == durable_before


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["vendor", "harness", "cwd", "project"])
async def test_current_revision_does_not_authorize_a_different_target(observer, change, tmp_path):
    store, session, binding = observer
    await _publish(store, session, binding)
    wrong = session.model_copy(deep=True)
    if change == "vendor":
        wrong.vendor_session_id = "other-worker"
    elif change == "harness":
        wrong.harness_type = HarnessType.CURSOR
    elif change == "cwd":
        wrong.cwd = str(tmp_path / "other")
    else:
        wrong.project_id = "unrelated-project"
    with pytest.raises(ValueError, match="identity changed|target changed"):
        await _publish(store, wrong, binding, 0)
    assert await store.get_session(session.id) == session


@pytest.mark.asyncio
async def test_detach_snapshot_cannot_restore_old_activity_or_control(observer):
    store, session, binding = observer
    saved = await _publish(store, session, binding)
    saved.last_activity = datetime.now(UTC)
    await store.upsert_session(saved)
    detached = session.model_copy(deep=True)
    detached.status = SessionStatus.DETACHED
    detached.capabilities = {"send_message": False, "observe_messages": False}
    result = await _publish(store, detached, binding, 0)
    assert result.status == SessionStatus.DETACHED
    assert result.last_activity == saved.last_activity
    assert result.capabilities["observe_messages"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", [True, -1, "0"])
async def test_invalid_control_revision_is_rejected_before_mutation(observer, revision):
    store, session, binding = observer
    with pytest.raises(ValueError, match="revision is invalid"):
        await _publish(store, session, binding, revision)
    assert await store.get_session(session.id) is None


@pytest.mark.asyncio
async def test_observation_does_not_create_a_user_goal_or_pause_policy(observer):
    store, session, binding = observer
    session.supervision_paused = True
    with pytest.raises(ValueError, match="cannot assign user control"):
        await _publish(store, session, binding)
    assert await store.get_session(session.id) is None


@pytest.mark.asyncio
async def test_publication_preserves_real_human_goal(observer):
    store, session, binding = observer
    now = datetime.now(UTC)
    goal = Goal(
        id="human-goal",
        project_id=session.project_id,
        title="Real goal",
        objective="Preserve human intent",
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    current = session.model_copy(update={"goal_id": goal.id, "supervision_paused": True})
    await store.upsert_session(current, allow_goal_change=True)
    result = await _publish(store, session, binding, 0)
    assert result.goal_id == goal.id
    assert result.supervision_paused is True
    assert (await store.get_session_for_authority(session.id)).goal_id == goal.id


@pytest.mark.asyncio
async def test_precommit_failure_rolls_back_without_publishing(observer, monkeypatch):
    store, session, binding = observer

    async def fail_commit(connection):
        raise RuntimeError("fixture commit failure")

    monkeypatch.setattr(aiosqlite.Connection, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="fixture commit failure"):
        await _publish(store, session, binding)
    assert await store.get_session(session.id) is None


def _observation_event(session, *, event_id="observer-live"):
    now = datetime.now(UTC)
    return HarnessEvent(
        event_id=event_id,
        ts=now,
        harness_type=session.harness_type,
        session_id=session.id,
        project_id=session.project_id,
        event_type=EventType.STATUS,
        metadata={"pex_observer_snapshot": {
            "schema": "pex.codex-live-observation.v1",
            "subscription_receipt": dict(session.metadata["subscription_receipt"]),
            "status": SessionStatus.WORKING.value,
            "last_activity": now.isoformat(),
            "observation_coverage": {"state": "observing", "last_observed_live_sequence": 1},
        }},
    )


@pytest.mark.asyncio
async def test_trusted_live_projection_advances_coverage_from_canonical_event(observer):
    store, baseline, binding = observer
    await _publish(store, baseline, binding)
    event = _observation_event(baseline)
    accepted = await store.accept_pipeline_event(event, session_snapshot=baseline)
    planned = baseline.model_copy(deep=True)
    planned.status = SessionStatus.WORKING
    planned.last_activity = event.ts
    planned.metadata["observation_coverage"] = {"forged_plan_coverage": True}

    merged = _merge_event_session_projection(
        accepted["processing"], baseline, planned, event=accepted["event"],
    )

    assert merged.status == SessionStatus.WORKING
    assert merged.last_activity == event.ts
    assert merged.metadata["observation_coverage"] == event.metadata[
        "pex_observer_snapshot"
    ]["observation_coverage"]
    assert "observation_coverage" not in baseline.metadata


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["receipt", "cwd"])
async def test_old_observer_plan_preserves_fresh_incarnation_even_equal_state(
    observer, changed, tmp_path,
):
    store, baseline, binding = observer
    await _publish(store, baseline, binding)
    event = _observation_event(baseline)
    accepted = await store.accept_pipeline_event(event, session_snapshot=baseline)
    current = baseline.model_copy(deep=True)
    current.metadata["observation_coverage"] = {"state": "new-incarnation"}
    if changed == "receipt":
        current.metadata["subscription_receipt"] = {"id": "replacement"}
    else:
        current.cwd = str(tmp_path / "new-target")
    planned = baseline.model_copy(deep=True)
    planned.status = SessionStatus.ERROR
    planned.last_activity = event.ts
    planned.capabilities = {"send_message": True}
    planned.metadata["observation_coverage"] = {"state": "old-plan"}

    merged = _merge_event_session_projection(
        accepted["processing"], current, planned, event=accepted["event"],
    )

    assert merged == current


@pytest.mark.asyncio
async def test_observer_plan_cannot_rollback_newer_coverage(observer):
    store, baseline, binding = observer
    await _publish(store, baseline, binding)
    event = _observation_event(baseline)
    accepted = await store.accept_pipeline_event(event, session_snapshot=baseline)
    current = baseline.model_copy(deep=True)
    current.metadata["observation_coverage"] = {"state": "disconnected", "reason": "later"}
    planned = baseline.model_copy(deep=True)
    planned.metadata["observation_coverage"] = {"state": "old-observing"}

    merged = _merge_event_session_projection(
        accepted["processing"], current, planned, event=accepted["event"],
    )

    assert merged.metadata["observation_coverage"] == current.metadata["observation_coverage"]


@pytest.mark.asyncio
async def test_untrusted_plan_cannot_add_observer_coverage(observer):
    store, baseline, binding = observer
    await _publish(store, baseline, binding)
    event = _observation_event(baseline)
    event.metadata.clear()
    accepted = await store.accept_pipeline_event(event, session_snapshot=baseline)
    planned = baseline.model_copy(deep=True)
    planned.metadata["observation_coverage"] = {"state": "invented"}

    merged = _merge_event_session_projection(
        accepted["processing"], baseline, planned, event=accepted["event"],
    )

    assert "observation_coverage" not in merged.metadata


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["missing", "receipt", "snapshot_receipt", "cwd"])
async def test_observer_acceptance_rechecks_durable_receipt_after_pipeline_check(
    observer, changed, tmp_path,
):
    store, baseline, binding = observer
    event = _observation_event(baseline)
    snapshot = baseline.model_copy(deep=True)
    if changed != "missing":
        await _publish(store, baseline, binding)
    if changed == "receipt":
        replacement = baseline.model_copy(deep=True)
        replacement.metadata["subscription_receipt"] = {"id": "replacement"}
        await _publish(store, replacement, binding, 0)
    elif changed == "snapshot_receipt":
        snapshot.metadata["subscription_receipt"] = {"id": "forged"}
    elif changed == "cwd":
        replacement = baseline.model_copy(update={"cwd": str(tmp_path / "new-target")})
        await store.upsert_session(replacement)

    with pytest.raises(ValueError, match="trusted observer"):
        await store.accept_pipeline_event(event, session_snapshot=snapshot)

    assert await store.get_event_processing(event.event_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("schema", "wrong"), ("status", {}), ("last_activity", "not-ISO"),
    ("last_activity", "2026-09-05T00:00:00"), ("observation_coverage", None),
])
async def test_malformed_observer_marker_cannot_be_accepted(observer, field, value):
    store, baseline, binding = observer
    await _publish(store, baseline, binding)
    event = _observation_event(baseline)
    event.metadata["pex_observer_snapshot"][field] = value

    with pytest.raises(ValueError, match="trusted observer"):
        await store.accept_pipeline_event(event, session_snapshot=baseline)

    assert await store.get_event_processing(event.event_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("replace_connection", [False, True])
async def test_plan_transaction_loads_canonical_observer_event(observer, replace_connection):
    from test_event_processing_store import _plan_envelope

    store, baseline, binding = observer
    await _publish(store, baseline, binding)
    event = _observation_event(baseline)
    await store.accept_pipeline_event(event, session_snapshot=baseline)
    await store.claim_event_processing(event.event_id, owner="observer-review")
    current = baseline.model_copy(deep=True)
    if replace_connection:
        current.metadata["subscription_receipt"] = {"id": "replacement"}
        current.metadata["observation_coverage"] = {"state": "new"}
        await _publish(store, current, binding, 0)
    planned = baseline.model_copy(deep=True)
    planned.status = SessionStatus.WORKING
    planned.last_activity = event.ts
    planned.metadata["observation_coverage"] = {"forged_plan_coverage": True}

    await store.commit_event_plan(
        event_id=event.event_id,
        owner="observer-review",
        plan=_plan_envelope(event),
        session=planned,
        receipt={
            "schema": "pex.event-processing.receipt.v1",
            "event_id": event.event_id,
            "status": "complete",
        },
    )

    saved = await store.get_session(baseline.id)
    if replace_connection:
        assert saved == current
    else:
        assert saved.status == SessionStatus.WORKING
        assert saved.metadata["observation_coverage"] == event.metadata[
            "pex_observer_snapshot"
        ]["observation_coverage"]
