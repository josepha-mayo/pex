"""PexBench runner.

Never invents scores. A run file is written only after arms execute.
Presentation code must read jsonl; it must not hand-edit it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "manifest.yaml"
RESULTS = ROOT / "results"


def load_manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def result_path(run_id: str) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    return RESULTS / f"{run_id}.jsonl"


def append_immutable(run_id: str, record: dict) -> Path:
    path = result_path(run_id)
    if "success" not in record:
        raise ValueError(
            "refusing to write a result without a success field from an actual evaluator"
        )
    arm = record.get("arm")
    presentation = arm in {"cursor", "cursor_pex", "codex", "codex_pex"}
    if presentation and not record.get("live") and not record.get(
        "not_a_presentation_arm"
    ):
        raise ValueError(
            "presentation Cursor/Codex arms require live=True from an actual harness run"
        )
    if presentation and record.get("live"):
        required = {
            "pair_id",
            "prompt_sha256",
            "seed_manifest_sha256",
            "harness_identity_sha256",
            "transport_evidence",
            "transport_kind",
            "worker_config_sha256",
            "worker_model",
        }
        missing = sorted(required.difference(record))
        if missing:
            raise ValueError(f"live presentation record lacks integrity evidence: {missing}")
        evidence = record.get("transport_evidence") or {}
        if arm in {"codex", "codex_pex"} and (
            record.get("transport_kind") != "codex_stdio" or not evidence.get("pid")
        ):
            raise ValueError("Codex live=True requires a running codex stdio process")
        if arm.endswith("_pex") and not (record.get("pex") or {}).get(
            "supervisor_process_isolated"
        ):
            raise ValueError("PEX live=True requires an out-of-process supervisor audit")
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            existing = json.loads(raw)
            if existing.get("arm") == arm and existing.get("task") == record.get("task"):
                raise ValueError(
                    f"immutable result already exists for {arm}/{record.get('task')} in {run_id}"
                )
    line = json.dumps(record, default=str)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
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
    extra: dict | None = None,
) -> Path:
    """Infrastructure smoke only. Forbidden as a stand-in for Cursor/Codex arms."""
    record = {
        "arm": "synthetic_pex",
        "task": "pexbench_001_premature_stop",
        "success": bool(success),
        "human_interventions": int(human_interventions),
        "not_a_presentation_arm": True,
        "ts": datetime.now(UTC).isoformat(),
    }
    if extra:
        record.update(extra)
    RESULTS.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, default=str)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return path


if __name__ == "__main__":
    print(json.dumps(describe(), indent=2))
