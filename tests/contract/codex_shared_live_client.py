"""Strict HTTP helpers for an operator-owned existing Codex worker proof.

This module does not discover, launch, prompt, or stop a worker.  Callers supply
the exact existing endpoint/thread/workspace and retain responsibility for the
operator confirmation and the live evidence oracle.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from httpx import AsyncClient, Response

_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}\Z")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_CORRECTION_ACTIONS = [
    "CONTINUE_SESSION",
    "INJECT_CONTEXT",
    "REQUEST_VERIFICATION",
    "SEND_NUDGE",
]


class LiveContractError(RuntimeError):
    """The bridge rejected the operation or returned an unsafe/stale receipt."""


@dataclass(frozen=True)
class ExistingCodexTarget:
    socket_path: str
    thread_id: str
    project_id: str
    cwd: str

    @property
    def session_id(self) -> str:
        return f"codex:{self.thread_id}"

    def inspect_body(self) -> dict[str, str]:
        return {
            "socket_path": self.socket_path,
            "thread_id": self.thread_id,
            "project_id": self.project_id,
            "cwd": self.cwd,
        }


def _record(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LiveContractError(f"{label} is not an object")
    return value


def _require_idempotency_key(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDEMPOTENCY_KEY.fullmatch(value) is None:
        raise LiveContractError(f"{label} must be an 8-128 character idempotency key")
    return value


def _same_cwd(left: object, right: object) -> bool:
    """Compare path spelling with only the host platform's lexical rules.

    This intentionally does not resolve paths, follow links, or relax the
    comparison for project or thread identifiers.
    """
    return (
        isinstance(left, str)
        and isinstance(right, str)
        and os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right))
    )


async def _json(response: Response, label: str) -> dict[str, Any]:
    if not response.is_success:
        raise LiveContractError(f"{label} failed with HTTP {response.status_code}")
    try:
        return _record(response.json(), label)
    except ValueError as exc:
        raise LiveContractError(f"{label} did not return JSON") from exc


def require_connection_available(status: Mapping[str, Any], target: ExistingCodexTarget) -> None:
    """Refuse to replace either a conflicting or an already-active observer."""
    connection = status.get("connection")
    if connection is None:
        return
    current = _record(connection, "shared connection")
    exact = (
        current.get("session_id") == target.session_id
        and current.get("thread_id") == target.thread_id
        and current.get("project_id") == target.project_id
        and _same_cwd(current.get("cwd"), target.cwd)
    )
    if exact:
        raise LiveContractError(
            "the exact target is already attached; reuse it explicitly rather than re-inspect"
        )
    raise LiveContractError("a different shared Codex connection is active; leave it untouched")


async def inspect_and_confirm(
    client: AsyncClient,
    target: ExistingCodexTarget,
    *,
    operator_confirmed_exact_target: bool,
) -> dict[str, Any]:
    """Inspect then subscribe to one exact existing thread without starting a turn."""
    status = await _json(await client.get("/v1/adapters/codex/shared/status"), "shared status")
    require_connection_available(status, target)
    inspected = await _json(
        await client.post("/v1/adapters/codex/shared/inspect", json=target.inspect_body()),
        "shared inspection",
    )
    expected = {
        "session_id": target.session_id,
        "thread_id": target.thread_id,
        "project_id": target.project_id,
        "subscribed": False,
    }
    if any(inspected.get(key) != value for key, value in expected.items()) or not _same_cwd(
        inspected.get("cwd"), target.cwd
    ):
        raise LiveContractError("inspection does not match the operator-supplied target")
    inspection_id = inspected.get("inspection_id")
    selection_id = inspected.get("selection_id")
    if not isinstance(inspection_id, str) or not isinstance(selection_id, str):
        raise LiveContractError("inspection receipt lacks selection identifiers")
    if operator_confirmed_exact_target is not True:
        raise LiveContractError("explicit exact-target confirmation is required")
    confirmed = await _json(
        await client.post(
            "/v1/adapters/codex/shared/confirm",
            json={
                "inspection_id": inspection_id,
                "selection_id": selection_id,
                "allow_resume": True,
            },
        ),
        "shared confirmation",
    )
    if (
        confirmed.get("ok") is not True
        or confirmed.get("kind") != "shared"
        or confirmed.get("support") != "observe_only"
        or confirmed.get("session_id") != target.session_id
        or confirmed.get("worker_delivery_enabled") is not False
    ):
        raise LiveContractError("confirmation receipt does not preserve observe-only binding")
    subscription = _record(confirmed.get("subscription"), "confirmation subscription")
    for key, expected_value in {
        "pex_session_id": target.session_id,
        "thread_id": target.thread_id,
        "project_id": target.project_id,
    }.items():
        if subscription.get(key) != expected_value:
            raise LiveContractError("confirmation subscription changed the inspected target")
    if not _same_cwd(subscription.get("cwd"), target.cwd):
        raise LiveContractError("confirmation subscription changed the inspected target")
    if confirmed.get("workspace_binding") != inspected.get("workspace_binding"):
        raise LiveContractError("confirmation workspace binding changed after inspection")
    return {"inspection": inspected, "confirmation": confirmed}


async def confirm_local_origin(
    client: AsyncClient, *, origin_body: Mapping[str, Any]
) -> dict[str, Any]:
    """Persist only the caller's explicit, fully formed local-origin CAS request."""
    body = dict(origin_body)
    if body.get("confirm_local_origin") is not True:
        raise LiveContractError("explicit local-origin confirmation is required")
    if body.get("allow_storage_rebind") is not False:
        raise LiveContractError("live proof must not rebind existing origin storage")
    return await _json(
        await client.patch("/v1/local-workspace-origin", json=body),
        "local-origin confirmation",
    )


async def create_goal_and_attach(
    client: AsyncClient,
    target: ExistingCodexTarget,
    *,
    goal_body: Mapping[str, Any],
) -> dict[str, Any]:
    """Create the supplied persistent goal and CAS-attach it to an unbound session."""
    body = dict(goal_body)
    attach_key = body.pop("attach_idempotency_key", None)
    if body.get("project_id") != target.project_id:
        raise LiveContractError("goal project_id does not match the inspected target")
    _require_idempotency_key(body.get("idempotency_key"), "goal creation")
    _require_idempotency_key(attach_key, "goal attachment")
    session_path = f"/v1/sessions/{quote(target.session_id, safe='')}"
    # The public single-session resource is a HarnessSession and intentionally
    # does not expose Store control CAS. The canonical pet snapshot decorates
    # each session with its current revision/control_revision for UI mutations.
    snapshot = await _json(await client.get("/v1/pet"), "canonical session snapshot")
    sessions = snapshot.get("sessions")
    if not isinstance(sessions, list):
        raise LiveContractError("canonical session snapshot lacks sessions")
    matches = [
        item
        for item in sessions
        if isinstance(item, dict) and item.get("id") == target.session_id
    ]
    if len(matches) != 1:
        raise LiveContractError("canonical session snapshot does not identify exactly one worker")
    session = matches[0]
    if session.get("goal_id") is not None:
        raise LiveContractError("session already has a goal; do not replace it in live proof")
    control_revision = session.get("control_revision")
    if type(control_revision) is not int or control_revision < 0:
        raise LiveContractError("session lacks a canonical control revision")
    goal = await _json(await client.post("/v1/goals", json=body), "goal creation")
    goal_id, intent_revision = goal.get("id"), goal.get("intent_revision")
    if (
        not isinstance(goal_id, str)
        or not goal_id
        or type(intent_revision) is not int
        or intent_revision < 0
        or not isinstance(goal.get("intent_hash"), str)
        or _SHA256.fullmatch(goal["intent_hash"]) is None
    ):
        raise LiveContractError("goal receipt lacks canonical identity or intent revision")
    attached = await _json(
        await client.post(
            f"{session_path}/attach",
            json={
                "idempotency_key": attach_key,
                "goal_id": goal_id,
                "replace_existing": False,
                "expected_goal_id": None,
                "expected_control_revision": control_revision,
                "expected_goal_intent_revision": intent_revision,
            },
        ),
        "goal attachment",
    )
    receipt = _record(attached.get("session_goal_attachment_receipt"), "attachment receipt")
    if (
        receipt.get("schema") != "pex.session-goal-attachment-receipt.v1"
        or receipt.get("goal_id") != goal_id
        or receipt.get("after_goal_id") != goal_id
    ):
        raise LiveContractError("goal attachment receipt is not bound to the created goal")
    return {"goal": goal, "session_before": session, "attachment": attached}


def correction_update_body(
    status: Mapping[str, Any], *, enabled: bool, idempotency_key: str
) -> dict[str, Any]:
    scope = _record(status.get("scope"), "correction scope")
    if scope.get("schema") != "pex.autonomous-correction-grant.v1":
        raise LiveContractError("correction scope schema is unavailable")
    fields = {
        "expected_control_revision": "control_revision",
        "expected_goal_id": "goal_id",
        "expected_goal_intent_revision": "goal_intent_revision",
        "expected_goal_intent_hash": "goal_intent_hash",
        "expected_project_binding": "project_binding",
        "expected_workspace_sha256": "workspace_sha256",
        "expected_subscription_authorization_id": "subscription_authorization_id",
        "expected_connection_generation": "connection_generation",
    }
    if any(scope.get(source) is None for source in fields.values()):
        raise LiveContractError("correction scope is incomplete")
    return {
        "enabled": enabled,
        "idempotency_key": idempotency_key,
        **{destination: scope[source] for destination, source in fields.items()},
    }


def _validate_correction_status(
    status: Mapping[str, Any], target: ExistingCodexTarget, *, require_disabled: bool
) -> dict[str, Any]:
    """Apply the public correction-status contract before a grant mutation."""
    for name in ("enabled", "effective_enabled", "connected"):
        if type(status.get(name)) is not bool:
            raise LiveContractError("correction status has invalid authority flags")
    if (
        not isinstance(status.get("reason"), str)
        or len(status["reason"]) > 160
        or status.get("delivery_proven") is not False
        or status["effective_enabled"] is not (status["enabled"] and status["connected"])
    ):
        raise LiveContractError("correction status is not a fresh public authority receipt")
    if status["connected"] is not True:
        raise LiveContractError("the exact shared worker is not connected")
    if require_disabled and (
        status["enabled"] is not False or status["effective_enabled"] is not False
    ):
        raise LiveContractError("correction authority is already enabled; do not reuse it")
    scope = _record(status.get("scope"), "correction scope")
    if scope.get("schema") != "pex.autonomous-correction-grant.v1":
        raise LiveContractError("correction scope schema is unavailable")
    if (
        scope.get("session_id") != target.session_id
        or scope.get("thread_id") != target.thread_id
        or scope.get("project_id") != target.project_id
    ):
        raise LiveContractError("correction scope does not bind the inspected worker")
    string_fields = (
        "session_id",
        "thread_id",
        "root_session_id",
        "goal_id",
        "project_id",
        "project_binding",
        "subscription_authorization_id",
        "subscription_selection_id",
        "endpoint_identity",
    )
    if any(
        not isinstance(scope.get(name), str)
        or not scope[name]
        or len(scope[name]) > 512
        or any(ord(char) < 32 or ord(char) == 127 for char in scope[name])
        for name in string_fields
    ):
        raise LiveContractError("correction scope has invalid identity fields")
    for name, minimum in (
        ("control_revision", 0),
        ("goal_intent_revision", 0),
        ("connection_generation", 1),
    ):
        if type(scope.get(name)) is not int or scope[name] < minimum:
            raise LiveContractError("correction scope has invalid revisions")
    for name in ("goal_intent_hash", "workspace_sha256"):
        if not isinstance(scope.get(name), str) or _SHA256.fullmatch(scope[name]) is None:
            raise LiveContractError("correction scope has invalid canonical hashes")
    if sorted(scope.get("allowed_intervention_types", [])) != _CORRECTION_ACTIONS:
        raise LiveContractError("correction scope has unsupported intervention authority")
    return scope


async def set_correction_grant(
    client: AsyncClient,
    target: ExistingCodexTarget,
    *,
    enabled: bool,
    idempotency_key: str,
) -> dict[str, Any]:
    _require_idempotency_key(idempotency_key, "correction grant")
    path = f"/v1/sessions/{quote(target.session_id, safe='')}/autonomous-corrections"
    before = await _json(await client.get(path), "correction status")
    _validate_correction_status(before, target, require_disabled=enabled)
    body = correction_update_body(before, enabled=enabled, idempotency_key=idempotency_key)
    mutation = await _json(await client.patch(path, json=body), "correction grant update")
    after = await _json(await client.get(path), "correction status refresh")
    _validate_correction_status(after, target, require_disabled=False)
    if after.get("enabled") is not enabled or after.get("effective_enabled") is not (
        enabled and after.get("connected") is True
    ):
        raise LiveContractError("correction grant did not reach the requested canonical state")
    return {"before": before, "mutation": mutation, "after": after}


async def detach_observer(
    client: AsyncClient, *, inspection_id: str, selection_id: str
) -> dict[str, Any]:
    receipt = await _json(
        await client.post(
            "/v1/adapters/codex/shared/detach",
            json={"inspection_id": inspection_id, "selection_id": selection_id},
        ),
        "shared detach",
    )
    if receipt.get("ok") is not True or receipt.get("worker_stopped") is not False:
        raise LiveContractError("detach receipt does not prove the worker was preserved")
    return receipt
