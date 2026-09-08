# PEX checkpoint — 8 September 2026 WAT

Updated after the 8 September WAT idle-freeze report. The internal filming
target remains 9 September WAT. The three specs and the full shipping checklist
remain binding. Overall submission is **NO-GO**, not blocked: substantial safe work
remains. Do not substitute packaging success or a synthetic test for product proof.

## Latest offline slice: idle event-ledger scan

Each desktop event socket tails event_publication_page every 250ms when caught up.
Its combined joined MIN/MAX bounds query scanned the entire publication history on
every idle read. Two small production-schema fixtures reproduced growing work:
at least 1,100 SQLite VM steps for 128 accepted records and 18,400 for 2,048. Both
failed the new 500-step ceiling on prior c5d8a04 source. These are query work counts,
not host CPU/GPU measurements or proof of the whole-PC freeze cause.

The replacement reads the two indexed endpoints with ASC/DESC LIMIT 1 scalar
subqueries in one statement, keeping the same join and statement-level bounds
snapshot. No schema/index migration, persisted watermark cache, polling interval,
event loss, retention-gap waiver or cursor-semantic change. The read cursor now
closes explicitly. Empty-ledger bounds, frozen pages, scope, retention gaps, socket
authentication, replay/cancellation and broadcast cleanup are covered by the narrow
three-file backend selection: **15 passed in 9.59s**, Ruff passed both changed Python
files. Both size cases now meet the <=500-step ceiling. The work-count guard targets
the valid caught-up ledger, not every query shape or corrupt orphan-row case.

Parent reviewed the query, relevant table/trigger/index definitions and tests. The
same existing Terra reviewer checked the narrow SQL/fixture diff independently and
found no actionable regression in empty/pruned/frozen/scoped behavior. This is not
a full store.py audit. No native app, worker/model, port-listening server, cloud,
large suite or build ran; fixture HTTP/WebSockets were local ASGI/TestClient only.
Protected loop.py hash is unchanged. Native stability and all submission gates
remain open; de83153 installers still predate these repairs.

## Earlier offline slice: hidden-pet animation lifetime

The renderer did not consume overlay visibility or page visibility. Hidden pets
could retain their frame timer, and CSS breathing/listening loops were not explicitly
paused by hiding. `PetStage` now receives the existing pet visibility intent without
unmounting it, preserving dismissed-message state. The sprite stops scheduling
frames when inactive, page-hidden, reduced-motion or missing its source; hidden/
reduced-motion sprites also pause CSS animation and remove their transform promotion
hint. Pointer hover/look timers clear when inactive, hidden or reduced-motion.
Explicit reduced-motion still allows deliberate dragging/keyboard activation.

New `pageVisibility.ts` uses React's external-store subscription and shares one
browser visibility listener per webview across all mounted consumers. Last cleanup
detaches it; remount reattaches it. This does not use focus loss as visibility, stop
backend supervision, change polling, destroy a pet or modify any of the eight
atlases, state mappings or frame durations. Hidden-to-visible resumes normal cadence
without a catch-up loop. Native WebView visibility reporting is not yet measured.

One SSR inactive-render regression failed on 2edcb4e and passes after the fix. A
fake-document test verifies nine consumers share a listener, hidden/restored
snapshots, subscriber isolation, last cleanup and remount. A source-wiring check
verifies the timer guards/cleanup and that visibility cleanup does not reset bubble
state. Final nine-file desktop selection: **223 passed, zero skipped, 9.93s**;
TypeScript no-emit exited **0**. These are SSR, helper and source tests, not mounted
browser/native timer or GPU measurements. Parent reviewed the complete visibility
helper, atlas/PetStage runtime changes and tests using the React review checklist;
no additional subagent or image-generation job was used for this slice.

Protected loop.py retains its recorded hash. PEX remains closed; no build, native
input, paid/cloud operation or live benchmark ran. Reported whole-PC freeze remains
unexplained. Do not infer current installer quality from these source-only tests.

## Earlier offline slice: native bootstrap read lifetime

The bootstrap UI awaited native `bridge_bootstrap_status` without a deadline. A
never-settling IPC left that poll pending indefinitely. It now uses a module-scoped
single-flight read with a five-second caller budget. Timeout/cancellation retires
the shared observation; while the underlying IPC remains pending, later reads fail
unavailable without dispatching duplicate native calls. After the raw call settles,
the next read observes fresh state, never a cached late ready result. Native IPC
itself is not cancellable by this helper; a permanently stuck native call remains
unavailable until native/application recovery. This is NOT a whole-PC freeze fix.

The main/settings bootstrap poll passes its cleanup AbortSignal and checks it
before publishing. The pet still does not poll native bootstrap. Native generation
ordering, token checks, bridge launch/retry mutation and unknown-mutation handling
are unchanged. An unavailable read gates UI without overwriting canonical native
generation state. Sharing is per JavaScript webview, not a cross-window global cap.

Parent reviewed the complete helper, its six new functional tests, bootstrap App
wiring and the new source-wiring regression. Terra's bounded read-only review found
no concrete regression and suggested the two-caller cancellation case; it was added
and parent-verified. Additional cases cover pre-start cancellation and synchronous
raw failure. The first development run failed import before the new helper existed;
that is not an old-runtime behavioral reproduction. Final serial nine-file desktop
selection (same command below): **220 passed, zero skipped, 6.83s**. TypeScript
no-emit subsequently exited **0**. Source-wiring tests are not rendered/native proof.

No native launch, Computer Use, large regression/build, live inference or worker
benchmark ran. Protected loop.py retains its recorded hash. Existing de83153
installers do not contain this or the preceding offline repairs. Primary remaining
work is current-source native stability/eight-pet/human workflow, genuine quiet and
recovery proof, full audit/comparisons, no-bill AgentCore and truthful submission.

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

Pushed as `7fd37570013bbd3bf7be73e59de41aad335ce3eb`.

Another source-level buildup path was found: the goal decisions/completion effect
depended on the entire sessions array. Each worker snapshot restarted both GETs;
cleanup ignored their results but did not cancel them. It now polls serially every
four seconds after completion, scoped to goal id/intent revision. Changing that
scope or losing the bridge aborts both pending reads. `startSerialPolling` exposes
its lifetime AbortSignal; this goal effect uses it. At that checkpoint the older
poll callbacks did not all consume the signal; the view-lifetime slice below
addresses those callbacks, not every native or backend cancellation boundary.
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

### Follow-up offline slice: discovery response deadline

Discovery limited individual HTTP waits and response size, but not the complete
response lifetime. A peer could keep sending small chunks without ever finishing.
The repair wraps each probe's headers/body/stream cleanup in `asyncio.timeout`,
using the existing configured timeout (default 350 ms, validated maximum five
seconds). The next peer is still probed after timeout. Loopback probes now explicitly
disable environment proxies and redirects; malformed and oversized responses remain
rejected, with size checked before appending a chunk to the accumulated body.
This is not a deadline on the complete discovery function: desktop enumeration and
executable resolution retain their existing separate behavior.

Three initial negatives failed on the previous source (stalled headers, stalled
body, and missing explicit proxy policy). A fourth test sends continuous small
chunks; it failed when the committed pre-fix module was loaded only into a child
test process, then passed on the repaired source. No live socket/worker was used,
and production files were not reverted for that negative. Final targeted command:
`.venv/Scripts/python.exe -m pytest -q tests/unit/test_discovery_budget.py tests/unit/test_adapter_deep_audit.py tests/unit/test_existing_sessions.py tests/unit/test_fleet_pets_codex.py -k 'discovery or discovered or probe_local' --tb=short`.
Result: **18 passed / 125 deselected, 1.59 seconds**. Ruff and changed-path diff check
pass. The nine new tests include stream closure, caller cancellation, continuing to
a healthy peer, valid health, malformed/oversized bodies and continuous progress.
Parent reviewed this small backend slice; no extra subagent was used. These tests
do not establish the cause of the whole-PC freeze or prove native idle stability.

### Follow-up offline slice: bounded, descriptor-checked workspace observation

Current baseline before this slice is pushed `af5161c066cf7cbedc23c432cc2ceeb5d69ccb0e`.
Independent Terra audit found a reachable containment gap in observe.py: a workspace
hardlink to an outside file was hashed, and replacement between containment check
and open bypassed the earlier path check. These are production observation paths
used by Pipeline during relevant tool/shell events, STOP and claim verification.
Only tiny fixture secrets were used to reproduce them; no real private data read.

The repair rejects linked/non-regular files, checks opened-descriptor identity
before bytes, and discards a hash if size/mtime/path identity changes during the
read. Common credential filenames and private-directory exclusions now recognize
case variants. Read-only snapshots no longer hash the whole workspace twice;
explicitly authorized verification still rescans afterward for new artifacts.
No new test execution, provider call, cache, model behavior or policy bypass is added.

Resource bounds now include a five-second **cooperative** per-manifest budget,
checked between directories, entries, files and chunks, plus a 20,000-total-entry
enumeration cap before sorting. Existing 10,000-file, 64 MiB/file and 512 MiB/pass
caps remain, and the total byte budget rejects an over-budget next file before
hashing it. Incremental scandir replaces os.walk's unbounded directory-list setup;
normal sorted depth-first manifest ordering is retained. Queued directories retain
their Path.stat identities and are rechecked before/after enumeration. The initial
DirEntry.stat implementation failed the normal nested-directory test on Windows;
using Path.stat for identity repaired it. Do not erase that development failure.

Evidence: two external-hardlink negatives failed on original source; parent added
three more negatives for duplicate hashing, non-regular open and replacement exactly
at open. A fake-clock negative then proved the missing time budget. Independent
review exposed enumeration before budget checks; two tiny negatives reproduced that
gap before incremental/capped enumeration. The reviewer subsequently exposed queued
directory replacement; the final cross-platform fixture proves refusal before the
replacement is enumerated. Final review found no new concrete regression.

Final lightweight verification, from main; all commands exit 0:

- `.venv/Scripts/python.exe -m pytest -q tests/unit/test_observe_budget.py tests/unit/test_observe_security.py -k 'not public_pytest' --tb=short`: **18 passed, 1 FIFO-host skip, 2 subprocess tests deselected**, 0.91s.
- `.venv/Scripts/python.exe -m pytest -q tests/unit/test_workspace_continuity_pipeline.py -k 'change_during_snapshot or queued_snapshot or snapshot_cancellation or unchanged_directory_identity' --tb=short`: **7 passed, 14 deselected**, 5.49s.
- `.venv/Scripts/python.exe -m pytest -q tests/unit/test_pexbench.py -k workspace_hashing_streams --tb=short`: **1 passed, 128 deselected**, 0.66s; a small streaming-hash fixture, not a benchmark run.
- Ruff passed the three changed Python paths; changed-path whitespace check passed.

Remaining limitations are **not closed by this slice**: an OS metadata/open/read
call already blocked cannot be interrupted by the cooperative budget; repeated
events can trigger separate bounded scans; path-based directory validation is not
atomic descriptor-bound enumeration. No claim of a whole-workspace atomic snapshot,
native stability, or cause of the reported idle freeze. Protected loop.py remains
untouched at its recorded hash. No native/build/live-model/CU workload was started.

### Follow-up offline slice: view cancellation and handoff read fanout

Pushed as `70ba867a7b50ec787196cc89d1d207cc5eb5b016`.

Baseline: pushed `50e66ff4dd210cdb7330e2cca2629005c79c054b`. App background pet,
base-state, pet-goal, detail and identity-status reads now consume their view/poll
lifetime AbortSignal. Cleanup advances the existing request sequence before abort;
late responses cannot publish into a superseding view. Explicit post-mutation reads
remain independent; there are no new writes, automatic mutation retries or model
calls. This is client cancellation, not proof that native or backend work stops.

History previously expanded up to 200 intervention rows into concurrent handoff
status GETs. The shared read helper now permits at most four active reads per batch
under one 15-second complete-batch deadline. Cancellation/deadline stops queued
reads; completed results retain their order, and unread entries explicitly map to
the existing unreachable presentation. Late uncooperative completions cannot mutate
the returned result or release queued work. This is not a global request limiter.

Core history data publishes without waiting for the follow-up status batch. Old
status results are cleared rather than presented as current; a second sequence
guard protects later publication. The batch promise is rejection-handled immediately
and remains part of the serial poll lifetime. Independent Terra follow-up caught
the first stale-sequence exit returning before the pending batch settled; parent
fixed that exit to await the bounded batch without publishing stale results.

Verification: **213 focused desktop tests passed, 0 skipped, in 3.52 seconds**;
TypeScript no-emit and changed-path diff check pass. The serial command is the same
nine-file desktop selection recorded above (not package-contract/full/native tests).
New functional tests cover four-read concurrency, ordered success/failure, a 200-item
deadline fixture, caller cancellation, empty/already-cancelled input and late results.
Source contracts cover signal plumbing and two-stage publication; those contracts
are not rendered/UI interaction evidence. The initial signal-wiring negative failed
on prior source. Two old source-regex expectations needed the added signal argument;
the first broader run failed on the stale AttentionMetrics regex, then passed after
the expectation was updated. No real bridge, model, worker or native app was launched.

Parent reviewed all changed desktop paths. Terra found no issue in the bounded-read
helper/cancellation slice; its two-stage lifetime finding was integrated afterward
and rechecked by parent. The protected operator loop.py is untouched at its recorded
hash. These are source repairs only; installers still predate them. They do not
explain the reported whole-PC freeze or establish idle/native stability.

### Follow-up offline slice: Cursor inbox read and record budgets

Pushed as `43d93370bcf72e4b1f01eeb07303d6087774e5a5`.

The parent read cursor_inbox.py, its fail-open producer and the bridge's quarter-
second observer loop. Six tiny negative fixtures exposed unbounded actual file and
marker reads, no record-count budget, and malformed Unicode/overlong offset handling.
A seventh negative proved the old over-8-MiB branch erased unread backlog. No user
inbox was read or modified; all reproductions used temporary fixture files.

The repair caps the actual inbox read at 8 MiB even if a producer grows the file
after stat, reads at most 65 marker bytes (rejects over 64), and accepts only ASCII
digit offsets. A drain consumes at most 128 physical lines, including malformed and
empty ones; only that prefix advances the marker. Incomplete JSONL remains pending.
Oversized complete records remain skipped under the existing per-record bound.
The reader no longer truncates a larger backlog: it drains it in bounded reads.

Final targeted verification: **13 passed / 44 deselected, 12.49 seconds** from
`.venv/Scripts/python.exe -m pytest -q tests/unit/test_cursor_inbox_budget.py tests/contract/test_cursor_hooks.py -k 'inbox or offset or batch_limit or production_batch' --tb=short`.
The new nine-case file includes the production 128-line cap, Unicode/CRLF byte
offsets, oversized complete records, partial writes and non-destructive backlog
draining. Four existing Cursor contracts also pass, including local ASGI ingestion;
no external server, Cursor process or model was used. Ruff initially found one long
test signature; wrapping it repaired the lint-only failure and Ruff now passes.
Parent reviewed both changed files; bounded Terra review found no new regression.

**Still open, not a whole-reader safety pass:** the loop still performs synchronous
OS I/O; the marker advances before async ingestion, so interruption can lose unread
processing work; path-based marker writes lack linked-path/generation protection;
an oversized newline-free record can exceed the read window; safe producer-
coordinated disk retention is not implemented. Removing destructive truncation
preserves evidence but is not a disk-space limit. Address these explicitly before
claiming reliable Cursor observation or native stability. No freeze cause established.
Protected loop.py remains unchanged. No native/build/live-model/CU work started.

### Follow-up offline slice: durable Cursor admission before checkpoint

Pushed as `b7fadf7`.

The previous goal turn made progress (70ba867 and 43d9337 pushed); the full goal
remains active. This slice replaces consuming `drain_inbox` with a non-consuming
`read_inbox` batch and explicit `acknowledge_inbox`. The runtime performs both file
operations on a worker thread, then processes the bounded batch serially. Only
normal completion of every valid record permits checkpointing. Failure, stop or
cancellation before acknowledgement keeps the prefix available for at-least-once
replay. The real Store/Pipeline duplicate contract, not a boolean HTTP response,
prevents duplicate acceptance. The old consuming helper has no remaining call sites.

Independent Terra audit found that every synchronous Cursor hook class can return
a normal fail-open response on timeout before durable acceptance. The observer now
has a separate ingestion path that forces observe-only delivery authority, shares
the unchanged session/event preparation, and directly awaits Pipeline ingestion and
continuation observation. HTTP hook response/deadline behavior remains unchanged.
Collisions, transient capacity/authority failures and other exceptions stay pending;
the loop no longer treats any error containing "event id collision" as safe to skip.
Failure polling backs off to 30 seconds and logs only the exception class once until
recovery, without payload contents. Reviewer follow-up caught the initially absent
observer deadline. The final 90-second **cooperative** deadline includes preparation,
ingestion and continuation; expiry propagates as failure, never acknowledgement.

File reads refuse linked/non-regular paths and check opened descriptor identity
before bytes. Acknowledgement rechecks source identity, the exact consumed-prefix
digest and the prior offset. It creates/flushed/fsyncs a fresh temporary checkpoint
and replaces the marker, without truncating through an existing marker link. Normal
append remains pending for the next batch. Failed replacement preserves the prior
marker and removes only its newly created temporary file.

Verification on main, no native/model/worker launch: **27 passed / 44 deselected,
14.64s** in the two inbox unit files plus `test_cursor_hooks.py`, selected with
`-k 'inbox or offset or batch_limit or production_batch or consumer or checkpoint or stop_between or reader_and_acknowledgement or source_or_marker or same_file or replacement_during_open'`.
A separate unchanged-HTTP behavior selection in `test_cursor_hooks.py`
(`-k 'hook_pipeline_deadlines or named_stop_hook_deadline or permission_mapping or pause_supervision'`)
passed **6 / 46 deselected, 7.74s**. Ruff and changed-path diff checks pass.
The new API's initial two tests failed because the mechanism did not yet exist;
do not portray that as an old-runtime reproduction. Two first deadline tests hit
SQLite setup before the intended injected failure; isolated preparation corrected
those fixture races. Two import-format lint failures were also corrected. Current
tests prove real local Store replay, timeout/collision refusal, cancellation, stop,
off-loop I/O, hardlink/open replacement refusal, checkpoint failure, and append.

**Remaining release obligations:** legacy numeric offsets still need persisted
file-generation binding across restart; directory/path check-open and final replace
are not atomic against concurrent external mutation; a blocked OS call or resistant
cancellation is not hard-bounded. Poison-record rejection receipts/UI, oversized
newline-free record recovery and producer-coordinated disk retention remain open.
Malformed physical JSONL lines still use the prior skip behavior without durable
rejection receipts; semantically invalid dictionaries remain pending and can block
later records. Do not describe these as reliable full Cursor delivery yet. Existing
bounded-reader tests were adapted to explicitly acknowledge only fixture reads;
production has no acknowledgement-before-consumption shortcut. Parent reviewed all
changed paths; Terra's observer-path findings were integrated and parent-rechecked.
Protected loop.py is unchanged at its recorded hash. Native stability/freeze cause,
latest installers and the full submission scope remain unverified/NO-GO.

### Follow-up offline slice: restart-bound inbox checkpoint and incremental reads

Three tiny negatives reproduced skipped new events after file replacement, same-
inode rewriting at the consumed boundary, and trusting an unproven legacy offset.
The checkpoint is now versioned JSON containing offset, filesystem device/inode
identity and a SHA256 of at most 4 KiB ending at that offset. Reads verify the
identity/boundary before seeking past old records. An unbound legacy or invalid
checkpoint replays from the beginning, and successful durable ingestion migrates it
once. Existing Pipeline semantic duplicate checks still arbitrate replay. Migration
can require processing a backlog; do not call it a no-work or live-proven upgrade.

Checkpoint parsing reads at most 257 bytes and rejects documents over 256 bytes,
duplicate keys, invalid version/field shapes, boolean/inadmissible numeric fields,
and invalid hashes. Legacy numeric input remains capped at 64 bytes. The exact prior
marker bytes, not merely its numeric offset, are checked before replacement.
Caught-up reads examine only the small boundary and do not read the backlog body.
Active reads now stop after 128 complete physical lines using bounded readline;
they no longer copy a whole backlog merely to consume that prefix. The 8 MiB
per-pass and existing per-record limits remain, and incomplete lines stay pending.

Final same three-file targeted inbox/contract command above: **36 passed / 44
deselected, 15.50s**. This includes nine added restart/format/idle tests; all three
restart negatives failed on b7fadf7 before repair. Ruff initially found one long
parameterization decorator; wrapping it repaired the lint-only failure. Ruff and
changed-path diff checks pass. Parent reviewed this small follow-up without another
subagent; no app/build/model/worker run. Protected loop.py remains unchanged.

Limits remain explicit: device/inode plus a small boundary checksum is not a digest
of all historic bytes. In-place edits earlier than that boundary, non-atomic
directory/check-open/replace races, resistant cancellation and blocked OS calls are
not excluded. Poison-record rejection receipts/UI, oversized newline-free recovery
and producer-coordinated retention remain next. Source protection is not installed-
app verification, native stability or a proven cause of the reported PC freeze.

Next: continue bounded offline audit; the main process/read lifetime paths still
need broader coverage. Native resource verification needs renewed operator
confirmation; the previous question remains unanswered. Proposed next native check,
**not yet approved or run**:

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
