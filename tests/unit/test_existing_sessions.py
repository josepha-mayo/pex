"""Existing open sessions are first-class for the starter harnesses.

Cursor, Codex, OpenCode, Hermes, and Claude Code list already-running apps
without restarting them or installing control. Grok Bot is excluded from that
starter inventory.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.acp_harness import HermesAdapter
from pex_bridge.adapters.claude_code import ClaudeCodeAdapter
from pex_bridge.adapters.codex import CodexAdapter
from pex_bridge.adapters.cursor import CursorAdapter
from pex_bridge.adapters.desktop import DESKTOP_APPS, desktop_process_inventory, list_desktop_apps
from pex_bridge.adapters.opencode import OpenCodeAdapter
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.enums import SessionStatus
from pex_protocol.session import HarnessSession

STARTER = {"cursor", "codex", "opencode", "hermes", "claude_code"}


def test_starter_desktop_inventory_excludes_grok_bot():
    assert {app["name"] for app in DESKTOP_APPS} == STARTER
    inventory = desktop_process_inventory(set())
    assert inventory["running"] == []
    assert set(inventory["not_running"]) == STARTER
    assert "grok_bot" not in inventory["not_running"]
    found = list_desktop_apps({"Grok Bot.exe"})
    assert found == []


async def test_cursor_lists_existing_exe_without_hooks_or_send(monkeypatch):
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"Cursor.exe"},
    )
    adapter = CursorAdapter()
    sessions = await adapter.discover_sessions()
    assert [session.id for session in sessions] == ["cursor:desktop"]
    assert sessions[0].metadata["existing_session"] is True
    caps = await adapter.probe()
    assert caps.support_label.value == "observe_only"
    assert caps.send_message is False
    assert caps.focus_ui is True
    assert "never auto-installed" in caps.notes.lower()
    assert "this open session" not in caps.notes.lower()


async def test_codex_observe_only_when_chatgpt_running(monkeypatch):
    from pex_protocol.enums import HarnessType

    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"ChatGPT.exe"},
    )
    adapter = CodexAdapter()
    adapter.sessions["codex:thr_stale"] = HarnessSession(
        id="codex:thr_stale",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thr_stale",
        status=SessionStatus.IDLE,
    )
    sessions = await adapter.discover_sessions()
    ids = {session.id for session in sessions}
    assert "codex:desktop" in ids
    assert "codex:thr_stale" not in ids
    caps = await adapter.probe()
    assert caps.support_label.value == "observe_only"
    assert caps.send_message is False
    assert caps.focus_ui is True


async def test_codex_keeps_working_isolated_session_when_chatgpt_is_also_open(
    monkeypatch,
):
    from pex_protocol.enums import HarnessType

    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"ChatGPT.exe"},
    )
    adapter = CodexAdapter()
    adapter.sessions["codex:thr_live"] = HarnessSession(
        id="codex:thr_live",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thr_live",
        status=SessionStatus.WORKING,
        cwd="C:/isolated",
        project_id="C:/isolated",
        metadata={"isolated": True, "source": "pexbench"},
    )
    sessions = await adapter.discover_sessions()
    ids = {session.id for session in sessions}
    assert ids == {"codex:desktop", "codex:thr_live"}
    assert adapter.sessions["codex:thr_live"].status == SessionStatus.WORKING
    caps = await adapter.probe()
    assert caps.support_label.value == "observe_only"
    assert caps.send_message is False
    assert caps.focus_ui is True


async def test_chatgpt_desktop_session_cannot_start_app_server_turns(monkeypatch):
    from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport

    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"ChatGPT.exe"},
    )
    transport = CodexAppServerTransport()
    adapter = CodexAdapter(transport)
    await adapter.discover_sessions()
    desktop = adapter.sessions["codex:desktop"]
    desktop.cwd = "C:/stolen"
    desktop.project_id = "C:/stolen"
    desktop.status = SessionStatus.WORKING
    adapter.sessions["codex:desktop"] = desktop
    assert await adapter.send_message(desktop, "continue from ChatGPT.exe") is False
    assert transport.turns == []


async def test_cursor_desktop_tile_cannot_send_even_with_acp():
    from pex_protocol.enums import HarnessType

    class RecordingAcp:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple]] = []

        async def activate(self, *args, **kwargs):
            self.calls.append(("activate", args))

        async def prompt(self, *args, **kwargs):
            self.calls.append(("prompt", args))

    adapter = CursorAdapter()
    adapter.acp = RecordingAcp()
    desktop = HarnessSession(
        id="cursor:desktop",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="desktop",
        cwd="C:/stolen",
        project_id="C:/stolen",
        status=SessionStatus.WORKING,
        metadata={"source": "desktop", "process": "Cursor.exe"},
    )
    adapter.sessions["cursor:desktop"] = desktop
    assert await adapter.send_message(desktop, "resume this Cursor") is False
    assert adapter.acp.calls == []
    assert adapter.inbox.get("cursor:desktop", []) == []


async def test_opencode_desktop_tile_cannot_prompt_the_http_server():
    from pex_protocol.enums import HarnessType

    class RecordingTransport:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        async def request(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {}

    adapter = OpenCodeAdapter(RecordingTransport())
    desktop = HarnessSession(
        id="opencode:desktop",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="desktop",
        cwd="C:/stolen",
        project_id="C:/stolen",
        status=SessionStatus.WORKING,
        metadata={"source": "desktop"},
    )
    adapter.sessions["opencode:desktop"] = desktop
    assert await adapter.send_message(desktop, "resume OpenCode") is False
    assert adapter.transport.calls == []


async def test_codex_unavailable_when_chatgpt_not_running(monkeypatch):
    monkeypatch.setattr("pex_bridge.adapters.desktop.running_image_names", lambda: set())
    adapter = CodexAdapter()
    sessions = await adapter.discover_sessions()
    assert sessions == []
    caps = await adapter.probe()
    assert caps.support_label.value == "unavailable"
    assert caps.send_message is False


async def test_opencode_lists_existing_tui_without_spawning_serve(monkeypatch):
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"OpenCode.exe"},
    )
    adapter = OpenCodeAdapter()
    sessions = await adapter.discover_sessions()
    assert [session.id for session in sessions] == ["opencode:desktop"]
    caps = await adapter.probe()
    assert caps.support_label.value == "observe_only"
    assert caps.send_message is False
    assert caps.fork is False
    assert "does not spawn serve" in caps.notes


async def test_hermes_lists_existing_desktop_without_launching(monkeypatch):
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"NousHermes.exe"},
    )
    adapter = HermesAdapter()
    sessions = await adapter.discover_sessions()
    assert [session.id for session in sessions] == ["hermes:desktop"]
    caps = await adapter.probe()
    assert caps.support_label.value == "observe_only"
    assert caps.send_message is False
    assert caps.focus_ui is True


async def test_claude_code_lists_existing_cli_without_installing_hooks(monkeypatch):
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"claude.exe"},
    )
    adapter = ClaudeCodeAdapter()
    sessions = await adapter.discover_sessions()
    assert [session.id for session in sessions] == ["claude_code:desktop"]
    caps = await adapter.probe()
    assert caps.support_label.value == "observe_only"
    assert caps.send_message is False
    assert "never auto-installed" in caps.notes.lower()


async def test_hook_sessions_win_over_generic_desktop_tiles(monkeypatch):
    from pex_protocol.enums import HarnessType

    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"Cursor.exe", "claude.exe"},
    )
    cursor = CursorAdapter()
    cursor.sessions["cursor:conv-1"] = HarnessSession(
        id="cursor:conv-1",
        harness_type=HarnessType.CURSOR,
        vendor_session_id="conv-1",
        status=SessionStatus.WORKING,
        metadata={"source": "hook"},
    )
    claude = ClaudeCodeAdapter()
    claude.sessions["claude_code:sess-1"] = HarnessSession(
        id="claude_code:sess-1",
        harness_type=HarnessType.CLAUDE_CODE,
        vendor_session_id="sess-1",
        status=SessionStatus.WORKING,
        metadata={"source": "hook"},
    )
    assert [session.id for session in await cursor.discover_sessions()] == ["cursor:conv-1"]
    assert [session.id for session in await claude.discover_sessions()] == ["claude_code:sess-1"]


async def test_refresh_detaches_vanished_desktop_rows(tmp_path, monkeypatch):
    from pex_protocol.enums import HarnessType

    monkeypatch.setattr("pex_bridge.adapters.desktop.running_image_names", lambda: set())
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    registry = AdapterRegistry()
    pipeline = Pipeline(
        store,
        registry,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="observe"),
    )
    await store.upsert_session(
        HarnessSession(
            id="cursor:desktop",
            harness_type=HarnessType.CURSOR,
            vendor_session_id="desktop",
            status=SessionStatus.DISCOVERED,
            metadata={"source": "desktop"},
        )
    )
    await pipeline.refresh_desktop_sessions()
    stored = await store.get_session("cursor:desktop")
    await store.close()
    assert stored is not None
    assert stored.status == SessionStatus.DETACHED


async def test_refresh_does_not_detach_a_working_codex_session(tmp_path, monkeypatch):
    from pex_protocol.enums import HarnessType

    monkeypatch.setattr("pex_bridge.adapters.desktop.running_image_names", lambda: set())
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    registry = AdapterRegistry()
    pipeline = Pipeline(
        store,
        registry,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="observe"),
    )
    await store.upsert_session(
        HarnessSession(
            id="codex:live",
            harness_type=HarnessType.CODEX,
            vendor_session_id="live",
            status=SessionStatus.WORKING,
        )
    )
    await pipeline.refresh_desktop_sessions()
    stored = await store.get_session("codex:live")
    await store.close()
    assert stored is not None
    assert stored.status == SessionStatus.WORKING


@pytest.fixture
async def existing_session_client(tmp_path):
    settings = Settings.for_test(require_auth=False, home=tmp_path, codex_attach=False)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    await store.connect()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://127.0.0.1",
        ) as client:
            yield client
    finally:
        await store.close()


async def test_cursor_attach_does_not_install_hooks_by_default(
    existing_session_client,
    monkeypatch,
):
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"Cursor.exe"},
    )
    monkeypatch.setattr("pex_bridge.adapters.discover.PROBES", ())
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_codex_bin", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_grok_build", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_hermes", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.shutil.which", lambda _name: None)

    called: list[bool] = []

    def boom():
        called.append(True)
        raise AssertionError("hooks must not install unless install_hooks is true")

    monkeypatch.setattr("pex_bridge.app._install_cursor_hooks_or_error", boom)
    response = await existing_session_client.post(
        "/v1/discover/attach",
        json={"name": "cursor"},
    )
    assert response.status_code == 200
    body = response.json()
    assert called == []
    assert body["hooks"] is None
    assert "this already-running" not in body["note"].lower()
    assert "hooks were not" in body["note"].lower()


async def test_codex_discover_attach_without_kind_does_not_spawn_app_server(
    existing_session_client,
    monkeypatch,
    tmp_path,
):
    fake = tmp_path / "codex.exe"
    fake.write_bytes(b"x")
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"ChatGPT.exe"},
    )
    monkeypatch.setattr("pex_bridge.adapters.discover.PROBES", ())
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_codex_bin", lambda: str(fake))
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_grok_build", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_hermes", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.shutil.which", lambda _name: None)

    def boom(*_args, **_kwargs):
        raise AssertionError("isolated App Server must not spawn without kind=stdio")

    monkeypatch.setattr(
        "pex_bridge.adapters.codex.CodexAdapter.attach_transport",
        boom,
    )
    response = await existing_session_client.post(
        "/v1/discover/attach",
        json={"name": "codex"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "desktop"
    assert "kind=stdio" in body["note"]


async def test_codex_discover_attach_without_kind_refuses_stdio_only_inventory(
    existing_session_client,
    monkeypatch,
    tmp_path,
):
    fake = tmp_path / "codex.exe"
    fake.write_bytes(b"x")
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: set(),
    )
    monkeypatch.setattr("pex_bridge.adapters.discover.PROBES", ())
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_codex_bin", lambda: str(fake))
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_grok_build", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_hermes", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.shutil.which", lambda _name: None)
    monkeypatch.setattr(
        "pex_bridge.adapters.codex.CodexAdapter.attach_transport",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("isolated App Server must not spawn without kind=stdio")
        ),
    )
    response = await existing_session_client.post(
        "/v1/discover/attach",
        json={"name": "codex"},
    )
    assert response.status_code == 400
    assert "kind=stdio" in response.json()["detail"]


async def test_cannot_attach_a_goal_to_the_chatgpt_desktop_tile(
    existing_session_client,
):
    from pex_bridge.app import state
    from pex_protocol.enums import HarnessType
    from pex_protocol.session import HarnessSession

    await state.store.upsert_session(
        HarnessSession(
            id="codex:desktop",
            harness_type=HarnessType.CODEX,
            vendor_session_id="desktop",
            metadata={"source": "desktop", "process": "ChatGPT.exe", "existing_session": True},
        )
    )
    await state.store.upsert_session(
        HarnessSession(
            id="codex:thr_live",
            harness_type=HarnessType.CODEX,
            vendor_session_id="thr_live",
            cwd="C:/isolated",
            project_id="C:/isolated",
            metadata={"isolated": True, "source": "pexbench"},
        )
    )
    goal = await existing_session_client.post(
        "/v1/goals",
        json={
            "project_id": "C:/isolated",
            "title": "report",
            "objective": "Create report.txt containing shipped.",
            "acceptance_criteria": ["report.txt contains shipped"],
        },
    )
    assert goal.status_code == 200
    goal_id = goal.json()["id"]
    denied = await existing_session_client.post(
        "/v1/sessions/codex:desktop/attach",
        json={"goal_id": goal_id},
    )
    assert denied.status_code == 409
    assert "observe" in denied.json()["detail"].lower()
    allowed = await existing_session_client.post(
        "/v1/sessions/codex:thr_live/attach",
        json={"goal_id": goal_id},
    )
    assert allowed.status_code == 200
    assert allowed.json()["goal_id"] == goal_id


async def test_cannot_attach_a_goal_to_cursor_or_opencode_desktop_tiles(
    existing_session_client,
):
    from pex_bridge.app import state
    from pex_protocol.enums import HarnessType
    from pex_protocol.session import HarnessSession

    await state.store.upsert_session(
        HarnessSession(
            id="cursor:desktop",
            harness_type=HarnessType.CURSOR,
            vendor_session_id="desktop",
            metadata={"source": "desktop", "process": "Cursor.exe", "existing_session": True},
        )
    )
    await state.store.upsert_session(
        HarnessSession(
            id="opencode:desktop",
            harness_type=HarnessType.OPENCODE,
            vendor_session_id="desktop",
            metadata={"source": "desktop", "process": "opencode.exe", "existing_session": True},
        )
    )
    await state.store.upsert_session(
        HarnessSession(
            id="cursor:conv-live",
            harness_type=HarnessType.CURSOR,
            vendor_session_id="conv-live",
            cwd="C:/isolated",
            project_id="C:/isolated",
            metadata={"source": "hook"},
        )
    )
    goal = await existing_session_client.post(
        "/v1/goals",
        json={
            "project_id": "C:/isolated",
            "title": "report",
            "objective": "Create report.txt containing shipped.",
            "acceptance_criteria": ["report.txt contains shipped"],
        },
    )
    assert goal.status_code == 200
    goal_id = goal.json()["id"]
    for session_id in ("cursor:desktop", "opencode:desktop"):
        denied = await existing_session_client.post(
            f"/v1/sessions/{session_id}/attach",
            json={"goal_id": goal_id},
        )
        assert denied.status_code == 409, session_id
        assert "observe" in denied.json()["detail"].lower()
    allowed = await existing_session_client.post(
        "/v1/sessions/cursor:conv-live/attach",
        json={"goal_id": goal_id},
    )
    assert allowed.status_code == 200
    assert allowed.json()["goal_id"] == goal_id


async def test_discover_not_running_is_closed_starter_harnesses(
    existing_session_client,
    monkeypatch,
):
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"Cursor.exe"},
    )
    monkeypatch.setattr("pex_bridge.adapters.discover.PROBES", ())
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_codex_bin", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_grok_build", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_hermes", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.shutil.which", lambda _name: None)
    response = await existing_session_client.get("/v1/discover")
    assert response.status_code == 200
    body = response.json()
    present = {item["name"] for item in body["found"] if item.get("kind") == "desktop"}
    assert present == {"cursor"}
    assert set(body["not_running"]) == STARTER - {"cursor"}
    assert "grok_bot" not in body["not_running"]


def test_prefer_attach_match_prefers_http_over_desktop():
    from pex_bridge.adapters.discover import prefer_attach_match

    found = [
        {"name": "opencode", "kind": "desktop"},
        {"name": "opencode", "kind": "http", "base_url": "http://127.0.0.1:4096"},
        {"name": "hermes", "kind": "desktop"},
        {"name": "hermes", "kind": "acp", "bin": "C:/hermes.exe"},
    ]
    assert prefer_attach_match(found, "opencode")["kind"] == "http"
    assert prefer_attach_match(found, "hermes")["kind"] == "acp"
    assert prefer_attach_match(found, "opencode", "desktop")["kind"] == "desktop"
    codex = [
        {"name": "codex", "kind": "desktop"},
        {"name": "codex", "kind": "stdio", "bin": "C:/codex.exe"},
    ]
    assert prefer_attach_match(codex, "codex")["kind"] == "desktop"
    assert prefer_attach_match(codex, "codex", "stdio")["kind"] == "stdio"
    assert prefer_attach_match([{"name": "codex", "kind": "stdio"}], "codex") is None


async def test_opencode_and_hermes_desktop_do_not_hide_control_bins(tmp_path, monkeypatch):
    from pex_bridge.adapters.desktop import list_desktop_apps
    from pex_bridge.adapters.discover import probe_local_harnesses

    hermes = tmp_path / "hermes.exe"
    hermes.write_bytes(b"x")
    opencode = tmp_path / "opencode.exe"
    opencode.write_bytes(b"x")
    monkeypatch.setattr(
        "pex_bridge.adapters.discover.list_desktop_apps",
        lambda: list_desktop_apps({"OpenCode.exe", "Hermes.exe"}),
    )
    monkeypatch.setattr("pex_bridge.adapters.discover.PROBES", ())
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_codex_bin", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_grok_build", lambda: None)
    monkeypatch.setattr("pex_bridge.adapters.discover.resolve_hermes", lambda: str(hermes))
    monkeypatch.setattr(
        "pex_bridge.adapters.discover.shutil.which",
        lambda name: str(opencode) if name == "opencode" else None,
    )
    found = await probe_local_harnesses()
    kinds = {(item["name"], item["kind"]) for item in found}
    assert ("opencode", "desktop") in kinds
    assert ("opencode", "cli") in kinds
    assert ("hermes", "desktop") in kinds
    assert ("hermes", "acp") in kinds
    assert "grok_bot" not in {item["name"] for item in found}
