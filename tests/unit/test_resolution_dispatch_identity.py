from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.decisions import (
    DecisionResolutionError,
    resolve_lifecycle_decision,
    resolve_permission_decision,
)
from pex_bridge.store import Store, utcnow
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.capabilities import AdapterCapabilities, PermissionResponseMode
from pex_protocol.context import ContextBundle
from pex_protocol.enums import Authority, HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessSession

PROJECT_ID = "resolution-dispatch-project"
ORIGIN = ProjectOrigin(namespace="machine", host="resolution-dispatch-test-host")


def _locator(name: str) -> ProjectLocator:
    return ProjectLocator.path(
        f"/work/{name}",
        platform=PathPlatform.POSIX,
        origin=ORIGIN,
    )


async def _seed(
    store: Store,
    *,
    suffix: str,
    status: SessionStatus = SessionStatus.NEEDS_DECISION,
    project_id: str = PROJECT_ID,
) -> tuple[Goal, HarnessSession, str]:
    registration = await store.register_project_locator(
        legacy_project_id=project_id,
        locator=_locator(f"identity-a-{suffix}"),
    )
    now = datetime.now(UTC)
    goal = Goal(
        id=f"goal-{suffix}",
        project_id=project_id,
        title="Keep the dispatch target immutable",
        objective="Do not cross a typed project identity boundary before external I/O.",
        created_at=now,
        updated_at=now,
    )
    capabilities = AdapterCapabilities(
        approve=True,
        deny=True,
        start=True,
        stop=True,
        fork=True,
        permission_response_mode=PermissionResponseMode.ASYNC,
    )
    session = HarnessSession(
        id=f"synthetic:resolution-{suffix}",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id=f"vendor-resolution-{suffix}",
        project_id=project_id,
        cwd=project_id,
        goal_id=goal.id,
        status=status,
        capabilities=capabilities.model_dump(mode="json"),
    )
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    return goal, session, registration["identity"].id


def _permission_intervention(
    session: HarnessSession,
    *,
    suffix: str,
) -> Intervention:
    request_id = f"permission-request-{suffix}"
    action = ProposedAction(
        type=InterventionType.RESPOND_PERMISSION,
        session_id=session.id,
        goal_id=session.goal_id,
        payload={"request_id": request_id},
        rationale="The exact permission request requires an authenticated human decision.",
        evidence=[f"permission:{request_id}"],
        confidence=1.0,
        risk=RiskLevel.HIGH,
        reversible=False,
        authority_required=Authority.HUMAN,
        requires_capability="approve",
    )
    return Intervention(
        id=f"int-permission-{suffix}",
        session_id=session.id,
        goal_id=session.goal_id,
        trigger="permission",
        evidence=action.evidence,
        diagnosis="permission_requires_human",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=False,
        authority_required=Authority.HUMAN.value,
        action_taken=InterventionType.RESPOND_PERMISSION.value,
        policy_verdict=PolicyVerdict.ASK_HUMAN,
        result="permission_awaiting_human",
        created_at=utcnow(),
        metadata={"permission_request_id": request_id},
    )


def _lifecycle_payload(
    kind: InterventionType,
    session: HarnessSession,
    *,
    suffix: str,
) -> dict:
    if kind == InterventionType.START_AGENT:
        return {
            "project": session.project_id,
            "prompt": "Run one bounded offline task.",
            "config": {"goal_id": session.goal_id},
        }
    if kind == InterventionType.FORK_PROBE:
        bundle = ContextBundle(
            goal_id=str(session.goal_id),
            target_session_id=session.id,
            source_session_ids=[session.id],
            goal_summary="Investigate one bounded hypothesis.",
            acceptance_criteria=["Return evidence without mutating the source session."],
            direct_evidence=[f"event:{suffix}"],
            next_objective="Test the isolated hypothesis.",
            created_at=datetime.now(UTC),
        )
        return {"bundle": bundle.model_dump(mode="json")}
    if kind == InterventionType.CLEANUP:
        return {"mode": "quarantine", "resource_ids": [f"resource-{suffix}"]}
    return {}


def _lifecycle_intervention(
    kind: InterventionType,
    session: HarnessSession,
    *,
    suffix: str,
) -> Intervention:
    action = ProposedAction(
        type=kind,
        session_id=session.id,
        goal_id=session.goal_id,
        payload=_lifecycle_payload(kind, session, suffix=suffix),
        rationale="The exact lifecycle action requires an authenticated human decision.",
        evidence=[f"event:{suffix}"],
        confidence=1.0,
        risk=RiskLevel.MEDIUM,
        reversible=kind == InterventionType.CLEANUP,
        authority_required=Authority.HUMAN,
        requires_capability={
            InterventionType.START_AGENT: "start",
            InterventionType.STOP_AGENT: "stop",
            InterventionType.FORK_PROBE: "fork",
        }.get(kind),
    )
    return Intervention(
        id=f"int-{kind.value.lower()}-{suffix}",
        session_id=session.id,
        goal_id=session.goal_id,
        trigger="status",
        evidence=action.evidence,
        diagnosis="lifecycle_requires_human",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=Authority.HUMAN.value,
        action_taken=kind.value,
        policy_verdict=PolicyVerdict.ASK_HUMAN,
        result="awaiting_human",
        created_at=utcnow(),
    )


async def _reserve_permission(
    store: Store,
    intervention: Intervention,
    *,
    decision: str,
) -> dict:
    await store.add_intervention(intervention)
    created, record = await store.reserve_permission_resolution(
        intervention_id=intervention.id,
        session_id=intervention.session_id,
        request_id=str(intervention.proposed_action.payload["request_id"]),
        decision=decision,
        started_at=utcnow(),
    )
    assert created is True
    return record


async def _reserve_lifecycle(
    store: Store,
    intervention: Intervention,
    *,
    decision: str = "allow",
) -> dict:
    await store.add_intervention(intervention)
    created, record = await store.reserve_lifecycle_resolution(
        intervention_id=intervention.id,
        session_id=intervention.session_id,
        decision=decision,
        started_at=utcnow(),
    )
    assert created is True
    return record


async def _resolve_to_identity_b(
    store: Store,
    *,
    suffix: str,
    project_id: str = PROJECT_ID,
) -> None:
    second = await store.register_project_locator(
        legacy_project_id=project_id,
        locator=_locator(f"identity-b-{suffix}"),
    )
    assert second["outcome"] == "quarantined"
    await store.resolve_project_identity_conflict(
        resolution_id=f"resolve-to-identity-b-{suffix}",
        legacy_project_id=project_id,
        selected_identity_id=second["identity"].id,
        resolved_by="test_operator",
        rationale="Select the replacement checkout to exercise the final dispatch CAS.",
    )


async def _quarantine(
    store: Store,
    *,
    suffix: str,
    project_id: str = PROJECT_ID,
) -> None:
    second = await store.register_project_locator(
        legacy_project_id=project_id,
        locator=_locator(f"identity-b-{suffix}"),
    )
    assert second["outcome"] == "quarantined"


async def _replace_session(store: Store, session: HarnessSession) -> None:
    await store.db.execute(
        "UPDATE sessions SET vendor_session_id = ?, harness_type = ?, json = ? WHERE id = ?",
        (
            session.vendor_session_id,
            session.harness_type.value,
            session.model_dump_json(),
            session.id,
        ),
    )
    await store.db.commit()


@pytest.mark.asyncio
async def test_permission_reservation_freezes_canonical_dispatch_binding(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        goal, session, identity_id = await _seed(store, suffix="canonical-permission")
        intervention = _permission_intervention(session, suffix="canonical-permission")
        record = await _reserve_permission(store, intervention, decision="allow")

        assert record["status"] == "reserved"
        assert record["session_id"] == session.id
        assert record["session_binding"]["vendor_session_id"] == session.vendor_session_id
        assert record["session_binding"]["harness_type"] == session.harness_type.value
        assert record["session_binding"]["goal_id"] == goal.id
        assert record["request_id"] == intervention.metadata["permission_request_id"]
        assert record["session_binding"]["project_id"] == PROJECT_ID
        assert record["goal_binding"] == {
            "goal_id": goal.id,
            "project_id": PROJECT_ID,
        }
        assert record["project_binding"] == f"identity:{identity_id}"
        assert record["intervention_binding"][
            "proposed_action"
        ] == intervention.proposed_action.model_dump(mode="json")
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_lifecycle_reservation_freezes_canonical_dispatch_binding(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        goal, session, identity_id = await _seed(store, suffix="canonical-lifecycle")
        intervention = _lifecycle_intervention(
            InterventionType.START_AGENT,
            session,
            suffix="canonical-lifecycle",
        )
        record = await _reserve_lifecycle(store, intervention)

        assert record["status"] == "reserved"
        assert record["session_id"] == session.id
        assert record["session_binding"]["vendor_session_id"] == session.vendor_session_id
        assert record["session_binding"]["harness_type"] == session.harness_type.value
        assert record["session_binding"]["goal_id"] == goal.id
        assert record["session_binding"]["project_id"] == PROJECT_ID
        assert record["goal_binding"] == {
            "goal_id": goal.id,
            "project_id": PROJECT_ID,
        }
        assert record["project_binding"] == f"identity:{identity_id}"
        assert record["intervention_binding"][
            "proposed_action"
        ] == intervention.proposed_action.model_dump(mode="json")
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_permission_allow_cannot_cross_same_key_physical_reresolution(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        _, session, _ = await _seed(store, suffix="permission-reresolution")
        intervention = _permission_intervention(session, suffix="permission-reresolution")
        await _reserve_permission(store, intervention, decision="allow")
        await _resolve_to_identity_b(store, suffix="permission-reresolution")

        with pytest.raises(PermissionError, match="project|physical|binding"):
            await store.start_permission_resolution_dispatch(intervention.id)
    finally:
        await store.close()


@pytest.mark.parametrize(
    "kind",
    [
        InterventionType.START_AGENT,
        InterventionType.FORK_PROBE,
        InterventionType.CLEANUP,
    ],
)
@pytest.mark.asyncio
async def test_authority_increasing_lifecycle_dispatch_cannot_cross_reresolution(
    tmp_path,
    kind: InterventionType,
):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    suffix = f"reresolution-{kind.value.lower()}"
    try:
        status = (
            SessionStatus.STOPPED
            if kind == InterventionType.CLEANUP
            else SessionStatus.NEEDS_DECISION
        )
        project_id = str(tmp_path) if kind == InterventionType.CLEANUP else PROJECT_ID
        _, session, _ = await _seed(
            store,
            suffix=suffix,
            status=status,
            project_id=project_id,
        )
        if kind == InterventionType.CLEANUP:
            scratch = tmp_path / "cleanup-scratch"
            scratch.mkdir()
            resource = await store.register_lifecycle_resource(
                session_id=session.id,
                path=scratch,
                scope_root=tmp_path,
                kind="scratch",
                created_by="resolution-dispatch-test",
                resource_id=f"resource-{suffix}",
            )
            await store.mark_lifecycle_resource_cleanup_ready(
                resource_id=resource["id"],
                session_id=session.id,
                evidence=["source session is stopped"],
            )
        intervention = _lifecycle_intervention(kind, session, suffix=suffix)
        await _reserve_lifecycle(store, intervention)
        await _resolve_to_identity_b(store, suffix=suffix, project_id=project_id)

        with pytest.raises(PermissionError, match="project|physical|binding"):
            await store.start_lifecycle_resolution_dispatch(intervention.id)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_permission_deny_crosses_quarantine_for_exact_immutable_target(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        _, session, _ = await _seed(store, suffix="permission-deny-containment")
        intervention = _permission_intervention(session, suffix="permission-deny-containment")
        await _reserve_permission(store, intervention, decision="deny")
        await _quarantine(store, suffix="permission-deny-containment")

        dispatch = await store.start_permission_resolution_dispatch(intervention.id)
        assert dispatch["granted"] is True
        assert dispatch["resolution"]["status"] == "dispatching"
        assert dispatch["session"]["id"] == session.id
        assert dispatch["session"]["vendor_session_id"] == session.vendor_session_id
    finally:
        await store.close()


@pytest.mark.parametrize("drift", ["vendor", "harness", "request", "goal"])
@pytest.mark.asyncio
async def test_permission_deny_quarantine_exception_rejects_target_drift(tmp_path, drift: str):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    suffix = f"permission-deny-drift-{drift}"
    try:
        goal, session, _ = await _seed(store, suffix=suffix)
        intervention = _permission_intervention(session, suffix=suffix)
        await _reserve_permission(store, intervention, decision="deny")

        if drift == "request":
            changed = intervention.model_copy(deep=True)
            changed.proposed_action.payload["request_id"] = "replacement-request"
            with pytest.raises(ValueError, match="proposed action"):
                await store.update_intervention(changed, record_type="test_request_drift")
            return
        elif drift == "goal":
            replacement = Goal(
                id=f"replacement-{goal.id}",
                project_id=PROJECT_ID,
                title=goal.title,
                objective=goal.objective,
                created_at=goal.created_at,
                updated_at=utcnow(),
            )
            await store.upsert_goal(replacement)
            changed_session = session.model_copy(update={"goal_id": replacement.id})
            await store.upsert_session(changed_session, allow_goal_change=True)
        else:
            changed_session = session.model_copy(
                update={
                    "vendor_session_id": (
                        "replacement-vendor"
                        if drift == "vendor"
                        else session.vendor_session_id
                    ),
                    "harness_type": (
                        HarnessType.CURSOR if drift == "harness" else session.harness_type
                    ),
                }
            )
            await _replace_session(store, changed_session)

        await _quarantine(store, suffix=suffix)
        with pytest.raises(PermissionError, match="session|vendor|harness|request|goal|binding"):
            await store.start_permission_resolution_dispatch(intervention.id)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_stop_crosses_quarantine_and_pause_for_exact_immutable_target(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        _, session, _ = await _seed(store, suffix="stop-containment")
        intervention = _lifecycle_intervention(
            InterventionType.STOP_AGENT,
            session,
            suffix="stop-containment",
        )
        await _reserve_lifecycle(store, intervention)
        await _quarantine(store, suffix="stop-containment")
        paused = (await store.get_session(session.id)).model_copy(
            update={"supervision_paused": True}
        )
        await store.upsert_session(paused, allow_supervision_change=True)

        dispatch = await store.start_lifecycle_resolution_dispatch(intervention.id)
        assert dispatch["granted"] is True
        assert dispatch["resolution"]["status"] == "dispatching"
        assert dispatch["session"]["id"] == session.id
        assert dispatch["session"]["vendor_session_id"] == session.vendor_session_id
    finally:
        await store.close()


@pytest.mark.parametrize("drift", ["vendor", "harness", "goal", "action"])
@pytest.mark.asyncio
async def test_stop_quarantine_exception_rejects_target_drift(tmp_path, drift: str):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    suffix = f"stop-drift-{drift}"
    try:
        goal, session, _ = await _seed(store, suffix=suffix)
        intervention = _lifecycle_intervention(
            InterventionType.STOP_AGENT,
            session,
            suffix=suffix,
        )
        await _reserve_lifecycle(store, intervention)

        if drift == "action":
            changed = intervention.model_copy(deep=True)
            changed.proposed_action.payload["unexpected"] = True
            with pytest.raises(ValueError, match="proposed action"):
                await store.update_intervention(changed, record_type="test_action_drift")
            return
        elif drift == "goal":
            replacement = Goal(
                id=f"replacement-{goal.id}",
                project_id=PROJECT_ID,
                title=goal.title,
                objective=goal.objective,
                created_at=goal.created_at,
                updated_at=utcnow(),
            )
            await store.upsert_goal(replacement)
            changed_session = session.model_copy(update={"goal_id": replacement.id})
            await store.upsert_session(changed_session, allow_goal_change=True)
        else:
            changed_session = session.model_copy(
                update={
                    "vendor_session_id": (
                        "replacement-vendor"
                        if drift == "vendor"
                        else session.vendor_session_id
                    ),
                    "harness_type": (
                        HarnessType.CURSOR if drift == "harness" else session.harness_type
                    ),
                }
            )
            await _replace_session(store, changed_session)

        await _quarantine(store, suffix=suffix)
        with pytest.raises(PermissionError, match="session|vendor|harness|goal|action|binding"):
            await store.start_lifecycle_resolution_dispatch(intervention.id)
    finally:
        await store.close()


@pytest.mark.parametrize("resolution_kind", ["permission", "lifecycle"])
@pytest.mark.asyncio
async def test_concurrent_resolution_starts_grant_exactly_once(tmp_path, resolution_kind: str):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    suffix = f"concurrent-{resolution_kind}"
    try:
        _, session, _ = await _seed(store, suffix=suffix)
        if resolution_kind == "permission":
            intervention = _permission_intervention(session, suffix=suffix)
            await _reserve_permission(store, intervention, decision="allow")
            starts = (
                store.start_permission_resolution_dispatch(intervention.id),
                store.start_permission_resolution_dispatch(intervention.id),
            )
        else:
            intervention = _lifecycle_intervention(
                InterventionType.START_AGENT,
                session,
                suffix=suffix,
            )
            await _reserve_lifecycle(store, intervention)
            starts = (
                store.start_lifecycle_resolution_dispatch(intervention.id),
                store.start_lifecycle_resolution_dispatch(intervention.id),
            )

        results = await asyncio.gather(*starts)
        assert sum(result["granted"] is True for result in results) == 1
        refused = next(result for result in results if result["granted"] is False)
        assert refused["resolution"]["status"] == "dispatching"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_lifecycle_dispatch_grant_is_durable_exact_and_current(tmp_path):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot-durable-grant")
    await store.connect()
    suffix = "durable-lifecycle-grant"
    try:
        _, session, _ = await _seed(store, suffix=suffix)
        intervention = _lifecycle_intervention(
            InterventionType.START_AGENT,
            session,
            suffix=suffix,
        )
        await _reserve_lifecycle(store, intervention)
        started = await store.start_lifecycle_resolution_dispatch(intervention.id)
        assert started["granted"] is True

        grant = await store.validate_lifecycle_dispatch_grant(
            intervention.id,
            intervention.proposed_action,
        )
        assert grant["granted"] is True
        assert grant["reason"] == "lifecycle_dispatch_granted"
        assert grant["resolution"]["dispatcher_boot_id"] == "boot-durable-grant"
        assert grant["session"]["id"] == session.id
        assert grant["intervention"]["id"] == intervention.id

        changed = intervention.proposed_action.model_copy(deep=True)
        changed.payload["prompt"] = "different external action"
        refused = await store.validate_lifecycle_dispatch_grant(intervention.id, changed)
        assert refused["granted"] is False
        assert refused["reason"] == "lifecycle_dispatch_action_changed"

        await _resolve_to_identity_b(store, suffix=suffix)
        with pytest.raises(ValueError, match="identity changed"):
            await store.validate_lifecycle_dispatch_grant(
                intervention.id,
                intervention.proposed_action,
            )
    finally:
        await store.close()


@pytest.mark.parametrize("resolution_kind", ["permission", "lifecycle"])
@pytest.mark.asyncio
async def test_finalization_under_quarantine_preserves_newer_session_controls(
    tmp_path,
    resolution_kind: str,
):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    suffix = f"finalize-controls-{resolution_kind}"
    try:
        _, session, _ = await _seed(store, suffix=suffix)
        stale_session = session.model_copy(deep=True)
        if resolution_kind == "permission":
            intervention = _permission_intervention(session, suffix=suffix)
            await _reserve_permission(store, intervention, decision="allow")
            started = await store.start_permission_resolution_dispatch(intervention.id)
        else:
            intervention = _lifecycle_intervention(
                InterventionType.START_AGENT,
                session,
                suffix=suffix,
            )
            await _reserve_lifecycle(store, intervention)
            started = await store.start_lifecycle_resolution_dispatch(intervention.id)
        assert started["granted"] is True

        revoked = AdapterCapabilities().model_dump(mode="json")
        current = (await store.get_session(session.id)).model_copy(
            update={"status": SessionStatus.STOPPED, "capabilities": revoked}
        )
        await store.upsert_session(current)
        await _quarantine(store, suffix=suffix)
        paused = (await store.get_session(session.id)).model_copy(
            update={"supervision_paused": True}
        )
        await store.upsert_session(paused, allow_supervision_change=True)

        completed = intervention.model_copy(deep=True)
        if resolution_kind == "permission":
            completed.result = "permission_allow"
            completed.outcome = "human_permission_delivered"
            await store.finalize_permission_resolution(
                completed,
                stale_session,
                status="delivered",
                delivery_result="permission_allow",
                finished_at=utcnow(),
                record_type="human_decision_resolved",
            )
        else:
            completed.result = "agent_started:synthetic:child"
            completed.outcome = "human_lifecycle_delivered"
            await store.finalize_lifecycle_resolution(
                completed,
                stale_session,
                {
                    **started["resolution"],
                    "status": "delivered",
                    "delivery_result": completed.result,
                    "finished_at": utcnow().isoformat(),
                },
                record_type="human_lifecycle_resolved",
            )

        preserved = await store.get_session(session.id)
        assert preserved is not None
        assert preserved.status == SessionStatus.STOPPED
        assert preserved.supervision_paused is True
        assert preserved.capabilities == revoked
        assert preserved.goal_id == session.goal_id
        assert preserved.project_id == session.project_id
        assert preserved.vendor_session_id == session.vendor_session_id
        assert preserved.harness_type == session.harness_type
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restart_after_permission_dispatch_marks_uncertain_without_replay(tmp_path):
    path = tmp_path / "pex.sqlite"
    first = Store(path, process_boot_id="boot-permission-before-restart")
    await first.connect()
    suffix = "restart-permission"
    _, session, _ = await _seed(first, suffix=suffix)
    intervention = _permission_intervention(session, suffix=suffix)
    await _reserve_permission(first, intervention, decision="allow")
    started = await first.start_permission_resolution_dispatch(intervention.id)
    assert started["granted"] is True

    revoked = AdapterCapabilities().model_dump(mode="json")
    newer = (await first.get_session(session.id)).model_copy(
        update={"status": SessionStatus.STOPPED, "capabilities": revoked}
    )
    await first.upsert_session(newer)
    await first.close()

    recovered = Store(path, process_boot_id="boot-permission-after-restart")
    await recovered.connect()
    try:
        receipt = await recovered.get_permission_resolution(intervention.id)
        assert receipt is not None
        assert receipt["status"] == "delivery_uncertain"
        assert receipt["delivery_result"] == "permission_allow_delivery_uncertain"
        assert receipt["dispatcher_boot_id"] == "boot-permission-before-restart"
        replay = await recovered.start_permission_resolution_dispatch(intervention.id)
        assert replay["granted"] is False
        assert replay["resolution"] == receipt

        preserved = await recovered.get_session(session.id)
        assert preserved is not None
        assert preserved.status == SessionStatus.STOPPED
        assert preserved.capabilities == revoked
    finally:
        await recovered.close()


@pytest.mark.asyncio
async def test_restart_after_lifecycle_dispatch_marks_uncertain_without_replay(tmp_path):
    path = tmp_path / "pex.sqlite"
    first = Store(path, process_boot_id="boot-lifecycle-before-restart")
    await first.connect()
    suffix = "restart-lifecycle"
    _, session, _ = await _seed(first, suffix=suffix)
    intervention = _lifecycle_intervention(
        InterventionType.START_AGENT,
        session,
        suffix=suffix,
    )
    await _reserve_lifecycle(first, intervention)
    started = await first.start_lifecycle_resolution_dispatch(intervention.id)
    assert started["granted"] is True

    revoked = AdapterCapabilities().model_dump(mode="json")
    newer = (await first.get_session(session.id)).model_copy(
        update={"status": SessionStatus.STOPPED, "capabilities": revoked}
    )
    await first.upsert_session(newer)
    await first.close()

    recovered = Store(path, process_boot_id="boot-lifecycle-after-restart")
    await recovered.connect()
    try:
        receipt = await recovered.get_lifecycle_resolution(intervention.id)
        assert receipt is not None
        assert receipt["status"] == "delivery_uncertain"
        assert receipt["delivery_result"] == "lifecycle_delivery_uncertain:ProcessRestart"
        assert receipt["dispatcher_boot_id"] == "boot-lifecycle-before-restart"
        replay = await recovered.start_lifecycle_resolution_dispatch(intervention.id)
        assert replay["granted"] is False
        assert replay["resolution"] == receipt

        preserved = await recovered.get_session(session.id)
        assert preserved is not None
        assert preserved.status == SessionStatus.STOPPED
        assert preserved.capabilities == revoked
    finally:
        await recovered.close()


@pytest.mark.parametrize("resolution_kind", ["permission", "lifecycle"])
@pytest.mark.asyncio
async def test_restart_before_dispatch_marker_leaves_resolution_startable_once(
    tmp_path,
    resolution_kind: str,
):
    path = tmp_path / "pex.sqlite"
    first = Store(path, process_boot_id=f"boot-reserved-{resolution_kind}-one")
    await first.connect()
    suffix = f"restart-reserved-{resolution_kind}"
    _, session, _ = await _seed(first, suffix=suffix)
    if resolution_kind == "permission":
        intervention = _permission_intervention(session, suffix=suffix)
        await _reserve_permission(first, intervention, decision="allow")
    else:
        intervention = _lifecycle_intervention(
            InterventionType.START_AGENT,
            session,
            suffix=suffix,
        )
        await _reserve_lifecycle(first, intervention)
    await first.close()

    recovered = Store(path, process_boot_id=f"boot-reserved-{resolution_kind}-two")
    await recovered.connect()
    try:
        if resolution_kind == "permission":
            receipt = await recovered.get_permission_resolution(intervention.id)
            starts = (
                recovered.start_permission_resolution_dispatch(intervention.id),
                recovered.start_permission_resolution_dispatch(intervention.id),
            )
        else:
            receipt = await recovered.get_lifecycle_resolution(intervention.id)
            starts = (
                recovered.start_lifecycle_resolution_dispatch(intervention.id),
                recovered.start_lifecycle_resolution_dispatch(intervention.id),
            )
        assert receipt is not None and receipt["status"] == "reserved"
        results = await asyncio.gather(*starts)
        assert sum(result["granted"] is True for result in results) == 1
        assert sum(result["granted"] is False for result in results) == 1
        assert all(result["resolution"]["status"] == "dispatching" for result in results)
    finally:
        await recovered.close()


@pytest.mark.asyncio
async def test_permission_cancellation_after_marker_finalizes_uncertain_before_propagating(
    tmp_path,
    monkeypatch,
):
    store = Store(tmp_path / "pex.sqlite", process_boot_id="boot-cancel-permission")
    await store.connect()
    adapters = AdapterRegistry()
    suffix = "cancel-permission"
    try:
        _, session, _ = await _seed(store, suffix=suffix)
        intervention = _permission_intervention(session, suffix=suffix)
        await store.add_intervention(intervention)
        entered_adapter = asyncio.Event()
        calls = 0

        async def cancelled_delivery(
            _session: HarnessSession,
            _request_id: str,
            _decision: str,
        ) -> bool:
            nonlocal calls
            calls += 1
            entered_adapter.set()
            await asyncio.Future()
            return True

        monkeypatch.setattr(adapters.synthetic, "respond_permission", cancelled_delivery)
        task = asyncio.create_task(
            resolve_permission_decision(
                store,
                adapters,
                intervention_id=intervention.id,
                decision="allow",
            )
        )
        await asyncio.wait_for(entered_adapter.wait(), timeout=2.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        receipt = await store.get_permission_resolution(intervention.id)
        assert receipt is not None
        assert receipt["status"] == "delivery_uncertain"
        assert receipt["delivery_result"] == "permission_allow_delivery_uncertain"
        stored_intervention = await store.get_intervention(intervention.id)
        assert stored_intervention is not None
        assert (
            stored_intervention.metadata["permission_resolution"]["exception_type"]
            == "CancelledError"
        )
        assert calls == 1
        refused = await store.start_permission_resolution_dispatch(intervention.id)
        assert refused["granted"] is False
        with pytest.raises(DecisionResolutionError):
            await resolve_permission_decision(
                store,
                adapters,
                intervention_id=intervention.id,
                decision="allow",
            )
        assert calls == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_resolution_classification_survives_rebind_without_granting_authority(
    tmp_path,
):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    suffix = "classification-rebind"
    try:
        _, session, _ = await _seed(store, suffix=suffix)
        deny = _permission_intervention(session, suffix=f"{suffix}-deny")
        allow = _permission_intervention(session, suffix=f"{suffix}-allow")
        await store.add_intervention(deny)
        await store.add_intervention(allow)
        await _resolve_to_identity_b(store, suffix=suffix)

        classified = await store.get_intervention_for_resolution_classification(
            deny.id
        )
        assert classified == deny
        assert (
            await store.get_intervention_for_resolution_classification("missing-intervention")
            is None
        )
        with pytest.raises(ValueError, match="identity changed"):
            await store.get_intervention_for_authority(deny.id)
        assert await store.get_permission_resolution(deny.id) is None

        created, _ = await store.reserve_permission_resolution(
            intervention_id=deny.id,
            session_id=session.id,
            request_id=str(deny.proposed_action.payload["request_id"]),
            decision="deny",
            started_at=utcnow(),
        )
        assert created is True
        dispatch = await store.start_permission_resolution_dispatch(deny.id)
        assert dispatch["granted"] is True

        with pytest.raises(ValueError, match="identity changed"):
            await store.reserve_permission_resolution(
                intervention_id=allow.id,
                session_id=session.id,
                request_id=str(allow.proposed_action.payload["request_id"]),
                decision="allow",
                started_at=utcnow(),
            )
    finally:
        await store.close()


@pytest.mark.parametrize("drift", ["vendor", "harness", "goal"])
@pytest.mark.asyncio
async def test_resolution_classification_rejects_frozen_target_drift(tmp_path, drift: str):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    suffix = f"classification-drift-{drift}"
    try:
        goal, session, _ = await _seed(store, suffix=suffix)
        intervention = _permission_intervention(session, suffix=suffix)
        await store.add_intervention(intervention)

        if drift == "goal":
            replacement = Goal(
                id=f"replacement-{goal.id}",
                project_id=PROJECT_ID,
                title=goal.title,
                objective=goal.objective,
                created_at=goal.created_at,
                updated_at=utcnow(),
            )
            await store.upsert_goal(replacement)
            await store.upsert_session(
                session.model_copy(update={"goal_id": replacement.id}),
                allow_goal_change=True,
            )
        else:
            await _replace_session(
                store,
                session.model_copy(
                    update={
                        "vendor_session_id": (
                            "replacement-vendor"
                            if drift == "vendor"
                            else session.vendor_session_id
                        ),
                        "harness_type": (
                            HarnessType.CURSOR
                            if drift == "harness"
                            else session.harness_type
                        ),
                    }
                ),
            )

        with pytest.raises(ValueError, match="target binding"):
            await store.get_intervention_for_resolution_classification(intervention.id)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_resolution_classification_rejects_action_hash_corruption(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    suffix = "classification-action-corruption"
    try:
        _, session, _ = await _seed(store, suffix=suffix)
        intervention = _permission_intervention(session, suffix=suffix)
        await store.add_intervention(intervention)

        await store.db.execute("DROP TRIGGER trg_interventions_bound_update")
        await store.db.execute(
            "UPDATE interventions SET action_hash = ? WHERE id = ?",
            ("0" * 64, intervention.id),
        )
        await store.db.commit()
        with pytest.raises(RuntimeError, match="authority binding is corrupt"):
            await store.get_intervention_for_resolution_classification(intervention.id)
    finally:
        await store.close()


class _RecordingLifecycleExecutor:
    def __init__(self, result: str) -> None:
        self.result = result
        self.calls: list[tuple[ProposedAction, PolicyVerdict, bool, str | None]] = []

    async def execute(
        self,
        action: ProposedAction,
        verdict: PolicyVerdict,
        *,
        human_authorized: bool = False,
        lifecycle_resolution_id: str | None = None,
    ) -> str:
        self.calls.append(
            (action, verdict, human_authorized, lifecycle_resolution_id)
        )
        return self.result


@pytest.mark.asyncio
async def test_permission_deny_resolver_crosses_quarantine_after_dispatch_grant(
    tmp_path,
    monkeypatch,
):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    suffix = "consumer-permission-deny-containment"
    probes = 0
    deliveries: list[tuple[str, str, str]] = []
    try:
        _, session, _ = await _seed(store, suffix=suffix)
        intervention = _permission_intervention(session, suffix=suffix)
        await store.add_intervention(intervention)
        await _quarantine(store, suffix=suffix)
        original_probe = adapters.synthetic.probe

        async def counted_probe():
            nonlocal probes
            probes += 1
            return await original_probe()

        async def deliver(
            exact_session: HarnessSession,
            request_id: str,
            decision: str,
        ) -> bool:
            deliveries.append((exact_session.id, request_id, decision))
            return True

        monkeypatch.setattr(adapters.synthetic, "probe", counted_probe)
        monkeypatch.setattr(adapters.synthetic, "respond_permission", deliver)

        result = await resolve_permission_decision(
            store,
            adapters,
            intervention_id=intervention.id,
            decision="deny",
        )

        assert result.delivered is True
        assert result.resolution["status"] == "delivered"
        assert result.resolution["authority_reducing"] is True
        assert probes == 1
        assert deliveries == [
            (
                session.id,
                str(intervention.proposed_action.payload["request_id"]),
                "deny",
            )
        ]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_lifecycle_deny_resolver_crosses_quarantine_without_executor_io(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    suffix = "consumer-lifecycle-deny-containment"
    executor = _RecordingLifecycleExecutor("must-not-run")
    try:
        _, session, _ = await _seed(store, suffix=suffix)
        intervention = _lifecycle_intervention(
            InterventionType.START_AGENT,
            session,
            suffix=suffix,
        )
        await store.add_intervention(intervention)
        await _quarantine(store, suffix=suffix)

        result = await resolve_lifecycle_decision(
            store,
            AdapterRegistry(),
            executor,
            intervention_id=intervention.id,
            decision="deny",
        )

        assert result.executed is False
        assert result.resolution["status"] == "denied"
        assert result.resolution["authority_reducing"] is True
        assert executor.calls == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_stop_resolver_crosses_quarantine_and_uses_started_target(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    suffix = "consumer-stop-containment"
    executor = _RecordingLifecycleExecutor("agent_stopped")
    try:
        _, session, _ = await _seed(store, suffix=suffix)
        intervention = _lifecycle_intervention(
            InterventionType.STOP_AGENT,
            session,
            suffix=suffix,
        )
        await store.add_intervention(intervention)
        await _quarantine(store, suffix=suffix)
        paused = (await store.get_session(session.id)).model_copy(
            update={"supervision_paused": True}
        )
        await store.upsert_session(paused, allow_supervision_change=True)

        result = await resolve_lifecycle_decision(
            store,
            AdapterRegistry(),
            executor,
            intervention_id=intervention.id,
            decision="allow",
        )

        assert result.executed is True
        assert result.resolution["status"] == "delivered"
        assert result.session.status == SessionStatus.STOPPED
        assert len(executor.calls) == 1
        action, verdict, human_authorized, resolution_id = executor.calls[0]
        assert action == intervention.proposed_action
        assert verdict == PolicyVerdict.ALLOW
        assert human_authorized is True
        assert resolution_id == intervention.id
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_authority_increasing_resolvers_block_rebind_before_any_io(
    tmp_path,
    monkeypatch,
):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    probes = 0
    executor = _RecordingLifecycleExecutor("must-not-run")
    suffix = "consumer-authority-increase-rebind"
    try:
        _, session, _ = await _seed(store, suffix=suffix)
        permission = _permission_intervention(session, suffix=f"{suffix}-permission")
        lifecycle = _lifecycle_intervention(
            InterventionType.START_AGENT,
            session,
            suffix=f"{suffix}-lifecycle",
        )
        await store.add_intervention(permission)
        await store.add_intervention(lifecycle)
        await _resolve_to_identity_b(store, suffix=suffix)
        original_probe = adapters.synthetic.probe

        async def counted_probe():
            nonlocal probes
            probes += 1
            return await original_probe()

        monkeypatch.setattr(adapters.synthetic, "probe", counted_probe)

        with pytest.raises(DecisionResolutionError) as permission_error:
            await resolve_permission_decision(
                store,
                adapters,
                intervention_id=permission.id,
                decision="allow",
            )
        with pytest.raises(DecisionResolutionError) as lifecycle_error:
            await resolve_lifecycle_decision(
                store,
                adapters,
                executor,
                intervention_id=lifecycle.id,
                decision="allow",
            )

        assert permission_error.value.status_code == 409
        assert lifecycle_error.value.status_code == 409
        assert probes == 0
        assert executor.calls == []
        assert await store.get_permission_resolution(permission.id) is None
        assert await store.get_lifecycle_resolution(lifecycle.id) is None
    finally:
        await store.close()


@pytest.mark.parametrize(
    ("scenario", "expected_status"),
    [
        ("live_permission_deny", SessionStatus.WORKING),
        ("quarantined_permission_deny", SessionStatus.NEEDS_DECISION),
        ("quarantined_stop", SessionStatus.STOPPED),
    ],
)
@pytest.mark.asyncio
async def test_containment_finalization_projects_only_safe_session_state(
    tmp_path,
    scenario: str,
    expected_status: SessionStatus,
):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    suffix = f"containment-finalize-{scenario}"
    try:
        _, session, _ = await _seed(store, suffix=suffix)
        if scenario.endswith("permission_deny"):
            intervention = _permission_intervention(session, suffix=suffix)
            await _reserve_permission(store, intervention, decision="deny")
            if scenario.startswith("quarantined"):
                await _quarantine(store, suffix=suffix)
            started = await store.start_permission_resolution_dispatch(intervention.id)
            assert started["granted"] is True

            completed = intervention.model_copy(deep=True)
            completed.result = "permission_deny"
            completed.outcome = "human_permission_delivered"
            requested_session = session.model_copy(
                update={"status": SessionStatus.WORKING, "last_activity": utcnow()}
            )
            await store.finalize_permission_resolution(
                completed,
                requested_session,
                status="delivered",
                delivery_result="permission_deny",
                finished_at=utcnow(),
                record_type="human_decision_resolved",
            )
        else:
            intervention = _lifecycle_intervention(
                InterventionType.STOP_AGENT,
                session,
                suffix=suffix,
            )
            await _reserve_lifecycle(store, intervention)
            await _quarantine(store, suffix=suffix)
            started = await store.start_lifecycle_resolution_dispatch(intervention.id)
            assert started["granted"] is True

            completed = intervention.model_copy(deep=True)
            completed.result = "agent_stopped"
            completed.outcome = "human_lifecycle_delivered"
            requested_session = session.model_copy(
                update={"status": SessionStatus.STOPPED, "last_activity": utcnow()}
            )
            await store.finalize_lifecycle_resolution(
                completed,
                requested_session,
                {
                    **started["resolution"],
                    "status": "delivered",
                    "delivery_result": "agent_stopped",
                    "finished_at": utcnow().isoformat(),
                },
                record_type="human_lifecycle_resolved",
            )

        current = await store.get_session(session.id)
        assert current is not None
        assert current.status == expected_status
    finally:
        await store.close()
