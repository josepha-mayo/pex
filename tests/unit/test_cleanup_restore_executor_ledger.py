from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.decisions import resolve_lifecycle_decision
from pex_bridge.executor import ActionExecutor
from pex_bridge.store import Store, new_id, utcnow
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention

AUTHORIZER = "local_bridge_operator"


async def _runtime(
    tmp_path: Path,
) -> tuple[Store, AdapterRegistry, ActionExecutor, object]:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    source = adapters.synthetic.seed_session(
        vendor_id="restore-source",
        project_id=str(tmp_path),
        cwd=str(tmp_path),
        goal_id="restore-goal",
    )
    source.capabilities = (await adapters.synthetic.probe()).model_dump(mode="json")
    now = utcnow()
    await store.upsert_goal(
        Goal(
            id="restore-goal",
            project_id=str(tmp_path),
            title="Exercise cleanup restore ledger",
            objective="Restore only an exact operator-authorized quarantine manifest.",
            created_at=now,
            updated_at=now,
        )
    )
    await store.upsert_session(source)
    return store, adapters, ActionExecutor(adapters, store), source


def _cleanup_action(session_id: str, resource_ids: list[str]) -> ProposedAction:
    return ProposedAction(
        type=InterventionType.CLEANUP,
        session_id=session_id,
        goal_id="restore-goal",
        payload={"mode": "quarantine", "resource_ids": resource_ids},
        rationale="The stopped source left exact PEX-owned scratch.",
        evidence=["source_session_stopped", "producer_marked_cleanup_ready"],
        confidence=0.99,
        risk=RiskLevel.LOW,
        reversible=True,
        authority_required=Authority.LOCAL_POLICY,
    )


async def _completed_cleanup(
    store: Store,
    adapters: AdapterRegistry,
    executor: ActionExecutor,
    source: object,
    tmp_path: Path,
    *,
    count: int = 1,
) -> tuple[str, ProposedAction, list[dict], list[Path]]:
    project = tmp_path / "project"
    scratch_root = project / "scratch"
    scratch_root.mkdir(parents=True)
    resources: list[dict] = []
    paths: list[Path] = []
    for index in range(count):
        path = scratch_root / f"resource-{index}.txt"
        path.write_text(f"payload-{index}", encoding="utf-8")
        resources.append(
            await store.register_lifecycle_resource(
                session_id=source.id,
                path=path,
                scope_root=project,
                kind="scratch",
                created_by="cleanup_restore_executor_test_producer",
            )
        )
        paths.append(path)
    source.status = SessionStatus.STOPPED
    adapters.synthetic.sessions[source.id].status = SessionStatus.STOPPED
    await store.upsert_session(source)
    for resource in resources:
        await store.mark_lifecycle_resource_cleanup_ready(
            resource_id=resource["id"],
            session_id=source.id,
            evidence=["source session is stopped", "producer lease is closed"],
        )
    action = _cleanup_action(source.id, [resource["id"] for resource in resources])
    intervention = Intervention(
        id=new_id("int_cleanup_restore_"),
        session_id=source.id,
        goal_id=source.goal_id,
        trigger="status",
        evidence=action.evidence,
        diagnosis="bounded cleanup restore executor test",
        proposed_action=action.model_copy(deep=True),
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=True,
        authority_required=action.authority_required.value,
        action_taken=InterventionType.CLEANUP.value,
        policy_verdict=PolicyVerdict.ASK_HUMAN,
        result="awaiting_human",
        created_at=utcnow(),
    )
    await store.add_intervention(intervention)
    result = await resolve_lifecycle_decision(
        store,
        adapters,
        executor,
        intervention_id=intervention.id,
        decision="allow",
    )
    assert result.executed is True
    assert result.intervention.result == f"cleanup_quarantined:{count}"
    assert all(not path.exists() for path in paths)
    return intervention.id, action, resources, paths


async def _restore(
    executor: ActionExecutor,
    intervention_id: str,
    *,
    key: str,
) -> dict[str, object]:
    result = await executor.restore_cleanup(
        intervention_id,
        authorized_by=AUTHORIZER,
        idempotency_key=key,
    )
    assert isinstance(result, dict)
    return result


def _receipt_operation_id(result: dict[str, object]) -> str:
    receipt = result["receipt"]
    assert isinstance(receipt, dict)
    operation_id = receipt["operation_id"]
    assert isinstance(operation_id, str)
    return operation_id


@pytest.mark.asyncio
async def test_restore_success_is_path_free_and_preserves_frozen_action(tmp_path: Path):
    store, adapters, executor, source = await _runtime(tmp_path)
    try:
        intervention_id, action, resources, paths = await _completed_cleanup(
            store,
            adapters,
            executor,
            source,
            tmp_path,
        )
        original_action = action.model_dump_json()

        result = await _restore(executor, intervention_id, key="restore-success-0001")

        assert result["code"] == "cleanup_restored:1"
        assert result["ok"] is True
        assert result["status"] == "completed"
        assert result["replayed"] is False
        assert paths[0].read_text(encoding="utf-8") == "payload-0"
        resource = await store.get_lifecycle_resource(resources[0]["id"])
        assert resource is not None and resource["state"] == "active"
        operation = await store.get_restore_operation(_receipt_operation_id(result))
        assert operation is not None and operation["state"] == "completed"
        stored = await store.get_intervention(intervention_id)
        assert stored is not None
        assert stored.proposed_action.model_dump_json() == original_action
        assert stored.result == "cleanup_restored:1"
        rendered = json.dumps(result, sort_keys=True)
        assert str(tmp_path) not in rendered
        assert "manifest" not in rendered
        assert "fingerprint" not in rendered
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restore_start_denied_performs_zero_filesystem_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, adapters, executor, source = await _runtime(tmp_path)
    try:
        intervention_id, _, resources, paths = await _completed_cleanup(
            store, adapters, executor, source, tmp_path
        )
        resource = await store.get_lifecycle_resource(resources[0]["id"])
        assert resource is not None
        quarantine = Path(resource["quarantine_path"])

        async def deny_start(operation_id: str):
            operation = await store.get_restore_operation(operation_id)
            assert operation is not None
            return {
                "granted": False,
                "replayed": True,
                "operation": {**operation, "state": "dispatching"},
            }

        def move_must_not_run(_entry):
            raise AssertionError("restore filesystem path ran without a Store grant")

        monkeypatch.setattr(store, "start_restore_operation", deny_start)
        monkeypatch.setattr(executor, "_move_restore_entry", move_must_not_run)
        result = await _restore(executor, intervention_id, key="restore-denied-0001")
        assert result["code"] == "cleanup_restore_dispatch_in_progress"
        assert not paths[0].exists()
        assert quarantine.read_text(encoding="utf-8") == "payload-0"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restore_occupied_original_is_conflict_and_never_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, adapters, executor, source = await _runtime(tmp_path)
    try:
        intervention_id, _, resources, paths = await _completed_cleanup(
            store, adapters, executor, source, tmp_path
        )
        resource = await store.get_lifecycle_resource(resources[0]["id"])
        assert resource is not None
        quarantine = Path(resource["quarantine_path"])
        real_start = store.start_restore_operation

        async def occupy_after_grant(operation_id: str):
            started = await real_start(operation_id)
            paths[0].write_text("user replacement", encoding="utf-8")
            return started

        monkeypatch.setattr(store, "start_restore_operation", occupy_after_grant)
        result = await _restore(executor, intervention_id, key="restore-occupied-0001")
        assert result["code"] == "cleanup_restore_conflict:1"
        assert paths[0].read_text(encoding="utf-8") == "user replacement"
        assert quarantine.read_text(encoding="utf-8") == "payload-0"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restore_missing_parent_never_creates_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, adapters, executor, source = await _runtime(tmp_path)
    try:
        intervention_id, _, _, paths = await _completed_cleanup(
            store, adapters, executor, source, tmp_path
        )
        real_start = store.start_restore_operation

        async def remove_parent_after_grant(operation_id: str):
            started = await real_start(operation_id)
            paths[0].parent.rmdir()
            return started

        monkeypatch.setattr(store, "start_restore_operation", remove_parent_after_grant)
        result = await _restore(executor, intervention_id, key="restore-parent-0001")
        assert result["code"] == "cleanup_restore_not_restored:1"
        assert not paths[0].parent.exists()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restore_quarantine_replacement_after_grant_is_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, adapters, executor, source = await _runtime(tmp_path)
    try:
        intervention_id, _, resources, paths = await _completed_cleanup(
            store, adapters, executor, source, tmp_path
        )
        resource = await store.get_lifecycle_resource(resources[0]["id"])
        assert resource is not None
        quarantine = Path(resource["quarantine_path"])
        real_start = store.start_restore_operation

        async def replace_after_grant(operation_id: str):
            started = await real_start(operation_id)
            quarantine.unlink()
            quarantine.write_text("attacker replacement", encoding="utf-8")
            return started

        monkeypatch.setattr(store, "start_restore_operation", replace_after_grant)
        result = await _restore(executor, intervention_id, key="restore-tamper-0001")
        assert result["code"] == "cleanup_restore_conflict:1"
        assert not paths[0].exists()
        assert quarantine.read_text(encoding="utf-8") == "attacker replacement"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restore_partial_failure_never_rolls_back_and_finalizes_all_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, adapters, executor, source = await _runtime(tmp_path)
    try:
        intervention_id, _, resources, paths = await _completed_cleanup(
            store, adapters, executor, source, tmp_path, count=2
        )
        real_move = executor._move_restore_entry
        attempts = 0

        def fail_second(entry):
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                raise OSError("simulated second no-replace rename failure")
            real_move(entry)

        monkeypatch.setattr(executor, "_move_restore_entry", fail_second)
        result = await _restore(executor, intervention_id, key="restore-partial-0001")
        assert result["code"] == (
            "cleanup_restore_delivery_uncertain:"
            "restored=1,not_restored=1,conflict=0"
        )
        assert paths[0].read_text(encoding="utf-8") == "payload-0"
        assert not paths[1].exists()
        operation = await store.get_restore_operation(_receipt_operation_id(result))
        assert operation is not None
        assert [row["outcome"] for row in operation["outcomes"]] == [
            "restored",
            "not_restored",
        ]
        first = await store.get_lifecycle_resource(resources[0]["id"])
        second = await store.get_lifecycle_resource(resources[1]["id"])
        assert first is not None and first["state"] == "active"
        assert second is not None and second["state"] == "quarantined"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restore_cancellation_shields_finalization_then_reraises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, adapters, executor, source = await _runtime(tmp_path)
    try:
        intervention_id, _, resources, paths = await _completed_cleanup(
            store, adapters, executor, source, tmp_path
        )
        real_finalize = store.finalize_restore_operation
        entered = asyncio.Event()
        release = asyncio.Event()

        async def delayed_finalize(operation_id: str, *, outcomes, finished_at=None):
            entered.set()
            await release.wait()
            return await real_finalize(
                operation_id,
                outcomes=outcomes,
                finished_at=finished_at,
            )

        monkeypatch.setattr(store, "finalize_restore_operation", delayed_finalize)
        task = asyncio.create_task(
            executor.restore_cleanup(
                intervention_id,
                authorized_by=AUTHORIZER,
                idempotency_key="restore-cancel-0001",
            )
        )
        await entered.wait()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert paths[0].read_text(encoding="utf-8") == "payload-0"
        resource = await store.get_lifecycle_resource(resources[0]["id"])
        assert resource is not None and resource["state"] == "active"
        operations = await store.list_restore_operations(source.id)
        assert len(operations) == 1 and operations[0]["state"] == "completed"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restore_terminal_replay_performs_zero_new_filesystem_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, adapters, executor, source = await _runtime(tmp_path)
    try:
        intervention_id, _, _, _ = await _completed_cleanup(
            store, adapters, executor, source, tmp_path
        )
        first = await _restore(executor, intervention_id, key="restore-replay-0001")
        assert first["code"] == "cleanup_restored:1"

        def move_must_not_replay(_entry):
            raise AssertionError("terminal restore replay repeated filesystem I/O")

        monkeypatch.setattr(executor, "_move_restore_entry", move_must_not_replay)
        replay = await _restore(executor, intervention_id, key="restore-replay-0001")
        assert replay["code"] == "cleanup_restored:1"
        assert replay["replayed"] is True
        assert replay["receipt"] == first["receipt"]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restore_ambiguous_finalize_never_repeats_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, adapters, executor, source = await _runtime(tmp_path)
    try:
        intervention_id, _, _, paths = await _completed_cleanup(
            store, adapters, executor, source, tmp_path
        )

        async def ambiguous_finalize(*_args, **_kwargs):
            raise RuntimeError("simulated ambiguous restore finalization")

        monkeypatch.setattr(store, "finalize_restore_operation", ambiguous_finalize)
        first = await _restore(executor, intervention_id, key="restore-uncertain-0001")
        assert first["code"] == "cleanup_restore_finalization_uncertain"
        assert paths[0].read_text(encoding="utf-8") == "payload-0"

        def move_must_not_replay(_entry):
            raise AssertionError("ambiguous restore repeated filesystem I/O")

        monkeypatch.setattr(executor, "_move_restore_entry", move_must_not_replay)
        replay = await _restore(executor, intervention_id, key="restore-uncertain-0001")
        assert replay["code"] == "cleanup_restore_dispatch_in_progress"
        assert replay["replayed"] is True
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_restore_atomic_noreplace_loses_race_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, adapters, executor, source = await _runtime(tmp_path)
    try:
        intervention_id, _, resources, paths = await _completed_cleanup(
            store, adapters, executor, source, tmp_path
        )
        resource = await store.get_lifecycle_resource(resources[0]["id"])
        assert resource is not None
        quarantine = Path(resource["quarantine_path"])
        real_atomic = executor._atomic_rename_noreplace

        def racing_atomic(source_path: Path, destination_path: Path):
            destination_path.write_text("racing user file", encoding="utf-8")
            real_atomic(source_path, destination_path)

        monkeypatch.setattr(
            ActionExecutor,
            "_atomic_rename_noreplace",
            staticmethod(racing_atomic),
        )
        result = await _restore(executor, intervention_id, key="restore-race-0001")
        assert result["code"] == "cleanup_restore_conflict:1"
        assert paths[0].read_text(encoding="utf-8") == "racing user file"
        assert quarantine.read_text(encoding="utf-8") == "payload-0"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_legacy_raw_restore_manifest_remains_fail_closed(tmp_path: Path):
    store, _, executor, _ = await _runtime(tmp_path)
    try:
        assert await executor.restore_cleanup(
            "synthetic:source",
            [{"resource_id": "forged", "quarantine_path": str(tmp_path)}],
        ) == "cleanup_restore_reservation_required"
    finally:
        await store.close()
