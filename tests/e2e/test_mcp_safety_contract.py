import asyncio
from typing import Any

import pex_bridge.app as bridge_app
import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.mcp_server import build_mcp_server
from pex_bridge.pets import PetSettings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store

EXPECTED_TOOL_FIELDS = {
    "pex.get_goal": {"session_id"},
    "pex.get_relevant_context": {"session_id", "token_budget"},
    "pex.find_agent_with_context": {"session_id", "query"},
    "pex.get_project_state": {"session_id"},
    "pex.report_progress": {"session_id", "report"},
    "pex.request_decision": {"session_id", "request"},
    "pex.handoff": {"session_id", "request"},
    "pex.verify_claim": {"session_id", "request"},
}


def _resolve_schema(node: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    seen: set[str] = set()
    current = node
    while "$ref" in current:
        ref = current["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/") or ref in seen:
            raise AssertionError(f"unsupported or recursive schema reference: {ref!r}")
        seen.add(ref)
        resolved: Any = root
        for part in ref[2:].split("/"):
            resolved = resolved[part.replace("~1", "/").replace("~0", "~")]
        if not isinstance(resolved, dict):
            raise AssertionError(f"schema reference does not resolve to an object: {ref!r}")
        current = resolved
    return current


def _object_properties(node: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_schema(node, root)
    if resolved.get("type") == "object":
        properties = resolved.get("properties", {})
        assert isinstance(properties, dict)
        return properties
    for keyword in ("anyOf", "oneOf"):
        for option in resolved.get(keyword, []):
            if isinstance(option, dict):
                properties = _object_properties(option, root)
                if properties:
                    return properties
    return {}


def _collect_missing_bounds(
    node: dict[str, Any],
    *,
    root: dict[str, Any],
    path: str,
    missing: list[str],
) -> None:
    resolved = _resolve_schema(node, root)
    value_type = resolved.get("type")
    required_bounds = {
        # Upper bounds are the resource-safety invariant. Empty values are
        # legitimate for optional context/options, while finite enums are
        # intrinsically bounded by their closed value set.
        "string": (() if resolved.get("enum") else ("maxLength",)),
        "array": ("maxItems",),
        "integer": ("minimum", "maximum"),
    }.get(value_type)
    if required_bounds:
        absent = [key for key in required_bounds if key not in resolved]
        if absent:
            missing.append(f"{path}: missing {', '.join(absent)}")

    if value_type == "array" and isinstance(resolved.get("items"), dict):
        _collect_missing_bounds(
            resolved["items"],
            root=root,
            path=f"{path}[]",
            missing=missing,
        )
    if value_type == "object":
        for name, child in resolved.get("properties", {}).items():
            if isinstance(child, dict):
                _collect_missing_bounds(
                    child,
                    root=root,
                    path=f"{path}.{name}",
                    missing=missing,
                )
    for keyword in ("anyOf", "oneOf", "allOf"):
        for index, option in enumerate(resolved.get(keyword, [])):
            if isinstance(option, dict) and option.get("type") != "null":
                _collect_missing_bounds(
                    option,
                    root=root,
                    path=f"{path}.{keyword}[{index}]",
                    missing=missing,
                )


@pytest.mark.asyncio
async def test_mcp_list_tools_bounds_every_caller_controlled_value():
    mcp, _app = build_mcp_server()
    tools = await mcp.list_tools()
    schemas = {tool.name: tool.inputSchema for tool in tools}

    assert schemas.keys() == EXPECTED_TOOL_FIELDS.keys()
    for tool_name, expected_fields in EXPECTED_TOOL_FIELDS.items():
        actual_fields = set(schemas[tool_name].get("properties", {}))
        assert expected_fields <= actual_fields, (
            f"{tool_name} is missing declared inputs: {sorted(expected_fields - actual_fields)}"
        )
    verify_schema = schemas["pex.verify_claim"]
    assert set(verify_schema.get("properties", {})) == {"session_id", "request"}
    assert set(verify_schema.get("required", [])) == {"session_id", "request"}
    handoff_schema = schemas["pex.handoff"]
    assert set(handoff_schema.get("properties", {})) == {"session_id", "request"}
    assert set(handoff_schema.get("required", [])) == {"session_id", "request"}
    handoff_fields = _object_properties(
        handoff_schema["properties"]["request"],
        handoff_schema,
    )
    assert set(handoff_fields) == {
        "idempotency_key",
        "target_session_id",
        "token_budget",
    }
    assert handoff_fields["token_budget"]["minimum"] == 256
    assert handoff_fields["token_budget"]["maximum"] == 12_000

    progress_root = schemas["pex.report_progress"]
    progress_tool_fields = progress_root["properties"]
    if "report" in progress_tool_fields:
        progress_fields = _object_properties(progress_tool_fields["report"], progress_root)
    else:
        progress_fields = progress_tool_fields
    expected_progress_fields = {"idempotency_key", "summary", "evidence_refs"}
    missing: list[str] = []
    absent_progress_fields = expected_progress_fields - progress_fields.keys()
    if absent_progress_fields:
        missing.append(
            "pex.report_progress: shared ProgressReport payload is missing "
            f"{sorted(absent_progress_fields)}"
        )
    evidence_schema = progress_fields.get("evidence_refs")
    if isinstance(evidence_schema, dict):
        resolved_evidence = _resolve_schema(evidence_schema, progress_root)
        evidence_item = resolved_evidence.get("items")
        evidence_properties = (
            _object_properties(evidence_item, progress_root)
            if isinstance(evidence_item, dict)
            else {}
        )
        expected_evidence_fields = {"type", "id"}
        absent_evidence_fields = expected_evidence_fields - evidence_properties.keys()
        if absent_evidence_fields:
            missing.append(
                "pex.report_progress.evidence_refs[]: shared "
                "ProgressEvidenceReference payload is missing "
                f"{sorted(absent_evidence_fields)}"
            )
    for tool_name, schema in schemas.items():
        for field_name, field_schema in schema.get("properties", {}).items():
            if isinstance(field_schema, dict):
                _collect_missing_bounds(
                    field_schema,
                    root=schema,
                    path=f"{tool_name}.{field_name}",
                    missing=missing,
                )
    assert not missing, "MCP input schemas have unbounded caller-controlled values:\n" + "\n".join(
        missing
    )


async def _never_finishes() -> None:
    await asyncio.Event().wait()


def _configure_lifespan_app(tmp_path):
    settings = Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    bridge_app.state.settings = settings
    bridge_app.state.store = store
    bridge_app.state.adapters = adapters
    bridge_app.state.bus = bus
    bridge_app.state.pipeline = Pipeline(store, adapters, bus, settings, model=None)
    bridge_app.state.token = None
    bridge_app.state.pet_settings = PetSettings()
    bridge_app.state.pet_path = tmp_path / "pet.json"
    bridge_app.state.sockets.clear()
    bridge_app.state._socket_send_locks.clear()
    bridge_app.state.background_tasks = set()
    return bridge_app.create_app(), store


def _quiet_external_startup(monkeypatch) -> None:
    async def no_attach(_adapters, _settings):
        return []

    monkeypatch.setattr("pex_bridge.adapters.attach.attach_from_settings", no_attach)
    monkeypatch.setattr("pex_bridge.pets.maybe_import_codex_home", lambda settings: settings)
    monkeypatch.setattr("pex_supervisor.providers.load_supervisor_model", lambda: None)


def _install_tracked_startup_tasks(monkeypatch) -> dict[str, asyncio.Task[None]]:
    tasks: dict[str, asyncio.Task[None]] = {}

    def start_tasks() -> None:
        pump = asyncio.create_task(_never_finishes(), name="test-mcp-safety-pump")
        background = asyncio.create_task(
            _never_finishes(), name="test-mcp-safety-background"
        )
        bridge_app.state.adapters.synthetic._pump_task = pump
        bridge_app.state.track_background(background)
        tasks.update(pump=pump, background=background)

    monkeypatch.setattr(bridge_app, "_start_event_pumps", start_tasks)
    return tasks


async def _cleanup_failed_lifespan_test(
    store: Store,
    tasks: dict[str, asyncio.Task[None]],
) -> None:
    for task in tasks.values():
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks.values(), return_exceptions=True)
    bridge_app.state.background_tasks.clear()
    if store._db is not None:
        await store.close()


class _FailingMcpEntry:
    async def __aenter__(self):
        raise RuntimeError("injected MCP session-manager entry failure")

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _RecordingMcpContext:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.exited = True
        return False


@pytest.mark.asyncio
async def test_lifespan_rolls_back_store_and_tasks_when_mcp_entry_raises(
    monkeypatch,
    tmp_path,
):
    app, store = _configure_lifespan_app(tmp_path)
    _quiet_external_startup(monkeypatch)
    tasks = _install_tracked_startup_tasks(monkeypatch)
    monkeypatch.setattr(
        app.state.pex_mcp.session_manager,
        "run",
        lambda: _FailingMcpEntry(),
    )

    try:
        with pytest.raises(RuntimeError, match="session-manager entry failure"):
            async with bridge_app.lifespan(app):
                pytest.fail("lifespan yielded after MCP entry failed")
        await asyncio.sleep(0)
        observed = {
            "store_closed": store._db is None,
            "pump_done": tasks["pump"].done(),
            "background_done": tasks["background"].done(),
            "background_registry_empty": not bridge_app.state.background_tasks,
        }
        assert observed == {
            "store_closed": True,
            "pump_done": True,
            "background_done": True,
            "background_registry_empty": True,
        }
    finally:
        await _cleanup_failed_lifespan_test(store, tasks)


@pytest.mark.asyncio
async def test_lifespan_rolls_back_mcp_store_and_tasks_on_post_connect_startup_failure(
    monkeypatch,
    tmp_path,
):
    app, store = _configure_lifespan_app(tmp_path)
    _quiet_external_startup(monkeypatch)
    tasks = _install_tracked_startup_tasks(monkeypatch)
    mcp_context = _RecordingMcpContext()
    monkeypatch.setattr(
        app.state.pex_mcp.session_manager,
        "run",
        lambda: mcp_context,
    )
    real_create_task = asyncio.create_task

    def fail_overlay_task_start(coro, *args, **kwargs):
        code = getattr(coro, "cr_code", None)
        if getattr(code, "co_name", "") == "_overlay_expiry_loop":
            coro.close()
            raise RuntimeError("injected post-connect task startup failure")
        return real_create_task(coro, *args, **kwargs)

    monkeypatch.setattr(asyncio, "create_task", fail_overlay_task_start)

    try:
        with pytest.raises(RuntimeError, match="post-connect task startup failure"):
            async with bridge_app.lifespan(app):
                pytest.fail("lifespan yielded after task startup failed")
        await asyncio.sleep(0)
        observed = {
            "mcp_entered": mcp_context.entered,
            "mcp_exited": mcp_context.exited,
            "store_closed": store._db is None,
            "pump_done": tasks["pump"].done(),
            "background_done": tasks["background"].done(),
            "background_registry_empty": not bridge_app.state.background_tasks,
        }
        assert observed == {
            "mcp_entered": True,
            "mcp_exited": True,
            "store_closed": True,
            "pump_done": True,
            "background_done": True,
            "background_registry_empty": True,
        }
    finally:
        await _cleanup_failed_lifespan_test(store, tasks)
        if mcp_context.entered and not mcp_context.exited:
            await mcp_context.__aexit__(None, None, None)
