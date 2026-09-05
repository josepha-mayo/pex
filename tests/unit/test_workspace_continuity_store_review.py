"""Desired continuous-authority regressions; temporary SQLite/files only."""

import hashlib
import json
from datetime import UTC, datetime

import pytest
from pex_bridge.local_origin_config import save_local_origin_choice
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.session import HarnessEvent
from test_event_processing_store import _plan_envelope
from test_workspace_publication import publication as _publication_fixture
from test_workspace_publication import publish

publication = _publication_fixture


def _event(session, *, observer=True):
    event = HarnessEvent(
        event_id="workspace-continuity-event",
        ts=datetime.now(UTC),
        harness_type=HarnessType.CODEX,
        session_id=session.id,
        project_id=session.project_id,
        event_type=EventType.AGENT_RESPONSE,
        message_delta="Observed work continues.",
    )
    if observer:
        event.metadata["pex_observer_snapshot"] = {
            "schema": "pex.codex-live-observation.v1",
            "subscription_receipt": dict(session.metadata["subscription_receipt"]),
            "status": session.status.value,
            "last_activity": None,
            "observation_coverage": {},
        }
        if "workspace_binding" in session.metadata:
            event.metadata["pex_observer_snapshot"]["workspace_binding"] = session.metadata[
                "workspace_binding"
            ]
    return event


async def _invalidate(fixture, change):
    store, _, binding, origin_path = fixture
    if change == "origin":
        save_local_origin_choice(
            origin_path,
            binding.origin_choice.origin,
            expected_revision=binding.origin_choice.revision,
            expected_choice_id=binding.origin_choice.choice_id,
        )
    elif change == "directory":
        directory = origin_path.parent / "workspace"
        directory.rename(origin_path.parent / "preserved-workspace")
        directory.mkdir()
    else:
        await store.db.execute(
            "DELETE FROM project_locators WHERE fingerprint = ?",
            (binding.locator.fingerprint,),
        )
        await store.db.commit()


@pytest.mark.parametrize("change", ["origin", "directory", "locator"])
async def test_stale_workspace_cannot_accept_new_observer_work(publication, change):
    store, session, _, _ = publication
    await publish(publication)
    await _invalidate(publication, change)
    event = _event(session)
    with pytest.raises((ValueError, PermissionError)):
        await store.accept_pipeline_event(event, session_snapshot=session)
    assert await store.get_event(event.event_id) is None


@pytest.mark.parametrize("change", ["drop", "replace"])
async def test_observer_acceptance_cannot_lose_workspace_snapshot(publication, change):
    store, session, _, _ = publication
    await publish(publication)
    incoming = session.model_copy(deep=True)
    if change == "drop":
        del incoming.metadata["workspace_binding"]
    else:
        incoming.metadata["workspace_binding"]["project_id"] = "forged-project"
    with pytest.raises((ValueError, PermissionError)):
        await store.accept_pipeline_event(_event(session), session_snapshot=incoming)


@pytest.mark.parametrize("change", ["origin", "directory", "locator"])
async def test_accepted_plan_cannot_project_after_workspace_change(publication, change):
    store, session, _, _ = publication
    await publish(publication)
    event = _event(session)
    await store.accept_pipeline_event(event, session_snapshot=session)
    await store.claim_event_processing(event.event_id, owner="review-owner")
    await _invalidate(publication, change)
    before = await store.get_session_control_state(session.id)
    planned = session.model_copy(deep=True)
    planned.status = SessionStatus.WORKING
    with pytest.raises((ValueError, PermissionError)):
        await store.commit_event_plan(
            event_id=event.event_id,
            owner="review-owner",
            plan=_plan_envelope(event),
            session=planned,
            receipt={
                "schema": "pex.event-processing.receipt.v1",
                "event_id": event.event_id,
                "status": "complete",
                "intervention": None,
            },
        )
    assert await store.get_session_control_state(session.id) == before


@pytest.mark.parametrize("change", ["drop", "replace"])
async def test_generic_session_upsert_cannot_erase_workspace_receipt(publication, change):
    store, session, binding, _ = publication
    await publish(publication)
    incoming = session.model_copy(deep=True)
    if change == "drop":
        del incoming.metadata["workspace_binding"]
    else:
        incoming.metadata["workspace_binding"]["project_id"] = "forged-project"
    await store.upsert_session(incoming)
    current = await store.get_session(session.id)
    assert current.metadata.get("workspace_binding") == binding.model_dump(mode="json")


async def test_generic_plan_preserves_existing_workspace_metadata(publication):
    store, session, binding, _ = publication
    await publish(publication)
    event = _event(session, observer=False)
    await store.accept_pipeline_event(event, session_snapshot=session)
    await store.claim_event_processing(event.event_id, owner="review-owner")
    planned = session.model_copy(deep=True)
    planned.metadata["workspace_binding"] = {"forged": True}
    await store.commit_event_plan(
        event_id=event.event_id,
        owner="review-owner",
        plan=_plan_envelope(event),
        session=planned,
        receipt={
            "schema": "pex.event-processing.receipt.v1",
            "event_id": event.event_id,
            "status": "complete",
            "intervention": None,
        },
    )
    assert (await store.get_session(session.id)).metadata[
        "workspace_binding"
    ] == binding.model_dump(mode="json")


async def test_generic_plan_cannot_create_workspace_authority(publication):
    store, session, _, _ = publication
    bare = session.model_copy(deep=True)
    del bare.metadata["workspace_binding"]
    await store.upsert_session(bare)
    event = _event(bare, observer=False)
    await store.accept_pipeline_event(event, session_snapshot=bare)
    await store.claim_event_processing(event.event_id, owner="review-owner")
    planned = bare.model_copy(deep=True)
    planned.metadata["workspace_binding"] = {"forged": True}
    await store.commit_event_plan(
        event_id=event.event_id,
        owner="review-owner",
        plan=_plan_envelope(event),
        session=planned,
        receipt={
            "schema": "pex.event-processing.receipt.v1",
            "event_id": event.event_id,
            "status": "complete",
            "intervention": None,
        },
    )
    assert "workspace_binding" not in (await store.get_session(session.id)).metadata


async def test_owned_stale_planning_can_be_terminalized_without_projecting(publication):
    store, session, _, _ = publication
    await publish(publication)
    event = _event(session)
    await store.accept_pipeline_event(event, session_snapshot=session)
    await store.claim_event_processing(event.event_id, owner="review-owner")
    await _invalidate(publication, "directory")
    before = await store.get_session_control_state(session.id)
    result = await store.fail_event_processing(
        event_id=event.event_id,
        owner="review-owner",
        code="workspace_authority_changed",
    )
    assert result["state"] == "failed"
    assert result["receipt"]["code"] == "workspace_authority_changed"
    assert await store.get_session_control_state(session.id) == before
    assert await store.get_event(event.event_id) == event
    assert await store.list_interventions(session.id) == []
    assert await store.list_recoverable_event_processing() == []
    assert (
        await store.fail_event_processing(
            event_id=event.event_id,
            owner="review-owner",
            code="workspace_authority_changed",
        )
        == result
    )


async def test_reserved_planner_cannot_dispatch_after_workspace_change(publication):
    store, session, _, _ = publication
    await publish(publication)
    event = _event(session)
    await store.accept_pipeline_event(event, session_snapshot=session)
    await store.claim_event_processing(event.event_id, owner="review-owner")
    payload = {"event_id": event.event_id, "review_only": True}
    await store.reserve_event_effect(
        event_id=event.event_id,
        effect_key="planner",
        kind="supervisor_decision",
        target_session_id=session.id,
        payload=payload,
        request_hash=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        owner="review-owner",
    )
    await _invalidate(publication, "directory")
    result = await store.start_event_effect_dispatch(
        event_id=event.event_id,
        effect_key="planner",
        owner="review-owner",
    )
    assert result["granted"] is False
    assert (await store.get_event_effect(event.event_id, "planner"))["state"] == "reserved"
