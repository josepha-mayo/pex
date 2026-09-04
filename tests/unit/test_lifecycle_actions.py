from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.base import AdapterMessageResult
from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport
from pex_bridge.executor import ActionExecutor, _message_execution_result
from pex_bridge.policy.engine import PolicyEngine
from pex_bridge.store import Store, new_id, utcnow
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.context import ContextBundle
from pex_protocol.enums import Authority, AutonomyLevel, HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessSession


async def _runtime(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    source = adapters.synthetic.seed_session(
        vendor_id="source",
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
            title="Exercise lifecycle actions",
            objective="Keep lifecycle effects bound to one explicit local goal.",
            created_at=now,
            updated_at=now,
        )
    )
    await store.upsert_session(source)
    return store, adapters, source, ActionExecutor(adapters, store)


def _action(kind: InterventionType, session_id: str, payload: dict) -> ProposedAction:
    return ProposedAction(
        type=kind,
        session_id=session_id,
        goal_id="goal-1",
        payload=payload,
        rationale="Observed lifecycle work is required.",
        evidence=["event:observed"],
        confidence=0.9,
        risk=RiskLevel.LOW,
        reversible=kind == InterventionType.CLEANUP,
        authority_required=(
            Authority.LOCAL_POLICY if kind == InterventionType.CLEANUP else Authority.HUMAN
        ),
    )


def _bundle(source_id: str) -> ContextBundle:
    return ContextBundle(
        goal_id="goal-1",
        target_session_id=source_id,
        source_session_ids=[source_id],
        goal_summary="Investigate one isolated hypothesis.",
        acceptance_criteria=["Return evidence without mutating the source session."],
        direct_evidence=["failure:repeatable"],
        next_objective="Test the bounded hypothesis.",
        created_at=datetime.now(UTC),
    )


async def _reserve_lifecycle_dispatch(store: Store, action: ProposedAction) -> str:
    intervention = Intervention(
        id=new_id("int_lifecycle_test_"),
        session_id=action.session_id,
        goal_id=action.goal_id,
        trigger="status",
        evidence=action.evidence,
        diagnosis="focused lifecycle executor test",
        proposed_action=action.model_copy(deep=True),
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ASK_HUMAN,
        result="awaiting_human",
        created_at=utcnow(),
    )
    await store.add_intervention(intervention)
    created, _ = await store.reserve_lifecycle_resolution(
        intervention_id=intervention.id,
        session_id=action.session_id,
        decision="allow",
        started_at=utcnow(),
    )
    assert created is True
    started = await store.start_lifecycle_resolution_dispatch(intervention.id)
    assert started["granted"] is True
    return intervention.id


async def _execute_granted_lifecycle(
    store: Store,
    executor: ActionExecutor,
    action: ProposedAction,
) -> str:
    intervention_id = await _reserve_lifecycle_dispatch(store, action)
    return await executor.execute(
        action,
        PolicyVerdict.ALLOW,
        human_authorized=True,
        lifecycle_resolution_id=intervention_id,
    )


@pytest.mark.asyncio
async def test_synthetic_start_stop_and_fork_are_real_and_durable(tmp_path):
    store, adapters, source, executor = await _runtime(tmp_path)
    try:
        start = _action(
            InterventionType.START_AGENT,
            source.id,
            {
                "project": str(tmp_path),
                "prompt": "Run the bounded offline probe.",
                "config": {"goal_id": "goal-1"},
            },
        )
        started = await _execute_granted_lifecycle(store, executor, start)
        assert started.startswith("agent_started:synthetic:")
        started_id = started.removeprefix("agent_started:")
        created = await store.get_session(started_id)
        assert created is not None
        assert created.metadata["lifecycle_parent_session_id"] == source.id
        assert adapters.synthetic.inbox[started_id] == ["Run the bounded offline probe."]

        assert (
            await executor._stop_agent(created, adapters.synthetic)
            == "agent_stopped"
        )
        stopped = await store.get_session(started_id)
        assert stopped is not None
        assert stopped.status == SessionStatus.STOPPED

        fork = _action(
            InterventionType.FORK_PROBE,
            source.id,
            {"bundle": _bundle(source.id).model_dump(mode="json")},
        )
        forked = await _execute_granted_lifecycle(store, executor, fork)
        assert forked.startswith("probe_forked:synthetic:")
        child_id = forked.removeprefix("probe_forked:")
        child = await store.get_session(child_id)
        assert child is not None
        assert child.metadata["forked_from"] == source.id
        assert child.metadata["probe"] is True
        assert "Investigate one isolated hypothesis" in adapters.synthetic.inbox[child_id][0]

        mismatched_bundle = _bundle(source.id).model_copy(
            update={"goal_id": "other-goal"}
        )
        mismatch = _action(
            InterventionType.FORK_PROBE,
            source.id,
            {"bundle": mismatched_bundle.model_dump(mode="json")},
        )
        before = set(adapters.synthetic.sessions)
        assert (
            await _execute_granted_lifecycle(store, executor, mismatch)
            == "probe_fork_context_mismatch"
        )
        assert set(adapters.synthetic.sessions) == before
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_fork_probe_sends_approach_a_to_parent_and_b_to_child(tmp_path):
    store, adapters, source, executor = await _runtime(tmp_path)
    try:
        bundle = _bundle(source.id).model_copy(
            update={"next_objective": "Isolated speculative probe. Try only this approach: sqlite."}
        )
        fork = _action(
            InterventionType.FORK_PROBE,
            source.id,
            {
                "bundle": bundle.model_dump(mode="json"),
                "parent_objective": (
                    "Isolated speculative probe. Try only this approach: in-memory."
                ),
                "approaches": ["in-memory", "sqlite"],
            },
        )
        before = set(adapters.synthetic.sessions)
        forked = await _execute_granted_lifecycle(store, executor, fork)
        assert forked.startswith("probe_forked:synthetic:")
        child_id = forked.removeprefix("probe_forked:")
        assert child_id not in before
        child = await store.get_session(child_id)
        parent = await store.get_session(source.id)
        assert child is not None and parent is not None
        assert parent.metadata["speculative"]["role"] == "a"
        assert child.metadata["speculative"]["role"] == "b"
        assert child.metadata["speculative"]["pair_id"] == parent.metadata["speculative"]["pair_id"]
        assert "in-memory" in adapters.synthetic.inbox[source.id][-1]
        assert "sqlite" in adapters.synthetic.inbox[child_id][0]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_lifecycle_reprobes_and_rejects_stale_capability(tmp_path, monkeypatch):
    store, adapters, source, executor = await _runtime(tmp_path)

    async def unavailable() -> AdapterCapabilities:
        return AdapterCapabilities(notes="live control disappeared")

    monkeypatch.setattr(adapters.synthetic, "probe", unavailable)
    try:
        action = _action(
            InterventionType.START_AGENT,
            source.id,
            {"project": str(tmp_path), "prompt": "Do not run.", "config": {}},
        )
        assert (
            await _execute_granted_lifecycle(store, executor, action)
            == "agent_start_unsupported"
        )
        assert len(adapters.synthetic.sessions) == 1
        stored = await store.get_session(source.id)
        assert stored is not None
        assert stored.capabilities["start"] is False
    finally:
        await store.close()


@pytest.mark.parametrize(
    "kind",
    [
        InterventionType.START_AGENT,
        InterventionType.STOP_AGENT,
        InterventionType.FORK_PROBE,
        InterventionType.CLEANUP,
    ],
)
@pytest.mark.asyncio
async def test_lifecycle_allow_cannot_bypass_explicit_human_gate(tmp_path, kind):
    store, adapters, source, executor = await _runtime(tmp_path)
    try:
        action = _action(
            kind,
            source.id,
            {"project": str(tmp_path), "prompt": "Do not start.", "config": {}},
        )
        assert await executor.execute(action, PolicyVerdict.ALLOW) == (
            "lifecycle_human_authorization_required"
        )
        assert len(adapters.synthetic.sessions) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_forged_lifecycle_resolution_id_cannot_reach_adapter_io(tmp_path, monkeypatch):
    store, adapters, source, executor = await _runtime(tmp_path)
    try:
        probe_calls = 0

        async def poisoned_probe():
            nonlocal probe_calls
            probe_calls += 1
            raise AssertionError("a forged grant must not reach the adapter")

        monkeypatch.setattr(adapters.synthetic, "probe", poisoned_probe)
        action = _action(
            InterventionType.START_AGENT,
            source.id,
            {"project": str(tmp_path), "prompt": "Do not start.", "config": {}},
        )

        assert (
            await executor.execute(
                action,
                PolicyVerdict.ALLOW,
                human_authorized=True,
                lifecycle_resolution_id="int_forged_dispatch",
            )
            == "lifecycle_dispatch_grant_invalid"
        )
        assert probe_calls == 0
        assert len(adapters.synthetic.sessions) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_requires_durable_dispatch_before_filesystem_path(tmp_path, monkeypatch):
    store, _, source, executor = await _runtime(tmp_path)
    try:
        source.status = SessionStatus.STOPPED
        await store.upsert_session(source)
        cleanup_calls = 0

        async def poisoned_cleanup(*_args, **_kwargs):
            nonlocal cleanup_calls
            cleanup_calls += 1
            raise AssertionError("ungranted cleanup must not inspect or mutate filesystem paths")

        monkeypatch.setattr(executor, "_cleanup", poisoned_cleanup)
        action = _action(
            InterventionType.CLEANUP,
            source.id,
            {"mode": "quarantine", "resource_ids": ["resource_untrusted"]},
        )

        assert (
            await executor.execute(
                action,
                PolicyVerdict.ALLOW,
                human_authorized=True,
                lifecycle_resolution_id="int_forged_cleanup",
            )
            == "lifecycle_dispatch_grant_invalid"
        )
        assert cleanup_calls == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_raw_cleanup_restore_is_rejected_before_registry_or_filesystem_io(
    tmp_path,
    monkeypatch,
):
    store, _, source, executor = await _runtime(tmp_path)
    try:
        registry_calls = 0

        async def poisoned_resource_lookup(*_args, **_kwargs):
            nonlocal registry_calls
            registry_calls += 1
            raise AssertionError("raw restore must not inspect an unbound resource")

        monkeypatch.setattr(store, "get_lifecycle_resource", poisoned_resource_lookup)
        assert await executor.restore_cleanup(
            source.id,
            [
                {
                    "resource_id": "resource_untrusted",
                    "original_path": str(tmp_path / "original"),
                    "quarantine_path": str(tmp_path / "quarantine"),
                }
            ],
        ) == "cleanup_restore_reservation_required"
        assert registry_calls == 0
        assert not (tmp_path / "original").exists()
        assert not (tmp_path / "quarantine").exists()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_durable_lifecycle_grant_rejects_action_drift_before_adapter_io(
    tmp_path,
    monkeypatch,
):
    store, adapters, source, executor = await _runtime(tmp_path)
    try:
        action = _action(
            InterventionType.START_AGENT,
            source.id,
            {"project": str(tmp_path), "prompt": "Original prompt.", "config": {}},
        )
        intervention_id = await _reserve_lifecycle_dispatch(store, action)
        changed = action.model_copy(deep=True)
        changed.payload["prompt"] = "Mutated after dispatch reservation."
        probe_calls = 0

        async def poisoned_probe():
            nonlocal probe_calls
            probe_calls += 1
            raise AssertionError("a drifted action must not reach the adapter")

        monkeypatch.setattr(adapters.synthetic, "probe", poisoned_probe)

        assert (
            await executor.execute(
                changed,
                PolicyVerdict.ALLOW,
                human_authorized=True,
                lifecycle_resolution_id=intervention_id,
            )
            == "lifecycle_dispatch_grant_invalid"
        )
        assert probe_calls == 0
        assert len(adapters.synthetic.sessions) == 1
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
async def test_durable_lifecycle_grant_rejects_project_rebind_before_any_io(
    tmp_path,
    monkeypatch,
    kind: InterventionType,
):
    project_id = str(tmp_path)
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    try:
        first = await store.register_project_locator(
            legacy_project_id=project_id,
            locator=ProjectLocator.path(
                "/workspace/lifecycle-authority-a",
                platform=PathPlatform.POSIX,
                origin=ProjectOrigin(
                    namespace="machine",
                    host="lifecycle-executor-test",
                ),
            ),
        )
        source = adapters.synthetic.seed_session(
            vendor_id=f"rebind-{kind.value.lower()}",
            project_id=project_id,
            cwd=project_id,
            goal_id="goal-1",
        )
        if kind == InterventionType.CLEANUP:
            source.status = SessionStatus.STOPPED
            adapters.synthetic.sessions[source.id].status = SessionStatus.STOPPED
        source.capabilities = (await adapters.synthetic.probe()).model_dump(mode="json")
        now = utcnow()
        await store.upsert_goal(
            Goal(
                id="goal-1",
                project_id=project_id,
                title="Reject lifecycle dispatch after project rebinding",
                objective="Keep every lifecycle effect on its creation-time project.",
                created_at=now,
                updated_at=now,
            )
        )
        await store.upsert_session(source)
        payload = {
            InterventionType.START_AGENT: {
                "project": project_id,
                "prompt": "This must not start after rebinding.",
                "config": {"goal_id": "goal-1"},
            },
            InterventionType.STOP_AGENT: {},
            InterventionType.FORK_PROBE: {
                "bundle": _bundle(source.id).model_dump(mode="json")
            },
            InterventionType.CLEANUP: {
                "mode": "quarantine",
                "resource_ids": ["resource_must_not_be_read"],
            },
        }[kind]
        action = _action(kind, source.id, payload)
        intervention_id = await _reserve_lifecycle_dispatch(store, action)

        second = await store.register_project_locator(
            legacy_project_id=project_id,
            locator=ProjectLocator.path(
                "/workspace/lifecycle-authority-b",
                platform=PathPlatform.POSIX,
                origin=ProjectOrigin(
                    namespace="machine",
                    host="lifecycle-executor-test",
                ),
            ),
        )
        assert second["outcome"] == "quarantined"
        await store.resolve_project_identity_conflict(
            resolution_id=f"resolve-rebind-{kind.value.lower()}",
            legacy_project_id=project_id,
            selected_identity_id=second["identity"].id,
            resolved_by="test_operator",
            rationale="Select project B to invalidate project A's durable dispatch grant.",
        )
        assert first["identity"].id != second["identity"].id

        probe_calls = 0
        cleanup_calls = 0

        async def poisoned_probe():
            nonlocal probe_calls
            probe_calls += 1
            raise AssertionError("a rebound lifecycle grant must not probe an adapter")

        async def poisoned_cleanup(*_args, **_kwargs):
            nonlocal cleanup_calls
            cleanup_calls += 1
            raise AssertionError("a rebound cleanup grant must not inspect filesystem state")

        monkeypatch.setattr(adapters.synthetic, "probe", poisoned_probe)
        executor = ActionExecutor(adapters, store)
        monkeypatch.setattr(executor, "_cleanup", poisoned_cleanup)

        assert (
            await executor.execute(
                action,
                PolicyVerdict.ALLOW,
                human_authorized=True,
                lifecycle_resolution_id=intervention_id,
            )
            == "lifecycle_dispatch_grant_invalid"
        )
        assert probe_calls == 0
        assert cleanup_calls == 0
        assert len(adapters.synthetic.sessions) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_denied_pex_permission_action_does_not_deny_worker_request(tmp_path):
    store, adapters, source, executor = await _runtime(tmp_path)
    try:
        action = _action(
            InterventionType.RESPOND_PERMISSION,
            source.id,
            {"request_id": "permission-1", "decision": "deny"},
        )
        result = await executor.execute(action, PolicyVerdict.DENY)
        assert result == "denied_by_policy"
        assert adapters.synthetic.permissions.get(source.id, []) == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_executor_rejects_missing_permission_decision_before_adapter_io(tmp_path):
    store, adapters, source, executor = await _runtime(tmp_path)
    try:
        action = _action(
            InterventionType.RESPOND_PERMISSION,
            source.id,
            {"request_id": "permission-1"},
        )
        assert (
            await executor.execute(action, PolicyVerdict.ALLOW)
            == "permission_invalid_decision"
        )
        assert adapters.synthetic.permissions.get(source.id, []) == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_executor_rejects_cross_goal_action_before_worker_io(tmp_path):
    store, adapters, source, executor = await _runtime(tmp_path)
    try:
        action = _action(
            InterventionType.SEND_NUDGE,
            source.id,
            {"text": "This must not cross the goal boundary."},
        )
        action.goal_id = "different-goal"
        assert await executor.execute(action, PolicyVerdict.ALLOW) == "action_goal_mismatch"
        assert adapters.synthetic.inbox[source.id] == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_executor_rejects_misdirected_handoff_bundle_before_worker_io(tmp_path):
    store, adapters, source, executor = await _runtime(tmp_path)
    try:
        bundle = _bundle("synthetic:someone-else")
        action = _action(
            InterventionType.FRESH_HANDOFF,
            source.id,
            {"bundle": bundle.model_dump(mode="json")},
        )
        assert (
            await executor.execute(action, PolicyVerdict.ALLOW)
            == "handoff_context_mismatch"
        )
        assert adapters.synthetic.inbox[source.id] == []
    finally:
        await store.close()


def test_bare_non_codex_adapter_acceptance_becomes_terminal_uncertainty():
    session = HarnessSession(
        id="synthetic:receipt-validation",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="receipt-validation",
    )

    assert (
        _message_execution_result(
            True,
            session=session,
            accepted_outcome="sent",
            rejected_outcome="send_failed",
        )
        == "send_delivery_uncertain"
    )


def test_synthetic_turn_receipt_is_terminal_delivery():
    session = HarnessSession(
        id="synthetic:receipt-validation",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="receipt-validation",
    )
    result = _message_execution_result(
        AdapterMessageResult(
            accepted=True,
            vendor_session_id=session.vendor_session_id,
            vendor_turn_id="syn-turn-0001",
        ),
        session=session,
        accepted_outcome="sent",
        rejected_outcome="send_failed",
    )

    assert result.outcome == "sent"
    assert result.worker_delivery_receipt == {
        "schema": "pex.worker-delivery.v1",
        "target_session_id": session.id,
        "vendor_session_id": session.vendor_session_id,
        "vendor_turn_id": "syn-turn-0001",
    }


def test_qwen_prompt_receipt_keeps_generic_schema_not_codex():
    session = HarnessSession(
        id="qwen:thread-1",
        harness_type=HarnessType.QWEN,
        vendor_session_id="thread-1",
    )
    result = _message_execution_result(
        AdapterMessageResult(
            accepted=True,
            vendor_session_id=session.vendor_session_id,
            vendor_turn_id="prompt-abc",
        ),
        session=session,
        accepted_outcome="sent",
        rejected_outcome="send_failed",
    )

    assert result.outcome == "sent"
    assert result.worker_delivery_receipt["schema"] == "pex.worker-delivery.v1"
    assert result.worker_delivery_receipt["vendor_turn_id"] == "prompt-abc"


def test_codex_turn_receipt_keeps_codex_schema():
    session = HarnessSession(
        id="codex:thread-1",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-1",
    )
    result = _message_execution_result(
        AdapterMessageResult(
            accepted=True,
            vendor_session_id=session.vendor_session_id,
            vendor_turn_id="turn_1",
        ),
        session=session,
        accepted_outcome="sent",
        rejected_outcome="send_failed",
    )

    assert result.outcome == "sent"
    assert result.worker_delivery_receipt["schema"] == "pex.worker-delivery.codex-turn.v1"


def test_malformed_adapter_turn_receipt_becomes_terminal_uncertainty():
    session = HarnessSession(
        id="codex:receipt-validation",
        harness_type=HarnessType.CODEX,
        vendor_session_id="receipt-validation",
    )
    malformed = AdapterMessageResult(
        accepted=True,
        vendor_session_id=session.vendor_session_id,
        vendor_turn_id=7,  # type: ignore[arg-type]
    )

    assert (
        _message_execution_result(
            malformed,
            session=session,
            accepted_outcome="sent",
            rejected_outcome="send_failed",
        )
        == "send_delivery_uncertain"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "method_name", "expected"),
    [
        (InterventionType.SEND_NUDGE, "send_message", "send_delivery_uncertain"),
        (
            InterventionType.REQUEST_VERIFICATION,
            "send_message",
            "verification_delivery_uncertain",
        ),
        (
            InterventionType.CONTINUE_SESSION,
            "continue_or_resume",
            "continue_delivery_uncertain",
        ),
    ],
)
async def test_worker_delivery_calls_are_bounded(
    tmp_path,
    monkeypatch,
    kind: InterventionType,
    method_name: str,
    expected: str,
):
    import pex_bridge.executor as executor_module

    store, adapters, source, executor = await _runtime(tmp_path)

    async def stalled(*_args, **_kwargs):
        await asyncio.sleep(10)
        return True

    monkeypatch.setattr(executor_module, "MESSAGE_ADAPTER_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(adapters.synthetic, method_name, stalled)
    try:
        action = _action(kind, source.id, {"text": "Run the exact focused check."})
        assert await executor.execute(action, PolicyVerdict.ALLOW) == expected
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_started_child_keeps_live_capabilities_returned_by_adapter(tmp_path, monkeypatch):
    store, adapters, source, executor = await _runtime(tmp_path)

    async def start_session(*_args, **_kwargs):
        return HarnessSession(
            id="synthetic:child-with-live-caps",
            harness_type=HarnessType.SYNTHETIC,
            vendor_session_id="child-with-live-caps",
            project_id=source.project_id,
            cwd=source.cwd,
            capabilities={"send_message": False, "focus_ui": True},
        )

    monkeypatch.setattr(adapters.synthetic, "start_session", start_session)
    try:
        action = _action(
            InterventionType.START_AGENT,
            source.id,
            {"project": str(tmp_path), "prompt": "Inspect only.", "config": {}},
        )
        result = await _execute_granted_lifecycle(store, executor, action)
        assert result == "agent_started:synthetic:child-with-live-caps"
        child = await store.get_session("synthetic:child-with-live-caps")
        assert child is not None
        assert child.capabilities == {"send_message": False, "focus_ui": True}
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_start_rejects_cross_goal_config_before_adapter_io(tmp_path, monkeypatch):
    store, adapters, source, executor = await _runtime(tmp_path)
    try:
        probe_calls = 0

        async def poisoned_probe():
            nonlocal probe_calls
            probe_calls += 1
            raise AssertionError("invalid start must not probe the adapter")

        monkeypatch.setattr(adapters.synthetic, "probe", poisoned_probe)
        action = _action(
            InterventionType.START_AGENT,
            source.id,
            {
                "project": str(tmp_path),
                "prompt": "Do not start.",
                "config": {"goal_id": "other-goal"},
            },
        )
        assert (
            await _execute_granted_lifecycle(store, executor, action)
            == "agent_start_goal_mismatch"
        )
        assert len(adapters.synthetic.sessions) == 1
        assert probe_calls == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_fork_rejects_invalid_binding_before_adapter_probe(tmp_path, monkeypatch):
    store, adapters, source, executor = await _runtime(tmp_path)
    try:
        probe_calls = 0

        async def poisoned_probe():
            nonlocal probe_calls
            probe_calls += 1
            raise AssertionError("invalid fork must not probe the adapter")

        monkeypatch.setattr(adapters.synthetic, "probe", poisoned_probe)
        mismatched = _bundle(source.id).model_copy(update={"goal_id": "other-goal"})
        action = _action(
            InterventionType.FORK_PROBE,
            source.id,
            {"bundle": mismatched.model_dump(mode="json")},
        )

        assert (
            await _execute_granted_lifecycle(store, executor, action)
            == "probe_fork_context_mismatch"
        )
        assert probe_calls == 0
        assert len(adapters.synthetic.sessions) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_only_quarantines_registered_pex_owned_child(tmp_path):
    store, _, source, executor = await _runtime(tmp_path)
    project = tmp_path / "project"
    scratch = project / "scratch" / "probe.txt"
    scratch.parent.mkdir(parents=True)
    scratch.write_text("recoverable", encoding="utf-8")
    try:
        resource = await store.register_lifecycle_resource(
            session_id=source.id,
            path=scratch,
            scope_root=project,
            kind="scratch",
            created_by="test_probe",
        )
        action = _action(
            InterventionType.CLEANUP,
            source.id,
            {"mode": "quarantine", "resource_ids": [resource["id"]]},
        )
        with pytest.raises(PermissionError, match="source session is not stopped"):
            await _reserve_lifecycle_dispatch(store, action)
        with pytest.raises(ValueError, match="stopped source session"):
            await store.mark_lifecycle_resource_cleanup_ready(
                resource_id=resource["id"],
                session_id=source.id,
                evidence=["scratch_probe_expired"],
            )
        source.status = SessionStatus.STOPPED
        await store.upsert_session(source)
        intervention_id = await _reserve_lifecycle_dispatch(store, action)
        assert await executor.execute(
            action,
            PolicyVerdict.ALLOW,
            human_authorized=True,
            lifecycle_resolution_id=intervention_id,
        ) == "cleanup_reservation_refused"
        await store.mark_lifecycle_resource_cleanup_ready(
            resource_id=resource["id"],
            session_id=source.id,
            evidence=["source_session_stopped", "scratch_probe_expired"],
        )
        original_action = action.model_dump(mode="json")
        assert await executor.execute(
            action,
            PolicyVerdict.ALLOW,
            human_authorized=True,
            lifecycle_resolution_id=intervention_id,
        ) == "cleanup_quarantined:1"
        assert action.model_dump(mode="json") == original_action
        assert not scratch.exists()
        stored = await store.get_lifecycle_resource(resource["id"])
        assert stored is not None
        assert stored["state"] == "quarantined"
        quarantined = stored["quarantine_path"]
        assert (tmp_path / "quarantine").resolve() in Path(quarantined).resolve().parents

        assert (
            await executor.restore_cleanup(
                source.id,
                [
                    {
                        "resource_id": resource["id"],
                        "original_path": str(scratch.resolve()),
                        "quarantine_path": quarantined,
                    }
                ],
            )
            == "cleanup_restore_reservation_required"
        )
        assert not scratch.exists()
        assert Path(quarantined).read_text(encoding="utf-8") == "recoverable"
        unchanged = await store.get_lifecycle_resource(resource["id"])
        assert unchanged is not None
        assert unchanged["state"] == "quarantined"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_refuses_raw_or_unregistered_targets_without_moving_them(tmp_path):
    store, _, source, executor = await _runtime(tmp_path)
    untouched = tmp_path / "user-data.txt"
    untouched.write_text("keep", encoding="utf-8")
    try:
        source.status = SessionStatus.STOPPED
        await store.upsert_session(source)
        raw_path = _action(
            InterventionType.CLEANUP,
            source.id,
            {"mode": "quarantine", "paths": [str(untouched)]},
        )
        assert await _execute_granted_lifecycle(
            store,
            executor,
            raw_path,
        ) == "cleanup_reservation_refused"
        unknown = _action(
            InterventionType.CLEANUP,
            source.id,
            {"mode": "quarantine", "resource_ids": ["res_unknown"]},
        )
        assert await _execute_granted_lifecycle(store, executor, unknown) == (
            "cleanup_reservation_refused"
        )
        assert untouched.read_text(encoding="utf-8") == "keep"
        with pytest.raises(ValueError, match="scope root"):
            await store.register_lifecycle_resource(
                session_id=source.id,
                path=tmp_path,
                scope_root=tmp_path,
                kind="scratch",
                created_by="invalid",
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_reports_uncertainty_when_finalization_persistence_fails(
    tmp_path,
    monkeypatch,
):
    store, _, source, executor = await _runtime(tmp_path)
    project = tmp_path / "project"
    scratch = project / "scratch" / "probe.txt"
    scratch.parent.mkdir(parents=True)
    scratch.write_text("recoverable", encoding="utf-8")
    try:
        resource = await store.register_lifecycle_resource(
            session_id=source.id,
            path=scratch,
            scope_root=project,
            kind="scratch",
            created_by="test_probe",
        )
        source.status = SessionStatus.STOPPED
        await store.upsert_session(source)
        await store.mark_lifecycle_resource_cleanup_ready(
            resource_id=resource["id"],
            session_id=source.id,
            evidence=["source_session_stopped", "scratch_probe_expired"],
        )
        async def fail_finalization(*_args, **_kwargs):
            raise RuntimeError("simulated final operation persistence failure")

        monkeypatch.setattr(store, "finalize_cleanup_operation", fail_finalization)
        action = _action(
            InterventionType.CLEANUP,
            source.id,
            {"mode": "quarantine", "resource_ids": [resource["id"]]},
        )
        original_action = action.model_dump(mode="json")
        assert await _execute_granted_lifecycle(store, executor, action) == (
            "cleanup_finalization_uncertain"
        )
        assert action.model_dump(mode="json") == original_action
        record = await store.get_lifecycle_resource(resource["id"])
        assert record is not None
        assert record["state"] == "quarantining"
        assert not scratch.exists()
        assert Path(record["quarantine_path"]).read_text(encoding="utf-8") == "recoverable"
        assert (
            await executor.restore_cleanup(
                source.id,
                [
                    {
                        "resource_id": resource["id"],
                        "original_path": str(scratch.resolve()),
                        "quarantine_path": record["quarantine_path"],
                    }
                ],
            )
            == "cleanup_restore_reservation_required"
        )
        assert not scratch.exists()
        assert Path(record["quarantine_path"]).read_text(encoding="utf-8") == "recoverable"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_restore_refuses_unreserved_durable_pre_move_state(tmp_path):
    store, _, source, executor = await _runtime(tmp_path)
    project = tmp_path / "project"
    scratch = project / "scratch" / "probe.txt"
    scratch.parent.mkdir(parents=True)
    scratch.write_text("still-original", encoding="utf-8")
    try:
        resource = await store.register_lifecycle_resource(
            session_id=source.id,
            path=scratch,
            scope_root=project,
            kind="scratch",
            created_by="test_probe",
        )
        source.status = SessionStatus.STOPPED
        await store.upsert_session(source)
        await store.mark_lifecycle_resource_cleanup_ready(
            resource_id=resource["id"],
            session_id=source.id,
            evidence=["source_session_stopped", "simulated_crash_after_prepare"],
        )
        resource = await store.get_lifecycle_resource(resource["id"])
        assert resource is not None
        quarantine = tmp_path / "quarantine" / "cleanup-crashed" / resource["id"] / scratch.name
        resource.update(
            {
                "state": "quarantining",
                "cleanup_run_id": "cleanup-crashed",
                "quarantine_path": str(quarantine.resolve()),
            }
        )
        with pytest.raises(PermissionError, match="generic lifecycle resource updates"):
            await store.update_lifecycle_resources([resource])
        manifest = [
            {
                "resource_id": resource["id"],
                "original_path": str(scratch.resolve()),
                "quarantine_path": str(quarantine.resolve()),
            }
        ]
        assert await executor.restore_cleanup(source.id, manifest) == (
            "cleanup_restore_reservation_required"
        )
        assert scratch.read_text(encoding="utf-8") == "still-original"
        unchanged = await store.get_lifecycle_resource(resource["id"])
        assert unchanged is not None
        assert unchanged["state"] == "cleanup_ready"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_registry_compare_and_swap_allows_only_one_run(tmp_path):
    store, _, source, _ = await _runtime(tmp_path)
    project = tmp_path / "project"
    scratch = project / "scratch" / "probe.txt"
    scratch.parent.mkdir(parents=True)
    scratch.write_text("recoverable", encoding="utf-8")
    try:
        resource = await store.register_lifecycle_resource(
            session_id=source.id,
            path=scratch,
            scope_root=project,
            kind="scratch",
            created_by="test_probe",
        )
        source.status = SessionStatus.STOPPED
        await store.upsert_session(source)
        ready = await store.mark_lifecycle_resource_cleanup_ready(
            resource_id=resource["id"],
            session_id=source.id,
            evidence=["source_session_stopped", "scratch_probe_expired"],
        )
        first = {
            **ready,
            "state": "quarantining",
            "cleanup_run_id": "cleanup-first",
            "quarantine_path": str(tmp_path / "quarantine" / "first"),
        }
        second = {
            **ready,
            "state": "quarantining",
            "cleanup_run_id": "cleanup-second",
            "quarantine_path": str(tmp_path / "quarantine" / "second"),
        }

        outcomes = await asyncio.gather(
            store.update_lifecycle_resources([first]),
            store.update_lifecycle_resources([second]),
            return_exceptions=True,
        )

        assert all(isinstance(outcome, PermissionError) for outcome in outcomes)
        stored = await store.get_lifecycle_resource(resource["id"])
        assert stored is not None
        assert stored["state"] == "cleanup_ready"
        assert stored.get("cleanup_run_id") is None
    finally:
        await store.close()


def test_policy_requires_human_for_agent_lifecycle_even_in_autopilot():
    policy = PolicyEngine(AutonomyLevel.AUTOPILOT)
    for kind in {
        InterventionType.START_AGENT,
        InterventionType.STOP_AGENT,
        InterventionType.FORK_PROBE,
    }:
        assert policy.decide(_action(kind, "synthetic:s1", {})) == PolicyVerdict.ASK_HUMAN


@pytest.mark.asyncio
async def test_human_gate_overwrites_untrusted_previous_status(tmp_path):
    store, adapters, source, executor = await _runtime(tmp_path)
    try:
        action = _action(
            InterventionType.START_AGENT,
            source.id,
            {
                "project": str(tmp_path),
                "prompt": "Wait for a real human decision.",
                "config": {},
                "previous_session_status": SessionStatus.STOPPED.value,
            },
        )
        assert await executor.execute(action, PolicyVerdict.ASK_HUMAN) == "awaiting_human"
        assert action.payload["previous_session_status"] == SessionStatus.WORKING.value
        pending = await store.get_session(source.id)
        assert pending is not None
        assert pending.status == SessionStatus.NEEDS_DECISION
        assert len(adapters.synthetic.sessions) == 1
    finally:
        await store.close()


def test_policy_requires_human_for_cleanup_without_standing_policy():
    for autonomy in {AutonomyLevel.MANAGE, AutonomyLevel.AUTOPILOT}:
        policy = PolicyEngine(autonomy)
        safe = _action(
            InterventionType.CLEANUP,
            "synthetic:s1",
            {"mode": "quarantine", "resource_ids": ["res_1"]},
        )
        assert policy.decide(safe) == PolicyVerdict.ASK_HUMAN
        unsafe = safe.model_copy(deep=True)
        unsafe.payload = {"mode": "delete", "resource_ids": ["res_1"]}
        assert policy.decide(unsafe) == PolicyVerdict.ASK_HUMAN


@pytest.mark.asyncio
async def test_codex_start_uses_isolated_workspace_write_thread(tmp_path):
    transport = CodexAppServerTransport()
    adapter = CodexAdapter(transport)
    session = await adapter.start_session(
        str(tmp_path),
        "Inspect the local fixture only.",
        {"name": "offline-test"},
    )
    assert session is not None
    assert session.metadata["sandbox"] == "workspace-write"
    assert session.metadata["started_by_pex"] is True
    assert transport.turns[-1]["approvalPolicy"] == "never"
    assert transport.turns[-1]["sandboxPolicy"]["type"] == "workspaceWrite"
    assert transport.turns[-1]["sandboxPolicy"]["networkAccess"] is False
