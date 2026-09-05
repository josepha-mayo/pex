"""Pure prefix evidence, using real selected snapshots and fake transport only."""

import copy
from dataclasses import FrozenInstanceError, replace

import pytest
from pex_bridge import codex_input_baseline as baseline_module
from pex_bridge.adapters.codex_subscription import CodexExistingThreadSubscription
from pex_bridge.adapters.strict_json import strict_json_loads
from pex_bridge.codex_correction import canonical
from pex_bridge.codex_input_baseline import CodexInputBaseline
from pex_bridge.codex_input_provenance import CodexInputProvenance
from test_codex_input_provenance import record, text
from test_codex_subscription import FakeSharedTransport, _inspect, _thread_response


def user(item_id="human-1", value="Original instruction", client=None):
    return {"type": "userMessage", "id": item_id, "clientId": client, "content": text(value)}


def turn(items=None, **fields):
    return {"id": "turn-1", "status": "completed", "itemsView": "full",
            "items": [user()] if items is None else items, **fields}


async def selected(tmp_path, turns=None, **thread_fields):
    response = _thread_response(tmp_path, turns=[turn()] if turns is None else turns,
                                thread_update=thread_fields)
    transport = FakeSharedTransport([response], {})
    return await _inspect(CodexExistingThreadSubscription(transport), tmp_path)


def index(snapshot, *, correction=False):
    records = ()
    if correction:
        raw = record()
        raw["correction"].update(session_id=snapshot.pex_session_id, thread_id=snapshot.thread_id)
        records = (canonical(raw),)
    return CodexInputProvenance.from_store_records(
        records, session_id=snapshot.pex_session_id, thread_id=snapshot.thread_id,
    )


def entries(raw, turn_id="turn-1"):
    return [{"turn_id": turn_id, "item_id": value["id"],
             "client_id": value["clientId"], "content": value["content"]} for value in raw]


@pytest.mark.asyncio
async def test_selected_history_is_ordered_immutable_and_matches_fresh_classifier(tmp_path):
    inputs = [user("z"), user("a", "second")]
    seed = await selected(tmp_path, [turn(inputs), turn([user("z", "third")], id="turn-2")])
    provenance = index(seed)
    ledger = CodexInputBaseline.from_selected(seed, provenance)
    frozen = ledger.snapshot()
    expected = provenance.external_snapshot(
        entries(inputs) + entries([user("z", "third")], "turn-2"),
    )
    assert frozen.complete and frozen.revision == 0 and frozen.external_count == 3
    assert frozen.digest == expected.digest
    assert ledger._private_external_inputs().external_inputs_json == expected.external_inputs_json
    assert not hasattr(frozen, "raw") and not hasattr(frozen, "external_inputs_json")
    with pytest.raises(FrozenInstanceError):
        frozen.digest = "changed"
    ledger.observe_item(turn_id="turn-2", item=user("next"), completed=True)
    assert ledger.snapshot().revision == 1 and frozen.external_count == 3


@pytest.mark.asyncio
async def test_empty_history_and_active_observation_do_not_require_dispatch_capability(tmp_path):
    seed = await selected(tmp_path, [])
    assert CodexInputBaseline.from_selected(seed, index(seed)).snapshot().complete
    active = await selected(tmp_path, [turn(status="inProgress")])
    # Recording input history does not require permission to deliver control.
    active = replace(active, can_accept_direct_input=False)
    assert CodexInputBaseline.from_selected(active, index(active)).snapshot().complete


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"itemsView": "summary"}, {"status": "future"}, {"truncated": 1},
    {"hasMore": "false"}, {"redacted": True}, {"content_status": "partial"},
])
async def test_incomplete_seed_never_becomes_empty_complete_authority(tmp_path, change):
    seed = await selected(tmp_path, [turn(**change)])
    ledger = CodexInputBaseline.from_selected(seed, index(seed))
    result = ledger.snapshot()
    assert not result.complete and result.digest is None
    ledger.observe_item(turn_id="turn-1", item=user("new"), completed=True)
    assert not ledger.snapshot().complete


@pytest.mark.asyncio
@pytest.mark.parametrize("item", [
    {"type": "futureInput", "id": "unknown"}, {"type": "", "id": "unknown"},
    {"type": "reasoning", "id": "unknown", "truncated": "false"},
])
async def test_unknown_or_incomplete_nonuser_history_refuses_digest(tmp_path, item):
    seed = await selected(tmp_path, [turn([item])])
    assert not CodexInputBaseline.from_selected(seed, index(seed)).snapshot().complete


@pytest.mark.asyncio
async def test_selected_record_content_and_scope_not_only_ids_are_bound(tmp_path):
    seed = await selected(tmp_path)
    changed = replace(seed, history_content_digest="0" * 64)
    with pytest.raises(ValueError, match="inconsistent"):
        CodexInputBaseline.from_selected(changed, index(seed))
    changed = replace(seed, history_records=seed.history_records[:1])
    with pytest.raises(ValueError, match="inconsistent"):
        CodexInputBaseline.from_selected(changed, index(seed))
    with pytest.raises(ValueError, match="scope"):
        CodexInputBaseline.from_selected(replace(seed, thread_id="foreign"), index(seed))
    with pytest.raises(ValueError, match="selected history"):
        CodexInputBaseline.from_selected(seed.history_records, index(seed))


@pytest.mark.asyncio
async def test_exact_tuple_dedup_and_content_conflict_are_not_order_rewrites(tmp_path):
    seed = await selected(tmp_path)
    ledger = CodexInputBaseline.from_selected(seed, index(seed))
    first = ledger.snapshot()
    assert ledger.observe_item(turn_id="turn-1", item=user(), completed=True) == first
    extra = {**user(), "vendorExtra": "ignored ancillary metadata"}
    assert ledger.observe_item(turn_id="turn-1", item=extra, completed=True) == first
    changed = ledger.observe_item(turn_id="turn-1", item=user(value="different"), completed=True)
    assert not changed.complete and changed.reason == "input_tuple_conflict"
    assert changed.revision == 1
    assert not ledger.observe_item(turn_id="turn-1", item=user(), completed=True).complete


@pytest.mark.asyncio
async def test_pending_completion_resolves_in_original_order_and_freezes_prefix(tmp_path):
    seed = await selected(tmp_path, [])
    provenance = index(seed)
    ledger = CodexInputBaseline.from_selected(seed, provenance)
    pending = user("first", "partial")
    first = ledger.observe_item(turn_id="turn-1", item=pending, completed=False)
    assert not first.complete and first.pending_count == 1 and first.revision == 1
    assert ledger.observe_item(turn_id="turn-1", item=pending, completed=False) == first
    ledger.observe_item(turn_id="turn-1", item=user("second"), completed=True)
    final = ledger.observe_item(turn_id="turn-1", item=user("first", "complete"), completed=True)
    assert final.complete and final.pending_count == 0 and final.revision == 3
    assert final.digest == provenance.external_snapshot(entries([
        user("first", "complete"), user("second"),
    ])).digest
    assert first.digest is None
    pending["content"][0]["text"] = "caller mutation"
    assert ledger.snapshot() == final


@pytest.mark.asyncio
async def test_pending_correlation_change_cannot_resolve_as_different_input(tmp_path):
    seed = await selected(tmp_path, [])
    ledger = CodexInputBaseline.from_selected(seed, index(seed))
    ledger.observe_item(turn_id="turn-1", item=user(client="client-a"), completed=False)
    result = ledger.observe_item(turn_id="turn-1", item=user(client="client-b"), completed=True)
    assert not result.complete and result.reason == "input_tuple_conflict"


@pytest.mark.asyncio
async def test_own_echo_pending_exact_conflict_and_multiplicity(tmp_path):
    seed = await selected(tmp_path, [])
    provenance = index(seed, correction=True)
    ledger = CodexInputBaseline.from_selected(seed, provenance)
    own = user(client="pex-correction-exact-id", value="Exact instruction.")
    assert not ledger.observe_item(turn_id="turn-1", item=own, completed=False).complete
    exact = ledger.observe_item(turn_id="turn-1", item=own, completed=True)
    assert exact.complete and exact.external_count == 0
    assert exact.digest == provenance.external_snapshot([]).digest
    duplicate = {**own, "id": "other-vendor-item"}
    assert not ledger.observe_item(turn_id="turn-1", item=duplicate, completed=True).complete
    mismatch = CodexInputBaseline.from_selected(seed, provenance)
    result = mismatch.observe_item(
        turn_id="turn-1", item={**own, "content": text("forged")}, completed=True,
    )
    assert not result.complete and result.external_count == 0


@pytest.mark.asyncio
async def test_later_reconciled_history_never_backfills_earlier_event_baseline(tmp_path):
    seed = await selected(tmp_path)
    provenance = index(seed)
    ledger = CodexInputBaseline.from_selected(seed, provenance)
    event_prefix = ledger.snapshot()
    later_history = provenance.external_snapshot(entries([user(), user("new-human", "new intent")]))
    assert event_prefix.complete and event_prefix.digest != later_history.digest
    live = ledger.observe_item(
        turn_id="turn-1", item=user("new-human", "new intent"), completed=True,
    )
    assert live.digest == later_history.digest and event_prefix.revision == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("bound,value", [
    ("MAX_INPUTS", 1), ("MAX_INPUT_BYTES", 1), ("MAX_ITEM_BYTES", 1),
])
async def test_bounds_fail_closed_without_partial_digest(tmp_path, monkeypatch, bound, value):
    seed = await selected(tmp_path, [])
    ledger = CodexInputBaseline.from_selected(seed, index(seed))
    monkeypatch.setattr(baseline_module, bound, value)
    ledger.observe_item(turn_id="turn-1", item=user(), completed=False)
    result = ledger.observe_item(turn_id="turn-1", item=user("second"), completed=True)
    assert not result.complete and result.digest is None
    assert result.reason == "input_ledger_bound_exceeded"


@pytest.mark.asyncio
async def test_known_noninput_ignored_but_unknown_live_type_is_sticky_gap(tmp_path):
    seed = await selected(tmp_path)
    ledger = CodexInputBaseline.from_selected(seed, index(seed))
    first = ledger.snapshot()
    assert ledger.observe_item(
        turn_id="turn-1", item={"id": "a", "type": "agentMessage"}, completed=True,
    ) == first
    result = ledger.observe_item(
        turn_id="turn-1", item={"id": "b", "type": "futureUser"}, completed=True,
    )
    assert not result.complete and result.reason == "live_input_identity_unknown"


@pytest.mark.asyncio
async def test_incomplete_completed_input_never_silently_resolves(tmp_path):
    seed = await selected(tmp_path, [])
    ledger = CodexInputBaseline.from_selected(seed, index(seed))
    partial = copy.deepcopy(user())
    del partial["clientId"]
    assert not ledger.observe_item(turn_id="turn-1", item=partial, completed=True).complete
    result = ledger.observe_item(turn_id="turn-1", item=user(), completed=True)
    assert not result.complete and result.reason == "input_tuple_conflict"
    assert strict_json_loads(ledger._inputs[("turn-1", "human-1")].raw_json) == partial


@pytest.mark.asyncio
async def test_revision_saturates_as_incomplete_and_unseeded_constructor_is_unavailable(tmp_path):
    seed = await selected(tmp_path, [])
    provenance = index(seed)
    assert not CodexInputBaseline(provenance).snapshot().complete
    ledger = CodexInputBaseline.from_selected(seed, provenance)
    ledger._revision = baseline_module.MAX_REVISION
    result = ledger.observe_item(turn_id="turn-1", item=user(), completed=True)
    assert result.revision == baseline_module.MAX_REVISION
    assert not result.complete and result.reason == "input_revision_bound_exceeded"


@pytest.mark.asyncio
async def test_user_identity_cannot_change_to_noninput_type(tmp_path):
    seed = await selected(tmp_path)
    ledger = CodexInputBaseline.from_selected(seed, index(seed))
    changed = {"id": "human-1", "type": "agentMessage"}
    result = ledger.observe_item(turn_id="turn-1", item=changed, completed=True)
    assert not result.complete and result.reason == "input_tuple_conflict"


@pytest.mark.asyncio
async def test_canonical_entry_byte_bound_also_returns_incomplete_snapshot(tmp_path, monkeypatch):
    from pex_bridge import codex_input_provenance

    seed = await selected(tmp_path, [])
    ledger = CodexInputBaseline.from_selected(seed, index(seed))
    monkeypatch.setattr(codex_input_provenance, "MAX_INPUT_BYTES", 1)
    result = ledger.observe_item(turn_id="turn-1", item=user(), completed=True)
    assert not result.complete and result.digest is None
    assert result.reason == "input_ledger_bound_exceeded"


@pytest.mark.asyncio
async def test_pending_without_client_identity_can_resolve_but_annotations_are_exact(tmp_path):
    seed = await selected(tmp_path, [])
    ledger = CodexInputBaseline.from_selected(seed, index(seed))
    pending = {"type": "userMessage", "id": "human-1", "content": []}
    ledger.observe_item(turn_id="turn-1", item=pending, completed=False)
    complete = user()
    assert ledger.observe_item(turn_id="turn-1", item=complete, completed=True).complete
    complete["content"][0]["text_elements"] = [
        {"byteRange": {"start": 0, "end": 1}, "placeholder": None},
    ]
    result = ledger.observe_item(turn_id="turn-1", item=complete, completed=True)
    assert not result.complete and result.reason == "input_tuple_conflict"


@pytest.mark.asyncio
async def test_provenance_replacement_reclassifies_without_mutating_old_snapshot(tmp_path):
    seed = await selected(tmp_path, [])
    ledger = CodexInputBaseline.from_selected(seed, index(seed))
    own = user(client="pex-correction-exact-id", value="Exact instruction.")
    before = ledger.observe_item(turn_id="turn-1", item=own, completed=True)
    assert before.complete and before.external_count == 1
    after = ledger.replace_provenance(index(seed, correction=True))
    assert after.complete and after.external_count == 0 and after.revision == before.revision + 1
    assert after.digest != before.digest and before.external_count == 1
    assert ledger.replace_provenance(index(seed, correction=True)) is after
    with pytest.raises(ValueError, match="removed or changed"):
        ledger.replace_provenance(index(seed))
    assert ledger.snapshot() is after


@pytest.mark.asyncio
async def test_provenance_replacement_rejects_wrong_scope_or_inconsistent_frozen_index(tmp_path):
    seed = await selected(tmp_path, [])
    ledger = CodexInputBaseline.from_selected(seed, index(seed))
    before = ledger.snapshot()
    with pytest.raises(ValueError, match="scope"):
        ledger.replace_provenance(replace(index(seed), thread_id="foreign"))
    corrupted = replace(index(seed, correction=True), _records=())
    with pytest.raises(ValueError, match="inconsistent"):
        ledger.replace_provenance(corrupted)
    assert ledger.snapshot() is before


@pytest.mark.asyncio
async def test_revision_saturation_invalidates_preexisting_cached_snapshot(tmp_path):
    seed = await selected(tmp_path, [])
    ledger = CodexInputBaseline.from_selected(seed, index(seed))
    ledger._revision = baseline_module.MAX_REVISION
    old = ledger.snapshot()
    assert old.complete
    new = ledger.observe_item(turn_id="turn-1", item=user(), completed=True)
    assert not new.complete and new.revision == old.revision
    assert ledger.snapshot() is new and old.complete
