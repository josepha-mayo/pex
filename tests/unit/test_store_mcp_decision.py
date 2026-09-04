from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import timedelta

import aiosqlite
import pex_bridge.store as store_module
import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.base import AdapterMessageResult, HarnessAdapter
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.decision_delivery import probe_human_decision_delivery
from pex_bridge.decisions import (
    DecisionResolutionError,
    resolve_permission_decision,
    resolve_requested_human_decision,
)
from pex_bridge.mcp_auth import MCPPrincipal
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import (
    MCP_REQUEST_DECISION_TOOL,
    ProjectIdentityBlockedError,
    Store,
    human_decision_logical_key,
    utcnow,
)
from pex_protocol import HumanDecisionRequest
from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessSession


class _DecisionDeliveryAdapter(HarnessAdapter):
    name = "codex"

    def __init__(
        self,
        *,
        capabilities: AdapterCapabilities | None = None,
        send_result: object = True,
        send_error: Exception | None = None,
        block_send: asyncio.Event | None = None,
    ) -> None:
        self.messages: list[tuple[str, str]] = []
        self.capabilities = capabilities or AdapterCapabilities(send_message=True)
        self.send_result = send_result
        self.send_error = send_error
        self.block_send = block_send
        self.send_started = asyncio.Event()

    async def probe(self) -> AdapterCapabilities:
        return self.capabilities

    async def discover_sessions(self) -> list[HarnessSession]:
        return []

    async def send_message(
        self,
        session: HarnessSession,
        text: str,
        attachments=None,
    ) -> bool:
        self.messages.append((session.id, text))
        self.send_started.set()
        if self.block_send is not None:
            await self.block_send.wait()
        if self.send_error is not None:
            raise self.send_error
        if self.send_result is True:
            return AdapterMessageResult(
                accepted=True,
                vendor_session_id=session.vendor_session_id,
                vendor_turn_id="turn-human-decision",
            )
        return self.send_result  # type: ignore[return-value]


def _delivery_registry(adapter: HarnessAdapter) -> AdapterRegistry:
    adapters = AdapterRegistry()
    adapters.bind("codex", adapter)
    return adapters


async def _bound_pipeline(tmp_path, *, suffix: str = ""):
    store = Store(tmp_path / f"pex{suffix}.sqlite")
    await store.connect()
    now = utcnow()
    goal = Goal(
        id=f"goal-decision{suffix}",
        project_id="C:/repo",
        title="Decision integrity",
        objective="Route consequential choices to the human",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id=f"codex:decision{suffix}",
        harness_type=HarnessType.CODEX,
        vendor_session_id=f"thread-decision{suffix}",
        project_id="C:/repo",
        goal_id=goal.id,
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    issued_at = utcnow() - timedelta(seconds=1)
    token = f"decision-token{suffix}"
    record = await store.issue_mcp_principal(
        principal_id=f"principal-decision{suffix}",
        session_id=session.id,
        goal_id=goal.id,
        project_id="C:/repo",
        vendor_session_id=session.vendor_session_id,
        harness_type=session.harness_type.value,
        scopes=["mcp:read", MCP_REQUEST_DECISION_TOOL],
        token_digest=hashlib.sha256(token.encode()).hexdigest(),
        issued_at=issued_at,
        expires_at=issued_at + timedelta(hours=1),
    )
    principal = MCPPrincipal.from_store_record(record)
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(home=tmp_path, require_auth=False, autonomy="manage"),
        model=None,
    )
    return store, pipeline, session, goal, principal


def _request(**changes) -> HumanDecisionRequest:
    values = {
        "idempotency_key": "decision-atomic-0001",
        "question": "Ship the candidate or keep iterating?",
        "options": ["ship", "iterate"],
        "urgency": "blocking",
        "context": "The candidate passed local structural validation.",
    }
    values.update(changes)
    return HumanDecisionRequest.model_validate(values)


def test_legacy_raw_choice_store_resolver_is_not_callable() -> None:
    assert not hasattr(Store, "resolve_requested_human_decision")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [SessionStatus.STOPPED, SessionStatus.ERROR, SessionStatus.DETACHED],
)
async def test_request_decision_rejects_terminal_session_states(tmp_path, status) -> None:
    store, pipeline, session, _goal, principal = await _bound_pipeline(
        tmp_path,
        suffix=f"-{status.value}",
    )
    try:
        session.status = status
        session.last_activity = utcnow()
        await store.upsert_session(session)

        with pytest.raises(PermissionError, match="terminal sessions"):
            await pipeline.request_human_decision(
                session,
                principal=principal,
                request=_request(idempotency_key=f"terminal-{status.value}-0001"),
            )

        cursor = await store.db.execute("SELECT COUNT(*) AS count FROM interventions")
        assert int((await cursor.fetchone())["count"]) == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_request_decision_is_atomic_concurrent_and_content_idempotent(tmp_path):
    store, pipeline, session, _goal, principal = await _bound_pipeline(tmp_path)
    try:
        request = _request()
        first, second = await asyncio.gather(
            pipeline.request_human_decision(
                session,
                principal=principal,
                request=request,
            ),
            pipeline.request_human_decision(
                session,
                principal=principal,
                request=request,
            ),
        )

        assert sorted([first["replayed"], second["replayed"]]) == [False, True]
        assert first["mutation_id"] == second["mutation_id"]
        assert first["intervention"] == second["intervention"]
        assert first["pending_context"] == second["pending_context"]
        assert first["session_status"] == second["session_status"] == "needs_decision"

        for table, expected in (
            ("mcp_mutations", 1),
            ("events", 1),
            ("context_items", 1),
            ("interventions", 1),
            ("intervention_audit", 1),
        ):
            cursor = await store.db.execute(f"SELECT COUNT(*) AS count FROM {table}")
            assert int((await cursor.fetchone())["count"]) == expected

        replay = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=request,
        )
        assert replay["replayed"] is True
        assert replay["intervention"] == first["intervention"]

        with pytest.raises(ValueError, match="reused with new content"):
            await pipeline.request_human_decision(
                session,
                principal=principal,
                request=_request(question="Deploy the candidate to production?"),
            )
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql_prefix",
    [
        "INSERT INTO events",
        "INSERT INTO context_items",
        "INSERT INTO interventions",
        "INSERT INTO intervention_audit",
        "UPDATE sessions SET json",
        "INSERT INTO mcp_mutations",
    ],
)
async def test_request_decision_rolls_back_on_every_write_stage(
    tmp_path,
    monkeypatch,
    sql_prefix,
):
    store, pipeline, session, _goal, principal = await _bound_pipeline(tmp_path)
    original_execute = aiosqlite.Connection.execute

    async def fail_selected(connection, sql, parameters=None):
        if " ".join(str(sql).split()).startswith(sql_prefix):
            raise RuntimeError(f"injected failure at {sql_prefix}")
        if parameters is None:
            return await original_execute(connection, sql)
        return await original_execute(connection, sql, parameters)

    try:
        with monkeypatch.context() as patcher:
            patcher.setattr(aiosqlite.Connection, "execute", fail_selected)
            with pytest.raises(RuntimeError, match="injected failure"):
                await pipeline.request_human_decision(
                    session,
                    principal=principal,
                    request=_request(
                        idempotency_key=(
                            "rollback-"
                            + hashlib.sha256(sql_prefix.encode()).hexdigest()[:16]
                        )
                    ),
                )

        for table in (
            "mcp_mutations",
            "events",
            "context_items",
            "interventions",
            "intervention_audit",
        ):
            cursor = await store.db.execute(f"SELECT COUNT(*) AS count FROM {table}")
            assert int((await cursor.fetchone())["count"]) == 0
        live = await store.get_session(session.id)
        assert live is not None
        assert live.status == SessionStatus.WORKING
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_request_decision_rejects_principal_and_live_binding_changes(tmp_path):
    cases = ("session", "goal", "project", "vendor", "harness")
    for index, case in enumerate(cases):
        case_root = tmp_path / str(index)
        case_root.mkdir()
        store, pipeline, session, goal, principal = await _bound_pipeline(
            case_root,
            suffix=f"-{case}",
        )
        try:
            if case == "session":
                other = session.model_copy(
                    update={
                        "id": f"codex:other-{case}",
                        "vendor_session_id": f"other-{case}",
                    }
                )
                await store.upsert_session(other)
                target = other
            elif case == "goal":
                replacement = goal.model_copy(
                    update={
                        "id": f"goal-other-{case}",
                        "created_at": utcnow(),
                        "updated_at": utcnow(),
                    }
                )
                await store.upsert_goal(replacement)
                session.goal_id = replacement.id
                await store.upsert_session(session, allow_goal_change=True)
                target = session
            else:
                target = session
                stored = session.model_copy(deep=True)
                if case == "project":
                    stored.project_id = "C:/foreign"
                elif case == "vendor":
                    stored.vendor_session_id = "thread-foreign"
                else:
                    stored.harness_type = HarnessType.CURSOR
                await store.db.execute(
                    "UPDATE sessions SET vendor_session_id = ?, harness_type = ?, json = ? "
                    "WHERE id = ?",
                    (
                        stored.vendor_session_id,
                        stored.harness_type.value,
                        stored.model_dump_json(),
                        stored.id,
                    ),
                )
                await store.db.commit()

            with pytest.raises(
                (PermissionError, ProjectIdentityBlockedError),
                match="binding|match|identity changed",
            ):
                await pipeline.request_human_decision(
                    target,
                    principal=principal,
                    request=_request(idempotency_key=f"rebind-{case}-0001"),
                )
            cursor = await store.db.execute("SELECT COUNT(*) AS count FROM mcp_mutations")
            assert int((await cursor.fetchone())["count"]) == 0
        finally:
            await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    ["principal", "session", "goal", "project", "vendor", "harness"],
)
async def test_request_decision_store_rechecks_binding_after_pipeline_precheck(
    tmp_path,
    monkeypatch,
    case,
):
    store, pipeline, session, goal, principal = await _bound_pipeline(tmp_path)
    original_commit = store.commit_human_decision_request
    replacement = goal.model_copy(
        update={
            "id": "goal-toctou-replacement",
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
    )
    if case == "goal":
        await store.upsert_goal(replacement)

    async def rebind_then_commit(**kwargs):
        if case == "principal":
            await store.revoke_mcp_principals_for_session(
                session.id,
                revoked_at=utcnow(),
            )
        elif case == "session":
            await store.db.execute("DELETE FROM sessions WHERE id = ?", (session.id,))
            await store.db.commit()
        else:
            changed = session.model_copy(deep=True)
            if case == "goal":
                changed.goal_id = replacement.id
            elif case == "project":
                changed.project_id = "C:/foreign"
            elif case == "vendor":
                changed.vendor_session_id = "thread-foreign"
            else:
                changed.harness_type = HarnessType.CURSOR
            await store.db.execute(
                "UPDATE sessions SET vendor_session_id = ?, harness_type = ?, json = ? "
                "WHERE id = ?",
                (
                    changed.vendor_session_id,
                    changed.harness_type.value,
                    changed.model_dump_json(),
                    changed.id,
                ),
            )
            await store.db.commit()
        return await original_commit(**kwargs)

    try:
        monkeypatch.setattr(
            store,
            "commit_human_decision_request",
            rebind_then_commit,
        )
        with pytest.raises(PermissionError, match="principal|session|binding"):
            await pipeline.request_human_decision(
                session,
                principal=principal,
                request=_request(idempotency_key=f"toctou-{case}-0001"),
            )
        cursor = await store.db.execute("SELECT COUNT(*) AS count FROM mcp_mutations")
        assert int((await cursor.fetchone())["count"]) == 0
        cursor = await store.db.execute("SELECT COUNT(*) AS count FROM interventions")
        assert int((await cursor.fetchone())["count"]) == 0
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_request_decision_collision_rolls_back_all_new_artifacts(tmp_path):
    store, pipeline, session, goal, principal = await _bound_pipeline(tmp_path)
    request = _request(idempotency_key="decision-collision-0001")
    artifact_key = human_decision_logical_key(
        tool=MCP_REQUEST_DECISION_TOOL,
        request_id=request.idempotency_key,
        session_id=session.id,
        goal_id=goal.id,
        project_id=session.project_id or "",
        vendor_session_id=session.vendor_session_id,
        harness_type=session.harness_type.value,
    )
    now = utcnow()
    collision = HarnessSession(
        id=f"collision-holder-{artifact_key}",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="collision-holder",
        project_id=goal.project_id,
        last_activity=now,
    )
    try:
        await store.upsert_session(collision)
        await store.db.execute(
            "INSERT INTO events(event_id, session_id, ts, json) VALUES (?, ?, ?, ?)",
            (
                f"mcp_decision_event_{artifact_key}",
                collision.id,
                now.isoformat(),
                "{}",
            ),
        )
        await store.db.commit()

        with pytest.raises(ValueError, match="artifact id collision"):
            await pipeline.request_human_decision(
                session,
                principal=principal,
                request=request,
            )
        cursor = await store.db.execute("SELECT COUNT(*) AS count FROM mcp_mutations")
        assert int((await cursor.fetchone())["count"]) == 0
        assert await store.get_context(f"decision_pending_{artifact_key}") is None
        assert await store.get_intervention(f"int_decision_{artifact_key}") is None
        live = await store.get_session(session.id)
        assert live is not None and live.status == SessionStatus.WORKING
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_human_decision_resolution_is_atomic_replay_safe_and_supersedes_pending(
    tmp_path,
):
    store, pipeline, session, goal, principal = await _bound_pipeline(tmp_path)
    adapters = AdapterRegistry()
    delivery_adapter = _DecisionDeliveryAdapter()
    adapters.bind("codex", delivery_adapter)
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(),
        )
        intervention_id = opened["intervention"]["id"]

        with pytest.raises(DecisionResolutionError) as wrong_path:
            await resolve_permission_decision(
                store,
                AdapterRegistry(),
                intervention_id=intervention_id,
                decision="allow",
            )
        assert wrong_path.value.code == "decision_not_pending_permission"
        with pytest.raises(DecisionResolutionError) as unoffered:
            await resolve_requested_human_decision(
                store,
                adapters,
                intervention_id=intervention_id,
                choice="Iterate",
            )
        assert unoffered.value.code == "human_decision_choice_not_offered"

        first, second = await asyncio.gather(
            resolve_requested_human_decision(
                store,
                adapters,
                intervention_id=intervention_id,
                choice="iterate",
            ),
            resolve_requested_human_decision(
                store,
                adapters,
                intervention_id=intervention_id,
                choice="iterate",
            ),
        )
        assert sorted([first.replayed, second.replayed]) == [False, True]
        delivered = [
            result
            for result in (first, second)
            if result.response()["delivery_status"] == "delivered"
        ]
        assert len(delivered) == 1
        replay = await resolve_requested_human_decision(
            store,
            adapters,
            intervention_id=intervention_id,
            choice="iterate",
        )
        assert replay.replayed is True
        assert replay.response()["delivery_status"] == "delivered"
        assert replay.response()["resolution"]["choice"] == "iterate"
        receipt = {
            "schema": "pex.worker-delivery.codex-turn.v1",
            "target_session_id": session.id,
            "vendor_session_id": session.vendor_session_id,
            "vendor_turn_id": "turn-human-decision",
        }
        assert replay.response()["resolution"]["worker_delivery_receipt"] == receipt
        assert len(delivery_adapter.messages) == 1

        with pytest.raises(DecisionResolutionError) as conflict:
            await resolve_requested_human_decision(
                store,
                adapters,
                intervention_id=intervention_id,
                choice="ship",
            )
        assert conflict.value.code == "human_decision_conflict"

        decisions = await store.list_decisions(goal.id)
        assert len(decisions) == 1
        assert decisions[0].statement == "iterate"
        resolved_context = await store.get_context(
            first.response()["resolution"]["context_id"]
        )
        pending_context = await store.get_context(
            first.response()["resolution"]["pending_context_id"]
        )
        assert resolved_context is not None
        assert pending_context is not None
        assert resolved_context.supersedes == pending_context.id
        assert pending_context.metadata["status"] == "resolved"
        assert pending_context.stale_after is not None
        live = await store.get_session(session.id)
        assert live is not None and live.status == SessionStatus.WORKING
        stored = await store.get_intervention(intervention_id)
        assert stored is not None and stored.result == "human_decision_delivered"
        assert stored.metadata["worker_delivery_receipt"] == receipt
        audit_cursor = await store.db.execute(
            "SELECT json FROM intervention_audit "
            "WHERE intervention_id = ? AND record_type = ?",
            (intervention_id, "human_decision_delivered"),
        )
        audit_row = await audit_cursor.fetchone()
        assert audit_row is not None
        assert '"choice":"iterate"' in str(audit_row["json"])
        assert json.loads(audit_row["json"])["worker_delivery_receipt"] == receipt
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql_prefix",
    [
        "INSERT INTO human_decision_resolutions",
        "INSERT INTO decisions",
        "INSERT INTO context_items",
        "UPDATE context_items SET json",
        "UPDATE interventions SET version",
        "INSERT INTO intervention_audit",
        "UPDATE mcp_mutations SET response_json",
    ],
)
async def test_human_decision_resolution_rolls_back_on_every_write_stage(
    tmp_path,
    monkeypatch,
    sql_prefix,
):
    store, pipeline, session, goal, principal = await _bound_pipeline(tmp_path)
    original_execute = aiosqlite.Connection.execute
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(),
        )
        intervention_id = opened["intervention"]["id"]
        pending_id = opened["pending_context"]["id"]
        audit_cursor = await store.db.execute(
            "SELECT COUNT(*) AS count FROM intervention_audit"
        )
        audit_before = int((await audit_cursor.fetchone())["count"])

        async def fail_selected(connection, sql, parameters=None):
            if " ".join(str(sql).split()).startswith(sql_prefix):
                raise RuntimeError(f"injected failure at {sql_prefix}")
            if parameters is None:
                return await original_execute(connection, sql)
            return await original_execute(connection, sql, parameters)

        with monkeypatch.context() as patcher:
            patcher.setattr(aiosqlite.Connection, "execute", fail_selected)
            with pytest.raises(RuntimeError, match="injected failure"):
                await store.reserve_human_decision_delivery(
                    intervention_id=intervention_id,
                    choice="iterate",
                    resolved_at=utcnow(),
                )

        assert await store.get_human_decision_resolution(intervention_id) is None
        assert await store.list_decisions(goal.id) == []
        pending = await store.get_context(pending_id)
        assert pending is not None
        assert pending.metadata["status"] == "pending"
        assert pending.stale_after is None
        intervention = await store.get_intervention(intervention_id)
        assert intervention is not None and intervention.result == "awaiting_human"
        live = await store.get_session(session.id)
        assert live is not None and live.status == SessionStatus.NEEDS_DECISION
        audit_cursor = await store.db.execute(
            "SELECT COUNT(*) AS count FROM intervention_audit"
        )
        assert int((await audit_cursor.fetchone())["count"]) == audit_before
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_human_decision_delivered_status_requires_consistent_code_and_exception(
    tmp_path,
):
    store, pipeline, session, _goal, principal = await _bound_pipeline(tmp_path)
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(idempotency_key="decision-code-invariant-0001"),
        )
        intervention_id = opened["intervention"]["id"]
        reserved = await store.reserve_human_decision_delivery(
            intervention_id=intervention_id,
            choice="iterate",
            resolved_at=utcnow(),
        )
        effect_id = reserved["record"]["effect_id"]
        started = await store.start_human_decision_delivery(
            intervention_id=intervention_id,
            effect_id=effect_id,
            started_at=utcnow(),
        )
        assert started["started"] is True

        with pytest.raises(ValueError, match="requires send_confirmed"):
            await store.finalize_human_decision_delivery(
                intervention_id=intervention_id,
                effect_id=effect_id,
                status="delivered",
                delivery_code="adapter_unavailable",
                finished_at=utcnow(),
            )
        with pytest.raises(ValueError, match="requires send_confirmed"):
            await store.finalize_human_decision_delivery(
                intervention_id=intervention_id,
                effect_id=effect_id,
                status="delivered",
                delivery_code="send_confirmed",
                exception_type="RuntimeError",
                finished_at=utcnow(),
            )
        current = await store.get_human_decision_resolution(intervention_id)
        assert current is not None and current["status"] == "dispatching"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_exact_turn_human_decision_contract_is_immutable_and_read_validated(tmp_path):
    store, pipeline, session, _goal, principal = await _bound_pipeline(
        tmp_path, suffix="-contract-read"
    )
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(idempotency_key="decision-contract-read-0001"),
        )
        resolved = await resolve_requested_human_decision(
            store,
            _delivery_registry(_DecisionDeliveryAdapter()),
            intervention_id=opened["intervention"]["id"],
            choice="iterate",
        )
        intervention_id = opened["intervention"]["id"]
        cursor = await store.db.execute(
            "SELECT delivery_contract_version, json FROM human_decision_resolutions "
            "WHERE intervention_id = ?",
            (intervention_id,),
        )
        row = await cursor.fetchone()
        assert row is not None and int(row["delivery_contract_version"]) == 3
        with pytest.raises(aiosqlite.IntegrityError, match="contract is immutable"):
            await store.db.execute(
                "UPDATE human_decision_resolutions SET delivery_contract_version = 1 "
                "WHERE intervention_id = ?",
                (intervention_id,),
            )
        await store.db.rollback()
        with pytest.raises(aiosqlite.IntegrityError, match="must be exact-turn"):
            await store.db.execute(
                "INSERT INTO human_decision_resolutions("
                "intervention_id, session_id, goal_id, choice, decision_id, context_id, "
                "resolved_at, delivery_contract_version, json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
                (
                    "int_new_legacy_forbidden",
                    session.id,
                    session.goal_id,
                    "iterate",
                    "dec_new_legacy_forbidden",
                    "ctx_new_legacy_forbidden",
                    utcnow().isoformat(),
                    "{}",
                ),
            )
        await store.db.rollback()
        with pytest.raises(aiosqlite.IntegrityError, match="must be exact-turn"):
            await store.db.execute(
                "INSERT OR REPLACE INTO human_decision_resolutions("
                "intervention_id, session_id, goal_id, choice, decision_id, context_id, "
                "resolved_at, delivery_contract_version, json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
                (
                    intervention_id,
                    session.id,
                    session.goal_id,
                    "iterate",
                    "dec_replacement_downgrade",
                    "ctx_replacement_downgrade",
                    utcnow().isoformat(),
                    "{}",
                ),
            )
        await store.db.rollback()

        record = json.loads(row["json"])
        record.pop("worker_delivery_receipt")
        await store.db.execute(
            "UPDATE human_decision_resolutions SET json = ? WHERE intervention_id = ?",
            (json.dumps(record, sort_keys=True, separators=(",", ":")), intervention_id),
        )
        await store.db.commit()
        with pytest.raises(RuntimeError, match="human decision delivery receipt is invalid"):
            await store.get_current_human_decision_resolution(intervention_id)
        with pytest.raises(RuntimeError, match="human decision delivery receipt is invalid"):
            await store.attention_metrics()
        assert resolved.response()["delivery_status"] == "delivered"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_terminal_human_decision_json_cannot_reactivate_delivery(tmp_path):
    store, pipeline, session, _goal, principal = await _bound_pipeline(
        tmp_path, suffix="-terminal-reactivation"
    )
    adapter = _DecisionDeliveryAdapter()
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(idempotency_key="decision-terminal-reactivation-0001"),
        )
        intervention_id = opened["intervention"]["id"]
        await resolve_requested_human_decision(
            store,
            _delivery_registry(adapter),
            intervention_id=intervention_id,
            choice="iterate",
        )
        cursor = await store.db.execute(
            "SELECT json FROM human_decision_resolutions WHERE intervention_id = ?",
            (intervention_id,),
        )
        row = await cursor.fetchone()
        assert row is not None
        corrupted = json.loads(row["json"])
        corrupted.update(status="delivery_reserved", delivery_code="effect_reserved")
        for key in (
            "finished_at",
            "started_at",
            "dispatcher_boot_id",
            "worker_delivery_receipt",
            "exception_type",
        ):
            corrupted.pop(key, None)
        await store.db.execute(
            "UPDATE human_decision_resolutions SET json = ? WHERE intervention_id = ?",
            (json.dumps(corrupted, sort_keys=True, separators=(",", ":")), intervention_id),
        )
        await store.db.commit()

        with pytest.raises((RuntimeError, DecisionResolutionError), match="projection"):
            await resolve_requested_human_decision(
                store,
                _delivery_registry(adapter),
                intervention_id=intervention_id,
                choice="iterate",
            )
        assert len(adapter.messages) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_first_human_decision_finalize_uses_frozen_vendor_binding(tmp_path):
    store, pipeline, session, _goal, principal = await _bound_pipeline(
        tmp_path, suffix="-first-frozen-finalize"
    )
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(idempotency_key="decision-first-frozen-finalize-0001"),
        )
        intervention_id = opened["intervention"]["id"]
        reserved = await store.reserve_human_decision_delivery(
            intervention_id=intervention_id,
            choice="iterate",
            resolved_at=utcnow(),
        )
        started = await store.start_human_decision_delivery(
            intervention_id=intervention_id,
            effect_id=reserved["record"]["effect_id"],
            started_at=utcnow(),
        )
        frozen = started["session"]
        rebound = session.model_copy(update={"vendor_session_id": "thread-rebound-before-final"})
        await store.db.execute(
            "UPDATE sessions SET vendor_session_id = ?, json = ? WHERE id = ?",
            (rebound.vendor_session_id, rebound.model_dump_json(), rebound.id),
        )
        await store.db.commit()
        receipt = {
            "schema": "pex.worker-delivery.codex-turn.v1",
            "target_session_id": frozen["id"],
            "vendor_session_id": frozen["vendor_session_id"],
            "vendor_turn_id": "turn-frozen-first-finalize",
        }

        finalized = await store.finalize_human_decision_delivery(
            intervention_id=intervention_id,
            effect_id=reserved["record"]["effect_id"],
            status="delivered",
            delivery_code="send_confirmed",
            worker_delivery_receipt=receipt,
            finished_at=utcnow(),
        )

        assert finalized["created"] is True
        assert finalized["record"]["worker_delivery_receipt"] == receipt
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_terminal_human_decision_replay_uses_frozen_vendor_binding(tmp_path):
    store, pipeline, session, _goal, principal = await _bound_pipeline(
        tmp_path, suffix="-frozen-replay"
    )
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(idempotency_key="decision-frozen-replay-0001"),
        )
        resolved = await resolve_requested_human_decision(
            store,
            _delivery_registry(_DecisionDeliveryAdapter()),
            intervention_id=opened["intervention"]["id"],
            choice="iterate",
        )
        resolution = resolved.response()["resolution"]
        receipt = resolution["worker_delivery_receipt"]
        # Simulate persisted session drift without weakening the public identity guard.
        # Terminal replay must remain bound to the resolution's frozen session snapshot.
        rebound = session.model_copy(update={"vendor_session_id": "thread-rebound"})
        await store.db.execute(
            "UPDATE sessions SET vendor_session_id = ?, json = ? WHERE id = ?",
            (rebound.vendor_session_id, rebound.model_dump_json(), rebound.id),
        )
        await store.db.commit()

        replay = await store.finalize_human_decision_delivery(
            intervention_id=opened["intervention"]["id"],
            effect_id=resolution["effect_id"],
            status="delivered",
            delivery_code="send_confirmed",
            worker_delivery_receipt=receipt,
            finished_at=utcnow(),
        )

        assert replay["created"] is False
        assert replay["record"]["worker_delivery_receipt"] == receipt
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_legacy_human_decision_rows_stay_legacy_without_receipt_backfill(tmp_path):
    path = tmp_path / "legacy-human-decision.sqlite"
    resolved_at = utcnow().isoformat()
    record = {
        "intervention_id": "int_legacy_human_decision",
        "session_id": "codex:legacy-human-decision",
        "goal_id": "goal_legacy_human_decision",
        "choice": "iterate",
        "decision_id": "decision_legacy_human_decision",
        "context_id": "context_legacy_human_decision",
        "resolved_at": resolved_at,
        "status": "delivered",
        "delivery_code": "send_confirmed",
    }
    connection = await aiosqlite.connect(path)
    try:
        await connection.execute(
            "CREATE TABLE human_decision_resolutions ("
            "intervention_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
            "goal_id TEXT NOT NULL, choice TEXT NOT NULL, decision_id TEXT NOT NULL UNIQUE, "
            "context_id TEXT NOT NULL UNIQUE, resolved_at TEXT NOT NULL, json TEXT NOT NULL)"
        )
        await connection.execute(
            "INSERT INTO human_decision_resolutions(intervention_id, session_id, goal_id, "
            "choice, decision_id, context_id, resolved_at, json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record["intervention_id"],
                record["session_id"],
                record["goal_id"],
                record["choice"],
                record["decision_id"],
                record["context_id"],
                resolved_at,
                json.dumps(record, sort_keys=True, separators=(",", ":")),
            ),
        )
        await connection.commit()
    finally:
        await connection.close()

    store = Store(path)
    await store.connect()
    try:
        cursor = await store.db.execute(
            "SELECT delivery_contract_version FROM human_decision_resolutions "
            "WHERE intervention_id = ?",
            (record["intervention_id"],),
        )
        row = await cursor.fetchone()
        assert row is not None and int(row["delivery_contract_version"]) == 1
        assert await store.get_human_decision_resolution(record["intervention_id"]) == record
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_request_decision_replays_across_exact_binding_credential_rotation(tmp_path):
    store, pipeline, session, goal, principal = await _bound_pipeline(tmp_path)
    request = _request(idempotency_key="credential-rotation-0001")
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=request,
        )
        issued_at = utcnow()
        rotated_record = await store.issue_mcp_principal(
            principal_id="principal-decision-rotated",
            session_id=session.id,
            goal_id=goal.id,
            project_id="C:/repo",
            vendor_session_id=session.vendor_session_id,
            harness_type=session.harness_type.value,
            scopes=["mcp:read", MCP_REQUEST_DECISION_TOOL],
            token_digest=hashlib.sha256(b"decision-token-rotated").hexdigest(),
            issued_at=issued_at,
            expires_at=issued_at + timedelta(hours=1),
        )
        rotated = MCPPrincipal.from_store_record(rotated_record)

        replay = await pipeline.request_human_decision(
            session,
            principal=rotated,
            request=request,
        )
        assert replay["replayed"] is True
        assert replay["mutation_id"] == opened["mutation_id"]
        assert replay["intervention"]["id"] == opened["intervention"]["id"]
        cursor = await store.db.execute(
            "SELECT principal_id, COUNT(*) AS count FROM mcp_mutations"
        )
        row = await cursor.fetchone()
        assert row["principal_id"] == principal.principal_id
        assert int(row["count"]) == 1

        adapter = _DecisionDeliveryAdapter()
        resolved = await resolve_requested_human_decision(
            store,
            _delivery_registry(adapter),
            intervention_id=opened["intervention"]["id"],
            choice="iterate",
        )
        assert resolved.response()["delivery_status"] == "delivered"
        current_replay = await pipeline.request_human_decision(
            session,
            principal=rotated,
            request=request,
        )
        assert current_replay["replayed"] is True
        assert current_replay["delivery_status"] == "delivered"
        assert current_replay["delivered"] is True
        assert current_replay["resolution"]["choice"] == "iterate"
        assert current_replay["intervention"]["result"] == "human_decision_delivered"
        assert len(adapter.messages) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_request_decision_enforces_atomic_pending_and_lifetime_quotas(
    tmp_path,
    monkeypatch,
):
    store, pipeline, session, _goal, principal = await _bound_pipeline(tmp_path)
    monkeypatch.setattr(store_module, "MAX_PENDING_HUMAN_DECISIONS_PER_SESSION", 2)
    monkeypatch.setattr(store_module, "MAX_CREATED_HUMAN_DECISIONS_PER_SESSION", 4)
    try:
        opened = []
        for index in range(2):
            opened.append(
                await pipeline.request_human_decision(
                    session,
                    principal=principal,
                    request=_request(
                        idempotency_key=f"quota-decision-{index:04d}",
                        question=f"Choose outcome {index}?",
                    ),
                )
            )
        with pytest.raises(PermissionError, match="pending human decision quota"):
            await pipeline.request_human_decision(
                session,
                principal=principal,
                request=_request(
                    idempotency_key="quota-decision-0002",
                    question="Choose outcome 2?",
                ),
            )
        cursor = await store.db.execute(
            "SELECT COUNT(*) AS count FROM interventions "
            "WHERE json_extract(json, '$.payload.metadata.decision_kind') = "
            "'mcp_human_request'"
        )
        assert int((await cursor.fetchone())["count"]) == 2

        adapter = _DecisionDeliveryAdapter()
        await resolve_requested_human_decision(
            store,
            _delivery_registry(adapter),
            intervention_id=opened[0]["intervention"]["id"],
            choice="iterate",
        )
        monkeypatch.setattr(store_module, "MAX_CREATED_HUMAN_DECISIONS_PER_SESSION", 2)
        with pytest.raises(PermissionError, match="creation quota"):
            await pipeline.request_human_decision(
                session,
                principal=principal,
                request=_request(
                    idempotency_key="quota-decision-0003",
                    question="Choose outcome 3?",
                ),
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_freeform_answer_is_opaque_in_every_durable_record_and_replay(tmp_path):
    store, pipeline, session, _goal, principal = await _bound_pipeline(tmp_path)
    raw_answer = "swordfish-proprietary-codename"
    request = _request(
        idempotency_key="freeform-opaque-0001",
        question="What internal codename should the worker use?",
        options=[],
    )
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=request,
        )
        adapter = _DecisionDeliveryAdapter()
        adapters = _delivery_registry(adapter)
        resolved = await resolve_requested_human_decision(
            store,
            adapters,
            intervention_id=opened["intervention"]["id"],
            choice=raw_answer,
        )
        payload = resolved.response()
        opaque_choice = payload["resolution"]["choice"]
        assert opaque_choice == (
            "[freeform answer sha256:"
            + hashlib.sha256(raw_answer.encode()).hexdigest()
            + "]"
        )
        assert raw_answer not in json.dumps(payload, ensure_ascii=False)
        assert len(adapter.messages) == 1
        assert raw_answer in adapter.messages[0][1]

        replay = await resolve_requested_human_decision(
            store,
            adapters,
            intervention_id=opened["intervention"]["id"],
            choice=raw_answer,
        )
        assert replay.replayed is True
        assert replay.response()["delivery_status"] == "delivered"
        assert len(adapter.messages) == 1
        with pytest.raises(DecisionResolutionError) as conflict:
            await resolve_requested_human_decision(
                store,
                adapters,
                intervention_id=opened["intervention"]["id"],
                choice="different-unpatterned-secret",
            )
        assert conflict.value.code == "human_decision_conflict"

        tables_cursor = await store.db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        for table_row in await tables_cursor.fetchall():
            table = str(table_row["name"])
            columns_cursor = await store.db.execute(f'PRAGMA table_info("{table}")')
            text_columns = [
                str(column["name"])
                for column in await columns_cursor.fetchall()
                if "TEXT" in str(column["type"]).upper()
            ]
            if not text_columns:
                continue
            select_columns = ", ".join(f'"{column}"' for column in text_columns)
            values_cursor = await store.db.execute(
                f'SELECT {select_columns} FROM "{table}"'
            )
            for row in await values_cursor.fetchall():
                assert all(raw_answer not in str(value) for value in row)

        await store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        await store.db.commit()
    finally:
        await store.close()

    for artifact in tmp_path.glob("pex.sqlite*"):
        assert raw_answer.encode() not in artifact.read_bytes()
    audit_path = tmp_path / "PEX_INTERVENTION_LOG.jsonl"
    assert raw_answer not in audit_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize("probe_before_crash", [False, True])
async def test_reserved_pre_io_crash_replays_exactly_once(
    tmp_path,
    probe_before_crash,
):
    store, pipeline, session, _goal, principal = await _bound_pipeline(tmp_path)
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(
                idempotency_key=f"reserved-resume-{int(probe_before_crash):04d}"
            ),
        )
        intervention_id = opened["intervention"]["id"]
        reserved = await store.reserve_human_decision_delivery(
            intervention_id=intervention_id,
            choice="iterate",
            resolved_at=utcnow(),
        )
        assert reserved["created"] is True
        assert reserved["record"]["status"] == "delivery_reserved"
        adapter = _DecisionDeliveryAdapter()
        if probe_before_crash:
            capability = await probe_human_decision_delivery(adapter)
            assert capability.ready is True

        resumed = await resolve_requested_human_decision(
            store,
            _delivery_registry(adapter),
            intervention_id=intervention_id,
            choice="iterate",
        )
        assert resumed.response()["delivery_status"] == "delivered"
        assert len(adapter.messages) == 1
        replay = await resolve_requested_human_decision(
            store,
            _delivery_registry(adapter),
            intervention_id=intervention_id,
            choice="iterate",
        )
        assert replay.replayed is True
        assert len(adapter.messages) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_prior_process_dispatching_recovers_uncertain_without_resend(tmp_path):
    store, pipeline, session, _goal, principal = await _bound_pipeline(tmp_path)
    path = store.path
    intervention_id = ""
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(idempotency_key="dispatch-restart-0001"),
        )
        intervention_id = opened["intervention"]["id"]
        reserved = await store.reserve_human_decision_delivery(
            intervention_id=intervention_id,
            choice="iterate",
            resolved_at=utcnow(),
        )
        effect_id = reserved["record"]["effect_id"]
        started = await store.start_human_decision_delivery(
            intervention_id=intervention_id,
            effect_id=effect_id,
            started_at=utcnow(),
        )
        assert started["started"] is True
        assert started["record"]["status"] == "dispatching"
        adapter = _DecisionDeliveryAdapter()
        live_duplicate = await resolve_requested_human_decision(
            store,
            _delivery_registry(adapter),
            intervention_id=intervention_id,
            choice="iterate",
        )
        assert live_duplicate.replayed is True
        assert live_duplicate.response()["delivery_status"] == "dispatching"
        assert adapter.messages == []
    finally:
        await store.close()

    restarted = Store(path, process_boot_id="test-restarted-process")
    await restarted.connect()
    try:
        current = await restarted.get_current_human_decision_resolution(intervention_id)
        assert current is not None
        assert current["status"] == "delivery_uncertain"
        assert current["delivery_code"] == "process_restarted_after_dispatch_started"
        adapter = _DecisionDeliveryAdapter()
        replay = await resolve_requested_human_decision(
            restarted,
            _delivery_registry(adapter),
            intervention_id=intervention_id,
            choice="iterate",
        )
        assert replay.replayed is True
        assert replay.response()["delivery_status"] == "delivery_uncertain"
        assert adapter.messages == []
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_human_decision_store_seals_exact_codex_turn_and_rejects_conflict(tmp_path):
    store, pipeline, session, _goal, principal = await _bound_pipeline(
        tmp_path,
        suffix="-receipt-seal",
    )
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(idempotency_key="decision-receipt-seal-0001"),
        )
        intervention_id = opened["intervention"]["id"]
        reserved = await store.reserve_human_decision_delivery(
            intervention_id=intervention_id,
            choice="iterate",
            resolved_at=utcnow(),
        )
        effect_id = reserved["record"]["effect_id"]
        await store.start_human_decision_delivery(
            intervention_id=intervention_id,
            effect_id=effect_id,
            started_at=utcnow(),
        )
        with pytest.raises(ValueError, match="requires an exact turn receipt"):
            await store.finalize_human_decision_delivery(
                intervention_id=intervention_id,
                effect_id=effect_id,
                status="delivered",
                delivery_code="send_confirmed",
                finished_at=utcnow(),
            )
        current = await store.get_current_human_decision_resolution(intervention_id)
        assert current is not None and current["status"] == "dispatching"

        receipt = {
            "schema": "pex.worker-delivery.codex-turn.v1",
            "target_session_id": session.id,
            "vendor_session_id": session.vendor_session_id,
            "vendor_turn_id": "turn-human-decision-sealed",
        }
        created = await store.finalize_human_decision_delivery(
            intervention_id=intervention_id,
            effect_id=effect_id,
            status="delivered",
            delivery_code="send_confirmed",
            worker_delivery_receipt=receipt,
            finished_at=utcnow(),
        )
        assert created["record"]["worker_delivery_receipt"] == receipt
        exact_replay = await store.finalize_human_decision_delivery(
            intervention_id=intervention_id,
            effect_id=effect_id,
            status="delivered",
            delivery_code="send_confirmed",
            worker_delivery_receipt=receipt,
            finished_at=utcnow(),
        )
        assert exact_replay["created"] is False
        with pytest.raises(ValueError, match="does not match the target session"):
            await store.finalize_human_decision_delivery(
                intervention_id=intervention_id,
                effect_id=effect_id,
                status="delivered",
                delivery_code="send_confirmed",
                worker_delivery_receipt={
                    **receipt,
                    "vendor_session_id": "another-thread",
                },
                finished_at=utcnow(),
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cancelled_send_finalizes_uncertain_then_reraises_without_secret_leak(tmp_path):
    store, pipeline, session, _goal, principal = await _bound_pipeline(tmp_path)
    raw_answer = "cancel-only-ordinary-secret"
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(
                idempotency_key="cancelled-delivery-0001",
                options=[],
            ),
        )
        adapter = _DecisionDeliveryAdapter(block_send=asyncio.Event())
        adapters = _delivery_registry(adapter)
        task = asyncio.create_task(
            resolve_requested_human_decision(
                store,
                adapters,
                intervention_id=opened["intervention"]["id"],
                choice=raw_answer,
            )
        )
        await asyncio.wait_for(adapter.send_started.wait(), timeout=2.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=3.0)

        current = await store.get_current_human_decision_resolution(
            opened["intervention"]["id"]
        )
        assert current is not None
        assert current["status"] == "delivery_uncertain"
        assert current["delivery_code"] == "send_cancelled"
        assert raw_answer not in json.dumps(current, ensure_ascii=False)
        assert len(adapter.messages) == 1
        replay = await resolve_requested_human_decision(
            store,
            adapters,
            intervention_id=opened["intervention"]["id"],
            choice=raw_answer,
        )
        assert replay.replayed is True
        assert replay.response()["delivery_status"] == "delivery_uncertain"
        assert len(adapter.messages) == 1

        cursor = await store.db.execute(
            "SELECT json FROM human_decision_resolutions WHERE intervention_id = ?",
            (opened["intervention"]["id"],),
        )
        assert raw_answer not in str((await cursor.fetchone())["json"])
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cancelled_send_preserves_cancellation_when_durable_finalize_fails(
    tmp_path,
    monkeypatch,
):
    store, pipeline, session, _goal, principal = await _bound_pipeline(tmp_path)
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(idempotency_key="cancel-finalize-failure-0001"),
        )
        adapter = _DecisionDeliveryAdapter(block_send=asyncio.Event())
        adapters = _delivery_registry(adapter)
        original_finalize = store.finalize_human_decision_delivery

        async def fail_finalize(**_kwargs):
            raise RuntimeError("injected durable finalization failure")

        monkeypatch.setattr(store, "finalize_human_decision_delivery", fail_finalize)
        task = asyncio.create_task(
            resolve_requested_human_decision(
                store,
                adapters,
                intervention_id=opened["intervention"]["id"],
                choice="iterate",
            )
        )
        await asyncio.wait_for(adapter.send_started.wait(), timeout=2.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=3.0)

        monkeypatch.setattr(store, "finalize_human_decision_delivery", original_finalize)
        current = await store.get_current_human_decision_resolution(
            opened["intervention"]["id"]
        )
        assert current is not None and current["status"] == "dispatching"
        replay = await resolve_requested_human_decision(
            store,
            adapters,
            intervention_id=opened["intervention"]["id"],
            choice="iterate",
        )
        assert replay.replayed is True
        assert replay.response()["delivery_status"] == "dispatching"
        assert len(adapter.messages) == 1
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution_order", [(0, 1), (1, 0)])
async def test_attention_generation_rollover_preserves_pending_and_newer_base_status(
    tmp_path,
    resolution_order,
):
    store, pipeline, session, _goal, principal = await _bound_pipeline(tmp_path)
    try:
        first = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(
                idempotency_key="attention-rollover-a-0001",
                question="Choose A?",
            ),
        )
        externally_updated = await store.get_session(session.id)
        assert externally_updated is not None
        externally_updated.status = SessionStatus.DRIFTING
        externally_updated.last_activity = utcnow() + timedelta(seconds=1)
        await store.upsert_session(externally_updated)

        second = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(
                idempotency_key="attention-rollover-b-0001",
                question="Choose B?",
            ),
        )
        intervention_ids = [
            first["intervention"]["id"],
            second["intervention"]["id"],
        ]
        waiting = await store.get_session(session.id)
        assert waiting is not None
        assert waiting.status == SessionStatus.NEEDS_DECISION
        attention = waiting.metadata["human_decision_attention"]
        assert attention["base_status"] == SessionStatus.DRIFTING.value
        assert set(attention["pending_intervention_ids"]) == set(intervention_ids)

        adapter = _DecisionDeliveryAdapter()
        adapters = _delivery_registry(adapter)
        first_result = await resolve_requested_human_decision(
            store,
            adapters,
            intervention_id=intervention_ids[resolution_order[0]],
            choice="iterate",
        )
        assert first_result.response()["delivery_status"] == "delivered"
        middle = await store.get_session(session.id)
        assert middle is not None
        assert middle.status == SessionStatus.NEEDS_DECISION
        remaining = middle.metadata["human_decision_attention"]
        assert remaining["pending_intervention_ids"] == [
            intervention_ids[resolution_order[1]]
        ]

        second_result = await resolve_requested_human_decision(
            store,
            adapters,
            intervention_id=intervention_ids[resolution_order[1]],
            choice="iterate",
        )
        assert second_result.response()["delivery_status"] == "delivered"
        final = await store.get_session(session.id)
        assert final is not None
        assert final.status == SessionStatus.DRIFTING
        assert "human_decision_attention" not in final.metadata
        assert len(adapter.messages) == 2
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_resolution_never_overwrites_newer_external_session_status(tmp_path):
    store, pipeline, session, _goal, principal = await _bound_pipeline(tmp_path)
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(idempotency_key="newer-session-state-0001"),
        )
        externally_updated = await store.get_session(session.id)
        assert externally_updated is not None
        externally_updated.status = SessionStatus.VERIFYING
        externally_updated.last_activity = utcnow() + timedelta(seconds=1)
        await store.upsert_session(externally_updated)

        adapter = _DecisionDeliveryAdapter()
        result = await resolve_requested_human_decision(
            store,
            _delivery_registry(adapter),
            intervention_id=opened["intervention"]["id"],
            choice="iterate",
        )
        assert result.response()["delivery_status"] == "delivered"
        assert result.response()["session_status"] == SessionStatus.VERIFYING.value
        final = await store.get_session(session.id)
        assert final is not None
        assert final.status == SessionStatus.VERIFYING
        assert "human_decision_attention" not in final.metadata
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter", "expected_status", "expected_calls"),
    [
        (
            _DecisionDeliveryAdapter(
                capabilities=AdapterCapabilities(send_message=False)
            ),
            "unsupported",
            0,
        ),
        (_DecisionDeliveryAdapter(send_result=False), "rejected", 1),
        (
            _DecisionDeliveryAdapter(send_error=RuntimeError("private adapter detail")),
            "delivery_uncertain",
            1,
        ),
        (_DecisionDeliveryAdapter(send_result=1), "delivery_uncertain", 1),
        (_DecisionDeliveryAdapter(send_result=None), "delivery_uncertain", 1),
    ],
)
async def test_delivery_outcomes_are_honest_and_never_resume_working(
    tmp_path,
    adapter,
    expected_status,
    expected_calls,
):
    store, pipeline, session, _goal, principal = await _bound_pipeline(tmp_path)
    try:
        opened = await pipeline.request_human_decision(
            session,
            principal=principal,
            request=_request(
                idempotency_key=(
                    "honest-outcome-"
                    + hashlib.sha256(
                        f"{expected_status}:{type(adapter.send_result).__name__}:"
                        f"{type(adapter.send_error).__name__}".encode()
                    ).hexdigest()[:16]
                )
            ),
        )
        result = await resolve_requested_human_decision(
            store,
            _delivery_registry(adapter),
            intervention_id=opened["intervention"]["id"],
            choice="iterate",
        )
        response = result.response()
        assert response["ok"] is False
        assert response["delivered"] is False
        assert response["delivery_status"] == expected_status
        assert response["session_status"] == SessionStatus.NEEDS_DECISION.value
        assert len(adapter.messages) == expected_calls
        assert "private adapter detail" not in json.dumps(response)
        live = await store.get_session(session.id)
        assert live is not None and live.status == SessionStatus.NEEDS_DECISION
    finally:
        await store.close()
