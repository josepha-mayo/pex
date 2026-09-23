"""Validate and summarize one OpenCode baseline/PEX diagnostic pair."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from pathlib import Path


def _parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--treatment", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_sse_capture(case_root: Path, receipt: dict) -> bool:
    capture = receipt.get("raw_sse_capture")
    if not isinstance(capture, dict):
        return False
    path = case_root / "opencode-global-event.sse"
    if (
        not path.is_file()
        or path.is_symlink()
        or capture.get("path") != str(path.resolve())
        or capture.get("scope") != "post_content_decoding_sse_bytes"
        or capture.get("stream_count") != 1
        or isinstance(capture.get("bytes"), bool)
        or not isinstance(capture.get("bytes"), int)
        or not 0 < capture["bytes"] <= 64 * 1024 * 1024
        or isinstance(capture.get("chunks"), bool)
        or not isinstance(capture.get("chunks"), int)
        or capture["chunks"] <= 0
        or path.stat().st_size != capture["bytes"]
    ):
        return False
    return _sha256(path) == capture.get("sha256")


def build_report(baseline_root: Path, treatment_root: Path) -> dict:
    baseline_root = baseline_root.resolve()
    treatment_root = treatment_root.resolve()
    if baseline_root == treatment_root:
        raise ValueError("baseline and treatment evidence directories must differ")
    baseline = _load_json(baseline_root / "summary.json")
    treatment = _load_json(treatment_root / "summary.json")
    blockers = []
    expected = (
        (baseline, "baseline", False, "baseline"),
        (treatment, "pex", True, "treatment"),
    )
    for summary, arm, attached, label in expected:
        if summary.get("arm") != arm or summary.get("pex_attached") is not attached:
            blockers.append(f"{label} summary has the wrong arm identity")
        if summary.get("source_unchanged") is not True:
            blockers.append(f"{label} source was not retained unchanged")
        if summary.get("owned_server_exited") is not True:
            blockers.append(f"{label} owned server exit is unproven")
        if summary.get("error_type") is not None:
            blockers.append(f"{label} ended with {summary.get('error_type')}")
        if summary.get("infrastructure_abort_reason") is not None:
            blockers.append(f"{label} has an infrastructure abort")

    for field in (
        "source_commit",
        "requested_case_count",
        "script_sha256",
        "completion_fence_sha256",
        "worker_model",
        "worker_provider",
        "worker_credential_source",
        "supervisor_provider",
        "supervisor_credential_source",
        "pex_mode",
    ):
        if baseline.get(field) != treatment.get(field):
            blockers.append(f"paired {field} mismatch")

    baseline_cases = baseline.get("cases")
    treatment_cases = treatment.get("cases")
    if not isinstance(baseline_cases, list) or not isinstance(treatment_cases, list):
        blockers.append("both summaries must contain case lists")
        baseline_cases, treatment_cases = [], []
    if len(baseline_cases) != len(treatment_cases):
        blockers.append("paired case count mismatch")

    pairs = []
    for index, (base, pex) in enumerate(zip(baseline_cases, treatment_cases, strict=False), 1):
        if not isinstance(base, dict) or not isinstance(pex, dict):
            blockers.append(f"case {index} receipt is malformed")
            continue
        identity = (base.get("number"), base.get("case"))
        if identity != (pex.get("number"), pex.get("case")):
            blockers.append(f"case {index} identity mismatch")
            continue
        number, case_name = identity
        if (
            isinstance(number, bool)
            or not isinstance(number, int)
            or not 1 <= number <= 10
            or not isinstance(case_name, str)
            or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", case_name) is None
        ):
            blockers.append(f"case {index} identity is invalid")
            continue
        if base.get("arm") != "baseline" or base.get("pex_attached") is not False:
            blockers.append(f"case {index} baseline identity mismatch")
        if pex.get("arm") != "pex" or pex.get("pex_attached") is not True:
            blockers.append(f"case {index} treatment identity mismatch")
        if base.get("worker_model") != pex.get("worker_model"):
            blockers.append(f"case {index} worker model mismatch")
        if base.get("worker_provider") != pex.get("worker_provider"):
            blockers.append(f"case {index} worker provider mismatch")
        if base.get("worker_credential_source") != pex.get("worker_credential_source"):
            blockers.append(f"case {index} worker credential source mismatch")
        for root, receipt, arm in (
            (baseline_root, base, "baseline"),
            (treatment_root, pex, "treatment"),
        ):
            case_root = root / f"case-{number:02d}-{case_name}"
            if not _valid_sse_capture(case_root, receipt):
                blockers.append(f"case {index} {arm} raw SSE capture is missing or invalid")
        baseline_task = baseline_root / f"case-{number:02d}-{case_name}" / "public-task.json"
        treatment_task = treatment_root / f"case-{number:02d}-{case_name}" / "public-task.json"
        if not baseline_task.is_file() or not treatment_task.is_file():
            blockers.append(f"case {index} public task evidence is missing")
            continue
        baseline_task_sha = _sha256(baseline_task)
        treatment_task_sha = _sha256(treatment_task)
        if baseline_task_sha != treatment_task_sha:
            blockers.append(f"case {index} public task mismatch")
        base_wall = base.get("wall_seconds")
        pex_wall = pex.get("wall_seconds")
        if isinstance(base_wall, bool) or not isinstance(base_wall, (int, float)):
            blockers.append(f"case {index} baseline wall time is unavailable")
            continue
        if isinstance(pex_wall, bool) or not isinstance(pex_wall, (int, float)):
            blockers.append(f"case {index} treatment wall time is unavailable")
            continue
        pairs.append(
            {
                "number": identity[0],
                "case": identity[1],
                "public_task_sha256": baseline_task_sha,
                "baseline_success": base.get("passed") is True,
                "pex_success": pex.get("passed") is True,
                "baseline_wall_seconds": base_wall,
                "pex_wall_seconds": pex_wall,
                "pex_minus_baseline_wall_seconds": round(pex_wall - base_wall, 2),
                "pex_followup_count": pex.get("followup_count"),
                "pex_model_call_count": pex.get("model_call_count"),
            }
        )

    if baseline.get("passed") is not True or treatment.get("passed") is not True:
        blockers.append("both paired runs must pass before comparative metrics are reported")
    comparable = not blockers and len(pairs) == len(baseline_cases) > 0
    deltas = [row["pex_minus_baseline_wall_seconds"] for row in pairs]
    metrics = None
    if comparable:
        metrics = {
            "case_count": len(pairs),
            "baseline_successes": sum(row["baseline_success"] for row in pairs),
            "pex_successes": sum(row["pex_success"] for row in pairs),
            "mean_wall_delta_seconds": round(statistics.fmean(deltas), 2),
            "median_wall_delta_seconds": round(statistics.median(deltas), 2),
            "pex_followups": sum(int(row["pex_followup_count"] or 0) for row in pairs),
            "pex_model_calls": sum(int(row["pex_model_call_count"] or 0) for row in pairs),
        }
    pex_mode = baseline.get("pex_mode") if comparable else None
    deterministic = pex_mode == "deterministic"
    return {
        "schema": "pex.opencode-paired-diagnostic.v2",
        "comparable": comparable,
        "comparative_benchmark": False,
        "claim_boundary": (
            "A bounded paired diagnostic over small public artifact tasks. "
            + (
                "PEX semantic supervision was explicitly disabled; only attachment, "
                "observation, deterministic policy, restraint, and overhead are measured. "
                if deterministic
                else ""
            )
            + "It is not a general productivity benchmark or leaderboard result."
        ),
        "source_commit": baseline.get("source_commit") if comparable else None,
        "worker_provider": baseline.get("worker_provider") if comparable else None,
        "worker_model": baseline.get("worker_model") if comparable else None,
        "worker_credential_source": (
            baseline.get("worker_credential_source") if comparable else None
        ),
        "supervisor_provider": baseline.get("supervisor_provider") if comparable else None,
        "supervisor_credential_source": (
            baseline.get("supervisor_credential_source") if comparable else None
        ),
        "pex_mode": pex_mode,
        "semantic_supervision_enabled": False if deterministic else (True if comparable else None),
        "blockers": blockers,
        "pairs": pairs,
        "metrics": metrics,
    }


def main() -> int:
    args = _parse_cli()
    report = build_report(args.baseline, args.treatment)
    serialized = json.dumps(report, indent=2) + "\n"
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        output.write(serialized)
    print(serialized, end="")
    return 0 if report["comparable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
