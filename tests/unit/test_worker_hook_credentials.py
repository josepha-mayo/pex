from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_python_worker_integrations_ignore_operator_credentials(tmp_path, monkeypatch):
    operator = "operator-token-that-must-not-enter-worker-hooks"
    (tmp_path / "bridge.token").write_text(operator, encoding="utf-8")
    monkeypatch.setenv("PEX_HOME", str(tmp_path))
    monkeypatch.setenv("PEX_TOKEN", operator)
    monkeypatch.setenv("PEX_BRIDGE_TOKEN", operator)
    monkeypatch.delenv("PEX_HOOK_TOKEN", raising=False)
    monkeypatch.delenv("PEX_CURSOR_HOOK_TOKEN", raising=False)
    monkeypatch.delenv("PEX_HERMES_HOOK_TOKEN", raising=False)

    generic = _load("pex_generic_hook_credential_test", "integrations/hooks/pex_hook.py")
    cursor = _load(
        "pex_cursor_hook_credential_test",
        "integrations/cursor-hook/pex_cursor_hook.py",
    )
    hermes = _load(
        "pex_hermes_hook_credential_test",
        "integrations/hermes-plugin/pex_plugin.py",
    )

    assert generic._token() == ""
    assert cursor._token() == ""
    assert hermes._token() == ""

    scoped = "scoped-hook-token-that-is-long-enough"
    monkeypatch.setenv("PEX_HOOK_TOKEN", scoped)
    assert generic._token() == scoped
    assert cursor._token() == scoped
    assert hermes._token() == scoped


def test_opencode_worker_plugin_has_no_operator_token_fallback():
    source = (ROOT / "integrations/opencode-plugin/pex-plugin.js").read_text(
        encoding="utf-8"
    )
    assert "PEX_OPENCODE_HOOK_TOKEN" in source
    assert "PEX_HOOK_TOKEN" in source
    assert "process.env.PEX_TOKEN" not in source
    assert "bridge.token" not in source
