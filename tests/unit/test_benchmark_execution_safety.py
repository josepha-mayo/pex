"""Execution safeguards are capabilities, not self-attested manifest flags."""

import importlib.util
import sys
from pathlib import Path

import pytest


def _four_arm():
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "four_arm.py"
    spec = importlib.util.spec_from_file_location("benchmark_execution_safety", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("arm", ["cursor", "cursor_pex", "codex", "codex_pex"])
def test_missing_runtime_isolation_blocks_every_real_arm(arm):
    blockers = _four_arm()._execution_preflight_blockers(arm)
    assert any("not a sandbox" in item for item in blockers)
    assert any("Cursor network" in item for item in blockers) == arm.startswith("cursor")


def test_manifest_assertions_cannot_create_runtime_isolation(monkeypatch):
    four = _four_arm()
    manifest = four.runner.load_manifest()
    manifest["suite"].update(
        natural_task_source_status="satisfied", task_execution_boundary="isolated_untrusted_worker"
    )
    manifest["integrity"] = {key: "satisfied" for key in manifest["integrity"]}
    manifest["protocol"]["network_policy"]["cursor"] = (
        "synchronous_controller_network_policy_verified"
    )
    monkeypatch.setattr(four.runner, "load_manifest", lambda: manifest)
    assert any("not a sandbox" in item for item in four._execution_preflight_blockers("codex"))
    assert any("Cursor network" in item for item in four._execution_preflight_blockers("cursor"))


def test_post_run_evidence_does_not_make_execution_gate_circular(monkeypatch):
    four = _four_arm()
    # This is a fake capability for a unit contract, not an implemented backend.
    monkeypatch.setattr(four.boundary, "execution_runtime_blockers", lambda arm=None: [])
    assert four._execution_preflight_blockers("codex") == []
    report = four._report_readiness_blockers()
    for missing in ("natural-task", "raw harness", "same-session", "repository commits"):
        assert any(missing in item for item in report)


@pytest.mark.parametrize("defect", ["suffix", "task_branch", "evaluator_import", "missing_source"])
def test_leakage_checks_run_before_dispatch(tmp_path, monkeypatch, defect):
    four = _four_arm()
    root = tmp_path / "benchmarks"
    supervisor = tmp_path / "services/supervisor/src/pex_supervisor"
    root.mkdir()
    supervisor.mkdir(parents=True)
    for name in (
        "four_arm.py",
        "pex_attach.py",
        "cursor_isolated_stop.py",
        "pex_supervisor_process.py",
    ):
        (root / name).write_text("pass\n", encoding="utf-8")
    for name in ("loop.py", "planner.py", "public_task.py"):
        (supervisor / name).write_text("pass\n", encoding="utf-8")
    if defect == "suffix":
        (root / "four_arm.py").write_text("append_better_prompt()\n", encoding="utf-8")
    elif defect == "task_branch":
        (supervisor / "loop.py").write_text("identity = 'pexbench_001'\n", encoding="utf-8")
    elif defect == "evaluator_import":
        (root / "pex_attach.py").write_text("import evaluator\n", encoding="utf-8")
    else:
        (supervisor / "planner.py").unlink()
    monkeypatch.setattr(four.boundary, "ROOT", root)
    monkeypatch.setattr(four.boundary, "REPO", tmp_path)
    monkeypatch.setattr(four.boundary, "execution_runtime_blockers", lambda arm=None: [])
    assert any(
        "information-boundary check failed" in item
        for item in four._execution_preflight_blockers("codex")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("arm", ["cursor", "cursor_pex", "codex", "codex_pex"])
async def test_live_entrypoints_fail_before_transport_or_workspace(tmp_path, monkeypatch, arm):
    from pex_bridge.adapters.codex import CodexStdioTransport

    four = _four_arm()

    def forbidden(*args, **kwargs):
        raise AssertionError("execution reached a side effect before safety validation")

    monkeypatch.setattr(four, "prepare_isolated_workspace", forbidden)
    monkeypatch.setattr(CodexStdioTransport, "start", forbidden)
    # A valid executable satisfies construction; the patched start must never run it.
    transport = CodexStdioTransport([sys.executable]) if arm.startswith("codex") else None
    with pytest.raises(RuntimeError, match="not a sandbox"):
        await four.run_live(
            arm,
            "pexbench_001_premature_stop",
            "blocked",
            transport=transport,
            workspace_root=tmp_path,
            worker_model="test-model",
            wait_cursor_stop=True,
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("command", ["prepare", "evaluate", "run"])
def test_cli_does_not_offer_an_unsafe_execution_bypass(tmp_path, monkeypatch, command):
    four = _four_arm()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "four_arm.py",
            command,
            "--arm",
            "cursor",
            "--task",
            "pexbench_001_premature_stop",
            "--run-id",
            "blocked",
            "--workspace",
            str(tmp_path),
            "--allow-live",
        ],
    )
    with pytest.raises(SystemExit, match="not a sandbox"):
        four.main()
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("disguised_as_fake", [False, True])
async def test_unknown_transport_cannot_skip_runtime_gate(tmp_path, monkeypatch, disguised_as_fake):
    from pex_bridge.adapters.codex import CodexAppServerTransport

    four = _four_arm()

    class UntrustedWrapper:
        async def request(self, *_args, **_kwargs):
            raise AssertionError("untrusted transport executed")

    class FakeSubclass(CodexAppServerTransport):
        async def request(self, *_args, **_kwargs):
            raise AssertionError("subclass transport executed")

    def forbidden(*args, **kwargs):
        raise AssertionError("unknown transport reached a workspace/evaluator effect")

    monkeypatch.setattr(four, "prepare_isolated_workspace", forbidden)
    monkeypatch.setattr(four.evaluator, "evaluate", forbidden)
    with pytest.raises(RuntimeError, match="unsupported benchmark transport"):
        await four.run_live(
            "codex", "pexbench_001_premature_stop", "blocked",
            transport=FakeSubclass() if disguised_as_fake else UntrustedWrapper(),
            workspace_root=tmp_path,
        )
    assert not list(tmp_path.iterdir())
