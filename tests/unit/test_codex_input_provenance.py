"""Pure shape/matching tests; fixture JSON is not authenticated Store authority."""

import copy
import hashlib
from dataclasses import FrozenInstanceError

import pytest
from pex_bridge import codex_input_provenance as provenance
from pex_bridge.codex_correction import CORRECTION_SCHEMA, canonical
from pex_bridge.codex_input_provenance import CodexInputProvenance

SESSION = "codex:thread"
THREAD = "thread"
CLIENT = "pex-correction-exact-id"


def text(value="Exact instruction."):
    return [{"type": "text", "text": value, "text_elements": []}]


def record(*, client=CLIENT, effect="effect-one", state="dispatching", version=1):
    # Only the integration layer can establish that records actually came from Store.
    return {
        "correction": {
            "schema": CORRECTION_SCHEMA, "session_id": SESSION, "thread_id": THREAD,
            "client_message_id": client, "effect_id": effect, "content": text(),
            "subscription_receipt": {"connection_generation": 1},
        },
        "effect_state": state, "effect_version": version,
    }


def index(*records):
    supplied = records or (record(),)
    return CodexInputProvenance.from_store_records(
        tuple(canonical(item) for item in supplied), session_id=SESSION, thread_id=THREAD,
    )


def item(*, client=CLIENT, content=None, item_id="item-one"):
    return {
        "type": "userMessage", "id": item_id, "clientId": client,
        "content": text() if content is None else content,
    }


def classify(current, raw, **changes):
    return current.classify_item(
        session_id=SESSION, thread_id=THREAD, turn_id="turn-one", item=raw, **changes,
    )


def entry(raw=None, *, turn_id="turn-one"):
    raw = item() if raw is None else raw
    return {
        "turn_id": turn_id, "item_id": raw["id"],
        "client_id": raw["clientId"], "content": raw["content"],
    }


@pytest.mark.parametrize("state", ["dispatching", "delivered", "delivery_uncertain", "failed"])
def test_exact_attempted_correction_is_same_for_live_and_history(state):
    current = index(record(state=state))
    live = classify(current, item())
    historical = current.classify_entry(entry())
    assert live == historical
    assert live.kind == "exact_pex"
    assert live.correction_json == canonical(record(state=state)["correction"])
    assert not hasattr(live, "dispatch_granted")


@pytest.mark.parametrize("client", [None, "human-client", "pex-correction-forged-prefix"])
def test_unknown_correlation_is_external_even_for_same_text(client):
    result = classify(index(), item(client=client))
    assert result.kind == "external"
    assert result.correction_json is None


@pytest.mark.parametrize("content", [
    text("Exact instruction. "), text("Different instruction"),
    text("Exact") + text(" instruction."),
])
def test_known_id_different_content_never_becomes_pex_or_human(content):
    result = classify(index(), item(content=content))
    assert result.kind == "uncertain"
    assert result.correction_json is None


@pytest.mark.parametrize("client,expected", [(CLIENT, "uncertain"), (None, "incomplete")])
@pytest.mark.parametrize("change", [
    "missing_content", "empty_content", "missing_elements", "image", "redacted",
    "truncated", "false_integer", "bad_text", "bad_id", "wrong_item_type",
    "content_extra", "unpaired_surrogate",
])
def test_partial_or_unsupported_input_has_no_external_baseline(client, expected, change):
    raw = item(client=client)
    if change == "missing_content":
        del raw["content"]
    elif change == "empty_content":
        raw["content"] = []
    elif change == "missing_elements":
        del raw["content"][0]["text_elements"]
    elif change == "image":
        raw["content"] = [{"type": "image", "url": "local-only-fixture"}]
    elif change == "redacted":
        raw["content"][0]["text"] = "[REDACTED:secret]"
    elif change in {"truncated", "false_integer"}:
        raw["truncated"] = True if change == "truncated" else 0
    elif change == "bad_text":
        raw["content"][0]["text"] = False
    elif change == "bad_id":
        raw["id"] = False
    elif change == "wrong_item_type":
        raw["type"] = "futureUserInput"
    elif change == "content_extra":
        raw["content"][0]["hasMore"] = True
    else:
        raw["content"][0]["text"] = "\ud800"
    result = classify(index(), raw)
    assert result.kind == expected
    assert result.entry_json is None and result.correction_json is None


@pytest.mark.parametrize("client,kind", [(CLIENT, "uncertain"), (None, "incomplete")])
def test_started_item_cannot_claim_complete_input(client, kind):
    assert classify(index(), item(client=client), completed=False).kind == kind
    assert classify(index(), item(client=client), completed=1).kind == kind


@pytest.mark.parametrize("field", ["session_id", "thread_id"])
def test_wrong_target_cannot_claim_correction(field):
    arguments = {
        "session_id": SESSION, "thread_id": THREAD, "turn_id": "turn", "item": item(),
    }
    arguments[field] = "other"
    result = index().classify_item(**arguments)
    assert result.kind == "incomplete" and result.correction_json is None


def test_ordered_digest_excludes_only_exact_corrections_and_matches_canonical_history():
    human_a = entry(item(client=None, content=text("A"), item_id="a"))
    human_b = entry(item(client="person", content=text("B"), item_id="b"))
    result = index().external_snapshot([human_a, entry(), human_b])
    expected = canonical([human_a, human_b])
    assert result.complete and result.external_inputs_json == expected
    assert result.digest == hashlib.sha256(expected.encode("utf-8")).hexdigest()
    reordered = index().external_snapshot([human_b, entry(), human_a])
    assert reordered.digest != result.digest


def test_dict_key_order_is_not_input_order():
    raw = entry(item(client=None))
    reverse_keys = dict(reversed(list(raw.items())))
    assert index().external_snapshot([raw]) == index().external_snapshot([reverse_keys])


@pytest.mark.parametrize("same_content", [True, False])
def test_duplicate_turn_item_identity_is_rejected(same_content):
    first = entry(item(client=None))
    second = copy.deepcopy(first)
    if not same_content:
        second["content"] = text("Changed")
    with pytest.raises(ValueError, match="duplicate Codex input"):
        index().external_snapshot([first, second])


def test_same_item_id_in_distinct_turns_is_not_collapsed():
    one = entry(item(client=None), turn_id="turn-a")
    two = entry(item(client=None), turn_id="turn-b")
    result = index().external_snapshot([one, two])
    assert result.complete and result.external_inputs_json == canonical([one, two])


def test_same_correction_correlating_multiple_items_is_uncertain():
    result = index().external_snapshot([entry(), entry(item(item_id="another-item"))])
    assert not result.complete and result.digest is None
    assert result.classifications[-1].kind == "uncertain"


def test_mismatch_never_returns_partial_human_digest():
    result = index().external_snapshot([
        entry(item(client=None, item_id="human")), entry(item(content=text("Wrong"))),
    ])
    assert not result.complete and result.external_inputs_json is None and result.digest is None


def test_empty_external_snapshot_is_explicit_complete_empty_not_missing():
    result = index().external_snapshot([])
    assert result.complete and result.external_inputs_json == "[]"
    assert result.digest == hashlib.sha256(b"[]").hexdigest()


@pytest.mark.parametrize("change", ["exact_duplicate", "same_client", "same_effect"])
def test_duplicate_and_conflicting_registration_rejected(change):
    other = record()
    if change == "same_client":
        other["correction"]["effect_id"] = "effect-two"
    elif change == "same_effect":
        other["correction"]["client_message_id"] = "other-client"
    with pytest.raises(ValueError, match="duplicate or conflicting"):
        index().with_store_records((canonical(other),))


def test_registration_returns_new_index_without_mutating_old():
    original = index()
    updated = original.with_store_records((canonical(record(client="new-client", effect="new")),))
    assert classify(original, item(client="new-client")).kind == "external"
    assert classify(updated, item(client="new-client")).kind == "exact_pex"


@pytest.mark.parametrize("change", [
    "reserved", "skipped", "bool_version", "zero_version", "wrong_session", "wrong_thread",
    "unknown_schema", "list_state", "missing_client", "content_mismatch_type",
])
def test_invalid_store_record_shape_is_rejected(change):
    raw = record()
    if change in {"reserved", "skipped"}:
        raw["effect_state"] = change
    elif change in {"bool_version", "zero_version"}:
        raw["effect_version"] = False if change == "bool_version" else 0
    elif change in {"wrong_session", "wrong_thread"}:
        raw["correction"]["session_id" if change == "wrong_session" else "thread_id"] = "other"
    elif change == "unknown_schema":
        raw["correction"]["schema"] = "pretend-authenticated"
    elif change == "list_state":
        raw["effect_state"] = []
    elif change == "missing_client":
        del raw["correction"]["client_message_id"]
    else:
        raw["correction"]["content"][0]["text_elements"] = False
    with pytest.raises(ValueError):
        index(raw)


def test_noncanonical_and_duplicate_json_keys_rejected():
    for encoded in ('{"correction":{},"correction":{}}', " " + canonical(record())):
        with pytest.raises(ValueError):
            CodexInputProvenance.from_store_records(
                (encoded,), session_id=SESSION, thread_id=THREAD,
            )


@pytest.mark.parametrize("limit", ["MAX_RECORDS", "MAX_INDEX_BYTES"])
def test_index_bounds_are_explicit_failures(monkeypatch, limit):
    monkeypatch.setattr(provenance, limit, 0)
    with pytest.raises(ValueError, match="bound"):
        index()


@pytest.mark.parametrize("limit", ["MAX_INPUTS", "MAX_INPUT_BYTES"])
def test_snapshot_bounds_are_explicit_failures(monkeypatch, limit):
    current = index()
    monkeypatch.setattr(provenance, limit, 0)
    with pytest.raises(ValueError, match="bound"):
        current.external_snapshot([entry(item(client=None))])


def test_results_and_index_have_no_mutable_aliases():
    raw = item(client=None)
    current = index()
    result = classify(current, raw)
    baseline = current.external_snapshot([entry(raw)])
    raw["content"][0]["text"] = "Mutated"
    assert "Mutated" not in result.entry_json
    assert "Mutated" not in baseline.external_inputs_json
    for target, field, value in (
        (current, "session_id", "other"), (result, "kind", "exact_pex"),
        (baseline, "complete", False),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(target, field, value)


@pytest.mark.parametrize("start,end,valid", [(0, 2, True), (1, 2, False), (False, 2, False)])
def test_text_elements_preserve_exact_utf8_ranges_without_boolean_aliases(start, end, valid):
    content = text("éx")
    content[0]["text_elements"] = [{
        "byteRange": {"start": start, "end": end}, "placeholder": None,
    }]
    result = classify(index(), item(client=None, content=content))
    assert result.kind == ("external" if valid else "incomplete")


@pytest.mark.parametrize("client,kind", [(CLIENT, "uncertain"), (None, "incomplete")])
def test_incomplete_history_entry_keeps_known_correlation_uncertain(client, kind):
    value = entry(item(client=client))
    del value["content"]
    assert index().classify_entry(value).kind == kind
    snapshot = index().external_snapshot([value])
    assert not snapshot.complete and snapshot.digest is None
