"""Validate and redact one controlled OpenCode recovery pair."""

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


def _valid_sse_capture(root: Path, capture: object) -> bool:
    path = root / "opencode-global-event.sse"
    return (
        isinstance(capture, dict)
        and path.is_file()
        and not path.is_symlink()
        and type(capture.get("bytes")) is int
        and 0 < capture["bytes"] <= 64 * 1024 * 1024
        and path.stat().st_size == capture["bytes"]
        and type(capture.get("chunks")) is int
        and capture["chunks"] > 0
        and capture.get("stream_count") == 1
        and capture.get("scope") == "post_content_decoding_sse_bytes"
        and capture.get("sha256") == _hash(path)
    )


def build_report(baseline_root: Path, treatment_root: Path) -> dict:
    baseline_root, treatment_root = baseline_root.resolve(), treatment_root.resolve()
    if baseline_root == treatment_root:
        raise ValueError("baseline and treatment directories must differ")
    baseline = _load(baseline_root / "summary.json")
    treatment = _load(treatment_root / "summary.json")
    base_receipt = baseline.get("receipt") or {}
    pex_receipt = treatment.get("receipt") or {}
    blockers: list[str] = []
    pex_mode = pex_receipt.get("pex_mode", "semantic")
    if pex_mode not in {"semantic", "deterministic"}:
        blockers.append("treatment supervisor mode is unsupported")
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
    scenario = base_receipt.get("scenario")
    if scenario not in {"false-test-claim", "incomplete-artifact"} or (
        pex_receipt.get("scenario") != scenario
    ):
        blockers.append("scenarios differ or are unsupported")
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
    matched_files = ["public-task.json"]
    if scenario == "false-test-claim":
        matched_files.extend(("workspace/test_csv_utils.py", "workspace/verify.py"))
    for name in matched_files:
        base_path, pex_path = baseline_root / name, treatment_root / name
        if not base_path.is_file() or not pex_path.is_file():
            blockers.append(f"{name} is missing")
            continue
        base_hash = _hash(base_path)
        if base_hash != _hash(pex_path):
            blockers.append(f"{name} differs between arms")
        matched_hashes[name] = base_hash

    capture = base_receipt.get("raw_sse_capture")
    if not _valid_sse_capture(baseline_root, capture):
        blockers.append("baseline raw OpenCode SSE is missing or invalid")
    treatment_capture = pex_receipt.get("raw_sse_capture")
    if not _valid_sse_capture(treatment_root, treatment_capture):
        blockers.append("treatment raw OpenCode SSE is missing or invalid")
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
    if pex_mode == "semantic":
        if pex_receipt.get("all_semantic_reviews_completed") is not True:
            blockers.append("treatment semantic review did not settle")
    elif pex_mode == "deterministic":
        if pex_receipt.get("all_no_model_reviews_completed") is not True:
            blockers.append("treatment no-model reviews did not settle")
        calls = pex_receipt.get("model_call_count")
        if type(calls) is not int or calls != 0:
            blockers.append("deterministic treatment made or omitted supervisor model calls")
        if pex_receipt.get("supervisor_model") != "disabled":
            blockers.append("deterministic treatment supervisor model was not disabled")

    base_first = base_receipt.get("first_stop_observation") or {}
    pex_first = pex_receipt.get("first_stop_observation") or {}
    base_initial = base_first.get("independent_initial_pytest") or {}
    pex_initial = pex_first.get("independent_initial_pytest") or {}
    base_final = base_receipt.get("independent_final_pytest") or {}
    pex_final = pex_receipt.get("independent_final_pytest") or {}
    if not base_receipt.get("worker_completed"):
        blockers.append("baseline worker completion is unproven")
    if not pex_receipt.get("latest_completed_generation"):
        blockers.append("treatment worker completion is unproven")
    if scenario == "false-test-claim":
        if not pex_first.get("false_test_claim_observed"):
            blockers.append("treatment false claim was not observed")
        if base_initial.get("exit_code") is None or pex_initial.get("exit_code") is None:
            blockers.append("an initial independent test is missing")
        if base_final.get("exit_code") is None or pex_final.get("exit_code") is None:
            blockers.append("a final independent test is missing")
    elif scenario == "incomplete-artifact":
        for name, observation in (("baseline", base_first), ("treatment", pex_first)):
            if (
                observation.get("stage_exact") is not True
                or observation.get("final_absent") is not True
            ):
                blockers.append(f"{name} initial artifact state is unproven")
        for name, receipt in (("baseline", base_receipt), ("treatment", pex_receipt)):
            if (
                type(receipt.get("stage_one_exact")) is not bool
                or type(receipt.get("final_exact")) is not bool
            ):
                blockers.append(f"{name} final artifact state is unproven")

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
            "One controlled "
            + ("false-completion" if scenario == "false-test-claim" else "incomplete-artifact")
            + " diagnostic on separate real OpenCode sessions. "
            "The baseline worker did not receive PEX's persistent goal or follow-ups. "
            + (
                "The treatment adds a persistent goal, local verification, and same-session "
                "follow-ups with zero supervisor model calls. "
                if pex_mode == "deterministic"
                else "The treatment adds a configured semantic model, verification, and time. "
            )
            + "A single pair does not "
            "establish a reliability rate, representative speedup, or native desktop acceptance."
        ),
        "source_commit": baseline.get("source_commit") if valid else None,
        "scenario": scenario if valid else None,
        "worker_provider": base_receipt.get("worker_provider") if valid else None,
        "worker_model": base_receipt.get("worker_model") if valid else None,
        "matched_sha256": matched_hashes,
        "baseline": {
            "initial_pytest_exit_code": base_initial.get("exit_code"),
            "final_pytest_exit_code": base_final.get("exit_code"),
            "initial_stage_exact": base_first.get("stage_exact"),
            "initial_final_absent": base_first.get("final_absent"),
            "final_stage_exact": base_receipt.get("stage_one_exact"),
            "final_exact": base_receipt.get("final_exact"),
            "worker_completed": base_receipt.get("worker_completed"),
            "wall_seconds": base_receipt.get("wall_seconds"),
            "followup_count": base_receipt.get("followup_count"),
            "event_count": base_receipt.get("event_count"),
            "raw_sse_sha256": capture.get("sha256") if isinstance(capture, dict) else None,
        },
        "treatment": {
            "pex_mode": pex_mode,
            "initial_pytest_exit_code": pex_initial.get("exit_code"),
            "final_pytest_exit_code": pex_final.get("exit_code"),
            "initial_stage_exact": pex_first.get("stage_exact"),
            "initial_final_absent": pex_first.get("final_absent"),
            "final_stage_exact": pex_receipt.get("stage_one_exact"),
            "final_exact": pex_receipt.get("final_exact"),
            "passed": pex_receipt.get("passed"),
            "wall_seconds": pex_receipt.get("wall_seconds"),
            "followup_count": pex_receipt.get("followup_count"),
            "actions_in_time_order": actions,
            "event_count": pex_receipt.get("event_count"),
            "raw_sse_sha256": (
                treatment_capture.get("sha256") if isinstance(treatment_capture, dict) else None
            ),
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
