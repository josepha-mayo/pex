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


def test_desktop_detection_uses_running_apps():
    from pex_bridge.adapters.desktop import list_desktop_apps

    found = list_desktop_apps({"Cursor.exe", "ChatGPT.exe", "Grok Bot.exe"})
    by_name = {item["name"]: item for item in found}
    assert set(by_name) == {"cursor", "codex", "grok_bot"}
    assert by_name["cursor"]["connect"] == "hooks"
    assert by_name["codex"]["connect"] == "app-server-stdio"
    assert by_name["grok_bot"]["connect"] == "observe-process"
    assert all(item["kind"] == "desktop" for item in found)


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


async def test_codex_unavailable_without_transport():
    caps = await CodexAdapter().probe()
    assert caps.support_label.value == "unavailable"


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


async def test_qwen_deep_only_with_transport():
    assert (await QwenAdapter().probe()).support_label.value == "unavailable"
    transport = MemoryHttpTransport()
    adapter = QwenAdapter(transport)
    assert (await adapter.probe()).support_label.value == "deep"
    sessions = await adapter.discover_sessions()
    assert await adapter.send_message(sessions[0], "PEX context bundle")
    assert any("/prompt" in call[1] for call in transport.calls)


async def test_devin_stays_basic_when_attached():
    assert (await DevinAdapter().probe()).support_label.value == "unavailable"
    transport = MemoryHttpTransport()
    adapter = DevinAdapter(transport)
    caps = await adapter.probe()
    assert caps.support_label.value == "basic"
    sessions = await adapter.discover_sessions()
    assert sessions
    assert await adapter.send_message(sessions[0], "PEX: the schema is already decided.")


async def test_grok_build_deep_with_acp():
    adapter = GrokBuildAdapter()
    assert (await adapter.probe()).support_label.value == "strong"
    adapter.attach_acp(FakeAcpTransport())
    assert (await adapter.probe()).support_label.value == "deep"
    sessions = await adapter.discover_sessions()
    assert sessions
    assert await adapter.send_message(sessions[0], "PEX: stay on the eval pipeline.")


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


def test_claude_pretool_hook_contract():
    adapter = ClaudeCodeAdapter()
    session = adapter.ingest_hook({"session_id": "c1", "hook_event_name": "PreToolUse", "tool_name": "Bash"})
    event = adapter.normalize_hook({"hook_event_name": "PreToolUse", "tool_name": "Bash"}, session)
    assert event.event_type.value == "tool_call"
    response = adapter.hook_response(session, {"hook_event_name": "PreToolUse"}, None)
    assert response["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_ten_starter_pets_and_codex_geometry():
    assert len(STARTERS) == 10
    assert {p.id for p in STARTERS} == {
        "pex",
        "ledger",
        "mesh",
        "nudge",
        "drift",
        "quiet",
        "ember",
        "spark",
        "bot",
        "kit",
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
    assert len(STARTERS) == 10
