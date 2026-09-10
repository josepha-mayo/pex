# PEX active handoff

**Shipping scope: [MVP_SHIP_GATE.md](MVP_SHIP_GATE.md).** Current official rules
make AgentCore deployment optional. Retain its tested implementation without
claiming deployment. The user's later small-MVP request takes priority over
historical expansion gates; formal four-arm scores remain unclaimed. The unsafe
933239a launcher instructions have been removed from the recording runbook.

Maintained checkpoint: 11 September 2026; current-source Codex recovery and quiet checks passed.
**Submission status: NO-GO. The full goal remains active.**
Verify Git/current files and running processes before relying on this checkpoint.
This is the active entry point, not another historical log.

## Latest verified checkpoint — supersedes historical status below

**Current packaged candidate: `567778b`.** Clean full Tauri build completed;
MSI and NSIS verification passes with zero blockers and 2,375 matching runtime
files. Receipt `build/package-567778b-20260910-rebuilt.json`, SHA-256
`9bda2583d3307dd7470002fec4e419f7ba4700a7fd9e9dcb393132222de7185e`.
An earlier verification against stale pre-commit installer artifacts correctly
failed with runtime/helper mismatches; retain
`build/package-567778b-20260910.json` as failed evidence. `567778b` includes the
Ask overflow repair and explicit OpenCode cancellation fence. Source gates:
290 frontend passed/one platform skip, production build passed, 77 focused
supervision/continuity tests passed, and 228 Ask + offline AgentCore tests passed.
Native verification of the newest Ask/cancellation behavior is pending because
Joseph is using the PC and requested offline-only work until he says otherwise.
Do not use Computer Use before that permission changes.

**Later offline checkpoint: product `53105d6`.** Native inspection of `5a4c4ac`
found the compact Ask input overflowing the window when suggestion chips appeared.
`53105d6` repairs the layout to one bounded column with scrolling suggestions;
289 frontend tests passed (one platform skip), production frontend and full
Tauri/MSI/NSIS builds passed. Installer integrity passed with zero blockers:
`build/package-53105d6-20260910.json`, SHA-256
`fb824849e6385e459dcb2bfd55610799fc14d942e73b9fa2a7da9ae048f74d64`.
The first verifier command omitted Rust from PATH and failed before verification;
the corrected command passed. This does not prove the new layout natively:
Escape stopped Computer Use before launch, and Joseph subsequently explicitly
requested offline-only work while he uses the PC. Do not resume UI control until
he says he is ready. No PEX process was found at the following read-only check.

The older full offline run completed: **4 failed, 4,426 passed, 16 skipped,
18 deselected**, 2,137.96s. Its XML is
`build/full-offline-5a4c4ac-20260910.xml`; it predates the cancellation repair.
Two failures were packaging contracts (missing Rust PATH and stale one-file
expectations); both contracts now verify the unpacked runtime. Focused preflight
passed. Codex echo cleanup had a test synchronization race: Store completion can
precede the adapter's in-memory acknowledgement. The fixture now waits for the
actual ingress-sequence acknowledgement before asserting cleanup. The fourth
failure was a 10-second STOP settle timeout with planner delivered; its focused
rerun passed without a production timing change, so broad-load stability is not
claimed. The first narrowed run passed 18 tests. After the cancellation repair
and echo wait fix, OpenCode idle/lineage, Codex echo and unchanged-workspace STOP
tests passed **77/77 in 29.23s**. Ruff/diff checks passed. Frontend: **290 passed,
one platform skip**, production build passed.

Exact assistant `MessageAbortedError` now persists `opencode_turn_aborted: true`,
holds STOPPED without automatic follow-up across idle/discovery/restart, and
clears only after concrete tool/file activity. A simultaneous provider limit
retains BLOCKED priority. Malformed/non-assistant/ordinary errors do not create
the fence. UI explains cancellation without calling it completion. This is
source-tested, not yet packaged or natively verified. Idle-only cancellation
without explicit vendor abort evidence is not distinguishable from ordinary
completion and is not claimed solved. Do not relabel the old full run as green.

**Native product `5a4c4ac` now verified for the provider-limit repair.** Full
Tauri build passed; MSI/NSIS verification passed on one bounded retry, retaining
the first cleanup-EPERM receipt. Native startup needed no Retry, both pet previews
loaded, and isolated OpenCode attach succeeded on the first attempt. One free
Ling prompt hit quota; Inspector showed Blocked with the correct explanation.
After exact-session abort/idle, 61 events were complete and the durable fence
remained set, with zero additional model reviews or interventions. The test
session is paused again and its owned server runner exited 0. PEX remains open.
See `demo/evidence/NATIVE_QUOTA_FENCE_5A4C4AC_2026-09-10.md`. Generic cancellation
without quota, final stability, fresh-user installation and recording remain
unverified. A current full offline Python regression is running; do not assume
it passed until its terminal result is recorded.

**Clean-source live Codex/Strands pair passed at `e864389`.** Quiet completion:
1 passed in 79.19s, validated evidence-supported NOOP. Incomplete-stop recovery:
1 passed in 193.45s, same owned thread/process, exact `report.txt`, helped outcome,
then model-backed NOOP. Both retained clean-source provenance, pinned Spark,
saved free Muse/Zen, and a three-dispatch cap. See
`demo/evidence/CODEX_LIVE_E864389_2026-09-10.md` for receipt hashes and limits.
PEX was closed normally through its own window before the rebuild; no PEX
process remained at the subsequent check. No unrelated app was closed.
The rebuilt native provider-limit check above now supersedes this checkpoint's
rebuild TODO. Keep the failed Ling run as failed evidence.

**Provider-limit repair, after the evening native failure:** OpenCode retry
messages/actions now survive normalization. Exact `free_tier_limit` becomes a
durable Blocked state with no automatic follow-up, including later idle and
repeated metadata. Discovery cannot erase or mint the fence, and atomic event
processing clears it only after observed tool/file activity. This conservative
reset does not treat a new text prompt as proof that provider access recovered.
Inspector explains the limit without recommending payment. Generic cancellation
without provider-limit evidence remains a separate unresolved behavior.
Broad processing/OpenCode regression: 123 passed in 91.95s; final persistence
guard rerun: 7 passed in 15.75s; Ruff passed. Frontend build and 288 tests passed
(one Windows symlink-fixture skip). Offline AgentCore contracts: 183 passed.
These repairs are now in the rebuilt native candidate described above. The test
session is paused (confirmed in durable state); the owned OpenCode server is stopped.
No-turn Codex preflight confirmed ChatGPT account + requested Spark availability;
the next bounded proof must preserve receipts and run against clean source.

**Evening update: product `dbc141a`, verifier `d1da140`.** Both rebuilt installers
pass integrity verification (zero blockers, 2,375 runtime files), and the native
selected-session Ask regression passes. See the evening section in
`MVP_SHIP_GATE.md` for the exact receipt/hash and retained cleanup failure.
Live OpenCode attach succeeded on a bounded retry, but the free worker hit
`Free usage exceeded`; no acceptance artifact exists. PEX ingested 40 events and
recorded one Strands/Zen inference. An additional worker prompt appeared after
the test session was aborted, so the exact owned server was stopped (runner
exit 0). Investigate provider-limit projection and cancellation/recovery
behavior next. Do not count this as a benchmark pass or mark the goal blocked.
The native PEX app remains open; only its window is authorized for automation.
Scratch helpers/receipts are in `build/native-mvp-be67a91-20260910/`.
The resumed server is now stopped; do not reuse its process/session handle.
No paid route, cloud deployment, or submission was performed.

**Native startup and two-pet checks passed on `be67a91`; live Ask found a bug.**
The unpacked runtime opened Home without Retry; startup trace reached `ready`
5.109 seconds after Python entry (not total process launch). The first direct
Cargo build lacked `tauri/custom-protocol` and showed a blank development URL;
that attempt is not a UI pass. Rebuilding with that feature fixed the bundle.
Both Pex and Von were visually transparent; bubble dismissal and pet hiding
worked independently without closing the main app. Restored Von, pet hidden.
Saved existing Zen/Muse configuration without reading/replacing its vault key.
Catalog refresh returned 70 models; this is not an inference/credential proof.

An isolated OpenCode server at loopback port 4097, pinned to
`opencode/ling-3.0-flash-fin-free`, connected through native Settings. The test
session appeared on Home. No worker prompt had been sent. Native Ask's
`what is Opencode doing?` incorrectly answered about an older stopped session,
and Inspector's no-goal heading borrowed global status text. Repairs are in
progress: optional exact session scope on Ask, selected-worker heading evidence,
and rejection of late replies after selection changes. Do not count this Ask
check as passing. New MSI/NSIS packages and current-source live supervision
remain pending; older package receipts do not validate the unpacked runtime.

The floating status-detail repair passes 30 pet snapshot/coalescing tests and
Ruff: unrelated stopped-session text cannot accompany the active status group.
Frontend production build passes. Combined Ask, workspace-authority and pet
tests pass 76/76; Ruff passes. Desktop suite passes 285 tests with one explicit
Windows symlink skip. The scoped-Ask wiring/render checks pass after fixing a
missing test-only import. The scoped API retains authorized same-goal peers of
different harnesses for context questions, while selected-session completion
cannot borrow another goal. Responses are invalidated on session/goal/revision
changes. Native synthetic goal entry and attachment also passed; worker still
discovered and all three review dispatches remained available. PEX was closed
through its own title bar for rebuilding; unrelated applications were untouched.

**Goal is active; startup packaging repair is in progress, not blocked.** The
isolated unpacked build completed, exit 0. Its `--help` took 8.0387 seconds versus
the earlier single-file 68.92s under different machine load; not a controlled
benchmark or native-ready proof. Builder, native resource launch and installer
verification now use `pex-bridge-runtime/`, with a full-tree v4 sidecar stamp and
v2 package receipt. Cursor helpers remain one-file; identity checks and 60-second
startup deadline are unchanged. Desktop suite: 283 passed, one explicit symlink
fixture skip; the additional installer-location regression also passes. Normal
sidecar preparation and exact-two-pet smoke completed, exit 0. Full runtime
manifest covers 2,375 files / 144,541,638 bytes. Rust `cargo test --locked` passed
all 19 tests, including the new fixed runtime-path check. Release desktop
compilation is now running; native startup and live flows remain pending.
The first preparation attempt failed
before building because rustc was absent from PATH; the retry pins Rust 1.97.1.

**User resumed PEX-only checks; native startup failure reproduced on `4de1db8`.**
Desktop suite with the runtime-tree checks now included in `npm test`: **283
passed, 1 explicitly skipped**, exit 0, 106.34 seconds on the loaded machine.
The skip is the Windows EPERM symbolic-link fixture. This is offline evidence,
not a native-startup, credential, chat or live-inference pass.

Both the opened app and one Retry exceeded the unchanged 60-second deadline.
Retry trace reached app imports at 11.031s and routes at 16s after Python entry,
but never Store startup. The isolated packaged `--help` path took 68.92 seconds,
exit 0, before app/db/provider initialization. CPU snapshot was 100% across 12
logical processors; these are loaded-machine timings, not proof of antivirus
or RAM failure. PEX was closed through its own Close button; unrelated apps
were untouched. [Detailed evidence](demo/evidence/PACKAGED_STARTUP_RECHECK_2026-09-10.md).

An isolated unpacked bridge build is running under `build/startup-unpacked`
(current exec session 80835). First attempt failed during keyring collection;
isolated keyring collection then passed and one retry progressed into Analysis.
Do not restart based on a polling timeout. It contains no staged pet assets and
is only a `--help` startup experiment, not a release candidate. Canonical package
unchanged. Standalone `bridge-runtime-contract.mjs` and tests prepare full-tree
integrity checking for an unpacked distribution; not integrated yet. Three tests
pass, one symlink-fixture test explicitly skips for Windows EPERM. Parent review
caught/fixed mixed-case sorting before acceptance. No new live model calls.

**Complete desktop suite: 280 passed**, 2.72 seconds, exit 0. The first run also
passed but printed a Vite WebSocket port-collision error: `hmr:false` does not
disable Vite's listener. All eight render-test server configurations now set
`ws:false` as well as middleware mode and disabled HMR. The repeated complete
suite passed without the collision error. This changes test infrastructure only;
no existing listener was stopped, native app opened or production config changed.

**AgentCore client/pipeline reverified at clean source `c07e60a`:** command
`.venv/Scripts/python.exe -m pytest tests/unit/test_agentcore_client.py tests/unit/test_agentcore_pipeline.py -q`
passed **130 tests in 13.25 seconds**, exit 0. Reviewed transport/router paths
retain exact request/session binding, locally reconstructed action authority,
independent-verifier requirements, typed uncertain delivery without automatic
second-model execution, and persisted failure receipts. These tests use fake
remote/SDK/model responses plus real local validation and Store logic; they do
not establish deployed AWS behavior, live Strands inference or native acceptance.
No new defect found in this pass; no cloud invocation/deployment or product edit.

**BYOK provider-switch UI repair:** selecting a provider with no catalog entry
now clears the prior provider's model ID instead of silently retaining it. The
existing credential-destination clearing remains unchanged. The new source-wiring
regression failed before the repair, then all 35 supervisor-draft tests passed;
TypeScript `--noEmit` passed. Seven selected backend BYOK/settings contracts
passed (53 deselected, 9.58 seconds): exact named-provider key/endpoint, write-only
restart persistence, model-only retention/endpoint change, invalid-secret errors,
and key rotation/explicit clear. Tests used fake secrets/vault/model constructors;
no actual key was read, no provider call or native UI check occurred. Packaged
`4de1db8` predates this UI repair; rebuild/native verification remain pending.

**Startup follow-up validation recovery repaired offline:** invalid follow-up
bindings now receive the same narrow logged-and-skipped `ValueError` handling as
main event heads. Rows remain intact; later healthy follow-ups continue; runtime
failures still propagate. Event-processing suite: 41 passed in 45.57 seconds;
Ruff/diff checks pass. An additional real SQLite close/reopen regression verifies
that a mismatched accepted vendor identity stays pending/unchanged while the
healthy event completes, with no invalid handoff. Focused startup/restart checks:
8 passed, 34 deselected in 11.14 seconds; Ruff passed. This is not a proven cause/fix of the earlier native
timeout. Current `4de1db8` package predates the repair; rebuild/native checks stay
paused. [Exact scope and evidence](demo/evidence/STARTUP_FOLLOWUP_RECOVERY_2026-09-10.md).

**Global-stream case isolation repaired while computer control remains paused:**
the quiet runner now filters both event and observed-session identity before
capturing STOP artifacts or invoking the case pipeline. Binding becomes active
only after the selected session/goal are stored and before the worker prompt.
Late events from another case cannot occupy the first-stop slot. Completion
suite: 71 passed in 5.48 seconds; Ruff/diff checks pass. No live calls, app launch
or package rebuild. Prior nine-pass/one-incomplete results remain unchanged.

**Quiet benchmark reporting tightened during the computer-control pause:** the
runner now audits every journal result, not only `used_llm=true` results, before
claiming completed semantic reviews. Setup/reconciliation failures with
`used_llm=false` can no longer hide behind earlier success. The quiescence gate
also requires a completed review bound to the exact captured STOP/session/goal,
not just an earlier review. 61 completion helper/CLI/wiring tests passed in
6.46 seconds, Ruff passed. Read-only inspection of the
archived ten-case run found no such hidden failures; its nine-pass/one-incomplete
conclusion is unchanged. No live calls or desktop checks were run.
[Exact defect, repair and evidence](demo/evidence/SEMANTIC_REVIEW_ACCOUNTING_2026-09-10.md).

**September 10 user scope override: exactly TWO pets, Pex and Von.** Runtime
catalog, selection API, picker and packaging allowlist now exclude the other six.
Old selection migrates to Pex while retaining nickname, scale and legacy import
metadata. No Codex-home pet scan at startup. Import endpoint rejects with 409;
generation/import controls, custom roster and hatch polling were removed from
the desktop. Independent review caught the still-callable hatch POST: it now
rejects with `hatch_disabled_for_mvp` before provider resolution or job creation.
Capability is explicitly false; authenticated historical job reads are retained.
The two picker cards have larger previews and an explicit Selected
label. Original atlas pixels and historical eight-pet review archives are preserved;
current release manifest/structural evidence/gallery bind only the two shipping pets.
279 desktop tests, TypeScript/Vite production build, and exact-two asset validation
pass. Updated bridge roundtrip suite: 16 passed (initial run caught two stale
eight-pet/tortoise expectations; those failures were not product regressions).
Final combined backend check: **113 passed in 74.51 seconds**, exit 0.
**Two-pet package `4de1db8` now built and verified, both installers exit 0.**
After disabling hatch writes, 19 API/roundtrip tests passed. Both installers are
unsigned. [Artifact hashes and exact evidence](demo/evidence/TWO_PET_PACKAGE_2026-09-10.md).
Old PEX was closed normally using its own Close button; its owned processes exited.
The new launch was stopped by physical Escape, and the user then asked to use
the computer. Do not resume computer control, open PEX or launch heavy checks
without renewed permission. Lightweight source review/docs can continue. Native
two-pet checks and the earlier startup timeout remain unverified/unresolved.

**Cold-start diagnostics:** optional fixed-phase, credential-free local trace
added for the next packaged launch. It does not fix or relax the 60-second
identity deadline. A read-only backup of the local SQLite database was profiled:
Store.connect on the isolated copy took 2.844 seconds; backup 4.547 seconds,
store module import 1.141 seconds. This does not measure frozen extraction/import
or prove the cause of the first native timeout. Private backup remains ignored
under build/startup-diagnostic-f575d45-20260910 and must not be published.

**Previous package `f575d45`: integrity passes; first native startup failed its
60-second identity deadline, one Retry succeeded.** The app is responsive and
the packaged cross-window pet feedback repair is now verified (hide via pet X
updates Settings to hidden). Keep the initial failure; do not claim cold-start
readiness or blame Windows Security without evidence. No security change or
unrelated process termination occurred. Its window was subsequently closed;
fresh-query process identity before any lifecycle action.
[Hashes and precise native chronology](demo/evidence/PACKAGE_F575D45_2026-09-10.md).
**Next priority: diagnose startup phase timing and fix the cold-start failure.**
Both build/verifier sessions ended exit 0; no test/build session remains active.
Previous staged package `06c6b73` is retained, new installers are unsigned and
not published. Rules agreement/public release approval/video remain outstanding.

**Completion runner and pet feedback source repairs:** tracked
`scripts/opencode_quiet_ten.py` now requires an idle terminal latest generation,
accepted follow-up history, stable event/action identity and final rereads.
36 helper/CLI tests pass; 129 surrounding OpenCode tests passed before the last
three CLI cases were added. Independent review found the target race closed.
Offline replay rejects the real unfinished tenth case; no new provider calls.
Native PEX transparency/bubble dismissal/hide controls were checked. Hiding from
the pet exposed stale Settings feedback; source now reconciles that message.
277 desktop tests and production UI build pass after repairing test import
isolation (the failed initial run is retained in the report).
[Changes, tests and limitations](demo/evidence/COMPLETION_FENCE_AND_PET_FEEDBACK_2026-09-10.md).
Historical next step is now completed by the package checkpoint above; the
first-launch timeout remains open even though the feedback repair is packaged.
Do not rerun live probes while the previous free-route limit remains active.

**Latest live restraint batch on `739c8d3`: nine valid quiet passes, tenth case
ineligible/failed; run exit 1, not a clean ten-case pass.** Last worker wrote a
UTF-8 BOM and hit free-route HTTP 429. PEX initially chose uncertainty NOOP,
then inspected bytes and sent an independently verified BOM-specific nudge.
The follow-up assistant was still unfinished when the quiet runner's journal-only
settlement gate sealed and stopped its own server. This is an incomplete recovery
observation, not proof the correction failed. Independent review confirmed.
No live process remains from that batch and no further provider calls should
run while its limit is active. [Full chronology, token costs and hashes](demo/evidence/QUIET_BATCH_739C8D3_2026-09-10.md).
Historical next action (now source-repaired above): offline-test and repair the quiet runner's
quiescence check to require worker idle and a terminal assistant response bound
to the latest follow-up generation. Preserve the sealed runner and failed run.

**Thirty-minute resource observation completed on package `06c6b73`:** all
180 samples retained, 1801.14 measured seconds, 342.4–347.5 MiB private memory,
31.026 CPU seconds / 1.72% of one core. Root PID/start identity unchanged.
PEX was minimized when inspected afterward; visibility was not sampled, so
this is not a foreground-animation test. Restoring PEX, Home navigation,
recorded OpenCode selection and Inspector refresh all responded. The same
process reports responsive; PEX is left open on Inspector with overlay hidden.
No model calls or worker follow-ups were started. Sampler has exited 0; no
resource/test session remains active. [Receipt, method and limits](demo/evidence/RESOURCE_OBSERVATION_2026-09-10.md).
Fresh-user install and active-workload/foreground stability remain unproven.

**Full offline regression now passes on `aba8d38`: 4,336 passed, 16 skipped,
18 deselected; exit 0, 1001.79 seconds.** Clean source at completion; XML confirms
zero failures/errors. [Reproduction, hashes, failed attempts and limits](demo/evidence/OFFLINE_REGRESSION_2026-09-10.md).
The two failed runs below are retained as historical evidence, not current
regression failures. No test process remains running from this pass. Current
package stays `06c6b73`; only docs/workflow and a test fixture changed afterward.
Fresh-user/long-stability, recording and authorized submission remain open.

**Second full regression result:** the Rust-PATH-corrected run on `10d4f51`
also exited 1: 4,335 passed, one failed, 16 skipped, 18 deselected in 970.66
seconds. The release preflight passed this time. The sole failure was
`test_snapshot_marks_directory_mutation_incomplete`; it also failed a standalone
reproduction. The fixture assumed an immediate file create changes directory
mtime. It now explicitly advances that timestamp, preserving the real file
creation and both truncation/reason assertions. No production code changed.
Workspace-file suite: 23 passed, one skipped (8.44 seconds); Ruff passes.
Independent read-only review agreed with this test-only repair and the explicit
non-atomic inventory limitation now recorded in `KNOWN_FAILURES.md`.
Original XML: `build/offline-10d4f51-rustpath.xml`, SHA-256
`349757d33801056dc22eef50cd50bbd4d5804e458b1d5eb9aef170e4f85079ee`.
The failed full run is retained; these targeted results are not a full green run.

**Current offline regression follow-through:** source `5ea699d` finished with
4,335 passed, one failed, 16 skipped and 18 deselected in 956.91 seconds (exit 1).
The sole failure was
`tests/unit/test_fleet_pets_codex.py::test_release_preflight_is_structured_and_never_claims_package_readiness`:
the shell lacked Rust on PATH, so the preflight returned the legitimate
`rust_toolchain_unavailable` blocker before fleet details. The installed
`C:/Users/JosephMayo/.cargo/bin/rustc.exe` reports `x86_64-pc-windows-msvc`.
With that directory prepended only to the command's PATH, the unchanged test
passed (1 passed, 23.14 seconds). No product code or assertion was weakened.
Original XML: `build/offline-5ea699d.xml`, SHA-256
`9b4daab2f2bdb747894c5aae2d4577a9ad4e57ccc6022d98672733a9c98a5878`.
This is a failed full run plus a successful targeted retest, not a full green run.
A fresh complete offline run on `10d4f51` has started with the explicit Rust
PATH and all live gates disabled; expected XML
`build/offline-10d4f51-rustpath.xml`. Verify its terminal result before claiming
success. The desktop suite independently passed all 276 tests on `5ea699d`.
Only workflow/docs changed during these runs, not runtime or test source.

**Recording reproducibility:** [REHEARSAL_CARD.md](demo/REHEARSAL_CARD.md)
now provides exact public goals, initial worker prompts, byte checks and stop
conditions for recovery and quiet takes. It is a manual recipe derived from
the retained native proof, not a new executed rehearsal or video.

**Local release staging:** `build/releases/pex-mvp-06c6b73` contains copies of
the verified MSI (125,607,936 bytes) and NSIS (124,336,673 bytes), `SHA256SUMS.txt`
and reviewed candidate `RELEASE_NOTES.md`. Both copied installers match the
package receipt. Exact four-file inventory and public-text checks pass; no
private receipts, credentials or logs were copied. Release notes identify the
unsigned build, source revision, supported setup and remaining limitations.
This folder is local/ignored, not a public GitHub release. Publication still
requires the pending explicit approval. Do not overwrite this versioned folder.

**Test-harness follow-up (no product binary change):** the legacy OpenCode
live-supervisor probe now requires literal `used_llm: true` and completed
inference, and closes only its own pump/pipeline/store. It is explicitly an
in-memory worker-transport probe, not a real worker or recovery result.
36 focused offline tests pass, Ruff passes, and the live probe skips with
`PEX_LIVE_SUPERVISOR=0` (no provider call). Independent review approved.
Both Codex live-proof cleanup blocks are now also scoped to their owned pump,
pipeline, transport and store. Cleanup exceptions remain visible and later
resources still close through finally blocks. 31 combined cleanup/proof-contract
tests pass; Ruff passes; all three live Codex tests skip with authorization
disabled. No new Codex process or inference was started. Existing sealed results are
not relabeled or rewritten. Current packaged app remains `06c6b73`.

**Latest: package `06c6b73`, product `97e84d4`.** Both installer integrity gates
pass, followed by native startup and visible three-step OpenCode onboarding.
PEX is open on Connections; no connection or new worker turn was submitted.
The preceding package completed a twelve-minute bounded observation, Inspector
refresh and normal close. Retained-tail CPU was 16.30% of one core, memory
336.8–340.4 MiB; not freeze clearance. [Exact current evidence and hashes](demo/evidence/MVP_ONBOARDING_2026-09-10.md).
Next required user-facing work: recording rehearsal/video and approved release
publication/submission. Fresh-user install and longer stability remain unproven;
formal research benchmark remains unclaimed. Public-release approval question
is still pending. No AWS resources or paid model calls were started.

**Onboarding follow-up:** OpenCode setup now explains `serve` versus `attach`
and creating/resuming the vendor session before selecting it in PEX. Connecting
an empty server does not create a worker. README and recording instructions
match the app. 276 desktop tests and production UI build pass; independent
read-only review approved. This copy-only follow-up is now bundled in `06c6b73`.
No adapter behavior, credentials or process lifecycle changed.

**Latest package: `e56a077` (product `320249b`).** Production build and MSI/NSIS
extraction/content/eight-pet checks exited 0. Both installers are unsigned.
Native startup and selecting the recorded OpenCode workflow succeeded: Home
shows the actual worker message, Von and the dismiss control; overlay remains
hidden. No new inference was invoked by this check. The prompt update is bundled.
[Hashes and boundaries](demo/evidence/SUPERVISOR_BUDGET_RETEST_2026-09-10.md#packaged-follow-through).
Public GitHub source is MIT; authenticated Devpost shows registered, not submitted.
No current test-CI run was established. Public installer release awaits the
pending user's approval; do not infer publication permission from this file.

**Source update `320249b`:** main supervisor prompt now explicitly reserves a
decision call within the unchanged three-call budget. 71 tests and independent
review pass. The previously failed identifiers case and one control both pass a
new source-level free-Zen/Strands retest: all decisions completed, zero followups,
exact artifacts before review. This is guidance, not enforced reservation, and
the control still used two reviews. Prior failures remain preserved.
[Exact results and native idle sample](demo/evidence/SUPERVISOR_BUDGET_RETEST_2026-09-10.md).
Native fcb624d also passed a three-minute no-input observation with 335–338 MiB
private memory and 2.73% of one core; navigation worked afterward. Not freeze
clearance. PEX was then closed normally; the prompt update was subsequently
bundled and reopened as recorded above.

**Latest: product `fcb624d`, clean package checkout `d50e420` (docs-only).** Both
installers pass, native progress text is repaired, and pause/resume is verified
with a read-only persisted-state check. Fresh packaged bridge profile passes
18 reads, authentication rejection and 11.8-second startup. Two-minute native
interaction observation completed without a hang; not long-soak freeze clearance.
See [the full receipt and exact limits](demo/evidence/MVP_NATIVE_FCB624D_2026-09-10.md).
Normal PEX close and second native reopen both succeeded. PEX is left open on
the recorded OpenCode workflow; Von selection and hidden-overlay preference persist.
No model calls were added. 84 focused and 117 wider OpenCode tests pass.
The first package check stopped only for two uncommitted documentation files;
after committing them, the clean verification passed. Do not repeat that failed
attempt as a package-content failure or claim full-source regression after fcb624d.

Next: keep the app available for filming, consolidate
judge-facing materials and finish the demo/submission with appropriate user
approval. Do not silently turn optional AgentCore deployment into a shipping gate.

**10 September, current checkpoint:** package `1a5eb92` passed both installer
content/eight-pet checks and native reopening. Receipt
`build/pex-package-receipt-1a5eb92.json`, SHA-256
`74f4328e8aab4a7d397a8dbc977dee85b5bd5ee71008ec182a881dba21cbd3a7`.
Native Inspector displays newer unverified STOP as completion uncertain,
not the obsolete acceptance gap. Pet is hidden. Re-enumerate windows before input.

Full offline suite on product/test source `1a5eb92`: **4,313 passed, 16 skipped,
16 deselected**, exit 0, 1150.65 seconds. XML `build/offline-1a5eb92.xml`, SHA-256
`3b52f989edb76091077028c939835cdc3cd791eed7d7970b11f3de44cdf6f35f`.
Only documentation/diagram changed during that run. Separate focused offline
Strands/AgentCore contracts: 235 passed; no AWS deployment or paid inference.

A later display-only repair hides OpenCode payloads that fall back to their
transport event kind, preserving actual text and the immutable journal. Native
`message.part.updated` exposed this remaining fallback. The updated snapshot
suite passes 22 tests and Ruff; combined snapshot, OpenCode lineage and delta
tests pass 84. Independent review caught literal event-name ambiguity, so the
adapter now tags synthetic fallback versus genuine text explicitly. Historical
journal rows lack the marker and retain a display-only equality heuristic;
their original data is not migrated or altered. This repair still needs packaging and
native verification. No extra polling or model calls were added.

Next: final package/native setup, pause/reopen and bounded stability checks;
retain honest behavior evidence; finish recording and public submission materials.
Follow `MVP_SHIP_GATE.md`, not the historical expansion queue. Optional AWS
deployment and formal four-arm research scoring are not contest prerequisites.
No formal score or freeze clearance is claimed.

### Historical checkpoint below — superseded where it conflicts

Package `1f3a0ea` now passes both installer extraction/content/eight-pet gates,
exit 0. Receipt `build/pex-package-receipt-1f3a0ea.json`, SHA-256
`bcf4bc57e0e131526864fb8fd06550ee2d4a98bd49350ddbcc4c14d89b9ec1ef`.
PEX was closed normally through its own window, then reopened successfully.
Current native window is 166987032 (reselect before input), pet hidden,
OpenCode recovery selected on Home. No unrelated app was controlled.

Follow-up source repairs, NOT in that package: skip bare assistant/user role
fallbacks in progress text, and let newer bound unverified STOP evidence
supersede old supported/unsatisfied goal verdicts as uncertain. Fingerprint
scoring keeps its previous evidence contract. The native goal panel had retained
an obsolete acceptance gap because its newer no_claims STOP was ignored; this
is not proof that the saved exact recovery artifacts disappeared. Two failing
regressions reproduced stale positive/negative verdicts; repair plus recovery,
snapshot and fingerprint suites pass 45 tests. An older stale-evidence count
now correctly includes both STOP records (2 rather than 1). Ruff passes.
Independent design review approved projection-only handling. Next: package
these repairs and verify native goal/progress display, then remaining behavior,
review-efficiency, Codex, benchmark and AgentCore gates. No model calls were
added for these repairs.

Live restraint audit: eight original small-task cases plus one supplemental
case have completed Strands NOOP decisions and zero followups. The original
batch stopped on an ambiguous CRLF/LF criterion; supplemental case 9 has a
failed structured decision, NOT a semantic pass despite its raw runner flag.
No ten-case batch PASS or comparative score. All owned fixture servers exited.
[Audited results, usage, hashes and resource sample](demo/evidence/QUIET_RESTRAINT_2026-09-10.md).
The 120-second native sample used 393.7–414.0 MiB private memory and about
19.58% of one CPU core; it does not clear the earlier freeze. PEX remains open
on package d55e899, pet hidden. Source-only progress-text repair ignores late
OpenCode bookkeeping in the visible message. Failed/timed-out Strands reviews
now carry their status/reason to the UI and say Review incomplete, not Stayed
quiet. 20 snapshot tests, 275 desktop tests, production UI build and Ruff pass;
independent review found no defect in the bookkeeping repair. These changes
are not yet in the running binary. The added status regression initially lacked
last_activity and was excluded from the snapshot; setting the fixture's current
activity made its scope match the real case. No production filter was relaxed.

Next priorities: investigate failed structured decisions/review overhead,
finish current behavior cases, then remaining native Codex, isolation,
AgentCore no-billing deployment and submission gates. Do not rerun sealed roots
or mutate failed receipts. The ignored quiet helper's gate now requires
completed inference, not merely an attempted model call.

**Native recovery now passed on verified package `d55e899`.** UI-connected
OpenCode worker received a specific Strands correction, created the missing
exact file, and PEX recorded `goal_evidence_supported` / `helped: true`, followed
by NOOP. All 216 events settled; exactly two reviews, no old-idle duplicate in
this run. Inspector showed Stopped and the actual rationale. Fixture exited 0,
owned server closed; temporary data cleanup remains incomplete. PEX stays open,
pet hidden. [Sealed evidence and limits](demo/evidence/NATIVE_D55E899_2026-09-10.md).

Next: required additional behavior cases and longer
stability, then native existing-Codex and fair benchmark/AgentCore evidence.
Do not rerun the already sealed fixture or overwrite its audit. The earlier
checkpoint below records the quiet case and intervening repair work.

Package `490b82b` passed MSI/NSIS content and eight-pet inventory verification.
Its **native desktop-owned OpenCode + saved free Zen/Muse + Strands quiet case
passed**: exact two-file acceptance, one semantic NOOP, all 336 events settled
(154 complete, 182 record-only), no manual correction or paid fallback. Native
pet transparency, bubble dismissal and Hide Pet passed; hidden preference was
restored. This is one behavioral case, not a comparative benchmark or GO.

Follow-up source fixes preserve stopped status across OpenCode bookkeeping and
show the actual action rationale in Inspector instead of an internal diagnosis
code. 114 focused backend tests passed; Ruff passed after formatting the new
test. All 274 desktop tests and production UI build passed. These follow-up
fixes are not yet in the running `490b82b` binary.

[Current native evidence and limits](demo/evidence/NATIVE_490B82B_2026-09-10.md).
Next: package the verified status/rationale and prompt-boundary repairs, then
run native recovery. The buffered-old-idle follow-up now passes 81 focused
tests (two behavioral failures reproduced before repair). A pre-POST,
transport-bound whole-batch cutoff prevents known-old idle from triggering a
new review; ambiguous mixed batches retain STOP. Native confirmation remains
required. Independent read-only review found no defect in the patch.
The quiet fixture server exited; its temporary data directory remains after
incomplete profile cleanup. Preserve receipts; never use recursive PID cleanup.

The paragraphs below retain the earlier `2174ad0` checkpoint and are historical.

Package `2174ad0` passed both installer content/inventory gates. Full offline
suite: **4295 passed, 16 skipped, 16 deselected**, exit 0. Two real, bounded
Codex Spark + saved free Zen/Muse + local Strands tests passed: incomplete-stop
same-worker correction with `goal_evidence_supported` / `helped: true`, and
correct-completion semantic NOOP. These are source-level App Server proofs,
not native existing-thread attachment or a scored comparative benchmark.

Packaged OpenCode follow-up is NOT a quiet pass: the worker used the parent
repository instead of the attached workspace. PEX detected the gap and nudged,
but the worker repeated the wrong-directory behavior. A delta-event backlog and
duplicate idle review were exposed. Follow-up source routes plain OpenCode token
deltas into immutable record-only storage, retaining full semantic processing
for actual message/tool/error/stop events. 111 combined regression tests pass.
The source change still needs rebuilt-native validation; duplicate idle remains
open. [Exact evidence, commands, hashes and limits](demo/evidence/CODEX_AND_PACKAGE_2174AD0_2026-09-10.md).

Next: finish scoped native evidence collection, rebuild the delta-path repair,
and rerun a fixture with its own Git root and explicit target path. Preserve
all failed receipts. Continue native quiet/recovery and resource checks before
claiming readiness. No paid fallback or AWS deployment is authorized without
verified no-billing coverage. PEX-only computer use is allowed; unrelated apps
and the unsafe recursive-PID launcher remain out of scope.

## Authority and product scope

Newest checkpoint supersedes historical latest/hold labels below: native package
`2dc5d81` verified both installers. PEX-only UI connected a fresh OpenCode worker,
attached its exact goal, showed correct Discovered status and compact Inspector.
The native Strands supervisor sent a specific independently verified correction
to that same worker; both exact files appeared, then a semantic NOOP inspected
them. All 306 events drained. This is NOT full submission/benchmark acceptance:
processing was slow, the first proposal failed evidence refs, and the recorded
intervention outcome remained unset. No paid fallback or manual correction.
Full details and hashes: [native evidence](demo/evidence/NATIVE_AND_RECOVERY_2026-09-10.md).

Follow-up source repairs address the live false exact-content/newline verdict,
per-event tasklist overhead (focus hint only), and lineage destroyed on an exact
ingestion retry. 248 focused tests pass. Broad prior run: 4272 passed, two failures
(stale Muse chat-only fixture and missing Rust PATH); both rerun checks pass with
the fixture corrected and toolchain available. Subsequent source still needs a
clean full-suite run and packaging/native rerun. Owned server/profile cleaned,
PEX closed normally, no unrelated apps touched. Keep quiet-case/Codex/outcome
tracking and benchmark isolation gates open; do not repeat older failure claims
as though this native progress did not occur.

Latest continuation: the user renewed PEX-only computer-use access after an
accidental physical Escape. Native package `66b5e52` passed MSI/NSIS content and
inventory verification (`build/pex-package-receipt-66b5e52.json`). Cold startup
loaded the saved Zen supervisor without manual Save; Von's hidden preference
persisted. The new OpenCode connection form connected a dedicated server, and
the native goal editor saved/attached exact criteria to the intended session.

The native recovery did NOT pass: after the worker completed phase one, the
desktop journal stayed at one complete and one accepted event, with no semantic
review. A manual abort was issued while investigating a transient provider retry;
retain that intervention, do not claim this was a clean hands-off run. Both PEX
and the dedicated server were closed normally/scoped; other apps were untouched.
Details: [native evidence](demo/evidence/NATIVE_AND_RECOVERY_2026-09-10.md).

Current un-packaged repairs: OpenCode retries retain the exact accepted event and
retain successful batch-prefix progress instead of replaying a completed batch
with mutated lineage. Discovery no longer invents activity or overwrites the
event-owned status/capabilities. Inspector uses a compact session selector, and
Ask PEX suggestions prioritize the selected worker. Two regressions failed before
repair. The real SQLite acceptance/retry regression passes too; the initial native
exception is not yet established, so these fixes still require a native rerun.
154 selected backend tests passed including the durable-journal regression.
Desktop: 273 tests and production build pass.

Latest source-only repair (10 September): AgentCore workspace compaction no
longer labels absent/empty evidence, invalid observation flags, or an explicit
read error as a successful observation. Five new cases failed before repair;
all nine observation cases are covered, including repeated compaction.
`python -m pytest tests/unit/test_agentcore_client.py tests/unit/test_agentcore_runtime.py -q`
passed 158 tests in 17.78s; Ruff passed for both edited files. No AWS/native
process was launched. This change is not in the b9702fd installer yet.
Follow-up verification exercises all nine cases through the serialized cloud
request, reconstructed remote request, actual `inspect_workspace` tool and its
EvidenceObservationCollector. Model-visible observation status and exact audited
output/request digest agree; 9 passed, 112 deselected in 5.30s. No model or AWS
call occurred. This is evidence-path verification, not live behavioral proof.
The recovery spec prioritizes the actual same-worker supervision loop before
more Docker/infrastructure work; the existing benchmark execution gate remains
intact. The former native hold has been lifted for scoped PEX checks.

Latest user goal supersedes the broader audit objective: implement and verify
UI/UX, Zen BYOK, OpenCode/Codex, Strands supervision, AgentCore implementation,
agent benchmarking and supervision behavior; then provide live recording steps.
Aim for a strong hackathon submission without guaranteeing a judging outcome.
Do not treat selected offline tests as completion of this acceptance chain.

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

10 September update: user explicitly approved resuming PEX-only live checks
("yes, its 3am so u have full access now"). The prior native hold below is
historical. Keep control scoped to PEX and dedicated test workers; do not
restart/close unrelated apps, use the quarantined script, or infer paid AWS
authority. Native b9702fd launched successfully; saved Zen activation timed out,
then visible Save recovered using the existing vault credential. A three-review
cap was saved. Von's overlay is visibly transparent and its bubble dismissed.
Source repair separates background startup's 60-second deadline from Save's
10-second deadline; 60 supervisor-settings tests pass (108.78s), Ruff passes.
Cold-start fix still needs rebuilt-native verification; no full live loop claim.

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

Included in package b9702fd: AgentCore request compaction preserves validated
complete artifact row counts instead of dropping them. Partial/invalid counts
remain unknown, and contents stay local. Nine regressions plus two actual
JSONL-reader-to-envelope cases cover this. The combined AgentCore/Strands gate
passed 221 tests before the two final additions; full AgentCore client suite then
passed 112 tests. Follow-through into audited model-tool output is also verified
offline; combined client/runtime/pipeline tests passed 158 cases. Live cloud
behavior remains unproven.

Last verified Windows package source:
`b9702fd70113462d82df302b9ac01ebfe46b4281`. Includes HTTP/Codex memory-retention,
Zen Muse routing and AgentCore artifact-count fixes. The default paths now contain
this build; historical 166a656/d1b259b hashes do not describe the current files.
Both MSI/NSIS passed extracted executable/hash and exact pet-inventory checks.

- Receipt: `build/pex-package-receipt-b9702fd.json`.
- [Durable hashes, warnings, commands and limitations](demo/evidence/PACKAGE_B9702FD_2026-09-10.md).
- Desktop: `apps/desktop/src-tauri/target/release/pex-desktop.exe`.
- MSI: `apps/desktop/src-tauri/target/release/bundle/msi/PEX_0.1.0_x64_en-US.msi`.
- NSIS: `apps/desktop/src-tauri/target/release/bundle/nsis/PEX_0.1.0_x64-setup.exe`.

Verification did not install/open desktop UI; the frozen bridge ran only its
inventory-only `--verify-bundle` path. Receipt `release_ready:true` is a package
gate, not submission readiness.

Historical post-166a656 notes below: all described fixes are now in package
2f5038e; their original source-only statements apply to the earlier checkpoint.

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
Integrated verification: four new tests feed the production HTTP retention buffer
through the actual OpenCode pump into delivery-lineage matching. Intact exact-parent
responses match; count eviction, byte eviction and oversize discard do not. The full
OpenCode lineage/pump selection passes 57 tests (4.77 seconds), without live I/O.
Codex follow-up: full offline pump suite passes 34 tests (26.09 seconds), including
1,400-notification reclamation and same-thread recovery. Subsequent capture repair
caps `raw_capture` at 8 MiB serialized bytes plus the record limit, marks the retained
prefix incomplete on saturation, and leaves live notifications flowing. The fallback
benchmark writer requires literal complete-capture evidence. Four transport cases,
six writer cases and the full 34-test pump suite pass (last pump run 24.00 seconds);
Ruff passes. This capture fix is not yet packaged. The live notification queue still
has its prior count bound; no native memory result is established by these tests.

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

Current live supervisor-only proof at `4329978`: saved OS-vault Zen Contributor
Free configuration passed the real Strands inference contract, with exact
provider/model/Responses assertions and a typed decision. Synthetic session only,
no worker or UI attached; not behavioral/benchmark or AgentCore proof.
[Receipt and limitations](demo/evidence/LIVE_ZEN_SUPERVISOR_4329978_2026-09-10.md).

Latest combined checkpoint: source `d53de4c`, 423 selected backend tests and all
268 desktop tests passed on 10 September (111.34s and 6.842s). No source changes
during verification. [Exact commands and scope](demo/evidence/OFFLINE_REGRESSION_D53DE4C_2026-09-10.md).
This is not the full Python suite or live acceptance.

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
