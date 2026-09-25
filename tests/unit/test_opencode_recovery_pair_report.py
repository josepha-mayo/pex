"""A controlled recovery pair needs independent raw worker evidence in both arms."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.opencode_recovery_pair_report import build_report


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _capture(root: Path) -> dict:
    payload = b"event: message\ndata: {}\n\n"
    (root / "opencode-global-event.sse").write_bytes(payload)
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "chunks": 1,
        "stream_count": 1,
        "scope": "post_content_decoding_sse_bytes",
    }


def _pair(
    tmp_path: Path, scenario: str = "false-test-claim"
) -> tuple[Path, Path]:
    baseline, treatment = tmp_path / "baseline", tmp_path / "treatment"
    for root in (baseline, treatment):
        (root / "workspace").mkdir(parents=True)
        names = ["public-task.json"]
        if scenario == "false-test-claim":
            names.extend(("workspace/test_csv_utils.py", "workspace/verify.py"))
        for name in names:
            path = root / name
            path.write_text(name, encoding="utf-8")
    base_receipt = {
        "arm": "baseline", "pex_attached": False, "scenario": scenario,
        "worker_model": "free-model", "worker_provider": "opencode",
        "worker_completed": True, "followup_count": 0, "event_count": 1,
        "first_stop_observation": {
            "independent_initial_pytest": {"exit_code": 1},
            "stage_exact": True, "final_absent": True,
        },
        "independent_final_pytest": {"exit_code": 1},
        "stage_one_exact": True, "final_exact": False,
        "raw_sse_capture": _capture(baseline),
    }
    treatment_receipt = {
        "schema": "pex.live-opencode-recovery.v2", "scenario": scenario,
        "worker_model": "free-model", "event_count": 1,
        "all_observed_events_settled": True,
        "all_semantic_reviews_completed": True,
        "latest_completed_generation": "generation-1",
        "first_stop_observation": {
            "false_test_claim_observed": True,
            "independent_initial_pytest": {"exit_code": 1},
            "stage_exact": True, "final_absent": True,
        },
        "independent_final_pytest": {"exit_code": 0},
        "stage_one_exact": True, "final_exact": True,
        "raw_sse_capture": _capture(treatment),
    }
    _write_json(baseline / "summary.json", {
        "source_commit": "same-commit", "source_unchanged": True,
        "owned_server_exited": True, "error_type": None,
        "measurement_valid": True, "receipt": base_receipt,
    })
    _write_json(treatment / "summary.json", {
        "source_commit": "same-commit", "source_unchanged": True,
        "owned_server_exited": True, "error_type": None,
        "worker_provider": "opencode",
        "worker_credential_source": "separate_environment",
        "receipt": treatment_receipt,
    })
    _write_json(treatment / "events.json", [{}])
    _write_json(treatment / "journal.json", [{}])
    _write_json(treatment / "interventions.json", [])
    return baseline, treatment


def test_recovery_pair_rejects_missing_treatment_raw_stream(tmp_path: Path) -> None:
    baseline, treatment = _pair(tmp_path)
    assert build_report(baseline, treatment)["valid_pair"] is True

    summary_path = treatment / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    del summary["receipt"]["raw_sse_capture"]
    _write_json(summary_path, summary)
    report = build_report(baseline, treatment)
    assert report["valid_pair"] is False
    assert "treatment raw OpenCode SSE is missing or invalid" in report["blockers"]


def test_recovery_pair_rejects_tampered_treatment_raw_stream(tmp_path: Path) -> None:
    baseline, treatment = _pair(tmp_path)
    stream = treatment / "opencode-global-event.sse"
    stream.write_bytes(b"event: message\ndata: []\n\n")
    report = build_report(baseline, treatment)
    assert report["valid_pair"] is False
    assert "treatment raw OpenCode SSE is missing or invalid" in report["blockers"]


def test_deterministic_pair_requires_zero_model_calls_and_reports_its_mode(tmp_path: Path) -> None:
    baseline, treatment = _pair(tmp_path)
    path = treatment / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    receipt = summary["receipt"]
    receipt.update({
        "pex_mode": "deterministic",
        "all_semantic_reviews_completed": None,
        "all_no_model_reviews_completed": True,
        "supervisor_model": "disabled",
        "model_call_count": 0,
    })
    _write_json(path, summary)

    report = build_report(baseline, treatment)
    assert report["valid_pair"] is True
    assert report["treatment"]["pex_mode"] == "deterministic"
    assert "zero supervisor model calls" in report["claim_boundary"]
    assert "Nebius model" not in report["claim_boundary"]

    receipt["model_call_count"] = 1
    _write_json(path, summary)
    report = build_report(baseline, treatment)
    assert report["valid_pair"] is False
    assert "deterministic treatment made or omitted supervisor model calls" in report["blockers"]


def test_incomplete_artifact_pair_requires_initial_and_final_independent_state(
    tmp_path: Path,
) -> None:
    baseline, treatment = _pair(tmp_path, "incomplete-artifact")
    report = build_report(baseline, treatment)
    assert report["valid_pair"] is True
    assert report["scenario"] == "incomplete-artifact"
    assert report["baseline"]["initial_final_absent"] is True
    assert report["treatment"]["final_exact"] is True

    path = baseline / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary["receipt"]["first_stop_observation"]["final_absent"] = False
    _write_json(path, summary)
    report = build_report(baseline, treatment)
    assert report["valid_pair"] is False
    assert "baseline initial artifact state is unproven" in report["blockers"]
