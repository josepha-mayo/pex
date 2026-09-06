import asyncio
import hashlib
import json
import sqlite3
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from urllib.parse import unquote

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.base import AdapterMessageResult, HarnessAdapter
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.mcp_auth import MCPPrincipal
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import MCP_REPORT_PROGRESS_TOOL, Store, utcnow
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.context import (
    ContextHandoffRequest,
    ContextItem,
    ProgressEvidenceReference,
    ProgressReport,
)
from pex_protocol.enums import ContextKind, EventPhase, EventType, HarnessType
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorResult

_OPERATOR_TOKEN = "handoff-operator-test-token-0123456789abcdef"


class _HandoffOperatorClient(AsyncClient):
    """Attach the authenticated goal-control contract to domain-focused requests."""

    _operation_sequence = 0

    async def request(self, method, url, *, json=None, **kwargs):
        path = str(url)
        verb = str(method).upper()
        if isinstance(json, dict) and (
            (verb == "POST" and path == "/v1/goals")
            or (verb == "PATCH" and path.startswith("/v1/goals/"))
            or (verb == "POST" and path.endswith("/attach"))
        ):
            self._operation_sequence += 1
            json = dict(json)
            json.setdefault(
                "idempotency_key",
                f"handoff-goal-control-{self._operation_sequence:08d}",
            )
            if path.endswith("/attach"):
                session_path = path.removesuffix("/attach")
                session_id = unquote(session_path.removeprefix("/v1/sessions/"))
                session_control = await state.store.get_session_control_state(session_id)
                goal_id = str(json.get("goal_id") or "")
                try:
                    goal = await state.store.get_goal_intent_view(goal_id)
                except Exception:
                    goal = None
                json.setdefault(
                    "expected_goal_id",
                    (
                        session_control["session"].goal_id
                        if session_control is not None
                        else None
                    ),
                )
                json.setdefault(
                    "expected_control_revision",
                    (
                        session_control.get("control_revision", 0)
                        if session_control is not None
                        else 0
                    ),
                )
                json.setdefault(
                    "expected_goal_intent_revision",
                    goal.get("intent_revision", 0) if goal is not None else 0,
                )
        return await super().request(method, url, json=json, **kwargs)


class _TypedCodexHandoffAdapter(HarnessAdapter):
    name = "codex"

    def __init__(self, result: AdapterMessageResult) -> None:
        self.result = result
        self.calls = 0

    async def probe(self) -> AdapterCapabilities:
        return AdapterCapabilities(send_message=True, inject_context=True)

    async def discover_sessions(self) -> list[HarnessSession]:
        return []

    async def send_message(self, session, text, attachments=None):
        self.calls += 1
        return self.result


async def _close_client_resources(pipeline: Pipeline, store: Store) -> None:
    try:
        await pipeline.close_presentations()
    finally:
        await store.close()


@pytest.fixture
async def client(tmp_path):
    settings = Settings(
        require_auth=True,
        token=_OPERATOR_TOKEN,
        home=tmp_path,
        autonomy="manage",
    )
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    pipeline = Pipeline(store, adapters, bus, settings)
    state.pipeline = pipeline
    state.token = _OPERATOR_TOKEN
    try:
        await store.connect()
        app = create_app()
        async with _HandoffOperatorClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers={"Authorization": f"Bearer {_OPERATOR_TOKEN}"},
        ) as ac:
            yield ac
    finally:
        await _close_client_resources(pipeline, store)


@pytest.mark.asyncio
async def test_client_cleanup_joins_pipeline_work_before_closing_store(tmp_path):
    store = Store(tmp_path / "fixture-cleanup.sqlite")
    await store.connect()
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(home=tmp_path, require_auth=False),
    )
    started = asyncio.Event()
    store_touch_finished = asyncio.Event()

    async def pending_presentation() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Presentation cancellation may still need to finish an already-owned
            # Store operation before the fixture closes the SQLite worker.
            await store.get_session("synthetic:missing")
            store_touch_finished.set()
            raise

    task = asyncio.create_task(pending_presentation())
    pipeline._presentation_tasks.add(task)
    try:
        await started.wait()
    finally:
        await _close_client_resources(pipeline, store)

    assert task.cancelled()
    assert store_touch_finished.is_set()
    assert not pipeline._presentation_tasks
    assert store._db is None


@pytest.mark.asyncio
async def test_rest_handoff_requires_authenticated_operator_control(tmp_path, monkeypatch):
    settings = Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = None
    source_lookup = AsyncMock(side_effect=AssertionError("auth must run before Store access"))
    dispatch = AsyncMock(side_effect=AssertionError("auth must run before adapter dispatch"))
    monkeypatch.setattr(store, "get_session_for_authority", source_lookup)
    monkeypatch.setattr(state.pipeline, "request_context_handoff", dispatch)
    await store.connect()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://127.0.0.1",
        ) as unauthenticated:
            response = await unauthenticated.post(
                "/v1/sessions/synthetic:source/handoff",
                json={
                    "idempotency_key": "rest-handoff-auth-0001",
                    "target_session_id": "synthetic:target",
                    "token_budget": 2_000,
                },
            )
    finally:
        await store.close()

    assert response.status_code == 403
    assert response.json()["detail"] == "operator mutations require bridge authentication"
    source_lookup.assert_not_awaited()
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_rest_handoff_rejects_wrong_operator_token(client: AsyncClient):
    response = await client.post(
        "/v1/sessions/synthetic:source/handoff",
        headers={"Authorization": "Bearer wrong-operator-token"},
        json={
            "idempotency_key": "rest-handoff-auth-0002",
            "target_session_id": "synthetic:target",
            "token_budget": 2_000,
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid token"


@pytest.mark.asyncio
async def test_rest_handoff_rejects_missing_operator_token(client: AsyncClient):
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://127.0.0.1",
    ) as missing_token:
        response = await missing_token.post(
            "/v1/sessions/synthetic:source/handoff",
            json={
                "idempotency_key": "rest-handoff-auth-0003",
                "target_session_id": "synthetic:target",
                "token_budget": 2_000,
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid token"


@pytest.mark.asyncio
async def test_rest_handoff_fails_closed_when_operator_token_is_unavailable(
    client: AsyncClient,
):
    state.token = None
    try:
        response = await client.post(
            "/v1/sessions/synthetic:source/handoff",
            json={
                "idempotency_key": "rest-handoff-auth-0004",
                "target_session_id": "synthetic:target",
                "token_budget": 2_000,
            },
        )
    finally:
        state.token = _OPERATOR_TOKEN

    assert response.status_code == 503
    assert response.json()["detail"] == "bridge authentication is unavailable"


async def _bind_cursor_conversation(
    client: AsyncClient,
    *,
    conversation_id: str,
    workspace_root: str = "C:/proj",
) -> None:
    started = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "sessionStart",
            "conversation_id": conversation_id,
            "workspace_roots": [workspace_root],
        },
    )
    assert started.status_code == 200, started.text
    session_id = f"cursor:{conversation_id}"
    session = (await client.get(f"/v1/sessions/{session_id}")).json()
    project_id = session["project_id"] or session["cwd"]
    assert project_id
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": project_id,
                "title": f"Authorize {conversation_id}",
                "objective": "Classify this bound pre-action permission request.",
            },
        )
    ).json()
    attached = await client.post(
        f"/v1/sessions/{session_id}/attach",
        json={"goal_id": goal["id"]},
    )
    assert attached.status_code == 200, attached.text


async def _deliver_synthetic_artifact_handoff(
    client: AsyncClient,
    *,
    target_session_id: str,
    goal_id: str,
    index: int,
    artifact_path: str,
    key_prefix: str,
    source_session_id: str | None = None,
) -> dict[str, object]:
    if source_session_id is None:
        source = state.adapters.synthetic.seed_session(
            vendor_id=f"{key_prefix}-source-{index:03d}"
        )
        await state.store.upsert_session(source)
        source_session_id = source.id
        attached = await client.post(
            f"/v1/sessions/{source_session_id}/attach",
            json={"goal_id": goal_id},
        )
        assert attached.status_code == 200, attached.text
    discovered = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source_session_id,
            "event_type": EventType.FILE_READ.value,
            "message": (
                f"Validated artifact contract {index:03d} is at {artifact_path}; "
                "the target must use this exact recorded path."
            ),
            "file_paths": [artifact_path],
        },
    )
    assert discovered.status_code == 200, discovered.text
    handoff = await client.post(
        f"/v1/sessions/{source_session_id}/handoff",
        json={
            "idempotency_key": f"{key_prefix}-handoff-{index:04d}",
            "target_session_id": target_session_id,
            "token_budget": 2_000,
        },
    )
    assert handoff.status_code == 200, handoff.text
    return handoff.json()


@pytest.mark.parametrize(
    "payload",
    [
        {"target_session_id": "synthetic:target"},
        {"idempotency_key": "short", "target_session_id": "synthetic:target"},
        {
            "idempotency_key": "rest-handoff-bounds-0001",
            "target_session_id": "synthetic:target",
            "token_budget": 255,
        },
        {
            "idempotency_key": "rest-handoff-bounds-0002",
            "target_session_id": "synthetic:target",
            "token_budget": 12_001,
        },
        {
            "idempotency_key": "rest-handoff-bounds-0003",
            "target_session_id": "synthetic:target",
            "token_budget": "2000",
        },
    ],
)
@pytest.mark.asyncio
async def test_context_handoff_requires_caller_key_and_bounded_budget(
    client: AsyncClient,
    payload: dict[str, object],
):
    response = await client.post(
        "/v1/sessions/synthetic:source/handoff",
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("status", "expected_status_code"),
    [
        ("delivered", 200),
        ("reserved", 202),
        ("dispatching", 202),
        ("delivery_uncertain", 502),
        ("failed", 409),
        ("skipped", 409),
    ],
)
@pytest.mark.asyncio
async def test_rest_handoff_preserves_canonical_effect_status(
    client: AsyncClient,
    monkeypatch,
    status: str,
    expected_status_code: int,
):
    source = (await client.post("/v1/synthetic/sessions")).json()
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Preserve the canonical handoff receipt",
                "objective": "Return the exact durable effect state to the operator",
            },
        )
    ).json()
    attached = await client.post(
        f"/v1/sessions/{source['id']}/attach",
        json={"goal_id": goal["id"]},
    )
    assert attached.status_code == 200
    canonical = AsyncMock(
        return_value={
            "ok": status == "delivered",
            "status": status,
            "effect": {"state": status},
            "replayed": False,
        }
    )
    monkeypatch.setattr(state.pipeline, "request_context_handoff", canonical)

    response = await client.post(
        f"/v1/sessions/{source['id']}/handoff",
        json={
            "idempotency_key": "rest-handoff-status-0001",
            "target_session_id": "synthetic:target",
            "token_budget": 3_000,
        },
    )

    assert response.status_code == expected_status_code
    assert response.json()["status"] == status
    call = canonical.await_args
    assert call.args == (await state.store.get_session(source["id"]),)
    assert call.kwargs["principal_id"] == "local_bridge_operator"
    assert call.kwargs["actor_assurance"] == "bridge_bearer"
    assert call.kwargs["request"] == ContextHandoffRequest(
        idempotency_key="rest-handoff-status-0001",
        target_session_id="synthetic:target",
        token_budget=3_000,
    )


@pytest.mark.asyncio
async def test_context_handoff_injects_bundle(client: AsyncClient):
    source = (await client.post("/v1/synthetic/sessions")).json()
    published_interventions: list[dict[str, object]] = []

    async def capture_intervention(topic: str, payload: dict[str, object]) -> None:
        if topic == "intervention":
            published_interventions.append(payload)

    state.bus.subscribe(capture_intervention)
    # second session
    source_adapter = state.adapters.synthetic
    target = source_adapter.seed_session(vendor_id="synth-2")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Eval",
                "objective": "Share the dataset path discovered by Codex with Cursor",
                "acceptance_criteria": ["the target uses the discovered dataset path"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{source['id']}/attach", json={"goal_id": goal["id"]})
    await client.post(f"/v1/sessions/{target.id}/attach", json={"goal_id": goal["id"]})
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source["id"],
            "event_type": EventType.AGENT_RESPONSE.value,
            "message": "Dataset is at artifacts/prepared_dataset.parquet. Do not regenerate it.",
            "file_paths": ["artifacts/prepared_dataset.parquet"],
        },
    )
    pre_delivery = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": target.id,
            "event_type": EventType.FILE_READ.value,
            "message": "Inspected the prepared dataset before receiving any handoff.",
            "file_paths": ["artifacts/prepared_dataset.parquet"],
        },
    )
    assert pre_delivery.status_code == 200
    handoff = await client.post(
        f"/v1/sessions/{source['id']}/handoff",
        json={
            "idempotency_key": "rest-handoff-dataset-0001",
            "target_session_id": target.id,
            "token_budget": 2_000,
        },
    )
    assert handoff.status_code == 200
    body = handoff.json()
    assert body["ok"] is True
    assert body["status"] == "delivered"
    assert body["replayed"] is False
    assert body["assimilation"]["status"] == "awaiting_target_evidence"
    assert body["assimilation"]["assimilation_proven"] is False
    assert body["assimilation"]["watermark"]["target_accept_seq_through"] >= 1
    assert body["assimilation"]["evidence"] == []
    assert body["assimilation"]["target_action_monitoring"] == {
        "available": True,
        "scope": "first_three_meaningful_accepted_target_events",
        "observed_count": 0,
        "actions_truncated": False,
        "possible_failure_observed": False,
        "handoff_failure_proven": False,
        "actions": [],
    }
    assert "prepared_dataset" in str(body["bundle"]).lower()
    bundle_receipt = body["bundle_receipt"]
    assert bundle_receipt["schema"] == "pex.handoff-bundle-receipt.v1"
    assert bundle_receipt["bundle_digest"] == body["assimilation"]["bundle_digest"]
    assert bundle_receipt["operator_effect_id"] == body["effect"]["effect_id"]
    assert bundle_receipt["context_item_ids"] == [
        item["id"] for item in body["bundle"]["items"]
    ]
    assert source_adapter.inbox[target.id]
    assert "context_id=" in source_adapter.inbox[target.id][0]
    intervention = body["intervention"]
    assert intervention["action_taken"] == "FRESH_HANDOFF"
    assert intervention["result"] == "handoff_injected"
    assert intervention["reversible"] is False
    assert intervention["metadata"]["human_requested"] is True
    actor_cursor = await state.store.db.execute(
        "SELECT COUNT(*) FROM human_operator_terminal_actions WHERE effect_id = ?",
        (body["effect"]["effect_id"],),
    )
    assert (await actor_cursor.fetchone())[0] == 1
    metrics = await state.store.attention_metrics()
    assert metrics["human_interventions"]["source_counts"][
        "operator_context_handoff"
    ] == 1
    assert metrics["human_interventions"]["unverified_operator_action_counts"][
        "operator_handoff"
    ] == 0
    assert metrics["human_interventions"]["value"] is None
    assert intervention["proposed_action"]["payload"] == {
        "bundle_receipt": bundle_receipt
    }
    assert "prepared_dataset" not in str(intervention["proposed_action"]["payload"]).lower()
    assert published_interventions
    assert published_interventions[-1]["proposed_action"]["payload"] == {
        "bundle_receipt": bundle_receipt
    }
    stored = await client.get("/v1/interventions", params={"session_id": target.id})
    stored_intervention = next(
        item for item in stored.json() if item["id"] == intervention["id"]
    )
    assert stored_intervention["proposed_action"]["payload"] == {
        "bundle_receipt": bundle_receipt
    }
    detailed = await client.get(
        "/v1/interventions",
        params={"session_id": target.id, "include_handoff_bundle": True},
    )
    detailed_intervention = next(
        item for item in detailed.json() if item["id"] == intervention["id"]
    )
    assert "prepared_dataset" in str(
        detailed_intervention["proposed_action"]["payload"]["bundle"]
    ).lower()
    audit_cursor = await state.store.db.execute(
        "SELECT json FROM intervention_audit WHERE intervention_id = ? ORDER BY id",
        (intervention["id"],),
    )
    audit_rows = [json.loads(row["json"]) for row in await audit_cursor.fetchall()]
    assert len(audit_rows) == 3
    assert all(
        row["action_payload"] == {"bundle_receipt": bundle_receipt}
        for row in audit_rows
    )
    assert "prepared_dataset" not in json.dumps(audit_rows).lower()
    projected = [
        json.loads(line)
        for line in state.store.audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    projected_rows = [
        row for row in projected if row.get("intervention_id") == intervention["id"]
    ]
    assert len(projected_rows) == 3
    assert "prepared_dataset" not in json.dumps(projected_rows).lower()
    effect = await state.store.get_operator_effect(body["effect"]["effect_id"])
    assert effect is not None
    assert "prepared_dataset" in str(effect["payload"]["bundle"]).lower()

    replay = await client.post(
        f"/v1/sessions/{source['id']}/handoff",
        json={
            "idempotency_key": "rest-handoff-dataset-0001",
            "target_session_id": target.id,
            "token_budget": 2_000,
        },
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["effect"] == body["effect"]
    assert replay.json()["bundle_receipt"] == bundle_receipt
    assert replay.json()["assimilation"]["status"] == "awaiting_target_evidence"
    assert len(source_adapter.inbox[target.id]) == 1

    generic = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": target.id,
            "event_type": EventType.STATUS.value,
            "message": "Working",
        },
    )
    assert generic.status_code == 200
    still_pending = await client.get(
        f"/v1/handoffs/{body['effect']['effect_id']}/assimilation"
    )
    assert still_pending.status_code == 200
    assert still_pending.json()["status"] == "awaiting_target_evidence"
    assert still_pending.json()["target_action_monitoring"]["observed_count"] == 0

    failed_attempt = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": target.id,
            "event_type": EventType.TOOL_FAILURE.value,
            "message": "Dataset inspection tool failed before reading the artifact.",
            "error": "reader unavailable",
        },
    )
    assert failed_attempt.status_code == 200
    failure_status = await client.get(
        f"/v1/handoffs/{body['effect']['effect_id']}/assimilation"
    )
    assert failure_status.status_code == 200
    failure_monitoring = failure_status.json()["target_action_monitoring"]
    assert failure_status.json()["status"] == "awaiting_target_evidence"
    assert failure_monitoring["observed_count"] == 1
    assert failure_monitoring["possible_failure_observed"] is True
    assert failure_monitoring["handoff_failure_proven"] is False
    assert failure_monitoring["actions"][0]["classification"] == (
        "possible_failure_observed"
    )

    relevant = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": target.id,
            "event_type": EventType.FILE_READ.value,
            "message": "Using the delivered prepared dataset for evaluation.",
            "file_paths": ["artifacts/prepared_dataset.parquet"],
        },
    )
    assert relevant.status_code == 200
    relevant_event = HarnessEvent.model_validate(relevant.json()["event"])
    observed = await client.get(f"/v1/handoffs/{body['effect']['effect_id']}/assimilation")
    assert observed.status_code == 200
    assimilation = observed.json()
    assert assimilation["status"] == "relevant_action_observed"
    assert assimilation["assimilation_proven"] is False
    assert assimilation["first_relevant_action"]["target_event_id"] == relevant_event.event_id
    assert assimilation["first_relevant_action"]["evidence_kind"] == "artifact_read"
    assert assimilation["first_relevant_action"]["evidence_strength"] == "behavioral"
    assert assimilation["first_relevant_action"]["verified"] is False
    assert assimilation["first_relevant_action"]["matched_artifact_paths"] == [
        "artifacts/prepared_dataset.parquet"
    ]
    assert len(assimilation["evidence"]) == 1
    monitoring = assimilation["target_action_monitoring"]
    assert monitoring["observed_count"] == 2
    assert monitoring["possible_failure_observed"] is True
    assert monitoring["handoff_failure_proven"] is False
    assert monitoring["actions"][1]["event_id"] == relevant_event.event_id
    assert monitoring["actions"][1]["classification"] == "relevant_action_observed"

    target_session = await state.store.get_session_for_authority(target.id)
    assert target_session is not None
    await state.pipeline.ingest_event(relevant_event, target_session)
    deduped = await state.store.handoff_assimilation_status(body["effect"]["effect_id"])
    assert len(deduped["evidence"]) == 1

    reopened = Store(state.store.path)
    await reopened.connect()
    try:
        persisted = await reopened.handoff_assimilation_status(body["effect"]["effect_id"])
        assert persisted == deduped
    finally:
        await reopened.close()

    conflict = await client.post(
        f"/v1/sessions/{source['id']}/handoff",
        json={
            "idempotency_key": "rest-handoff-dataset-0001",
            "target_session_id": target.id,
            "token_budget": 3_000,
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "context_handoff_idempotency_conflict"
    assert len(source_adapter.inbox[target.id]) == 1

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        await state.store.db.execute(
            "DELETE FROM handoff_assimilation_evidence WHERE effect_id = ?",
            (body["effect"]["effect_id"],),
        )
    await state.store.db.rollback()
    cursor = await state.store.db.execute(
        "SELECT evidence_id, json FROM handoff_assimilation_evidence WHERE effect_id = ?",
        (body["effect"]["effect_id"],),
    )
    evidence_row = await cursor.fetchone()
    assert evidence_row is not None
    forged = json.loads(evidence_row["json"])
    forged["bundle_digest"] = "0" * 64
    await state.store.db.execute("DROP TRIGGER trg_handoff_assimilation_immutable")
    await state.store.db.execute(
        "UPDATE handoff_assimilation_evidence SET json = ? WHERE evidence_id = ?",
        (json.dumps(forged), evidence_row["evidence_id"]),
    )
    await state.store.db.commit()
    with pytest.raises(RuntimeError, match="assimilation binding"):
        await state.store.handoff_assimilation_status(body["effect"]["effect_id"])


@pytest.mark.asyncio
async def test_target_can_acknowledge_exact_delivered_context_without_claiming_use(
    client: AsyncClient,
):
    source = (await client.post("/v1/synthetic/sessions")).json()
    target = state.adapters.synthetic.seed_session(vendor_id="ack-target")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Assimilation acknowledgement",
                "objective": "Use the transferred parser contract without inventing context",
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{source['id']}/attach", json={"goal_id": goal["id"]})
    await client.post(f"/v1/sessions/{target.id}/attach", json={"goal_id": goal["id"]})
    discovered = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source["id"],
            "event_type": EventType.FILE_READ.value,
            "message": "The parser contract is artifacts/parser.json.",
            "file_paths": ["artifacts/parser.json"],
        },
    )
    assert discovered.status_code == 200
    delivered = await client.post(
        f"/v1/sessions/{source['id']}/handoff",
        json={
            "idempotency_key": "rest-handoff-ack-0001",
            "target_session_id": target.id,
            "token_budget": 2_000,
        },
    )
    assert delivered.status_code == 200, delivered.text
    body = delivered.json()
    transferred = [
        item
        for item in body["bundle"]["items"]
        if item["metadata"].get("files") == ["artifacts/parser.json"]
    ]
    assert len(transferred) == 1
    context_id = transferred[0]["id"]

    target_session = await state.store.get_session_for_authority(target.id)
    assert target_session is not None
    issued_at = utcnow() - timedelta(seconds=1)
    principal_record = await state.store.issue_mcp_principal(
        principal_id="mcp-handoff-ack-target",
        session_id=target.id,
        goal_id=goal["id"],
        project_id="demo",
        vendor_session_id=target_session.vendor_session_id,
        harness_type=target_session.harness_type.value,
        scopes=["mcp:read", MCP_REPORT_PROGRESS_TOOL],
        token_digest=hashlib.sha256(b"ack-target-secret").hexdigest(),
        issued_at=issued_at,
        expires_at=issued_at + timedelta(hours=1),
    )
    principal = MCPPrincipal(
        principal_id=principal_record["principal_id"],
        kind="session",
        scopes=frozenset(principal_record["scopes"]),
        session_id=target.id,
        goal_id=goal["id"],
        project_id="demo",
        project_binding=principal_record["project_binding"],
        vendor_session_id=target_session.vendor_session_id,
        harness_type=target_session.harness_type,
        issued_at=datetime.fromisoformat(principal_record["issued_at"]),
        expires_at=datetime.fromisoformat(principal_record["expires_at"]),
    )
    report = ProgressReport(
        idempotency_key="target-ack-report-0001",
        summary="I received the parser contract and will inspect it before implementation.",
        evidence_refs=(ProgressEvidenceReference(type="context", id=context_id),),
    )
    acknowledgement = await state.pipeline.record_reported_progress(
        target_session,
        principal=principal,
        report=report,
    )
    assert acknowledgement["replayed"] is False

    assimilation = await state.store.handoff_assimilation_status(body["effect"]["effect_id"])
    assert assimilation["status"] == "target_acknowledged"
    assert assimilation["assimilation_proven"] is False
    assert assimilation["first_relevant_action"] is None
    assert len(assimilation["evidence"]) == 1
    evidence = assimilation["evidence"][0]
    assert evidence["evidence_kind"] == "target_acknowledgement"
    assert evidence["evidence_strength"] == "self_attested"
    assert evidence["verified"] is False
    assert evidence["matched_context_item_ids"] == [context_id]
    assert evidence["matched_artifact_paths"] == []

    replay = await state.pipeline.record_reported_progress(
        target_session,
        principal=principal,
        report=report,
    )
    assert replay["replayed"] is True
    replayed_status = await state.store.handoff_assimilation_status(
        body["effect"]["effect_id"]
    )
    assert replayed_status == assimilation


@pytest.mark.asyncio
async def test_corrupt_exact_ack_index_rolls_back_the_entire_progress_mutation(
    client: AsyncClient,
):
    target = state.adapters.synthetic.seed_session(vendor_id="corrupt-ack-target")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Reject corrupt acknowledgement authority",
                "objective": "Use the exact contract at artifacts/corrupt-ack.json",
            },
        )
    ).json()
    attached = await client.post(
        f"/v1/sessions/{target.id}/attach",
        json={"goal_id": goal["id"]},
    )
    assert attached.status_code == 200, attached.text
    body = await _deliver_synthetic_artifact_handoff(
        client,
        target_session_id=target.id,
        goal_id=goal["id"],
        index=0,
        artifact_path="artifacts/corrupt-ack.json",
        key_prefix="corrupt-ack",
    )
    effect_id = body["effect"]["effect_id"]
    context_items = [
        item
        for item in body["bundle"]["items"]
        if item["metadata"].get("files") == ["artifacts/corrupt-ack.json"]
    ]
    assert len(context_items) == 1
    context_id = context_items[0]["id"]
    target_session = await state.store.get_session_for_authority(target.id)
    assert target_session is not None
    issued_at = utcnow() - timedelta(seconds=1)
    principal_record = await state.store.issue_mcp_principal(
        principal_id="mcp-corrupt-ack-target",
        session_id=target.id,
        goal_id=goal["id"],
        project_id="demo",
        vendor_session_id=target_session.vendor_session_id,
        harness_type=target_session.harness_type.value,
        scopes=["mcp:read", MCP_REPORT_PROGRESS_TOOL],
        token_digest=hashlib.sha256(b"corrupt-ack-secret").hexdigest(),
        issued_at=issued_at,
        expires_at=issued_at + timedelta(hours=1),
    )
    principal = MCPPrincipal(
        principal_id=principal_record["principal_id"],
        kind="session",
        scopes=frozenset(principal_record["scopes"]),
        session_id=target.id,
        goal_id=goal["id"],
        project_id="demo",
        project_binding=principal_record["project_binding"],
        vendor_session_id=target_session.vendor_session_id,
        harness_type=target_session.harness_type,
        issued_at=datetime.fromisoformat(principal_record["issued_at"]),
        expires_at=datetime.fromisoformat(principal_record["expires_at"]),
    )
    candidate_cursor = await state.store.db.execute(
        "SELECT candidate_id, json FROM handoff_context_candidates "
        "WHERE effect_id = ? AND context_item_id = ?",
        (effect_id, context_id),
    )
    candidate_row = await candidate_cursor.fetchone()
    assert candidate_row is not None
    forged = json.loads(candidate_row["json"])
    forged["bundle_digest"] = "0" * 64
    await state.store.db.execute("DROP TRIGGER trg_handoff_context_candidate_immutable")
    await state.store.db.execute(
        "UPDATE handoff_context_candidates SET json = ? WHERE candidate_id = ?",
        (json.dumps(forged), candidate_row["candidate_id"]),
    )
    await state.store.db.commit()

    tables = (
        "events",
        "context_items",
        "interventions",
        "mcp_mutations",
        "handoff_assimilation_evidence",
    )

    async def counts() -> dict[str, int]:
        result: dict[str, int] = {}
        for table in tables:
            cursor = await state.store.db.execute(f"SELECT COUNT(*) AS count FROM {table}")
            row = await cursor.fetchone()
            assert row is not None
            result[table] = int(row["count"])
        return result

    before = await counts()
    with pytest.raises(RuntimeError, match="context candidate binding"):
        await state.pipeline.record_reported_progress(
            target_session,
            principal=principal,
            report=ProgressReport(
                idempotency_key="corrupt-ack-report-0001",
                summary="I received the exact contract.",
                evidence_refs=(
                    ProgressEvidenceReference(type="context", id=context_id),
                ),
            ),
        )
    assert await counts() == before


@pytest.mark.asyncio
async def test_reentrant_target_action_after_dispatch_start_is_observed(
    client: AsyncClient,
    monkeypatch,
):
    source = (await client.post("/v1/synthetic/sessions")).json()
    target = state.adapters.synthetic.seed_session(vendor_id="reentrant-target")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Reentrant delivery evidence",
                "objective": "Use artifacts/reentrant.json after it is handed off",
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{source['id']}/attach", json={"goal_id": goal["id"]})
    await client.post(f"/v1/sessions/{target.id}/attach", json={"goal_id": goal["id"]})
    discovered = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source["id"],
            "event_type": EventType.FILE_READ.value,
            "message": "The validated input is artifacts/reentrant.json.",
            "file_paths": ["artifacts/reentrant.json"],
        },
    )
    assert discovered.status_code == 200
    adapter = state.adapters.synthetic
    original_inject = adapter.inject_context

    async def inject_and_emit(session, bundle):
        accepted = await original_inject(session, bundle)
        event = adapter.emit(
            session,
            EventType.FILE_READ,
            message_delta="Opened the handed-off reentrant input.",
            file_paths=["artifacts/reentrant.json"],
        )
        await state.pipeline.ingest_event(event, session)
        return accepted

    monkeypatch.setattr(adapter, "inject_context", inject_and_emit)
    delivered = await client.post(
        f"/v1/sessions/{source['id']}/handoff",
        json={
            "idempotency_key": "rest-handoff-reentrant-0001",
            "target_session_id": target.id,
            "token_budget": 2_000,
        },
    )
    assert delivered.status_code == 200, delivered.text
    assimilation = delivered.json()["assimilation"]
    assert assimilation["status"] == "relevant_action_observed"
    assert assimilation["first_relevant_action"]["evidence_kind"] == "artifact_read"
    assert (
        assimilation["first_relevant_action"]["target_event_accept_seq"]
        > assimilation["watermark"]["target_accept_seq_through"]
    )


@pytest.mark.asyncio
async def test_one_passive_action_credits_only_newest_matching_handoff(client: AsyncClient):
    target = state.adapters.synthetic.seed_session(vendor_id="single-owner-target")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Single passive evidence owner",
                "objective": "Use the newest contract for artifacts/shared.json",
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{target.id}/attach", json={"goal_id": goal["id"]})

    effect_ids: list[str] = []
    source_messages = {
        1: "Alpha schema contract maps legacy fields at artifacts/shared.json.",
        2: "Newest validation manifest records release gates at artifacts/shared.json.",
    }
    for index in (1, 2):
        source_session = state.adapters.synthetic.seed_session(
            vendor_id=f"single-owner-source-{index}"
        )
        await state.store.upsert_session(source_session)
        source = source_session.model_dump(mode="json")
        await client.post(
            f"/v1/sessions/{source['id']}/attach",
            json={"goal_id": goal["id"]},
        )
        discovered = await client.post(
            "/v1/synthetic/events",
            json={
                "session_id": source["id"],
                "event_type": EventType.FILE_READ.value,
                "message": source_messages[index],
                "file_paths": ["artifacts/shared.json"],
            },
        )
        assert discovered.status_code == 200
        handoff = await client.post(
            f"/v1/sessions/{source['id']}/handoff",
            json={
                "idempotency_key": f"rest-handoff-single-owner-000{index}",
                "target_session_id": target.id,
                "token_budget": 2_000,
            },
        )
        assert handoff.status_code == 200, handoff.text
        effect_ids.append(handoff.json()["effect"]["effect_id"])

    relevant = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": target.id,
            "event_type": EventType.FILE_READ.value,
            "message": "Opened the newest shared contract.",
            "file_paths": ["artifacts/shared.json"],
        },
    )
    assert relevant.status_code == 200
    statuses = [await state.store.handoff_assimilation_status(item) for item in effect_ids]
    assert [item["status"] for item in statuses].count("relevant_action_observed") == 1
    assert statuses[0]["status"] == "awaiting_target_evidence"
    assert statuses[1]["status"] == "relevant_action_observed"


@pytest.mark.asyncio
async def test_indexed_handoff_routing_has_no_newest_64_blind_spot(client: AsyncClient):
    target = state.adapters.synthetic.seed_session(vendor_id="indexed-capacity-target")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Index every delivered handoff",
                "objective": (
                    "Use every validated indexed artifact contract while retaining exact "
                    "evidence routing beyond 64 target handoffs"
                ),
            },
        )
    ).json()
    attached = await client.post(
        f"/v1/sessions/{target.id}/attach",
        json={"goal_id": goal["id"]},
    )
    assert attached.status_code == 200, attached.text

    source = state.adapters.synthetic.seed_session(vendor_id="indexed-capacity-source")
    await state.store.upsert_session(source)
    source_attached = await client.post(
        f"/v1/sessions/{source.id}/attach",
        json={"goal_id": goal["id"]},
    )
    assert source_attached.status_code == 200, source_attached.text

    first_body: dict[str, object] | None = None
    first_context_id = ""
    for index in range(65):
        artifact_path = f"artifacts/indexed-{index:03d}.json"
        body = await _deliver_synthetic_artifact_handoff(
            client,
            target_session_id=target.id,
            goal_id=goal["id"],
            index=index,
            artifact_path=artifact_path,
            key_prefix="indexed-capacity",
            source_session_id=source.id,
        )
        if index == 0:
            first_body = body
            matching_items = [
                item
                for item in body["bundle"]["items"]
                if item["metadata"].get("files") == [artifact_path]
            ]
            assert len(matching_items) == 1
            first_context_id = matching_items[0]["id"]

    assert first_body is not None
    effect_id = first_body["effect"]["effect_id"]
    indexed_effects_cursor = await state.store.db.execute(
        "SELECT COUNT(DISTINCT effect_id) AS count FROM handoff_candidate_manifests"
    )
    indexed_effects = await indexed_effects_cursor.fetchone()
    assert indexed_effects is not None
    assert indexed_effects["count"] == 65
    initial = await state.store.handoff_assimilation_status(effect_id)
    assert initial["status"] == "awaiting_target_evidence"
    assert initial["typed_evidence_monitoring"] == {
        "available": True,
        "routing": "immutable_dispatch_candidate_index",
        "capacity_limited": False,
    }

    target_session = await state.store.get_session_for_authority(target.id)
    assert target_session is not None
    issued_at = utcnow() - timedelta(seconds=1)
    principal_record = await state.store.issue_mcp_principal(
        principal_id="mcp-indexed-capacity-target",
        session_id=target.id,
        goal_id=goal["id"],
        project_id="demo",
        vendor_session_id=target_session.vendor_session_id,
        harness_type=target_session.harness_type.value,
        scopes=["mcp:read", MCP_REPORT_PROGRESS_TOOL],
        token_digest=hashlib.sha256(b"indexed-capacity-secret").hexdigest(),
        issued_at=issued_at,
        expires_at=issued_at + timedelta(hours=1),
    )
    principal = MCPPrincipal(
        principal_id=principal_record["principal_id"],
        kind="session",
        scopes=frozenset(principal_record["scopes"]),
        session_id=target.id,
        goal_id=goal["id"],
        project_id="demo",
        project_binding=principal_record["project_binding"],
        vendor_session_id=target_session.vendor_session_id,
        harness_type=target_session.harness_type,
        issued_at=datetime.fromisoformat(principal_record["issued_at"]),
        expires_at=datetime.fromisoformat(principal_record["expires_at"]),
    )
    acknowledged = await state.pipeline.record_reported_progress(
        target_session,
        principal=principal,
        report=ProgressReport(
            idempotency_key="indexed-capacity-ack-0001",
            summary="I received the oldest indexed artifact contract.",
            evidence_refs=(
                ProgressEvidenceReference(type="context", id=first_context_id),
            ),
        ),
    )
    assert acknowledged["replayed"] is False
    after_ack = await state.store.handoff_assimilation_status(effect_id)
    assert after_ack["status"] == "target_acknowledged"

    relevant = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": target.id,
            "event_type": EventType.FILE_READ.value,
            "message": "Opened the oldest artifact after all 65 deliveries.",
            "file_paths": ["artifacts/indexed-000.json"],
        },
    )
    assert relevant.status_code == 200, relevant.text
    observed = await state.store.handoff_assimilation_status(effect_id)
    assert observed["status"] == "relevant_action_observed"
    assert {item["evidence_kind"] for item in observed["evidence"]} == {
        "artifact_read",
        "target_acknowledgement",
    }


@pytest.mark.asyncio
async def test_corrupt_newer_matching_index_fails_optional_evidence_closed(
    client: AsyncClient,
):
    target = state.adapters.synthetic.seed_session(vendor_id="indexed-corrupt-target")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Fail corrupt indexed evidence closed",
                "objective": (
                    "Use the newest validated contract at artifacts/corrupt-shared.json "
                    "without reassigning corrupt evidence"
                ),
            },
        )
    ).json()
    attached = await client.post(
        f"/v1/sessions/{target.id}/attach",
        json={"goal_id": goal["id"]},
    )
    assert attached.status_code == 200, attached.text
    bodies = [
        await _deliver_synthetic_artifact_handoff(
            client,
            target_session_id=target.id,
            goal_id=goal["id"],
            index=index,
            artifact_path="artifacts/corrupt-shared.json",
            key_prefix="indexed-corrupt",
        )
        for index in range(2)
    ]
    older_effect_id = bodies[0]["effect"]["effect_id"]
    newer_effect_id = bodies[1]["effect"]["effect_id"]

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        await state.store.db.execute(
            "DELETE FROM handoff_candidate_manifests WHERE effect_id = ?",
            (newer_effect_id,),
        )
    await state.store.db.rollback()
    artifact_cursor = await state.store.db.execute(
        "SELECT candidate_id, json FROM handoff_artifact_candidates WHERE effect_id = ?",
        (newer_effect_id,),
    )
    artifact_row = await artifact_cursor.fetchone()
    assert artifact_row is not None
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        await state.store.db.execute(
            "DELETE FROM handoff_artifact_candidates WHERE candidate_id = ?",
            (artifact_row["candidate_id"],),
        )
    await state.store.db.rollback()
    context_cursor = await state.store.db.execute(
        "SELECT candidate_id, json FROM handoff_context_candidates WHERE effect_id = ? LIMIT 1",
        (newer_effect_id,),
    )
    context_row = await context_cursor.fetchone()
    assert context_row is not None
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        await state.store.db.execute(
            "UPDATE handoff_context_candidates SET json = ? WHERE candidate_id = ?",
            (context_row["json"], context_row["candidate_id"]),
        )
    await state.store.db.rollback()
    forged = json.loads(artifact_row["json"])
    forged["bundle_digest"] = "0" * 64
    await state.store.db.execute("DROP TRIGGER trg_handoff_artifact_candidate_immutable")
    await state.store.db.execute(
        "UPDATE handoff_artifact_candidates SET json = ? WHERE candidate_id = ?",
        (json.dumps(forged), artifact_row["candidate_id"]),
    )
    await state.store.db.commit()

    relevant = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": target.id,
            "event_type": EventType.FILE_READ.value,
            "message": "This accepted event must survive optional index corruption.",
            "file_paths": ["artifacts/corrupt-shared.json"],
        },
    )
    assert relevant.status_code == 200, relevant.text
    assert relevant.json()["event"]["event_id"]
    older = await state.store.handoff_assimilation_status(older_effect_id)
    assert older["status"] == "awaiting_target_evidence"
    assert older["evidence"] == []
    with pytest.raises(RuntimeError, match="artifact candidate binding"):
        await state.store.handoff_assimilation_status(newer_effect_id)

    await state.store.db.execute("DROP TRIGGER trg_handoff_candidate_manifest_no_delete")
    await state.store.db.execute(
        "DELETE FROM handoff_candidate_manifests WHERE effect_id = ?",
        (older_effect_id,),
    )
    await state.store.db.commit()
    with pytest.raises(RuntimeError, match="candidate manifest is missing"):
        await state.store.handoff_assimilation_status(older_effect_id)


@pytest.mark.asyncio
async def test_v3_handoff_cannot_be_downgraded_to_a_v1_watermark(
    client: AsyncClient,
):
    target = state.adapters.synthetic.seed_session(vendor_id="indexed-legacy-target")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Preserve legacy monitoring truth",
                "objective": (
                    "Use the artifact at artifacts/legacy-index.json without inferring an "
                    "index for handoffs that predate it"
                ),
            },
        )
    ).json()
    attached = await client.post(
        f"/v1/sessions/{target.id}/attach",
        json={"goal_id": goal["id"]},
    )
    assert attached.status_code == 200, attached.text
    body = await _deliver_synthetic_artifact_handoff(
        client,
        target_session_id=target.id,
        goal_id=goal["id"],
        index=0,
        artifact_path="artifacts/legacy-index.json",
        key_prefix="indexed-legacy",
    )
    effect_id = body["effect"]["effect_id"]
    watermark_cursor = await state.store.db.execute(
        "SELECT json FROM handoff_dispatch_watermarks WHERE effect_id = ?",
        (effect_id,),
    )
    watermark_row = await watermark_cursor.fetchone()
    assert watermark_row is not None
    v2_watermark = json.loads(watermark_row["json"])
    v1_watermark = {
        key: value
        for key, value in v2_watermark.items()
        if key
        in {
            "effect_id",
            "target_session_id",
            "target_accept_seq_through",
            "dispatch_started_at",
            "effect_version",
        }
    }
    v1_watermark["schema"] = "pex.handoff-dispatch-watermark.v1"
    for trigger in (
        "trg_handoff_dispatch_watermark_immutable",
        "trg_handoff_artifact_candidate_no_delete",
        "trg_handoff_context_candidate_no_delete",
        "trg_handoff_candidate_manifest_no_delete",
    ):
        await state.store.db.execute(f"DROP TRIGGER {trigger}")
    await state.store.db.execute(
        "DELETE FROM handoff_artifact_candidates WHERE effect_id = ?",
        (effect_id,),
    )
    await state.store.db.execute(
        "DELETE FROM handoff_context_candidates WHERE effect_id = ?",
        (effect_id,),
    )
    await state.store.db.execute(
        "DELETE FROM handoff_candidate_manifests WHERE effect_id = ?",
        (effect_id,),
    )
    await state.store.db.execute(
        "UPDATE handoff_dispatch_watermarks SET json = ? WHERE effect_id = ?",
        (json.dumps(v1_watermark, separators=(",", ":")), effect_id),
    )
    await state.store.db.commit()

    with pytest.raises(RuntimeError, match="dispatch authority is missing"):
        await state.store.handoff_assimilation_status(effect_id)


@pytest.mark.asyncio
async def test_candidate_index_failure_rolls_dispatch_back_before_adapter_io(
    client: AsyncClient,
    monkeypatch,
):
    source = (await client.post("/v1/synthetic/sessions")).json()
    target = state.adapters.synthetic.seed_session(vendor_id="index-failure-target")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Keep dispatch atomic with monitoring authority",
                "objective": "Use the contract at artifacts/index-failure.json",
            },
        )
    ).json()
    for session_id in (source["id"], target.id):
        attached = await client.post(
            f"/v1/sessions/{session_id}/attach",
            json={"goal_id": goal["id"]},
        )
        assert attached.status_code == 200, attached.text
    discovered = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source["id"],
            "event_type": EventType.FILE_READ.value,
            "message": "Validated contract is at artifacts/index-failure.json.",
            "file_paths": ["artifacts/index-failure.json"],
        },
    )
    assert discovered.status_code == 200, discovered.text
    failed_insert = AsyncMock(side_effect=RuntimeError("forced candidate index failure"))
    monkeypatch.setattr(
        state.store,
        "_insert_handoff_monitor_candidates",
        failed_insert,
    )

    with pytest.raises(RuntimeError, match="forced candidate index failure"):
        await client.post(
            f"/v1/sessions/{source['id']}/handoff",
            json={
                "idempotency_key": "candidate-index-failure-0001",
                "target_session_id": target.id,
                "token_budget": 2_000,
            },
        )
    assert failed_insert.await_count == 1
    effect_cursor = await state.store.db.execute(
        "SELECT effect_id, state FROM operator_effects WHERE idempotency_key = ?",
        ("candidate-index-failure-0001",),
    )
    effect = await effect_cursor.fetchone()
    assert effect is not None
    assert effect["state"] == "reserved"
    for table in (
        "handoff_dispatch_watermarks",
        "handoff_candidate_manifests",
        "handoff_context_candidates",
        "handoff_artifact_candidates",
    ):
        cursor = await state.store.db.execute(
            f"SELECT COUNT(*) AS count FROM {table} WHERE effect_id = ?",
            (effect["effect_id"],),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["count"] == 0
    assert state.adapters.synthetic.inbox[target.id] == []


@pytest.mark.asyncio
async def test_absolute_windows_path_requires_completed_in_root_action(
    client: AsyncClient,
):
    project_root = "C:/work/pex"
    source = state.adapters.synthetic.seed_session(
        vendor_id="absolute-path-source",
        project_id=project_root,
        cwd=project_root,
    )
    target = state.adapters.synthetic.seed_session(
        vendor_id="absolute-path-target",
        project_id=project_root,
        cwd=project_root,
    )
    await state.store.upsert_session(source)
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": project_root,
                "title": "Use the transferred Windows artifact",
                "objective": "Read the exact prepared dataset after handoff",
            },
        )
    ).json()
    for session in (source, target):
        attached = await client.post(
            f"/v1/sessions/{session.id}/attach",
            json={"goal_id": goal["id"]},
        )
        assert attached.status_code == 200

    discovered = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source.id,
            "event_type": EventType.FILE_READ.value,
            "message": "Prepared dataset is ready.",
            "file_paths": [r"C:\WORK\PEX\artifacts\Prepared.parquet"],
            "phase": EventPhase.AFTER.value,
        },
    )
    assert discovered.status_code == 200
    handoff = await client.post(
        f"/v1/sessions/{source.id}/handoff",
        json={
            "idempotency_key": "rest-handoff-absolute-path-0001",
            "target_session_id": target.id,
            "token_budget": 2_000,
        },
    )
    assert handoff.status_code == 200, handoff.text
    effect_id = handoff.json()["effect"]["effect_id"]

    before = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": target.id,
            "event_type": EventType.FILE_READ.value,
            "message": "Permission-time read attempt only.",
            "file_paths": [r"c:\work\pex\ARTIFACTS\prepared.parquet"],
            "phase": EventPhase.BEFORE.value,
        },
    )
    assert before.status_code == 200
    assert (
        await state.store.handoff_assimilation_status(effect_id)
    )["status"] == "awaiting_target_evidence"

    outside = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": target.id,
            "event_type": EventType.FILE_READ.value,
            "message": "Different file outside the frozen project root.",
            "file_paths": [r"C:\work\other\artifacts\prepared.parquet"],
            "phase": EventPhase.AFTER.value,
        },
    )
    assert outside.status_code == 200
    assert (
        await state.store.handoff_assimilation_status(effect_id)
    )["status"] == "awaiting_target_evidence"

    completed = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": target.id,
            "event_type": EventType.FILE_READ.value,
            "message": "Completed the exact in-root read.",
            "file_paths": [r"c:\work\pex\ARTIFACTS\prepared.parquet"],
            "phase": EventPhase.AFTER.value,
        },
    )
    assert completed.status_code == 200
    assimilation = await state.store.handoff_assimilation_status(effect_id)
    assert assimilation["status"] == "relevant_action_observed"
    assert assimilation["first_relevant_action"]["matched_artifact_paths"] == [
        "artifacts/Prepared.parquet"
    ]


@pytest.mark.parametrize(
    ("project_root", "source_path", "false_alias", "exact_match"),
    [
        (
            "C:/work/pex",
            r"C:\work\pex\artifacts\Straße.json",
            r"C:\WORK\PEX\ARTIFACTS\STRASSE.json",
            r"c:\work\pex\artifacts\straße.json",
        ),
        (
            "/work/pex",
            r"artifacts\contract.json",
            "artifacts/contract.json",
            r"artifacts\contract.json",
        ),
    ],
)
@pytest.mark.asyncio
async def test_artifact_path_matching_does_not_expand_unicode_or_posix_separators(
    client: AsyncClient,
    project_root: str,
    source_path: str,
    false_alias: str,
    exact_match: str,
):
    source = state.adapters.synthetic.seed_session(
        vendor_id=f"path-semantics-source-{hashlib.sha256(project_root.encode()).hexdigest()[:8]}",
        project_id=project_root,
        cwd=project_root,
    )
    target = state.adapters.synthetic.seed_session(
        vendor_id=f"path-semantics-target-{hashlib.sha256(project_root.encode()).hexdigest()[:8]}",
        project_id=project_root,
        cwd=project_root,
    )
    await state.store.upsert_session(source)
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": project_root,
                "title": "Preserve exact artifact path semantics",
                "objective": f"Use the exact validated artifact {source_path}",
            },
        )
    ).json()
    for session in (source, target):
        attached = await client.post(
            f"/v1/sessions/{session.id}/attach",
            json={"goal_id": goal["id"]},
        )
        assert attached.status_code == 200, attached.text
    discovered = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source.id,
            "event_type": EventType.FILE_READ.value,
            "message": f"Validated artifact is at {source_path}.",
            "file_paths": [source_path],
            "phase": EventPhase.AFTER.value,
        },
    )
    assert discovered.status_code == 200, discovered.text
    handoff = await client.post(
        f"/v1/sessions/{source.id}/handoff",
        json={
            "idempotency_key": (
                "path-semantics-handoff-"
                + hashlib.sha256(project_root.encode()).hexdigest()[:12]
            ),
            "target_session_id": target.id,
            "token_budget": 2_000,
        },
    )
    assert handoff.status_code == 200, handoff.text
    effect_id = handoff.json()["effect"]["effect_id"]

    alias_event = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": target.id,
            "event_type": EventType.FILE_READ.value,
            "message": "Opened a spelling that must remain distinct.",
            "file_paths": [false_alias],
            "phase": EventPhase.AFTER.value,
        },
    )
    assert alias_event.status_code == 200, alias_event.text
    assert (
        await state.store.handoff_assimilation_status(effect_id)
    )["status"] == "awaiting_target_evidence"

    exact_event = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": target.id,
            "event_type": EventType.FILE_READ.value,
            "message": "Opened the exact platform-semantic artifact.",
            "file_paths": [exact_match],
            "phase": EventPhase.AFTER.value,
        },
    )
    assert exact_event.status_code == 200, exact_event.text
    assert (
        await state.store.handoff_assimilation_status(effect_id)
    )["status"] == "relevant_action_observed"


@pytest.mark.asyncio
async def test_context_handoff_rejects_self_target_before_delivery(client: AsyncClient):
    source = (await client.post("/v1/synthetic/sessions")).json()
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Bounded handoff",
                "objective": "Never deliver a handoff back into its source session",
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{source['id']}/attach", json={"goal_id": goal["id"]})

    response = await client.post(
        f"/v1/sessions/{source['id']}/handoff",
        json={
            "idempotency_key": "rest-handoff-self-0001",
            "target_session_id": source["id"],
        },
    )

    assert response.status_code == 409
    assert state.adapters.synthetic.inbox[source["id"]] == []


@pytest.mark.asyncio
async def test_handoff_rejects_observe_only_desktop_tiles(client: AsyncClient):
    from pex_protocol.enums import HarnessType, SessionStatus
    from pex_protocol.session import HarnessSession

    source = (await client.post("/v1/synthetic/sessions")).json()
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Share path",
                "objective": "Share an observed artifact path with the sibling worker",
                "acceptance_criteria": ["the target uses the discovered dataset path"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{source['id']}/attach", json={"goal_id": goal["id"]})
    desktop = HarnessSession(
        id="cursor:desktop",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="desktop",
        status=SessionStatus.WORKING,
        project_id="demo",
        cwd="demo",
        goal_id=goal["id"],
        metadata={"source": "desktop"},
        capabilities={"inject_context": True, "send_message": True},
    )
    await state.store.upsert_session(desktop, allow_goal_change=True)
    denied = await client.post(
        f"/v1/sessions/{source['id']}/handoff",
        json={
            "idempotency_key": "rest-handoff-observe-0001",
            "target_session_id": "cursor:desktop",
        },
    )
    assert denied.status_code == 409
    assert "observe" in denied.json()["detail"]["message"].lower()
    assert state.adapters.synthetic.inbox[source["id"]] == []
    assert state.adapters.cursor.inbox.get("cursor:desktop", []) == []


@pytest.mark.asyncio
async def test_auto_handoff_skips_observe_only_desktop_tiles(client: AsyncClient):
    from pex_protocol.enums import HarnessType, SessionStatus
    from pex_protocol.session import HarnessSession

    source = (await client.post("/v1/synthetic/sessions")).json()
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Share path",
                "objective": "Share the dataset path discovered by one worker",
                "acceptance_criteria": ["the sibling uses the discovered dataset path"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{source['id']}/attach", json={"goal_id": goal["id"]})
    desktop = HarnessSession(
        id="codex:desktop",
        harness_type=HarnessType.CODEX,
        vendor_session_id="desktop",
        status=SessionStatus.WORKING,
        project_id="demo",
        cwd="demo",
        goal_id=goal["id"],
        metadata={"source": "desktop"},
        capabilities={"inject_context": True, "send_message": True},
    )
    await state.store.upsert_session(desktop, allow_goal_change=True)
    event = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source["id"],
            "event_type": EventType.AGENT_RESPONSE.value,
            "message": (
                "Verified artifact path: artifacts/prepared_dataset.parquet. "
                "Do not regenerate it."
            ),
        },
    )
    assert event.status_code == 200
    rows = await client.get("/v1/interventions", params={"session_id": "codex:desktop"})
    assert rows.json() == []
    assert state.adapters.codex.inbox.get("codex:desktop", []) == []


@pytest.mark.asyncio
async def test_auto_handoff_from_cursor_conversation_reaches_isolated_codex_not_desktop(
    client: AsyncClient,
):
    from pex_bridge.adapters.codex import CodexAppServerTransport
    from pex_protocol.enums import HarnessType, SessionStatus
    from pex_protocol.session import HarnessSession

    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_handoff", "cwd": "C:/proj"}]
    state.adapters.codex.attach_transport(transport)
    await transport.ensure_ready()
    isolated = HarnessSession(
        id="codex:thr_handoff",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thr_handoff",
        cwd="C:/proj",
        project_id="C:/proj",
        status=SessionStatus.WORKING,
        metadata={"isolated": True, "source": "pexbench"},
    )
    state.adapters.codex.sessions[isolated.id] = isolated
    await state.store.upsert_session(isolated)
    desktop = HarnessSession(
        id="codex:desktop",
        harness_type=HarnessType.CODEX,
        vendor_session_id="desktop",
        cwd="C:/proj",
        project_id="C:/proj",
        status=SessionStatus.WORKING,
        metadata={"source": "desktop", "process": "ChatGPT.exe"},
        capabilities={"inject_context": True, "send_message": True},
    )
    await state.store.upsert_session(desktop)
    started = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "sessionStart",
            "conversation_id": "conv-handoff",
            "workspace_roots": ["C:/proj"],
        },
    )
    assert started.status_code == 200
    cursor_row = (await client.get("/v1/sessions/cursor:conv-handoff")).json()
    project_id = cursor_row["project_id"] or cursor_row["cwd"]
    assert project_id
    isolated.cwd = project_id
    isolated.project_id = project_id
    state.adapters.codex.sessions[isolated.id] = isolated
    await state.store.upsert_session(isolated)
    desktop.cwd = project_id
    desktop.project_id = project_id
    await state.store.upsert_session(desktop)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": project_id,
                "title": "Share path",
                "objective": "Share the dataset path Cursor discovered with Codex",
                "acceptance_criteria": [
                    "the isolated Codex thread uses the discovered dataset path"
                ],
            },
        )
    ).json()
    attached_cursor = await client.post(
        "/v1/sessions/cursor:conv-handoff/attach",
        json={"goal_id": goal["id"]},
    )
    attached_codex = await client.post(
        "/v1/sessions/codex:thr_handoff/attach",
        json={"goal_id": goal["id"]},
    )
    assert attached_cursor.status_code == 200
    assert attached_codex.status_code == 200
    await state.store.upsert_session(
        desktop.model_copy(update={"goal_id": goal["id"]}),
        allow_goal_change=True,
    )
    observed = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "afterAgentResponse",
            "conversation_id": "conv-handoff",
            "workspace_roots": ["C:/proj"],
            "text": (
                "Verified artifact path: artifacts/prepared_dataset.parquet. "
                "Do not regenerate it."
            ),
            "observed_ns": 1,
        },
    )
    assert observed.status_code == 200
    inbox = state.adapters.codex.inbox.get("codex:thr_handoff", [])
    assert inbox
    assert "prepared_dataset" in inbox[-1].lower()
    assert transport.turns
    assert transport.turns[-1]["threadId"] == "thr_handoff"
    assert all(turn.get("threadId") != "desktop" for turn in transport.turns)
    assert state.adapters.codex.inbox.get("codex:desktop", []) == []
    denied = await client.post(
        "/v1/sessions/codex:desktop/attach",
        json={"goal_id": goal["id"]},
    )
    assert denied.status_code == 409


@pytest.mark.asyncio
async def test_auto_handoff_from_isolated_codex_reaches_cursor_conversation_not_desktop(
    client: AsyncClient,
):
    from datetime import UTC, datetime

    from pex_bridge.adapters.codex import CodexAppServerTransport
    from pex_bridge.store import new_id
    from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
    from pex_protocol.session import HarnessEvent, HarnessSession

    class RecordingAcp:
        ready = True

        def __init__(self) -> None:
            self.prompts: list[tuple] = []

        async def handshake(self) -> dict:
            return {}

        async def list_sessions(self) -> list:
            return []

        async def activate(self, session_id: str, _cwd: str) -> None:
            self.prompts.append(("activate", session_id))

        async def prompt(self, session_id: str, text: str) -> None:
            self.prompts.append(("prompt", session_id, text))

    acp = RecordingAcp()
    state.adapters.cursor.acp = acp
    started = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "sessionStart",
            "conversation_id": "conv-back",
            "workspace_roots": ["C:/proj"],
        },
    )
    assert started.status_code == 200
    cursor_row = (await client.get("/v1/sessions/cursor:conv-back")).json()
    project_id = cursor_row["project_id"] or cursor_row["cwd"]
    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_back", "cwd": project_id}]
    state.adapters.codex.attach_transport(transport)
    await transport.ensure_ready()
    isolated = HarnessSession(
        id="codex:thr_back",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thr_back",
        cwd=project_id,
        project_id=project_id,
        status=SessionStatus.WORKING,
        metadata={"isolated": True, "source": "pexbench"},
    )
    state.adapters.codex.sessions[isolated.id] = isolated
    await state.store.upsert_session(isolated)
    await state.store.upsert_session(
        HarnessSession(
            id="cursor:desktop",
            harness_type=HarnessType.CURSOR,
            vendor_session_id="desktop",
            cwd=project_id,
            project_id=project_id,
            status=SessionStatus.WORKING,
            metadata={"source": "desktop", "process": "Cursor.exe"},
            capabilities={"inject_context": True, "send_message": True},
        )
    )
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": project_id,
                "title": "Share path",
                "objective": "Share the dataset path Codex discovered with Cursor",
                "acceptance_criteria": [
                    "the Cursor conversation uses the discovered dataset path"
                ],
            },
        )
    ).json()
    assert (
        await client.post(
            "/v1/sessions/cursor:conv-back/attach",
            json={"goal_id": goal["id"]},
        )
    ).status_code == 200
    assert (
        await client.post(
            "/v1/sessions/codex:thr_back/attach",
            json={"goal_id": goal["id"]},
        )
    ).status_code == 200
    desktop = await state.store.get_session("cursor:desktop")
    assert desktop is not None
    await state.store.upsert_session(
        desktop.model_copy(update={"goal_id": goal["id"]}),
        allow_goal_change=True,
    )
    source = await state.store.get_session("codex:thr_back")
    assert source is not None
    await state.pipeline.ingest_event(
        HarnessEvent(
            event_id=new_id("evt_"),
            ts=datetime.now(UTC),
            harness_type=HarnessType.CODEX,
            session_id=source.id,
            project_id=project_id,
            event_type=EventType.AGENT_RESPONSE,
            phase=EventPhase.AFTER,
            message_delta=(
                "Verified artifact path: artifacts/prepared_dataset.parquet. "
                "Do not regenerate it."
            ),
        ),
        source,
    )
    prompts = [item for item in acp.prompts if item[0] == "prompt"]
    assert prompts
    assert prompts[-1][1] == "conv-back"
    assert "prepared_dataset" in str(prompts[-1][2]).lower()
    assert all(item[1] != "desktop" for item in prompts if len(item) > 1)
    assert state.adapters.cursor.inbox.get("cursor:desktop", []) == []
    assert (
        await client.post(
            "/v1/sessions/cursor:desktop/attach",
            json={"goal_id": goal["id"]},
        )
    ).status_code == 409


@pytest.mark.asyncio
async def test_auto_handoff_injects_without_explicit_post(
    client: AsyncClient,
    monkeypatch,
):
    source = (await client.post("/v1/synthetic/sessions")).json()
    source_adapter = state.adapters.synthetic
    original_inject_context = source_adapter.inject_context

    async def inject_with_lock_assertion(session, bundle):
        assert not state.pipeline._handoff_mutation_lock.locked()
        return await original_inject_context(session, bundle)

    monkeypatch.setattr(source_adapter, "inject_context", inject_with_lock_assertion)
    target = source_adapter.seed_session(vendor_id="synth-auto")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Share path",
                "objective": "Share the dataset path discovered by Codex with Cursor",
                "acceptance_criteria": ["the target uses the discovered dataset path"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{source['id']}/attach", json={"goal_id": goal["id"]})
    await client.post(f"/v1/sessions/{target.id}/attach", json={"goal_id": goal["id"]})
    event = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source["id"],
            "event_type": EventType.AGENT_RESPONSE.value,
            "message": (
                "Verified artifact path: artifacts/prepared_dataset.parquet. "
                "Do not regenerate it."
            ),
        },
    )
    assert event.status_code == 200
    event_id = event.json()["event"]["event_id"]
    inbox = source_adapter.inbox[target.id]
    assert inbox
    assert "prepared_dataset" in inbox[-1].lower()
    attached = await client.get(f"/v1/sessions/{target.id}")
    assert attached.json()["goal_id"] == goal["id"]
    effect_cursor = await state.store.db.execute(
        "SELECT * FROM operator_effects WHERE action_kind = 'context_handoff'"
    )
    effect_rows = await effect_cursor.fetchall()
    assert len(effect_rows) == 1
    effect = dict(effect_rows[0])
    effect_payload = json.loads(effect["payload_json"])
    assert effect["principal_id"] == "system_auto_handoff"
    assert effect["state"] == "delivered"
    assert effect_payload["event_id"] == event_id
    assert effect_payload["trigger_event_mode"] == "existing"
    handoff = await state.store.get_intervention(effect_payload["intervention_id"])
    assert handoff is not None
    assert handoff.trigger == EventType.AGENT_RESPONSE.value
    assert handoff.metadata["trigger_event_id"] == event_id
    assert handoff.metadata["origin_event_id"] == event_id
    audit_cursor = await state.store.db.execute(
        "SELECT record_type FROM intervention_audit WHERE intervention_id = ? "
        "ORDER BY id",
        (handoff.id,),
    )
    assert [row["record_type"] for row in await audit_cursor.fetchall()] == [
        "handoff_delivery_reserved",
        "handoff_delivery_dispatching",
        "handoff_delivery_delivered",
    ]
    event_cursor = await state.store.db.execute(
        "SELECT COUNT(*) AS count FROM events WHERE event_id = ?",
        (event_id,),
    )
    assert (await event_cursor.fetchone())["count"] == 1
    followup_cursor = await state.store.db.execute(
        "SELECT state FROM event_followups WHERE event_id = ? AND kind = 'auto_handoff'",
        (event_id,),
    )
    assert (await followup_cursor.fetchone())["state"] == "complete"

    repeated = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source["id"],
            "event_type": EventType.AGENT_RESPONSE.value,
            "message": (
                "Verified artifact path: artifacts/prepared_dataset.parquet. "
                "Do not regenerate it."
            ),
        },
    )
    assert repeated.status_code == 200
    assert len(source_adapter.inbox[target.id]) == 1
    effect_cursor = await state.store.db.execute(
        "SELECT COUNT(*) AS count FROM operator_effects "
        "WHERE action_kind = 'context_handoff'"
    )
    assert (await effect_cursor.fetchone())["count"] == 1


@pytest.mark.asyncio
async def test_auto_handoff_ignores_generic_status_chatter(client: AsyncClient):
    source = (await client.post("/v1/synthetic/sessions")).json()
    adapter = state.adapters.synthetic
    target = adapter.seed_session(vendor_id="synth-generic")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Parser",
                "objective": "Implement the parser and its tests",
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{source['id']}/attach", json={"goal_id": goal["id"]})
    await client.post(f"/v1/sessions/{target.id}/attach", json={"goal_id": goal["id"]})

    event = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source["id"],
            "event_type": EventType.AGENT_RESPONSE.value,
            "message": "I am continuing to work through the parser implementation now.",
        },
    )
    assert event.status_code == 200
    assert adapter.inbox[target.id] == []


@pytest.mark.asyncio
async def test_auto_handoff_uses_target_prompt_to_exclude_other_goal_phase_context(
    client: AsyncClient,
):
    source = (await client.post("/v1/synthetic/sessions")).json()
    adapter = state.adapters.synthetic
    target = adapter.seed_session(vendor_id="synth-target-routing")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Release surfaces",
                "objective": "Finish the frontend pet atlas and backend database migration",
                "acceptance_criteria": [
                    "frontend pet atlas is ready",
                    "backend database migration is ready",
                ],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{source['id']}/attach", json={"goal_id": goal["id"]})
    await client.post(f"/v1/sessions/{target.id}/attach", json={"goal_id": goal["id"]})
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": target.id,
            "event_type": EventType.USER_PROMPT.value,
            "message": "Work only on the frontend pet sprites atlas.",
        },
    )

    backend = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source["id"],
            "event_type": EventType.AGENT_RESPONSE.value,
            "message": "Verified backend database migration artifact is ready.",
        },
    )
    assert backend.status_code == 200
    assert adapter.inbox[target.id] == []

    frontend = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source["id"],
            "event_type": EventType.AGENT_RESPONSE.value,
            "message": "Verified frontend pet sprites atlas artifact is ready.",
        },
    )
    assert frontend.status_code == 200
    assert len(adapter.inbox[target.id]) == 1
    delivered = adapter.inbox[target.id][0].lower()
    assert "frontend pet sprites atlas" in delivered
    stored = await client.get(
        "/v1/interventions",
        params={"session_id": target.id, "include_handoff_bundle": True},
    )
    handoff = next(
        item for item in stored.json() if item["action_taken"] == "FRESH_HANDOFF"
    )
    bundled_items = handoff["proposed_action"]["payload"]["bundle"]["items"]
    assert [item["content"] for item in bundled_items] == [
        "Verified frontend pet sprites atlas artifact is ready."
    ]


@pytest.mark.asyncio
async def test_auto_handoff_promotes_only_supported_test_result(client: AsyncClient):
    adapter = state.adapters.synthetic
    source = adapter.seed_session(vendor_id="verified-source")
    target = adapter.seed_session(vendor_id="verified-target")
    await state.store.upsert_session(source)
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Parser tests",
                "objective": "Implement the parser with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{source.id}/attach", json={"goal_id": goal["id"]})
    await client.post(f"/v1/sessions/{target.id}/attach", json={"goal_id": goal["id"]})
    saved_target = await state.store.get_session(target.id)
    assert saved_target is not None
    assert saved_target.status.value == "working"
    observed = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {"pytest": {"ok": True, "exit_code": 0, "passed": 4}},
        },
    )
    assert observed.status_code == 200
    stopped = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source.id,
            "event_type": EventType.STOP.value,
            "message": "All parser tests passed. I am done.",
        },
    )
    assert stopped.status_code == 200
    assert stopped.json()["intervention"]["metadata"]["verification"]["status"] == "supported"
    assert len(adapter.inbox[target.id]) == 1
    prompt = adapter.inbox[target.id][0]
    assert "Direct evidence:" in prompt
    assert "pytest_ok=true" in prompt
    assert "[result; test; confidence=0.95" in prompt

    context = await client.get("/v1/context", params={"project_id": "demo"})
    verified = [item for item in context.json() if item["kind"] == "result"]
    assert len(verified) == 1
    assert verified[0]["metadata"]["verified"] is True


@pytest.mark.asyncio
async def test_context_listing_is_paginated_and_bounded(client: AsyncClient):
    now = datetime.now(UTC)
    for index in range(3):
        await state.store.add_context(
            ContextItem(
                id=f"context-page-{index}",
                project_id="pagination-project",
                kind=ContextKind.FACT,
                content=f"fact {index}",
                valid_from=now + timedelta(seconds=index),
            )
        )

    first = await client.get(
        "/v1/context",
        params={"project_id": "pagination-project", "limit": 2},
    )
    second = await client.get(
        "/v1/context",
        params={"project_id": "pagination-project", "limit": 2, "offset": 2},
    )

    assert [item["id"] for item in first.json()] == ["context-page-2", "context-page-1"]
    assert [item["id"] for item in second.json()] == ["context-page-0"]
    assert (
        await client.get(
            "/v1/context",
            params={"project_id": "pagination-project", "limit": 1001},
        )
    ).status_code == 422


@pytest.mark.asyncio
async def test_auto_handoff_never_crosses_goal_boundary(client: AsyncClient):
    source = (await client.post("/v1/synthetic/sessions")).json()
    adapter = state.adapters.synthetic
    target = adapter.seed_session(vendor_id="synth-other-goal")
    await state.store.upsert_session(target)
    source_goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Dataset",
                "objective": "Share the discovered dataset path",
                "acceptance_criteria": ["use prepared_dataset.parquet"],
            },
        )
    ).json()
    other_goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Unrelated deploy",
                "objective": "Deploy another service",
            },
        )
    ).json()
    await client.post(
        f"/v1/sessions/{source['id']}/attach",
        json={"goal_id": source_goal["id"]},
    )
    await client.post(
        f"/v1/sessions/{target.id}/attach",
        json={"goal_id": other_goal["id"]},
    )
    event = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source["id"],
            "event_type": EventType.AGENT_RESPONSE.value,
            "message": (
                "Verified artifact path: artifacts/prepared_dataset.parquet. "
                "Do not regenerate it."
            ),
        },
    )
    assert event.status_code == 200
    assert adapter.inbox[target.id] == []


@pytest.mark.asyncio
async def test_goal_persists_non_goals(client: AsyncClient):
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Keep loader",
                "objective": "Finish eval without rewriting the loader",
                "acceptance_criteria": ["results.json exists"],
                "constraints": ["Do not alter dataset preprocessing."],
                "non_goals": ["Do not rewrite the dataset loader."],
            },
        )
    ).json()
    assert goal["non_goals"] == ["Do not rewrite the dataset loader."]
    fetched = await client.get(f"/v1/goals/{goal['id']}")
    assert fetched.json()["non_goals"] == ["Do not rewrite the dataset loader."]


@pytest.mark.asyncio
async def test_stop_stores_extracted_claims(client: AsyncClient):
    session = (await client.post("/v1/synthetic/sessions")).json()
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Parser",
                "objective": "Implement the parser with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session['id']}/attach", json={"goal_id": goal["id"]})
    stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session["id"],
            "event_type": EventType.STOP.value,
            "message": "Implemented the parser and tests pass.",
        },
    )
    body = stop.json()["intervention"]
    claims = (body.get("metadata") or {}).get("claims") or []
    kinds = {item["kind"] for item in claims}
    assert "tests_pass" in kinds
    assert "implemented" in kinds
    items = await client.get("/v1/context", params={"project_id": "demo"})
    kinds_stored = {item["kind"] for item in items.json()}
    assert "claim" in kinds_stored


@pytest.mark.asyncio
async def test_uncertain_stop_audits_evidence_gathering_before_silence(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "uncertain-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="uncertain-stop", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Explain design",
                "objective": "Write a clear explanation of the design tradeoffs",
                "acceptance_criteria": ["the explanation is clear and accurate"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})

    stopped = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "I am done.",
        },
    )

    intervention = stopped.json()["intervention"]
    verification = intervention["metadata"]["verification"]
    receipt = verification["evidence_gathering"]
    assert verification["status"] == "uncertain"
    assert intervention["action_taken"] == "NOOP"
    assert adapter.inbox[session.id] == []
    assert receipt == {
        "state": "inspected",
        "sources": ["recent_events", "workspace_snapshot"],
        "recent_events": "inspected",
        "workspace_snapshot": "inspected",
        "workspace_snapshot_reason": None,
        "claim_count": 1,
        "probe": None,
        "execution": None,
        "reason": "bounded_existing_evidence_only",
    }


@pytest.mark.asyncio
async def test_same_probe_id_with_altered_payload_is_rejected_before_adapter_io(
    client: AsyncClient, tmp_path, monkeypatch
):
    worker = tmp_path / "altered-probe-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="altered-probe", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Reject altered verifier probes",
                "objective": "Finish with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})

    altered_payload: dict = {}

    async def altered_decide(request, *, local_model):
        del local_model
        minted = deepcopy(
            request.scores.features["verification"]["evidence_gathering"]["probe"]
        )
        minted["timeout_seconds"] += 1
        altered_payload.update(minted)
        return SupervisorResult(
            action=ProposedAction(
                type=InterventionType.REQUEST_VERIFICATION,
                session_id=request.session.id,
                goal_id=request.goal.id,
                payload={
                    "probe": minted,
                    "text": "Run pytest for this altered probe.",
                },
                rationale="Attempt to reuse the bridge probe id with changed bounds.",
                evidence=[f"probe:{minted['id']}"],
                requires_capability="send_message",
            ),
            used_llm=True,
            diagnosis="model_altered_bridge_probe",
            inference_status="completed",
        )

    decide = AsyncMock(side_effect=altered_decide)
    monkeypatch.setattr(state.pipeline.supervisor, "decide", decide)
    stopped = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )

    assert stopped.status_code == 200
    intervention = stopped.json()["intervention"]
    bridge_probe = intervention["metadata"]["verification"]["evidence_gathering"]["probe"]
    assert altered_payload["id"] == bridge_probe["id"]
    assert altered_payload["timeout_seconds"] == bridge_probe["timeout_seconds"] + 1
    assert intervention["proposed_action"]["type"] == "NOOP"
    assert intervention["action_taken"] == "NOOP"
    assert intervention["result"] == "noop"
    assert intervention["diagnosis"] == "verification_probe_not_bridge_minted"
    assert "verification_probe_not_bridge_minted" in intervention["metadata"]["traces"]
    assert adapter.inbox[session.id] == []
    decide.assert_awaited_once()


@pytest.mark.asyncio
async def test_model_cannot_mint_request_verification_probe(
    client: AsyncClient, tmp_path, monkeypatch
):
    worker = tmp_path / "model-minted-probe-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="model-minted-probe", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Reject model-minted probes",
                "objective": "Write a concise design explanation",
                "acceptance_criteria": ["the explanation is clear"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})

    async def minting_decide(request, *, local_model):
        del local_model
        probe = {
            "id": "probe_model_minted",
            "kind": "pytest",
            "harness_type": request.session.harness_type.value,
            "session_id": request.session.id,
            "project_id": request.session.project_id,
            "goal_id": request.goal.id,
            "request_event_id": request.event.event_id,
            "cwd": request.session.cwd,
            "relative_targets": [],
            "timeout_seconds": 60,
            "output_limit_bytes": 16_384,
        }
        return SupervisorResult(
            action=ProposedAction(
                type=InterventionType.REQUEST_VERIFICATION,
                session_id=request.session.id,
                goal_id=request.goal.id,
                payload={"probe": probe, "text": "Run a model-minted pytest probe."},
                rationale="Attempt to mint a verifier probe without bridge authorization.",
                evidence=["model_minted_probe"],
                requires_capability="send_message",
            ),
            used_llm=True,
            diagnosis="model_minted_verification_probe",
            inference_status="completed",
        )

    decide = AsyncMock(side_effect=minting_decide)
    monkeypatch.setattr(state.pipeline.supervisor, "decide", decide)
    stopped = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "I am done.",
        },
    )

    assert stopped.status_code == 200
    intervention = stopped.json()["intervention"]
    receipt = intervention["metadata"]["verification"]["evidence_gathering"]
    assert receipt["probe"] is None
    assert intervention["proposed_action"]["type"] == "NOOP"
    assert intervention["action_taken"] == "NOOP"
    assert intervention["result"] == "noop"
    assert intervention["diagnosis"] == "verification_probe_not_bridge_minted"
    assert adapter.inbox[session.id] == []
    decide.assert_awaited_once()


@pytest.mark.asyncio
async def test_verification_delivery_exception_is_attempted_uncertain_and_not_retried(
    client: AsyncClient, tmp_path, monkeypatch
):
    worker = tmp_path / "uncertain-verification-delivery-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="uncertain-verification", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Do not duplicate uncertain verification delivery",
                "objective": "Finish with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})
    send = AsyncMock(side_effect=RuntimeError("transport failed after possible delivery"))
    monkeypatch.setattr(adapter, "send_message", send)

    first = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    second = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )

    assert first.status_code == 200
    first_intervention = first.json()["intervention"]
    first_receipt = first_intervention["metadata"]["verification"]["evidence_gathering"]
    assert first_intervention["action_taken"] == "REQUEST_VERIFICATION"
    assert first_intervention["result"] == "verification_delivery_uncertain"
    assert first_receipt["state"] == "attempted"
    assert first_receipt["execution"] is None
    assert first_receipt["reason"] == "verification_request_delivery_uncertain"

    assert second.status_code == 200
    second_intervention = second.json()["intervention"]
    second_receipt = second_intervention["metadata"]["verification"]["evidence_gathering"]
    assert second_intervention["action_taken"] == "NOOP"
    assert second_receipt["state"] == "attempted"
    assert second_receipt["execution"] is None
    send.assert_awaited_once()
    stored = (await client.get(
        "/v1/interventions", params={"session_id": session.id}
    )).json()
    original = next(item for item in stored if item["id"] == first_intervention["id"])
    assert original["result"] == "verification_delivery_uncertain"
    assert original["metadata"].get("outcome_final") is not True


@pytest.mark.asyncio
async def test_requested_pytest_receipt_requires_matching_execution_then_stop(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "verification-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="verification-worker", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Verified parser",
                "objective": "Implement the parser with passing tests",
                "acceptance_criteria": ["tests pass"],
                "evidence_requirements": ["pytest output"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})

    first_stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    request = first_stop.json()["intervention"]
    assert request["action_taken"] == "REQUEST_VERIFICATION"
    gathering = request["metadata"]["verification"]["evidence_gathering"]
    assert gathering["state"] == "attempted"
    assert gathering["probe"]["kind"] == "pytest"
    assert gathering["execution"] is None
    assert len(adapter.inbox[session.id]) == 1

    unrelated = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": 'python -c "print(123)"',
            "process_state": {"pytest": {"ok": True, "exit_code": 0}},
        },
    )
    assert unrelated.status_code == 200
    stored = (await client.get(
        "/v1/interventions", params={"session_id": session.id}
    )).json()
    request = next(item for item in stored if item["action_taken"] == "REQUEST_VERIFICATION")
    gathering = request["metadata"]["verification"]["evidence_gathering"]
    assert gathering["state"] == "attempted"
    assert gathering["execution"] is None
    assert request["metadata"].get("outcome_final") is not True

    spoofed_stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    spoofed_verification = spoofed_stop.json()["intervention"]["metadata"]["verification"]
    assert spoofed_verification["status"] == "uncertain"
    assert spoofed_verification["evidence_gathering"]["state"] == "attempted"
    assert len(adapter.inbox[session.id]) == 1

    observed = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "uv run pytest -q",
            "process_state": {
                "pytest": {
                    "ok": True,
                    "exit_code": 0,
                    "passed": 4,
                    "output": "4 passed in 0.12s",
                }
            },
        },
    )
    assert observed.status_code == 200
    observed_event_id = observed.json()["event"]["event_id"]
    stored = (await client.get(
        "/v1/interventions", params={"session_id": session.id}
    )).json()
    request = next(item for item in stored if item["action_taken"] == "REQUEST_VERIFICATION")
    gathering = request["metadata"]["verification"]["evidence_gathering"]
    assert gathering["state"] == "executed"
    execution = gathering["execution"]
    assert execution["source_event_id"] == observed_event_id
    assert execution["observed_at"]
    assert {
        key: value
        for key, value in execution.items()
        if key not in {"source_event_id", "observed_at"}
    } == {
        "backend": "harness",
        "policy_verdict": "allow",
        "argv": [],
        "observed_command": "uv run pytest -q",
        "cwd": str(worker),
        "process_started": True,
        "exit_code": 0,
        "timed_out": False,
        "result": "passed",
        "output": "4 passed in 0.12s",
        "failure_node": None,
        "error_type": None,
    }
    assert request["metadata"].get("outcome_final") is not True

    completed = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    completion = completed.json()["intervention"]
    assert completion["action_taken"] == "NOOP"
    assert completion["metadata"]["verification"]["status"] == "supported"
    assert (
        completion["metadata"]["verification"]["evidence_gathering"]["state"]
        == "executed"
    )
    assert len(adapter.inbox[session.id]) == 1
    stored = (await client.get(
        "/v1/interventions", params={"session_id": session.id}
    )).json()
    request = next(item for item in stored if item["action_taken"] == "REQUEST_VERIFICATION")
    assert request["outcome"] == "goal_evidence_supported"
    assert request["helped"] is True
    assert request["metadata"]["outcome_final"] is True


@pytest.mark.asyncio
async def test_requested_service_health_receipt_updates_after_matching_worker_event(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "health-verification-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="health-verification", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Local health",
                "objective": "Keep the local /health endpoint green",
                "acceptance_criteria": ["healthcheck is green"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})

    first_stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "I am done.",
        },
    )
    request = first_stop.json()["intervention"]
    assert request["action_taken"] == "REQUEST_VERIFICATION"
    gathering = request["metadata"]["verification"]["evidence_gathering"]
    assert gathering["probe"]["kind"] == "service_health"
    assert gathering["state"] == "attempted"
    assert gathering["execution"] is None
    assert len(adapter.inbox[session.id]) == 1

    observed = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "curl -sf http://127.0.0.1:7420/health",
            "process_state": {
                "service_health": {
                    "ok": True,
                    "exit_code": 0,
                    "output": "ok",
                }
            },
        },
    )
    assert observed.status_code == 200
    stored = (
        await client.get("/v1/interventions", params={"session_id": session.id})
    ).json()
    request = next(item for item in stored if item["action_taken"] == "REQUEST_VERIFICATION")
    gathering = request["metadata"]["verification"]["evidence_gathering"]
    assert gathering["state"] == "executed"
    assert gathering["execution"]["result"] == "passed"
    assert gathering["execution"]["observed_command"] == (
        "curl -sf http://127.0.0.1:7420/health"
    )
    assert request["outcome"] == "verification_passed_after_intervention"


@pytest.mark.asyncio
async def test_edit_after_executed_pytest_mints_a_successor_probe(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "stale-verification-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="stale-verification", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Stale test evidence",
                "objective": "Finish with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})
    first = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    first_request = first.json()["intervention"]
    first_probe = first_request["metadata"]["verification"]["evidence_gathering"]["probe"]
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {
                "pytest": {
                    "ok": True,
                    "exit_code": 0,
                    "passed": 4,
                    "output": "4 passed",
                }
            },
        },
    )
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.FILE_EDIT.value,
            "file_paths": ["src/parser.py"],
        },
    )
    stale_stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    successor = stale_stop.json()["intervention"]
    assert successor["action_taken"] == "REQUEST_VERIFICATION"
    successor_receipt = successor["metadata"]["verification"]["evidence_gathering"]
    assert successor_receipt["state"] == "attempted"
    assert successor_receipt["probe"]["id"] != first_probe["id"]
    assert len(adapter.inbox[session.id]) == 2
    stored = (await client.get(
        "/v1/interventions", params={"session_id": session.id}
    )).json()
    old = next(item for item in stored if item["id"] == first_request["id"])
    assert old["outcome"] == "verification_result_staled_by_later_progress"
    assert old["helped"] is None
    assert old["metadata"]["outcome_final"] is True


@pytest.mark.asyncio
async def test_later_pytest_supersedes_old_receipt_without_mixing_event_ids(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "superseded-verification-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="superseded-verification", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Superseded test evidence",
                "objective": "Finish with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})
    first = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    request = first.json()["intervention"]
    passed = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {
                "pytest": {"ok": True, "exit_code": 0, "output": "4 passed"}
            },
        },
    )
    passed_event_id = passed.json()["event"]["event_id"]
    failed_node = "tests/test_parser.py::test_nested_array"
    failed = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {
                "pytest": {
                    "ok": False,
                    "exit_code": 1,
                    "failed": failed_node,
                    "output": f"FAILED {failed_node}",
                }
            },
        },
    )
    failed_event_id = failed.json()["event"]["event_id"]
    stopped = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    current = stopped.json()["intervention"]
    verification = current["metadata"]["verification"]
    assert current["action_taken"] == "SEND_NUDGE"
    assert verification["status"] == "contradicted"
    assert verification["pytest_event_id"] == failed_event_id
    assert verification["evidence_gathering"]["state"] == "inspected"
    stored = (await client.get(
        "/v1/interventions", params={"session_id": session.id}
    )).json()
    original = next(item for item in stored if item["id"] == request["id"])
    old_execution = original["metadata"]["verification"]["evidence_gathering"][
        "execution"
    ]
    assert old_execution["source_event_id"] == passed_event_id
    assert old_execution["source_event_id"] != verification["pytest_event_id"]
    assert original["outcome"] == "verification_superseded_by_newer_pytest"
    assert original["helped"] is None
    assert original["metadata"]["outcome_final"] is True


@pytest.mark.asyncio
async def test_newer_nudge_turn_cannot_mutate_pending_verification_result(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "verification-and-nudge-worker"
    worker.mkdir()
    required = worker / "required.txt"
    required.write_text("ready\n", encoding="utf-8")
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="verification-and-nudge", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Verification survives a newer nudge",
                "objective": "Finish with passing tests and required.txt",
                "acceptance_criteria": ["tests pass", "required.txt exists"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})
    requested = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    request = requested.json()["intervention"]
    assert request["action_taken"] == "REQUEST_VERIFICATION"

    required.unlink()
    nudged = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    assert nudged.json()["intervention"]["action_taken"] == "SEND_NUDGE"
    required.write_text("ready\n", encoding="utf-8")

    wrong_turn_execution = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {
                "pytest": {"ok": True, "exit_code": 0, "output": "4 passed"}
            },
        },
    )
    wrong_turn_event_id = wrong_turn_execution.json()["event"]["event_id"]
    stored = (await client.get(
        "/v1/interventions", params={"session_id": session.id}
    )).json()
    original = next(item for item in stored if item["id"] == request["id"])
    receipt = original["metadata"]["verification"]["evidence_gathering"]
    assert receipt["state"] == "attempted"
    assert receipt["execution"] is None
    assert original["helped"] is None
    assert original["outcome"] == "post_delivery_activity_observed_causality_unavailable"
    assert wrong_turn_event_id in original["metadata"]["outcome_event_ids"]
    assert original["metadata"].get("causal_continuation_proven") is not True


@pytest.mark.asyncio
async def test_goal_or_workspace_rebind_cannot_satisfy_old_probe(
    client: AsyncClient, tmp_path
):
    first_workspace = tmp_path / "bound-workspace-a"
    second_workspace = tmp_path / "bound-workspace-b"
    first_workspace.mkdir()
    second_workspace.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="rebound-verification", cwd=str(first_workspace))
    await state.store.upsert_session(session)
    first_goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Original test goal",
                "objective": "Finish the original task with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(
        f"/v1/sessions/{session.id}/attach",
        json={"goal_id": first_goal["id"]},
    )
    requested = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    request = requested.json()["intervention"]
    second_goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Replacement test goal",
                "objective": "Finish a different task with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    replaced = await client.post(
        f"/v1/sessions/{session.id}/attach",
        json={
            "goal_id": second_goal["id"],
            "expected_goal_id": first_goal["id"],
            "replace_existing": True,
        },
    )
    assert replaced.status_code == 200
    live = await state.store.get_session(session.id)
    assert live is not None
    live.cwd = str(second_workspace)
    await state.store.upsert_session(live)
    adapter.sessions[session.id].goal_id = second_goal["id"]
    adapter.sessions[session.id].cwd = str(second_workspace)

    observed = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {
                "pytest": {"ok": True, "exit_code": 0, "output": "4 passed"}
            },
        },
    )
    assert observed.status_code == 200
    stored = (await client.get(
        "/v1/interventions", params={"session_id": session.id}
    )).json()
    original = next(item for item in stored if item["id"] == request["id"])
    receipt = original["metadata"]["verification"]["evidence_gathering"]
    assert receipt["state"] == "attempted"
    assert receipt["execution"] is None


@pytest.mark.asyncio
async def test_pending_verification_stop_does_not_repeat_or_finalize(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "pending-verification-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="pending-verification", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Pending tests",
                "objective": "Finish with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})

    for _ in range(2):
        stopped = await client.post(
            "/v1/synthetic/events",
            json={
                "session_id": session.id,
                "event_type": EventType.STOP.value,
                "message": "All tests passed. I am done.",
            },
        )
        assert stopped.status_code == 200
    assert len(adapter.inbox[session.id]) == 1
    stored = (await client.get(
        "/v1/interventions", params={"session_id": session.id}
    )).json()
    request = next(item for item in stored if item["action_taken"] == "REQUEST_VERIFICATION")
    assert request["outcome"] == "worker_stopped_outcome_uncertain"
    assert request["helped"] is None
    assert request["metadata"].get("outcome_final") is not True
    latest = stored[0]
    assert latest["action_taken"] == "NOOP"
    assert latest["metadata"]["verification"]["evidence_gathering"]["state"] == "attempted"


@pytest.mark.asyncio
async def test_matching_failed_pytest_is_executed_and_drives_exact_nudge(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "failed-verification-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="failed-verification", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Failing tests",
                "objective": "Finish with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    failed_node = "tests/test_parser.py::test_nested_array"
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {
                "pytest": {
                    "ok": False,
                    "exit_code": 1,
                    "failed": failed_node,
                    "output": f"FAILED {failed_node}",
                }
            },
        },
    )
    stopped = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    nudge = stopped.json()["intervention"]
    assert nudge["action_taken"] == "SEND_NUDGE"
    assert failed_node in adapter.inbox[session.id][-1]
    gathering = nudge["metadata"]["verification"]["evidence_gathering"]
    assert gathering["state"] == "executed"
    assert gathering["execution"]["result"] == "failed"
    assert gathering["execution"]["failure_node"] == failed_node
    stored = (await client.get(
        "/v1/interventions", params={"session_id": session.id}
    )).json()
    request = next(item for item in stored if item["action_taken"] == "REQUEST_VERIFICATION")
    assert request["outcome"] == "verification_revealed_unsatisfied_goal"
    assert request["helped"] is True
    assert request["metadata"]["evidence_collection_succeeded"] is True
    assert request["metadata"]["goal_satisfied"] is False
    assert request["metadata"]["outcome_final"] is True


@pytest.mark.asyncio
async def test_verification_request_without_send_capability_is_unavailable(
    client: AsyncClient, tmp_path, monkeypatch
):
    worker = tmp_path / "observe-only-verification-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    monkeypatch.setattr(
        adapter,
        "probe",
        AsyncMock(
            return_value=AdapterCapabilities(
                observe_messages=True,
                observe_shell=True,
                observe_session_status=True,
                notes="observe-only test adapter",
            )
        ),
    )
    session = adapter.seed_session(vendor_id="observe-only-verification", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Observe-only tests",
                "objective": "Finish with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})
    stopped = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    intervention = stopped.json()["intervention"]
    assert intervention["proposed_action"]["type"] == "REQUEST_VERIFICATION"
    assert intervention["action_taken"] == "NOOP"
    assert intervention["policy_verdict"] == "deny"
    assert intervention["result"] == "denied_by_policy"
    receipt = intervention["metadata"]["verification"]["evidence_gathering"]
    assert receipt["state"] == "unavailable"
    assert receipt["probe"]["kind"] == "pytest"
    assert receipt["execution"] is None
    assert receipt["reason"] == "verification_unavailable:denied_by_policy"
    assert adapter.inbox[session.id] == []


@pytest.mark.asyncio
async def test_false_test_claim_nudges_with_failing_pytest(client: AsyncClient, tmp_path):
    worker = tmp_path / "worker"
    worker.mkdir()
    (worker / "src").mkdir()
    (worker / "src" / "parser.py").write_text("def parse():\n    return 1\n", encoding="utf-8")
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="false-claim", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Parser",
                "objective": "Implement the parser with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "file_paths": ["src/parser.py"],
            "process_state": {
                "pytest": {
                    "ok": False,
                    "exit_code": 1,
                    "failed": "tests/test_parser.py::test_nested_array",
                }
            },
        },
    )
    stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    body = stop.json()
    assert body["intervention"]["action_taken"] == "SEND_NUDGE"
    text = adapter.inbox[session.id][-1]
    assert "test_nested_array" in text
    assert not text.startswith("PEX:")
    verification = (body["intervention"].get("metadata") or {}).get("verification", {})
    assert verification.get("status") == "contradicted"

    transient_error = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.ERROR.value,
            "message": "A transient parser error occurred while retrying.",
        },
    )
    assert transient_error.status_code == 200
    after_error = await client.get(
        "/v1/interventions",
        params={"session_id": session.id},
    )
    pending_nudge = next(
        item for item in after_error.json() if item["action_taken"] == "SEND_NUDGE"
    )
    assert pending_nudge["outcome"] == "worker_error_observed_after_intervention"
    assert pending_nudge["helped"] is None
    assert pending_nudge["metadata"].get("outcome_final") is not True

    passed = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {
                "pytest": {
                    "ok": True,
                    "exit_code": 0,
                    "passed": 4,
                }
            },
        },
    )
    assert passed.status_code == 200
    completed = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    assert completed.status_code == 200
    completed_intervention = completed.json()["intervention"]
    assert completed_intervention["action_taken"] == "NOOP"
    verification = (completed_intervention.get("metadata") or {}).get("verification", {})
    assert verification.get("status") == "supported"
    stored = await client.get("/v1/interventions", params={"session_id": session.id})
    nudge = next(item for item in stored.json() if item["action_taken"] == "SEND_NUDGE")
    assert nudge["worker_response"] == "All tests passed. I am done."
    assert nudge["outcome"] == "goal_evidence_supported"
    assert nudge["helped"] is True
    audit_path = tmp_path / "PEX_INTERVENTION_LOG.jsonl"
    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    observed = [item for item in records if item["intervention_id"] == nudge["id"]]
    assert [item["record_type"] for item in observed] == [
        "delivery_reserved",
        "delivery_delivered",
        "outcome_observed",
        "outcome_observed",
        "outcome_observed",
    ]
    assert observed[-1]["outcome"] == "goal_evidence_supported"
    assert observed[-1]["helped"] is True


@pytest.mark.asyncio
async def test_short_eval_artifact_contradicts_done(client: AsyncClient, tmp_path):
    worker = tmp_path / "eval-worker"
    worker.mkdir()
    rows = "\n".join(f'{{"id": {i}}}' for i in range(27))
    (worker / "results.jsonl").write_text(rows + "\n", encoding="utf-8")
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="short-eval", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Eval",
                "objective": "Produce a complete evaluation",
                "acceptance_criteria": ["results.jsonl has 30 rows"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})
    stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "The evaluation is complete.",
        },
    )
    body = stop.json()
    assert body["intervention"]["action_taken"] == "SEND_NUDGE"
    text = adapter.inbox[session.id][-1]
    assert "27" in text and "30" in text
    assert not text.startswith("PEX:")


@pytest.mark.asyncio
async def test_pytest_permission_auto_allowed(client: AsyncClient):
    await _bind_cursor_conversation(
        client,
        conversation_id="conv-perm",
    )
    hook = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeShellExecution",
            "conversation_id": "conv-perm",
            "command": "pytest -q",
            "workspace_roots": ["C:/proj"],
        },
    )
    assert hook.json().get("permission") == "allow"


@pytest.mark.asyncio
async def test_destructive_shell_permission_asks_human(client: AsyncClient):
    hook = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeShellExecution",
            "conversation_id": "conv-rm",
            "command": "rm -rf /tmp/pex-scratch",
            "workspace_roots": ["C:/proj"],
        },
    )
    assert hook.json().get("permission") == "ask"


@pytest.mark.asyncio
async def test_commandless_and_sensitive_permissions_default_to_human(client: AsyncClient):
    cases = [
        {
            "hook_event_name": "beforeReadFile",
            "conversation_id": "conv-secret",
            "file_path": "C:/Users/me/.ssh/id_rsa",
            "workspace_roots": ["C:/proj"],
        },
        {
            "hook_event_name": "beforeMCPExecution",
            "conversation_id": "conv-mcp",
            "tool_name": "send_email",
            "workspace_roots": ["C:/proj"],
        },
        {
            "hook_event_name": "beforeShellExecution",
            "conversation_id": "conv-unknown-shell",
            "command": "python deploy.py",
            "workspace_roots": ["C:/proj"],
        },
    ]
    for payload in cases:
        await _bind_cursor_conversation(
            client,
            conversation_id=str(payload["conversation_id"]),
            workspace_root=str(payload["workspace_roots"][0]),
        )
        hook = await client.post("/v1/hooks/cursor", json=payload)
        assert hook.status_code == 200
        assert hook.json().get("permission") == "ask"


@pytest.mark.asyncio
async def test_codex_handoff_requires_and_persists_exact_target_turn(client: AsyncClient):
    project_id = "codex-handoff-project"
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": project_id,
                "title": "Exact Codex handoff delivery",
                "objective": "Share the observed schema fact with the bound Codex thread.",
            },
        )
    ).json()
    source = state.adapters.synthetic.seed_session(
        vendor_id="codex-handoff-source",
        project_id=project_id,
    )
    await state.store.upsert_session(source)
    source_attach = await client.post(
        f"/v1/sessions/{source.id}/attach",
        json={"goal_id": goal["id"]},
    )
    assert source_attach.status_code == 200
    observed = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source.id,
            "event_type": EventType.AGENT_RESPONSE.value,
            "message": "The exact schema fact is stored in schema.json.",
            "file_paths": ["schema.json"],
        },
    )
    assert observed.status_code == 200

    exact_target = HarnessSession(
        id="codex:handoff-exact",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-handoff-exact",
        project_id=project_id,
        capabilities={"send_message": True, "inject_context": True},
    )
    await state.store.upsert_session(exact_target)
    exact_attach = await client.post(
        f"/v1/sessions/{exact_target.id}/attach",
        json={"goal_id": goal["id"]},
    )
    assert exact_attach.status_code == 200
    exact_adapter = _TypedCodexHandoffAdapter(
        AdapterMessageResult(
            accepted=True,
            vendor_session_id=exact_target.vendor_session_id,
            vendor_turn_id="turn-handoff-exact",
        )
    )
    state.adapters.bind("codex", exact_adapter)

    delivered = await client.post(
        f"/v1/sessions/{source.id}/handoff",
        json={
            "idempotency_key": "codex-handoff-exact-0001",
            "target_session_id": exact_target.id,
            "token_budget": 2_000,
        },
    )

    assert delivered.status_code == 200, delivered.text
    receipt = {
        "schema": "pex.worker-delivery.codex-turn.v1",
        "target_session_id": exact_target.id,
        "vendor_session_id": exact_target.vendor_session_id,
        "vendor_turn_id": "turn-handoff-exact",
    }
    assert delivered.json()["effect"]["result"]["worker_delivery_receipt"] == receipt
    assert delivered.json()["intervention"]["metadata"]["worker_delivery_receipt"] == receipt
    assert exact_adapter.calls == 1

    wrong_target = HarnessSession(
        id="codex:handoff-wrong",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-handoff-wrong",
        project_id=project_id,
        capabilities={"send_message": True, "inject_context": True},
    )
    await state.store.upsert_session(wrong_target)
    wrong_attach = await client.post(
        f"/v1/sessions/{wrong_target.id}/attach",
        json={"goal_id": goal["id"]},
    )
    assert wrong_attach.status_code == 200
    wrong_adapter = _TypedCodexHandoffAdapter(
        AdapterMessageResult(
            accepted=True,
            vendor_session_id="another-thread",
            vendor_turn_id="turn-handoff-wrong",
        )
    )
    state.adapters.bind("codex", wrong_adapter)

    uncertain = await client.post(
        f"/v1/sessions/{source.id}/handoff",
        json={
            "idempotency_key": "codex-handoff-wrong-0001",
            "target_session_id": wrong_target.id,
            "token_budget": 2_000,
        },
    )

    assert uncertain.status_code == 502, uncertain.text
    assert uncertain.json()["status"] == "delivery_uncertain"
    assert uncertain.json()["effect"]["result"] == {
        "status": "delivery_uncertain",
        "reason": "handoff_invalid_adapter_receipt",
    }
    assert uncertain.json()["intervention"]["action_taken"] == "NOOP"
    assert uncertain.json()["intervention"]["result"] == "handoff_delivery_uncertain"
    assert "worker_delivery_receipt" not in uncertain.json()["intervention"]["metadata"]
    assert wrong_adapter.calls == 1
