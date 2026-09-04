"""Fail-closed, reproducible analysis for one coherent PexBench run.

Partial, aborted, mixed-fingerprint, or out-of-order runs produce blockers and
no metrics. Raw JSONL is read-only; derived artifacts are created in a new
directory and never replace prior output.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import boundary  # noqa: E402
import four_arm  # noqa: E402
import runner  # noqa: E402

_BOOTSTRAP_SAMPLES = 10_000


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total <= 0:
        return None
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return [max(0.0, centre - margin), min(1.0, centre + margin)]


def _exact_mcnemar(baseline: list[bool], treatment: list[bool]) -> dict[str, Any]:
    regressed = sum(base and not treated for base, treated in zip(baseline, treatment, strict=True))
    improved = sum(not base and treated for base, treated in zip(baseline, treatment, strict=True))
    discordant = regressed + improved
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(
            math.comb(discordant, k) for k in range(min(regressed, improved) + 1)
        ) / (2**discordant)
        p_value = min(1.0, 2 * tail)
    return {
        "baseline_only_successes": regressed,
        "treatment_only_successes": improved,
        "discordant_pairs": discordant,
        "two_sided_exact_p_value": p_value,
    }


def _bootstrap_indices(seed: str, sample: int, draw: int, size: int) -> int:
    digest = hashlib.sha256(f"{seed}|{sample}|{draw}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % size


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(probability * len(ordered)) - 1))
    return ordered[index]


def _paired_bootstrap_interval(
    pairs: list[tuple[float, float]],
    *,
    seed: str,
    statistic: Callable[[list[float]], float] = statistics.fmean,
) -> list[float] | None:
    if not pairs:
        return None
    differences = [treated - base for base, treated in pairs]
    estimates: list[float] = []
    for sample in range(_BOOTSTRAP_SAMPLES):
        selected = [
            differences[_bootstrap_indices(seed, sample, draw, len(differences))]
            for draw in range(len(differences))
        ]
        estimates.append(float(statistic(selected)))
    return [_percentile(estimates, 0.025), _percentile(estimates, 0.975)]


def _arm_summary(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    selected = [row for row in rows if row.get("arm") == arm]
    successes = sum(row.get("success") is True for row in selected)
    interventions = sum(int(row.get("human_interventions") or 0) for row in selected)
    intervention_requests = sum(
        int(row.get("human_intervention_requests") or 0) for row in selected
    )
    wall = [
        float(row["execution_wall_seconds"])
        for row in selected
        if isinstance(row.get("execution_wall_seconds"), (int, float))
        and not isinstance(row.get("execution_wall_seconds"), bool)
    ]
    human_active = [
        float(row["human_active_seconds"])
        for row in selected
        if (row.get("measurement_availability") or {}).get("human_active_seconds") is True
        and isinstance(row.get("human_active_seconds"), (int, float))
        and not isinstance(row.get("human_active_seconds"), bool)
    ]
    combined_tokens = [
        int((row.get("combined_metrics") or {}).get("input_tokens") or 0)
        + int((row.get("combined_metrics") or {}).get("output_tokens") or 0)
        for row in selected
        if (row.get("combined_metrics") or {}).get("tokens_available") is True
    ]
    pex_tokens = [
        int((row.get("pex_metrics") or {}).get("input_tokens") or 0)
        + int((row.get("pex_metrics") or {}).get("output_tokens") or 0)
        for row in selected
        if (row.get("pex_metrics") or {}).get("tokens_available") is True
    ]
    audits = [
        audit
        for row in selected
        for audit in ((row.get("pex") or {}).get("audits") or [])
        if isinstance(audit, dict)
    ]
    intervention_audits = [audit for audit in audits if audit.get("actual_action_sent")]
    judged_help = [
        (audit.get("result_afterward") or {}).get("helped")
        for audit in intervention_audits
        if isinstance(audit.get("result_afterward"), dict)
        and type((audit.get("result_afterward") or {}).get("helped")) is bool
    ]
    pex_interventions = sum(
        int((row.get("pex_metrics") or {}).get("interventions") or 0)
        for row in selected
    )
    return {
        "arm": arm,
        "tasks": len(selected),
        "successes": successes,
        "task_success_rate": successes / len(selected),
        "task_success_wilson_95": _wilson(successes, len(selected)),
        "human_interventions": interventions,
        "human_intervention_requests": intervention_requests,
        "human_interventions_per_task": interventions / len(selected),
        "human_interventions_per_success": interventions / successes if successes else None,
        "human_active_seconds_total": (
            sum(human_active) if len(human_active) == len(selected) else None
        ),
        "human_active_seconds_observed_total": sum(human_active),
        "median_human_active_seconds": (
            statistics.median(human_active) if human_active else None
        ),
        "human_active_seconds_per_success": (
            sum(human_active) / successes
            if successes and len(human_active) == len(selected)
            else None
        ),
        "human_active_seconds_missing": len(selected) - len(human_active),
        "median_execution_wall_seconds": statistics.median(wall) if wall else None,
        "execution_wall_missing": len(selected) - len(wall),
        "combined_tokens_total": sum(combined_tokens)
        if len(combined_tokens) == len(selected)
        else None,
        "combined_tokens_missing": len(selected) - len(combined_tokens),
        "pex_tokens_total": sum(pex_tokens) if len(pex_tokens) == len(selected) else None,
        "pex_tokens_missing": len(selected) - len(pex_tokens),
        "pex_interventions": pex_interventions,
        "helpful_pex_interventions": sum(value is True for value in judged_help),
        "harmful_pex_interventions": sum(value is False for value in judged_help),
        "pex_intervention_judgments_missing": max(0, pex_interventions - len(judged_help)),
    }


def _harness_comparison(
    rows: list[dict[str, Any]], harness: str, bootstrap_seed: str
) -> dict[str, Any]:
    by_key = {(str(row["arm"]), str(row["task"])): row for row in rows}
    tasks = sorted({str(row["task"]) for row in rows})
    baseline_rows = [by_key[(harness, task)] for task in tasks]
    treatment_rows = [by_key[(f"{harness}_pex", task)] for task in tasks]
    baseline_success = [row["success"] is True for row in baseline_rows]
    treatment_success = [row["success"] is True for row in treatment_rows]
    baseline_rate = sum(baseline_success) / len(tasks)
    treatment_rate = sum(treatment_success) / len(tasks)
    success_pairs = [
        (float(base), float(treated))
        for base, treated in zip(baseline_success, treatment_success, strict=True)
    ]
    wall_pairs: list[tuple[float, float]] = []
    for baseline, treatment in zip(baseline_rows, treatment_rows, strict=True):
        left = baseline.get("execution_wall_seconds")
        right = treatment.get("execution_wall_seconds")
        if all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in (left, right)
        ):
            wall_pairs.append((float(left), float(right)))
    intervention_pairs = [
        (
            float(baseline.get("human_interventions") or 0),
            float(treatment.get("human_interventions") or 0),
        )
        for baseline, treatment in zip(baseline_rows, treatment_rows, strict=True)
    ]
    human_active_pairs: list[tuple[float, float]] = []
    for baseline, treatment in zip(baseline_rows, treatment_rows, strict=True):
        left_available = (baseline.get("measurement_availability") or {}).get(
            "human_active_seconds"
        ) is True
        right_available = (treatment.get("measurement_availability") or {}).get(
            "human_active_seconds"
        ) is True
        left = baseline.get("human_active_seconds")
        right = treatment.get("human_active_seconds")
        if left_available and right_available and all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in (left, right)
        ):
            human_active_pairs.append((float(left), float(right)))
    return {
        "harness": harness,
        "paired_tasks": len(tasks),
        "baseline_success_rate": baseline_rate,
        "treatment_success_rate": treatment_rate,
        "absolute_success_lift": treatment_rate - baseline_rate,
        "relative_success_lift": (
            (treatment_rate - baseline_rate) / baseline_rate if baseline_rate else None
        ),
        "paired_success_lift_bootstrap_95": _paired_bootstrap_interval(
            success_pairs, seed=f"{bootstrap_seed}|{harness}|success"
        ),
        "mcnemar": _exact_mcnemar(baseline_success, treatment_success),
        "median_wall_delta_seconds": (
            statistics.median(treated - base for base, treated in wall_pairs)
            if wall_pairs
            else None
        ),
        "paired_wall_delta_bootstrap_95": _paired_bootstrap_interval(
            wall_pairs,
            seed=f"{bootstrap_seed}|{harness}|wall",
            statistic=statistics.median,
        ),
        "wall_pairs_available": len(wall_pairs),
        "median_human_intervention_delta": statistics.median(
            treated - base for base, treated in intervention_pairs
        ),
        "paired_human_intervention_delta_bootstrap_95": _paired_bootstrap_interval(
            intervention_pairs,
            seed=f"{bootstrap_seed}|{harness}|human",
            statistic=statistics.median,
        ),
        "median_human_active_seconds_delta": (
            statistics.median(treated - base for base, treated in human_active_pairs)
            if human_active_pairs
            else None
        ),
        "paired_human_active_seconds_delta_bootstrap_95": _paired_bootstrap_interval(
            human_active_pairs,
            seed=f"{bootstrap_seed}|{harness}|human-active",
            statistic=statistics.median,
        ),
        "human_active_seconds_pairs_available": len(human_active_pairs),
    }


def analyze_run(path: Path) -> dict[str, Any]:
    """Return metrics only when the raw run passes the full freeze validator."""
    resolved = path.resolve()
    results_root = runner.RESULTS.resolve()
    if (
        not resolved.is_relative_to(results_root)
        or resolved.parent != results_root
        or runner._is_link_like(path)
    ):
        return {
            "schema_version": 1,
            "status": "no_go",
            "run_id": path.stem,
            "metrics": None,
            "blockers": ["raw run must be a regular top-level benchmark result"],
            "rows_observed": 0,
            "abort_appendix": [],
            "note": "No statistics are emitted for an incomplete or incoherent run.",
        }
    try:
        with runner._exclusive_result_lock(resolved):
            blockers = four_arm._run_blockers(resolved)
            rows = runner.read_result_records(resolved)
            result_sha256 = boundary.sha256_file(
                resolved,
                max_bytes=runner._MAX_RESULT_BYTES,
            )
    except (OSError, ValueError) as exc:
        rows = []
        blockers = [str(exc)]
        result_sha256 = None
    if blockers:
        return {
            "schema_version": 1,
            "status": "no_go",
            "run_id": resolved.stem,
            "metrics": None,
            "blockers": list(dict.fromkeys(blockers)),
            "rows_observed": len(rows),
            "abort_appendix": [
                {
                    "task": row.get("task"),
                    "arm": row.get("arm"),
                    "abort_reason": row.get("abort_reason"),
                    "abort_detail": row.get("abort_detail"),
                }
                for row in rows
                if row.get("record_type") == "abort"
            ],
            "note": "No statistics are emitted for an incomplete or incoherent run.",
        }
    protocol = runner.protocol_config()
    bootstrap_seed = str(protocol["reporting"]["bootstrap_seed"])
    arm_summaries = [_arm_summary(rows, arm) for arm in runner.PRESENTATION_ARMS]
    failures = [
        {
            "task": row["task"],
            "arm": row["arm"],
            "fail_reason": row.get("fail_reason"),
            "evaluator_reasons": list(row.get("reasons") or []),
        }
        for row in rows
        if row.get("success") is False
    ]
    return {
        "schema_version": 1,
        "status": "coherent",
        "run_id": resolved.stem,
        "metrics": {
            "arms": arm_summaries,
            "within_harness": [
                _harness_comparison(rows, harness, bootstrap_seed)
                for harness in ("cursor", "codex")
            ],
        },
        "failed_run_appendix": failures,
        "provenance": {
            "result_sha256": result_sha256,
            "manifest_sha256": runner.manifest_sha256(),
            "benchmark_sha256": runner.benchmark_sha256(),
            "protocol_sha256": runner.protocol_sha256(),
            "schedule_sha256": runner.experiment_plan_sha256(),
            "controller_sha256": runner.controller_sha256(),
            "harness_versions": sorted(
                {str(row["harness_version"]) for row in rows}
            ),
            "worker_models": sorted({str(row["worker_model"]) for row in rows}),
            "worker_config_sha256": sorted(
                {str(row["worker_config_sha256"]) for row in rows}
            ),
            "model_settings_sha256": sorted(
                {str(row["model_settings_sha256"]) for row in rows}
            ),
            "model_version_evidence": sorted(
                {
                    json.dumps(row["model_version_evidence"], sort_keys=True)
                    for row in rows
                }
            ),
            "controller_environment_sha256": sorted(
                {str(row["controller_environment_sha256"]) for row in rows}
            ),
            "pex_config_sha256": sorted(
                {
                    str(row["pex_config_sha256"])
                    for row in rows
                    if row.get("pex_config_sha256")
                }
            ),
            "network_policy": protocol["network_policy"],
            "budget": protocol["budget"],
            "rerun_policy": protocol["rerun_policy"],
            "abort_policy": protocol["abort_policy"],
        },
        "methods": {
            "paired_binary_test": "two-sided exact McNemar/binomial test",
            "paired_lift_interval": (
                f"{_BOOTSTRAP_SAMPLES} deterministic paired bootstrap resamples, "
                "nearest-rank percentile interval"
            ),
            "marginal_interval": "95% Wilson score interval",
            "continuous_summary": "paired median difference with paired bootstrap interval",
            "causal_scope": "within-harness paired comparison only",
        },
        "limitations": [
            "Worker token usage, active human time, and cost remain null when a harness does "
            "not expose them; complete raw vendor logs and source commits are mandatory freeze "
            "evidence.",
            "Requested model IDs and settings are pinned, but provider-side immutable model "
            "revisions remain unavailable unless the harness supplies them.",
            "The current five-task recovery suite is self-contained management stress, not "
            "the required natural public-repository task set.",
            "Cursor+PEX is admissible only with an observed follow-up in the same conversation; "
            "a saved or replayed stop payload is not evidence of that continuation.",
        ],
    }


def _write_text_exclusive(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _summary_csv(report: dict[str, Any]) -> str:
    import io

    buffer = io.StringIO(newline="")
    fields = [
        "arm",
        "tasks",
        "successes",
        "task_success_rate",
        "task_success_wilson_95",
        "human_interventions",
        "human_intervention_requests",
        "human_interventions_per_task",
        "human_interventions_per_success",
        "human_active_seconds_total",
        "human_active_seconds_observed_total",
        "median_human_active_seconds",
        "human_active_seconds_per_success",
        "human_active_seconds_missing",
        "median_execution_wall_seconds",
        "execution_wall_missing",
        "combined_tokens_total",
        "combined_tokens_missing",
        "pex_tokens_total",
        "pex_tokens_missing",
        "pex_interventions",
        "helpful_pex_interventions",
        "harmful_pex_interventions",
        "pex_intervention_judgments_missing",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in report["metrics"]["arms"]:
        serialized = dict(row)
        serialized["task_success_wilson_95"] = json.dumps(
            serialized["task_success_wilson_95"], separators=(",", ":")
        )
        writer.writerow(serialized)
    return buffer.getvalue()


def _success_svg(report: dict[str, Any]) -> str:
    bars = report["metrics"]["arms"]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="300" '
        'viewBox="0 0 720 300" role="img" aria-label="Task success rate by arm">',
        '<rect width="720" height="300" fill="white"/>',
        '<text x="20" y="28" font-family="sans-serif" font-size="18">Task success rate</text>',
    ]
    for index, row in enumerate(bars):
        x = 35 + index * 170
        height = round(float(row["task_success_rate"]) * 200, 3)
        y = 250 - height
        parts.append(
            f'<rect x="{x}" y="{y}" width="110" height="{height}" fill="#3157d5"/>'
        )
        parts.append(
            f'<text x="{x}" y="275" font-family="sans-serif" font-size="13">{row["arm"]}</text>'
        )
    parts.append("</svg>\n")
    return "".join(parts)


def write_report(report: dict[str, Any], output_dir: Path) -> list[Path]:
    if report.get("status") != "coherent" or report.get("metrics") is None:
        raise ValueError("refusing to write statistical artifacts for a NO-GO run")
    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "analysis.py": Path(__file__).read_text(encoding="utf-8"),
        "benchmark_manifest.yaml": runner.MANIFEST.read_text(encoding="utf-8"),
        "summary.csv": _summary_csv(report),
        "statistical_report.json": json.dumps(
            report, indent=2, sort_keys=True, allow_nan=False
        )
        + "\n",
        "failed_runs.json": json.dumps(
            report["failed_run_appendix"],
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        "task_success.svg": _success_svg(report),
    }
    written: list[Path] = []
    for name, content in artifacts.items():
        path = output / name
        _write_text_exclusive(path, content)
        written.append(path)
    manifest = {
        "schema_version": 1,
        "analysis_script": "analysis.py",
        "analysis_script_sha256": hashlib.sha256(
            (output / "analysis.py").read_bytes()
        ).hexdigest(),
        "artifacts": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in written
        },
        "raw_result_sha256": report["provenance"]["result_sha256"],
    }
    manifest_path = output / "analysis_manifest.json"
    _write_text_exclusive(
        manifest_path,
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )
    return [*written, manifest_path]


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and analyze one PexBench run")
    parser.add_argument("run_id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    path = runner.result_path(args.run_id)
    report = analyze_run(path)
    if args.output and report["status"] == "coherent":
        report["written"] = [str(path) for path in write_report(report, args.output)]
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    raise SystemExit(0 if report["status"] == "coherent" else 2)


if __name__ == "__main__":
    main()
