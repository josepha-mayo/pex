from __future__ import annotations

import math
import ntpath
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

from pex_protocol.actions import InterventionType
from pex_protocol.capabilities import AdapterCapabilities, AdapterSupportLabel
from pex_protocol.context import ContextBundle
from pex_protocol.enums import EventType, HarnessType, PolicyVerdict
from pex_protocol.intervention import Intervention
from pex_protocol.redaction import redact_mapping, redact_text
from pex_protocol.session import HarnessEvent, HarnessSession

MAX_ADAPTER_MESSAGE_CHARS = 262_144
MAX_ADAPTER_ID_CHARS = 512
MAX_ADAPTER_BINDING_CHARS = 4_096
MAX_OBSERVED_MAPPING_ITEMS = 128
MAX_OBSERVED_MAPPING_NODES = 4_096
MAX_OBSERVED_MAPPING_DEPTH = 8
MAX_OBSERVED_VALUE_CHARS = 32_768
MAX_OBSERVED_MAPPING_TEXT_CHARS = 65_536


class DeliveryUncertainError(RuntimeError):
    """A mutating request may have reached the harness, but no receipt was verified."""


@dataclass(frozen=True)
class AdapterMessageResult:
    """A verified adapter acceptance plus its bounded vendor continuation identity."""

    accepted: bool
    vendor_session_id: str | None = None
    vendor_turn_id: str | None = None

    def __bool__(self) -> bool:
        return self.accepted is True


@dataclass(frozen=True)
class CursorHookPreparation:
    """A Cursor stop-hook follow-up prepared locally, not vendor-accepted."""

    preparation_id: str
    trigger_event_id: str
    vendor_session_id: str
    message_sha256: str


@dataclass(frozen=True)
class AdapterMessageResolution:
    """Fail-closed interpretation of one adapter mutation result."""

    status: Literal["delivered", "rejected", "delivery_uncertain", "hook_prepared"]
    worker_delivery_receipt: dict[str, str] | None = None
    hook_preparation_receipt: dict[str, str] | None = None


def bounded_adapter_text(
    value: object,
    *,
    field: str = "message",
    max_chars: int = MAX_ADAPTER_MESSAGE_CHARS,
) -> str:
    """Validate one adapter-bound string before it reaches a harness.

    Adapter methods are public Python boundaries as well as HTTP consumers, so
    they cannot rely only on the API model limits.  Preserve whitespace in the
    delivered value, but reject empty, NUL-bearing, or oversized text.
    """

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    if "\x00" in value:
        raise ValueError(f"{field} contains a NUL byte")
    if len(value) > max_chars:
        raise ValueError(f"{field} exceeds the adapter safety bound")
    return value


def bounded_adapter_id(value: object, *, field: str = "identifier") -> str:
    text = bounded_adapter_text(value, field=field, max_chars=MAX_ADAPTER_ID_CHARS).strip()
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in text):
        raise ValueError(f"{field} contains control characters")
    return text


def bounded_adapter_binding(value: object, *, field: str = "binding") -> str:
    """Validate an exact project or workspace binding without trimming it."""

    text = bounded_adapter_text(value, field=field, max_chars=MAX_ADAPTER_BINDING_CHARS)
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in text):
        raise ValueError(f"{field} contains control characters")
    return text


WORKER_DELIVERY_SCHEMA_GENERIC = "pex.worker-delivery.v1"
WORKER_DELIVERY_SCHEMA_CODEX = "pex.worker-delivery.codex-turn.v1"
CURSOR_HOOK_PREPARATION_SCHEMA = "pex.cursor-hook-preparation.v1"
WORKER_DELIVERY_RECEIPT_KEYS = frozenset(
    {
        "schema",
        "target_session_id",
        "vendor_session_id",
        "vendor_turn_id",
    }
)
CURSOR_HOOK_PREPARATION_RECEIPT_KEYS = frozenset(
    {
        "schema",
        "preparation_id",
        "trigger_event_id",
        "target_session_id",
        "vendor_session_id",
        "message_sha256",
    }
)


def _bounded_sha256(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def worker_delivery_schema_for(harness_type: object) -> str:
    if harness_type in {HarnessType.CODEX, HarnessType.CODEX.value}:
        return WORKER_DELIVERY_SCHEMA_CODEX
    return WORKER_DELIVERY_SCHEMA_GENERIC


def validate_worker_delivery_receipt(
    receipt: object,
    *,
    session: HarnessSession,
) -> dict[str, str]:
    """Validate one exact, content-free worker-delivery receipt."""

    return validate_worker_delivery_receipt_binding(
        receipt,
        target_session_id=session.id,
        vendor_session_id=session.vendor_session_id,
        harness_type=session.harness_type,
    )


def validate_worker_delivery_receipt_binding(
    receipt: object,
    *,
    target_session_id: object,
    vendor_session_id: object,
    harness_type: object,
) -> dict[str, str]:
    """Validate a turn receipt against one immutable session binding."""

    if not isinstance(receipt, dict):
        raise ValueError("worker delivery receipt has the wrong shape")
    target_id = bounded_adapter_id(
        target_session_id,
        field="worker delivery target session id",
    )
    bound_vendor_session_id = bounded_adapter_id(
        vendor_session_id,
        field="worker delivery bound vendor session id",
    )
    if set(receipt) != WORKER_DELIVERY_RECEIPT_KEYS:
        raise ValueError("worker delivery receipt has invalid keys")
    receipt_vendor_session_id = bounded_adapter_id(
        receipt.get("vendor_session_id"),
        field="worker delivery vendor session id",
    )
    receipt_vendor_turn_id = bounded_adapter_id(
        receipt.get("vendor_turn_id"),
        field="worker delivery vendor turn id",
    )
    expected = {
        "schema": worker_delivery_schema_for(harness_type),
        "target_session_id": target_id,
        "vendor_session_id": bound_vendor_session_id,
        "vendor_turn_id": receipt_vendor_turn_id,
    }
    if (
        receipt != expected
        or receipt_vendor_session_id != receipt.get("vendor_session_id")
        or receipt_vendor_turn_id != receipt.get("vendor_turn_id")
    ):
        raise ValueError("worker delivery receipt does not match the target session")
    return expected


def validate_codex_worker_delivery_receipt(
    receipt: object,
    *,
    session: HarnessSession,
) -> dict[str, str]:
    """Validate the exact content-free receipt for one accepted Codex turn."""

    return validate_codex_worker_delivery_receipt_binding(
        receipt,
        target_session_id=session.id,
        vendor_session_id=session.vendor_session_id,
        harness_type=session.harness_type,
    )


def validate_codex_worker_delivery_receipt_binding(
    receipt: object,
    *,
    target_session_id: object,
    vendor_session_id: object,
    harness_type: object,
) -> dict[str, str]:
    """Validate a Codex turn receipt against one immutable session binding."""

    if harness_type not in {HarnessType.CODEX, HarnessType.CODEX.value}:
        raise ValueError("Codex worker delivery receipt has the wrong target harness")
    expected = validate_worker_delivery_receipt_binding(
        receipt,
        target_session_id=target_session_id,
        vendor_session_id=vendor_session_id,
        harness_type=harness_type,
    )
    if expected["schema"] != WORKER_DELIVERY_SCHEMA_CODEX:
        raise ValueError("Codex worker delivery receipt has the wrong schema")
    return expected


def validate_cursor_hook_preparation_receipt(
    receipt: object,
    *,
    session: HarnessSession,
    trigger_event_id: object | None = None,
    preparation_id: object | None = None,
    message_sha256: object | None = None,
) -> dict[str, str]:
    """Validate an exact content-free Cursor hook-preparation binding."""

    if session.harness_type != HarnessType.CURSOR:
        raise ValueError("Cursor hook preparation has the wrong target harness")
    if not isinstance(receipt, dict) or set(receipt) != CURSOR_HOOK_PREPARATION_RECEIPT_KEYS:
        raise ValueError("Cursor hook preparation receipt has invalid keys")
    target_session_id = bounded_adapter_id(
        session.id,
        field="Cursor hook preparation target session id",
    )
    bound_vendor_session_id = bounded_adapter_id(
        session.vendor_session_id,
        field="Cursor hook preparation bound vendor session id",
    )
    receipt_preparation_id = bounded_adapter_id(
        receipt.get("preparation_id"),
        field="Cursor hook preparation id",
    )
    receipt_trigger_event_id = bounded_adapter_id(
        receipt.get("trigger_event_id"),
        field="Cursor hook preparation trigger event id",
    )
    receipt_vendor_session_id = bounded_adapter_id(
        receipt.get("vendor_session_id"),
        field="Cursor hook preparation vendor session id",
    )
    receipt_message_sha256 = _bounded_sha256(
        receipt.get("message_sha256"),
        field="Cursor hook preparation message hash",
    )
    expected = {
        "schema": CURSOR_HOOK_PREPARATION_SCHEMA,
        "preparation_id": receipt_preparation_id,
        "trigger_event_id": receipt_trigger_event_id,
        "target_session_id": target_session_id,
        "vendor_session_id": bound_vendor_session_id,
        "message_sha256": receipt_message_sha256,
    }
    exact_bindings = (
        (preparation_id, receipt_preparation_id, "preparation id"),
        (trigger_event_id, receipt_trigger_event_id, "trigger event id"),
        (message_sha256, receipt_message_sha256, "message hash"),
    )
    if (
        receipt != expected
        or target_session_id != f"cursor:{bound_vendor_session_id}"
        or receipt_vendor_session_id != bound_vendor_session_id
        or any(
            supplied is not None and supplied != observed
            for supplied, observed, _field in exact_bindings
        )
    ):
        raise ValueError("Cursor hook preparation receipt does not match its binding")
    return expected


def resolve_adapter_message_result(
    result: object,
    *,
    session: HarnessSession,
) -> AdapterMessageResolution:
    """Resolve Boolean adapters and exact turn receipts without truthiness."""

    if isinstance(result, CursorHookPreparation):
        candidate = {
            "schema": CURSOR_HOOK_PREPARATION_SCHEMA,
            "preparation_id": result.preparation_id,
            "trigger_event_id": result.trigger_event_id,
            "target_session_id": session.id,
            "vendor_session_id": result.vendor_session_id,
            "message_sha256": result.message_sha256,
        }
        try:
            receipt = validate_cursor_hook_preparation_receipt(candidate, session=session)
        except (TypeError, ValueError):
            return AdapterMessageResolution(status="delivery_uncertain")
        return AdapterMessageResolution(
            status="hook_prepared",
            hook_preparation_receipt=receipt,
        )
    if result is False:
        return AdapterMessageResolution(status="rejected")
    if result is True:
        return AdapterMessageResolution(status="delivery_uncertain")
    if not isinstance(result, AdapterMessageResult):
        return AdapterMessageResolution(status="delivery_uncertain")
    if result.accepted is False:
        return AdapterMessageResolution(status="rejected")
    if result.accepted is not True:
        return AdapterMessageResolution(status="delivery_uncertain")
    candidate = {
        "schema": worker_delivery_schema_for(session.harness_type),
        "target_session_id": session.id,
        "vendor_session_id": result.vendor_session_id,
        "vendor_turn_id": result.vendor_turn_id,
    }
    try:
        receipt = validate_worker_delivery_receipt(candidate, session=session)
    except (TypeError, ValueError):
        return AdapterMessageResolution(status="delivery_uncertain")
    return AdapterMessageResolution(
        status="delivered",
        worker_delivery_receipt=receipt,
    )


def bounded_observed_text(
    value: object,
    *,
    field: str = "observed text",
    max_chars: int = 4_096,
) -> str | None:
    """Bound and redact untrusted display metadata before session persistence."""

    if value in (None, "") or not isinstance(value, str):
        return None
    try:
        text = bounded_adapter_text(value, field=field, max_chars=max_chars)
    except ValueError:
        return None
    cleaned, _ = redact_text(text)
    return cleaned


def bounded_observed_mapping(value: object) -> dict | None:
    """Copy a JSON-like observation into a small, redacted in-memory shape."""

    if not isinstance(value, dict):
        return None
    budget = [MAX_OBSERVED_MAPPING_NODES]
    text_budget = [MAX_OBSERVED_MAPPING_TEXT_CHARS]

    def clean(node: object, depth: int) -> object:
        budget[0] -= 1
        if budget[0] < 0 or depth > MAX_OBSERVED_MAPPING_DEPTH:
            raise ValueError("observed mapping exceeded the structural safety bound")
        if node is None or isinstance(node, bool):
            return node
        if isinstance(node, int) and not isinstance(node, bool):
            if node.bit_length() > 4_096:
                raise ValueError("observed integer exceeded the safety bound")
            return node
        if isinstance(node, float):
            if not math.isfinite(node):
                raise ValueError("observed number is non-finite")
            return node
        if isinstance(node, str):
            if len(node) > MAX_OBSERVED_VALUE_CHARS or "\x00" in node:
                raise ValueError("observed string exceeded the safety bound")
            text_budget[0] -= len(node)
            if text_budget[0] < 0:
                raise ValueError("observed mapping exceeded the text safety bound")
            return node
        if isinstance(node, dict):
            if len(node) > MAX_OBSERVED_MAPPING_ITEMS:
                raise ValueError("observed object exceeded the item safety bound")
            copied: dict[str, object] = {}
            for key, item in node.items():
                if (
                    not isinstance(key, str)
                    or not key
                    or len(key) > 128
                    or any(ord(char) < 0x20 or ord(char) == 0x7F for char in key)
                ):
                    raise ValueError("observed object contains an unsafe key")
                text_budget[0] -= len(key)
                if text_budget[0] < 0:
                    raise ValueError("observed mapping exceeded the text safety bound")
                copied[key] = clean(item, depth + 1)
            return copied
        if isinstance(node, (list, tuple)):
            if len(node) > MAX_OBSERVED_MAPPING_ITEMS:
                raise ValueError("observed list exceeded the item safety bound")
            return [clean(item, depth + 1) for item in node]
        raise ValueError("observed mapping contains a non-JSON value")

    try:
        copied = clean(value, 0)
    except ValueError:
        return None
    cleaned, _ = redact_mapping(copied)
    return cleaned if isinstance(cleaned, dict) else None


def session_binding_matches(
    bound: HarnessSession | None,
    supplied: HarnessSession,
    *,
    harness_type,
) -> bool:
    """Return whether caller state can address one already-bound vendor session.

    The bridge may attach a goal after discovery, so a missing goal on either
    snapshot is tolerated.  Conflicting non-empty goal/project/cwd values are
    never tolerated, and adapter I/O should still use the canonical ``bound``
    object after this check.
    """

    if (
        bound is None
        or supplied.id != bound.id
        or supplied.vendor_session_id != bound.vendor_session_id
        or supplied.harness_type != harness_type
        or bound.harness_type != harness_type
    ):
        return False
    if not _compatible_binding(bound.goal_id, supplied.goal_id, path_like=False):
        return False
    if not _same_present_binding(bound.project_id, supplied.project_id, path_like=True):
        return False
    return _same_present_binding(bound.cwd, supplied.cwd, path_like=True)


def preserve_bridge_state(
    existing: HarnessSession | None,
    *,
    cwd: str | None,
    project_id: str | None,
) -> tuple[str | None, bool]:
    """Preserve goal/pause state only while the discovered project is stable."""

    if existing is None:
        return None, False
    if not _same_present_binding(existing.cwd, cwd, path_like=True):
        return None, False
    if not _same_present_binding(existing.project_id, project_id, path_like=True):
        return None, False
    return existing.goal_id, existing.supervision_paused


def _compatible_binding(left: str | None, right: str | None, *, path_like: bool) -> bool:
    if not left or not right:
        return True
    if not path_like:
        return left == right
    return ntpath.normcase(ntpath.normpath(left)) == ntpath.normcase(ntpath.normpath(right))


def _same_present_binding(left: str | None, right: str | None, *, path_like: bool) -> bool:
    if bool(left) != bool(right):
        return False
    return _compatible_binding(left, right, path_like=path_like)


class HarnessAdapter(ABC):
    name: str

    @abstractmethod
    async def probe(self) -> AdapterCapabilities: ...

    @abstractmethod
    async def discover_sessions(self) -> list[HarnessSession]: ...

    async def attach(self, session_ref: str) -> HarnessSession | None:
        sessions = await self.discover_sessions()
        for session in sessions:
            if session.id == session_ref or session.vendor_session_id == session_ref:
                return session
        return None

    async def stream_events(self, session: HarnessSession) -> AsyncIterator[HarnessEvent]:
        if False:
            yield  # pragma: no cover
        return

    async def read_state(self, session: HarnessSession) -> dict:
        return {"session_id": session.id, "status": session.status}

    async def send_message(
        self, session: HarnessSession, text: str, attachments=None
    ) -> bool | AdapterMessageResult | CursorHookPreparation:
        return False

    async def inject_context(
        self, session: HarnessSession, bundle: ContextBundle
    ) -> bool | AdapterMessageResult | CursorHookPreparation:
        return await self.send_message(session, _bundle_as_prompt(bundle))

    async def respond_permission(
        self, session: HarnessSession, request_id: str, decision: str
    ) -> bool:
        return False

    async def stop(self, session: HarnessSession) -> bool:
        return False

    async def start_session(
        self,
        project: str,
        prompt: str,
        config: dict | None = None,
    ) -> HarnessSession | None:
        """Start one new worker session when ``probe().start`` is true.

        Returning ``None`` means no session was started. Implementations must
        return the exact vendor-backed session they created; the executor will
        persist it only after capability negotiation and collision checks.
        """
        return None

    async def fork_or_fresh_handoff(
        self,
        session: HarnessSession,
        context_bundle: ContextBundle,
    ) -> HarnessSession | None:
        """Create an isolated probe/fork when ``probe().fork`` is true."""
        return None

    async def continue_or_resume(
        self, session: HarnessSession, message: str | None = None
    ) -> bool | AdapterMessageResult | CursorHookPreparation:
        if message:
            return await self.send_message(session, message)
        return False

    async def apply_overlay(self, session: HarnessSession, overlay) -> bool:
        return False

    async def revert_overlay(self, overlay_id: str, rollback: dict | None = None) -> bool:
        return False

    async def focus_ui(self, session: HarnessSession) -> bool:
        return False

    async def health(self) -> dict:
        caps = await self.probe()
        return {
            "name": self.name,
            "ok": caps.support_label != AdapterSupportLabel.UNAVAILABLE,
            "support": caps.support_label,
        }


def verified_inline_permission_outcome(
    session: HarnessSession,
    intervention: Intervention | None,
    *,
    expected_trigger: EventType,
    expected_request_id: str | None = None,
) -> str | None:
    """Return only a completed permission outcome for this exact hook.

    ``PolicyVerdict.DENY`` means PEX was not authorized to execute the
    proposed action. It is not a permission denial for the worker. Likewise,
    cooldown/capability failures and passive autonomy modes must not be turned
    into harness control. The executor result is the delivery receipt for an
    inline hook response.
    """
    if intervention is None:
        return None
    action = getattr(intervention, "proposed_action", None)
    if action is None:
        return None
    if (
        getattr(intervention, "session_id", None) != session.id
        or getattr(intervention, "trigger", None) != expected_trigger.value
        or getattr(intervention, "action_taken", None)
        != InterventionType.RESPOND_PERMISSION.value
        or action.type != InterventionType.RESPOND_PERMISSION
        or action.session_id != session.id
        or not any(str(item).strip() for item in getattr(intervention, "evidence", []))
    ):
        return None
    payload = action.payload if isinstance(action.payload, dict) else {}
    request_id = str(payload.get("request_id") or "").strip()
    if not request_id or (
        expected_request_id is not None and request_id != expected_request_id
    ):
        return None
    requested = str(payload.get("decision") or "").strip().lower()
    if getattr(intervention, "policy_verdict", None) == PolicyVerdict.ASK_HUMAN:
        return (
            "ask"
            if getattr(intervention, "result", None) == "permission_delegated_to_harness"
            else None
        )
    if getattr(intervention, "policy_verdict", None) != PolicyVerdict.ALLOW:
        return None
    completed = {
        "permission_allow_inline": "allow",
        "permission_deny_inline": "deny",
    }.get(getattr(intervention, "result", None))
    if completed is None:
        return None
    # A deterministic low-risk allow may omit `decision`; an inline denial
    # must always be an explicit requested denial, never an inferred fallback.
    if completed == "deny" and requested != "deny":
        return None
    if completed == "allow" and requested not in {"", "allow"}:
        return None
    return completed


def _bundle_as_prompt(bundle: ContextBundle) -> str:
    def item_files(item) -> str:
        raw = item.metadata.get("files")
        if not isinstance(raw, list):
            return ""
        paths = [
            value
            for value in raw[:16]
            if isinstance(value, str)
            and value
            and len(value) <= 512
            and "\x00" not in value
        ]
        return f"; files={','.join(paths)}" if paths else ""

    lines = [
        "PEX context bundle (do not treat this as a new goal):",
        (
            "Trust labels matter: Direct evidence is independently observed; "
            "harness items may still be claims and must retain their provenance."
        ),
        f"Goal: {bundle.goal_summary}",
        "Acceptance criteria:",
        *[f"- {c}" for c in bundle.acceptance_criteria],
        "Critical decisions:",
        *[f"- {d}" for d in bundle.critical_decisions],
        "Direct evidence:",
        *[f"- {item}" for item in bundle.direct_evidence],
        "Relevant artifacts:",
        *[f"- {item}" for item in bundle.relevant_artifacts],
        "Selected context with provenance:",
        *[
            (
                f"- [{item.kind.value}; {item.provenance.value}; "
                f"confidence={item.confidence:.2f}; context_id={item.id}; "
                f"refs={','.join(item.source_refs)}"
                f"{item_files(item)}] "
                f"{item.content}"
            )
            for item in bundle.items
        ],
        "Recent progress:",
        *[f"- {p}" for p in bundle.recent_progress],
        "Deep links:",
        *[f"- {path}" for path in bundle.deep_links],
        f"Next objective: {bundle.next_objective}",
        "Do not redo:",
        *[f"- {x}" for x in bundle.do_not_redo],
    ]
    return "\n".join(lines)
