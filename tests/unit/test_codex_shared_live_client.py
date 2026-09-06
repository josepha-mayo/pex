"""Negative contracts for the opt-in shared-existing-worker HTTP helper.

The fixtures mirror only fields published by the bridge routes and desktop
correction-status parser.  They deliberately prove refusal before a mutation.
"""

from __future__ import annotations

import json
import os

import httpx
import pytest

from tests.contract.codex_shared_live_client import (
    ExistingCodexTarget,
    LiveContractError,
    _same_cwd,
    create_goal_and_attach,
    inspect_and_confirm,
    set_correction_grant,
)

TARGET = ExistingCodexTarget(
    socket_path=r"\\.\pipe\pex-live-worker",
    thread_id="thread-live-1",
    project_id="project-live-1",
    cwd=r"C:\work\shared-live",
)


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler, base_url="http://bridge.test")


def _scope(*, thread_id: str = TARGET.thread_id) -> dict[str, object]:
    return {
        "schema": "pex.autonomous-correction-grant.v1",
        "session_id": TARGET.session_id,
        "thread_id": thread_id,
        "root_session_id": "root-live-1",
        "goal_id": "goal-live-1",
        "project_id": TARGET.project_id,
        "project_binding": "binding-live-1",
        "workspace_sha256": "a" * 64,
        "subscription_authorization_id": "inspection-live-1",
        "subscription_selection_id": "selection-live-1",
        "endpoint_identity": "endpoint-live-1",
        "connection_generation": 1,
        "control_revision": 4,
        "goal_intent_revision": 2,
        "goal_intent_hash": "b" * 64,
        "allowed_intervention_types": [
            "CONTINUE_SESSION",
            "INJECT_CONTEXT",
            "REQUEST_VERIFICATION",
            "SEND_NUDGE",
        ],
    }


def _correction_status(*, thread_id: str = TARGET.thread_id) -> dict[str, object]:
    return {
        "enabled": False,
        "effective_enabled": False,
        "connected": True,
        "reason": "ready",
        "delivery_proven": False,
        "scope": _scope(thread_id=thread_id),
    }


@pytest.mark.skipif(os.name != "nt", reason="Windows normalizes cwd case")
@pytest.mark.asyncio
async def test_windows_cwd_case_equivalence_preserves_exact_target() -> None:
    calls: list[httpx.Request] = []
    canonical_cwd = TARGET.cwd.lower()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"connection": None})
        if request.url.path.endswith("/inspect"):
            return httpx.Response(
                200,
                json={
                    "inspection_id": "inspection-live-1",
                    "selection_id": "selection-live-1",
                    "session_id": TARGET.session_id,
                    "thread_id": TARGET.thread_id,
                    "project_id": TARGET.project_id,
                    "cwd": canonical_cwd,
                    "subscribed": False,
                    "workspace_binding": {"project_id": TARGET.project_id},
                },
            )
        if request.url.path.endswith("/confirm"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "kind": "shared",
                    "support": "observe_only",
                    "session_id": TARGET.session_id,
                    "worker_delivery_enabled": False,
                    "workspace_binding": {"project_id": TARGET.project_id},
                    "subscription": {
                        "pex_session_id": TARGET.session_id,
                        "thread_id": TARGET.thread_id,
                        "project_id": TARGET.project_id,
                        "cwd": canonical_cwd,
                    },
                },
            )
        pytest.fail(f"unexpected request: {request.url.path}")

    async with _client(httpx.MockTransport(handler)) as client:
        await inspect_and_confirm(client, TARGET, operator_confirmed_exact_target=True)

    assert [request.url.path for request in calls] == [
        "/v1/adapters/codex/shared/status",
        "/v1/adapters/codex/shared/inspect",
        "/v1/adapters/codex/shared/confirm",
    ]


@pytest.mark.asyncio
async def test_different_cwd_never_reaches_confirmation() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"connection": None})
        if request.url.path.endswith("/inspect"):
            return httpx.Response(
                200,
                json={
                    "inspection_id": "inspection-live-1",
                    "selection_id": "selection-live-1",
                    "session_id": TARGET.session_id,
                    "thread_id": TARGET.thread_id,
                    "project_id": TARGET.project_id,
                    "cwd": r"C:\other\shared-live",
                    "subscribed": False,
                },
            )
        pytest.fail(f"unexpected request: {request.url.path}")

    async with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(LiveContractError, match="does not match"):
            await inspect_and_confirm(client, TARGET, operator_confirmed_exact_target=True)

    assert [request.url.path for request in calls] == [
        "/v1/adapters/codex/shared/status",
        "/v1/adapters/codex/shared/inspect",
    ]


@pytest.mark.skipif(os.name == "nt", reason="Windows cwd comparison is case-insensitive")
def test_posix_cwd_comparison_remains_case_sensitive() -> None:
    assert _same_cwd("/work/Shared", "/work/shared") is False


@pytest.mark.asyncio
async def test_wrong_inspection_target_never_reaches_confirmation() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"connection": None})
        if request.url.path.endswith("/inspect"):
            return httpx.Response(
                200,
                json={
                    "inspection_id": "inspection-live-1",
                    "selection_id": "selection-live-1",
                    "session_id": TARGET.session_id,
                    "thread_id": "other-thread",
                    "project_id": TARGET.project_id,
                    "cwd": TARGET.cwd,
                    "subscribed": False,
                },
            )
        pytest.fail(f"unexpected request: {request.url.path}")

    async with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(LiveContractError, match="does not match"):
            await inspect_and_confirm(client, TARGET, operator_confirmed_exact_target=True)

    assert [request.url.path for request in calls] == [
        "/v1/adapters/codex/shared/status",
        "/v1/adapters/codex/shared/inspect",
    ]


@pytest.mark.asyncio
async def test_invalid_attach_key_cannot_create_an_orphan_goal() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        pytest.fail(f"mutation must not be attempted: {request.url.path}")

    async with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(LiveContractError, match="goal attachment"):
            await create_goal_and_attach(
                client,
                TARGET,
                goal_body={
                    "project_id": TARGET.project_id,
                    "idempotency_key": "goal-live-123",
                    "attach_idempotency_key": "short",
                    "title": "Recovery check",
                    "objective": "Report is shipped.",
                },
            )

    assert calls == []


@pytest.mark.asyncio
async def test_bound_session_never_creates_or_replaces_a_goal() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        assert request.url.path == "/v1/pet"
        return httpx.Response(
            200,
            json={"sessions": [{
                "id": TARGET.session_id, "goal_id": "existing-goal", "control_revision": 3,
            }]},
        )

    async with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(LiveContractError, match="already has a goal"):
            await create_goal_and_attach(
                client,
                TARGET,
                goal_body={
                    "project_id": TARGET.project_id,
                    "idempotency_key": "goal-live-123",
                    "attach_idempotency_key": "attach-live-123",
                    "title": "Recovery check",
                    "objective": "Report is shipped.",
                },
            )

    assert [request.url.path for request in calls] == ["/v1/pet"]


@pytest.mark.asyncio
async def test_goal_success_uses_pet_control_revision_and_exact_attach_cas() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/v1/pet":
            return httpx.Response(200, json={"sessions": [{
                "id": TARGET.session_id, "goal_id": None, "control_revision": 7,
            }]})
        if request.url.path == "/v1/goals":
            body = json.loads(request.content)
            assert "attach_idempotency_key" not in body
            return httpx.Response(200, json={
                "id": "goal-live-1", "intent_revision": 2, "intent_hash": "b" * 64,
            })
        if request.url.path.endswith("/attach"):
            assert json.loads(request.content) == {
                "idempotency_key": "attach-live-123",
                "goal_id": "goal-live-1",
                "replace_existing": False,
                "expected_goal_id": None,
                "expected_control_revision": 7,
                "expected_goal_intent_revision": 2,
            }
            return httpx.Response(200, json={
                "session_goal_attachment_receipt": {
                    "schema": "pex.session-goal-attachment-receipt.v1",
                    "goal_id": "goal-live-1", "after_goal_id": "goal-live-1",
                }
            })
        pytest.fail(f"unexpected request: {request.url.path}")

    async with _client(httpx.MockTransport(handler)) as client:
        result = await create_goal_and_attach(client, TARGET, goal_body={
            "project_id": TARGET.project_id,
            "idempotency_key": "goal-live-123",
            "attach_idempotency_key": "attach-live-123",
            "title": "Recovery check",
            "objective": "Report is shipped.",
        })

    assert result["attachment"]["session_goal_attachment_receipt"]["goal_id"] == "goal-live-1"
    assert [request.url.path for request in calls] == [
        "/v1/pet", "/v1/goals", "/v1/sessions/codex:thread-live-1/attach",
    ]


@pytest.mark.asyncio
async def test_grant_success_uses_exact_fresh_scope_and_confirms_state() -> None:
    calls: list[httpx.Request] = []
    statuses = [_correction_status(), {
        **_correction_status(), "enabled": True, "effective_enabled": True,
    }]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=statuses.pop(0))
        body = json.loads(request.content)
        assert body["expected_control_revision"] == 4
        assert body["expected_goal_id"] == "goal-live-1"
        assert body["expected_subscription_authorization_id"] == "inspection-live-1"
        assert body["expected_connection_generation"] == 1
        return httpx.Response(200, json={"autonomous_correction_grant": {"enabled": True}})

    async with _client(httpx.MockTransport(handler)) as client:
        result = await set_correction_grant(
            client, TARGET, enabled=True, idempotency_key="grant-live-123",
        )

    assert result["after"]["effective_enabled"] is True
    assert [request.method for request in calls] == ["GET", "PATCH", "GET"]


@pytest.mark.asyncio
async def test_wrong_correction_scope_never_grants_authority() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        return httpx.Response(200, json=_correction_status(thread_id="other-thread"))

    async with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(LiveContractError, match="does not bind"):
            await set_correction_grant(
                client,
                TARGET,
                enabled=True,
                idempotency_key="grant-live-123",
            )

    assert [request.method for request in calls] == ["GET"]
