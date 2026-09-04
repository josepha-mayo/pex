from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pex_bridge.executor as executor_module
import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.executor import ActionExecutor
from pex_bridge.store import Store, new_id, utcnow
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention


async def _runtime(tmp_path: Path) -> tuple[Store, ActionExecutor, object]:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    source = adapters.synthetic.seed_session(
        vendor_id="cleanup-source",
        project_id=str(tmp_path),
        cwd=str(tmp_path),
        goal_id="cleanup-goal",
    )
    source.capabilities = (await adapters.synthetic.probe()).model_dump(mode="json")
    now = utcnow()
    await store.upsert_goal(
        Goal(
            id="cleanup-goal",
            project_id=str(tmp_path),
            title="Exercise cleanup operation ledger",
            objective="Quarantine only an exact Store-frozen resource manifest.",
            created_at=now,
            updated_at=now,
        )
    )
    await store.upsert_session(source)
    return store, ActionExecutor(adapters, store), source


def _action(session_id: str, resource_ids: list[str]) -> ProposedAction:
    return ProposedAction(
        type=InterventionType.CLEANUP,
        session_id=session_id,
        goal_id="cleanup-goal",
        payload={"mode": "quarantine", "resource_ids": resource_ids},
        rationale="The stopped source left exact PEX-owned scratch.",
        evidence=["source_session_stopped", "producer_marked_cleanup_ready"],
        confidence=0.99,
        risk=RiskLevel.LOW,
        reversible=True,
        authority_required=Authority.LOCAL_POLICY,
    )


async def _ready_resources(
    store: Store,
    source: object,
    tmp_path: Path,
    *,
    count: int = 1,
) -> tuple[list[dict], list[Path]]:
    project = tmp_path / "project"
    scratch_root = project / "scratch"
    scratch_root.mkdir(parents=True)
    records: list[dict] = []
    paths: list[Path] = []
    for index in range(count):
        path = scratch_root / f"resource-{index}.txt"
        path.write_text(f"payload-{index}", encoding="utf-8")
        records.append(
            await store.register_lifecycle_resource(
                session_id=source.id,
                path=path,
                scope_root=project,
                kind="scratch",
                created_by="cleanup_executor_test_producer",
            )
        )
        paths.append(path)
    source.status = SessionStatus.STOPPED
    await store.upsert_session(source)
    for record in records:
        await store.mark_lifecycle_resource_cleanup_ready(
            resource_id=record["id"],
            session_id=source.id,
            evidence=["source session is stopped", "producer lease is closed"],
        )
    return records, paths


async def _dispatch_resolution(
    store: Store,
    action: ProposedAction,
) -> str:
    intervention = Intervention(
        id=new_id("int_cleanup_executor_"),
        session_id=action.session_id,
        goal_id=action.goal_id,
        trigger="status",
        evidence=action.evidence,
        diagnosis="bounded cleanup executor test",
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


async def _execute(
    executor: ActionExecutor,
    action: ProposedAction,
    resolution_id: str,
) -> str:
    return await executor.execute(
        action,
        PolicyVerdict.ALLOW,
        human_authorized=True,
        lifecycle_resolution_id=resolution_id,
    )


def _operation_id(resolution_id: str) -> str:
    digest = hashlib.sha256(resolution_id.encode("utf-8")).hexdigest()
    return f"cleanup_operation_{digest[:40]}"


@pytest.mark.asyncio
async def test_cleanup_success_uses_operation_ledger_without_mutating_action_or_legacy_updater(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, executor, source = await _runtime(tmp_path)
    try:
        resources, paths = await _ready_resources(store, source, tmp_path)
        action = _action(source.id, [resources[0]["id"]])
        resolution_id = await _dispatch_resolution(store, action)
        original = action.model_dump_json()

        async def legacy_updater_must_not_run(_records):
            raise AssertionError("legacy lifecycle updater was called")

        monkeypatch.setattr(
            store,
            "update_lifecycle_resources",
            legacy_updater_must_not_run,
        )
        assert await _execute(executor, action, resolution_id) == "cleanup_quarantined:1"
        assert action.model_dump_json() == original
        assert not paths[0].exists()

        operation = await store.get_cleanup_operation(_operation_id(resolution_id))
        assert operation is not None
        assert operation["state"] == "completed"
        assert operation["outcomes"][0]["outcome"] == "moved"
        resource = await store.get_lifecycle_resource(resources[0]["id"])
        assert resource is not None
        assert resource["state"] == "quarantined"
        assert Path(resource["quarantine_path"]).read_text(encoding="utf-8") == "payload-0"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_start_denied_performs_zero_filesystem_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, executor, source = await _runtime(tmp_path)
    try:
        resources, paths = await _ready_resources(store, source, tmp_path)
        action = _action(source.id, [resources[0]["id"]])
        resolution_id = await _dispatch_resolution(store, action)

        async def deny_start(operation_id: str):
            return {
                "granted": False,
                "operation": {"id": operation_id, "state": "dispatching"},
            }

        def move_must_not_run(_entry):
            raise AssertionError("filesystem move path ran without a Store start grant")

        monkeypatch.setattr(store, "start_cleanup_operation", deny_start)
        monkeypatch.setattr(executor, "_move_cleanup_entry", move_must_not_run)
        assert await _execute(executor, action, resolution_id) == (
            "cleanup_dispatch_in_progress"
        )
        assert paths[0].read_text(encoding="utf-8") == "payload-0"
        assert not (tmp_path / "quarantine").exists()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_resource_replacement_before_start_refuses_without_move(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, executor, source = await _runtime(tmp_path)
    try:
        resources, paths = await _ready_resources(store, source, tmp_path)
        action = _action(source.id, [resources[0]["id"]])
        resolution_id = await _dispatch_resolution(store, action)
        real_start = store.start_cleanup_operation

        async def replace_then_start(operation_id: str):
            paths[0].unlink()
            paths[0].write_text("replacement", encoding="utf-8")
            return await real_start(operation_id)

        def move_must_not_run(_entry):
            raise AssertionError("replaced resource reached the filesystem mover")

        monkeypatch.setattr(store, "start_cleanup_operation", replace_then_start)
        monkeypatch.setattr(executor, "_move_cleanup_entry", move_must_not_run)
        assert await _execute(executor, action, resolution_id) == "cleanup_start_refused"
        assert paths[0].read_text(encoding="utf-8") == "replacement"
        assert not (tmp_path / "quarantine").exists()
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_two_calls_grant_at_most_one_move_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, executor, source = await _runtime(tmp_path)
    try:
        resources, _ = await _ready_resources(store, source, tmp_path)
        action = _action(source.id, [resources[0]["id"]])
        resolution_id = await _dispatch_resolution(store, action)
        real_move = executor._move_cleanup_entry
        moves = 0

        def counted_move(entry):
            nonlocal moves
            moves += 1
            real_move(entry)

        monkeypatch.setattr(executor, "_move_cleanup_entry", counted_move)
        results = await asyncio.gather(
            _execute(executor, action, resolution_id),
            _execute(executor, action, resolution_id),
        )
        assert moves == 1
        assert sorted(results) == [
            "cleanup_dispatch_in_progress",
            "cleanup_quarantined:1",
        ]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_partial_move_failure_never_rolls_back_and_finalizes_all_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, executor, source = await _runtime(tmp_path)
    try:
        resources, paths = await _ready_resources(store, source, tmp_path, count=2)
        action = _action(source.id, [record["id"] for record in resources])
        resolution_id = await _dispatch_resolution(store, action)
        real_move = executor._move_cleanup_entry
        attempts = 0

        def fail_second(entry):
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                raise OSError("simulated second rename failure")
            real_move(entry)

        monkeypatch.setattr(executor, "_move_cleanup_entry", fail_second)
        assert await _execute(executor, action, resolution_id) == (
            "cleanup_delivery_uncertain:moved=1,not_moved=1,conflict=0"
        )
        assert not paths[0].exists()
        assert paths[1].read_text(encoding="utf-8") == "payload-1"

        operation = await store.get_cleanup_operation(_operation_id(resolution_id))
        assert operation is not None
        assert operation["state"] == "delivery_uncertain"
        assert [row["outcome"] for row in operation["outcomes"]] == [
            "moved",
            "not_moved",
        ]
        first = await store.get_lifecycle_resource(resources[0]["id"])
        second = await store.get_lifecycle_resource(resources[1]["id"])
        assert first is not None and first["state"] == "quarantined"
        assert second is not None and second["state"] == "cleanup_ready"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_cancellation_shields_finalization_then_reraises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, executor, source = await _runtime(tmp_path)
    try:
        resources, paths = await _ready_resources(store, source, tmp_path)
        action = _action(source.id, [resources[0]["id"]])
        resolution_id = await _dispatch_resolution(store, action)
        real_finalize = store.finalize_cleanup_operation
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

        monkeypatch.setattr(store, "finalize_cleanup_operation", delayed_finalize)
        task = asyncio.create_task(_execute(executor, action, resolution_id))
        await entered.wait()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert not paths[0].exists()
        operation = await store.get_cleanup_operation(_operation_id(resolution_id))
        assert operation is not None
        assert operation["state"] == "completed"
        resource = await store.get_lifecycle_resource(resources[0]["id"])
        assert resource is not None and resource["state"] == "quarantined"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_destination_tamper_is_conflict_and_never_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, executor, source = await _runtime(tmp_path)
    try:
        resources, paths = await _ready_resources(store, source, tmp_path)
        action = _action(source.id, [resources[0]["id"]])
        resolution_id = await _dispatch_resolution(store, action)
        real_start = store.start_cleanup_operation
        destination: Path | None = None

        async def tamper_after_grant(operation_id: str):
            nonlocal destination
            started = await real_start(operation_id)
            destination = Path(started["manifest"][0]["destination_path"])
            destination.parent.mkdir(parents=True)
            destination.write_text("tamper", encoding="utf-8")
            return started

        monkeypatch.setattr(store, "start_cleanup_operation", tamper_after_grant)
        assert await _execute(executor, action, resolution_id) == "cleanup_conflict:1"
        assert paths[0].read_text(encoding="utf-8") == "payload-0"
        assert destination is not None
        assert destination.read_text(encoding="utf-8") == "tamper"
        operation = await store.get_cleanup_operation(_operation_id(resolution_id))
        assert operation is not None and operation["state"] == "conflict"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_destination_symlink_contract_rejection_is_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, executor, source = await _runtime(tmp_path)
    try:
        resources, paths = await _ready_resources(store, source, tmp_path)
        action = _action(source.id, [resources[0]["id"]])
        resolution_id = await _dispatch_resolution(store, action)
        real_start = store.start_cleanup_operation
        real_canonical = executor_module._canonical_lifecycle_path
        destination: Path | None = None

        async def symlink_after_grant(operation_id: str):
            nonlocal destination
            started = await real_start(operation_id)
            destination = Path(started["manifest"][0]["destination_path"])
            return started

        def reject_reparse_destination(path: Path, *, must_exist: bool):
            if destination is not None and Path(path) == destination:
                raise ValueError(
                    "lifecycle resource cannot traverse a symlink or reparse point"
                )
            return real_canonical(path, must_exist=must_exist)

        monkeypatch.setattr(store, "start_cleanup_operation", symlink_after_grant)
        monkeypatch.setattr(
            executor_module,
            "_canonical_lifecycle_path",
            reject_reparse_destination,
        )
        assert await _execute(executor, action, resolution_id) == "cleanup_conflict:1"
        assert paths[0].read_text(encoding="utf-8") == "payload-0"
        operation = await store.get_cleanup_operation(_operation_id(resolution_id))
        assert operation is not None and operation["state"] == "conflict"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cleanup_terminal_replay_and_ambiguous_finalize_never_repeat_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store, executor, source = await _runtime(tmp_path)
    try:
        resources, _ = await _ready_resources(store, source, tmp_path)
        action = _action(source.id, [resources[0]["id"]])
        resolution_id = await _dispatch_resolution(store, action)
        assert await _execute(executor, action, resolution_id) == "cleanup_quarantined:1"

        def move_must_not_replay(_entry):
            raise AssertionError("terminal cleanup replay repeated filesystem I/O")

        monkeypatch.setattr(executor, "_move_cleanup_entry", move_must_not_replay)
        assert await _execute(executor, action, resolution_id) == "cleanup_quarantined:1"

        other_resources, _ = await _ready_resources(store, source, tmp_path / "other")
        other_action = _action(source.id, [other_resources[0]["id"]])
        other_resolution = await _dispatch_resolution(store, other_action)

        async def ambiguous_finalize(*_args, **_kwargs):
            raise RuntimeError("simulated ambiguous final persistence")

        monkeypatch.undo()
        monkeypatch.setattr(store, "finalize_cleanup_operation", ambiguous_finalize)
        assert await _execute(executor, other_action, other_resolution) == (
            "cleanup_finalization_uncertain"
        )
        monkeypatch.setattr(executor, "_move_cleanup_entry", move_must_not_replay)
        assert await _execute(executor, other_action, other_resolution) == (
            "cleanup_dispatch_in_progress"
        )
    finally:
        await store.close()
