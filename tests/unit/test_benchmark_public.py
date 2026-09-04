from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.app import create_app, state
from pex_bridge.benchmark_public import load_public_summary
from pex_bridge.config import Settings


def _summary() -> dict:
    manifest = "a" * 64
    benchmark = "c" * 64
    runs = []
    for arm in ("cursor", "cursor_pex", "codex", "codex_pex"):
        runs.append(
            {
                "id": f"run:{arm}",
                "name": arm,
                "status": "frozen",
                "arm": arm,
                "harness": arm.removesuffix("_pex"),
                "created_at": "2026-08-27T00:00:00Z",
                "manifest_hash": manifest,
                "benchmark_hash": benchmark,
                "frozen": True,
                "metrics": {
                    "task_success_rate": 0.5,
                    "human_interventions_per_success": 1.0,
                    "useful_interventions": 1,
                    "harmful_interventions": 0,
                    "context_handoffs": 0,
                    "pex_input_tokens": 123,
                    "pex_output_tokens": 45,
                    "tasks": 2,
                },
            }
        )
    return {
        "schema_version": 1,
        "run_id": "run",
        "manifest_sha256": manifest,
        "benchmark_sha256": benchmark,
        "result_sha256": "b" * 64,
        "generated_at": "2026-08-27T00:00:00Z",
        "runs": runs,
        "note": "aggregate only",
    }


def test_missing_summary_is_honestly_unfrozen(tmp_path):
    result = load_public_summary(tmp_path / "missing.json")
    assert result["runs"] == []
    assert result["status"] == "unfrozen"


def test_public_summary_exposes_only_aggregate_allowlist(tmp_path):
    path = tmp_path / "summary.json"
    raw = _summary()
    raw["private_worker_logs"] = ["secret transcript"]
    path.write_text(json.dumps(raw), encoding="utf-8")

    result = load_public_summary(path)

    assert result["status"] == "frozen"
    assert len(result["runs"]) == 4
    assert result["benchmark_sha256"] == "c" * 64
    assert result["runs"][0]["metrics"]["pex_input_tokens"] == 123
    assert "private_worker_logs" not in result
    assert "secret transcript" not in json.dumps(result)


def test_public_summary_fails_closed_on_non_public_metrics(tmp_path):
    path = tmp_path / "summary.json"
    raw = _summary()
    raw["runs"][0]["metrics"]["worker_transcript"] = "private"
    path.write_text(json.dumps(raw), encoding="utf-8")

    result = load_public_summary(path)

    assert result["status"] == "invalid"
    assert result["runs"] == []


def test_public_summary_rejects_unfrozen_or_duplicate_arms(tmp_path):
    path = tmp_path / "summary.json"
    raw = _summary()
    raw["runs"][0]["frozen"] = False
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_public_summary(path)["status"] == "invalid"


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version": 1, "schema_version": 1}',
        '{"schema_version": 1, "score": NaN}',
    ],
)
def test_public_summary_rejects_non_strict_json(tmp_path, payload):
    path = tmp_path / "summary.json"
    path.write_text(payload, encoding="utf-8")

    assert load_public_summary(path)["status"] == "invalid"


@pytest.mark.parametrize("timestamp", ["yesterday", "2026-08-27T00:00:00"])
def test_public_summary_requires_timezone_aware_timestamps(tmp_path, timestamp):
    path = tmp_path / "summary.json"
    raw = _summary()
    raw["generated_at"] = timestamp
    path.write_text(json.dumps(raw), encoding="utf-8")

    assert load_public_summary(path)["status"] == "invalid"


def test_public_summary_rejects_benchmark_fingerprint_mismatch(tmp_path):
    path = tmp_path / "summary.json"
    raw = _summary()
    raw["runs"][0]["benchmark_hash"] = "d" * 64
    path.write_text(json.dumps(raw), encoding="utf-8")

    assert load_public_summary(path)["status"] == "invalid"


@pytest.mark.parametrize("invalid", [-0.1, 1.1, float("nan"), float("inf")])
def test_public_summary_rejects_impossible_or_nonfinite_success_rates(tmp_path, invalid):
    path = tmp_path / "summary.json"
    raw = _summary()
    raw["runs"][0]["metrics"]["task_success_rate"] = invalid
    path.write_text(json.dumps(raw), encoding="utf-8")

    result = load_public_summary(path)
    assert result["status"] == "invalid"
    assert str(invalid) not in result["message"]


def test_public_summary_does_not_publish_untrusted_note_or_validation_detail(tmp_path):
    path = tmp_path / "summary.json"
    raw = _summary()
    raw["note"] = "private transcript sentinel"
    path.write_text(json.dumps(raw), encoding="utf-8")
    loaded = load_public_summary(path)
    assert loaded["status"] == "frozen"
    assert "sentinel" not in loaded["message"]

    raw["runs"][0]["metrics"]["private transcript sentinel"] = 1
    path.write_text(json.dumps(raw), encoding="utf-8")
    rejected = load_public_summary(path)
    assert rejected["status"] == "invalid"
    assert "sentinel" not in rejected["message"]


@pytest.mark.asyncio
async def test_authenticated_bridge_surface_exposes_only_public_summary(tmp_path, monkeypatch):
    path = tmp_path / "summary.json"
    raw = _summary()
    raw["private_worker_logs"] = ["secret transcript"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setenv("PEX_BENCH_SUMMARY", str(path))
    monkeypatch.setattr(
        state,
        "settings",
        Settings.for_test(require_auth=False, home=tmp_path),
    )

    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://127.0.0.1",
    ) as client:
        response = await client.get("/v1/bench/runs")

    assert response.status_code == 200
    assert response.json()["status"] == "frozen"
    assert "secret transcript" not in response.text

    raw = _summary()
    raw["runs"][0]["arm"] = "codex"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_public_summary(path)["status"] == "invalid"
