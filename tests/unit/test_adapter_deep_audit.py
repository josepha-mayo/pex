from __future__ import annotations

import asyncio
import importlib.util
import json
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import httpx
import pytest
from pex_bridge.adapters import http_json as http_json_module
from pex_bridge.adapters.acp_client import (
    AcpClient,
    AcpRpcError,
    FakeAcpTransport,
    StdioAcpTransport,
    _AcpMalformedResult,
)
from pex_bridge.adapters.attach import _bounded_secret, _https_origin, _loopback_http_origin
from pex_bridge.adapters.base import DeliveryUncertainError, bounded_observed_mapping
from pex_bridge.adapters.claude_code import ClaudeCodeAdapter
from pex_bridge.adapters.codex import (
    CodexAdapter,
    CodexAppServerTransport,
    CodexStdioTransport,
    _validated_jsonrpc_id,
)
from pex_bridge.adapters.cursor import CursorAdapter, _post_bridge_followup, _valid_bridge_token
from pex_bridge.adapters.discover import _resolved_cli, probe_local_harnesses
from pex_bridge.adapters.http_json import (
    LiveHttpTransport,
    MemoryHttpTransport,
    _bounded_sse_lines,
    _decode_sse_data,
    _validated_request_path,
    transport_events_since,
)
from pex_bridge.adapters.opencode import OpenCodeAdapter
from pex_bridge.adapters.qwen import QwenAdapter
from pex_bridge.adapters.strict_json import strict_json_loads
from pex_bridge.adapters.synthetic import SyntheticAdapter
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, EventType, HarnessType, PolicyVerdict
from pex_protocol.intervention import Intervention
from pex_protocol.overlay import Overlay, OverlayDiff
from pex_protocol.session import HarnessEvent, HarnessSession


def _successful_stop_intervention(session_id: str, text: str) -> Intervention:
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=session_id,
        payload={"text": text},
        rationale="Missing required evidence.",
        evidence=["missing:report.txt"],
        risk=RiskLevel.LOW,
        authority_required=Authority.LOCAL_POLICY,
    )
    return Intervention(
        id="int-stop",
        session_id=session_id,
        trigger=EventType.STOP.value,
        evidence=list(action.evidence),
        diagnosis="Missing required evidence.",
        proposed_action=action,
        risk=RiskLevel.LOW.value,
        authority_required=Authority.LOCAL_POLICY.value,
        action_taken=InterventionType.SEND_NUDGE.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="sent",
        created_at=datetime.now(UTC),
    )


def _inline_permission_intervention(
    session_id: str,
    *,
    trigger: EventType,
    decision: str,
    request_id: str = "permission-1",
    verdict: PolicyVerdict = PolicyVerdict.ALLOW,
    action_taken: str = InterventionType.RESPOND_PERMISSION.value,
    result: str | None = None,
) -> Intervention:
    action = ProposedAction(
        type=InterventionType.RESPOND_PERMISSION,
        session_id=session_id,
        payload={"request_id": request_id, "decision": decision},
        rationale="Exact active permission request.",
        evidence=["tool:Shell"],
        risk=RiskLevel.LOW,
        authority_required=Authority.LOCAL_POLICY,
    )
    return Intervention(
        id="int-permission",
        session_id=session_id,
        trigger=trigger.value,
        evidence=list(action.evidence),
        diagnosis="Permission reviewed.",
        proposed_action=action,
        risk=RiskLevel.LOW.value,
        authority_required=Authority.LOCAL_POLICY.value,
        action_taken=action_taken,
        policy_verdict=verdict,
        result=(
            result
            or (
                "permission_delegated_to_harness"
                if verdict == PolicyVerdict.ASK_HUMAN
                else f"permission_{decision}_inline"
            )
        ),
        created_at=datetime.now(UTC),
    )


def test_cursor_requires_stable_conversation_identity_and_keeps_parallel_chats_separate():
    adapter = CursorAdapter()
    with pytest.raises(ValueError, match="conversation_id"):
        adapter.upsert_from_hook({"cwd": "C:/same", "workspace_roots": ["C:/same"]})

    first = adapter.upsert_from_hook(
        {"conversation_id": "conversation-a", "workspace_roots": ["C:/same"]}
    )
    second = adapter.upsert_from_hook(
        {"conversation_id": "conversation-b", "workspace_roots": ["C:/same"]}
    )
    assert first.id == "cursor:conversation-a"
    assert second.id == "cursor:conversation-b"
    assert len(adapter.sessions) == 2


def test_live_transport_origins_and_credentials_fail_closed():
    assert _loopback_http_origin("http://127.0.0.1:4096/", "OpenCode") == ("http://127.0.0.1:4096")
    assert _https_origin("https://api.devin.ai", "Devin") == "https://api.devin.ai"
    for unsafe in (
        "https://127.0.0.1:4096",
        "http://example.com:4096",
        "http://user:secret@127.0.0.1:4096",
        "http://127.0.0.1:4096/session",
    ):
        with pytest.raises(ValueError):
            _loopback_http_origin(unsafe, "OpenCode")
    with pytest.raises(ValueError):
        _https_origin("http://api.devin.ai", "Devin")
    with pytest.raises(ValueError):
        _bounded_secret("x" * 8_193)
    with pytest.raises(ValueError, match="visible ASCII"):
        _bounded_secret("t\N{LATIN SMALL LETTER E WITH ACUTE}ken")
    assert _loopback_http_origin("  http://127.0.0.1:4096/  ", "OpenCode") == (
        "http://127.0.0.1:4096"
    )


@pytest.mark.asyncio
async def test_live_http_transport_bounds_buffered_json_responses(monkeypatch):
    monkeypatch.setattr(http_json_module, "MAX_HTTP_RESPONSE_BYTES", 8)
    transport = LiveHttpTransport("http://127.0.0.1:4096")
    await transport._client.aclose()
    transport._client = httpx.AsyncClient(
        base_url="http://127.0.0.1:4096",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                content=b'{"large":true}',
                headers={"content-type": "application/json"},
            )
        ),
    )
    try:
        with pytest.raises(RuntimeError, match="safety bound"):
            await transport.request("GET", "/session")
        await transport._client.aclose()
        transport._client = httpx.AsyncClient(
            base_url="http://127.0.0.1:4096",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    content=b"not-json",
                    headers={"content-type": "application/json"},
                )
            ),
        )
        with pytest.raises(RuntimeError, match="delivery is uncertain"):
            await transport.request("POST", "/session/s1/prompt", json={"text": "go"})
        transport.events = deque([{"id": 4}, {"id": 5}], maxlen=2)
        transport._event_cursor = 5
        latest, retained, dropped = transport.events_since(0)
        assert (latest, retained, dropped) == (5, [{"id": 4}, {"id": 5}], 3)
    finally:
        await transport.aclose()


@pytest.mark.asyncio
async def test_sse_line_reader_discards_unterminated_oversized_lines(monkeypatch):
    monkeypatch.setattr(http_json_module, "MAX_SSE_LINE_CHARS", 8)
    response = httpx.Response(200, content=b"0123456789\n\ndata: {}\n\n")
    lines = [line async for line in _bounded_sse_lines(response)]
    assert "0123456789" not in lines
    assert lines[-2:] == ["data: {}", ""]


def test_http_fallback_event_reader_and_request_paths_are_strictly_bounded(monkeypatch):
    transport = type("InjectedTransport", (), {"events": [{"id": i} for i in range(12)]})()
    monkeypatch.setattr(http_json_module, "MAX_HTTP_EVENTS", 4)
    latest, retained, dropped = transport_events_since(transport, 0)
    assert latest == 12
    assert retained == [{"id": 8}, {"id": 9}, {"id": 10}, {"id": 11}]
    assert dropped == 8
    with pytest.raises(ValueError, match="non-negative integer"):
        transport_events_since(transport, -1)
    with pytest.raises(ValueError, match="unsafe"):
        _validated_request_path("/session#ignored-fragment")


def test_observed_protocol_mappings_are_redacted_and_have_a_total_text_bound():
    cleaned = bounded_observed_mapping(
        {"tool": {"authorization": "Bearer super-secret-token", "path": "src/app.py"}}
    )
    assert cleaned is not None
    assert "super-secret-token" not in str(cleaned)

    assert bounded_observed_mapping({"chunks": ["x" * 32_768, "y" * 32_768]}) is None
    assert _decode_sse_data(
        ['{"type":"event","token":"secret-value-secret-value"}'],
        "/session/s1/events",
    ) == {
        "type": "event",
        "token": "[REDACTED:token]",
        "_pex_sse_path": "/session/s1/events",
    }


def test_discovered_cli_paths_and_codex_rpc_ids_require_concrete_identity(
    tmp_path,
    monkeypatch,
):
    executable = tmp_path / "opencode.exe"
    executable.write_bytes(b"inventory evidence")
    monkeypatch.setattr("pex_bridge.adapters.discover.shutil.which", lambda _name: str(executable))
    assert _resolved_cli("opencode") == str(executable.resolve())
    monkeypatch.setattr("pex_bridge.adapters.discover.shutil.which", lambda _name: "relative.exe")
    assert _resolved_cli("opencode") is None

    assert _validated_jsonrpc_id(7) == 7
    assert _validated_jsonrpc_id("approval-7") == "approval-7"
    assert _validated_jsonrpc_id(True) is None
    assert _validated_jsonrpc_id("bad\nrequest") is None
    valid_bridge_token = "a" * 32
    assert _valid_bridge_token(valid_bridge_token) == valid_bridge_token
    assert _valid_bridge_token("ascii-token") == ""
    assert _valid_bridge_token("a" * 513) == ""
    assert _valid_bridge_token("t\N{LATIN SMALL LETTER E WITH ACUTE}ken") == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [None, True, 0, -1, float("nan"), float("inf"), 5.1])
async def test_discovery_timeout_is_finite_and_bounded(timeout):
    with pytest.raises(ValueError, match="five seconds"):
        await probe_local_harnesses(timeout)


@pytest.mark.asyncio
async def test_acp_malformed_mutation_receipt_is_delivery_uncertain(tmp_path, monkeypatch):
    executable = tmp_path / "acp.exe"
    executable.write_bytes(b"test executable identity")
    transport = StdioAcpTransport([str(executable.resolve())])

    async def malformed_write(payload):
        transport._pending[payload["id"]].set_exception(_AcpMalformedResult("malformed result"))

    monkeypatch.setattr(transport, "_write", malformed_write)
    with pytest.raises(DeliveryUncertainError, match="authoritative result"):
        await transport.request("session/load", {"sessionId": "s1"})
    with pytest.raises(ValueError, match="malformed result"):
        await transport.request("session/list", {})


def test_adapter_json_decoder_rejects_duplicate_keys_and_nonfinite_numbers():
    assert strict_json_loads('{"ok":true,"nested":{"value":1.5}}') == {
        "ok": True,
        "nested": {"value": 1.5},
    }
    for payload in (
        '{"id":1,"id":2}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":-Infinity}',
        '{"value":1e9999}',
    ):
        with pytest.raises(ValueError):
            strict_json_loads(payload)
        assert _decode_sse_data([payload], "/event") is None


def test_acp_remote_error_text_is_bounded_and_secret_redacted():
    error = AcpRpcError(-32000, "authorization=super-secret-provider-token")
    assert "super-secret-provider-token" not in str(error)
    assert error.data is None


def test_cursor_bridge_followup_distinguishes_rejection_from_uncertain_delivery(monkeypatch):
    monkeypatch.setattr("pex_bridge.adapters.cursor._bridge_token", lambda: "bridge-token")

    def rejected(*_args, **_kwargs):
        raise HTTPError("http://127.0.0.1:7420/redacted", 403, "forbidden", None, None)

    monkeypatch.setattr("pex_bridge.adapters.cursor.urlopen", rejected)
    assert _post_bridge_followup("http://127.0.0.1:7420", "cursor:s1", "continue") is False

    def uncertain(*_args, **_kwargs):
        raise URLError("connection reset")

    monkeypatch.setattr("pex_bridge.adapters.cursor.urlopen", uncertain)
    with pytest.raises(DeliveryUncertainError, match="without a receipt"):
        _post_bridge_followup("http://127.0.0.1:7420", "cursor:s1", "continue")


@pytest.mark.asyncio
async def test_acp_and_codex_line_readers_ignore_ambiguous_jsonrpc_frames(tmp_path):
    executable = tmp_path / "protocol.exe"
    executable.write_bytes(b"test executable identity")

    for transport in (
        StdioAcpTransport([str(executable.resolve())]),
        CodexStdioTransport([str(executable.resolve())]),
    ):
        reader = asyncio.StreamReader()
        if isinstance(transport, StdioAcpTransport):
            reader.feed_data(b'{"jsonrpc":"2.0","id":1,"result":{},"result":[]}\n')
        else:
            reader.feed_data(b'{"id":1,"result":{},"result":[]}\n')
        reader.feed_eof()
        transport._proc = SimpleNamespace(stdout=reader)
        pending = asyncio.get_running_loop().create_future()
        transport._pending[1] = pending
        await transport._read_loop()
        with pytest.raises(RuntimeError, match="stdout"):
            await pending


@pytest.mark.asyncio
async def test_live_http_json_rejects_ambiguous_or_nonfinite_receipts():
    for payload in (b'{"ok":true,"ok":false}', b'{"value":NaN}', b'{"value":1e9999}'):
        transport = LiveHttpTransport("http://127.0.0.1:4096")
        await transport._client.aclose()
        transport._client = httpx.AsyncClient(
            base_url="http://127.0.0.1:4096",
            transport=httpx.MockTransport(
                lambda _request, body=payload: httpx.Response(
                    200,
                    content=body,
                    headers={"content-type": "application/json"},
                )
            ),
        )
        try:
            with pytest.raises(ValueError):
                await transport.request("GET", "/session")
            with pytest.raises(DeliveryUncertainError):
                await transport.request("POST", "/session/s1/prompt", json={"text": "go"})
        finally:
            await transport.aclose()


@pytest.mark.asyncio
async def test_provider_session_titles_are_bounded_and_redacted_before_persistence():
    secret_title = "report token=abcdefghijklmnop"

    acp_transport = FakeAcpTransport()
    acp_transport.sessions = [{"sessionId": "s1", "cwd": "C:/project", "title": secret_title}]
    acp_rows = await AcpClient(acp_transport).list_sessions()
    assert acp_rows[0]["title"] == "report [REDACTED:credential_assignment]"

    opencode_transport = MemoryHttpTransport()
    opencode_transport.sessions = [{"id": "s1", "cwd": "C:/project", "title": secret_title}]
    opencode = (await OpenCodeAdapter(opencode_transport).discover_sessions())[0]
    assert opencode.metadata["title"] == "report [REDACTED:credential_assignment]"

    codex_transport = CodexAppServerTransport()
    codex_transport.threads = [
        {
            "id": "t1",
            "cwd": "C:/project",
            "name": secret_title,
            "source": "token=abcdefghijklmnop",
        }
    ]
    codex = (await CodexAdapter(codex_transport).discover_sessions())[0]
    assert codex.metadata["name"] == "report [REDACTED:credential_assignment]"
    assert codex.metadata["source"] == "[REDACTED:credential_assignment]"


@pytest.mark.asyncio
async def test_cursor_permission_receipt_is_bound_to_the_active_hook_event():
    adapter = CursorAdapter()
    session = adapter.upsert_from_hook({"conversation_id": "permission-chat"})
    event = adapter.normalize_hook(
        {
            "conversation_id": "permission-chat",
            "hook_event_name": "beforeShellExecution",
            "command": "pytest -q",
        },
        session,
    )
    assert await adapter.respond_permission(session, "other-request", "allow") is False
    assert await adapter.respond_permission(session, event.event_id, "allow") is True


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_type", [ClaudeCodeAdapter, QwenAdapter])
async def test_stop_block_requires_matching_evidenced_completed_delivery(adapter_type):
    adapter = adapter_type()
    payload = {"session_id": "stop-1", "hook_event_name": "Stop"}
    session = adapter.ingest_hook(payload)
    adapter.normalize_hook(payload, session)
    assert await adapter.send_message(session, "Verify report.txt")

    intervention = _successful_stop_intervention(session.id, "Verify report.txt")
    assert adapter.hook_response(session, payload, intervention) == {
        "decision": "block",
        "reason": "Verify report.txt",
    }

    adapter.normalize_hook(payload, session)
    assert await adapter.send_message(session, "Verify report.txt")
    mismatched = _successful_stop_intervention(session.id, "Different instruction")
    assert adapter.hook_response(session, payload, mismatched) == {}


@pytest.mark.parametrize("adapter_type", [ClaudeCodeAdapter, QwenAdapter])
def test_hook_permissions_require_exact_completed_inline_action(adapter_type):
    adapter = adapter_type()
    session = adapter.ingest_hook({"session_id": "permission-session"})
    payload = {"hook_event_name": "PreToolUse"}

    event = adapter.normalize_hook(payload, session)
    denied_by_policy = _inline_permission_intervention(
        session.id,
        trigger=EventType.TOOL_CALL,
        decision="deny",
        request_id=event.event_id,
        verdict=PolicyVerdict.DENY,
        result="denied_by_policy",
    )
    assert adapter.hook_response(session, payload, denied_by_policy) == {}

    event = adapter.normalize_hook(payload, session)
    missing_capability = _inline_permission_intervention(
        session.id,
        trigger=EventType.TOOL_CALL,
        decision="deny",
        request_id=event.event_id,
        verdict=PolicyVerdict.DENY,
        action_taken=InterventionType.NOOP.value,
        result="denied_by_policy",
    )
    assert adapter.hook_response(session, payload, missing_capability) == {}

    event = adapter.normalize_hook(payload, session)
    explicit_deny = _inline_permission_intervention(
        session.id,
        trigger=EventType.TOOL_CALL,
        decision="deny",
        request_id=event.event_id,
    )
    response = adapter.hook_response(session, payload, explicit_deny)
    assert response["hookSpecificOutput"]["permissionDecision"] == "deny"

    permission_payload = {"hook_event_name": "PermissionRequest"}
    permission_event = adapter.normalize_hook(permission_payload, session)
    explicit_allow = _inline_permission_intervention(
        session.id,
        trigger=EventType.PERMISSION_REQUEST,
        decision="allow",
        request_id=permission_event.event_id,
    )
    response = adapter.hook_response(
        session,
        permission_payload,
        explicit_allow,
    )
    assert response["hookSpecificOutput"]["decision"] == {"behavior": "allow"}

    wrong_trigger = explicit_deny.model_copy(update={"trigger": EventType.PERMISSION_REQUEST.value})
    adapter.normalize_hook(payload, session)
    assert adapter.hook_response(session, payload, wrong_trigger) == {}

    replay = adapter.normalize_hook(payload, session)
    stale = _inline_permission_intervention(
        session.id,
        trigger=EventType.TOOL_CALL,
        decision="deny",
        request_id="different-hook-event",
    )
    assert replay.event_id != "different-hook-event"
    assert adapter.hook_response(session, payload, stale) == {}


def test_qwen_only_treats_submitted_prompt_as_direct_human_input():
    adapter = QwenAdapter()
    session = adapter.ingest_hook({"session_id": "q-human"})
    generated = adapter.normalize_hook(
        {"hook_event_name": "UserPromptSubmit", "prompt": "generated continuation"},
        session,
    )
    direct = adapter.normalize_hook(
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "wrapped prompt",
            "submitted_prompt": "actual user request",
        },
        session,
    )
    assert generated.event_type == EventType.STATUS
    assert direct.event_type == EventType.USER_PROMPT
    assert direct.message_delta == "actual user request"

    permission_payload = {"hook_event_name": "PreToolUse"}
    permission_event = adapter.normalize_hook(permission_payload, session)
    delegated = _inline_permission_intervention(
        session.id,
        trigger=EventType.TOOL_CALL,
        decision="deny",
        request_id=permission_event.event_id,
        verdict=PolicyVerdict.ASK_HUMAN,
    )
    response = adapter.hook_response(
        session,
        permission_payload,
        delegated,
    )
    assert response["hookSpecificOutput"]["permissionDecision"] == "ask"

    escalation = _inline_permission_intervention(
        session.id,
        trigger=EventType.USER_PROMPT,
        decision="deny",
        verdict=PolicyVerdict.ASK_HUMAN,
        action_taken=InterventionType.ASK_HUMAN.value,
        result="awaiting_human",
    )
    assert (
        adapter.hook_response(
            session,
            {"hook_event_name": "UserPromptSubmit"},
            escalation,
        )
        == {}
    )


@pytest.mark.asyncio
async def test_opencode_global_sse_wrapper_binds_exact_session_and_current_route():
    transport = MemoryHttpTransport()
    adapter = OpenCodeAdapter(transport)
    received: list[HarnessEvent] = []

    async def ingest(event: HarnessEvent, _session: HarnessSession) -> None:
        received.append(event)

    transport.events.append(
        {
            "directory": "C:/project",
            "payload": {
                "type": "message.updated",
                "properties": {"info": {"id": "msg-1", "sessionID": "s1", "role": "user"}},
            },
        }
    )
    transport.events.append(
        {
            "directory": "C:/project",
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "part": {
                        "id": "part-1",
                        "messageID": "msg-1",
                        "sessionID": "s1",
                        "type": "text",
                        "text": "hello",
                    }
                },
            },
        }
    )
    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(50):
            if len(received) >= 2:
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert "/global/event" in transport.connected_sse_paths
    assert {event.session_id for event in received} == {"opencode:s1"}
    assert received[-1].event_type == EventType.USER_PROMPT
    assert received[-1].message_delta == "hello"
    assert "opencode:unknown" not in adapter.sessions


def test_sse_decoder_supports_multiline_data_and_preserves_source_path():
    payload = _decode_sse_data(
        ['{"type":"session_update",', '"data":{"sessionUpdate":"agent_message_chunk"}}'],
        "/session/s1/events",
    )
    assert payload is not None
    assert payload["type"] == "session_update"
    assert payload["_pex_sse_path"] == "/session/s1/events"


@pytest.mark.asyncio
async def test_opencode_permissions_and_overlays_require_real_supported_bindings():
    transport = MemoryHttpTransport()
    adapter = OpenCodeAdapter(transport)
    session = HarnessSession(
        id="opencode:s1",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="s1",
        cwd="C:/project",
        project_id="C:/project",
    )
    assert await adapter.respond_permission(session, "permission-1", "allow") is False
    adapter.normalize_sse(
        session,
        {
            "type": "permission.updated",
            "properties": {
                "id": "permission-1",
                "sessionID": "s1",
                "cwd": "C:/project",
            },
        },
    )
    wrong = session.model_copy(update={"id": "opencode:s2", "vendor_session_id": "s2"})
    assert await adapter.respond_permission(wrong, "permission-1", "allow") is False
    assert await adapter.respond_permission(session, "permission-1", "allow") is True

    adapter.mark_plugin_heartbeat(session.id)
    unsupported = Overlay(
        id="permission-overlay",
        session_id=session.id,
        reason="test unsupported upstream hook",
        diff=OverlayDiff(permission_policy={"bash": "deny"}),
    )
    assert await adapter.apply_overlay(session, unsupported) is False
    assert (await adapter.probe()).modify_permissions is False


@pytest.mark.asyncio
async def test_codex_rejects_turn_safety_overrides_before_delivery():
    adapter = CodexAdapter(CodexAppServerTransport())
    session = (await adapter.discover_sessions())[0]
    with pytest.raises(ValueError, match="cannot override"):
        await adapter.start_turn(session, "continue", {"threadId": "other-thread"})
    assert adapter.inbox.get(session.id, []) == []

    await adapter.start_turn(session, "continue", {"model": "gpt-5.6-sol"})
    assert adapter.last_turn_params is not None
    assert adapter.last_turn_params["model"] == "gpt-5.6-sol"
    assert adapter.last_turn_params["approvalPolicy"] == "never"
    with pytest.raises(ValueError, match="control characters"):
        await adapter.start_turn(session, "continue", {"model": "unsafe\nmodel"})
    with pytest.raises(ValueError, match="outputSchema must be an object"):
        await adapter.start_turn(session, "continue", {"outputSchema": "not-an-object"})
    with pytest.raises(ValueError, match="must be an object"):
        await adapter.start_turn(session, "continue", [])
    for timeout in (True, float("nan"), float("inf"), 3_601):
        with pytest.raises(ValueError, match="timeout"):
            await adapter.wait_for_turn_completion(session, "turn-1", timeout=timeout)


@pytest.mark.asyncio
async def test_codex_resumes_discovered_thread_once_before_first_turn():
    class RecordingTransport(CodexAppServerTransport):
        def __init__(self):
            super().__init__()
            self.calls = []

        async def request(self, method, params=None):
            self.calls.append((method, dict(params or {})))
            return await super().request(method, params)

    transport = RecordingTransport()
    adapter = CodexAdapter(transport)
    session = (await adapter.discover_sessions())[0]
    transport.calls.clear()

    await adapter.start_turn(session, "first")
    await adapter.start_turn(session, "second")

    assert [method for method, _ in transport.calls] == [
        "thread/resume",
        "turn/start",
        "turn/start",
    ]
    assert transport.calls[0][1] == {
        "threadId": session.vendor_session_id,
        "excludeTurns": True,
    }
    assert session.metadata["resumed_model"] == "test-model"
    assert session.metadata["resumed_model_provider"] == "test-provider"


@pytest.mark.asyncio
async def test_codex_serializes_concurrent_first_resume():
    class SlowResumeTransport(CodexAppServerTransport):
        def __init__(self):
            super().__init__()
            self.resume_count = 0
            self.turn_active = False
            self.turn_order = []

        async def request(self, method, params=None):
            if method == "thread/resume":
                self.resume_count += 1
                await asyncio.sleep(0.05)
            if method == "turn/start":
                assert self.turn_active is False
                self.turn_active = True
                text = params["input"][0]["text"]
                self.turn_order.append(f"start:{text}")
                await asyncio.sleep(0.02)
                result = await super().request(method, params)
                self.turn_order.append(f"end:{text}")
                self.turn_active = False
                return result
            return await super().request(method, params)

    transport = SlowResumeTransport()
    adapter = CodexAdapter(transport)
    session = (await adapter.discover_sessions())[0]

    await asyncio.gather(
        adapter.start_turn(session, "first"),
        adapter.start_turn(session, "second"),
    )

    assert transport.resume_count == 1
    assert len(transport.turns) == 2
    assert transport.turn_order == ["start:first", "end:first", "start:second", "end:second"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("resume_result", "error"),
    [
        ({}, "authoritative thread receipt"),
        (
            {
                "thread": {
                    "id": "wrong-thread",
                    "cwd": "C:/fake",
                },
                "cwd": "C:/fake",
                "model": "test-model",
                "modelProvider": "test-provider",
            },
            "requested thread",
        ),
        (
            {
                "thread": {
                    "id": "thr_demo",
                    "cwd": "C:/other",
                },
                "cwd": "C:/other",
                "model": "test-model",
                "modelProvider": "test-provider",
            },
            "workspace did not match",
        ),
        (
            {
                "thread": {
                    "id": "thr_demo",
                    "cwd": "C:/fake",
                },
                "cwd": "C:/other",
                "model": "test-model",
                "modelProvider": "test-provider",
            },
            "workspace did not match",
        ),
        (
            {
                "thread": {
                    "id": "thr_demo",
                    "cwd": "C:/fake",
                },
                "cwd": "C:/fake",
                "modelProvider": "test-provider",
            },
            "authoritative model",
        ),
        (
            {
                "thread": {
                    "id": "thr_demo",
                    "cwd": "C:/fake",
                },
                "cwd": "C:/fake",
                "model": "test-model",
            },
            "model provider",
        ),
        (
            {
                "thread": {
                    "id": "thr_demo",
                    "cwd": "C:/fake",
                    "canAcceptDirectInput": False,
                },
                "cwd": "C:/fake",
                "model": "test-model",
                "modelProvider": "test-provider",
            },
            "cannot accept direct input",
        ),
    ],
)
async def test_codex_refuses_turn_when_resume_receipt_is_not_exact(resume_result, error):
    class BadResumeTransport(CodexAppServerTransport):
        async def request(self, method, params=None):
            if method == "thread/resume":
                return resume_result
            return await super().request(method, params)

    transport = BadResumeTransport()
    adapter = CodexAdapter(transport)
    session = (await adapter.discover_sessions())[0]

    with pytest.raises(DeliveryUncertainError, match=error):
        await adapter.start_turn(session, "must not deliver")

    assert transport.turns == []


@pytest.mark.asyncio
async def test_codex_new_isolated_thread_is_already_loaded(tmp_path):
    class RecordingTransport(CodexAppServerTransport):
        def __init__(self):
            super().__init__()
            self.calls = []

        async def request(self, method, params=None):
            self.calls.append(method)
            return await super().request(method, params)

    transport = RecordingTransport()
    adapter = CodexAdapter(transport)
    session = await adapter.start_isolated_thread(str(tmp_path))
    transport.calls.clear()
    session.goal_id = "goal-attached-after-thread-start"

    await adapter.start_turn(session, "continue")

    assert transport.calls == ["turn/start"]


@pytest.mark.asyncio
async def test_codex_transport_restart_and_replacement_force_fresh_resume():
    class CountingTransport(CodexAppServerTransport):
        def __init__(self):
            super().__init__()
            self.resumes = 0

        async def request(self, method, params=None):
            if method == "thread/resume":
                self.resumes += 1
            return await super().request(method, params)

    first = CountingTransport()
    adapter = CodexAdapter(first)
    session = (await adapter.discover_sessions())[0]
    await adapter.start_turn(session, "first")

    await first.close()
    await adapter.start_turn(session, "after restart")
    assert first.connection_generation == 2

    second = CountingTransport()
    adapter.attach_transport(second)
    await adapter.start_turn(session, "after replacement")

    assert len(first.turns) == 2
    assert first.resumes == 2
    assert len(second.turns) == 1
    assert second.resumes == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "binding_update",
    [{"project_id": "C:/other"}, {"goal_id": "different-goal"}],
)
async def test_codex_revalidates_canonical_binding_after_awaited_resume(binding_update):
    resume_started = asyncio.Event()
    release_resume = asyncio.Event()

    class PausedResumeTransport(CodexAppServerTransport):
        async def request(self, method, params=None):
            if method == "thread/resume":
                resume_started.set()
                await release_resume.wait()
            return await super().request(method, params)

    transport = PausedResumeTransport()
    adapter = CodexAdapter(transport)
    session = (await adapter.discover_sessions())[0]
    delivery = asyncio.create_task(adapter.start_turn(session, "must not deliver"))
    await resume_started.wait()
    with pytest.raises(RuntimeError, match="during a delivery"):
        adapter.attach_transport(CodexAppServerTransport())
    adapter.sessions[session.id] = session.model_copy(update=binding_update)
    release_resume.set()

    with pytest.raises(DeliveryUncertainError, match="changed while.*resuming"):
        await delivery
    assert transport.turns == []


@pytest.mark.asyncio
@pytest.mark.parametrize("resume_error", [RuntimeError("rejected"), TimeoutError()])
async def test_codex_resume_failure_never_starts_turn(resume_error):
    class FailedResumeTransport(CodexAppServerTransport):
        async def request(self, method, params=None):
            if method == "thread/resume":
                raise resume_error
            return await super().request(method, params)

    transport = FailedResumeTransport()
    adapter = CodexAdapter(transport)
    session = (await adapter.discover_sessions())[0]

    with pytest.raises(type(resume_error)):
        await adapter.start_turn(session, "must not deliver")
    assert transport.turns == []


@pytest.mark.asyncio
async def test_codex_uncertain_turn_start_is_never_retried():
    class UncertainTurnTransport(CodexAppServerTransport):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        async def request(self, method, params=None):
            if method == "turn/start":
                self.attempts += 1
                raise DeliveryUncertainError("receipt lost")
            return await super().request(method, params)

    transport = UncertainTurnTransport()
    adapter = CodexAdapter(transport)
    session = (await adapter.discover_sessions())[0]

    with pytest.raises(DeliveryUncertainError, match="receipt lost"):
        await adapter.start_turn(session, "one attempt only")
    assert transport.attempts == 1


@pytest.mark.asyncio
async def test_codex_isolated_thread_rejects_unsafe_paths_and_malformed_receipts(tmp_path):
    with pytest.raises(ValueError, match="absolute path"):
        await CodexAdapter().start_isolated_thread("relative/workspace")
    with pytest.raises(ValueError, match="filesystem root"):
        await CodexAdapter().start_isolated_thread(str(Path(tmp_path.anchor)))

    class MalformedThread(CodexAppServerTransport):
        async def request(self, method, params=None):
            if method == "thread/start":
                return {"thread": []}
            return await super().request(method, params)

    with pytest.raises(DeliveryUncertainError, match="malformed thread receipt"):
        await CodexAdapter(MalformedThread()).start_isolated_thread(str(tmp_path))


@pytest.mark.asyncio
async def test_synthetic_overlay_revert_is_not_a_fake_success():
    adapter = SyntheticAdapter()
    session = adapter.seed_session()
    overlay = Overlay(
        id="overlay-1",
        session_id=session.id,
        reason="test",
        diff=OverlayDiff(system_instructions="verify"),
    )
    assert await adapter.apply_overlay(session, overlay) is True
    assert await adapter.revert_overlay("missing") is False
    assert await adapter.revert_overlay(overlay.id) is True
    assert await adapter.revert_overlay(overlay.id) is False


def test_generic_hook_deadlines_and_explicit_harness_fragments():
    root = Path(__file__).resolve().parents[2]
    helper_path = root / "integrations" / "hooks" / "pex_hook.py"
    spec = importlib.util.spec_from_file_location("pex_deadline_hook_test", helper_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._client_timeout({"hook_event_name": "Stop"}) == 42.0
    assert module._client_timeout({"hook_event_name": "PreToolUse"}) == 7.0

    claude = json.loads(
        (root / "integrations" / "claude-hook" / "settings.fragment.json").read_text()
    )
    qwen = json.loads((root / "integrations" / "qwen-hook" / "settings.fragment.json").read_text())
    for event, rows in claude["hooks"].items():
        hook = rows[0]["hooks"][0]
        assert "--harness claude_code" in hook["command"]
        assert hook["timeout"] == (45 if event == "Stop" else 10)
    for event, rows in qwen["hooks"].items():
        hook = rows[0]["hooks"][0]
        assert "--harness qwen" in hook["command"]
        assert hook["timeout"] == (45_000 if event == "Stop" else 10_000)
