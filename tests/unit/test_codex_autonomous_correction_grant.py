"""Exact, revocable authority for shared-Codex autonomous corrections."""

# ruff: noqa: F401, F811 -- imported pytest fixture is injected by name.

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pex_bridge import store as store_module
from pex_bridge.app import state
from pex_bridge.local_origin_config import (
    load_local_origin_choice,
    save_local_origin_choice,
)
from pex_bridge.store import (
    OperatorEffectConflictError,
    stable_event_artifact_id,
    utcnow,
)
from pex_bridge.workspace_binding import WorkspaceAuthorityError
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import EventType, PolicyVerdict
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent
from test_codex_shared_attach import _confirm, _inspect, shared_client
from test_event_processing_store import _plan_envelope


async def _attached(shared_client):
    client, body, _, _, _, _ = shared_client
    selection = await _inspect(client, body)
    confirmed = await _confirm(client, selection)
    assert confirmed.status_code == 200, confirmed.text
    store = state.store
    now = datetime.now(UTC)
    goal = Goal(
        id="autonomous-correction-goal",
        project_id=body["project_id"],
        title="Correct this existing worker",
        objective="Finish the exact attached task.",
        acceptance_criteria=["The requested result is externally verified."],
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    intent = await store.get_goal_intent_view(goal.id)
    control = await store.get_session_control_state(selection["session_id"])
    attached = await store.attach_session_goal(
        selection["session_id"],
        goal.id,
        expected_goal_id=None,
        expected_control_revision=control["control_revision"],
        expected_goal_intent_revision=intent["intent_revision"],
    )
    assert attached["granted"] is True
    return client, body, selection, goal, intent


def _grant_arguments(status, *, enabled=True, key="autonomous-grant-0001"):
    scope = status["scope"]
    return {
        "enabled": enabled,
        "expected_control_revision": scope["control_revision"],
        "expected_goal_id": scope["goal_id"],
        "expected_goal_intent_revision": scope["goal_intent_revision"],
        "expected_goal_intent_hash": scope["goal_intent_hash"],
        "expected_project_binding": scope["project_binding"],
        "expected_workspace_sha256": scope["workspace_sha256"],
        "expected_subscription_authorization_id": scope[
            "subscription_authorization_id"
        ],
        "expected_connection_generation": scope["connection_generation"],
        "principal_id": "local_bridge_operator",
        "actor_assurance": "bridge_bearer",
        "idempotency_key": key,
    }


async def _reserve_correction(store, session, event_id):
    event = HarnessEvent(
        event_id=event_id,
        ts=utcnow(),
        harness_type=session.harness_type,
        session_id=session.id,
        project_id=session.project_id,
        goal_id=session.goal_id,
        event_type=EventType.AGENT_RESPONSE,
        message_delta="The worker stopped before the exact criterion was verified.",
    )
    await store.accept_pipeline_event(event, session_snapshot=session)
    owner = f"owner-{event_id}"
    await store.claim_event_processing(event.event_id, owner=owner)
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=session.id,
        goal_id=session.goal_id,
        payload={"text": "Verify the missing public artifact before stopping."},
        rationale="The required evidence is missing.",
        evidence=[event.event_id],
        confidence=0.9,
        risk=RiskLevel.LOW,
        reversible=False,
        requires_capability="send_message",
    )
    intervention = Intervention(
        id=stable_event_artifact_id(event.event_id, "intervention"),
        session_id=session.id,
        goal_id=session.goal_id,
        trigger=event.event_type.value,
        evidence=action.evidence,
        diagnosis="missing_required_evidence",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=False,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="delivery_reserved",
        created_at=event.ts,
        metadata={"trigger_event_id": event.event_id},
    )
    payload = await store.prepare_main_effect_payload(
        event_id=event.event_id,
        intervention_id=intervention.id,
        action=action.model_dump(mode="json"),
        required_capability="send_message",
    )
    request_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    await store.commit_event_plan(
        event_id=event.event_id,
        owner=owner,
        plan=_plan_envelope(
            event,
            intervention=intervention,
            effect_kind="worker_action",
            required_capability="send_message",
        ),
        session=session,
        intervention=intervention,
        main_effect={
            "effect_key": "main",
            "kind": "worker_action",
            "target_session_id": session.id,
            "payload": payload,
            "request_hash": request_hash,
        },
    )
    return event, owner, action


@pytest.mark.asyncio
async def test_explicit_grant_is_exact_idempotent_and_keeps_observer_receipt(
    shared_client,
):
    _, _, selection, _, _ = await _attached(shared_client)
    store = state.store
    before_session = await store.get_session(selection["session_id"])
    before_receipt = dict(before_session.metadata["subscription_receipt"])
    status = await store.get_autonomous_correction_grant_status(selection["session_id"])
    assert status["enabled"] is False
    assert status["reason"] == "explicit_grant_required"

    first = await store.set_session_autonomous_corrections(
        selection["session_id"], **_grant_arguments(status)
    )
    assert first["autonomous_correction_grant"]["enabled"] is True
    assert first["autonomous_correction_grant"]["changed"] is True
    assert first["control_revision"] == status["scope"]["control_revision"] + 1
    assert set(first["autonomous_correction_grant"]["scope"]["allowed_intervention_types"]) == {
        "CONTINUE_SESSION",
        "INJECT_CONTEXT",
        "REQUEST_VERIFICATION",
        "SEND_NUDGE",
    }
    after = await store.get_autonomous_correction_grant_status(selection["session_id"])
    assert after["enabled"] is True
    assert (await store.get_session(selection["session_id"])).metadata[
        "subscription_receipt"
    ] == before_receipt
    assert before_receipt["observation_only"] is True
    assert before_receipt["delivery_proven"] is False

    replay = await store.set_session_autonomous_corrections(
        selection["session_id"], **_grant_arguments(status)
    )
    assert replay["replayed"] is True
    assert replay["control_revision"] == first["control_revision"]
    with pytest.raises(OperatorEffectConflictError, match="different content"):
        await store.set_session_autonomous_corrections(
            selection["session_id"],
            **_grant_arguments(status, enabled=False),
        )
    disabled = await store.set_session_autonomous_corrections(
        selection["session_id"],
        **_grant_arguments(after, enabled=False, key="autonomous-grant-disable-0002"),
    )
    assert disabled["autonomous_correction_grant"]["enabled"] is False
    assert disabled["autonomous_correction_grant"]["changed"] is True
    assert (
        await store.get_autonomous_correction_grant_status(selection["session_id"])
    )["enabled"] is False


@pytest.mark.asyncio
async def test_pause_revokes_and_resume_does_not_silently_regrant(
    shared_client,
):
    _, _, selection, _, _ = await _attached(shared_client)
    store = state.store
    status = await store.get_autonomous_correction_grant_status(selection["session_id"])
    await store.set_session_autonomous_corrections(
        selection["session_id"], **_grant_arguments(status)
    )
    control = await store.get_session_control_state(selection["session_id"])
    paused = await store.set_session_supervision_paused(
        selection["session_id"],
        paused=True,
        expected_control_revision=control["control_revision"],
    )
    assert paused["granted"] is True
    assert (
        await store.get_autonomous_correction_grant_status(selection["session_id"])
    )["enabled"] is False
    control = await store.get_session_control_state(selection["session_id"])
    resumed = await store.set_session_supervision_paused(
        selection["session_id"],
        paused=False,
        expected_control_revision=control["control_revision"],
    )
    assert resumed["granted"] is True
    status = await store.get_autonomous_correction_grant_status(selection["session_id"])
    assert status["enabled"] is False
    assert status["reason"] == "explicit_grant_required"


@pytest.mark.asyncio
async def test_goal_intent_change_invalidates_without_rewriting_old_grant(
    shared_client,
):
    _, _, selection, goal, intent = await _attached(shared_client)
    store = state.store
    status = await store.get_autonomous_correction_grant_status(selection["session_id"])
    granted = await store.set_session_autonomous_corrections(
        selection["session_id"], **_grant_arguments(status)
    )
    changed_goal = goal.model_copy(
        update={
            "objective": "A deliberately changed human objective.",
            "updated_at": datetime.now(UTC),
        }
    )
    await store.patch_goal_with_ledger(
        goal,
        changed_goal,
        [],
        expected_intent_revision=intent["intent_revision"],
    )
    current = await store.get_autonomous_correction_grant_status(selection["session_id"])
    assert current["enabled"] is False
    assert current["scope"]["goal_intent_hash"] != granted[
        "autonomous_correction_grant"
    ]["scope"]["goal_intent_hash"]
    regranted = await store.set_session_autonomous_corrections(
        selection["session_id"],
        **_grant_arguments(current, key="autonomous-grant-after-goal-change-0002"),
    )
    assert regranted["autonomous_correction_grant"]["enabled"] is True
    assert (
        await store.get_autonomous_correction_grant_status(selection["session_id"])
    )["enabled"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("expected_control_revision", 999),
        ("expected_goal_id", "different-goal"),
        ("expected_goal_intent_revision", 999),
        ("expected_goal_intent_hash", "0" * 64),
        ("expected_project_binding", "identity:different-project"),
        ("expected_workspace_sha256", "0" * 64),
        ("expected_subscription_authorization_id", "different-authorization"),
        ("expected_connection_generation", 999),
    ],
)
async def test_every_scope_cas_mismatch_refuses_without_mutation(
    shared_client, field, replacement
):
    _, _, selection, _, _ = await _attached(shared_client)
    store = state.store
    status = await store.get_autonomous_correction_grant_status(selection["session_id"])
    arguments = _grant_arguments(status, key=f"scope-mismatch-{field}-0001")
    arguments[field] = replacement
    with pytest.raises(ValueError, match="scope changed"):
        await store.set_session_autonomous_corrections(selection["session_id"], **arguments)
    assert (
        await store.get_session_control_state(selection["session_id"])
    )["control_revision"] == status["scope"]["control_revision"]
    assert (
        await store.get_autonomous_correction_grant_status(selection["session_id"])
    )["enabled"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("enabled", 1),
        ("expected_control_revision", True),
        ("expected_goal_intent_revision", True),
        ("expected_connection_generation", True),
        ("expected_goal_intent_hash", None),
        ("expected_workspace_sha256", 7),
        ("expected_subscription_authorization_id", 7),
        ("idempotency_key", 7),
    ],
)
async def test_malformed_grant_inputs_fail_closed(shared_client, field, replacement):
    _, _, selection, _, _ = await _attached(shared_client)
    store = state.store
    status = await store.get_autonomous_correction_grant_status(selection["session_id"])
    arguments = _grant_arguments(status, key=f"malformed-{field}-0001")
    arguments[field] = replacement
    with pytest.raises(ValueError):
        await store.set_session_autonomous_corrections(selection["session_id"], **arguments)
    assert (
        await store.get_autonomous_correction_grant_status(selection["session_id"])
    )["enabled"] is False


@pytest.mark.asyncio
async def test_grant_survives_store_restart_but_not_connection_replacement(shared_client):
    client, body, selection, _, _ = await _attached(shared_client)
    store = state.store
    status = await store.get_autonomous_correction_grant_status(selection["session_id"])
    await store.set_session_autonomous_corrections(
        selection["session_id"], **_grant_arguments(status)
    )
    reopened = type(store)(store.path)
    await reopened.connect()
    try:
        assert (
            await reopened.get_autonomous_correction_grant_status(selection["session_id"])
        )["enabled"] is True
    finally:
        await reopened.close()

    detached = await client.post(
        "/v1/adapters/codex/shared/detach",
        json={
            "inspection_id": selection["inspection_id"],
            "selection_id": selection["selection_id"],
        },
    )
    assert detached.status_code == 200, detached.text
    replacement = await _inspect(client, body)
    confirmed = await _confirm(client, replacement)
    assert confirmed.status_code == 200, confirmed.text
    replaced = await store.get_autonomous_correction_grant_status(selection["session_id"])
    assert replaced["enabled"] is False
    assert replaced["reason"] == "explicit_grant_required"
    assert replaced["scope"]["subscription_authorization_id"] != status["scope"][
        "subscription_authorization_id"
    ]


@pytest.mark.asyncio
async def test_external_origin_replacement_invalidates_grant(shared_client):
    _, body, selection, _, _ = await _attached(shared_client)
    store = state.store
    status = await store.get_autonomous_correction_grant_status(selection["session_id"])
    await store.set_session_autonomous_corrections(
        selection["session_id"], **_grant_arguments(status)
    )
    origin_path = Path(body["cwd"]) / "local-origin.json"
    choice = load_local_origin_choice(origin_path)
    assert choice is not None
    save_local_origin_choice(
        origin_path,
        choice.origin,
        expected_revision=choice.revision,
        expected_choice_id=choice.choice_id,
    )
    invalidated = await store.get_autonomous_correction_grant_status(
        selection["session_id"]
    )
    assert invalidated == {
        "enabled": False,
        "reason": "autonomous_correction_scope_unavailable",
        "scope": None,
        "grant": None,
    }


@pytest.mark.asyncio
async def test_workspace_resample_failure_invalidates_grant(shared_client, monkeypatch):
    _, _, selection, _, _ = await _attached(shared_client)
    store = state.store
    status = await store.get_autonomous_correction_grant_status(selection["session_id"])
    await store.set_session_autonomous_corrections(
        selection["session_id"], **_grant_arguments(status)
    )

    def replaced_workspace(*_args, **_kwargs):
        raise WorkspaceAuthorityError("injected physical workspace replacement")

    monkeypatch.setattr(store_module, "require_current_workspace", replaced_workspace)
    invalidated = await store.get_autonomous_correction_grant_status(
        selection["session_id"]
    )
    assert invalidated["enabled"] is False
    assert invalidated["reason"] == "autonomous_correction_scope_unavailable"
    assert invalidated["scope"] is None


@pytest.mark.asyncio
async def test_claim_needs_explicit_grant_despite_truthful_false_public_capability(
    shared_client,
):
    _, _, selection, _, _ = await _attached(shared_client)
    store = state.store
    session = await store.get_session(selection["session_id"])
    assert session.capabilities.get("send_message", False) is False
    event, owner, _ = await _reserve_correction(store, session, "correction-without-grant")
    refused = await store.claim_main_event_effect(event_id=event.event_id, owner=owner)
    assert refused["granted"] is False
    assert refused["reason"] == "autonomous_correction_grant_required"


@pytest.mark.asyncio
async def test_active_grant_claims_with_false_capability_and_revoke_blocks_final_check(
    shared_client,
):
    _, _, selection, _, _ = await _attached(shared_client)
    store = state.store
    status = await store.get_autonomous_correction_grant_status(selection["session_id"])
    await store.set_session_autonomous_corrections(
        selection["session_id"], **_grant_arguments(status)
    )
    session = await store.get_session(selection["session_id"])
    assert session.capabilities.get("send_message", False) is False
    event, owner, action = await _reserve_correction(store, session, "active-grant-correction")
    claim = await store.claim_main_event_effect(event_id=event.event_id, owner=owner)
    assert claim["granted"] is True
    active = await store.get_autonomous_correction_grant_status(selection["session_id"])
    await store.set_session_autonomous_corrections(
        selection["session_id"],
        **_grant_arguments(
            active, enabled=False, key="revoke-after-claim-before-final-0002"
        ),
    )
    final = await store.validate_main_event_effect_dispatch(
        event_id=event.event_id,
        owner=owner,
        effect_id=claim["effect"]["effect_id"],
        effect_version=claim["effect"]["version"],
        expected_action=action.model_dump(mode="json"),
    )
    assert final["granted"] is False
    assert final["reason"] in {
        "session_authority_changed_before_dispatch",
        "autonomous_correction_grant_required",
    }
