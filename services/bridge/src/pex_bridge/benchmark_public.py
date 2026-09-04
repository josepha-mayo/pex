"""Read the sanitized benchmark summary without importing benchmark internals.

The live supervisor must never import the hidden evaluator or parse worker logs.
The private benchmark controller emits one aggregate JSON artifact only after a
coherent run freezes; this module exposes that artifact to the command deck.
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_MAX_BYTES = 1_000_000
_RUN_FIELDS = {
    "id",
    "name",
    "status",
    "arm",
    "harness",
    "created_at",
    "manifest_hash",
    "benchmark_hash",
    "frozen",
    "metrics",
}
_METRIC_FIELDS = {
    "task_success_rate",
    "human_interventions_per_success",
    "useful_interventions",
    "harmful_interventions",
    "context_handoffs",
    "pex_input_tokens",
    "pex_output_tokens",
    "tasks",
}


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r} is not allowed")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _require_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError(f"invalid {label}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid {label}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"invalid {label}")
    return value


def _default_path() -> Path:
    configured = os.environ.get("PEX_BENCH_SUMMARY")
    if configured:
        return Path(configured).expanduser()
    repo_candidate = (
        Path(__file__).resolve().parents[4] / "benchmarks" / "results" / "frozen_summary.json"
    )
    return repo_candidate


def load_public_summary(path: str | Path | None = None) -> dict[str, Any]:
    summary_path = Path(path).expanduser() if path else _default_path()
    if not summary_path.is_file():
        return {
            "runs": [],
            "status": "unfrozen",
            "message": "No coherent frozen benchmark run has been published.",
        }
    try:
        if summary_path.stat().st_size > _MAX_BYTES:
            raise ValueError("summary exceeds the public artifact size limit")
        with summary_path.open("rb") as handle:
            content = handle.read(_MAX_BYTES + 1)
        if len(content) > _MAX_BYTES:
            raise ValueError("summary exceeds the public artifact size limit")
        raw = json.loads(
            content.decode("utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )
        return _validate_summary(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {
            "runs": [],
            "status": "invalid",
            "message": (
                "Benchmark summary failed integrity validation "
                f"({type(exc).__name__})."
            ),
        }


def _validate_summary(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("unsupported summary schema")
    manifest_hash = raw.get("manifest_sha256")
    benchmark_hash = raw.get("benchmark_sha256")
    result_hash = raw.get("result_sha256")
    if not isinstance(manifest_hash, str) or not _SHA256.fullmatch(manifest_hash):
        raise ValueError("invalid manifest fingerprint")
    if not isinstance(result_hash, str) or not _SHA256.fullmatch(result_hash):
        raise ValueError("invalid result fingerprint")
    if not isinstance(benchmark_hash, str) or not _SHA256.fullmatch(benchmark_hash):
        raise ValueError("invalid benchmark fingerprint")
    source_runs = raw.get("runs")
    if not isinstance(source_runs, list) or len(source_runs) != 4:
        raise ValueError("summary must contain exactly four presentation arms")
    expected_arms = {"cursor", "cursor_pex", "codex", "codex_pex"}
    run_id = raw.get("run_id")
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run id")
    generated_at = _require_timestamp(raw.get("generated_at"), "generation timestamp")
    seen: set[str] = set()
    runs: list[dict[str, Any]] = []
    for source in source_runs:
        if not isinstance(source, dict):
            raise ValueError("run summary entry is not an object")
        arm = source.get("arm")
        if arm not in expected_arms or arm in seen:
            raise ValueError("summary arms are missing or duplicated")
        if source.get("frozen") is not True:
            raise ValueError("public run is not frozen")
        if source.get("status") != "frozen":
            raise ValueError("public run status is not frozen")
        if source.get("harness") != str(arm).removesuffix("_pex"):
            raise ValueError("public run harness does not match its arm")
        if source.get("id") != f"{run_id}:{arm}":
            raise ValueError("public run id does not match its frozen run and arm")
        name = source.get("name")
        if not isinstance(name, str) or not 1 <= len(name) <= 512:
            raise ValueError("public run name is invalid")
        _require_timestamp(source.get("created_at"), "public run created_at")
        if source.get("manifest_hash") != manifest_hash:
            raise ValueError("run manifest fingerprint mismatch")
        if source.get("benchmark_hash") != benchmark_hash:
            raise ValueError("run benchmark fingerprint mismatch")
        metrics = source.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError("run metrics are missing")
        if set(metrics) != _METRIC_FIELDS:
            raise ValueError("run metrics do not match the public aggregate schema")
        for key, value in metrics.items():
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise ValueError("run metric is not numeric")
            if value is not None and (not math.isfinite(float(value)) or value < 0):
                raise ValueError("run metric is negative or non-finite")
            if key in {
                "useful_interventions",
                "harmful_interventions",
                "context_handoffs",
                "pex_input_tokens",
                "pex_output_tokens",
                "tasks",
            } and value is not None and not isinstance(value, int):
                raise ValueError("run count metric is not an integer")
        success_rate = metrics["task_success_rate"]
        if success_rate is None or success_rate > 1:
            raise ValueError("task success rate is outside [0, 1]")
        if not isinstance(metrics["tasks"], int) or metrics["tasks"] < 1:
            raise ValueError("run task count is invalid")
        seen.add(str(arm))
        runs.append({key: source[key] for key in _RUN_FIELDS if key in source})
    if seen != expected_arms:
        raise ValueError("summary does not contain all presentation arms")
    return {
        "runs": runs,
        "status": "frozen",
        "message": "Aggregate frozen benchmark evidence; raw worker logs are excluded.",
        "run_id": run_id,
        "generated_at": generated_at,
        "manifest_sha256": manifest_hash,
        "benchmark_sha256": benchmark_hash,
        "result_sha256": result_hash,
    }
