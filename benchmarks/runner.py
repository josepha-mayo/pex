"""PexBench runner.

Never invents scores. A run file is written only after arms execute.
Presentation code must read jsonl; it must not hand-edit it.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import yaml
from yaml.constructor import ConstructorError
from yaml.resolver import BaseResolver

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "manifest.yaml"
RESULTS = ROOT / "results"
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_FROZEN_METADATA = {
    "frozen",
    "frozen_at",
    "frozen_benchmark_sha256",
    "frozen_result_sha256",
    "frozen_run_id",
    "frozen_task_count",
}
_CONTROLLER_FILES = (
    "boundary.py",
    "evaluator.py",
    "four_arm.py",
    "pex_attach.py",
    "cursor_isolated_stop.py",
    "cursor_capture.py",
    "pex_supervisor_process.py",
    "report.py",
    "runner.py",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
PRESENTATION_ARMS = ("cursor", "cursor_pex", "codex", "codex_pex")
RECOVERY_TASK_IDS = (
    "pexbench_001_premature_stop",
    "pexbench_002_drift",
    "pexbench_003_permission_spam",
    "pexbench_004_false_claim",
    "pexbench_005_handoff",
)
_MAX_COUNT = 10**12
_MAX_CONTROLLER_FILE_BYTES = 4 * 1024 * 1024
_MAX_MANIFEST_BYTES = 512_000
_MAX_RESULT_BYTES = 16 * 1024 * 1024
_MAX_RESULT_RECORD_BYTES = 1024 * 1024
_MAX_RESULT_RECORDS = 100


def _is_link_like(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


def _bounded_file_sha256(path: Path, limit: int, label: str) -> str:
    if _is_link_like(path) or not path.is_file():
        raise ValueError(f"{label} must be a regular file")
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(min(1024 * 1024, limit + 1)):
                total += len(chunk)
                if total > limit:
                    raise ValueError(f"{label} exceeds the size bound")
                digest.update(chunk)
    except OSError as exc:
        raise ValueError(f"{label} is unreadable") from exc
    return digest.hexdigest()


class _UniqueSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects ambiguous duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueSafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict:
    loader.flatten_mapping(node)
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueSafeLoader.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def load_manifest() -> dict:
    if _is_link_like(MANIFEST) or not MANIFEST.is_file():
        raise ValueError("benchmark manifest must be a regular file")
    try:
        with MANIFEST.open("rb") as handle:
            raw = handle.read(_MAX_MANIFEST_BYTES + 1)
    except OSError as exc:
        raise ValueError("benchmark manifest is unreadable") from exc
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise ValueError("benchmark manifest exceeds the size bound")
    try:
        text = raw.decode("utf-8")
        if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(text)):
            raise ValueError("YAML aliases are not allowed")
        loaded = yaml.load(text, Loader=_UniqueSafeLoader)
    except (UnicodeError, yaml.YAMLError, RecursionError, ValueError) as exc:
        raise ValueError("benchmark manifest is not strict bounded UTF-8 YAML") from exc
    if not isinstance(loaded, dict):
        raise ValueError("benchmark manifest must be a mapping")
    return loaded


def manifest_sha256(manifest: dict | None = None) -> str:
    """Hash the predeclared experiment, excluding post-run freeze metadata."""
    source = load_manifest() if manifest is None else manifest
    config = {key: value for key, value in source.items() if key not in _FROZEN_METADATA}
    return _json_sha256(config)


def evaluator_sha256() -> str:
    return _bounded_file_sha256(
        ROOT / "evaluator.py",
        _MAX_CONTROLLER_FILE_BYTES,
        "benchmark evaluator",
    )


def task_package_sha256(manifest: dict | None = None) -> str:
    """Hash every declared public prompt and private deterministic task package."""
    source = load_manifest() if manifest is None else manifest
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in source.get("tasks") or []:
        task_id = str((item or {}).get("id") or "")
        if not _RUN_ID.fullmatch(task_id) or task_id in seen:
            raise ValueError(f"invalid or duplicate task id {task_id!r}")
        seen.add(task_id)
        task_dir = ROOT / "tasks" / task_id
        for name in ("prompt.md", "metadata.yaml"):
            path = task_dir / name
            if not path.is_file():
                raise ValueError(f"declared task lacks {task_id}/{name}")
            rows.append(
                {
                    "path": f"tasks/{task_id}/{name}",
                    "sha256": _bounded_file_sha256(
                        path,
                        _MAX_MANIFEST_BYTES,
                        f"benchmark task {task_id}/{name}",
                    ),
                }
            )
    return _json_sha256(rows)


def controller_sha256() -> str:
    """Hash controller code capable of seeding, supervising, recording, or scoring."""
    rows = []
    for name in _CONTROLLER_FILES:
        path = ROOT / name
        rows.append(
            {
                "path": name,
                "sha256": _bounded_file_sha256(
                    path,
                    _MAX_CONTROLLER_FILE_BYTES,
                    f"benchmark controller {name}",
                ),
            }
        )
    return _json_sha256(rows)


def benchmark_sha256(manifest: dict | None = None) -> str:
    source = load_manifest() if manifest is None else manifest
    return _json_sha256(
        {
            "manifest_sha256": manifest_sha256(source),
            "task_package_sha256": task_package_sha256(source),
            "controller_sha256": controller_sha256(),
        }
    )


def protocol_config(manifest: dict | None = None) -> dict:
    """Return the predeclared experiment protocol or fail closed."""
    source = load_manifest() if manifest is None else manifest
    protocol = source.get("protocol")
    if not isinstance(protocol, dict) or protocol.get("schema_version") != 1:
        raise ValueError("benchmark manifest lacks protocol schema version 1")
    randomization = protocol.get("randomization")
    if not isinstance(randomization, dict) or randomization.get("algorithm") != (
        "sha256_sorted_paired_blocks_v1"
    ) or randomization.get("block") != "task_within_harness" or randomization.get(
        "within_block"
    ) != "sha256_condition_order":
        raise ValueError("benchmark manifest has an unsupported randomization protocol")
    if not str(randomization.get("seed") or "").strip():
        raise ValueError("benchmark randomization seed must be predeclared")
    randomization_seed = str(randomization["seed"])
    if len(randomization_seed) > 512 or any(
        ord(character) < 32 for character in randomization_seed
    ):
        raise ValueError("benchmark randomization seed is invalid")
    budget = protocol.get("budget")
    if (
        not isinstance(budget, dict)
        or budget.get("regime") != "natural_completion"
        or type(budget.get("task_wall_seconds")) is not int
        or not 0 < budget["task_wall_seconds"] <= 86_400
        or budget.get("includes_worker_and_pex") is not True
        or budget.get("evaluator_outside_task_budget") is not True
        or type(budget.get("max_pex_followups")) is not int
        or not 0 <= budget["max_pex_followups"] <= 10
        or type(budget.get("max_supervisor_decision_seconds")) is not int
        or not 0 < budget["max_supervisor_decision_seconds"] <= budget["task_wall_seconds"]
    ):
        raise ValueError("benchmark protocol lacks a valid worker-plus-PEX budget")
    rerun = protocol.get("rerun_policy")
    abort = protocol.get("abort_policy")
    if (
        not isinstance(rerun, dict)
        or rerun.get("selective_reruns") != "forbidden"
        or rerun.get("completed_task_reruns") != "forbidden"
        or rerun.get("infrastructure_abort_recovery")
        != "restart_entire_experiment_with_new_run_id"
        or rerun.get("retain_aborted_raw_run") is not True
        or not isinstance(abort, dict)
        or tuple(abort.get("abort_entire_run_on") or ())
        != (
            "vendor_outage",
            "harness_disconnect",
            "controller_crash",
            "budget_exhaustion",
            "provenance_failure",
            "operator_intervention",
        )
        or abort.get("resume_same_run_id") is not False
        or abort.get("preserve_partial_jsonl") is not True
    ):
        raise ValueError("benchmark rerun and abort policy is not fail-closed")
    network = protocol.get("network_policy")
    reporting = protocol.get("reporting")
    if (
        not isinstance(network, dict)
        or network.get("codex") != "workspace_write_network_disabled"
        or network.get("cursor")
        not in {
            "unchanged_between_pairs_but_not_controller_verified",
            "synchronous_controller_network_policy_verified",
        }
        or not isinstance(reporting, dict)
        or not str(reporting.get("bootstrap_seed") or "").strip()
        or reporting.get("require_complete_coherent_run") is not True
        or reporting.get("primary_test") != "exact_mcnemar"
        or reporting.get("paired_lift_interval")
        != "deterministic_paired_bootstrap_95"
        or reporting.get("marginal_interval") != "wilson_95"
    ):
        raise ValueError("benchmark network or reporting policy is incomplete")
    return protocol


def protocol_sha256(manifest: dict | None = None) -> str:
    return _json_sha256(protocol_config(manifest))


def experiment_plan(manifest: dict | None = None) -> list[dict[str, object]]:
    """Build the deterministic, predeclared paired randomization schedule."""
    source = load_manifest() if manifest is None else manifest
    protocol = protocol_config(source)
    seed = str(protocol["randomization"]["seed"])
    tasks = [str(item.get("id") or "") for item in source.get("tasks") or []]
    if tuple(tasks) != RECOVERY_TASK_IDS:
        raise ValueError("benchmark plan requires exactly the five recovery tasks in order")
    if tuple(source.get("arms") or ()) != PRESENTATION_ARMS:
        raise ValueError("benchmark plan requires the canonical four presentation arms")
    blocks: list[tuple[str, str, str]] = []
    for task in tasks:
        for harness in ("cursor", "codex"):
            block_key = hashlib.sha256(
                f"{seed}|block|{task}|{harness}".encode()
            ).hexdigest()
            blocks.append((block_key, task, harness))
    plan: list[dict[str, object]] = []
    for block_index, (_, task, harness) in enumerate(sorted(blocks), 1):
        arms = (harness, f"{harness}_pex")
        ordered_arms = sorted(
            arms,
            key=lambda arm: hashlib.sha256(
                f"{seed}|condition|{task}|{harness}|{arm}".encode()
            ).hexdigest(),
        )
        for arm in ordered_arms:
            plan.append(
                {
                    "schedule_index": len(plan) + 1,
                    "block_index": block_index,
                    "task": task,
                    "arm": arm,
                    "harness": harness,
                    "condition": "pex" if arm.endswith("_pex") else "baseline",
                }
            )
    return plan


def experiment_plan_sha256(manifest: dict | None = None) -> str:
    return _json_sha256(experiment_plan(manifest))


def scheduled_entry(task: str, arm: str, manifest: dict | None = None) -> dict[str, object]:
    matches = [
        row
        for row in experiment_plan(manifest)
        if row["task"] == task and row["arm"] == arm
    ]
    if len(matches) != 1:
        raise ValueError(f"{arm}/{task} is not uniquely scheduled")
    return matches[0]


def assert_next_scheduled(run_id: str, task: str, arm: str) -> dict[str, object]:
    """Refuse a live controller launch that skips or reorders the frozen plan."""
    manifest = load_manifest()
    if manifest.get("frozen"):
        raise ValueError("benchmark manifest is frozen; no new live run may start")
    path = result_path(run_id)
    if path.is_file():
        chain_errors = verify_result_chain(path)
        if chain_errors:
            raise ValueError("existing run is not immutable: " + chain_errors[0])
        existing = read_result_records(path)
    else:
        existing = []
    if any(row.get("record_type") == "abort" for row in existing):
        raise ValueError("this run id is aborted and cannot be resumed")
    if any(
        row.get("arm") not in PRESENTATION_ARMS
        or row.get("live") is not True
        or row.get("not_a_presentation_arm") is True
        or row.get("run_status") != "completed"
        or row.get("run_id") != run_id
        for row in existing
    ):
        raise ValueError("existing run contains a non-presentation or malformed row")
    expected_fingerprints = {
        "manifest_sha256": manifest_sha256(manifest),
        "evaluator_sha256": evaluator_sha256(),
        "task_package_sha256": task_package_sha256(manifest),
        "controller_sha256": controller_sha256(),
        "benchmark_sha256": benchmark_sha256(manifest),
    }
    if any(
        row.get(field) != expected
        for row in existing
        for field, expected in expected_fingerprints.items()
    ):
        raise ValueError("benchmark code or manifest changed; continue under a new run id")
    completed = [
        row
        for row in existing
        if row.get("arm") in PRESENTATION_ARMS and row.get("run_status") == "completed"
    ]
    plan = experiment_plan(manifest)
    actual_prefix = [
        (row.get("arm"), row.get("task"), row.get("schedule_index")) for row in completed
    ]
    expected_prefix = [
        (row["arm"], row["task"], row["schedule_index"])
        for row in plan[: len(completed)]
    ]
    if actual_prefix != expected_prefix:
        raise ValueError("existing run does not follow the predeclared schedule prefix")
    if len(completed) >= len(plan):
        raise ValueError("this run id already contains the complete experiment")
    expected = plan[len(completed)]
    if expected["task"] != task or expected["arm"] != arm:
        raise ValueError(
            "live run order violates the predeclared schedule: "
            f"expected {expected['arm']}/{expected['task']} at index "
            f"{expected['schedule_index']}"
        )
    return expected


def protocol_record_fields(task: str, arm: str) -> dict[str, object]:
    """Fields every completed presentation record must bind verbatim."""
    protocol = protocol_config()
    scheduled = scheduled_entry(task, arm)
    harness = str(scheduled["harness"])
    network_policy = str((protocol.get("network_policy") or {}).get(harness) or "")
    if not network_policy:
        raise ValueError(f"benchmark protocol lacks a {harness} network policy")
    return {
        "record_schema_version": 2,
        "schedule_index": scheduled["schedule_index"],
        "schedule_block_index": scheduled["block_index"],
        "schedule_sha256": experiment_plan_sha256(),
        "protocol_sha256": protocol_sha256(),
        "attempt": 1,
        "run_status": "completed",
        "harness": harness,
        "condition": scheduled["condition"],
        "budget": dict(protocol["budget"]),
        "network_policy": network_policy,
        "network_policy_sha256": _json_sha256(network_policy),
    }


def _json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def json_sha256(value: object) -> str:
    """Public canonical JSON fingerprint for record subdocuments."""
    return _json_sha256(value)


def record_sha256(record: dict) -> str:
    payload = {key: value for key, value in record.items() if key != "record_sha256"}
    return _json_sha256(payload)


def resource_metric_errors(record: dict) -> list[str]:
    """Validate nullable telemetry and worker/PEX/combined accounting."""
    errors: list[str] = []
    worker = record.get("worker_metrics")
    pex = record.get("pex_metrics")
    combined = record.get("combined_metrics")
    availability = record.get("measurement_availability")
    if not all(isinstance(value, dict) for value in (worker, pex, combined, availability)):
        return ["resource metric groups must be objects"]

    def number(value: object) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and 0 <= value <= _MAX_COUNT
        )

    def count_or_none(value: object) -> bool:
        return value is None or (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value <= _MAX_COUNT
        )

    for name in (
        "worker_tokens",
        "pex_tokens",
        "tool_calls",
        "human_active_seconds",
        "cost_usd",
        "raw_log_hash",
        "repo_commit",
    ):
        if type(availability.get(name)) is not bool:
            errors.append(f"measurement availability {name} must be boolean")
    for field, availability_name in (
        ("human_active_seconds", "human_active_seconds"),
        ("cost_usd", "cost_usd"),
    ):
        value = record.get(field)
        if availability.get(availability_name) is True and not number(value):
            errors.append(f"available {field} must be nonnegative")
        if availability.get(availability_name) is False and value is not None:
            errors.append(f"unavailable {field} must be null")
    repo_commit = record.get("repo_commit")
    if availability.get("repo_commit") is True:
        commit = str(repo_commit or "")
        if len(commit) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in commit
        ):
            errors.append("available repo commit must be an exact hexadecimal revision")
    if availability.get("repo_commit") is False and repo_commit is not None:
        errors.append("unavailable repo commit must be null")
    raw_log = str(record.get("raw_log_sha256") or "")
    if availability.get("raw_log_hash") is True and not _SHA256.fullmatch(raw_log):
        errors.append("available raw log must have a SHA-256 fingerprint")
    if availability.get("raw_log_hash") is False and record.get("raw_log_sha256") is not None:
        errors.append("unavailable raw log fingerprint must be null")

    if not number(worker.get("wall_seconds")):
        errors.append("worker wall time must be nonnegative")
    worker_tokens_available = availability.get("worker_tokens") is True
    for name in ("input_tokens", "output_tokens"):
        value = worker.get(name)
        if (worker_tokens_available and not count_or_none(value)) or (
            worker_tokens_available and value is None
        ):
            errors.append(f"available worker {name} must be a nonnegative integer")
        if not worker_tokens_available and value is not None:
            errors.append(f"unavailable worker {name} must be null")
    if availability.get("tool_calls") is True:
        if not count_or_none(worker.get("tool_calls")) or worker.get("tool_calls") is None:
            errors.append("available worker tool calls must be a nonnegative integer")
    elif worker.get("tool_calls") is not None:
        errors.append("unavailable worker tool calls must be null")

    pex_enabled = pex.get("enabled")
    if type(pex_enabled) is not bool or not number(pex.get("wall_seconds")):
        errors.append("PEX enabled flag or wall time is invalid")
    for name in ("interventions", "followups", "decision_count"):
        if not count_or_none(pex.get(name)) or pex.get(name) is None:
            errors.append(f"PEX {name} must be a nonnegative integer")
    pex_tokens_available = pex.get("tokens_available") is True
    if type(pex.get("tokens_available")) is not bool:
        errors.append("PEX token availability must be boolean")
    if availability.get("pex_tokens") != pex.get("tokens_available"):
        errors.append("PEX token availability flags disagree")
    for name in ("input_tokens", "output_tokens"):
        value = pex.get(name)
        if pex_tokens_available and (not count_or_none(value) or value is None):
            errors.append(f"available PEX {name} must be a nonnegative integer")
        if not pex_tokens_available and value is not None:
            errors.append(f"unavailable PEX {name} must be null")
    if pex_enabled is False and any(
        (
            pex.get("wall_seconds") != 0,
            pex.get("input_tokens") != 0,
            pex.get("output_tokens") != 0,
            pex.get("interventions") != 0,
            pex.get("followups") != 0,
            pex.get("decision_count") != 0,
            pex.get("tokens_available") is not True,
        )
    ):
        errors.append("baseline PEX overhead must be explicit zero with available accounting")

    combined_tokens_available = combined.get("tokens_available") is True
    if type(combined.get("tokens_available")) is not bool:
        errors.append("combined token availability must be boolean")
    expected_combined_tokens = availability.get("worker_tokens") is True and (
        pex.get("tokens_available") is True
    )
    if combined.get("tokens_available") is not expected_combined_tokens:
        errors.append("combined token availability does not match worker and PEX telemetry")
    for name in ("input_tokens", "output_tokens"):
        value = combined.get(name)
        if combined_tokens_available and (not count_or_none(value) or value is None):
            errors.append(f"available combined {name} must be a nonnegative integer")
        if not combined_tokens_available and value is not None:
            errors.append(f"unavailable combined {name} must be null")
        if combined_tokens_available:
            expected = int(worker[name]) + int(pex[name])
            if value != expected:
                errors.append(f"combined {name} does not equal worker plus PEX accounting")
    execution = record.get("execution_wall_seconds")
    if number(execution):
        if not number(combined.get("wall_seconds")) or not math.isclose(
            float(combined.get("wall_seconds") or 0), float(execution), abs_tol=1e-5
        ):
            errors.append("combined wall time does not match execution wall time")
        if (
            number(worker.get("wall_seconds"))
            and number(pex.get("wall_seconds"))
            and not math.isclose(
                float(worker["wall_seconds"]) + float(pex["wall_seconds"]),
                float(execution),
                abs_tol=1e-5,
            )
        ):
            errors.append("worker plus PEX wall time does not match execution wall time")
    total = record.get("wall_time_seconds")
    evaluation = record.get("evaluation_wall_seconds")
    if number(total) and number(execution) and number(evaluation) and (
        float(total) + 1e-5 < float(execution) + float(evaluation)
    ):
        errors.append("total wall time excludes execution or evaluation time")
    return errors


def pex_audit_errors(record: dict) -> list[str]:
    """Bind treatment resource counters to the retained supervisor audit rows."""
    arm = str(record.get("arm") or "")
    if not arm.endswith("_pex"):
        return []
    pex = record.get("pex")
    metrics = record.get("pex_metrics")
    if not isinstance(pex, dict) or not isinstance(metrics, dict):
        return ["treatment PEX state and metrics must be objects"]
    audits = pex.get("audits")
    if not isinstance(audits, list) or not audits or any(
        not isinstance(audit, dict) for audit in audits
    ):
        return ["treatment PEX audits must be a non-empty list of objects"]
    errors: list[str] = []
    if metrics.get("decision_count") != len(audits):
        errors.append("PEX decision count does not match retained audits")
    actual_interventions = sum(bool(audit.get("actual_action_sent")) for audit in audits)
    if metrics.get("interventions") != actual_interventions:
        errors.append("PEX intervention count does not match retained audits")
    if metrics.get("followups") != pex.get("followups"):
        errors.append("PEX follow-up count does not match retained supervisor state")
    if pex.get("used_llm") is not any(audit.get("used_llm") is True for audit in audits):
        errors.append("PEX used-LLM flag does not match retained audits")
    for audit in audits:
        for field in ("input_tokens", "output_tokens"):
            value = audit.get(field)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not 0 <= value <= _MAX_COUNT
            ):
                errors.append(f"PEX audit {field} is invalid")
        if audit.get("actual_action_sent") is not None and audit.get(
            "actual_action_sent"
        ) not in {"SEND_NUDGE", "CONTINUE_SESSION", "REQUEST_VERIFICATION"}:
            errors.append("PEX audit contains a non-public actual action")
    if metrics.get("tokens_available") is True:
        for field in ("input_tokens", "output_tokens"):
            if metrics.get(field) != sum(int(audit.get(field) or 0) for audit in audits):
                errors.append(f"PEX {field} does not match retained audits")
    return errors


def read_result_records(path: Path) -> list[dict]:
    records: list[dict] = []
    if _is_link_like(path):
        raise ValueError(f"{path.name} is not a regular immutable result file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{path.name} is not a regular immutable result file") from exc
    try:
        descriptor_stat = os.fstat(descriptor)
        path_stat = os.stat(path, follow_symlinks=False)
        if (
            not stat.S_ISREG(descriptor_stat.st_mode)
            or _is_link_like(path)
            or (descriptor_stat.st_dev, descriptor_stat.st_ino)
            != (path_stat.st_dev, path_stat.st_ino)
        ):
            raise ValueError(f"{path.name} is not a regular immutable result file")
        if descriptor_stat.st_size > _MAX_RESULT_BYTES:
            raise ValueError(f"{path.name} exceeds the immutable result size bound")
        total_bytes = 0
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            for line_number, raw_bytes in enumerate(handle, 1):
                total_bytes += len(raw_bytes)
                if total_bytes > _MAX_RESULT_BYTES:
                    raise ValueError(f"{path.name} exceeds the immutable result size bound")
                if len(raw_bytes) > _MAX_RESULT_RECORD_BYTES:
                    raise ValueError(f"{path.name}:{line_number} exceeds the record size bound")
                try:
                    raw = raw_bytes.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ValueError(f"{path.name}:{line_number} is not UTF-8") from exc
                if not raw.strip():
                    continue
                try:
                    value = json.loads(
                        raw,
                        parse_constant=lambda constant: (_ for _ in ()).throw(
                            ValueError(f"non-finite JSON number {constant}")
                        ),
                        object_pairs_hook=_unique_object,
                    )
                except (json.JSONDecodeError, ValueError, RecursionError) as exc:
                    detail = exc.msg if isinstance(exc, json.JSONDecodeError) else str(exc)
                    raise ValueError(
                        f"{path.name}:{line_number} is invalid JSON: {detail}"
                    ) from exc
                if not isinstance(value, dict):
                    raise ValueError(f"{path.name}:{line_number} is not an object")
                records.append(value)
                if len(records) > _MAX_RESULT_RECORDS:
                    raise ValueError(f"{path.name} exceeds the record count bound")
        final_stat = os.stat(path, follow_symlinks=False)
        if _is_link_like(path) or (
            descriptor_stat.st_dev,
            descriptor_stat.st_ino,
        ) != (final_stat.st_dev, final_stat.st_ino):
            raise ValueError(f"{path.name} changed while it was read")
    finally:
        os.close(descriptor)
    return records


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def verify_result_chain(path: Path) -> list[str]:
    """Verify append order and content hashes without changing the raw result."""
    errors: list[str] = []
    try:
        records = read_result_records(path)
    except (OSError, ValueError) as exc:
        return [str(exc)]
    previous: str | None = None
    for index, record in enumerate(records, 1):
        if record.get("previous_record_sha256") != previous:
            errors.append(f"{path.name}:{index} breaks the append-only hash chain")
        actual = str(record.get("record_sha256") or "")
        if not _SHA256.fullmatch(actual) or actual != record_sha256(record):
            errors.append(f"{path.name}:{index} has an invalid record fingerprint")
        previous = actual or None
    return errors


def result_path(run_id: str) -> Path:
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must be a short filesystem-safe identifier")
    RESULTS.mkdir(parents=True, exist_ok=True)
    return RESULTS / f"{run_id}.jsonl"


@contextmanager
def _exclusive_result_lock(path: Path):
    """Serialize append admission; a stale lock fails closed after a controller crash."""
    if path.exists() and _is_link_like(path):
        raise ValueError("refusing a linked immutable result path")
    lock_path = path.with_suffix(path.suffix + ".lock")
    descriptor = None
    last_exists: FileExistsError | None = None
    for attempt in range(8):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError as exc:
            last_exists = exc
            # Windows can still observe a lock we just released. A live second
            # writer still fails closed after these retries.
            time.sleep(0.025 * (attempt + 1))
    if descriptor is None:
        raise ValueError(f"result append already in progress for {path.stem}") from last_exists
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode())
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        # Windows scanners and indexers can briefly retain a just-closed file
        # handle.  Do not leave a false stale lock behind for the next append,
        # but keep persistent cleanup failures visible to the caller.
        last_permission_error: PermissionError | None = None
        for attempt in range(8):
            try:
                lock_path.unlink(missing_ok=True)
                break
            except PermissionError as exc:
                last_permission_error = exc
                time.sleep(0.025 * (attempt + 1))
        else:
            assert last_permission_error is not None
            raise last_permission_error


def _append_fsynced(path: Path, data: bytes) -> None:
    """Append through one verified descriptor without following a swapped final link."""
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOINHERIT", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        descriptor_stat = os.fstat(descriptor)
        path_stat = os.stat(path, follow_symlinks=False)
        if _is_link_like(path) or (
            descriptor_stat.st_dev,
            descriptor_stat.st_ino,
        ) != (path_stat.st_dev, path_stat.st_ino):
            raise ValueError("immutable result path changed during append")
        remaining = memoryview(data)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("immutable result append made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
        final_stat = os.stat(path, follow_symlinks=False)
        if _is_link_like(path) or (
            descriptor_stat.st_dev,
            descriptor_stat.st_ino,
        ) != (final_stat.st_dev, final_stat.st_ino):
            raise ValueError("immutable result path changed during append")
    finally:
        os.close(descriptor)


def append_immutable(run_id: str, record: dict) -> Path:
    manifest = load_manifest()
    if manifest.get("frozen"):
        raise ValueError("benchmark manifest is frozen; refusing to append a new raw row")
    path = result_path(run_id)
    record = dict(record)
    supplied_run_id = record.get("run_id")
    if supplied_run_id is not None and supplied_run_id != run_id:
        raise ValueError("record run_id does not match the immutable result filename")
    record["run_id"] = run_id
    expected_manifest = manifest_sha256(manifest)
    expected_evaluator = evaluator_sha256()
    expected_packages = task_package_sha256(manifest)
    expected_controller = controller_sha256()
    expected_benchmark = _json_sha256(
        {
            "manifest_sha256": expected_manifest,
            "task_package_sha256": expected_packages,
            "controller_sha256": expected_controller,
        }
    )
    record.setdefault("manifest_sha256", expected_manifest)
    record.setdefault("evaluator_sha256", expected_evaluator)
    record.setdefault("task_package_sha256", expected_packages)
    record.setdefault("controller_sha256", expected_controller)
    record.setdefault("benchmark_sha256", expected_benchmark)
    if "success" not in record:
        raise ValueError(
            "refusing to write a result without a success field from an actual evaluator"
        )
    arm = record.get("arm")
    presentation = arm in {"cursor", "cursor_pex", "codex", "codex_pex"}
    if presentation and not record.get("live") and not record.get("not_a_presentation_arm"):
        raise ValueError(
            "presentation Cursor/Codex arms require live=True from an actual harness run"
        )
    if presentation and record.get("live"):
        required = {
            "attempt",
            "benchmark_sha256",
            "budget",
            "budget_exhausted",
            "combined_metrics",
            "condition",
            "controller_environment",
            "controller_environment_sha256",
            "controller_sha256",
            "cost_usd",
            "cwd",
            "ended_at",
            "evaluator_sha256",
            "evaluation_wall_seconds",
            "execution_wall_seconds",
            "fail_reason",
            "final_workspace_sha256",
            "harness",
            "harness_version",
            "human_active_seconds",
            "human_intervention_log",
            "human_intervention_requests",
            "human_interventions",
            "isolated",
            "isolation_proof",
            "manifest_sha256",
            "measurement_availability",
            "model_settings",
            "model_settings_sha256",
            "model_version_evidence",
            "network_policy",
            "network_policy_sha256",
            "pair_id",
            "pex_metrics",
            "pex_version",
            "prompt_sha256",
            "protocol_sha256",
            "raw_log_sha256",
            "record_schema_version",
            "repo_commit",
            "repo_revision",
            "run_status",
            "schedule_block_index",
            "schedule_index",
            "schedule_sha256",
            "seed_manifest_sha256",
            "snapshot",
            "started_at",
            "task_package_sha256",
            "harness_identity_sha256",
            "thread_id",
            "transport_evidence",
            "transport_kind",
            "wall_time_seconds",
            "worker_config_sha256",
            "worker_metrics",
            "worker_model",
        }
        missing = sorted(required.difference(record))
        if missing:
            raise ValueError(f"live presentation record lacks integrity evidence: {missing}")
        if type(record.get("success")) is not bool:
            raise ValueError("live presentation record requires a binary success result")
        if record.get("not_a_presentation_arm") is True:
            raise ValueError("live presentation record cannot be labeled non-presentation")
        worker_model = str(record.get("worker_model") or "").strip()
        if not worker_model or len(worker_model) > 256:
            raise ValueError("live presentation record requires a pinned worker model")
        expected_protocol = protocol_record_fields(str(record.get("task") or ""), str(arm))
        for field, expected in expected_protocol.items():
            if record.get(field) != expected:
                raise ValueError(
                    f"live presentation record violates predeclared protocol field {field}"
                )
        if record.get("record_schema_version") != 2 or record.get("run_status") != "completed":
            raise ValueError("live presentation record is not a completed schema-v2 row")
        if record.get("attempt") != 1:
            raise ValueError("selective presentation reruns are forbidden")
        if not str(record.get("harness_version") or "").strip() or str(
            record.get("harness_version")
        ).lower() == "unknown":
            raise ValueError("live presentation record requires an exact harness version")
        if not isinstance(record.get("model_settings"), dict):
            raise ValueError("live presentation record requires explicit model settings")
        if record.get("model_settings_sha256") != _json_sha256(record["model_settings"]):
            raise ValueError("live presentation record has an invalid model settings hash")
        if record["model_settings"].get("model") != worker_model:
            raise ValueError("live presentation worker model does not match sent settings")
        harness = str(record.get("harness") or "")
        if harness == "codex":
            sandbox = record["model_settings"].get("sandbox_policy")
            if (
                record["model_settings"].get("approval_policy") != "never"
                or not isinstance(sandbox, dict)
                or sandbox.get("type") != "workspaceWrite"
                or sandbox.get("networkAccess") is not False
                or sandbox.get("writableRoots") != ["<workspace>"]
            ):
                raise ValueError("live Codex settings do not prove the declared isolation policy")
        elif record["model_settings"].get("network_policy") != record.get(
            "network_policy"
        ):
            raise ValueError("live Cursor settings do not bind the declared network policy")
        model_evidence = record.get("model_version_evidence")
        controller_environment = record.get("controller_environment")
        if (
            not isinstance(model_evidence, dict)
            or model_evidence.get("requested_model_id") != worker_model
            or type(model_evidence.get("provider_revision_available")) is not bool
            or (
                model_evidence.get("provider_revision_available") is True
                and not str(model_evidence.get("provider_revision") or "").strip()
            )
            or (
                model_evidence.get("provider_revision_available") is False
                and model_evidence.get("provider_revision") is not None
            )
            or not isinstance(controller_environment, dict)
            or not all(
                isinstance(controller_environment.get(field), str)
                and bool(controller_environment[field].strip())
                for field in ("platform", "python_version")
            )
            or record.get("controller_environment_sha256")
            != _json_sha256(record.get("controller_environment"))
        ):
            raise ValueError("live presentation record lacks exact runtime version evidence")
        parsed_timestamps = []
        for timestamp in (record.get("started_at"), record.get("ended_at")):
            try:
                parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("live presentation record has an invalid run timestamp") from exc
            if parsed.tzinfo is None:
                raise ValueError("live presentation timestamps must include a timezone")
            parsed_timestamps.append(parsed)
        if parsed_timestamps[1] < parsed_timestamps[0]:
            raise ValueError("live presentation run ended before it started")
        numeric_fields = (
            "execution_wall_seconds",
            "evaluation_wall_seconds",
            "wall_time_seconds",
        )
        for field in numeric_fields:
            value = record.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0 <= value <= _MAX_COUNT
            ):
                raise ValueError(f"live presentation record has invalid {field}")
        timestamp_wall = (parsed_timestamps[1] - parsed_timestamps[0]).total_seconds()
        if not math.isclose(
            timestamp_wall,
            float(record["wall_time_seconds"]),
            abs_tol=1.0,
        ):
            raise ValueError("live presentation wall time disagrees with its timestamps")
        if record.get("budget_exhausted") is not False or record.get("fail_reason") is not None:
            raise ValueError("completed presentation row cannot be exhausted or failed")
        cap = float((record.get("budget") or {}).get("task_wall_seconds") or 0)
        if float(record["execution_wall_seconds"]) > cap:
            raise ValueError("completed presentation row exceeded its worker-plus-PEX budget")
        if record.get("repo_revision") != record.get("seed_manifest_sha256"):
            raise ValueError("presentation repo revision is not bound to the canonical seed")
        availability = record.get("measurement_availability")
        worker_metrics = record.get("worker_metrics")
        pex_metrics = record.get("pex_metrics")
        combined_metrics = record.get("combined_metrics")
        if not all(
            isinstance(value, dict)
            for value in (availability, worker_metrics, pex_metrics, combined_metrics)
        ):
            raise ValueError("live presentation record lacks structured resource metrics")
        for metrics, fields in (
            (
                worker_metrics,
                ("wall_seconds", "input_tokens", "output_tokens", "tool_calls"),
            ),
            (
                pex_metrics,
                (
                    "enabled",
                    "wall_seconds",
                    "input_tokens",
                    "output_tokens",
                    "interventions",
                    "tokens_available",
                ),
            ),
            (
                combined_metrics,
                ("wall_seconds", "input_tokens", "output_tokens", "tokens_available"),
            ),
        ):
            if any(field not in metrics for field in fields):
                raise ValueError("live presentation record has incomplete resource metrics")
        metric_errors = resource_metric_errors(record)
        if metric_errors:
            raise ValueError(
                "live presentation record has invalid resource metrics: " + metric_errors[0]
            )
        audit_errors = pex_audit_errors(record)
        if audit_errors:
            raise ValueError(
                "live presentation record has invalid PEX audit accounting: "
                + audit_errors[0]
            )
        raw_log_available = availability.get("raw_log_hash") is True
        if raw_log_available != bool(_SHA256.fullmatch(str(record.get("raw_log_sha256") or ""))):
            raise ValueError("raw log availability does not match its fingerprint")
        if arm.endswith("_pex"):
            if not str(record.get("pex_version") or "").strip():
                raise ValueError("treatment row requires an exact PEX version fingerprint")
            if pex_metrics.get("enabled") is not True:
                raise ValueError("treatment row must include PEX overhead metrics")
        elif record.get("pex_version") is not None or pex_metrics.get("enabled") is not False:
            raise ValueError("baseline row cannot report a PEX runtime")
        interventions = record.get("human_interventions", 0)
        if (
            not isinstance(interventions, int)
            or isinstance(interventions, bool)
            or not 0 <= interventions <= _MAX_COUNT
        ):
            raise ValueError("live presentation record has invalid human intervention count")
        intervention_log = record.get("human_intervention_log")
        requests = record.get("human_intervention_requests")
        if (
            not isinstance(intervention_log, list)
            or len(intervention_log) != interventions
            or not isinstance(requests, int)
            or isinstance(requests, bool)
            or not 0 <= requests <= _MAX_COUNT
        ):
            raise ValueError("human intervention count is not backed by an exact action log")
        for item in intervention_log:
            if (
                not isinstance(item, dict)
                or not str(item.get("action") or "").strip()
                or not str(item.get("timestamp") or "").strip()
            ):
                raise ValueError("human intervention log contains an invalid user action")
            try:
                action_time = datetime.fromisoformat(
                    str(item["timestamp"]).replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise ValueError("human intervention log has an invalid timestamp") from exc
            if (
                action_time.tzinfo is None
                or action_time < parsed_timestamps[0]
                or action_time > parsed_timestamps[1]
            ):
                raise ValueError("human intervention timestamp falls outside the run")
        if record["manifest_sha256"] != expected_manifest:
            raise ValueError("live presentation record uses a different benchmark manifest")
        if record["evaluator_sha256"] != expected_evaluator:
            raise ValueError("live presentation record uses a different hidden evaluator")
        if record["task_package_sha256"] != expected_packages:
            raise ValueError("live presentation record uses different task packages")
        if record["controller_sha256"] != expected_controller:
            raise ValueError("live presentation record uses different controller code")
        if record["benchmark_sha256"] != expected_benchmark:
            raise ValueError("live presentation record uses a different benchmark fingerprint")
        declared_tasks = {
            str(item.get("id") or "")
            for item in manifest.get("tasks") or []
            if isinstance(item, dict)
        }
        if record.get("task") not in declared_tasks:
            raise ValueError("live presentation record names an undeclared task")
        task = str(record["task"])
        expected_prompt = _bounded_file_sha256(
            ROOT / "tasks" / task / "prompt.md",
            _MAX_MANIFEST_BYTES,
            f"benchmark task {task}/prompt.md",
        )
        if record.get("prompt_sha256") != expected_prompt:
            raise ValueError("live presentation prompt does not match the canonical public task")
        if record.get("pair_id") != f"{run_id}:{task}":
            raise ValueError("live presentation pair id is not bound to this run and task")
        thread_id = str(record.get("thread_id") or "").strip()
        if not thread_id or len(thread_id) > 256:
            raise ValueError("live presentation record lacks a bounded worker session id")
        if record.get("isolated") is not True:
            raise ValueError("live presentation record must use an isolated workspace")
        proof = record.get("isolation_proof") or {}
        expected_workspace_name = (
            "ws_"
            + hashlib.sha256(f"{run_id}:{arm}:{task}".encode()).hexdigest()[:16]
        )
        cwd = Path(str(record.get("cwd") or ""))
        if (
            proof.get("mode") != "fresh_seeded_workspace"
            or proof.get("prepared_before_worker") is not True
            or proof.get("workspace_name") != expected_workspace_name
            or not str(proof.get("receipt_path") or "").strip()
            or not _SHA256.fullmatch(str(proof.get("receipt_sha256") or ""))
            or not cwd.is_absolute()
            or cwd.name != expected_workspace_name
        ):
            raise ValueError("live presentation record lacks fresh-workspace proof")
        for field in (
            "final_workspace_sha256",
            "prompt_sha256",
            "seed_manifest_sha256",
            "worker_config_sha256",
            "harness_identity_sha256",
        ):
            if not _SHA256.fullmatch(str(record.get(field) or "")):
                raise ValueError(f"live presentation record has invalid {field}")
        evidence = record.get("transport_evidence") or {}
        if arm in {"codex", "codex_pex"}:
            command = evidence.get("command")
            server_info = evidence.get("server_info")
            if (
                record.get("transport_kind") != "codex_stdio"
                or not isinstance(evidence.get("pid"), int)
                or isinstance(evidence.get("pid"), bool)
                or int(evidence["pid"]) <= 0
                or not isinstance(command, list)
                or not 1 <= len(command) <= 64
                or any(
                    not isinstance(argument, str)
                    or not argument
                    or len(argument) > 4_096
                    or any(ord(character) < 32 for character in argument)
                    for argument in command
                )
                or not isinstance(server_info, dict)
                or record.get("harness_identity_sha256")
                != _json_sha256({"command": command, "server_info": server_info})
            ):
                raise ValueError("Codex live=True lacks exact stdio harness identity evidence")
        if arm in {"cursor", "cursor_pex"}:
            hooks_path = Path(str(evidence.get("hooks_path") or ""))
            hooks_sha256 = str(evidence.get("hooks_sha256") or "")
            cursor_version = str(evidence.get("cursor_version") or "")
            if (
                record.get("transport_kind") != "cursor_hooks"
                or not hooks_path.is_absolute()
                or not _SHA256.fullmatch(hooks_sha256)
                or cursor_version != record.get("harness_version")
                or evidence.get("process") != "Cursor.exe"
                or not evidence.get("conversation_id")
                or evidence.get("conversation_id") != thread_id
                or record.get("harness_identity_sha256")
                != _json_sha256(
                    {
                        "cursor_version": cursor_version,
                        "hooks_sha256": hooks_sha256,
                    }
                )
            ):
                raise ValueError("Cursor live=True lacks exact this-desktop hook identity evidence")
        if arm.endswith("_pex"):
            pex = record.get("pex") or {}
            if (
                not pex.get("supervisor_process_isolated")
                or not pex.get("used_llm")
                or not pex.get("audits")
            ):
                raise ValueError("PEX live=True requires an out-of-process supervisor audit")
            if not _SHA256.fullmatch(str(record.get("pex_config_sha256") or "")):
                raise ValueError("PEX live=True requires a PEX configuration fingerprint")
        elif record.get("pex") is not None:
            raise ValueError("baseline presentation rows cannot contain PEX state")
        if arm == "cursor_pex":
            continuation = evidence.get("same_session_continuation") or {}
            followups = (record.get("pex") or {}).get("followups")
            if (
                continuation.get("confirmed") is not True
                or continuation.get("conversation_id") != record.get("thread_id")
                or not continuation.get("initial_stop_id")
                or not continuation.get("followup_stop_id")
                or continuation.get("initial_stop_id") == continuation.get("followup_stop_id")
                or not isinstance(followups, int)
                or followups < 1
            ):
                raise ValueError(
                    "Cursor+PEX live=True requires a proven same-session continuation"
                )
    with _exclusive_result_lock(MANIFEST), _exclusive_result_lock(path):
        locked_manifest = load_manifest()
        if locked_manifest.get("frozen"):
            raise ValueError("benchmark manifest froze before result commit")
        if manifest_sha256(locked_manifest) != expected_manifest:
            raise ValueError("benchmark manifest changed before result commit")
        existing_records: list[dict] = []
        if path.exists():
            chain_errors = verify_result_chain(path)
            if chain_errors:
                raise ValueError(
                    "refusing to append to invalid immutable result: " + chain_errors[0]
                )
            existing_records = read_result_records(path)
            for existing in existing_records:
                if existing.get("arm") == arm and existing.get("task") == record.get("task"):
                    raise ValueError(
                        f"immutable result already exists for {arm}/{record.get('task')} "
                        f"in {run_id}"
                    )
        if presentation and record.get("live"):
            if any(
                existing.get("record_type") == "abort"
                or existing.get("arm") not in PRESENTATION_ARMS
                or existing.get("live") is not True
                or existing.get("not_a_presentation_arm") is True
                or existing.get("run_status") != "completed"
                or existing.get("run_id") != run_id
                for existing in existing_records
            ):
                raise ValueError("refusing to mix a live presentation run with other records")
            expected_fingerprints = {
                "manifest_sha256": expected_manifest,
                "evaluator_sha256": expected_evaluator,
                "task_package_sha256": expected_packages,
                "controller_sha256": expected_controller,
                "benchmark_sha256": expected_benchmark,
            }
            if any(
                existing.get(field) != expected
                for existing in existing_records
                for field, expected in expected_fingerprints.items()
            ):
                raise ValueError(
                    "benchmark code or manifest changed; continue under a new run id"
                )
            completed = [
                existing
                for existing in existing_records
                if existing.get("run_status") == "completed"
            ]
            plan = experiment_plan(manifest)
            actual_prefix = [
                (
                    existing.get("arm"),
                    existing.get("task"),
                    existing.get("schedule_index"),
                )
                for existing in completed
            ]
            expected_prefix = [
                (entry["arm"], entry["task"], entry["schedule_index"])
                for entry in plan[: len(completed)]
            ]
            if actual_prefix != expected_prefix:
                raise ValueError("existing live rows violate the predeclared schedule prefix")
            if len(completed) >= len(plan):
                raise ValueError("this run id already contains the complete experiment")
            expected = plan[len(completed)]
            if expected["task"] != record.get("task") or expected["arm"] != arm:
                raise ValueError(
                    "live result append violates the predeclared schedule: "
                    f"expected {expected['arm']}/{expected['task']}"
                )
        record["previous_record_sha256"] = (
            existing_records[-1]["record_sha256"] if existing_records else None
        )
        record["record_sha256"] = record_sha256(record)
        line = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
            allow_nan=False,
        )
        if len(line.encode("utf-8")) > _MAX_RESULT_RECORD_BYTES:
            raise ValueError("immutable result row exceeds the record size bound")
        if (path.stat().st_size if path.exists() else 0) + len(line.encode("utf-8")) + 1 > (
            _MAX_RESULT_BYTES
        ):
            raise ValueError("immutable result file would exceed its size bound")
        _append_fsynced(path, (line + "\n").encode("utf-8"))
    return path


def append_abort(
    run_id: str,
    *,
    task: str,
    arm: str,
    abort_reason: str,
    started_at: str,
    ended_at: str,
    detail: str | None = None,
) -> Path:
    """Append an immutable terminal abort; the same run id can never resume."""
    if detail is not None and (not isinstance(detail, str) or len(detail) > 500):
        raise ValueError("abort detail exceeds the immutable record bound")
    parsed_abort_times = []
    for timestamp in (started_at, ended_at):
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("abort timestamps are invalid") from exc
        if parsed.tzinfo is None:
            raise ValueError("abort timestamps must include a timezone")
        parsed_abort_times.append(parsed)
    if parsed_abort_times[1] < parsed_abort_times[0]:
        raise ValueError("abort ended before it started")
    manifest = load_manifest()
    if manifest.get("frozen"):
        raise ValueError("benchmark manifest is frozen; refusing to append an abort")
    allowed_reasons = set(
        (protocol_config(manifest).get("abort_policy") or {}).get("abort_entire_run_on") or []
    )
    if abort_reason not in allowed_reasons:
        raise ValueError(f"abort reason is not predeclared: {abort_reason}")
    expected = assert_next_scheduled(run_id, task, arm)
    fields = protocol_record_fields(task, arm)
    fields["run_status"] = "aborted"
    record: dict[str, object] = {
        **fields,
        "record_type": "abort",
        "run_id": run_id,
        "task": task,
        "arm": arm,
        "abort_reason": abort_reason,
        "abort_detail": detail or None,
        "started_at": started_at,
        "ended_at": ended_at,
        "expected_schedule_index": expected["schedule_index"],
        "manifest_sha256": manifest_sha256(manifest),
        "evaluator_sha256": evaluator_sha256(),
        "task_package_sha256": task_package_sha256(manifest),
        "controller_sha256": controller_sha256(),
        "benchmark_sha256": benchmark_sha256(manifest),
    }
    path = result_path(run_id)
    with _exclusive_result_lock(MANIFEST), _exclusive_result_lock(path):
        locked_manifest = load_manifest()
        if locked_manifest.get("frozen"):
            raise ValueError("benchmark manifest froze before abort commit")
        if manifest_sha256(locked_manifest) != record["manifest_sha256"]:
            raise ValueError("benchmark manifest changed before abort commit")
        existing = read_result_records(path) if path.is_file() else []
        chain_errors = verify_result_chain(path) if path.is_file() else []
        if chain_errors:
            raise ValueError("refusing to append to invalid immutable result: " + chain_errors[0])
        if any(row.get("record_type") == "abort" for row in existing):
            raise ValueError("this run id already has a terminal abort")
        if any(
            row.get("arm") not in PRESENTATION_ARMS
            or row.get("live") is not True
            or row.get("not_a_presentation_arm") is True
            or row.get("run_status") != "completed"
            or row.get("run_id") != run_id
            for row in existing
        ):
            raise ValueError("refusing to mix an abort with non-presentation records")
        expected_fingerprints = {
            "manifest_sha256": record["manifest_sha256"],
            "evaluator_sha256": record["evaluator_sha256"],
            "task_package_sha256": record["task_package_sha256"],
            "controller_sha256": record["controller_sha256"],
            "benchmark_sha256": record["benchmark_sha256"],
        }
        if any(
            row.get(field) != expected_value
            for row in existing
            for field, expected_value in expected_fingerprints.items()
        ):
            raise ValueError("benchmark changed; abort this attempt under a new run id")
        completed = [
            row
            for row in existing
            if row.get("arm") in PRESENTATION_ARMS and row.get("run_status") == "completed"
        ]
        plan = experiment_plan(manifest)
        if len(completed) >= len(plan):
            raise ValueError("this run id already contains the complete experiment")
        locked_expected = plan[len(completed)]
        if locked_expected["task"] != task or locked_expected["arm"] != arm:
            raise ValueError("abort does not match the next predeclared schedule entry")
        if any(row.get("arm") == arm and row.get("task") == task for row in existing):
            raise ValueError(f"immutable result already exists for {arm}/{task} in {run_id}")
        record["previous_record_sha256"] = (
            existing[-1]["record_sha256"] if existing else None
        )
        record["record_sha256"] = record_sha256(record)
        line = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
            allow_nan=False,
        )
        if len(line.encode("utf-8")) > _MAX_RESULT_RECORD_BYTES:
            raise ValueError("immutable abort row exceeds the record size bound")
        if (path.stat().st_size if path.exists() else 0) + len(line.encode("utf-8")) + 1 > (
            _MAX_RESULT_BYTES
        ):
            raise ValueError("immutable result file would exceed its size bound")
        _append_fsynced(path, (line + "\n").encode("utf-8"))
    return path


def describe() -> dict:
    manifest = load_manifest()
    return {
        "manifest": manifest,
        "results_exist": (
            sorted(p.name for p in RESULTS.glob("*.jsonl")) if RESULTS.exists() else []
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "note": (
            "No lift numbers until a four-arm run appends jsonl via append_immutable. "
            "synthetic_pex smoke is not a Cursor/Codex arm."
        ),
    }


def write_synthetic_smoke(
    path: Path,
    *,
    success: bool,
    human_interventions: int,
    task: str = "pexbench_001_premature_stop",
    extra: dict | None = None,
) -> Path:
    """Infrastructure smoke only. Forbidden as a stand-in for Cursor/Codex arms."""
    if type(success) is not bool:
        raise ValueError("synthetic smoke success must be a binary evaluator result")
    declared_tasks = {
        str(item.get("id") or "")
        for item in load_manifest().get("tasks") or []
        if isinstance(item, dict)
    }
    if task not in declared_tasks:
        raise ValueError("synthetic smoke task is not declared by the benchmark")
    if (
        not isinstance(human_interventions, int)
        or isinstance(human_interventions, bool)
        or not 0 <= human_interventions <= _MAX_COUNT
    ):
        raise ValueError("synthetic intervention count is invalid")
    reserved = {
        "arm",
        "live",
        "not_a_presentation_arm",
        "success",
        "task",
    }
    if extra and reserved.intersection(extra):
        raise ValueError("synthetic extras cannot override provenance labels")
    record = {
        **(extra or {}),
        "arm": "synthetic_pex",
        "task": task,
        "success": success,
        "human_interventions": int(human_interventions),
        "not_a_presentation_arm": True,
        "ts": datetime.now(UTC).isoformat(),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, default=str, allow_nan=False)
    encoded_size = len((line + "\n").encode("utf-8"))
    if encoded_size > _MAX_RESULT_RECORD_BYTES:
        raise ValueError("synthetic smoke row exceeds the record size bound")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (
        _is_link_like(path) or path.stat().st_size + encoded_size > _MAX_RESULT_BYTES
    ):
        raise ValueError("synthetic smoke path is linked or exceeds the size bound")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return path


if __name__ == "__main__":
    print(json.dumps(describe(), indent=2))
