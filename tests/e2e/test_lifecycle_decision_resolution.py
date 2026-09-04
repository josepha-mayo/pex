from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store, new_id, utcnow
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.overlay import Overlay, OverlayDiff
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin

_OPERATOR_TOKEN = "test-operator-token-0123456789abcdef"


@pytest.fixture
async def lifecycle_client(tmp_path):
    settings = Settings(
        require_auth=True,
        token=_OPERATOR_TOKEN,
        home=tmp_path,
        autonomy="autopilot",
    )
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.token = _OPERATOR_TOKEN
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    await store.connect()
    source = adapters.synthetic.seed_session(
        vendor_id="lifecycle-source",
        project_id=str(tmp_path),
        cwd=str(tmp_path),
        goal_id="goal-1",
    )
    source.capabilities = (await adapters.synthetic.probe()).model_dump(mode="json")
    now = utcnow()
    await store.upsert_goal(
        Goal(
            id="goal-1",
            project_id=str(tmp_path),
            title="Exercise lifecycle controls",
            objective="Bind each lifecycle test to explicit persistent intent.",
            created_at=now,
            updated_at=now,
        )
    )
    await store.upsert_session(source)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {_OPERATOR_TOKEN}"},
    ) as client:
        yield client, source
    await store.close()


async def _pending(
    kind: InterventionType,
    source,
    payload: dict,
    *,
    reversible: bool = False,
) -> Intervention:
    action = ProposedAction(
        type=kind,
        session_id=source.id,
        goal_id=source.goal_id,
        payload=payload,
        rationale="Observed state justifies this exact lifecycle action.",
        evidence=["event:observed"],
        confidence=0.9,
        risk=RiskLevel.MEDIUM,
        reversible=reversible,
        authority_required=Authority.HUMAN,
        requires_capability={
            InterventionType.START_AGENT: "start",
            InterventionType.STOP_AGENT: "stop",
            InterventionType.FORK_PROBE: "fork",
        }.get(kind),
    )
    verdict = state.pipeline.policy.decide(action)
    assert verdict == PolicyVerdict.ASK_HUMAN
    result = await state.pipeline.executor.execute(action, verdict)
    assert result == "awaiting_human"
    intervention = Intervention(
        id=new_id("int_"),
        session_id=source.id,
        goal_id=source.goal_id,
        trigger="status",
        evidence=action.evidence,
        diagnosis="lifecycle_decision_required",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=kind.value,
        policy_verdict=verdict,
        result=result,
        created_at=utcnow(),
        metadata={"used_llm": True, "model_name": "test-supervisor"},
    )
    await state.store.add_intervention(intervention)
    return intervention


@pytest.mark.asyncio
async def test_intervention_undo_requires_operator_auth_even_in_no_auth_mode(tmp_path):
    previous_settings = state.settings
    previous_token = state.token
    try:
        state.settings = Settings.for_test(require_auth=False, home=tmp_path)
        state.token = None
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://127.0.0.1",
        ) as client:
            response = await client.post("/v1/interventions/unknown/undo")

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "operator mutations require bridge authentication"
        )
    finally:
        state.settings = previous_settings
        state.token = previous_token


@pytest.mark.asyncio
async def test_intervention_undo_requires_one_strict_bounded_idempotency_key(
    lifecycle_client,
):
    client, _ = lifecycle_client
    path = "/v1/interventions/missing-intervention/undo"

    assert (await client.post(path)).status_code == 422
    assert (
        await client.post(path, json={"idempotency_key": "short"})
    ).status_code == 422
    assert (
        await client.post(path, json={"idempotency_key": "x" * 129})
    ).status_code == 422
    assert (
        await client.post(
            path,
            json={"idempotency_key": "valid-undo-key-0001", "manifest": []},
        )
    ).status_code == 422

    missing = await client.post(
        path,
        json={"idempotency_key": "valid-undo-key-0001"},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "intervention not found"


@pytest.mark.parametrize(
    ("restore_result", "expected_status"),
    [
        (
            {
                "ok": True,
                "code": "cleanup_restored:1",
                "status": "completed",
                "replayed": False,
            },
            200,
        ),
        (
            {
                "ok": False,
                "code": "cleanup_restore_reserved_not_started",
                "status": "reserved",
                "replayed": True,
            },
            202,
        ),
        (
            {
                "ok": False,
                "code": "cleanup_restore_dispatch_in_progress",
                "status": "dispatching",
                "replayed": True,
            },
            202,
        ),
        (
            {
                "ok": False,
                "code": "cleanup_restore_not_restored:1",
                "status": "failed",
                "replayed": False,
            },
            409,
        ),
        (
            {
                "ok": False,
                "code": "cleanup_restore_conflict:1",
                "status": "conflict",
                "replayed": False,
            },
            409,
        ),
        (
            {
                "ok": False,
                "code": "cleanup_restore_reservation_refused",
                "status": "refused",
                "replayed": False,
            },
            409,
        ),
        (
            {
                "ok": False,
                "code": (
                    "cleanup_restore_delivery_uncertain:"
                    "restored=0,not_restored=1,conflict=0"
                ),
                "status": "delivery_uncertain",
                "replayed": False,
            },
            502,
        ),
        (
            {
                "ok": False,
                "code": "cleanup_restore_finalization_uncertain",
                "status": "uncertain",
                "replayed": False,
            },
            502,
        ),
    ],
)
@pytest.mark.asyncio
async def test_cleanup_undo_maps_only_path_free_executor_receipts(
    lifecycle_client,
    monkeypatch,
    restore_result,
    expected_status,
):
    client, source = lifecycle_client
    intervention = await _pending(
        InterventionType.CLEANUP,
        source,
        {"mode": "quarantine", "resource_ids": ["resource-classification-only"]},
        reversible=True,
    )
    receipt = {
        "operation_id": "restore-operation-1",
        "cleanup_operation_id": "cleanup-operation-1",
        "intervention_id": intervention.id,
        "session_id": source.id,
        "goal_id": source.goal_id,
        "state": restore_result["status"],
        "version": 2,
        "reserved_at": "2026-08-31T00:00:00Z",
        "dispatch_started_at": None,
        "finished_at": None,
        "resource_count": 1,
        "outcome_counts": {"restored": 0, "not_restored": 0, "conflict": 0},
    }
    expected = {**restore_result, "receipt": receipt}
    restore = AsyncMock(
        return_value={
            **restore_result,
            "receipt": {
                **receipt,
                "source_path": "C:\\must-not-leak\\source",
                "manifest": [{"destination_path": "C:\\must-not-leak\\destination"}],
            },
        }
    )
    monkeypatch.setattr(state.pipeline.executor, "restore_cleanup", restore)

    response = await client.post(
        f"/v1/interventions/{intervention.id}/undo",
        json={"idempotency_key": "cleanup-undo-mapping-0001"},
    )

    assert response.status_code == expected_status, response.text
    assert response.json() == expected
    assert "path" not in json.dumps(response.json()).lower()
    restore.assert_awaited_once_with(
        intervention.id,
        authorized_by="local_bridge_operator",
        idempotency_key="cleanup-undo-mapping-0001",
    )


@pytest.mark.asyncio
async def test_human_can_execute_exact_pending_start_once_with_audit(lifecycle_client, tmp_path):
    client, source = lifecycle_client
    intervention = await _pending(
        InterventionType.START_AGENT,
        source,
        {
            "project": str(tmp_path),
            "prompt": "Run the bounded offline task.",
            "config": {},
        },
    )

    pending = await state.store.get_session(source.id)
    assert pending is not None
    assert pending.status == SessionStatus.NEEDS_DECISION

    response = await client.post(
        f"/v1/decisions/{intervention.id}/resolve",
        json={"decision": "allow"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "lifecycle"
    assert body["executed"] is True
    assert body["replayed"] is False
    assert body["resolution"]["status"] == "delivered"
    started_id = body["intervention"]["result"].removeprefix("agent_started:")
    assert await state.store.get_session(started_id) is not None
    assert state.adapters.synthetic.inbox[started_id] == ["Run the bounded offline task."]

    replay = await client.post(
        f"/v1/decisions/{intervention.id}/resolve",
        json={"decision": "allow"},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert len([item for item in state.adapters.synthetic.sessions if item != source.id]) == 1

    conflict = await client.post(
        f"/v1/decisions/{intervention.id}/resolve",
        json={"decision": "deny"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "lifecycle_decision_conflict"

    records = [
        json.loads(line)
        for line in (tmp_path / "PEX_INTERVENTION_LOG.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    relevant = [row for row in records if row["intervention_id"] == intervention.id]
    assert [row["record_type"] for row in relevant] == [
        "created",
        "human_lifecycle_resolved",
    ]
    assert relevant[-1]["lifecycle_resolution"]["status"] == "delivered"
    assert "started_session_id" not in relevant[-1]["action_payload"]
    assert relevant[-1]["lifecycle_resolution"]["delivery_result"] == (
        f"agent_started:{started_id}"
    )


@pytest.mark.asyncio
async def test_resolve_route_rejects_rebound_intervention_before_executor_io(
    lifecycle_client,
    tmp_path,
    monkeypatch,
):
    client, source = lifecycle_client
    intervention = await _pending(
        InterventionType.START_AGENT,
        source,
        {
            "project": str(tmp_path),
            "prompt": "This must not start after project rebinding.",
            "config": {},
        },
    )
    await state.store.register_project_locator(
        legacy_project_id=str(tmp_path),
        locator=ProjectLocator.path(
            "/workspace/rebound-lifecycle-route",
            platform=PathPlatform.POSIX,
            origin=ProjectOrigin(
                namespace="machine",
                host="lifecycle-route-test",
            ),
        ),
    )
    execute = AsyncMock()
    monkeypatch.setattr(state.pipeline.executor, "execute", execute)

    response = await client.post(
        f"/v1/decisions/{intervention.id}/resolve",
        json={"decision": "allow"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "artifact_project_identity_changed"
    execute.assert_not_awaited()
    assert len(state.adapters.synthetic.sessions) == 1


@pytest.mark.asyncio
async def test_overlay_undo_rejects_unowned_rebound_intervention_without_adapter_io(
    lifecycle_client,
    tmp_path,
    monkeypatch,
):
    client, source = lifecycle_client
    action = ProposedAction(
        type=InterventionType.APPLY_OVERLAY,
        session_id=source.id,
        goal_id=source.goal_id,
        payload={"overlay": {"id": "overlay-rebound-undo"}},
        rationale="A reversible overlay was previously applied.",
        evidence=["event:overlay-applied"],
        confidence=0.9,
        risk=RiskLevel.LOW,
        reversible=True,
        authority_required=Authority.LOCAL_POLICY,
    )
    intervention = Intervention(
        id=new_id("int_overlay_rebind_"),
        session_id=source.id,
        goal_id=source.goal_id,
        trigger="event",
        evidence=action.evidence,
        diagnosis="overlay_previously_applied",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=True,
        authority_required=action.authority_required.value,
        action_taken=InterventionType.APPLY_OVERLAY.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="overlay_applied",
        created_at=utcnow(),
    )
    await state.store.add_intervention(intervention)
    await state.store.register_project_locator(
        legacy_project_id=str(tmp_path),
        locator=ProjectLocator.path(
            "/workspace/rebound-overlay-undo",
            platform=PathPlatform.POSIX,
            origin=ProjectOrigin(
                namespace="machine",
                host="overlay-undo-test",
            ),
        ),
    )
    revert = AsyncMock(return_value=True)
    monkeypatch.setattr(state.adapters.synthetic, "revert_overlay", revert)

    response = await client.post(
        f"/v1/interventions/{intervention.id}/undo",
        json={"idempotency_key": "overlay-rebound-undo-0001"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "overlay_not_found"
    revert.assert_not_awaited()


@pytest.mark.asyncio
async def test_overlay_undo_contains_exact_owner_through_pause_rebind_and_replays(
    lifecycle_client,
    tmp_path,
    monkeypatch,
):
    client, source = lifecycle_client
    intervention_id = new_id("int_overlay_containment_")
    overlay = Overlay(
        id="overlay-containment-undo",
        session_id=source.id,
        reason="Verify exact authority-reducing overlay containment.",
        diff=OverlayDiff(extra={"phase": "implementation"}),
        ttl_seconds=300,
    )
    action = ProposedAction(
        type=InterventionType.APPLY_OVERLAY,
        session_id=source.id,
        goal_id=source.goal_id,
        payload={"overlay": overlay.model_dump(mode="json")},
        rationale="Apply one exact reversible session overlay.",
        evidence=["event:overlay-containment"],
        confidence=0.9,
        risk=RiskLevel.LOW,
        reversible=True,
        authority_required=Authority.LOCAL_POLICY,
    )
    intervention = Intervention(
        id=intervention_id,
        session_id=source.id,
        goal_id=source.goal_id,
        trigger="event",
        evidence=action.evidence,
        diagnosis="overlay_previously_applied",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=True,
        authority_required=action.authority_required.value,
        action_taken=InterventionType.APPLY_OVERLAY.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="delivery_reserved",
        created_at=utcnow(),
    )
    await state.store.add_intervention(intervention)
    apply = AsyncMock(return_value=True)
    revert = AsyncMock(return_value=True)
    monkeypatch.setattr(state.adapters.synthetic, "apply_overlay", apply)
    monkeypatch.setattr(state.adapters.synthetic, "revert_overlay", revert)
    assert (
        await state.pipeline.executor.execute(
            action,
            PolicyVerdict.ALLOW,
            operation_owner_id=intervention_id,
        )
        == "overlay_applied"
    )

    source.supervision_paused = True
    await state.store.upsert_session(source)
    goal = await state.store.get_goal(source.goal_id)
    assert goal is not None
    goal.paused = True
    goal.updated_at = utcnow()
    await state.store.upsert_goal(goal)
    await state.store.register_project_locator(
        legacy_project_id=str(tmp_path),
        locator=ProjectLocator.path(
            "/workspace/rebound-overlay-containment",
            platform=PathPlatform.POSIX,
            origin=ProjectOrigin(
                namespace="machine",
                host="overlay-containment-test",
            ),
        ),
    )

    request = {"idempotency_key": "overlay-containment-undo-0001"}
    first = await client.post(
        f"/v1/interventions/{intervention.id}/undo",
        json=request,
    )
    replay = await client.post(
        f"/v1/interventions/{intervention.id}/undo",
        json=request,
    )

    assert first.status_code == 200, first.text
    assert first.json()["code"] == "overlay_reverted"
    assert first.json()["state"] == "delivered"
    assert first.json()["replayed"] is False
    assert replay.status_code == 200, replay.text
    assert replay.json()["code"] == "overlay_already_reverted"
    assert replay.json()["state"] == "delivered"
    assert replay.json()["replayed"] is True
    assert replay.json()["receipt"] == first.json()["receipt"]
    revert.assert_awaited_once()

    frozen = await state.store.get_intervention(intervention.id)
    assert frozen is not None
    assert frozen.result == "overlay_reverted"
    assert frozen.outcome == "overlay_reverted_by_human"
    assert frozen.metadata["undo_result"] == "overlay_reverted"
    assert (
        frozen.metadata["overlay_revert_operation_id"]
        == first.json()["receipt"]["operation_id"]
    )


@pytest.mark.asyncio
async def test_pending_start_cannot_cross_its_source_project(lifecycle_client, tmp_path):
    client, source = lifecycle_client
    intervention = await _pending(
        InterventionType.START_AGENT,
        source,
        {
            "project": str(tmp_path / "another-project"),
            "prompt": "Do not start outside the bound project.",
            "config": {},
        },
    )

    response = await client.post(
        f"/v1/decisions/{intervention.id}/resolve",
        json={"decision": "allow"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lifecycle_failed"
    assert response.json()["detail"]["resolution"]["resolution"][
        "delivery_result"
    ] == "agent_start_project_mismatch"
    assert len(state.adapters.synthetic.sessions) == 1


@pytest.mark.asyncio
async def test_human_denial_does_not_call_stop_and_is_replay_safe(lifecycle_client):
    client, source = lifecycle_client
    intervention = await _pending(InterventionType.STOP_AGENT, source, {})
    response = await client.post(
        f"/v1/decisions/{intervention.id}/resolve",
        json={"decision": "deny"},
    )
    assert response.status_code == 200
    assert response.json()["executed"] is False
    assert response.json()["resolution"]["status"] == "denied"
    current = await state.store.get_session(source.id)
    assert current is not None
    assert current.status == SessionStatus.WORKING
    assert state.adapters.synthetic.sessions[source.id].status == SessionStatus.WORKING

    replay = await client.post(
        f"/v1/decisions/{intervention.id}/resolve",
        json={"decision": "deny"},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True


@pytest.mark.asyncio
async def test_cleanup_undo_restores_from_bound_path_free_receipt_and_replays(
    lifecycle_client,
    tmp_path,
):
    client, source = lifecycle_client
    project = tmp_path / "owned-project"
    scratch = project / "tmp" / "probe.json"
    scratch.parent.mkdir(parents=True)
    scratch.write_text('{"ok":true}', encoding="utf-8")
    resource = await state.store.register_lifecycle_resource(
        session_id=source.id,
        path=scratch,
        scope_root=project,
        kind="scratch",
        created_by="test_probe",
    )
    source.status = SessionStatus.STOPPED
    state.adapters.synthetic.sessions[source.id].status = SessionStatus.STOPPED
    await state.store.upsert_session(source)
    await state.store.mark_lifecycle_resource_cleanup_ready(
        resource_id=resource["id"],
        session_id=source.id,
        evidence=["source_session_stopped", "scratch_probe_expired"],
    )
    intervention = await _pending(
        InterventionType.CLEANUP,
        source,
        {"mode": "quarantine", "resource_ids": [resource["id"]]},
        reversible=True,
    )
    original_action = intervention.proposed_action.model_dump(mode="json")
    original_hash_row = await state.store.db.execute(
        "SELECT action_hash FROM interventions WHERE id = ?",
        (intervention.id,),
    )
    original_hash = (await original_hash_row.fetchone())["action_hash"]
    pending = await state.store.get_session(source.id)
    assert pending is not None
    assert pending.status == SessionStatus.STOPPED
    resolved = await client.post(
        f"/v1/decisions/{intervention.id}/resolve",
        json={"decision": "allow"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolution"]["status"] == "delivered"
    assert resolved.json()["intervention"]["result"] == "cleanup_quarantined:1"
    assert resolved.json()["intervention"]["proposed_action"] == original_action
    assert not scratch.exists()

    undo_body = {"idempotency_key": "cleanup-restore-e2e-0001"}
    undone = await client.post(
        f"/v1/interventions/{intervention.id}/undo",
        json=undo_body,
    )
    assert undone.status_code == 200, undone.text
    assert undone.json()["code"] == "cleanup_restored:1"
    assert undone.json()["status"] == "completed"
    assert undone.json()["replayed"] is False
    assert undone.json()["receipt"]["resource_count"] == 1
    assert "path" not in json.dumps(undone.json()["receipt"]).lower()
    assert scratch.read_text(encoding="utf-8") == '{"ok":true}'
    stored_resource = await state.store.get_lifecycle_resource(resource["id"])
    assert stored_resource is not None
    assert stored_resource["state"] == "active"
    stored = await state.store.get_intervention(intervention.id)
    assert stored is not None
    assert stored.proposed_action.model_dump(mode="json") == original_action
    final_hash_row = await state.store.db.execute(
        "SELECT action_hash FROM interventions WHERE id = ?",
        (intervention.id,),
    )
    assert (await final_hash_row.fetchone())["action_hash"] == original_hash
    assert stored.result == "cleanup_restored:1"
    assert stored.outcome == "cleanup_restored_by_operator"
    assert "path" not in json.dumps(stored.metadata["undo_receipt"]).lower()

    replay = await client.post(
        f"/v1/interventions/{intervention.id}/undo",
        json=undo_body,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["code"] == "cleanup_restored:1"
    assert replay.json()["replayed"] is True
    assert replay.json()["receipt"] == undone.json()["receipt"]
    assert scratch.read_text(encoding="utf-8") == '{"ok":true}'


@pytest.mark.asyncio
async def test_delivered_nudge_cannot_be_falsely_undone(lifecycle_client, tmp_path):
    client, source = lifecycle_client
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=source.id,
        goal_id=source.goal_id,
        payload={
            "message": (
                "Continue from the observed failing test; "
                "API_KEY=dummy-secret-value-12345 must never enter the audit log."
            )
        },
        rationale="A concrete failure remains.",
        evidence=["pytest failed"],
        confidence=0.9,
        risk=RiskLevel.LOW,
        reversible=True,
        authority_required=Authority.LOCAL_POLICY,
        requires_capability="message",
    )
    intervention = Intervention(
        id=new_id("int_"),
        session_id=source.id,
        goal_id=source.goal_id,
        trigger="stop",
        evidence=action.evidence,
        diagnosis="unfinished_work",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=True,
        authority_required=action.authority_required.value,
        action_taken=InterventionType.SEND_NUDGE.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="message_sent",
        created_at=utcnow(),
    )
    await state.store.add_intervention(intervention)

    response = await client.post(
        f"/v1/interventions/{intervention.id}/undo",
        json={"idempotency_key": "nudge-undo-refused-0001"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "intervention has no truthful undo operation"
    assert state.adapters.synthetic.inbox.get(source.id, []) == []
    audit = (tmp_path / "PEX_INTERVENTION_LOG.jsonl").read_text(encoding="utf-8")
    assert "dummy-secret-value-12345" not in audit
    assert "[REDACTED:credential_assignment]" in audit
