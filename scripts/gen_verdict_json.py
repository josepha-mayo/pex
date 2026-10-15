"""Generate docs/demo/verdict.json from the committed fixture-suite receipt.

The Pages site serves verdict.json as the machine-readable summary a scraper
(or judge) can check without running anything. It is derived, never
hand-written: every number comes from the latest FIXTURE_SUITE_EVAL receipt
and, when present, the --repeat determinism receipt.

    uv run python scripts/gen_verdict_json.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITE = ROOT / "docs/demo/evidence/FIXTURE_SUITE_EVAL_2026-10-15.json"
DETERMINISM = ROOT / "docs/demo/evidence/FIXTURE_SUITE_EVAL_DETERMINISM_2026-10-15.json"
EVIDENCE = ROOT / "docs/evidence"
OUT = ROOT / "docs/demo/verdict.json"

# Receipt files named <slug>-YYYY-MM-DD.json with schema_version + a live
# provider call are surfaced so the scraped page reports live verification
# machine-readably — names and dates derive from the files, not copy.
_LIVE_RECEIPTS = (
    "token-factory-inference",
    "opencode-stop-nemotron",
    "opencode-tamper-escalation",
    "tavily-evidence-path",
    "codex-nebius-live",
)


def main() -> int:
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    fixtures = suite["fixtures"]

    statuses: dict[str, int] = {}
    claims = interventions = incidents = 0
    for row in fixtures:
        statuses[row["completion_status"]] = statuses.get(row["completion_status"], 0) + 1
        claims += int(row.get("claims_adjudicated") or 0)
        interventions += len(row.get("interventions") or [])
        incidents += int(row.get("integrity_incidents") or 0)

    met = sum(1 for row in fixtures if not row.get("failures"))

    out: dict = {
        "schema": "pex.pages-verdict-summary/v1",
        "generated_from": f"docs/demo/evidence/{SUITE.name}",
        "scope": "curated_replay_fixture_suite_not_a_benchmark",
        "suite": {
            "fixtures_total": len(fixtures),
            "declared_arcs_met": met,
            "labels": ["replay", "not_live_control"],
            "replay": True,
            "not_live_control": True,
            "claims_adjudicated": claims,
            "interventions": interventions,
            "integrity_incidents": incidents,
            "completion_statuses": dict(sorted(statuses.items())),
            "note": (
                "Deterministic replay adjudication of recorded trajectories "
                "through the real pipeline — not a benchmark and not live "
                "worker control."
            ),
        },
        "fixtures": [
            {
                "id": row["fixture"],
                "completion_status": row["completion_status"],
                "claims_adjudicated": row.get("claims_adjudicated") or 0,
                "interventions": row.get("interventions") or [],
                "integrity_incidents": row.get("integrity_incidents") or 0,
            }
            for row in fixtures
        ],
    }

    if DETERMINISM.exists():
        det = json.loads(DETERMINISM.read_text(encoding="utf-8"))
        det_fixtures = det.get("fixtures", [])
        repeat = max((int(row.get("runs") or 1) for row in det_fixtures), default=1)
        identical = sum(
            1
            for row in det_fixtures
            if not any(str(f).startswith("nondeterministic") for f in (row.get("failures") or []))
        )
        out["suite"]["determinism"] = {
            "repeat": repeat,
            "identical_arcs": identical,
            "receipt": f"demo/evidence/{DETERMINISM.stem}.html",
            "note": (
                "Every fixture adjudicated identically across repeats — "
                "completion, claims, incidents, verdicts, and normalized "
                "evidence strings compared."
            ),
        }

    live = []
    for receipt in sorted(EVIDENCE.glob("*.json")):
        try:
            body = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        slug = receipt.stem.rsplit("-", 3)[0]
        if slug not in _LIVE_RECEIPTS:
            continue
        live.append(
            {
                "receipt": f"evidence/{receipt.name}",
                "date": body.get("observed_date"),
                "provider": body.get("provider"),
                "model": body.get("supervisor_model")
                or (body.get("supervisor") or {}).get("model"),
                "worker": body.get("worker_harness") or (body.get("worker") or {}).get("harness"),
            }
        )
    if live:
        out["live_verified"] = live

    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {OUT.relative_to(ROOT)}: {met}/{len(fixtures)} arcs met, "
        f"{claims} claims, {incidents} incidents, {len(live)} live receipts"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
