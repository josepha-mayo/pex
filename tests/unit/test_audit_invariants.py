"""Always-on honesty audit. These must stay green or the product is lying."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.connect import CONNECT
from pex_bridge.adapters.cursor_bin import resolve_cursor_agent
from pex_bridge.adapters.grok_build_bin import acp_command


def test_required_harnesses_are_registered():
    names = {adapter.name for adapter in AdapterRegistry().all()}
    missing = set(AdapterRegistry.REQUIRED_HARNESSES) - names
    assert not missing, f"required harnesses missing from registry: {missing}"


def test_connect_table_does_not_invent_a_shared_protocol():
    assert CONNECT["cursor"]["method"] == "hooks"
    assert CONNECT["codex"]["method"] == "app-server-stdio"
    assert "observe/focus" in CONNECT["codex"]["note"]
    assert CONNECT["grok_bot"]["method"] == "observe-process"
    assert CONNECT["grok_build"]["method"] == "acp-stdio"
    assert CONNECT["opencode"]["method"] == "http"
    assert CONNECT["hermes"]["command"] == ["hermes", "acp"]
    assert CONNECT["devin"]["method"] == "org-api"
    assert (
        "second Cursor" in CONNECT["cursor"]["note"] or "Never spawn" in CONNECT["cursor"]["note"]
    )
    assert CONNECT["grok_bot"]["method"] != CONNECT["grok_build"]["method"]


def test_cursor_agent_is_never_auto_discovered(monkeypatch):
    monkeypatch.delenv("PEX_CURSOR_AGENT", raising=False)
    assert resolve_cursor_agent() is None


def test_grok_build_acp_is_agent_stdio_not_grok_acp(tmp_path):
    grok = tmp_path / "grok"
    grok.write_bytes(b"fake")
    assert acp_command(str(grok)) == [str(grok), "agent", "stdio"]


def test_pexbench_manifest_stays_unfrozen_without_one_coherent_live_run(tmp_path, monkeypatch):
    import yaml

    path = Path("benchmarks/four_arm.py")
    spec = importlib.util.spec_from_file_location("pexbench_four_arm_audit", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    # The repository intentionally does not track raw result JSONL files. Keep
    # this honesty invariant independent of ignored developer-local runs.
    monkeypatch.setattr(module.runner, "RESULTS", tmp_path / "empty-results")
    manifest = yaml.safe_load(Path("benchmarks/manifest.yaml").read_text(encoding="utf-8"))
    blockers = module.freeze_blockers()
    assert blockers
    assert module.coherent_presentation_runs() == []
    assert any("no result for cursor/" in blocker for blocker in blockers)
    assert any("no result for codex_pex/" in blocker for blocker in blockers)
    assert manifest.get("frozen") is False


def test_synthetic_results_are_not_presentation_arms(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "runner.py"
    spec = importlib.util.spec_from_file_location("pexbench_runner_audit", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "RESULTS", tmp_path)
    record = {
        "arm": "codex_pex",
        "task": "pexbench_001_premature_stop",
        "success": True,
    }
    try:
        module.append_immutable("audit", record)
        raise AssertionError("presentation arm without live=True must be refused")
    except ValueError as exc:
        assert "live" in str(exc)
