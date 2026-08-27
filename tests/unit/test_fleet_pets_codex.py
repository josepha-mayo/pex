from __future__ import annotations

import asyncio
import json
from pathlib import Path

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.acp_client import FakeAcpTransport
from pex_bridge.adapters.acp_harness import KimiAdapter, HermesAdapter, OmpAdapter
from pex_bridge.adapters.claude_code import ClaudeCodeAdapter
from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport
from pex_bridge.adapters.codex_bin import resolve_codex_bin
from pex_bridge.adapters.cursor import CursorAdapter
from pex_bridge.adapters.cursor_bin import resolve_cursor_agent
from pex_bridge.adapters.devin import DevinAdapter
from pex_bridge.adapters.grok_build import GrokBuildAdapter
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
)
from pex_bridge.pets.atlas import ATLAS_H, ATLAS_W, render_atlas, write_atlas
from pex_protocol.overlay import Overlay, OverlayDiff
from pex_protocol.enums import EventType


def test_desktop_detection_uses_running_apps():
    from pex_bridge.adapters.desktop import list_desktop_apps

    found = list_desktop_apps({"Cursor.exe", "ChatGPT.exe", "Grok Bot.exe"})
    by_name = {item["name"]: item for item in found}
    assert set(by_name) == {"cursor", "codex", "grok_bot"}
    assert by_name["cursor"]["connect"] == "hooks"
    assert by_name["codex"]["connect"] == "observe-process"
    assert by_name["grok_bot"]["connect"] == "observe-process"
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
    assert "ChatGPT.exe" in by_kind["desktop"]["surface"] or "observe" in by_kind["desktop"]["surface"].lower()
    assert by_kind["stdio"]["connect"] == "app-server-stdio"
    assert "Not ChatGPT.exe" in by_kind["stdio"]["surface"]


def test_focus_maps_harness_to_desktop_process():
    from pex_bridge.adapters.winfocus import HARNESS_IMAGES

    assert HARNESS_IMAGES["cursor"] == "Cursor.exe"
    assert HARNESS_IMAGES["codex"] == "ChatGPT.exe"
    assert HARNESS_IMAGES["grok_bot"] == "Grok Bot.exe"


async def test_focus_ui_uses_process_images(monkeypatch):
    from pex_protocol.enums import HarnessType, SessionStatus
    from pex_protocol.session import HarnessSession

    seen: list[str] = []
    monkeypatch.setattr("pex_bridge.adapters.winfocus.focus_image", lambda name: seen.append(name) or True)
    session = HarnessSession(
        id="cursor:live",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="live",
        status=SessionStatus.WORKING,
    )
    assert await CursorAdapter().focus_ui(session) is True
    assert seen == ["Cursor.exe"]
    assert await CodexAdapter().focus_ui(session) is True
    assert seen[-1] == "ChatGPT.exe"


def test_connect_table_keeps_bot_and_build_apart():
    from pex_bridge.adapters.connect import CONNECT

    assert CONNECT["grok_bot"]["method"] == "observe-process"
    assert CONNECT["grok_build"]["command"] == ["grok", "agent", "stdio"]
    assert CONNECT["cursor"]["method"] == "hooks"
    assert CONNECT["codex"]["method"] == "app-server-stdio"
    assert "Not Grok Bot" in CONNECT["grok_build"]["note"] or "not Grok Bot" in CONNECT["grok_build"]["note"]


async def test_grok_bot_observes_desktop_process(monkeypatch):
    from pex_bridge.adapters.grok_bot import GrokBotAdapter

    monkeypatch.setattr(
        "pex_bridge.adapters.grok_bot.running_image_names",
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
    assert caps.support_label.value == "deep"
    sessions = await adapter.discover_sessions()
    assert transport.initialized
    assert sessions
    ok = await adapter.send_message(sessions[0], "PEX: run the hidden tests.")
    assert ok
    assert transport.turns
    await adapter.respond_permission(sessions[0], "req-1", "allow")
    assert transport.approvals[0]["decision"] == "allow"


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


async def test_codex_unavailable_without_transport(monkeypatch):
    monkeypatch.setattr("pex_bridge.adapters.codex.chatgpt_desktop_running", lambda: False)
    caps = await CodexAdapter().probe()
    assert caps.support_label.value == "unavailable"


async def test_chatgpt_exe_is_observe_only(monkeypatch):
    monkeypatch.setattr("pex_bridge.adapters.codex.chatgpt_desktop_running", lambda: True)
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


async def test_cursor_binary_path_is_not_deep():
    adapter = CursorAdapter()
    adapter._bin = "C:/not-an-attached-acp"
    caps = await adapter.probe()
    assert caps.support_label.value == "strong"


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

    assert approval_result("item/commandExecution/requestApproval", "allow") == {"decision": "accept"}
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
        "'userAgent': 'fake', 'codexHome': '/', 'platformFamily': 'test', 'platformOs': 'test'}}), flush=True)\n"
        "    elif method == 'thread/list':\n"
        "        print(json.dumps({'id': msg['id'], 'result': {"
        "'data': [{'id': 'thr_jsonl', 'preview': 'fake', 'cwd': 'C:/proj'}]}}), flush=True)\n"
        "    elif method == 'turn/start':\n"
        "        print(json.dumps({'id': msg['id'], 'result': {'turn': {'id': 't1', 'status': 'inProgress'}}}), flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', 'id': 'note_1',"
        " 'params': {'threadId': 'thr_jsonl', 'turn': {'id': 't1', 'status': 'completed', 'items': []}}}), flush=True)\n"
        "        print(json.dumps({'id': 'appr_1', 'method': 'item/commandExecution/requestApproval',"
        " 'params': {'command': 'pytest', 'threadId': 'thr_jsonl'}}), flush=True)\n",
        encoding="utf-8",
    )
    transport = CodexStdioTransport([sys.executable, "-u", str(script)])
    adapter = CodexAdapter(transport)
    try:
        caps = await adapter.probe()
        assert caps.support_label.value == "deep"
        sessions = await adapter.discover_sessions()
        assert sessions[0].vendor_session_id == "thr_jsonl"
        assert await adapter.send_message(sessions[0], "PEX: continue")
        for _ in range(40):
            if transport.pending_approvals and any(
                n.get("method") == "turn/completed" for n in transport.notifications
            ):
                break
            await asyncio.sleep(0.05)
        assert any(n.get("method") == "turn/completed" for n in transport.notifications)
        assert "appr_1" in transport.pending_approvals
        assert await adapter.respond_permission(sessions[0], "appr_1", "allow")
        assert transport.approvals[0]["result"]["decision"] == "accept"
    finally:
        await transport.close()


async def test_opencode_deep_only_with_transport():
    cold = OpenCodeAdapter()
    assert (await cold.probe()).support_label.value == "unavailable"
    transport = MemoryHttpTransport()
    adapter = OpenCodeAdapter(transport)
    assert (await adapter.probe()).support_label.value == "deep"
    sessions = await adapter.discover_sessions()
    assert sessions
    assert await adapter.send_message(sessions[0], "PEX: continue with evidence.")
    assert transport.prompts
    assert await adapter.respond_permission(sessions[0], "perm_1", "allow")
    overlay = Overlay(
        id="ovl_1",
        session_id=sessions[0].id,
        reason="tighten permissions",
        diff=OverlayDiff(permission_policy={"bash": "ask"}),
    )
    assert await adapter.apply_overlay(sessions[0], overlay)
    assert transport.config_patches
    sse = adapter.normalize_sse(sessions[0], {"type": "session.idle", "text": "idle"})
    assert sse.event_type.value == "stop"


async def test_qwen_strong_until_sse_pump():
    assert (await QwenAdapter().probe()).support_label.value == "unavailable"
    transport = MemoryHttpTransport()
    adapter = QwenAdapter(transport)
    assert (await adapter.probe()).support_label.value == "strong"
    sessions = await adapter.discover_sessions()
    assert await adapter.send_message(sessions[0], "PEX context bundle")
    assert any("/prompt" in call[1] for call in transport.calls)
    ingested: list = []

    async def ingest(event, session):
        ingested.append((event, session))

    transport.events.append({"type": "session.idle", "text": "idle", "sessionId": "sess_demo"})
    task = adapter.start_pipeline_pump(ingest)
    for _ in range(40):
        if ingested:
            break
        await asyncio.sleep(0.05)
    assert (await adapter.probe()).support_label.value == "deep"
    assert ingested
    assert ingested[0][0].event_type.value == "stop"
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
    assert idle.support_label.value == "strong"
    assert idle.send_message is False
    adapter.attach_acp(FakeAcpTransport())
    assert (await adapter.probe()).support_label.value == "deep"
    sessions = await adapter.discover_sessions()
    assert sessions
    assert await adapter.send_message(sessions[0], "PEX: stay on the eval pipeline.")


async def test_grok_build_send_fails_honestly():
    adapter = GrokBuildAdapter()
    session = adapter.ingest_hook({"id": "g1"})
    assert await adapter.send_message(session, "hi") is False

    class Boom:
        ready = True

        async def prompt(self, session_id, text):
            raise RuntimeError("acp down")

    adapter.acp = Boom()
    assert await adapter.send_message(session, "hi") is False


async def test_acp_harness_stays_strong_if_handshake_fails():
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
    assert caps.support_label.value == "strong"


def test_grok_build_bin_is_not_cursor(monkeypatch, tmp_path):
    grok = tmp_path / ".grok" / "bin" / "grok.exe"
    grok.parent.mkdir(parents=True)
    grok.write_text("fake")
    monkeypatch.setenv("PEX_GROK_BUILD", str(grok))
    monkeypatch.delenv("PEX_CURSOR_AGENT", raising=False)
    from pex_bridge.adapters.grok_build_bin import resolve_grok_build

    resolved = resolve_grok_build()
    assert resolved == str(grok)
    cursor = resolve_cursor_agent()
    assert cursor is None or ".grok" not in cursor.lower()


async def test_kimi_hermes_omp_deep_with_acp():
    for cls in (KimiAdapter, HermesAdapter, OmpAdapter):
        adapter = cls()
        assert (await adapter.probe()).support_label.value == "strong"
        adapter.attach_acp(FakeAcpTransport())
        assert (await adapter.probe()).support_label.value == "deep"
        sessions = await adapter.discover_sessions()
        assert sessions
        assert await adapter.send_message(sessions[0], "PEX: keep the goal.")


async def test_omp_acp_pump_ingests_idle_stop():
    transport = FakeAcpTransport()
    adapter = OmpAdapter()
    adapter.attach_acp(transport)
    session = adapter.ingest_hook({"session_id": "omp-pump", "cwd": "C:/proj"})
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
        for _ in range(40):
            types = {event.event_type.value for event, _ in ingested}
            if EventType.AGENT_RESPONSE.value in types and EventType.STOP.value in types:
                break
            await asyncio.sleep(0.05)
        types = {event.event_type.value for event, _ in ingested}
        assert EventType.STOP.value in types
        assert EventType.AGENT_RESPONSE.value in types
        assert all(sess.id == session.id for _, sess in ingested)
        notes = (await adapter.probe()).notes
        assert "pump running" in notes
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
    caps = await adapter.probe()
    assert caps.support_label.value == "basic"
    assert caps.send_message is False
    session = adapter.ingest_hook({"session_id": "pi-1"})
    assert await adapter.send_message(session, "keep going") is False


def test_claude_pretool_hook_contract():
    adapter = ClaudeCodeAdapter()
    session = adapter.ingest_hook({"session_id": "c1", "hook_event_name": "PreToolUse", "tool_name": "Bash"})
    event = adapter.normalize_hook({"hook_event_name": "PreToolUse", "tool_name": "Bash"}, session)
    assert event.event_type.value == "tool_call"
    response = adapter.hook_response(session, {"hook_event_name": "PreToolUse"}, None)
    assert response["hookSpecificOutput"]["permissionDecision"] == "allow"


async def test_hermes_plugin_hooks_use_official_returns():
    from types import SimpleNamespace

    from pex_protocol.enums import PolicyVerdict

    adapter = HermesAdapter()
    session = adapter.ingest_hook({"session_id": "h1", "cwd": "C:/proj"})
    end = adapter.normalize_hook(
        {"hook_event_name": "on_session_end", "text": "I am done."},
        session,
    )
    assert end.event_type.value == "stop"
    assert adapter.hook_response(session, {"hook_event_name": "on_session_end"}, None) == {}
    assert await adapter.send_message(session, "Create report.txt with shipped.")
    injected = adapter.hook_response(session, {"hook_event_name": "pre_llm_call"}, None)
    assert injected == {"context": "Create report.txt with shipped."}
    blocked = adapter.hook_response(
        session,
        {"hook_event_name": "pre_tool_call", "tool_name": "terminal"},
        SimpleNamespace(policy_verdict=PolicyVerdict.DENY, diagnosis="blocked by policy"),
    )
    assert blocked == {"action": "block", "message": "blocked by policy"}
    assert await adapter.send_message(session, "PEX: keep going") is False


def test_seven_starter_pets_and_codex_geometry():
    assert len(STARTERS) == 7
    assert {p.id for p in STARTERS} == {
        "pex",
        "ledger",
        "mesh",
        "nudge",
        "drift",
        "quiet",
        "ember",
    }
    assert {p.species for p in STARTERS} == {
        "owl",
        "tortoise",
        "moth",
        "hedgehog",
        "axolotl",
        "armadillo",
        "robot",
    }
    assert CODEX_CELL_W * 8 == 1536
    assert CODEX_CELL_H * CODEX_ROWS_V2 == 2288
    assert ATLAS_W == 1536
    assert ATLAS_H == 2288
    assert codex_row_index("decision") == 6
    assert codex_row_index("working") == 7


def test_atlas_renders_codex_v2_geometry():
    image = render_atlas(STARTERS[0])
    assert image.size == (1536, 2288)
    extrema = image.getextrema()
    assert extrema[-1][1] > 0


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
    assert len(STARTERS) == 7
