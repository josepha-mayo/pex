from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pex_bridge.pets as pet_module
import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.acp_client import FakeAcpTransport
from pex_bridge.adapters.acp_harness import HermesAdapter, KimiAdapter, OmpAdapter
from pex_bridge.adapters.claude_code import ClaudeCodeAdapter
from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport
from pex_bridge.adapters.codex_bin import resolve_codex_bin
from pex_bridge.adapters.cursor import CursorAdapter
from pex_bridge.adapters.cursor_bin import resolve_cursor_agent
from pex_bridge.adapters.devin import DevinAdapter
from pex_bridge.adapters.grok_build import GrokBuildAdapter
from pex_bridge.adapters.grok_build_bin import resolve_grok_build
from pex_bridge.adapters.hermes_bin import resolve_hermes
from pex_bridge.adapters.http_json import MemoryHttpTransport
from pex_bridge.adapters.opencode import OpenCodeAdapter
from pex_bridge.adapters.qwen import QwenAdapter
from pex_bridge.pets import (
    CODEX_CELL_H,
    CODEX_CELL_W,
    CODEX_ROWS_V2,
    STARTERS,
    PetSettings,
    catalog,
    codex_row_index,
    import_codex_pet,
    resolve_spritesheet,
)
from pex_bridge.pets.atlas import ATLAS_H, ATLAS_W, cached_bytes, render_atlas, write_atlas
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, EventType, PolicyVerdict
from pex_protocol.intervention import Intervention
from pex_protocol.overlay import Overlay, OverlayDiff


def test_desktop_detection_uses_running_apps():
    from pex_bridge.adapters.desktop import list_desktop_apps

    found = list_desktop_apps(
        {"Cursor.exe", "ChatGPT.exe", "OpenCode.exe", "Hermes.exe", "claude.exe", "Grok Bot.exe"}
    )
    by_name = {item["name"]: item for item in found}
    assert set(by_name) == {"cursor", "codex", "opencode", "hermes", "claude_code"}
    assert "grok_bot" not in by_name
    assert by_name["cursor"]["connect"] == "hooks"
    assert by_name["codex"]["connect"] == "observe-process"
    assert by_name["opencode"]["connect"] == "observe-process"
    assert by_name["hermes"]["connect"] == "observe-process"
    assert by_name["claude_code"]["connect"] == "hooks"
    assert all(item["kind"] == "desktop" for item in found)


async def test_discover_keeps_chatgpt_and_isolated_appserver_apart(monkeypatch):
    from pex_bridge.adapters.desktop import list_desktop_apps
    from pex_bridge.adapters.discover import probe_local_harnesses

    monkeypatch.setattr(
        "pex_bridge.adapters.discover.list_desktop_apps",
        lambda: list_desktop_apps({"ChatGPT.exe"}),
    )
    monkeypatch.setattr("pex_bridge.adapters.discover.PROBES", ())
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_codex_bin", lambda: "C:/codex.exe")
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_grok_build", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_hermes", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.shutil.which", lambda _name: None)

    found = await probe_local_harnesses()
    codex = [item for item in found if item["name"] == "codex"]
    assert len(codex) == 2
    by_kind = {item["kind"]: item for item in codex}
    assert by_kind["desktop"]["connect"] == "observe-process"
    assert (
        "ChatGPT.exe" in by_kind["desktop"]["surface"]
        or "observe" in by_kind["desktop"]["surface"].lower()
    )
    assert by_kind["stdio"]["connect"] == "app-server-stdio"
    assert "Not ChatGPT.exe" in by_kind["stdio"]["surface"]


def test_focus_maps_harness_to_desktop_process():
    from pex_bridge.adapters.winfocus import HARNESS_IMAGES

    assert HARNESS_IMAGES["cursor"] == ("Cursor.exe",)
    assert HARNESS_IMAGES["codex"] == ("ChatGPT.exe",)
    assert HARNESS_IMAGES["opencode"] == ("OpenCode.exe", "opencode.exe")
    assert HARNESS_IMAGES["hermes"] == ("Hermes.exe", "NousHermes.exe")
    assert HARNESS_IMAGES["claude_code"] == ("claude.exe",)


async def test_focus_ui_uses_process_images(monkeypatch):
    from pex_protocol.enums import HarnessType, SessionStatus
    from pex_protocol.session import HarnessSession

    seen: list[str] = []
    monkeypatch.setattr(
        "pex_bridge.adapters.winfocus.focus_image", lambda name: seen.append(name) or True
    )
    cursor_session = HarnessSession(
        id="cursor:live",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="live",
        status=SessionStatus.WORKING,
    )
    cursor = CursorAdapter()
    cursor.sessions[cursor_session.id] = cursor_session
    assert await cursor.focus_ui(cursor_session) is True
    assert seen == ["Cursor.exe"]
    codex_session = HarnessSession(
        id="codex:live",
        harness_type=HarnessType.CODEX,
        vendor_session_id="live",
        status=SessionStatus.WORKING,
    )
    codex = CodexAdapter()
    codex.sessions[codex_session.id] = codex_session
    assert await codex.focus_ui(codex_session) is True
    assert seen[-1] == "ChatGPT.exe"


def test_connect_table_keeps_bot_and_build_apart():
    from pex_bridge.adapters.connect import CONNECT

    assert CONNECT["grok_bot"]["method"] == "observe-process"
    assert CONNECT["grok_build"]["command"] == ["grok", "agent", "stdio"]
    assert CONNECT["cursor"]["method"] == "hooks"
    assert CONNECT["codex"]["method"] == "app-server-stdio"
    assert (
        "Not Grok Bot" in CONNECT["grok_build"]["note"]
        or "not Grok Bot" in CONNECT["grok_build"]["note"]
    )


async def test_grok_bot_observes_desktop_process(monkeypatch):
    from pex_bridge.adapters.grok_bot import GrokBotAdapter

    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"Grok Bot.exe"},
    )
    adapter = GrokBotAdapter()
    sessions = await adapter.discover_sessions()
    assert sessions[0].id == "grok_bot:desktop"
    assert (await adapter.probe()).support_label.value == "observe_only"


def test_required_harnesses_are_registered():
    registry = AdapterRegistry()
    names = {adapter.name for adapter in registry.all()}
    for required in AdapterRegistry.REQUIRED_HARNESSES:
        assert required in names


async def test_each_adapter_probes_honestly():
    registry = AdapterRegistry()
    for adapter in registry.all():
        caps = await adapter.probe()
        assert caps.support_label.value in {
            "deep",
            "strong",
            "basic",
            "observe_only",
            "experimental",
            "unavailable",
        }
        assert caps.notes


async def test_codex_appserver_turn_and_approval():
    transport = CodexAppServerTransport()
    adapter = CodexAdapter(transport)
    caps = await adapter.probe()
    assert caps.support_label.value == "basic"
    sessions = await adapter.discover_sessions()
    assert transport.initialized
    assert sessions

    async def ingest(*_):
        return None

    pump = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(20):
            if (await adapter.probe()).support_label.value == "deep":
                break
            await asyncio.sleep(0.01)
        assert (await adapter.probe()).support_label.value == "deep"
        ok = await adapter.send_message(sessions[0], "PEX: run the hidden tests.")
        assert ok
        assert transport.turns
        transport.pending_approvals["req-1"] = {
            "id": "req-1",
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": sessions[0].vendor_session_id},
        }
        assert await adapter.respond_permission(sessions[0], "req-1", "allow") is False
        assert await adapter.respond_permission(sessions[0], "req-1", "deny")
        assert transport.approvals[0]["decision"] == "deny"
    finally:
        pump.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pump


async def test_codex_pump_ingests_stop_permission_and_agent_message():
    from pex_protocol.enums import EventType

    transport = CodexAppServerTransport()
    transport.threads = [{"id": "thr_pump", "preview": "pump thread", "cwd": "C:/proj"}]
    adapter = CodexAdapter(transport)
    ingested: list = []

    async def ingest(event, session):
        ingested.append((event, session))

    transport.pending_approvals["req_pump"] = {
        "id": "req_pump",
        "method": "item/commandExecution/requestApproval",
        "params": {"threadId": "thr_pump", "command": "pytest", "cwd": "C:/proj"},
    }
    transport.notifications.append(
        {
            "method": "item/completed",
            "params": {
                "threadId": "thr_pump",
                "cwd": "C:/proj",
                "item": {"id": "item_msg", "type": "agentMessage", "text": "working on it"},
            },
        }
    )
    transport.notifications.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": "thr_pump",
                "cwd": "C:/proj",
                "turn": {"id": "t_pump", "status": "completed", "items": []},
            },
        }
    )

    task = adapter.start_pipeline_pump(ingest)
    try:
        wanted = {
            EventType.PERMISSION_REQUEST.value,
            EventType.AGENT_RESPONSE.value,
            EventType.STOP.value,
        }
        for _ in range(40):
            types = {event.event_type.value for event, _ in ingested}
            if wanted <= types:
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    types = {event.event_type.value for event, _ in ingested}
    assert EventType.PERMISSION_REQUEST.value in types
    assert EventType.AGENT_RESPONSE.value in types
    assert EventType.STOP.value in types
    session = adapter.sessions.get("codex:thr_pump")
    assert session is not None
    assert session.cwd == "C:/proj"


async def test_codex_pump_does_not_ingest_chatgpt_desktop_thread_ids(monkeypatch):
    from pex_protocol.enums import EventType

    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"ChatGPT.exe"},
    )
    transport = CodexAppServerTransport()
    transport.threads = []
    adapter = CodexAdapter(transport)
    ingested: list = []

    async def ingest(event, session):
        ingested.append((event.session_id, event.event_type.value))

    transport.notifications.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": "desktop",
                "turn": {"id": "t_desktop", "status": "completed", "items": []},
            },
        }
    )
    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(20):
            if ingested:
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    assert "codex:desktop" in adapter.sessions
    assert ingested == []
    assert EventType.STOP.value not in {row[1] for row in ingested}


async def test_codex_unavailable_without_transport(monkeypatch):
    monkeypatch.setattr("pex_bridge.adapters.codex.chatgpt_desktop_running", lambda: False)
    caps = await CodexAdapter().probe()
    assert caps.support_label.value == "unavailable"


async def test_chatgpt_exe_is_observe_only(monkeypatch):
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"ChatGPT.exe"},
    )
    adapter = CodexAdapter()
    caps = await adapter.probe()
    assert caps.support_label.value == "observe_only"
    assert caps.send_message is False
    sessions = await adapter.discover_sessions()
    assert sessions[0].id == "codex:desktop"
    assert sessions[0].metadata["process"] == "ChatGPT.exe"
    assert await adapter.send_message(sessions[0], "keep going") is False


def test_resolve_codex_bin_respects_env(tmp_path, monkeypatch):
    fake = tmp_path / "codex.exe"
    fake.write_text("x", encoding="utf-8")
    monkeypatch.setenv("PEX_CODEX_BIN", str(fake))
    assert resolve_codex_bin() == str(fake)


@pytest.mark.parametrize(
    ("env_name", "resolver", "fallback_name"),
    [
        ("PEX_CODEX_BIN", resolve_codex_bin, "codex.exe"),
        ("PEX_GROK_BUILD", resolve_grok_build, "grok.exe"),
        ("PEX_HERMES", resolve_hermes, "hermes.exe"),
    ],
)
def test_explicit_invalid_harness_binary_never_falls_back_to_path(
    tmp_path, monkeypatch, env_name, resolver, fallback_name
):
    fallback = tmp_path / fallback_name
    fallback.write_text("different install", encoding="utf-8")
    monkeypatch.setenv(env_name, "relative-or-missing")
    monkeypatch.setattr("shutil.which", lambda _name: str(fallback))

    assert resolver() is None


async def test_cursor_binary_path_is_not_deep(monkeypatch):
    monkeypatch.setattr("pex_bridge.adapters.desktop.running_image_names", lambda: set())
    adapter = CursorAdapter()
    adapter._bin = "C:/not-an-attached-acp"
    caps = await adapter.probe()
    assert caps.support_label.value == "unavailable"
    assert caps.send_message is False


def test_cursor_hook_reads_completion_and_tool_alias():
    adapter = CursorAdapter()
    session = adapter.upsert_from_hook({"conversation_id": "live"})
    event = adapter.normalize_hook(
        {"hook_event_name": "afterAgentResponse", "completion": "Ran the hidden tests."},
        session,
    )
    assert event.message_delta == "Ran the hidden tests."
    shell = adapter.normalize_hook(
        {
            "hook_event_name": "beforeShellExecution",
            "tool": "Shell",
            "tool_input": {"cmd": "pytest -q"},
        },
        session,
    )
    assert shell.tool_name == "Shell"
    assert shell.command == "pytest -q"


def test_codex_approval_mapping():
    from pex_bridge.adapters.codex import approval_result

    assert approval_result("item/commandExecution/requestApproval", "allow") == {
        "decision": "accept"
    }
    assert approval_result("item/fileChange/requestApproval", "deny") == {"decision": "decline"}
    assert approval_result("execCommandApproval", "allow") == {"decision": "approved"}


async def test_codex_stdio_jsonl_fake_process(tmp_path):
    import sys

    from pex_bridge.adapters.codex import CodexAdapter, CodexStdioTransport

    script = tmp_path / "fake_appserver.py"
    script.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    msg = json.loads(line)\n"
        "    method = msg.get('method')\n"
        "    if method == 'initialize':\n"
        "        print(json.dumps({'id': msg['id'], 'result': {"
        "'userAgent': 'fake', 'codexHome': '/', 'platformFamily': 'test', "
        "'platformOs': 'test'}}), flush=True)\n"
        "    elif method == 'thread/list':\n"
        "        print(json.dumps({'id': msg['id'], 'result': {"
        "'data': [{'id': 'thr_jsonl', 'preview': 'fake', 'cwd': 'C:/proj'}]}}), flush=True)\n"
        "    elif method == 'turn/start':\n"
        "        print(json.dumps({'id': msg['id'], 'result': {'turn': "
        "{'id': 't1', 'status': 'inProgress'}}}), flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', 'id': 'note_1',"
        " 'params': {'threadId': 'thr_jsonl', 'turn': {'id': 't1', "
        "'status': 'completed', 'items': []}}}), flush=True)\n"
        "        print(json.dumps({'id': 'appr_1', "
        "'method': 'item/commandExecution/requestApproval',"
        " 'params': {'command': 'pytest', 'threadId': 'thr_jsonl'}}), flush=True)\n",
        encoding="utf-8",
    )
    transport = CodexStdioTransport([sys.executable, "-u", str(script)])
    adapter = CodexAdapter(transport)
    pump = None
    try:
        caps = await adapter.probe()
        assert caps.support_label.value == "basic"
        sessions = await adapter.discover_sessions()
        assert sessions[0].vendor_session_id == "thr_jsonl"

        ingested_types: list[EventType] = []

        async def ingest(event, _session):
            ingested_types.append(event.event_type)

        pump = adapter.start_pipeline_pump(ingest)
        for _ in range(20):
            if (await adapter.probe()).support_label.value == "deep":
                break
            await asyncio.sleep(0.01)
        assert (await adapter.probe()).support_label.value == "deep"
        assert await adapter.send_message(sessions[0], "PEX: continue")
        for _ in range(40):
            if transport.pending_approvals and EventType.STOP in ingested_types:
                break
            await asyncio.sleep(0.05)
        assert EventType.STOP in ingested_types
        assert transport.notifications == []
        assert "appr_1" in transport.pending_approvals
        assert await adapter.respond_permission(sessions[0], "appr_1", "allow") is False
        assert await adapter.respond_permission(sessions[0], "appr_1", "deny")
        assert transport.approvals[0]["result"]["decision"] == "decline"
    finally:
        if pump is not None:
            pump.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pump
        await transport.close()


async def test_opencode_deep_only_with_transport_and_event_pump():
    cold = OpenCodeAdapter()
    assert (await cold.probe()).support_label.value == "unavailable"
    transport = MemoryHttpTransport()
    adapter = OpenCodeAdapter(transport)
    assert (await adapter.probe()).support_label.value == "strong"
    sessions = await adapter.discover_sessions()
    assert sessions
    assert await adapter.send_message(sessions[0], "PEX: continue with evidence.")
    assert transport.prompts
    adapter.normalize_sse(
        sessions[0],
        {
            "type": "permission.updated",
            "properties": {"id": "perm_1", "sessionID": sessions[0].vendor_session_id},
        },
    )
    assert await adapter.respond_permission(sessions[0], "perm_1", "allow")
    assert transport.permissions[-1]["body"] == {"response": "once"}
    overlay = Overlay(
        id="ovl_1",
        session_id=sessions[0].id,
        reason="tighten permissions",
        diff=OverlayDiff(system_instructions="Verify the requested artifact before stopping."),
    )
    adapter.mark_plugin_heartbeat(sessions[0].id)
    assert await adapter.apply_overlay(sessions[0], overlay)
    caps = await adapter.probe()
    assert caps.modify_config is True
    assert caps.config_scope == "session"
    assert transport.config_patches == []
    assert await adapter.revert_overlay(overlay.id, overlay.rollback)
    sse = adapter.normalize_sse(
        sessions[0],
        {
            "type": "session.idle",
            "text": "idle",
            "properties": {"sessionID": sessions[0].vendor_session_id},
            "directory": sessions[0].cwd,
        },
    )
    assert sse.event_type.value == "stop"

    async def ingest(*_):
        return None

    task = adapter.start_pipeline_pump(ingest)
    try:
        for _ in range(50):
            caps = await adapter.probe()
            if caps.support_label.value == "deep":
                break
            await asyncio.sleep(0.01)
        assert caps.support_label.value == "deep"
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def test_qwen_strong_until_sse_pump():
    assert (await QwenAdapter().probe()).support_label.value == "unavailable"
    transport = MemoryHttpTransport()
    adapter = QwenAdapter(transport)
    assert (await adapter.probe()).support_label.value == "basic"
    sessions = await adapter.discover_sessions()
    ingested: list = []

    async def ingest(event, session):
        ingested.append((event, session))

    transport.events.extend(
        [
            {
                "id": 1,
                "v": 1,
                "type": "permission_request",
                "data": {
                    "requestId": "permission-qwen-1",
                    "sessionId": "sess_demo",
                    "options": [
                        {"optionId": "proceed_once", "name": "Proceed once"},
                        {"optionId": "reject", "name": "Reject"},
                    ],
                },
            },
            {
                "id": 2,
                "v": 1,
                "type": "turn_complete",
                "data": {
                    "sessionId": "sess_demo",
                    "promptId": "prompt-1",
                    "stopReason": "end_turn",
                },
            },
        ]
    )
    task = adapter.start_pipeline_pump(ingest)
    for _ in range(40):
        if (await adapter.probe()).support_label.value == "strong" and ingested:
            break
        await asyncio.sleep(0.05)
    assert (await adapter.probe()).support_label.value == "strong"
    assert await adapter.send_message(sessions[0], "PEX context bundle")
    prompt_call = next(call for call in transport.calls if "/prompt" in call[1])
    assert prompt_call[2] == {"prompt": [{"type": "text", "text": "PEX context bundle"}]}
    assert ingested
    assert [event.event_type.value for event, _ in ingested] == ["permission_request", "stop"]
    assert await adapter.respond_permission(sessions[0], "permission-qwen-1", "allow")
    permission_call = next(call for call in transport.calls if "/permission/" in call[1])
    assert permission_call[1] == "/permission/permission-qwen-1"
    assert permission_call[2] == {"outcome": {"outcome": "selected", "optionId": "proceed_once"}}
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


class _FailPrompt(MemoryHttpTransport):
    async def request(self, method: str, path: str, *, json=None):
        if "prompt" in path:
            raise RuntimeError("daemon down")
        return await super().request(method, path, json=json)


async def test_qwen_send_fails_honestly():
    adapter = QwenAdapter(_FailPrompt())
    sessions = await adapter.discover_sessions()
    assert await adapter.send_message(sessions[0], "PEX context bundle") is False
    assert adapter.inbox.get(sessions[0].id, []) == []


async def test_devin_stays_basic_when_attached():
    assert (await DevinAdapter().probe()).support_label.value == "unavailable"
    transport = MemoryHttpTransport()
    transport.sessions = [
        {"id": "sess_demo", "project_id": "project-1", "status": "running"}
    ]
    adapter = DevinAdapter(transport)
    caps = await adapter.probe()
    assert caps.support_label.value == "basic"
    sessions = await adapter.discover_sessions()
    assert sessions
    assert await adapter.send_message(sessions[0], "PEX: the schema is already decided.")
    assert any("/messages" in call[1] for call in transport.calls)


class _FailDevin(MemoryHttpTransport):
    async def request(self, method: str, path: str, *, json=None):
        if path.endswith("/messages") and method.upper() == "POST":
            raise RuntimeError("devin api down")
        return await super().request(method, path, json=json)


async def test_devin_send_fails_honestly():
    adapter = DevinAdapter(_FailDevin())
    sessions = await adapter.discover_sessions()
    assert await adapter.send_message(sessions[0], "keep going") is False
    assert adapter.inbox.get(sessions[0].id, []) == []


async def test_grok_build_deep_with_acp():
    adapter = GrokBuildAdapter()
    idle = await adapter.probe()
    assert idle.support_label.value == "unavailable"
    assert idle.send_message is False
    adapter.attach_acp(FakeAcpTransport())
    attached = await adapter.probe()
    assert attached.support_label.value == "basic"
    assert attached.send_message is False
    assert attached.observe_messages is False
    sessions = await adapter.discover_sessions()
    assert sessions
    assert await adapter.send_message(sessions[0], "PEX: stay on the eval pipeline.") is False

    async def ingest(*_):
        return None

    task = adapter.start_pipeline_pump(ingest)
    try:
        assert (await adapter.probe()).support_label.value == "strong"
        assert await adapter.send_message(sessions[0], "Stay on the eval pipeline.")
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def test_grok_build_send_fails_honestly():
    adapter = GrokBuildAdapter()
    with pytest.raises(RuntimeError, match="no installed HTTP hook surface"):
        adapter.ingest_hook({"id": "g1"})

    class Boom(FakeAcpTransport):
        async def request(self, method, params=None):
            if method == "session/prompt":
                raise RuntimeError("acp down")
            return await super().request(method, params)

        async def request_with_delivery(self, method, params, delivered):
            if method == "session/prompt":
                delivered.set_exception(RuntimeError("acp down before delivery"))
                raise RuntimeError("acp down")
            return await self.request(method, params)

    adapter.attach_acp(Boom())
    session = (await adapter.discover_sessions())[0]

    async def ingest(*_):
        return None

    task = adapter.start_pipeline_pump(ingest)
    try:
        assert await adapter.send_message(session, "hi") is False
        assert adapter.inbox.get(session.id, []) == []
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_acp_harness_fails_closed_if_handshake_fails():
    class DeadAcp:
        async def request(self, method, params=None):
            raise RuntimeError("no handshake")

        async def notify(self, method, params=None):
            return None

        async def close(self):
            return None

    adapter = HermesAdapter()
    adapter.attach_acp(DeadAcp())
    caps = await adapter.probe()
    assert caps.support_label.value == "unavailable"
    assert caps.send_message is False


def test_grok_build_bin_is_not_cursor(monkeypatch, tmp_path):
    grok = tmp_path / ".grok" / "bin" / "grok.exe"
    grok.parent.mkdir(parents=True)
    grok.write_text("fake")
    monkeypatch.setenv("PEX_GROK_BUILD", str(grok))
    monkeypatch.delenv("PEX_CURSOR_AGENT", raising=False)
    resolved = resolve_grok_build()
    assert resolved == str(grok)
    cursor = resolve_cursor_agent()
    assert cursor is None or ".grok" not in cursor.lower()


async def test_kimi_hermes_omp_deep_with_acp():
    async def ingest(*_):
        return None

    for cls in (KimiAdapter, HermesAdapter, OmpAdapter):
        adapter = cls()
        assert (await adapter.probe()).support_label.value == "unavailable"
        adapter.attach_acp(FakeAcpTransport())
        assert (await adapter.probe()).support_label.value == "basic"
        sessions = await adapter.discover_sessions()
        assert sessions
        assert await adapter.send_message(sessions[0], "PEX: keep the goal.") is False
        task = adapter.start_pipeline_pump(ingest)
        try:
            assert (await adapter.probe()).support_label.value == "strong"
            assert await adapter.send_message(sessions[0], "Keep the goal.")
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def test_omp_acp_pump_uses_prompt_result_for_stop():
    transport = FakeAcpTransport()
    transport.sessions = [{"sessionId": "omp-pump", "cwd": "C:/proj"}]
    adapter = OmpAdapter()
    adapter.attach_acp(transport)
    session = (await adapter.discover_sessions())[0]
    ingested: list = []

    async def ingest(event, sess):
        ingested.append((event, sess))

    transport.events.append(
        {
            "method": "session/update",
            "params": {
                "sessionId": "omp-pump",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "I am done."},
                },
            },
        }
    )
    transport.events.append(
        {
            "method": "session/update",
            "params": {
                "sessionId": "omp-pump",
                "update": {
                    "sessionUpdate": "state_update",
                    "state": "idle",
                    "stopReason": "end_turn",
                },
            },
        }
    )
    task = adapter.start_pipeline_pump(ingest)
    try:
        assert await adapter.send_message(session, "Finish the report.")
        for _ in range(40):
            types = {event.event_type.value for event, _ in ingested}
            if EventType.AGENT_RESPONSE.value in types and EventType.STOP.value in types:
                break
            await asyncio.sleep(0.05)
        types = {event.event_type.value for event, _ in ingested}
        assert EventType.STOP.value in types
        assert EventType.AGENT_RESPONSE.value in types
        state_updates = [
            event
            for event, _ in ingested
            if event.metadata.get("session_update") == "state_update"
        ]
        assert state_updates and state_updates[0].event_type == EventType.STATUS
        assert all(sess.id == session.id for _, sess in ingested)
        notes = (await adapter.probe()).notes
        assert "pump is running" in notes
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def test_pi_stays_basic_without_control_api():
    registry = AdapterRegistry()
    adapter = registry.get("pi")
    assert adapter is not None
    cold = await adapter.probe()
    assert cold.support_label.value == "unavailable"
    with pytest.raises(RuntimeError, match="no verified hook integration"):
        adapter.ingest_hook({"session_id": "pi-1"})
    caps = await adapter.probe()
    assert caps.support_label.value == "unavailable"
    assert caps.send_message is False


def test_claude_pretool_hook_contract():
    adapter = ClaudeCodeAdapter()
    session = adapter.ingest_hook(
        {"session_id": "c1", "hook_event_name": "PreToolUse", "tool_name": "Bash"}
    )
    event = adapter.normalize_hook({"hook_event_name": "PreToolUse", "tool_name": "Bash"}, session)
    assert event.event_type.value == "tool_call"
    response = adapter.hook_response(session, {"hook_event_name": "PreToolUse"}, None)
    assert response == {}


def _claude_text_intervention(
    session_id: str,
    *,
    hook: str,
    action_type: InterventionType,
    text: str,
    verdict: PolicyVerdict = PolicyVerdict.ALLOW,
) -> Intervention:
    trigger = EventType.USER_PROMPT if hook == "UserPromptSubmit" else EventType.COMPACTION
    action = ProposedAction(
        type=action_type,
        session_id=session_id,
        payload={"text": text},
        rationale="Ledger-grounded context.",
        evidence=["goal:eval"],
        risk=RiskLevel.LOW,
        authority_required=Authority.LOCAL_POLICY,
    )
    return Intervention(
        id="int-claude-text",
        session_id=session_id,
        trigger=trigger.value,
        evidence=list(action.evidence),
        diagnosis="Ledger-grounded context.",
        proposed_action=action,
        risk=RiskLevel.LOW.value,
        authority_required=Authority.LOCAL_POLICY.value,
        action_taken=action_type.value,
        policy_verdict=verdict,
        result="sent" if verdict == PolicyVerdict.ALLOW else "awaiting_human",
        created_at=datetime.now(UTC),
    )


def test_claude_user_prompt_submit_annotates_with_additional_context():
    adapter = ClaudeCodeAdapter()
    payload = {
        "session_id": "c-prompt",
        "hook_event_name": "UserPromptSubmit",
        "prompt": "just quickly hack it",
    }
    session = adapter.ingest_hook(payload)
    adapter.normalize_hook(payload, session)
    intervention = _claude_text_intervention(
        session.id,
        hook="UserPromptSubmit",
        action_type=InterventionType.ANNOTATE,
        text="Interpret this as work on Eval, not a shortcut.",
    )
    assert adapter.hook_response(session, payload, intervention) == {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "Interpret this as work on Eval, not a shortcut.",
        }
    }


def test_claude_user_prompt_submit_ask_human_does_not_reject_submitted_prompt():
    adapter = ClaudeCodeAdapter()
    payload = {"session_id": "c-ask", "hook_event_name": "UserPromptSubmit"}
    session = adapter.ingest_hook(payload)
    adapter.normalize_hook(payload, session)
    intervention = _claude_text_intervention(
        session.id,
        hook="UserPromptSubmit",
        action_type=InterventionType.ASK_HUMAN,
        text="Conflicts with a persistent constraint.",
        verdict=PolicyVerdict.ASK_HUMAN,
    )
    assert adapter.hook_response(session, payload, intervention) == {}


def test_claude_precompact_allow_nudge_becomes_additional_context():
    adapter = ClaudeCodeAdapter()
    payload = {"session_id": "c-compact", "hook_event_name": "PreCompact"}
    session = adapter.ingest_hook(payload)
    adapter.normalize_hook(payload, session)
    intervention = _claude_text_intervention(
        session.id,
        hook="PreCompact",
        action_type=InterventionType.SEND_NUDGE,
        text="Keep the attached Eval title, acceptance, and report.txt in working memory.",
    )
    assert adapter.hook_response(session, payload, intervention) == {
        "hookSpecificOutput": {
            "hookEventName": "PreCompact",
            "additionalContext": (
                "Keep the attached Eval title, acceptance, and report.txt in working memory."
            ),
        }
    }


def test_claude_precompact_pex_prefix_and_denied_nudges_are_not_injected():
    adapter = ClaudeCodeAdapter()
    payload = {"session_id": "c-compact-deny", "hook_event_name": "PreCompact"}
    session = adapter.ingest_hook(payload)
    adapter.normalize_hook(payload, session)
    prefixed = _claude_text_intervention(
        session.id,
        hook="PreCompact",
        action_type=InterventionType.SEND_NUDGE,
        text="PEX: remember the goal",
    )
    assert adapter.hook_response(session, payload, prefixed) == {}
    adapter.normalize_hook(payload, session)
    denied = _claude_text_intervention(
        session.id,
        hook="PreCompact",
        action_type=InterventionType.SEND_NUDGE,
        text="Keep Eval in working memory.",
        verdict=PolicyVerdict.DENY,
    )
    assert adapter.hook_response(session, payload, denied) == {}


def test_claude_permission_hooks_ignore_incomplete_intervention_records():
    from types import SimpleNamespace

    adapter = ClaudeCodeAdapter()
    session = adapter.ingest_hook(
        {"session_id": "c-permission", "hook_event_name": "PermissionRequest"}
    )
    assert (
        adapter.hook_response(
            session,
            {"hook_event_name": "PermissionRequest"},
            None,
        )
        == {}
    )
    ask = SimpleNamespace(policy_verdict=PolicyVerdict.ASK_HUMAN)
    assert (
        adapter.hook_response(
            session,
            {"hook_event_name": "PermissionRequest"},
            ask,
        )
        == {}
    )
    allow = SimpleNamespace(policy_verdict=PolicyVerdict.ALLOW)
    assert (
        adapter.hook_response(
            session,
            {"hook_event_name": "PermissionRequest"},
            allow,
        )
        == {}
    )


async def test_hermes_plugin_hooks_use_official_returns():
    adapter = HermesAdapter()
    session = adapter.ingest_hook({"session_id": "h1", "cwd": "C:/proj"})
    end = adapter.normalize_hook(
        {"hook_event_name": "on_session_end", "text": "I am done."},
        session,
    )
    assert end.event_type.value == "stop"
    assert adapter.hook_response(session, {"hook_event_name": "on_session_end"}, None) == {}
    caps = await adapter.probe()
    assert caps.support_label.value == "basic"
    assert caps.send_message is False
    assert caps.approve is False
    assert caps.deny is False
    assert await adapter.send_message(session, "Create report.txt with shipped.") is False
    injected = adapter.hook_response(session, {"hook_event_name": "pre_llm_call"}, None)
    assert injected == {}
    permission_payload = {"hook_event_name": "pre_tool_call", "tool_name": "terminal"}
    permission_event = adapter.normalize_hook(permission_payload, session)
    policy_rejection = adapter.hook_response(
        session,
        permission_payload,
        Intervention(
            id="int-policy-rejection",
            session_id=session.id,
            trigger=EventType.TOOL_CALL.value,
            evidence=["tool:terminal"],
            diagnosis="PEX action rejected by policy",
            proposed_action=ProposedAction(
                type=InterventionType.RESPOND_PERMISSION,
                session_id=session.id,
                payload={"request_id": permission_event.event_id, "decision": "deny"},
                rationale="Review terminal permission.",
                evidence=["tool:terminal"],
            ),
            risk=RiskLevel.LOW.value,
            authority_required=Authority.LOCAL_POLICY.value,
            action_taken=InterventionType.RESPOND_PERMISSION.value,
            policy_verdict=PolicyVerdict.DENY,
            result="denied_by_policy",
            created_at=datetime.now(UTC),
        ),
    )
    assert policy_rejection == {}
    permission_event = adapter.normalize_hook(permission_payload, session)
    deny_action = ProposedAction(
        type=InterventionType.RESPOND_PERMISSION,
        session_id=session.id,
        payload={"request_id": permission_event.event_id, "decision": "deny"},
        rationale="Deny exact active terminal permission.",
        evidence=["tool:terminal"],
    )
    blocked = adapter.hook_response(
        session,
        permission_payload,
        Intervention(
            id="int-explicit-deny",
            session_id=session.id,
            trigger=EventType.TOOL_CALL.value,
            evidence=list(deny_action.evidence),
            diagnosis="Explicit permission denial.",
            proposed_action=deny_action,
            risk=RiskLevel.LOW.value,
            authority_required=Authority.LOCAL_POLICY.value,
            action_taken=InterventionType.RESPOND_PERMISSION.value,
            policy_verdict=PolicyVerdict.ALLOW,
            result="permission_deny_inline",
            created_at=datetime.now(UTC),
        ),
    )
    assert blocked == {"action": "block", "message": "Explicit permission denial."}
    assert await adapter.send_message(session, "PEX: keep going") is False


def test_eight_starter_pets_and_codex_geometry():
    assert len(STARTERS) == 8
    assert {p.id for p in STARTERS} == {
        "pex",
        "ledger",
        "mesh",
        "nudge",
        "drift",
        "quiet",
        "ember",
        "von",
    }
    assert {p.species for p in STARTERS} == {
        "owl",
        "tortoise",
        "moth",
        "hedgehog",
        "axolotl",
        "armadillo",
        "robot",
        "cat",
    }
    assert CODEX_CELL_W * 8 == 1536
    assert CODEX_CELL_H * CODEX_ROWS_V2 == 2288
    assert ATLAS_W == 1536
    assert ATLAS_H == 2288
    assert codex_row_index("decision") == 6
    assert codex_row_index("working") == 7
    assert codex_row_index("approved") == 8


def test_atlas_renders_codex_v2_geometry():
    image = render_atlas(STARTERS[0])
    assert image.size == (1536, 2288)
    extrema = image.getextrema()
    assert extrema[-1][1] > 0


def test_cached_atlas_repairs_corrupt_cache_and_rejects_invalid_keys(tmp_path: Path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "pex_0.webp").write_bytes(b"not-a-webp")
    cached_bytes.cache_clear()

    data = cached_bytes("pex", 0, str(cache))

    from PIL import Image

    with Image.open(BytesIO(data)) as image:
        assert image.format == "WEBP"
        assert image.size == (1536, 2288)
        assert "A" in image.getbands()
    with pytest.raises(ValueError, match="unknown starter"):
        cached_bytes("../escape", 0, str(cache))
    with pytest.raises(ValueError, match="between -360 and 360"):
        cached_bytes("pex", 361, str(cache))


def test_all_eight_shipped_starter_atlases_pass_the_v2_file_contract():
    resolved = catalog(PetSettings())
    assert [pet.id for pet in resolved] == [
        "pex",
        "ledger",
        "mesh",
        "nudge",
        "drift",
        "quiet",
        "ember",
        "von",
    ]
    assert all(pet.atlas_ready and pet.spritesheet for pet in resolved)


def test_starter_spritesheets_are_not_gitignored_and_match_release_manifest():
    repo = Path(__file__).resolve().parents[2]
    pets_dir = repo / "apps" / "desktop" / "src" / "pets"
    manifest_path = pets_dir / "release-manifest.json"
    locked = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert locked["built_in_pet_ids"] == [pet.id for pet in STARTERS]
    by_id = {row["id"]: row for row in locked["pets"]}
    ignored: list[str] = []
    for pet in STARTERS:
        sheet = pets_dir / pet.id / "spritesheet.webp"
        pet_json = pets_dir / pet.id / "pet.json"
        assert sheet.is_file(), f"missing starter spritesheet {pet.id}"
        data = json.loads(pet_json.read_text(encoding="utf-8"))
        assert data["spriteVersionNumber"] == 2
        check = subprocess.run(
            ["git", "check-ignore", "-q", str(sheet)],
            cwd=repo,
            check=False,
        )
        if check.returncode == 0:
            ignored.append(pet.id)
        digest = hashlib.sha256(sheet.read_bytes()).hexdigest()
        assert digest == by_id[pet.id]["spritesheet_sha256"]
        manifest_digest = hashlib.sha256(pet_json.read_bytes()).hexdigest()
        assert manifest_digest == by_id[pet.id]["manifest_sha256"]
    assert ignored == []


def test_release_manifest_seals_current_exact_eight_playback_closure():
    repo = Path(__file__).resolve().parents[2]
    pets_dir = repo / "apps" / "desktop" / "src" / "pets"
    release = json.loads((pets_dir / "release-manifest.json").read_text(encoding="utf-8"))
    assert release["schema_version"] == 2
    assert release["built_in_pet_ids"] == [pet.id for pet in STARTERS]

    def assert_bound(binding: dict[str, object], *, base: Path = pets_dir) -> Path:
        path = base.joinpath(*str(binding["path"]).split("/"))
        data = path.read_bytes()
        assert path.is_file()
        assert len(data) == int(binding["bytes"])
        assert hashlib.sha256(data).hexdigest() == binding["sha256"]
        return path

    audit_path = assert_bound(release["fleet_audit"])
    playback_path = assert_bound(release["direct_playback"])
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["schema_version"] == 2
    assert audit["direct_playback"] == release["direct_playback"]
    assert [row["id"] for row in audit["pets"]] == release["built_in_pet_ids"]

    playback = json.loads(playback_path.read_text(encoding="utf-8"))
    current = playback_path.parent
    assert playback["verdict"] == "pass"
    assert playback["scope"]["pet_ids"] == release["built_in_pet_ids"]
    assert playback["scope"]["gif_count"] == 72
    runtime_path = assert_bound(playback["bindings"]["runtime_contract"], base=current)
    assert_bound(playback["bindings"]["prior_visual_qa"], base=current)
    assert_bound(playback["bindings"]["local_viewer"], base=current)
    screenshots = playback["screenshot_hashes"]
    assert len(screenshots) == len({row["path"] for row in screenshots}) == 25
    for screenshot in screenshots:
        path = current / screenshot["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == screenshot["sha256"]

    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    assert runtime["ok"] is True
    assert runtime["repair_requested"] is False
    assert [row["current_evidence"]["pet_id"] for row in runtime["results"]] == release[
        "built_in_pet_ids"
    ]
    preview_paths: set[str] = set()
    frame_paths: set[str] = set()
    for result in runtime["results"]:
        evidence = result["current_evidence"]
        previews = evidence["motion_previews"]
        assert len(previews) == 9
        for preview in previews:
            path = repo.joinpath(*preview["path"].split("/"))
            data = path.read_bytes()
            assert len(data) == preview["bytes"]
            assert hashlib.sha256(data).hexdigest() == preview["sha256"]
            preview_paths.add(preview["path"])
        manifest_binding = evidence["standard_frame_manifest"]
        manifest_path = repo.joinpath(*manifest_binding["path"].split("/"))
        manifest_data = manifest_path.read_bytes()
        assert len(manifest_data) == manifest_binding["bytes"]
        assert hashlib.sha256(manifest_data).hexdigest() == manifest_binding["sha256"]
        frame_manifest = json.loads(manifest_data)
        for row in frame_manifest["rows"]:
            for frame in row["frames"]:
                frame_path = repo.joinpath(*frame["path"].split("/"))
                assert hashlib.sha256(frame_path.read_bytes()).hexdigest() == frame["png_sha256"]
                frame_paths.add(frame["path"])
    assert len(preview_paths) == 72
    assert len(frame_paths) == 456


def test_release_preflight_is_structured_and_never_claims_package_readiness():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["node", "scripts/build-sidecar.mjs", "--preflight-release"],
        cwd=repo / "apps" / "desktop",
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode in {0, 2}, result.stderr
    report = json.loads(result.stdout)
    assert report["schema"] == "pex.release-preflight.v1"
    assert report["stage"] == "source"
    assert report["release_ready"] is False
    assert report["fleet"]["pet_ids"] == [pet.id for pet in STARTERS]
    assert report["fleet"]["playback_receipt"]["gif_count"] == 72
    assert report["fleet"]["playback_receipt"]["decoded_frame_count"] == 456
    assert report["git"]["release_input_count"] == 888
    assert report["git"]["audit_reachable_input_count"] == 672
    assert report["git"]["audit_closure_sha256"] == (
        "94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470"
    )
    assert "cursor_observe_sha256" in report["sidecars"]
    assert report["tauri"]["external_bin"] == [
        "binaries/pex-bridge",
        "binaries/pex-cursor-hook",
        "binaries/pex-cursor-observe",
    ]
    assert result.returncode == (0 if report["source_ready"] else 2)
    assert bool(report["blockers"]) is (not report["source_ready"])


def test_runtime_bundle_inventory_proves_exact_eight_resource_hashes():
    from pex_bridge.main import bundled_pet_inventory

    inventory = bundled_pet_inventory()
    assert inventory["version"] == 1
    pets = inventory["pets"]
    assert isinstance(pets, list)
    assert [pet["id"] for pet in pets] == [pet.id for pet in STARTERS]
    assert all(len(str(pet["manifest_sha256"])) == 64 for pet in pets)
    assert all(len(str(pet["spritesheet_sha256"])) == 64 for pet in pets)
    assert all(int(pet["spritesheet_bytes"]) > 0 for pet in pets)


def test_starter_resolution_never_falls_back_to_same_name_codex_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    home = tmp_path / "home"
    home_pet = home / ".codex" / "pets" / "pex"
    home_pet.mkdir(parents=True)
    write_atlas(STARTERS[0], home_pet / "spritesheet.webp")
    (home_pet / "pet.json").write_text(
        json.dumps({"id": "pex", "spriteVersionNumber": 2}),
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(pet_module, "_repo_pets_dir", lambda: tmp_path / "missing-bundle")

    assert resolve_spritesheet("pex") is None


def test_import_codex_pet_rejects_transparent_or_empty_required_frames(tmp_path: Path):
    from PIL import Image

    manifest = tmp_path / "pet.json"
    manifest.write_text(
        json.dumps({"id": "blank", "spriteVersionNumber": 2}),
        encoding="utf-8",
    )
    sheet = tmp_path / "spritesheet.webp"
    Image.new("RGBA", (1536, 2288), (0, 0, 0, 0)).save(sheet, "WEBP", lossless=True)
    with pytest.raises(ValueError, match="visible pixels"):
        import_codex_pet(tmp_path)

    atlas = render_atlas(STARTERS[0])
    atlas.paste((0, 0, 0, 0), (0, 0, CODEX_CELL_W, CODEX_CELL_H))
    atlas.save(sheet, "WEBP", lossless=True)
    with pytest.raises(ValueError, match=r"required frame idle\[0\]"):
        import_codex_pet(tmp_path)


def test_import_codex_pet_rejects_pixels_in_runtime_unused_cells(tmp_path: Path):
    manifest = tmp_path / "pet.json"
    manifest.write_text(
        json.dumps({"id": "occupied-unused", "spriteVersionNumber": 2}),
        encoding="utf-8",
    )
    sheet = tmp_path / "spritesheet.webp"
    atlas = render_atlas(STARTERS[0])
    atlas.paste(
        (255, 0, 0, 255),
        (
            6 * CODEX_CELL_W,
            0,
            7 * CODEX_CELL_W,
            CODEX_CELL_H,
        ),
    )
    atlas.save(sheet, "WEBP", lossless=True)

    with pytest.raises(ValueError, match=r"unused frame idle\[6\]"):
        import_codex_pet(tmp_path)


def test_import_codex_pet_contract(tmp_path: Path):
    sheet = tmp_path / "spritesheet.webp"
    write_atlas(STARTERS[-1], sheet)
    (tmp_path / "pet.json").write_text(
        json.dumps(
            {
                "id": "von-test",
                "displayName": "VonTest",
                "description": "Imported contract check",
                "spriteVersionNumber": 2,
                "spritesheetPath": "spritesheet.webp",
            }
        ),
        encoding="utf-8",
    )
    imported = import_codex_pet(tmp_path)
    assert imported.id == "import:von-test"
    assert imported.sprite_version == 2
    settings = PetSettings(imports=[imported], selected_id=imported.id)
    ids = {pet.id for pet in catalog(settings)}
    assert "import:von-test" in ids
    assert len(STARTERS) == 8

    sheet.unlink()
    stale = next(pet for pet in catalog(settings) if pet.id == "import:von-test")
    assert stale.atlas_ready is False
    assert stale.spritesheet is None


def test_import_codex_pet_rejects_spritesheet_path_escape(tmp_path: Path):
    pet_dir = tmp_path / "pet"
    pet_dir.mkdir()
    write_atlas(STARTERS[0], tmp_path / "outside.webp")
    (pet_dir / "pet.json").write_text(
        json.dumps(
            {
                "id": "escape",
                "spriteVersionNumber": 2,
                "spritesheetPath": "../outside.webp",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="inside the pet directory"):
        import_codex_pet(pet_dir)


def test_import_codex_pet_rejects_wrong_atlas_geometry(tmp_path: Path):
    from PIL import Image

    Image.new("RGBA", (192, 208), (0, 0, 0, 0)).save(
        tmp_path / "spritesheet.webp", "WEBP", lossless=True
    )
    (tmp_path / "pet.json").write_text(
        json.dumps({"id": "tiny", "spriteVersionNumber": 2}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="1536x2288"):
        import_codex_pet(tmp_path)


def test_import_codex_pet_rejects_invalid_or_unbounded_manifest(tmp_path: Path):
    (tmp_path / "pet.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="contain an object"):
        import_codex_pet(tmp_path)

    (tmp_path / "pet.json").write_bytes(b"{" + b"x" * 65_536)
    with pytest.raises(ValueError, match="64 KiB"):
        import_codex_pet(tmp_path)

    for payload in (
        '{"id":"first","id":"second","spriteVersionNumber":2}',
        '{"id":"invalid","spriteVersionNumber":NaN}',
    ):
        (tmp_path / "pet.json").write_text(payload, encoding="utf-8")
        with pytest.raises(ValueError, match="valid UTF-8 JSON"):
            import_codex_pet(tmp_path)


def test_import_codex_pet_rejects_non_integer_version_and_opaque_atlas(tmp_path: Path):
    (tmp_path / "pet.json").write_text(
        json.dumps({"id": "bad-version", "spriteVersionNumber": {"nested": 2}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="integer 2"):
        import_codex_pet(tmp_path)

    from PIL import Image

    Image.new("RGB", (1536, 2288), (1, 2, 3)).save(
        tmp_path / "spritesheet.webp", "WEBP", lossless=True
    )
    (tmp_path / "pet.json").write_text(
        json.dumps({"id": "opaque", "spriteVersionNumber": 2}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="alpha channel"):
        import_codex_pet(tmp_path)

    Image.new("RGBA", (1536, 2288), (1, 2, 3, 255)).save(
        tmp_path / "spritesheet.webp", "WEBP", lossless=True
    )
    with pytest.raises(ValueError, match="alpha channel|transparent background"):
        import_codex_pet(tmp_path)
