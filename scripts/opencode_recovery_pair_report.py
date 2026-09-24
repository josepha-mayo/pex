"""Validate and redact one controlled OpenCode false-claim recovery pair."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a JSON object")
    return value


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_report(baseline_root: Path, treatment_root: Path) -> dict:
    baseline_root, treatment_root = baseline_root.resolve(), treatment_root.resolve()
    if baseline_root == treatment_root:
        raise ValueError("baseline and treatment directories must differ")
    baseline = _load(baseline_root / "summary.json")
    treatment = _load(treatment_root / "summary.json")
    base_receipt = baseline.get("receipt") or {}
    pex_receipt = treatment.get("receipt") or {}
    blockers: list[str] = []
    if baseline.get("source_commit") != treatment.get("source_commit"):
        blockers.append("source commits differ")
    for name, summary in (("baseline", baseline), ("treatment", treatment)):
        if summary.get("source_unchanged") is not True:
            blockers.append(f"{name} source changed during measurement")
        if summary.get("owned_server_exited") is not True:
            blockers.append(f"{name} server exit is unproven")
        if summary.get("error_type") is not None:
            blockers.append(f"{name} raised an exception")
    if baseline.get("measurement_valid") is not True:
        blockers.append("baseline measurement is invalid")
    if base_receipt.get("arm") != "baseline" or base_receipt.get("pex_attached") is not False:
        blockers.append("baseline arm identity is invalid")
    if pex_receipt.get("schema") != "pex.live-opencode-recovery.v2":
        blockers.append("treatment receipt schema is unsupported")
    if (
        base_receipt.get("scenario") != "false-test-claim"
        or pex_receipt.get("scenario") != "false-test-claim"
    ):
        blockers.append("scenario is not the controlled false-claim task")
    if base_receipt.get("worker_model") != pex_receipt.get("worker_model"):
        blockers.append("worker models differ")
    if base_receipt.get("worker_provider") != treatment.get("worker_provider"):
        blockers.append("worker providers differ")
    if base_receipt.get("infrastructure_abort_reason") or pex_receipt.get(
        "infrastructure_abort_reason"
    ):
        blockers.append("provider infrastructure aborted")
    if treatment.get("worker_credential_source") != "separate_environment":
        blockers.append("treatment worker route is not the separate free credential")

    matched_hashes = {}
    for name in ("public-task.json", "workspace/test_csv_utils.py", "workspace/verify.py"):
        base_path, pex_path = baseline_root / name, treatment_root / name
        if not base_path.is_file() or not pex_path.is_file():
            blockers.append(f"{name} is missing")
            continue
        base_hash = _hash(base_path)
        if base_hash != _hash(pex_path):
            blockers.append(f"{name} differs between arms")
        matched_hashes[name] = base_hash

    capture = base_receipt.get("raw_sse_capture") or {}
    sse_path = baseline_root / "opencode-global-event.sse"
    if (
        not sse_path.is_file()
        or sse_path.is_symlink()
        or capture.get("sha256") != _hash(sse_path)
        or capture.get("bytes") != sse_path.stat().st_size
        or capture.get("stream_count") != 1
    ):
        blockers.append("baseline raw OpenCode SSE is missing or invalid")
    if (
        not (treatment_root / "events.json").is_file()
        or not (treatment_root / "journal.json").is_file()
    ):
        blockers.append("treatment event or processing journal is missing")
    else:
        events = json.loads((treatment_root / "events.json").read_text(encoding="utf-8"))
        journal = json.loads((treatment_root / "journal.json").read_text(encoding="utf-8"))
        if not isinstance(events, list) or len(events) != pex_receipt.get("event_count"):
            blockers.append("treatment event count disagrees with the receipt")
        if not isinstance(journal, list) or len(journal) != len(events):
            blockers.append("treatment processing journal does not cover all events")
    if pex_receipt.get("all_observed_events_settled") is not True:
        blockers.append("treatment event processing did not settle")
    if pex_receipt.get("all_semantic_reviews_completed") is not True:
        blockers.append("treatment semantic review did not settle")

    base_initial = (base_receipt.get("first_stop_observation") or {}).get(
        "independent_initial_pytest"
    ) or {}
    pex_initial = (pex_receipt.get("first_stop_observation") or {}).get(
        "independent_initial_pytest"
    ) or {}
    base_final = base_receipt.get("independent_final_pytest") or {}
    pex_final = pex_receipt.get("independent_final_pytest") or {}
    if not base_receipt.get("worker_completed"):
        blockers.append("baseline worker completion is unproven")
    if not pex_receipt.get("latest_completed_generation"):
        blockers.append("treatment worker completion is unproven")
    if not (pex_receipt.get("first_stop_observation") or {}).get("false_test_claim_observed"):
        blockers.append("treatment false claim was not observed")
    if base_initial.get("exit_code") is None or pex_initial.get("exit_code") is None:
        blockers.append("an initial independent test is missing")
    if base_final.get("exit_code") is None or pex_final.get("exit_code") is None:
        blockers.append("a final independent test is missing")

    interventions_path = treatment_root / "interventions.json"
    actions: list[str] = []
    if interventions_path.is_file():
        interventions = json.loads(interventions_path.read_text(encoding="utf-8"))
        if isinstance(interventions, list):
            actions = [
                str(row.get("action_taken"))
                for row in sorted(interventions, key=lambda row: str(row.get("created_at")))
                if isinstance(row, dict)
            ]
        else:
            blockers.append("treatment interventions are malformed")
    else:
        blockers.append("treatment interventions are missing")

    valid = not blockers
    return {
        "schema": "pex.opencode-controlled-recovery-pair.v1",
        "valid_pair": valid,
        "comparative_benchmark": False,
        "claim_boundary": (
            "One controlled false-completion diagnostic on separate real OpenCode sessions. "
            "The baseline worker did not receive PEX's persistent goal or follow-ups. "
            "The treatment adds a Nebius model, verification, and time. A single pair does not "
            "establish a reliability rate, representative speedup, or native desktop acceptance."
        ),
        "source_commit": baseline.get("source_commit") if valid else None,
        "worker_provider": base_receipt.get("worker_provider") if valid else None,
        "worker_model": base_receipt.get("worker_model") if valid else None,
        "matched_sha256": matched_hashes,
        "baseline": {
            "initial_pytest_exit_code": base_initial.get("exit_code"),
            "final_pytest_exit_code": base_final.get("exit_code"),
            "worker_completed": base_receipt.get("worker_completed"),
            "wall_seconds": base_receipt.get("wall_seconds"),
            "followup_count": base_receipt.get("followup_count"),
            "event_count": base_receipt.get("event_count"),
            "raw_sse_sha256": capture.get("sha256"),
        },
        "treatment": {
            "initial_pytest_exit_code": pex_initial.get("exit_code"),
            "final_pytest_exit_code": pex_final.get("exit_code"),
            "passed": pex_receipt.get("passed"),
            "wall_seconds": pex_receipt.get("wall_seconds"),
            "followup_count": pex_receipt.get("followup_count"),
            "actions_in_time_order": actions,
            "event_count": pex_receipt.get("event_count"),
            "supervisor_model": pex_receipt.get("supervisor_model"),
            "supervisor_model_calls": pex_receipt.get("model_call_count"),
            "supervisor_input_tokens": pex_receipt.get("input_tokens"),
            "supervisor_output_tokens": pex_receipt.get("output_tokens"),
        },
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--treatment", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = build_report(args.baseline, args.treatment)
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps({"valid_pair": report["valid_pair"], "blockers": report["blockers"]}))
    return 0 if report["valid_pair"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
