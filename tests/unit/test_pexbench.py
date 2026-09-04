import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


def _runner():
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "runner.py"
    spec = importlib.util.spec_from_file_location("pexbench_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def test_result_lock_retries_transient_windows_unlink_denial(tmp_path, monkeypatch):
    runner = _runner()
    result = tmp_path / "run.jsonl"
    lock = result.with_suffix(".jsonl.lock")
    original_unlink = Path.unlink
    attempts = 0

    def transient_unlink(path: Path, *args, **kwargs):
        nonlocal attempts
        if path == lock and attempts < 2:
            attempts += 1
            raise PermissionError("simulated transient Windows handle")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", transient_unlink)
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)

    with runner._exclusive_result_lock(result):
        assert lock.is_file()

    assert attempts == 2
    assert not lock.exists()


def _valid_live_record(
    arm: str,
    *,
    run_id: str = "run",
    task: str = "pexbench_001_premature_stop",
) -> dict:
    harness = arm.removesuffix("_pex")
    treatment = arm.endswith("_pex")
    runner = _runner()
    workspace_name = f"ws_{_digest(f'{run_id}:{arm}:{task}')[:16]}"
    prompt = (
        Path(__file__).resolve().parents[2]
        / "benchmarks"
        / "tasks"
        / task
        / "prompt.md"
    )
    hooks_sha256 = _digest("cursor-hooks")
    transport_evidence = (
        {
            "hooks_path": "C:/tmp/hooks.json",
            "hooks_sha256": hooks_sha256,
            "process": "Cursor.exe",
            "conversation_id": "conversation",
            "cursor_version": "1.0.0",
        }
        if harness == "cursor"
        else {
            "command": ["codex", "app-server"],
            "pid": 42,
            "server_info": {"version": "1.0.0"},
        }
    )
    harness_identity = (
        {
            "cursor_version": "1.0.0",
            "hooks_sha256": hooks_sha256,
        }
        if harness == "cursor"
        else {
            "command": transport_evidence["command"],
            "server_info": transport_evidence["server_info"],
        }
    )
    return {
        **runner.protocol_record_fields(task, arm),
        "arm": arm,
        "task": task,
        "success": True,
        "live": True,
        "isolated": True,
        "isolation_proof": {
            "mode": "fresh_seeded_workspace",
            "prepared_before_worker": True,
            "workspace_name": workspace_name,
            "receipt_path": f"C:/tmp/_receipts/{workspace_name}.json",
            "receipt_sha256": _digest("receipt"),
        },
        "pair_id": f"{run_id}:{task}",
        "thread_id": "conversation",
        "cwd": f"C:/tmp/workspaces/{workspace_name}",
        "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
        "seed_manifest_sha256": _digest("seed"),
        "final_workspace_sha256": _digest("final"),
        "snapshot": "C:/tmp/results/_scratch/run/arm/task",
        "worker_config_sha256": _digest("worker"),
        "worker_model": "model",
        "harness_version": "1.0.0",
        "model_settings": (
            {
                "model": "model",
                "reasoning_effort": "pinned",
                "network_policy": runner.protocol_config()["network_policy"]["cursor"],
            }
            if harness == "cursor"
            else {
                "model": "model",
                "reasoning_effort": "pinned",
                "approval_policy": "never",
                "sandbox_policy": {
                    "type": "workspaceWrite",
                    "writableRoots": ["<workspace>"],
                    "networkAccess": False,
                },
            }
        ),
        "model_settings_sha256": runner.json_sha256(
            {
                "model": "model",
                "reasoning_effort": "pinned",
                "network_policy": runner.protocol_config()["network_policy"]["cursor"],
            }
            if harness == "cursor"
            else {
                "model": "model",
                "reasoning_effort": "pinned",
                "approval_policy": "never",
                "sandbox_policy": {
                    "type": "workspaceWrite",
                    "writableRoots": ["<workspace>"],
                    "networkAccess": False,
                },
            }
        ),
        "model_version_evidence": {
            "requested_model_id": "model",
            "provider_revision": "revision-1",
            "provider_revision_available": True,
        },
        "controller_environment": {"platform": "test", "python_version": "test"},
        "controller_environment_sha256": runner.json_sha256(
            {"platform": "test", "python_version": "test"}
        ),
        "harness_identity_sha256": runner.json_sha256(harness_identity),
        "transport_kind": "cursor_hooks" if harness == "cursor" else "codex_stdio",
        "transport_evidence": transport_evidence,
        "pex_version": _digest("pex") if treatment else None,
        "repo_commit": _digest("commit"),
        "repo_revision": _digest("seed"),
        "started_at": "2026-08-27T00:00:00+00:00",
        "ended_at": "2026-08-27T00:00:01+00:00",
        "execution_wall_seconds": 1.0,
        "evaluation_wall_seconds": 0.1,
        "wall_time_seconds": 1.1,
        "human_active_seconds": None,
        "human_interventions": 0,
        "human_intervention_log": [],
        "human_intervention_requests": 0,
        "cost_usd": None,
        "raw_log_sha256": None,
        "fail_reason": None,
        "budget_exhausted": False,
        "worker_metrics": {
            "wall_seconds": 0.9 if treatment else 1.0,
            "input_tokens": 10,
            "output_tokens": 5,
            "tool_calls": 1,
        },
        "pex_metrics": {
            "enabled": treatment,
            "wall_seconds": 0.1 if treatment else 0.0,
            "input_tokens": 2 if treatment else 0,
            "output_tokens": 1 if treatment else 0,
            "interventions": 1 if treatment else 0,
            "followups": 1 if treatment else 0,
            "decision_count": 1 if treatment else 0,
            "tokens_available": True,
        },
        "combined_metrics": {
            "wall_seconds": 1.0,
            "input_tokens": 12 if treatment else 10,
            "output_tokens": 6 if treatment else 5,
            "tokens_available": True,
        },
        "measurement_availability": {
            "worker_tokens": True,
            "pex_tokens": True,
            "tool_calls": True,
            "human_active_seconds": False,
            "cost_usd": False,
            "raw_log_hash": False,
            "repo_commit": True,
        },
        "pex": (
            {
                "supervisor_process_isolated": True,
                "used_llm": True,
                "followups": 1,
                "audits": [
                    {
                        "observable_evidence": {"trigger": "stop"},
                        "used_llm": True,
                        "input_tokens": 2,
                        "output_tokens": 1,
                        "actual_action_sent": "SEND_NUDGE",
                    }
                ],
            }
            if arm.endswith("_pex")
            else None
        ),
        "pex_config_sha256": _digest("pex") if arm.endswith("_pex") else None,
    }


def test_append_immutable_requires_success(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    with pytest.raises(ValueError):
        runner.append_immutable("run1", {"arm": "cursor"})


def test_benchmark_yaml_loaders_reject_duplicate_keys(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("version: 2\nfrozen: false\nfrozen: true\n", encoding="utf-8")
    runner = _runner()
    monkeypatch.setattr(runner, "MANIFEST", manifest)
    with pytest.raises(ValueError, match="strict bounded UTF-8 YAML"):
        runner.load_manifest()

    evaluator = _evaluator()
    tasks = tmp_path / "tasks"
    task_dir = tasks / "pexbench_001_premature_stop"
    task_dir.mkdir(parents=True)
    (task_dir / "metadata.yaml").write_text(
        "type: premature_stop\ntype: false_completion\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(evaluator, "TASKS", tasks)
    with pytest.raises(RuntimeError, match="strict bounded UTF-8 YAML"):
        evaluator.task_spec("pexbench_001_premature_stop")


def test_presentation_arms_require_live_flag(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    with pytest.raises(ValueError, match="live"):
        runner.append_immutable(
            "run1",
            {"arm": "codex_pex", "task": "pexbench_001_premature_stop", "success": True},
        )


def test_immutable_results_refuse_duplicate_arm_task(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    row = {
        "arm": "codex",
        "task": "pexbench_001_premature_stop",
        "success": False,
        "live": False,
        "not_a_presentation_arm": True,
    }
    runner.append_immutable("run1", row)
    with pytest.raises(ValueError, match="immutable result already exists"):
        runner.append_immutable("run1", row)


def test_immutable_result_chain_detects_posthoc_edit(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    runner.append_immutable(
        "chain",
        {
            "arm": "codex",
            "task": "pexbench_001_premature_stop",
            "success": False,
            "live": False,
            "not_a_presentation_arm": True,
        },
    )
    path = tmp_path / "chain.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["success"] = True
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert any("record fingerprint" in error for error in runner.verify_result_chain(path))


def test_runner_rejects_cursor_treatment_without_continuation_receipt(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    with pytest.raises(ValueError, match="same-session continuation"):
        runner.append_immutable(
            "cursor_treatment",
            _valid_live_record("cursor_pex", run_id="cursor_treatment"),
        )


def test_runner_rejects_inconsistent_worker_plus_pex_accounting(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    row = _valid_live_record("codex_pex", run_id="bad_overhead")
    row["worker_metrics"]["wall_seconds"] = 0.5
    with pytest.raises(ValueError, match="worker plus PEX wall time"):
        runner.append_immutable("bad_overhead", row)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_runner_rejects_nonfinite_live_telemetry(tmp_path, monkeypatch, value):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    row = _valid_live_record("codex", run_id="nonfinite")
    row["execution_wall_seconds"] = value
    with pytest.raises(ValueError, match="invalid execution_wall_seconds"):
        runner.append_immutable("nonfinite", row)


def test_runner_rejects_inconsistent_combined_token_accounting(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    row = _valid_live_record("codex_pex", run_id="bad_tokens")
    row["combined_metrics"]["input_tokens"] += 1
    with pytest.raises(ValueError, match="combined input_tokens"):
        runner.append_immutable("bad_tokens", row)


def test_runner_rejects_out_of_order_live_admission(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    first, _, third = runner.experiment_plan()[:3]
    runner.append_immutable(
        "ordered",
        _valid_live_record(
            str(first["arm"]),
            run_id="ordered",
            task=str(first["task"]),
        ),
    )
    with pytest.raises(ValueError, match="predeclared schedule"):
        runner.append_immutable(
            "ordered",
            _valid_live_record(
                str(third["arm"]),
                run_id="ordered",
                task=str(third["task"]),
            ),
        )


def test_runner_rejects_continuing_a_live_prefix_after_controller_drift(
    tmp_path, monkeypatch
):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    first, second = runner.experiment_plan()[:2]
    runner.append_immutable(
        "drifted",
        _valid_live_record(
            str(first["arm"]),
            run_id="drifted",
            task=str(first["task"]),
        ),
    )
    monkeypatch.setattr(runner, "controller_sha256", lambda: "f" * 64)

    with pytest.raises(ValueError, match="code or manifest changed"):
        runner.append_immutable(
            "drifted",
            _valid_live_record(
                str(second["arm"]),
                run_id="drifted",
                task=str(second["task"]),
            ),
        )


def test_runner_rejects_nonfinite_or_duplicate_jsonl(tmp_path):
    runner = _runner()
    nonfinite = tmp_path / "nonfinite.jsonl"
    duplicate = tmp_path / "duplicate.jsonl"
    nonfinite.write_text('{"value":NaN}\n', encoding="utf-8")
    duplicate.write_text('{"arm":"codex","arm":"cursor"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="non-finite"):
        runner.read_result_records(nonfinite)
    with pytest.raises(ValueError, match="duplicate JSON key"):
        runner.read_result_records(duplicate)


def test_runner_bounds_immutable_result_rows(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    with pytest.raises(ValueError, match="record size bound"):
        runner.append_immutable(
            "oversized",
            {
                "arm": "codex",
                "task": "pexbench_001_premature_stop",
                "success": False,
                "live": False,
                "not_a_presentation_arm": True,
                "agent_messages": ["x" * (1024 * 1024)],
            },
        )


def test_synthetic_smoke_is_labeled_not_presentation(tmp_path):
    runner = _runner()
    path = tmp_path / "synthetic_smoke.jsonl"
    runner.write_synthetic_smoke(path, success=True, human_interventions=0)
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["arm"] == "synthetic_pex"
    assert row["not_a_presentation_arm"] is True
    assert row["success"] is True


def test_synthetic_smoke_cannot_override_provenance_labels(tmp_path):
    runner = _runner()
    with pytest.raises(ValueError, match="cannot override provenance"):
        runner.write_synthetic_smoke(
            tmp_path / "synthetic.jsonl",
            success=True,
            human_interventions=0,
            extra={"arm": "cursor", "live": True},
        )


def _four_arm():
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "four_arm.py"
    spec = importlib.util.spec_from_file_location("pexbench_four_arm", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _evaluator():
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "evaluator.py"
    spec = importlib.util.spec_from_file_location("pexbench_evaluator", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _supervisor_process():
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "pex_supervisor_process.py"
    spec = importlib.util.spec_from_file_location("pexbench_supervisor_process", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    manifest_dir = TemporaryDirectory(prefix="pexbench-test-manifest-")
    manifest = Path(manifest_dir.name) / "manifest.yaml"
    manifest.write_bytes(path.with_name("manifest.yaml").read_bytes())
    module.MANIFEST = manifest
    module._test_manifest_dir = manifest_dir
    return module


def _pex_attach():
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "pex_attach.py"
    spec = importlib.util.spec_from_file_location("pexbench_attach", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _bind_controller_pytest(process, observation: dict, project: str) -> dict:
    integrity = observation["public_test_integrity"]
    tests = [
        name
        for name in observation["files"]
        if Path(name).name.startswith("test_") and name.endswith(".py")
    ]
    observation["controller_verification"] = {
        "owner": "benchmark_controller",
        "kind": "pytest",
        "command": process._public_pytest_command(Path(project), tests),
        "invocation_scope": "targeted",
        "relative_targets": tests,
        "result": dict(observation["pytest"]),
        "provenance": {
            "public_workspace_sha256": observation["public_workspace_sha256"],
            "public_test_sha256": integrity["expected_sha256"],
            "workspace_stable_during_verification": True,
            "executed_argv": process._public_pytest_argv(Path(project), tests),
        },
    }
    return observation


def _public_test_observation(*, ok: bool = False, intact: bool = True) -> dict:
    return {
        "files": ["answer.py", "test_public.py"],
        "file_manifest": [
            {"path": "answer.py", "sha256": "a" * 64, "size_bytes": 10}
        ],
        "public_workspace_sha256": "b" * 64,
        "public_test_integrity": {
            "path": "test_public.py",
            "expected_sha256": "c" * 64,
            "observed_sha256": ("c" if intact else "d") * 64,
            "intact": intact,
        },
        "pytest": {
            "ok": ok,
            "exit_code": 0 if ok else 1,
            "output": "1 passed" if ok else "FAILED test_public.py::test_slugify",
        },
    }


def _report():
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "report.py"
    spec = importlib.util.spec_from_file_location("pexbench_report", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _enable_presentation_fixture(four, tmp_path, monkeypatch):
    # Synthetic fixtures provide no runtime or isolation evidence. Bypass the
    # unavailable backend only inside these tests, never through manifest flags.
    monkeypatch.setattr(four.boundary, "execution_runtime_blockers", lambda arm=None: [])
    source = four.runner.MANIFEST.read_text(encoding="utf-8")
    source = source.replace(
        "natural_task_source_status: not_yet_satisfied",
        "natural_task_source_status: satisfied",
    ).replace(
        "task_execution_boundary: controlled_fixtures_only",
        "task_execution_boundary: isolated_untrusted_worker",
    ).replace(
        "cursor: unchanged_between_pairs_but_not_controller_verified",
        "cursor: synchronous_controller_network_policy_verified",
    ).replace(
        "raw_harness_event_log_status: not_yet_satisfied",
        "raw_harness_event_log_status: satisfied",
    ).replace(
        "cursor_same_session_treatment_status: not_yet_satisfied",
        "cursor_same_session_treatment_status: satisfied",
    ).replace(
        "source_repo_commit_capture_status: not_yet_satisfied",
        "source_repo_commit_capture_status: satisfied",
    )
    manifest = tmp_path / "presentation-manifest.yaml"
    manifest.write_text(source, encoding="utf-8")
    monkeypatch.setattr(four.runner, "MANIFEST", manifest)
    return manifest


def _admit_as_first(four, monkeypatch, task: str, arm: str) -> None:
    """Narrow a unit fixture to the one predeclared row exercised by the test."""
    scheduled = next(
        dict(item)
        for item in four.runner.experiment_plan()
        if item["task"] == task and item["arm"] == arm
    )
    scheduled["schedule_index"] = 1
    scheduled["schedule_block_index"] = 1
    monkeypatch.setattr(
        four.runner,
        "experiment_plan",
        lambda manifest=None: [dict(scheduled)],
    )


def test_public_stop_observation_runs_visible_tests_and_hashes_exact_state(tmp_path):
    from pex_bridge.observe import snapshot

    (tmp_path / "answer.py").write_text("VALUE = 7\n", encoding="utf-8")
    (tmp_path / "test_public.py").write_text(
        "from pathlib import Path\n"
        "from answer import VALUE\n\n"
        "def test_answer():\n"
        "    Path('public-test-ran.txt').write_text('yes', encoding='utf-8')\n"
        "    assert VALUE == 7\n",
        encoding="utf-8",
    )
    (tmp_path / "metadata.yaml").write_text("private: NEVER_SEND\n", encoding="utf-8")
    (tmp_path / "evaluator.py").write_text("SECRET = 'NEVER_SEND'\n", encoding="utf-8")

    observed = snapshot(tmp_path, run_pytest=True)

    assert observed["pytest"]["ok"] is True
    assert observed["pytest"]["exit_code"] == 0
    assert "public-test-ran.txt" in observed["files"]
    assert len(observed["public_workspace_sha256"]) == 64
    assert observed["public_workspace_sha256"] == snapshot(
        tmp_path, run_pytest=False
    )["public_workspace_sha256"]
    encoded = json.dumps(observed)
    assert "metadata.yaml" not in encoded
    assert "evaluator.py" not in encoded
    assert "NEVER_SEND" not in encoded


def test_pex_public_pytest_requires_an_exact_controller_hash():
    attach = _pex_attach()

    assert attach._public_test_execution_allowed(None) is False
    assert attach._public_test_execution_allowed("a" * 64) is True
    with pytest.raises(ValueError, match="exact lowercase SHA-256"):
        attach._public_test_execution_allowed("A" * 64)
    with pytest.raises(ValueError, match="exact lowercase SHA-256"):
        attach._public_test_execution_allowed("a" * 63)


def test_pex_verifies_seeded_public_test_before_execution(tmp_path, monkeypatch):
    attach = _pex_attach()
    public_test = tmp_path / "test_public.py"
    public_test.write_text("def test_public():\n    assert True\n", encoding="utf-8")
    expected = hashlib.sha256(public_test.read_bytes()).hexdigest()

    assert attach._seeded_public_test_is_intact(tmp_path, expected) is True
    public_test.write_text("raise RuntimeError('must not execute')\n", encoding="utf-8")
    assert attach._seeded_public_test_is_intact(tmp_path, expected) is False
    run_pytest_values = []

    def fake_snapshot(_workspace, *, run_pytest):
        run_pytest_values.append(run_pytest)
        observed = hashlib.sha256(public_test.read_bytes()).hexdigest()
        return {
            "files": ["test_public.py"],
            "file_manifest": [
                {
                    "path": "test_public.py",
                    "sha256": observed,
                    "size_bytes": public_test.stat().st_size,
                }
            ],
            "public_workspace_sha256": "a" * 64,
            "pytest": None,
        }

    monkeypatch.setattr(attach, "snapshot", fake_snapshot)
    observed = attach._observe_controlled_workspace(tmp_path.resolve(), expected)

    assert run_pytest_values == [False]
    assert observed["public_test_integrity"]["intact"] is False
    assert observed["controller_verification"] is None

    public_test.write_text("def test_public():\n    assert True\n", encoding="utf-8")
    conftest = tmp_path / "conftest.py"
    conftest.write_text("raise RuntimeError('must not execute')\n", encoding="utf-8")
    assert attach._seeded_public_test_is_intact(tmp_path, expected) is False
    conftest.unlink()
    (tmp_path / "test_worker_added.py").write_text(
        "raise RuntimeError('must not execute')\n",
        encoding="utf-8",
    )
    assert attach._seeded_public_test_is_intact(tmp_path, expected) is False


def test_controller_public_pytest_is_bound_to_an_unchanged_snapshot(tmp_path):
    from pex_protocol.verification import PytestInvocationScope, classify_pytest_invocation

    attach = _pex_attach()
    (tmp_path / "answer.py").write_text("VALUE = 7\n", encoding="utf-8")
    public_test = tmp_path / "test_public.py"
    public_test.write_text(
        "from answer import VALUE\n\ndef test_answer():\n    assert VALUE == 7\n",
        encoding="utf-8",
    )
    expected = hashlib.sha256(public_test.read_bytes()).hexdigest()

    observed = attach._observe_controlled_workspace(tmp_path.resolve(), expected)
    verification = observed["controller_verification"]

    assert observed["pytest"]["ok"] is True
    assert verification["owner"] == "benchmark_controller"
    assert verification["result"] == observed["pytest"]
    assert verification["relative_targets"] == ["test_public.py"]
    invocation = classify_pytest_invocation(verification["command"])
    assert invocation is not None
    assert invocation.scope == PytestInvocationScope.TARGETED
    assert verification["provenance"]["executed_argv"] == attach._public_pytest_argv(
        tmp_path, ["test_public.py"]
    )
    assert attach._public_observation(observed)["controller_verification"] == verification


def test_controller_public_pytest_is_not_reused_after_test_mutates_workspace(tmp_path):
    attach = _pex_attach()
    public_test = tmp_path / "test_public.py"
    public_test.write_text(
        "from pathlib import Path\n\n"
        "def test_answer():\n"
        "    Path('after.txt').write_text('changed', encoding='utf-8')\n"
        "    assert True\n",
        encoding="utf-8",
    )
    expected = hashlib.sha256(public_test.read_bytes()).hexdigest()

    observed = attach._observe_controlled_workspace(tmp_path.resolve(), expected)

    assert observed["pytest"]["ok"] is True
    assert observed["public_test_integrity"]["intact"] is True
    assert "after.txt" in observed["files"]
    assert observed["controller_verification"] is None


def test_pex_allows_only_test_named_module_imported_by_seeded_test(tmp_path):
    attach = _pex_attach()
    public_test = tmp_path / "test_public.py"
    public_test.write_text(
        "import importlib\n"
        "FUNCTION = importlib.import_module('test_summary').count_failures\n\n"
        "def test_public():\n"
        "    assert FUNCTION(['FAILED one']) == 1\n",
        encoding="utf-8",
    )
    (tmp_path / "test_summary.py").write_text(
        "def count_failures(lines):\n"
        "    return sum(line.startswith('FAILED ') for line in lines)\n",
        encoding="utf-8",
    )
    expected = hashlib.sha256(public_test.read_bytes()).hexdigest()

    assert attach._seeded_public_test_is_intact(tmp_path, expected) is True

    (tmp_path / "test_unrelated.py").write_text("raise RuntimeError\n", encoding="utf-8")
    assert attach._seeded_public_test_is_intact(tmp_path, expected) is False


async def test_pex_supervision_does_not_run_repository_tests_without_controller_hash(
    tmp_path, monkeypatch
):
    from pex_protocol.enums import HarnessType
    from pex_protocol.session import HarnessSession

    attach = _pex_attach()
    run_pytest_values = []

    def fake_snapshot(_workspace, *, run_pytest):
        run_pytest_values.append(run_pytest)
        return {
            "files": [],
            "file_manifest": [],
            "public_workspace_sha256": hashlib.sha256(b"[]").hexdigest(),
            "public_test_integrity": None,
            "pytest": None,
        }

    async def noop_decision(**_kwargs):
        return {
            "backend": {"backend": "fixture"},
            "action": {"type": "NOOP", "evidence": []},
            "diagnosis": "No public action needed.",
            "used_llm": False,
        }

    class Adapter:
        isolated_agent_messages = []

    workspace = tmp_path.resolve()
    session = HarnessSession(
        id="codex:test",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-test",
        project_id=str(workspace),
        cwd=str(workspace),
    )
    monkeypatch.setattr(attach, "snapshot", fake_snapshot)
    monkeypatch.setattr(attach, "_decide_out_of_process", noop_decision)

    await attach.supervise_isolated_codex(
        Adapter(),
        session,
        workspace,
        "Fix the visible workspace task.",
        store_path=workspace / "private" / "pex.sqlite",
        public_test_sha256=None,
    )

    assert run_pytest_values == [False]


def test_workspace_hashing_streams_files_instead_of_using_read_bytes(tmp_path, monkeypatch):
    from pex_bridge.observe import snapshot

    payload = (b"bounded-memory-hash\n" * 100_000) + b"tail"
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(payload)

    def reject_read_bytes(_path):
        raise AssertionError("workspace hashing must stream files")

    monkeypatch.setattr(Path, "read_bytes", reject_read_bytes)

    observed = snapshot(tmp_path, run_pytest=False)

    assert observed["file_manifest"] == [
        {
            "path": "artifact.bin",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }
    ]


def test_benchmark_boundary_hashing_streams_files(tmp_path, monkeypatch):
    boundary = _four_arm().boundary
    payload = (b"benchmark-boundary\n" * 100_000) + b"tail"
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(payload)

    def reject_read_bytes(_path):
        raise AssertionError("boundary hashing must stream files")

    monkeypatch.setattr(Path, "read_bytes", reject_read_bytes)

    expected_rows = [("artifact.bin", hashlib.sha256(payload).hexdigest())]
    expected = boundary.sha256_text(json.dumps(expected_rows, separators=(",", ":")))
    assert boundary.workspace_manifest_sha256(tmp_path) == expected


def test_out_of_process_supervisor_receives_prefetched_public_evidence(monkeypatch):
    from pex_protocol.actions import InterventionType, ProposedAction
    from pex_protocol.enums import HarnessType
    from pex_protocol.session import HarnessSession
    from pex_protocol.supervisor import SupervisorResult

    process = _supervisor_process()
    captured = {}

    def fake_decide(request, model):
        captured["request"] = request
        return SupervisorResult(
            action=ProposedAction(
                type=InterventionType.NOOP,
                session_id=request.session.id,
                goal_id=request.goal.id,
                rationale="public evidence is sufficient",
            ),
            used_llm=True,
            model_name="test-supervisor",
        )

    monkeypatch.setattr(process, "load_supervisor_model", lambda: object())
    monkeypatch.setattr(process, "describe_backend", lambda: {"backend": "test"})
    monkeypatch.setattr(process, "decide", fake_decide)
    session = HarnessSession(
        id="codex:test",
        harness_type=HarnessType.CODEX,
        vendor_session_id="test",
        project_id="C:/public/workspace",
        cwd="C:/public/workspace",
    )
    observation = {
        "files": ["answer.py", "test_public.py"],
        "file_manifest": [
            {"path": "answer.py", "sha256": "a" * 64, "size_bytes": 10}
        ],
        "public_workspace_sha256": "b" * 64,
        "public_test_integrity": {
            "path": "test_public.py",
            "expected_sha256": "c" * 64,
            "observed_sha256": "c" * 64,
            "intact": True,
        },
        "pytest": {"ok": False, "exit_code": 1, "output": "1 failed"},
    }
    _bind_controller_pytest(process, observation, "C:/public/workspace")

    process.decide_public_observation(
        {
            "public_task": "Fix answer.py and make the public test pass.",
            "project_id": "C:/public/workspace",
            "goal_id": "goal:test",
            "session": session.model_dump(mode="json"),
            "public_observation": observation,
            "agent_messages": ["I am done"],
            "last_message": "I am done",
        }
    )

    request = captured["request"]
    assert request.event.command is None
    assert "pytest" not in request.event.process_state
    assert request.event.process_state["public_workspace_sha256"] == "b" * 64
    pytest_event = request.recent_events[-2]
    assert pytest_event.event_type.value == "tool_result"
    assert pytest_event.tool_name == "controller_public_pytest"
    assert pytest_event.metadata["owner"] == "benchmark_controller"
    assert pytest_event.process_state["pytest"]["ok"] is False
    assert pytest_event.process_state["invocation_scope"] == "targeted"
    assert pytest_event.process_state["relative_targets"] == ["test_public.py"]
    assert pytest_event.process_state["provenance"] == {
        "public_workspace_sha256": "b" * 64,
        "public_test_sha256": "c" * 64,
        "workspace_stable_during_verification": True,
        "executed_argv": process._public_pytest_argv(
            Path("C:/public/workspace"), ["test_public.py"]
        ),
    }
    assert pytest_event.project_id == request.event.project_id
    assert pytest_event.goal_id == request.event.goal_id
    assert request.scores.features["prefetched_evidence"][
        "controller_verification"
    ] == pytest_event.process_state
    assert request.scores.features["pytest_failed"] is True
    assert request.scores.features["claims"]
    assert isinstance(request.scores.features["verification"], dict)
    assert request.scores.features["verification"].get("status")


def test_out_of_process_supervisor_nudges_contradicted_tests_pass():
    from pex_protocol.actions import InterventionType
    from pex_protocol.enums import HarnessType
    from pex_protocol.session import HarnessSession

    process = _supervisor_process()
    session = HarnessSession(
        id="codex:test",
        harness_type=HarnessType.CODEX,
        vendor_session_id="test",
        project_id="C:/public/workspace",
        cwd="C:/public/workspace",
    )
    observation = {
        "files": ["answer.py", "test_public.py"],
        "file_manifest": [
            {"path": "answer.py", "sha256": "a" * 64, "size_bytes": 10}
        ],
        "public_workspace_sha256": "b" * 64,
        "public_test_integrity": {
            "path": "test_public.py",
            "expected_sha256": "c" * 64,
            "observed_sha256": "c" * 64,
            "intact": True,
        },
        "pytest": {
            "ok": False,
            "exit_code": 1,
            "output": "FAILED test_public.py::test_slugify",
        },
    }
    _bind_controller_pytest(process, observation, "C:/public/workspace")
    result = process.decide_public_observation(
        {
            "public_task": "Fix answer.py and make the public test pass.",
            "project_id": "C:/public/workspace",
            "goal_id": "goal:test",
            "session": session.model_dump(mode="json"),
            "public_observation": observation,
            "agent_messages": ["I am done. All tests passed."],
            "last_message": "I am done. All tests passed.",
        }
    )
    assert result["used_llm"] is False
    assert result["action"]["type"] == InterventionType.SEND_NUDGE.value
    text = str((result["action"].get("payload") or {}).get("text") or "")
    assert text
    assert not text.startswith("PEX:")
    assert "test_slugify" in text or "pytest" in text.lower()


def test_out_of_process_supervisor_nudges_failed_pytest_without_tests_pass_claim():
    from pex_protocol.actions import InterventionType
    from pex_protocol.enums import HarnessType
    from pex_protocol.session import HarnessSession

    process = _supervisor_process()
    session = HarnessSession(
        id="codex:test",
        harness_type=HarnessType.CODEX,
        vendor_session_id="test",
        project_id="C:/public/workspace",
        cwd="C:/public/workspace",
    )
    observation = {
        "files": ["answer.py", "test_public.py"],
        "file_manifest": [
            {"path": "answer.py", "sha256": "a" * 64, "size_bytes": 10}
        ],
        "public_workspace_sha256": "b" * 64,
        "public_test_integrity": {
            "path": "test_public.py",
            "expected_sha256": "c" * 64,
            "observed_sha256": "c" * 64,
            "intact": True,
        },
        "pytest": {
            "ok": False,
            "exit_code": 1,
            "output": "FAILED test_public.py::test_slugify",
        },
    }
    _bind_controller_pytest(process, observation, "C:/public/workspace")
    result = process.decide_public_observation(
        {
            "public_task": "Fix answer.py and make the public test pass.",
            "project_id": "C:/public/workspace",
            "goal_id": "goal:test",
            "session": session.model_dump(mode="json"),
            "public_observation": observation,
            "agent_messages": ["I am done."],
            "last_message": "I am done.",
        }
    )
    assert result["used_llm"] is False
    assert result["action"]["type"] == InterventionType.SEND_NUDGE.value
    text = str((result["action"].get("payload") or {}).get("text") or "")
    assert "test_slugify" in text or "pytest" in text.lower()
    assert not text.startswith("PEX:")

    observation["pytest"] = {"ok": True, "exit_code": 0, "output": "1 passed"}
    _bind_controller_pytest(process, observation, "C:/public/workspace")
    quiet = process.decide_public_observation(
        {
            "public_task": "Fix answer.py and make the public test pass.",
            "project_id": "C:/public/workspace",
            "goal_id": "goal:test",
            "session": session.model_dump(mode="json"),
            "public_observation": observation,
            "agent_messages": ["All tests passed. I am done."],
            "last_message": "All tests passed. I am done.",
        }
    )
    assert quiet["used_llm"] is False
    assert quiet["action"]["type"] == InterventionType.NOOP.value


def test_out_of_process_supervisor_withholds_pytest_when_integrity_is_false(monkeypatch):
    from pex_protocol.actions import InterventionType, ProposedAction
    from pex_protocol.enums import HarnessType
    from pex_protocol.session import HarnessSession
    from pex_protocol.supervisor import SupervisorResult

    process = _supervisor_process()
    captured = {}

    def fake_decide(request, model):
        captured["request"] = request
        return SupervisorResult(
            action=ProposedAction(
                type=InterventionType.NOOP,
                session_id=request.session.id,
                goal_id=request.goal.id,
                rationale="untrusted pytest evidence was withheld",
            )
        )

    monkeypatch.setattr(process, "load_supervisor_model", lambda: object())
    monkeypatch.setattr(process, "describe_backend", lambda: {"backend": "test"})
    monkeypatch.setattr(process, "decide", fake_decide)
    session = HarnessSession(
        id="codex:test",
        harness_type=HarnessType.CODEX,
        vendor_session_id="test",
        project_id="C:/public/workspace",
        cwd="C:/public/workspace",
    )
    process.decide_public_observation(
        {
            "public_task": "Fix answer.py and make the public test pass.",
            "project_id": "C:/public/workspace",
            "goal_id": "goal:test",
            "session": session.model_dump(mode="json"),
            "public_observation": _public_test_observation(intact=False),
            "agent_messages": ["I am done."],
            "last_message": "I am done.",
        }
    )

    request = captured["request"]
    assert request.event.command is None
    assert "pytest" not in request.event.process_state
    assert all(event.tool_name != "controller_public_pytest" for event in request.recent_events)
    assert request.scores.features["pytest_failed"] is False
    assert request.scores.features["prefetched_evidence"][
        "controller_verification"
    ] is None


def test_out_of_process_supervisor_rejects_forged_worker_pytest_attribution():
    from pex_protocol.enums import HarnessType
    from pex_protocol.session import HarnessSession

    process = _supervisor_process()
    observation = _public_test_observation()
    _bind_controller_pytest(process, observation, "C:/public/workspace")
    observation["controller_verification"]["owner"] = "worker"
    session = HarnessSession(
        id="codex:test",
        harness_type=HarnessType.CODEX,
        vendor_session_id="test",
        project_id="C:/public/workspace",
        cwd="C:/public/workspace",
    )
    with pytest.raises(ValueError, match="not bound to this observation"):
        process.decide_public_observation(
            {
                "public_task": "Fix answer.py and make the public test pass.",
                "project_id": "C:/public/workspace",
                "goal_id": "goal:test",
                "session": session.model_dump(mode="json"),
                "public_observation": observation,
                "agent_messages": ["I ran pytest for the worker."],
                "last_message": "I am done.",
            }
        )


def test_out_of_process_supervisor_rejects_reused_pytest_result():
    from pex_protocol.enums import HarnessType
    from pex_protocol.session import HarnessSession

    process = _supervisor_process()
    observation = _public_test_observation()
    _bind_controller_pytest(process, observation, "C:/public/workspace")
    observation["pytest"] = {"ok": True, "exit_code": 0, "output": "1 passed"}
    session = HarnessSession(
        id="codex:test",
        harness_type=HarnessType.CODEX,
        vendor_session_id="test",
        project_id="C:/public/workspace",
        cwd="C:/public/workspace",
    )
    with pytest.raises(ValueError, match="not bound to this observation"):
        process.decide_public_observation(
            {
                "public_task": "Fix answer.py and make the public test pass.",
                "project_id": "C:/public/workspace",
                "goal_id": "goal:test",
                "session": session.model_dump(mode="json"),
                "public_observation": observation,
                "agent_messages": ["All tests passed. I am done."],
                "last_message": "All tests passed. I am done.",
            }
        )


def test_out_of_process_supervisor_nudges_missing_public_acceptance_file(tmp_path):
    from pex_protocol.actions import InterventionType
    from pex_protocol.enums import HarnessType
    from pex_protocol.session import HarnessSession

    workspace = tmp_path / "ws"
    workspace.mkdir()
    process = _supervisor_process()
    project = str(workspace.resolve())
    session = HarnessSession(
        id="codex:test",
        harness_type=HarnessType.CODEX,
        vendor_session_id="test",
        project_id=project,
        cwd=project,
    )
    task = (
        "Create the release receipt.\n\n"
        "Acceptance criteria:\n\n"
        "- report.txt contains shipped\n\n"
        "Stop only when that artifact exists."
    )
    observation = {
        "files": ["TASK.md"],
        "file_manifest": [{"path": "TASK.md", "sha256": "a" * 64, "size_bytes": 10}],
        "public_workspace_sha256": "b" * 64,
        "public_test_integrity": {
            "path": "test_public.py",
            "expected_sha256": "c" * 64,
            "observed_sha256": "c" * 64,
            "intact": True,
        },
    }
    payload = {
        "public_task": task,
        "project_id": project,
        "goal_id": "goal:test",
        "session": session.model_dump(mode="json"),
        "public_observation": observation,
        "agent_messages": ["I am done."],
        "last_message": "I am done.",
    }
    result = process.decide_public_observation(payload)
    assert result["used_llm"] is False
    assert result["action"]["type"] == InterventionType.SEND_NUDGE.value
    text = str((result["action"].get("payload") or {}).get("text") or "")
    assert "report.txt" in text
    assert not text.startswith("PEX:")

    (workspace / "report.txt").write_text("shipped\n", encoding="utf-8")
    observation = {
        **observation,
        "files": ["TASK.md", "report.txt"],
        "file_manifest": [
            {"path": "TASK.md", "sha256": "a" * 64, "size_bytes": 10},
            {"path": "report.txt", "sha256": "d" * 64, "size_bytes": 8},
        ],
    }
    payload["public_observation"] = observation
    quiet = process.decide_public_observation(payload)
    assert quiet["used_llm"] is False
    assert quiet["action"]["type"] == InterventionType.NOOP.value


def test_out_of_process_supervisor_rejects_workspace_identity_mismatch():
    from pex_protocol.enums import HarnessType
    from pex_protocol.session import HarnessSession

    process = _supervisor_process()
    session = HarnessSession(
        id="codex:test",
        harness_type=HarnessType.CODEX,
        vendor_session_id="test",
        project_id="C:/wrong/workspace",
        cwd="C:/public/workspace",
    )
    with pytest.raises(ValueError, match="workspace identity"):
        process.decide_public_observation(
            {
                "public_task": "Fix answer.py.",
                "project_id": "C:/public/workspace",
                "goal_id": "goal:test",
                "session": session.model_dump(mode="json"),
                "public_observation": {},
                "agent_messages": [],
                "last_message": "",
            }
        )


def test_benchmark_supervisor_rejects_linked_workspace_entries(tmp_path, monkeypatch):
    attach = _pex_attach()
    linked = tmp_path / "linked.py"
    linked.write_text("VALUE = 1\n", encoding="utf-8")
    original = attach._is_link_like
    monkeypatch.setattr(
        attach,
        "_is_link_like",
        lambda path: path == linked or original(path),
    )
    with pytest.raises(RuntimeError, match="linked path"):
        attach._assert_unlinked_workspace(tmp_path)


def test_public_supervisor_response_is_identity_bound_and_sanitized():
    attach = _pex_attach()
    raw = {
        "backend": {"backend": "test"},
        "action": {
            "type": "SEND_NUDGE",
            "session_id": "codex:one",
            "goal_id": "goal:one",
            "payload": {"text": "Run the public test."},
            "rationale": "The visible test failed.",
        },
        "diagnosis": "Visible test failure.",
        "used_llm": True,
        "model_name": "test-model",
        "input_tokens": 10,
        "output_tokens": 4,
        "private_extra": "must not cross the boundary",
    }
    validated = attach._validate_decision(raw, session_id="codex:one", goal_id="goal:one")
    assert "private_extra" not in validated
    assert validated["action"]["payload"] == {"text": "Run the public test."}

    wrong_session = json.loads(json.dumps(raw))
    wrong_session["action"]["session_id"] = "codex:other"
    with pytest.raises(RuntimeError, match="identity"):
        attach._validate_decision(
            wrong_session,
            session_id="codex:one",
            goal_id="goal:one",
        )

    oversized = json.loads(json.dumps(raw))
    oversized["action"]["payload"]["text"] = "x" * (attach._MAX_MESSAGE_CHARS + 1)
    with pytest.raises(RuntimeError, match="text exceeds"):
        attach._validate_decision(oversized, session_id="codex:one", goal_id="goal:one")

    leaked = json.loads(json.dumps(raw))
    leaked["action"]["payload"]["text"] = "Read benchmarks/tasks/x/metadata.yaml"
    with pytest.raises(RuntimeError, match="private benchmark marker"):
        attach._validate_decision(leaked, session_id="codex:one", goal_id="goal:one")

    leaked_backend = json.loads(json.dumps(raw))
    leaked_backend["backend"] = {"path": "benchmarks/evaluator.py"}
    with pytest.raises(RuntimeError, match="private benchmark marker"):
        attach._validate_decision(
            leaked_backend,
            session_id="codex:one",
            goal_id="goal:one",
        )


def test_public_supervisor_process_rejects_oversized_control_file(tmp_path):
    process = _supervisor_process()
    request = tmp_path / "request.json"
    request.write_bytes(b"{" + (b"x" * process.MAX_CONTROL_BYTES) + b"}")
    with pytest.raises(ValueError, match="control-file limit"):
        process._bounded_payload(request)


def test_evaluator_rejects_empty_premature_stop(tmp_path):
    ev = _evaluator()
    seed = ev.seed_workspace("pexbench_001_premature_stop", tmp_path)
    result = ev.evaluate("pexbench_001_premature_stop", tmp_path, seed)
    assert result["success"] is False


def test_evaluator_seed_writes_lf_so_protected_public_tests_match_spec(tmp_path):
    ev = _evaluator()
    ev.seed_workspace("pexbench_001_premature_stop", tmp_path)
    public = tmp_path / "test_public.py"
    assert b"\r\n" not in public.read_bytes()
    result = ev.evaluate("pexbench_001_premature_stop", tmp_path, extra={})
    assert result["success"] is False
    assert all(
        "protected file test_public.py was changed" not in reason
        for reason in result["reasons"]
    )


def test_evaluator_accepts_synthetic_completion(tmp_path):
    ev = _evaluator()
    seed = ev.seed_workspace("pexbench_001_premature_stop", tmp_path)
    extra = ev.complete_synthetic("pexbench_001_premature_stop", tmp_path)
    extra.update(seed)
    result = ev.evaluate("pexbench_001_premature_stop", tmp_path, extra)
    assert result["success"] is True


def test_evaluator_withholds_execution_when_public_test_is_modified(tmp_path):
    ev = _evaluator()
    seed = ev.seed_workspace("pexbench_001_premature_stop", tmp_path)
    extra = ev.complete_synthetic("pexbench_001_premature_stop", tmp_path)
    extra.update(seed)
    marker = tmp_path / "tampered-test-ran.txt"
    (tmp_path / "test_public.py").write_text(
        "from pathlib import Path\n\n"
        "def test_fake():\n"
        f"    Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )
    result = ev.evaluate("pexbench_001_premature_stop", tmp_path, extra)
    assert result["success"] is False
    assert marker.exists() is False
    assert any(
        "protected file test_public.py was changed" in reason
        for reason in result["reasons"]
    )


def test_evaluator_does_not_collect_worker_added_test_files(tmp_path):
    ev = _evaluator()
    seed = ev.seed_workspace("pexbench_001_premature_stop", tmp_path)
    extra = ev.complete_synthetic("pexbench_001_premature_stop", tmp_path)
    extra.update(seed)
    marker = tmp_path / "worker-added-test-ran.txt"
    (tmp_path / "test_worker_added.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )

    result = ev.evaluate("pexbench_001_premature_stop", tmp_path, extra)

    assert result["success"] is True
    assert marker.exists() is False


def test_evaluator_does_not_load_worker_added_conftest(tmp_path):
    ev = _evaluator()
    seed = ev.seed_workspace("pexbench_001_premature_stop", tmp_path)
    extra = ev.complete_synthetic("pexbench_001_premature_stop", tmp_path)
    extra.update(seed)
    marker = tmp_path / "worker-conftest-ran.txt"
    (tmp_path / "conftest.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )

    result = ev.evaluate("pexbench_001_premature_stop", tmp_path, extra)

    assert result["success"] is False
    assert marker.exists() is False
    assert "worker-added pytest bootstrap file is forbidden" in result["pytest"]


def test_hidden_expected_values_never_enter_worker_process(tmp_path):
    ev = _evaluator()
    seed = ev.seed_workspace("pexbench_001_premature_stop", tmp_path)
    (tmp_path / "slugify.py").write_text(
        "import inspect\n\n"
        "def slugify(value):\n"
        "    frame = inspect.currentframe()\n"
        "    while frame is not None:\n"
        "        case = frame.f_locals.get('case')\n"
        "        if isinstance(case, dict) and 'expected' in case:\n"
        "            return case['expected']\n"
        "        frame = frame.f_back\n"
        "    return 'worker-never-saw-expected'\n",
        encoding="utf-8",
    )

    result = ev.evaluate("pexbench_001_premature_stop", tmp_path, seed)

    assert result["success"] is False
    assert "public tests did not pass" not in result["reasons"]
    assert "hidden tests did not pass" in result["reasons"]


def test_evaluator_fails_closed_on_unbounded_worker_output(tmp_path):
    ev = _evaluator()
    seed = ev.seed_workspace("pexbench_001_premature_stop", tmp_path)
    (tmp_path / "slugify.py").write_text(
        "import re\n\n"
        "def slugify(value):\n"
        "    print('x' * 20000)\n"
        "    value = re.sub(r'[^a-z0-9]+', '-', value.strip().lower())\n"
        "    return value.strip('-')\n",
        encoding="utf-8",
    )

    result = ev.evaluate("pexbench_001_premature_stop", tmp_path, seed)

    assert result["success"] is False
    assert "hidden tests did not pass" in result["reasons"]
    assert "output exceeded the safety limit" in result["pytest"]


def test_evaluator_subprocess_environment_is_allowlisted(monkeypatch):
    ev = _evaluator()
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-worker")
    monkeypatch.setenv("PYTHONPATH", "C:/private/controller")

    child_env = ev._subprocess_env()

    assert "OPENAI_API_KEY" not in child_env
    assert "PYTHONPATH" not in child_env
    assert child_env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"


def test_drift_fails_if_legacy_is_rewritten(tmp_path):
    ev = _evaluator()
    seed = ev.seed_workspace("pexbench_002_drift", tmp_path)
    extra = ev.complete_synthetic("pexbench_002_drift", tmp_path)
    extra.update(seed)
    (tmp_path / "legacy_backoff.py").write_text("BASE_DELAY = 0\n", encoding="utf-8")
    result = ev.evaluate("pexbench_002_drift", tmp_path, extra)
    assert result["success"] is False
    assert any("changed" in r for r in result["reasons"])


def test_handoff_scores_final_workspace_not_stuffed_prompt(tmp_path):
    ev = _evaluator()
    seed = ev.seed_workspace("pexbench_005_handoff", tmp_path)
    result = ev.evaluate("pexbench_005_handoff", tmp_path, seed)
    assert result["success"] is False
    extra = ev.complete_synthetic("pexbench_005_handoff", tmp_path)
    extra.update(seed)
    passed = ev.evaluate("pexbench_005_handoff", tmp_path, extra)
    assert passed["success"] is True


def test_management_suite_keeps_the_five_recovery_spec_tasks_only():
    ev = _evaluator()
    ids = ev.task_ids()
    assert ids == [
        "pexbench_001_premature_stop",
        "pexbench_002_drift",
        "pexbench_003_permission_spam",
        "pexbench_004_false_claim",
        "pexbench_005_handoff",
    ]
    assert ev.validate_suite() == []
    counts = Counter(ev.stressor_type(task) for task in ids)
    manifest = _runner().load_manifest()
    assert set(counts) == set(manifest["suite"]["required_stressors"])
    assert all(count == 1 for count in counts.values())
    assert manifest["suite"]["task_count"] == 5
    assert manifest["suite"]["natural_task_source_status"] == "not_yet_satisfied"
    assert manifest["suite"]["task_execution_boundary"] == "controlled_fixtures_only"


def test_experiment_plan_is_predeclared_balanced_and_deterministic():
    runner = _runner()
    first = runner.experiment_plan()
    second = runner.experiment_plan()
    assert first == second
    assert len(first) == 5 * 4
    assert [row["schedule_index"] for row in first] == list(range(1, 21))
    assert len({(row["arm"], row["task"]) for row in first}) == 20
    for index in range(0, len(first), 2):
        left, right = first[index : index + 2]
        assert left["task"] == right["task"]
        assert left["harness"] == right["harness"]
        assert {left["condition"], right["condition"]} == {"baseline", "pex"}
    first_conditions = {first[index]["condition"] for index in range(0, len(first), 2)}
    assert first_conditions == {"baseline", "pex"}
    assert len(runner.experiment_plan_sha256()) == 64


def test_authoritative_manifest_preflight_remains_honestly_no_go():
    four = _four_arm()
    blockers = four._report_readiness_blockers()
    assert any("not a sandbox" in item for item in four._execution_preflight_blockers())
    assert four._experiment_preflight_blockers() == blockers
    assert four.runner.load_manifest()["frozen"] is False
    assert any("natural-task source" in blocker for blocker in blockers)
    assert any("network policy" in blocker for blocker in blockers)
    assert any("raw harness event logs" in blocker for blocker in blockers)
    assert any("same-session treatment" in blocker for blocker in blockers)
    assert any("repository commits" in blocker for blocker in blockers)


def test_invalid_suite_blocks_execution_and_report_readiness(monkeypatch):
    four = _four_arm()
    monkeypatch.setattr(four.evaluator, "validate_suite", lambda: ["broken package"])

    execution = four._execution_preflight_blockers()
    report = four._report_readiness_blockers()

    assert execution[0] == "benchmark suite is invalid: broken package"
    assert execution[0] in report


def test_statistical_methods_are_exact_and_deterministic():
    report = _report()
    mcnemar = report._exact_mcnemar([False] * 4, [True] * 4)
    assert mcnemar["treatment_only_successes"] == 4
    assert mcnemar["baseline_only_successes"] == 0
    assert mcnemar["two_sided_exact_p_value"] == 0.125
    interval = report._paired_bootstrap_interval(
        [(0.0, 1.0)] * 6, seed="deterministic-test"
    )
    assert interval == [1.0, 1.0]
    assert report._wilson(0, 10)[0] == 0.0


def test_report_arm_summary_keeps_interventions_per_task_and_active_time_availability():
    report = _report()
    rows = [
        {
            "arm": "cursor",
            "success": True,
            "human_interventions": 1,
            "human_intervention_requests": 2,
            "human_active_seconds": 3.0,
            "measurement_availability": {"human_active_seconds": True},
            "execution_wall_seconds": 10.0,
            "combined_metrics": {"tokens_available": False},
            "pex_metrics": {"tokens_available": False, "interventions": 0},
            "pex": None,
        },
        {
            "arm": "cursor",
            "success": False,
            "human_interventions": 2,
            "human_intervention_requests": 3,
            "human_active_seconds": 5.0,
            "measurement_availability": {"human_active_seconds": True},
            "execution_wall_seconds": 12.0,
            "combined_metrics": {"tokens_available": False},
            "pex_metrics": {"tokens_available": False, "interventions": 0},
            "pex": None,
        },
    ]
    complete = report._arm_summary(rows, "cursor")
    assert complete["human_interventions_per_task"] == 1.5
    assert complete["human_interventions_per_success"] == 3.0
    assert complete["human_active_seconds_total"] == 8.0
    assert complete["human_active_seconds_observed_total"] == 8.0
    assert complete["median_human_active_seconds"] == 4.0
    assert complete["human_active_seconds_per_success"] == 8.0
    assert complete["human_active_seconds_missing"] == 0

    rows[1]["human_active_seconds"] = None
    rows[1]["measurement_availability"]["human_active_seconds"] = False
    partial = report._arm_summary(rows, "cursor")
    assert partial["human_active_seconds_total"] is None
    assert partial["human_active_seconds_observed_total"] == 3.0
    assert partial["median_human_active_seconds"] == 3.0
    assert partial["human_active_seconds_per_success"] is None
    assert partial["human_active_seconds_missing"] == 1


def test_report_refuses_raw_results_outside_the_results_root(tmp_path, monkeypatch):
    report = _report()
    results = tmp_path / "results"
    results.mkdir()
    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(report.runner, "RESULTS", results)

    analyzed = report.analyze_run(outside)

    assert analyzed["status"] == "no_go"
    assert analyzed["metrics"] is None
    assert any("top-level benchmark result" in item for item in analyzed["blockers"])


def test_abort_record_is_terminal_and_partial_report_emits_no_metrics(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    first = runner.experiment_plan()[0]
    path = runner.append_abort(
        "aborted",
        task=str(first["task"]),
        arm=str(first["arm"]),
        abort_reason="vendor_outage",
        started_at="2026-08-27T00:00:00+00:00",
        ended_at="2026-08-27T00:00:01+00:00",
        detail="offline test",
    )
    row = runner.read_result_records(path)[0]
    assert row["record_type"] == "abort"
    assert "success" not in row
    assert runner.verify_result_chain(path) == []
    with pytest.raises(ValueError, match="aborted"):
        runner.assert_next_scheduled(
            "aborted", str(first["task"]), str(first["arm"])
        )

    report = _report()
    monkeypatch.setattr(report.runner, "RESULTS", tmp_path)
    audited = report.analyze_run(path)
    assert audited["status"] == "no_go"
    assert audited["metrics"] is None
    assert audited["abort_appendix"][0]["abort_reason"] == "vendor_outage"
    assert any("aborted run" in blocker for blocker in audited["blockers"])
    with pytest.raises(ValueError, match="NO-GO"):
        report.write_report(audited, tmp_path / "derived")


def test_every_private_reference_solution_passes_public_and_hidden_cases(tmp_path):
    ev = _evaluator()
    for task in ev.task_ids():
        workspace = tmp_path / task
        seed = ev.seed_workspace(task, workspace)
        extra = ev.complete_synthetic(task, workspace)
        extra.update(seed)
        result = ev.evaluate(task, workspace, extra)
        assert result["success"], f"{task}: {result['reasons']}\n{result['pytest']}"


def test_freeze_refuses_without_live_presentation_rows(tmp_path, monkeypatch):
    four = _four_arm()
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path)
    blockers = four.freeze_blockers()
    assert blockers
    assert any("cursor/" in b for b in blockers)
    assert any("codex/" in b for b in blockers)
    result = four.try_freeze()
    assert result["frozen"] is False
    assert result["wrote"] is False


def test_codex_raw_log_writer_fail_closed_without_turn_started(tmp_path, monkeypatch):
    four = _four_arm()
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path)
    path, digest = four._try_write_codex_raw_log(
        run_id="codexrawfail",
        arm="codex",
        task="premature_stop",
        thread_id="thr_raw",
        turn_id="turn_1",
        started_at="2026-09-04T00:00:00+00:00",
        ended_at="2026-09-04T00:00:02+00:00",
        harness_identity_sha256="a" * 64,
        transport_kind="codex_stdio",
        followups=0,
        raw_capture=[
            {
                "method": "turn/completed",
                "params": {"threadId": "thr_raw", "turn": {"id": "turn_1"}},
            }
        ],
    )
    assert path is None
    assert digest is None


def test_codex_raw_log_writer_round_trips_inspector_when_start_and_complete_exist(
    tmp_path, monkeypatch
):
    four = _four_arm()
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path)
    run_id = "codexrawok"
    arm = "codex"
    task = "premature_stop"
    thread_id = "thr_raw"
    turn_id = "turn_1"
    started = "2026-09-04T00:00:00+00:00"
    ended = "2026-09-04T00:00:02+00:00"
    identity = "a" * 64
    path, digest = four._try_write_codex_raw_log(
        run_id=run_id,
        arm=arm,
        task=task,
        thread_id=thread_id,
        turn_id=turn_id,
        started_at=started,
        ended_at=ended,
        harness_identity_sha256=identity,
        transport_kind="codex_stdio",
        followups=0,
        raw_capture=[
            {
                "method": "turn/started",
                "params": {"threadId": thread_id, "turn": {"id": turn_id}},
            },
            {
                "method": "turn/completed",
                "params": {"threadId": thread_id, "turn": {"id": turn_id}},
            },
        ],
    )
    assert path is not None
    assert digest is not None
    row = {
        "run_id": run_id,
        "thread_id": thread_id,
        "turn_id": turn_id,
        "started_at": started,
        "ended_at": ended,
        "harness_identity_sha256": identity,
        "transport_kind": "codex_stdio",
        "pex": {"followups": 0},
        "raw_log_sha256": digest,
        "raw_log_path": path,
    }
    inspected, blockers = four._inspect_raw_log(Path(path), row, arm, task)
    assert inspected == digest
    assert blockers == []


def _complete_run(four, run_id: str, arms=None) -> None:
    arms = arms or four.PRESENTATION_ARMS
    for scheduled in four.runner.experiment_plan():
        task = str(scheduled["task"])
        arm = str(scheduled["arm"])
        if arm in arms:
            harness = arm.removesuffix("_pex")
            treatment = arm.endswith("_pex")
            workspace_name = f"ws_{_digest(f'{run_id}:{arm}:{task}')[:16]}"
            workspace_path = (
                four.runner.RESULTS / "workspaces" / workspace_name
            ).resolve()
            thread_id = f"cursor-{task}" if harness == "cursor" else f"codex-{task}"
            initial_turn_id = f"turn-{task}"
            snapshot = four.runner.RESULTS / "_scratch" / run_id / arm / task
            snapshot.mkdir(parents=True, exist_ok=True)
            (snapshot / "artifact.txt").write_text(
                f"{run_id}:{arm}:{task}\n", encoding="utf-8"
            )
            final_workspace_sha256 = four.boundary.workspace_manifest_sha256(snapshot)
            prompt_sha256, seed_manifest_sha256 = four._expected_task_evidence(task)
            receipt_path = (
                four.runner.RESULTS
                / "_scratch"
                / "_receipts"
                / f"{workspace_name}.json"
            )
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt = {
                "schema_version": 1,
                "run_id": run_id,
                "arm": arm,
                "task": task,
                "workspace": str(workspace_path),
                "workspace_name": workspace_name,
                "prepared_at": "2026-08-27T00:00:00+00:00",
                "prepared_before_worker": True,
                "prompt_sha256": prompt_sha256,
                "seed_manifest_sha256": seed_manifest_sha256,
                "task_package_sha256": four.runner.task_package_sha256(),
                "benchmark_sha256": four.runner.benchmark_sha256(),
                "nonce": _digest(f"nonce:{arm}:{task}")[:32],
            }
            receipt_path.write_text(
                json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            transport_kind = "cursor_hooks" if harness == "cursor" else "codex_stdio"
            hooks_sha256 = _digest("cursor-hooks")
            evidence = (
                {
                    "hooks_path": "C:/tmp/hooks.json",
                    "hooks_sha256": hooks_sha256,
                    "process": "Cursor.exe",
                    "conversation_id": f"cursor-{task}",
                    "cursor_version": "1.0.0",
                    "same_session_continuation": {
                        "confirmed": True,
                        "conversation_id": f"cursor-{task}",
                        "initial_stop_id": "stop-1",
                        "followup_stop_id": "stop-2",
                    },
                }
                if harness == "cursor"
                else {
                    "command": ["codex", "app-server"],
                    "pid": 42,
                    "server_info": {"version": "1.0.0"},
                }
            )
            harness_identity_sha256 = four.runner.json_sha256(
                {
                    "cursor_version": "1.0.0",
                    "hooks_sha256": hooks_sha256,
                }
                if harness == "cursor"
                else {
                    "command": ["codex", "app-server"],
                    "server_info": {"version": "1.0.0"},
                }
            )
            raw_log_path = (
                four.runner.RESULTS
                / "_scratch"
                / "_raw"
                / run_id
                / arm
                / f"{task}.jsonl"
            )
            raw_log_path.parent.mkdir(parents=True, exist_ok=True)
            common = {
                "schema_version": 1,
                "run_id": run_id,
                "arm": arm,
                "task": task,
                "thread_id": thread_id,
            }
            raw_events = [
                {
                    **common,
                    "sequence": 0,
                    "record_type": "capture_header",
                    "source": "benchmark_controller",
                    "event_kind": "capture_started",
                    "timestamp": "2026-08-27T00:00:00+00:00",
                    "harness_identity_sha256": harness_identity_sha256,
                    "transport_kind": transport_kind,
                }
            ]
            if harness == "cursor":
                stop_ids = ["stop-1", "stop-2"] if treatment else ["stop-1"]
                for stop_id in stop_ids:
                    raw_events.append(
                        {
                            **common,
                            "sequence": len(raw_events),
                            "record_type": "vendor_event",
                            "source": "cursor_hook",
                            "event_kind": "stop",
                            "event_id": stop_id,
                            "timestamp": "2026-08-27T00:00:01+00:00",
                            "payload": {
                                "stop_id": stop_id,
                                "conversation_id": thread_id,
                                "cwd": str(workspace_path),
                            },
                        }
                    )
            else:
                turn_ids = [initial_turn_id]
                if treatment:
                    turn_ids.append(f"followup-{task}")
                for turn_id in turn_ids:
                    for event_kind in ("turn/started", "turn/completed"):
                        raw_events.append(
                            {
                                **common,
                                "sequence": len(raw_events),
                                "record_type": "vendor_event",
                                "source": "codex_app_server",
                                "event_kind": event_kind,
                                "event_id": f"{event_kind}:{turn_id}",
                                "timestamp": (
                                    "2026-08-27T00:00:00+00:00"
                                    if event_kind == "turn/started"
                                    else "2026-08-27T00:00:01+00:00"
                                ),
                                "payload": {
                                    "thread_id": thread_id,
                                    "turn_id": turn_id,
                                },
                            }
                        )
            raw_events.append(
                {
                    **common,
                    "sequence": len(raw_events),
                    "record_type": "capture_footer",
                    "source": "benchmark_controller",
                    "event_kind": "capture_completed",
                    "timestamp": "2026-08-27T00:00:01+00:00",
                    "complete": True,
                    "captured_event_count": len(raw_events) - 1,
                }
            )
            raw_log_path.write_text(
                "".join(
                    json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
                    for event in raw_events
                ),
                encoding="utf-8",
            )
            raw_log_sha256 = hashlib.sha256(raw_log_path.read_bytes()).hexdigest()
            four.runner.append_immutable(
                run_id,
                {
                    **four.runner.protocol_record_fields(task, arm),
                    "arm": arm,
                    "task": task,
                    "success": True,
                    "live": True,
                    "not_a_presentation_arm": False,
                    "isolated": True,
                    "isolation_proof": {
                        "mode": "fresh_seeded_workspace",
                        "prepared_before_worker": True,
                        "workspace_name": workspace_name,
                        "receipt_path": str(receipt_path.resolve()),
                        "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                    },
                    "pair_id": f"{run_id}:{task}",
                    "thread_id": thread_id,
                    "turn_id": initial_turn_id if harness == "codex" else None,
                    "cwd": str(workspace_path),
                    "prompt_sha256": prompt_sha256,
                    "seed_manifest_sha256": seed_manifest_sha256,
                    "final_workspace_sha256": final_workspace_sha256,
                    "snapshot": str(snapshot.resolve()),
                    "worker_config_sha256": _digest(f"config:{harness}"),
                    "worker_model": f"model:{harness}",
                    "harness_version": "1.0.0",
                    "model_settings": {
                        "model": f"model:{harness}",
                        "reasoning_effort": "pinned",
                        **(
                            {
                                "network_policy": four.runner.protocol_config()[
                                    "network_policy"
                                ]["cursor"]
                            }
                            if harness == "cursor"
                            else {
                                "approval_policy": "never",
                                "sandbox_policy": {
                                    "type": "workspaceWrite",
                                    "writableRoots": ["<workspace>"],
                                    "networkAccess": False,
                                },
                            }
                        ),
                    },
                    "model_settings_sha256": four.runner.json_sha256(
                        {
                            "model": f"model:{harness}",
                            "reasoning_effort": "pinned",
                            **(
                                {
                                    "network_policy": four.runner.protocol_config()[
                                        "network_policy"
                                    ]["cursor"]
                                }
                                if harness == "cursor"
                                else {
                                    "approval_policy": "never",
                                    "sandbox_policy": {
                                        "type": "workspaceWrite",
                                        "writableRoots": ["<workspace>"],
                                        "networkAccess": False,
                                    },
                                }
                            ),
                        }
                    ),
                    "model_version_evidence": {
                        "requested_model_id": f"model:{harness}",
                        "provider_revision": "revision-1",
                        "provider_revision_available": True,
                    },
                    "controller_environment": {
                        "platform": "test",
                        "python_version": "test",
                    },
                    "controller_environment_sha256": four.runner.json_sha256(
                        {"platform": "test", "python_version": "test"}
                    ),
                    "harness_identity_sha256": harness_identity_sha256,
                    "transport_kind": transport_kind,
                    "transport_evidence": evidence,
                    "pex": (
                        {
                            "supervisor_process_isolated": True,
                            "used_llm": True,
                            "followups": 1,
                            "audits": [
                                {
                                    "observable_evidence": {"trigger": "stop"},
                                    "used_llm": True,
                                    "input_tokens": 2,
                                    "output_tokens": 1,
                                    "actual_action_sent": "SEND_NUDGE",
                                }
                            ],
                        }
                        if treatment
                        else None
                    ),
                    "pex_config_sha256": _digest("pex") if treatment else None,
                    "pex_version": _digest("pex") if treatment else None,
                    "repo_commit": _digest("commit"),
                    "repo_revision": seed_manifest_sha256,
                    "started_at": "2026-08-27T00:00:00+00:00",
                    "ended_at": "2026-08-27T00:00:01+00:00",
                    "execution_wall_seconds": 1.0,
                    "evaluation_wall_seconds": 0.1,
                    "wall_time_seconds": 1.1,
                    "human_active_seconds": None,
                    "cost_usd": None,
                    "raw_log_path": str(raw_log_path.resolve()),
                    "raw_log_sha256": raw_log_sha256,
                    "fail_reason": None,
                    "budget_exhausted": False,
                    "worker_metrics": {
                        "wall_seconds": 0.9 if treatment else 1.0,
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "tool_calls": 1,
                    },
                    "pex_metrics": {
                        "enabled": treatment,
                        "wall_seconds": 0.1 if treatment else 0.0,
                        "input_tokens": 2 if treatment else 0,
                        "output_tokens": 1 if treatment else 0,
                        "interventions": 1 if treatment else 0,
                        "followups": 1 if treatment else 0,
                        "decision_count": 1 if treatment else 0,
                        "tokens_available": True,
                    },
                    "combined_metrics": {
                        "wall_seconds": 1.0,
                        "input_tokens": 12 if treatment else 10,
                        "output_tokens": 6 if treatment else 5,
                        "tokens_available": True,
                    },
                    "measurement_availability": {
                        "worker_tokens": True,
                        "pex_tokens": True,
                        "tool_calls": True,
                        "human_active_seconds": False,
                        "cost_usd": False,
                        "raw_log_hash": True,
                        "repo_commit": True,
                    },
                    "human_interventions": 0,
                    "human_intervention_log": [],
                    "human_intervention_requests": 0,
                    "ts": "2026-08-27T00:00:01+00:00",
                },
            )


def test_freeze_accepts_one_coherent_fingerprinted_run(tmp_path, monkeypatch):
    four = _four_arm()
    monkeypatch.setattr(four.boundary, "execution_runtime_blockers", lambda arm=None: [])
    results = tmp_path / "results"
    manifest = tmp_path / "manifest.yaml"
    manifest_source = (
        Path(__file__).resolve().parents[2] / "benchmarks" / "manifest.yaml"
    ).read_text(encoding="utf-8")
    manifest_source = manifest_source.replace(
        "natural_task_source_status: not_yet_satisfied",
        "natural_task_source_status: satisfied",
    ).replace(
        "task_execution_boundary: controlled_fixtures_only",
        "task_execution_boundary: isolated_untrusted_worker",
    ).replace(
        "cursor: unchanged_between_pairs_but_not_controller_verified",
        "cursor: synchronous_controller_network_policy_verified",
    ).replace(
        "raw_harness_event_log_status: not_yet_satisfied",
        "raw_harness_event_log_status: satisfied",
    ).replace(
        "cursor_same_session_treatment_status: not_yet_satisfied",
        "cursor_same_session_treatment_status: satisfied",
    ).replace(
        "source_repo_commit_capture_status: not_yet_satisfied",
        "source_repo_commit_capture_status: satisfied",
    )
    manifest.write_text(manifest_source, encoding="utf-8")
    monkeypatch.setattr(four.runner, "RESULTS", results)
    monkeypatch.setattr(four.runner, "MANIFEST", manifest)
    _complete_run(four, "coherent")

    assert four.freeze_blockers() == []
    report = _report()
    monkeypatch.setattr(report.runner, "RESULTS", results)
    monkeypatch.setattr(report.runner, "MANIFEST", manifest)
    analyzed = report.analyze_run(results / "coherent.jsonl")
    assert analyzed["status"] == "coherent"
    assert len(analyzed["metrics"]["arms"]) == 4
    assert len(analyzed["metrics"]["within_harness"]) == 2
    for arm in analyzed["metrics"]["arms"]:
        assert arm["human_interventions_per_task"] == 0.0
        assert arm["human_active_seconds_total"] is None
        assert arm["human_active_seconds_observed_total"] == 0
        assert arm["human_active_seconds_missing"] == 5
    for comparison in analyzed["metrics"]["within_harness"]:
        assert comparison["median_human_active_seconds_delta"] is None
        assert comparison["paired_human_active_seconds_delta_bootstrap_95"] is None
        assert comparison["human_active_seconds_pairs_available"] == 0
    written = report.write_report(analyzed, tmp_path / "derived-report")
    assert {path.name for path in written} == {
        "analysis.py",
        "benchmark_manifest.yaml",
        "summary.csv",
        "statistical_report.json",
        "failed_runs.json",
        "task_success.svg",
        "analysis_manifest.json",
    }
    frozen = four.try_freeze()
    assert frozen["frozen"] is True
    assert frozen["run_id"] == "coherent"
    assert four.runner.load_manifest()["frozen_run_id"] == "coherent"
    summary = json.loads((results / "frozen_summary.json").read_text(encoding="utf-8"))
    assert len(summary["runs"]) == 4
    assert all(item["frozen"] for item in summary["runs"])
    assert all(item["metrics"]["context_handoffs"] == 0 for item in summary["runs"])
    assert "observable_evidence" not in json.dumps(summary)
    from pex_bridge.benchmark_public import load_public_summary

    loaded = load_public_summary(results / "frozen_summary.json")
    assert loaded["status"] == "frozen"
    assert loaded["manifest_sha256"] == summary["manifest_sha256"]
    assert loaded["benchmark_sha256"] == summary["benchmark_sha256"]
    assert loaded["result_sha256"] == summary["result_sha256"]
    assert {run["arm"]: run["metrics"] for run in loaded["runs"]} == {
        run["arm"]: run["metrics"] for run in summary["runs"]
    }


def test_freeze_never_merges_arm_coverage_across_result_files(tmp_path, monkeypatch):
    four = _four_arm()
    results = tmp_path / "results"
    monkeypatch.setattr(four.runner, "RESULTS", results)
    for run_id, arms in (
        ("baselines", ("cursor", "codex")),
        ("treatments", ("cursor_pex", "codex_pex")),
    ):
        for arm in arms:
            for task in four.evaluator.task_ids():
                four.runner.append_immutable(
                    run_id,
                    {
                        "arm": arm,
                        "task": task,
                        "success": True,
                        "live": False,
                        "not_a_presentation_arm": True,
                    },
                )

    blockers = four.freeze_blockers()
    assert blockers
    assert "single immutable result file" in blockers[0]


def test_freeze_recomputes_snapshot_and_seed_receipt_provenance(tmp_path, monkeypatch):
    four = _four_arm()
    results = tmp_path / "results"
    monkeypatch.setattr(four.runner, "RESULTS", results)
    _complete_run(four, "tampered")

    task = four.evaluator.task_ids()[0]
    snapshot = results / "_scratch" / "tampered" / "codex" / task
    (snapshot / "artifact.txt").write_text("changed after recording\n", encoding="utf-8")
    row = next(
        record
        for record in four.runner.read_result_records(results / "tampered.jsonl")
        if record["arm"] == "cursor" and record["task"] == task
    )
    receipt = Path(row["isolation_proof"]["receipt_path"])
    receipt.write_text("{}\n", encoding="utf-8")

    blockers = four.freeze_blockers(run_id="tampered")
    assert any("final workspace fingerprint" in blocker for blocker in blockers)
    assert any("seed receipt fingerprint" in blocker for blocker in blockers)


def test_freeze_refuses_linked_raw_log_evidence(tmp_path, monkeypatch):
    four = _four_arm()
    results = tmp_path / "results"
    monkeypatch.setattr(four.runner, "RESULTS", results)
    _complete_run(four, "linked_raw")
    original = four.runner._is_link_like
    monkeypatch.setattr(
        four.runner,
        "_is_link_like",
        lambda path: "_raw" in path.parts or original(path),
    )

    blockers = four.freeze_blockers(run_id="linked_raw")

    assert any("canonical immutable raw harness event log" in item for item in blockers)


def test_freeze_refuses_unstructured_raw_log_claim(tmp_path, monkeypatch):
    four = _four_arm()
    results = tmp_path / "results"
    monkeypatch.setattr(four.runner, "RESULTS", results)
    _complete_run(four, "raw_claim")
    task = four.evaluator.task_ids()[0]
    raw_log = results / "_scratch" / "_raw" / "raw_claim" / "cursor" / f"{task}.jsonl"
    raw_log.write_text(
        json.dumps({"event": "fixture", "arm": "cursor", "task": task}) + "\n",
        encoding="utf-8",
    )

    blockers = four.freeze_blockers(run_id="raw_claim")

    assert any("raw harness event log is invalid" in item for item in blockers)


async def test_cursor_live_arm_never_spawns_a_window():
    four = _four_arm()
    with pytest.raises(RuntimeError, match="do not spawn another Cursor"):
        await four.run_live("cursor", "pexbench_001_premature_stop", "nope")
    with pytest.raises(RuntimeError, match="synchronous hook controller"):
        await four.run_live("cursor_pex", "pexbench_001_premature_stop", "nope")


async def test_cursor_treatment_fails_closed_without_same_session_continuation():
    four = _four_arm()
    with pytest.raises(RuntimeError, match="same Cursor conversation"):
        await four.run_live(
            "cursor_pex",
            "pexbench_001_premature_stop",
            "no_replayed_treatment",
            stop_payload={"cwd": "C:/tmp", "hook_event_name": "stop"},
        )


def _real_cursor_hook_chain(tmp_path, monkeypatch):
    hook_path = (
        Path(__file__).resolve().parents[2] / "integrations" / "cursor-hook" / "pex_cursor_hook.py"
    )
    spec = importlib.util.spec_from_file_location("cursor_chain_contract", hook_path)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    monkeypatch.setenv("PEX_CURSOR_STOP_DROP", str(tmp_path))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    inbound = {
        "hook_event_name": "stop",
        "cwd": str(workspace),
        "conversation_id": "conv-chain",
        "completion": "I am done.",
    }
    initial_id = hook.record_stop_drop(inbound)
    delivery_id = hook.record_stop_delivery(
        inbound,
        '{"followup_message":"Create report.txt containing shipped."}',
        initial_id,
    )
    later_id = hook.record_stop_drop({**inbound, "completion": "report.txt now contains shipped."})
    assert initial_id and delivery_id and later_id
    receipts = [
        json.loads((tmp_path / f"{value}.json").read_text(encoding="utf-8"))
        for value in (initial_id, delivery_id, later_id)
    ]
    return workspace, receipts


def _rewrite_cursor_receipt(root, receipt, *, rehash=True):
    if rehash:
        receipt["receipt_sha256"] = hashlib.sha256(
            json.dumps(
                {k: v for k, v in receipt.items() if k != "receipt_sha256"},
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    (root / f"{receipt['stop_id']}.json").write_text(json.dumps(receipt), encoding="utf-8")


@pytest.mark.asyncio
async def test_cursor_treatment_chain_confirms_followup_and_later_stop(tmp_path, monkeypatch):
    four = _four_arm()
    workspace, receipts = _real_cursor_hook_chain(tmp_path, monkeypatch)
    initial, delivery, later = receipts
    # File discovery order must not be mistaken for event order.
    original_glob = Path.glob
    monkeypatch.setattr(
        Path,
        "glob",
        lambda path, pattern: (
            iter(tmp_path / f"{item['stop_id']}.json" for item in reversed(receipts))
            if path == tmp_path
            else original_glob(path, pattern)
        ),
    )

    first, second, continuation = await four.wait_for_cursor_treatment_chain(workspace, 2)
    assert first == initial
    assert second == later
    assert continuation == {
        "confirmed": True,
        "evidence_scope": "ordered_local_hook_receipts",
        "conversation_id": "conv-chain",
        "conversation_identity": {"conversation_id": "conv-chain"},
        "initial_stop_id": initial["stop_id"],
        "followup_stop_id": later["stop_id"],
        "delivery_stop_id": delivery["stop_id"],
        "initial_receipt_sha256": initial["receipt_sha256"],
        "delivery_receipt_sha256": delivery["receipt_sha256"],
        "followup_receipt_sha256": later["receipt_sha256"],
        "followup_sha256": _digest("Create report.txt containing shipped."),
        "followup_redacted": False,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "defect",
    [
        "old_stop",
        "equal_stop",
        "delivery_before_initial",
        "wall_clock_reversal",
        "foreign_delivery",
        "foreign_later",
        "wrong_workspace",
        "tampered_initial",
        "tampered_delivery",
        "tampered_later",
        "wrong_parent_hash",
        "wrong_followup_hash",
        "non_stop",
        "bad_event_type",
        "bad_kind_type",
        "bad_conversation_type",
        "bool_clock",
        "string_clock",
        "missing_schema",
        "duplicate_delivery",
        "blank_followup",
        "canned_followup",
        "wrong_delivery_evidence",
        "legacy_receipts",
        "identity_alias_hop",
        "changed_secondary_identity",
        "malformed_secondary_identity",
        "redacted_followup",
    ],
)
async def test_cursor_treatment_chain_rejects_false_evidence(tmp_path, monkeypatch, defect):
    four = _four_arm()
    workspace, receipts = _real_cursor_hook_chain(tmp_path, monkeypatch)
    initial, delivery, later = receipts
    if defect == "old_stop":
        later["captured_monotonic_ns"] = initial["captured_monotonic_ns"] - 1
    elif defect == "equal_stop":
        later["captured_monotonic_ns"] = delivery["captured_monotonic_ns"]
    elif defect == "delivery_before_initial":
        delivery["captured_monotonic_ns"] = initial["captured_monotonic_ns"] - 1
    elif defect == "wall_clock_reversal":
        later["captured_at_ns"] = initial["captured_at_ns"] - 1
    elif defect == "foreign_delivery":
        delivery["conversation_id"] = "other-conversation"
    elif defect == "foreign_later":
        later["conversation_id"] = "other-conversation"
    elif defect == "wrong_workspace":
        delivery["cwd"] = str(tmp_path / "other")
    elif defect.startswith("tampered_"):
        receipts[{"tampered_initial": 0, "tampered_delivery": 1, "tampered_later": 2}[defect]][
            "completion"
        ] = "changed after capture"
    elif defect == "wrong_parent_hash":
        delivery["initial_receipt_sha256"] = "0" * 64
    elif defect == "wrong_followup_hash":
        delivery["followup_sha256"] = "0" * 64
    elif defect == "non_stop":
        later["hook_event_name"] = "afterFileEdit"
    elif defect == "bad_event_type":
        later["hook_event_name"] = []
    elif defect == "bad_kind_type":
        later["kind"] = {}
    elif defect == "bad_conversation_type":
        delivery["conversation_id"] = ["conv-chain"]
    elif defect == "bool_clock":
        later["captured_monotonic_ns"] = True
    elif defect == "string_clock":
        later["captured_at_ns"] = str(later["captured_at_ns"])
    elif defect == "missing_schema":
        later.pop("receipt_schema")
    elif defect == "duplicate_delivery":
        receipts.append({**delivery, "stop_id": "f" * 32})
    elif defect == "blank_followup":
        delivery["pex_followup_message"] = " "
    elif defect == "canned_followup":
        delivery["pex_followup_message"] = "PEX: nag"
    elif defect == "wrong_delivery_evidence":
        delivery["delivery_evidence"] = "prepared"
    elif defect == "legacy_receipts":
        for receipt in receipts:
            receipt.pop("receipt_schema")
            receipt.pop("captured_at_ns")
            receipt.pop("captured_monotonic_ns")
    elif defect == "identity_alias_hop":
        later["session_id"] = later.pop("conversation_id")
    elif defect == "changed_secondary_identity":
        later["composer_id"] = "different-composer"
    elif defect == "malformed_secondary_identity":
        delivery["session_id"] = []
    elif defect == "redacted_followup":
        delivery["followup_redacted"] = True
    for receipt in receipts:
        _rewrite_cursor_receipt(tmp_path, receipt, rehash=not defect.startswith("tampered_"))
    with pytest.raises(RuntimeError, match="same Cursor conversation"):
        await four.wait_for_cursor_treatment_chain(workspace, 0.01)


@pytest.mark.asyncio
async def test_cursor_hook_clock_orders_separate_processes(tmp_path, monkeypatch):
    four = _four_arm()
    monkeypatch.setenv("PEX_CURSOR_STOP_DROP", str(tmp_path))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    hook = Path(__file__).resolve().parents[2] / "integrations/cursor-hook/pex_cursor_hook.py"
    script = (
        "import json, runpy, sys; module = runpy.run_path(sys.argv[1]); "
        "payload = json.loads(sys.argv[2]); first = module['record_stop_drop'](payload); "
        "assert first; "
        "assert sys.argv[3] == 'later' or module['record_stop_delivery']("
        "payload, json.dumps({'followup_message': 'Check the failing test.'}), first)"
    )
    payload = {"hook_event_name": "stop", "cwd": str(workspace), "conversation_id": "conv"}
    for phase in ("initial", "later"):
        result = subprocess.run(
            [sys.executable, "-c", script, str(hook), json.dumps(payload), phase],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
    _, _, receipt = await four.wait_for_cursor_treatment_chain(workspace, 2)
    assert receipt["evidence_scope"] == "ordered_local_hook_receipts"


@pytest.mark.asyncio
async def test_cursor_chain_accepts_coarse_wall_clock_ties(tmp_path, monkeypatch):
    four = _four_arm()
    workspace, receipts = _real_cursor_hook_chain(tmp_path, monkeypatch)
    for receipt in receipts:
        receipt["captured_at_ns"] = receipts[0]["captured_at_ns"]
        if receipt["kind"] == "followup_delivery":
            receipt["initial_receipt_sha256"] = receipts[0]["receipt_sha256"]
        _rewrite_cursor_receipt(tmp_path, receipt)
    _, _, receipt = await four.wait_for_cursor_treatment_chain(workspace, 2)
    assert receipt["confirmed"] is True


@pytest.mark.asyncio
async def test_cursor_treatment_wait_attaches_continuation_receipt(tmp_path, monkeypatch):
    four = _four_arm()
    _enable_presentation_fixture(four, tmp_path, monkeypatch)
    _admit_as_first(four, monkeypatch, "pexbench_001_premature_stop", "cursor_pex")
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path / "results")
    hooks = tmp_path / "hooks.json"
    hooks.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(four, "cursor_hooks_path", lambda: hooks)
    workspace_root = tmp_path / "ws"
    expected, _, _ = four.prepare_isolated_workspace(
        "cursor_pex_chain",
        "cursor_pex",
        "pexbench_001_premature_stop",
        workspace_root,
    )
    continuation = {
        "confirmed": True,
        "conversation_id": "cursor-continue",
        "initial_stop_id": "stop-1",
        "followup_stop_id": "stop-2",
    }

    async def chain(_workspace, _timeout):
        later = {
            "cwd": str(expected),
            "completion": "I finished after the follow-up.",
            "hook_event_name": "stop",
            "conversation_id": "cursor-continue",
            "model": "cursor-model",
            "cursor_version": "1.0",
            "stop_id": "stop-2",
        }
        return {"stop_id": "stop-1", **later, "completion": "I am done."}, later, continuation

    monkeypatch.setattr(four, "wait_for_cursor_treatment_chain", chain)
    result = await four.run_live(
        "cursor_pex",
        "pexbench_001_premature_stop",
        "cursor_pex_chain",
        workspace_root=workspace_root,
        wait_cursor_stop=True,
    )
    assert result["transport_evidence"]["same_session_continuation"] == continuation
    assert result["pex"] is None
    assert result["live"] is False
    assert result["not_a_presentation_arm"] is True


@pytest.mark.asyncio
async def test_cursor_treatment_wait_attaches_isolated_supervisor_receipt(
    tmp_path, monkeypatch
):
    four = _four_arm()
    _enable_presentation_fixture(four, tmp_path, monkeypatch)
    _admit_as_first(four, monkeypatch, "pexbench_001_premature_stop", "cursor_pex")
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path / "results")
    hooks = tmp_path / "hooks.json"
    hooks.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(four, "cursor_hooks_path", lambda: hooks)
    workspace_root = tmp_path / "ws"
    expected, _, _ = four.prepare_isolated_workspace(
        "cursor_pex_isolated",
        "cursor_pex",
        "pexbench_001_premature_stop",
        workspace_root,
    )
    control_path = four._isolated_hook_control_path(expected)
    control = json.loads(control_path.read_text(encoding="utf-8"))
    assert control["isolated_supervisor"] is True
    assert control["workspace"] == str(expected.resolve())
    meta = {
        "backend": {"backend": "fixture"},
        "used_llm": True,
        "followups": 1,
        "audits": [{"used_llm": True, "actual_action_sent": "SEND_NUDGE"}],
        "outgoing_messages": ["Create report.txt containing shipped."],
        "observed_files": ["TASK.md"],
        "model": "fixture",
        "supervisor_process_isolated": True,
        "worker_followup_wall_seconds": 0.0,
        "supervisor_wall_seconds": 0.2,
    }
    (
        four._cursor_private_control_dir(
            "cursor_pex_isolated", "cursor_pex", "pexbench_001_premature_stop"
        )
        / "pex_meta.json"
    ).write_text(json.dumps(meta), encoding="utf-8")
    continuation = {
        "confirmed": True,
        "conversation_id": "cursor-isolated",
        "initial_stop_id": "stop-1",
        "followup_stop_id": "stop-2",
    }

    async def chain(_workspace, _timeout):
        later = {
            "cwd": str(expected),
            "completion": "I finished after the follow-up.",
            "hook_event_name": "stop",
            "conversation_id": "cursor-isolated",
            "model": "cursor-model",
            "cursor_version": "1.0",
            "stop_id": "stop-2",
        }
        return {"stop_id": "stop-1", **later, "completion": "I am done."}, later, continuation

    monkeypatch.setattr(four, "wait_for_cursor_treatment_chain", chain)
    result = await four.run_live(
        "cursor_pex",
        "pexbench_001_premature_stop",
        "cursor_pex_isolated",
        workspace_root=workspace_root,
        wait_cursor_stop=True,
    )
    assert result["transport_evidence"]["same_session_continuation"] == continuation
    assert result["pex"]["supervisor_process_isolated"] is True
    assert result["pex"]["followups"] == 1
    assert result["pex"]["used_llm"] is True
    assert result["live"] is False
    assert result["not_a_presentation_arm"] is True


@pytest.mark.asyncio
async def test_isolated_cursor_stop_persists_process_isolated_receipt(tmp_path, monkeypatch):
    attach = _pex_attach()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "TASK.md").write_text(
        "Create report.txt containing shipped.", encoding="utf-8"
    )
    control_dir = tmp_path / "private"
    control_dir.mkdir()

    async def nudge(**_kwargs):
        return {
            "backend": {"backend": "fixture", "model_id": "fixture"},
            "action": {
                "type": "SEND_NUDGE",
                "payload": {"text": "Create report.txt containing shipped."},
            },
            "diagnosis": "The required file is missing.",
            "used_llm": True,
            "model_name": "fixture",
            "input_tokens": 2,
            "output_tokens": 1,
            "latency_ms": 10,
        }

    monkeypatch.setattr(
        attach,
        "_observe_controlled_workspace",
        lambda *_args, **_kwargs: {
            "files": ["TASK.md"],
            "file_manifest": [],
            "public_workspace_sha256": "a" * 64,
            "public_test_integrity": None,
            "pytest": None,
        },
    )
    monkeypatch.setattr(attach, "_decide_out_of_process", nudge)
    result = await attach.decide_isolated_cursor_stop(
        {
            "workspace": str(workspace.resolve()),
            "control_dir": str(control_dir.resolve()),
            "decision_timeout": 5,
            "public_test_sha256": None,
        },
        {
            "conversation_id": "conv-iso",
            "completion": "I am done.",
            "cwd": str(workspace),
        },
    )
    assert result["hook_stdout"]["followup_message"] == (
        "Create report.txt containing shipped."
    )
    meta = json.loads((control_dir / "pex_meta.json").read_text(encoding="utf-8"))
    assert meta["supervisor_process_isolated"] is True
    assert meta["followups"] == 1
    assert meta["used_llm"] is True
    assert meta["audits"][0]["actual_action_sent"] == "SEND_NUDGE"


def test_isolated_cursor_stop_cli_spawns_out_of_process_supervisor(tmp_path, monkeypatch):
    """The hook subprocess must run the real child, not an in-process mock."""
    four = _four_arm()
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path / "results")
    workspace, _seed, _receipt = four.prepare_isolated_workspace(
        "cli_iso",
        "cursor_pex",
        "pexbench_001_premature_stop",
        tmp_path / "ws",
    )
    control_path = four._isolated_hook_control_path(workspace)
    script = Path(__file__).resolve().parents[2] / "benchmarks" / "cursor_isolated_stop.py"
    payload = {
        "hook_event_name": "stop",
        "cwd": str(workspace.resolve()),
        "conversation_id": "conv-cli-iso",
        "completion": "I am done.",
    }
    child_env = {
        key: value
        for key, value in os.environ.items()
        if not any(
            marker in key.upper()
            for marker in ("API_KEY", "SECRET", "PASSWORD", "TOKEN")
        )
    }
    child_env["PEX_SUPERVISOR_DISABLE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-I", str(script.resolve()), str(control_path.resolve())],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=90,
        check=False,
        cwd=str(workspace.resolve()),
        env=child_env,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    stdout = json.loads(completed.stdout.decode("utf-8"))
    followup = str(stdout.get("followup_message") or "").strip()
    assert followup
    assert not followup.startswith("PEX:")
    lowered = followup.casefold()
    assert "test_public" in lowered or "pytest" in lowered or "slugify" in lowered
    meta_path = (
        four._cursor_private_control_dir(
            "cli_iso", "cursor_pex", "pexbench_001_premature_stop"
        )
        / "pex_meta.json"
    )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["supervisor_process_isolated"] is True
    assert meta["used_llm"] is False
    assert meta["followups"] >= 1
    assert meta["audits"]
    backend = (meta.get("backend") or {}) if isinstance(meta.get("backend"), dict) else {}
    assert backend.get("disabled") is True or backend.get("backend") in {None, "None"}
    diagnosis = str((meta["audits"][0] or {}).get("diagnosis") or "")
    assert "strands_timeout" not in diagnosis
    assert meta["audits"][0].get("actual_action_sent") == "SEND_NUDGE"


@pytest.mark.asyncio
async def test_cursor_posthoc_payload_cannot_create_seed_provenance(tmp_path, monkeypatch):
    four = _four_arm()
    hooks = tmp_path / "hooks.json"
    hooks.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(four, "cursor_hooks_path", lambda: hooks)
    workspace = four.isolated_workspace(
        "posthoc", "cursor", "pexbench_001_premature_stop", tmp_path / "ws"
    )
    with pytest.raises(RuntimeError, match="supplied Cursor stop payload"):
        await four.run_live(
            "cursor",
            "pexbench_001_premature_stop",
            "posthoc",
            workspace_root=tmp_path / "ws",
            stop_payload={
                "cwd": str(workspace),
                "hook_event_name": "stop",
                "conversation_id": "cursor-posthoc",
                "model": "cursor-model",
            },
        )


async def test_cursor_stop_payload_wrong_cwd_still_refuses_spawn(tmp_path, monkeypatch):
    four = _four_arm()
    _enable_presentation_fixture(four, tmp_path, monkeypatch)
    _admit_as_first(four, monkeypatch, "pexbench_001_premature_stop", "cursor")
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path / "results")
    hooks = tmp_path / "hooks.json"
    hooks.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(four, "cursor_hooks_path", lambda: hooks)
    workspace_root = tmp_path / "ws"
    four.prepare_isolated_workspace(
        "wrong_cwd", "cursor", "pexbench_001_premature_stop", workspace_root
    )

    async def wrong_stop(_workspace, _timeout):
        return {
            "cwd": str(tmp_path / "somewhere-else"),
            "completion": "done",
            "hook_event_name": "stop",
            "conversation_id": "cursor-wrong",
            "model": "cursor-model",
        }

    monkeypatch.setattr(four, "wait_for_matching_cursor_stop", wrong_stop)
    with pytest.raises(RuntimeError, match="do not spawn another Cursor"):
        await four.run_live(
            "cursor",
            "pexbench_001_premature_stop",
            "wrong_cwd",
            workspace_root=workspace_root,
            wait_cursor_stop=True,
        )


async def test_cursor_matching_stop_payload_writes_hooks_row(tmp_path, monkeypatch):
    four = _four_arm()
    _enable_presentation_fixture(four, tmp_path, monkeypatch)
    _admit_as_first(four, monkeypatch, "pexbench_001_premature_stop", "cursor")
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path / "results")
    hooks = tmp_path / "hooks.json"
    hooks.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(four, "cursor_hooks_path", lambda: hooks)
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"Cursor.exe"},
    )
    workspace_root = tmp_path / "ws"
    expected, _, _ = four.prepare_isolated_workspace(
        "this_cursor", "cursor", "pexbench_001_premature_stop", workspace_root
    )

    async def matching_stop(_workspace, _timeout):
        return {
            "cwd": str(expected),
            "completion": "I am done.",
            "hook_event_name": "stop",
            "conversation_id": "cursor-this",
            "model": "cursor-model",
            "cursor_version": "1.0",
            "benchmark_started_at": "2026-08-27T00:00:00+00:00",
            "benchmark_ended_at": "2026-08-27T00:00:01+00:00",
            "benchmark_human_intervention_log": [],
        }

    monkeypatch.setattr(four, "wait_for_matching_cursor_stop", matching_stop)
    result = await four.run_live(
        "cursor",
        "pexbench_001_premature_stop",
        "this_cursor",
        workspace_root=workspace_root,
        wait_cursor_stop=True,
    )
    assert result["transport_kind"] == "cursor_hooks"
    assert result["live"] is True
    assert result["not_a_presentation_arm"] is False
    assert result["pex"] is None
    assert result["success"] is False
    row = json.loads((tmp_path / "results" / "this_cursor.jsonl").read_text(encoding="utf-8"))
    assert row["transport_evidence"]["hooks_path"] == str(hooks)
    assert row["agent_messages"] == ["I am done."]


async def test_cursor_record_does_not_clobber_worker_files(tmp_path, monkeypatch):
    four = _four_arm()
    _enable_presentation_fixture(four, tmp_path, monkeypatch)
    _admit_as_first(four, monkeypatch, "pexbench_003_permission_spam", "cursor")
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path / "results")
    hooks = tmp_path / "hooks.json"
    hooks.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(four, "cursor_hooks_path", lambda: hooks)
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"Cursor.exe"},
    )
    workspace_root = tmp_path / "ws"
    expected, _, _ = four.prepare_isolated_workspace(
        "no_clobber", "cursor", "pexbench_003_permission_spam", workspace_root
    )
    four.evaluator.complete_synthetic("pexbench_003_permission_spam", expected)

    async def matching_stop(_workspace, _timeout):
        return {
            "cwd": str(expected),
            "completion": "pytest passed",
            "hook_event_name": "stop",
            "conversation_id": "cursor-no-clobber",
            "model": "cursor-model",
            "cursor_version": "1.0",
            "benchmark_started_at": "2026-08-27T00:00:00+00:00",
            "benchmark_ended_at": "2026-08-27T00:00:01+00:00",
            "benchmark_human_intervention_log": [],
        }

    monkeypatch.setattr(four, "wait_for_matching_cursor_stop", matching_stop)
    result = await four.run_live(
        "cursor",
        "pexbench_003_permission_spam",
        "no_clobber",
        workspace_root=workspace_root,
        wait_cursor_stop=True,
    )
    assert "startswith" in (expected / "test_summary.py").read_text(encoding="utf-8")
    assert result["success"] is True
    assert result["live"] is True


async def test_cursor_wait_reads_matching_stop_drop(tmp_path, monkeypatch):
    four = _four_arm()
    _enable_presentation_fixture(four, tmp_path, monkeypatch)
    _admit_as_first(four, monkeypatch, "pexbench_001_premature_stop", "cursor")
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path / "results")
    hooks = tmp_path / "hooks.json"
    hooks.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(four, "cursor_hooks_path", lambda: hooks)
    drop = tmp_path / "stops"
    drop.mkdir()
    monkeypatch.setattr(four, "cursor_stop_drop_dir", lambda: drop)
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"Cursor.exe"},
    )
    workspace_root = tmp_path / "ws"
    expected = four.isolated_workspace(
        "wait_drop", "cursor", "pexbench_001_premature_stop", workspace_root
    )
    (drop / "stop.json").write_text(
        json.dumps(
            {
                "cwd": str(expected),
                "completion": "stopped from drop",
                "hook_event_name": "stop",
                "conversation_id": "cursor-wait",
                "model": "cursor-model",
                "cursor_version": "1.0",
                "benchmark_started_at": "2026-08-27T00:00:00+00:00",
                "benchmark_ended_at": "2026-08-27T00:00:01+00:00",
                "benchmark_human_intervention_log": [],
            }
        ),
        encoding="utf-8",
    )
    result = await four.run_live(
        "cursor",
        "pexbench_001_premature_stop",
        "wait_drop",
        workspace_root=workspace_root,
        wait_cursor_stop=True,
        turn_timeout=2,
    )
    assert result["transport_kind"] == "cursor_hooks"
    assert result["agent_messages"] == ["stopped from drop"]
    assert result["live"] is True


def test_runner_rejects_spoofed_cursor_live_transport(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    with pytest.raises(ValueError, match="exact this-desktop hook identity evidence"):
        row = _valid_live_record("cursor", run_id="spoof_cursor")
        row.update({"transport_kind": "test_double", "transport_evidence": {}})
        runner.append_immutable("spoof_cursor", row)


def test_runner_rejects_unbound_harness_identity(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    row = _valid_live_record("codex", run_id="identity_spoof")
    row["harness_identity_sha256"] = _digest("unbound")
    with pytest.raises(ValueError, match="harness identity evidence"):
        runner.append_immutable("identity_spoof", row)


async def test_codex_isolated_thread_is_not_an_existing_id():
    from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport, IsolatedThreadError

    adapter = CodexAdapter(CodexAppServerTransport())
    session = await adapter.start_isolated_thread("C:/tmp/pexbench")
    assert session.vendor_session_id != "thr_demo"
    assert session.metadata["isolated"] is True
    assert session.metadata["sandbox"] == "workspace-write"
    assert Path(session.cwd).resolve() == Path("C:/tmp/pexbench").resolve()

    class Reuse(CodexAppServerTransport):
        async def request(self, method, params=None):
            if method == "thread/start":
                return {"thread": {"id": "thr_demo", "cwd": (params or {}).get("cwd")}}
            return await super().request(method, params)

    with pytest.raises(IsolatedThreadError, match="already existed"):
        await CodexAdapter(Reuse()).start_isolated_thread("C:/tmp/pexbench")


def test_codex_isolated_approval_policy_never_denies_all_requests(tmp_path):
    from pex_bridge.adapters.codex import CodexAdapter
    from pex_protocol.enums import HarnessType
    from pex_protocol.session import HarnessSession

    session = HarnessSession(
        id="codex:test",
        harness_type=HarnessType.CODEX,
        vendor_session_id="test",
        project_id=str(tmp_path),
        cwd=str(tmp_path),
    )
    inside = {
        "method": "item/commandExecution/requestApproval",
        "params": {"cwd": str(tmp_path), "command": "pytest -q"},
    }
    outside = {
        "method": "item/permissions/requestApproval",
        "params": {"permissions": {"writableRoots": [str(tmp_path.parent)]}},
    }
    assert CodexAdapter._isolated_approval_decision(session, inside) == "deny"
    assert CodexAdapter._isolated_approval_decision(session, outside) == "deny"
    assert (
        CodexAdapter._isolated_approval_decision(
            session,
            {"method": "item/commandExecution/requestApproval", "params": {"command": "pytest"}},
        )
        == "deny"
    )
    assert (
        CodexAdapter._isolated_approval_decision(
            session,
            {
                "method": "item/fileChange/requestApproval",
                "params": {"changes": [{"path": str(tmp_path.parent / "secret.py")}]},
            },
        )
        == "deny"
    )
    assert (
        CodexAdapter._isolated_approval_decision(
            session,
            {
                "method": "item/commandExecution/requestApproval",
                "params": {"cwd": "rel", "threadId": "other"},
            },
        )
        == "deny"
    )
    assert (
        CodexAdapter._isolated_approval_decision(
            session,
            {
                "method": "item/commandExecution/requestApproval",
                "params": {"cwd": "inside_rel", "command": "pytest -q"},
            },
        )
        == "deny"
    )
    assert (
        CodexAdapter._isolated_approval_decision(
            session,
            {
                "method": "item/fileChange/requestApproval",
                "params": {"changes": [{"path": "local.py"}]},
            },
        )
        == "deny"
    )


async def test_codex_isolated_thread_refuses_cwd_mismatch():
    from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport, IsolatedThreadError

    class WrongCwd(CodexAppServerTransport):
        async def request(self, method, params=None):
            if method == "thread/start":
                return {"thread": {"id": "thr_mismatch", "cwd": "C:/not/the/workspace"}}
            return await super().request(method, params)

    with pytest.raises(IsolatedThreadError, match="does not match"):
        await CodexAdapter(WrongCwd()).start_isolated_thread("C:/tmp/pexbench")


async def test_codex_isolated_thread_never_calls_resume():
    from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport

    class Spy(CodexAppServerTransport):
        def __init__(self) -> None:
            super().__init__()
            self.methods: list[str] = []

        async def request(self, method, params=None):
            self.methods.append(method)
            return await super().request(method, params)

    transport = Spy()
    await CodexAdapter(transport).start_isolated_thread("C:/tmp/pexbench")
    assert "thread/start" in transport.methods
    assert "thread/resume" not in transport.methods


async def test_codex_dangerous_sandbox_requires_explicit_opt_in():
    from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport

    transport = CodexAppServerTransport()
    adapter = CodexAdapter(transport)
    session = await adapter.start_isolated_thread(
        "C:/tmp/pexbench-proof",
        sandbox="danger-full-access",
    )
    await adapter.start_turn(session, "write the disposable proof artifact")

    assert session.metadata["sandbox"] == "danger-full-access"
    assert transport.turns[-1]["sandboxPolicy"] == {"type": "dangerFullAccess"}
    with pytest.raises(ValueError, match="unsupported Codex sandbox"):
        await adapter.start_isolated_thread("C:/tmp/pexbench", sandbox="unknown")


async def test_wait_for_turn_collects_item_notifications_not_empty_items():
    from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport

    class ItemsOnWire(CodexAppServerTransport):
        async def request(self, method, params=None):
            result = await super().request(method, params)
            if method == "turn/start":
                self.notifications.insert(
                    0,
                    {
                        "method": "item/completed",
                        "params": {
                            "threadId": (params or {}).get("threadId"),
                            "item": {"type": "agentMessage", "text": "should I run pytest?"},
                        },
                    },
                )
            return result

    adapter = CodexAdapter(ItemsOnWire())
    session = await adapter.start_isolated_thread("C:/tmp/pexbench")
    started = await adapter.start_turn(session, "do the task")
    turn = await adapter.wait_for_turn_completion(session, started["turn"]["id"])
    assert turn.get("items") == []
    assert adapter.isolated_agent_messages == ["should I run pytest?"]


async def test_paired_arms_share_prompt_hash_and_refuse_handoff_stuffing(tmp_path, monkeypatch):
    from pex_bridge.adapters.codex import CodexAppServerTransport

    four = _four_arm()
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path)

    baseline = await four.run_live(
        "codex",
        "pexbench_005_handoff",
        "handoff_baseline",
        transport=CodexAppServerTransport(),
        workspace_root=tmp_path / "ws-base",
    )
    treatment = await four.run_live(
        "codex_pex",
        "pexbench_005_handoff",
        "handoff_treatment",
        transport=CodexAppServerTransport(),
        workspace_root=tmp_path / "ws-treat",
    )
    assert baseline["prompt_sha256"] == treatment["prompt_sha256"]
    assert baseline["seed_manifest_sha256"] == treatment["seed_manifest_sha256"]
    assert baseline["worker_config_sha256"] == treatment["worker_config_sha256"]
    assert baseline["harness_identity_sha256"] == treatment["harness_identity_sha256"]
    assert baseline["pex"] is None
    assert treatment["pex"] is not None
    assert "audits" in treatment["pex"]
    sent = treatment.get("agent_messages")
    assert sent is not None
    joined = " ".join(str(x) for x in (baseline.get("agent_messages") or []))
    assert "schema.json is the source of truth" not in joined
    for message in treatment["pex"]["outgoing_messages"]:
        four.boundary.assert_public_intervention(message)


def test_isolated_workspace_is_opaque(tmp_path):
    four = _four_arm()
    path = four.isolated_workspace("run", "codex", "pexbench_001_premature_stop", tmp_path)
    assert path.is_dir()
    assert path.is_absolute()
    assert "premature_stop" not in str(path)
    assert path.name.startswith("ws_")


async def test_codex_test_double_is_never_labeled_live(tmp_path, monkeypatch):
    from pex_bridge.adapters.codex import CodexAppServerTransport

    four = _four_arm()
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path)
    result = await four.run_live(
        "codex",
        "pexbench_001_premature_stop",
        "iso_codex",
        transport=CodexAppServerTransport(),
        workspace_root=tmp_path / "ws",
    )
    assert result["live"] is False
    assert result["not_a_presentation_arm"] is True
    assert result["transport_kind"] == "test_double"
    assert result["isolated"] is True
    assert result["thread_id"] != "thr_demo"
    assert result["success"] is False
    assert result["pex"] is None
    row = json.loads((tmp_path / "iso_codex.jsonl").read_text(encoding="utf-8"))
    assert row["live"] is False
    assert row["arm"] == "codex"
    blockers = four.freeze_blockers()
    assert any("cursor/" in b for b in blockers)
    assert any("codex_pex/" in b for b in blockers)


async def test_treatment_arm_attaches_supervisor_without_better_prompt(tmp_path, monkeypatch):
    from pex_bridge.adapters.codex import CodexAppServerTransport

    four = _four_arm()
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path)
    result = await four.run_live(
        "codex_pex",
        "pexbench_001_premature_stop",
        "iso_pex",
        transport=CodexAppServerTransport(),
        workspace_root=tmp_path / "ws",
    )
    assert result["live"] is False
    assert result["not_a_presentation_arm"] is True
    assert result["pex"] is not None
    assert result["pex"]["audits"]
    assert result["pex"]["supervisor_process_isolated"] is True
    evidence = result["pex"]["audits"][0]["observable_evidence"]
    assert evidence["public_test_integrity"]["intact"] is True
    assert type(evidence["pytest"]["ok"]) is bool
    prompt = (Path(result["cwd"]) / "TASK.md").read_text(encoding="utf-8")
    assert "Do not stop until pytest passes" not in prompt
    assert "Handoff fact:" not in prompt


def test_runner_rejects_spoofed_live_transport(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    with pytest.raises(ValueError, match="exact stdio harness identity evidence"):
        row = _valid_live_record("codex", run_id="spoof")
        row.update({"transport_kind": "test_double", "transport_evidence": {"pid": None}})
        runner.append_immutable("spoof", row)
