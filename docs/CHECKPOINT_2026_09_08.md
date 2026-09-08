# PEX checkpoint — 8 September 2026 WAT

Updated after the 8 September WAT idle-freeze report. The internal filming
target remains 9 September WAT. The three specs and the full shipping checklist
remain binding. Overall submission is **NO-GO**, not blocked: substantial safe work
remains. Do not substitute packaging success or a synthetic test for product proof.

## P0: reported whole-PC freeze while PEX was idle

The user reported that PEX froze the whole PC, and answered "nothing rly" when
asked what they were doing beforehand. Treat idle/background behavior as the
current critical path. **The cause has not been reproduced or established.** Do
not relaunch PEX, run live benchmarks, or resume the large regression/build workload
without a fresh bounded resource plan and operator confirmation. The earlier
Computer Use resume question is superseded by this incident. No app input occurred
after Escape.

The assistant stopped its exact clean full-regression Python child PID 23980 after
checking the owned launcher/command identity. Session 32515 ended -1 around 8%; this
is INTERRUPTED, never a pass. Retain `build/full-regression-1854eaf.log` in the clean
worktree. At incident inspection PEX PID 36124 and all pex-desktop/pex-bridge processes
were already absent; do not claim the assistant closed a live app that was not there.
Other apps and model servers were left untouched. Follow-up checks still found no
PEX process. No recent matching PEX application crash/hang or display-driver reset
was returned by the bounded Windows event-log queries. That is not proof no hang
occurred. Post-incident free RAM was about 31.5 GiB and C: had 85.6 GiB free; these
snapshots do not describe peak use during the freeze. The host reports Intel UHD 630.

Offline source review identified two resource-control gaps, not a proven freeze cause:

1. App background polls used intervals without awaiting slow reads. Most JSON reads
   and sprite-body downloads had no deadline. WebSocket intervention bursts could
   launch additional pet reads. The repair serializes each background poll, shares
   a pending background pet read across a burst, and applies a 15-second budget to
   the complete GET/authentication/body operation. Caller cancellation is preserved;
   superseded asset requests abort and release blob URLs. Explicit post-mutation
   reads remain independent, and mutation retry/unknown-outcome rules are unchanged.
2. Python lru_cache permitted duplicate concurrent cold atlas decodes. The first
   repair used a broad lock; independent Terra review correctly found it could
   block unrelated cached reads. A negative test reproduced that flaw. The final
   keyed implementation serves completed hits without waiting on image I/O, shares
   duplicate misses, allows at most two cold decodes, bounds follower waits to one
   second, and does not cache busy/timeouts as invalid. Completed cache size remains
   bounded to 128 and metadata changes invalidate the key. This is resource control,
   not a waiver of atlas validation or a change to the eight images.

These two repairs and activation-state presentation were pushed as
`1fdb7668021a49c285a8d724567f351f03d1e0ae`. They are not yet in a rebuilt installer.

Lightweight verification only: 112 focused desktop tests passed serially and
TypeScript no-emit passed. Fifteen targeted backend tests passed / 48 deselected;
JUnit in main: `build/freeze-bounded-backend.xml`, SHA256
`03DD8DEC3C9D98BED815164D912C2B66F816151F295D09B3B2296C5EDF951704`.
That selection includes new concurrency/deadline and saved-model activation-state
contracts; it is not the full suite or native resource proof. Ruff passed changed
Python paths. Two original cold-concurrency negatives failed before repair, and
the broad-lock cached-read negative failed before the keyed correction.

The same slice exposes bounded supervisor activation states to Home and Settings:
loading, timed_out, failed, unavailable, disabled and configured. Timed-out/failed
setup explains the existing Save supervisor retry path. It does not retry
automatically, change provider/billing settings, weaken timeouts or claim successful
inference from client configuration. Eight backend state negatives and one frontend
guidance negative failed before the presentation repair; scoped positives pass.

### Follow-up offline slice: goal polling and completed setup status

Another source-level buildup path was found: the goal decisions/completion effect
depended on the entire sessions array. Each worker snapshot restarted both GETs;
cleanup ignored their results but did not cancel them. It now polls serially every
four seconds after completion, scoped to goal id/intent revision. Changing that
scope or losing the bridge aborts both pending reads. `startSerialPolling` exposes
its lifetime AbortSignal; this goal effect uses it. Do not claim every older poll
now cancels in-flight work: their callbacks do not all consume the signal yet.
Two new negative tests failed before this repair; the old-code receipt remains
`build/goal-poll-negative.log` in main.

The new loading-state presentation also exposed a UI freshness gap: initial GET
could return `activation_status=loading`, then the backend could finish setup with
no subsequent Settings read. A loading-only, four-second serial status refresh now
updates the canonical supervisor snapshot, not the form draft. It never calls
loadSettings, resets a key/provider/model/input, retries a write, reloads a model,
or promotes configuration into inference proof. It is disabled for the floating
pet, unavailable canonical settings and active saves; cancellation and request
sequence guards discard superseded reads. A changed/invalid saved revision or a
read failure stops polling and requires explicit reload rather than silently
rebasing a draft or clearing an uncertain-save warning. Terminal activation states
stop polling. One wiring negative failed before implementation; helper tests cover
invalid/changed revisions and concurrent edits/reloads/saves.

Verification of the follow-up source: **207 focused desktop tests passed serially**
in 3.7 seconds; TypeScript no-emit passed. Command from apps/desktop:
`node --test --test-concurrency=1 src/viewModel.test.ts src/firstRun.test.ts src/readBudget.test.ts src/startupRecovery.test.ts src/supervisorDraft.test.ts src/operatorRequest.test.ts src/sharedConnection.test.ts src/autonomousCorrections.test.ts src/releasePet.test.ts`.
This excludes packaging-contract tests and backend/full/native suites. Parent
reviewed the diffs; the existing Terra-medium reviewer independently found no
actionable issue in goal cancellation, the final keyed atlas cache, or loading-only
supervisor refresh. Source/wiring checks are not rendered or native UI evidence.
The protected operator loop.py hash remains unchanged; do not stage that file.

Next: push the follow-up slice, then continue bounded offline audit. Native resource
verification needs renewed operator confirmation; the previous question remains
unanswered. Proposed next native check, **not yet approved or run**:

1. Arrange a time when the operator is not using this PC. Verify exact source and
   owned process identities; preserve other agents, apps and model servers.
2. Build sequentially from the clean worktree, without a parallel full suite/live
   worker. Confirm separate build resource limits before starting that workload.
3. Launch one isolated PEX profile with inference and automatic attachment disabled.
   Record only owned process identity/creation time, CPU, memory, handles/threads and
   sanitized lifecycle status; do not collect credentials or other app content.
4. Observe a maximum 60-second idle interval, with agreed resource-stop thresholds
   and an independent bounded watchdog. Do not drive mouse/keyboard during this
   idle capture or attach a real worker. Stop earlier on abnormal growth or failure.
5. Close the exact owned instance and retain the receipt, including any failure.
   Only a successful capture can justify discussing a longer stability/workflow run;
   it would still not prove the whole-PC freeze resolved.

No kernel/driver freeze can be guaranteed recoverable by a userspace watchdog.
Broader release gates and submission work remain open until stability is demonstrated.

## Verified package and paused native check

Exact pushed source `de8315393e193a3ad1ec37398141ee49e48ad49e` includes the pet-only
canvas color-scheme specificity fix. Desktop 215 tests and TypeScript/Vite passed on
main and the clean worktree. Its normal Tauri build produced both Windows installers.
Both extracted installer inventories passed: the four executables and eight pets.

Clean worktree: `C:\Users\JosephMayo\Projects\pex-release-9329a67` (historical name).
Receipt: `build/package-de83153.json`, SHA256
`CC6070D4E5793691405BA9ADBBCABE59CB41FBFB6CE0AB157F4A431731CBFDD9`.
MSI SHA256: `ee23c926e8be8824708904264761584b5a71b8499bebd361ae73284c32776c21`.
NSIS SHA256: `0d254e1a5f284f059ec910876b8ef055c20a5d67a576c77001d1c5160563e26c`.
`release_ready: true` in that receipt means package integrity only.

The first de build failed frozen-bundle smoke with a 60-second subprocess timeout
and an EPERM cleanup error. It is retained in `build/release-build-de83153.log`.
The unchanged normal retry completed with exit 0; retained log:
`build/release-build-de83153-retry.log`. Do not erase or relabel the first failure.

An isolated inference/automatic-attachment-disabled de desktop was launched with
`build/launch_native_de83153.py` from main; profile
`build/native-smoke-de83153` in the clean worktree, launch PID 36124. The subsequent
window inventory was stopped by physical Escape. No further Computer Use or app
input was issued. PEX was left open; recheck PID/window identity before any future
action. Canvas transparency and eight-pet animation playback remain unverified on
de. Earlier 7a native startup, restart, bubble dismissal, hide/restore and persisted
Von selection were observed and remain distinct historical evidence.

## Real Q18: completed inference, quiet behavior, limited acceptance evidence

This was a fresh existing Codex worker observed by exact clean de PEX, not a replay
or prewritten PEX intervention. Worker model: `gpt-5.3-codex-spark`. Supervisor:
`muse-spark-1.3-contributor-free` via the saved Zen free configuration. No production
SDK retry overrides, paid provider, AWS resource or additional task-changing prompt.

- Workspace: `C:\Users\JosephMayo\pex-live-demo\workspace\quiet-20260907-Q18`.
- Worker: `01a07e04-74f3-7450-a78e-20f31af4b5fc`.
- Work turn: `01a07e08-c8f1-7d12-a234-1d7dc11fa787`; completed.
- Intervention: `intervention_62a8a1b3ce236b86d6fba446f2eb88a9cf7e37fa`.
- Strands runtime 1.53.0; two real model calls, HTTP 200/200; inference completed
  in 26,068 ms; NOOP, transport not attempted, no worker correction delivered.
- Tools: run_verification, inspect_workspace, inspect_artifact. The exact
  `test_durations.py` unittest target was observed with exit 0 and no later edits.
- Independent copied-workspace oracle passed four tests. All five immutable input
  hashes matched. Output `durations.json` matched the oracle byte for byte, SHA256
  `E66FAD6FE122A62397EFDC0E7975047C54BBC0C52BC500EB713E9D13EFAFBA73`.
- Model acceptance remained uncertain: the file existed, but inspect_artifact only
  searched five conventional filenames and could not read this named output. The
  model stayed silent rather than invent a defect. This is completed model reasoning
  with quiet behavior on the tested output, NOT full semantic acceptance, a scored
  benchmark, the ten-case quiet gate, or whole-product readiness.

Retained final post-revoke/detach capture, under the clean worktree:
`build/quiet-live-20260907/Q18/client/capture-20260907T224948154732Z.json`, SHA256
`F3586CE5193178ED13EFCBF98A644400C6F38FD899C3EAEBD124EF70DBC5F69F`.
Raw events are paginated under `events.items`; do not treat the envelope as events.
The capture may not be the entire transcript; preserve the other client captures,
worker receipts and logs alongside it.

Q18's first saved-model activation timed out during cold setup. One explicit normal
configuration PATCH reloaded the same free configuration before task execution;
`Q18/supervisor-reload.json` records it. This was configuration, not inference.
Startup recovery guidance still needs improvement; do not conceal the cold timeout.
Q17's earlier 200/429 inference timeout stays inconclusive and is not replaced by Q18.

Cleanup completed: correction grant revoked, observer detached, owned bridge PID
36720 and private listener PID 18428 stopped after exact identity checks, port 7439
no longer listening, and only the stale owned zero-byte Q18 socket removed. All
receipts and worker artifacts remain. Never restart Q18 or reuse its intents/IDs.

## Named-artifact repair and audit

The checkpoint's source slice lets inspect_artifact read a specifically named
visible output through the existing invocation authority guard. It reports an
800-byte head preview and explicit truncation; conventional result tails remain
available without an argument. It does not execute worker code or infer goal success.

Validation rejects falsey non-string arguments, escapes, alternate streams, hidden
and dependency paths, private link aliases and hardlinks. Independent Terra-medium
review caught falsey arguments and a path-check/open race. Three deterministic race
tests reproduced private-content leakage before the descriptor-bound repair. The
checked descriptor now supplies both preview and row count; identity/link validation
occurs before bytes are read. Generic visible-file reads use that same safe reader.
Existing cancellation and changed-authority tests cover named artifacts as well.

Ruff passed the six changed Python files. Scoped backend regression passed **189,
five skipped** (Windows symlink creation unavailable), in 44.15s; JUnit:
`build/named-artifact-descriptor-regression.xml`, SHA256
`4087D2006209232A3537A39D9FC1F2F687DF8263FA50B29E010833EAB02FE4F8` in main.
A subsequent non-regular-file pre-open guard still needs the next clean gate.
This is bounded changed-path review, not closure of the 341-path source audit.

Two earlier broad-run failures are retained: one test assumed its constructor
worker had entered within 20ms; it now explicitly synchronizes worker entry and
always releases it in finally, preserving timeout/quarantine assertions. The other
was an unexpected 503 on restoring the inherited review cap. Its original response
body was not captured. A focused 49-test rerun, the 189-test run and 30 fresh repeated
save/revision diagnostics passed. The 503 is unreproduced, not causally explained;
the contract assertion now retains its response detail if it recurs. No speculative
production storage retry or weaker configuration authority was added.

## Immediate ordered work

1. Address the P0 idle-freeze report above; do not restart full gates or native PEX
   while the operator is using the PC without renewed bounded-run confirmation.
2. Push reviewed resource/activation-state repairs and finish safe offline checks.
   Keep tested package de separate from newer source evidence. Full clean regression
   for pushed `1854eaf65f4f391758085da6ebfb1f471db4c195` was interrupted, not green.
3. Complete a fresh provider-complete quiet/recovery pair after clean gates. Preserve
   all failures/aborts and distinguish demos from the frozen benchmark. Do not seed
   a desired PEX decision or substitute a manually sent recovery message.
4. Resume native checks only after renewed permission following Escape: verify de
   canvas and all eight pets at actual size, then the complete human onboarding,
   goal, connection, inspection, pause/decisions/context and recovery workflow.
5. Continue the full source audit and fair requested Cursor/Codex/OpenCode comparisons
   under the existing model, isolation and budget boundaries. The binding frozen
   benchmark has four Cursor/Codex arms; OpenCode is an explicitly separate addition.
6. Resolve actual AgentCore proof under the user's no-bill constraint. Do not claim
   deployed AWS infrastructure when only deploy code exists. Finish truthful setup,
   architecture, filming script, <=5-minute live video and submission materials.
7. Final evidence-backed review and operator-authorized submission. Winning is the
   aim, not a promised result; incomplete checklist items remain incomplete.

Protected operator-owned `services/supervisor/src/pex_supervisor/loop.py` is unstaged
and unchanged, SHA256
`DEA56DA49607069E889D56DA0D458D7CF5284555967FCD617867316A6D7ED77E`.
Never stage it with this slice. No paid inference, AWS deployment, duplicate public
post or final submission has been performed. Use economical Terra-medium review
only when an independent bounded subtask adds value. Keep working on safe open work.
