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


def _pair(tmp_path: Path) -> tuple[Path, Path]:
    baseline, treatment = tmp_path / "baseline", tmp_path / "treatment"
    for root in (baseline, treatment):
        (root / "workspace").mkdir(parents=True)
        for name in ("public-task.json", "workspace/test_csv_utils.py", "workspace/verify.py"):
            path = root / name
            path.write_text(name, encoding="utf-8")
    base_receipt = {
        "arm": "baseline", "pex_attached": False, "scenario": "false-test-claim",
        "worker_model": "free-model", "worker_provider": "opencode",
        "worker_completed": True, "followup_count": 0, "event_count": 1,
        "first_stop_observation": {"independent_initial_pytest": {"exit_code": 1}},
        "independent_final_pytest": {"exit_code": 1},
        "raw_sse_capture": _capture(baseline),
    }
    treatment_receipt = {
        "schema": "pex.live-opencode-recovery.v2", "scenario": "false-test-claim",
        "worker_model": "free-model", "event_count": 1,
        "all_observed_events_settled": True,
        "all_semantic_reviews_completed": True,
        "latest_completed_generation": "generation-1",
        "first_stop_observation": {
            "false_test_claim_observed": True,
            "independent_initial_pytest": {"exit_code": 1},
        },
        "independent_final_pytest": {"exit_code": 0},
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
