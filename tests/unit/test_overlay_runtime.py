from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.http_json import MemoryHttpTransport
from pex_bridge.adapters.opencode import OpenCodeAdapter
from pex_bridge.executor import ActionExecutor
from pex_bridge.overlay_runtime import compile_overlay_runtime
from pex_bridge.store import Store, utcnow
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import EventPhase, EventType, HarnessType, PolicyVerdict
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.overlay import Overlay, OverlayDiff
from pex_protocol.session import HarnessSession


def _applied(overlay_id: str, diff: OverlayDiff, *, seconds: int = 60) -> Overlay:
    applied_at = utcnow()
    return Overlay(
        id=overlay_id,
        session_id="opencode:s1",
        reason="verified debug mismatch",
        diff=diff,
        ttl_seconds=seconds,
        applied_at=applied_at,
        expires_at=applied_at + timedelta(seconds=seconds),
    )


def test_runtime_compiles_only_live_session_overlay_fields():
    first = _applied(
        "ovl_first",
        OverlayDiff(
            system_instructions="Stay on the reproduction.",
            tools_disabled=["WebSearch"],
            extra={"phase": "debug", "pin": "pytest tests/test_parser.py"},
        ),
    )
    second = _applied(
        "ovl_second",
        OverlayDiff(
            tools_disabled=["Browser"],
        ),
    )
    expired = _applied("ovl_expired", OverlayDiff(tools_disabled=["read"]), seconds=1)

    runtime = compile_overlay_runtime(
        [second, expired, first],
        now=expired.expires_at + timedelta(seconds=1),
    )

    assert runtime["active"] is True
    assert runtime["overlay_ids"] == ["ovl_first", "ovl_second"]
    assert runtime["disabled_tools"] == ["Browser", "WebSearch"]
    assert "Stay on the reproduction" in runtime["system_instructions"]
    assert "Current PEX work phase: debug" in runtime["system_instructions"]
    assert "pytest tests/test_parser.py" in runtime["system_instructions"]


@pytest.mark.asyncio
async def test_opencode_overlay_requires_live_plugin_and_supported_session_diff():
    adapter = OpenCodeAdapter(MemoryHttpTransport())
    session = HarnessSession(
        id="opencode:s1",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="s1",
    )
    supported = Overlay(
        id="ovl_supported",
        session_id=session.id,
        reason="debug loop",
        diff=OverlayDiff(
            system_instructions="Stay on the failing test.",
            tools_disabled=["WebSearch"],
            extra={"phase": "debug"},
        ),
    )
    assert await adapter.apply_overlay(session, supported) is False

    adapter.mark_plugin_heartbeat(session.id)
    adapter.sessions[session.id] = session
    assert await adapter.apply_overlay(session, supported) is True
    assert supported.rollback["strategy"] == "bridge_active_overlay_query"
    assert await adapter.revert_overlay(supported.id, supported.rollback) is True

    unsupported = Overlay(
        id="ovl_model",
        session_id=session.id,
        reason="model switch",
        diff=OverlayDiff(model="anthropic/claude-sonnet"),
    )
    assert await adapter.apply_overlay(session, unsupported) is False


@pytest.mark.asyncio
async def test_opencode_plugin_heartbeat_is_bound_to_the_exact_session():
    adapter = OpenCodeAdapter(MemoryHttpTransport())
    first = HarnessSession(
        id="opencode:first",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="first",
    )
    second = HarnessSession(
        id="opencode:second",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="second",
    )
    adapter.sessions = {first.id: first, second.id: second}
    adapter.mark_plugin_heartbeat(first.id)
    overlay = Overlay(
        id="ovl_second",
        session_id=second.id,
        reason="Second session must have its own plugin acknowledgement.",
        diff=OverlayDiff(tools_disabled=["WebSearch"], extra={"phase": "debug"}),
    )

    assert adapter.overlay_projection_ready(first) is True
    assert adapter.overlay_projection_ready(second) is False
    assert await adapter.apply_overlay(second, overlay) is False


@pytest.mark.asyncio
async def test_opencode_overlay_survives_bridge_restart_and_reverts_from_durable_record(tmp_path):
    database = tmp_path / "pex.sqlite"
    session = HarnessSession(
        id="opencode:restart",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="restart",
        project_id="overlay-runtime-restart",
        goal_id="goal_overlay_runtime_restart",
    )
    overlay = Overlay(
        id="ovl_restart",
        session_id=session.id,
        reason="keep the verified reproduction pinned across a bridge restart",
        diff=OverlayDiff(
            system_instructions=(
                "Stay on the failing reproduction. Do not start unrelated research. "
                "Preserve the failing state until the attached acceptance criteria move."
            ),
            tools_disabled=["WebSearch"],
            extra={"phase": "debug"},
        ),
    )
    action = ProposedAction(
        type=InterventionType.APPLY_OVERLAY,
        session_id=session.id,
        goal_id=session.goal_id,
        payload={"overlay": overlay.model_dump(mode="json")},
        rationale="Use an ephemeral session overlay while debugging.",
        reversible=True,
    )

    first_store = Store(database)
    await first_store.connect()
    first_adapters = AdapterRegistry()
    first_adapters.opencode.mark_plugin_heartbeat(session.id)
    first_adapters.opencode.sessions[session.id] = session
    first_adapters.opencode.apply_overlay = AsyncMock(
        side_effect=AssertionError("Store projection must not call adapter apply")
    )
    now = utcnow()
    await first_store.upsert_goal(
        Goal(
            id="goal_overlay_runtime_restart",
            project_id="overlay-runtime-restart",
            title="Keep the OpenCode overlay durable across restart",
            objective="Replay only the exact Store-projected overlay lifecycle.",
            created_at=now,
            updated_at=now,
        )
    )
    await first_store.upsert_session(session)
    owner_intervention_id = "int_overlay_runtime_restart"
    await first_store.add_intervention(
        Intervention(
            id=owner_intervention_id,
            session_id=session.id,
            goal_id=session.goal_id,
            trigger="test_overlay_runtime",
            evidence=action.evidence,
            diagnosis="bounded_test_overlay",
            proposed_action=action,
            confidence=action.confidence,
            risk=action.risk.value,
            reversible=action.reversible,
            authority_required=action.authority_required.value,
            action_taken=InterventionType.APPLY_OVERLAY.value,
            policy_verdict=PolicyVerdict.ALLOW,
            result="delivery_reserved",
            created_at=now,
        )
    )
    try:
        first_executor = ActionExecutor(first_adapters, first_store)
        assert (
            await first_executor.execute(
                action,
                PolicyVerdict.ALLOW,
                operation_owner_id=owner_intervention_id,
            )
            == "overlay_applied"
        )
        first_adapters.opencode.apply_overlay.assert_not_awaited()
    finally:
        await first_store.close()

    restarted_store = Store(database)
    await restarted_store.connect()
    restarted_adapters = AdapterRegistry()
    restarted_adapters.opencode.mark_plugin_heartbeat(session.id)
    restarted_adapters.opencode.revert_overlay = AsyncMock(
        side_effect=AssertionError("Store projection must not call adapter revert")
    )
    try:
        live = compile_overlay_runtime(await restarted_store.active_overlays(session.id))
        assert live["active"] is True
        assert live["overlay_ids"] == [overlay.id]
        assert live["disabled_tools"] == ["WebSearch"]

        restarted_executor = ActionExecutor(restarted_adapters, restarted_store)
        assert await restarted_executor.revert_overlay(overlay.id) == "overlay_reverted"
        restarted_adapters.opencode.revert_overlay.assert_not_awaited()
        inactive = compile_overlay_runtime(await restarted_store.active_overlays(session.id))
        assert inactive == {
            "active": False,
            "scope": "session",
            "overlay_ids": [],
            "system_instructions": "",
            "disabled_tools": [],
            "overlays": [],
        }
    finally:
        await restarted_store.close()


def test_runtime_rejects_fields_and_sizes_the_plugin_cannot_enforce():
    unsupported = _applied(
        "ovl_permission",
        OverlayDiff(permission_policy={"bash": "deny"}),
    )
    with pytest.raises(ValueError, match="unsupported runtime fields"):
        compile_overlay_runtime([unsupported])

    too_many = [
        _applied(f"ovl_{index}", OverlayDiff(tools_disabled=[f"tool-{index}"]))
        for index in range(65)
    ]
    with pytest.raises(ValueError, match="64 active overlays"):
        compile_overlay_runtime(too_many)


@pytest.mark.asyncio
async def test_opencode_current_permission_and_sse_shapes_are_normalized():
    transport = MemoryHttpTransport()
    adapter = OpenCodeAdapter(transport)
    session = HarnessSession(
        id="opencode:s1",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="s1",
        cwd="C:/project one",
        project_id="C:/project one",
    )
    adapter.sessions[session.id] = session

    adapter.normalize_sse(
        session,
        {
            "type": "permission.updated",
            "properties": {"id": "perm-1", "sessionID": "s1"},
            "directory": "C:/project one",
        },
    )
    assert await adapter.respond_permission(session, "perm-1", "deny") is True
    assert transport.permissions[-1]["body"] == {"response": "reject"}
    assert "directory=C%3A%2Fproject%20one" in transport.permissions[-1]["path"]

    permission = adapter.normalize_sse(
        session,
        {
            "type": "permission.updated",
            "properties": {"id": "perm-2", "sessionID": "s1", "type": "bash"},
            "directory": "C:/project one",
        },
    )
    assert permission.event_type == EventType.PERMISSION_REQUEST
    assert permission.phase == EventPhase.BEFORE
    assert permission.approval_request == {"request_id": "perm-2"}

    tool = adapter.normalize_sse(
        session,
        {
            "type": "message.part.updated",
            "properties": {
                "sessionID": "s1",
                "part": {
                    "type": "tool",
                    "tool": "bash",
                    "state": {"status": "error", "error": "exit 1"},
                },
            },
            "directory": "C:/project one",
        },
    )
    assert tool.event_type == EventType.TOOL_FAILURE
    assert tool.tool_name == "bash"
    assert tool.error == "exit 1"
