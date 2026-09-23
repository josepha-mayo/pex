import json

from scripts.opencode_pair_report import build_report


def write_pair(tmp_path):
    baseline = tmp_path / "baseline"
    treatment = tmp_path / "treatment"
    baseline.mkdir()
    treatment.mkdir()
    common = {
        "source_commit": "a" * 40,
        "source_unchanged": True,
        "owned_server_exited": True,
        "error_type": None,
        "infrastructure_abort_reason": None,
        "requested_case_count": 1,
        "passed": True,
        "script_sha256": "b" * 64,
        "completion_fence_sha256": "c" * 64,
        "worker_model": "ling-3.0-flash-fin-free",
        "worker_provider": "opencode",
    }
    base_case = {
        "number": 1,
        "case": "deduplicate",
        "arm": "baseline",
        "pex_attached": False,
        "passed": True,
        "wall_seconds": 20.0,
        "worker_model": common["worker_model"],
        "worker_provider": common["worker_provider"],
    }
    pex_case = {
        **base_case,
        "arm": "pex",
        "pex_attached": True,
        "wall_seconds": 23.0,
        "followup_count": 0,
        "model_call_count": 1,
    }
    (baseline / "summary.json").write_text(
        json.dumps({**common, "arm": "baseline", "pex_attached": False, "cases": [base_case]}),
        encoding="utf-8",
    )
    (treatment / "summary.json").write_text(
        json.dumps({**common, "arm": "pex", "pex_attached": True, "cases": [pex_case]}),
        encoding="utf-8",
    )
    for root in (baseline, treatment):
        case_root = root / "case-01-deduplicate"
        case_root.mkdir()
        (case_root / "public-task.json").write_text('{"task":"same"}\n', encoding="utf-8")
    return baseline, treatment


def test_open_code_pair_report_requires_and_reports_a_true_pair(tmp_path):
    baseline, treatment = write_pair(tmp_path)

    report = build_report(baseline, treatment)

    assert report["comparable"] is True
    assert report["comparative_benchmark"] is False
    assert report["blockers"] == []
    assert report["metrics"] == {
        "case_count": 1,
        "baseline_successes": 1,
        "pex_successes": 1,
        "mean_wall_delta_seconds": 3.0,
        "median_wall_delta_seconds": 3.0,
        "pex_followups": 0,
        "pex_model_calls": 1,
    }


def test_open_code_pair_report_fails_closed_on_task_or_route_drift(tmp_path):
    baseline, treatment = write_pair(tmp_path)
    summary_path = treatment / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["worker_provider"] = "nebius"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    (treatment / "case-01-deduplicate" / "public-task.json").write_text(
        '{"task":"changed"}\n', encoding="utf-8"
    )

    report = build_report(baseline, treatment)

    assert report["comparable"] is False
    assert report["metrics"] is None
    assert "paired worker_provider mismatch" in report["blockers"]
    assert "case 1 public task mismatch" in report["blockers"]


def test_open_code_pair_report_rejects_path_shaped_case_identity(tmp_path):
    baseline, treatment = write_pair(tmp_path)
    for root in (baseline, treatment):
        summary_path = root / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["cases"][0]["case"] = "../outside"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")

    report = build_report(baseline, treatment)

    assert report["comparable"] is False
    assert report["metrics"] is None
    assert "case 1 identity is invalid" in report["blockers"]
