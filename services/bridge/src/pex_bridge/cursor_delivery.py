from __future__ import annotations

import hashlib
import re
from typing import Any

CURSOR_HOOK_DELIVERY_SCHEMA = "pex.cursor-hook-delivery.v1"
CURSOR_HOOK_FLUSH_SCHEMA = "pex.cursor-hook-flush.v1"
CURSOR_HOOK_CONTINUATION_SCHEMA = "pex.cursor-hook-continuation.v1"
CURSOR_HOOK_PREPARED_OUTCOME = "hook_followup_prepared_delivery_uncertain"

_HEX_64 = re.compile(r"[0-9a-f]{64}")
_PACKET_KEYS = frozenset(
    {
        "schema",
        "preparation_id",
        "intervention_id",
        "trigger_event_id",
        "target_session_id",
        "vendor_session_id",
        "goal_id",
        "message_sha256",
        "nonce",
    }
)
_AUTHORITY_KEYS = frozenset(
    {
        "control_revision",
        "project_binding",
        "discovery_generation",
        "goal_id",
        "intent_revision",
        "intent_hash",
    }
)


def _bounded_id(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > 512
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")
    return value


def validate_cursor_hook_authority(value: object) -> dict[str, Any]:
    """Validate the caller's last-read Store authority fence."""

    if not isinstance(value, dict) or set(value) != _AUTHORITY_KEYS:
        raise ValueError("Cursor hook expected authority has invalid keys")
    control_revision = value.get("control_revision")
    intent_revision = value.get("intent_revision")
    if (
        not isinstance(control_revision, int)
        or isinstance(control_revision, bool)
        or control_revision < 0
        or not isinstance(intent_revision, int)
        or isinstance(intent_revision, bool)
        or intent_revision < 0
    ):
        raise ValueError("Cursor hook expected authority revision is invalid")
    discovery_generation = value.get("discovery_generation")
    if discovery_generation is not None:
        discovery_generation = _bounded_id(
            discovery_generation,
            label="Cursor hook discovery generation",
        )
    return {
        "control_revision": control_revision,
        "project_binding": _bounded_id(
            value.get("project_binding"), label="Cursor hook project binding"
        ),
        "discovery_generation": discovery_generation,
        "goal_id": _bounded_id(value.get("goal_id"), label="Cursor hook goal id"),
        "intent_revision": intent_revision,
        "intent_hash": _sha256(
            value.get("intent_hash"), label="Cursor hook goal intent hash"
        ),
    }


def validate_cursor_hook_delivery_packet(value: object) -> dict[str, str]:
    """Validate the one-time packet returned privately to the hook helper."""

    if not isinstance(value, dict) or set(value) != _PACKET_KEYS:
        raise ValueError("Cursor hook delivery packet has invalid keys")
    expected = {
        "schema": CURSOR_HOOK_DELIVERY_SCHEMA,
        "preparation_id": _bounded_id(
            value.get("preparation_id"), label="Cursor hook preparation id"
        ),
        "intervention_id": _bounded_id(
            value.get("intervention_id"), label="Cursor hook intervention id"
        ),
        "trigger_event_id": _bounded_id(
            value.get("trigger_event_id"), label="Cursor hook trigger event id"
        ),
        "target_session_id": _bounded_id(
            value.get("target_session_id"), label="Cursor hook target session id"
        ),
        "vendor_session_id": _bounded_id(
            value.get("vendor_session_id"), label="Cursor hook vendor session id"
        ),
        "goal_id": _bounded_id(value.get("goal_id"), label="Cursor hook goal id"),
        "message_sha256": _sha256(
            value.get("message_sha256"), label="Cursor hook message hash"
        ),
        "nonce": _sha256(value.get("nonce"), label="Cursor hook delivery nonce"),
    }
    if value != expected:
        raise ValueError("Cursor hook delivery packet is not canonical")
    return expected


def cursor_message_sha256(text: str) -> str:
    if not isinstance(text, str) or not text.strip() or "\x00" in text:
        raise ValueError("Cursor hook follow-up text is invalid")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cursor_nonce_sha256(nonce: str) -> str:
    canonical = _sha256(nonce, label="Cursor hook delivery nonce")
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()
