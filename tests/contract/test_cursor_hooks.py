import json

import pytest
from httpx import ASGITransport, AsyncClient

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.enums import EventType


@pytest.fixture
async def client(tmp_path):
    settings = Settings(require_auth=False, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.pipeline = Pipeline(store, adapters, bus, settings)
    await store.connect()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await store.close()


@pytest.mark.asyncio
async def test_cursor_stop_hook_does_not_inject_followup(client: AsyncClient):
    await client.post("/v1/synthetic/sessions")
    goal = await client.post(
        "/v1/goals",
        json={
            "project_id": "C:/proj",
            "title": "Fix bug",
            "objective": "Fix the failing test",
            "acceptance_criteria": ["tests pass"],
        },
    )
    goal_id = goal.json()["id"]
    # Seed cursor session via hook
    first = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "sessionStart",
            "conversation_id": "conv-1",
            "workspace_roots": ["C:/proj"],
            "session_id": "conv-1",
        },
    )
    assert first.status_code == 200
    await client.post("/v1/sessions/cursor:conv-1/attach", json={"goal_id": goal_id})
    stop = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "stop",
            "conversation_id": "conv-1",
            "workspace_roots": ["C:/proj"],
            "status": "completed",
            "loop_count": 0,
        },
    )
    data = stop.json()
    assert "followup_message" not in data
    # Deterministic stop without a loaded model must stay silent.


@pytest.mark.asyncio
async def test_pause_supervision_blocks_interventions(client: AsyncClient):
    session = (await client.post("/v1/synthetic/sessions")).json()
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "x",
                "objective": "y",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    sid = session["id"]
    await client.post(f"/v1/sessions/{sid}/attach", json={"goal_id": goal["id"]})
    await client.post(f"/v1/sessions/{sid}/pause-supervision")
    stop = await client.post(
        "/v1/synthetic/events",
        json={"session_id": sid, "event_type": EventType.STOP.value, "message": "done"},
    )
    assert stop.json()["intervention"] is None


@pytest.mark.asyncio
async def test_focus_does_not_inject_worker_text(client: AsyncClient):
    session = (await client.post("/v1/synthetic/sessions")).json()
    sid = session["id"]
    focused = await client.post(f"/v1/sessions/{sid}/focus")
    assert focused.status_code == 200
    assert focused.json()["ok"] is True
    inbox = state.adapters.synthetic.inbox.get(sid, [])
    assert "PEX: focusing this session." not in inbox


@pytest.mark.asyncio
async def test_harness_focus_endpoint_uses_process_map(client: AsyncClient, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr("pex_bridge.adapters.winfocus.focus_harness", lambda name: seen.append(name) or True)
    focused = await client.post("/v1/harnesses/codex/focus")
    assert focused.status_code == 200
    assert focused.json()["ok"] is True
    assert seen == ["codex"]


def test_cursor_hook_script_recovers_event_name():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "integrations" / "cursor-hook" / "pex_cursor_hook.py"
    spec = importlib.util.spec_from_file_location("pex_cursor_hook", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    parsed = mod.parse_payload(
        'noise {"hook_event_name":"afterAgentResponse","text":"ok"} trailing',
        ["pex_cursor_hook.py"],
    )
    assert parsed["hook_event_name"] == "afterAgentResponse"
    assert parsed["text"] == "ok"
    from_argv = mod.parse_payload("{", ["pex_cursor_hook.py", "beforeShellExecution"])
    assert from_argv["hook_event_name"] == "beforeShellExecution"
    assert json.loads(mod._fail_open("preToolUse")) == {"permission": "allow"}
    assert json.loads(mod._fail_open("beforeSubmitPrompt")) == {"continue": True}
    blocked = json.loads(
        mod._safe_hook_stdout(
            '{"continue": false, "user_message": "Conflicts with a persistent constraint."}',
            "beforeSubmitPrompt",
        )
    )
    assert blocked == {
        "continue": False,
        "user_message": "Conflicts with a persistent constraint.",
    }
    assert json.loads(mod._safe_hook_stdout('{"continue": true}', "beforeSubmitPrompt")) == {
        "continue": True
    }
    assert json.loads(
        mod._safe_hook_stdout('{"permission":"ask"}', "preToolUse", {"command": "pytest -q"})
    ) == {"permission": "allow"}
    assert json.loads(
        mod._safe_hook_stdout(
            '{"permission":"ask"}',
            "beforeShellExecution",
            {"command": "rm -rf /tmp/pex-scratch"},
        )
    ) == {"permission": "ask"}
    assert json.loads(mod._safe_hook_stdout('{"followup_message":"PEX: nag"}', "stop")) == {}
    passed = json.loads(
        mod._safe_hook_stdout(
            '{"followup_message":"Create report.txt containing shipped."}',
            "stop",
        )
    )
    assert passed == {"followup_message": "Create report.txt containing shipped."}


@pytest.mark.asyncio
async def test_cursor_false_done_stop_returns_evidenced_followup(client: AsyncClient, tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    roots = [str(workspace)]
    goal = await client.post(
        "/v1/goals",
        json={
            "project_id": roots[0],
            "title": "Parser",
            "objective": "Implement the parser with passing tests",
            "acceptance_criteria": ["tests pass"],
        },
    )
    goal_id = goal.json()["id"]
    start = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "sessionStart",
            "conversation_id": "conv-false-done",
            "workspace_roots": roots,
        },
    )
    assert start.status_code == 200
    await client.post("/v1/sessions/cursor:conv-false-done/attach", json={"goal_id": goal_id})
    shell = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "afterShellExecution",
            "conversation_id": "conv-false-done",
            "command": "pytest -q",
            "exit_code": 1,
            "output": "FAILED tests/test_parser.py::test_nested_array\n1 failed, 0 passed",
        },
    )
    assert shell.status_code == 200
    stop = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "stop",
            "conversation_id": "conv-false-done",
            "completion": "All tests passed. I am done.",
        },
    )
    body = stop.json()
    text = str(body.get("followup_message") or "")
    assert "test_nested_array" in text
    assert not text.startswith("PEX:")


def test_stop_hook_writes_drop_file(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    hook_path = Path(__file__).resolve().parents[2] / "integrations" / "cursor-hook" / "pex_cursor_hook.py"
    spec = importlib.util.spec_from_file_location("pex_cursor_hook_drop", hook_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setenv("PEX_CURSOR_STOP_DROP", str(tmp_path))
    spec.loader.exec_module(mod)
    mod.record_stop_drop(
        {
            "hook_event_name": "stop",
            "cwd": str(tmp_path / "ws"),
            "completion": "done",
        }
    )
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    dumped = json.loads(files[0].read_text(encoding="utf-8"))
    assert dumped["cwd"] == str(tmp_path / "ws")
    mod.record_stop_drop({"hook_event_name": "beforeReadFile", "cwd": str(tmp_path)})
    assert len(list(tmp_path.glob("*.json"))) == 1


@pytest.mark.asyncio
async def test_cursor_overlay_is_not_prompt_injection():
    from pex_protocol.overlay import Overlay, OverlayDiff

    from pex_bridge.adapters.cursor import CursorAdapter

    adapter = CursorAdapter()
    session = adapter.upsert_from_hook(
        {"hook_event_name": "sessionStart", "conversation_id": "ovl", "workspace_roots": ["C:/proj"]}
    )
    overlay = Overlay(
        id="ovl_1",
        session_id=session.id,
        reason="debug",
        diff=OverlayDiff(system_instructions="pin the failing test"),
    )
    assert await adapter.apply_overlay(session, overlay) is False
    assert adapter.inbox.get(session.id, []) == []


def test_install_user_hooks_passes_event_name(tmp_path):
    from pex_bridge.adapters.cursor_hooks import install_user_hooks

    path = install_user_hooks(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    stop = data["hooks"]["stop"]
    assert any("stop" in item["command"] and "pex_cursor_hook.py" in item["command"] for item in stop)


@pytest.mark.asyncio
async def test_before_submit_prompt_blocks_constraint_contradiction(client: AsyncClient):
    goal = await client.post(
        "/v1/goals",
        json={
            "project_id": "C:/proj",
            "title": "Train model",
            "objective": "Train without touching preprocessing",
            "acceptance_criteria": ["metrics.json exists"],
            "constraints": ["Do not alter dataset preprocessing."],
        },
    )
    goal_id = goal.json()["id"]
    first = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "sessionStart",
            "conversation_id": "conv-prompt",
            "workspace_roots": ["C:/proj"],
        },
    )
    assert first.status_code == 200
    await client.post("/v1/sessions/cursor:conv-prompt/attach", json={"goal_id": goal_id})
    blocked = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeSubmitPrompt",
            "conversation_id": "conv-prompt",
            "workspace_roots": ["C:/proj"],
            "prompt": "Just alter dataset preprocessing first.",
        },
    )
    assert blocked.status_code == 200
    body = blocked.json()
    assert body["continue"] is False
    assert "constraint" in str(body.get("user_message") or "").lower()
    allowed = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeSubmitPrompt",
            "conversation_id": "conv-prompt",
            "workspace_roots": ["C:/proj"],
            "prompt": "Run the training script on the existing preprocessed dataset.",
        },
    )
    assert allowed.json()["continue"] is True


@pytest.mark.asyncio
async def test_supervisor_catalog_is_selectable_without_exposing_keys(client: AsyncClient, tmp_path):
    listed = await client.get("/v1/supervisor")
    assert listed.status_code == 200
    body = listed.json()
    assert body["catalog_size"] >= 50
    assert any(row["model_id"] == "gpt-5.6-sol" for row in body["catalog"])
    dumped = json.dumps(body)
    assert "sk-" not in dumped
    assert body.get("has_api_key") in {True, False}
    patched = await client.patch(
        "/v1/supervisor",
        json={"provider": "openrouter", "model_id": "anthropic/claude-sonnet-4.6"},
    )
    assert patched.status_code == 200
    assert patched.json()["backend"] == "openrouter"
    assert patched.json()["model_id"] == "anthropic/claude-sonnet-4.6"
    saved = json.loads((tmp_path / "supervisor.json").read_text(encoding="utf-8"))
    assert saved == {"provider": "openrouter", "model_id": "anthropic/claude-sonnet-4.6"}
    bad = await client.patch("/v1/supervisor", json={"provider": "not-a-vendor"})
    assert bad.status_code == 400
