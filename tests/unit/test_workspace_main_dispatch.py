"""Real publication/Store/Pipeline dispatch receipts with an explicit fake worker."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pex_bridge.adapters.base import AdapterMessageResult
from pex_bridge.store import utcnow
from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.enums import EventType
from pex_protocol.session import HarnessEvent
from test_event_processing_store import _plan_envelope, _planned_intervention
from test_workspace_continuity_pipeline import _change_workspace
from test_workspace_continuity_pipeline import bound_pipeline as bound_pipeline


@pytest.mark.parametrize("change", [None, "directory", "origin"])
async def test_main_marker_refusal_is_terminal_failed_not_stranded(
    bound_pipeline,
    monkeypatch,
    change,
):
    bound = bound_pipeline
    store = bound.store
    session = await store.get_session(bound.adapter.session.id)
    # Only this isolated fake worker supports sends. The actual shared adapter's
    # capabilities/implementation remain observe-only and are not modified.
    session.capabilities = AdapterCapabilities(send_message=True).model_dump(mode="json")
    await store.upsert_session(session)
    fake = SimpleNamespace(
        send_message=AsyncMock(
            return_value=AdapterMessageResult(
                accepted=True,
                vendor_session_id=session.vendor_session_id,
                vendor_turn_id="fake-accepted-turn",
            )
        ),
    )
    bound.pipeline.adapters.bind("codex", fake)
    try:
        event = HarnessEvent(
            event_id="workspace-main-dispatch",
            ts=utcnow(),
            harness_type=session.harness_type,
            session_id=session.id,
            project_id=session.project_id,
            goal_id=session.goal_id,
            event_type=EventType.AGENT_RESPONSE,
            message_delta="Bounded dispatch fixture",
        )
        await store.accept_pipeline_event(event, session_snapshot=session)
        owner = "workspace-main-review"
        await store.claim_event_processing(event.event_id, owner=owner)
        intervention = _planned_intervention(event)
        intervention.proposed_action.payload = {"text": "One evidence-backed continuation"}
        payload = await store.prepare_main_effect_payload(
            event_id=event.event_id,
            intervention_id=intervention.id,
            action=intervention.proposed_action.model_dump(mode="json"),
            required_capability="send_message",
        )
        await store.commit_event_plan(
            event_id=event.event_id,
            owner=owner,
            plan=_plan_envelope(
                event,
                intervention=intervention,
                effect_kind="worker_action",
                required_capability="send_message",
            ),
            session=session,
            intervention=intervention,
            main_effect={
                "effect_key": "main",
                "kind": "worker_action",
                "target_session_id": session.id,
                "payload": payload,
                "request_hash": hashlib.sha256(
                    json.dumps(
                        payload,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
            },
        )
        original = store.claim_main_event_effect
        grants = []

        async def claim_then_change(*args, **kwargs):
            claimed = await original(*args, **kwargs)
            assert claimed["granted"] is True
            assert claimed["effect"]["state"] == "dispatching"
            grants.append(claimed)
            if change is not None:
                _change_workspace(bound, change)
            return claimed

        monkeypatch.setattr(store, "claim_main_event_effect", claim_then_change)
        processing = await store.get_event_processing(event.event_id)
        await bound.pipeline._resume_planned_event(processing, owner=owner)
        assert len(grants) == 1
        terminal = await store.get_event_effect(event.event_id, "main")
        assert terminal["dispatch_started_at"] is not None
        completed = await store.get_event_processing(event.event_id)
        assert completed["state"] == "complete"
        recorded = await store.get_intervention(intervention.id)
        if change is None:
            fake.send_message.assert_awaited_once()
            assert terminal["state"] == "delivered"
            assert recorded.result == "sent"
            assert (
                terminal["result"]["worker_delivery_receipt"]["vendor_turn_id"]
                == "fake-accepted-turn"
            )
        else:
            fake.send_message.assert_not_awaited()
            assert terminal["state"] == "failed"
            assert terminal["result"]["code"] == "workspace_authority_changed"
            assert recorded.result == "workspace_authority_changed"
            assert recorded.metadata["effect_state"] == "failed"
            assert "worker_delivery_receipt" not in terminal["result"]
        # Replaying the terminal Pipeline head cannot reclaim or redeliver.
        await bound.pipeline._resume_planned_event(completed, owner=owner)
        assert len(grants) == 1
        assert fake.send_message.await_count == (1 if change is None else 0)
    finally:
        bound.pipeline.adapters.bind("codex", bound.adapter)
