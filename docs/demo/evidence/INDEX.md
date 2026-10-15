# Evidence index

This directory catalogues the demo-facing receipts — every file below lists
the command that re-checks it. A PASS proves the artifact is internally
consistent; it does not claim a live worker ran where the artifact itself is
a recording. Deeper engineering receipts live in `docs/evidence/` and are
referenced where their claims are made.

## Evidence packs — `verify_pack.py`

Self-contained bundles: verification report + sealed baseline bytes + flagged
bytes + hash-chained event ledger, all under a manifest digest. Re-verify any
one of them — or the whole directory — with no bridge running:

```powershell
uv run python scripts/verify_pack.py docs/demo/evidence
uv run python scripts/verify_pack.py docs/demo/evidence/EVIDENCE_PACK_captured_live_2026-10-05.json
```

The `.html` siblings are the same packs rendered as forensic pages — open one
in a browser and the checks, diffs, and ledger render inline; the raw pack JSON
rides embedded so the page verifies itself.

| Pack | What it covers |
| --- | --- |
| `EVIDENCE_PACK_captured_live_2026-10-05.{json,html}` | A real OpenCode run captured into `captured_live_eval` — the canonical verify-it-yourself pack. |
| `EVIDENCE_PACK_drift_loop_2026-10-05.{json,html}` | The drift arc: `apply overlay` proposed, honestly refused on a replay session, cooldown suppressions. |
| `EVIDENCE_PACK_live_tamper_2026-10-05.{json,html}` | Live tamper: the flagged-bytes diff (sealed baseline vs weakened test) that produced the integrity incident. |
| `EVIDENCE_PACK_live_dispute_2026-10-06.{json,html}` | Live worker dispute — the worker pushed back on a nudge and PEX re-adjudicated on evidence. |
| `EVIDENCE_PACK_live_escalation_2026-10-14.{json,html}` | The worker-initiated escalation run: `pex.request_decision` → durable human ruling on a terminal session. |
| `LIVE_EVIDENCE_PACK_2026-10-14.json` | Pack for `ses_ec5dda675` — the live closed loop: fake `verify.py` claim contradicted, real repair verified. |

## Fixture-suite receipts — `eval_replays.py`

Every fixture in `fixtures/demo/` replayed through the real bridge and scored
against its declared supervision arc. Reproduce:

```powershell
uv run python scripts/eval_replays.py --json out.json --html out.html   # needs the demo bridge
```

| Receipt | Suite state |
| --- | --- |
| `FIXTURE_SUITE_EVAL_2026-10-15.{json,html}` | **Latest — 19/19 arcs**, including `report_progress_eval` (progress reports are signal, never proof). |
| `FIXTURE_SUITE_EVAL_DETERMINISM_2026-10-15.{json,html}` | **19/19 arcs under `--repeat 2`** — every fixture adjudicated identically twice (completion, claims, incidents, verdicts, evidence strings compared per repeat); the determinism claim receipted, not just asserted. |
| `FIXTURE_SUITE_EVAL_2026-10-14.{json,html}` | 17/17 — first suite with the live-captured `worker_escalation_eval`. |
| `FIXTURE_SUITE_EVAL_2026-10-06.{json,html}` | 15/15 historical snapshot. |
| `FIXTURE_SUITE_EVAL_2026-10-05.{json,html}` | 12/12 historical snapshot. |
| `CHALLENGE_PRESETS_EVAL_2026-10-06.json` | Attack-preset sweep: each shipped challenge preset adjudicated honestly — none reach verified completion on the attack. |

## Live-run receipts — verification reports and captures

`pex.verification-report.v1` exports of real supervised sessions (the same
shape the Inspector's receipt button downloads), plus smaller live-evidence
receipts for specific behaviors. `ses_*` names are the real OpenCode session ids.

| Receipt | What it records |
| --- | --- |
| `LIVE_RECEIPT_2026-10-14.json` | `ses_ec5dda675` — the live worker-MCP loop: worker claimed a fake `verify.py` proved tests, PEX contradicted on independent pytest, worker repaired, final claim supported. `verified_complete`. |
| `LIVE_OPENCODE_TAMPER_ESCALATION_ses_ec4b20a7_2026-10-14.json` | The worker-initiated escalation run — worker asked whether to obey a tampered file; human ruling outlived the session (the arc `worker_escalation_eval` replays). `incomplete` — the session ended awaiting the ruling, honestly. |
| `LIVE_OPENCODE_TAMPER_DISPUTE_ses_ef0f0d88_2026-10-06.json` | Worker disputed a contradiction nudge; PEX re-adjudicated on evidence. Ends `uncertain`. |
| `LIVE_OPENCODE_TAMPER_PUSHBACK_ses_ef18550c_2026-10-05.json` | Worker pushback arc mid-run — honest `in_progress`. |
| `LIVE_OPENCODE_TAMPER_ses_ef720112cffe_2026-10-04.json` | Tamper detection on a live worker — `uncertain`. |
| `LIVE_OPENCODE_TAMPER_PREFIX_2026-10-04.json` | Earlier tamper-prefix run — `uncertain`. |
| `LIVE_OPENCODE_HANDOFF_ef467f58_2026-10-05.json` | `pex.live-handoff-receipt.v1` — a goal handoff delivered a content-addressed context bundle to a sibling session: `delivery_status: delivered`. |
| `LIVE_OPENCODE_FALSE_CLAIM_1ab1152_2026-10-04.json` | `pex.live-evidence.v1` — same-session recovery: false "tests pass" claim → independent pytest contradicts → worker repairs. |
| `LIVE_OPENCODE_DEMO_UI_1ab1152_2026-10-04.json` | `pex.live-evidence.v1` — the full `demo.py --live` path exercised through the desktop UI. |
| `LIVE_OPENCODE_PEX_CLOSED_LOOP_2026-09-09.json` | Closed loop against a real worker with an OS-secret-store credential — 1 intervention, exact final state. |
| `LIVE_OPENCODE_QUIET_2026-09-09.json` | Quiet adjudication receipt — documents a checker defect found and fixed (the harness wrongly required zero interventions). |
| `INSTALLED_BRIDGE_SOAK_F2832A8_2026-09-13.json` | `pex.packaged-settings-smoke.v1` — installed-bridge soak: authenticated supervisor read, identity verified. |

## Engineering receipts

`docs/evidence/` holds the deeper build-log receipts — package-verification
receipts, Codex adapter captures, Linux/Windows installed-bridge smokes, and
the pytest collection receipt — referenced where their claims are made in
`BENCHMARKS.md`, `INTEGRATIONS.md`, and `docs/`.
