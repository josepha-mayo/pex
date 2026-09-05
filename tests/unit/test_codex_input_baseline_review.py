"""Independent call-count regression for the private per-event baseline ledger."""

from pex_bridge.codex_input_baseline import CodexInputBaseline
from test_codex_input_baseline import index, selected, user


async def test_unchanged_event_baseline_does_not_reclassify_entire_history(tmp_path, monkeypatch):
    seed = await selected(tmp_path)
    ledger = CodexInputBaseline.from_selected(seed, index(seed))
    original = ledger._classify
    calls = 0

    def classify(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(ledger, "_classify", classify)
    first = ledger.snapshot()
    after_initial = calls
    for _ in range(12):
        assert ledger.snapshot() == first
    unchanged = ledger.observe_item(
        turn_id="turn-1", item={"id": "agent-item", "type": "agentMessage"}, completed=True,
    )
    assert unchanged == first and ledger.snapshot() == first
    assert calls == after_initial


async def test_snapshot_cache_must_invalidate_on_pending_completion_and_sticky_gap(tmp_path):
    seed = await selected(tmp_path, [])
    ledger = CodexInputBaseline.from_selected(seed, index(seed))
    initial = ledger.snapshot()
    assert initial.complete and initial.external_count == 0
    item = user("new-input")
    pending = ledger.observe_item(turn_id="turn-1", item=item, completed=False)
    assert not pending.complete and pending.pending_count == 1 and pending.revision == 1
    assert ledger.snapshot() == pending
    completed = ledger.observe_item(turn_id="turn-1", item=item, completed=True)
    assert completed.complete and completed.external_count == 1 and completed.revision == 2
    assert completed.digest != initial.digest and ledger.snapshot() == completed
    assert initial.complete and initial.external_count == 0 and pending.digest is None
    gap = ledger.observe_item(
        turn_id="turn-1", item={"id": "unknown", "type": "futureInput"}, completed=True,
    )
    assert not gap.complete and gap.digest is None and gap.revision == 3
    assert ledger.snapshot() == gap
