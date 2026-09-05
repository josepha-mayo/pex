"""Real published Store, adapter receiver/bootstrap, and Pipeline; fake vendor only."""

from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace

import pytest
from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.codex_input_provenance import CodexInputProvenance
from pex_protocol.enums import EventType
from test_codex_correction_store import attempt, prepare
from test_codex_subscription import _notification
from test_workspace_continuity_pipeline import bound_pipeline as _bound_pipeline_fixture


@pytest.fixture
async def echo_pipeline(tmp_path, monkeypatch):
    # Delay the actual receiver's initial Store load until this test has a
    # durable attempted correction to recover. No production file is patched.
    release = asyncio.Event()
    loaded = asyncio.Event()
    bootstrap = SimpleNamespace(fail=False, calls=0)
    original_start = CodexSharedAdapter.start_pipeline_pump

    def start_with_store_bootstrap(adapter, ingest, **kwargs):
        pipeline = ingest.__self__

        async def loader(session):
            bootstrap.calls += 1
            await release.wait()
            if bootstrap.fail:
                raise OSError("fixture attribution store unavailable")
            records = await pipeline.store.list_codex_correction_attributions(session)
            loaded.set()
            return records

        kwargs["provenance_loader"] = loader
        return original_start(adapter, ingest, **kwargs)

    monkeypatch.setattr(CodexSharedAdapter, "start_pipeline_pump", start_with_store_bootstrap)
    generator = _bound_pipeline_fixture.__wrapped__(tmp_path, monkeypatch)
    bound = await anext(generator)
    try:
        session = await bound.store.get_session(bound.adapter.session.id)
        # The sole attempt is a Store fixture, never a worker call. Real shared
        # capability probes remain disabled throughout the actual event pump.
        session.capabilities["send_message"] = True
        await bound.store.upsert_session(session)
        session = await bound.store.get_session(session.id)
        publication = (bound.store, session, bound.workspace_binding, bound.origin_path)
        fixture = (bound.store, session, publication)
        prepared = await prepare(fixture, event_id="prior-correction-attempt")
        effect = await attempt(fixture, prepared)
        await bound.pipeline._seal_main_event_effect(
            processing=await bound.store.get_event_processing(prepared[0].event_id),
            effect=effect, reserved=prepared[1], session=session,
            outcome="send_delivery_uncertain", effect_state="delivery_uncertain",
            code="fixture_prior_attempt_uncertain", publish=False,
        )
        # The Store result is real; no vendor delivery is being asserted.
        assert (await bound.store.get_event_processing(prepared[0].event_id))["state"] == "complete"
        yield SimpleNamespace(
            bound=bound, correction=prepared[2]["codex_correction"],
            release=release, loaded=loaded, bootstrap=bootstrap,
        )
    finally:
        release.set()
        await generator.aclose()


def item_for(case, *, item_id="correction-item", client_id=None, text=None):
    content = copy.deepcopy(case.correction["content"])
    if text is not None:
        content[0]["text"] = text
    return {
        "type": "userMessage", "id": item_id,
        "clientId": case.correction["client_message_id"] if client_id is None else client_id,
        "content": content,
    }


def enqueue(case, item):
    case.bound.transport.notifications.append(_notification("item/completed", {
        "threadId": case.bound.adapter.session.vendor_session_id,
        "turnId": "turn-1", "item": item,
    }))


async def settled(case, item_id):
    async def wait():
        while True:
            events = await case.bound.store.recent_events(case.bound.adapter.session.id)
            for event in events:
                marker = event.metadata.get("pex_correction_observation") or {}
                matches = marker.get("vendor_item_id") == item_id
                if not matches and event.event_type == EventType.USER_PROMPT:
                    # This fixture emits exactly one external input. Shared
                    # normalizer references use hashed record IDs, not raw IDs.
                    matches = event.metadata.get("source") == "codex_shared_live_notification"
                if matches:
                    processing = await case.bound.store.get_event_processing(event.event_id)
                    if processing["state"] in {"complete", "failed", "record_only_complete"}:
                        return event, processing
            if case.bound.task.done():
                raise AssertionError(f"pump stopped: {case.bound.adapter.last_pump_error}")
            await asyncio.sleep(0.01)

    return await asyncio.wait_for(wait(), timeout=10)


async def test_receiver_loads_durable_history_then_records_exact_echo_without_supervisor(
    echo_pipeline,
):
    case = echo_pipeline
    before = await case.bound.store.get_session_control_state(case.bound.adapter.session.id)
    goal = await case.bound.store.get_goal(case.bound.adapter.session.goal_id)
    enqueue(case, item_for(case))
    case.release.set()
    await asyncio.wait_for(case.loaded.wait(), timeout=5)
    event, processing = await settled(case, "correction-item")
    assert case.bootstrap.calls == 1
    assert isinstance(case.bound.adapter._input_provenance, CodexInputProvenance)
    assert event.event_type == EventType.STATUS and event.message_delta is None
    assert processing["mode"] == "record_only" and processing["state"] == "record_only_complete"
    assert case.bound.supervisor_calls == []
    assert case.bound.adapter.input_revision == 0
    assert await case.bound.store.get_session_control_state(case.bound.adapter.session.id) == before
    assert await case.bound.store.get_goal(goal.id) == goal
    assert await case.bound.store.get_event_effect(event.event_id, "planner") is None
    assert case.bound.adapter._correction_items == {}


@pytest.mark.parametrize("kind", ["external_prefix", "conflicting_known"])
async def test_external_input_not_suppressed_and_conflicting_known_cannot_become_override(
    echo_pipeline, kind,
):
    case = echo_pipeline
    session_id = case.bound.adapter.session.id
    before_goal = await case.bound.store.get_goal(case.bound.adapter.session.goal_id)
    item = item_for(
        case, item_id="different-input",
        client_id="pex-correction-not-owned" if kind == "external_prefix" else None,
        text="Please inspect the public artifact against the existing task criteria.",
    )
    enqueue(case, item)
    case.release.set()
    event, processing = await settled(case, item["id"])
    assert event.event_type == EventType.USER_PROMPT
    assert "pex_correction_observation" not in event.metadata
    assert processing["mode"] == "pipeline"
    assert case.bound.adapter.input_revision == 1
    assert len(case.bound.supervisor_calls) == 1
    assert (await case.bound.store.get_session(session_id)).goal_id == before_goal.id
    assert await case.bound.store.get_goal(before_goal.id) == before_goal
    if kind == "conflicting_known":
        assert event.metadata["content_status"] == "uncertain_input_provenance"
        assert await case.bound.store.list_decisions(before_goal.id) == []
    else:
        assert event.metadata["content_status"] == "complete"


async def test_failed_bootstrap_closes_before_any_human_normalization_or_inference(echo_pipeline):
    case = echo_pipeline
    case.bootstrap.fail = True
    goal = await case.bound.store.get_goal(case.bound.adapter.session.goal_id)
    enqueue(case, item_for(case))
    case.release.set()
    await asyncio.wait_for(asyncio.shield(case.bound.task), timeout=5)
    assert case.bootstrap.calls == 1
    assert case.bound.adapter._input_provenance is None
    assert case.bound.adapter._invalid
    assert case.bound.transport.closed
    assert case.bound.supervisor_calls == []
    assert case.bound.adapter.input_revision == 0
    events = await case.bound.store.recent_events(case.bound.adapter.session.id)
    assert not any(event.event_type == EventType.USER_PROMPT for event in events)
    assert not any("pex_correction_observation" in event.metadata for event in events)
    assert await case.bound.store.get_goal(goal.id) == goal


async def test_generic_ingest_cannot_inject_correction_marker(echo_pipeline):
    case = echo_pipeline
    event = (await case.bound.store.recent_events(case.bound.adapter.session.id))[0]
    forged = event.model_copy(deep=True)
    forged.event_id = "untrusted-correction-marker"
    forged.event_type = EventType.STATUS
    forged.metadata["pex_correction_observation"] = {"effect_id": case.correction["effect_id"]}
    with pytest.raises(ValueError, match="internal ingestion path"):
        await case.bound.pipeline.ingest_event(forged, case.bound.adapter.session)
    assert await case.bound.store.get_event(forged.event_id) is None
    assert case.bound.supervisor_calls == []


async def test_one_correction_id_on_two_vendor_items_is_uncertain_not_two_owned_echoes(
    echo_pipeline,
):
    case = echo_pipeline
    goal = await case.bound.store.get_goal(case.bound.adapter.session.goal_id)
    enqueue(case, item_for(case))
    case.release.set()
    first, first_processing = await settled(case, "correction-item")
    assert first.event_type == EventType.STATUS
    assert first_processing["state"] == "record_only_complete"
    enqueue(case, item_for(case, item_id="second-correction-item"))
    second, processing = await settled(case, "second-correction-item")
    assert second.event_id != first.event_id
    assert second.event_type == EventType.USER_PROMPT
    assert "pex_correction_observation" not in second.metadata
    assert second.metadata["content_status"] == "uncertain_input_provenance"
    assert processing["mode"] == "pipeline"
    assert case.bound.adapter.input_revision == 1
    assert await case.bound.store.get_goal(goal.id) == goal
    assert await case.bound.store.list_decisions(goal.id) == []


@pytest.mark.parametrize("kind", ["known_correction", "external_input"])
async def test_pending_start_waits_for_complete_input_before_supervision(echo_pipeline, kind):
    case = echo_pipeline
    goal = await case.bound.store.get_goal(case.bound.adapter.session.goal_id)
    item = item_for(
        case,
        client_id="ordinary-client-input" if kind == "external_input" else None,
        text="Please inspect the public result." if kind == "external_input" else None,
    )
    partial = copy.deepcopy(item)
    partial["content"] = []
    case.bound.transport.notifications.append(_notification("item/started", {
        "threadId": case.bound.adapter.session.vendor_session_id,
        "turnId": "turn-1", "item": partial,
    }))
    case.release.set()

    async def started_settled():
        while True:
            for event in await case.bound.store.recent_events(case.bound.adapter.session.id):
                if event.metadata.get("raw_method") == "item/started":
                    processing = await case.bound.store.get_event_processing(event.event_id)
                    if processing["state"] in {"complete", "failed", "record_only_complete"}:
                        return event
            if case.bound.task.done():
                raise AssertionError(f"pump stopped: {case.bound.adapter.last_pump_error}")
            await asyncio.sleep(0.01)

    started = await asyncio.wait_for(started_settled(), timeout=10)
    assert started.event_type == EventType.STATUS
    assert started.metadata["human_input_pending"] is True
    assert "pex_correction_observation" not in started.metadata
    assert (await case.bound.store.get_event_processing(started.event_id))["mode"] == "record_only"
    calls_after_started = len(case.bound.supervisor_calls)
    revision_after_started = case.bound.adapter.input_revision
    enqueue(case, item)
    completed, processing = await settled(case, item["id"])
    assert calls_after_started == 0
    if kind == "known_correction":
        assert completed.event_type == EventType.STATUS
        assert processing["mode"] == "record_only"
        assert case.bound.supervisor_calls == []
    else:
        assert revision_after_started > 0
        assert case.bound.adapter.input_revision > revision_after_started
        assert completed.event_type == EventType.USER_PROMPT
        assert completed.metadata["content_status"] == "complete"
        assert "pex_correction_observation" not in completed.metadata
        assert processing["mode"] == "pipeline"
        assert len(case.bound.supervisor_calls) == 1
    assert await case.bound.store.get_goal(goal.id) == goal
    assert await case.bound.store.list_decisions(goal.id) == []
