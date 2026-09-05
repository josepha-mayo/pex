from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.http_json import MemoryHttpTransport
from pex_bridge.adapters.opencode import OpenCodeAdapter
from pex_bridge.adapters.opencode_outcomes import (
    OPENCODE_MESSAGE_LINEAGE_KEY,
    event_matches_opencode_delivery,
)
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import EventPhase, EventType, HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession


def _session(vendor_id: str = "session-one") -> HarnessSession:
    return HarnessSession(
        id=f"opencode:{vendor_id}",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id=vendor_id,
        cwd="C:/project",
        project_id="C:/project",
        goal_id="goal-one",
        status=SessionStatus.WORKING,
    )


def _adapter_session(vendor_id: str = "session-one") -> tuple[OpenCodeAdapter, HarnessSession]:
    adapter = OpenCodeAdapter(MemoryHttpTransport())
    session = _session(vendor_id)
    adapter.sessions[session.id] = session
    return adapter, session


def _intervention(session: HarnessSession, admitted_id: str = "user-pex") -> Intervention:
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=session.id,
        goal_id=session.goal_id,
        payload={"text": "Inspect the missing evidence."},
        rationale="The goal is not verified.",
        evidence=["report missing"],
    )
    return Intervention(
        id="intervention-one",
        session_id=session.id,
        goal_id=session.goal_id,
        trigger=EventType.STOP.value,
        evidence=list(action.evidence),
        diagnosis="Missing evidence.",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="sent",
        outcome="worker_delivery_observed",
        created_at=datetime.now(UTC),
        metadata={
            "effect_state": "delivered",
            "worker_delivery_receipt": {
                "schema": "pex.worker-delivery.v1",
                "target_session_id": session.id,
                "vendor_session_id": session.vendor_session_id,
                "vendor_turn_id": admitted_id,
            },
        },
    )


def _human_decision_intervention(session: HarnessSession) -> Intervention:
    action = ProposedAction(
        type=InterventionType.ASK_HUMAN,
        session_id=session.id,
        goal_id=session.goal_id,
        payload={"question": "Which branch?"},
        rationale="A consequential choice is required.",
        evidence=["two valid branches"],
    )
    return Intervention(
        id="human-intervention",
        session_id=session.id,
        goal_id=session.goal_id,
        trigger=EventType.STOP.value,
        evidence=list(action.evidence),
        diagnosis="Human decision required.",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ASK_HUMAN,
        result="human_decision_delivered",
        outcome="human_decision_delivered",
        created_at=datetime.now(UTC),
        metadata={
            "human_decision_resolution": {"status": "delivered"},
            "worker_delivery_receipt": {
                "schema": "pex.worker-delivery.v1",
                "target_session_id": session.id,
                "vendor_session_id": session.vendor_session_id,
                "vendor_turn_id": "user-pex",
            },
        },
    )
def _assistant_payload(
    session: HarnessSession,
    *,
    message_id: object = "assistant-one",
    parent_id: object = "user-pex",
) -> dict:
    return {
        "type": "message.updated",
        "properties": {
            "info": {
                "id": message_id,
                "sessionID": session.vendor_session_id,
                "role": "assistant",
                "parentID": parent_id,
            },
            "cwd": session.cwd,
        },
    }


def test_exact_assistant_parent_matches_admitted_pex_message() -> None:
    adapter, session = _adapter_session()
    event = adapter.normalize_sse(session, _assistant_payload(session))

    assert event_matches_opencode_delivery(_intervention(session), session, event) is True
    assert event.metadata[OPENCODE_MESSAGE_LINEAGE_KEY] == {
        "schema": "pex.opencode-message-lineage.v1",
        "target_session_id": session.id,
        "vendor_session_id": session.vendor_session_id,
        "message_id": "assistant-one",
        "role": "assistant",
        "parent_message_id": "user-pex",
        "source_event_type": "message.updated",
        "stream_contiguous": True,
        "parent_removed_observed": False,
        "assistant_message_completed": False,
        "assistant_message_error": False,
        "assistant_finish": "",
    }


def test_exact_descendant_of_delivered_human_decision_matches() -> None:
    adapter, session = _adapter_session()
    event = adapter.normalize_sse(session, _assistant_payload(session))

    assert (
        event_matches_opencode_delivery(
            _human_decision_intervention(session), session, event
        )
        is True
    )


def test_delivered_human_decision_remains_lineage_bound_after_intermediate_update() -> None:
    adapter, session = _adapter_session()
    event = adapter.normalize_sse(session, _assistant_payload(session))
    intervention = _human_decision_intervention(session)
    intervention.outcome = "worker_responded"

    assert event_matches_opencode_delivery(intervention, session, event) is True


def test_assistant_part_inherits_only_an_observed_exact_parent() -> None:
    adapter, session = _adapter_session()
    adapter.normalize_sse(session, _assistant_payload(session))
    part = adapter.normalize_sse(
        session,
        {
            "type": "message.part.updated",
            "properties": {
                "part": {
                    "id": "part-one",
                    "sessionID": session.vendor_session_id,
                    "messageID": "assistant-one",
                    "type": "tool",
                    "tool": "bash",
                    "state": {"status": "completed", "input": {}, "output": "ok"},
                },
                "cwd": session.cwd,
            },
        },
    )

    assert part.event_type == EventType.TOOL_RESULT
    assert event_matches_opencode_delivery(_intervention(session), session, part) is True
    assert part.metadata[OPENCODE_MESSAGE_LINEAGE_KEY]["source_event_type"] == (
        "message.part.updated"
    )


@pytest.mark.parametrize(
    "parent_id", ["human-concurrent", "user-old", " user-pex ", "", None, 17]
)
def test_unrelated_absent_or_malformed_parent_never_matches(parent_id: object) -> None:
    adapter, session = _adapter_session()
    event = adapter.normalize_sse(
        session,
        _assistant_payload(session, parent_id=parent_id),
    )

    assert event_matches_opencode_delivery(_intervention(session), session, event) is False
    if parent_id in {" user-pex ", "", None, 17}:
        assert OPENCODE_MESSAGE_LINEAGE_KEY not in event.metadata


def test_noncanonical_message_role_cannot_form_terminal_lineage() -> None:
    adapter, session = _adapter_session()
    payload = _assistant_payload(session)
    payload["properties"]["info"]["role"] = "Assistant"
    payload["properties"]["info"]["time"] = {"created": 10, "completed": 20}
    payload["properties"]["info"]["finish"] = "stop"
    event = adapter.normalize_sse(session, payload)

    assert event.event_type == EventType.AGENT_RESPONSE
    assert OPENCODE_MESSAGE_LINEAGE_KEY not in event.metadata


@pytest.mark.parametrize("message_id", ["", " ", " msg-prompt "])
def test_noncanonical_admission_id_is_not_a_worker_receipt(message_id: str) -> None:
    turn_id = OpenCodeAdapter._matching_new_prompt_id(
        [
            {
                "info": {
                    "id": message_id,
                    "role": "user",
                    "sessionID": "session-one",
                },
                "parts": [{"type": "text", "text": "Continue."}],
            }
        ],
        "Continue.",
        prior_message_ids=set(),
        vendor_session_id="session-one",
    )

    assert turn_id is None


def test_concurrent_human_prompt_and_its_child_do_not_match() -> None:
    adapter, session = _adapter_session()
    human_prompt = adapter.normalize_sse(
        session,
        {
            "type": "message.updated",
            "properties": {
                "info": {
                    "id": "user-human",
                    "sessionID": session.vendor_session_id,
                    "role": "user",
                },
                "cwd": session.cwd,
            },
        },
    )
    human_child = adapter.normalize_sse(
        session,
        _assistant_payload(session, message_id="assistant-human", parent_id="user-human"),
    )

    intervention = _intervention(session)
    assert event_matches_opencode_delivery(intervention, session, human_prompt) is False
    assert event_matches_opencode_delivery(intervention, session, human_child) is False


def test_idle_and_unrelated_activity_do_not_inherit_last_message_lineage() -> None:
    adapter, session = _adapter_session()
    adapter.normalize_sse(session, _assistant_payload(session))
    idle = adapter.normalize_sse(
        session,
        {
            "type": "session.idle",
            "properties": {"sessionID": session.vendor_session_id, "cwd": session.cwd},
        },
    )

    assert idle.event_type == EventType.STOP
    assert OPENCODE_MESSAGE_LINEAGE_KEY not in idle.metadata
    assert event_matches_opencode_delivery(_intervention(session), session, idle) is False


def test_idle_after_exact_terminal_is_not_a_second_stop() -> None:
    adapter, session = _adapter_session()
    payload = _assistant_payload(session)
    payload["properties"]["info"]["time"] = {"created": 10, "completed": 20}
    payload["properties"]["info"]["finish"] = "stop"
    terminal = adapter.normalize_sse(session, payload)
    idle_payload = {
        "type": "session.idle",
        "properties": {"sessionID": session.vendor_session_id, "cwd": session.cwd},
    }
    first_idle = adapter.normalize_sse(session, idle_payload)
    repeated_idle = adapter.normalize_sse(session, idle_payload)

    assert terminal.event_type == EventType.STOP
    assert first_idle.event_type == EventType.STATUS
    assert first_idle.phase == EventPhase.AFTER
    assert repeated_idle.event_type == EventType.STATUS


def test_duplicate_final_sibling_for_same_parent_is_not_a_second_stop() -> None:
    adapter, session = _adapter_session()
    first_payload = _assistant_payload(session, message_id="assistant-first")
    first_payload["properties"]["info"]["time"] = {"created": 10, "completed": 20}
    first_payload["properties"]["info"]["finish"] = "stop"
    duplicate_payload = _assistant_payload(session, message_id="assistant-duplicate")
    duplicate_payload["properties"]["info"]["time"] = {
        "created": 21,
        "completed": 22,
    }
    duplicate_payload["properties"]["info"]["finish"] = "stop"

    first = adapter.normalize_sse(session, first_payload)
    duplicate = adapter.normalize_sse(session, duplicate_payload)

    assert first.event_type == EventType.STOP
    assert duplicate.event_type == EventType.STATUS
    assert duplicate.phase == EventPhase.AFTER
    assert event_matches_opencode_delivery(
        _intervention(session), session, duplicate
    ) is False


def test_new_user_prompt_restores_idle_fallback_for_the_new_turn() -> None:
    adapter, session = _adapter_session()
    payload = _assistant_payload(session)
    payload["properties"]["info"]["time"] = {"created": 10, "completed": 20}
    payload["properties"]["info"]["finish"] = "stop"
    adapter.normalize_sse(session, payload)
    adapter.normalize_sse(
        session,
        {
            "type": "message.updated",
            "properties": {
                "info": {
                    "id": "user-next",
                    "sessionID": session.vendor_session_id,
                    "role": "user",
                },
                "cwd": session.cwd,
            },
        },
    )
    idle = adapter.normalize_sse(
        session,
        {
            "type": "session.idle",
            "properties": {"sessionID": session.vendor_session_id, "cwd": session.cwd},
        },
    )

    assert idle.event_type == EventType.STOP
    assert idle.phase == EventPhase.TERMINAL


def test_transport_replacement_invalidates_terminal_idle_suppression() -> None:
    adapter, session = _adapter_session()
    payload = _assistant_payload(session)
    payload["properties"]["info"]["time"] = {"created": 10, "completed": 20}
    payload["properties"]["info"]["finish"] = "stop"
    adapter.normalize_sse(session, payload)

    adapter.attach_transport(MemoryHttpTransport())
    idle = adapter.normalize_sse(
        session,
        {
            "type": "session.idle",
            "properties": {"sessionID": session.vendor_session_id, "cwd": session.cwd},
        },
    )

    assert idle.event_type == EventType.STOP
    assert idle.phase == EventPhase.TERMINAL


@pytest.mark.asyncio
async def test_admitted_pex_prompt_restores_idle_fallback_before_user_sse() -> None:
    adapter, session = _adapter_session()
    payload = _assistant_payload(session)
    payload["properties"]["info"]["time"] = {"created": 10, "completed": 20}
    payload["properties"]["info"]["finish"] = "stop"
    adapter.normalize_sse(session, payload)

    result = await adapter.send_message(session, "Continue with exact evidence.")
    idle = adapter.normalize_sse(
        session,
        {
            "type": "session.idle",
            "properties": {"sessionID": session.vendor_session_id, "cwd": session.cwd},
        },
    )

    assert result is not False
    assert idle.event_type == EventType.STOP
    assert idle.phase == EventPhase.TERMINAL


def test_completed_assistant_message_is_exact_terminal_for_its_parent() -> None:
    adapter, session = _adapter_session()
    payload = _assistant_payload(session)
    payload["properties"]["info"]["time"] = {"created": 10, "completed": 20}
    payload["properties"]["info"]["finish"] = "stop"
    terminal = adapter.normalize_sse(session, payload)

    assert terminal.event_type == EventType.STOP
    assert terminal.phase == EventPhase.TERMINAL
    lineage = terminal.metadata[OPENCODE_MESSAGE_LINEAGE_KEY]
    assert lineage["assistant_message_completed"] is True
    assert lineage["assistant_message_error"] is False
    assert lineage["assistant_finish"] == "stop"
    assert event_matches_opencode_delivery(_intervention(session), session, terminal) is True


@pytest.mark.asyncio
async def test_pipeline_attributes_verified_terminal_only_through_exact_parent(
    tmp_path,
) -> None:
    now = datetime.now(UTC)
    project = str(tmp_path)
    session = _session().model_copy(update={"cwd": project, "project_id": project})
    adapter = OpenCodeAdapter(MemoryHttpTransport())
    adapter.sessions[session.id] = session
    intervention = _intervention(session)
    payload = _assistant_payload(session)
    payload["properties"]["info"]["time"] = {"created": 10, "completed": 20}
    payload["properties"]["info"]["finish"] = "stop"
    terminal = adapter.normalize_sse(session, payload)

    store = Store(tmp_path / "opencode-lineage.sqlite")
    await store.connect()
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(home=tmp_path, require_auth=False),
    )
    try:
        await store.upsert_goal(
            Goal(
                id="goal-one",
                project_id=project,
                title="Finish the task",
                objective="Produce verified evidence.",
                created_at=now,
                updated_at=now,
            )
        )
        await store.upsert_session(session)
        await store.add_intervention(intervention)

        updates = await pipeline._observe_prior_intervention(
            session,
            terminal,
            {"status": "supported", "acceptance_status": "supported"},
        )

        assert len(updates) == 1
        assert updates[0].outcome == "goal_evidence_supported"
        assert updates[0].helped is True
        assert updates[0].metadata["outcome_event_ids"] == [terminal.event_id]
    finally:
        await store.close()


@pytest.mark.parametrize(
    "time_info",
    [
        {},
        {"created": 10},
        {"created": 10, "completed": True},
        {"created": 10, "completed": 9},
    ],
)
def test_malformed_or_incomplete_completion_is_not_terminal(time_info: dict) -> None:
    adapter, session = _adapter_session()
    payload = _assistant_payload(session)
    payload["properties"]["info"]["time"] = time_info
    payload["properties"]["info"]["finish"] = "stop"
    event = adapter.normalize_sse(session, payload)

    assert event.event_type == EventType.AGENT_RESPONSE
    assert event.metadata[OPENCODE_MESSAGE_LINEAGE_KEY][
        "assistant_message_completed"
    ] is False


def test_stop_finish_without_required_parent_is_not_terminal() -> None:
    adapter, session = _adapter_session()
    payload = _assistant_payload(session, parent_id=None)
    payload["properties"]["info"]["time"] = {"created": 10, "completed": 20}
    payload["properties"]["info"]["finish"] = "stop"
    event = adapter.normalize_sse(session, payload)

    assert event.event_type == EventType.AGENT_RESPONSE
    assert event.phase == EventPhase.AFTER
    assert OPENCODE_MESSAGE_LINEAGE_KEY not in event.metadata


@pytest.mark.parametrize(
    "finish", ["tool-calls", "unknown", "length", "error", "STOP", " stop ", ""]
)
def test_nonfinal_finish_reason_is_not_terminal(finish: str) -> None:
    adapter, session = _adapter_session()
    payload = _assistant_payload(session)
    payload["properties"]["info"]["time"] = {"created": 10, "completed": 20}
    payload["properties"]["info"]["finish"] = finish
    event = adapter.normalize_sse(session, payload)

    assert event.event_type == EventType.AGENT_RESPONSE
    lineage = event.metadata[OPENCODE_MESSAGE_LINEAGE_KEY]
    assert lineage["assistant_message_completed"] is False
    assert event_matches_opencode_delivery(_intervention(session), session, event) is True


def test_non_json_completion_timestamp_is_rejected() -> None:
    adapter, session = _adapter_session()
    payload = _assistant_payload(session)
    payload["properties"]["info"]["time"] = {
        "created": 10,
        "completed": float("inf"),
    }

    with pytest.raises(ValueError, match="JSON compliant"):
        adapter.normalize_sse(session, payload)


def test_assistant_error_is_lineage_bound_but_not_clean_completion() -> None:
    adapter, session = _adapter_session()
    payload = _assistant_payload(session)
    payload["properties"]["info"]["time"] = {"created": 10, "completed": 20}
    payload["properties"]["info"]["error"] = {
        "name": "MessageAbortedError",
        "data": {"message": "aborted"},
    }
    # Upstream can leave an earlier finish value on an aborted message. The
    # explicit error must win over that stale value without becoming success.
    payload["properties"]["info"]["finish"] = "stop"
    event = adapter.normalize_sse(session, payload)

    assert event.event_type == EventType.ERROR
    lineage = event.metadata[OPENCODE_MESSAGE_LINEAGE_KEY]
    assert lineage["assistant_message_completed"] is False
    assert lineage["assistant_message_error"] is True
    assert event_matches_opencode_delivery(_intervention(session), session, event) is True


def test_part_after_cache_loss_has_no_authoritative_lineage() -> None:
    adapter, session = _adapter_session()
    part = adapter.normalize_sse(
        session,
        {
            "type": "message.part.updated",
            "properties": {
                "part": {
                    "id": "part-one",
                    "sessionID": session.vendor_session_id,
                    "messageID": "assistant-one",
                    "type": "text",
                    "text": "continuing",
                },
                "cwd": session.cwd,
            },
        },
    )

    assert OPENCODE_MESSAGE_LINEAGE_KEY not in part.metadata
    assert event_matches_opencode_delivery(_intervention(session), session, part) is False


def test_malformed_full_update_clears_prior_parent_before_later_part() -> None:
    adapter, session = _adapter_session()
    adapter.normalize_sse(session, _assistant_payload(session))
    malformed = adapter.normalize_sse(
        session,
        _assistant_payload(session, parent_id=None),
    )
    part = adapter.normalize_sse(
        session,
        {
            "type": "message.part.updated",
            "properties": {
                "part": {
                    "id": "part-after-malformed",
                    "sessionID": session.vendor_session_id,
                    "messageID": "assistant-one",
                    "type": "text",
                    "text": "unbound continuation",
                },
                "cwd": session.cwd,
            },
        },
    )

    assert OPENCODE_MESSAGE_LINEAGE_KEY not in malformed.metadata
    assert OPENCODE_MESSAGE_LINEAGE_KEY not in part.metadata
    assert event_matches_opencode_delivery(_intervention(session), session, part) is False


def test_retention_gap_marks_even_exact_parent_non_authoritative() -> None:
    adapter, session = _adapter_session()
    adapter._event_gap_detected = True
    event = adapter.normalize_sse(session, _assistant_payload(session))

    assert event.metadata[OPENCODE_MESSAGE_LINEAGE_KEY]["stream_contiguous"] is False
    assert event_matches_opencode_delivery(_intervention(session), session, event) is False


def test_observed_parent_removal_invalidates_later_orphaned_assistant() -> None:
    adapter, session = _adapter_session()
    adapter.normalize_sse(
        session,
        {
            "type": "message.removed",
            "properties": {
                "sessionID": session.vendor_session_id,
                "messageID": "user-pex",
                "cwd": session.cwd,
            },
        },
    )
    event = adapter.normalize_sse(session, _assistant_payload(session))

    assert event.metadata[OPENCODE_MESSAGE_LINEAGE_KEY]["parent_removed_observed"] is True
    assert event_matches_opencode_delivery(_intervention(session), session, event) is False


def test_removal_tombstone_exhaustion_marks_stream_gap(monkeypatch) -> None:
    monkeypatch.setattr("pex_bridge.adapters.opencode.MAX_MESSAGE_ROLES", 1)
    adapter, session = _adapter_session()
    for message_id in ("removed-one", "removed-two"):
        adapter.normalize_sse(
            session,
            {
                "type": "message.removed",
                "properties": {
                    "sessionID": session.vendor_session_id,
                    "messageID": message_id,
                    "cwd": session.cwd,
                },
            },
        )

    event = adapter.normalize_sse(session, _assistant_payload(session))

    assert event.metadata[OPENCODE_MESSAGE_LINEAGE_KEY]["stream_contiguous"] is False
    assert event_matches_opencode_delivery(_intervention(session), session, event) is False


def test_cross_session_project_goal_and_receipt_bindings_fail_closed() -> None:
    adapter, session = _adapter_session()
    event = adapter.normalize_sse(session, _assistant_payload(session))
    intervention = _intervention(session)

    foreign = _session("session-two")
    assert event_matches_opencode_delivery(intervention, foreign, event) is False
    assert event_matches_opencode_delivery(
        intervention,
        session.model_copy(update={"project_id": "C:/other"}),
        event,
    ) is False
    assert event_matches_opencode_delivery(
        intervention.model_copy(
            update={
                "metadata": {
                    **intervention.metadata,
                    "worker_delivery_receipt": {
                        **intervention.metadata["worker_delivery_receipt"],
                        "vendor_session_id": "session-two",
                    },
                }
            }
        ),
        session,
        event,
    ) is False


@pytest.mark.parametrize("result", ["send_failed", "send_delivery_uncertain", None])
def test_unaccepted_or_uncertain_delivery_result_never_matches(result: str | None) -> None:
    adapter, session = _adapter_session()
    event = adapter.normalize_sse(session, _assistant_payload(session))
    intervention = _intervention(session).model_copy(update={"result": result})

    assert event_matches_opencode_delivery(intervention, session, event) is False


def test_forged_or_incomplete_lineage_mapping_fails_closed() -> None:
    _, session = _adapter_session()
    event = HarnessEvent(
        event_id="forged-event",
        ts=datetime.now(UTC),
        harness_type=HarnessType.OPENCODE,
        session_id=session.id,
        project_id=session.project_id,
        goal_id=session.goal_id,
        event_type=EventType.AGENT_RESPONSE,
        phase=EventPhase.AFTER,
        metadata={
            OPENCODE_MESSAGE_LINEAGE_KEY: {
                "schema": "pex.opencode-message-lineage.v1",
                "target_session_id": session.id,
                "vendor_session_id": session.vendor_session_id,
                "message_id": "assistant-one",
                "role": "assistant",
                "parent_message_id": "user-pex",
                "source_event_type": "message.updated",
                "stream_contiguous": True,
                # parent_removed_observed is intentionally absent.
                "assistant_message_completed": False,
                "assistant_message_error": False,
                "assistant_finish": "",
            }
        },
    )

    assert event_matches_opencode_delivery(_intervention(session), session, event) is False
