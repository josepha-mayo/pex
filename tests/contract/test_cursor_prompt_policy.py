import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge import app as bridge_app
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import _cursor_submit_response, create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import EventPhase, EventType, HarnessType, PolicyVerdict
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorResult


@pytest.fixture
async def client(tmp_path):
    settings = Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.pipeline = Pipeline(store, adapters, bus, settings)
    await store.connect()
    app = create_app()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1",
        ) as ac:
            yield ac
    finally:
        await store.close()


def _session() -> HarnessSession:
    return HarnessSession(
        id="cursor:policy-conv",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="policy-conv",
        project_id="C:/proj",
        goal_id="goal-policy",
        cwd="C:/proj",
    )


def _event(session: HarnessSession) -> HarnessEvent:
    return HarnessEvent(
        event_id="cursor:policy-conv:hook:prompt-1",
        ts=datetime.now(UTC),
        harness_type=HarnessType.CURSOR,
        session_id=session.id,
        project_id=session.project_id,
        goal_id=session.goal_id,
        event_type=EventType.USER_PROMPT,
        phase=EventPhase.BEFORE,
        message_delta="Keep this prompt within the persistent goal.",
        metadata={"hook_event_name": "beforeSubmitPrompt"},
    )


def _intervention(
    session: HarnessSession,
    event: HarnessEvent,
    *,
    kind: InterventionType = InterventionType.ASK_HUMAN,
    verdict: PolicyVerdict = PolicyVerdict.ALLOW,
    result: str | None = None,
    action_taken: str | None = None,
    payload: dict | None = None,
    evidence: list[str] | None = None,
    session_id: str | None = None,
    goal_id: str | None = None,
    trigger: str | None = None,
    trigger_event_id: str | None = None,
) -> Intervention:
    bound_session_id = session.id if session_id is None else session_id
    bound_goal_id = session.goal_id if goal_id is None else goal_id
    evidence = ["persistent goal conflict"] if evidence is None else evidence
    if payload is None:
        payload = (
            {"question": "This conflicts with the goal. Continue anyway?"}
            if kind == InterventionType.ASK_HUMAN
            else {"text": "Clarify this prompt against the persistent goal."}
        )
    action = ProposedAction(
        type=kind,
        session_id=bound_session_id,
        goal_id=bound_goal_id,
        payload=payload,
        rationale="Apply the completed prompt policy decision.",
        evidence=evidence,
    )
    return Intervention(
        id="intervention-prompt-1",
        session_id=bound_session_id,
        goal_id=bound_goal_id,
        trigger=trigger or EventType.USER_PROMPT.value,
        evidence=action.evidence,
        diagnosis="prompt_policy",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action_taken or kind.value,
        policy_verdict=verdict,
        result=result
        or ("escalated" if kind == InterventionType.ASK_HUMAN else "annotated"),
        created_at=datetime.now(UTC),
        metadata={"trigger_event_id": trigger_event_id or event.event_id},
    )


async def _bind_cursor(client: AsyncClient, *, conversation_id: str) -> tuple[str, str]:
    goal_response = await client.post(
        "/v1/goals",
        json={
            "project_id": "C:/proj",
            "title": "Keep the prompt goal-bound",
            "objective": "Do not alter dataset preprocessing",
            "acceptance_criteria": ["metrics.json exists"],
            "constraints": ["Do not alter dataset preprocessing."],
        },
    )
    assert goal_response.status_code == 200
    goal_id = goal_response.json()["id"]
    started = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "sessionStart",
            "conversation_id": conversation_id,
            "workspace_roots": ["C:/proj"],
        },
    )
    assert started.status_code == 200
    session_id = f"cursor:{conversation_id}"
    attached = await client.post(
        f"/v1/sessions/{session_id}/attach",
        json={"goal_id": goal_id},
    )
    assert attached.status_code == 200
    return session_id, goal_id


@pytest.mark.parametrize("verdict", [PolicyVerdict.ALLOW, PolicyVerdict.ASK_HUMAN])
def test_cursor_submit_response_accepts_completed_human_question(verdict: PolicyVerdict):
    session = _session()
    event = _event(session)
    intervention = _intervention(
        session,
        event,
        verdict=verdict,
        payload={"question": "  Should this override the persistent goal?  "},
    )

    assert _cursor_submit_response(intervention, event, session) == {
        "continue": False,
        "user_message": "Should this override the persistent goal?",
    }


def test_cursor_submit_response_accepts_completed_annotation():
    session = _session()
    event = _event(session)
    intervention = _intervention(
        session,
        event,
        kind=InterventionType.ANNOTATE,
        payload={"text": "  Keep the existing preprocessing fixed.  "},
    )

    assert _cursor_submit_response(intervention, event, session) == {
        "continue": True,
        "user_message": "Keep the existing preprocessing fixed.",
    }


@pytest.mark.parametrize(
    "case",
    [
        "stale_event",
        "wrong_trigger",
        "wrong_intervention_session",
        "wrong_intervention_goal",
        "wrong_action_session",
        "wrong_action_goal",
        "pending_result",
        "wrong_action_taken",
        "empty_evidence",
        "denied_human_question",
        "denied_annotation",
        "pending_annotation",
        "paused_session",
        "unattached_session",
        "wrong_event_type",
        "wrong_event_phase",
        "wrong_hook_name",
        "wrong_event_session",
        "wrong_event_project",
        "wrong_event_goal",
        "wrong_session_harness",
        "wrong_event_harness",
    ],
)
def test_cursor_submit_response_rejects_stale_or_unbound_decisions(case: str):
    session = _session()
    event = _event(session)
    intervention = _intervention(session, event)

    if case == "stale_event":
        intervention = _intervention(session, event, trigger_event_id="older-event")
    elif case == "wrong_trigger":
        intervention = _intervention(session, event, trigger=EventType.STOP.value)
    elif case == "wrong_intervention_session":
        intervention = _intervention(session, event, session_id="cursor:other")
    elif case == "wrong_intervention_goal":
        intervention = _intervention(session, event, goal_id="goal-other")
    elif case == "wrong_action_session":
        action = intervention.proposed_action.model_copy(
            update={"session_id": "cursor:other"}
        )
        intervention = intervention.model_copy(update={"proposed_action": action})
    elif case == "wrong_action_goal":
        action = intervention.proposed_action.model_copy(update={"goal_id": "goal-other"})
        intervention = intervention.model_copy(update={"proposed_action": action})
    elif case == "pending_result":
        intervention = _intervention(session, event, result="pending")
    elif case == "wrong_action_taken":
        intervention = _intervention(
            session,
            event,
            action_taken=InterventionType.NOOP.value,
        )
    elif case == "empty_evidence":
        intervention = _intervention(session, event, evidence=[])
    elif case == "denied_human_question":
        intervention = _intervention(
            session,
            event,
            verdict=PolicyVerdict.DENY,
            result="denied_by_policy",
            action_taken=InterventionType.NOOP.value,
        )
    elif case == "denied_annotation":
        intervention = _intervention(
            session,
            event,
            kind=InterventionType.ANNOTATE,
            verdict=PolicyVerdict.DENY,
            result="denied_by_policy",
            action_taken=InterventionType.NOOP.value,
        )
    elif case == "pending_annotation":
        intervention = _intervention(
            session,
            event,
            kind=InterventionType.ANNOTATE,
            result="pending",
        )
    elif case == "paused_session":
        session = session.model_copy(update={"supervision_paused": True})
    elif case == "unattached_session":
        session = session.model_copy(update={"goal_id": None})
    elif case == "wrong_event_type":
        event = event.model_copy(update={"event_type": EventType.AGENT_RESPONSE})
    elif case == "wrong_event_phase":
        event = event.model_copy(update={"phase": EventPhase.AFTER})
    elif case == "wrong_hook_name":
        event = event.model_copy(update={"metadata": {"hook_event_name": "other"}})
    elif case == "wrong_event_session":
        event = event.model_copy(update={"session_id": "cursor:other"})
    elif case == "wrong_event_project":
        event = event.model_copy(update={"project_id": "C:/other"})
    elif case == "wrong_event_goal":
        event = event.model_copy(update={"goal_id": "goal-other"})
    elif case == "wrong_session_harness":
        session = session.model_copy(update={"harness_type": HarnessType.UNKNOWN})
    elif case == "wrong_event_harness":
        event = event.model_copy(update={"harness_type": HarnessType.UNKNOWN})

    assert _cursor_submit_response(intervention, event, session) == {"continue": True}


def test_cursor_submit_response_requires_real_intervention_model():
    session = _session()
    event = _event(session)
    lookalike = SimpleNamespace(
        session_id=session.id,
        goal_id=session.goal_id,
        trigger=EventType.USER_PROMPT.value,
        evidence=["looks valid"],
        proposed_action=SimpleNamespace(
            type=InterventionType.ASK_HUMAN,
            session_id=session.id,
            goal_id=session.goal_id,
            payload={"question": "Should this block?"},
        ),
        action_taken=InterventionType.ASK_HUMAN.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="escalated",
        metadata={"trigger_event_id": event.event_id},
    )

    assert _cursor_submit_response(lookalike, event, session) == {"continue": True}


@pytest.mark.parametrize("kind", [InterventionType.ASK_HUMAN, InterventionType.ANNOTATE])
@pytest.mark.parametrize("message", ["", "   ", "x" * 4_097])
def test_cursor_submit_response_rejects_blank_or_unbounded_text(
    kind: InterventionType,
    message: str,
):
    session = _session()
    event = _event(session)
    field = "question" if kind == InterventionType.ASK_HUMAN else "text"
    intervention = _intervention(
        session,
        event,
        kind=kind,
        payload={field: message},
    )

    response = _cursor_submit_response(intervention, event, session)

    assert response == {"continue": True}
    assert "user_message" not in response


@pytest.mark.asyncio
async def test_before_submit_prompt_does_not_surface_policy_denied_question(
    client: AsyncClient,
    monkeypatch,
):
    conversation_id = "policy-deny"
    await _bind_cursor(client, conversation_id=conversation_id)
    supervisor_calls = []
    policy_calls = []

    async def decide(request, *, local_model):
        del local_model
        supervisor_calls.append(request)
        return SupervisorResult(
            action=ProposedAction(
                type=InterventionType.ASK_HUMAN,
                session_id=request.session.id,
                goal_id=request.goal.id,
                payload={"question": "This must not reach Cursor."},
                rationale="The prompt conflicts with the persistent constraint.",
                evidence=["constraint conflict"],
            ),
            diagnosis="forced_question_for_policy_test",
        )

    def deny(action, command=None):
        policy_calls.append((action, command))
        return PolicyVerdict.DENY

    monkeypatch.setattr(state.pipeline.supervisor, "decide", decide)
    monkeypatch.setattr(state.pipeline.policy, "decide", deny)

    response = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeSubmitPrompt",
            "conversation_id": conversation_id,
            "workspace_roots": ["C:/proj"],
            "prompt": "Alter dataset preprocessing despite the constraint.",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"continue": True}
    assert len(supervisor_calls) == 1
    assert supervisor_calls[0].event.event_type == EventType.USER_PROMPT
    assert supervisor_calls[0].event.phase == EventPhase.BEFORE
    assert len(policy_calls) == 1
    assert policy_calls[0][0].type == InterventionType.ASK_HUMAN


@pytest.mark.asyncio
async def test_before_submit_prompt_rejects_pause_resume_aba_during_pipeline(
    client: AsyncClient,
    monkeypatch,
):
    conversation_id = "policy-aba"
    session_id, _ = await _bind_cursor(client, conversation_id=conversation_id)

    async def pause_resume_then_return_question(event, session):
        intervention = _intervention(session, event)
        before = await state.store.get_session_control_state(session.id)
        assert before is not None
        paused = await state.store.set_session_supervision_paused(
            session.id,
            paused=True,
            expected_control_revision=before["control_revision"],
            principal_id="test-operator",
            actor_assurance="bridge_bearer",
        )
        assert paused["granted"] is True
        middle = await state.store.get_session_control_state(session.id)
        assert middle is not None
        resumed = await state.store.set_session_supervision_paused(
            session.id,
            paused=False,
            expected_control_revision=middle["control_revision"],
            principal_id="test-operator",
            actor_assurance="bridge_bearer",
        )
        assert resumed["granted"] is True
        return intervention

    monkeypatch.setattr(
        state.pipeline,
        "ingest_event",
        pause_resume_then_return_question,
    )

    response = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeSubmitPrompt",
            "conversation_id": conversation_id,
            "workspace_roots": ["C:/proj"],
            "prompt": "Override the persistent goal.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {"continue": True}
    assert "user_message" not in body
    current = await state.store.get_session_for_authority(session_id)
    assert current is not None
    assert current.supervision_paused is False


@pytest.mark.asyncio
async def test_before_submit_authority_read_shares_hook_deadline(client, monkeypatch):
    conversation_id = "policy-authority-timeout"
    await _bind_cursor(client, conversation_id=conversation_id)
    cancelled = asyncio.Event()

    async def stalled_authority(session_id):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(bridge_app, "_cursor_submit_authority", stalled_authority)
    monkeypatch.setattr(bridge_app, "CURSOR_SUBMIT_PIPELINE_TIMEOUT_SECONDS", 0.01)
    response = await asyncio.wait_for(client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeSubmitPrompt",
            "conversation_id": conversation_id,
            "workspace_roots": ["C:/proj"],
            "prompt": "Continue the goal.",
        },
    ), timeout=5)
    assert response.status_code == 200
    assert response.json() == {"continue": True}
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_before_submit_rejects_goal_intent_aba_during_pipeline(client, monkeypatch):
    conversation_id = "policy-intent-aba"
    _, goal_id = await _bind_cursor(client, conversation_id=conversation_id)
    original = await state.store.get_goal_for_authority(goal_id)
    assert original is not None
    before = await state.store.get_goal_intent_view(goal_id)

    async def change_intent_twice_then_return_question(event, session):
        intervention = _intervention(session, event)
        changed = original.model_copy(update={"title": "A different goal title"})
        await state.store.patch_goal_with_ledger(original, changed, [])
        await state.store.patch_goal_with_ledger(changed, original, [])
        return intervention

    monkeypatch.setattr(state.pipeline, "ingest_event", change_intent_twice_then_return_question)
    response = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeSubmitPrompt",
            "conversation_id": conversation_id,
            "workspace_roots": ["C:/proj"],
            "prompt": "Continue the goal.",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"continue": True}
    after = await state.store.get_goal_intent_view(goal_id)
    assert after["intent_hash"] == before["intent_hash"]
    assert after["intent_revision"] > before["intent_revision"]


@pytest.mark.asyncio
async def test_before_submit_rejects_global_pause_during_pipeline(client, monkeypatch):
    conversation_id = "policy-global-pause"
    await _bind_cursor(client, conversation_id=conversation_id)

    async def pause_then_return_question(event, session):
        state.pipeline.supervision_paused = True
        return _intervention(session, event)

    monkeypatch.setattr(state.pipeline, "ingest_event", pause_then_return_question)
    response = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeSubmitPrompt",
            "conversation_id": conversation_id,
            "workspace_roots": ["C:/proj"],
            "prompt": "Continue the goal.",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"continue": True}
