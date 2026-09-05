"""Trusted persisted workspace authority and no-provider recovery boundaries."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge import store as store_module
from pex_bridge.store import MCP_VERIFY_CLAIM_TOOL, Store
from pex_bridge.workspace_binding import WorkspaceAuthorityError
from pex_protocol.enums import SessionStatus
from pex_protocol.goal import Goal
from test_event_processing_store import _commit_worker_plan, _planned_intervention
from test_store_mcp_verify_claim import _commit, _verification_artifacts
from test_workspace_continuity_store_review import _event, _invalidate
from test_workspace_publication import publication as _publication_fixture
from test_workspace_publication import publish

publication = _publication_fixture


async def test_valid_public_guard_returns_only_persisted_server_path(publication):
    store, session, binding, origin_path = publication
    selected_path = origin_path.with_name("explicit-server-selected.json")
    origin_path.rename(selected_path)
    session.metadata["local_origin_path"] = "C:/untrusted/client/path.json"
    await store.publish_observer_session(
        session,
        expected_control_revision=None,
        expected_project_binding=binding.project_binding,
        expected_workspace=binding,
        local_origin_path=selected_path,
    )
    witness = await store.require_session_workspace_current(session)
    assert witness == (binding, selected_path)
    assert witness[0] is not binding


@pytest.mark.parametrize("change", [None, "directory", "origin", "locator"])
async def test_reopened_store_revalidates_persisted_witness(publication, change):
    store, session, binding, origin_path = publication
    await publish(publication)
    before = await store.get_session_control_state(session.id)
    if change:
        await _invalidate(publication, change)
    recovered = Store(store.path)
    await recovered.connect()
    try:
        if change:
            with pytest.raises(WorkspaceAuthorityError):
                await recovered.require_session_workspace_current(session)
        else:
            assert await recovered.require_session_workspace_current(session) == (
                binding,
                origin_path,
            )
        assert await recovered.get_session_control_state(session.id) == before
        assert await recovered.list_interventions(session.id) == []
    finally:
        await recovered.close()


@pytest.mark.parametrize("change", ["missing-witness", "missing-key", "path", "receipt", "binding"])
async def test_unavailable_or_mismatched_durable_witness_fails_closed(publication, change):
    store, session, _, _ = publication
    await publish(publication)
    if change == "missing-witness":
        await store.db.execute(
            "DELETE FROM observer_workspace_authorities WHERE session_id = ?", (session.id,)
        )
    elif change == "missing-key":
        altered = session.model_copy(deep=True)
        del altered.metadata["workspace_binding"]
        await store.db.execute(
            "UPDATE sessions SET json = ? WHERE id = ?", (altered.model_dump_json(), session.id)
        )
    else:
        column, value = {
            "path": ("local_origin_path", "relative/client-path.json"),
            "receipt": ("subscription_json", '{"authorization_id":"foreign"}'),
            "binding": ("project_binding", "legacy:foreign"),
        }[change]
        await store.db.execute(
            f"UPDATE observer_workspace_authorities SET {column} = ? WHERE session_id = ?",
            (value, session.id),
        )
    await store.db.commit()
    with pytest.raises(WorkspaceAuthorityError):
        await store.require_session_workspace_current(session)


async def test_content_edit_does_not_change_workspace_authority(publication):
    store, session, binding, origin_path = publication
    await publish(publication)
    (origin_path.parent / "workspace" / "normal-edit.txt").write_text(
        "ordinary work", encoding="utf-8"
    )
    assert await store.require_session_workspace_current(session) == (binding, origin_path)


async def test_failed_witness_publication_leaves_no_session_or_authority(publication, monkeypatch):
    store, session, _, _ = publication
    original = store_module.require_current_workspace
    calls = 0

    def fail_second(binding, path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise WorkspaceAuthorityError("changed at publication commit")
        return original(binding, path)

    monkeypatch.setattr(store_module, "require_current_workspace", fail_second)
    with pytest.raises(WorkspaceAuthorityError):
        await publish(publication)
    assert await store.get_session(session.id) is None
    cursor = await store.db.execute("SELECT COUNT(*) FROM observer_workspace_authorities")
    assert (await cursor.fetchone())[0] == 0


async def test_detached_receipt_is_retained_but_does_not_authorize_work(publication):
    store, session, binding, _ = publication
    await publish(publication)
    control = await store.get_session_control_state(session.id)
    detached = session.model_copy(deep=True)
    detached.status = SessionStatus.DETACHED
    await store.publish_observer_session(
        detached,
        expected_control_revision=control["control_revision"],
        expected_project_binding=binding.project_binding,
    )
    with pytest.raises(WorkspaceAuthorityError):
        await store.require_session_workspace_current(detached)
    with pytest.raises(WorkspaceAuthorityError):
        await store.accept_pipeline_event(_event(session), session_snapshot=session)
    cursor = await store.db.execute("SELECT COUNT(*) FROM observer_workspace_authorities")
    assert (await cursor.fetchone())[0] == 1


async def test_truly_unbound_legacy_cannot_mint_observer_metadata(publication):
    store, session, _, _ = publication
    await store.upsert_session(session)
    saved = await store.get_session(session.id)
    assert "workspace_binding" not in saved.metadata
    assert "subscription_receipt" not in saved.metadata
    assert await store.require_session_workspace_current(saved) is None
    with pytest.raises(WorkspaceAuthorityError):
        await store.require_session_workspace_current(session)


async def _reserve_planner(store, session):
    event = _event(session)
    await store.accept_pipeline_event(event, session_snapshot=session)
    await store.claim_event_processing(event.event_id, owner="recovery-owner")
    payload = {"event_id": event.event_id}
    await store.reserve_event_effect(
        event_id=event.event_id,
        effect_key="planner",
        kind="supervisor_decision",
        target_session_id=session.id,
        payload=payload,
        request_hash=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        owner="recovery-owner",
    )
    return event


async def test_valid_planner_dispatch_grants_only_database_transition(publication):
    store, session, _, _ = publication
    await publish(publication)
    event = await _reserve_planner(store, session)
    result = await store.start_event_effect_dispatch(
        event_id=event.event_id,
        effect_key="planner",
        owner="recovery-owner",
    )
    assert result["granted"] is True
    assert (await store.get_event_processing(event.event_id))["state"] == "decision_dispatching"
    # No actual provider is called. An already granted dispatch cannot be falsely
    # settled as unexecuted after a later filesystem change.
    await _invalidate(publication, "directory")
    with pytest.raises(ValueError):
        await store.fail_event_processing(
            event_id=event.event_id,
            owner="recovery-owner",
            code="workspace_authority_changed",
        )


async def test_stale_reserved_planner_settlement_is_durable_and_unblocks_queue(publication):
    store, session, _, _ = publication
    await publish(publication)
    event = await _reserve_planner(store, session)
    await _invalidate(publication, "origin")
    result = await store.start_event_effect_dispatch(
        event_id=event.event_id,
        effect_key="planner",
        owner="recovery-owner",
    )
    assert result["granted"] is False
    assert result["reason"] == "workspace_authority_changed"
    failed = await store.fail_event_processing(
        event_id=event.event_id,
        owner="recovery-owner",
        code="workspace_authority_changed",
    )
    assert failed["state"] == "failed"
    assert (await store.get_event_effect(event.event_id, "planner"))["state"] == "skipped"
    assert await store.list_recoverable_event_processing() == []
    assert await store.get_event(event.event_id) == event


async def test_dispatch_final_sample_rolls_back_unpublished_dispatch_marker(
    publication, monkeypatch
):
    store, session, _, _ = publication
    await publish(publication)
    event = await _reserve_planner(store, session)
    original = store_module._require_processing_workspace_current
    calls = 0

    async def change_before_final_sample(tx, processing):
        nonlocal calls
        calls += 1
        if calls == 2:
            await _invalidate(publication, "directory")
        await original(tx, processing)

    monkeypatch.setattr(
        store_module, "_require_processing_workspace_current", change_before_final_sample
    )
    result = await store.start_event_effect_dispatch(
        event_id=event.event_id,
        effect_key="planner",
        owner="recovery-owner",
    )
    assert result["granted"] is False
    assert result["reason"] == "workspace_authority_changed"
    assert calls == 2
    assert (await store.get_event_effect(event.event_id, "planner"))["state"] == "reserved"
    assert (await store.get_event_processing(event.event_id))["state"] == "planning"


async def test_planned_main_effect_is_not_granted_after_workspace_change(publication):
    store, session, _, _ = publication
    session.capabilities = {"send_message": True}
    await publish(publication)
    await _attach_goal(store, session)
    event = _event(session)
    await store.accept_pipeline_event(event, session_snapshot=session)
    await store.claim_event_processing(event.event_id, owner="recovery-owner")
    await _commit_worker_plan(store, event, session, owner="recovery-owner")
    await _invalidate(publication, "directory")
    result = await store.claim_main_event_effect(event_id=event.event_id, owner="recovery-owner")
    assert result["granted"] is False
    assert result["reason"] == "workspace_authority_changed"
    assert (await store.get_event_effect(event.event_id, "main"))["state"] == "reserved"


async def _attach_goal(store, session):
    now = datetime.now(UTC)
    goal = Goal(
        id="workspace-continuity-goal",
        project_id=session.project_id,
        title="Continuous authority",
        objective="Keep actual worker outcomes honest",
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    await store.attach_session_goal(session.id, goal.id, expected_goal_id=None)
    session.goal_id = goal.id
    return goal


@pytest.mark.parametrize("change_at", ["before-finalization", "after-processing-update"])
async def test_known_delivery_finalizes_after_workspace_loss_without_session_projection(
    publication, monkeypatch, change_at,
):
    store, session, _, _ = publication
    session.capabilities = {"send_message": True}
    await publish(publication)
    await _attach_goal(store, session)
    event = _event(session)
    await store.accept_pipeline_event(event, session_snapshot=session)
    await store.claim_event_processing(event.event_id, owner="recovery-owner")
    await _commit_worker_plan(store, event, session, owner="recovery-owner")
    dispatch = await store.claim_main_event_effect(event_id=event.event_id, owner="recovery-owner")
    assert dispatch["granted"] is True
    calls = 0
    if change_at == "before-finalization":
        await _invalidate(publication, "origin")
    else:
        original = store_module._require_processing_workspace_current

        async def change_before_final_projection(tx, processing):
            nonlocal calls
            calls += 1
            if calls == 2:
                await _invalidate(publication, "origin")
            return await original(tx, processing)

        monkeypatch.setattr(
            store_module, "_require_processing_workspace_current", change_before_final_projection
        )
    before = await store.get_session_control_state(session.id)
    projected = session.model_copy(deep=True)
    projected.status = SessionStatus.WORKING
    projected.last_activity = datetime.now(UTC)
    delivered = _planned_intervention(event).model_copy(update={"result": "sent"})
    receipt = {
        "schema": "pex.event-processing.receipt.v1",
        "event_id": event.event_id,
        "status": "complete",
        "effect_state": "delivered",
        "effect_result": {"outcome": "sent"},
        "effect_id": dispatch["effect"]["effect_id"],
        "downstream_operation_id": "fake-vendor-receipt",
        "intervention": delivered.model_dump(mode="json"),
    }
    final = await store.finalize_event_processing(
        event_id=event.event_id,
        effect_state="delivered",
        effect_result={"outcome": "sent"},
        intervention=delivered,
        receipt=receipt,
        session=projected,
        downstream_operation_id="fake-vendor-receipt",
    )
    assert final["state"] == "complete"
    assert final["receipt"] == receipt
    assert await store.get_session_control_state(session.id) == before
    assert (await store.get_event_effect(event.event_id, "main"))["state"] == "delivered"
    if change_at == "after-processing-update":
        assert calls == 2


@pytest.mark.parametrize("change", [None, "directory", "late-origin"])
async def test_claim_verification_commit_checks_workspace_after_awaits(
    publication, monkeypatch, change
):
    store, session, _, _ = publication
    await publish(publication)
    goal = await _attach_goal(store, session)
    now = datetime.now(UTC)
    principal_id = "workspace-verification-principal"
    await store.issue_mcp_principal(
        principal_id=principal_id,
        session_id=session.id,
        goal_id=goal.id,
        project_id=session.project_id,
        vendor_session_id=session.vendor_session_id,
        harness_type=session.harness_type.value,
        scopes=["mcp:read", MCP_VERIFY_CLAIM_TOOL],
        token_digest=hashlib.sha256(b"temporary-fixture-token").hexdigest(),
        issued_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(hours=1),
    )
    artifacts = _verification_artifacts(
        "workspace",
        session,
        goal,
        principal_id=principal_id,
        outcome="uncertain",
    )
    if change == "directory":
        await _invalidate(publication, "directory")
    elif change == "late-origin":
        original = store_module._insert_bound_intervention

        async def change_after_authority_reads(tx, intervention):
            await original(tx, intervention)
            await _invalidate(publication, "origin")

        monkeypatch.setattr(
            store_module, "_insert_bound_intervention", change_after_authority_reads
        )
    if change:
        with pytest.raises(WorkspaceAuthorityError):
            await _commit(store, principal_id, "workspace-verify-request-1", (), artifacts)
        assert await store.get_event(artifacts[0].event_id) is None
        assert await store.list_interventions(session.id) == []
    else:
        result = await _commit(store, principal_id, "workspace-verify-request-1", (), artifacts)
        assert result["created"] is True
        assert await store.get_event(artifacts[0].event_id) is not None
