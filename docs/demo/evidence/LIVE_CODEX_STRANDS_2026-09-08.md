# Live Codex + Strands release-candidate evidence — 8 September 2026

This is a sanitized, judge-readable summary of two validated contract receipts captured on
clean source `af3570726923b9d233723de950c9d33e4606e033`. The raw receipts stay in ignored
local scratch because they contain machine-local paths and run identities.

## Why this recapture mattered

The first quiet attempt on clean packaged source `d66e6a1` failed after 234.62 seconds. Codex
correctly wrote `ping.txt = pong`, but PEX retained zero events and zero interventions. A
schema-only trace showed that current Codex CLI 0.153.4 still emitted `turn/completed`; the
adapter had left 22 notifications queued because its first event-pump pass waited on a slow
account-wide thread discovery.

Commit `af35707` makes an already identity-bound isolated thread drain its buffered events
before periodic discovery. Unknown sessions still require discovery. The regression holds
discovery open indefinitely and proves the bound thread's STOP is ingested first. The focused
Codex pump/attach gate passes 57/57 and Ruff is clean.

## Case A — verified completion stays quiet

- Command target: `test_live_codex_stop_inspects_with_strands`
- Result: **1 passed in 108.79 seconds**
- Worker: isolated Codex App Server, requested model `gpt-5.3-codex-spark`
- Supervisor: Strands Agents 1.53.0, Zen `muse-spark-1.3-contributor-free`
- Evidence: `ping.txt` contained exactly `pong`
- Decision: `NOOP`
- Supervisor receipt: `used_llm=true`, `inference_status=completed`, one model call
- Raw validated receipt SHA-256:
  `11CF4780857B8F7D66448BB61C49C33B162464DA9D081E45817DD845A1A95762`

## Case B — incomplete work is recovered on the same thread

- Command target: `test_live_codex_incomplete_stop_sends_specific_continue`
- Result: **1 passed in 173.82 seconds**
- Worker: one isolated Codex App Server thread, requested model
  `gpt-5.3-codex-spark`
- Supervisor: Strands Agents 1.53.0, Zen `muse-spark-1.3-contributor-free`
- Initial evidence: `report.txt` existed but did not contain `shipped`
- Initial decision: `SEND_NUDGE`, supported by four bounded evidence-tool observations
- Delivery: a verified second turn on the same vendor thread
- Outcome: `report.txt` contained exactly `shipped`; `helped=true` and
  `outcome=goal_evidence_supported`
- Final decision: evidence-supported `NOOP`
- Raw validated receipt SHA-256:
  `6A0D2F314254D06C4C3F49EABF69FAFE89EC5808643F2DCC52649A70DBE81AE8`

## Limits

These contracts prove the source-level closed loop with real Codex and real Strands inference.
They do not prove the unsigned packaged desktop, native window stability, AgentCore deployment,
Cursor delivery, a frozen PexBench score, or a public leaderboard rank. No native PEX window or
AWS resource ran during this capture.
