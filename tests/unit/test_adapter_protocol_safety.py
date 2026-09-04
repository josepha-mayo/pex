from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest
from pex_bridge.adapters.acp_client import AcpClient, AcpRpcError, FakeAcpTransport
from pex_bridge.adapters.acp_harness import HermesAdapter, KimiAdapter, OmpAdapter
from pex_bridge.adapters.claude_code import ClaudeCodeAdapter
from pex_bridge.adapters.http_json import MemoryHttpTransport
from pex_bridge.adapters.qwen import QwenAdapter
from pex_protocol.capabilities import AdapterSupportLabel, PermissionResponseMode
from pex_protocol.enums import EventType, HarnessType
from pex_protocol.session import HarnessSession


class AuthOfferingTransport(FakeAcpTransport):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    async def request(self, method, params=None):
        self.calls.append(method)
        result = await super().request(method, params)
        if method == "initialize":
            result["authMethods"] = [{"id": "cursor_login"}]
        return result


@pytest.mark.asyncio
async def test_acp_probe_never_authenticates_without_explicit_action():
    transport = AuthOfferingTransport()
    client = AcpClient(transport)

    await client.handshake()
    assert "authenticate" not in transport.calls
    assert transport.authed is False

    await client.authenticate("cursor_login")
    assert transport.authed is True
    assert transport.calls[-1] == "authenticate"


@pytest.mark.asyncio
async def test_acp_rejects_wrong_protocol_and_terminal_auth():
    class WrongVersion(FakeAcpTransport):
        async def request(self, method, params=None):
            result = await super().request(method, params)
            if method == "initialize":
                result["protocolVersion"] = 2
            return result

    with pytest.raises(RuntimeError, match="unsupported protocol"):
        await AcpClient(WrongVersion()).handshake()

    transport = AuthOfferingTransport()
    transport_type = "terminal"

    async def request(method, params=None):
        result = await FakeAcpTransport.request(transport, method, params)
        if method == "initialize":
            result["authMethods"] = [{"id": "terminal-login", "type": transport_type}]
        return result

    transport.request = request
    client = AcpClient(transport)
    await client.handshake()
    with pytest.raises(ValueError, match="cannot use the authenticate method"):
        await client.authenticate("terminal-login")


@pytest.mark.asyncio
async def test_acp_session_list_paginates_and_setup_is_schema_complete(tmp_path: Path):
    class PagedTransport(FakeAcpTransport):
        async def request(self, method, params=None):
            if method == "session/list":
                if (params or {}).get("cursor") == "next":
                    return {"sessions": [{"sessionId": "two"}], "nextCursor": None}
                return {"sessions": [{"sessionId": "one"}], "nextCursor": "next"}
            return await super().request(method, params)

    transport = PagedTransport()
    client = AcpClient(transport)
    assert [item["sessionId"] for item in await client.list_sessions()] == ["one", "two"]

    with pytest.raises(RuntimeError, match="loaded or resumed"):
        await client.prompt("one", "continue")
    cwd = str(tmp_path.resolve())
    await client.activate("one", cwd)
    await client.prompt("one", "continue")
    assert transport.loaded == [{"sessionId": "one", "cwd": cwd, "mcpServers": []}]


@pytest.mark.asyncio
async def test_explicit_acp_attach_requires_auth_then_starts_pump(monkeypatch):
    import pex_bridge.app as app_module
    from fastapi import HTTPException

    class RequiresAuth(FakeAcpTransport):
        async def request(self, method, params=None):
            if method == "initialize":
                result = await super().request(method, params)
                result["authMethods"] = [{"id": "cached_token"}]
                return result
            if method == "session/list" and not self.authed:
                raise AcpRpcError(-32000, "Authentication required")
            return await super().request(method, params)

    rejected_transport = RequiresAuth()
    rejected = KimiAdapter()
    rejected.attach_acp(rejected_transport)
    with pytest.raises(HTTPException) as error:
        await app_module._finish_acp_attach(rejected, {})
    assert error.value.status_code == 409
    assert rejected.acp is None
    assert rejected_transport.closed is True

    accepted = KimiAdapter()
    accepted.attach_acp(RequiresAuth())

    async def ingest(*_):
        return None

    monkeypatch.setattr(
        app_module,
        "_start_event_pumps",
        lambda: accepted.start_pipeline_pump(ingest),
    )
    caps = await app_module._finish_acp_attach(
        accepted,
        {"auth_method": "cached_token", "auth_metadata": {"headless": True}},
    )
    assert caps.support_label == AdapterSupportLabel.STRONG
    assert accepted.acp is not None
    assert accepted.acp.transport.authed is True
    assert accepted._pump_task is not None
    accepted._pump_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await accepted._pump_task


@pytest.mark.asyncio
async def test_acp_permission_is_session_bound_allow_once_and_write_acknowledged(tmp_path: Path):
    adapter = KimiAdapter()
    transport = FakeAcpTransport()
    adapter.attach_acp(transport)
    session = (await adapter.discover_sessions())[0]
    await adapter.acp.activate(session.vendor_session_id, str(tmp_path.resolve()))
    seen = []

    async def ingest(event, bound_session):
        seen.append(event)
        assert bound_session.id == session.id
        assert event.approval_request["method"] == "session/request_permission"
        wrong = HarnessSession(
            id="kimi:wrong",
            harness_type=HarnessType.KIMI,
            vendor_session_id="wrong",
        )
        assert (
            await adapter.respond_permission(wrong, event.approval_request["request_id"], "allow")
            is False
        )
        assert (
            await adapter.respond_permission(session, event.approval_request["request_id"], "allow")
            is True
        )

    pump = adapter.start_pipeline_pump(ingest)

    async def provider_request():
        response = await transport.on_permission(
            {
                "sessionId": session.vendor_session_id,
                "toolCall": {
                    "toolCallId": "tool-1",
                    "title": "Edit file",
                    "kind": "edit",
                    "rawInput": {"path": "a.py"},
                },
                "options": [
                    {"optionId": "always", "name": "Always", "kind": "allow_always"},
                    {"optionId": "once", "name": "Once", "kind": "allow_once"},
                    {"optionId": "reject", "name": "Reject", "kind": "reject_once"},
                ],
            }
        )
        response.delivered.set_result(None)
        return response.result

    request = asyncio.create_task(provider_request())
    try:
        result = await asyncio.wait_for(request, timeout=2)
        assert result == {"outcome": {"outcome": "selected", "optionId": "once"}}
        assert len(seen) == 1
    finally:
        pump.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pump


def test_acp_idle_notification_is_not_a_terminal_turn():
    adapter = OmpAdapter()
    session = HarnessSession(
        id="omp:s1",
        harness_type=HarnessType.OMP,
        vendor_session_id="s1",
    )
    adapter.sessions[session.id] = session
    event = adapter.normalize_acp(
        session,
        {
            "method": "session/update",
            "params": {
                "sessionId": "s1",
                "update": {
                    "sessionUpdate": "state_update",
                    "state": "idle",
                    "stopReason": "end_turn",
                },
            },
        },
    )
    assert event is not None
    assert event.event_type == EventType.STATUS

    terminal = adapter.normalize_prompt_result(session, "dispatch", {"stopReason": "end_turn"})
    assert terminal.event_type == EventType.STOP
    assert terminal.event_id.startswith("omp:s1:acp-prompt:")


@pytest.mark.asyncio
async def test_qwen_sse_source_path_prevents_cross_session_fallback():
    adapter = QwenAdapter(MemoryHttpTransport())
    adapter.sessions = {
        "qwen:a": HarnessSession(id="qwen:a", harness_type=HarnessType.QWEN, vendor_session_id="a"),
        "qwen:b": HarnessSession(id="qwen:b", harness_type=HarnessType.QWEN, vendor_session_id="b"),
    }
    payload = {
        "id": 7,
        "v": 1,
        "type": "session_update",
        "data": {"sessionUpdate": "agent_message_chunk", "content": {"text": "same"}},
        "_pex_sse_path": "/session/b/events",
    }
    bound = adapter._session_for(payload)
    assert bound is not None and bound.id == "qwen:b"
    assert adapter._session_for({"id": 8, "type": "session_update", "data": {}}) is None

    with pytest.raises(ValueError, match="session binding mismatch"):
        adapter.normalize_sse(adapter.sessions["qwen:a"], payload)
    second = adapter.normalize_sse(adapter.sessions["qwen:b"], payload)
    assert second.session_id == "qwen:b"


@pytest.mark.asyncio
async def test_qwen_rejects_unverified_prompt_receipt():
    class BadReceipt(MemoryHttpTransport):
        async def request(self, method, path, *, json=None):
            if method.upper() == "POST" and path.endswith("/prompt"):
                return {"ok": True}
            return await super().request(method, path, json=json)

    transport = BadReceipt()
    adapter = QwenAdapter(transport)
    session = (await adapter.discover_sessions())[0]

    async def ingest(*_):
        return None

    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(20):
            if adapter._events_connected(session):
                break
            await asyncio.sleep(0.01)
        with pytest.raises(RuntimeError, match="no verified prompt id"):
            await adapter.send_message(session, "continue")
        assert adapter.inbox.get(session.id, []) == []
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_qwen_expired_prompt_stays_locked_when_completion_was_not_observed(monkeypatch):
    adapter = QwenAdapter(MemoryHttpTransport())
    session = HarnessSession(
        id="qwen:uncertain",
        harness_type=HarnessType.QWEN,
        vendor_session_id="uncertain",
        cwd="C:/project",
        project_id="C:/project",
    )
    adapter.sessions[session.id] = session
    adapter._active_prompt_ids[session.id] = "prompt-1"
    adapter._active_prompt_started_at[session.id] = 1.0
    monkeypatch.setattr(
        "pex_bridge.adapters.qwen.time.monotonic",
        lambda: 1.0 + 3_601.0,
    )

    assert adapter._prompt_active(session.id) is True
    assert adapter._active_prompt_ids[session.id] == "prompt-1"
    assert session.metadata["prompt_delivery_state"] == "completion_unobserved"


@pytest.mark.asyncio
async def test_qwen_permissions_are_session_bound_and_allow_once_only():
    transport = MemoryHttpTransport()
    adapter = QwenAdapter(transport)
    await adapter.probe()
    first = HarnessSession(id="qwen:a", harness_type=HarnessType.QWEN, vendor_session_id="a")
    second = HarnessSession(id="qwen:b", harness_type=HarnessType.QWEN, vendor_session_id="b")
    adapter.sessions = {first.id: first, second.id: second}
    adapter.normalize_sse(
        first,
        {
            "id": 1,
            "type": "permission_request",
            "data": {
                "requestId": "perm-1",
                "sessionId": "a",
                "options": [
                    {
                        "optionId": "always",
                        "name": "Always allow",
                        "kind": "allow_always",
                    },
                    {
                        "optionId": "reject-always",
                        "name": "Always reject",
                        "kind": "reject_always",
                    },
                    {"optionId": "reject", "name": "Reject", "kind": "reject_once"},
                ],
            },
            "_pex_sse_path": "/session/a/events",
        },
    )
    assert await adapter.respond_permission(second, "perm-1", "deny") is False
    assert await adapter.respond_permission(first, "perm-1", "allow") is False
    assert await adapter.respond_permission(first, "perm-1", "deny") is True
    assert transport.permissions[-1]["path"] == "/permission/perm-1"
    assert transport.permissions[-1]["body"]["outcome"]["optionId"] == "reject"
    assert await adapter.respond_permission(first, "perm-1", "deny") is False


def test_qwen_rejects_sse_payload_session_mismatch_and_stale_terminal():
    adapter = QwenAdapter(MemoryHttpTransport())
    session = HarnessSession(id="qwen:a", harness_type=HarnessType.QWEN, vendor_session_id="a")
    adapter.sessions[session.id] = session
    assert (
        adapter._session_for(
            {
                "type": "session_update",
                "data": {"sessionId": "b"},
                "_pex_sse_path": "/session/a/events",
            }
        )
        is None
    )

    adapter._active_prompt_ids[session.id] = "new-prompt"
    stale = adapter.normalize_sse(
        session,
        {
            "id": 9,
            "type": "turn_complete",
            "data": {"sessionId": "a", "promptId": "old-prompt", "stopReason": "end_turn"},
            "_pex_sse_path": "/session/a/events",
        },
    )
    assert stale.event_type == EventType.STATUS
    assert adapter._active_prompt_ids[session.id] == "new-prompt"

    current = adapter.normalize_sse(
        session,
        {
            "id": 10,
            "type": "turn_complete",
            "data": {"sessionId": "a", "promptId": "new-prompt", "stopReason": "end_turn"},
            "_pex_sse_path": "/session/a/events",
        },
    )
    assert current.event_type == EventType.STOP
    assert session.id not in adapter._active_prompt_ids


@pytest.mark.asyncio
async def test_qwen_designated_policy_does_not_advertise_anonymous_votes():
    class DesignatedTransport(MemoryHttpTransport):
        async def request(self, method, path, *, json=None):
            result = await super().request(method, path, json=json)
            if method.upper() == "GET" and path == "/capabilities":
                result["policy"] = {"permission": "designated"}
            return result

    transport = DesignatedTransport()
    adapter = QwenAdapter(transport)
    await adapter.discover_sessions()

    async def ingest(*_):
        return None

    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(20):
            caps = await adapter.probe()
            if caps.support_label == AdapterSupportLabel.STRONG:
                break
            await asyncio.sleep(0.01)
        assert caps.approve is False
        assert caps.deny is False
        assert caps.permission_response_mode == PermissionResponseMode.NONE
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_claude_and_qwen_clear_stale_stop_followups_without_blocking():
    claude = ClaudeCodeAdapter()
    claude_session = claude.ingest_hook({"session_id": "c1"})
    claude.normalize_hook({"hook_event_name": "Stop", "session_id": "c1"}, claude_session)
    assert await claude.send_message(claude_session, "Verify report.txt")
    assert claude.hook_response(claude_session, {"hook_event_name": "Stop"}, None) == {}
    assert claude.consume_followup(claude_session.id) is None

    qwen = QwenAdapter()
    qwen_session = qwen.ingest_hook({"session_id": "q1"})
    qwen.normalize_hook({"hook_event_name": "Stop", "session_id": "q1"}, qwen_session)
    assert await qwen.send_message(qwen_session, "Verify report.txt")
    assert qwen.hook_response(qwen_session, {"hook_event_name": "Stop"}, None) == {}
    assert qwen._pending_followups.get(qwen_session.id) is None


def test_hermes_task_identity_and_native_human_escalation():
    from types import SimpleNamespace

    from pex_protocol.enums import PolicyVerdict

    adapter = HermesAdapter()
    session = adapter.ingest_hook({"task_id": "task-1", "hook_event_name": "pre_tool_call"})
    assert session.id == "hermes:task-1"
    response = adapter.hook_response(
        session,
        {"hook_event_name": "pre_tool_call"},
        SimpleNamespace(policy_verdict=PolicyVerdict.ASK_HUMAN, diagnosis="ask operator"),
    )
    assert response == {}


def test_generic_hook_helper_rejects_fabricated_harnesses_and_filters_output():
    path = Path(__file__).resolve().parents[2] / "integrations" / "hooks" / "pex_hook.py"
    spec = importlib.util.spec_from_file_location("pex_generic_hook_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module.HARNESS = "grok_build"
    assert module._endpoint() is None
    module.HARNESS = "claude_code"
    module.BRIDGE = "https://example.com"
    assert module._endpoint() is None
    module.BRIDGE = "http://127.0.0.1:7420"
    assert module._endpoint() == "http://127.0.0.1:7420/v1/hooks/claude_code"
    module.BRIDGE = "http://localhost:7420"
    assert module._endpoint() == "http://127.0.0.1:7420/v1/hooks/claude_code"
    module.BRIDGE = "http://127.0.0.1:bad"
    assert module._endpoint() is None

    safe = module._safe_response(
        b'{"ok":true,"session_id":"secret","inbox":["x"],"decision":"block","reason":"continue"}'
    )
    assert safe == {"decision": "block", "reason": "continue"}
    annotated = module._safe_response(
        b'{"ok":true,"hookSpecificOutput":'
        b'{"hookEventName":"UserPromptSubmit","additionalContext":"Keep Eval."}}'
    )
    assert annotated == {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "Keep Eval.",
        }
    }
    assert module._safe_response(b'{"decision":"block","decision":"allow"}') == {}
    for payload in ('{"value":NaN}', '{"value":1e9999}'):
        with pytest.raises(ValueError):
            module._strict_json_loads(payload)


def test_hermes_plugin_rejects_ambiguous_or_nonfinite_bridge_json():
    path = Path(__file__).resolve().parents[2] / "integrations" / "hermes-plugin" / "pex_plugin.py"
    spec = importlib.util.spec_from_file_location("pex_hermes_plugin_json_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for payload in ('{"action":"block","action":"allow"}', '{"value":NaN}'):
        with pytest.raises(ValueError):
            module._strict_json_loads(payload)
