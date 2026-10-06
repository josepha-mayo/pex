import asyncio
import hashlib
import json
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.mcp_auth import MCPPrincipal
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import MCP_REQUEST_DECISION_TOOL, Store, utcnow
from pex_protocol.capabilities import AdapterCapabilities, PermissionResponseMode
from pex_protocol.context import HumanDecisionRequest
from pex_protocol.enums import EventType
from pex_protocol.goal import Goal

_OPERATOR_TOKEN = "test-operator-token-0123456789abcdef"


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
    state.token = _OPERATOR_TOKEN
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    await store.connect()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {_OPERATOR_TOKEN}"},
    ) as ac:
        yield ac
    await store.close()


async def _pending_permission(client: AsyncClient) -> tuple[dict, dict]:
    session = (await client.post("/v1/synthetic/sessions")).json()
    now = utcnow()
    goal = Goal(
        id=f"goal-{session['id'].replace(':', '-')}",
        project_id="demo",
        title="Resolve one synthetic permission",
        objective="Bind the test request to explicit persistent intent.",
        created_at=now,
        updated_at=now,
    )
    bound = await state.store.get_session(session["id"])
    assert bound is not None
    bound.project_id = goal.project_id
    bound.goal_id = goal.id
    state.adapters.synthetic.sessions[bound.id].project_id = goal.project_id
    state.adapters.synthetic.sessions[bound.id].goal_id = goal.id
    await state.store.upsert_goal(goal)
    await state.store.upsert_session(bound, allow_goal_change=True)
    session = bound.model_dump(mode="json")
    event = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session["id"],
            "event_type": EventType.PERMISSION_REQUEST.value,
            "phase": "before",
            "command": "rm -rf /tmp/important-state",
        },
    )
    assert event.status_code == 200
    intervention = event.json()["intervention"]
    assert intervention["action_taken"] == "RESPOND_PERMISSION"
    assert intervention["policy_verdict"] == "ask_human"
    assert intervention["result"] == "permission_awaiting_human"
    return session, intervention


async def _pending_generic_decision(
    *,
    request_id: str,
    options: list[str],
) -> tuple[dict, dict]:
    now = utcnow()
    goal = Goal(
        id=f"goal-{request_id}",
        project_id="demo",
        title="Route a worker decision",
        objective="Deliver the exact authenticated human answer.",
        created_at=now,
        updated_at=now,
    )
    session = state.adapters.synthetic.seed_session(
        vendor_id=f"worker-{request_id}",
        project_id=goal.project_id,
        goal_id=goal.id,
    )
    await state.store.upsert_goal(goal)
    await state.store.upsert_session(session)
    issued_at = now - timedelta(seconds=1)
    principal_record = await state.store.issue_mcp_principal(
        principal_id=f"principal-{request_id}",
        session_id=session.id,
        goal_id=goal.id,
        project_id=goal.project_id,
        vendor_session_id=session.vendor_session_id,
        harness_type=session.harness_type.value,
        scopes=["mcp:read", MCP_REQUEST_DECISION_TOOL],
        token_digest=hashlib.sha256(f"token-{request_id}".encode()).hexdigest(),
        issued_at=issued_at,
        expires_at=issued_at + timedelta(hours=1),
    )
    opened = await state.pipeline.request_human_decision(
        session,
        principal=MCPPrincipal.from_store_record(principal_record),
        request=HumanDecisionRequest(
            idempotency_key=request_id,
            question="What exact answer should the worker use?",
            options=options,
            urgency="blocking",
        ),
    )
    return session.model_dump(mode="json"), opened


@pytest.mark.asyncio
async def test_human_permission_resolution_is_delivered_audited_and_replay_safe(
    client: AsyncClient,
    tmp_path,
):
    session, intervention = await _pending_permission(client)
    request_id = intervention["proposed_action"]["payload"]["request_id"]

    pending_session = await client.get(f"/v1/sessions/{session['id']}")
    assert pending_session.json()["status"] == "needs_decision"

    resolved = await client.post(
        f"/v1/decisions/{intervention['id']}/resolve",
        json={"decision": "deny"},
    )
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["ok"] is True
    assert body["delivered"] is True
    assert body["replayed"] is False
    assert body["resolution"]["status"] == "delivered"
    assert body["resolution"]["source"] == "human"
    assert body["resolution"]["channel"] == "authenticated_local_control_api"
    assert state.adapters.synthetic.permissions[session["id"]] == [
        {"request_id": request_id, "decision": "deny"}
    ]

    stored = await state.store.get_intervention(intervention["id"])
    assert stored is not None
    assert stored.policy_verdict.value == "ask_human"
    assert stored.result == "permission_deny"
    assert stored.outcome == "human_permission_delivered"
    assert stored.metadata["permission_resolution"]["source"] == "human"
    resumed_session = await client.get(f"/v1/sessions/{session['id']}")
    assert resumed_session.json()["status"] == "working"

    replay = await client.post(
        f"/v1/decisions/{intervention['id']}/resolve",
        json={"decision": "deny"},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert len(state.adapters.synthetic.permissions[session["id"]]) == 1

    conflict = await client.post(
        f"/v1/decisions/{intervention['id']}/resolve",
        json={"decision": "allow"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "permission_decision_conflict"
    assert len(state.adapters.synthetic.permissions[session["id"]]) == 1

    records = [
        json.loads(line)
        for line in (tmp_path / "PEX_INTERVENTION_LOG.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    relevant = [row for row in records if row["intervention_id"] == intervention["id"]]
    assert [row["record_type"] for row in relevant] == [
        "created",
        "human_decision_resolved",
    ]
    assert relevant[-1]["permission_request_id"] == request_id
    assert relevant[-1]["permission_resolution"]["decision"] == "deny"


@pytest.mark.asyncio
async def test_hook_only_permission_cannot_be_falsely_resolved_later(
    client: AsyncClient,
    tmp_path,
):
    cold_claude = await state.adapters.claude_code.probe()
    assert cold_claude.approve is False
    assert cold_claude.deny is False
    assert cold_claude.permission_response_mode == PermissionResponseMode.NONE

    workspace = str(tmp_path.resolve())
    hook = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeShellExecution",
            "conversation_id": "human-decision-hook-only",
            "command": "rm -rf /tmp/important-state",
            "workspace_roots": [workspace],
        },
    )
    assert hook.status_code == 200
    assert hook.json()["permission"] == "ask"
    cursor_caps = await state.adapters.cursor.probe()
    assert cursor_caps.approve is True
    assert cursor_caps.deny is True
    assert cursor_caps.permission_response_mode == PermissionResponseMode.INLINE
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "idempotency_key": "decision-hook-goal-create-0001",
                "project_id": workspace,
                "title": "Keep an inline hook decision bound to persistent intent",
                "objective": "Prove a returned hook prompt cannot be answered later.",
            },
        )
    ).json()
    attached = await client.post(
        "/v1/sessions/cursor:human-decision-hook-only/attach",
        json={
            "idempotency_key": "decision-hook-goal-attach-0001",
            "goal_id": goal["id"],
            "expected_goal_id": None,
            "expected_control_revision": 0,
            "expected_goal_intent_revision": goal["intent_revision"],
        },
    )
    assert attached.status_code == 200, attached.text
    second_hook = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeShellExecution",
            "conversation_id": "human-decision-hook-only",
            "generation_id": "human-decision-hook-only-second",
            "command": "rm -rf /tmp/important-state",
            "workspace_roots": [workspace],
        },
    )
    assert second_hook.status_code == 200
    assert second_hook.json()["permission"] == "ask"
    interventions = await client.get(
        "/v1/interventions",
        params={"session_id": "cursor:human-decision-hook-only"},
    )
    pending = interventions.json()[0]
    assert pending["result"] == "permission_delegated_to_harness"

    # Simulate a stale record written by a pre-mode PEX version. Even though
    # inline adapters truthfully support allow/deny, the later control API must
    # never pretend it can answer an already-returned hook.
    stored = await state.store.get_intervention(pending["id"])
    assert stored is not None
    stored.result = "permission_awaiting_human"
    await state.store.update_intervention(stored, record_type="test_legacy_pending")

    response = await client.post(
        f"/v1/decisions/{pending['id']}/resolve",
        json={"decision": "deny"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "permission_delivery_unsupported"
    assert state.adapters.cursor.permission_responses == []


@pytest.mark.asyncio
async def test_failed_permission_delivery_is_persisted_and_not_retried(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    session, intervention = await _pending_permission(client)
    calls = 0

    async def fail_delivery(*_args):
        nonlocal calls
        calls += 1
        return False

    monkeypatch.setattr(state.adapters.synthetic, "respond_permission", fail_delivery)
    failed = await client.post(
        f"/v1/decisions/{intervention['id']}/resolve",
        json={"decision": "allow"},
    )
    assert failed.status_code == 502
    detail = failed.json()["detail"]
    assert detail["code"] == "permission_delivery_failed"
    assert detail["resolution"]["resolution"]["status"] == "failed"
    assert calls == 1

    stored = await state.store.get_intervention(intervention["id"])
    assert stored is not None
    assert stored.result == "permission_allow_failed"
    assert stored.outcome == "human_permission_delivery_failed"
    current = await client.get(f"/v1/sessions/{session['id']}")
    assert current.json()["status"] == "needs_decision"

    no_retry = await client.post(
        f"/v1/decisions/{intervention['id']}/resolve",
        json={"decision": "allow"},
    )
    assert no_retry.status_code == 409
    assert no_retry.json()["detail"]["code"] == "permission_delivery_not_retriable"
    assert calls == 1


@pytest.mark.asyncio
async def test_exception_during_permission_delivery_is_marked_uncertain(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _, intervention = await _pending_permission(client)

    async def uncertain_delivery(*_args):
        raise RuntimeError("transport disconnected after write")

    monkeypatch.setattr(state.adapters.synthetic, "respond_permission", uncertain_delivery)
    response = await client.post(
        f"/v1/decisions/{intervention['id']}/resolve",
        json={"decision": "deny"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "permission_delivery_uncertain"
    stored = await state.store.get_intervention(intervention["id"])
    assert stored is not None
    resolution = stored.metadata["permission_resolution"]
    assert resolution["status"] == "delivery_uncertain"
    assert resolution["exception_type"] == "RuntimeError"
    assert stored.outcome == "human_permission_delivery_uncertain"


@pytest.mark.asyncio
async def test_permission_delivery_timeout_is_persisted_as_uncertain(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    import pex_bridge.decisions as decisions

    _, intervention = await _pending_permission(client)

    async def stalled_delivery(*_args):
        await asyncio.sleep(10)
        return True

    monkeypatch.setattr(decisions, "PERMISSION_DELIVERY_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(state.adapters.synthetic, "respond_permission", stalled_delivery)
    response = await client.post(
        f"/v1/decisions/{intervention['id']}/resolve",
        json={"decision": "deny"},
    )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "permission_delivery_uncertain"
    stored = await state.store.get_intervention(intervention["id"])
    assert stored is not None
    assert stored.metadata["permission_resolution"]["exception_type"] == "TimeoutError"


@pytest.mark.asyncio
async def test_non_permission_intervention_cannot_be_resolved_as_approval(client: AsyncClient):
    session = (await client.post("/v1/synthetic/sessions")).json()
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "idempotency_key": "decision-no-channel-goal-create-0001",
                "project_id": session.get("project_id") or "demo",
                "title": "Keep STOP inspection bound to persistent intent",
                "objective": "Inspect the worker STOP without creating a permission decision.",
            },
        )
    ).json()
    attached = await client.post(
        f"/v1/sessions/{session['id']}/attach",
        json={
            "idempotency_key": "decision-no-channel-goal-attach-0001",
            "goal_id": goal["id"],
            "expected_goal_id": None,
            "expected_control_revision": 0,
            "expected_goal_intent_revision": goal["intent_revision"],
        },
    )
    assert attached.status_code == 200, attached.text
    stopped = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session["id"],
            "event_type": EventType.STOP.value,
            "message": "Stopping for a goal-bound non-permission inspection.",
        },
    )
    intervention = stopped.json()["intervention"]
    response = await client.post(
        f"/v1/decisions/{intervention['id']}/resolve",
        json={"decision": "allow"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "decision_not_pending_permission"


@pytest.mark.asyncio
async def test_permission_resolution_completes_with_real_app_lifespan(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Exercise the same startup/background-task path used by the desktop bridge."""
    monkeypatch.setenv("PEX_SUPERVISOR_DISABLE", "1")
    settings = Settings(
        require_auth=True,
        token=_OPERATOR_TOKEN,
        home=tmp_path,
        autonomy="manage",
        codex_attach=False,
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
    app = create_app()

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers={"Authorization": f"Bearer {_OPERATOR_TOKEN}"},
        ) as live_client:
            session, intervention = await _pending_permission(live_client)
            response = await asyncio.wait_for(
                live_client.post(
                    f"/v1/decisions/{intervention['id']}/resolve",
                    json={"decision": "deny"},
                ),
                timeout=2,
            )

    assert response.status_code == 200
    assert response.json()["resolution"]["status"] == "delivered"
    assert adapters.synthetic.permissions[session["id"]] == [
        {
            "request_id": intervention["proposed_action"]["payload"]["request_id"],
            "decision": "deny",
        }
    ]


@pytest.mark.asyncio
async def test_generic_freeform_rest_delivery_is_opaque_on_response_bus_and_replay(
    client: AsyncClient,
):
    raw_answer = "swordfish-proprietary-rest-answer"
    published: list[tuple[str, dict]] = []

    async def capture(topic: str, payload: dict) -> None:
        published.append((topic, payload))

    async def broken_presentation(_topic: str, _payload: dict) -> None:
        raise RuntimeError("presentation unavailable")

    state.bus.subscribe(capture)
    state.bus.subscribe(broken_presentation)
    session, opened = await _pending_generic_decision(
        request_id="rest-freeform-opaque-0001",
        options=[],
    )
    resolved = await client.post(
        f"/v1/decisions/{opened['intervention']['id']}/resolve",
        json={"decision": raw_answer},
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["ok"] is True
    assert body["delivered"] is True
    assert body["delivery_status"] == "delivered"
    assert body["resolution"]["status"] == "delivered"
    assert raw_answer not in json.dumps(body, ensure_ascii=False)
    assert raw_answer not in json.dumps(published, ensure_ascii=False)
    assert sum(
        raw_answer in message
        for message in state.adapters.synthetic.inbox[session["id"]]
    ) == 1

    replay = await client.post(
        f"/v1/decisions/{opened['intervention']['id']}/resolve",
        json={"decision": raw_answer},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert sum(
        raw_answer in message
        for message in state.adapters.synthetic.inbox[session["id"]]
    ) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_status", "expected_http"),
    [
        ("unsupported", "unsupported", 409),
        ("rejected", "rejected", 409),
        ("uncertain", "delivery_uncertain", 502),
    ],
)
async def test_generic_rest_delivery_failures_preserve_structured_honest_status(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected_status: str,
    expected_http: int,
):
    session, opened = await _pending_generic_decision(
        request_id=f"rest-outcome-{mode}-0001",
        options=["ship", "iterate"],
    )
    adapter = state.adapters.synthetic
    calls = 0
    if mode == "unsupported":

        async def unsupported_probe() -> AdapterCapabilities:
            return AdapterCapabilities(send_message=False)

        monkeypatch.setattr(adapter, "probe", unsupported_probe)
    else:

        async def controlled_send(*_args, **_kwargs) -> bool:
            nonlocal calls
            calls += 1
            if mode == "uncertain":
                raise RuntimeError("private transport detail")
            return False

        monkeypatch.setattr(adapter, "send_message", controlled_send)

    response = await client.post(
        f"/v1/decisions/{opened['intervention']['id']}/resolve",
        json={"decision": "iterate"},
    )
    assert response.status_code == expected_http
    detail = response.json()["detail"]
    assert detail["code"] == f"human_decision_{expected_status}"
    receipt = detail["resolution"]
    assert receipt["ok"] is False
    assert receipt["delivered"] is False
    assert receipt["delivery_status"] == expected_status
    assert receipt["resolution"]["status"] == expected_status
    assert receipt["session_status"] == "needs_decision"
    assert "private transport detail" not in json.dumps(detail)
    assert calls == (0 if mode == "unsupported" else 1)
    live = await state.store.get_session(session["id"])
    assert live is not None and live.status.value == "needs_decision"


@pytest.mark.asyncio
async def test_general_escalation_resolution_is_recorded_replay_safe_and_restores(
    client: AsyncClient,
    tmp_path,
):
    """A human answer resolves a supervisor escalation — once, durably.

    The answer is ledger evidence, not worker delivery: the response must
    say ``worker_delivery: not_attempted``, the escalation leaves the
    pending inbox, and the replayed session returns to its pre-decision
    (stopped) status. Repeating the same answer replays; a different one
    conflicts.
    """

    replay = await client.post("/v1/demo/replay", json={"fixture": "nudge_dispute_eval"})
    assert replay.status_code == 200, replay.text
    body = replay.json()
    assert body["replay"] is True and body["not_live_control"] is True
    # The adjudicated verdict travels with the run so callers can summarize
    # the arc without a second fetch — status/reason, never narration.
    assert body["completion"]["status"] in {"uncertain", "incomplete", "in_progress"}
    assert isinstance(body["completion"]["reason"], str)
    # The fixture's declared arc is scored by the bridge against this run —
    # the same contract scripts/eval_replays.py enforces suite-wide.
    declared = body["declared"]
    assert declared["met"] is True
    assert declared["failures"] == []
    assert "ASK_HUMAN" in declared["expectation"]["interventions_any"]
    escalation = next(
        item for item in body["interventions"] if item.get("action_taken") == "ASK_HUMAN"
    )
    session_id = body["session_id"]
    pending_session = await state.store.get_session(session_id)
    assert pending_session.status.value == "needs_decision"

    resolved = await client.post(
        f"/v1/decisions/{escalation['id']}/resolve",
        json={"decision": "Keep the requirement; the test file stays sealed."},
    )
    assert resolved.status_code == 200, resolved.text
    resolved_body = resolved.json()
    assert resolved_body["ok"] is True
    assert resolved_body["kind"] == "escalation"
    assert resolved_body["recorded"] is True
    assert resolved_body["worker_delivery"] == "not_attempted"
    assert resolved_body["replayed"] is False
    assert resolved_body["resolution"]["status"] == "recorded"
    assert resolved_body["resolution"]["answer"] == (
        "Keep the requirement; the test file stays sealed."
    )
    assert resolved_body["intervention"]["result"] == "human_answered"
    assert resolved_body["intervention"]["outcome"] == "human_answered"

    replay_session = await state.store.get_session(session_id)
    assert replay_session.status.value == "stopped"

    metrics = (await client.get("/v1/attention/metrics")).json()
    pending_ids = {item["id"] for item in metrics["current_pending"]["items"]}
    assert escalation["id"] not in pending_ids

    replayed = await client.post(
        f"/v1/decisions/{escalation['id']}/resolve",
        json={"decision": "Keep the requirement; the test file stays sealed."},
    )
    assert replayed.status_code == 200
    assert replayed.json()["replayed"] is True

    conflict = await client.post(
        f"/v1/decisions/{escalation['id']}/resolve",
        json={"decision": "Amend the goal; accept the worker's position."},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "escalation_resolution_conflict"

    # The ruling is durable human intent: it journals onto the goal's
    # Decision ledger once (the replayed call added no second row), so
    # future planning and prompt linting inherit the human's call.
    assert replay_session.goal_id is not None
    decisions = await state.store.list_decisions_for_authority(replay_session.goal_id)
    rulings = [item for item in decisions if item.metadata.get("kind") == "escalation_ruling"]
    assert len(rulings) == 1
    ruling = rulings[0]
    assert ruling.statement == "Keep the requirement; the test file stays sealed."
    assert ruling.source.value == "human"
    assert ruling.metadata["intervention_id"] == escalation["id"]
    assert ruling.id == resolved_body["resolution"]["ledger_decision_id"]

    records = [
        json.loads(line)
        for line in (tmp_path / "PEX_INTERVENTION_LOG.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    relevant = [row for row in records if row["intervention_id"] == escalation["id"]]
    assert relevant[0]["record_type"] == "created"
    assert relevant[-1]["record_type"] == "human_resolution"
    assert relevant[-1]["human_resolution"]["answer"] == (
        "Keep the requirement; the test file stays sealed."
    )


@pytest.mark.asyncio
async def test_recorded_ruling_governs_a_second_replay_on_the_same_goal(
    client: AsyncClient,
):
    """A journaled ruling is durable intent, not a closed ticket.

    Resolve the dispute escalation with a ban-phrased ruling, then attach a
    second replay to the *same* goal — the goal's own text never forbids the
    sealed-test edit, so the nudge can only cite the recorded human ruling.
    """

    replay = await client.post("/v1/demo/replay", json={"fixture": "nudge_dispute_eval"})
    assert replay.status_code == 200, replay.text
    body = replay.json()
    escalation = next(
        item for item in body["interventions"] if item.get("action_taken") == "ASK_HUMAN"
    )
    session = await state.store.get_session(body["session_id"])
    assert session is not None and session.goal_id is not None
    goal_id = session.goal_id

    resolved = await client.post(
        f"/v1/decisions/{escalation['id']}/resolve",
        json={"decision": "Do not modify the sealed baseline test file"},
    )
    assert resolved.status_code == 200, resolved.text

    second = await client.post(
        "/v1/demo/replay",
        json={"fixture": "ruling_continuity_eval", "goal_id": goal_id},
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["replay"] is True and second_body["not_live_control"] is True
    assert second_body["goal_id"] == goal_id
    assert second_body["goal_source"] == "attached"

    nudge = next(
        item for item in second_body["interventions"] if item.get("action_taken") == "SEND_NUDGE"
    )
    blob = json.dumps(nudge)
    assert "agent_contradiction" in blob
    assert "Do not modify the sealed baseline test file" in blob


@pytest.mark.asyncio
async def test_recorded_ruling_governs_after_an_override_mode_goal_edit(
    client: AsyncClient,
):
    """A ruling survives the very resolution path the card suggests.

    Resolve the dispute, then amend the goal with mode="override" — which
    mints a successor goal row and rebinds sessions to it. The ruling must
    still govern replays attached to the successor: durable human intent
    outlives the goal revision it was recorded under.
    """

    replay = await client.post("/v1/demo/replay", json={"fixture": "nudge_dispute_eval"})
    assert replay.status_code == 200, replay.text
    body = replay.json()
    escalation = next(
        item for item in body["interventions"] if item.get("action_taken") == "ASK_HUMAN"
    )
    session = await state.store.get_session(body["session_id"])
    assert session is not None and session.goal_id is not None
    goal_id = session.goal_id

    resolved = await client.post(
        f"/v1/decisions/{escalation['id']}/resolve",
        json={"decision": "Do not modify the sealed baseline test file"},
    )
    assert resolved.status_code == 200, resolved.text

    goals = (await client.get("/v1/goals")).json()
    current = next(item for item in goals if item["id"] == goal_id)
    patched = await client.patch(
        f"/v1/goals/{goal_id}",
        json={
            "idempotency_key": "e2e-override-after-ruling",
            "mode": "override",
            "expected_intent_revision": current["intent_revision"],
            "objective": current["objective"] + " Weekly standoff reporting.",
        },
    )
    assert patched.status_code == 200, patched.text
    successor = patched.json()
    assert successor["id"] != goal_id
    assert successor["supersedes"] == goal_id

    migrated = await state.store.get_session(session.id)
    assert migrated.goal_id == successor["id"]

    decisions = (await client.get(f"/v1/goals/{successor['id']}/decisions")).json()
    assert any(
        item.get("statement") == "Do not modify the sealed baseline test file" for item in decisions
    )

    second = await client.post(
        "/v1/demo/replay",
        json={"fixture": "ruling_continuity_eval", "goal_id": successor["id"]},
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["goal_id"] == successor["id"]
    assert second_body["goal_source"] == "attached"
    nudge = next(
        item for item in second_body["interventions"] if item.get("action_taken") == "SEND_NUDGE"
    )
    blob = json.dumps(nudge)
    assert "agent_contradiction" in blob
    assert "Do not modify the sealed baseline test file" in blob

    # A stale handle follows the lineage too: attaching to the retired
    # predecessor lands on the live successor, never on a dead revision.
    third = await client.post(
        "/v1/demo/replay",
        json={"fixture": "ruling_continuity_eval", "goal_id": goal_id},
    )
    assert third.status_code == 200, third.text
    third_body = third.json()
    assert third_body["goal_id"] == successor["id"]
    assert third_body["goal_source"] == "attached"


@pytest.mark.asyncio
async def test_recorded_ruling_lints_the_humans_own_later_prompt(
    client: AsyncClient,
):
    """Durable intent bounds the human too, not just the worker.

    After a ruling is journaled, a user prompt that contradicts it on a
    later attached trajectory escalates to the human for confirmation —
    the constraint cited in the card is the recorded ruling itself.
    """

    replay = await client.post("/v1/demo/replay", json={"fixture": "nudge_dispute_eval"})
    assert replay.status_code == 200, replay.text
    body = replay.json()
    escalation = next(
        item for item in body["interventions"] if item.get("action_taken") == "ASK_HUMAN"
    )
    session = await state.store.get_session(body["session_id"])
    assert session is not None and session.goal_id is not None

    resolved = await client.post(
        f"/v1/decisions/{escalation['id']}/resolve",
        json={"decision": "Do not modify the sealed baseline test file"},
    )
    assert resolved.status_code == 200, resolved.text

    second = await client.post(
        "/v1/demo/replay",
        json={"fixture": "ruling_selfcheck_eval", "goal_id": session.goal_id},
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["goal_source"] == "attached"
    ask_human = next(
        item for item in second_body["interventions"] if item.get("action_taken") == "ASK_HUMAN"
    )
    blob = json.dumps(ask_human)
    assert "possible_contradiction" in blob
    assert "Do not modify the sealed baseline test file" in blob
    # The card asks the human to confirm or override — it does not pretend
    # the prompt was blocked or silently rewritten.
    assert "Did you mean to keep that ledger rule" in blob


@pytest.mark.asyncio
async def test_replay_attach_rejects_an_unknown_goal(client: AsyncClient):
    response = await client.post(
        "/v1/demo/replay",
        json={
            "fixture": "ruling_continuity_eval",
            "goal_id": "goal_doesnotexist000000000000000000000000",
        },
    )
    assert response.status_code == 404
