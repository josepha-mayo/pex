"""Frozen content-free input baseline metadata through actual temporary SQLite."""

import copy
from datetime import timedelta

import pytest
from test_observer_retention_store import retention as retention


def baseline(*, complete=True):
    return {
        "schema": "pex.codex-input-baseline.v1", "complete": complete,
        "digest": "a" * 64 if complete else None, "revision": 3,
        "external_count": 2, "pending_count": 0 if complete else 1,
        "reason": None if complete else "pending_input",
    }


async def save(retention, path, event):
    store, session, _, binding = retention
    if path == "accept":
        await store.accept_pipeline_event(event, session_snapshot=session)
        return await store.get_event(event.event_id)
    return (await store.retain_observer_events(
        (event,), session, expected_project_binding=binding,
    ))[0]


@pytest.mark.parametrize("path", ["accept", "retain"])
@pytest.mark.parametrize("kind", [
    "complete", "incomplete", "bounds", "incomplete_bounds", "legacy",
])
async def test_valid_baseline_is_preserved_without_session_projection(retention, path, kind):
    store, session, events, _ = retention
    event = events[0].model_copy(deep=True)
    snapshot = event.metadata["pex_observer_snapshot"]
    if kind != "legacy":
        snapshot["input_baseline"] = baseline(complete=not kind.startswith("incomplete"))
        if kind == "bounds":
            snapshot["input_baseline"].update(revision=2**63 - 1, external_count=4096)
        elif kind == "incomplete_bounds":
            snapshot["input_baseline"].update(
                revision=0, external_count=0, pending_count=4096, reason="x" * 160,
            )
    before = await store.get_session_control_state(session.id)
    saved = await save(retention, path, event)
    assert saved.metadata["pex_observer_snapshot"] == snapshot
    assert await store.get_session_control_state(session.id) == before
    assert "input_baseline" not in (await store.get_session(session.id)).metadata
    assert await store.get_event_effect(saved.event_id, "main") is None
    processing = await store.get_event_processing(saved.event_id)
    assert processing["mode"] == ("pipeline" if path == "accept" else "record_only")


INVALID = [
    ("schema", "other.v1"), ("complete", 1), ("complete", "true"),
    ("digest", "A" * 64), ("digest", "a" * 63), ("digest", "g" * 64),
    ("digest", None), ("digest", 4), ("revision", -1), ("revision", True),
    ("revision", 1.5), ("revision", 2**63), ("external_count", -1),
    ("external_count", 4097), ("external_count", True), ("external_count", 1.5),
    ("pending_count", -1), ("pending_count", 4097), ("pending_count", True),
    ("pending_count", 1), ("reason", "unexpected_reason"),
    ("reason", "x" * 161), ("content", [{"text": "raw input must never be stored here"}]),
]


@pytest.mark.parametrize("path", ["accept", "retain"])
@pytest.mark.parametrize(("field", "value"), INVALID)
async def test_invalid_baseline_is_rejected_before_any_event_write(retention, path, field, value):
    store, session, events, _ = retention
    event = events[0].model_copy(deep=True)
    value_snapshot = baseline()
    value_snapshot[field] = value
    event.metadata["pex_observer_snapshot"]["input_baseline"] = value_snapshot
    before = await store.get_session_control_state(session.id)
    with pytest.raises(ValueError):
        await save(retention, path, event)
    assert await store.get_event(event.event_id) is None
    assert await store.get_event_processing(event.event_id) is None
    assert await store.get_session_control_state(session.id) == before


@pytest.mark.parametrize("path", ["accept", "retain"])
@pytest.mark.parametrize("change", [
    "null", "missing", "no_reason", "digest_present", "long_reason", "reason_not_string",
])
async def test_incomplete_baseline_must_explicitly_preserve_uncertainty(retention, path, change):
    store, _, events, _ = retention
    event = events[0].model_copy(deep=True)
    value = baseline(complete=False)
    if change == "null":
        value = None
    elif change == "missing":
        del value["digest"]
    elif change == "no_reason":
        value["reason"] = ""
    elif change == "digest_present":
        value["digest"] = "a" * 64
    elif change == "long_reason":
        value["reason"] = "x" * 161
    else:
        value["reason"] = True
    event.metadata["pex_observer_snapshot"]["input_baseline"] = value
    with pytest.raises(ValueError):
        await save(retention, path, event)
    assert await store.get_event(event.event_id) is None


@pytest.mark.parametrize("path", ["accept", "retain"])
async def test_baseline_replay_preserves_first_snapshot_and_rejects_later_baseline(retention, path):
    store, _, events, _ = retention
    event = events[0].model_copy(deep=True)
    event.metadata["pex_observer_snapshot"]["input_baseline"] = baseline()
    original = await save(retention, path, event)
    processing = await store.get_event_processing(event.event_id)
    replay = original.model_copy(deep=True)
    replay.ts += timedelta(seconds=1)
    assert await save(retention, path, replay) == original
    changed = replay.model_copy(deep=True)
    changed.metadata["pex_observer_snapshot"]["input_baseline"]["revision"] += 1
    with pytest.raises(ValueError, match="collision"):
        await save(retention, path, changed)
    assert await store.get_event(event.event_id) == original
    assert await store.get_event_processing(event.event_id) == processing
    # The caller can subsequently edit its copy without altering durable evidence.
    event.metadata["pex_observer_snapshot"]["input_baseline"]["digest"] = "b" * 64
    assert await store.get_event(event.event_id) == original


@pytest.mark.parametrize("baseline_index", [0, 1])
async def test_mixed_legacy_and_baseline_retention_does_not_reuse_previous_keys(
    retention, baseline_index,
):
    store, session, events, binding = retention
    first, second = [event.model_copy(deep=True) for event in events]
    (first, second)[baseline_index].metadata["pex_observer_snapshot"]["input_baseline"] = baseline()
    saved = await store.retain_observer_events(
        (first, second), session, expected_project_binding=binding,
    )
    assert saved[baseline_index].metadata["pex_observer_snapshot"]["input_baseline"] == baseline()
    assert "input_baseline" not in saved[1 - baseline_index].metadata["pex_observer_snapshot"]


async def test_invalid_later_baseline_cannot_leave_earlier_retention_event(retention):
    store, session, events, binding = retention
    first, second = [event.model_copy(deep=True) for event in events]
    first.metadata["pex_observer_snapshot"]["input_baseline"] = baseline()
    second.metadata["pex_observer_snapshot"]["input_baseline"] = copy.deepcopy(baseline())
    second.metadata["pex_observer_snapshot"]["input_baseline"]["raw_items"] = ["private"]
    with pytest.raises(ValueError):
        await store.retain_observer_events(
            (first, second), session, expected_project_binding=binding,
        )
    assert await store.get_event(first.event_id) is None
    assert await store.get_event(second.event_id) is None
