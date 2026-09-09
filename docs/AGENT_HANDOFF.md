# PEX active handoff

Maintained checkpoint: 10 September 2026; includes aggregate HTTP event-buffer budgeting.
**Submission status: NO-GO. The full goal remains active.**
Verify Git/current files before relying on this checkpoint. No prior build/test
session remains running. This is the active entry point, not another historical log.

## Authority and product scope

Read all three specifications before implementation:

1. [Core specification](PEX_CORE_SPEC.md).
2. [Build specification](PEX_BUILD_SPEC.md).
3. [Implementation recovery specification](PEX_IMPLEMENTATION_RECOVERY_SPEC.md).

Then consult [shipping checklist](SHIP_CHECKLIST.md) and [audit coverage](CODE_AUDIT_COVERAGE.md).
PEX is an independent goal-aware supervisor above existing coding harnesses:
observe evidence, reason with Strands, enforce policy, continue the same worker
when justified, verify the outcome, and stay quiet when no action is needed.
A dashboard, generic continuation prompt, model call or green unit suite is not
the complete product.

Shipping focus: useful stable MVP, Pex/Von as two demo pets, OpenCode/Codex primary
integrations, Cursor where required by the benchmark, good UI/UX, Zen BYOK,
Strands and the implemented AgentCore path. Preserve the eight-pet catalog and
full spec/audit obligations. Do not silently redefine completion around the parts
already built or promise contest success.

The entire former 838 KB, 10,000+ line handoff is retained unchanged in
[historical handoff](AGENT_HANDOFF_HISTORY_2026_09_09.md), in the same directory
so relative links still resolve. Its many "current/latest" labels are historical.
Search that archive for needed details instead of loading it wholesale each turn.
Update this active handoff in place; put detailed receipts in evidence files.

## Safety hold and user constraints

- User reported a whole-PC freeze and later Codex closing during native testing.
  Native app launches, process termination and computer input are ON HOLD pending
  fresh agreement. Earlier blanket live-test approvals do not lift the hold.
  An asynchronous question about user-opened PEX-only checks remains unanswered;
  do not interpret automatic goal continuations as permission or repeatedly ask.
- `C:\Users\JosephMayo\Documents\Codex\pex-native-smoke-933239a.ps1` is quarantined
  with an unconditional throw. Its recursive PID-only cleanup could target
  unrelated processes after PID reuse. Never run it or remove the quarantine.
  This is a plausible mechanism, not proof of the exact incident victim.
- Read-only observer: `scripts/measure_pex_readonly.ps1` plus
  `scripts/pex_process_snapshot.psm1`. Eight synthetic tests passed; real-app
  operation is unverified. It pins executable/PID/creation-time for measurement,
  never termination authority. Summed working sets can double-count shared pages;
  sample duration is not a hard OS-query timeout.
- No paid providers or AWS deployment. A card/account/free-model label is not
  proof of no billing. Recheck provider availability and price before authorized
  live use. Never print credentials or copy the conversation's key into source.
- Preserve unrelated changes. User authorized pushes per verified update. Use
  fewer subagents; when a bounded independent audit warrants one, user requested
  Terra medium. Recent repairs used no subagents.
- When live checks are agreed, input must stay in PEX. Never close/restart the
  user's Codex, OpenCode, Cursor or other apps for cleanup.

## Current source versus package

Last verified Windows package source:
`166a65661234879bb8ccda48fe180300baf7456c`; the subsequent HTTP event-buffer fix is not yet packaged.
Both MSI/NSIS passed extracted executable/hash and exact pet-inventory checks.

- Receipt: `build/pex-package-receipt-166a656.json`.
- [Durable hashes, warnings, commands and limitations](demo/evidence/PACKAGE_166A656_2026-09-10.md).
- Desktop: `apps/desktop/src-tauri/target/release/pex-desktop.exe`.
- MSI: `apps/desktop/src-tauri/target/release/bundle/msi/PEX_0.1.0_x64_en-US.msi`.
- NSIS: `apps/desktop/src-tauri/target/release/bundle/nsis/PEX_0.1.0_x64-setup.exe`.

Verification did not install/open desktop UI; the frozen bridge ran only its
inventory-only `--verify-bundle` path. Receipt `release_ready:true` is a package
gate, not submission readiness.

Post-package change: HTTP SSE retention now enforces an 8 MiB aggregate serialized
payload budget as well as the 1,024-event limit. Eviction preserves absolute
cursor/drop accounting; a single oversized event clears the earlier retained tail
so no internal gap is hidden. Ten HTTP/SSE tests, four OpenCode pump tests and two
lineage-gap tests pass; Ruff passes. This is not an RSS cap or proof of freeze cause.
Collect the change into the next package rebuild before claiming installer coverage.
Follow-up: malformed/non-object SSE payloads and oversized lines/frames now emit a
retention gap rather than silently preserving apparent continuity. Empty keep-alives
and comments remain harmless. Sixteen HTTP/SSE checks plus four OpenCode pump checks
pass; Ruff passes. This follow-up is also not in package 166a656.

Collected fixes now included in package 166a656:

| Commit | Change | Evidence |
| --- | --- | --- |
| `da15cea` | Recheck opened Windows thread owner before resume | 3 fully mocked ownership/cleanup tests; Ruff |
| `157b119` | Bound Retry response to 5 seconds without duplicating unresolved native IPC | 42 recovery/read-budget tests; frontend build |
| `4fc703c` | Count scope in the 18,000-character decision-text budget | Regression formerly admitted 27,000 characters; 15 context/integration tests; Ruff |
| `a988748` | Lock goal fields while saving to prevent loss of concurrent edits | 267 desktop tests; frontend build |
| `d8f09a3` | Require validated decisions for the selected goal revision before editing; reject stale drafts and remove unscoped post-save decision reads | 268 desktop tests; frontend build |
| `dec84d1` | Do not re-extract previously cleared criteria/decisions during unrelated partial edits or unchanged-objective resubmission; new objective text still extracts | 120 API/parser/store tests; Ruff |

Collect verified fixes instead of rebuilding after every tiny change. Keep source
clean and unchanged during build/verification. Never claim current native behavior
from an older installer.

## Repairs already in package 2966259

- White canvas: removed JS `setBackgroundColor` call whose `color` argument
  mismatched installed Rust setter `value`, resetting the canvas to white. Typed
  native transparent setup remains. Source defect found; repaired native rendering
  has NOT been observed.
- Calmer sprite timing, fixed overlay close anchor, user scale respected, no overlay
  hover jump, unselected picker previews paused; Home has worker/workspace structure.
  Native UX/resource improvement is unproven.
- WebSocket compression off; smaller outbound queue with bounded enqueue waits.
  Hidden readers pause, abort on cleanup and invalidate stale responses. Adapter
  stall repairs have offline evidence; no quiet-native CPU/memory claim.
- Pause gates in semantic loop and deterministic planner, including AgentCore/hybrid.
  Paused goals/sessions cannot force inference through overrides.
- Equal-time material events break ambiguous failure streaks; three later ordered
  failures can still trigger review. This does not grant intervention authority.
- BYOK save distinguishes saved configuration from tested key/successful inference.
- Benchmark helpfulness requires observed literal failed -> passed tests; missing
  baseline gets no credit. Historical evidence was not rewritten.

## Verification ledger

| Source/scope | Result | Not proven |
| --- | --- | --- |
| Goal-ledger freshness repair full desktop suite | 268 passed, zero skipped; TypeScript/Vite build exit 0 | Native rendering, interaction, resource use |
| `157b119` combined backend gate | 107 passed in 110.29 seconds | Full Python suite; live worker/provider/AgentCore |
| `4fc703c` context gate | 15 passed | Measured token/cost savings |
| API intent-preservation repair | 120 passed in 48.03 seconds: goal lifecycle, operation routes, public-task parser, authority, operations, transactions and semantic hashing | Live workers or full Python suite |
| `dec84d1` recovery/event regression | 86 passed, 2 background-process cases deselected, 169.73 seconds | Real-worker behavior; the two excluded process cases |
| Ledger-only dispatch regression | 16 passed in 13.16 seconds; Ruff passed | Real harness delivery |
| `166a656` installers | Both extracted inventories verified; zero package blockers | End-to-end product acceptance; native UX/resource use |
| Historical `933239a` full Python | 4,178 passed, 32 skipped | Current full-suite result |

Combined backend command from repo root:

```text
.venv\Scripts\python.exe -m pytest -q tests/unit/test_supervisor_loop.py tests/unit/test_trajectory_review.py tests/unit/test_event_processing_pipeline.py tests/unit/test_event_processing_store.py tests/unit/test_agentcore_pipeline.py tests/unit/test_windows_job_ownership.py --tb=short
```

Covers durable replay, uncertainty non-retry, budgets, routing and mocked ownership.
Inspect side effects before running whole process/worker test files under the hold.
Live authorization inventory is an AST check, not live-run approval. Test fixtures
do not replace explicit authorization. Earlier receipts and failures remain in the archive.

## Remaining work, in shipping order

1. **Native safety/acceptance:** fresh agreement for user-opened PEX-only checks.
   Observe transparency, calm motion, accessible fixed hide control, dismissible
   status, workspace/goal flow, startup/recovery and bounded idle CPU/memory.
   Retain exact source/package and screenshots. No PID cleanup.
2. **Visible MVP journey:** Zen BYOK save/error handling, real OpenCode/Codex attach,
   persistent goal, real Strands evidence-based NOOP/intervention, same-session
   continuation and verified completion. Saved settings or one CLI receipt does
   not prove the UI journey. Review code after every implementation batch.
3. **Quiet behavior:** complete ten-case sample, retaining failures.
   [OpenCode quiet receipt](demo/evidence/LIVE_OPENCODE_QUIET_2026-09-09.md) is one
   controlled case. [Closed-loop receipt](demo/evidence/LIVE_OPENCODE_PEX_CLOSED_LOOP_2026-09-09.md)
   is historical evidence, not a fair comparative benchmark.
4. **Benchmark:** `benchmarks/manifest.yaml` stays `frozen:false` until enforced
   worker/hidden-evaluator separation, raw vendor logs, Cursor same-conversation/
   network-policy proof, fixed models/budgets and attribution are satisfied.
   Eight-task package exists. Ordinary subprocesses, Python `-I`, manifest claims
   and saved stop payloads are not isolation/continuation proof. Do not add tasks
   to evade the recovery specification or publish a scored win prematurely.
   [Latest read-only runtime preflight](demo/evidence/BENCHMARK_RUNTIME_PREFLIGHT_2026-09-09.md):
   Docker CLI/WSL exist, Docker engine pipe unavailable; six execution-gate tests
   pass. Do not start Docker/VM services under the safety hold without agreement.
5. **Strands/AgentCore:** retain Strands reasoning and implemented AgentCore route.
   Fake-client tests are not deployment evidence. Live AWS proof requires current
   no-billing evidence and appropriate authorization.
6. **Audit/regression:** finish CODE_AUDIT_COVERAGE and remaining spec obligations.
   Many full-file audits remain pending; diff review and green subsets are not
   full audits or evidence of a perfect app.
7. **Build/video/submission:** rebuild collected fixes, verify package, capture live
   acceptance, film, and check materials against current official rules. Historical
   official deadline: 14 September 2026, 5 PM PDT; reverify before consequential
   submission action. User's target is tighter. Do not submit without authority.

## Local tools

Repo `C:\Users\JosephMayo\Projects\pex`; PowerShell.
Python/Ruff: `.venv\Scripts\python.exe`, `.venv\Scripts\ruff.exe`.
Desktop: run `npm test` and `npm run build` from `apps/desktop`.
Native build/verifier require the pinned toolchain on the current shell PATH:
`C:\Users\JosephMayo\.rustup\toolchains\1.97.1-x86_64-pc-windows-msvc\bin`.
Set `CARGO_BUILD_JOBS=2`. Build: `npm run tauri -- build`.
Verify: `npm run verify:package -- --receipt <new-source-specific-path>`.
Receipts are exclusive-write; never overwrite old evidence.

This handoff cleanup preserves all prior history. It changes no memory files,
credentials, runtime profiles, user apps or historical receipts.
