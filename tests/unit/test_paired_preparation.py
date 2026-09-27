import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from benchmarks import paired_preparation
from benchmarks.boundary import sha256_file

FINGERPRINTS = {harness: {"runtime_sha256": "a" * 64, "settings_sha256": "b" * 64}
                for harness in ("codex", "opencode")}


def prepare(path):
    return paired_preparation.prepare_experiment(
        path, run_id="prospective-1", seed="predeclared-order",
        models={"codex": "pinned/codex", "opencode": "pinned/opencode"},
        worker_fingerprints=FINGERPRINTS,
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
        for field in ("model", "worker_profile_sha256", "seed_manifest_sha256",
                      "prompt_sha256", "protected_sha256"):
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
                                             models={"codex": "pinned"},
                                             worker_fingerprints=FINGERPRINTS)
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


@pytest.mark.parametrize("limits", [
    {"task_wall_seconds": True}, {"task_wall_seconds": 0},
    {"max_model_calls": 0}, {"max_followups": 11}, {"review_seconds": 601},
])
def test_invalid_limits_cannot_reserve_an_experiment(tmp_path, limits):
    root = tmp_path / "experiment"
    with pytest.raises(ValueError, match="execution budget"):
        paired_preparation.prepare_experiment(
            root, run_id="run", seed="seed", models={"codex": "pinned", "opencode": "pinned"},
            worker_fingerprints=FINGERPRINTS, **limits,
        )
    assert not root.exists()


@pytest.mark.parametrize("profile", [
    {"runtime_sha256": "unknown", "settings_sha256": "b" * 64},
    {"runtime_sha256": "a" * 64, "settings_sha256": "b" * 64, "extra": "ignored"},
])
def test_unknown_runtime_or_extra_configuration_cannot_be_predeclared(tmp_path, profile):
    root = tmp_path / "experiment"
    invalid = {**FINGERPRINTS, "codex": profile}
    with pytest.raises(ValueError, match="fingerprints"):
        paired_preparation.prepare_experiment(
            root, run_id="run", seed="seed", models={"codex": "pinned", "opencode": "pinned"},
            worker_fingerprints=invalid,
        )
    assert not root.exists()


def test_changed_worker_settings_change_the_bound_profile(tmp_path):
    original = prepare(tmp_path / "original")
    changed = paired_preparation.prepare_experiment(
        tmp_path / "changed", run_id="prospective-1", seed="predeclared-order",
        models={"codex": "pinned/codex", "opencode": "pinned/opencode"},
        worker_fingerprints={**FINGERPRINTS, "codex": {
            "runtime_sha256": "a"*64, "settings_sha256": "c"*64,
        }}, task_wall_seconds=300, review_seconds=60, max_model_calls=10, max_followups=1,
    )
    assert changed["budget"] == {
        "task_wall_seconds": 300, "includes_worker_and_pex": True, "max_worker_model_calls": 10,
        "max_pex_followups": 1, "max_review_seconds": 60, "evaluator_outside_task_budget": True,
    }
    for first, second in zip(original["schedule"], changed["schedule"], strict=True):
        assert first["condition"] == second["condition"] and first["task"] == second["task"]
        assert (first["worker_profile_sha256"] != second["worker_profile_sha256"]) == (
            first["harness"] == "codex"
        )


def test_attempt_reservation_is_exclusive_and_preserves_predeclared_budget(tmp_path):
    root = tmp_path / "experiment"
    plan = prepare(root)
    digest = sha256_file(root / "controller/plan.json")
    profile = plan["worker_profiles"][plan["schedule"][0]["harness"]]

    def reserve():
        try:
            return paired_preparation.reserve_attempt(
                root, index=0, expected_plan_sha256=digest, worker_profile=profile,
            )
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: reserve(), range(2)))
    assert sum(row is not None for row in receipts) == 1
    receipt = next(row for row in receipts if row is not None)
    assert receipt["budget"] == plan["budget"]
    assert receipt["entry"] == plan["schedule"][0]
    assert receipt["status"] == "reserved"
    assert not receipt["execution_boundary_verified"] and not receipt["presentation_eligible"]
    assert reserve() is None
    saved = root / "controller" / f"attempt-{plan['schedule'][0]['workspace']}.json"
    assert json.loads(saved.read_text()) == receipt


@pytest.mark.parametrize("drift", ["plan", "profile", "workspace", "sources"])
def test_admission_drift_cannot_consume_an_attempt(tmp_path, monkeypatch, drift):
    root = tmp_path / "experiment"
    plan = prepare(root)
    path = root / "controller/plan.json"
    digest = sha256_file(path)
    profile = dict(plan["worker_profiles"][plan["schedule"][0]["harness"]])
    if drift == "plan":
        path.write_text(path.read_text() + " ")
    elif drift == "profile":
        profile["settings_sha256"] = "c" * 64
    elif drift == "workspace":
        (root / "workers" / plan["schedule"][0]["workspace"] / "TASK.md").write_text("drift")
    else:
        monkeypatch.setattr(paired_preparation.runner, "benchmark_sha256", lambda: "c" * 64)
    with pytest.raises(ValueError):
        paired_preparation.reserve_attempt(
            root, index=0, expected_plan_sha256=digest, worker_profile=profile,
        )
    assert not list((root / "controller").glob("attempt-*.json"))


def test_uncertain_reservation_write_is_not_reusable(tmp_path, monkeypatch):
    root = tmp_path / "experiment"
    plan = prepare(root)
    options = {
        "index": 0, "expected_plan_sha256": sha256_file(root / "controller/plan.json"),
        "worker_profile": plan["worker_profiles"][plan["schedule"][0]["harness"]],
    }

    def fail(_descriptor):
        raise OSError("uncertain persistence")

    monkeypatch.setattr(paired_preparation.os, "fsync", fail)
    with pytest.raises(OSError, match="uncertain persistence"):
        paired_preparation.reserve_attempt(root, **options)
    with pytest.raises(FileExistsError):
        paired_preparation.reserve_attempt(root, **options)
