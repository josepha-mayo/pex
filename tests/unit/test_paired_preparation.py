import json

import pytest

from benchmarks import paired_preparation


def prepare(path):
    return paired_preparation.prepare_experiment(
        path, run_id="prospective-1", seed="predeclared-order",
        models={"codex": "pinned/codex", "opencode": "pinned/opencode"},
    )


def test_full_pairs_have_identical_public_seeds_and_external_plan(tmp_path):
    root = tmp_path / "experiment"
    plan = prepare(root)
    assert len(plan["schedule"]) == 32
    assert not plan["presentation_eligible"] and not plan["execution_boundary_verified"]
    assert json.loads((root / "controller/plan.json").read_text()) == plan
    grouped = {}
    for row in plan["schedule"]:
        worker = root / "workers" / row["workspace"]
        assert len(row["workspace"]) == 64
        assert (worker / "TASK.md").is_file()
        assert not (worker / "metadata.yaml").exists()
        assert not (worker / "plan.json").exists()
        grouped.setdefault((row["harness"], row["task"]), []).append(row)
    assert len(grouped) == 16
    for first, second in grouped.values():
        assert {first["condition"], second["condition"]} == {"baseline", "pex"}
        assert first["workspace"] != second["workspace"]
        for field in ("model", "seed_manifest_sha256", "prompt_sha256", "protected_sha256"):
            assert first[field] == second[field]


def test_order_repeats_without_copying_or_reusing_experiments(tmp_path):
    first, second = prepare(tmp_path / "first"), prepare(tmp_path / "second")
    assert first == second
    with pytest.raises(ValueError, match="fresh"):
        prepare(tmp_path / "first")


def test_failed_preparation_remains_consumed_and_is_never_reused(tmp_path, monkeypatch):
    root = tmp_path / "experiment"

    def fail(*args):
        raise RuntimeError("infrastructure failure")

    monkeypatch.setattr(paired_preparation.evaluator, "seed_workspace", fail)
    with pytest.raises(RuntimeError, match="infrastructure"):
        prepare(root)
    assert root.is_dir() and not (root / "controller/plan.json").exists()
    with pytest.raises(ValueError, match="fresh"):
        prepare(root)


def test_invalid_configuration_cannot_reserve_a_directory(tmp_path):
    root = tmp_path / "experiment"
    with pytest.raises(ValueError, match="both harnesses"):
        paired_preparation.prepare_experiment(root, run_id="run", seed="seed",
                                             models={"codex": "pinned"})
    assert not root.exists()


def test_source_drift_cannot_publish_a_prepared_plan(tmp_path, monkeypatch):
    fingerprints = iter(["a" * 64, "b" * 64])
    monkeypatch.setattr(paired_preparation.runner, "benchmark_sha256", lambda: next(fingerprints))
    root = tmp_path / "experiment"
    with pytest.raises(RuntimeError, match="sources changed"):
        prepare(root)
    assert root.is_dir() and not (root / "controller/plan.json").exists()


def test_invalid_task_package_is_rejected_before_reservation(tmp_path, monkeypatch):
    original = paired_preparation.evaluator.task_spec

    def malformed(task_id):
        value = dict(original(task_id))
        value.pop("starter", None)
        return value

    monkeypatch.setattr(paired_preparation.evaluator, "task_spec", malformed)
    root = tmp_path / "experiment"
    with pytest.raises(RuntimeError, match="invalid PexBench suite"):
        prepare(root)
    assert not root.exists()
