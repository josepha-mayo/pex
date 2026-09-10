# Current-source Codex proof and package verification — 10 September 2026

Source: `2174ad0c80ee9232ebff7c6399e1f30d90b9dcc6`. These are bounded
live behavioral checks, not a comparative benchmark or submission GO.

## Verified

- Full offline suite: `4295 passed, 16 skipped, 16 deselected in 1312.84s`.
  Command: `.venv/Scripts/python.exe -m pytest -q -m "not live_llm and not live_codex and not live_opencode and not live_agentcore" --junitxml=build/offline-2174ad0.xml`.
  The Rust 1.97.1 toolchain directory was explicitly on PATH. Exit 0.
- `npm run tauri -- build`, followed by `npm run verify:package -- --receipt
  C:\Users\JosephMayo\Projects\pex\build\pex-package-receipt-2174ad0.json`:
  exit 0; MSI and NSIS embedded content and eight-pet inventories verified.
  Package readiness is not end-to-end product readiness.
- No-turn owned Codex preflight: account type `chatgpt`, requested
  `gpt-5.3-codex-spark` available. No model substitution.
- Real Codex incomplete-stop check: `1 passed in 113.67s`, exit 0.
  `tests/contract/test_live_codex_pump.py::test_live_codex_incomplete_stop_sends_specific_continue`.
  Same owned App Server process/thread, specific intervention, resulting
  `report.txt` exactly `shipped`, final semantic NOOP, correlated delivery/stop
  audit, and initial outcome `goal_evidence_supported`, `helped: true`.
- Real Codex correct-completion check: `1 passed in 52.29s`, exit 0.
  `tests/contract/test_live_codex_pump.py::test_live_codex_stop_inspects_with_strands`.
  Receipt status `validated`, kind `evidence_supported_noop`.

Both Codex checks used the saved OS-vault Zen route, Muse Spark 1.3 Contributor
Free with local Strands, and the explicitly authorized Spark worker quota.
Each process had a three-supervisor-dispatch cap, workspace-write sandbox,
network-disabled worker policy, and no AgentCore/paid-provider fallback.
Only each test's own App Server handle was closed. The user's Codex app was
not automated, closed or restarted. Credentials were not written to receipts.

## Local receipts and SHA-256

| Receipt | SHA-256 |
| --- | --- |
| `build/offline-2174ad0.xml` | `4ac22161d025fa1d17275912586a4e7a892690a299cbd291199a775a43f35c18` |
| `build/pex-package-receipt-2174ad0.json` | `eeb6d52add032545b7495e79688bac75208370af6703437320da80d22fb4866f` |
| `build/codex-live-2174ad0/codex-incomplete-proof.json` | `31da9d3dc314f3ee622f3accf3a9e5b6e53ec0ec6724f0def69d5092c37aaf08` |
| `build/codex-live-2174ad0-quiet/codex_inspect_proof.json` | `2e9d408510a2a3630f494e19be91a1ea5928414791178e68a1bbeb8271fcce0d` |

Older scratch proofs were copied into the run directories before these tests;
they were not silently discarded. Raw receipts remain local and require privacy
review before publication.

## Packaged OpenCode follow-up: not a quiet-case pass

Root: `build/native-opencode-2174ad0-quiet-20260910`.
Session: `opencode:ses_f765ccb40ffefPiSsCeUZnDDqd`.
Goal: `goal_cda85d482d634fdc97dc7224cb3ac617`.

Native PEX loaded the saved supervisor configuration, connected via its
OpenCode form, and saved/attached the exact two-file/newline goal through its
goal editor. The fresh session correctly displayed Discovered before the turn.

The free Ling worker claimed success but explicitly used the parent PEX
repository as its tool working directory, leaving the attached workspace
empty. PEX independently verified the gap and sent a same-session correction.
The worker again used the wrong directory. This is neither correct completion
nor verified successful recovery. No manual correction was sent.

The run exposed two remaining defects:

1. Hundreds of `message.part.delta` frames became full STATUS planning cycles,
   delaying STOP by minutes. At 311 accepted events, 222 were token deltas.
2. Sending a correction cleared the terminal marker before the already-buffered
   old `session.idle` was consumed. This caused a second semantic review, whose
   action was suppressed by cooldown, wasting a review allowance.

At the checkpoint, the sent intervention had `worker_responded`, not
`goal_evidence_supported`; `helped` remained null. The preset fixture budget
expired, and its own server and all four temporary profile directories were
cleaned. The native bridge was still draining buffered events. The two exact
misplaced test files were moved from the repository root to this run's
`misplaced-artifacts` directory, preserving the evidence.

## Follow-up source repair

Plain OpenCode token-delta STATUS events now use the existing immutable
record-only journal path, retaining their IDs, redacted payloads and processing
receipts without per-token capability probes or planner effects. Full message,
tool, error, session-status and terminal events retain normal processing. The
first event for an unknown durable session also retains normal processing.

Combined offline event-processing, delta-ingestion, OpenCode pump and lineage
checks: `111 passed in 52.77s`; Ruff and `git diff --check` pass. The 100-delta
regression proves durable `record_only_complete`, no probes/planner effects,
idempotent replay, collision rejection, and a later parent-bound STOP completing
the normal pipeline. This follow-up is not in package `2174ad0`; native latency
improvement is not yet established.

## Still open

Native existing-Codex attachment, corrected packaged OpenCode recovery and quiet
checks, duplicate-idle review, ten-case false-positive measurement, resource and
long-duration stability checks, isolated comparative benchmark execution,
AgentCore deployed-runtime evidence under no-billing authority, and recording.
AgentCore client/runtime tests do not substitute for a deployed invocation.
