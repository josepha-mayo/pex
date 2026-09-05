"""Identity-bound, observation-only subscription to an existing Codex thread.

Persisted ``thread/read`` history is kept distinct from live App Server
notifications.  This coordinator never creates a turn, responds to an approval,
or manufactures a timestamp or terminal event.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, Protocol

from pex_bridge.adapters.base import bounded_adapter_id
from pex_bridge.adapters.codex import CodexAdapter
from pex_bridge.adapters.codex_shared import SharedCodexReadSnapshot
from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads

MAX_HISTORY_TURNS = 256
MAX_HISTORY_ITEMS = 4_096
MAX_NOTIFICATIONS_PER_DRAIN = 1_024
MAX_PROTOCOL_JSON_BYTES = 1_048_576
MAX_NOTIFICATION_BATCH_JSON_BYTES = 4_194_304
MAX_IDENTITY_JSON_BYTES = 16_384
MAX_LIVE_IDENTITIES = 8_192
SUBSCRIPTION_SCHEMA = "pex.codex-existing-thread-subscription.v1"
RUNTIME_STATUSES = frozenset({"active", "idle", "notLoaded", "systemError"})
# Control must not silently drop a future input-bearing item from its intent
# digest. Unknown items remain observable; adopting a new kind needs review.
CONTROL_HISTORY_ITEM_TYPES = frozenset({
    "userMessage", "hookPrompt", "agentMessage", "plan", "reasoning",
    "commandExecution", "fileChange", "mcpToolCall", "dynamicToolCall",
    "collabAgentToolCall", "subAgentActivity", "webSearch", "imageView", "sleep",
    "imageGeneration", "enteredReviewMode", "exitedReviewMode", "contextCompaction",
})
RuntimeStatus = Literal["active", "idle", "notLoaded", "systemError", "unknown"]


class CodexSubscriptionError(RuntimeError):
    """The existing-thread identity or observation boundary failed closed."""


class _CodexThreadUnavailable(CodexSubscriptionError):
    """The selected worker's lifecycle ended this observation attachment."""


class CodexSubscriptionTransport(Protocol):
    initialized: bool
    connection_generation: int
    endpoint_identity: str

    async def ensure_ready(self) -> dict[str, Any]: ...

    async def request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...

    def drain_notifications(self, *, limit: int = 256) -> list[dict[str, Any]]: ...

    def connection_token(self) -> tuple[str, int]: ...

    async def close(self) -> None: ...

    async def read_current_thread(self) -> SharedCodexReadSnapshot: ...


@dataclass(frozen=True, slots=True)
class CodexControlSnapshot:
    """Fresh observed state, not permission to act or a server-side input lock."""

    receipt: CodexSubscriptionReceipt
    read: SharedCodexReadSnapshot
    active_turn_id: str | None
    user_inputs_json: str
    user_inputs_digest: str


@dataclass(frozen=True, slots=True)
class CodexObservedRecord:
    """One bounded vendor record, without inferred time or lifecycle meaning."""

    source: Literal["history", "live_notification"]
    stable_id: str
    method: str
    turn_id: str
    item_id: str | None
    live_sequence: int | None
    payload_json: str

    def payload(self) -> dict[str, Any]:
        value = strict_json_loads(self.payload_json)
        if not isinstance(value, dict):  # pragma: no cover - constructor invariant
            raise CodexSubscriptionError("stored Codex observation is not an object")
        return value


@dataclass(frozen=True, slots=True)
class CodexSelectedThread:
    """Read-only identity snapshot that an operator may explicitly authorize."""

    selection_id: str
    endpoint_identity: str
    connection_generation: int
    pex_session_id: str
    thread_id: str
    root_session_id: str
    project_id: str
    vendor_project_id: str | None
    cwd: str
    source_json: str
    originator_json: str | None
    model: str | None
    model_provider: str
    can_accept_direct_input: bool | None
    history_mode: Literal["includeTurns"]
    history_identity_digest: str
    history_content_digest: str
    history_ids: tuple[str, ...]
    history_shape: tuple[tuple[str, tuple[str, ...]], ...]
    history_records: tuple[CodexObservedRecord, ...]


@dataclass(frozen=True, slots=True)
class CodexSubscriptionAuthorization:
    """Caller-supplied evidence of the exact selection authorized for resume."""

    authorization_id: str
    selection_id: str
    endpoint_identity: str
    connection_generation: int
    pex_session_id: str
    thread_id: str
    project_id: str
    allow_resume: bool


@dataclass(frozen=True, slots=True)
class CodexSubscriptionReceipt:
    schema: Literal["pex.codex-existing-thread-subscription.v1"]
    authorization_id: str
    selection_id: str
    endpoint_identity: str
    connection_generation: int
    pex_session_id: str
    thread_id: str
    root_session_id: str
    project_id: str
    vendor_project_id: str | None
    cwd: str
    history_mode: Literal["includeTurns"]
    history_identity_digest: str
    history_record_count: int
    reconciliation_live_watermark: int
    observation_only: Literal[True]
    delivery_proven: Literal[False]


@dataclass(frozen=True, slots=True)
class CodexSubscriptionState:
    selected: CodexSelectedThread
    receipt: CodexSubscriptionReceipt
    reconciled_history_ids: tuple[str, ...]
    reconciled_history_shape: tuple[tuple[str, tuple[str, ...]], ...]
    reconciled_history_records: tuple[CodexObservedRecord, ...]
    reconciliation_records: tuple[CodexObservedRecord, ...]
    runtime_status: RuntimeStatus
    runtime_flags: tuple[str, ...] = ()
    active: bool = True
    invalidation_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CodexObservationBatch:
    endpoint_identity: str
    connection_generation: int
    thread_id: str
    after_live_watermark: int
    live_watermark: int
    records: tuple[CodexObservedRecord, ...]


class CodexObservationInterrupted(CodexSubscriptionError):
    """Validated observations before loss, never continuing delivery authority."""

    def __init__(self, message: str, *, batch: CodexObservationBatch, reason: str) -> None:
        super().__init__(message)
        self.batch = batch
        self.reason = reason


class _CodexRawDrainInterrupted(CodexSubscriptionError):
    """Bounded JSON prefix; semantic identity still requires validation."""

    def __init__(self, message: str, records: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.records = records


@dataclass(frozen=True, slots=True)
class _ThreadSnapshot:
    thread_id: str
    root_session_id: str
    vendor_project_id: str | None
    cwd: str
    source_json: str
    originator_json: str | None
    model: str | None
    model_provider: str
    can_accept_direct_input: bool | None
    runtime_status: RuntimeStatus
    runtime_flags: tuple[str, ...]
    history_ids: tuple[str, ...]
    history_shape: tuple[tuple[str, tuple[str, ...]], ...]
    records: tuple[CodexObservedRecord, ...]
    history_digest: str
    history_content_digest: str


def _bounded_id(value: object, field: str) -> str:
    try:
        return bounded_adapter_id(value, field=field)
    except ValueError as exc:
        raise CodexSubscriptionError(str(exc)) from exc


def _frozen_object(value: object, *, field: str, limit: int) -> tuple[dict[str, Any], str]:
    if not isinstance(value, dict):
        raise CodexSubscriptionError(f"{field} must be an object")
    try:
        encoded = strict_json_dumps(value, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise CodexSubscriptionError(f"{field} is not strict JSON") from exc
    if len(encoded.encode("utf-8")) > limit:
        raise CodexSubscriptionError(f"{field} exceeds the safety bound")
    decoded = strict_json_loads(encoded)
    if not isinstance(decoded, dict):  # pragma: no cover - encoded from a dict
        raise CodexSubscriptionError(f"{field} must be an object")
    return decoded, encoded


def _identity_json(value: object, field: str) -> str:
    if value is None or value == "" or value == {}:
        raise CodexSubscriptionError(f"Codex thread has no authoritative {field}")
    try:
        encoded = strict_json_dumps(value, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise CodexSubscriptionError(f"Codex {field} is not strict JSON") from exc
    if len(encoded.encode("utf-8")) > MAX_IDENTITY_JSON_BYTES:
        raise CodexSubscriptionError(f"Codex {field} exceeds the safety bound")
    return encoded


def _stable_record_id(
    source: Literal["history", "live_notification"],
    method: str,
    turn_id: str,
    item_id: str | None,
) -> str:
    encoded = strict_json_dumps(
        [source, method, turn_id, item_id], separators=(",", ":")
    )
    return f"codex:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


def _history_content_digest(records: tuple[CodexObservedRecord, ...]) -> str:
    encoded = strict_json_dumps(
        [
            [record.stable_id, record.method, record.payload_json]
            for record in records
        ],
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_cwd(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CodexSubscriptionError(f"{field} is missing")
    try:
        path = Path(value)
        if not path.is_absolute():
            raise CodexSubscriptionError(f"{field} is not absolute")
        return os.path.normcase(str(path.resolve()))
    except CodexSubscriptionError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise CodexSubscriptionError(f"{field} could not be resolved") from exc


def _one_consistent(values: list[object], field: str) -> object:
    present = [value for value in values if value is not None and value != ""]
    if not present:
        raise CodexSubscriptionError(f"Codex thread has no authoritative {field}")
    encoded = [_identity_json(value, field) for value in present]
    if any(item != encoded[0] for item in encoded[1:]):
        raise CodexSubscriptionError(f"Codex thread returned conflicting {field}")
    return present[0]


def _nullable_consistent(
    containers: tuple[dict[str, Any], ...],
    key: str,
    field: str,
) -> object | None:
    present = [container[key] for container in containers if key in container]
    if not present:
        return None
    try:
        encoded = [
            strict_json_dumps(value, sort_keys=True, separators=(",", ":"))
            for value in present
        ]
    except (TypeError, ValueError, RecursionError) as exc:
        raise CodexSubscriptionError(f"Codex {field} is not strict JSON") from exc
    if any(item != encoded[0] for item in encoded[1:]):
        raise CodexSubscriptionError(f"Codex thread returned conflicting {field}")
    return present[0]


def _nullable_bounded_id(value: object | None, field: str) -> str | None:
    if value is None:
        return None
    return _bounded_id(value, field)


def _nullable_identity_json(value: object | None, field: str) -> str | None:
    if value is None:
        return None
    return _identity_json(value, field)


def _runtime_status(value: object | None) -> RuntimeStatus:
    if isinstance(value, dict):
        value = value.get("type")
    return value if isinstance(value, str) and value in RUNTIME_STATUSES else "unknown"


def _runtime_flags(value: object | None) -> tuple[str, ...]:
    if not isinstance(value, dict) or "activeFlags" not in value:
        return ()
    flags = value["activeFlags"]
    if not isinstance(flags, list) or any(not isinstance(flag, str) for flag in flags):
        raise CodexSubscriptionError("Codex runtime flags are malformed")
    # Preserve unknown flags as evidence, never reinterpret them as active work.
    return tuple(flags)


def _is_truncated(container: dict[str, Any]) -> bool:
    if container.get("truncated") is True or container.get("hasMore") is True:
        return True
    if container.get("has_more") is True:
        return True
    next_cursor = container.get("nextCursor")
    legacy_cursor = container.get("next_cursor")
    return not (next_cursor is None or next_cursor == "") or not (
        legacy_cursor is None or legacy_cursor == ""
    )


def _history(
    thread: dict[str, Any],
) -> tuple[
    tuple[str, ...],
    tuple[tuple[str, tuple[str, ...]], ...],
    tuple[CodexObservedRecord, ...],
]:
    if _is_truncated(thread):
        raise CodexSubscriptionError("Codex thread history is truncated")
    turns = thread.get("turns")
    if not isinstance(turns, list):
        raise CodexSubscriptionError("Codex thread/read omitted includeTurns history")
    if len(turns) > MAX_HISTORY_TURNS:
        raise CodexSubscriptionError("Codex thread history exceeds the turn bound")
    identities: list[str] = []
    records: list[CodexObservedRecord] = []
    seen_turns: set[str] = set()
    seen_items: set[tuple[str, str]] = set()
    shape: list[tuple[str, tuple[str, ...]]] = []
    item_count = 0
    for turn in turns:
        frozen_turn, turn_json = _frozen_object(
            turn, field="Codex history turn", limit=MAX_PROTOCOL_JSON_BYTES
        )
        turn_id = _bounded_id(frozen_turn.get("id"), "Codex history turn id")
        if turn_id in seen_turns:
            raise CodexSubscriptionError("Codex thread history repeated a turn id")
        seen_turns.add(turn_id)
        turn_stable_id = _stable_record_id("history", "history/turn", turn_id, None)
        identities.append(turn_stable_id)
        records.append(
            CodexObservedRecord(
                source="history",
                stable_id=turn_stable_id,
                method="history/turn",
                turn_id=turn_id,
                item_id=None,
                live_sequence=None,
                payload_json=turn_json,
            )
        )
        items = frozen_turn.get("items", [])
        if not isinstance(items, list):
            raise CodexSubscriptionError("Codex history turn items are malformed")
        item_count += len(items)
        if item_count > MAX_HISTORY_ITEMS:
            raise CodexSubscriptionError("Codex thread history exceeds the item bound")
        turn_item_ids: list[str] = []
        for item in items:
            frozen_item, item_json = _frozen_object(
                item, field="Codex history item", limit=MAX_PROTOCOL_JSON_BYTES
            )
            item_id = _bounded_id(frozen_item.get("id"), "Codex history item id")
            item_key = (turn_id, item_id)
            if item_key in seen_items:
                raise CodexSubscriptionError("Codex thread history repeated an item id")
            seen_items.add(item_key)
            turn_item_ids.append(item_id)
            item_stable_id = _stable_record_id(
                "history", "history/item", turn_id, item_id
            )
            identities.append(item_stable_id)
            records.append(
                CodexObservedRecord(
                    source="history",
                    stable_id=item_stable_id,
                    method="history/item",
                    turn_id=turn_id,
                    item_id=item_id,
                    live_sequence=None,
                    payload_json=item_json,
                )
            )
        shape.append((turn_id, tuple(turn_item_ids)))
    return tuple(identities), tuple(shape), tuple(records)


def _parse_snapshot(response: object, *, require_history: bool = True) -> _ThreadSnapshot:
    frozen, _ = _frozen_object(
        response, field="Codex thread response", limit=MAX_PROTOCOL_JSON_BYTES
    )
    if _is_truncated(frozen):
        raise CodexSubscriptionError("Codex thread response is truncated")
    thread = frozen.get("thread")
    if not isinstance(thread, dict):
        raise CodexSubscriptionError("Codex thread response omitted the thread")
    thread_id = _bounded_id(thread.get("id"), "Codex thread id")
    root_session_id = _bounded_id(
        _one_consistent(
            [thread.get("sessionId"), frozen.get("sessionId")], "root session id"
        ),
        "Codex root session id",
    )
    if "projectId" not in thread and "projectId" not in frozen:
        raise CodexSubscriptionError(
            "Codex thread has no authoritative vendor project field"
        )
    vendor_project_id = _nullable_bounded_id(
        _nullable_consistent((thread, frozen), "projectId", "project id"),
        "Codex project id",
    )
    cwd = _canonical_cwd(
        _one_consistent([thread.get("cwd"), frozen.get("cwd")], "workspace"),
        "Codex thread workspace",
    )
    source_json = _identity_json(
        _one_consistent([thread.get("source"), frozen.get("source")], "source"),
        "source",
    )
    originator_json = _nullable_identity_json(
        _nullable_consistent((thread, frozen), "originator", "originator"),
        "originator",
    )
    model = _nullable_bounded_id(
        _nullable_consistent((thread, frozen), "model", "model"),
        "Codex model",
    )
    model_provider = _bounded_id(
        _one_consistent(
            [thread.get("modelProvider"), frozen.get("modelProvider")],
            "model provider",
        ),
        "Codex model provider",
    )
    direct_values = [
        value
        for value in (
            thread.get("canAcceptDirectInput"),
            frozen.get("canAcceptDirectInput"),
        )
        if value is not None
    ]
    if any(type(value) is not bool for value in direct_values):
        raise CodexSubscriptionError("Codex direct-input capability is malformed")
    if len(set(direct_values)) > 1:
        raise CodexSubscriptionError("Codex direct-input capability conflicted")
    direct = direct_values[0] if direct_values else None
    status = _nullable_consistent((thread, frozen), "status", "runtime status")
    runtime_status = _runtime_status(status)
    runtime_flags = _runtime_flags(status)
    if require_history:
        history_ids, history_shape, records = _history(thread)
    else:
        history_ids, history_shape, records = (), (), ()
    digest = hashlib.sha256("\n".join(history_ids).encode("utf-8")).hexdigest()
    content_digest = _history_content_digest(records)
    return _ThreadSnapshot(
        thread_id=thread_id,
        root_session_id=root_session_id,
        vendor_project_id=vendor_project_id,
        cwd=cwd,
        source_json=source_json,
        originator_json=originator_json,
        model=model,
        model_provider=model_provider,
        can_accept_direct_input=direct,
        runtime_status=runtime_status,
        runtime_flags=runtime_flags,
        history_ids=history_ids,
        history_shape=history_shape,
        records=records,
        history_digest=digest,
        history_content_digest=content_digest,
    )


def _selection_id(payload: dict[str, object]) -> str:
    encoded = strict_json_dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _selection_payload(selected: CodexSelectedThread) -> dict[str, object]:
    return {
        "endpoint_identity": selected.endpoint_identity,
        "connection_generation": selected.connection_generation,
        "pex_session_id": selected.pex_session_id,
        "thread_id": selected.thread_id,
        "root_session_id": selected.root_session_id,
        "project_id": selected.project_id,
        "vendor_project_id": selected.vendor_project_id,
        "cwd": selected.cwd,
        "source_json": selected.source_json,
        "originator_json": selected.originator_json,
        "model": selected.model,
        "model_provider": selected.model_provider,
        "can_accept_direct_input": selected.can_accept_direct_input,
        "history_mode": selected.history_mode,
        "history_identity_digest": selected.history_identity_digest,
        "history_content_digest": selected.history_content_digest,
    }


def _flatten_history_shape(
    shape: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[str, ...]:
    identities: list[str] = []
    for turn_id, item_ids in shape:
        identities.append(_stable_record_id("history", "history/turn", turn_id, None))
        identities.extend(
            _stable_record_id("history", "history/item", turn_id, item_id)
            for item_id in item_ids
        )
    return tuple(identities)


def _history_digest(identities: tuple[str, ...]) -> str:
    return hashlib.sha256("\n".join(identities).encode("utf-8")).hexdigest()


def _snapshot_matches(left: _ThreadSnapshot, right: _ThreadSnapshot) -> bool:
    return (
        left.thread_id == right.thread_id
        and left.root_session_id == right.root_session_id
        and left.vendor_project_id == right.vendor_project_id
        and left.cwd == right.cwd
        and left.source_json == right.source_json
        and left.originator_json == right.originator_json
        and left.model == right.model
        and left.model_provider == right.model_provider
        and left.can_accept_direct_input == right.can_accept_direct_input
    )


def _ordered_prefix(before: tuple[str, ...], after: tuple[str, ...]) -> bool:
    return len(before) <= len(after) and after[: len(before)] == before


def _history_extends(
    before: tuple[tuple[str, tuple[str, ...]], ...],
    after: tuple[tuple[str, tuple[str, ...]], ...],
) -> bool:
    if not _ordered_prefix(
        tuple(turn_id for turn_id, _ in before),
        tuple(turn_id for turn_id, _ in after),
    ):
        return False
    return all(
        _ordered_prefix(before_items, after[index][1])
        for index, (_, before_items) in enumerate(before)
    )


class CodexExistingThreadSubscription:
    """Coordinate one explicitly authorized, observation-only thread subscription."""

    def __init__(self, transport: CodexSubscriptionTransport) -> None:
        self.transport = transport
        self._lock = asyncio.Lock()
        self._state: CodexSubscriptionState | None = None
        self._live_watermark = 0
        self._seen_live: dict[str, str] = {}
        self._live_phase: dict[tuple[str, str | None], int] = {}
        self._runtime_status: RuntimeStatus = "unknown"
        self._runtime_flags: tuple[str, ...] = ()
        self._interrupted_batch: CodexObservationBatch | None = None

    @property
    def state(self) -> CodexSubscriptionState | None:
        return self._state

    @property
    def interrupted_batch(self) -> CodexObservationBatch | None:
        """Frozen prefix available even if cleanup cancellation hides the error.

        This is record-only recovery evidence, never a live subscription token.
        """
        return self._interrupted_batch

    def _token(self) -> tuple[str, int]:
        try:
            endpoint, generation = self.transport.connection_token()
        except Exception as exc:
            raise CodexSubscriptionError("Codex transport identity is unavailable") from exc
        endpoint = _bounded_id(endpoint, "Codex endpoint identity")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise CodexSubscriptionError("Codex connection generation is invalid")
        return endpoint, generation

    def _invalidate(self, reason: str) -> None:
        if self._state is not None:
            self._state = replace(self._state, active=False, invalidation_reason=reason)

    def _require_token(self, expected: tuple[str, int]) -> None:
        if self._token() != expected:
            self._invalidate("connection_generation_changed")
            raise CodexSubscriptionError("Codex connection generation changed")

    async def inspect_thread(
        self,
        *,
        pex_session_id: str,
        thread_id: str,
        project_id: str,
        cwd: str,
        expected_vendor_project_id: str | None = None,
    ) -> CodexSelectedThread:
        async with self._lock:
            await self.transport.ensure_ready()
            token = self._token()
            pex_session_id = _bounded_id(pex_session_id, "PEX session id")
            thread_id = _bounded_id(thread_id, "Codex thread id")
            project_id = _bounded_id(project_id, "project id")
            if expected_vendor_project_id is not None:
                expected_vendor_project_id = _bounded_id(
                    expected_vendor_project_id, "expected Codex project id"
                )
            expected_cwd = _canonical_cwd(cwd, "selected project workspace")
            response = await self.transport.request(
                "thread/read", {"threadId": thread_id, "includeTurns": True}
            )
            self._require_token(token)
            snapshot = _parse_snapshot(response)
            if snapshot.thread_id != thread_id:
                raise CodexSubscriptionError("Codex thread/read returned another thread")
            if (
                expected_vendor_project_id is not None
                and snapshot.vendor_project_id != expected_vendor_project_id
            ):
                raise CodexSubscriptionError(
                    "Codex thread/read returned another vendor project"
                )
            if snapshot.cwd != expected_cwd:
                raise CodexSubscriptionError("Codex thread/read returned another workspace")
            identity = {
                "endpoint_identity": token[0],
                "connection_generation": token[1],
                "pex_session_id": pex_session_id,
                "thread_id": thread_id,
                "root_session_id": snapshot.root_session_id,
                "project_id": project_id,
                "vendor_project_id": snapshot.vendor_project_id,
                "cwd": expected_cwd,
                "source_json": snapshot.source_json,
                "originator_json": snapshot.originator_json,
                "model": snapshot.model,
                "model_provider": snapshot.model_provider,
                "can_accept_direct_input": snapshot.can_accept_direct_input,
                "history_mode": "includeTurns",
                "history_identity_digest": snapshot.history_digest,
                "history_content_digest": snapshot.history_content_digest,
            }
            return CodexSelectedThread(
                selection_id=_selection_id(identity),
                endpoint_identity=token[0],
                connection_generation=token[1],
                pex_session_id=pex_session_id,
                thread_id=thread_id,
                root_session_id=snapshot.root_session_id,
                project_id=project_id,
                vendor_project_id=snapshot.vendor_project_id,
                cwd=expected_cwd,
                source_json=snapshot.source_json,
                originator_json=snapshot.originator_json,
                model=snapshot.model,
                model_provider=snapshot.model_provider,
                can_accept_direct_input=snapshot.can_accept_direct_input,
                history_mode="includeTurns",
                history_identity_digest=snapshot.history_digest,
                history_content_digest=snapshot.history_content_digest,
                history_ids=snapshot.history_ids,
                history_shape=snapshot.history_shape,
                history_records=snapshot.records,
            )

    def _validate_authorization(
        self,
        selected: CodexSelectedThread,
        authorization: CodexSubscriptionAuthorization,
    ) -> None:
        if type(authorization.allow_resume) is not bool or not authorization.allow_resume:
            raise CodexSubscriptionError("Codex thread resume was not explicitly authorized")
        for value, field in (
            (authorization.authorization_id, "subscription authorization id"),
            (authorization.selection_id, "authorized selection id"),
            (authorization.endpoint_identity, "authorized endpoint identity"),
            (authorization.pex_session_id, "authorized PEX session id"),
            (authorization.thread_id, "authorized Codex thread id"),
            (authorization.project_id, "authorized project id"),
        ):
            _bounded_id(value, field)
        if (
            isinstance(authorization.connection_generation, bool)
            or not isinstance(authorization.connection_generation, int)
            or authorization.connection_generation < 1
        ):
            raise CodexSubscriptionError("Codex authorization generation is invalid")
        expected = (
            selected.selection_id,
            selected.endpoint_identity,
            selected.connection_generation,
            selected.pex_session_id,
            selected.thread_id,
            selected.project_id,
        )
        observed = (
            authorization.selection_id,
            authorization.endpoint_identity,
            authorization.connection_generation,
            authorization.pex_session_id,
            authorization.thread_id,
            authorization.project_id,
        )
        if observed != expected:
            raise CodexSubscriptionError("Codex resume authorization binding mismatch")

    def _validate_selected(self, selected: CodexSelectedThread) -> None:
        if selected.history_mode != "includeTurns":
            raise CodexSubscriptionError("Codex selection history mode is invalid")
        for value, field in (
            (selected.endpoint_identity, "Codex endpoint identity"),
            (selected.pex_session_id, "PEX session id"),
            (selected.thread_id, "Codex thread id"),
            (selected.root_session_id, "Codex root session id"),
            (selected.project_id, "project id"),
            (selected.model_provider, "Codex model provider"),
        ):
            _bounded_id(value, field)
        if selected.vendor_project_id is not None:
            _bounded_id(selected.vendor_project_id, "Codex project id")
        if selected.model is not None:
            _bounded_id(selected.model, "Codex model")
        if (
            isinstance(selected.connection_generation, bool)
            or not isinstance(selected.connection_generation, int)
            or selected.connection_generation < 1
        ):
            raise CodexSubscriptionError("Codex selection generation is invalid")
        if _canonical_cwd(selected.cwd, "selected project workspace") != selected.cwd:
            raise CodexSubscriptionError("Codex selection workspace is not canonical")
        for encoded, field in (
            (selected.source_json, "source"),
            (selected.originator_json, "originator"),
        ):
            if encoded is None:
                if field == "originator":
                    continue
                raise CodexSubscriptionError("Codex source is missing")
            if not isinstance(encoded, str):
                raise CodexSubscriptionError(f"Codex {field} is not JSON text")
            if len(encoded.encode("utf-8")) > MAX_IDENTITY_JSON_BYTES:
                raise CodexSubscriptionError(f"Codex {field} exceeds the safety bound")
            try:
                if strict_json_dumps(
                    strict_json_loads(encoded), sort_keys=True, separators=(",", ":")
                ) != encoded:
                    raise CodexSubscriptionError(f"Codex {field} is not canonical JSON")
            except (TypeError, ValueError, RecursionError) as exc:
                raise CodexSubscriptionError(f"Codex {field} is not strict JSON") from exc
        if selected.can_accept_direct_input is not None and type(
            selected.can_accept_direct_input
        ) is not bool:
            raise CodexSubscriptionError("Codex direct-input capability is malformed")
        if _flatten_history_shape(selected.history_shape) != selected.history_ids:
            raise CodexSubscriptionError("Codex selection history shape is inconsistent")
        if _history_digest(selected.history_ids) != selected.history_identity_digest:
            raise CodexSubscriptionError("Codex selection history digest is inconsistent")
        if _history_content_digest(selected.history_records) != selected.history_content_digest:
            raise CodexSubscriptionError(
                "Codex selection history content digest is inconsistent"
            )
        if tuple(record.stable_id for record in selected.history_records) != selected.history_ids:
            raise CodexSubscriptionError("Codex selection history records are inconsistent")
        for record in selected.history_records:
            if record.source != "history" or record.live_sequence is not None:
                raise CodexSubscriptionError("Codex selection contains non-history records")
            expected_id = _stable_record_id(
                "history", "history/turn", record.turn_id, None
            )
            expected_method = "history/turn"
            if record.item_id is not None:
                expected_method = "history/item"
                expected_id = _stable_record_id(
                    "history", expected_method, record.turn_id, record.item_id
                )
            if record.stable_id != expected_id or record.method != expected_method:
                raise CodexSubscriptionError("Codex history record identity is malformed")
            if len(record.payload_json.encode("utf-8")) > MAX_PROTOCOL_JSON_BYTES:
                raise CodexSubscriptionError("Codex history record exceeds the safety bound")
            try:
                payload = strict_json_loads(record.payload_json)
                if not isinstance(payload, dict):
                    raise CodexSubscriptionError("Codex history record is not an object")
                if strict_json_dumps(
                    payload, sort_keys=True, separators=(",", ":")
                ) != record.payload_json:
                    raise CodexSubscriptionError("Codex history record is not canonical JSON")
            except (TypeError, ValueError, RecursionError) as exc:
                raise CodexSubscriptionError("Codex history record is not strict JSON") from exc
            if payload.get("id") != (record.item_id or record.turn_id):
                raise CodexSubscriptionError("Codex history payload identity is inconsistent")
        if _selection_id(_selection_payload(selected)) != selected.selection_id:
            raise CodexSubscriptionError("Codex selection identity is invalid")

    def _notification_envelope(
        self,
        notification: dict[str, Any],
        connection_generation: int,
    ) -> tuple[dict[str, Any], str, str]:
        try:
            frozen, encoded = _frozen_object(
                notification,
                field="Codex live notification",
                limit=MAX_PROTOCOL_JSON_BYTES,
            )
        except CodexSubscriptionError:
            self._invalidate("malformed_notification")
            raise
        method = frozen.get("method")
        if not isinstance(method, str):
            self._invalidate("malformed_notification_method")
            raise CodexSubscriptionError("Codex live notification has no method")
        observed_generation = frozen.get("connection_generation")
        if (
            isinstance(observed_generation, bool)
            or not isinstance(observed_generation, int)
            or observed_generation < 1
        ):
            self._invalidate("malformed_notification_generation")
            raise CodexSubscriptionError(
                "Codex live notification has no valid connection generation"
            )
        if observed_generation != connection_generation:
            self._invalidate("foreign_notification_generation")
            raise CodexSubscriptionError(
                "Codex live notification belongs to another connection generation"
            )
        if type(frozen.get("shared_server_request")) is not bool:
            self._invalidate("malformed_notification_envelope")
            raise CodexSubscriptionError("Codex live notification envelope is malformed")
        return frozen, encoded, method

    def _notification_thread_id(
        self,
        frozen: dict[str, Any],
        method: str,
    ) -> tuple[dict[str, Any], str]:
        params = frozen.get("params")
        if not isinstance(params, dict):
            self._invalidate("malformed_notification_params")
            raise CodexSubscriptionError("Codex live notification has no params")
        thread_ids: list[str] = []
        try:
            if "threadId" in params:
                thread_ids.append(
                    _bounded_id(params["threadId"], "notification thread id")
                )
            thread = params.get("thread")
            if method.startswith("thread/") and isinstance(thread, dict) and "id" in thread:
                thread_ids.append(_bounded_id(thread["id"], "notification thread id"))
        except CodexSubscriptionError:
            self._invalidate("malformed_notification_identity")
            raise
        if not thread_ids or any(value != thread_ids[0] for value in thread_ids[1:]):
            self._invalidate("conflicting_notification_identity")
            raise CodexSubscriptionError(
                "Codex live notification has conflicting thread identity"
            )
        return params, thread_ids[0]

    def _clean_queue_before_resume(
        self,
        *,
        thread_id: str,
        connection_generation: int,
    ) -> None:
        queued = self._drain_raw()
        for notification in queued:
            frozen, _, method = self._notification_envelope(
                notification, connection_generation
            )
            if not method.startswith(("thread/", "turn/", "item/")):
                continue
            _, observed_thread = self._notification_thread_id(frozen, method)
            if observed_thread != thread_id:
                raise CodexSubscriptionError(
                    "Codex pre-resume notification belongs to another thread"
                )
            raise CodexSubscriptionError(
                "Codex thread notification queue was not clean before resume"
            )

    async def _close_after_failed_resume(self) -> None:
        # Own exactly one close operation. Cancelling its shielded await does
        # not stop that operation, so settle it before releasing the coordinator
        # lock or returning the original subscription failure. Never retry close.
        close_task = asyncio.create_task(self.transport.close())
        while not close_task.done():
            try:
                await asyncio.shield(close_task)
            except asyncio.CancelledError:
                # Either another caller cancellation or cancellation of the
                # owned close itself; the loop's done check distinguishes them.
                continue
            except BaseException:
                break
        if not close_task.cancelled():
            try:
                close_task.result()
            except BaseException:
                # The original failure remains primary. Settled cleanup is not
                # proof of successful closure, and grants no reuse authority.
                pass

    async def subscribe(
        self,
        selected: CodexSelectedThread,
        authorization: CodexSubscriptionAuthorization,
    ) -> CodexSubscriptionState:
        async with self._lock:
            if self._state is not None and self._state.active:
                raise CodexSubscriptionError("Codex coordinator already has an active subscription")
            self._validate_selected(selected)
            self._validate_authorization(selected, authorization)
            token = (selected.endpoint_identity, selected.connection_generation)
            self._require_token(token)
            reread = _parse_snapshot(
                await self.transport.request(
                    "thread/read", {"threadId": selected.thread_id, "includeTurns": True}
                )
            )
            self._require_token(token)
            if not self._selected_identity_matches(selected, reread):
                raise CodexSubscriptionError("Codex thread identity changed before resume")
            if not _history_extends(selected.history_shape, reread.history_shape):
                raise CodexSubscriptionError("Codex history was reordered before resume")
            self._clean_queue_before_resume(
                thread_id=selected.thread_id,
                connection_generation=token[1],
            )
            self._require_token(token)
            try:
                resumed = _parse_snapshot(
                    await self.transport.request(
                        "thread/resume", {"threadId": selected.thread_id}
                    ),
                    require_history=False,
                )
                self._require_token(token)
                if not _snapshot_matches(reread, resumed):
                    raise CodexSubscriptionError("Codex thread/resume identity mismatch")
                during = self._drain_raw()
                post = _parse_snapshot(
                    await self.transport.request(
                        "thread/read",
                        {"threadId": selected.thread_id, "includeTurns": True},
                    )
                )
                self._require_token(token)
                if not _snapshot_matches(reread, post):
                    raise CodexSubscriptionError(
                        "Codex thread identity changed during reconciliation"
                    )
                if not _history_extends(reread.history_shape, post.history_shape):
                    raise CodexSubscriptionError(
                        "Codex reconciliation history was reordered or truncated"
                    )
                self._runtime_status = post.runtime_status
                self._runtime_flags = post.runtime_flags
                after = self._drain_raw()
                live_records = self._accept_live(
                    during + after,
                    selected.thread_id,
                    token[1],
                    post.history_shape,
                )
            except BaseException:
                await self._close_after_failed_resume()
                raise
            receipt = CodexSubscriptionReceipt(
                schema=SUBSCRIPTION_SCHEMA,
                authorization_id=authorization.authorization_id,
                selection_id=selected.selection_id,
                endpoint_identity=token[0],
                connection_generation=token[1],
                pex_session_id=selected.pex_session_id,
                thread_id=selected.thread_id,
                root_session_id=selected.root_session_id,
                project_id=selected.project_id,
                vendor_project_id=selected.vendor_project_id,
                cwd=selected.cwd,
                history_mode="includeTurns",
                history_identity_digest=post.history_digest,
                history_record_count=len(post.records),
                reconciliation_live_watermark=self._live_watermark,
                observation_only=True,
                delivery_proven=False,
            )
            self._state = CodexSubscriptionState(
                selected=selected,
                receipt=receipt,
                reconciled_history_ids=post.history_ids,
                reconciled_history_shape=post.history_shape,
                reconciled_history_records=post.records,
                reconciliation_records=live_records,
                runtime_status=self._runtime_status,
                runtime_flags=self._runtime_flags,
            )
            return self._state

    @staticmethod
    def _selected_identity_matches(
        selected: CodexSelectedThread, snapshot: _ThreadSnapshot
    ) -> bool:
        return (
            selected.thread_id == snapshot.thread_id
            and selected.root_session_id == snapshot.root_session_id
            and selected.vendor_project_id == snapshot.vendor_project_id
            and selected.cwd == snapshot.cwd
            and selected.source_json == snapshot.source_json
            and selected.originator_json == snapshot.originator_json
            and selected.model == snapshot.model
            and selected.model_provider == snapshot.model_provider
            and selected.can_accept_direct_input == snapshot.can_accept_direct_input
        )

    def _drain_raw(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        encoded_bytes = 0
        while True:
            remaining = MAX_NOTIFICATIONS_PER_DRAIN + 1 - len(records)
            batch = self.transport.drain_notifications(limit=min(256, remaining))
            if not isinstance(batch, list) or len(batch) > min(256, remaining):
                self._invalidate("notification_retention_bound")
                raise _CodexRawDrainInterrupted(
                    "Codex notifications exceeded the safety bound", records
                )
            for record in batch:
                if not isinstance(record, dict):
                    self._invalidate("malformed_notification")
                    raise _CodexRawDrainInterrupted(
                        "Codex notification was not an object", records
                    )
                try:
                    encoded_bytes += len(
                        strict_json_dumps(
                            record, sort_keys=True, separators=(",", ":")
                        ).encode("utf-8")
                    )
                except (TypeError, ValueError, RecursionError) as exc:
                    self._invalidate("malformed_notification")
                    raise _CodexRawDrainInterrupted(
                        "Codex notification was not strict JSON", records
                    ) from exc
                if encoded_bytes > MAX_NOTIFICATION_BATCH_JSON_BYTES:
                    self._invalidate("notification_retention_bound")
                    raise _CodexRawDrainInterrupted(
                        "Codex notifications exceeded the byte bound", records
                    )
                if len(records) >= MAX_NOTIFICATIONS_PER_DRAIN:
                    self._invalidate("notification_retention_bound")
                    raise _CodexRawDrainInterrupted(
                        "Codex notifications exceeded the safety bound", records
                    )
                records.append(record)
            if not batch:
                break
        return records

    def _accept_live(
        self,
        notifications: list[dict[str, Any]],
        thread_id: str,
        connection_generation: int,
        history_shape: tuple[tuple[str, tuple[str, ...]], ...],
        *,
        accepted_prefix: list[CodexObservedRecord] | None = None,
    ) -> tuple[CodexObservedRecord, ...]:
        history_turns = {turn_id for turn_id, _ in history_shape}
        accepted = accepted_prefix if accepted_prefix is not None else []
        for notification in notifications:
            frozen, encoded, method = self._notification_envelope(
                notification, connection_generation
            )
            if not method.startswith(("thread/", "turn/", "item/")):
                continue
            params, observed_thread = self._notification_thread_id(frozen, method)
            if observed_thread != thread_id:
                self._invalidate("foreign_thread_notification")
                raise CodexSubscriptionError("Codex live notification belongs to another thread")
            if method in {"thread/closed", "thread/archived", "thread/deleted"}:
                # A connected App Server socket is not proof this selected
                # worker remains available. Do not auto-resume an archived or
                # unloaded thread, and never turn its closure into completion.
                self._invalidate(f"vendor_{method.replace('/', '_')}")
                raise _CodexThreadUnavailable(
                    "Codex selected thread became unavailable"
                )
            if method in {"thread/started", "thread/status/changed"}:
                if method == "thread/status/changed":
                    thread = params.get("thread")
                    try:
                        status = _nullable_consistent(
                            (params, thread if isinstance(thread, dict) else {}),
                            "status",
                            "runtime status",
                        )
                    except CodexSubscriptionError:
                        self._invalidate("conflicting_runtime_status")
                        raise
                    if not isinstance(status, dict):
                        self._invalidate("malformed_runtime_status")
                        raise CodexSubscriptionError("Codex runtime status is malformed")
                    try:
                        flags = _runtime_flags(status)
                    except CodexSubscriptionError:
                        self._invalidate("malformed_runtime_flags")
                        raise
                if len(self._seen_live) >= MAX_LIVE_IDENTITIES:
                    self._invalidate("live_identity_bound")
                    raise CodexSubscriptionError(
                        "Codex live identities exceeded the lifetime bound"
                    )
                self._live_watermark += 1
                stable_id = _stable_record_id(
                    "live_notification",
                    f"{method}:{connection_generation}:{self._live_watermark}",
                    "",
                    None,
                )
                self._seen_live[stable_id] = encoded
                accepted.append(
                    CodexObservedRecord(
                        source="live_notification",
                        stable_id=stable_id,
                        method=method,
                        turn_id="",
                        item_id=None,
                        live_sequence=self._live_watermark,
                        payload_json=encoded,
                    )
                )
                if method == "thread/status/changed":
                    self._runtime_status = _runtime_status(status)
                    self._runtime_flags = flags
                continue
            if method not in {
                "turn/started",
                "turn/completed",
                "item/started",
                "item/completed",
            }:
                continue
            turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
            turn_ids: list[str] = []
            try:
                if "turnId" in params:
                    turn_ids.append(
                        _bounded_id(params["turnId"], "notification turn id")
                    )
                if "id" in turn:
                    turn_ids.append(_bounded_id(turn["id"], "notification turn id"))
            except CodexSubscriptionError:
                self._invalidate("malformed_notification_identity")
                raise
            if not turn_ids or any(value != turn_ids[0] for value in turn_ids[1:]):
                self._invalidate("conflicting_notification_identity")
                raise CodexSubscriptionError(
                    "Codex live notification has conflicting turn identity"
                )
            turn_id = turn_ids[0]
            item_id: str | None = None
            if method.startswith("item/"):
                item = params.get("item")
                if not isinstance(item, dict):
                    self._invalidate("malformed_item_notification")
                    raise CodexSubscriptionError("Codex item notification omitted the item")
                item_ids: list[str] = []
                try:
                    if "itemId" in params:
                        item_ids.append(
                            _bounded_id(params["itemId"], "notification item id")
                        )
                    if "id" in item:
                        item_ids.append(_bounded_id(item["id"], "notification item id"))
                except CodexSubscriptionError:
                    self._invalidate("malformed_notification_identity")
                    raise
                if not item_ids or any(value != item_ids[0] for value in item_ids[1:]):
                    self._invalidate("conflicting_notification_identity")
                    raise CodexSubscriptionError(
                        "Codex live notification has conflicting item identity"
                    )
                item_id = item_ids[0]
            entity = (turn_id, item_id)
            phase = 1 if method.endswith("/started") else 2
            stable_id = _stable_record_id(
                "live_notification", method, turn_id, item_id
            )
            prior_phase = self._live_phase.get(entity, 0)
            if phase < prior_phase:
                self._invalidate("reordered_live_notification")
                raise CodexSubscriptionError("Codex live notification order regressed")
            prior_payload = self._seen_live.get(stable_id)
            if prior_payload is not None and prior_payload != encoded:
                self._invalidate("conflicting_duplicate_notification")
                raise CodexSubscriptionError(
                    "Codex repeated a live identity with conflicting content"
                )
            if prior_payload is not None:
                continue
            turn_observed = turn_id in history_turns or self._live_phase.get(
                (turn_id, None), 0
            ) > 0
            if item_id is not None and not turn_observed:
                self._invalidate("missing_live_parent")
                raise CodexSubscriptionError("Codex item has no observed turn identity")
            if phase == 2 and prior_phase == 0 and not turn_observed:
                self._invalidate("missing_live_parent")
                raise CodexSubscriptionError("Codex completion has no observed turn identity")
            if len(self._seen_live) >= MAX_LIVE_IDENTITIES or (
                entity not in self._live_phase
                and len(self._live_phase) >= MAX_LIVE_IDENTITIES
            ):
                self._invalidate("live_identity_bound")
                raise CodexSubscriptionError(
                    "Codex live identities exceeded the lifetime bound"
                )
            self._live_watermark += 1
            self._seen_live[stable_id] = encoded
            self._live_phase[entity] = phase
            accepted.append(
                CodexObservedRecord(
                    source="live_notification",
                    stable_id=stable_id,
                    method=method,
                    turn_id=turn_id,
                    item_id=item_id,
                    live_sequence=self._live_watermark,
                    payload_json=encoded,
                )
            )
        return tuple(accepted)

    async def refresh_control_snapshot(self) -> CodexControlSnapshot:
        """Read current identity/turns without draining the pipeline's own queue.

        The action caller may already be inside consumer ingestion. Waiting for
        that consumer here would deadlock; newly discovered input must invalidate
        its plan instead of being replayed as a synthetic human event.
        """
        async with self._lock:
            state = self._state
            if state is None or not state.active:
                raise CodexSubscriptionError("Codex subscription is not active")
            token = (state.receipt.endpoint_identity, state.receipt.connection_generation)
            self._require_token(token)
            read = await self.transport.read_current_thread()
            self._require_token(token)
            if not isinstance(read, SharedCodexReadSnapshot) or read.connection_token != token:
                raise CodexSubscriptionError("Codex control read has no matching witness")
            response = strict_json_loads(read.result_json)
            snapshot = _parse_snapshot(response)
            if not self._selected_identity_matches(state.selected, snapshot):
                raise CodexSubscriptionError("Codex control read changed selected identity")
            if snapshot.can_accept_direct_input is not True:
                raise CodexSubscriptionError("Codex direct input is not available")
            thread = response["thread"]
            status = _nullable_consistent((thread, response), "status", "runtime status")
            if (
                not isinstance(status, dict)
                or snapshot.runtime_status not in {"idle", "active"}
                or snapshot.runtime_flags
                or (snapshot.runtime_status == "active" and status.get("activeFlags") != [])
            ):
                raise CodexSubscriptionError("Codex runtime does not permit ordinary text control")
            active: list[str] = []
            inputs: list[dict[str, Any]] = []
            for turn in thread["turns"]:
                if (
                    turn.get("itemsView") != "full" or _is_truncated(turn)
                    or turn.get("status") not in {
                        "inProgress", "completed", "interrupted", "failed",
                    }
                    or not isinstance(turn.get("items"), list)
                ):
                    raise CodexSubscriptionError("Codex control history is incomplete")
                if turn["status"] == "inProgress":
                    active.append(turn["id"])
                for item in turn["items"]:
                    if (
                        not isinstance(item.get("type"), str)
                        or item["type"] not in CONTROL_HISTORY_ITEM_TYPES
                        or _is_truncated(item)
                    ):
                        raise CodexSubscriptionError("Codex control item is incomplete")
                    if item["type"] != "userMessage":
                        continue
                    content = item.get("content")
                    _, coverage = CodexAdapter._normalize_user_message_content(item)
                    if (
                        "clientId" not in item
                        or (item["clientId"] is not None and (
                            not isinstance(item["clientId"], str)
                            or _bounded_id(item["clientId"], "Codex client message id")
                            != item["clientId"]
                        ))
                        or coverage["content_status"] != "complete"
                        or coverage["content_redacted"] or coverage["content_truncated"]
                        or not isinstance(content, list) or not content
                        or any(
                            not isinstance(part, dict) or part.get("type") != "text"
                            or not isinstance(part.get("text"), str)
                            or not part["text"].strip() or "\x00" in part["text"]
                            or _is_truncated(part)
                            for part in content
                        )
                    ):
                        # Non-text/unknown content remains observable, but this
                        # text-control path cannot certify its human intent.
                        raise CodexSubscriptionError("Codex control input is not complete text")
                    inputs.append({
                        "turn_id": turn["id"], "item_id": item["id"],
                        "client_id": item["clientId"], "content": content,
                    })
            if (
                (snapshot.runtime_status == "idle" and active)
                or (snapshot.runtime_status == "active" and len(active) != 1)
            ):
                raise CodexSubscriptionError("Codex runtime and active turns conflict")
            encoded = strict_json_dumps(inputs, sort_keys=True, separators=(",", ":"))
            return CodexControlSnapshot(
                receipt=state.receipt, read=read,
                active_turn_id=active[0] if active else None,
                user_inputs_json=encoded,
                user_inputs_digest=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
            )

    async def drain_live(self) -> CodexObservationBatch:
        async with self._lock:
            state = self._state
            if state is None or not state.active:
                raise CodexSubscriptionError("Codex subscription is not active")
            token = (state.receipt.endpoint_identity, state.receipt.connection_generation)
            self._require_token(token)
            after = self._live_watermark
            raw_failure: _CodexRawDrainInterrupted | None = None
            try:
                raw = self._drain_raw()
            except _CodexRawDrainInterrupted as exc:
                raw = exc.records
                raw_failure = exc
            self._require_token(token)
            accepted_prefix: list[CodexObservedRecord] = []
            try:
                records = self._accept_live(
                    raw,
                    state.receipt.thread_id,
                    token[1],
                    state.reconciled_history_shape,
                    accepted_prefix=accepted_prefix,
                )
                if raw_failure is not None:
                    raise raw_failure
            except CodexSubscriptionError as exc:
                if self._state is not None and self._state.active:
                    self._invalidate("live_observation_interrupted")
                reason = (
                    self._state.invalidation_reason if self._state is not None else None
                ) or "live_observation_interrupted"
                interrupted = CodexObservationInterrupted(
                    str(exc),
                    batch=CodexObservationBatch(
                        endpoint_identity=token[0],
                        connection_generation=token[1],
                        thread_id=state.receipt.thread_id,
                        after_live_watermark=after,
                        live_watermark=self._live_watermark,
                        records=tuple(accepted_prefix),
                    ),
                    reason=reason,
                )
                # Publish the immutable prefix before the cleanup await. An
                # adapter finalizer may need it even if cancellation prevents
                # its receiver from handling the interruption exception.
                self._interrupted_batch = interrupted.batch
                # This is only the dedicated observer/proxy connection. Never
                # send stop, delete, unsubscribe or another worker-side action.
                await self._close_after_failed_resume()
                raise interrupted from exc
            if (
                self._runtime_status != state.runtime_status
                or self._runtime_flags != state.runtime_flags
            ):
                self._state = replace(
                    state,
                    runtime_status=self._runtime_status,
                    runtime_flags=self._runtime_flags,
                )
            return CodexObservationBatch(
                endpoint_identity=token[0],
                connection_generation=token[1],
                thread_id=state.receipt.thread_id,
                after_live_watermark=after,
                live_watermark=self._live_watermark,
                records=records,
            )
