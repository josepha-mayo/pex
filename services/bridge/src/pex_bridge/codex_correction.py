"""Local correction provenance, never a vendor idempotency or dispatch grant."""

from __future__ import annotations

import hashlib
from typing import Any

from pex_protocol.actions import InterventionType
from pex_protocol.enums import HarnessType
from pex_protocol.session import HarnessSession

from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads
from pex_bridge.workspace_binding import WorkspaceBinding

CORRECTION_SCHEMA = "pex.codex-correction.v1"
MAX_CORRECTION_TEXT_BYTES = 65_536
MAX_ATTRIBUTION_RECORDS = 4096
MAX_ATTRIBUTION_BYTES = 8 * 1024 * 1024
TEXT_ACTIONS = frozenset({
    InterventionType.SEND_NUDGE.value, InterventionType.INJECT_CONTEXT.value,
    InterventionType.REQUEST_VERIFICATION.value,
    InterventionType.CONTINUE_SESSION.value,
})


class CodexCorrectionMultiplicityError(ValueError):
    """A correction ID cannot establish ownership of a second vendor input."""


def canonical(value: Any) -> str:
    return strict_json_dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def requires_correction(session: HarnessSession, action: dict[str, Any]) -> bool:
    return (
        session.harness_type == HarnessType.CODEX
        and session.metadata.get("connection_kind") == "codex_shared"
        and isinstance(action, dict) and isinstance(action.get("type"), str)
        and action.get("type") in TEXT_ACTIONS
    )


def _identifier(value: Any) -> str:
    if (
        not isinstance(value, str) or not value or value != value.strip()
        or len(value) > 512 or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("Codex correction identity is invalid")
    return value


def correction_scope(session: HarnessSession, workspace: WorkspaceBinding) -> dict[str, Any]:
    """Stable historical attribution scope; excludes mutable goal/epoch/choice revision."""
    receipt = session.metadata.get("subscription_receipt")
    if not isinstance(receipt, dict):
        raise ValueError("Codex correction requires a subscription receipt")
    for name in ("authorization_id", "endpoint_identity", "thread_id", "root_session_id"):
        _identifier(receipt.get(name))
    if (
        receipt.get("schema") != "pex.codex-existing-thread-subscription.v1"
        or type(receipt.get("connection_generation")) is not int
        or receipt["connection_generation"] < 1
        or receipt.get("pex_session_id") != session.id
        or receipt.get("thread_id") != session.vendor_session_id
        or receipt.get("project_id") != session.project_id
        or receipt.get("cwd") != session.cwd
        or "vendor_project_id" not in receipt
        or session.project_id != workspace.project_id
    ):
        raise ValueError("Codex correction subscription binding is invalid")
    vendor_project = receipt["vendor_project_id"]
    if vendor_project is not None:
        _identifier(vendor_project)
    return {
        "session_id": session.id,
        "thread_id": receipt["thread_id"],
        "root_session_id": receipt["root_session_id"],
        "vendor_project_id": vendor_project,
        "endpoint_identity": receipt["endpoint_identity"],
        "project_binding": workspace.project_binding,
        "directory": workspace.model_dump(mode="json")["directory"],
        "origin": workspace.origin_choice.origin.model_dump(mode="json"),
        "origin_storage_physical": workspace.origin_choice.storage_physical.model_dump(mode="json"),
    }


def build_correction(
    *, event_id: str, effect_id: str, intervention_id: str,
    action: dict[str, Any], required_capability: Any,
    session: HarnessSession, workspace: WorkspaceBinding,
) -> dict[str, Any]:
    if not isinstance(action, dict):
        raise ValueError("Codex correction action binding is invalid")
    scope = correction_scope(session, workspace)
    payload = action.get("payload")
    capability = (
        "resume"
        if action.get("type") == InterventionType.CONTINUE_SESSION.value else "send_message"
    )
    if (
        not requires_correction(session, action) or required_capability != capability
        or action.get("session_id") != session.id
        or not session.goal_id or action.get("goal_id") != session.goal_id
        or not isinstance(payload, dict)
        or {"codex_correction", "client_message_id", "clientUserMessageId"}.intersection(action)
        or {"codex_correction", "client_message_id", "clientUserMessageId"}.intersection(payload)
    ):
        raise ValueError("Codex correction action binding is invalid")
    text = payload.get("text")
    if (
        not isinstance(text, str) or not text.strip() or "\x00" in text
        or len(text.encode("utf-8")) > MAX_CORRECTION_TEXT_BYTES
    ):
        raise ValueError("Codex correction requires bounded exact text")
    correlation = "pex-correction-" + hashlib.sha256(
        canonical([CORRECTION_SCHEMA, _identifier(effect_id)]).encode("utf-8")
    ).hexdigest()
    return strict_json_loads(canonical({
        "schema": CORRECTION_SCHEMA,
        "event_id": _identifier(event_id),
        "effect_id": effect_id,
        "intervention_id": _identifier(intervention_id),
        "client_message_id": correlation,
        "content": [{"type": "text", "text": text, "text_elements": []}],
        **{key: scope[key] for key in (
            "session_id", "thread_id", "root_session_id", "vendor_project_id", "project_binding",
        )},
        "workspace_binding": workspace.model_dump(mode="json"),
        "subscription_receipt": session.metadata["subscription_receipt"],
    }))
