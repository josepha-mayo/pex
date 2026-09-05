"""Private, ordered input-prefix evidence; never a dispatch grant or history replay.

Seed only from the selected pre-resume snapshot. A later reconciliation read
must not silently introduce input into an earlier live event's baseline. The
revision below measures ledger changes, not adapter human-input revisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pex_bridge.adapters.strict_json import strict_json_loads
from pex_bridge.codex_correction import canonical
from pex_bridge.codex_input_provenance import (
    CodexExternalInputs,
    CodexInputProvenance,
    _id,
    _incomplete,
)

if TYPE_CHECKING:
    from pex_bridge.adapters.codex_subscription import CodexSelectedThread

MAX_INPUTS = 4096
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_ITEM_BYTES = 262_144
MAX_REVISION = 2**63 - 1
BASELINE_SCHEMA = "pex.codex-input-baseline.v1"


@dataclass(frozen=True, slots=True)
class CodexInputBaselineSnapshot:
    schema: str
    complete: bool
    digest: str | None
    revision: int
    external_count: int
    pending_count: int
    reason: str | None


@dataclass(frozen=True, slots=True)
class _Input:
    raw_json: str
    completed: bool


class CodexInputBaseline:
    """Internally installed Store provenance is required; JSON is not authority.

All mutable/raw state stays private. Snapshot exports contain no input content,
and historical PEX classification never grants current goal/worker authority.
"""

    def __init__(self, provenance: CodexInputProvenance) -> None:
        self._provenance = provenance
        self._inputs: dict[tuple[str, str], _Input] = {}
        self._bytes = 0
        self._revision = 0
        self._gap: str | None = "selected_history_unavailable"
        self._cached_snapshot: CodexInputBaselineSnapshot | None = None
        self._cached_external: CodexExternalInputs | None = None

    @classmethod
    def from_selected(
        cls, selected: CodexSelectedThread, provenance: CodexInputProvenance,
    ) -> CodexInputBaseline:
        # Import here so a coordinator can use this helper without a cycle.
        from pex_bridge.adapters.codex_subscription import (
            CONTROL_HISTORY_ITEM_TYPES,
            CodexSelectedThread,
            _history,
            _history_content_digest,
            _history_digest,
        )

        if (
            type(selected) is not CodexSelectedThread
            or type(provenance) is not CodexInputProvenance
        ):
            raise ValueError("input baseline requires selected history and immutable provenance")
        if (selected.pex_session_id, selected.thread_id) != (
            provenance.session_id, provenance.thread_id,
        ):
            raise ValueError("input baseline selected scope differs from provenance")
        result = cls(provenance)
        if selected.history_mode != "includeTurns":
            result._mark_gap("selected_history_unavailable")
            return result
        if type(selected.history_records) is not tuple or len(selected.history_records) > 4352:
            raise ValueError("input baseline selected record bound/type is invalid")
        # Regenerate full records as well as IDs: nested turn items must agree
        # exactly with the separate frozen item records, not merely their IDs.
        turns = [record.payload() for record in selected.history_records
                 if record.method == "history/turn"]
        ids, shape, records = _history({"turns": turns})
        if (
            records != selected.history_records or ids != selected.history_ids
            or shape != selected.history_shape
            or _history_digest(ids) != selected.history_identity_digest
            or _history_content_digest(records) != selected.history_content_digest
        ):
            raise ValueError("input baseline selected history is inconsistent")
        result._gap = None
        for turn in turns:
            if (
                _incomplete(turn) or turn.get("itemsView") != "full"
                or type(turn.get("status")) is not str
                or turn.get("status") not in {"inProgress", "completed", "interrupted", "failed"}
                or type(turn.get("items")) is not list
            ):
                result._mark_gap("selected_history_incomplete")
            for item in turn.get("items", []):
                if (
                    type(item.get("type")) is not str
                    or item["type"] not in CONTROL_HISTORY_ITEM_TYPES or _incomplete(item)
                ):
                    result._mark_gap("selected_history_item_incomplete")
                if item.get("type") == "userMessage":
                    result._observe(turn["id"], item, True)
        # Seed is revision zero, regardless of the number of historical inputs.
        result._revision = 0
        result._invalidate_cache()
        return result

    def _invalidate_cache(self) -> None:
        self._cached_snapshot = None
        self._cached_external = None

    def _mark_gap(self, reason: str) -> None:
        if self._gap is None:
            self._gap = reason
            self._advance()

    def _advance(self) -> None:
        self._invalidate_cache()
        if self._revision >= MAX_REVISION:
            self._gap = "input_revision_bound_exceeded"
        else:
            self._revision += 1

    def replace_provenance(
        self, provenance: CodexInputProvenance,
    ) -> CodexInputBaselineSnapshot:
        """Install a refreshed internal Store index, never caller/model authority.

        Existing attribution must remain intact; a newly attempted correction
        may be added before enqueueing its text. Reclassification changes the
        local revision, while already returned snapshots remain frozen.
        """
        if type(provenance) is not CodexInputProvenance or (
            provenance.session_id, provenance.thread_id,
        ) != (self._provenance.session_id, self._provenance.thread_id):
            raise ValueError("replacement input provenance scope is invalid")
        validated = CodexInputProvenance.from_store_records(
            provenance._records, session_id=provenance.session_id, thread_id=provenance.thread_id,
        )
        if validated != provenance:
            raise ValueError("replacement input provenance is inconsistent")
        prior = {entry.correction_json for entry in self._provenance._attributions}
        current = {entry.correction_json for entry in validated._attributions}
        if not prior <= current:
            raise ValueError("replacement input provenance removed or changed attribution")
        if validated != self._provenance:
            self._provenance = validated
            self._advance()
        return self.snapshot()

    def observe_item(
        self, *, turn_id: str, item: dict[str, Any], completed: bool,
    ) -> CodexInputBaselineSnapshot:
        """Observe one raw item in receive order before freezing its event.

        Complete exact repeats deduplicate by turn/item and canonical input
        content. Started input may resolve on completion; conflicting completed
        input and unknown record types leave a permanent coverage gap.
        """
        self._observe(turn_id, item, completed)
        return self.snapshot()

    def _observe(self, turn_id: str, item: dict[str, Any], completed: bool) -> None:
        from pex_bridge.adapters.codex_subscription import CONTROL_HISTORY_ITEM_TYPES

        if (
            not _id(turn_id) or type(item) is not dict or not _id(item.get("id"))
            or type(completed) is not bool or type(item.get("type")) is not str
            or item["type"] not in CONTROL_HISTORY_ITEM_TYPES
        ):
            self._mark_gap("live_input_identity_unknown")
            return
        if item["type"] != "userMessage":
            if (turn_id, item["id"]) in self._inputs:
                self._mark_gap("input_tuple_conflict")
            elif _incomplete(item):
                self._mark_gap("live_item_incomplete")
            return
        try:
            encoded = canonical(item)
            size = len(encoded.encode("utf-8"))
        except (ValueError, TypeError, RecursionError):
            self._mark_gap("live_input_encoding_invalid")
            return
        key = (turn_id, item["id"])
        old = self._inputs.get(key)
        if old is not None:
            if old == _Input(encoded, completed):
                return
            previous = strict_json_loads(old.raw_json)
            if old.completed:
                # Late started copies cannot erase completion. Even a repeat
                # with different ancillary fields needs identical canonical
                # classified content, including clientId and text annotations.
                before = self._classify(turn_id, previous, True)
                after = self._classify(turn_id, item, True)
                if before.entry_json is not None and before.entry_json == after.entry_json:
                    return
                self._mark_gap("input_tuple_conflict")
                return
            if "clientId" in previous and previous["clientId"] != item.get("clientId"):
                self._mark_gap("input_tuple_conflict")
                return
        next_bytes = self._bytes + size - (len(old.raw_json.encode("utf-8")) if old else 0)
        if size > MAX_ITEM_BYTES or next_bytes > MAX_INPUT_BYTES or (
            old is None and len(self._inputs) >= MAX_INPUTS
        ):
            self._mark_gap("input_ledger_bound_exceeded")
            return
        self._inputs[key] = _Input(encoded, completed)
        self._bytes = next_bytes
        self._advance()

    def _classify(self, turn_id: str, item: dict, completed: bool):
        return self._provenance.classify_item(
            session_id=self._provenance.session_id, thread_id=self._provenance.thread_id,
            turn_id=turn_id, item=item, completed=completed,
        )

    def _private_external_inputs(self) -> CodexExternalInputs:
        """Internal comparison seam; never put its raw strings in API metadata."""
        if self._cached_external is None:
            self._cached_external = self._compute_external_inputs()
        return self._cached_external

    def _compute_external_inputs(self) -> CodexExternalInputs:
        entries = []
        classifications = []
        for (turn_id, _), slot in self._inputs.items():
            classification = self._classify(
                turn_id, strict_json_loads(slot.raw_json), slot.completed,
            )
            classifications.append(classification)
            if classification.entry_json is not None:
                entries.append(strict_json_loads(classification.entry_json))
        if self._gap is not None or any(
            entry.kind in {"uncertain", "incomplete"} for entry in classifications
        ):
            return CodexExternalInputs(False, None, None, tuple(classifications))
        # Reuse cross-item correlation multiplicity and ordered digest semantics.
        try:
            return self._provenance.external_snapshot(entries)
        except ValueError:
            # Canonical entries add turn identity fields, so their independent
            # byte bound can be reached before the raw-slot byte bound.
            self._mark_gap("input_ledger_bound_exceeded")
            return CodexExternalInputs(False, None, None, tuple(classifications))

    def snapshot(self) -> CodexInputBaselineSnapshot:
        if self._cached_snapshot is not None:
            return self._cached_snapshot
        external = self._private_external_inputs()
        pending = sum(not slot.completed for slot in self._inputs.values())
        reason = self._gap
        if not external.complete and reason is None:
            reason = "input_pending" if pending else "input_provenance_unresolved"
        self._cached_snapshot = CodexInputBaselineSnapshot(
            BASELINE_SCHEMA, external.complete, external.digest, self._revision,
            sum(entry.kind == "external" for entry in external.classifications), pending, reason,
        )
        return self._cached_snapshot
