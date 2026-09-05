"""Immutable input attribution shared by live observation and history reads.

This module does NOT authenticate JSON. Only the internal attachment/dispatch
path may install records returned by Store.list_codex_correction_attributions.
A matching historical record is attribution, never permission to dispatch or a
claim of vendor idempotency. Store must independently verify record-only writes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from pex_bridge.adapters.strict_json import strict_json_loads
from pex_bridge.codex_correction import CORRECTION_SCHEMA, canonical

MAX_RECORDS = 4096
MAX_INDEX_BYTES = 8 * 1024 * 1024
MAX_ITEM_BYTES = 262_144
MAX_INPUTS = 4096
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 65_536
MAX_CONTENT_PARTS = 128
InputKind = Literal["exact_pex", "external", "uncertain", "incomplete"]


def _id(value: Any) -> bool:
    return (
        type(value) is str and 0 < len(value) <= 512 and value == value.strip()
        and not any(ord(character) < 32 for character in value)
    )


def _incomplete(value: dict[str, Any]) -> bool:
    for key in ("truncated", "hasMore", "has_more", "redacted"):
        if key in value and value[key] is not False:
            return True
    for key in ("nextCursor", "next_cursor"):
        if key in value and value[key] not in (None, ""):
            return True
    return "content_status" in value and value["content_status"] != "complete"


def _complete_content(content: Any) -> bool:
    if type(content) is not list or not 0 < len(content) <= MAX_CONTENT_PARTS:
        return False
    total = 0
    for part in content:
        if type(part) is not dict or set(part) != {"type", "text", "text_elements"}:
            return False
        text = part["text"]
        elements = part["text_elements"]
        if (
            part["type"] != "text" or type(text) is not str or not text.strip()
            or "\x00" in text or "[REDACTED:" in text
            or type(elements) is not list or len(elements) > MAX_CONTENT_PARTS
        ):
            return False
        size = len(text.encode("utf-8"))
        total += size
        if total > MAX_TEXT_BYTES:
            return False
        # TextElement byte ranges refer to UTF-8 boundaries, not Python indexes.
        boundaries = {0}
        offset = 0
        for character in text:
            offset += len(character.encode("utf-8"))
            boundaries.add(offset)
        for element in elements:
            if type(element) is not dict or set(element) != {"byteRange", "placeholder"}:
                return False
            span = element["byteRange"]
            placeholder = element["placeholder"]
            if (
                type(span) is not dict or set(span) != {"start", "end"}
                or type(span["start"]) is not int or type(span["end"]) is not int
                or span["start"] not in boundaries or span["end"] not in boundaries
                or span["start"] > span["end"]
                or (placeholder is not None and (
                    type(placeholder) is not str or len(placeholder) > MAX_TEXT_BYTES
                    or "\x00" in placeholder
                ))
            ):
                return False
    return True


@dataclass(frozen=True, slots=True)
class CodexInputClassification:
    kind: InputKind
    entry_json: str | None = None
    correction_json: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CodexExternalInputs:
    complete: bool
    external_inputs_json: str | None
    digest: str | None
    classifications: tuple[CodexInputClassification, ...]


@dataclass(frozen=True, slots=True)
class _Attribution:
    client_id: str
    effect_id: str
    content_json: str
    correction_json: str


@dataclass(frozen=True, slots=True)
class CodexInputProvenance:
    session_id: str
    thread_id: str
    _records: tuple[str, ...]
    _attributions: tuple[_Attribution, ...]

    @classmethod
    def from_store_records(
        cls, records: tuple[str, ...], *, session_id: str, thread_id: str,
    ) -> CodexInputProvenance:
        """Validate shape and freeze Store results; callers supply the trust boundary."""
        if type(records) is not tuple or not _id(session_id) or not _id(thread_id):
            raise ValueError("Codex attribution index requires exact immutable inputs")
        if len(records) > MAX_RECORDS:
            raise ValueError("Codex attribution index record bound exceeded")
        total = 0
        clients: set[str] = set()
        effects: set[str] = set()
        entries = []
        for encoded in records:
            if type(encoded) is not str:
                raise ValueError("Codex attribution records must be canonical JSON strings")
            total += len(encoded.encode("utf-8"))
            if total > MAX_INDEX_BYTES or len(encoded.encode("utf-8")) > MAX_ITEM_BYTES:
                raise ValueError("Codex attribution index byte bound exceeded")
            record = strict_json_loads(encoded)
            if (
                type(record) is not dict
                or set(record) != {"correction", "effect_state", "effect_version"}
                or canonical(record) != encoded
                or type(record["effect_state"]) is not str
                or record["effect_state"] not in {
                    "dispatching", "delivered", "delivery_uncertain", "failed",
                }
                or type(record["effect_version"]) is not int or record["effect_version"] < 1
            ):
                raise ValueError("Codex attribution attempt record is invalid")
            correction = record["correction"]
            if (
                type(correction) is not dict
                or correction.get("schema") != CORRECTION_SCHEMA
                or correction.get("session_id") != session_id
                or correction.get("thread_id") != thread_id
                or not _id(correction.get("client_message_id"))
                or not _id(correction.get("effect_id"))
                or not _complete_content(correction.get("content"))
            ):
                raise ValueError("Codex attribution correction scope/content is invalid")
            client = correction["client_message_id"]
            effect = correction["effect_id"]
            if client in clients or effect in effects:
                raise ValueError("duplicate or conflicting Codex attribution registration")
            clients.add(client)
            effects.add(effect)
            entries.append(_Attribution(
                client, effect, canonical(correction["content"]), canonical(correction),
            ))
        return cls(session_id, thread_id, records, tuple(entries))

    def with_store_records(self, records: tuple[str, ...]) -> CodexInputProvenance:
        if type(records) is not tuple:
            raise ValueError("Codex attribution additions must be immutable")
        return self.from_store_records(
            self._records + records, session_id=self.session_id, thread_id=self.thread_id,
        )

    def classify_item(
        self, *, session_id: str, thread_id: str, turn_id: str,
        item: dict[str, Any], completed: bool = True,
    ) -> CodexInputClassification:
        if session_id != self.session_id or thread_id != self.thread_id:
            return CodexInputClassification("incomplete", reason="input_scope_mismatch")
        client = item.get("clientId") if type(item) is dict else None
        known = next((entry for entry in self._attributions if entry.client_id == client), None)
        refusal: InputKind = "uncertain" if known is not None else "incomplete"
        if (
            type(item) is not dict or item.get("type") != "userMessage"
            or not _id(turn_id) or not _id(item.get("id"))
            or "clientId" not in item or (client is not None and not _id(client))
            or type(completed) is not bool or not completed or _incomplete(item)
        ):
            return CodexInputClassification(refusal, reason="input_incomplete")
        try:
            if not _complete_content(item.get("content")):
                return CodexInputClassification(refusal, reason="input_content_incomplete")
            encoded = canonical({
                "turn_id": turn_id, "item_id": item["id"],
                "client_id": client, "content": item["content"],
            })
            if len(encoded.encode("utf-8")) > MAX_ITEM_BYTES:
                return CodexInputClassification(refusal, reason="input_byte_bound")
            if known is not None:
                if canonical(item["content"]) != known.content_json:
                    return CodexInputClassification(
                        "uncertain", reason="correction_content_mismatch",
                    )
                return CodexInputClassification("exact_pex", encoded, known.correction_json)
            return CodexInputClassification("external", encoded)
        except (ValueError, TypeError, RecursionError):
            return CodexInputClassification(refusal, reason="input_encoding_invalid")

    def classify_entry(self, entry: dict[str, Any]) -> CodexInputClassification:
        if type(entry) is not dict or set(entry) != {
            "turn_id", "item_id", "client_id", "content",
        }:
            client = entry.get("client_id") if type(entry) is dict else None
            known = any(attribution.client_id == client for attribution in self._attributions)
            return CodexInputClassification(
                "uncertain" if known else "incomplete", reason="history_entry_incomplete",
            )
        return self.classify_item(
            session_id=self.session_id, thread_id=self.thread_id, turn_id=entry["turn_id"],
            item={
                "type": "userMessage", "id": entry["item_id"],
                "clientId": entry["client_id"], "content": entry["content"],
            },
        )

    def external_snapshot(self, entries: list[dict] | tuple[dict, ...]) -> CodexExternalInputs:
        """Preserve input order; duplicate turn/item identities never silently collapse."""
        if type(entries) not in (list, tuple) or len(entries) > MAX_INPUTS:
            raise ValueError("Codex external input snapshot record bound/type is invalid")
        results = []
        external = []
        seen: set[tuple[str, str]] = set()
        seen_corrections: set[str] = set()
        total = 0
        for entry in entries:
            result = self.classify_entry(entry)
            if result.entry_json is not None:
                total += len(result.entry_json.encode("utf-8"))
                if total > MAX_INPUT_BYTES:
                    raise ValueError("Codex external input snapshot byte bound exceeded")
                frozen = strict_json_loads(result.entry_json)
                key = (frozen["turn_id"], frozen["item_id"])
                if key in seen:
                    raise ValueError("duplicate Codex input turn/item identity")
                seen.add(key)
                if result.kind == "exact_pex":
                    if frozen["client_id"] in seen_corrections:
                        result = CodexInputClassification(
                            "uncertain", reason="correction_correlation_has_multiple_items",
                        )
                    seen_corrections.add(frozen["client_id"])
                elif result.kind == "external":
                    external.append(frozen)
            results.append(result)
        if any(result.kind in {"uncertain", "incomplete"} for result in results):
            return CodexExternalInputs(False, None, None, tuple(results))
        encoded = canonical(external)
        return CodexExternalInputs(
            True, encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest(), tuple(results),
        )
