"""Workspace fencing after a real claimed shared-Codex correction.

The fake boundary is only private vendor I/O. Pipeline planning, Store grant,
observer ingress, claim, settlement and replay are real and local.
"""

import pytest
from pex_bridge.workspace_binding import WorkspaceAuthorityError
from test_codex_correction_pipeline import (
    actual_observer_baseline_without_background_consumer,  # noqa: F401
    correction_bound_pipeline,  # noqa: F401
)
from test_codex_correction_pipeline import correction_pipeline as correction_pipeline  # noqa: F401
from test_workspace_continuity_pipeline import _change_workspace
from test_workspace_continuity_pipeline import bound_pipeline as bound_pipeline  # noqa: F401


@pytest.mark.parametrize("change", [None, "directory", "origin"])
async def test_main_marker_refusal_is_terminal_failed_not_stranded(
    correction_pipeline,  # noqa: F811
    monkeypatch,
    change,
):
    case = correction_pipeline
    store = case.store
    original = store.claim_main_event_effect
    grants = []

    async def claim_then_change(*args, **kwargs):
        claimed = await original(*args, **kwargs)
        assert claimed["granted"] is True
        assert claimed["effect"]["state"] == "dispatching"
        grants.append(claimed)
        if change is not None:
            _change_workspace(case.bound, change)
        return claimed

    monkeypatch.setattr(store, "claim_main_event_effect", claim_then_change)
    try:
        case.event = await case.ingest_observed()
    except WorkspaceAuthorityError:
        assert change is not None
        event_id = case.current_event[0].event_id
        case.event = await store.get_event(event_id)
        assert case.event is not None
    assert len(grants) == 1
    terminal = await store.get_event_effect(case.event.event_id, "main")
    assert terminal["dispatch_started_at"] is not None
    completed = await store.get_event_processing(case.event.event_id)
    assert completed["state"] == "complete"
    interventions = await store.list_interventions(case.session.id)
    assert len(interventions) == 1
    recorded = interventions[0]
    if change is None:
        case.private_dispatch.assert_awaited_once()
        assert terminal["state"] == "delivered"
        assert recorded.result == "sent"
        assert (
            terminal["result"]["worker_delivery_receipt"]["vendor_turn_id"]
            == "fixture-correction-turn"
        )
    else:
        case.private_dispatch.assert_not_awaited()
        assert terminal["state"] == "failed"
        assert terminal["result"]["code"] == "workspace_authority_changed"
        assert recorded.result == "workspace_authority_changed"
        assert recorded.metadata["effect_state"] == "failed"
        assert "worker_delivery_receipt" not in terminal["result"]
    case.generic_send.assert_not_awaited()
    case.generic_continue.assert_not_awaited()

    # Replaying the terminal Store head cannot reclaim or redeliver, even when
    # the workspace is no longer current.
    await case.pipeline._resume_planned_event(completed, owner=completed["lease_owner"] or "replay")
    assert len(grants) == 1
    assert case.private_dispatch.await_count == (1 if change is None else 0)
