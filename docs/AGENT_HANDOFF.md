# PEX agent handoff

## Latest low-quota audit — 6 September, after Q07

Semantic-gate follow-up inspected the existing force option across pipeline,
local/AgentCore routing and remote runtime. It is not a safe one-line bypass:
the pipeline semantic flag also affects ambiguous-dispatch accounting, and each
backend has its own eligibility call. See `TRAJECTORY_SEMANTIC_REVIEW.md` for the
verified call path, budget/authority invariants and exact required mocked/live
gates. No global force setting or runtime was changed. The protected-file
permission question is still pending; this P0 is explicitly unfinished.

Background identity follow-up: PID-less commands longer than the 200-character
display preview could never match their terminal event. A SHA-256 fingerprint
now preserves full-command identity without enlarging displayed command text;
different suffixes cannot alias. PID parsing now rejects booleans, nonpositive
values, non-ASCII/nondecimal strings, excessive-length values and identities
outside a conservative positive signed-32-bit range before native lookup.
Unsupported PIDs stay unknown rather than being coerced/wrapped. Of 13 added
cases, 10 failed before repair; final background unit/API selection **22 passed,
15 deselected in 16.39s**, Ruff clean. Live process birth identity and semantic
abandonment diagnosis remain open; this is not a live-agent benchmark.

Background-job audit: root fully read `background.py` and its small unit suite.
The tracker only settled the last launch, leaving older jobs falsely active when
they exited out of order; `running=false` without identity could also clear an
unrelated job. Three new regressions failed before repair. Settlement now finds
the most recent matching launch, requires exact observed PID for PID-bound jobs,
and a matching command for PID-less jobs. **9 targeted unit/API tests passed,
15 deselected in 15.95s**; scoped Ruff clean. This does not prove process birth
identity/PID-reuse protection, remote process visibility or abandonment intent.
Existing command truncation and lexical launch detection remain audit limitations.
No user process was stopped; unit tests own their short-lived subprocesses.

Post-trajectory integration check on `f650260`: complete
`tests/e2e/test_recovery_stop_loop.py` passed **17 tests in 94.42s**, with
PytestUnhandledThreadExceptionWarning treated as an error. Scope includes
completion/continuation, goal attribution, local no-nag fixtures, missing data,
cleanup escalation, background jobs, compaction/overlay and quiet trajectory
candidates. These use synthetic adapters/local ASGI, with model inference
disabled by the test fixture; they do not replace the unfinished ten live quiet
cases or prove semantic trajectory review. No new inference or desktop input.
Audit coverage now records the full drift-module read and remaining P0 gate.

Adjacent broad-refactor repair: deterministic planning no longer equates four
unlisted filenames or refactor narration with proof of goal irrelevance. It
retains `broad_work_candidate` evidence as NOOP rather than issuing the old
generic correction and setting the session/pet to drifting. **13 targeted
drift/planner/HTTP checks passed, 54 deselected, in 17.38s**, including unchanged
worker inbox and no invented drifting count. This removes a false-certainty
shortcut; semantic trajectory diagnosis is still NOT complete and remains a
submission requirement. Pending protected-loop question has not been answered.

Follow-on overlap provenance: candidates now retain source/current event IDs
and an explicit `observed_overlap_candidate` basis. Reject mismatched sibling
identity, self-session tuples, non-action/narration events, timestamps without
timezone evidence and events later than the current observation. **50
drift/planner tests passed in 7.13s**. These remain signals, not proof that work
was duplicated or complete. Asked the user asynchronously whether a narrowly
scoped semantic-gate edit to protected `loop.py` is permitted while preserving
its existing changes; no answer was received during this pass. Do not interpret
the request as permission. No new model calls or subagents were used.

Trajectory audit found an unjustified automatic sibling-work correction:
`src/parser.py` and `lib/parser.py` matched by basename, and even genuine path
overlap was treated as proof that a sibling had completed the same work. Root
fully read `drift.py` and its unit tests, plus bounded planner/pipeline/semantic
gate paths. Overlap now preserves directory and case identity (separator
normalization only), and deterministic planning retains candidate evidence as
NOOP rather than telling the worker to reuse an unverified result. This follows
recovery spec section 15: detection is not intervention. Drift/planner **45
tests passed**; synthetic HTTP two-worker no-message regression **1 passed in
12.49s**; scoped Ruff passed. The initial API expectation of a NOOP record was
corrected because the pipeline can suppress nonmaterial NOOP records; worker
inbox remains empty. This is not a new live model or cross-harness proof.
Important remaining gap: `needs_semantic_inference` normally invokes semantic
inspection on STOP only unless forced; genuine trajectory review is not finished.
The broad-refactor lexical rule also still needs evidence/semantic review.
Protected `loop.py` hash unchanged; it was read but not edited or staged.

Native bridge bounded audit: existing Rust suite passed 15 tests. Added an actual
ephemeral loopback identity exchange covering fragmented authenticated response
delivery with the server kept open until the client returns. It uses only a test
token, checks that the token is absent from the request, and never binds port
7420 or touches a live PEX bridge. `cargo test --locked --offline`: **16 passed**;
Rust formatting applied. Current implementation passes this case; no production
identity policy was weakened or rewritten. This narrows a regression gap, but
does not reproduce or diagnose the user's old installed bridge failure.

Startup-recovery copy audit: non-retryable accepted error states hid the Retry
button but several code-specific guidance strings (and copied diagnostics) still
instructed users to choose Retry. A regression failed on `bridge_identity_lost`.
Copy now preserves the specific failure diagnosis but supplies close/reopen and
repair guidance when Retry is unavailable; unknown-process takeover is never
suggested. Startup recovery tests **10 passed**, TypeScript check passed. This
is a recovery-message fix, not evidence that the native startup failures from
the screenshots have been reproduced or resolved on the current installed app.

Integration check on source `4dd121f`: full desktop `npm test` **193 passed**;
`npm run build` succeeded (TypeScript + Vite, 63 modules). No PEX window was
launched/focused and no native installer was produced. Audit coverage now records
the recent evidence-reader and pet-interaction repairs with their red/green
regressions and explicit limits; do not equate source-contract/render tests with
native interaction verification. Remaining full specification gates stay open.

Pet interaction audit: existing overlay hide and status-dismiss controls remain
present. Root found horizontal-only drag detection and unconditional pointer-up
activation: vertical movement could open the inspector rather than start drag,
and secondary/middle releases could activate without a primary pointer-down.
`PetStage.tsx` now uses two-axis distance and requires a tracked primary gesture
without drag before activation. Pure interaction helpers have boundary, vertical,
diagonal, cancellation/no-start and non-primary-button tests. Focused command
`node --test --test-name-pattern="pet" src/viewModel.test.ts` passed **9 tests**;
`npx tsc --noEmit` passed. Source diff reviewed. This is not a native mouse test:
shared-PC input remains paused, and drag/close/Escape must still be checked in
the latest packaged application before submission readiness is claimed.

Next local audit repaired `workspace.artifact_row_count`: the old stat-size
check preceded an unbounded JSON read / JSONL iteration, so concurrent growth
could bypass the 4 MB budget. Both formats now read at most the clamped limit
plus one overflow byte and reject oversized payloads before parsing. Two stale
stat regressions failed before repair; exact-limit JSON/JSONL counts remain
valid. Focused workspace/verify/evidence-tools gate: **97 passed, 1 skipped in
16.69s**. This bounds input reads; it does not provide atomic snapshots or prove
that concurrently rewritten same-size artifacts are stable. No runtime restart,
new model call, or native interaction occurred.

Follow-on local artifact audit: supplied artifact snapshots could treat boolean
row counts as integers (`true` supported one row; `false` contradicted it), and
negative counts produced false failure verdicts. `verify.py` now accepts only
nonnegative strict integers as complete row counts; malformed counts stay
uncertain and select artifact evidence gathering. Eight regressions cover six
invalid values plus valid zero/one counts; three failed before repair. Combined
verify/evidence-tools/workspace-inspection gate: **93 passed, 1 skipped in
16.01s**, scoped Ruff and diff checks clean. This does not claim malformed counts
occurred in the live bridge or that the packaged build includes the repair.

User reports quota burning fast: no new subagents or live model benches for now.
Q08 preparation has a retained completed warmup receipt; actual work has NOT
started. Do not repeat prepare. Q01-Q07 outcomes below remain unchanged.
Background local audit found that pathless FILE_EDIT events invalidated the new
pytest observation flag but not verdict/probe selection: stale passing results
could support claims, and stale failures could cause false corrections.
`verify.py` now retains a descriptive unknown-path edit marker (never file I/O),
so all existing stale-evidence gates request fresh evidence instead. Four new
regressions (pass/fail, with/without a claim) failed before repair; focused
`test_verify.py` + `test_evidence_tools.py`: 70 passed in 11.18s after repair.
Protected `loop.py` SHA256 remains
`392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`.
This is local regression evidence, not a new live or packaged-build pass.
Running clean d67 bridge has not been restarted or upgraded. Full goal remains
ACTIVE / submission NO-GO; resume remaining quiet cases only with budget in mind.

## Current authority — 6 September continuation, target 9 September

Start with [CHECKPOINT_2026_09_06.md](CHECKPOINT_2026_09_06.md). It records the newer
source, exact retained package, clean-checkout failure diagnosis, native pet-close proof,
settings repairs, native-control boundaries, protected file, owners and next
actions. Earlier native checks were stopped with Escape. The current shared-PC
boundary keeps native input paused: ask before the next foreground PEX check. The
user is actively using this PC with other agents; keep background work separate
from shared mouse, keyboard and foreground focus, even when targeting only PEX.
Fresh shared-worker recovery and separate quiet proofs passed on clean `4543a58`;
the false-test-claim recovery now passed independent review on clean `ee459f8`.
Full clean `84d9bd3` testing completed with 3,691 passes, 29 skips and one cleanup
warning. The new full strict run on fixture repair `f529644` passed: 3,718 passed,
27 skipped, zero failures/errors or thread warnings. Run-08 exposed a genuine
verification-probe binding failure; its exact original decision and terminal
receipts are retained. Repair `5ff58f6` passed 231 clean affected tests and an
independent live run-09 audit: gather evidence, same-worker verification request,
actual four-test pass, then NOOP. Consult the checkpoint/review for exact receipts.
Next: ten varied quiet cases and deeper required flows, not another run of the
already completed failure fixture.
Final installed-build gates remain open.
All `current` or `final` headings below are historical wherever they conflict.
The goal remains active and the full three-spec submission scope remains incomplete.
Latest user cost instruction: subagents use **GPT-5.6 Terra, medium reasoning**;
the user subsequently asked to reduce delegation because quota is burning fast.
Keep work local by default; the broad quiet-fixture subagent audit was interrupted.
Ten public quiet-case workspaces now exist under
`C:/Users/JosephMayo/pex-live-demo/workspace/quiet-20260906-Q01` through `Q10`.
Q01 has now run once and is retained as inconclusive; Q02-Q10 have not started. Root reviewed public
tasks/tests/goal contracts and strengthened Q05 suffix-collision coverage, Q06
strict date formatting, and Q08 SPDX/metadata validation before any live attempt.
Fresh baseline: Q01 4 failures; Q02 4; Q03 3 failures/1 pass; Q04 4; Q05 5;
Q06 5; Q07 5; Q08 7; Q09 5; Q10 5. These are intentional unfinished worker
fixtures, not PEX failures or quiet-success evidence. Private runner scripts are
`build/quiet_owner_operator.py` and `build/quiet_case.py`; their recovery guards
received root static review: the worker identity is now persisted before warm-up,
and started turn identities before waiting. Root independently reran CLI help and
Ruff successfully. This is static runner validation, not a live quiet-suite result.
Q01 live worker `01a077be-3193-7313-9698-46df7153189f`, work turn
`01a077bf-2bb7-7ff0-b757-3ba8f888fe43`, completed the public implementation/artifact.
However, PEX disconnected with `CodexSubscriptionError` at observed sequence 29,
ingested 28, before any intervention or typed pytest result was recorded. Do not
count absent messages as a successful NOOP. Diagnose the exact transport/journal
failure before launching Q02; do not rerun Q01 to replace this failure.
The revoke helper refused the already disconnected target; explicit detach then
succeeded, with worker_stopped=false. Terminal correction status is enabled=false,
effective_enabled=false, connected=false, grant=null. Immutable hashes matched;
root external pytest after detach passed 4 tests in 0.02s (not PEX-observed proof).
Receipt: clean `pex-live-5ff58f6/build/quiet-live-20260906/Q01/client/`
`capture-20260906T172539532234Z.json`, SHA256
`E3BA8D5686D64CF90AEC7D87F3AEF6EF5533A841EF92E99C4DE7587F50CE76E1`.
Progress: 0 quiet successes, 0 proven false positives, 1 inconclusive, 9 pending
out of the ten declared cases. Dedicated bridge 7434 remains alive and detached.
Root diagnosed Q01 from read-only receive-journal frames: chunk 106 contains
foreign run-09 `thread/status/changed` (notLoaded) and `thread/closed` broadcasts,
both with the vendor envelope field `emittedAtMs`. The prior minimal-envelope
allowlist rejected that timestamp and disconnected the selected Q01 observer.
The narrow transport repair accepts only integer timestamps in [0, 2**53-1] on
the already allowed foreign lifecycle shapes; no arbitrary envelope extras,
server requests, selected-thread closures, or malformed identities are ignored.
Root gate: 160 tests passed in 5.61s across shared transport, subscription and
adapter tests, with thread warnings as errors; scoped Ruff clean. This is not a
new live pass. Existing bridge/source remains clean 5ff58f6 without this repair;
use a fresh clean repaired-source bridge/profile for Q02 and retain Q01 unchanged.
Private read-only diagnosis helper: `build/audit_quiet_q01.py`; it parses only the
retained inspection's journal frames and prints bounded envelope metadata, not
raw prompts, message text, credentials, or execution payloads.
Fresh clean checkout `C:/Users/JosephMayo/Projects/pex-live-6f929ea` now exists at
`6f929ea50ce7d909269ac26f260001ddd21f587b`; locked uv sync installed 113 packages.
Root repeated the same strict three-file gate there: 160 passed in 6.62s,
tracked checkout clean. Read-only offline classification of both exact retained
chunk-106 lifecycle envelopes proved old 5ff58f6 filter=false and repaired
filter=true. No frame was replayed into a live worker, bridge, or supervisor.
No bridge has been started from this new checkout yet. Next action remains a
fresh repaired-source bridge/profile and Q02, preserving the Q01 failure receipt.
Q02 has now run once on clean 6f929ea: dedicated bridge 7435, PID 18952,
session 42593, private profile `pex-live-6f929ea/build/quiet-home-6f`.
Ignored runners are `build/run_quiet_bridge_6f.py`, `quiet_owner_6f.py`, and
`quiet_case_6f.py`. New origin is independently confirmed in that profile; later
cases reuse its exact receipt read-only. Worker `01a077cb-0b44-7a10-8820-a29437a8b8e7`
completed initial turn `01a077cc-3748-73c1-a430-9af3152fb62c` and a PEX-induced turn
`01a077cd-74d7-77b3-8a81-b9e6916ffa4f`; all three turns including warmup are idle/completed.
Observation survived through the actual full-suite result. That result was exit 1:
3 passed and 1 tmp_path setup PermissionError on the shared system pytest temp
directory, plus cache permission warnings. Do not fix shared temp directories or
their ACLs; this PC is shared. Future unstarted fixtures need isolated sandbox-
writable test temp/cache paths, with changes documented before the attempt.
Two retained interventions: deterministic ASK_HUMAN
`intervention_c0403a5cd1f4ba75ced9682cc6074d96e2eef559` spuriously classified the
task's repeated no-install/no-network restriction as a contradiction. Subsequent
source inspection corrected the initial diagnosis: production pipeline.py around
2446 appends standing-correction policy to request.notes, NOT the persisted goal.
Planner parsing incorrectly presented that appended paragraph as constraint text.
This was not an actual approval request.
Real Strands/verifier SEND_NUDGE `intervention_05d9809c22e4d31617b4f73dd1e6741728e956bc`
then requested repairing the test environment; aggregate model calls 4. It is not
evidence of pointless nagging on a correctly completed task because pytest failed.
Q02 is inconclusive, not quiet success; Q03-Q10 pending. Revoke and detach both
succeeded. Retain terminal client capture `capture-20260906T173942247149Z.json`
under clean checkout `build/quiet-live-20260906/Q02/client`, SHA256
`5599B8AEAE662D0EAB7472824FF2E889E104C65FB575C6B4B6A02B641EF75522`.
Next: fix/audit the false prompt contradiction and prepare sandbox-local test
paths for unstarted cases before Q03. No UI/native input or subagents were used.
Root repaired the bounded negative-list matcher so a continued restriction such
as "Do not modify tests, fixtures, install dependencies, or use the network"
does not create a conflict. Contrast words and sentence/semicolon boundaries do
not hide later affirmative actions; added regressions cover both cases. Planner
questions now stop constraint parsing at the first blank-line paragraph, keeping
route policy out of quoted human intent. This is narrow lexical triage repair,
not proof of general semantic intent understanding. Focused unit/planner/contract
gate: 79 passed in 21.27s. No Q03 attempt or fresh live claim yet; sandbox-local
fixture temp/cache preparation remains open. Protected supervisor loop unchanged.
Pre-attempt fixture update completed for Q03-Q10 only: each now has immutable
`pytest.ini` with `-p no:cacheprovider --basetemp=.pex-test-tmp`; its case manifest
includes that config and TASK documents pytest-only disposable local scratch.
The requested full-suite command and public acceptance tests are unchanged.
Root collect-only validation passed for all eight: 4,4,5,5,5,7,5,5 tests respectively.
No `.pex-test-tmp` directory exists yet, so the sandboxed worker, not the root
operator, will create its test scratch. Q01/Q02 and shared system temp paths/ACLs
were untouched. This is collection/config validation, not proof the sandbox can
execute the suite. Next: clean bb32b0f-source runtime and Q03 live verification;
current dedicated 7435 bridge still runs 6f929ea and must not be mistaken for the
new intent repair. All earlier live failure receipts remain authoritative.
Q03 live completed on fresh clean `pex-live-bb32b0f` at exact
`bb32b0f886abd93d98e48cec68ce8426168c9b88` (locked sync113; clean focused gate
79 passed in 34.92s). Background bridge7436/PID4420/session94277, private home
`build/quiet-home-bb`; ignored scripts `run_quiet_bridge_bb.py`,
`quiet_owner_bb.py`, `quiet_case_bb.py`. Q03 origin confirmed once; subsequent
cases reuse exact `build/quiet-live-20260906/origin.json` read-only.
Worker `01a077d7-3fb9-7ce1-a772-87a98dc5c400`, single task turn
`01a077d8-afce-7773-88df-f88a2927c9ec`, ended idle with only warmup+task completed.
Observed full-suite pytest event
`codex-shared:58704c732fa39161662264f7b01ccd17fc9b2d39522a81fe7adec1e546cdfcaf`
at17:52:24Z follows final file edit17:51:58Z: exit0,4passed0.04s, exact Q03cwd.
Root inspected implementation and generated JSON: version2/label renamed,
unknown theme/custom_flag retained; all immutable input/test/config hashes match.
Exactly one real Strands NOOP/noop:
`intervention_b9fd168b6ef2b19225d4b7c97b9d6e752bb4f9e7`, aggregate3calls19265ms.
No correction/escalation/extra operator prompt. Revoke/detach succeeded and worker
remained idle. Q03 is a behavioral quiet success, not a benchmark or proof the
model understood every observation: its rationale calls pytest uncertain despite
the correctly recorded typed pass. Investigate that evidence-context discrepancy.
Terminal receipt in clean checkout `build/quiet-live-20260906/Q03/client/`
`capture-20260906T175353708550Z.json`. Current matrix: 1 quiet success, 2 retained
inconclusive, 7 unstarted. No general completion, all-eight-pet/UI or submission claim.
Root traced Q03's explanation mismatch to a lossy verification summary: absent a
recognized tests_pass claim, verdicts can remain empty/uncertain even while the
typed full-suite pass is present. Previous `latest_pytest` exposed only ID/scope.
Repair adds separate `pytest_observation` facts: event ID, scope, explicitly
worker-observed basis, strict boolean ok/integer exit, bounded nonnegative counts,
and a conservative later-file-edit flag (including pathless edits). Raw command
output is not copied. Overall claim/acceptance status is deliberately unchanged;
these observations do not claim independent execution or complete human intent.
Regression/evidence-tool gate:65 passed10.18s, scoped Ruff clean. Cases cover
absent claims, later edits, targeted runs, invalid types/counts, and log spoofing.
Protected supervisor loop remains unchanged; current live7436 runtime predates
this summary repair. Need fresh-source verification before claiming model uptake.
Added a real evidence-tool regression: `verify_claims` output passes through
`run_verification` and `EvidenceObservationCollector`, preserving worker-observed
ok/exit/pass/scope fields and the exact audited receipt while keeping status
no_claims and omitting private raw output. Broader five-file verification,
evidence-tool/observation, supervisor-loop and planner gate passed134 tests11.42s
with thread warnings as errors; scoped Ruff/diff checks clean. This gate used the
main worktree with its unchanged protected loop, not a clean-checkout/full-suite
or live inference proof. No workers, provider calls, UI or subagents launched.
New live authority: clean `pex-live-d8d38ab` at
`d8d38ab12fa0d01202927f6a73aa94a1e619f71e`, locked sync113 and clean five-file
strict gate134passed18.70s. Dedicated bridge7437/PID14384/session16444, private
`build/quiet-home-d8`, scripts `run_quiet_bridge_d8.py`, `quiet_owner_d8.py`,
`quiet_case_d8.py`. Q04 confirmed this profile's origin once; later cases reuse it.
Q04 is a quiet success: worker `01a077e3-adcc-7352-9649-d0cbdc4f3303`, work turn
`01a077e4-fa40-76a3-9595-655732014d38`, correctly generated the three-heading JSON;
immutable hashes match, observed full suite4passed/exit0 after final edit.
Pytest source `codex-shared:1f07130851671aecbbd80808ee356f12d6ec7e7b245047b443930502bad065a3`.
One real Strands NOOP `intervention_c6235d1d31a816b95b228d4e28157f0609e18ecd`,
2aggregatecalls20430ms; the actual audited run_verification receipt contains the
new pytest_observation fields and rationale accurately cites four passes/no later
edits. This demonstrates live uptake, not just offline serialization. Revoke and
detach succeeded. Terminal Q04/client `capture-20260906T180659233358Z.json` SHA256
`26FEF38C57C70CDF808F8E4A73F6C65252332EDBD1CC9A85AB863F35310A7449` under
clean source `build/quiet-live-20260906`. Q05 has started on this same build;
retain its exact receipts and do not retrigger its single task.
Q05 then completed as a quiet success on the same clean d8d38ab runtime. Worker
`01a077e7-59e4-7d30-ad7b-e7cc2814969b`, task turn
`01a077e8-aba0-7bc0-b9eb-90717ffadaee`: immutable files unchanged, correct generated
manifest, accent transliteration and numeric-suffix collision handling inspected.
Observed full suite5passed/exit0/exactQ05cwd/no later edits; pytest event
`codex-shared:08b08778fc28099298c893ff1175142c2410fac01aee6d6059b557c7650b49e4`.
Exactly one Strands NOOP/noop `intervention_e4ff282e660d040e8f4afd5a5cfbe1ff5bd7a2b1`,
1aggregatecall6683ms; rationale correctly cites5passes/exit0/no later edits.
Revoke/detach succeeded; terminal Q05/client receipt
`capture-20260906T181110697936Z.json`. Tally:3 behavioral quiet successes (Q03-Q05),
2 retained inconclusive (Q01-Q02),5 unstarted (Q06-Q10). No accuracy/benchmark
claim. Reuse detached7437 and exact origin for Q06; do not start another bridge
unless source/config actually needs changing. No UI or subagents used this pass.
Q06 ran on d8d38ab: worker `01a077ec-14e3-7160-8afc-05de4e1520d6`, task turn
`01a077ed-51c5-70c0-b9b0-2bb07ed488ff`, idle warmup+task only. Immutable hashes
unchanged, generated date report inspected, observed full-suite5passed/exit0.
However, initial deterministic ASK_HUMAN
`intervention_9cc000ea022c6e17eb14416cb181f50717770f48` incorrectly joined an
affirmative "create report" mention to the separate prohibition "Do not create
a git commit". Final NOOP `intervention_e8612a02166e7b38377527febfb2ffcfc4346feb`
does not erase that unnecessary early escalation. Classify Q06 as a false-positive
prompt escalation, not a quiet success or a failure to verify completion at STOP.
Revoke/detach succeeded, no correction/extra worker turn; terminal receipt
Q06/client `capture-20260906T181646431022Z.json`, SHA256
`2A15D9D35B45D0B29BB78E1CEEB920CE23DEC32EE22BD410F92F595A2ED71ABD`.
Root repaired the matcher to require action/object terms in order within the same
bounded clause; sentence/semicolon/contrast boundaries prevent borrowing forbidden
objects from later prohibitions. Added regressions retain genuine git-commit
conflicts. Focused unit/planner/contract84passed24.27s. This remains bounded lexical
triage, not general semantic intent understanding. New repair is not loaded in
7437. Matrix:3quiet,2inconclusive,1early false escalation,4pending(Q07-Q10).
Before spending on more workers, root replayed all ten actual public TASK/goal
pairs through local lint only (`build/audit_quiet_prompt_lint.py`). This exposed
remaining false flags in Q07-Q10: semicolon-coordinated prohibitions ending in
"or create a git commit", with dotted filenames inside the same negative list.
Repair recognizes explicit or/nor coordination across semicolons and treats only
sentence punctuation (not filename dots) as the boundary. Bare semicolon or
contrast followed by an affirmative commit remains a conflict. All ten actual
prompt pairs now classify likely_refinement with no matched conflicts; no fixture
text was rewritten to produce this result. Final focused gate88passed24.63s,
Ruff/scoped diff clean. No new worker/model/network/UI/subagent activity for this
audit. Live matrix unchanged; fresh repaired-source Q07 remains next.
Q07 live now passed behaviorally quiet on clean
`d67e78f24a22092b2b2e4f56682e384f4a0d0e6f` at `pex-live-d67e78f` (locked sync113,
clean focused88passed35.94s). Dedicated bridge7438/PID7712/session34047, private
`build/quiet-home-d67`; ignored scripts `run_quiet_bridge_d67.py`,
`quiet_owner_d67.py`, `quiet_case_d67.py`. Reuse this origin/profile for Q08.
Worker `01a077f6-418b-7490-8a2f-e5ae36d13e92`, task
`01a077f7-92c9-7213-ac5a-a04c9bd9e095`, completed with only warmup+task turns.
Immutable files unchanged; root inspected rule-driven implementation and report:
T1..T5 ordered, category counts critical1/high2/medium1/low1. Full-suite5passed,
exit0, exactQ07cwd, no later edits, event
`codex-shared:0d28206f0d9ac46d32578857ca7f35c93f11029bc5a7140ca8f38f4579b61321`.
Exactly one Strands NOOP `intervention_cb9024157167117b26c196620b056890aa5a4097`,
2aggregatecalls14788ms; no prompt conflict. Rationale recognizes test pass but
does not claim independent validation of report category counts. Do not overstate
that semantic evidence scope. Revoke/detach succeeded; terminal Q07/client
`capture-20260906T182723969025Z.json` retained under clean build/quiet-live-20260906.
Matrix now4quiet,2inconclusive,1early false escalation,3pending(Q08-Q10).
older Sol instructions below are superseded. Reboot interrupted the previous full
suite; consult the checkpoint for the restarted run and failed live recovery evidence.

## 2026-09-06 final package/native checkpoint — current authority

Overall submission remains **NO-GO**, despite a green package-integrity receipt. Final
repository `HEAD` and `origin/main` are
`f99fe4399720a223d96f1ad860b34ae175f5d917`. The clean package receipt SHA-256 is
`23E1FA33736E387C22292D471375E43AC970DD37E3D27319E8D88CA204683C12`; it reports
`release_ready: true` and `blockers: []`. Interpret that only as the post-build package
contract passing. It does not encompass signing, live-loop recapture, visual replay,
AgentCore, benchmark, video, or submission gates.

### Exact package authority

- MSI: 122,585,088 bytes, SHA-256
  `759A9B2091804603563333C9087AD88ED4BFA60FD60A9BBBE3F89C126B2660DE`, unsigned
  (`NotSigned`).
- NSIS: 121,294,055 bytes, SHA-256
  `ADD72B18AFF7792D32D5AEAA1BC07C48929E3ED0A45F0AD4CDD896833FF76A69`, unsigned
  (`NotSigned`).
- Canonical desktop executable: 11,538,432 bytes, SHA-256
  `8D46B3650773D88A0FDF50405BAA6AF8359CDB686A27DC39D810C0DB79755FED`.
- Release-input hash:
  `66d333ea5417295de68d2e7137b930f0a057cb07a6b6976127b7d50a5ba4e2fa`.
- Sidecar-input hash:
  `c86435798c0ede81fa0ffb3cda860b37882272dcaf47f615ad58ad52b085aa2e`.
- Normalized desktop bundle marker:
  `bcf76659f3631f95b7d833d8a685db39a6c7cc8eb5a6fffd54792f50dcfc3dde`.
- Embedded sidecars: bridge
  `c20631fa2bb0cfacb432a042cc6e5522e785ddc958eb55c03157d1b347cfe3f4`,
  hook `754c13dcd25fcad5201f8098c01d46b0a090a770b7376fbb3a4e23ae224b0c15`,
  observer `f67df6c484699df210234f1207db7ff323a3a01cf1cc187196fbc85f589a5c7f`.

### Native evidence and exact limit

An extracted NSIS build was launched against a fresh profile. The packaged bridge reached
**All quiet**, Settings displayed the exact eight-pet roster, and the pet window rendered
with transparency. Escape dismissal and restoration from Settings were proven on a prior
pass of the same packaged runtime. During the final pass, Windows Security presented a
Node-automation prompt; this blocked the final all-eight animation replay and the final
native Alt+F4 persistence replay. Those two replays are incomplete and must not be
claimed as verified package evidence.

### Backend/keyring and test checkpoint

The post-live backend work made supervisor construction non-blocking to bridge health,
preserved authoritative startup/reload state across slow or failed configuration, and
made environment-credential availability reporting accurate without exposing secrets.
Native OS-keyring references remain opaque; secrets are not stored in public config or
these docs. Final strict backend focus: **36 passed**. The preceding broader backend gate:
**139 passed, 3 skipped**. Desktop: **180/180 passed**. Rust: **14 passed**. Do not sum
overlapping backend receipts. A whole-Python clean run was still in progress when this
checkpoint was written and is intentionally not claimed.

Protected boundary: do not edit, stage, restore, reformat, or clean
`services/supervisor/src/pex_supervisor/loop.py`. Its retained SHA-256 is
`392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`.

### Remaining submission blockers

- The validated live Codex + provider-live Strands restraint/recovery pair remains bound
  only to `5c49c10eaed4ad96346ceef8d2eb257e46fcd425`; it was not recaptured on `f99fe43`.
- Bedrock AgentCore is not deployed.
- PexBench is not frozen and there is no retained leaderboard result.
- The required public judge video is missing.
- Both installers are unsigned.
- The final all-eight native animation and Alt+F4 replay was blocked as described above.

Next work should close these exact blockers without weakening the three binding specs or
converting package integrity into a broader readiness claim. Older handoff headings below
are chronological evidence and are superseded wherever they say the package is absent,
the clean release-evidence closure is still being repaired, or the final repo is dirty.

**Latest live progress (after `4cfec67`):** production PEX transport observed a real demo worker turn start, deltas and completion and then read two turns from the exact CLI thread. First observer timed out; second traced check succeeded without a production change, so no unsupported defect/cause claim. [Exact events, handles and next provider step](CODEX_WINDOWS_LIVE_CONNECTION.md). This is transport/worker proof, not full goal-bound bridge/Strands supervision. Existing local inference endpoints are unavailable; supervisor consumer login is unimplemented. Keep listener7657/client64982, preserve current user sessions, use Sol low and pursue no-card-charge real inference without treating AWS credit eligibility as a billing guarantee.

**RESUMED — local shared-session progress:** user's no-card-charge approval permits the separate local demo; native goal ACTIVE. A real Windows listener exposed the AF_UNIX reparse-leaf bug, now narrowly repaired and independently reviewed with **150 focused tests passed**. Production PEX transport has actually initialized, read the exact demo CLI thread and subscribed on the same listener, without fake endpoint validation. [Current live handles, setup, failures and next step](CODEX_WINDOWS_LIVE_CONNECTION.md). Listener session7657 and client64982 are owned demo handles; existing sessions are untouched. No model call/full supervisor loop, verified visible panel or cloud proof yet. Older BLOCKED statements below are superseded, not a reason to stop local work.

**Native goal BLOCKED, not complete:** after three consecutive goal turns with the same live-runtime prerequisites unresolved, the safe checks are exhausted. Source `decc74b` and runtime receipt `244d806` remain accepted; latest process recheck still finds the same two App Servers without explicit shared listeners. Await a supported user-owned endpoint or the unanswered approval for a separate visible shared-listener demo, without replacing current sessions. AWS creation/inference additionally remains conditional on no card charges, which has not been established. Recovery section 0 forbids substituting more feature work for the real loop. Resume on user direction or meaningful external-state change; retain the full original goal and all submission gates. Older ACTIVE statements below are historical.

**Latest existing-worker refresh (after `decc74b`):** current Codex artifact is now `27d6a192e9c98618`; two App Servers show no explicit shared-listener flag and no owned TCP listener in the bounded check. Read-only daemon-version query is unsupported on Windows. [Exact current evidence](CODEX_EXISTING_SESSION_AUDIT.md). Need a supported user-owned shared endpoint, or explicit approval for a separate visible shared-listener demo while preserving current sessions; do not silently restart/migrate/replace workers. This is not a new live-loop or source-test receipt. No-card-charge cloud constraint remains in force.

**Latest authority:** the user conditionally approved AWS setup **only if no card billing occurs**. General credit service eligibility was checked, but no hard no-charge protection was established; no cloud creation/invocation is authorized under unresolved billing risk. Keep private billing details out of git. A Sol-low audit also led to a bounded preflight region/qualifier validation repair: main reproduced 5 bad-target false positives and 4 valid controls; complete preflight/client gate **91 passed**, Ruff/whitespace clean. [Updated receipt and remaining limitations](AGENTCORE_LIVE_PREFLIGHT_2026_09_05.md). Actual existing-worker/Strands/AgentCore proof remains open; do not repeat broad accepted tests or call the product ready.

**Live prerequisite refresh, 5 Sep ~20:01 UTC:** existing Brave browser-extension access now works; signed-in AWS Runtime lists show zero resources in `us-east-1` and `eu-north-1`. Local preflight is not deployable: CLI authentication/current deployment tools/running Docker/ARM64 image/runtime ARN are missing or unverified. Region/spend authorization is still required. The first article renders Published with its stable URL; logged-out availability and bonus award remain unverified. [Exact evidence and next steps](AGENTCORE_LIVE_PREFLIGHT_2026_09_05.md). New subagents must use **GPT-5.6 Sol low**, superseding all older medium instructions. No new test, deployment or live-model proof is claimed.

## CURRENT EXECUTION — claimed corrections and cancellation repair, 5 September 2026

**Goal ACTIVE; release NO-GO; 6 September WAT target at risk.** Reviewed source **`fe34a3a12087aed23a3fd89a1806e0c122e2fc04`** is committed and pushed with exact remote equality verified. New separate standing correction grant/API/desktop controls and real claimed-effect Pipeline/Executor/private shared start-or-steer composition are implemented and independently reviewed. Complete exact behavior, failed reproductions, test inventory and limits: [`CODEX_CLAIMED_DISPATCH_REVIEW.md`](CODEX_CLAIMED_DISPATCH_REVIEW.md). Older CURRENT headings below are chronological receipts, not instructions to rebuild finished prerequisites.

Main post-repair combined gate: **969 passed in 283.17s across 41 complete files**, no skips. Final frozen cancellation/framed gate: **6 passed in 15.62s**; desktop **171 tests and TypeScript/Vite build** passed. These overlapping receipts must not be summed. Nineteen Python paths passed Ruff; 24 staged source/test paths passed whitespace. Full framed local testing found a real post-Executor cancellation gap that the smaller suites missed. Main fixed it with a retained, repeated-cancellation-safe task covering the entire refresh/reconciliation/seal. Two independent tests failed before that repair; three final cancellation regressions plus three full framed cases pass. A timing-sensitive followup-list expectation was corrected without weakening receipt/no-redelivery checks. One interrupted exploratory teardown stall was not reproduced in seven later independent runs; exact limits are in the receipt. No owned test handles remain. These tests use fake supervisor/vendor I/O, bypassed test endpoint validation and a fake empty workspace evidence snapshot; never present them as installed-worker, actual Strands/AgentCore or useful-outcome proof.

**Current owners:** `sol_control_authority` (GPT-5.6 Sol medium) completed Store/grant, supervisor-context and cancellation regressions, plus independent API/UI/Pipeline review. `sol_shared_dispatch` (same model/effort) completed adapter dispatch, framed tests and Pipeline/workspace fixture migrations, plus independent Executor review. Both are finished and approve their bounded scopes. Main owns integration, the two explicit-grant echo/bootstrap fixture migrations, final gates, receipts and scoped push. New agents now use **Sol/low**, per the latest user instruction (`fork_turns="none"` with a self-contained bounded task). No temporary diagnostic is required; the reproduced cancellation issue now has ordinary regression tests. Preserve the unowned `services/supervisor/src/pex_supervisor/loop.py` +28/hash `392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604` outside staging.

**Immediate next:** resolve the actual existing-worker endpoint/executable and AWS runtime prerequisites; the source checkpoint is already published. Latest read-only Codex process/artifact evidence differs from the old audit and is in the new receipt; no usable shared endpoint was established, and the production ACL validator still rejects AppData/Local ancestors. Do not weaken security, restart this Codex app, launch a replacement worker or change permissions silently. The user identified the AWS account in their own browser, but **region and spend cap are still unspecified**. Checked environment variables are unconfigured; that does not establish absence of credentials/deployed resources. No cloud/provider call/deployment happened. Browser auto-connect cannot attach to current Brave; no new profile or restart was used. Computer-use remains paused after physical Escape unless the user directs it to resume.

The user reports publishing the first bonus article. Do not duplicate it; public URL/moderation and bonus award remain unverified. Follow the full seven-stage `SHIP_CHECKLIST.md`, reread all three specs and relevant files before another implementation cycle, independently audit every repair and push only verified owned paths. Next core proof is actual existing-worker Strands main/verifier NOOP and justified correction, observed useful outcome, ten quiet cases, actual AgentCore runtime, then all remaining full-spec/UI/backend/harness/release/**exactly eight pets**/fair visible comparison gates. Local source passes do not mark any of those live-product stages complete.

## CURRENT EXECUTION — per-event input baseline accepted, 5 September 2026

**Goal ACTIVE; release NO-GO; 6 September WAT target at risk.** Source **`6b7eecacc559bea05b8248836a92203c773b58e1`** is reviewed/pushed with exact remote main equality verified. Main final **878 passed in 185.13s across 31 complete files**, no skips; ten changed Python paths Ruff/staged-whitespace clean. Full receipt: [`CODEX_INPUT_BASELINE_REVIEW.md`](CODEX_INPUT_BASELINE_REVIEW.md). Baselines now freeze per observation from selected pre-resume history and the observed prefix; later history cannot retroactively grant an earlier trigger authority. Raw inputs remain private, incomplete evidence has no digest, and Store validates the optional content-free shape. No shared dispatch or real-loop completion is claimed.

**User's latest instructions:** all new subagents must use **GPT-5.6 Sol, medium reasoning**. Use fresh bounded agents with explicit model/effort and a self-contained task rather than reusing an older inherited-model worker. The user reports **they published the first article**; do not click Publish or create a duplicate. Its stable public URL/moderation state has not yet been independently verified; no bonus award is claimed. The old pending Publish prompt is superseded for that article. Other two posts remain local drafts.

**Exact next:** implement actual claimed-effect Executor/shared-adapter start/steer delivery plus a distinct one-time, revocable **Enable autonomous corrections** permission scoped to the selected session, goal, workspace and connection incarnation. The existing receipt remains `observation_only=True`; attaching/unpausing a goal is not a delivery grant. This is standing authorization, not confirmation for every correction. Install just-attempted Store provenance before the fresh control read; compare accepted/current/fresh external-input digests. Capture the current ledger revision after installation, since provenance installation advances it legitimately. Carry exact claimed effect ID/version/owner/action through Executor; final synchronous transport callback reuses full current Store validation, then live policy/pause/adapter/workspace/input checks after lock waits. No consumer-drain wait, uncertain resend or steer-to-start fallback; preserve strict four-key worker receipts. Cross-client post-check races remain disclosed, not imaginary server CAS.

`sol_control_authority` owns a read-only minimal grant/API/UI design. `sol_shared_dispatch` owns only the private shared-adapter dispatch method and its new focused test file. Main owns integration and checkpoint documentation; all new agents use the requested Sol/medium configuration. Old reviewers have finished. Preserve unowned supervisor `loop.py` +28/hash in the receipt. Reread the three specs/current important files each cycle and independently audit changes before scoped verified pushes. Then prove the real existing-worker Strands NOOP/correction/outcome and ten quiet cases, AgentCore runtime, and all remaining full-spec/UI/backend/cross-harness/release/**eight pets**/fair visible comparison gates.

## CURRENT EXECUTION — exact echoes accepted, 5 September 2026, 17:55 UTC

**Goal ACTIVE; release NO-GO; 6 September WAT target at risk.** Source **`9ba5f394b14040e8e0808f7101f1dc821084d5b3`** is reviewed/pushed with exact remote equality verified. Main **703 passed in 165.28s across 26 complete files**, no skips; ten changed Python paths Ruff/staged-whitespace clean. Full changes, failed reproductions, command inventory and limits: [`CODEX_INPUT_PROVENANCE_REVIEW.md`](CODEX_INPUT_PROVENANCE_REVIEW.md).

Exact Store-backed correction ID/content attribution now precedes live normalization and is shared with the history classifier. Completed echoes are record-only, not human input or another model call. Incomplete starts are record-only without claiming authorship; completed external input remains supervised. Bootstrap failure/cancellation, transactional multiplicity, replay, private sidecar lifetime and stopped evidence retention are reviewed. A duplicate discovered after reattachment closes with an explicit gap rather than retrying forever. No shared control, live worker/model/AgentCore or submission-readiness claim.

**Next, immediately:** coherent per-event accepted external-input baseline, then actual claimed-effect Executor/shared dispatch through fresh policy, Store and transport checks. Seed from selected pre-resume history only, advance in observed prefix order, and keep raw input private; later reconciled history cannot grant an earlier STOP authority. Never wait for the action's own consumer drainage/echo. Then real existing-worker Strands NOOP/correction/outcome plus ten quiet cases, verified AgentCore runtime and all remaining full-spec/UI/backend/cross-harness/release/**eight pets**/visible fair comparison gates.

`transport_review` owns next-slice NEW `codex_input_baseline.py` and NEW `test_codex_input_baseline.py` only; these are unaccepted WIP and excluded from the echo commit. Main owns subsequent adapter/Pipeline/Store integration and final gates. `attachment_review` finished independent approval (65-pass four-file gate) and is available for bounded review. All echo-checkpoint test handles completed. Preserve unowned `loop.py` +28 and unchanged hash in the receipt. Reread all three specs/current operational files each cycle; use explicit non-overlapping subagent work, independent review and scoped verified pushes.

The first short Builder article remains saved/previewed in the user's own signed-in Brave, **not public**, awaiting the already-present action-time Publish confirmation. Other two remain local reviewed drafts. See [`posts/PUBLICATION_CHECKLIST.md`](posts/PUBLICATION_CHECKLIST.md). Posting is authorized side work, not permission for final Devpost submission or cloud spend. All earlier CURRENT headings below are historical receipts, not the active queue.

## CURRENT EXECUTION — correction provenance accepted, 5 September 2026

**Goal ACTIVE; release NO-GO; 6 September WAT target at risk.** Source **`4f034e1a0dfe19a70c931f8269f44df339fdc55e`** is reviewed/pushed with exact remote main equality verified. Main **551 passed in 135.77s across 19 files**, no skips; eight changed Python paths Ruff/staged-whitespace clean. Full receipt: [`CODEX_CORRECTION_REVIEW.md`](CODEX_CORRECTION_REVIEW.md).

Pipeline now obtains Store-derived exact correction provenance before committing the immutable main effect. Store recomputes it transactionally, rejects model correlation, enforces unique correlation/immutable authority and exposes bounded historical attribution without reviving dispatch. Supplied exact continuation text is supported. Independent review repaired endpoint scope and generic-planner injection. Main reproduced/fixed stale older-turn completion erasing a newer active turn. Shared control remains disabled; no live delivery or Strands/AgentCore deployment claim.

**Next:** exact live/history echo classification and Store-validated record-only ingestion; coherent accepted human baseline (never give an initial STOP later reconciliation history); claimed-effect context through Executor to one fresh-policy/Store/transport-fenced start/steer write. Never wait for the action's own consumer drainage. Then actual existing-worker Strands NOOP/correction/outcome and ten quiet cases, followed by all full-spec/UI/backend/cross-harness/release/**eight pets**/fair comparisons. Read all three specs/current checklist, use bounded delegation and independently review each batch.

User confirmed Strands + AgentCore as intended stack and requested short bonus posts as side work. All three local posts are about 160 words. Main recovered the user's existing Brave after they opened Builder Center and signed in; first article is saved/previewed, **not published**, awaiting the computer-use skill's action-time Publish confirmation. Exact draft/status/duplicate checks: [`posts/PUBLICATION_CHECKLIST.md`](posts/PUBLICATION_CHECKLIST.md). No separate browser, credential transfer or bonus-point claim. Final Devpost submission remains separately gated.

Source owners/reviewers finished; `transport_review` has a new read-only baseline/echo design assignment, no edits. Preserve unowned `loop.py` +28 and hash in the receipt. No test handles remain at this checkpoint. Historical CURRENT headings below are evidence, not the active queue.

## CURRENT EXECUTION — fresh control snapshots accepted, 5 September 2026

**Goal ACTIVE; product/release NO-GO; 6 September WAT target remains at risk.** Source **`e64270c1e947d3e0f7c95598ec108bc2a28dc282`** is independently reviewed/pushed with exact remote main equality verified. Final main **483 passed in 86.41s across 18 complete files**, no skips; six Python paths Ruff-clean and staged whitespace-clean. Full scope, failed reproductions, command inventory and limitations: [`CONTROL_SNAPSHOT_REVIEW.md`](CONTROL_SNAPSHOT_REVIEW.md). This supersedes fresh-snapshot-as-unimplemented wording below; no production dispatch caller or enabled shared control exists yet.

Transport now captures immutable read provenance at response routing and refuses snapshots superseded by later same-chunk input. Actual parser consumed-byte boundaries reject incomplete headers/payloads/fragmented messages even when the parser buffer is empty. Coordinator verifies selected identity, full supported history, explicit idle/active/direct-input state and immutable user-input digest without draining/replaying its consumer. Store's new validation-only path rechecks the exact claimed main effect, boot/lease/action/ALLOW and full current goal/control/project/workspace/human-input authority without another claim or marker mutation. Main and independent review reproduced/fixed an unknown/empty history-item-type bypass after the initial green gate; final control allowlist matches the existing generated schema, not a newly verified installed runtime.

**Exact next implementation:** durable correction provenance and actual Pipeline/Executor/shared-adapter dispatch. Extend the existing immutable main effect with a server-generated unique correlation, canonical content and exact session/thread/root/project/workspace/subscription/epoch binding; validate at Store insertion, never trust model-provided action metadata. Carry claimed effect context into execution; apply live local policy, fresh input digest, Store final validator and final transport revisions before the one write. Classify exact trusted `clientId` echoes before human normalization, including uncertain sends; use an explicit Store-validated record-only ingestion path (STATUS alone does not skip supervision). Load bounded historical bindings before a reattached pump starts: old correlation may prove attribution, never new dispatch authority. Unknown prefixes must not suppress human input; partial/mismatched known echoes retain uncertainty. Repair stale completion bookkeeping. Never await consumer drainage/echo from inside its own action cycle. Preserve the strict existing four-key worker delivery receipt; record richer correlation separately. The review contains the ordered integration gates.

Then demonstrate the real existing-worker Strands NOOP/correction/observed outcome and ten quiet cases under applicable authority; continue full required audit/UI/backend/cross-harness/release/**eight pets**/visible fair comparisons per [`SHIP_CHECKLIST.md`](SHIP_CHECKLIST.md). No per-correction human confirmation substitute, alternate worker, uncertain resend or steer-to-start fallback. Read all three specs/current operational files at the next cycle, use bounded non-overlapping subagents and independent review, and push only verified scoped changes.

All assigned agents finished and no test handles remain. `transport_review` authored Store and independently reviewed coordinator; `attachment_review` authored framed read tests, reviewed transport and completed read-only provenance design; main integrated/reviewed and ran the final gate. Only unowned supervisor `loop.py` +28 remains dirty outside documentation; preserve its unchanged hash in the receipt. Global diffcheck reports its existing trailing blank line; six owned staged source paths passed. No native/proxy/worker/provider/UI benchmark/package/deployment/submission ran. Source tests are dirty-checkout evidence, not a clean release build.

## CURRENT EXECUTION — durable received bytes accepted, 5 September 2026

**Goal ACTIVE; product/release NO-GO; 6 September WAT target remains at risk.** New source **`db98481dc4cdae701a77667b7d93296f8e1a2172`** is reviewed/pushed with exact remote main equality verified. Main final **456 passed in 89.32s across 23 complete files**, no skips; nine Python paths passed Ruff, ten staged paths passed whitespace. Complete receipt and precise limits: [`RECEIVED_JOURNAL_REVIEW.md`](RECEIVED_JOURNAL_REVIEW.md). This supersedes raw-journal-as-next-action wording below; connection UI `cd39913` and text primitive `03045b5` remain accepted prerequisites, not live control.

Production inspection now creates a local immutable requested-provenance journal before the connector. Exact bounded receive chunks, including upgrade/partial/malformed data, commit before parsing/clearing. Held-ack timeout no longer destroys the only retained copy of the received human notification in the reproduced case. Separate raw-chunk revision and pending-byte state fence the internal dispatch primitive; a missing/failed journal refuses control, and encountered failure retires that transport. No raw HTTP/model export or live replay was added. Sensitive journal files are local/gitignored; payload/record caps stop capture without deleting evidence. Crash-before-commit, unreceived bytes, ambiguous initialization and full recovery remain limitations, not green coverage claims.

Independent review caught a foreign-WAL preservation bug after green tests; main repaired it with a plain-file format preflight before any SQLite open. Final independent original reproduction preserves exact main/WAL bytes and creates no SHM; 32 new tests passed in 7.04s. `transport_review` hit capacity after authoring its slice; `attachment_review` resumed successfully and gave final bounded approval. All agents are finished, no test handles remain. Only unowned supervisor `loop.py` +28 remains dirty, unchanged hash recorded in the receipt. Preserve it. No native/provider/package/benchmark/submission ran.

**Next implementation, immediately:** fresh same-thread coordinator read/current turn/input reconciliation and PEX-message provenance, then real durable goal/autonomy/trigger/intent/control/subscription/workspace/effect dispatch to the reviewed start/steer primitive. `active_turn_id=None` is not proof of idle; stale completion can clear it. Journal readiness does not rule out partial protocol input. Use actual fresh state and both receive revisions, retain uncertainty and never resend an uncertain action or fall back from rejected steer to start. Then obtain applicable runtime/provider authority and demonstrate the actual same-worker Strands NOOP/correction/outcome and ten quiet cases. Do not replace autonomy with one human confirmation per correction or launch a substitute worker. Follow [`SHIP_CHECKLIST.md`](SHIP_CHECKLIST.md), reread all three specs before the next implementation cycle, and use bounded non-overlapping subagent ownership plus independent review.

## CURRENT EXECUTION — connection UI and internal text transport, 5 September 2026

**Goal ACTIVE; release NO-GO; 6 September WAT target at risk.** New accepted/pushed source: desktop connection **`cd399133eddd7384994a7bc7f917b4d1871ef43e`**, internal same-thread text transport **`03045b58957414935b54840f15f0a0a98c492a79`**. Exact remote main equality verified for both pushes. Complete review, failed reproductions, browser evidence, commands and activation gates: [`CONNECTION_CONTROL_REVIEW.md`](CONNECTION_CONTROL_REVIEW.md). This section supersedes the older CURRENT headings below.

Desktop: explicit origin/CAS/rebind → inspect → exact full review → confirm → canonical status → detach/recovery is wired in Settings. Main **154 desktop tests passed**, TypeScript and production frontend Vite build passed; separate backend route gate **42 passed**. Rendered real component with a clearly labeled fake API passed setup/confirm/disconnect/lost-detach-response recovery, with exactly one detach mutation. Browser errors/overlay absent; accessible group-name issue repaired; gradient contrast remains a manual check. This is not a native desktop-to-worker run, and no production origin was configured.

Transport: an internal `_dispatch_text` now supports both idle start and active steer, strict same-channel/epoch/received-revision checks and mandatory synchronous final authority callback; no implicit reconnect, config override or uncertain resend. Shared close now settles the one actual cleanup across concurrent readers/callers. Final main **406 passed in 70.85s across 18 complete files**, scoped Ruff/whitespace clean. **There is no production caller, and shared capability remains observe-only.** Do not enable this primitive by simply changing the capability label.

**Exact next action:** integrate a durable received-envelope journal before normalization/clearing, with attachment/epoch provenance and journal-failure control refusal. Then fix fresh coordinator/adapter turn/input reconciliation, PEX-message provenance, and durable goal/policy/effect dispatch to this primitive. A reproduced timeout currently clears an undrained received human notification: this is an activation blocker, not a green-control claim. Read the review's four critical-path gates and the shipping checklist. Use bounded non-overlapping implementation/review owners. No per-correction human confirmation substitute; no alternate PEX-owned worker. Server start has no idle/input CAS; enforce measurable freshness and disclose the remaining external-client race rather than promising impossible atomicity.

All agents finished their assigned slices; no ongoing source edits remain. `legacy_attach_fence` completed UI review but its later transport review hit capacity; final independent transport approval came from `attachment_review`. Main's task-owned browser and Vite process were stopped. Only unowned supervisor `loop.py` +28 remains dirty, unchanged hash in the review. Preserve it. All three specs were reread this cycle; no worker/model, native GUI benchmark, installer/package, cloud deploy or submission ran. Source progress does not complete Recovery, full Build scope, eight pets or submission readiness.

## CURRENT EXECUTION AND TODO — accepted cleanup, 5 September 2026

**Goal ACTIVE; release NO-GO; 6 September WAT target remains at risk.** Latest accepted source is **`c15a2fce3ae9b5c9c1db2b530cd76eb4b29a5acc`**, pushed and exact remote main equality verified. It settles the one owned subscription-close task through repeated caller cancellation, retaining the original failure and immediate revoked authority. Main's final 17-file connection/retention gate: **355 passed in 179.14 seconds**, scoped Ruff and staged whitespace clean. Earlier continuity source `c0db453` retains its separate 1,016-pass/3-skip receipt. Do not sum overlapping gates.

Updated objective, prioritized TODOs, seven stages, evidence requirements and stop conditions: [`SHIP_CHECKLIST.md`](SHIP_CHECKLIST.md). The native active goal was checked; its objective cannot be edited through available tools. The checklist holds the refined working objective without falsely completing/replacing the goal. Winning remains the aim, not a guaranteed outcome.

**Exact next action:** reread all three binding specs and current operational files, review `docs/adapters/local-workspace-origin.md` against desktop authenticated request/state handling, and assign the minimum explicit origin → inspect/confirm → status → detach/reload workflow. In a separate bounded slice, close durable/raw observation and actual same-worker control gaps. Do not enable generic shared delivery or substitute a new worker. Then prove actual Strands NOOP/correction/observed outcome before optional expansion. All full-spec, release, eight-pet and visible fair benchmark requirements remain open.

`transport_review` implemented the three-path close repair; `attachment_review` independently approved its bounded ownership behavior and actual transport cleanup boundaries; main reviewed the patch/tests and ran the final gate. All agents are paused without ongoing edit assignments. Full receipt and residual risks are in [`WORKSPACE_CONTINUITY_REVIEW.md`](WORKSPACE_CONTINUITY_REVIEW.md). Only the unowned 28-line supervisor `loop.py` diff remains outside the accepted source checkpoint; preserve it. Tests used the existing dirty checkout, not a clean package. No native worker/model, GUI, benchmark, build/package, deployment or submission ran.

**Historical sections below:** older CURRENT/LATEST headings and pending-continuity/close instructions are retained as chronological evidence, not the current queue. This section and the shipping checklist take precedence. Do not rerun completed repair work from stale assignments.

## CURRENT REPAIR REVIEW — post-attachment continuity, 5 September 2026

**Goal ACTIVE; release NO-GO.** Reviewed source/API guide pushed as **`c0db4536db3c3cbb7366032e9bfdd9d22237aa4e`**, exact remote equality verified. Final main gate: **1,016 passed/3 skipped in 627.20 seconds across 56 complete files**. Scoped Ruff passed across 27 changed/new Python paths; staged whitespace passed for those plus the API guide. The skips are temporary symlink creation denied in `test_local_workspace.py`, `test_local_origin_config.py` and `test_workspace_inspect.py`. No permission changes or live runtime calls occurred.

Read [`WORKSPACE_CONTINUITY_REVIEW.md`](WORKSPACE_CONTINUITY_REVIEW.md) for the full repair, exact test inventory, failed reproductions, migration, review scope and residual risks. Two late independent findings are repaired: the real Ask answer function could enter its fallback provider after timeout/revocation; detached historical bound sessions could prevent reporting valid current same-goal progress. The final gate includes those real-answer tests and per-attempt HTTP/queued-Strands checks. Preserve the unowned supervisor `loop.py` edit; its exact hash and test-worktree limitation are in the review.

Next: repair the independently reproduced subscription-close ownership defect (**2 failed/2 passed**, new uncommitted `test_codex_subscription_close_ownership.py`). Single/repeated cancellation lets failed subscribe return before its one shielded close finishes; controls retain original errors and settle normally. This is not part of the accepted continuity slice. Then move toward minimum usable connection and actual same-existing-worker control, not optional pet/UI expansion. A read-only protocol review confirmed shared control is absent, and local input/turn counters alone cannot fence another client's input. OpenAI Docs was checked for distinct steer/start semantics. A single operator-confirmed action is only a diagnostic; it cannot replace the required autonomous Strands correction/outcome loop. The seven-stage shipping plan and all three specs remain binding. Older assignments/status below are historical when contradicted here.

## LATEST EXECUTION STATE — goal and TODO refresh, 5 September 2026

**Goal ACTIVE; release NO-GO; user shipping target 6 September WAT remains at risk.** This section supersedes stale reproduction-only assignments and next-action text below. The native goal was checked again: it remains active and its unfinished objective cannot be edited with the available tools. Do not falsely mark it complete to replace it. The updated working objective, ordered seven-step plan, owners and acceptance gates live in [`SHIP_CHECKLIST.md`](SHIP_CHECKLIST.md). Winning is the aim; verified submission readiness is the controllable completion criterion.

The post-attachment continuity repair has advanced beyond reproduction: main independently reproduced **15 failed / 4 passed**, then integrated Store, Pipeline, executor, local evidence tools and Ask PEX guards with bounded reviewers. Changes remain **uncommitted and not yet accepted as a complete source checkpoint**. They preserve historical observations and already-called outcomes, reject stale new reads/model entry/dispatch, and add a server-persisted workspace witness. Older workspace-bound sessions without that witness require detach/reinspection; genuinely unbound legacy paths are not newly certified. Filesystem checks are samples, not atomic locks or worker cwd-handle proof.

Main's already-running 51-file compatibility gate has now completed: **967 passed, 3 skipped in 455.51 seconds**. This run does not include the two newest Ask/operator-handoff files and is not the final frozen-tree gate; the exact three skip reasons still need inspection. Separately, reviewers report **14 Ask tests passed in 29.88 seconds** and **5 direct operator-handoff tests passed in 11.52 seconds**, with scoped Ruff clean. These are local temporary Store/Pipeline tests with fake vendor/model boundaries, not live provider/worker/UI evidence. Do not add overlapping earlier gate totals or claim the whole repository audited.

**Exact next action:** finish main review of the remaining new tests/diffs and reviewer findings; run the final combined 53-file gate including Ask and direct operator handoff, inspect skips, run scoped lint/whitespace checks, update audit/failure/API receipts, then commit/push only the accepted source slice and verify remote equality. Preserve the unowned 28 inserted lines in `services/supervisor/src/pex_supervisor/loop.py` and all other pending source outside this planning-only commit. Baseline source is `f08ad8097775fa45b7057983b6365f5e9272623e`; the preceding planning commit is `8b025f27868f498560317a2492c28ed2cf1c4190`.

All three bounded agents have finished their current slices and are frozen pending a new explicit assignment: `legacy_attach_fence` owns the Store continuity implementation/tests; `transport_review` owns adapter/Pipeline/access regressions and the Ask regression file; `attachment_review` owns evidence-tool/executor changes and direct-handoff regressions. Main owns integration and the Pipeline/Ask production changes. These are current ownership records, not permission for overlapping edits or whole-product approval. No desktop UI assignment is active.

After the accepted continuity checkpoint, follow the checklist: minimum usable connection flow → observation and safe same-worker control → real Strands NOOP/correction/outcome and ten quiet cases → remaining full-spec/code/human-workflow audit → normal release, all eight pets and visible fair comparisons → independent submission decision. No native worker, provider call, GUI benchmark, packaging, deployment or submission occurred in this planning update. Required runtime/submission authority is not granted by updating a TODO list.

## CURRENT PLAN — latest 5 Sep 2026 goal/TODO request

**Goal ACTIVE; release NO-GO; target 6 September 2026 WAT remains at risk.** The active native objective was checked again. Available goal tools cannot edit an unfinished objective; do not falsely complete or replace it to change its wording. The revised working objective and ordered seven-step execution queue are in [`SHIP_CHECKLIST.md`](SHIP_CHECKLIST.md), under **Updated working objective** and **Current execution queue**. This planning-only refresh supersedes older assignment/next-action paragraphs below; it is not a fresh full-spec read, source repair or live-validation receipt.

Reviewed baseline: attachment source **`f08ad8097775fa45b7057983b6365f5e9272623e`**, documentation **`f26221a86870a321a3d2993bb97cd3e490a1324c`**. The prior final gate remains **545 passed / 2 skipped** over 26 files; no new gate is claimed. Post-attachment authority is the first unfinished repair: initial Store review reports missing workspace checks during acceptance/planning and workspace-metadata mutation paths. Main has not yet independently verified or repaired those findings; inspect the reproduction results below and changed code before implementation.

Current bounded WIP: `transport_review` owns only `tests/unit/test_workspace_continuity_pipeline.py`, covering actual workspace-bound publication followed by directory/origin changes and valid controls through real temporary Store/Pipeline with fake vendor/model boundaries. `legacy_attach_fence` owns only `tests/unit/test_workspace_continuity_store_review.py`, covering acceptance, planning, dispatch and metadata continuity. Both are to finish reproduction results and pause; neither has production edit ownership. `attachment_review` has no current UI assignment. Main has read the React skill and selected references but has not completed the App request-helper/Settings wiring review or made UI edits. Preserve both uncommitted tests and the pre-existing unowned 28-line `services/supervisor/src/pex_supervisor/loop.py` edit; stage none in this documentation checkpoint.

Agent-reported reproduction results received during this planning update: Store review **12 failed, 2 passed in 14.71s**, including a reserved planner dispatch transition after directory replacement; final instrumented Pipeline review **3 failed, 2 passed in 11.41s**, with snapshot and supervisor spies each called once in all three stale cases (actual directory replacement, origin refresh, origin change after acceptance). Unchanged-directory and ordinary content-edit controls passed. Both agents have paused and report scoped Ruff clean. These are deliberately failing diagnostic tests, not a green gate or main-independent verification; no real model was called. Store's pre-dispatch `fail_event_processing` was reported to preserve the observation and avoid session projection; planned/dispatching states require separate treatment and must not be mislabeled as safely unexecuted.

**Exact next action:** review the continuity reproductions, then implement durable no-effect stale settlement plus positive current-workspace behavior across evidence/planning/delivery boundaries. In parallel only after contract review, assign the minimum explicit desktop connection workflow. Continue to raw/durable observation, actual safe same-worker control and real Strands NOOP/correction/outcome proof before optional polish. Then finish full code/spec and human-workflow coverage, normal release, exactly eight pets, visible fair Cursor/Codex benchmarks with separately labeled OpenCode diagnostics, and final independent readiness review. Every implementation cycle reads the three specs/current handoff, reproduces, fixes, independently audits, verifies and pushes only accepted work. No observer-only or local-test checkpoint completes the goal; no final submission is authorized by this plan update.

## CURRENT REPAIR — 5 Sep 2026 — explicit local origin and workspace-bound attachment

**Goal ACTIVE; release NO-GO; user target 6 September WAT remains at risk.** Reviewed source and the API guide are committed/pushed as **`f08ad8097775fa45b7057983b6365f5e9272623e`**; main verified exact remote `main` equality. Final main integration gate: **545 passed, 2 skipped in 261.43 seconds across 26 complete test files**. Scoped Ruff passed across all 12 source/test paths; staged whitespace checks passed for those plus the API guide. Only the unowned 28 inserted lines in `services/supervisor/src/pex_supervisor/loop.py` remain outside this checkpoint. No native worker/proxy/model, live GUI, package, benchmark, cloud deployment or submission was run. No production local-origin configuration or ACL was changed.

### What changed and what was actually reviewed

Main reread all three binding specs and the current handoff/operational sections; Core/Recovery's actual existing-worker loop and strict hidden-data boundary still govern the full Build scope. Main read/reviewed all new helper and test files and the changed manager/Store paths. Store's large remainder is not newly approved; the full inventory audit remains open. Bounded roles: `transport_review` wrote directory measurement, repaired the config publication defect and independently reviewed manager integration; `legacy_attach_fence` wrote config persistence and the Store publication guard/tests; `attachment_review` independently reviewed helpers and Store, reproducing the config defect. Main integrated the workspace receipt, manager/routes, and API integration tests. No reviewer report alone was treated as whole-product approval.

- `local_workspace.py` samples actual directory device/file IDs and canonical targets with explicit Windows/POSIX proof providers. It rejects invalid/non-directory/unavailable/changing targets, permits measured stable aliases, and does not use contents or timestamps as directory identity. Python's official [stat documentation](https://docs.python.org/3.12/library/os.html#os.stat_result) was checked. These samples are not machine attestation, an atomic filesystem lock, protection against inode reuse, or proof of a running worker's cwd handle.
- `local_origin_config.py` stores a strict bounded versioned `local-origin.json` in `settings.home`. The operator chooses the exact origin; PEX does not guess a hostname or relabel existing project history. Exact revision + fresh UUID4 choice ID prevents stale/ABA saves. Copying to a different measured installation directory requires explicit prior-choice rebind confirmation. Corrupt/unreadable data stays unavailable, not silently first-run. Writes flush an exclusive owned temporary file and verify its object and exact bytes before replacement. Residual last-sample filesystem races remain explicit.
- `workspace_binding.py` freezes project ID/binding, origin choice, measured directory and selected locator. Foreign-origin paths are not locally probed. A typed project whose legacy key looks like cwd no longer uses the raw-path shortcut. A genuinely unregistered exact-directory key remains supported with explicit origin/measurement. A physical conflict cannot be bypassed by selecting an older locator without proof for the same local directory; Store checks all current identity locators too.
- `codex_shared_attach.py` validates workspace authority before connector creation, freezes it at inspection, rechecks after asynchronous authority/expiry reads before subscription, and supplies it for transactional publication. It adds operator-authenticated `GET/PATCH /v1/local-workspace-origin` and `GET /v1/adapters/codex/shared/status`. Status does not start/probe/resume workers and supplies reload-safe detach IDs, coverage and truthful pending expiry/confirmability. Saving origin requires explicit confirmation and exact old revision/ID; active attachments must be detached first. The one threaded save and pending-connector invalidation settle under the manager lock before propagating cancellation. Uncertain saves require reload, not blind retry.
- `Store.publish_observer_session` accepts a paired internal `expected_workspace` / `local_origin_path` witness, rechecks project identity, exact selected locator ownership/JSON/membership and all local physical claims in its transaction, then samples current config and the actual incoming session path before publication. It preserves current human goal/pause and blocks changing a workspace receipt in place. Exact-subscription detach/lifecycle can preserve the old receipt without revalidating a directory/config that has disappeared. Other legacy callers without workspace witnesses remain outside this new guarantee; the method is not a public capability-granting endpoint.

### Failed cases, repairs and final verification

Independent config review initially reproduced two cases that overwrote valid config with a substituted or modified temporary file before rejecting it. Both now reject before publication; foreign replacement objects are preserved. Main's first combined attachment run had **14 failed, 21 passed in 32.83s**: literal Store cwd equality rejected valid Windows normalized paths, and one old test expected an already-created connector rather than earlier rejection. Physical checks remain intact; path comparison was corrected and the old assertion strengthened to zero connector creation. The next full two-file attachment gate passed **35 in 51.92s**.

Independent manager review reproduced stale-origin `thread/resume` before rejection, stale `can_confirm`, and fallback past a conflicting physical claim using an older bare locator. All repaired; final reviewer suite **7 passed in 19.84s**, including a real temporary directory rename/replacement preserving the original. Store owner reproduced four conflict-publication bypasses before repair, then passed **30 workspace cases**. Helper gate **84 passed/2 skips**; independent helper+Store review **32 passed**. These overlap the final 545-case run and must not be added as separate coverage. Both skips are real symlink creation unavailable under this Windows profile; no permissions were changed.

Final command from `C:\Users\JosephMayo\Projects\pex`:

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_codex_shared_transport.py tests/unit/test_codex_subscription.py tests/unit/test_codex_user_content.py tests/unit/test_codex_shared_attach.py tests/unit/test_codex_shared_adapter.py tests/unit/test_observer_session_publication.py tests/unit/test_observer_lifecycle_pipeline.py tests/unit/test_codex_attach_serialization.py tests/unit/test_codex_pipeline_pump.py tests/unit/test_attach_security.py tests/unit/test_existing_sessions.py tests/unit/test_generic_dispatch_authority.py tests/unit/test_event_processing_store.py tests/unit/test_event_processing_pipeline.py tests/unit/test_pipeline_session_merge.py tests/unit/test_codex_shared_status_pipeline.py tests/unit/test_codex_partial_intent.py tests/unit/test_codex_observation_retention.py tests/unit/test_observer_retention_store.py tests/unit/test_codex_reconciliation_retention.py tests/unit/test_local_workspace.py tests/unit/test_local_origin_config.py tests/unit/test_local_origin_review.py tests/unit/test_workspace_attachment.py tests/unit/test_workspace_attachment_review.py tests/unit/test_workspace_publication.py -q
```

### Exact next work — do not stop at this observer checkpoint

1. Read the binding specs/current state before the next implementation cycle. This attachment backend checkpoint is complete, not WIP. API contract and limitations: [`adapters/local-workspace-origin.md`](adapters/local-workspace-origin.md). Desktop origin/inspect/confirm/status caller is still absent; no new TSX/native visual checks were performed. Wire only necessary setup, using the applicable skills, rather than expanding unrelated UI before Recovery's loop.
2. Carry current workspace authority into continuous post-attachment evidence and action boundaries; an attachment-time witness does not certify later directory/config changes. Complete remaining raw/durable observation and owned coordinator-close settlement, without erasing retained observations or reviving lost transport authority.
3. Complete safe actual same-worker control with connection epoch, current human intent/input/turn and uncertain-delivery handling. Protected installed executable/endpoint and applicable runtime authority remain prerequisites; no second worker/ACL weakening as substitutes. Prove actual Strands main/verifier NOOP, specific justified correction and independently verified outcome, plus ten quiet tasks.
4. Continue all seven shipping stages: full code/config audit, usable human workflow and remaining required harness behavior, normal sidecar release, exactly eight pets, visible fair Cursor/Codex four-arm comparisons and separately labeled OpenCode diagnostics, final review and honest submission artifacts. Read-only official [overview](https://agentsforhumans.devpost.com/) refreshed this cycle: deadline still September 14, 5 PM PDT; no scored leaderboard exposed in the inspected overview/navigation. No rank is claimed; September 6 WAT remains the earlier user target.

## CURRENT PLAN — 5 Sep 2026 — goal and executable TODO refresh

The user requested an edited goal, TODO list and steps. The native goal was freshly checked and remains **ACTIVE**; available tools cannot edit an unfinished objective. The refined working objective and single current execution queue are in [`SHIP_CHECKLIST.md`](SHIP_CHECKLIST.md), under **Updated working objective** and **Next repair cycle — executable TODOs**. Do not falsely complete/replace the native goal to change its text. Target remains **6 September WAT**, exactly **eight pets**, release **NO-GO**; substantial live/control/product/release gates remain unproven and the target is at risk.

This is a planning-only refresh, not a fresh full-spec read, implementation checkpoint or live validation. It replaces stale prefix-repair assignments with the current workspace-authority tasks. Prefix retention remains the completed `7570297` source checkpoint with 413 passing integration cases and documentation `458c2c8`; its detailed receipt follows below.

Current bounded WIP: `transport_review` owns only `services/bridge/src/pex_bridge/local_workspace.py` and `tests/unit/test_local_workspace.py`; it reports 39 passed/1 environment-dependent symlink skip and Ruff clean, not yet independently accepted/integrated by main. `legacy_attach_fence` owns only `services/bridge/src/pex_bridge/local_origin_config.py` and `tests/unit/test_local_origin_config.py`; configuration implementation/tests remain in progress. `attachment_review` has completed read-only origin/desktop-flow design, with no UI edit ownership. Main has not yet implemented the origin API, workspace receipt, attachment/Store integration or desktop caller. Preserve these uncommitted files and the unowned 28-line `loop.py` edit; this docs checkpoint must stage none of them.

**Exact next steps:** review both helper modules and their evidence; reproduce remaining origin/path authority failures; integrate explicit origin + measured workspace through inspect/confirm and transactional publication; wire only the minimum truthful connection UI; independently review and run affected integration gates; update evidence and push scoped accepted work. Then complete safe same-worker control and the real Strands closed loop before optional polish. Follow all seven checklist stages through full audit, human workflow, normal release, eight pets, visible fair four-arm Cursor/Codex benchmarks plus separately labeled OpenCode diagnostics, and final submission readiness. No model/worker/GUI/package/benchmark/deploy/submission run occurred for this planning refresh.

## CURRENT REPAIR — 5 Sep 2026 — retain observations across stream loss

**Goal ACTIVE; release NO-GO; target 6 September WAT.** Prefix-retention source is independently reviewed, committed/pushed as **`757029700bde782399828981ba099d907e57a3a2`**, and exact remote `main` equality verified. Main's final gate: **413 passed in 212.58 seconds across 20 complete files**; scoped Ruff and staged whitespace checks passed across all ten changed/new source/test paths. This section is the documentation receipt follow-up. No real worker/provider/GUI/package/benchmark/deployment/submission activity occurred. Preserve the unexplained 28 inserted lines in `services/supervisor/src/pex_supervisor/loop.py` outside staging.

### Changed behavior and evidence boundary

- Main completed the remaining fresh Build read; all three specs, current handoff and changed source/test paths were read for this cycle. Large existing Pipeline/Store modules received changed-path review, not whole-file approval.
- Five new real coordinator → adapter → Pipeline → temporary SQLite cases initially failed because valid observations disappeared before closure/malformed/foreign suffixes. The coordinator now exposes only the validated ordered prefix in `CodexObservationInterrupted.batch`, with a sanitized reason and immutable `interrupted_batch` fallback set before cleanup. Invalid status/flags are validated before acceptance/watermark advancement; failing records and suffixes are excluded. Initial subscription failure still cannot publish a partially valid adapter.
- The adapter freezes the whole bounded batch before queue backpressure and retains queued, enqueueing and in-flight objects until durable acknowledgment. Independent review reproduced a 2,048-record initial reconciliation batch being cut to 1,281 by the first patch. The corrected bound covers both initial drains, with a regression preserving all 2,048 records under cancellation. That saturation test uses a fake retention callback, not SQLite durability evidence; the separate 300-record full-queue test uses actual Store/Pipeline.
- After joining both stopped pumps, a dedicated internal Pipeline callback verifies the actual retained tuple, event/session object witnesses and current registry owner. It freezes the same per-event observation snapshot as normal ingestion and redacts it. `Store.retain_observer_events` rechecks exact subscription, vendor/session/cwd and immutable project binding inside one transaction; it inserts new record-only events without session projection. Current goal/pause are not replaced. Existing canonical records retain their original binding and processing mode; a commit-then-cancel retry does not downgrade or duplicate accepted pipeline work.
- Retained worker completion and human input never enter the semantic planner through this recovery path. The separate disconnect receipt remains a local STATUS, not a fabricated worker STOP. Existing live-ingestion connection guards remain intact; shared worker effects remain disabled.
- Retention is bounded to 2,048 normalized records, 1 MiB per serialized event and 32 MiB aggregate, with a 10-second bounded retry window. Failure preserves pending objects/counts and reports failed retention; successful acceptance reports separately retained counts/sequence. Repeated cancellation settles the owned adapter finalizer before propagating. These bounds and in-memory receipts are not complete raw capture or process-crash durability.

### Verification and ownership

Main's focused real Pipeline/Store retention suite: **12 passed in 12.63 seconds**. Independent main-diff reviewer: **13 passed in 14.07 seconds** across that file and the reconciliation saturation test. Store owner: **25 passed in 19.15 seconds**; coordinator owner: **85 passed in 6.77 seconds**. Counts overlap the final 413-case integration gate; never sum them as distinct coverage. The first wider gate used an outdated attachment fixture missing the new callback: **11 failed, 402 passed in 238.39 seconds**. The fixture was updated without weakening assertions, all **24 attachment tests passed in 36.69 seconds**, then the complete corrected 20-file gate passed. Earlier additive coverage-key validation failures were corrected before this final gate as well.

Final command, from `C:\Users\JosephMayo\Projects\pex`:

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_codex_shared_transport.py tests/unit/test_codex_subscription.py tests/unit/test_codex_user_content.py tests/unit/test_codex_shared_attach.py tests/unit/test_codex_shared_adapter.py tests/unit/test_observer_session_publication.py tests/unit/test_observer_lifecycle_pipeline.py tests/unit/test_codex_attach_serialization.py tests/unit/test_codex_pipeline_pump.py tests/unit/test_attach_security.py tests/unit/test_existing_sessions.py tests/unit/test_generic_dispatch_authority.py tests/unit/test_event_processing_store.py tests/unit/test_event_processing_pipeline.py tests/unit/test_pipeline_session_merge.py tests/unit/test_codex_shared_status_pipeline.py tests/unit/test_codex_partial_intent.py tests/unit/test_codex_observation_retention.py tests/unit/test_observer_retention_store.py tests/unit/test_codex_reconciliation_retention.py -q
```

Bounded ownership: main implemented adapter/Pipeline/wiring and integration tests; `transport_review` implemented coordinator retention and independently reviewed Store; `legacy_attach_fence` implemented Store retention/tests; `attachment_review` independently reviewed main's diff and added the saturation regression. No other paths were assigned or cleaned. Ten source/test paths belong to this checkpoint (five production modules, two existing test files, three new test files).

### Remaining work and exact next direction

1. This bounded source checkpoint is complete and pushed, with the 413-case gate above. Before the next repair, reread the binding specs/current handoff as required and verify current worktree/ownership; do not rerun completed work merely from stale historical WIP sections below.
2. Implement named-project local-origin/physical workspace binding. The read-only design found both cross-origin path acceptance and the typed-project raw-cwd shortcut. No trusted local origin convention exists. Explicit operator-selected origin and server-measured directory identity with confirmation/migration are proposed, not implemented; preserve existing identities/history rather than silently relabeling them.
3. Finish durable/raw observation and cleanup ownership: a generation change or raw transport error before identity validation cannot produce a trusted prefix; selected lifecycle records still exclude deltas/diagnostics/token/approval frames. The coordinator's pre-existing shielded close lacks an owned task/settlement, so cancellation may leave its first cleanup pending while a second close returns. A reviewer initially suspected prefix loss there but withdrew that claim after reproduction showed retention succeeded. Do not report the withdrawn hypothesis as a reproduced bug or the fallback property as complete cleanup recovery.
4. Complete actual same-worker control with epoch/current-intent/input/turn fences and honest uncertain-delivery handling, then prove real Strands main/verifier NOOP and useful correction/outcome plus ten quiet cases. Protected executable/endpoint prerequisites and applicable run authority remain required; no ACL weakening or second worker substitutes.
5. Continue all seven shipping stages: remaining full-spec audit and human workflow, normal sidecar release, exactly eight pets, visible fair four-arm Cursor/Codex comparisons plus separately labeled OpenCode diagnostics, and final submission evidence. No leaderboard check occurred in this source cycle. The 6 September target is at risk while these substantial gates remain unproven; do not hide that risk or lower the product bar.

## CURRENT IMPLEMENTATION — 5 Sep 2026 — shared observer integration and intent safety

Reviewed source is committed/pushed as **`8a402c2221623a95b3d1ffa8b56c20d00d4dfcb6`**. Main verified exact HEAD/remote `main` equality after push. Only the unowned supervisor `loop.py` remained dirty; this source receipt is a documentation-only follow-up, not another implementation or runtime gate.

**Goal ACTIVE; release NO-GO.** This section supersedes older WIP descriptions below, not their historical test receipts. Target remains **6 September WAT**, exactly **eight pets**. The prior planning-only status restatement did not advance implementation; this cycle reproduced and repaired actual failures. Main reread all three binding specs and current handoff/status/decisions/integration/audit files before changes. Use bounded subagents with exact non-overlapping ownership, independent review, real integration tests, and scoped pushes after each repair cycle. Do not stop at observer-only support: same-worker intervention and the complete Recovery loop remain required.

### Implemented source, not installed-runtime proof

- New shared transport (`adapters/codex_shared.py`) connects through a dedicated hidden proxy to an explicitly selected existing socket, not a second App Server. Executable/endpoint ancestry and identity validation, bounded JSON/WebSocket framing, strict response IDs, generation invalidation, minimal environment and connector-only cleanup have regression coverage. No actual proxy, worker or provider was launched in this cycle. The installed executable/endpoint remains unverified for this path; modifiable AppData ancestry is rejected, and no ACL was changed.
- `adapters/codex_subscription.py` separates inspection/history from live observations and performs selected-thread read/resume/read reconciliation. Exact thread/root/project/cwd/connection identity and explicit confirmation are bound. History is never fabricated as live input or activity. Selected thread closure/archive/deletion closes the observer; it is not evidence of worker completion. `item/completed` is the item authority; do not synthesize live human input from an embedded `turn/completed.items` snapshot. Official protocol reference read this cycle: https://learn.chatgpt.com/docs/app-server . Installed-version schema compatibility remains unproven, including the required nullable vendor `projectId` field.
- `codex_shared_attach.py` authenticates inspection and requires operator authority for confirmation/detachment. It bounds pending selections, checks monotonic expiry after authority awaits, rejects stale registry/Store bindings and serializes with both legacy attach routes. Retries are exact-selection bound. Failed publication restores only the old transport-less pump this attempt actually stopped. A post-commit task cancellation shields/settles the one Store operation and adopts its result before propagating cancellation; it never starts the old pump after successful replacement. Process crashes are not covered by this in-memory settlement.
- `Store.publish_observer_session` is a real SQLite compare-and-swap publication, not ordinary discovery upsert. It preserves current human goal/pause/attention and worker activity, accepts only observer-owned metadata changes and advances control revision for a new observation incarnation. Its optional disconnect event is committed atomically as record-only. Pre-commit rollback, post-commit cancellation, current-goal preservation, stale revision and cwd ABA have tests.
- `CodexSharedAdapter` queues bounded live normalized events, retries the same event/receipt time after transient ingestion failure, and exposes incomplete observation coverage. A local disconnect is recorded through `Pipeline.ingest_observer_lifecycle`, not normal semantic worker processing: it does not manufacture STOP, activity or a supervisor call. This repaired an actual adapter → Pipeline → Store defect where disconnection became WORKING and stale observing coverage.
- `Pipeline.ingest_shared_codex_event` accepts only the current registered adapter's actual in-flight event/session objects, freezes runtime/activity/coverage into the accepted event, and rejects reserved observer snapshots through generic ingestion. Store rechecks the current receipt/cwd inside acceptance and loads the canonical event at both projection transactions. Changed connection/target preserves the new session; arbitrary planned metadata cannot manufacture coverage. Turn completion remains a STOP inspection trigger but cannot replace independently observed thread runtime state. Status notifications do not invent worker activity; batch processing cannot use a later coordinator status for an earlier event.
- Codex human `content` is authoritative over legacy text. Ordered text is preserved within bounds, unsupported/malformed/truncated content is labeled and secrets are redacted. Independent review reproduced partial text being elevated to an ACTIVE HUMAN override decision. Pipeline now requires positively complete, non-truncated, non-redacted normalized input for override authority. Original USER_PROMPT observations remain durable for provenance and later-input action invalidation. Existing `[REDACTED:` markers conservatively preserve upstream-redaction uncertainty, including literal marker text.

### Verification and review boundary

**Main final integrated gate: 357 passed in 177.91 seconds across 17 complete files**, including the final initial-runtime-flags repair and both real Store projection transaction regressions. Scoped Ruff passed across all 18 changed/new source and test files; staged source whitespace check passed. The unowned `loop.py` has an additional unreachable duplicate raise and blank lines; its whole-worktree EOF warning is deliberately not fixed or staged. No claimed clean tree. The preceding 333-case gate predates initial flags and two final Store transaction cases and is not the final receipt; earlier 291 cases also overlap. Independent review accepted the bounded repaired paths, not full product readiness.

Run from `C:\Users\JosephMayo\Projects\pex`:

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_codex_shared_transport.py tests/unit/test_codex_subscription.py tests/unit/test_codex_user_content.py tests/unit/test_codex_shared_attach.py tests/unit/test_codex_shared_adapter.py tests/unit/test_observer_session_publication.py tests/unit/test_observer_lifecycle_pipeline.py tests/unit/test_codex_attach_serialization.py tests/unit/test_codex_pipeline_pump.py tests/unit/test_attach_security.py tests/unit/test_existing_sessions.py tests/unit/test_generic_dispatch_authority.py tests/unit/test_event_processing_store.py tests/unit/test_event_processing_pipeline.py tests/unit/test_pipeline_session_merge.py tests/unit/test_codex_shared_status_pipeline.py tests/unit/test_codex_partial_intent.py -q
```

This cycle reproduced idle→working in actual Store, two attachment recovery failures, three incomplete-input authority failures plus an upstream-redaction failure, and three committed-baseline Store merge failures. Independent initial-status review also produced 22 failing cases before the coordinator repair; an intervening fixture cleanup API typo was corrected without weakening assertions. These failures were not hidden. All current tests use fake vendor transports and real local Store/Pipeline where specified; they are not real worker/model/UI/release evidence. The separate intent/content compatibility gate passed 60 cases, of which 29 overlap this final run; do not add overlapping totals.

Initial thread runtime flags now survive post-resume reconciliation and flags-only notifications. Present flags must be a list of strings. Documented `waitingOnApproval` maps to BLOCKED; other nonempty flags conservatively map to DISCOVERED/unknown, not WORKING. Current official docs did not establish `waitingOnUserInput`, so it is not certified as a known blocked state. Runtime flags are not immutable selection identity or permission authority.

Bounded reviewers: `attachment_review` owns manager recovery and initial runtime flag repair; `transport_review` reviews transport/subscription and owns Store canonical observation guards; `legacy_attach_fence` reviews legacy attachment/content and repairs incomplete-input authority. Main owns live adapter/Pipeline integration, cross-review and final acceptance. Existing huge `app.py`, `pipeline.py`, `store.py` and `codex.py` receive changed-path review, not a false whole-file audit claim. Preserve the unexplained **28 inserted lines in supervisor `loop.py`** outside staging; ownership is still unknown.

### Next required work — do not hide these gaps

1. **Named-project origin binding:** the attachment helper verifies path/platform but ignores LOCAL_PATH origin host. Two separately registered machine origins with the same lexical path have distinct immutable identities yet currently both match the local cwd. No trusted local-machine convention exists in the present registration contract. Implement explicit local-origin/physical workspace binding plus safe migration/confirmation; do not guess a hostname or discard origin identity. This is a remaining correctness gate, not support proof.
2. **Continuity/durable observation:** a later closure or malformed record in one drained batch currently discards earlier valid records. The reviewer reproduced two observed records and zero delivered worker events. The disconnect receipt honestly retains `raw_stream_complete=false` and unknown lost count, but does not recover them. Preserve validated prefixes/durable ingress before claiming complete trajectories, outcomes or benchmark capture. Queueing remains in-memory, with raw diagnostic/delta/token/approval frames outside the selected lifecycle subset.
3. **Actual safe worker control:** shared send/steer/start/approval/configuration controls remain disabled. Implement actual epoch/current-intent/input/turn fences, separate active steering from idle continuation, preserve worker sandbox/approval/cwd settings, and account for post-claim/uncertain-delivery races. An observer snapshot is not delivery authority.
4. **Installed runtime and true product loop:** resolve protected executable/endpoint prerequisites and obtain applicable exact run authority before launching. Prove same existing worker events, real persistent goal/external evidence, actual Strands main/verifier calls, justified NOOP and useful correction, observed continuation and verified outcome. Run ten quiet cases. No existing-worker/provider/build/UI/pet/benchmark/AgentCore/submission gate became complete here.
5. Continue the full seven-stage `SHIP_CHECKLIST.md`; finish all requirements across the three specs, UI/UX, release sidecars, eight pets and visible fair comparisons. Primary frozen benchmark remains four Cursor/Codex arms; added OpenCode pair is separately labeled. No leaderboard was checked this source cycle; historical absence is not current rank evidence. No submission, package, deployment, worker/config/ACL mutation or benchmark freeze occurred.

## CURRENT PLAN — 5 Sep 2026 — goal and shipping TODO refresh

The user again requested an updated goal, TODO list and steps after source `8a402c2` and documentation `93272ad`. The native goal was freshly checked and remains ACTIVE; available tools cannot edit an unfinished objective. `SHIP_CHECKLIST.md` records the refined working objective without falsely completing/replacing or shrinking the full three-spec goal. Release remains NO-GO, internal ship target 6 September WAT, exactly eight pets. This refresh changes planning documentation only; no new implementation or live verification is claimed.

The checklist now has one current seven-stage execution order with checkboxes and exit conditions: existing-worker connection integration; safe same-worker control; actual Strands main/verifier loop and quiet cases; remaining full-spec audit and human workflow; normal release build and eight-pet visual review; visible fair Cursor/Codex comparisons plus a separate OpenCode pair; final independent review/submission preparation. Completed Store/provider source repairs are no longer listed as unfixed. Detailed acceptance checklists remain required; one observed Codex thread does not satisfy the whole product.

The shared transport/coordinator/adapter/attachment and human-content source is now committed at the checkpoint above, with the recorded 357-case integration gate; the previous WIP statement in this section is superseded. It is not a live-verified connector. Shared delivery remains disabled. Protected launch-path validation currently rejects modifiable AppData ancestry; do not relax it or silently change host ACLs. No real endpoint/proxy/provider launch is evidenced by this planning update.

The checklist's **Next repair cycle — executable TODOs** supplies six immediate steps: finish audit-input refresh; reproduce prefix loss through real Store/Pipeline; retain validated observations without post-loss semantic effects; resolve explicit local-origin/physical workspace authority; independently review/run integration gates; record, commit/push and verify only owned reviewed paths before proceeding to control and the real loop. Fresh Core/Recovery rereads are complete for this continuation; fresh Build reread is still incomplete. No implementation started during this planning refresh.

Current bounded ownership: main owns the future prefix repair across coordinator/adapter/Pipeline/Store; `transport_review` completed a read-only reproduction/design review and should independently review the patch; `attachment_review` completed a read-only origin/migration proposal, with implementation ownership still to be assigned; `legacy_attach_fence` has no new assignment. The transport reviewer reproduced two accepted records and zero delivered observations after a bad suffix, and identified validation occurring after status-record acceptance. The attachment reviewer reproduced acceptance of two distinct machine origins at one path, including a typed raw-path shortcut; server-measured proof and explicit origin configuration remain proposed, not implemented. Preserve unowned `loop.py`. After every cycle, assess the 6 September target honestly and continue through the full seven-stage checklist.

## CURRENT REPAIR — 5 Sep 2026 — durable dispatch authority

**Active goal; overall NO-GO.** Main implemented the first authority repair in `services/bridge/src/pex_bridge/store.py`, with 14 new cases in `tests/unit/test_generic_dispatch_authority.py`. This is a bounded backend repair, not a live independent-supervisor or release receipt. Main's stable seven-file integration gate passed **162 tests in 194.86 seconds**; scoped Ruff and whitespace checks passed. Reviewed source is pushed as **`125b97649d54902818e36640c6cb50e471ea1406`**; main verified exact HEAD/remote equality. This receipt is a documentation-only follow-up; agent-owned shared Codex files and unowned `loop.py` remain outside the source checkpoint.

### What changed and why

- Event acceptance atomically freezes a canonical session-authority snapshot: exact session/vendor/harness/project/goal/cwd binding, durable control revision and immutable project binding. Main-effect dispatch compares that snapshot, the accepted goal intent revision/hash, and any later accepted same-session `USER_PROMPT` inside the same `BEGIN IMMEDIATE` transaction that grants the sole dispatch marker. Vendor timestamps cannot override acceptance order; recorded-only prompts count too.
- Changing a session working directory now advances its control revision after existing project-alias reconciliation. Semantic plan projection always preserves the current adapter-owned cwd, so an old plan cannot restore its own target directory. Pause/resume and cwd away/back cycles invalidate old authority even when the visible state returns to its earlier value.
- The nullable migration deliberately does not backfill current authority into historical decisions. Missing snapshots fail closed for worker actions; duplicate event acceptance and plan replay cannot refresh stale authority. Existing narrowly scoped permission-denial containment remains exempt from these new intent checks and retains its previous target/policy checks.
- Independent review caught that `discovery_generation` is a routine desktop-refresh token, not a connection epoch. It is deliberately excluded from this snapshot. The reviewer exercised actual `Pipeline.refresh_desktop_sessions` with a fake adapter and confirmed a normal refresh still permits a valid action. Status-only updates, unrelated-session prompts and later worker activity also remain dispatchable in regressions.

### Evidence and limitations

Main independently executed the committed pre-fix Store from `0d3cd0f` in memory against the new fixtures, without rewriting tracked source or calling a provider/adapter: five goal-intent, pause/resume and newer-prompt cases all failed because stale dispatch was incorrectly granted. Independent final review passed all 14 new tests and approved the bounded Store/test diff. A preceding four-file gate passed 82 tests; an intermediate seven-file gate passed 160, but both precede the final cwd repair and are not its final integration receipt. The initial 39-pass/1-failure run exposed a nonexistent test-helper method; that fixture typo was corrected to `add_event`.

Main also ran both cwd regressions against that same committed baseline: the ABA case failed because control revision remained zero, and the pre-plan target-change case failed because the old plan restored `C:/repo` over `C:/different-target`. The final 162-case gate contains the complete files `test_generic_dispatch_authority`, `test_event_processing_store`, `test_event_processing_pipeline`, `test_cursor_hook_preparation`, `test_session_control_transactions`, `test_goal_store_transaction`, and `test_resolution_dispatch_identity`, all under `tests/unit`. Overlapping earlier counts are not additive. The unrelated `loop.py` diff grew to 26 inserted lines during this cycle; main did not write or stage it and its writer remains unknown.

Additional main compatibility gate on the same source: **28 passed in 53.71 seconds** across complete `test_pipeline_session_merge.py`, `test_codex_pipeline_pump.py`, and `test_opencode_pipeline_pump.py`. These are local fake-adapter/runtime tests, not real harness or provider activity. No live process, installed hook, package, benchmark, deployment or submission action occurred.

**Still open:** actual transport/subscription incarnation fencing, raw input arriving before durable acceptance, global pause/resume ABA, and changes after the Store claim commits. Do not claim that a local transaction solves vendor/input concurrency. Documented Codex human-message normalization, immediate turn/input watermarks, safe active `turn/steer` versus idle continuation, and preserving worker configuration still need integration and proof. Live model-backed NOOP/correction, primary UI flows, package/pets/comparisons and submission gates remain incomplete.

Shared transport and coordinator files/tests are separate uncommitted agent work, not part of this Store checkpoint. Raw transport owner reports 21 mocked tests passing, but main has not completed its source review or live proof. Cross-review initially blocked the coordinator on canonical project identity, normal global notifications, conflicting stable IDs and post-resume cleanup; the owner repaired them and the sibling reviewer now approves integration. Coordinator owner reports 30 tests passing, Ruff/compile/diff checks clean. Main still must fully review both modules/tests and integrate authenticated attachment, truthful capabilities, actual live observation and safe delivery. Missing canonical project/model/originator fields and thread responses above 1 MiB currently fail closed; installed-version compatibility is not proven. Preserve these files and the unowned `loop.py` edit; do not stage them with the Store repair.

## CURRENT PLAN — 5 Sep 2026 — refreshed goal, TODOs and execution order

The user's latest request is to edit the goal and create a TODO list and steps. The native goal was inspected and remains **active**; available goal tools cannot rewrite its unfinished objective. The updated working objective and detailed ordered plan are in `SHIP_CHECKLIST.md`, especially **Immediate execution plan — latest goal/TODO request, 5 September**. Do not falsely complete or replace the goal to change its text. Internal target remains **6 September WAT**, exactly **eight pets**, overall **NO-GO**.

Next priority: independently reproduce and repair stale generic dispatch authority before enabling shared Codex mutations. The read-only credential reviewer reports actual temporary-Store reproductions granting an older action after a same-goal objective edit, pause/resume, and later accepted user prompt. The reviewer also reproduced loss of documented `userMessage.content` text during normalization, and identified that current nudges can use `turn/start` plus configuration overrides. These are reviewer findings awaiting main verification/repair, not completed fixes. Separate exact-active-turn steering from idle continuation; do not silently change the user's session configuration or fall back from failed steering to a new turn.

Bounded parallel ownership: `codex_audit` owns only new shared transport/test files; `opencode_audit` owns only new subscription coordinator/test files; `credential_review` independently reviews delivery/authority without source edits; main owns integration, authority fixes, final review and receipts. Transport/subscription designs are in progress, not installed-runtime proof. Preserve unowned `loop.py` changes and all agent-owned WIP; stage only reviewed paths. Read the three specs/current handoff before each grind and audit every repair.

After the authority/connection work: prove real main/verifier NOOP and same-worker correction, then ten quiet cases; finish primary UI/backend flows and remaining source audit; validate normal release and clean-profile setup; inspect all eight pets; run fair visible Cursor/Codex comparisons plus separately labeled OpenCode diagnostics; perform final independent release review. Applicable live/provider/process/package/publication authority gates remain. This update changes planning documentation only and adds no new test, runtime, benchmark or readiness claim.

## CURRENT HANDOFF — 5 Sep 2026 — safe provider setup and honest source bootstrap

**Pushed source receipt:** `67168204b11331a4a3db21b20e09a6900f3bbec5` (`Bind provider credentials and make source setup safe`). Main verified exact HEAD/remote `main` equality after push. Only the unowned `loop.py` change remained outside that checkpoint. This receipt is a documentation-only follow-up.

**Active goal; overall NO-GO.** Internal ship target remains 6 September WAT. Main reread the three binding specifications and current operational files, completed the inherited credential-form WIP, and independently reviewed bounded setup/provider repairs. Exactly eight pets; real existing-worker supervision still takes priority over pet polish and comparisons.

### Completed source repair, not live product proof

- `supervisorDraft.ts` binds pasted credentials to provider, auth mode, custom protocol and the actual endpoint, including named-provider overrides. Changing destination clears the pasted key; model-only edits do not change its audience. Named saved endpoints are visible, read-only in the form, and explicitly included in PATCH. An explicit null selects the registry endpoint for a newly chosen named provider instead of inheriting an undisplayed override. Custom endpoints remain editable. The backend's existing stored-key audience checks remain intact.
- App callbacks are wired through synchronous in-flight/draft guards. Conflicting fields are disabled while saving; old GET/catalog responses and save responses cannot overwrite newer draft/view state. The backend GET now explicitly reports revision zero before the first saved choice. Missing/malformed revisions no longer become guessed first-run authority, and PATCH success must confirm the next revision. Failed/uncertain writes require canonical reload before another save. Supervisor/settings/catalog requests have bounded abort-aware waits; cancellation is not rollback and never implies a failed write was safe to replay.
- Catalog refresh freezes the immutable runtime configuration in its ContextVar, including explicit unconfigured state, until the request finishes. A reproduced old-key/new-endpoint race is closed. A requested provider that conflicts with committed routing is rejected before HTTP/AWS client construction. Context scope restores on exceptions; environment-only/auto provider selection remains available.
- The Windows source bootstrap checks prerequisites, uses `uv sync --dev`, locked `npm ci`, and all-three-sidecar preparation, stops on native failures and restores the caller's location. Default setup no longer installs global Cursor hooks. README separates source setup from a packaged installer, documents actual worker/session/goal order and isolated Codex limitations, removes the nonexistent worker Attach control, explains explicit observe-hook installation and cautious rollback, and corrects stale supervisor architecture claims. No real installer/build/hook command was executed during this cycle.

### Verification and review receipt

Final main integration run: **147 passed, 1 skipped in 37.91 seconds** across seven complete files: `tests/contract/test_supervisor_settings.py`, `tests/unit/test_supervisor_config.py`, `test_providers.py`, `test_source_setup_contract.py`, `test_attach_security.py`, `test_existing_sessions.py`, and `test_config_security.py`. Skip: the environment cannot create the symlink fixture in `test_supervisor_config.py:101`. Main desktop gate: **97 Node tests passed**, TypeScript `--noEmit` passed. Scoped Ruff and scoped diff whitespace checks passed. The 23 new frontend cases include helper behavior and source wiring contracts, not rendered React/native UI proof.

Independent credential review reproduced both hidden named-endpoint routing and catalog TOCTOU; main repaired/re-reviewed the form/route boundary and the reviewer implemented the catalog fix. Five catalog-race fixtures failed before that repair. The final provider-only gate is 72 passed. The source bootstrap is executed in isolated PowerShell tests with fake commands only, proving exact ordering, native failure short-circuit and location restoration without doing a real install. Earlier 94/95/97 desktop and 78/142/147 backend runs overlap; never add their counts. One old frontend source assertion failed after bounded request wrappers were added; it was updated to require the new bounded parallel form, not weakened to ignore the contract.

**Security incident:** an initial provider test-isolation failure allowed an ambient credential to appear in a reviewer's local assertion output. A MockTransport prevented an external request. Do not repeat or retain the value; the user was told to rotate it if live. The fixture now removes ambient supervisor-key precedence and uses a content-free boolean credential assertion. A corrected test does not erase historical tool output or prove credential rotation occurred.

**Preserved unknown edits:** `loop.py` remains outside ownership and the checkpoint. During this cycle its unexplained uncommitted addition grew from the earlier duplicate to 12 inserted lines in the observed diff. None of the three bounded agents or main claims those writes. Do not clean, stage or infer a cause; identify the writer before overlapping changes. The prior handoff's duplicate description is historical, not the entire current diff.

### Next core action

Read `CODEX_EXISTING_SESSION_AUDIT.md` before implementing the next adapter slice. Current stdio attachment starts a different App Server and cannot be counted as the user's existing live stream. The independent audit records installed binary markers/hash separately from current official/upstream behavior. Main confirmed official documentation distinguishes stored `thread/read` from subscription and describes a shared Unix/WebSocket listener; no live installed-version proof occurred. Shared-server observation, exact subscription/reconciliation, connection recovery and a genuine safe mutation fence remain to be built. A read-only intermediate slice does not satisfy the final independent-supervisor goal. The proposed Windows proxy connector is a design candidate, not an implemented or live-verified bridge.

Next: solve actual existing-session observation/control, recoverable adapter attachment and truthful session state; then real main/verifier NOOP and specific continuation proofs, ten quiet cases, full primary flows, normal release/package gates, all-eight-pet QA and fair visible comparisons. No provider inference, bridge restart, new harness launch, UI automation, sidecar freeze/package, deployment or submission occurred here. Their applicable action-time gates remain. Continue bounded subagents with exact file ownership, independent review and verified scoped pushes.

## Planning update — 5 Sep 2026

At the user's request, `SHIP_CHECKLIST.md` now records the revised winning-oriented working objective and an ordered next-cycle TODO list with owners, dependencies and evidence-based completion rules. The native goal remains active; its tool cannot edit an unfinished objective, so do not falsely complete it to replace the text. Internal ship target remains 6 September WAT. This is a planning-only update, not new implementation or validation evidence.

Historical planning state, superseded by the provider/setup receipt above: the credential draft repair was incomplete when this earlier plan was written; its reviewed source repair is now pushed in `67168204b11331a4a3db21b20e09a6900f3bbec5`. Rendered UI/provider proof remains open. The separate unexplained `services/supervisor/src/pex_supervisor/loop.py` edit remains untouched and outside reviewed checkpoints. Follow the latest immediate execution plan before moving to the gated live loop, eight-pet review and comparisons.

## CURRENT HANDOFF — 5 Sep 2026 — exact model evidence and recoverable desktop startup

**Active goal; overall NO-GO.** Reread all three binding specifications (`PEX_CORE_SPEC.md`, `PEX_BUILD_SPEC.md`, `PEX_IMPLEMENTATION_RECOVERY_SPEC.md`), this handoff and the root `STATUS.md`, `KNOWN_FAILURES.md`, `DECISIONS.md`, and `INTEGRATIONS.md` before continuing. Internal ship target is **6 September WAT**, not the later official contest deadline. Exactly eight pets. The updated objective and ordered TODOs remain in `SHIP_CHECKLIST.md`; do not falsely complete the active goal to replace its text.

### Current source repair and ownership

Two bounded existing subagents split protocol/supervisor evidence and native/frontend startup; main integrated bridge validation, persistence and crash replay. Main independently reviewed both source slices and drove corrections, then the supervisor owner independently reviewed main's bridge/pipeline/Store changes. Agents share this checkout: assign exact non-overlapping files, use bounded follow-up work, do not start another agent's process or overwrite its files. Continue review after each repair cycle; a local fixture pass is not live product proof.

- New `SupervisorEvidenceObservation` receipts retain the exact bounded, sanitized JSON returned by a tool, canonical sanitized arguments, SHA-256, timestamp, observation ID, distinct main/verifier invocation ID, and request/session/goal/event binding. They are immutable typed records with strict JSON, hash, embedded-ID, duplicate, size and reference checks. Tools can read changing visible files; receipts preserve the returned observation, not a claim that all inputs were frozen. The collector enforces final UTF-8 output/argument limits, a 24-observation count and a 128-KiB serialized-receipt budget per model stage, with locked concurrent admission and a content-free overflow refusal. Invalid/nonfinite/cyclic request payloads fail closed rather than receive a lossy digest.
- Main and verifier explicitly cite their own observation IDs. Tool names and model-authored prose are not evidence authority. Non-NOOP semantic proposals need valid main citations; STOP interventions still need a fresh independent verifier, valid verifier citations and distinct main/verifier model-call accounting. Observed/cited is not proof the model understood a fact or that an action helped. Failed/NOOP calls retain observations even without valid citations; invalid foreign verifier observations are not preserved as legitimate evidence and cannot erase valid main provenance.
- AgentCore validates every exact receipt against the actual sanitized request dispatched, not a new local reconstruction. Foreign request/event/session/goal, bad hashes, unresolved or reused IDs, shared invocation identity and unsafe output/labels fail closed as delivery-uncertain without another semantic dispatch. Exact returned bytes are rejected if unsafe, never silently rewritten and rehashed. Every non-NOOP remote proposal must report completed main inference, actual-use telemetry and positive main calls; failed/timeout/not-attempted/zero-call replies cannot carry worker actions. These fields are correlation/provenance, not remote-execution attestation.
- Pipeline interventions, SQLite planner effects and JSONL audit retain main observations/refs plus the separate verifier receipt. A typed timeout previously discarded already-collected observations: now its original response remains in the immutable `delivery_uncertain` planner record, while a separate NOOP projection preserves telemetry and rejects its action. Crash recovery reuses that record without repeating inference or sending the ambiguous proposal. Unknown exceptions still produce the existing content-free uncertainty receipt; no evidence is invented.
- The prior two review suggestions are closed: tests directly assert that the current planned context ID reaches the offered durable packet and is stored, and that unsupported generic activity remains noncausal/unknown in the audit projection.
- Desktop source now shows the main surface before fallible bridge startup; the pet starts hidden. A native Starting/Ready/Failed state and main-only retry/status commands replace invisible setup aborts. The official single-instance plugin is registered first to focus an existing instance before another bootstrap. Per-attempt state serializes retries; occupied/unverified port owners are neither adopted nor killed. Only the desktop-owned child is subject to cleanup. Startup probes use a monotonic deadline and bounded output draining; token access requires current verified readiness. Failures use safe codes/guidance without exposing credentials, PID, paths or stderr. Retry and recovery must earn fresh canonical backend state.
- Frontend startup recovery separates native status availability from lifecycle state, rejects older-attempt or terminal-state resurrection, and keeps privileged recovery commands out of the pet window. The React review skill guided request races, effect cleanup, accessible announcements/focus and stale canonical-state review. This does not finish provider setup, worker attachment or other onboarding.

### Verification and checkpoint receipt

Final main integration gate: **332 passed in 137.76 seconds** across 15 complete unit files: `test_agentcore_client`, `test_agentcore_pipeline`, `test_event_processing_pipeline`, `test_worker_outcome_attribution`, `test_event_processing_store`, `test_store_audit_outbox`, `test_supervisor_loop`, `test_agentcore_runtime`, `test_agentcore_preflight`, `test_policy_scoring`, `test_supervisor_evidence_observations`, `test_evidence_tools`, `test_strands_runtime`, `test_supervisor_context`, and `test_audit_invariants`. Main also reran **74 desktop Node tests**, TypeScript `--noEmit`, **12 Rust unit tests** and Rust formatting; all passed. Scoped Ruff passed. Independent bridge re-review approved the final failed-model guard. The startup owner additionally ran clean `cargo clippy --tests -- -D warnings`.

**Rust build caveat:** unit tests and Clippy used a process-local `TAURI_CONFIG` override with `bundle.externalBin` limited to `binaries/pex-bridge` and `binaries/pex-cursor-hook`, both real existing frozen executables. The required frozen `pex-cursor-observe` binary is absent. Main reran `cargo test --locked` under the same disclosed override. No tracked release configuration was weakened: the normal release config still requires all sidecars. This is not an unmodified release build, package/preflight pass, rendered React test, actual single-instance/retry UI smoke, or provider proof. Native unit tests cover state admission, token readiness, timeout/terminal classification, port policy, identity and permissions; they do not simulate every native process-spawn/kill branch or parent-death lifecycle. Crash-orphan cleanup has no Job Object/watchdog yet; unknown owners are diagnosed rather than killed.

Prior development runs included a 13-failure/49-pass serialization mismatch and a 2-pass/1-fail timeout-provenance case; those findings drove actual repairs. Intermediate 71/74/173/319/329-case gates overlap and must not be added together. The final 332-case run includes the malformed-verifier-invocation and serialized-budget regressions. **Pushed source receipt: `1574c56d00a41a0f9d1769e3c1b6a85e59e0af72` (`Preserve exact supervisor evidence and recover desktop startup`), with exact `origin/main` equality verified.** This paragraph is a documentation-only follow-up.

**Unexpected concurrent local edit:** after source freeze and push, `services/supervisor/src/pex_supervisor/loop.py` acquired a second unreachable final `raise RuntimeError("decide() cannot run inside an event loop; await decide_async()")`, separated by a blank line. File LastWriteTime was 5 Sep 02:03:34 local. The supervisor agent had previously removed the same duplicate, verified one raise, and reports no later writes, watchers/editors/background processes or outstanding exec sessions. Main did not write this module. The post-push edit is intentionally **left uncommitted and untouched**, outside the reviewed source receipt; identify its writer before overlapping edits or cleanup. Do not claim a clean working tree. The pushed commit contains one final raise. This unexpected edit is unreachable but its origin is unresolved; do not invent a cause or broadly reset the checkout.

### Next actions, evidence limits and authority

1. Preserve the unexpected local `loop.py` edit and identify the concurrent writer before touching that file; source checkpoint remote equality is verified. Continue independent non-overlapping product work below. Do not count a source checkpoint as submission readiness.
2. Prove one real existing Codex same-session supervisor loop: correct completion → real model-backed NOOP; incomplete completion → specific evidence-backed main proposal + independent verification → policy → actual same-worker continuation → independently verified final state. Then ten quiet cases. Do not substitute fake Strands telemetry, canned prompts, synthetic adapters or a benchmark wrapper.
3. Complete usable first-run/provider/worker/goal/autonomy flow; correct installer interpreter/attachment instructions and authenticated source-valid demo capture. Exercise primary user workflows before pets or comparative runs.
4. Continue the incomplete path-by-path audit and benchmark integrity work. Four formal Cursor/Codex arms remain the spec contract; the OpenCode pair is a separately labeled diagnostic extension. Real benchmark runtime/evaluator isolation and enforced network policy remain missing; never flip flags to bypass them. Human actions/raw coverage/timing must remain unknown where unobserved.
5. After product/integrity gates: visibly inspect all eight pets and eligible PEX/Cursor UI using the required skills, run authorized live comparisons, verify exact package/source identity and demo/submission artifacts, then final independent release review.

No live provider/model calls, bridge restart, installed hook changes, second Cursor, desktop/package launch, packaging/freeze, deploy, publication or submission occurred in this repair cycle. Those actions retain their applicable action-time gates. Read-only listener checks found ports 7420 and 4096 occupied; unauthenticated health/identity requests failed and **do not establish source-valid health**. The earlier contest bridge home/goal identifiers are historical until refreshed; do not disrupt the running user's session. No leaderboard rank or benchmark improvement is claimed. No claim of whole-repository audit, rendered UI correctness, packaged-startup success or submission readiness is justified yet.

## CURRENT HANDOFF — 5 Sep 2026 — outcome lineage, semantic context and canonical UI

**Reviewed local source checkpoint, not submission readiness.** The active goal remains active. `SHIP_CHECKLIST.md` now contains the updated working objective, ordered steps, prioritized TODOs, stage-by-stage execution board, exit conditions and deadline discipline. Goal tools cannot edit an unfinished goal's objective; do not falsely complete it to replace it. Internal target remains **6 September WAT**, with exactly eight pets and the visible comparison phase after real-product/integrity gates.

**Pushed source receipt:** `a779404082edb3fe861a643bf1f981eeb5373b40` (`Bind supervisor context and outcomes to honest canonical state`) is on `origin/main`. Local HEAD and the remote branch hash matched exactly, with a clean working tree immediately after push. This receipt is a documentation-only follow-up; no source changed after the recorded final gates.

### What changed in this batch

- `pipeline.py` rejects foreign session/harness/goal/project observations before touching outcome state. Non-Codex/OpenCode activity is recorded as noncausal observation with `helped=None`; generic transport acceptance is not enough to claim a useful result. Cursor's legacy completion query now explicitly returns unsupported with no invented turn ID or vendor acceptance. Existing immutable Cursor preparation/flush/activity history is preserved.
- OpenCode normalization retains exact vendor message ID, assistant `parentID`, role, source type and continuity/removal status. Outcome matching requires the exact admitted user-message receipt, action/result/policy binding and target project/session/goal. Terminal completion requires a clean assistant `message.updated`, finite ordered creation/completion timestamps and exact `finish="stop"`. Tool-calls, truncation/unknown finish, errors, missing parents, foreign scope, uncertain delivery and stream gaps cannot become clean completion. Following idle and duplicate final siblings for the same parent are demoted to status to avoid a second supervisor dispatch; new prompts and stream discontinuity clear that marker. Idle remains a fallback when no authoritative final message was observed. Official-source references used in review: [message schema](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/message-v2.ts) and [session loop](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/prompt.ts). These moving development sources are not proof of the user's installed version.
- Typed bounded durable context and decisions now reach `SupervisorRequest`, the local supervisor and the redacted AgentCore request. Selection enforces project/goal/session, validity, supersession, sensitivity, provenance and size. Secret/local-only/foreign/stale material is excluded. A harness self-report cannot become verified merely through its metadata. Stable current-event planned records can join existing durable records in the frozen planning packet; replay retains the original packet.
- `get_context_items` and `get_decisions` expose three-record pages and bounded exact-ID detail. The index and both model prompts expose counts/first IDs; pagination explicitly reports next IDs and omissions. Large envelopes no longer imply that one tool call showed all records. The audit stores **offered** IDs and the canonical packet hash, never a claim that every offered record was used. Field-level truncation remains explicit. Exact per-call tool observations are still missing and remain the next P0 repair.
- Desktop state now distinguishes loading, fresh, stale and unavailable per resource, with independent endpoint errors and cached-state warnings. It no longer reports quiet before the first canonical response or submits unavailable supervisor settings as defaults. Revision-dependent controls are disabled when their required source is unavailable. Intervention-history failure blocks Undo even if the deck endpoint succeeds. Context is cleared/hidden on project changes, preventing the prior project's context from appearing in the newly selected project. Settings requests have sequencing and a retry path. The React review skill guided request-state, project-scope, accessible status and disabled-control review.

### Stable-source verification and review

Main combined backend gate: **298 passed in 62.15 seconds** across 15 complete files: `test_worker_outcome_attribution`, `test_opencode_outcome_lineage`, `test_opencode_pipeline_pump`, `test_codex_pipeline_pump`, `test_event_processing_pipeline`, `test_supervisor_context`, `test_evidence_tools`, `test_supervisor_loop`, `test_strands_runtime`, `test_agentcore_client`, `test_agentcore_pipeline`, `test_agentcore_runtime`, `test_ask_review`, `test_audit_invariants`, and `test_store_audit_outbox` (all under `tests/unit`).

After the final OpenCode duplicate-sibling refinement, main reran the complete lineage and OpenCode pump files plus adapter capabilities, Cursor hook/prompt-policy contracts, Cursor delivery Store and hook-preparation files: **191 passed in 44.92 seconds**. This overlaps the 298-case gate; do not add the totals or present either as a whole-repository test pass. A preceding invocation used two incorrect Cursor test filenames and collected no tests; the corrected run is the receipt. Earlier development failures and partial runs remain superseded, not hidden.

Main frontend rerun: **67 passed**, then `npx --no-install tsc --noEmit` exited 0. These are helper/state/source-contract checks, **not rendered React, actual desktop, provider or end-to-end user workflow proof**. Scoped Ruff and diff whitespace checks passed. Agent-owned supervisor/context gate had 119 passing tests and OpenCode's final focused selection had 66 passing/65 deselected; those overlap main gates and are not additive.

Main reviewed bounded changes; independent pipeline/Store cross-review approved the identity fencing, unknown generic outcomes, OpenCode delegation and frozen context reference. Reviewer suggestions still open: directly assert a current planned-context ID reaches the packet and assert the generic causal flag in the audit projection. An actual Store/pipeline OpenCode parent-attribution test is included. All new imported modules must land atomically with pipeline/protocol callers. `CODE_AUDIT_COVERAGE.md` retains 49 original full-read entries and adds five new paths (346 listed); most of the original inventory still needs fresh review. Do not turn changed-code approval into a blanket whole-file or whole-app claim.

### Exact next steps and limits

1. Source checkpoint push is verified above. Keep push-per-verified-update discipline for the next repair.
2. Implement exact bounded timestamped request/event-bound tool-observation receipts separately for main and verifier, persist them, and test workspace mutation between calls. Offered-context hashes and tool names do not solve this.
3. Complete first-run connection and recoverable visible startup; verify the actual primary human workflows. Investigate evidence polling under slow endpoints, not only helper tests.
4. Establish real Strands main/verifier and same-session Codex NOOP/correction evidence, then ten quiet cases. Resolve applicable live/provider authority and budget at execution, preserving the existing bridge and sessions.
5. Finish remaining source audit and benchmark raw-event/human-count/isolation repairs; review all eight pets and run user-visible comparisons only after their gates. The formal spec contract remains four Cursor/Codex arms; OpenCode is a separately labeled diagnostic pair or an explicitly versioned extension.
6. Clean-profile/package smoke, accurate demo/setup/submission artifacts and final independent GO/NO-GO remain mandatory. Final publication/submission needs explicit authority.

No provider/model call, installed/global hook mutation, service restart/launch, live benchmark, desktop UI automation, package, deploy, freeze or submission occurred in this batch. No benchmark improvement or live causal benefit is established. Use bounded subagents with non-overlapping ownership, reread all three specs/current handoff before each grind, review and verify every repair, and keep the goal active while safe meaningful work remains. Do not promise literal perfection or claim shipping readiness from test counts.

## Latest operator priority — ship tomorrow

On **5 September 2026**, the user explicitly changed the internal target to **shipping tomorrow (6 September, WAT)** and requested a fresh independent full-code/spec audit, a repair/build checklist, complete UI/UX and backend review, then final pet review and visible live PEX comparisons using Cursor, OpenCode, and Codex, with Computer Use for suitable validation. Follow [`SHIP_CHECKLIST.md`](SHIP_CHECKLIST.md), not the older six-cell-only development restriction. Main reread all three specs completely after this request. Three bounded independent audits returned concrete backend, harness/integrity and UI/release findings; the checklist now contains the ranked repair queue and required evidence. Planning commit `0aaf2847528283e1726c37cef050bfdfb5cfc0c1` was pushed and remote-verified. No full-code audit or release-ready claim has yet been earned. The official contest date is unchanged; the earlier user target now drives prioritization.

## CURRENT HANDOFF — 5 Sep 2026 — truthful production Cursor hook delivery

**Active goal continuation, not submission readiness. Read `PEX_CORE_SPEC.md`, `PEX_BUILD_SPEC.md`, and `PEX_IMPLEMENTATION_RECOVERY_SPEC.md` before continuing. This checkpoint repairs the real bridge/helper path, not a benchmark wrapper. Final verification and push receipt are recorded below when complete.**

### What changed and why

- The old hook-only Cursor adapter manufactured a local `cursor-stop-*` turn ID and reported acceptance while text was merely queued. It now returns a distinct `CursorHookPreparation`, bound to the exact stop event/session/vendor and SHA-256 of the emitted text. Pending text is keyed by `(session_id, event_id)`, consumed once, and discarded without exposure on denial, mismatch, cancellation, or timeout. It does not populate the sent inbox or mint a vendor receipt.
- Executor and durable pipeline preserve `hook_followup_prepared_delivery_uncertain`; the immutable main effect remains `delivery_uncertain`. Operator-message and handoff branches explicitly treat preparation as uncertain, never delivered. Generic Cursor activity can no longer make an old intervention appear helpful through the generic worker-delivery matcher.
- The synchronous stop response rechecks canonical goal, intent revision/hash, session control/discovery/project binding, pause state, exact completed intervention/action/policy/evidence, and text identity. Store atomically validates that authority against the frozen event/effect receipt before issuing the private delivery packet. Aborted/error Cursor stops are persisted as complete events with no intervention and no supervisor/executor dispatch, including ACP-backed sessions; post-response suppression alone was insufficient.
- The production helper strips the private `pex_hook_delivery` packet from Cursor stdout. Exact packet shape, conversation identity, and emitted-message hash are mandatory when the packet is present. Invalid packets suppress the follow-up. Only a full-character-count stdout write plus successful flush permits the authenticated, local, no-redirect/no-retry ACK (0.75-second helper timeout). Broken or partial output creates no receipt. The schema-2 isolated benchmark branch cannot use this production acknowledgment. Legacy responses without a packet remain legacy/no-ACK, not upgraded evidence.
- New append-only SQLite preparation, flush, and activity tables bind observations to the original intervention. Only the nonce digest is durable; raw nonce appears solely in the private bridge/helper exchange, never Cursor stdout or audit. First ACK requires the frozen canonical project binding, same process boot, Store-clock age from zero through 30 seconds, and exact trigger accept-sequence watermark. Concurrent/later activity before the ACK, late packets, restart, nonce mismatch, and wrong project fail closed. An already-recorded exact replay is read-only/idempotent, including after restart; project authority is still validated.
- Ordered later activity requires an accepted canonical Cursor worker event with a distinct nonempty generation, unchanged session/goal intent/control/project authority, and a strictly post-flush accept sequence. An intervening persisted user prompt, multiple candidates, or bounded-history overflow leaves correlation ambiguous. The projection says `same_session_activity_observed`, with `vendor_acceptance_proven=False`, `prompt_coverage_complete=False`, `causal_continuation_proven=False`, and `helped=None`. The original prepared/uncertain effect is never rewritten as delivered.

### Evidence limits and continuation

Cursor documents `followup_message` as a stop-hook response that triggers another message; hook output is used after successful helper exit. A successful local flush/ACK occurs before that exit and is **not vendor acceptance**. The local token/nonce handshake is not cryptographic attestation of the helper against a compromised same-host process. Missing prompt-hook coverage can hide an unrelated user turn. Neither local sequence observation nor these fake-model/ASGI tests proves causal improvement or live Strands quality. Official contract: <https://cursor.com/docs/hooks>.

The official contest overview was refreshed in this turn: deadline remains **September 14, 2026, 5:00 PM PDT** (**September 15, 01:00 WAT**), Professional Agents track. No scored leaderboard is exposed in the inspected overview/navigation; no rank is claimed. Source: <https://agentsforhumans.devpost.com/>. Real independent Strands/Codex same-session evidence, safe six-cell execution isolation/network enforcement, package smoke, demo video, and submission readiness remain unproven. **Overall NO-GO; keep the goal active.**

Three bounded subagents split adapter/executor, standalone hook, and Store ledger work; independent cross-review found and drove repairs for aborted-stop dispatch, action-goal mismatch, partial writes, missing project validation, delayed first ACKs, and replay project validation. Main owns integration and final combined verification. Preserve review-after-each-grind, eight pets, source push per verified checkpoint, and the six-cell priorities. Do not spend provider quota, deploy, package/freeze/submit, mutate installed hooks, restart the existing bridge, or spawn another Cursor without explicit action-time authority. No such action occurred here.

### Verification receipt

**Pushed source:** `c519883190c57566e6b5823042193b0e20936146` (`Separate Cursor hook preparation from delivery observations`). Local HEAD and `git ls-remote origin refs/heads/main` matched exactly, and the working tree was clean immediately after push. Subsequent outcome/context/UI repairs are a new, separately reviewed batch; do not apply the checkpoint's test receipt to those newer edits.

Stable-source 12-file gate **206 passed in 134.00 seconds** after repairing the test drain to await descendant presentation tasks, not just the first task snapshot. Scope: event processing pipeline, Cursor Store ledger, Cursor hooks/prompt policy/helper ACK, response authority, preparation/legacy receipt compatibility, adapter protocol safety, audit invariants/outbox and operator handoff effects. Separate complete Codex pipeline-pump/fleet files: **77 passed in 79.92 seconds**. Final adapter-capability file: **24 passed in 14.05 seconds**, after independent review found and corrected its stale expectation that discard-only `consume_followup` returns text. These three disjoint gates cover **307 tests across 15 files**. Scoped Ruff passed. Independent app/pipeline, Store and adapter/helper source reviews found no blocker in this bounded lifecycle repair; the last review's stale test finding is resolved. Source-push identity is recorded in the next receipt.

Immediate carry-forward: OpenCode/generic outcome attribution remains fail-open; supervisor context/evidence and first-run UX have P0 gaps recorded in the checklist. Cursor's older `wait_for_turn_completion` still fabricates an acceptance label for an arbitrary turn ID; no current production caller was found, but replace that unsupported result before any Cursor live comparison uses it. Do not mistake this narrowly reviewed delivery lifecycle for whole-product approval.

Failure history retained: the earlier broad 20-file diagnostic run was interrupted after failures/stalled progress and is **not green**. Its readiness timeouts led to test-only host-I/O allowances, without changing production timeouts or durable receipt assertions. The next 12-file run had **205 passed / 1 failed** because the helper drained only a snapshot; the final 206-case run above fixes that actual test defect. Older interim selections (122, 42, 7, 2 and the initial 125 passed / 4 failed) overlap and must not be added into a unique total. No whole-repository, installed-app, provider or live benchmark proof is claimed.

## CURRENT HANDOFF — 4 Sep 2026 — production intent and semantic arbitration repair

**Verified and pushed checkpoint, not submission readiness. All three binding specs remain authoritative. This slice repairs production supervision, not benchmark scoring. The final stable-source gate passed 334 tests. No live provider/model call, installed/global hook mutation, bridge restart, deployment, package, freeze, or submission has occurred.**

**Pushed source receipt:** `004cd2ce94f51100bd6e41f1e6b37334a5886cc5` (`Honor prompt authority and independently verified semantic decisions`) is on `origin/main`. `git rev-parse HEAD` and `git ls-remote origin refs/heads/main` matched exactly and the working tree was clean. This paragraph is the documentation-only receipt follow-up. No push protection was bypassed.

### Audit findings and implementation

- Cursor `beforeSubmitPrompt` previously mapped the proposed action directly to a block/message, even if policy denied it or it no longer belonged to the current prompt. `app.py` now requires a real completed `Intervention`, the exact triggering event/session/goal, nonblank evidence, matching executed action and approved policy/result. ASK_HUMAN requires an escalation; ANNOTATE requires an annotation. Invalid, pending, denied, oversized, empty, stale, paused, or unbound responses pass through without inventing a fallback question.
- Prompt processing compares canonical session control/discovery/project-binding revisions and goal intent revision/hash before and after inference. Pause/resume and goal-change A-to-B-to-A cannot revive an old response. Newly added authority reads share the inference deadline; they cannot introduce an unbounded wait inside that processing phase. This is a last-read authority fence, not an atomic transaction through vendor receipt. Existing hook setup/store work outside this processing phase is not newly covered by that deadline. A returned annotation is not proof that Cursor displays it or rewrites the prompt.
- The intent audit reproduced false durable human overrides for negated and quoted instructions, negative-constraint restatements being called contradictions, and `hackathon` triggering the `hack` nuisance rule. The classifier now accepts only direct, affirmative, opening-clause ledger overrides with a nearby explicit constraint/decision/rule/restriction object; quoted/code/example, conditional/meta language, or unrelated later text cannot lend authority. Full prompt text remains available for conservative contradiction detection. Exact tokenization handles sentence-final punctuation and retains dotted/hyphenated identifiers; contracted negative constraints retain their action verb. Ambiguity needs an unquoted whole-word shortcut (`hack`) plus speed/vagueness, so ordinary `maybe quickly` text and quoted shortcut examples stay quiet. This is bounded lexical triage, not general natural-language understanding; complex or ambiguous requests must not silently become human decisions.
- Supervisor arbitration previously replaced model NOOPs and failed/timeout results with the pre-model deterministic plan. It also treated a supported worker claim as overall goal completion and discarded model wording even for matching action types. The repair retains completed semantic NOOPs, makes failed/missing-output inference silent, reserves the completion guard for supported acceptance plus compatible verification, and independently verifies every surviving semantic STOP intervention. Verifier rejection must be NOOP, never a restored unverified pre-plan. No configured model remains explicitly deterministic and cannot count as live semantic proof.
- Independent review additionally found that a post-inference processing exception erased real inference telemetry, and an old AgentCore deployment could return an intervention without the new independent-verifier evidence. Both companion repairs are part of this slice. Definite AgentCore configuration/pre-dispatch failure is silent, with safe failure provenance; delivery-uncertain transport outcomes retain their existing no-retry behavior.
- `SupervisorResult.independent_verifier` is now a strict, bounded typed receipt, separate from aggregate model telemetry. Local and remote authorization share the approved-status, concrete-evidence, relevant-tool, and positive-verifier-call predicate. AgentCore additionally requires actual main-call provenance (`used_llm` and aggregate calls greater than verifier-only calls), and rejects uncertain verification-only support. Missing/rejected/insufficient receipts from a safely decoded old runtime become NOOP while retaining transport/inference provenance; malformed receipt scalars are protocol-uncertain, not retried. Raw booleans/numeric strings cannot invent local verifier counts; strict remote scalar validation rejects them. Receipt strings are redacted/path-masked, and the receipt survives intervention metadata, SQLite, and the redacted audit JSONL. This is an evidence contract, not cryptographic proof of provider execution or writer authentication.

### Review and continuation discipline

Three bounded subagents split supervisor/runtime, intent/persisted-decision tests, and AgentCore/independent review. Main owns Cursor response authority and integration verification. Independent review forced a second intent-scope correction and a post-inference provenance correction. The first combined gate exposed a whole-word matching regression at sentence-final punctuation after **124 passed**; this is a failed intermediate run, not a final green receipt. Earlier Cursor hook/policy gate passed **83 tests**; the later expanded policy-only gate passed **37 tests**, including goal-intent ABA. These overlapping interim results must not be summed or presented as whole-repository validation.

### Final stable-source verification

**334 passed in 110.08 seconds** across the complete files: `tests/contract/test_cursor_hooks.py`, `test_cursor_prompt_policy.py`, `test_intent_guardrails.py`; `tests/unit/test_intent_guardrails.py`, `test_policy_scoring.py`, `test_planner.py`, `test_supervisor_loop.py`, `test_strands_runtime.py`, `test_agentcore_client.py`, `test_agentcore_pipeline.py`, `test_agentcore_runtime.py`, `test_audit_invariants.py`, `test_store_audit_outbox.py`, `test_event_processing_pipeline.py`; and `tests/integration/test_strands_supervisor.py`. Repository-wide Ruff and diff whitespace checks passed. No code edits occurred during this final run. Independent supervisor/AgentCore and durable-audit reviews are **APPROVE for this slice**; main independently reviewed intent and prompt authority.

Intermediate failures are superseded by that final run: the rejected-decision punctuation regression after 124 passes; a new audit fixture using healthy non-STOP NOOP (which correctly creates no intervention), corrected to STOP; and an obsolete pipeline test after 328 passes that expected a deterministic nudge to replace remote NOOP. The updated pipeline assertion proves both no worker message and retention of missing-file evidence: NOOP does not mean the goal is complete. These are not separate additive test totals or a whole-repository/live-provider pass.

Source delivery is verified by the exact push receipt above. Keep future source pushes scoped to reviewed files; no force push or protection bypass. Next, continue the actual production delivery audit: Cursor stop delivery is still prepared before hook stdout/vendor acceptance, and complete same-session observed outcomes remain unproven. Separately implement the enforced hidden-data/no-network execution boundary before any real six-cell benchmark. Preserve all execution isolation/network/report gates in the previous capture checkpoint. No live six-cell pair or benchmark improvement is established by these local fake-model/ASGI regressions. The app remains **NO-GO** for submission; do not mark the active goal complete. Read all three specs before the next grind, split independent bounded work with subagents, audit every changed path, verify, and push each reviewed checkpoint.

## CURRENT HANDOFF — 4 Sep 2026 — nonce-bound Cursor observed capture

**Continuation of the active hackathon goal, not submission readiness. Read all three binding specs before continuing. No live model/provider call, installed/global hook change, deployment, package, freeze, or submission occurred in this slice. Verified source pushes remain authorized.**

**Pushed source receipt:** `ec64f63e724a6aac4d70c2012343580536594b0b` (`Capture nonce-bound Cursor observations and terminal failures`) is on `origin/main`. Local `HEAD` and `git ls-remote origin refs/heads/main` matched exactly and the working tree was clean. This paragraph is the documentation-only receipt follow-up. No push protection was bypassed.

### Implementation and evidence boundaries

- New schema-2 private Cursor control binds `run_id`, `arm`, `task`, resolved workspace, the preparation receipt's random nonce, and the unchanged public prompt SHA-256. It selects a private `receipts` spool outside the worker workspace. Both Cursor arms use the same capture surfaces. Capture identity is controller-run identity; vendor `generation_id` can change each user message and is not treated as a stable conversation identifier.
- The standalone hook observes `beforeSubmitPrompt` only after `continue: true` stdout successfully flushes. It hashes the exact submitted `prompt`, never a worker-supplied hash, and does not retain the prompt text. This is **submission release**, not backend acceptance. The official contract was refreshed from [Cursor hooks](https://prod.cursor.com/docs/hooks).
- Stop, delivery, prompt-release, and identity-only activity receipts retain hook-owned UUID, wall/QPC timestamps, canonical content hash, and controller binding. Generic activity excludes arbitrary response/tool/input text. Expected binding and spool are rechecked at writing: a changed/disappearing control cannot redirect a delivery, prompt release, or activity receipt to another run or the global drop. Valid schema-2 non-stop callbacks cannot post to the operator's unrelated live bridge. No global hooks were installed or changed.
- `benchmarks/cursor_capture.py` journals bounded, exclusive, fsynced observed receipts under `pex.cursor-observed-capture.v1`. It derives a prompt-release-to-terminal-stop interval only from valid bound, ordered, namespace-consistent receipts. This interval **already includes PEX and waiting**; worker-only time and total task-to-finalization time are unavailable, not fabricated from preparation, collector startup, or evaluation time.
- `run_live_this_cursor` no longer trusts `benchmark_started_at`, `benchmark_ended_at`, or `benchmark_human_intervention_log` from stop payloads. Human counts/logs remain `null`, human coverage stays `partial`, and observed prompts are not classified as human actions without origin proof. The journal has a distinct observed-capture hash; authoritative `raw_log_sha256` remains `null`. Missing callbacks, full vendor transcript coverage, authentication of shared-host writers, backend acceptance, and causal impact are still unproved.
- Baseline collection now validates canonical stop receipts too. Real collection uses the private run spool; legacy global stop drops cannot establish a run-bound start/timing record. The capture module is part of the controller source fingerprint. Never retrofit old receipts or flip manifest flags to green.

### Audit-driven lifecycle repair

Independent review found an inherited Cursor lifecycle gap: timeouts/exceptions had no immutable terminal abort, while deliberately non-presentation captures were written as completed official rows. The Cursor wrapper now owns the attempt after safety/schedule admission. Timeout, cancellation, and controller failures append declared terminal aborts; incomplete captures are stored in private `partial_result.json` as `diagnostic_only`, with an official `provenance_failure` abort. The run ID cannot resume. Failure journals are preserved. A pre-dispatch safety rejection still produces no workspace, worker, or result mutation.

### Verification status and next work

The stable six-file run (`test_pexbench.py`, `test_cursor_capture.py`, both Cursor hook contract files, `test_benchmark_execution_safety.py`, and `test_leakage.py`) passed **248 tests in 514.73 seconds** with no source edits during execution. Independent hook review is **APPROVE** after control-rebinding/control-loss fixes; its new file passed **17 tests**, with **12** legacy compatibility tests separately passing. The capture module passed **33** focused tests. These counts overlap; do not sum them into unique tests. After the final abort-classification refinement and added cancellation coverage, the affected lifecycle, execution-safety, and leakage selection passed **35 tests in 74.39 seconds**. Final scoped Ruff and `git diff --check` passed. Independent final lifecycle/classification review is **APPROVE**. This is offline evidence, not whole-repository or live-provider validation. Commit/push receipt follows below.

The final classification refinement distinguishes observation from execution: a `CursorCaptureTimeout` becomes `harness_disconnect`, **not** a claim that the worker exhausted its task budget. Cancellation becomes `operator_intervention`; explicit provenance mismatches become `provenance_failure`; evaluator/controller failures remain `controller_crash`. Missing installed hooks are a harness disconnect. Both-arm cancellation tests verify that the partial journal closes and the official abort prevents resumption.

The new journal checks aggregate size (64 MiB), count (10,000), strict receipt clocks/identities/binding/hash, recursive malformed input, and link/reparse paths. Its streaming digest includes only successfully written/fsynced bytes; bounded descriptor rereading verifies byte count, file identity, and exact digest before exposing the observed-capture hash. Changed bytes invalidate timing/hash. Only a matching session-start preamble can precede the benchmark prompt; preexisting worker activity, clock reversal/ties, identity drift, or a terminal that is not last suppress timing. Per-kind receipt-key allowlists remain a possible hardening step: the consumer retains bounded canonical same-binding receipt extras; local content hashes are not writer authentication.

Read-only plan still reports **2 execution blockers, 7 report blockers, `frozen: false`**. Host capability check found Windows 11 Pro with Docker/WSL installed, but the configured Docker Linux-engine pipe was absent and `wsl --list --verbose` showed only `docker-desktop`, stopped, version 2. This is a current-host diagnostic, not an enforced sandbox or permission to start services; no service/container/WSL instance was started.

After the final verification/push receipt below, continue toward an actual enforced hidden-data/no-network execution boundary and real independent same-session supervisor evidence. The existing execution blockers remain intact: ordinary Python subprocess isolation is not an OS sandbox, and Cursor network enforcement is still unimplemented. Full raw-event and human-action coverage remain prerequisites for presentation. Do not confuse this partial diagnostic collector with a scored live six-cell result. Keep the user's eight-pet scope, six-cell priorities, deadline, bounded subagent audits, and review-after-each-grind discipline; push verified updates without bypasses.

## CURRENT HANDOFF — 4 Sep 2026 ~22:15 WAT — pre-run safety restored

**This supersedes the earlier zero-execution-blocker claim and the previous paragraph's pending gate repair. The app is not submission-ready. The goal remains active; continue from real requirements and evidence, with all three specs as authority.**

**Pushed receipt:** safety source checkpoint **`04e77f8dc909917d34fe32281837a8f6b5f8844c`** (`Restore implementation-owned benchmark execution gates`) is on `origin/main`; `git rev-parse HEAD` and `git ls-remote origin refs/heads/main` matched exactly, and the tree was clean. This paragraph is the receipt-only follow-up; no protection bypass or live run was used.

The Cursor receipt slice below was committed as **`bff82bdcdce28546bbb504020ad750ab88264b71`** (`Bind Cursor continuation to ordered hook receipts`), pushed to `origin/main`, and verified against `git ls-remote` with exact local/remote equality and a clean tree.

The separate safety repair now makes `_execution_preflight_blockers(arm)` check the suite, implementation-owned runtime capability blockers, and static anti-leakage rules. Current reality is explicit: **no OS-isolated worker/PEX/hidden-evaluator backend is implemented**; plain `python -I` is not a sandbox. Cursor additionally has no controller-enforced runtime network receipt; this Cursor-specific blocker does not apply to Codex arms. There is no environment switch or manifest string that can assert these capabilities into existence.

The real four-arm Cursor/Codex entrypoints and CLI `prepare`, `run`, and `evaluate` reject before worker startup or workspace creation. Pre-dispatch static checks now cover the existing treatment-suffix prohibition, benchmark-identity branches in six supervisor-boundary files, and known private evaluator/oracle references. These lexical checks are defense-in-depth, not a replacement for OS isolation. The evaluator library itself remains process-bounded and must not be used to run untrusted candidate code outside a future enforced backend.

Post-run logs, actual continuation/outcome, source-commit receipts, and natural-task provenance remain report concerns, not circular prerequisites for generating those facts. Report/freeze still include the safety blockers. Read-only `four_arm.py plan` now reports **2 execution blockers, 7 report blockers, `frozen: false`**. Tests that create fully synthetic presentation fixtures explicitly monkeypatch the missing runtime capability; this test-only bypass is not product evidence and no real manifest was frozen.

Verification: **23 passed** across new execution-safety and existing leakage tests; **9 passed, 112 deselected** across affected existing preflight, synthetic freeze, and Cursor collection tests; scoped Ruff and `git diff --check` clean. Two early new-fixture attempts used a nonexistent executable rejected by the real Codex transport constructor. The final fixture constructs the transport with the existing Python path and patches `start` to fail if reached; the passing tests prove the gate rejects before any process starts. No provider/model turn, global hook mutation, installer, deployment, live benchmark, or submission occurred.

Final adversarial review found and forced closure of an additional injected-transport bypass: an unknown real wrapper previously entered the ungated fake path because it was not `CodexStdioTransport`. Only the **exact** `CodexAppServerTransport` class can now use the synthetic non-presentation path; its subclasses and unknown wrappers are rejected before workspace, transport, or evaluator effects. Actual stdio transports remain gated. **Final verdict: independent APPROVE**, with **2 additional adversarial tests** and clean Ruff/diff check. Final main verification is **25 safety/leakage tests passed**, the prior **9 compatibility tests passed**, and **3 synthetic Codex compatibility tests passed (112.28 seconds)**. The 25-test run supersedes the earlier 23-test safety receipt; do not sum overlapping test runs into a unique-test total.

**Next work:** implement controller-owned Cursor start/timing, human-action accounting, and canonical append-only raw-event capture, retaining the local-sequence limitations below. Separately design and verify an actual hidden-data/no-network execution boundary before enabling real benchmark calls. Do not unblock by flipping manifest statuses, deleting the blockers, calling the evaluator directly, or relabeling a synthetic row. The six-cell development exercise remains distinct from presentation/freeze and still needs real same-session model evidence. Use bounded independent subagent audits and review/tests after each coherent repair; push verified changes and record exact receipts.

## CURRENT HANDOFF — 4 Sep 2026 ~22:00 WAT — Cursor local receipt chain hardened

**Read the three binding specs (`PEX_CORE_SPEC.md`, `PEX_BUILD_SPEC.md`, `PEX_IMPLEMENTATION_RECOVERY_SPEC.md`) before continuing. This checkpoint is offline evidence only. Overall submission remains NO-GO, the manifest remains unfrozen, and no live worker/provider run or global Cursor-hook mutation occurred.**

### What changed

- The standalone Cursor hook now assigns opaque UUID receipt filenames; incoming `stop_id`, kind, timestamps, parent references, or hash fields cannot choose the path or manufacture receipt metadata. Exclusive creation fails closed on collision without replacing earlier evidence.
- Receipts use `pex.cursor-hook-receipt.v1`, hook-owned wall and high-resolution monotonic timestamps, and SHA-256 of canonical UTF-8 JSON excluding only `receipt_sha256`. The original sanitized stop is held in invocation-local memory; a delivery cannot adopt a supplied or rewritten on-disk parent.
- A delivery binds the initial receipt's ID/hash and the exact emitted follow-up's UTF-8 SHA-256. The hook preserves redaction, records whether it changed the message, and records only after stdout successfully flushes. A pipe failure creates no delivery receipt and does not append a second JSON response. Evidence is explicitly `hook_stdout_flushed`, never vendor acceptance.
- The treatment waiter validates all receipt hashes and requires initial stop < delivery < later stop under the monotonic clock, with nondecreasing wall time, the exact resolved workspace, and the identical set of `(identity field, value)` pairs. `conversation_id=X` cannot be substituted by `session_id=X`; changed or malformed secondary identifiers also fail.
- Discovery order cannot imply event order. Legacy receipts, changed receipt bytes, ambiguous deliveries, unrelated event kinds, malformed clocks, clock reversal, wrong parent/message hashes, and redacted follow-ups cannot confirm the chain. The returned evidence scope is `ordered_local_hook_receipts`, with three receipt hashes and the exact follow-up hash.
- Python 3.11 on this Windows host reports `GetTickCount64()` and wall-clock resolution of 15.625 ms. The initial regression run exposed equal timestamps. `perf_counter_ns()` uses monotonic host-wide `QueryPerformanceCounter()` at 100 ns resolution; separate-process ordering and coarse wall-clock ties are covered without fabricating timestamps.

### Audit and remaining boundaries

Independent Cursor review: **APPROVE for this narrow slice**, with **31 passed, 90 deselected**, **11 passed, 37 deselected**, and Ruff clean. The first focused main run had two clock-resolution failures; the corrected selection passed **37 tests**. A broader run was invalidated by edits during execution (67 passed, two failures: source-fingerprint drift and a stale loaded assertion against newly loaded code). It is not a final verification receipt; a stable-source rerun follows before push.

**Final stable-source receipt:** `uv run pytest -q tests/unit/test_pexbench.py tests/contract/test_cursor_hooks.py --maxfail=1` completed **169 passed in 378.58 seconds**, with no source edits during the run. Ruff on the four changed Python files and `git diff --check` passed. This is not a whole-repository or live-provider validation. Commit/push follows this receipt; verify the exact remote hash before calling the update delivered.

These hashes detect changed content; they do not authenticate writers on the shared host. Workspace scope is opaque/per-run but not a controller nonce. A later stop after flushed stdout is not proof of Cursor acceptance, causal impact, or a correlated supervisor audit/outcome. Full controller-owned execution timing, human-action accounting, canonical append-only raw capture, and runtime isolation are still missing. Do not set manifest integrity flags to satisfied on this receipt alone. Do not rewrite/backfill legacy drops.

**New safety finding supersedes the previous zero-execution-blocker interpretation:** independent review of `cbd5427` found that CORE §16 requires hidden-evaluator/untrusted-code isolation and pre-run leakage checks before execution, and BUILD §34.4 requires enforced network fairness. Moving these to report-only is too permissive. The current evaluator executes candidate code using ordinary `python -I`, which is not a filesystem/network sandbox. **Do not launch a real benchmark through the current execution gate.** Correct it next without reintroducing a circular requirement for post-run logs/outcomes. Natural-task provenance and finished result receipts can remain report-only; actual safety cannot be bypassed by a manifest assertion. A development-only six-cell ledger must remain separate from presentation results and cannot waive isolation.

Continue with focused subagent review after each coherent repair, retain the user's eight-pet scope and six-cell priorities, and push verified source updates. Do not claim the app is perfect from unit tests; persistent progress is toward real same-session supervision and submission evidence, with deadline and authorization gates intact.

## CURRENT HANDOFF — 4 Sep 2026 ~21:34 BST — execution gate separated from report/freeze gate

**The binding Cursor/benchmark sections of all three specs were reread before this slice. This section supersedes the 21:16 next-action paragraph only. The manifest remains unfrozen and overall submission state remains NO-GO.**

The previous runner used one `_experiment_preflight_blockers()` list for two incompatible jobs: deciding whether a controlled run could safely begin and deciding whether its evidence could support a presentation/freeze claim. That created a circular gate because missing raw logs, source-commit receipts, and genuine same-session continuation blocked the runs that must generate those receipts.

`benchmarks/four_arm.py` now has two explicit layers:

- `_execution_preflight_blockers()` rejects an invalid benchmark package/suite. It gates Cursor prepare, Cursor wait/live collection, Codex live collection, and the CLI live path.
- `_report_readiness_blockers()` includes execution blockers plus every former hard claim gate: natural-task provenance and isolated hidden-evaluator boundary, complete immutable raw logs, genuine Cursor same-session treatment, verified source commits, and controller-verified Cursor network policy.
- `_run_blockers()`, coherent-run selection, and freeze continue to use report readiness. `_experiment_preflight_blockers()` remains only as a backward-compatible alias for the full report NO-GO list.
- `four_arm.py plan` now prints `execution_preflight_blockers` and `report_readiness_blockers` separately instead of the ambiguous `preflight_blockers` key.

This does **not** weaken presentation rules or call controlled fixtures submission evidence. It allows development evidence collection while keeping those rows unable to freeze until the full report gate is green.

Verification:

- focused Cursor/preflight/freeze selection: **21 passed, 70 deselected**;
- direct invalid-suite and honest-manifest tests after the naming cleanup: **2 passed**;
- live `plan` command: `EXECUTION_BLOCKERS=0`, `REPORT_BLOCKERS=5`, `FROZEN=False`; the five blockers are the exact expected natural-task/evaluator boundary, raw-log, same-session treatment, source-commit, and Cursor-network gaps;
- independent post-fix review: **APPROVE** for this split, with a separate **2 passed** focused run and direct verification that every prepare/live call uses execution safety while `_run_blockers`, coherent selection, and freeze retain report readiness;
- Ruff passed and `git diff --check` passed.

**Next exact slice:** add controller-owned Cursor timing, human-action receipts, and an append-only canonical raw event log. Do not trust worker/hook-provided benchmark timing, do not call observe-only hooks `+PEX`, and do not alter the global installed Cursor hooks while implementing offline contracts/tests.

Independent review is **APPROVE**. Source checkpoint **`cbd5427cf87e61ce30e61c7283fcb1bb3d34ec5a`** (`Separate benchmark execution and report gates`) was pushed to `origin/main`; local and remote hashes were verified equal. No push-protection bypass was used. This paragraph is the receipt-only follow-up.

## CURRENT HANDOFF — 4 Sep 2026 ~21:16 BST — Codex same-session resume gate repaired

**The three binding specs were reread before this slice. This section supersedes the 20:22 Codex next-action text. The six-cell demo remains the only execution workstream; benchmark freeze, deployment, spending, packaging, and Devpost submission remain unauthorized. Overall submission state is NO-GO.**

### What is now implemented

Discovered Codex threads can no longer be mutated merely because they appeared in `thread/list`. Before PEX sends the first same-session intervention on an App Server connection, `CodexAdapter` now performs the authoritative state transition:

1. acquire one bounded adapter delivery lock;
2. capture the exact canonical PEX session binding and initialized App Server connection generation;
3. issue only `thread/resume {threadId, excludeTurns: true}`;
4. require the exact resumed thread id, absolute matching top-level and nested workspace paths, bounded top-level model/provider receipts, and a thread that can accept direct input;
5. re-fetch and revalidate the PEX session, goal, project, workspace, transport identity, and connection generation after the awaited resume;
6. issue `turn/start` on that same captured transport while still holding the delivery lock;
7. require a correlated bounded `turn.id` before recording acceptance.

The loaded-thread cache is private and keyed to `(transport identity, connection generation, thread id, canonical project/workspace binding)`. A close/restart of the same transport object or a replacement transport therefore forces a fresh resume. A newly created isolated `thread/start` session is already loaded on that connection and does not perform a redundant resume before its first turn. No uncertain `turn/start` is retried.

The production/default safety contract remains unchanged: `thread/start` uses `sandbox: "workspace-write"`; `turn/start` uses `sandboxPolicy.type: "workspaceWrite"`, `networkAccess: false`, and `approvalPolicy: "never"`. Do not change those values based on casing guesswork.

### Audit corrections made before accepting the slice

The first draft was deliberately not pushed after the independent auditor found real races. The final implementation:

- holds the delivery lock across both resume and turn creation, not resume alone;
- rejects `attach_transport` while a delivery is in flight;
- keys loaded state to a monotonically increasing connection generation, so same-object process restarts invalidate it;
- revalidates canonical goal/project/workspace and the captured connection after the resume await;
- does not depend on a fabricated `thread.projectId` or nested `thread.model` field; those are not authoritative v2 resume contracts;
- keeps connection-local loaded truth out of durable session metadata;
- prunes loaded cache entries when stale App Server sessions are dropped;
- serializes all Codex delivery through one lock instead of retaining an unbounded per-thread lock map.

### Regression evidence

- New adversarial adapter suite: **51 passed** after final formatting. It covers resume-before-turn order, exact request parameters, cached second send, strict serialization of two concurrent sends, isolated-thread no-resume behavior, same-object restart invalidation, transport replacement invalidation, attachment rejection mid-delivery, canonical project and goal changes during resume, wrong thread id, missing/mismatched workspaces, missing model/provider, `canAcceptDirectInput: false`, resume rejection/timeout, and no retry after an uncertain turn.
- Independent post-fix audit: **APPROVE**. The auditor's separate run of the three affected files completed **127 passed** with one non-failing `PytestUnhandledThreadExceptionWarning` from an aiosqlite teardown worker after event-loop close. The warning is cleanup debt, not a claimed pass over a failure, and should be removed in a later bounded slice.
- Full Codex pipeline/fleet/live-contract partition after the fixture update: **77 passed, 4 skipped** in 2:01.
- Broader Codex/benchmark partition reached **181 passed** before finding one stale JSONL fake App Server that lacked a `thread/resume` response. The fixture was updated to implement the real contract; its focused test passed and is included in the 77-test partition above. This was a fixture-contract failure, not a weakened production check.
- Four closed-loop pipeline tests that were canceling a still-valid STOP evaluation after a fixed four-second scheduling window now use a 40-second maximum wait. Under current machine load all four plus the real JSONL transport test passed: **5 passed** in 43.98s. Assertions and product timeouts are unchanged; only the test harness scheduling allowance changed.
- Ruff passed on every changed Python file. `git diff --check` passed; repository-wide LF/CRLF notices are informational.

The full 1,843-test Python suite was **not** rerun in this slice; do not claim a new whole-suite receipt. The last whole-suite evidence remains the 20:22 checkpoint below. No live Codex model turn and no provider quota were consumed.

### Current truth and next exact slice

Codex offline same-session delivery is now substantially safer, but there is still no valid Codex GPT-5.4-mini baseline/+PEX result. A live model run remains quota/action-time gated and must verify the exact requested worker model; this checkpoint does not authorize or claim it.

The highest-impact offline blocker is now Cursor. The read-only Cursor/benchmark audit found:

1. `four_arm.py` mixes execution-safety preflight with freeze/report-readiness, making evidence generation circular;
2. Cursor hook sanitization drops controller timing and human-intervention fields required for a truthful live row, and Cursor has no canonical append-only raw log equivalent;
3. continuation validation is not yet monotonic or hash-bound to the originating intervention/audit/outcome;
4. the installed Cursor hook is observe-only and must never be labeled `+PEX`;
5. evaluator execution is process-bounded but not a disposable no-network sandbox, so current results remain development evidence.

**Next exact implementation slice:** split Cursor run-safety from freeze-readiness, add controller-owned timing/action/raw receipts, then make the continuation chain monotonic and hash-bound with regressions. Keep the six-cell demo ledger separate and `frozen: false`. After independent review, commit/push and record the remote receipt. Do not launch or impersonate the separate Composer 2.5 worker session.

### Push receipt

Independent review is **APPROVE**. Source checkpoint **`8596c9e4986c70c7d2620617ad4da9644b3d5003`** (`Harden Codex same-session resume delivery`) was pushed to `origin/main`; local and remote hashes were verified equal with `git rev-parse` and `git ls-remote`. No push-protection bypass was used. This paragraph is the promised receipt-only follow-up.

## CURRENT HANDOFF — 4 Sep 2026 ~20:22 BST — audited source checkpoint and push policy

**This section supersedes the 18:52 checkpoint only where stated. The three specs still prevail, the six-cell demo remains the only execution workstream, and overall submission state remains NO-GO.**

### Operator authorization changed: commit and push verified updates

The operator explicitly ordered: **“always push changes per update, let codebase be neater too.”** The old prohibition on commits is therefore withdrawn. For every coherent implementation slice:

1. audit the exact diff and test it in proportion to risk;
2. exclude `.env`, secrets, `benchmarks/results/_scratch/`, `.opencode/`, generated caches, and unrelated machine-bound evidence;
3. commit on `main`, push `origin main`, and verify the remote commit;
4. record the receipt here and in `STATUS.md`.

This is authorization to preserve verified source progress. It is **not** authorization to freeze the benchmark, publish/deploy, spend money or quota, package an installer, or submit Devpost. Those gates remain separate.

### What this agent audited and repaired

Three independent read-only audits covered OpenCode, Codex, and Cursor/benchmark code after rereading all three binding specs. The OpenCode slice then received a second adversarial review and was approved narrowly.

- `OpenCodeAdapter.send_message` no longer treats an old identical user message as proof that a new intervention was delivered. It snapshots message IDs before `prompt_async`, serializes sends per exact session, polls a bounded number of times, requires one new exact user/session/text receipt, and returns delivery-uncertain on zero or ambiguous candidates.
- Added regressions for repeated identical prompts, delayed message visibility, missing receipts, concurrent identical sends, cross-session receipts, ambiguous same-session collisions, and lock-map exhaustion attempts.
- Removed the plugin's hard-coded `C:\Users\JosephMayo\...\_scratch` debug file sink and startup log writes. Added a security regression that forbids machine-specific or filesystem-debug sinks in the plugin.
- Corrected the OpenCode integration README: a rotated hook token is inherited only after OpenCode restarts; the plugin cannot reread a changed parent-process environment.
- Added `.opencode/` to `.gitignore`; it contains local package dependencies and logs, not source.
- Repaired one stale pipeline test fixture so it exercises the production-required project binding (`project_id` and `cwd`).
- Increased the Windows bridge-lock subprocess test timeout from 10 to 30 seconds. Under heavy concurrent CPU load the child import exceeded 10 seconds even though the production lock behavior was correct; the test now retains the same assertions without a machine-speed assumption.

### Verification receipts for this checkpoint

- Source checkpoint **pushed and remote-verified**: `cda1b8eb8955bebc8e4abe4acd5cabe9d5e4bffc` (`main` and `origin/main` matched after `git ls-remote`). Commit message: `Checkpoint audited PEX supervisor and integration foundation`.
- The first push attempt was blocked by GitHub push protection because a redaction test contained a literal Slack-token-shaped canary. The canary is now assembled at runtime, its file passed **21 tests**, the unpushed commit was amended, and the successful push used no secret-scanning bypass.

- Serial whole Python suite before the two fixture-only test repairs: **1,822 passed, 21 skipped, 1 failed** in 30:12. The single failure was the missing project binding in `test_progress_event_does_not_pollute_intervention_log_with_noop`; no production assertion failed.
- Repaired pipeline-session file: **5 passed**.
- Bridge auth/lock file after timeout hardening: **16 passed, 2 skipped**.
- Contract/integration/chaos partition: **53 passed, 16 skipped**.
- OpenCode receipt/security review: independent **APPROVE**, with **9 targeted tests**, Ruff, JavaScript syntax, and diff check passing.
- Repository Ruff: **all checks passed**.
- Desktop: **62/62 tests passed** and production Vite build passed (**52 modules**).
- `git diff --check`: no whitespace errors; Windows LF/CRLF notices are informational.

The interrupted parallel unit/e2e rerun is **not** a release receipt. It exposed the 10-second Windows timing assumption above and was stopped; do not quote it as a complete gate. No live worker/model run was performed in this checkpoint.

### Current integration truth and next exact action

- OpenCode observe via real HTTP/SSE is available, but there is still no valid same-task free-model baseline/+PEX pair. The latest real STOP fell back to safe NOOP after the Strands provider failed; it proves neither treatment nor outcome lift.
- The installed Codex `0.153.0-alpha.5` App Server schema was generated and inspected locally. `thread/start.sandbox = "workspace-write"` is correct; `turn/start.sandboxPolicy.type = "workspaceWrite"` is also correct. Do **not** apply the earlier audit's casing change.
- The real Codex blocker is that `thread/list` discovery does not establish the thread as loaded in PEX's App Server process. Add a correlated `thread/resume` exactly once before the first intervention to a discovered thread, verify returned thread identity/project binding, and test resume-before-turn ordering plus failure/ambiguity behavior.
- Cursor remains observe-only in the installed global hook and must not be labeled +PEX. Its run-safety gate must be separated from freeze-readiness, and treatment evidence needs controller-owned timing/raw receipts and monotonic continuation binding.
- The generated pet QA tree under `apps/desktop/src/pets/_audit/` is about 79 MB and contains machine-bound provenance. Do not sweep it into Git. The source fleet remains exactly eight pets; generated release evidence needs a separate portability/release review before tracking.
- `benchmarks/manifest.yaml` remains `frozen: false`. There is no scored public leaderboard. Overall state remains **NO-GO**.

**Next exact implementation slice:** make discovered Codex sessions resume authoritatively before same-session PEX delivery, then obtain independent review, run focused adapter/pump tests, commit, push, and verify the remote receipt. Do not spend live model quota until that offline gate is green.

## CURRENT HANDOFF — 4 Sep 2026 ~18:52 BST — next agent reads this first

**This section supersedes older “chase until submit / loop all night / freeze theater” instructions in this file and in CreateGoal text.** The operator just narrowed scope after a full day of contest testing with little demo-ready evidence. Follow **this** checkpoint. Older dated sections below are audit history, not current orders.

### Mandatory first action — always read the three specs

Before inspecting code, before touching 7420, before seeding a workspace, before claiming +PEX:

1. `docs/PEX_CORE_SPEC.md`
2. `docs/PEX_BUILD_SPEC.md`
3. `docs/PEX_IMPLEMENTATION_RECOVERY_SPEC.md`

Read them **every turn**, not once. They prevail over this handoff on conflict. This file is implementation context, **not a fourth spec**.

CORE §1: PEX is a **separate supervisor that observes after work began**, not extra prompt text. If the demo is “we prepended a system prompt,” it is wrong.

BUILD §0: the **submission empirical claim** is Cursor±PEX and Codex±PEX (task success + human-management burden). The operator now also wants a **third pair: OpenCode (free model) ±PEX**, as a hard task that fails without monitoring. Do not invent a fifth harness. Cut everything else.

RECOVERY: a canned “tests still fail, continue” blast is not supervision. Closed loop = observe real state → decide NOOP or a **specific** evidence-grounded intervention.

### What the operator just ordered (do this; cut the rest)

> Make sure OpenCode, Cursor, and Codex integration **all work**. Cut the rest and perfect these. It has been a whole day with nothing to show. We are supposed to **evaluate agents without and with PEX**:
>
> - **OpenCode** + a **free** model, with and without PEX
> - **Cursor** — **another session** using **Composer**, with and without PEX
> - **Codex** using **GPT-5.4 mini**, with and without PEX
>
> Same **hard task** for each pair: without monitoring they should **most likely fail, go the wrong direction, or end the turn prematurely**. With PEX they should be **followed and corrected**. These things should not take a day.

That is now the **only** execution workstream. Not AWS. Not AgentCore. Not builder.aws.com posts. Not pets. Not freeze. Not Devpost. Not more PexBench task packages. Not looping Muse quota. Not Chrome/WinError archaeology beyond keeping the companion alive. Not four-arm `freeze` until these six cells exist with honest labels.

### Hackathon / winning (still true; do not submit)

- Contest: **AWS + Devpost Agents for Humans**, track **Professional Agents**.
- Deadline: **14 Sep 2026 17:00 PDT**.
- Devpost: `https://agentsforhumans.devpost.com/`.
- Operator email on record: **ayandajoseph390@gmail.com**.
- **Do not Devpost-submit** unless the operator explicitly says submit at action time.
- Winning, per BUILD, is **not** “the model got smarter.” Winning is: a human can run agents they already use; PEX babysits; **measured delta** with vs without PEX on premature stop / drift / false completion.
- No scored public leaderboard is retained. Do not invent a rank.

### Durable goals (never delete)

- Cursor CreateGoal in this thread: keep **active**. Operator deletes only at submit. **Do not** `UpdateGoal` complete. **Do not** delete it.
- PEX contest goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`**. Home **`C:\Users\JosephMayo\.pex\contest-goal`** (not default `~/.pex`). Never delete. Never bind isolated bench workers to this goal. Operator deletes only at submit.
- Bridge: `http://127.0.0.1:7420`. Token file `C:\Users\JosephMayo\.pex\contest-goal\bridge.token`. Hook token `C:\Users\JosephMayo\.pex\contest-goal\opencode.hook.token` (do not print).
- Git identity is already set. **Do not `git config`.** Do not commit unless the operator asks.

### Standing prohibitions

- Do **not** spawn another Cursor from four-arm / this desktop session (`four_arm.py` refuses it). Cursor **Composer** with/without PEX must be **another Cursor session** (CLI/agent or a second window the operator opens), not this Grok 4.6 chat pretending to be Composer 2.5.
- Do **not** freeze `benchmarks/manifest.yaml` (`frozen: false` stays). Isolated TASK.md rows **do not count** for freeze.
- Do **not** `PATCH /config` for overlays (CORE/BUILD: ephemeral overlay via plugin/hooks).
- Do **not** spoof `POST /v1/adapters/opencode/plugin-heartbeat` with the **operator** bearer and call that CORE overlay. Isolated scripts that did this are **not** overlay proof.
- Do **not** bind bench sessions to the contest goal.
- Do **not** loop Muse 001 hangs (180s / `hung-read-root`).
- Do **not** kill/restart `pex-bridge` casually; on Windows it dies with **WinError 64**, then a second start fails on **SQLite lock** until you `taskkill` the zombie Python PID. Prefer `taskkill /F /PID`, not `Get-CimInstance` (Call cancelled).
- Do **not** GET overlay-runtime from a Python poller in a tight loop; that was wedging 7420. Let the **plugin** GET overlay-runtime.
- PowerShell: `;` not `&&`. Python: `uv run` from `C:\Users\JosephMayo\Projects\pex`.

### Runtime snapshot at handoff (verify; do not assume)

- Contest companion: last known **GET 200** on `goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7` after restarts. Process may have died; **verify first**.
- OpenCode: last start was `opencode serve --port 4096` from isolated 001 workspace `C:\Users\JosephMayo\.pex\pexbench\workspaces\ws_ed0e0029fd8d5df0` with fresh hook `hook_credential_525fa493a94a4039b1b41e2746e80201` (expires ~2026-09-05T01:48:45Z). The **previous** serve (`761255`) **exited 1**; a replacement serve was started. **Verify 4096 health** and `message=init` before POST `/session`.
- Global plugin only: `C:\Users\JosephMayo\.config\opencode\plugins\pex-plugin.js` (source of truth `integrations/opencode-plugin/pex-plugin.js`). Workspace and repo copies should stay `.off` to avoid dual-load **403 session binding mismatch**. OpenCode sessions often show **`projectID=global`**, so **workspace plugins never load**.
- Plugin: named export `export const PexPlugin` (default `{ server }` broke loading). `AbortController` not `AbortSignal.timeout`. Factory heartbeat delayed; `event` hook is now a **no-op** (was flooding 7420). `chat.message` heartbeats with `sessionID`. `experimental.chat.system.transform` + `tool.execute.before` apply overlay. Module-level `sharedLastHeartbeat`. Fetch abort **8000ms**.
- Zen/Muse API key lives in repo `.env` (`PEX_SUPERVISOR_API_KEY` / `PEX_ZEN_API_KEY` / `OPENCODE_API_KEY`). **Do not paste.** Muse 1.3 on the bridge often logs **Quota violation** / **Call cancelled** → interventions **n=0**.
- `aws sts get-caller-identity` → **NoCredentials**. No AgentCore. No Builder post. Operator said **cut this**.
- Chrome/devtools hits `GET /` and `GET /json/version` on 7420 (404). Correlates with WinError 64; do not fake a CDP endpoint.

### Operator-narrowed 6-cell experiment (the only demo)

One **hard** public task (premature-stop / wrong-direction / early-exit). Same package for all six cells. Current harder seed hash for `pexbench_001_premature_stop`:

`c55436d006fa8ad0ff2838d98a73fb81eb5159b92ce49bda18c673e9f07f8c3e`

(LF evaluator writes; unit test `test_evaluator_seed_writes_lf_so_protected_public_tests_match_spec` **passed** 4 Sep.)

| Cell | Harness | Worker model | PEX | What “works” means |
| --- | --- | --- | --- | --- |
| 1 | OpenCode | **Free** Zen worker (use `big-pickle` or current free id; **not** Muse as worker) | off | Completes or **fails as expected** (premature stop / stub left). Evaluator public+hidden. |
| 2 | OpenCode | same free model | **on** | Live attach to a **new bench goal**, real plugin overlay (hook token), supervisor may nudge. Evaluator. Contest goal **unbound**. |
| 3 | Cursor | **Composer 2.5** in a **separate** Cursor session | off | Isolated workspace + TASK.md. This Grok chat is **not** the worker. |
| 4 | Cursor | Composer 2.5, same session style as 3 | **on** | Same-session Cursor+PEX (hooks that actually treat, not observe-only) **or** honest label: observe-only ≠ +PEX. |
| 5 | Codex | **GPT-5.4 mini** (confirm exact vendor `modelID`; scratch pinned `gpt-5.4-nano` earlier — **do not mix**) | off | Live App Server / `thread/start` if it works; else record the exact failure. |
| 6 | Codex | same mini model | **on** | Live attach + evidence-grounded intervention, not prompt suffix. |

**Success for the operator:** all six run, results in one table, honest about attach vs prompt-policy, hard task actually bites the control arm.

Cap wall-clock. Do not spend another day on freeze blockers, pets, or AWS.

### Honest audit of previous work (do not trust STATUS.md blindly)

STATUS.md still contains **older checkpoints** where isolated Muse/Cursor 001–003 are called **success**. Those successes were often:

- **easy** TASK.md packages, later **rewritten harder** (4 Sep “microtasks made substantially harder”). Old successes **do not** score the current package.
- **operator-bearer spoofed** `plugin-heartbeat` (`iso001_muse13_pex.py`, `iso001_bigpickle_pex.py` POST heartbeat via `_bridge` operator token). That is **not** CORE overlay.
- Isolated TASK.md **explicitly not freezeable** four-arm.
- Cursor Grok 4.6 control 001 **success** on harder package (`iso001_grok46_cursor_ctrl_*.json`) — that is **control**, this session, **not Composer**, **not presentation freeze**.
- Isolated Muse 001 +PEX later **NotImplementedError** on stub (`iso001_muse13_pex.result.json`, `iso001_bigpickle_pex.result.json`) after harder package / premature eval.
- Isolated OpenCode +PEX **002** (`ws_6d4ec95d6f9fb232`, `ses_f93211f82ffelyyQ4oNRdClovp`) evaluator **success** with **HTTP/SSE attach**, interventions **n=0**.
- Four-arm freeze 4 Sep: `frozen: false`, `wrote: false`, blockers include no coherent four-arm file, synthetic_smoke junk, no presentation rows for cursor/codex ±pex 001–005, Cursor same-session unsatisfied, Codex live `thread/start` unreliable / `DeliveryUncertainError`.

**This Grok session (4 Sep evening) actually proved:**

1. Evaluator LF seed hashes (unit test pass).
2. Real OpenCode plugin factory + **plugin** `GET /v1/sessions/opencode:ses_f927fb021ffe7lUY4QNrLYgIKM/overlay-runtime` **200** (hook path). Contest stayed 200 when Python did **not** poll overlay-runtime.
3. Attach of that session to bench **`goal_95e9fa13064f4d71b7a2ee3321f7b452`**, contest **not** bound, interventions **0**.
4. `benchmarks/manifest.yaml` still `frozen: false`.

**This session failed / must not repeat:**

- Overlay-runtime **TimeoutError** from Python while companion **WinError 64**.
- Dual plugin copies → 403 bind mismatch.
- Workspace-only plugin with `projectID=global` → factory never ran.
- OpenCode `POST /session` hang until workspace `.opencode` has `package.json` + lock + `node_modules` (`@opencode-ai/plugin` 1.18.19) and `OPENCODE_DISABLE_MODELS_FETCH=true`, wait for log `message=init`.
- Serve cwd for bench = **isolated workspace**, not the full pex repo.
- Fresh hook credential **per bind**; first session-bearing heartbeat binds; another session cannot reuse it. After bind, bootstrap + OpenCode **restart** with new `PEX_OPENCODE_HOOK_TOKEN` env (plugin reads **env**, not the token file live).
- `iso_models.py` says isolated OpenCode workers = **big-pickle**, supervisor = Muse. Operator now wants **free OpenCode worker ±PEX**. Keep Muse as **PEX supervisor**, not as the six-cell worker.

Prepared but **not run** at handoff: isolated 001 workspace `C:\Users\JosephMayo\.pex\pexbench\workspaces\ws_ed0e0029fd8d5df0` (seed hash above), `.opencode` copied from `ws_6d4ec95d6f9fb232`, hook bootstrapped. Prep json: `benchmarks/results/_scratch/iso001_muse13_plugin_prep.json`. Do **not** spoof heartbeat if you use it. Prefer the **6-cell** design above rather than another Muse 001 loop.

Scratch scripts live under `benchmarks/results/_scratch/` (gitignored). Treat them as contaminated unless you read them: many spoof heartbeat.

### How to run the six cells without another wasted day

1. Verify 7420 contest GET 200. If WinError 64: kill **pex-bridge Python PID**, then `uv run pex-bridge --host 127.0.0.1 --port 7420` with `PEX_HOME=C:\Users\JosephMayo\.pex\contest-goal`. Prefer **no** `PEX_OPENCODE_URL` if SSE+Muse quota is melting the event loop; CORE overlay plugin does not need SSE. Honesty: SSE observe ≠ overlay.
2. OpenCode: one global plugin; wait `init`; `POST /session?directory=<workspace>`; `prompt_async` with **free** model; **do not** Python-GET overlay-runtime; grep bridge log for `plugin-heartbeat` and `overlay-runtime` **200**.
3. Cursor Composer: open **another** Cursor session on a **new** seeded workspace. Control arm: no PEX attach. Treatment: live PEX attach + hooks that can act. If hooks remain observe-only, **say so** in the result JSON.
4. Codex GPT-5.4 mini: one live thread with, one without. If `thread/start` is still `DeliveryUncertainError`, fix that adapter **just enough** to run the two cells; do not rebuild the universe.
5. Evaluate with `benchmarks/evaluator.py` on the seeded workspace (public + hidden). Never leak hidden cases into the worker tree.
6. Write **one** comparison JSON (control vs +PEX × three harnesses). Keep four-arm **unfrozen**.

### Integrations to perfect (only these)

- OpenCode: `integrations/opencode-plugin/pex-plugin.js`, `services/bridge` OpenCode adapter + hook overlay-runtime.
- Cursor: hooks under `~/.cursor/hooks.json` (backup `hooks.json.pex-backup`); `four_arm.py` Cursor arms; same-session treatment still `not_yet_satisfied` in the manifest.
- Codex: App Server adapter; `raw_capture`; do not claim +PEX if attach 404 / delivery uncertain.

Starter desktop inventory in older handoff text listed more apps. **Operator: cut the rest.** Do not expand Hermes/Devin/Qwen.

### CreateGoal / todos

Leave the Cursor contest CreateGoal **active**. Do not complete it. The objective text still mentions Muse-for-OpenCode-arms, AWS bonus, freeze-unfrozen, isolated 001 loops — **operator override 18:52**: six-cell OpenCode-free / Cursor-Composer / Codex-mini, hard task, with vs without PEX.

---

## ARCHIVE — Handoff transfer for next operator — 3 Sep 2026, live continuity, GO-FOR-PERFECTION


This is a direct continuity handoff. The next operator must continue from this exact file plus the three binding specs:

- `docs/PEX_CORE_SPEC.md`
- `docs/PEX_BUILD_SPEC.md`
- `docs/PEX_IMPLEMENTATION_RECOVERY_SPEC.md`

Do not treat this as a "handoff memo"; treat it as continuation authority.

### Prime directive — chase one goal at a time until PEX bags the hackathon

The deadline is **September 14, 2026, 5:00 PM PDT**, Professional Agents track,
`https://agentsforhumans.devpost.com/`. The user's explicit instruction to the
next agent is:

> "create a goal and chase it, till pex is super perfect and would bag the
> hackathon, use subagents for audit and review and don't end its turn till we
> submit."

Operate against that directive as follows:

1. **Create one durable PEX goal at the start of your turn** that captures the
   real submission-quality objective: a correctness-first independent
   supervisor that a human can open alone to manage many agents, with truthful
   evidence, auditability, real closed-loop proof, and benchmark proof. Use the
   existing goal-control API (`POST /v1/goals` with an idempotency key) or the
   Store directly if the bridge is not running. Do not invent a fake goal or a
   cosmetic polish goal.
2. **Chase that goal until it is `verified_complete`** by PEX's own canonical
   completion projection (`GET /v1/goals/{id}/completion`). That means the
   supervisor must actually verify the work against acceptance criteria, not
   that the agent narrates completion.
3. **Do not end your turn until either** (a) the goal is `verified_complete`
   and the operator has authorized submission, **or** (b) the only remaining
   work is explicitly operator-authorization-gated (live provider, AWS spend,
   package build, Git commit, Devpost submit). If you hit (b), state exactly
   which authorization gates remain and keep iterating on every offline item
   that does not require authorization.
4. **Use subagents by default for audit and review on every major edit**:
   - one read-only subagent for core authority/store/app contracts,
   - one for desktop/pet behavior and UI evidence,
   - one for test suite/release/packaging gate impact,
   - one for benchmark and objective-alignment checks.
   Run them in parallel where possible. Keep edit clusters disjoint (no
   overlapping files) and centralize findings before integration.
5. **Loop to perfection**: after each major slice, rerun focused tests, then
   the full Python suite, Ruff, desktop tests, desktop build, and
   `git diff --check`. Update `STATUS.md`, `KNOWN_FAILURES.md`, `DECISIONS.md`,
   and `INTEGRATIONS.md` truthfully. Then immediately start the next highest-
   impact offline slice. Do not stop for cosmetic polish or scope expansion
   before the recovery chain is closed.

### Standing rules (do not weaken)

- Always start by reading those three specs end-to-end before any code inspection.
- Then read this file from the top and follow the freshest checkpoint sections as current history.
- Preserve all dirty state in `C:\Users\JosephMayo\Projects\pex` unless the operator explicitly authorizes cleanup.
- Do not mark anything complete because a turn/message looks good. Completion means explicit passing of required acceptance conditions and evidence.
- Never end a turn on "good progress"; keep iterating until the app is at a true submission-quality state for this contest context.
- If a public leaderboard appears at any point, use it as the minimum progress bar and avoid moving on if it indicates regression relative to deadline targets.
- If no leaderboard is present, continue hardening product correctness, especially the core closed-loop and auditability obligations from the recovery spec.
- Every major change block must include a full mini-cycle:
  1) read/understand the touched files,
  2) implement,
  3) audit and review every changed line for spec and integrity drift.
  If uncertain, keep it in review rather than shipping.
- Mandatory process bar before declaring milestones:
  - No fake completion hooks,
  - explicit proof of real Codex closed-loop behavior,
  - deterministic/no-op correctness,
  - actor-assured interventions with evidence trace,
  - no leaderboard claims without reproducible provenance,
  - no submission/deploy/freeze/commit staging side effects unless explicitly authorized by operator action.
- This repository's current contest objective is to win by correctness-first execution, not by cosmetic polish. No scope expansion before the recovery chain is closed.

## Current snapshot — 3 Sep 2026 — still NO-GO

This section is the current operator-facing implementation context for the next agent. The three PEX specs below prevail over this handoff on any conflict; within this file, this snapshot supersedes older dated history. The working tree is dirty and must be preserved. Do not discard it. Do not commit unless the operator explicitly asks. Do not Submit, deploy, publish, spend, build/package an installer, stage, freeze the four-arm manifest, spawn a second Cursor, kill the live companion unless asked, or mark the persistent Cursor goal complete.

### Binding operator constraints (action-time; do not weaken)

- **Overall status: NO-GO.** Not a Devpost submit. Deadline **September 14, 2026, 5:00 PM PDT**, Professional Agents, `https://agentsforhumans.devpost.com/`. No scored public leaderboard was found; no validated rank is retained.
- Binding specs, all three: `docs/PEX_CORE_SPEC.md`, `docs/PEX_BUILD_SPEC.md`, `docs/PEX_IMPLEMENTATION_RECOVERY_SPEC.md`. They prevail on conflict. This handoff is implementation context, not a fourth spec.
- **Do not submit, deploy, publish, spend, build/package an installer, stage, or commit** without explicit operator authorization at action time.
- Do **not** spawn a second Cursor. Do **not** freeze this editor. This editor stays on **observe** hooks.
- Control hooks (`failClosed`, `beforeShellExecution`, `preToolUse`, `beforeReadFile`, `beforeMCPExecution`) are **opt-in for isolated bench worktrees only**.
- Live `opencode serve`, Grok Build, Hermes ACP, Devin spawn, live Codex App Server, and live supervisor (`PEX_LIVE_SUPERVISOR=1`) only if the operator asks. Isolated live Codex tests skip unless **`PEX_LIVE_CODEX=1`**.
- Default Cursor attach does **not** install hooks (`install_hooks is True` only). `Settings.codex_attach` default **False**.
- Starter desktop inventory is exactly **Cursor, Codex, OpenCode, Hermes, Claude Code**. Grok Bot is a registered adapter, **not** in `DESKTOP_APPS`.
- Built-in pets: exactly **8** in current source. Current evidence exists under `apps/desktop/src/pets/_audit/release/current-20260831`, but it is untracked and release/package state is still NO-GO. A hatch provider result is only an unverified base candidate, never a finished atlas or playable pet.
- Canonical mutation: `POST /v1/sessions/{id}/handoff` / MCP `pex.handoff`. No validated scored leaderboard or rank is retained.
- Product copy is generic (no "this Cursor" / "this machine" / operator-name framing).
- Manifest stays **`frozen: false`**. `cursor_same_session_treatment_status` stays **`not_yet_satisfied`**.
- Do not cite leaked 1/5 vs 4/5 under `benchmarks/results/INVALID_LEAKED_RUNS_DO_NOT_USE/`.
- Python: `uv run` from `C:\Users\JosephMayo\Projects\pex`. PowerShell: `;` not `&&`. Branch: `main`.
- A companion is already bound **`127.0.0.1:7420`**. Do not start a second `pex-bridge`, kill it, or restart it without explicit operator coordination. This dirty checkout is ahead of that process. Backup of Cursor hooks: `hooks.json.pex-backup`. UTF-8 BOM: read with `utf-8-sig`.

## Newest checkpoint — DNS pin + Windows token ACL + honesty matrix — 3 Sep 2026

Offline slices 3–6 from the durable contest goal moved:

- Supervisor request DNS is pinned to a literal global IP with original Host
  and httpcore `sni_hostname`. Regression:
  `test_request_destination_pins_global_dns_so_later_answers_cannot_rebind`.
  Scrape hostnames fail closed on non-global DNS.
- Windows `bridge.token` gets a protected owner-only DACL; the parent directory
  is held open (`CreateFileW` + `FILE_FLAG_BACKUP_SEMANTICS`). `PEX_TOKEN` must
  not live in inherited process env (sidecar already pops it).
- `docs/SUBMISSION.md` is the Devpost draft; README and KNOWN_FAILURES matrix
  match it on AgentCore, freeze, and live-proof. Pets git-tracking remains
  authorization-gated.

### Still open (do not freeze/submit)

1. Live Codex / live supervisor / AgentCore deploy / Devpost — operator-gated.
2. Four-arm `can_freeze` stays false; `cursor_same_session_treatment_status`
   stays `not_yet_satisfied`.
3. Von spritesheet + `_audit/release/current-20260831` git-track after review.

### Gate

Fresh full Python: **1804 passed, 21 skipped in 616.64 s (10:16)**. Ruff and
`git diff --check` are clean aside from Windows LF/CRLF notices. Desktop
`npm test` is **62/62**. No desktop production rebuild. No live, benchmark,
package, hook, process, Git, deploy, publication, spend, or submission action
occurred. Overall remains **NO-GO**.

## Prior checkpoint — typed non-pytest verification + untrusted decision framing — 3 Sep 2026

Two more offline audit items landed on the durable contest goal.

### Typed REQUEST_VERIFICATION beyond pytest

`VerificationProbeKind` now includes `file_count`, `artifact_tail`,
`command_exit`, and `service_health` in addition to `pytest`. The bridge mints
contained relative targets from the goal; the planner no longer NOOPs those
kinds. A later matching SHELL with a typed `process_state` key closes the
attempted receipt to `executed`. Codex pytest matching is unchanged. Unknown
probe kinds still NOOP. Proven by unit probes plus
`test_requested_service_health_receipt_updates_after_matching_worker_event`.

### Untrusted human-decision interpolation

`format_human_decision_message` bounds question/choice, strips delimiter
injection, and wraps them in an explicit untrusted block so workers cannot
treat the human text as PEX policy.

### Still open (do not freeze/submit)

1. Live Codex, AgentCore deploy, Devpost submit remain operator-gated.
2. Four-arm freeze and Cursor same-session treatment remain unsatisfied.
3. Presentation: pets git-tracking remains authorization-gated.

### Gate

Fresh full Python: **1802 passed, 21 skipped in 606.76 s (10:06)**. Ruff and
`git diff --check` are clean aside from Windows LF/CRLF notices. Desktop
`npm test` is **62/62**. No desktop production rebuild. No live, benchmark,
package, hook, process, Git, deploy, publication, spend, or submission action
occurred. Overall remains **NO-GO**.

## Prior checkpoint — worker-delivery receipts + attached-only completion — 3 Sep 2026

The mid-implementation delivery-receipt slice is **complete and verified**. A
second high-severity completion honesty gap from the same audit is also closed.

### Worker-delivery receipts

Bare `True` from any adapter is now `delivery_uncertain`. `delivered` requires
an exact turn receipt:

- Codex keeps `pex.worker-delivery.codex-turn.v1`.
- Synthetic, Qwen HTTP `promptId`, Qwen Stop-hook followup, Cursor Stop-hook
  followup, and Claude Code Stop-hook followup mint `pex.worker-delivery.v1`
  (or Codex schema when the harness is Codex) via `AdapterMessageResult`.
- Cursor ACP, OpenCode, Devin, Fleet, and other Boolean-only paths stay
  honestly uncertain.
- `_seal_main_event_effect`, operator-effect finalization, and human-decision
  v3 receipts use `validate_worker_delivery_receipt_binding`. Codex/Qwen/
  Synthetic delivered operator/human-decision rows still require a receipt.
  Causal Codex event matching remains Codex-schema-only.

### Goal completion no longer credits a moved-off session

`goal_completion_projection` only treats fresh STOP evidence as latest when
that `session_id` is still in the current attached, non-`DETACHED` session
list for the goal. Re-attaching the completing session onto another goal
after `verified_complete` now yields `uncertain`.

### Gate

Fresh full Python: **1793 passed, 21 skipped in 592.34 s (9:52)**. Ruff and
`git diff --check` are clean aside from Windows LF/CRLF notices. Desktop
`npm test` is **62/62**. No desktop production rebuild (no desktop source
change). No live, benchmark, package, hook, process, Git, deploy, publication,
spend, or submission action occurred. Overall remains **NO-GO**.

### Next agent order (do not freeze/submit)

1. Live Codex / AgentCore / Devpost remain operator-gated.
2. Four-arm freeze stays false.
3. Pets git-tracking remains authorization-gated.

## Prior checkpoint — exclusive bridge startup ownership + delivery-receipt safety start — 3 Sep 2026

Two offline correctness slices landed in this checkpoint; one is complete and
verified below, one was mid-implementation and is now finished in the newest
checkpoint.

### Complete: exclusive bridge startup ownership before lease recovery

A cross-process advisory lock now guards bridge startup. Without it, a second
`pex-bridge` process could call `recover_unfinished_events` /
`recover_interrupted_operator_effects` and steal or duplicate dispatch
authority over a still-live prior process.

Implementation:

- `services/bridge/src/pex_bridge/app.py` adds `_BridgeStateLock`.
  - POSIX: `flock(LOCK_EX | LOCK_NB)` on the resolved database **parent
    directory** inode. The directory is not unlinked while non-empty and does
    not collide with SQLite's own byte-range locks on the database file, so
    this is portable across Linux and macOS.
  - Windows: nonblocking `msvcrt.locking(LK_NBLCK, 1)` on a sidecar
    `.{db.name}.bridge.lock` in the resolved parent directory.
  - Descriptor is `O_CLOEXEC` / `set_inheritable(False)` so worker subprocesses
    never inherit the lock.
  - `lifespan` acquires the lock before `state.store.connect()` and any
    `recover_*` call, and releases it only after runtime/store shutdown via the
    `AsyncExitStack`.
- `tests/unit/test_auth.py` proves cross-process exclusion with a real child
  `subprocess`, not an in-process `flock` recursion check. The child fails
  while the parent holds the lock and succeeds after release.

Trust boundary: this prevents a second **normal** PEX bridge from running
startup recovery against the same configured state. It does not defend against
a malicious same-user attacker who can replace database aliases or rewrite PEX
state directly; that is outside the local-user trust boundary and is not
claimed.

Focused cluster: **39 passed, 2 skipped** (`test_auth.py`,
`test_operator_handoff_effects.py`, `test_event_processing_pipeline.py`).
Ruff clean. `git diff --check` clean apart from informational Windows
line-ending notices.

### Completed in the newest checkpoint: worker-delivery receipt safety

The generic receipt contract is now live. See the 3 Sep newest checkpoint
above. Codex schema is unchanged. Cursor/Claude/Qwen Stop-hook followups mint
generic receipts so the same-HTTP-response followup is not recorded as
uncertain; Cursor ACP and other Boolean adapters remain uncertain.

### Other offline blockers identified by the cross-spec audit

These were surfaced by four independent read-only reviewers on 3 Sep 2026.
Chase remaining items in severity order. Delivery receipts and attached-only
completion are done.

1. **Done — `goal_completion_projection` no longer credits a moved-off session.**
   Fresh STOP evidence is ignored unless `session_id` is still attached and not
   `DETACHED`. Regression:
   `test_completion_does_not_credit_session_moved_off_the_goal`.

2. **Done — supervisor REQUEST_VERIFICATION is not pytest-only.**
   Typed kinds `file_count`, `artifact_tail`, `command_exit`, and
   `service_health` are minted and executed. Regression:
   `test_requested_service_health_receipt_updates_after_matching_worker_event`.

3. **Done — DNS rebinding TOCTOU is pinned on the credential-bearing client.**
   The request hook rewrites a passing hostname to a literal global IP and
   sets Host + httpcore `sni_hostname`. A later `getaddrinfo` returning a
   private address cannot retarget that request. Regression:
   `test_request_destination_pins_global_dns_so_later_answers_cannot_rebind`.
   Scrape DNS is fail-closed on non-global answers.

4. **Done — Windows bridge token file owner-only ACL.**
   Protected DACL `D:P(A;;FA;;;<current user SID>)`; parent directory handle
   held for the transaction; `PEX_TOKEN` is not left in process env.
   Regression: `test_bridge_token_windows_acl_is_owner_only_and_holds_parent`.

5. **Done — prompt-injection framing in `decision_delivery.py`.**
   Question/choice are bounded, delimiter-stripped, and wrapped in an untrusted
   block before they reach a worker. Regression:
   `test_human_decision_message_frames_untrusted_text_and_strips_delimiter_injection`.

6. **Done — judge-facing docs share one NO-GO story.**
   `docs/SUBMISSION.md` is the Devpost draft. README hackathon copy and the
   `KNOWN_FAILURES.md` verified/not-yet/blocked matrix match on AgentCore,
   unfrozen four-arm, and live-proof. Pets git-track remains item 7.

7. **Presentation — close the built-in pet source-evidence boundary.**
   After operator review, git-track the missing `von/spritesheet.webp` and the
   `_audit/release/current-20260831` receipts so a clean clone reproduces the
   8-pet manifest. Run
   `apps/desktop/scripts/release-contract.test.mjs` and
   `test_fleet_pets_codex.py` to confirm the contract holds. This is
   authorization-gated (Git stage/commit) but the offline prep is not.

8. **Presentation — pre-stage the 5-minute demo storyboard and builder bonus
   posts.** Finalize `docs/SUBMISSION.md:42-53` voiceover into a shot-by-shot
   script. Finalize the three `docs/posts/*.md` drafts with required
   `Agents for Humans` titles and honest "not deployed / not frozen" caveats.
   Recording and publishing remain authorization-gated.

### Authorization-gated work (do not perform without fresh operator authorization)

These require operator action, credentials, or live harnesses and must not be
performed by the next agent without explicit action-time authorization:

1. AWS / AgentCore deployment (`deploy/agentcore/preflight.py` blockers).
2. Live Codex / Cursor closed-loop demo recording.
3. PexBench freeze (needs 20 live rows, fresh-workspace receipts, real
   treatment audits).
4. Packaging / installer build (sidecar binaries not built).
5. Builder Center posts publication (AWS Builder ID login required).
6. Git stage or commit.
7. Devpost submission.

### Latest verified results before this checkpoint

- Full Python suite: **1784 passed, 21 skipped** (before the delivery-receipt
  safety patch; the next agent must rerun after finishing that slice).
- Desktop tests: **62 passed**.
- Desktop build: clean, 52 Vite modules.
- Ruff: clean.
- `git diff --check`: clean apart from informational Windows LF-to-CRLF
  notices.
- Provider focused tests: **74 passed**.
- Completion/Ask focused tests: **32 passed**.
- Auth/operator-handoff/event-processing focused cluster after the startup
  lock: **39 passed, 2 skipped**.
- Release preflight: intentionally nonzero and still NO-GO.

No live, benchmark, package, hook, process, Git, deploy, or submission action
occurred in this checkpoint. Status remains **NO-GO** pending real
harness/provider and release proof.

## Prior checkpoint — credential-safe supervisor transports — 3 Sep 2026

Credential-bearing OpenAI and Anthropic inference now inject the correct async SDK transport
with redirects and environment proxies disabled, bounded timeout, and per-request DNS rejection
of private/link-local/reserved or mixed answers. Catalog and Ask review use the same synchronous
policy; literal loopback remains allowed for local runtimes. This closes redirect-based bearer
and Anthropic `x-api-key` leakage. DNS remains unpinned between request-hook resolution and socket
connect, so residual rebinding TOCTOU is disclosed rather than claimed solved.

Provider/inspect tests are **74/74**; fresh whole-tree Python is **1784 passed, 21 skipped in
696.53 s (11:36)**; Ruff and diff checks clean; desktop remains **62/62** with a clean 52-module
build. Handoff UI now distinguishes an unreachable monitoring request from delivered context
whose target-use evidence is still absent; outages do not imply target neglect. No live,
benchmark, package, hook, process, Git, deploy, or submission action occurred.
Overall status remains **NO-GO** pending real harness/provider and release proof.


## Prior checkpoint — intent-bound canonical goal completion — 3 Sep 2026

Pipeline event acceptance now freezes exact current Goal intent revision/hash beside the accepted
session/project snapshot. A new one-transaction `pex.goal-completion.v1` projection validates
committed STOP plan ownership and returns only `verified_complete`, `incomplete`, `in_progress`,
or `uncertain`. It never uses worker narration or benchmark data. Supported evidence must match
the current intent and project binding; legacy rows with no historical intent receipt are stale,
not backfilled.

Active sibling work newer than a supported STOP takes precedence using the event timestamp, not
server acceptance time. Goal edits stale prior evidence; paused/superseded goals remain uncertain.
REST exposes `/v1/goals/{id}/completion`; desktop refetches it as sessions change and presents it
in Inspector with an offline fail-closed message. Ask PEX uses the same projection, scopes generic
completion questions to the latest verifier-backed goal, and refuses ambiguous cross-goal evidence.
Genuine supported completion, multi-session precedence, post-verification acceptance changes, and
Ask agreement are covered. Full Python is **1783 passed, 21 skipped in 705.09 s (11:45)**; Ruff
clean; desktop **62 passed**; production frontend and diff
checks clean. No live, benchmark, package, hook, process, Git, deploy, or submission action
occurred. Status remains **NO-GO** pending real harness/provider and release proof.

## Prior checkpoint — consistent handoff replay and immediate fleet freshness — 3 Sep 2026

`find_operator_handoff` now composes the effect, Intervention, trigger/audit/watermark authority,
and actor receipt in one fresh SQLite read transaction. A deterministic WAL race regression
freezes a dispatching read, commits delivery concurrently, and proves both the historical and
subsequent delivered views are internally consistent. Handoff/assimilation coverage is **74/74**.

Desktop socket/token failure now marks cached state offline immediately instead of waiting for
the next four-second poll. Cached agent Ask chips are suppressed, the Decisions view falls back
to cached interventions only beneath the explicit degraded banner, and every agent row exposes
last-observed time plus a `Cached` label when degraded. Desktop is **62/62** and the 52-module
production frontend build is clean. Full Python is **1783 passed, 21 skipped in 856.42 s
(14:16)**; Ruff and diff checks are clean apart from informational line-ending notices.

No live session/model, benchmark, package, hook, process, Git, deploy, or submission action
occurred. Status remains **NO-GO**. The next offline human-value gap is a truthful goal-level
completion/acceptance projection; PEX still shows criteria and evidence but has no canonical
single answer for whether a goal is verified complete.

## Prior checkpoint — scalar Context goal authority — 2 Sep 2026

This offline slice adds nullable scalar `context_items.goal_id`, a marker-bound validated legacy
backfill, immutable scalar/JSON binding, and indexes on `(project_binding, goal_id, id)` and
`(project_id, goal_id, id)`. All eight production Context insert paths supply the scalar; managed
retirement and human-decision updates pin it; goal-intent, retirement, handoff, counts, and
authority listings now filter by the scalar. Valid bound legacy rows are backfilled, while
malformed/orphan/mismatched rows retain null authority. After migration, bound and unbound rows
cannot be retargeted and reconnect rejects scalar corruption. Independent migration/query/test
and hostile reviews were reconciled; SQLite DDL remains inside the atomic `BEGIN IMMEDIATE`
migration transaction.

Verification: focused migration/authority/event/MCP gate **127 passed**; fresh whole tree
**1782 passed, 21 skipped in 826.09 s (13:46)**; Ruff clean; desktop **61 passed**; production
frontend build clean at 52 modules; diff checks clean except informational Windows line-ending
notices. No live session/model, benchmark, package, hook, process, Git, deploy, or submission
action occurred. Overall status remains **NO-GO**. Next offline work should reassess the remaining
submission-critical authority and evidence gaps; Codex proof remains quota-blocked and Cursor
remains observe-only.

## Prior checkpoint — managed goal-ledger retired-history guards — 2 Sep 2026

This is the newest completed offline authority slice. The parent retained all dirty operator
state, used independent read-only audits for trigger bypasses, migration compatibility, tests,
and final hostile review, and reconciled findings against the three binding specs. No live
session/model, benchmark, package, process, hook, Git, deploy, or submission action occurred.

### Managed Decision/Context SQLite authority

- The three managed persistent-intent kinds remain exactly `decision`, `rejected_approach`, and
  `unresolved_question`. Their Python writers were already restricted to the atomic Goal
  mutation; SQLite now independently enforces the representation and history boundary.
- A fresh managed Decision insert requires human provenance, internal sensitivity, a nonempty
  statement, kind-appropriate `active`/`uncertain` status, no retirement marker, and a parent
  Goal with no same-binding successor. Its Context insert requires one exact paired Decision,
  matching goal/project binding, statement/content, status, kind, source reference, creation
  instant, human provenance, internal sensitivity, and unresolved flag.
- Managed rows may update only through the exact live-to-superseded transition used by
  `_retire_goal_ledger_kinds`: every non-retirement JSON field is preserved, the Decision is
  retired first, and Context `stale_after` plus both `superseded_at` projections identify the
  same instant. Retired rows cannot be reactivated or rewritten. Live managed rows cannot be
  directly rewritten, reparented, or converted into/out of the managed namespace.
- All managed Decision/Context rows are append-only. Direct delete and `INSERT OR REPLACE` are
  rejected. Direct managed inserts under a superseded predecessor are rejected. Existing Goal
  semantic-hash recomputation remains a second fail-closed boundary for incomplete direct SQL
  transitions.
- Non-managed MCP progress, human-decision, event, verification, and ordinary context rows do
  not carry one of the managed metadata kinds and remain unaffected. Trigger names use the
  existing `trg_decisions_*` / `trg_context_items_*` namespaces, so legacy test/migration paths
  drop them before binding old rows and recreate them afterward.

### Verification and release truth

- focused Goal/ledger/retirement/human-decision transaction gate: **128 passed**;
- fresh whole tree `uv run pytest -q`: **1780 passed, 21 skipped in 783.92 s (13:03)**;
- repository-wide Ruff: clean;
- desktop: **61 passed** and clean 52-module production frontend build;
- final diff check: exit 0 with informational Windows LF-to-CRLF notices only.

Check-only release preflight remains **NO-GO**: exactly 8 pets, 888 release inputs (166 tracked,
722 untracked), zero hidden-index inputs, 1205 dirty paths, audit closure
`94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470`, sidecar-input SHA-256
`6f848f9b9748c848e8a41f40ea8c7c0a16352f96e1d6b7be299280ccdb78bf9b`, stale stamp, and
missing Cursor observer bytes. No release blocker was hidden or cleared.

### Next actions

1. Live Codex + Strands proof remains blocked by operator quota. Existing Cursor remains
   observe-only and cannot prove continuation without separately authorized isolated control.
2. The next safe offline authority candidate is the scalar/indexed Context `goal_id` migration,
   replacing repeated JSON extraction while preserving legacy quarantine and exact project/Goal
   binding. Design and audit it before changing the schema.
3. Preserve package/sidecar, Git, AWS/deploy, benchmark/freeze, publication, and Devpost as
   separate explicit action-time gates.

## Prior checkpoint — durable goal control and prospective attention eligibility — 2 Sep 2026

This is the newest completed offline correctness slice and supersedes older verification
counts while preserving every unresolved live/package/release gate. The three binding specs
and the current handoff were reread before code inspection. Four independent read-only
reviews covered receipt/trigger integrity, retry/crash semantics, Build Spec §58.2 metric
eligibility, and deadline priority. The parent reconciled their findings, retained the
in-progress dirty implementation, fixed the reproduced blocker, and ran every final gate.
No reviewer edited overlapping files or performed live actions.

### Durable actor-assured goal-control operations

- Authenticated REST goal create/update/override and session attachment require a bounded
  body `idempotency_key`. The versioned canonical logical request excludes the key and all
  server-generated IDs/timestamps. A reused key with different content is a typed 409.
- Non-secret `bridge_bearer` actor evidence, exact action/project/project binding/goal/session
  authority, semantic outcome, committed public response, and response hash are frozen in one
  immutable `goal_control_operations` row. The row is inserted in the same `BEGIN IMMEDIATE`
  transaction as the Goal/ledger/session mutation. Update/delete triggers block rewriting and
  deletion. Legacy no-auth and internal compatibility calls remain unassured and receive no
  operation row or inferred human history.
- Route replay occurs before ordinary goal/session authority reads. The write transaction
  independently rechecks after acquiring the SQLite writer lock, so concurrent duplicates
  across Store instances serialize to one mutation and one replay. Restart replay returns the
  exact original generated goal ID, timestamp, semantic receipt, attachment receipt, and
  operation ID even when current CAS authority has moved on.
- Semantic no-ops are terminal and replayable but remain `changed:false`; this is required to
  make response-loss retries exact and does not make them metric-eligible. Failed/denied
  mutations do not acquire a committed terminal row and may be safely reevaluated.

### Hostile replay repair and desktop retry behavior

- Independent review found a real fail-closed defect: the fast REST replay path validated the
  stored response hash and public operation receipt but returned raw `response_json` without
  binding its semantic outcome to the immutable authority row or reconstructing the typed Goal
  or session response. A coherently rehashed contradictory outcome could therefore replay.
- Store reads now require the stored authority outcome to equal the exact nested mutation or
  attachment receipt; bind goal/session/predecessor/action/project/binding/revision/hash fields
  across the scalar authority and response projections; and reconstruct the public response
  through the typed receipt validators before it leaves the replay API. The hostile
  rehashed-outcome regression now
  fails closed. Forced receipt insertion rolls back goal creation, and concurrent two-Store
  creation proves one domain effect and one exact replay.
- Desktop create/update/attach now keeps a request signature plus idempotency key until a
  committed response arrives. Exact response-loss or bridge-token retries reuse the key;
  changed content or target scope receives a new key. Success clears only the matching current
  attempt, preventing an older response from clearing newer intent.

### Prospective goal-control attention eligibility and release truthfulness

- A separate immutable migration marker and exact-ID snapshot freeze every pre-coverage
  operation identity; three actor-coverage rows declare `goal_update`, `goal_override`, and
  `session_goal_attach` without interpreting earlier rows. Every later authenticated terminal
  operation in those classes must
  have exactly one append-only `pex.goal-control-attention-receipt.v1` eligibility decision.
- The decision is committed in the same mutation transaction and freezes operation identity,
  request/result hashes, actor/project/goal/session authority, changed state, sorted mutation-time
  live-session IDs, eligibility, and an exact reason. Missing or corrupt prospective decisions
  fail `attention_metrics()` closed. A forced decision insertion failure rolls back both the
  operation row and Goal mutation.
- Goal create, semantic no-op, unattached update/override, paused/observe-only/detached targets,
  and internal/no-auth calls do not count. An attached-live semantic update or changed live
  attachment counts once. An override reattaching two live sessions also counts once, never N
  times. Historical changed operations in the frozen legacy identity set are reported as
  unverified and never backfilled or joined to mutable current sessions. The stable identity
  boundary deliberately avoids SQLite implicit-rowid drift across `VACUUM` or restore.
- `source_counts.goal_control_attention` now contributes only validated eligible decisions to the
  observed lower bound, and `goal_mutation` is no longer labeled wholly unmeasured. The canonical
  `human_interventions.value` remains null because out-of-band manual context copy/verification
  and consented active-human timing remain incomplete. This remains product evidence, not
  benchmark evidence.
- The operator reported no Codex quota and authorized inspection of already-running Cursor
  processes or continued local work. Existing Cursor is observe-only; it cannot truthfully prove
  same-session continuation without changing control hooks. No hook change, second Cursor,
  companion restart, or fake live proof occurred.
- Overall status remains **NO-GO**. No live model/provider, control-mode Cursor, process kill,
  sidecar build, package/installer, AWS/deploy, benchmark, freeze, stage/commit, publication,
  spend, or submission action occurred.

### Exact verification receipts

- focused goal-control/attention unit/E2E gate: **30 passed**;
- widened goal/Store/session/MCP authority gate: **114 passed**;
- fresh whole tree, `uv run pytest -q`: **1778 passed, 21 skipped in 1048.26 s (17:28)**;
- repository-wide `uv run ruff check .`: clean;
- desktop `npm test -- --runInBand`: **61 passed**;
- desktop `npm run build`: clean, **52 modules transformed**;
- final diff check: exit 0 with informational Windows LF-to-CRLF notices only.

Check-only release preflight exited 1 as designed: `source_ready:false`,
`release_ready:false`, exactly 8 pets, 888 release inputs (166 tracked, 722 untracked), zero
hidden-index inputs, 1205 dirty paths, release-input SHA-256
`3a1cd6d40aa98f0b23f1f0419aa5cd7c8de840dfc79b6ce00ef0e667366491e1`, audit closure
`94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470`, current sidecar
input SHA-256 `fd92651dc3ace13cf92ccde39ab16a8c80d1d35fa6b2fa4a837327eaedf181d7`, stale stamp
`be840b7c65f57575d0f629dfe2ccccd9c0c026b8352a71985e7a8b8db0b931b0`, and missing
Cursor observer bytes. The only blockers remain untracked release inputs, the operator-owned
dirty tree, and stale/missing sidecars.

### Next actions

1. Highest product milestone remains the two prepared isolated real Codex + real Strands
   cases, but the operator currently has no Codex quota. When quota and fresh action-time
   authorization exist, retain validated v3 exact-turn proof plus SQLite/JSONL, source/process,
   same-thread continuation, and exact artifact evidence. Do not use or restart the companion
   on `127.0.0.1:7420`.
2. Existing Cursor is observe-only. Do not relabel observation as control. A real Cursor
   continuation milestone requires a separately isolated control surface and explicit hook or
   package authority; never modify this editor's hooks or spawn a second Cursor implicitly.
3. The next safe offline authority candidate is the complete retired-history trigger model for
   managed Decision/Context representations, followed by a scalar/indexed Context `goal_id`
   migration. Keep either change subordinate to the real closed-loop proof and audit it against
   current typed goal authority before editing.
4. Preserve all package/sidecar, Git, AWS/deploy, benchmark/freeze, publication, and Devpost
   gates as separate explicit operator decisions. Deadline remains **September 14, 2026,
   5:00 PM PDT**.

## Prior checkpoint — goal-intent authority, attachment receipts, and clean full gate — 1 Sep 2026

This is the newest completed offline correctness slice. It supersedes the verification
counts in every older checkpoint below, while preserving all of their unresolved
live/package/release gates. The parent agent reread all three binding specs and this
handoff, kept the persistent hackathon goal active, and used the already-requested
focused subagent split for independent read-only review of goal/attention authority,
handoff actor receipts, and direct-message actor receipts. The subagents did not make
overlapping edits or perform live actions. The parent reconciled their findings against
the specs, implemented the retained design, and ran the final gates itself.

### Exact outcome and release state

- **Overall status remains NO-GO.** This checkpoint does not prove the real Codex + real
  Strands same-session milestone, packaged-app behavior, Devpost readiness, or a scored
  leaderboard result. No scored public leaderboard was found, and no rank is claimed.
- The built-in fleet remains exactly **8 pets**: `pex`, `ledger`, `mesh`, `nudge`,
  `drift`, `quiet`, `ember`, and `von`. Do not expand it to 10.
- No live provider, live supervisor, live Codex, live Cursor, browser submission,
  deployment, publication, spend, packaging, staging, freezing, commit, bridge restart,
  or process termination occurred in this slice. The existing companion on
  `127.0.0.1:7420` was not touched.
- The dirty working tree is intentional operator state. Preserve it. The clean serial
  test result below validates the current filesystem, not a committed or releasable Git
  revision.

### Goal intent is now semantic, revisioned, and transaction-frozen

Primary implementation: `services/bridge/src/pex_bridge/store.py` and
`services/bridge/src/pex_bridge/app.py`. Principal regression coverage:
`tests/unit/test_goal_intent_authority.py`,
`tests/unit/test_goal_store_transaction.py`,
`tests/unit/test_artifact_project_bindings.py`,
`tests/unit/test_credential_project_bindings.py`,
`tests/unit/test_session_control_transactions.py`,
`tests/e2e/test_goal_lifecycle.py`, and `tests/e2e/test_mcp_server.py`.

- Store now produces a frozen `GoalMutationReceipt` from the same transaction that
  commits a create, update, or override. It contains the exact committed Goal, mutation
  mode, changed/no-op result, predecessor, before/after intent revisions and hashes, and
  any sessions reattached by an override. Its public representation keeps the Goal at
  top level for compatibility and adds `goal_mutation_receipt` as the explicit authority
  envelope.
- New receipt-returning Store methods are used by REST. Existing compatibility methods
  retain their old return shapes so internal callers and MCP behavior were not silently
  broken. REST does not mutate and then re-read: request A cannot accidentally report a
  later request B state.
- A semantic no-op returns the already-stored Goal and its committed timestamp. A
  discarded proposal timestamp is never presented as persisted state. A stale writer is
  rejected even when its proposed patch would currently be a semantic no-op.
- Authenticated REST goal PATCH now requires `expected_intent_revision`; omission after a
  nonempty mutation request is HTTP 428. The comparison happens within the same
  `BEGIN IMMEDIATE` transaction. Desktop always sends the observed revision. Two-Store
  tests prove a stale ledger-only writer cannot pass CAS.
- Semantic revision/hash changes include case-only intent changes. Override rejects an
  empty semantic successor, retains only explicitly inherited ledger kinds, and clones
  inherited Decision/Context records with new identities rather than aliasing predecessor
  rows.
- Direct managed goal-ledger bypass is closed. Generic `add_decision`, `add_context`, and
  `add_decision_context_pair` reject managed goal-intent kinds; callers must use the
  atomic goal mutation path. Tests prove all three bypass attempts create no row and do
  not alter the intent revision/hash.
- Goal public views validate the semantic hash. Malformed legacy goal rows are
  quarantined: list views skip them with a warning, while direct access raises the typed
  `goal_intent_quarantined` conflict instead of returning plausible-looking state.

### Migration and successor-lineage hardening

- Goal-intent migration markers are validated for exact schema, timestamp, and
  cardinality. The prospective insert guard requires an independent goal at revision 1,
  or a successor with the same typed binding and exactly parent revision + 1.
- Genuine legacy revision-0 parent/successor chains remain readable only through the
  migration boundary; the migration does not invent historical operator-action counts.
  Tests cover valid legacy chains, corrupt markers, prospective revision 0 insertion,
  and wrong successor revisions.
- Same-binding successor discovery validates hash and lineage and loads with quarantine
  visibility, so corrupt successor data cannot disappear and reopen mutation of a
  predecessor. An explicitly re-resolved alias with a different physical identity is
  treated as forensic history and no longer blocks the old physical goal. Foreign
  forensic rows remain distinguishable from same-binding corruption.
- All mutable/control paths found reading raw goal JSON were moved onto typed bound-goal
  authority inside their existing transaction: resolution-session merge, overlay binding,
  session upsert goal changes, direct-message reservation/start, handoff reservation/start,
  main-event containment, human-decision reservation/start, and post-decision control
  restoration. Corrupt goal state now fails closed rather than authorizing control from a
  raw JSON row.
- Handoff preserves the established typed distinction: quarantined same-binding authority
  propagates a project-identity conflict; an alias deliberately re-resolved to a different
  physical project remains the established permission failure.

### Goal attachment is CAS-protected and returns exact committed evidence

- Session goal attachment accepts `expected_control_revision` and
  `expected_goal_intent_revision`. These remain optional at the Store/legacy REST boundary
  for compatibility, but the desktop always supplies both. Stale session control or goal
  intent fails in the attachment transaction.
- The attachment result is frozen before commit and reports `attached`, `replaced`, or
  `already_attached`; before/after goal IDs; session and control revisions; goal intent
  revision/hash; typed project binding/generation; and exact MCP/hook credential revocation
  counts. REST retains Session-compatible top-level fields and adds the nested
  `session_goal_attachment_receipt`.
- Replacing a goal now atomically revokes both MCP credentials and hook credentials. A
  forced failure or authority corruption rolls back the entire change. No-op replay is
  distinguished from a first attachment and from replacement.
- A final hostile receipt review found that `already_attached` was evaluated before a
  caller-supplied `expected_goal_id`. Store now rejects a false explicit prior-goal claim
  as `session_goal_changed` before returning the no-op receipt. Omitted legacy CAS remains
  compatible. The exact regression passed 1/1, and focused Ruff plus diff checks passed.
- Live-pet AppState includes current session/control revisions, giving the desktop an
  observed CAS value rather than guessing from local UI state.

### Desktop receipt consumption and stale-refresh truthfulness

Desktop files changed in this slice: `apps/desktop/src/App.tsx`,
`apps/desktop/src/types.ts`, `apps/desktop/src/viewModel.ts`, and
`apps/desktop/src/viewModel.test.ts`.

- Desktop types now model `GoalMutationResponse` and
  `SessionGoalAttachmentResponse`; mutation success copy is driven by the committed
  receipt, including a truthful “already matched” no-op outcome.
- Attachment copy uses the committed `attached` / `replaced` / `already_attached` reason;
  it no longer infers the result by comparing against whichever session snapshot happens
  to be current after the request.
- `refreshPet()` returns a discriminated `applied`, `superseded`, or `failed` outcome.
  Superseded refreshes are neutral because a newer request owns the view. Only an actual
  refresh failure adds the stale-state warning. A committed mutation remains reported as
  committed even when its subsequent refresh fails.

### Authoritative verification receipts

The following are the latest receipts for the current filesystem:

- First widened full serial run after the authority changes:
  **1751 passed, 21 skipped, 5 failed in 752.12s**. All five failures were investigated
  and fixed; none were hidden or reclassified.
- Second full serial run: **1755 passed, 21 skipped, 1 failed in 781.32s**. The remaining
  failure exposed a quarantine-vs-explicit-re-resolution exception distinction. It was
  fixed, and the two exact handoff regressions passed 2/2.
- Final clean serial gate, `uv run pytest -q`:
  **1756 passed, 21 skipped in 761.36s (0:12:41)**.
- Python lint, `uv run ruff check .`: **All checks passed**.
- Desktop unit gate, `npm test -- --runInBand`: **60 passed**.
- Desktop production build, `npm run build`: **clean; 52 modules transformed**.
- Widened handoff/permission gate: **58 passed in 272.12s**.
- Widened authority/session/decision gate: **55 passed**.
- Hostile new authority group: **67 passed**.
- `git diff --check`: exit 0; only the existing Windows LF/CRLF warnings were printed.

These are strong offline regression receipts. They are not live provider proof,
packaged-app proof, benchmark superiority, or release authority.

### Latest release preflight — expected truthful failure

`npm run preflight:release` was run read-only from `apps/desktop` and exited 1 as expected.
Its JSON reported `schema=pex.release-preflight.v1`, `source_ready=false`, and
`release_ready=false`. Important receipt fields:

- exact fleet: the 8 IDs listed above;
- release manifest SHA-256: `866348ec...`;
- audit manifest SHA-256: `ec759c...`;
- playback receipt SHA-256: `57d63c...`, with 72 GIFs, 25 screenshots, and 456 decoded
  frames;
- Git clean: false;
- release inputs: 888 total, 166 tracked, 722 untracked;
- dirty-worktree inventory: 1203 staged/modified/untracked paths;
- hidden index entries: 0;
- release-input SHA-256: `8b9b...`;
- audit reachable files: 672; closure SHA-256: `94dceb...`;
- target: `x86_64-pc-windows-msvc`;
- current sidecars: false; frozen inventory: false;
- current sidecar input SHA-256: `d337fe...`; recorded stamp begins `be840...`;
- verified tools: Node 24.19, Python 3.12.13, Rust 1.97.1, PyInstaller 6.22.2;
- Tauri external-bin wiring recognizes `pex-bridge`, `pex-cursor-hook`, and
  `pex-cursor-observe`; Cursor observe receipt is still null.

The explicit blockers were 722 untracked release inputs, a 1203-path dirty inventory,
and stale/missing sidecars. Do not make the preflight green by deleting operator work,
building sidecars, staging, committing, or rewriting the stamp without the separate
authorization appropriate to each action.

### Remaining gaps after this slice — do not blur them into completed work

1. **Durable idempotent mutation operations remain incomplete.** Current goal and attach
   receipts are exact and transaction-frozen, but there is no append-only operation-key
   ledger that guarantees actor-assured replay of the same request across transport retry
   and process restart. Goal REST mutation still uses the general bearer dependency rather
   than the frozen operator-actor reservation/terminal-receipt pattern used for assured
   direct messages and handoffs.
   Three focused reviewers converged on the next design boundary: these effects are fully
   SQLite-local, so use one immutable terminal operation row in the same
   `BEGIN IMMEDIATE` transaction as the mutation, not an externally durable dispatch
   reservation state machine. Require a body `idempotency_key` on the authenticated
   operator surface; hash the versioned validated logical request without the key or
   server-generated IDs/timestamps; replay before mutable authority reads; freeze exact
   response/authority hashes; and keep legacy/no-auth/internal paths unassured. A separate
   reservation lifecycle remains appropriate only for adapter I/O. This is reviewed
   design, not yet implemented code.
2. **Attachment CAS is not mandatory for every legacy REST caller.** Desktop supplies it,
   but a future compatibility migration must make the authority requirement universal
   without silently breaking the protocol.
3. **Goal mutation/attachment attention metrics are not implemented.** Do not count the
   new receipts as human interventions merely because an authenticated request exists.
   The exact actor-reservation, terminal-effect, consent/window, and lower-bound semantics
   from Build Spec §58.2 still apply.
4. Generic managed Decision/Context writer bypass is closed, and goal hashes validate
   current authority, but the database does not yet have a complete retired-history trigger
   model for every managed Decision/Context representation.
5. A scalar/indexed `goal_id` migration for Context remains a longer-term authority and
   query-hardening improvement; current binding is validated through canonical payloads.
6. Real Codex (`PEX_LIVE_CODEX=1`), real supervisor (`PEX_LIVE_SUPERVISOR=1`), same-session
   loop evidence, packaged playback, release cleanup, sidecar rebuild, staging, commit,
   deployment, and submission all remain separately authorization-gated.

### Next agent operating instructions

- Keep the persistent hackathon goal active and continue working; do not end merely after
  reporting status. Use focused subagents as the operator requested: one bounded cluster
  per reviewer, read-only where edits might overlap, and keep spec reconciliation plus
  final integration in the primary agent.
- At the start of every continuation, reread all three binding specs and the current top
  of this handoff. If an older checkpoint conflicts with this one, this newest checkpoint
  governs implementation history, while the specs always govern product requirements.
- The next safest high-value slice is an actor-assured, durable idempotency ledger for goal
  mutation and attachment operations. Design it before editing: operation identity,
  canonical request hash, actor evidence, exact project/session/goal authority, reservation,
  terminal receipt, restart replay, conflict semantics, append-only guards, and no-secret
  payload must all be explicit. Do not infer human evidence from a bearer principal alone.
- Split review across receipt-schema/trigger invariants, retry-and-crash semantics, and
  metric eligibility. Avoid concurrent edits to `store.py` or `app.py`; reviewers should
  return findings or own isolated tests.
- After each edit, run the smallest affected authority tests and lint. Before widening any
  product or release claim, rerun the clean full serial suite plus desktop unit/build gates.
- Continue using the release preflight as a truthful bar. A nonzero NO-GO preflight is the
  correct result until all gated release inputs and proofs are actually authorized and
  satisfied.

## Latest spec/audit checkpoint — actor-assured direct messages and handoffs, 1 Sep 2026

This is the newest source and verification checkpoint. It supersedes the 1698-pass
checkpoint below but does not replace any unresolved live/package/release gate. The parent
agent reread the three binding specs and this handoff, then used three independent
read-only subagents to audit (1) authenticated direct-message provenance, (2) authenticated
handoff provenance, and (3) the exact attention-metric definition and migration boundary.
All three agreed on the central rule from Build Spec §58.2: an action may enter the observed
human-intervention lower bound only when a user action actually alters/unblocks execution
and durable actor assurance is coupled to the terminal effect. A principal string,
`human_requested` Boolean, delivery receipt, policy request, navigation action, or
autonomous PEX handoff is not human evidence. The subagents did not edit files.

### What was implemented

- `_require_operator_token` now returns a frozen, non-secret `OperatorActorEvidence` only
  after the operator-only bearer dependency succeeds. It carries
  `principal_id=local_bridge_operator` and `actor_assurance=bridge_bearer`; it does not
  retain the bearer or a bearer digest. The direct-message REST route passes this evidence
  to Store. Missing/wrong/unavailable auth and explicit test-only no-auth still fail before
  Store access.
- New authenticated direct-message reservations use
  `pex.operator-effect.session-message.v2`. Before adapter I/O, the same transaction freezes
  the actor assurance, exact source/target session, vendor/harness, goal, project, typed
  project binding, request hash, exact-turn delivery contract version, and reservation
  timestamp in append-only `human_operator_action_reservations`. Existing v1 direct-message
  effects and internal Store calls without actor evidence remain permanently unassured; no
  migration backfill infers a human from `principal_id` or timestamps.
- `human_operator_action_coverage` declares prospective schema-version-1 boundaries for
  both `session_message` and `context_handoff`. Coverage is declaration only: each counted
  delivery must still pass its own exact effect/reservation/terminal-receipt validation.
  Existing v1 effects remain legacy and receive no inferred actor backfill.
- The first authenticated `dispatching -> delivered` direct-message CAS inserts one
  content-free `pex.human-operator-terminal-action.v1` receipt in the same
  `BEGIN IMMEDIATE` transaction. It binds the immutable reservation, terminal effect
  version/state, exact result digest, and timestamps. It contains no prompt text, bearer,
  bearer digest, or attachment content. A forced receipt-insert failure rolls back the
  terminal effect, leaving it `dispatching`; Store never reports a delivered effect without
  its required actor receipt.
- Exact terminal replay validates and returns the existing receipt without adapter I/O or
  a second row. `get_operator_effect`, reservation replay, pre-dispatch grant, restart
  recovery, and attention metrics all validate the prospective actor ledger. Missing or
  corrupt reservation/receipt rows fail closed. Prior-boot authenticated dispatches become
  `delivery_uncertain` without a delivered-action receipt and are never resent.
- Coverage, reservation, and terminal tables are append-only/update-delete blocked.
  Exact-effect authority fields/payload are immutable, independently blocking an actor
  schema/project/request downgrade. Validation still rechecks SQL/JSON scalar binding,
  deterministic receipt identity, exact hashes, schema versions, and frozen authority, so
  trigger removal plus data corruption fails reads rather than becoming legacy.
- Attention metrics validate every prospective effect/reservation/receipt inside their one
  SQLite read snapshot. Valid delivered receipts enter
  `source_counts.direct_operator_message` exactly once and are removed from
  `unverified_operator_action_counts.operator_message`. Failed/skipped/uncertain assured
  outcomes are reported separately under
  `actor_assured_operator_message_outcomes`; only delivered enters the observed lower
  bound. The canonical `human_interventions.value` remains null and `measured:false`,
  because handoffs, goal mutation/attachment, out-of-band context/verification, and
  consented active-human timing remain incomplete. Product counts remain non-benchmark
  evidence.
- Desktop protocol typing includes `session_message` prospective coverage and the separate
  actor-assured outcome map. No UI claim was widened to named-human, presence, helpfulness,
  assimilation, task success, benchmark improvement, or active-human-time proof.

### Authenticated context-handoff completion

- The operator-only REST handoff route now carries the same frozen
  `OperatorActorEvidence`; Store writes the actor reservation with the effect, bound
  Intervention, trigger event, and reserved audit. MCP, automatic, and internal
  compatibility handoffs receive no actor assurance.
- `human_requested=True` is no longer authority. Pipeline derives the human-requested
  allow path only from `bridge_bearer` actor evidence; an internal Boolean stays
  `system_internal_handoff`, remains policy-controlled, and cannot acquire a human receipt.
- The first delivered handoff CAS atomically couples effect, frozen Intervention, exact
  delivery audit, and one content-free actor terminal receipt. Forced receipt failure
  rolls all three canonical projections back. Replay/restart/corruption validation uses
  the same frozen exact-turn and candidate-manifest authority.
- Valid authenticated REST deliveries now enter
  `source_counts.operator_context_handoff` once and leave the unverified-handoff bucket.
  Bundle size, acknowledgement, artifact use, and later assimilation audits never multiply
  the human action. MCP/automatic/legacy handoffs remain excluded. Canonical human total
  remains null because other action routes and consented active time remain incomplete.

### Goal-lifecycle audit and correctness repair

- Three fresh read-only audits examined goal create/update/override and session attachment
  against Core persistent intent, Build §58.2, and Recovery §3/§12. They agree that the
  routes are not yet safe to add to the human-intervention lower bound: they use ordinary
  bridge auth, have no durable actor receipt, and have no caller idempotency key. Existing
  Goal/session state cannot reconstruct historical user-action cardinality, so it must
  never be backfilled as human provenance.
- The audit found a real override defect: a ledger-only
  `PATCH {"mode":"override", ...}` took the early ledger-patch branch and modified the
  predecessor instead of creating a successor. Mode dispatch is now correct; the request
  creates a successor, preserves the predecessor, atomically moves attached sessions, and
  projects the successor ledger. A new E2E regression proves the chain.
- Same-value scalar goal updates previously manufactured a new `updated_at` despite no
  semantic change. They now return the exact current Goal without Store mutation. This is
  necessary before any action counter can distinguish a real intervention from UI save
  churn.
- Desktop goal replacement previously sent `replace_existing:true` without the API's
  required exact `expected_goal_id`, so explicit replacement and save-then-replace could
  fail with `session_goal_changed`. The desktop now derives one exact attachment payload:
  initial/same-goal attachment sends no predecessor; replacement binds the exact current
  goal. The pure payload contract is regression-tested.
- The next safe offline implementation is a prospective, append-only, actor-assured goal
  request/action ledger with required bounded idempotency and semantic intent revisions.
  Standalone goal creation and unattached edits are setup/management evidence, not counted
  interventions. A changed binding, semantic update of an attached live goal, or explicit
  supersede counts once per user intent; implicit N-session rebinds never multiply it.
  Initial benchmark setup must be predefined symmetrically and kept outside treatment
  intervention inflation. Until the exact contract exists, `goal_mutation` remains
  unmeasured and the canonical total remains null.

Focused evidence for this repair: goal lifecycle **13/13** (including unchanged projection
identity and bounded-read saturation); broad goal/store/session-control/authority/auth
**67 passed, 2 skipped**; desktop **60/60** and frontend production build clean at 52
modules. The fresh serial whole-tree receipt is **1707 passed, 21 skipped in 828.51 s
(13:48)** with no warning.

### Hostile and integrated evidence

- focused actor/direct-message/attention gate: **27/27 in 18.58 s**;
- shared authenticated session-control regression: **24/24 in 30.21 s**;
- handoff Store regression: **11/11 in 8.10 s**;
- the intentionally large newest-64-blind-spot handoff case passed **1/1 in 235.10 s**;
- repository-wide `uv run ruff check .`: clean;
- final fresh serial whole repository `uv run pytest -q -x`: **1707 passed, 21 skipped in
  828.51 s (13:48)**, with no warning in this run;
- desktop `npm test`: **60/60**;
- desktop `npm run build`: clean, **52 modules** transformed; this is frontend compilation,
  not Tauri/sidecar/installer packaging.

The hostile cases cover auth-before-Store, assured versus internal/unassured reservation,
exact replay, append-only triggers, immutable effect authority, receipt content minimization,
forced terminal receipt failure/transaction rollback, missing actor reservation,
corrupted terminal receipt, restart-to-uncertain with zero delivered receipt, attention
fail-closed behavior, no double counting, and legacy messages remaining unverified.

Fresh check-only `npm run preflight:release` exited nonzero as designed and remains
**NO-GO**:

```text
source_ready:false
release_ready:false
pet_ids: pex, ledger, mesh, nudge, drift, quiet, ember, von
release_input_count:888
tracked_release_input_count:166
untracked_release_input_count:722
hidden_index_input_count:0
dirty_paths:1201
release_input_sha256:4b1b3025daef477a082560f3f62e23380166e512b6ab79b8d0bd39daa8d8e6ea
audit_reachable_input_count:672
audit_closure_sha256:94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470
sidecar_input_sha256:d66906e85c94ced814ea6f67fc6a05e2e5f179cdff4175f7817139ba54000fa3
sidecar_stamp_input_sha256:be840b7c65f57575d0f629dfe2ccccd9c0c026b8352a71985e7a8b8db0b931b0
cursor_observe_sha256:null
toolchains_verified:true
tauri_wiring_verified:true
sidecars_current:false
```

No live harness/provider, bridge/process mutation, package/installer, deploy, publication,
benchmark run/freeze, AWS mutation, Git stage/commit, or submission occurred. Overall state
is still **NO-GO**. Highest-priority Recovery proof remains fresh real Codex + real Strands
under explicit `PEX_LIVE_CODEX=1` and `PEX_LIVE_SUPERVISOR=1` authorization. The next safe
offline attention slice is prospective actor coverage for goal create/update/supersede and
goal attachment, without inferring history or making the canonical human total numeric.
Do not count handoff delivery as assimilation/helpfulness.

## Latest audit/repair checkpoint — non-downgradable exact-turn ledgers, 1 Sep 2026

This is the newest source and verification checkpoint and supersedes the 1690-pass
checkpoint immediately below. The primary agent reread all three binding specs and this
handoff before implementation. Three independent read-only subagents separately audited
direct-message receipts, handoff receipts/recovery, and the new human-decision migration.
Their findings were reproduced and fixed; they did not edit the tree. No live harness,
provider, package, process, Git, deployment, benchmark, AWS, or submission authority was
inferred.

### Human-decision exact-turn authority

- New `human_decision_resolutions` are explicitly contract version 3. Fresh schemas
  default to 3; an old table receives version 1 only during migration. A prospective
  insert trigger rejects every new v1 row, including `INSERT OR REPLACE`, and the update
  trigger makes the discriminator immutable. Historical rows stay v1 without invented
  Codex turn IDs.
- Every v3 read now validates the resolution scalar columns, exact Codex receipt, strict
  bound Intervention envelope, frozen worker target, Intervention state/result/metadata,
  and matching delivery audit projection. A terminal JSON row rewritten to
  `delivery_reserved` cannot cause a second worker send. Attention metrics use this same
  fail-closed loader, so corrupt resolution rows cannot inflate product counts.
- `get_current_human_decision_resolution()` now reads resolution, Intervention, session,
  Decision, and ContextItem in one SQLite snapshot instead of composing several
  independently committed reads.
- First finalization and exact terminal replay validate the receipt against the frozen
  reservation/dispatch target. A concurrent current-session vendor change can no longer
  reject the real accepted turn or cause replay to rebind. Terminal Intervention updates
  preserve the original bound envelope rather than adopting mutable discovery identity.
- The attention pagination fixture now seeds a genuine pre-column legacy row before
  migration; it no longer inserts an authority-looking legacy row after the prospective
  boundary.

### Direct-message and handoff exact-turn authority

- `operator_effects` now has the same prospective version-3 / migrated-version-1
  discriminator, immutable-update trigger, and new-v1 insert/replace rejection. Both new
  `session_message` and `context_handoff` reservations explicitly write version 3.
- `_operator_effect_record()` is now a read-time authority boundary for v3. It binds
  effect columns to the frozen payload, rejects terminal/nonterminal state/result
  contradictions, requires `result.status == state`, and validates a delivered Codex turn
  against the frozen target session/vendor/harness. Stripping or rewriting the stored
  receipt makes Store reads and HTTP/pipeline replay fail closed rather than returning
  `ok:true`.
- Direct-message finalization uses the frozen payload, not the mutable current session.
  Honest first finalization and identical terminal replay survive later discovery drift;
  a conflicting target receipt remains rejected.
- Handoff validation now requires the strict `pex.intervention-bound.v1` envelope and its
  SQL project/vendor/harness/action/version bindings. It validates effect state against
  the canonical Intervention result/action/metadata and the matching delivery audit row.
  Later assimilation audit records do not shadow that exact delivery audit.
- Every new post-dispatch handoff requires its v2 dispatch watermark and candidate
  manifest authority. A v3 handoff cannot be rewritten to a legacy v1 watermark. Truly
  migrated v1 effects remain legacy and are not silently upgraded.
- Handoff first finalization and terminal replay use the frozen target receipt and a
  frozen-bound Intervention update. Restart recovery validates the complete effect,
  Intervention, trigger event, audit, v2 watermark, and candidate manifest before changing
  either ledger. A hostile corrupt-watermark test proves the transaction rolls back with
  the effect still dispatching, the Intervention still in progress, and no uncertain
  audit row.
- The existing SQL Intervention immutability trigger independently blocks attempts to
  replace a canonical handoff envelope with its raw payload; read validation remains a
  second boundary.

### Exact hostile and integrated evidence

- new human-decision hostile cases: **5/5** (terminal reactivation, update/replace
  downgrade, first frozen finalization, terminal replay, legacy migration);
- broad decision/human-delivery/attention cluster: **84/84 in 80.73 s**;
- direct-message + handoff Store hostile/unit gate: **19/19 in 9.46 s**;
- impacted direct-message/handoff REST/E2E gate: **12/12 in 22.20 s**;
- fresh whole repository `uv run pytest -q -x`: **1698 passed, 21 skipped in 780.43 s
  (13:00)**;
- the whole run emitted one aiosqlite event-loop-shutdown warning under
  `test_focus_does_not_inject_worker_text`; the exact test then passed **1/1** with no
  warning, and the complete Cursor contract passed **37/37** with no warning. This is a
  non-reproduced resource-lifecycle warning, not hidden as a failure and not used to claim
  live proof;
- repository-wide `uv run ruff check .`: clean;
- desktop `npm test`: **59/59**;
- desktop `npm run build`: clean, **52 modules** transformed; frontend only, not Tauri,
  sidecar, or installer packaging;
- `git diff --check`: exit 0 with informational Windows LF-to-CRLF notices only.

Fresh check-only release preflight returned nonzero as designed and remains **NO-GO**:

```text
source_ready:false
release_ready:false
pet_ids: pex, ledger, mesh, nudge, drift, quiet, ember, von
release_input_count:888
tracked_release_input_count:166
untracked_release_input_count:722
hidden_index_input_count:0
dirty_paths:1201
release_input_sha256:d1c625bbae9560622cb1957f2ae1cdd8de00ce7c54df2edb155cb4d45922e794
audit_reachable_input_count:672
audit_closure_sha256:94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470
sidecar_source_input_sha256:c954a170550c4dafe876e1776c97c9dda35c1a5e0d3e87bd57b5b8fe35bb429d
stale_stamp_input_sha256:be840b7c65f57575d0f629dfe2ccccd9c0c026b8352a71985e7a8b8db0b931b0
cursor_observe_sha256:null
toolchains_verified:true
tauri_wiring_verified:true
sidecars_current:false
```

The blockers are exactly untracked release inputs, the user-owned dirty tree, and
stale/missing sidecars. Do not clear, stage, commit, build, or package them without fresh
action-time authorization. Exactly eight built-ins remain enforced.

### Exact next actions from this checkpoint

1. **Binding product milestone, separately authorized:** execute the two prepared isolated
   real Codex + real Strands cases with fresh `PEX_LIVE_CODEX=1` and
   `PEX_LIVE_SUPERVISOR=1`, then retain validated v3 proof plus SQLite/JSONL,
   source/process, same-thread continuation, and exact-turn outcome evidence. Offline
   1698/21 does not check Recovery Core sections 0, 1, or 12.
2. **Next safe offline slice:** add prospective terminal actor-assurance receipts for
   authenticated operator direct messages and human-requested handoffs. Until then,
   attention metrics must continue labeling them `unverified_operator_actions` instead of
   inflating the measured human-action lower bound.
3. Make historical handoff/read APIs use one dedicated SQLite read snapshot everywhere a
   response combines effect, bound Intervention, trigger, audit, watermark, candidates,
   and assimilation evidence. Current write transactions are atomic; some descriptive
   read paths still compose through the long-lived connection.
4. Cursor remains a separate real-proof milestone. Only with explicit package authority:
   build the missing observer sidecar, refresh the v3 stamp, package Tauri, and measure
   frozen cold/warm completion inside Cursor's 3-second observe budget. Source and Vite
   tests do not prove PyInstaller or packaged playback.
5. Preserve the lifecycle-producer NO-GO until PEX owns a genuinely isolated disposable
   worktree/sandbox. Keep AWS/deploy, benchmark execution/freeze, Git staging/commit,
   publication, and Devpost submission as separate action-time gates. Deadline remains
   **September 14, 2026, 5:00 PM PDT**; cut speculative polish before the real closed loop,
   exact demo evidence, eight-pet product surface, or release gate.

Overall state remains **NO-GO**. No scored public leaderboard or validated rank exists.

## Latest audit/repair checkpoint — exact delivery, pytest evidence, and packaged observe separation, 1 Sep 2026

This is the newest source and verification checkpoint. It supersedes the older 1653-pass
checkpoint below without deleting its history. The handoff and all three binding specs
were reread, and three independent read-only subagent audits were used to challenge
delivery causality, human-decision durability, pytest evidence, and packaged Cursor
behavior. The operator's deadline and win bar remain binding, but no action-time live,
package, deploy, submit, spend, stage, commit, or process-control authority was inferred.

### Repaired P0/P1 integrity gaps

- Adapter delivery is now normalized by one strict resolver. A Codex bare Boolean `True`,
  non-Boolean `accepted`, missing/malformed/control-bearing/oversized turn identity, or a
  cross-session typed result becomes `delivery_uncertain`; it cannot become delivered.
  Non-Codex Boolean compatibility remains explicit. Direct operator messages, automatic
  and operator handoffs, ActionExecutor delivery, and human-decision delivery all use the
  same contract.
- Exact `pex.worker-delivery.codex-turn.v1` receipts now survive the direct-message,
  handoff, and human-decision Store transactions and their canonical Intervention/audit
  projections. Store independently seal-validates the receipt against the authoritative
  target session. Exact terminal replay is stable; conflicting receipt replay is rejected;
  new delivered Codex human decisions require the exact receipt.
- `ASK_HUMAN`/`human_decision_delivered` is now eligible for the exact-turn outcome
  observer. A same-thread unrelated Codex turn cannot acquire causal credit, while a STOP
  from the exact delivered human-choice turn can produce the same evidence-grounded
  helped/outcome receipt as other active interventions.
- Generic operator-message finalization now rejects `context_handoff` effects, preventing
  an internal caller from bypassing the handoff Intervention/audit transaction. Human
  decision `delivered` is sealed to `send_confirmed` with no exception; contradictory
  delivered/code combinations are rejected before mutation.
- Pytest pass summaries no longer fabricate success without a terminal process exit.
  Generic `status: passed` is not an exit-code receipt, conflicting explicit exit fields
  are uncertain, and only complete terminal summary lines supply counts. Distinct plausible
  summaries cannot select a spoofed count. Passed, collected, skipped, xfailed, xpassed,
  and deselected categories stay separate.
- Persistent count requirements distinguish absent, valid, and ambiguous instead of
  collapsing all three to `None`. Exact and minimum passed/collected requirements are
  bounded and merged only when compatible. Conflicts, ranges, decimals, negation,
  historical language, and unsupported comparators remain uncertain and cannot support a
  claim. Minimum-count violations create an acceptance gap even without an explicit
  worker claim. A malformed semantic requirement requests clarification rather than an
  endless identical pytest probe.
- Packaged Cursor observe and control execution are now physically separated. Frozen
  observe hooks resolve only to `pex-cursor-observe-<triple>` (the fail-open JSONL helper);
  frozen control resolves only to `pex-cursor-hook-<triple>` (the bridge/control helper).
  A missing selected helper aborts before `hooks.json` backup or mutation. Ambient
  `PEX_CURSOR_HOOK_MODE=control` can no longer silently upgrade desktop/default attach;
  desktop and discovery attach pass `mode="observe"` explicitly.
- The observer source is now a sidecar fingerprint input. Tauri exact external-bin wiring
  contains bridge, control helper, and observer helper. The exact sidecar stamp contract is
  version 3 and binds all three SHA-256 values. The new observer is intentionally missing
  from the stale local binary set until a separately authorized package/sidecar build.

### Exact verification on this tree

- focused pytest evidence gate: **62/62**;
- focused Cursor contract: **37/37** after the ambient-mode regression was added;
- release-contract Node gate: **8/8**;
- broad decision/direct-message/handoff durability gate: **213/213 in 237.63 s**;
- exact Codex human-decision same-turn/other-turn causality: **2/2**;
- exact Store bypass/status guards: **2/2**;
- first whole-tree run stopped honestly at **740 passed, 18 skipped** because the release
  inventory assertion still expected 887 inputs; the observer source correctly made it
  888. That stale assertion was updated and its exact preflight regression passed **1/1**;
- final fresh `uv run pytest -q -x`: **1690 passed, 21 skipped in 640.85 s (10:40)**;
- repository-wide `uv run ruff check .`: clean;
- desktop `npm test`: **59/59**;
- desktop `npm run build`: clean, 52 modules transformed; this was frontend TypeScript/Vite
  build only, not Tauri/sidecar/installer packaging;
- `git diff --check`: exit 0, with informational Windows LF→CRLF warnings only.

Fresh check-only release preflight remains correctly **NO-GO**:
`source_ready:false`, `release_ready:false`, exactly **8 pets**, 888 release inputs (166
tracked, 722 untracked), zero hidden-index inputs, 1201 dirty paths, and stale/missing v3
sidecars. Release-input SHA-256 is
`938f83654499eddda4b69dfe019cabfa08a5f86643f73dda095d9a6c7e521b56`;
audit-closure SHA-256 remains
`94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470`;
current sidecar-source SHA-256 is
`94764d234faaf3d0e08b3c6ec55178def4384d04cd4d4c7d44e6f0e7bdcecaeb`, while the
stale v2 stamp still names
`be840b7c65f57575d0f629dfe2ccccd9c0c026b8352a71985e7a8b8db0b931b0`.
Toolchains and the exact three-binary Tauri wiring pass. The built-in fleet remains exactly
`pex`, `ledger`, `mesh`, `nudge`, `drift`, `quiet`, `ember`, and `von`.

No live Codex/App Server, Strands/provider, Cursor, existing bridge restart, process kill,
sidecar build, Tauri/installer package, AWS action, benchmark run/freeze, deploy, publish,
stage/commit, or Devpost submission occurred. Overall status remains **NO-GO**. Recovery
Core remains unchecked until fresh action-time authorization permits the prepared real
Codex + real Strands cases. There is still no scored public leaderboard or validated rank.

### Exact next actions from this checkpoint

1. Highest product milestone, authorization-gated: run the two prepared isolated live
   Codex cases with fresh `PEX_LIVE_CODEX=1` and `PEX_LIVE_SUPERVISOR=1`, preserve v3 proof
   JSON plus SQLite/JSONL/source/process evidence, and revalidate through `validate_proof()`.
2. Highest remaining offline receipt hardening: make the new human-decision receipt
   contract discriminator non-downgradable, validate terminal receipts on read, and make
   exact terminal replay compare against the frozen binding rather than mutable current
   vendor-session identity. Do not backfill legacy turn IDs.
3. Cursor remains a separate real-proof milestone: add a truthful reusable live proof
   contract and exact generation/turn causality, then—only with package authorization—test
   frozen observer cold/warm completion inside Cursor's 3-second budget. Source tests do
   not prove PyInstaller one-file startup latency.
4. Preserve the honest lifecycle decision: do not invent a cleanup producer until PEX owns
   a real isolated worktree/sandbox with creation and disposability receipts.
5. Keep packaging, AWS/deploy, benchmark execution/freeze, and Devpost as independent
   action-time gates. Deadline remains **September 14, 2026, 5:00 PM PDT**.

## Latest Recovery-spec checkpoint — exact Codex continuation causality, 1 Sep 2026

This is now the newest source and verification checkpoint. All three binding specs and the
current handoff were reread before the slice. Recovery §10–§12 requires more than proving
that a follow-up reached the same thread: PEX must observe what happened afterward, and the
audit must make the causal boundary defensible. The prior implementation collapsed Codex's
verified `turn/start` result to a Boolean and then to `"sent"`. Any later supported STOP on
the same thread/goal could therefore be credited as `helped:true`, including an unrelated
human-started turn. Codex events also lacked an immutable vendor reference. That was a real
closed-loop integrity gap, not a presentation issue.

The production path now retains exact continuation identity end to end:

- `CodexAdapter.send_message()` returns a typed `AdapterMessageResult` containing the exact
  vendor thread and the returned vendor turn ID. A malformed/missing/cross-thread identity
  becomes delivery uncertainty; it is never reduced to ordinary success.
- `ActionExecutor` converts a valid Codex result into a content-free
  `pex.worker-delivery.codex-turn.v1` receipt containing exact PEX target session, vendor
  session, and vendor turn. Accepted-outcome to uncertain-outcome mapping is explicit for
  nudge, continue, verification, and handoff rather than string replacement.
- The event-processing effect persists that receipt atomically with its delivered terminal
  state and canonical Intervention. Seal-time validation requires exact keys, bounded
  nonempty/control-free IDs, delivered state, Codex harness, supported message action,
  authoritative Store session/vendor match, and exact effect-result status/outcome/code.
  Failed/skipped/uncertain or contradictory receipts are rejected.
- Codex item and STOP normalization writes canonical `pex.codex-event-ref.v1` JSON with
  exact thread/turn and optional item identity, plus the bounded vendor turn in metadata.
  Conflicting item/params/enclosing-turn identities produce no vendor turn; a nested item
  cannot override its authoritative enclosing turn. Missing vendor turn IDs keep only an
  anonymous bridge event suffix and are not mislabeled as vendor identity.
- Causal outcome matching now requires the delivery receipt, event metadata, canonical raw
  reference, thread, turn, and event ID to agree. A same-thread unrelated turn, forged
  metadata, wrong raw reference, or wrong event ID cannot produce `helped`,
  `goal_evidence_supported`, or `acceptance_still_unsatisfied`.
- Legacy delivered Codex interventions without a turn receipt are finalized honestly as
  `worker_delivery_causality_unavailable_legacy` when encountered; malformed stored
  receipts become `worker_delivery_receipt_corrupt`. Neither can poison the shared pump or
  acquire invented credit. Delivery-uncertain synthetic verification retains its existing
  gather-first/no-duplicate behavior.
- The JSONL/SQLite intervention audit projection includes the exact worker-delivery
  receipt. `tests/contract/codex_live_proof.py` is now
  `pex.codex.closed_loop.v3`: reusable proof requires canonical raw event references,
  exact vendor turns, no delivery receipt on supported NOOP, and exact equality between
  the initial intervention's delivered turn and the final successful STOP turn. A
  canonically rehashed but unrelated turn is rejected.

One adjacent regression was found by independent subagent audit and repaired: the generic
human-decision delivery helper previously accepted only identity `True`/`False`, so the new
typed Codex result was incorrectly classified `delivery_uncertain` after real App Server
acceptance. It now accepts only a valid exact-session bounded typed receipt, rejects a
cross-session/malformed one, and preserves the existing non-Codex Boolean contract.

The prepared live tests also now configure the detected local OpenAI-compatible supervisor
endpoint before constructing the model. An offline AST regression prevents that readiness
step from disappearing. This avoids a false skip at an authorized run; it does not invoke
or prove a live provider.

The pause/resume attention receipt checkpoint immediately below was hardened during the
same audit. Wall-clock ordering is no longer used as the prospective boundary, so a clock
rollback cannot hide a valid new action. Receipt validation now requires exact JSON/column
binding, deterministic identity, bounded revision progression no later than the current
session revision, valid UTC time, distinct session digests, and explicit action semantics
(`pause: false→true`, `resume: true→false`). A valid unbound containment pause is
well-formed but excluded from the measured source count; it does not corrupt the whole
metric. The canonical human-intervention value remains null because coverage is incomplete.

Fresh exact-source verification after all source/test changes:

- focused causality/attention/decision/live-proof gate: **102/102**;
- exact legacy-no-receipt + corrupt-receipt no-false-credit regression: **1/1**;
- broad adapter/pipeline/handoff gate first exposed one real synthetic uncertain-delivery
  regression at 221 passes; the over-broad terminal marker was removed and the exact
  failure plus adjacent gate passed **35/35**;
- final `uv run pytest -q -x`: **1653 passed, 21 skipped in 617.72 s (10:17)**;
- final repository-wide `uv run ruff check .`: clean;
- final `git diff --check`: clean apart from informational Windows LF→CRLF warnings.

Fresh check-only release preflight remains correctly **NO-GO** and exited nonzero:
`source_ready:false`, `release_ready:false`, exactly 8 pets, 887 release inputs (166
tracked, 721 untracked), zero hidden-index inputs, and 1201 dirty paths. Release-input
SHA-256 is `d5b0a9b474a1b48f1c2079b48e0161685fb3073efecabcdbfca2c922b8db3726`;
audit-closure SHA-256 is
`94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470`;
current sidecar-source SHA-256 is
`bb37a07b1c8731503b151b36808dd629bd0ac09abcccadcce68e542d4c8da459`, while the
stale stamp remains
`be840b7c65f57575d0f629dfe2ccccd9c0c026b8352a71985e7a8b8db0b931b0`.
Toolchains and Tauri wiring pass. The built-in fleet is exactly `pex`, `ledger`, `mesh`,
`nudge`, `drift`, `quiet`, `ember`, and `von`. No sidecar or package was built.

No live Codex or supervisor/provider call, existing bridge restart, process kill, sidecar,
installer/package, AWS action, benchmark run/freeze, deploy, publish, commit/stage, or
submission occurred. Recovery Core remains **unchecked** until a fresh operator-authorized
real Codex + real Strands run proves both supported NOOP and incomplete→specific
continuation→exact-turn observed outcome with the v3 receipt. Overall state remains
**NO-GO**. There is still no scored public leaderboard or validated rank.

### Exact next action from this checkpoint

1. Preserve the exact turn/raw-reference authority and v3 reuse gate; do not weaken it to
   same-thread timing or worker narration.
2. With fresh operator authorization for both `PEX_LIVE_CODEX=1` and
   `PEX_LIVE_SUPERVISOR=1`, run the two isolated prepared cases in
   `tests/contract/test_live_codex_pump.py`. Do not use/restart `127.0.0.1:7420`.
3. Retain both proof JSON files, SQLite/JSONL correlations, source/process provenance, and
   exact artifact evidence; validate them again through `validate_proof()` before reuse.
4. Only after that real Recovery milestone, advance the deadline-critical real Cursor
   same-session story and judge-facing evidence. Packaging, AWS/deploy, four-arm freeze,
   benchmark execution, and Devpost remain separate action-time gates.

## Latest spec-correction checkpoint — prospective human session-control receipts, 1 Sep 2026

This checkpoint supersedes the earlier statement that pause/resume is wholly unmeasured.
All three specs were reread. BUILD §21.2 and §58.2 define a human intervention as an actual
user action that alters or unblocks execution, not a PEX request or a mutable UI state.
Existing pause/resume had a strong Store control-revision CAS, but its REST routes used the
ordinary auth dependency and the state transition had no append-only actor evidence.

The pause and resume REST mutations now require `_require_operator_token`. Exact failures
are 403 in explicit test-only no-auth mode before Store access, 401 for missing/wrong
bearer, and 503 when auth is enabled but the bridge token is unavailable. A successful
changed transition passes `local_bridge_operator` plus `bridge_bearer` assurance into the
same Store transaction as the session CAS.

Two new append-only/update-delete-blocked ledgers establish a prospective boundary without
historical guessing:

- `human_session_control_coverage` declares exact independent coverage start rows for
  `pause_supervision` and `resume_supervision` on first Store startup with this schema;
- `human_session_control_actions` records one content-free
  `pex.human-action-receipt.v1` only when the supervision bit really changes.

Each action binds the principal/assurance, session, goal, project and frozen project
binding, before/after control revisions, before/after session SHA-256, and exact occurrence
time. Its ID is deterministic from session, action kind, principal, and resulting control
revision. The receipt insert and session mutation commit together: a forced receipt-insert
failure rolls back the pause/resume state. A replay/no-op click creates no second action.
Direct internal Store calls carry no actor assurance and therefore create no human receipt.
Rows and coverage survive restart; corrupt coverage fails the metrics snapshot closed.

`attention_metrics()` now includes both table watermarks and exact coverage records, counts
only structurally bound, assured, post-boundary session-control actions under
`source_counts.supervision_control`, and removes `pause_resume` from the unmeasured lists.
The canonical `human_interventions.value` deliberately remains **null** and coverage remains
incomplete because goal create/update/supersede/attach, out-of-band context copy/manual
verification, and consented active-human time are not all receipted. No historical state is
backfilled.

The adjacent direct worker-message mutation was also hardened from `_require_token` to
`_require_operator_token`; the same 403/401/503-before-Store boundary is tested. Existing
and new direct-message operator effects still lack a prospective actor-assurance terminal
ledger, so they remain explicitly `unverified_operator_action_counts` and do not inflate
the observed human-action lower bound. The next coherent attention slice is a separate
coverage-bound terminal-action ledger for authenticated delivered direct messages and
human-requested handoffs; automatic/MCP handoffs must never count.

Hostile and regression proof on the exact tree:

- session-control + attention focused gate: **28/28**;
- direct-message durability/auth gate: **6/6**;
- MCP handoff regression: **5/5**; M0/attention route regression: **10/10**;
- desktop: **59/59**, TypeScript/Vite production build clean (52 modules);
- final exact `uv run pytest -q -x`: **1642 passed, 21 skipped in 600.95 s (10:00)**;
- repository-wide Ruff and diff-check clean apart from informational LF→CRLF warnings.

The first whole-tree attempt stopped at 9 passed because one contract fixture called pause
under explicit no-auth mode, ignored the correct 403, and then expected supervision to be
paused. The fixture now temporarily exercises the real bearer-authenticated operator path,
asserts its typed receipt, restores its test-only hook configuration, and its exact test
passes. No auth rule or downstream assertion was weakened.

Fresh check-only release preflight remains correctly **NO-GO** and exited nonzero:
`source_ready:false`, `release_ready:false`, exactly 8 pets, 887 inputs (166 tracked, 721
untracked), zero hidden-index inputs, 1201 dirty paths, and stale/non-frozen sidecars.
Release-input SHA-256 is
`dcbb32819319a6f07e22064e5ee8da443bb7026c5a995ce6a2c7cd7d99fcc057`;
audit-closure SHA-256 remains
`94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470`;
current sidecar-source SHA-256 is
`cba12458e729cde23c383c48383ce9c2723e91d90f1a70c60ce215ca85946e7e`,
while the stale stamp remains
`be840b7c65f57575d0f629dfe2ccccd9c0c026b8352a71985e7a8b8db0b931b0`.
Toolchains/Tauri wiring pass. No sidecar, package, installer, deployment, benchmark, or
submission action occurred. Overall state remains **NO-GO**.

## Latest spec-audit checkpoint — no honest lifecycle cleanup producer yet, 1 Sep 2026

This checkpoint supersedes the earlier ranked instruction to "complete lifecycle cleanup
producer wiring" as if a safe producer merely needed plumbing. All three binding specs and
the complete current implementation were reread. BUILD §24 permits cleanup only after an
agent has genuinely moved on, for low-risk residue whose ownership and provenance are
known; it requires quarantine-first behavior and an intervention-log audit. The existing
Store/executor/Undo foundation enforces those constraints, but repository-wide source
search proves that `register_lifecycle_resource()` and
`mark_lifecycle_resource_cleanup_ready()` have **zero production callers**. Every current
resource is created by a test fixture. There is a second independent producer gap:
`list_lifecycle_resources_for_authority()` also has zero production callers, and the
`SupervisorRequest` built by `Pipeline` contains no projection of cleanup-ready resource
IDs. A model therefore cannot legitimately propose the required exact
`CLEANUP {mode:"quarantine", resource_ids:[...]}` manifest. A guessed ID can reach a
human-facing proposal, but Store authority correctly rejects it before filesystem I/O.
Registration alone would leave the feature operationally dead.

The filesystem ledger itself remains deliberately narrow and correct. It accepts only an
exact existing child path of a verified local project root, with kind `scratch`, `temp`,
`cache`, `sandbox`, or `worktree`; freezes its entity identity, source session, goal,
typed project binding, owner, and creator; rejects roots, outside paths, replacements,
symlinks/reparse points, and ambiguous entities; and permits readiness only after the exact
source session is stopped and the trusted producer supplies concrete evidence. Cleanup is
still operator-authenticated and human-gated, moves only the Store-frozen manifest to
quarantine, records exact outcomes, and supports authority-bound Undo.

Every plausible current producer was traced and rejected for specific reasons:

- `FORK_PROBE` is the best eventual product producer because BUILD §23 expects isolated
  worktrees and safe loser disposal, but the current OpenCode and synthetic forks reuse the
  existing cwd. They create sessions, not PEX-owned worktrees.
- `START_AGENT` also creates only a harness session; no current adapter returns an
  independently owned filesystem child.
- PexBench creates physical sandbox roots, but the workspace is created before the worker,
  becomes the session project root (which registration correctly rejects), and its
  snapshots, receipts, raw logs, and private control records remain required evidence.
  The benchmark manifest is still `frozen:false`, natural public-repository coverage and
  Cursor same-session treatment remain unsatisfied, and treatment-only Store writes could
  contaminate fairness. It is not a disposable producer yet.
- `TemporaryDirectory` users already have lexical cleanup; adapter subprocesses have direct
  lifespan ownership; overlays/config changes have their own apply/revert authority; pet,
  hatch, release, benchmark-log, receipt, and snapshot files are persistent assets or
  evidence, not disposable residue.
- Stale child processes cannot be forced into the pathname ledger. A future implementation
  needs a distinct PID/process-group plus process-start/boot identity and ownership/kill
  authority. ACP/Codex transport children already closed by their owning transport must
  not be mislabeled as abandoned task processes.

Therefore the implementation decision is **NO-GO for a producer today**. Do not add a REST
convenience registrar, path scanner, `.tmp` heuristic, PID heuristic, dummy resource, or a
test-only caller relabeled as production. That would manufacture cleanup availability and
increase deletion risk. Revisit only when either (a) `FORK_PROBE` truly creates and returns
an isolated PEX-owned worktree, or (b) a finalized benchmark controller establishes a
dedicated run-owned sandbox authority, registers it at creation, and marks it disposable
only after evaluator, snapshot, raw-log, and audit finalization. Then require hostile proof
for creation-time registration, stopped-session evidence, replacement races, partial
cleanup, restart recovery, quarantine, Undo conflicts, and retained audit.

No production source or test was changed by this audit, so the exact current verification
receipt remains **1635 passed, 21 skipped**, desktop **59/59** with a clean production build,
and repository Ruff/diff gates clean as recorded immediately below. The next safe offline
product slice is durable actor-assured human-action coverage from a declared migration
boundary, while the real Cursor↔Codex demo, provider calls, package/deploy/freeze/run, and
submission remain action-time gated. Overall release state stays **NO-GO**.

## Latest spec-correction checkpoint — authenticated least-disclosure handoff control, 1 Sep 2026

This checkpoint supersedes the older named weaknesses that the REST handoff mutation was
available in explicit no-auth test mode and that public/audit receipts repeated the full
already-minimized bundle. All three specs were reread. BUILD §28 requires authenticated
localhost HTTP and §32.2 requires authentication for local control APIs; CORE §6, BUILD
§15.3-15.4, and Recovery §16 require the smallest sufficient exact bundle; CORE §17, BUILD
§37, and Recovery §11 require a complete auditable action. The implementation now satisfies
both least-disclosure and exact-audit constraints without rewriting historical v1 rows.

### REST operator authentication is fail-closed

`POST /v1/sessions/{session_id}/handoff` now depends on `_require_operator_token`, matching
the established hatch, lifecycle, project-identity, overlay, and Undo operator-mutation
contract. `require_auth:false` is available only through `Settings.for_test`; no supported
development/release CLI or environment path disables authentication. Exact behavior is:

- explicit test-only `require_auth:false` → **403** before Store lookup, reservation,
  pipeline mutation, or adapter I/O;
- auth enabled with missing, malformed, or wrong bearer → **401**;
- auth enabled but the bridge token is unavailable → **503**;
- exact bridge bearer → the stable principal remains `local_bridge_operator` with
  `human_requested:true`, preserving effect IDs and replay across token rotation.

The handoff E2E fixture now uses the same real authenticated operator pattern as the other
privileged endpoint suites. Automatic handoff and scoped MCP handoff retain their distinct
system/session-bound principals; neither is relabeled as a human operator.

### One exact bundle, content-free broad receipts

New `services/bridge/src/pex_bridge/handoff_views.py` defines
`pex.handoff-bundle-receipt.v1`. A receipt contains only:

- canonical operator effect ID when one exists;
- SHA-256 of canonical ContextBundle JSON;
- exact ordered ContextItem IDs and item count;
- token estimate;
- the canonical detail authority (`operator_effects.payload_json.bundle`) when applicable.

It contains no ContextItem content, objectives, decisions, paths embedded in content, or
other INTERNAL bundle text. Digest equality is proved against the assimilation status and
the immutable operator-effect bundle.

Exact content now has only intentionally narrow consumers:

1. the immutable canonical `operator_effects.payload_json.bundle` delivery authority;
2. the actual target adapter injection/inbox;
3. the authenticated operator REST handoff response, exactly once as top-level `bundle`;
4. authenticated desktop detail, which explicitly calls
   `/v1/interventions?include_handoff_bundle=true`.

Every broader copy is content-free:

- the nested `intervention` in REST/MCP handoff responses carries `bundle_receipt`, not a
  second bundle;
- MCP `pex.handoff` omits the top-level bundle entirely: the source worker gets only the
  receipt, while exact content is delivered to the target;
- `GET /v1/interventions` defaults to a minimized handoff intervention; exact detail is an
  authenticated explicit query opt-in;
- intervention WebSocket/event-bus publication uses the minimized intervention;
- all reserved/dispatching/terminal `intervention_audit` rows and their
  `PEX_INTERVENTION_LOG.jsonl` projections carry the same receipt instead of repeating
  bundle content three times.

The canonical bound Intervention stored in SQLite still retains the full v1 action payload
because current Store validation and historical replay bind it byte-for-byte to the exact
bundle. Removing that second **internal canonical** copy requires a versioned receipt/schema
migration and is not mixed into this compatible boundary hardening. Default HTTP/MCP/event
feeds and audit projections no longer expose the duplicate.

### Hostile coverage and fresh receipts

Tests prove denial occurs before Store/pipeline access, all four auth failure classes, the
six canonical REST effect-state mappings, exact REST bundle presence once, content absence
from nested/default/MCP/event/audit/JSONL surfaces, explicit operator-detail presence,
receipt equality on replay, immutable effect content retention, and exact target delivery.

Current exact-tree receipts after this slice:

- full handoff E2E: **57/57**;
- MCP server + operator-effect + audit-invariant gate: **20/20**;
- exact MCP least-disclosure handoff tests: **2/2**;
- exact REST/audit/event minimization test: **1/1**;
- desktop: **59/59**, production TypeScript/Vite build clean (52 modules);
- final `uv run pytest -q -x`: **1635 passed, 21 skipped in 605.15 s (10:05)**;
- final repository-wide Ruff clean;
- final diff-check clean apart from informational Windows LF→CRLF warnings.

The first full post-hardening run stopped at 719 passed/18 skipped because the deliberately
exact release-input test still expected 886 files. Adding `handoff_views.py` correctly made
the inventory 887; the pinned count was updated, the exact preflight test passed, and the
fresh whole suite passed. That first run also emitted one non-fatal aiosqlite worker-thread
warning after an event loop closed. The named test passed alone with
`PytestUnhandledThreadExceptionWarning` promoted to an error, and the fresh final whole
suite did not reproduce the warning. No source “fix” or completion claim was invented for a
non-reproducible warning.

Fresh check-only release preflight remains correctly **NO-GO** and exits nonzero:
`source_ready:false`, `release_ready:false`, exactly 8 pets, 887 release inputs (166 tracked,
721 untracked), zero hidden-index inputs, 1201 dirty paths, and stale/non-frozen sidecars.
Release-input SHA-256 is
`281011b0cd0f2912d81da55f20f2081ae391437f450a33521eea7c0643aaecd1`;
audit-closure SHA-256 remains
`94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470`;
current sidecar-source SHA-256 is
`de930a0a1c84341760bb4e6f650f00f2e680975aa7ffc7cc84be84f23f74adcb`,
while the stale stamp remains
`be840b7c65f57575d0f629dfe2ccccd9c0c026b8352a71985e7a8b8db0b931b0`.
Toolchains and Tauri wiring pass. No sidecar/package/installer/deployment was built.

### Next ranked safe work — still NO-GO

1. Preserve operator-only REST mutation and the one-exact-bundle boundary. A receipt is not
   bundle delivery or target understanding.
2. Run the operator-authorized isolated real Cursor↔Codex handoff demonstration. Do not
   touch the live `127.0.0.1:7420` bridge or spawn a second Cursor without action-time
   approval.
3. Complete lifecycle cleanup producer wiring and its durable hostile verification.
4. Consider a later versioned canonical-handoff schema migration only if eliminating the
   remaining internal Intervention/effect duplicate is worth migration risk before deadline.
5. Real supervisor/Codex, packaging, AWS/deployment, four-arm freeze/run, and submission
   remain action-time gated. No scored leaderboard/rank is known. Deadline remains
   **September 14, 2026, 5:00 PM PDT**.

## Latest spec-correction checkpoint — immutable indexed handoff routing, 1 Sep 2026

This checkpoint supersedes the availability limitation at the older lines that describe a
newest-64 passive candidate scan and the corresponding ranked recommendation to build an
index later. All three binding specs were reread in full before this slice. The governing
bar remains CORE §§6 and 17, BUILD §15.4 and §37, and Recovery §16: PEX must transfer the
smallest sufficient provenance-backed context, bind the real source and target, and observe
the target's first actions without converting delivery or correlation into proof of
understanding. Every typed receipt therefore still has `verified:false` and
`assimilation_proven:false`.

### Corrected defect and immutable candidate authority

The previous newest-64 scan could silently miss an authentic older delivered handoff even
when an explicit target acknowledgement named one of its exact ContextItem IDs or the target
read its unique transferred artifact. That was a real evidence-availability defect. It is
now replaced by three append-only, update/delete-blocked Store ledgers:

- `handoff_context_candidates` for exact delivered ContextItem ownership;
- `handoff_artifact_candidates` for exact platform-normalized artifact ownership;
- `handoff_candidate_manifests` for one immutable dispatch index commitment.

`pex.handoff-dispatch-watermark.v2` binds a
`pex.handoff-candidate-manifest.v1`, the exact context/artifact candidate counts, candidate
index schema, and SHA-256 digest of every canonical candidate receipt. Candidate rows,
manifest, watermark, and the final reserved→dispatching compare-and-swap are committed in
one SQLite transaction **before adapter I/O**. A forced index insertion failure leaves the
effect reserved, creates no watermark/manifest/candidate rows, and performs no adapter call.
There is no recovery-time backfill from mutable current sessions.

Every candidate load revalidates table columns against canonical JSON; exact effect,
intervention, source/target session, frozen vendor/harness, goal, and typed project binding;
dispatch version and time; bundle digest and exact membership; manifest counts/digest; and
the complete expected context and artifact sets. Relevant v2 deletion, mutation, malformed
JSON, or digest/count mismatch is corruption, never “legacy.” A genuine v1 watermark with
no manifest remains honestly `monitoring_unavailable_legacy` for typed evidence, while its
causal first-action monitor can remain available.

### Indexed routing, corruption boundaries, and path truth

Explicit MCP acknowledgement lookup is indexed by exact target session, goal, typed project
binding, and ContextItem ID. It stops after two fully valid candidates because two proves
ambiguity. One report may deliberately cite exact ContextItems from multiple delivered
effects; each is retained as a separate self-attested acknowledgement. This differs from
passive artifact activity.

Passive read/edit routing is indexed by exact target, goal, project binding, normalized path
hash, and dispatch time. It searches newest-first inside the 24-hour server-time evidence
window, fully validates the selected effect/index, and gives one passive event exactly one
owner. Relevant corruption fails typed derivation closed and cannot fall through to credit
an older effect. A SQLite SAVEPOINT contains optional evidence derivation during ordinary
event ingestion: an evidence/index fault rolls back only optional evidence and is logged,
while the already accepted worker event remains committed. An explicit corrupt ACK still
rolls back its whole progress mutation, including event/context/intervention/MCP mutation and
evidence projections.

Path identity is deliberately conservative. Windows uses an ASCII-only case key so Unicode
fold expansions such as `straße`→`STRASSE` cannot alias distinct artifact names. Windows
drive-root-relative paths such as `\Artifacts\file` remain rejected; exact rooted drive and
UNC handling remains project-bound. POSIX relative paths preserve backslash as a literal
character, so `a\b` cannot alias `a/b`. Canonical paths for the corresponding platform still
match exactly. Basename, suffix, glob, traversal, out-of-root, control-character, and
permission-time `BEFORE` aliases remain rejected.

The status contract now exposes:

```text
typed_evidence_monitoring.available
typed_evidence_monitoring.routing = immutable_dispatch_candidate_index | unavailable_legacy
typed_evidence_monitoring.capacity_limited = false
```

Desktop types and Interventions copy distinguish indexed monitoring from legacy-unavailable
monitoring and retain the mandatory disclaimer. They never present delivery,
acknowledgement, artifact correlation, or early target activity as “assimilated,”
“understood,” or correctly used.

### Hostile coverage and exact current receipts

The E2E gate now includes 65 canonical handoffs followed by an exact acknowledgement and
artifact action for the oldest dispatch, proving the former blind spot is gone. It also
covers corrupt-newer fail-closed/no-fallthrough behavior, independent update/delete trigger
enforcement, manifest deletion, honest v1 legacy behavior, atomic insertion rollback,
corrupt exact-ACK full rollback, Windows Unicode fold-expansion non-aliasing, POSIX
backslash/slash separation, and positive exact-platform matches.

Current receipts on this exact source tree:

- full `tests/e2e/test_handoff_and_permissions.py`: **53/53**;
- adjacent timeout/MCP/protocol/operator/serialization gate: **49/49**;
- focused path gate: **5/5**;
- corrupt exact-ACK rollback and forced candidate-index insertion rollback: **1/1 each**;
- formerly flaky presentation-listener test: **12/12 consecutive fresh processes**;
- full `tests/unit/test_event_processing_pipeline.py`: **11/11**;
- pet atlas runtime contract after its Windows test-portability repair: **10/10
  consecutive fresh processes**;
- final `uv run pytest -q -x`: **1631 passed, 21 skipped in 693.51 s (11:33)**;
- desktop `npm test`: **59/59**; production TypeScript/Vite build clean, 52 modules;
- final repository-wide `uv run ruff check .`: clean;
- final `git diff --check`: clean apart from informational Windows LF→CRLF warnings.

Three broad-run failures were investigated rather than waived. The first run reached 739
passed/18 skipped before exposing a Windows drive-root-relative path regression; the exact
path gate passed after correction. The second reached 598 passed/18 skipped before exposing
a recurrent loaded-event-loop bookkeeping race: a publication task had finished after the
100 ms listener timeout but its done callback had not yet removed the strong reference by
the 150 ms assertion. Publication and pet-snapshot coroutines now discard their current task
in `finally` before completion, while retaining the done callback for cancellation before
the first coroutine step. No timeout or assertion was widened. The third reached 1016
passed/19 skipped before a Windows `Path.replace()` in the pet atlas unit test hit an
external sharing lock. The production writer leaked no handles; the synthetic test now
writes directly into the final evidence layout used by `seal_current_evidence`, preserving
all pixel/hash/sealing assertions without a sharing-sensitive rename. The fresh final suite
then passed.

Fresh check-only `npm run preflight:release` remains correctly **NO-GO** and exited nonzero:
`source_ready:false`, `release_ready:false`, exactly 8 pets, 886 release inputs (166 tracked,
720 untracked), zero hidden-index inputs, 1200 dirty paths, and stale/non-frozen sidecars.
Release-input SHA-256 is
`c2593bf25c31d0b0efc0a9f20ea326ce241f59438ba2a5f3f99f684900e40152`;
audit-closure SHA-256 is
`94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470`;
current sidecar-source SHA-256 is
`f18e65682c04099fef188d771c9ec3d55df5e0a41378d66fcfb1ae9f1c7dce80`,
while the stale stamp records
`be840b7c65f57575d0f629dfe2ccccd9c0c026b8352a71985e7a8b8db0b931b0`.
Toolchains and Tauri wiring pass. No sidecar, package, installer, or deployment was built.

### Next ranked safe work — overall state remains NO-GO

1. Preserve the exact evidence vocabulary and immutable candidate/index authority. Never
   infer target comprehension, correctness, or causation from these receipts.
2. Run an operator-authorized isolated real Cursor↔Codex demonstration and retain source
   discovery, selected bundle, immutable v2 index, target first actions, typed evidence, and
   audit. Do not use/restart the bridge on `127.0.0.1:7420` or spawn a second Cursor without
   action-time approval.
3. Review REST handoff authentication and public/audit duplication of the already-minimized
   bundle as a separate hardening slice without breaking tokenless tests or hiding the exact
   operator demo bundle.
4. Complete lifecycle cleanup producer wiring and its durable verification.
5. Real supervisor/Codex calls, packaging, AWS/deployment, four-arm freeze, benchmark run,
   and Devpost submission remain explicitly authorization-gated. There is no validated
   leaderboard or rank. Deadline remains **September 14, 2026, 5:00 PM PDT**.

## Latest spec-correction checkpoint — post-handoff target evidence, 1 Sep 2026

This section supersedes the older recommendation to build typed handoff-assimilation
evidence next. All three binding specs were reread. The relevant bar is not merely that
PEX injected a compact bundle: BUILD §15.4 requires monitoring the target's first actions
for handoff failure; CORE requires a closed observe-decide-act-observe loop and the
smallest sufficient provenance-backed project context; Recovery §16 requires a real
observed source → stored provenance → computed relevance → minimal bundle → target →
record chain. The implementation deliberately does **not** claim that a target understood,
correctly used, or was caused to act by a bundle.

### Audited defect and corrected truth boundary

The prior E2E acceptance criterion said the target uses the discovered dataset path, but
the test stopped after adapter injection, inbox presence, and delivery persistence. That
was delivery evidence only. Generic later activity and the existing `helped` observer are
still not assimilation evidence.

The new strict/frozen `HandoffAssimilationEvidence` protocol always serializes
`verified:false` and `assimilation_proven:false`. It distinguishes:

- `target_acknowledgement`: a bound target MCP `pex.report_progress` cites the exact
  transferred ContextItem IDs; this is **self-attested** receipt, never use proof;
- `artifact_read` / `artifact_edit`: an accepted target event touches an exact transferred
  artifact path after the causal dispatch watermark; this is **behavioral** evidence,
  still not comprehension, correctness, or causal proof.

User-facing states are `not_delivered`, `monitoring_unavailable_legacy`,
`awaiting_target_evidence`, `target_acknowledged`, `relevant_action_observed`, and
`evidence_window_expired`. Do not rename any state to “assimilated,” “understood,” or
“used successfully.”

### Durable authority and hostile-case closure

`services/bridge/src/pex_bridge/store.py` now has two append-only, update/delete-blocked
ledgers:

- `handoff_dispatch_watermarks`, committed with the target's accepted-event sequence
  before adapter I/O. This catches a synchronous/re-entrant target action emitted after
  injection but before `inject_context()` returns;
- `handoff_assimilation_evidence`, an immutable child of the exact operator effect,
  handoff intervention, target event, bundle digest, ContextItem IDs, source/target
  PEX+vendor+harness identity, goal, typed source/target/goal project bindings, dispatch
  version/watermark, accepted-event sequence or exact MCP mutation, and observed time.

Insertion, replay, restart reads, and the authenticated
`GET /v1/handoffs/{effect_id}/assimilation` path revalidate table columns against JSON,
the complete handoff receipt, bundle membership/digest, immutable event-processing
acceptance snapshot, and MCP principal/mutation/context bindings. Forged historical JSON
fails closed. Ordinary accepted target events tolerate and log unrelated corrupt historical
handoffs so optional evidence derivation cannot roll back the primary event. A corrupt
unrelated handoff also no longer blocks an otherwise valid exact acknowledgement.

Passive path overlap has exactly one deterministic owner: the newest eligible dispatch.
One target read cannot credit multiple handoffs that happen to mention the same artifact.
At most the first read, first edit, and first explicit acknowledgement are retained per
effect. Replays and Store restart do not duplicate them.

Artifact matching is rooted, exact, and adapter-realistic:

- relative paths are normalized only when they are canonical and traversal-free;
- Windows drive/UNC paths are made relative to the frozen project root and compared with
  Windows case-insensitive semantics;
- POSIX absolute paths remain root-bound and case-sensitive;
- absolute out-of-root paths, basename/suffix/glob aliases, drive-relative paths,
  traversal, control characters, and unsafe normalization are rejected;
- a symbolic non-filesystem project ID accepts only a safe already-relative path;
- `EventPhase.BEFORE` read/edit attempts cannot become behavioral evidence. This closes
  Cursor's real `beforeReadFile` false-positive; a denied permission-time attempt is not a
  completed read.

The injected prompt now includes stable `context_id=...`, bounded item file paths, and
deep links while preserving the old provenance-first trust label. A target can therefore
truthfully cite exact delivered items instead of guessing hidden IDs.

### First-action monitoring without overclaiming

Every status read derives the first three meaningful accepted target events after the
dispatch watermark and inside the 24-hour monitoring window from immutable
`event_processing` acceptance snapshots. Status/heartbeat/token noise is excluded. Each
event is labeled only as `other_target_action_observed`, `possible_failure_observed`, or
`relevant_action_observed`. An ERROR/tool failure is visible as a possible failure, but
`handoff_failure_proven:false` remains mandatory because temporal proximity is not
causation. This broader monitor is independent of the narrower typed evidence ledger.

The passive typed-evidence candidate scan is intentionally bounded to the newest 64
matching target/goal handoffs and fills one spare row after a corrupt candidate. This is
an honest availability limit, not a correctness relaxation; high-volume indexing remains
future hardening. The per-effect first-action view itself is not subject to that scan.

### Desktop-visible semantics

The Interventions view now fetches assimilation status only for real handoff
interventions. It renders delivery-only, self-attested acknowledgement, behavioral action,
expired, legacy-unavailable, not-delivered, and endpoint-unavailable states separately.
Every row says `Verified: false · Not proof of understanding or correct use.` A possible
failure among early target actions is visible with the same non-causal caveat. The exact
delivered bundle is expandable with selected item IDs/content, provenance, source refs,
next objective, do-not-redo items, and token estimate. Unrelated operator effects are not
misclassified as handoffs.

### Current focused receipts

- full `tests/e2e/test_handoff_and_permissions.py`: **46/46**;
- handoff operator/MCP integrity + MCP server + protocol/path units: **47/47**;
- strict protocol/path unit gate: **28/28**;
- final phase/timing hostile pair after first-action-monitor changes: **2 passed,
  44 deselected**;
- desktop: **59/59**, production TypeScript/Vite build clean (52 modules);
- final `uv run pytest -q -x`: **1624 passed, 21 skipped in 1018.95 s (16:58)**;
- final repository-wide Ruff clean; final `git diff --check` clean apart from
  informational Windows LF/CRLF warnings.

The first broad post-slice run was interrupted after ambiguous failure markers. A fresh
fail-fast run isolated one real Windows concurrency bug outside the handoff slice:
`HatchRegistry._connect()` checked SQLite's transient `-wal`/`-shm` paths with separate
`exists()` and `is_file()` calls. SQLite could remove a sidecar between those calls, and
the registry mislabeled normal disappearance as an unsafe path. The repair uses one
`lstat` snapshot: absence is safe, while non-regular files, symlinks, and Windows reparse
points remain rejected. The formerly failing concurrent hatch replay passed **5/5**
consecutive processes; hatch durability passed **27/27**; then the exact final whole suite
passed. No timeout or assertion was widened.

Fresh read-only release preflight remains correctly NO-GO: `source_ready:false`,
`release_ready:false`, 886 inputs (166 tracked, 720 untracked), zero hidden-index inputs,
1200 dirty paths, and stale/non-frozen sidecars. Release-input SHA-256 is
`a1c579ae1afacce7e64cacd18c710557e7bdf2ebbc8c3315f13dcf58583aae37`;
current source-to-sidecar input SHA-256 is
`6b530d74914b279e039a513ba74c211f12960e8151c4a6582ed130bd39fd6001`;
the stale stamp records
`be840b7c65f57575d0f629dfe2ccccd9c0c026b8352a71985e7a8b8db0b931b0`.
Toolchains and Tauri wiring pass. No sidecar, package, or installer was built.

### Next ranked safe work

1. Preserve this evidence vocabulary and never promote delivery, acknowledgement, a
   path-correlated action, or an early error into proof of understanding/correctness.
2. Run an operator-authorized isolated real Cursor↔Codex demonstration and retain the
   exact source discovery, bundle, target first actions, evidence status, and audit. Do
   not use the already-running desktop bridge or spawn a second Cursor without approval.
3. Replace the newest-64 passive matcher with an indexed per-artifact candidate ledger if
   high-volume handoff monitoring is prioritized; surface any capacity limitation first.
4. Review REST handoff authentication and public/audit bundle duplication as separate
   hardening slices. Do not break tokenless test/development semantics or hide the exact
   operator demo bundle merely to make the change small.
5. Lifecycle cleanup producer wiring, real supervisor/Codex runs, packaged app, AWS,
   deployment, benchmark freeze, and submission remain authorization-gated and NO-GO.

## Latest spec-correction checkpoint — durable Human Attention Broker truth, 1 Sep 2026

This section supersedes the older client-attention implementation, the older statement
that Now uses a last-40 metric window, and the earlier recommendation to build a durable
attention aggregate next. The three specs were reread for this work. The binding rules
are BUILD §21.2 and §58.2 plus CORE/PexBench reporting: a human intervention is an actual
user action that alters or unblocks execution, not a PEX request, alert, observation, or
autonomous PEX action; human active time is measurable only with consented focus-to-action
intervals; missing numerator/denominator coverage remains null; benchmark interventions
per successful task comes only from exact per-run action logs and independent success.

### Audited defect, end to end

The prior agent's `apps/desktop/src/viewModel.ts::attentionMetrics()` was deleted because
every non-null metric it produced was semantically unsafe:

- `ASK_HUMAN` creation was counted as both “Human interventions” and “Decisions,” even
  though it proves only that PEX requested attention;
- unnecessary-alert rate was `helped=false / every helped-known intervention`, mixing
  autonomous actions with alerts and proving neither alert exposure nor adjudication;
- auto-resolution confidence included almost every non-NOOP/non-ASK action without a
  terminal successful resolution;
- reversals counted `REVERT_OVERLAY` or any truthy `metadata.undo_result`, including
  attempts/failures and unbound metadata;
- only human active seconds correctly stayed null, but it exposed no consent/availability
  contract;
- no metric named its scope, time window, watermark, denominator, completeness, or
  truncation.

The population was also unstable. `App.tsx` fetched `/v1/interventions` every eight
seconds and preferred that nonempty global forensic newest-200 list; only an empty list
fell back to `/v1/deck`, whose current-authority projection was newest 40. Thus metric
scope silently changed between historical/forensic 200 and current/live 40. The same raw
forensic list fed Decisions, so quarantined or A→B-rebound pending rows could reappear;
older valid pending rows could disappear after enough newer interventions. The old
desktop unit test encoded these contradictions and was removed.

### New backend contract and authority split

`Store.attention_metrics()` in `services/bridge/src/pex_bridge/store.py` opens a dedicated
configured SQLite connection and runs all reads inside one `BEGIN` snapshot. There is no
`LIMIT` before an aggregate. `GET /v1/attention/metrics` in `app.py` exposes the strict
`pex.attention-metrics.v1` response independently of adapter probes and display pages, so
the desktop polls it on every detail refresh.

The response always includes:

- `definition_version:1`;
- scope `all_local_durable_history`, with historical authority explicitly included;
- all-time `started_at`, `ended_at`, `as_of`, records considered, aggregate truncation
  false, and detail truncation separate/null when not part of the aggregate;
- canonical SQLite source, consistent-snapshot flag, and max-rowid watermarks for
  interventions, audit, all three decision-resolution ledgers, operator effects, overlay
  operations, cleanup restores, and project-identity resolutions;
- coverage completeness false, coverage start, excluded legacy/unbound source-row count,
  and named unmeasured action kinds;
- `benchmark_evidence:false` as an explicit firewall.

Historical counts use creation/reservation-time immutable evidence and deliberately do
not revalidate today's project binding; otherwise a later rebind would rewrite the past.
Only rows with a persisted immutable project binding are eligible where that source has
one. Legacy/unbound rows are counted as excluded source rows, not silently converted to
measured zero.

The metric groups now mean exactly:

- `human_intervention_requests`: bound durable interventions whose policy verdict is
  `ask_human`. This is never relabeled as a user action.
- `decisions`: union-deduplicated permission, lifecycle, and worker-question resolution
  records, with requested/resolved/unresolved-history/delivery-uncertain counts. It is
  explicitly historical, not the live inbox.
- `current_pending`: every unresolved candidate is scanned without a count limit and
  revalidated in the same transaction through the exact bound intervention, session,
  goal, project identity, and successor authority. The count is exact. The response
  returns the newest 200 items, `items_limit`, and `items_truncated`; it also exact-counts
  live `NEEDS_DECISION` sessions that have no explainable current item. Quarantined,
  superseded, unbound, or A→B-stale rows are excluded from this actionable projection.
- `human_interventions`: canonical `value:null`, `measured:false`, coverage incomplete.
  `observed_count` is only a clearly labeled authenticated lower bound from delivered
  human worker-question responses, delivered permission responses, delivered/denied
  lifecycle responses, operator-authenticated completed overlay undo, completed cleanup
  restore, and project-identity resolution. Source counts remain separate.
- existing direct message/handoff effects are reported only under
  `unverified_operator_action_counts`. Their old rows say `local_bridge_operator` but do
  not retain whether bearer auth was enforced at action time, so they are not promoted to
  human proof retroactively.
- `human_active_seconds`: null/unmeasured, consent `not_configured`, zero measured
  intervals. No wall-time/event-gap inference.
- `unnecessary_alert_rate`: null/unmeasured with numerator 0, denominator 0, and an
  explicit reason that alert exposure/adjudication is not recorded. A local inbox append
  is delivery, not proof the human saw or judged it.
- `average_auto_resolution_confidence`: null/unmeasured until terminal successful
  autonomous eligibility is frozen. The previous broad average is gone.
- `reversals`: unique operator-authorized overlay revert and cleanup restore receipts,
  separated into attempted/completed/failed/delivery-uncertain. Only delivered/completed
  operations contribute to the value.

Coverage remains incomplete because pause/resume, goal mutation/attach, out-of-band
manual context copy, out-of-band manual verification, and active-human focus intervals
do not all have append-only actor-assured receipts. Do not replace the null canonical
human-intervention value with `observed_count`. The clean future closure is an append-only
human-attention action ledger written in the same transaction as each mutation, carrying
actor assurance at action time and a real migration coverage start. Never backfill guesses
from mutable state.

### Desktop wiring and visible semantics

Files changed:

- `apps/desktop/src/types.ts`: strict `AttentionMetrics` contract;
- `apps/desktop/src/App.tsx`: independent metrics poll; a failed refresh clears metrics
  rather than leaving a stale confident value; current pending items come from the
  backend snapshot; deck-current and forensic intervention lists remain separate;
- `apps/desktop/src/components/CommandDeck.tsx`: Now renders backend values verbatim,
  shows “Not fully measured”/“Not measured,” observed coverage, samples/denominators,
  attempt/uncertain reversal counts, all-history/as-of/exact/not-benchmark basis; Decisions
  uses only `current_pending`; the sidebar uses the exact backend current count; a
  truncated pending detail page is disclosed; Interventions is labeled recent forensic
  detail up to 200; per-session action cards say “Recent PEX actions” rather than total;
- `apps/desktop/src/styles.css`: compact metric evidence/basis copy;
- `apps/desktop/src/viewModel.ts`: deleted the unsafe client reducer and generic fake
  formatter;
- `apps/desktop/src/viewModel.test.ts`: deleted the incorrect synthetic metric test and
  updated App wiring assertions so current, pending, and forensic inputs cannot collapse
  back together.

`Pipeline.current_projection()` now probes one extra intervention per session when
possible and returns `interventions_truncated`; `/v1/deck.evidence_basis` exposes it.
This does not turn the deck detail page into an aggregate.

### Benchmark-report closure (separate evidence source)

`benchmarks/report.py` now adds the BUILD-required `human_interventions_per_task` beside
the existing headline `human_interventions_per_success`. It also reports active-human
time without destroying missingness:

- a complete total only when every arm row has available timing;
- an explicitly observed subtotal;
- median and missing-row count;
- per-success timing only with complete timing and at least one success;
- paired available-case median delta, deterministic paired bootstrap interval, and pair
  count.

If any row lacks timing, complete totals/per-success remain null. If a pair lacks timing,
the paired delta remains null. The CSV includes the new arm fields. Product operational
metrics are not imported into the benchmark.

### Tests and exact current evidence before the next whole-tree run

New `tests/unit/test_attention_metrics.py` proves:

1. empty history returns measured zero counts but null unmeasured rates/time/action total;
2. 205 requests produce the same exact aggregate beyond 40- and 200-row detail limits,
   return an exact 204-item current count with a disclosed 200-item page, and reproduce
   after closing/reopening the database;
3. quarantine and A→B rebound retain historical request counts but remove the stale row
   from current pending; an authenticated project-identity resolution contributes once to
   the observed lower bound.

`tests/e2e/test_m0_roundtrip.py` checks the authenticated/versioned REST schema, exact
snapshot flag, null/consent semantics, and benchmark firewall. Benchmark tests cover
complete and partial active-time summaries and one coherent derived report.

Receipts:

- attention Store hostile tests: **3/3**;
- attention + M0 route file: **13/13**;
- benchmark selected report gate: **3 passed, 84 deselected** in 84.52 s;
- desktop: **58/58**, production TypeScript/Vite build clean;
- focused Ruff clean;
- a mixed broader run had one unchanged presentation-task timing assertion fail because a
  finished task remained in a set after 150 ms; that exact test passed alone immediately.
  No timeout/assertion was weakened; it did not recur in the final whole-tree process;
- final `uv run pytest -q`: **1608 passed, 21 skipped in 769.64 s (12:49)**;
- final repository-wide `uv run ruff check .`: clean;
- final `git diff --check`: clean apart from informational Windows LF/CRLF warnings.
- fresh read-only release preflight: `source_ready:false`, `release_ready:false`, 886
  inputs (166 tracked, 720 untracked), zero hidden-index inputs, 1199 dirty paths,
  sidecars stale/not frozen. Release-input SHA-256
  `85fafaf4c34267574c288fedef6725f965e9ee2038ffaa32ef1fbd18a47b54d8`; sidecar
  source-input SHA-256
  `4d7cdff72913a79b29ae142dd1a15a8d5aaf8a9cc659d98b223eddcb806d6276`.
  Toolchains and Tauri wiring pass. No sidecar or installer was built.

### Next ranked safe work after the full gate

1. Reread all three specs and this top section; preserve the dirty tree and NO-GO gates.
2. Preserve the **1608/21** full-gate receipt unless the tree changes. After any change,
   rerun the proportionate focused gate and then the whole suite before calling the tree
   current. Audit failures; do not suppress or merely raise timeouts.
3. Next product-value slice: typed handoff-assimilation evidence, so receipt of a durable
   bundle is distinct from proof the receiving agent actually incorporated it.
4. Then wire lifecycle cleanup to one real producer only if the producer can supply the
   existing immutable resource/manifest authority. Do not add a convenience mutation.
5. A future attention-coverage slice may add the append-only actor-assured ledger from a
   declared migration time, but must not fabricate historical pause/goal/manual actions.
6. Real Codex + real supervisor + same-session continuation/outcome/audit, packaged app,
   AWS, deployment, freeze, and submission remain authorization-gated and NO-GO.

## Latest authority checkpoint — supervisor BYOK/custom closure, 1 Sep 2026

This section supersedes every older suite count, BYOK ranking, and release-input total
later in this handoff. The older sections remain as implementation history; do not use
their rolling counts as current proof.

### Exact current gate

- `uv run pytest -q` -> **1603 passed, 21 skipped in 633.56s (10:33)**.
- `uv run ruff check .` -> **clean**.
- `git diff --check` -> **clean**, with informational LF/CRLF warnings only.
- `apps/desktop`: `npm test` -> **59/59**; `npm run build` -> **clean**.
- Focused provider/config/search/supervisor gate -> **126 passed, 1 skipped**.
- Earlier narrow provider/config gate -> **94 passed, 1 skipped**.
- First full run after the slice was **1599 passed, 21 skipped, 3 failed**. No failure
  was hidden or waived:
  1. one Cursor→Codex auto-handoff test passed alone, as its full 42-test file, after all
     contract tests, and in the final whole-tree process; it was an unproven transient;
  2. release input count was correctly updated from 885 to **886** because the new
     `supervisor_config.py` is a release input;
  3. the Windows immutable-result lock now retries a transient post-close
     `PermissionError` while persistent cleanup failure remains visible. A deterministic
     regression injects two transient unlink failures. The exact former-failure set then
     passed **3/3** and all three paths passed in the final full suite.

This is a green current-tree local gate, not a live model, live Codex, packaged app,
deployment, leaderboard, benchmark-lift, or submission claim. Overall state remains
**NO-GO**. The deadline is still **September 14, 2026 at 5:00 PM PDT**. No scored public
leaderboard was found and no rank is retained.

### Binding spec reconciliation

The three binding specs were reread before this slice. The relevant contract is:

- CORE §4.1: supervisor-model choices include API key, login, local, and custom; custom
  supports OpenAI-compatible or Anthropic-compatible endpoints; credentials stay local;
  login may be unavailable but must say so; BYOK/custom must actually work.
- BUILD §26: provider/model/API key/base URL/auth mode are explicit; no config is a
  deterministic `used_llm=false` path; auto-detection is ordered and logged; provenance
  names provider/model/endpoint/auth and an honest request id; restart must retain the
  chosen routing without exposing credentials; Bedrock/AgentCore remains a distinct path.
- Recovery spec: local/fake tests cannot check off the real Codex + real supervisor
  same-session recovery loop. That live milestone is still authorization-gated.

The previous implementation violated that authority boundary. `PATCH /v1/supervisor`
persisted only provider/model, mutated environment state, could retarget provider ambient
keys through a base URL, let keyless custom OpenAI inherit `OPENAI_API_KEY`, accepted weak
endpoint forms, did not implement custom Anthropic, silently converted unsupported login
into API-key behavior, allowed `.env` to import arbitrary variables into the process, and
could leave config/model/secret state partially updated. Those behaviors are replaced,
not documented around.

### Retained supervisor snapshot and secret authority

New `services/bridge/src/pex_bridge/supervisor_config.py` defines a strict version-1,
revisioned `SupervisorChoice` containing only:

- provider;
- model id;
- auth mode;
- custom protocol;
- canonical base URL;
- credential source (`none`, `environment`, or `secret_store`);
- an opaque secret reference;
- revision/version metadata.

The public representation omits both the raw secret and opaque reference. JSON loading is
bounded at 16 KiB, rejects duplicate/non-finite keys, refuses symlink paths, and migrates
the original two-field provider/model file to an environment-backed snapshot without
inventing a secret. Saving is atomic and uses mode 0600 where POSIX permissions apply.

`KeyringSupervisorSecretStore` stores a bounded versioned envelope in the native OS
credential backend. It accepts only recognized native backend modules:

- Windows WinVault;
- macOS Keychain;
- Linux SecretService or KWallet.

Plaintext, fallback, unknown, or absent backends fail closed. On this host a read-only
probe resolved `keyring.backends.Windows.WinVaultKeyring`, priority `5`. Tests use a fake
store and do **not** write/delete real user credentials. The sidecar build now has
`--collect-all keyring` so dynamic backend modules are included on the next authorized
rebuild; no frozen executable was rebuilt here, so packaged WinVault remains unproven.

Secret envelopes are audience-bound to provider, auth mode, protocol, and canonical base
URL. Named-provider default endpoints are persisted in new snapshots so restart and
audience computation agree. A model-only change can keep the same secret; a routing-
boundary change clears it unless a replacement is explicitly written. Rotation and clear
retire the old value only after commit. Missing/tampered/wrong-audience restart secrets
fail closed and never fall back to ambient provider keys.

### Transactional API/restart path

`GET /v1/supervisor` now returns version, revision, routing, credential source,
configured/readiness state, and sanitized errors without returning a key/reference.
`PATCH /v1/supervisor` accepts a strict full routing patch with optional
`expected_revision`, write-only `api_key`, and explicit keep/environment/clear behavior.
Provider changes reset stale model/base/auth/protocol fields; a base-only custom selection
canonicalizes to provider `custom`. Model catalog refresh has a separate request schema so
a credential cannot accidentally be posted to it.

PATCH is serialized by an async config lock and follows this order:

1. merge one complete desired snapshot;
2. validate revision and routing/auth/protocol/endpoint matrix;
3. stage a replacement secret when requested;
4. resolve the exact candidate secret;
5. construct the candidate model in a task-local `ContextVar` runtime so uncommitted
   routing is invisible to concurrent inference;
6. atomically persist the candidate snapshot;
7. publish global routing and swap the pipeline model;
8. retire the previous secret after commit.

Store failure, candidate construction failure, config write failure, stale revision, and
concurrent writers preserve the prior committed snapshot/model/secret. A staged secret is
deleted on rollback. A concurrency regression proves two writers using the same expected
revision produce exactly one winner. The global FastAPI validation handler strips
Pydantic `input`, `ctx`, and `url` data, so malformed secret input is not echoed by 422
responses or logs. Constructor-failure canaries are also asserted absent from logs.

Startup loads the complete snapshot, resolves only its audience-bound keyring reference,
constructs the model task-locally, and then commits runtime state. Missing secret,
unavailable keyring, invalid snapshot, or unavailable constructor leaves deterministic
operation/model unavailable with a typed sanitized error. It does not mutate environment
state to simulate successful persistence.

### Provider and endpoint behavior

`SupervisorRuntimeConfig` is immutable and validated separately from commit. Global
committed routing and task-local candidate routing are distinct. Supported first-class
auth vocabulary is `api_key`, `login`, `local`, `custom`, `bedrock`, and `agentcore`, with
provider-specific combinations enforced.

Retained working local constructor contracts include named API-key providers, Bedrock,
Ollama, LM Studio, llama.cpp, vLLM, LiteLLM, Writer, and Llama API where their installed
SDK/surface is actually sufficient. Custom endpoints support both OpenAI-compatible and
Anthropic-compatible request/catalog semantics. Mistral currently uses its documented
OpenAI-compatible surface because the native optional dependency is absent.

Truthful unavailable/degraded paths:

- consumer ChatGPT/Claude/Grok login is not reused and `login` never constructs an
  API-key model;
- AgentCore auth never silently becomes ordinary Bedrock;
- Azure OpenAI remains unavailable because deployment/API-version semantics are not the
  generic OpenAI-compatible contract;
- generic SageMaker construction remains unavailable because endpoint/payload schemas
  cannot be inferred safely;
- inference request id remains null when the SDK exposes none.

Endpoint validation now requires remote HTTPS and permits HTTP only for literal loopback.
It rejects localhost aliases, userinfo, query/fragment/control characters, percent or
backslash ambiguity, dot/double-slash paths, default-port aliases, integer/hex IPv4,
IPv4-mapped IPv6, and cleartext LAN/metadata endpoints. Custom OpenAI without a key gets a
harmless explicit placeholder to prevent SDK inheritance of ambient `OPENAI_API_KEY`.
Named endpoint overrides never reuse a provider ambient key; only the explicit generic
PEX credential may accompany such a route. The `.env` compatibility loader is allowlisted
to supervisor/provider variables instead of importing arbitrary environment values.

Do not overstate this boundary. HTTPS hostname DNS resolution/rebinding protection and
cross-origin redirect credential stripping are not yet independently proven. Remote
HTTPS remains allowed. A dedicated redirect/DNS hardening slice is needed before claiming
broad SSRF resistance.

### Provenance and search correction

Supervisor provenance now includes a secret-free SHA-256 configuration fingerprint in
the protocol result, loop, and intervention metadata. It binds the effective routing
choice without exposing key material. Provider/model/base/auth remain explicit and
request IDs remain honest.

Tavily search now follows the binding spec by sending `api_key` in the JSON body rather
than inventing an Authorization Bearer contract. Tests were updated to assert the exact
request shape.

### Desktop Settings contract

`App.tsx`, `SettingsPage.tsx`, and `types.ts` now expose the backend authority rather than
provider/model only:

- auth-mode selector;
- custom OpenAI/Anthropic protocol selector;
- custom base URL;
- password-type write-only API key input;
- explicit keep / use environment / clear credential action;
- revision sent with PATCH;
- source/configured/vault status copy;
- local key state cleared after save;
- provider switches reset stale settings.

Source-level desktop tests assert the write-only key, base/protocol, and vault/source UI.
`npm test` is 59/59 and the production Vite build is green. There was no packaged-window
visual QA and the live companion was not restarted, so do not claim the running Settings
screen contains this implementation yet.

### Files in this slice

Core implementation:

- `services/bridge/src/pex_bridge/supervisor_config.py` (new);
- `services/bridge/src/pex_bridge/app.py`;
- `services/bridge/src/pex_bridge/pipeline.py`;
- `services/bridge/pyproject.toml` and `uv.lock`;
- `services/supervisor/src/pex_supervisor/providers.py`;
- `services/supervisor/src/pex_supervisor/search.py`;
- `services/supervisor/src/pex_supervisor/loop.py`;
- `packages/protocol/src/pex_protocol/supervisor.py`;
- `apps/desktop/scripts/build-sidecar.mjs`;
- `apps/desktop/src/App.tsx`;
- `apps/desktop/src/components/SettingsPage.tsx`;
- `apps/desktop/src/types.ts`.

Tests/contracts:

- `tests/contract/test_supervisor_settings.py` (new fake-store/restart/transaction suite);
- `tests/unit/test_supervisor_config.py` (new file/keyring/build-collection suite);
- `tests/unit/test_providers.py`;
- `tests/unit/test_search.py`;
- `tests/contract/test_cursor_hooks.py` (legacy settings contract updated);
- `apps/desktop/src/viewModel.test.ts`;
- `tests/unit/test_pexbench.py` (Windows lock regression);
- `tests/unit/test_fleet_pets_codex.py` (886-input release closure).

Operational records updated: `STATUS.md`, `DECISIONS.md`, `INTEGRATIONS.md`,
`KNOWN_FAILURES.md`, and this handoff. No staging, commit, cleaning, reset, package,
deployment, publication, benchmark freeze, AWS mutation, Devpost mutation, paid-provider
call, live Codex call, or bridge restart occurred.

### Current release preflight after this slice

Check-only `node apps/desktop/scripts/build-sidecar.mjs --preflight-release` reports:

- `source_ready:false`, `release_ready:false`;
- exactly 8 pets;
- 886 release inputs: 166 tracked, 720 untracked;
- 0 hidden-index inputs;
- 1198 dirty records;
- release-input SHA-256
  `8bb59b2e7f95b3aa3237ab21c822f3cd45d61a841e41d2a19e463210ba3f2012`;
- 672 reachable audit inputs with unchanged closure SHA-256
  `94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470`;
- sidecar source-input SHA-256
  `cb1929107f72192862a135c48687a0730a4bdcb788c3dc2d70f127c57721feab`;
- sidecars not current and frozen inventory not verified;
- pinned toolchains and Tauri wiring verified.

The expected blockers are untracked inputs, dirty worktree, and stale/missing sidecars.
Do not clear them by staging, committing, deleting evidence, rebuilding sidecars, or
packaging without explicit action-time authorization.

### Subagent audit split for this slice

The user explicitly requested subagent delegation. Three read-only auditors independently
reread the specs and inspected non-overlapping boundaries:

- `byok_spec_audit`: extracted the exact CORE/BUILD/recovery requirements and ranked
  missing behaviors;
- `byok_security_audit`: found secret echo/persistence/rollback/audience/ambient-key and
  endpoint issues;
- `byok_provider_audit`: audited provider constructors, auth truth, custom Anthropic,
  catalog behavior, provenance, and SDK mismatches.

The primary agent independently verified every retained finding, owned all edits,
integrated the architecture, ran focused and whole-tree gates, and rejected any claim not
supported by current evidence.

### Next work in deadline order

1. Keep the real Codex + real Strands same-thread outcome/audit loop as the binding product
   milestone. It requires fresh `PEX_LIVE_CODEX=1` and `PEX_LIVE_SUPERVISOR=1`
   authorization; do not initiate it from this handoff alone.
2. Durable attention aggregation is closed by the top checkpoint; do not restore the
   historical newest-200/newest-40 client reducer. Future coverage requires a new
   actor-assured append-only ledger from a declared migration time, never a guessed
   backfill.
3. Best safe offline slice now: add typed handoff-assimilation evidence bound to the exact bundle/intervention and the
   target's first relevant action. Generic target activity is not assimilation proof.
4. Harden HTTPS redirect/DNS behavior and, with explicit package authorization later,
   verify real packaged WinVault write/read/delete without exposing a real key.
5. Wire lifecycle cleanup to one real tightly scoped producer only after its ownership,
   path manifest, and Undo contract are exact. Do not invent broad temp cleanup.
6. Once live/product proof is authorized and green, prioritize the <=5 minute judge story,
   clean reproducible exact-eight package, current packaged visual QA, builder posts, and
   Devpost assets before the Sep 14 deadline. Submission remains a separate explicit gate.

### What PEX is (do not redefine)

Independent supervisor over **already-running** coding agents. Recovery spec: real persistent goal + real observation + **NOOP** or a **specific evidenced** intervention. Canned `PEX:` worker nags are forbidden. A stop event is a trigger to **inspect**, not proof of failure. CORE development order: Codex deep → Cursor deep → supervisor behaviors → pet → JIT → more harnesses → **only then** four-arm. Recovery §0 still says the core milestone is a **real Codex session** observed by a real supervisor. Fake App Server tests are local contract only.

### Fresh current-tree receipts — 31 Aug 2026

| Gate | Last honest result | Notes |
| --- | --- | --- |
| `uv run pytest -q` | **1567 passed, 20 skipped** (385.04s, 1 Sep) | Fresh exact-tree receipt after overlay/full-gate repair, truthful Pet/Deck authority, anti-overfit projection, and two release-seal/preflight regressions. Initial run was 1527/20 with 34 failures; the repaired previous-failure matrix passed 186/186 together; first repaired full gate was 1562/20. |
| `uv run ruff check .` | **clean** (31 Aug) | Fresh repository-wide receipt. |
| Desktop `npm test -- --runInBand` | **51 passed** (31 Aug) | Fresh current desktop receipt, including exact-eight fleet and truthful overlay Undo pending/conflict/uncertain/completed state. |
| Desktop `npm exec tsc -- --noEmit` | **clean** (31 Aug) | Fresh TypeScript receipt. |
| Desktop `npm run build` | **clean** (31 Aug) | Fresh Vite production build. This is not a Tauri installer/package. |
| Tauri `cargo test` / `cargo check` | **8 passed / clean** (31 Aug) | Fresh Rust and compile receipt; no package was built. |
| Phase2B cleanup focused gate | **87 passed, 1 skipped** | Overlapping lifecycle-resource, cleanup-ledger, executor, resolution, and restart tests; the skip is Windows symlink privilege. This is not a full-repository suite. |
| Phase2B restore Store/lifecycle gate | **93 passed, 1 skipped** | Separate immutable restore ledger, recovery, disabled generic updater, intervention/audit projection; overlapping focused bundle, not a full-suite total. |
| Restore executor + integration | **64 passed, 1 skipped** agent receipt; **31/31** independent lower-stack rerun; **45/45 selected** integrated Undo rerun | No-replace restore, partial/cancellation/replay, path-free receipts, REST/Desktop Undo. The selected gate deselected 18 unrelated cases. |
| Overlay end-to-end local contract | **70/70 expanded overlay; 32/32 REST; 51/51 desktop** | Store, executor, recovery, REST, and desktop are integrated. Real vendor acknowledgement remains unproven. |
| Phase2B focused Ruff / diff-check | **clean** | Scoped source/test lint and diff integrity only, not repository-wide certification. |
| Direct overlay revert operator auth | **1 focused test passed; broad goal-lifecycle file 9 passed** | `--no-auth` now returns 403 before executor/adapter work; the broad fixture is auth-enabled. |
| `uv run python benchmarks/four_arm.py readiness` | **`can_freeze`: false** | `cursor_hook_mode`: **observe**. Observe hooks do **not** count as same-session stop treatment. |
| Four-arm freeze / headline lift | **not allowed** | No coherent 20-row file, no natural public-repo half, no `cursor_same_session_treatment`. |

`git diff --check` is clean apart from informational LF/CRLF warnings. `npm run validate:pets` proves the exact ordered built-ins are `pex, ledger, mesh, nudge, drift, quiet, ember, von`. A read-only `pet_atlas_runtime_contract.py` run against all eight with `--seal-current-evidence-root apps/desktop/src/pets/_audit/release/current-20260831` returned `ok: true` for every atlas, no repairs, and no occupied unused cells. That source/runtime contract is complemented by the separate 72/72 direct-playback receipt below; neither replaces packaged Tauri QA or a current installer.

### Full-gate failure audit and repair

The first whole-tree run after overlay owner hardening was **1527 passed, 20 skipped, 34 failed**. Each failure was inspected; production authority was not weakened to recover old tests.

- Pipeline cluster: **90/90** across handoff/permissions, speculative execution, adapter capabilities, pet snapshot, pipeline serialization/session merge, and intervention authority. A genuine bug was fixed: an ASK_HUMAN `FORK_PROBE` triggered by STOP left the session `STOPPED`, so Store correctly rejected later approval. Pending human `START_AGENT` / `STOP_AGENT` / `FORK_PROBE` now projects `NEEDS_DECISION`; ordinary STOP/NOOP remains `STOPPED` and has an explicit regression.
- Store fixture/fingerprint cluster: **65/65** across audit outbox, canonical queries, fingerprints, M0, and MCP decisions. Fixtures now use real persistent goal/session/project bindings and typed Windows aliases. A genuine Store bug was fixed: fingerprint SQL still read legacy bare intervention JSON even though current rows are `pex.intervention-bound.v1` envelopes. Queries now use envelope-first `COALESCE` with legacy fallback; tests assert the bound schema.
- Proof cluster: **15/15** across MCP verify-claim, AgentCore pipeline, Codex live-proof validation, and intervention authority consumers. The shared live-proof helper now requires the exact bound-envelope schema and checks frozen session/goal/project/vendor/harness/action/version fields before comparing the payload. MCP and AgentCore fixtures use authority-bound event acceptance and exact goal CAS.
- Root overlay/E2E repair: the exact-owner real-Store executor regression and the pause/rebind/terminal replay E2E both pass. The whole original-failure set then passed **186/186 together**, ruling out order-only fixes, before the first repaired **1562/20** run.

Post-gate red-team found and closed two additional presentation-truth gaps:

- `Pipeline.current_projection()` now performs bounded O(n) revalidation through existing Store authority APIs. Pet derives sessions, goals, interventions, events, counts, headline, message, and last action only from current live bindings; `/v1/deck` returns only current-authority sessions/interventions while fingerprints remain explicitly historical. Quarantined and A→B-rebound rows remain available to forensic Store reads but cannot look working/drifting/needs-you or current in the UI. No new Store API or authority relaxation was added.
- `decorate_agent_fingerprint()` preserves one observed premature-session failure/count/rate but recommends no overlay from one anecdote. `evidence-before-done` appears only after two distinct gap sessions, matching the planner's existing anti-overfit execution threshold.
- Independent combined focused receipt: **29/29** plus scoped Ruff clean. The fresh whole-tree gate including the release-boundary tests is **1567 passed, 20 skipped**; repository-wide Ruff and diff-check are clean.

### Current identity/lifecycle checkpoint (focused contracts included in fresh whole-suite proof)

- Creation-time project binding for credentials and handoff recomputation is complete. Retained focused receipts are **141 Store-focused tests**, **42 authority-bound consumer tests**, **6 credential integration tests**, and **42 repaired broad E2E handoff/permission tests** passed. These sets overlap; do not add them into or present them as a new full-suite result.
- Intervention and permission/lifecycle-resolution binding is complete in focused local proof: session/goal/project/typed-project/vendor/harness/action identity is frozen at creation, action hashes are immutable, dispatch/finalization is versioned CAS, interrupted dispatch is not replayed, and exact deny/STOP containment survives quarantine while authority-increasing actions fail closed. Retained integrated receipts are **78 tests passed** plus the final **38-test resolution-identity suite**; they overlap and are not a whole-suite total.
- **Phase2B cleanup foundation/integration is complete in focused local proof.** Lifecycle resources and cleanup child operations carry immutable target/identity fingerprints and revisioned state. Cleanup reserve creates the durable child; `start_cleanup_operation` is the sole dispatch grant and returns the canonical frozen manifest. The executor moves only those exact manifest entries after that CAS, then finalizes exact per-resource outcomes. Partial, ambiguous, cancelled, or interrupted work is never blindly rolled back or replayed.
- Restart preserves exact parent/child truth: a prior-boot dispatch is classified from the durable child, a merely reserved child stays inert and cannot make its parent look started, and a missing/corrupt/mismatched link makes the parent uncertain rather than successful. The combined focused gate is **87 passed, 1 skipped** (Windows symlink privilege); focused Ruff and diff-check are green. These tests overlap the earlier lifecycle sets and are **not** a new full-suite total.
- **Phase2B restore is complete in focused local proof.** `lifecycle_restore_operations` and its resource joins freeze cleanup/intervention/session/goal/project/vendor/harness/action/manifest/operator/idempotency identity with scalar+JSON triggers and revisioned transitions. Existing terminal requests replay from frozen non-live evidence even after A→B; new grants and start stay live-bound. Start is the sole CAS returning the canonical reverse manifest. Finalize/recovery atomically project exact outcomes into resources, the original intervention, and audit without changing the frozen `ProposedAction` or action hash.
- The executor accepts only `(intervention_id, authorized_by, idempotency_key)`, never caller paths/manifests. It revalidates exact source/destination identity, requires the original parent to exist, uses atomic no-replace rename on Windows/Linux/macOS, fails closed elsewhere, never rolls back partial success, shields finalization on cancellation, and exposes only a path-free `{ok, code, status, replayed, receipt}`. REST requires operator auth plus one bounded key; desktop reuses that key for an identical retry and refetches Store truth. The generic lifecycle-resource updater now always raises `PermissionError`.
- Exact restore receipts: new Store restore file **11 passed**; overlapping Store/lifecycle bundle **93 passed, 1 skipped**; executor bundle **64 passed, 1 skipped**; independent lower-stack rerun **31 passed**; route file **17 passed** plus the updated recovery Undo case; integrated selected Undo rerun **45 passed** with 18 unrelated cases deselected. These overlap; current desktop and full-tree certification are recorded in the fresh receipt table above.
- **Overlay Store authority is accepted in focused local proof.** Bound overlay and operation rows freeze session/goal/project/vendor/harness/overlay/action/owner/parent/request/version truth in scalar columns plus canonical JSON with lifecycle triggers. New apply requires an attached persistent goal, a live project identity, and the exact harness adapter. Start is the sole CAS grant and returns the canonical frozen operation/overlay/session/adapter/rollback bundle. Terminal replay and exact authority-reducing revert do not reacquire mutable live authority, so they survive pause, quarantine, and raw project key A→B without redirecting to B.
- Runtime serving joins only a delivered apply against the current immutable identity and fails closed for pause, quarantine/rebind, expiry, reserved/dispatching/delivered/uncertain revert, malformed/unbound rows, or overflow. Owner-based Undo does not trust `ProposedAction` metadata: a partial unique apply-owner invariant plus transactional exact-owner recount selects one delivered bound apply. Expiry uses indexed `(expires_at,id)` keyset pages, advances past more than 1000 poison rows, and coalesces overlapping sweepers whose attempt N finished after their sweep start; only a genuinely later sweep may allocate N+1 after known failure/skipped. Delivery uncertainty never auto-retries.
- The original Store-only overlay checkpoint was `tests/unit/test_overlay_store_authority.py` **7 passed** and that file plus `tests/unit/test_resolution_dispatch_identity.py` **45 passed**. Consumer/recovery integration is now closed in the dedicated overlay section below and in the fresh full-tree receipt above.
- No production lifecycle-resource producer exists yet. A PexBench sandbox that has reached a durable finalized state is the only credible future source currently identified, but no registration/wiring exists. Tests and manually seeded resources do not prove a production cleanup target.
- Deadline triage remains proof-first: close these authority boundaries, re-establish local gates, then seek the action-time-authorized real Codex proof. Release/package and live Codex remain NO-GO and action-time gated. Do not spend the remaining window on leaderboard chasing: no scored public leaderboard was found and no validated rank is retained.

### JIT overlay locally integrated end to end; live-vendor proof remains

The Store, executor, pipeline/recovery, REST, and desktop now consume one immutable overlay operation protocol. Local contract closure:

- `overlays` and `overlay_operations` freeze session/goal/project/vendor/harness/hash/owner/parent/request/version truth in scalar columns plus canonical JSON with transition triggers.
- Every new apply requires a real live bound `APPLY_OVERLAY` intervention whose action is ALLOW, reversible, and the exact same fresh overlay proposal, session, goal, and project. Rollback is Store/executor-owned and deliberately excluded from the proposal comparison. Ownerless, wrong-overlay owner, DENY owner, and an owner deleted after reservation all refuse before probe or adapter I/O. Terminal receipts remain non-live forensic replay.
- Executor reserves before capability probing. Store start CAS is the sole dispatch grant and supplies the canonical frozen session/overlay/adapter/rollback bundle. OpenCode Store projection is proven to call no fake overlay adapter. Cancellation retains finalization before reraising; a transport ambiguity becomes `delivery_uncertain` and is never blindly replayed.
- Automatic overlay children bind the exact parent effect action type, exact overlay id, session, and intervention owner. Apply cannot link to a revert parent or vice versa. Startup/event recovery consumes known child truth before mutable session/goal/planning gates and cannot downgrade a known terminal receipt to generic uncertainty.
- Runtime serving still fails closed after project A→B, quarantine, pause, expiry, uncertain revert, malformed/unbound rows, or overflow. Exact authority-reducing revert and terminal replay survive those mutable-state changes and cannot redirect to B.
- Expiry uses indexed keyset pages beyond 1000 rows and coalesces overlapping sweepers. Failed/skipped attempts only retry from a genuinely later sweep; uncertain/delivered/dispatching work never does.
- Direct and intervention Undo require operator auth and a stable bounded idempotency key. Intervention Undo selects the exact delivered owner-bound apply, uses reason `operator_undo`, and atomically projects canonical intervention outcome/audit. Receipts expose only stable path-free fields. HTTP maps delivered/pending/not-found/conflict/uncertain honestly; desktop keeps the same key for the same intent, refetches canonical truth, and claims completion only for delivered+ok.

Important independent defects caught during review and repaired:

1. Intervention Undo used `intervention_undo`, which bypassed the Store's exact `operator_undo` projection. It now uses the canonical reason and has direct projection assertions.
2. A skipped child could previously be linked under the wrong overlay operation kind. Parent binding and event finalization now derive and require exact `apply`/`revert` plus exact overlay id.
3. Apply previously accepted a missing or arbitrary owner string. Store creation, reserved replay, and start all revalidate the exact live owner before external I/O.
4. Desktop used the non-canonical `overlay_reverted` outcome; it now projects `overlay_reverted_by_human`.

Receipts: expanded overlay suite **70/70**; earlier cross-layer overlay/event/recovery bundle **109/109**; REST route files **32/32**; desktop **51/51**, TypeScript clean, production Vite build clean. The adversarial real-Store executor regression proves ownerless and mismatched owners create no operation, activate no overlay, and never call `probe` or `apply_overlay`.

Honest limit: this is strong local Store/mock-plugin/mock-adapter evidence, not a live OpenCode/Codex/Cursor vendor acknowledgement. Legacy rows without an operation receipt fail closed as inactive; migration does not invent delivery. Synthetic adapter state remains process memory.

### Realtime socket cancellation leak repaired

The first post-overlay full suite exposed one late failure: the authenticated event socket remained in `state.sockets` after TestClient exit. This was not dismissed as flaky. Starlette sends `websocket.disconnect` and immediately cancels an AnyIO scope; the handler caught cancellation but awaited child joins and an async registry lock before unregistering. Level-triggered cancellation could interrupt that `finally`, leaving a stale capacity entry.

`AppState` now uses a small synchronous socket-registry lock with cancellation-free `register_event_socket`, `detach_event_socket`, `detach_all_event_sockets`, and snapshot helpers. A socket registers only after successful accept; handler `finally` detaches it before the first await; queue-full detaches before close; lifespan shutdown atomically empties the registry before closing sockets. `test_websocket_cancellation_detaches_before_blocked_tail_cleanup` forces a blocked durable tail and cancellation, then requires sockets, queues, and send locks to be empty immediately. The original auth test was strengthened to the same immediate three-map assertion. Focused websocket/broadcast suite: **8 passed**; the fresh full **1567/20** gate includes it.

### Release/package audit after the exact-eight current-evidence contract

The exact ordered built-in pet source contract is `pex, ledger, mesh, nudge, drift, quiet, ember, von`; source validation and desktop tests pass. The current evidence root is `apps/desktop/src/pets/_audit/release/current-20260831`: all eight repo runtime contracts pass; **456 exact decoded RGBA frames**, **72 GIF previews**, and eight contact-sheet, direction-sheet, continuity, and frame-review sets were generated; independent ordered-frame visual QA passed all eight. A later isolated-browser pass now closes the earlier animation limitation for **72/72 state cells**; exact receipt boundaries are below. The generic external hatch validator reports false only because it requires an extended idle cell at row 0, column 6; PEX's runtime contract intentionally requires that unused cell to be transparent, so it must not be repopulated to satisfy that incompatible validator.

Release closure is still **NO-GO**: the evidence and critical release inputs are untracked in this dirty tree; the surviving debug MSI/NSIS are from 28 Aug; no current release bundle exists; and all eight atlases embedded in the old frozen bridge differ from the current release-manifest hashes. Current screenshots/video do not prove the real 15-step Cursor+Codex loop. Do not call the historical installers, generated GIFs, or UI-only captures current live evidence. No package, stage, commit, deploy, publish, or submit action was performed.

The source-side release chain is now fail-closed rather than one-way. `release-manifest.json` is schema 2 and hashes both `_audit/release/manifest.json` and the 72/72 direct-playback receipt; the fleet audit is schema 2 and independently binds the same receipt. `build-sidecar.mjs` validates that chain transitively: exact ordered eight, eight v2 atlases and old per-pet receipts, canonical non-traversing evidence paths, distinct blind-review artifacts with semantic pair records, the current runtime contract, 72 uniquely named GIFs, 25 timed screenshots, and all 456 hash-bound decoded frame PNGs. Changing any nested artifact without resealing the manifests now fails pet validation and changes the sidecar source fingerprint. Cached sidecars also re-run `--verify-bundle` in an isolated home before reuse; a matching old stamp is no longer sufficient.

`npm run preflight:release` / `node scripts/build-sidecar.mjs --preflight-release` is a check-only source gate. It emits `pex.release-preflight.v1` JSON, always leaves `release_ready: false` because installer inspection is a separate authorized stage, requires every release input to be Git-tracked and the entire worktree clean, rejects skip-worktree/assume-unchanged index flags, verifies exact Tauri sidecar/capability/version wiring and active pinned toolchains, recomputes the authoritative sidecar source fingerprint, checks both helper bytes against the target-triple stamp, and only then runs the frozen exact-eight inventory smoke. It snapshots the full release-input hash, source fingerprint, and Git status again after any smoke to catch mutation by a cached executable. The current result is correctly **NO-GO**: **1,054** release inputs inspected, **888 untracked**, **1,191 dirty status records**, and `stale_or_missing_sidecars`; Tauri wiring and active toolchains are green. The old stamp records `be840b7c65f57575d0f629dfe2ccccd9c0c026b8352a71985e7a8b8db0b931b0`, while current source is different. Node is pinned by `.node-version` to 24.19.0, Rust by `rust-toolchain.toml` to 1.97.1, Python by `.python-version` to 3.12.13, and the installed PyInstaller 6.22.2 is checked against `uv.lock`.

A clean checkout still cannot reproduce the boundary until the operator authorizes a reviewed tracking/commit action. Critical release source/evidence remains untracked, seven pre-Von pet manifests/atlases and package/Tauri wiring remain modified, `target/release` and `target/release/bundle` remain absent, and the surviving debug/PyInstaller artifacts are stale intermediate outputs. No installer/package was built. After an authorized clean source boundary, rerun the source preflight, rebuild sidecars, and then add a separate post-package receipt that reopens the actual MSI/NSIS and compares embedded sidecar/pet bytes; the source gate deliberately does not claim this final bundle proof.

Direct animated QA is now **PASS for all 72 state cells** in `current-20260831/direct-playback-qa.json` (11,397 bytes; SHA-256 `57d63ccc75290b7660b45f3aa8c227156b71d9f2d8f67be9879548603fd87a9f`). Isolated local `file://` browser sessions displayed all nine GIF states at intended 192×208 scale. Timed visible-viewport screenshots and per-stage RGB diffs prove 72/72 changed; extra phases closed initial alignment on `mesh/idle` and `ember/waving`. Qualitative review found stable identity/scale, distinct semantics, correct opposed travel, and no blank/missing frame or reversed gait. All 72 GIF hashes/lengths match `runtime-contract.json`, frame counts are expected, every decoded frame is unique within its GIF, and an independent receipt check verified 28 bound artifacts with zero failures. The viewer's canvas sampler raises a local-file taint `SecurityError` and leaves its status loading/error, so the receipt explicitly excludes that status from evidence. This receipt supersedes only `visual-qa.md`'s old “GIFs did not animate in this review path” limitation; its direction warnings, external-validator discrepancy, Git/sidecar/build/package gates, and packaged Tauri QA remain unchanged. All named browser sessions were closed.

### Live Cursor observe on this machine (not control)

Installed: `C:\Users\JosephMayo\.cursor\hooks.json` → `.venv\Scripts\python.exe -S …\pex_cursor_observe.py`, **timeout 3**, **no failClosed**, `loop_limit: null` on stop/subagentStop. Does **not** install `beforeShellExecution`, `preToolUse`, `beforeReadFile`, `beforeMCPExecution`. Helper: `integrations/cursor-hook/pex_cursor_observe.py` — stdlib only, compact JSONL to `{PEX_HOME}/hooks/cursor.jsonl` (`~/.pex/hooks/cursor.jsonl`), never urllib/bridge. Strips `edits` / shell `output`. Adds `observed_ns`. Extracts `conversation_id` / `generation_id` / `file_path` / `command` / `cwd` **and now** first `workspace_roots[]` entry plus `"workspace"` as cwd fallback, even from huge truncated stdin (`test_cursor_observe_helper_keeps_workspace_root_when_edits_are_huge`). Inbox pump: companion `_cursor_observe_loop` → `apply_cursor_hook` with `_delivery_channel="observe"`. Observe `stop` is **not** a waiting hook; `SEND_NUDGE` records **`send_failed`**, no fake `followup_message` (`test_observe_inbox_stop_records_send_failed_instead_of_fake_followup`). Same-session Cursor stop follow-up is **not** claimed. Live proof conversation `ca942dcb-7937-4823-8f7b-06042d2951e6` wrote `afterFileEdit` for the observe helper. Store `add_event`: timestamp-only replay of the same `event_id` is idempotent.

### Observe-only desktop inventory tiles (landed this session; local contract)

Process-inventory rows (`{harness}:desktop`, `vendor_session_id=="desktop"`, `metadata.source=="desktop"`) are **not** vendor threads.

1. **Persistent goal attach is refused.** `POST /v1/sessions/{id}/attach` → **409** for every starter desktop tile, not only ChatGPT.exe. Isolated App Server threads and `cursor:conv-*` / hook sessions still attach. Proven: `test_cannot_attach_a_goal_to_the_chatgpt_desktop_tile`, `test_cannot_attach_a_goal_to_cursor_or_opencode_desktop_tiles`.
2. **Refresh will not keep a leftover `goal_id` on those rows.** `upsert_desktop_observe_session` writes `goal_id=None`. `Pipeline.refresh_desktop_sessions` upserts with `allow_goal_change=True` for observe tiles so store cannot copy an old goal back.
3. **Send is fail-closed.** `is_desktop_observe_session` gates `send_message` on Cursor (even if ACP is connected), OpenCode (even if HTTP transport is connected), Claude Code, and ACP harnesses (Hermes/Kimi/OMP). Codex already refused ChatGPT.exe (`is_chatgpt_observe_session`). Proven: `test_chatgpt_desktop_session_cannot_start_app_server_turns`, `test_cursor_desktop_tile_cannot_send_even_with_acp`, `test_opencode_desktop_tile_cannot_prompt_the_http_server`.
4. **Companion UI.** `canAttachPersistentGoal` is false for `*:desktop` / `source=desktop`. Inspector select is disabled; creating a ledger does not auto-attach to the inventory tile. Codex App Server threads still must **not** claim ChatGPT.exe focus (`canFocusSession`); only `codex:desktop` can focus the exe.
5. **Context handoff cannot target or originate from those tiles.** `POST /v1/sessions/{id}/handoff` → **409**. Auto-handoff skips desktop sources and siblings. **Both directions** are local-contract proven: Cursor conversation → isolated Codex `turn/start` (`test_auto_handoff_from_cursor_conversation_reaches_isolated_codex_not_desktop`); isolated Codex AGENT_RESPONSE → Cursor ACP `session/prompt` on `conv-back`, never `desktop` (`test_auto_handoff_from_isolated_codex_reaches_cursor_conversation_not_desktop`). Neither is a live `codex` binary nor this editor’s observe-only ACP.

This is **not** a live Cursor→Codex handoff on this desktop. It is the identity/honesty layer so a later live handoff cannot dump context into ChatGPT.exe or a generic Cursor.exe row.

### Codex deep (local fake App Server — not live `codex`)

- Isolated WORKING/VERIFYING/DRIFTING/NEEDS_DECISION/BLOCKED threads (and `metadata.isolated`) survive ChatGPT.exe being open. Idle listed threads still drop if transport is down. Discover also `_observe_desktop_session()` after thread list.
- `codex:desktop` cannot `turn/start`. Pump ignores `threadId=desktop` / unknown / none / ChatGPT observe sessions. Approvals on desktop refused.
- Discover attach never auto-spawns App Server. Omitted `kind` for Codex prefers desktop; if no ChatGPT tile, **400** requiring `kind=stdio` or `POST /v1/adapters/codex/attach`.
- Closed loop on `CodexAppServerTransport`: false “tests passed” STOP → `SEND_NUDGE` + `turn/start` **same `threadId`**, no `PEX:` prefix; genuine passing pytest STOP → **NOOP**; missing `report.txt` STOP → same-thread specific nudge. Tests in `tests/unit/test_codex_pipeline_pump.py` / `test_fleet_pets_codex.py`.
- Live Codex still needs **`PEX_LIVE_CODEX=1`**. Recovery §25 Core boxes stay **unchecked** until a real App Server log exists.

### Cursor deep (this editor)

Observe JSONL + optional ACP. ACP is **not** attached on this companion unless an explicit attach succeeded. Without ACP and without a waiting stop hook, interventions cannot reach the same conversation. Observe STOP still **inspects** the bound cwd: missing `report.txt` is a specific `SEND_NUDGE` recorded as **`send_failed`** (not a fake `followup_message`); a present `report.txt` containing shipped is **NOOP** / `verification.status=supported` (`test_observe_inbox_stop_records_send_failed_instead_of_fake_followup`, `test_observe_inbox_stop_is_noop_when_required_file_is_present`). Huge `afterFileEdit` payloads previously could keep `conversation_id`/`file_path` and **drop `workspace_roots`**; the helper now regex-extracts the first `workspace_roots` string (and `workspace` as cwd).

### CORE phase map (do not skip to four-arm)

| Phase | Status | Evidence class |
| --- | --- | --- |
| 1 Real supervisor | Partial | Local Strands inspect tools, two-Agent STOP contract, Ask PEX review path. Provider-live STOP on a real Codex thread **unproven** in this snapshot. |
| 2 Deep Codex | Local contract yes; live no | Fake App Server closed loop. ChatGPT.exe observe only. |
| 3 Deep Cursor | Observe yes; control/ACP follow-up no | This editor cannot claim stop `followup_message`. |
| 4 Behaviors | Synthetic + fake Codex | Recovery Tests 1–5 locally for isolated STOP; local synthetic Test 5 is **0 false nudges / 10 genuine completions**. Live Test 5 remains unmeasured. |
| 5 Pet UI | Companion exists; exact-eight frame/runtime QA and **72/72 direct playback pass** | Packaged Tauri visual QA **missing**. Evidence/source boundary remains untracked; Von spritesheet still must be git-tracked for clean clones. |
| 6 JIT | Local Store/executor/recovery/REST/Desktop contract complete; live vendor no | Must not be extra prompt text. Cursor hooks cannot `modify_config`. |
| 7 More harnesses | Honest labels | Pi/Prime/ZCode/DeepSeek unavailable; OAuth unimplemented and declared so. |
| 8 Four-arm | **Blocked** | Keep `frozen: false`. No freeze. No headline lift. |

### Recovery §25 / §30 (live boxes still empty)

Do not check these off from unit tests. Still missing: real Codex attach + event stream + goal on that thread + `used_llm=true` inspect + same-`threadId` follow-up + observed outcome + complete audit; live Tests 1–5; live Test 5 false-positive measurement (local synthetic is 0/10 only); Cursor same-session treatment; AgentCore deploy; live Telegram/Discord; 15-step CORE §20 demo on real Codex+Cursor; context view is a list not a graph.

### What the next agent should do (deadline-aware; push the product, never Submit)

1. Preserve the **1567/20** current-tree gate. Use focused subagents for independent audit/proof/release slices, but keep architecture, diff review, integration, and final whole-tree verification in the parent. Do not stop at a progress summary while safe offline spec work remains.
2. **Highest-value next proof is the real Codex loop**, but only after fresh operator authorization for `PEX_LIVE_CODEX=1`: isolated `codex app-server --listen stdio://`, attach a real goal to the **thread** rather than `codex:desktop`, prove Test 1 NOOP and Test 2 a specific evidenced continuation on the same `threadId`, require `used_llm=true`, observe the worker outcome, and retain a complete audit. Never substitute the fake App Server or historical receipt.
3. The exact-eight evidence is now transitively sealed and the source preflight is implemented. Next, review its **888 untracked release inputs** and the wider dirty tree, then obtain explicit operator authorization before staging/committing or rebuilding sidecars. Only after a clean source preflight may an authorized package stage build a fresh MSI/NSIS and reopen it for byte-for-byte embedded sidecar/pet verification. Do **not** build an installer/package, stage, commit, publish, or replace the live companion without action-time permission.
4. Build the judge-facing evidence package around the spec and judging order: truthful architecture, concise ≤5 minute live-loop story, visible persistent goal/attention/Undo value, and clearly separated local versus live evidence. No scored public leaderboard was found and no validated rank is retained, so use spec coverage, differentiation, demo credibility, and current gates as the bar.
5. **Cursor** stays observe on this editor. Do not install control hooks or spawn a second Cursor. If the operator authorizes ACP attach, it must refuse `cursor:desktop`; same-session stop follow-up remains unclaimed without a truthful control path.
6. Restart/replace the already-bound companion on `127.0.0.1:7420` only with explicit operator coordination. Never start a second bridge. The running process is behind this checkout.
7. Four-arm stays blocked until the live recovery loop, natural-task half, same-session Cursor treatment, coherent immutable run file, and freeze checks are real. Devpost, Builder posts, AWS spend/deploy, stage/commit, publish, and Submit remain action-time user gates.

### Judge-safe evidence and ≤5-minute cut (not yet submission-ready)

The submission video must show real live integrations with **both Cursor and Codex** (`PEX_BUILD_SPEC.md` §46). The sequence below is the strongest current cut, but its local-contract Codex segment must be replaced by fresh real evidence and a truthful live Cursor segment before it can satisfy that rule. Never present replay, fake App Server, synthetic provider, or UI state as live control.

| Claim safe today | Evidence | Boundary to say aloud |
| --- | --- | --- |
| Substantial typed supervisory control plane with persistent goals, local policy, durable authority, audit, recovery, and UI integration | Fresh **1567 passed / 20 skipped**, Ruff clean, desktop **51/51**, Rust **8/8** | Current-tree local contract, not live-provider or packaged proof |
| Stale authority cannot look current; quarantined and project A→B rows remain forensic only | Pet/Deck current-authority projection plus full-gate regressions | Local technical-implementation evidence |
| Supported completion becomes NOOP; an exact evidence gap becomes a specific continuation | Fake App Server and synthetic same-thread contracts | Do not call this a fresh real Codex loop |
| Reversible overlays fail closed and expose truthful operator-bound Undo | Overlay **70/70**, REST **32/32**, desktop **51/51** | Mock-adapter/local proof, not vendor acknowledgement |
| Exactly eight source pets pass runtime/frame contracts | `pex, ledger, mesh, nudge, drift, quiet, ember, von`; 456 decoded frames and 72 preview GIFs | Direct playback receipt, packaged Tauri QA, clean bundle, and installer are separate gates |
| Local synthetic Test 5 measured **0 false nudges / 10 genuine completions** | Current phase-map fixture | Always label it local synthetic; live Test 5 is unmeasured |
| No impact lift or rank is established | Four-arm `can_freeze:false`, manifest `frozen:false` | No percentage lift, leaked 1/5-vs-4/5, leaderboard, or rank claim |

Honest shot order:

1. **0:00–0:25 — problem and wedge:** coding agents created a management job; PEX is the independent supervisor above already-running agents, not another orchestrator.
2. **0:25–0:55 — persistent intent:** show objective, acceptance, constraints, attached session, and the quiet Pet attention count.
3. **0:55–1:50 — completion distinction:** until the authorized live run exists, label this “local deterministic/App Server contract.” Show supported completion → NOOP, then missing `report.txt` → specific continuation → verified outcome, with audit ids. Replace with the fresh real Codex two-case capture when available.
4. **1:50–2:30 — human attention and safety:** show one evidence-backed consequential decision and truthful overlay Undo state; do not imply automatic success from dispatch.
5. **2:30–3:10 — context without copy/paste:** show the provenance-bound minimal context bundle and Ask PEX answering “what needs me?” from canonical state.
6. **3:10–3:45 — fail-closed authority:** show an A→B-rebound row retained for forensics but excluded from current Pet/Deck counts and actions.
7. **3:45–4:15 — architecture:** harnesses → local bridge → Strands supervisor/verifier → local policy → typed action → audit/UI. Label AgentCore as a deployment target, not deployed.
8. **4:15–4:40 — evidence scorecard:** 1567/20 Python, 51 desktop, 8 Rust, exact-eight source QA, local synthetic Test 5 0/10, and visible `frozen:false`.
9. **4:40–4:55 — close:** “You keep the goals and consequential decisions. PEX handles the repetitive supervision.”

The single highest-leverage authorization to seek is the fresh current-source two-case real Codex proof with `PEX_LIVE_CODEX=1` and `PEX_LIVE_SUPERVISOR=1`: real persistent binding, `used_llm=true`, supported NOOP, same-`threadId` specific continuation, observed worker outcome, and complete audit. Prepared cases are in `tests/contract/test_live_codex_pump.py`; no live run is authorized by this handoff.

### Files touched this session (dirty tree; not committed)

- `services/bridge/src/pex_bridge/adapters/desktop.py` — `is_desktop_observe_session`; desktop upsert `goal_id=None`.
- `pipeline.py` — refresh clears desktop goals; auto-handoff skips desktop; `deliver_context_handoff` rejects desktop.
- `app.py` — attach/handoff 409 boundaries; operator-bound, idempotent, path-free cleanup Undo.
- `adapters/cursor.py`, `opencode.py`, `claude_code.py`, `acp_harness.py` — send refuse desktop.
- `apps/desktop/src/viewModel.ts`, `Inspector.tsx`, `App.tsx` — `canAttachPersistentGoal`; cleanup Undo retry identity and canonical-state refresh.
- `integrations/cursor-hook/pex_cursor_observe.py` — `workspace` / `workspace_roots` regex extract.
- Cleanup/restore: `store.py`, `executor.py`, `tests/unit/test_lifecycle_restore_operations.py`, `tests/unit/test_cleanup_restore_executor_ledger.py`, `tests/unit/test_cleanup_executor_ledger.py`, and focused lifecycle resource/action tests.
- Overlay/current full-gate production: `services/bridge/src/pex_bridge/store.py`, `executor.py`, `pipeline.py`, `app.py`, `apps/desktop/src/App.tsx`, `viewModel.ts`, and `viewModel.test.ts`.
- Post-gate truth fixes: `pipeline.py` (`current_projection` + Pet), `app.py` (Deck current authority), `fingerprints.py` (two-distinct-session recommendation threshold), `tests/unit/test_pet_snapshot.py`, `test_store_fingerprints.py`, and `tests/e2e/test_m0_roundtrip.py` (quarantine + A→B + one-vs-two regressions).
- Overlay proof: `tests/unit/test_overlay_store_authority.py`, `test_overlay_executor_ledger.py`, `test_overlay_lifecycle.py`, `test_overlay_runtime.py`, `test_overlay_pipeline_recovery.py`, `test_resolution_dispatch_identity.py`; `tests/e2e/test_overlay_revert_operator_auth.py` and `test_lifecycle_decision_resolution.py`.
- Full-gate fixture/proof repairs: `tests/e2e/test_handoff_and_permissions.py`, `test_speculative_execution.py`, `test_m0_roundtrip.py`, `test_mcp_verify_claim_atomic.py`; `tests/unit/test_adapter_capabilities.py`, `test_agentcore_pipeline.py`, `test_codex_live_proof.py`, `test_intervention_authority_consumers.py`, `test_pet_snapshot.py`, `test_pipeline_serialization.py`, `test_pipeline_session_merge.py`, `test_store_audit_outbox.py`, `test_store_canonical_queries.py`, `test_store_fingerprints.py`, `test_store_mcp_decision.py`; shared `tests/contract/codex_live_proof.py`.

## 29 Aug 2026 — observe-only desktop tiles cannot hold a goal or send; still NO-GO

**Do not submit, deploy, publish, spend, stage, or commit.** Overall status remains **NO-GO**.

Current verified local suite: **`uv run pytest -q` → 893 passed, 19 skipped**. Desktop `npm test`: **35 passed**; `npx tsc --noEmit` clean. Manifest stays **`frozen: false`**.

`POST /v1/sessions/{id}/attach` now 409s every process-inventory row (`*:desktop` / `source=desktop`), not only ChatGPT.exe. Refresh will not keep a leftover `goal_id` on those rows. Cursor/OpenCode/Claude/ACP `send_message` refuses the desktop tile even if ACP or HTTP transport is connected. The inspector disables Attach on those tiles and will not auto-attach a newly created ledger. Live vendor sessions (`cursor:conv-*`, isolated App Server threads) still attach. This is local contract evidence, not a live Codex App Server and not same-session Cursor stop follow-up. Live Codex still needs `PEX_LIVE_CODEX=1`. Restart the companion on 7420 to load Python store/pump changes.

## 29 Aug 2026 — fail-open Cursor observe hooks; 15-day scale path; still NO-GO

**Do not submit, deploy, publish, or freeze.** Overall status remains **NO-GO**. Operator authorized live Cursor monitoring if it cannot stall edits, shells, or subagent rollouts. A second Cursor was not spawned.

Current verified local suite: **`uv run pytest -q` → 890 passed, 19 skipped**. `uv run python benchmarks/four_arm.py readiness` was **`can_freeze`: false** on the prior observe install (`cursor_hook_mode`: **observe**). Desktop tests were not re-run this slice.

### CORE Phase 3 / BUILD §12.1 / recovery §23 — observe without blocking (this slice)

Default Cursor install is **observe**, not control. `~/.cursor/hooks.json` runs `python -S …/pex_cursor_observe.py` with **timeout 3**, **`loop_limit: null`** on stop/subagentStop, and **no `failClosed`**. It does not install `beforeShellExecution`, `preToolUse`, `beforeReadFile`, or `beforeMCPExecution`. The helper compact-drops one JSONL line (conversation_id / file_path / command / `observed_ns`; never `edits` or shell output) under `{PEX_HOME}/hooks/cursor.jsonl`, then fail-opens (`{}` / `continue: true`). Live proof: this conversation `ca942dcb-7937-4823-8f7b-06042d2951e6` wrote `afterFileEdit` for `integrations/cursor-hook/pex_cursor_observe.py`. The inbox pump belongs to the already-running companion (`python -m pex_bridge` on `127.0.0.1:7420`). A second `pex-bridge --no-auth` was not started (port in use). Compact duplicate lines previously collided on `event_id` because `HarnessEvent.ts` is ingest time; `add_event` now treats timestamp-only replays as idempotent, and observe drops include `observed_ns`. Restart that companion to load those store/pump fixes. Observe-ingested `stop` no longer claims `followup_message` delivery: without ACP, `SEND_NUDGE` records `send_failed` instead of a discarded hook response (`test_observe_inbox_stop_records_send_failed_instead_of_fake_followup`). Same-session stop follow-up is **not** claimed on this editor.

### Benchmark (this slice)

Readiness was run after the observe install. Freeze blockers still include missing coherent four-arm file, `cursor_same_session_treatment` unavailable, natural-task source unsatisfied, and observe-only hooks not counting as stop treatment. **No headline lift. No freeze. Do not cite leaked 1/5 vs 4/5.** Isolated App Server threads stay attached when ChatGPT.exe is also running; idle listed threads still drop if the transport is down. `POST /v1/discover/attach` for Codex without `kind=stdio` never spawns App Server; ChatGPT.exe stays observe-only. Isolated App Server remains an explicit attach. On the fake App Server, a missing `report.txt` STOP `turn/start`s the same `threadId` with a specific non-`PEX:` nudge; a passing pytest on that thread is **NOOP**. A persistent goal cannot be attached to the ChatGPT.exe desktop tile (`409`); attach the isolated App Server thread instead. Live Codex still needs `PEX_LIVE_CODEX=1`.

## 29 Aug 2026 — existing-session starters, Claude additionalContext, Bench inventory; still NO-GO

**Do not submit, deploy, publish, spend, stage, commit, or discard the dirty worktree.** Overall status remains **NO-GO**.

Current verified local suite: **`uv run pytest -q` → 874 passed, 19 skipped**; **`uv run ruff check` green on this slice**. Desktop `npm test`: **34 passed**; `npx tsc --noEmit` clean. Historical: 867/19 after existing-session observe; 853/19 after STOP inspect tools docs lag; 847/19 after STOP inspect tools.

### CORE §9 / BUILD §12.1–12.4 / §12.10 existing-session observe (prior slice, still binding)

Starter desktop inventory is exactly five: Cursor, Codex, OpenCode, Hermes, Claude Code. Grok Bot stays a registered adapter and is **not** listed in `DESKTOP_APPS`, discover `not_running`, or companion empty copy. Discover never launches a second copy of a running editor. Default `POST /v1/discover/attach` for Cursor does **not** install hooks (`install_hooks is True` only). `Settings.codex_attach` defaults to **False**. ChatGPT.exe is observe/focus only; isolated `codex app-server --listen stdio://` is a separate attach. OpenCode/Hermes desktop observe does not spawn `opencode serve` or ACP. Claude Code hooks are never auto-merged into `~/.claude/settings.json`. Proven by `tests/unit/test_existing_sessions.py`. This is process-inventory evidence, not a live Codex App Server, live `opencode serve`, or live Claude settings install. Product copy is generic (no “this Cursor” / “this machine”).

### BUILD §12.3 Claude Code UserPromptSubmit / PreCompact (this slice)

Claude `hook_response` now maps completed interventions onto the official `hookSpecificOutput.additionalContext` contract. `UserPromptSubmit` ANNOTATE continues the already-submitted prompt with ledger-grounded context; ASK_HUMAN does **not** reject that prompt. `PreCompact` ANNOTATE (planner emits ANNOTATE on `EventPhase.BEFORE` compaction so the pre-hook is not deferred to NOOP) injects the attached title, acceptance, constraints, and required files. `PEX:` prefixes and non-ALLOW verdicts stay `{}`. Stop still uses `{decision: "block", reason}` only. The generic hook helper forwards `hookSpecificOutput` and strips bridge bookkeeping. The opt-in fragment remains `integrations/claude-hook/settings.fragment.json`; PEX does not write `~/.claude/settings.json`. Proven by `tests/unit/test_fleet_pets_codex.py` Claude additionalContext tests, `test_pre_hook_compaction_annotates_instead_of_nudging`, `tests/e2e/test_m0_roundtrip.py` Claude HTTP hooks, and `test_generic_hook_helper_rejects_fabricated_harnesses_and_filters_output`. This is local hook-contract evidence, not a live Claude Code session.

### BUILD §6 command-deck Bench inventory without freeze (this slice)

The companion Bench view fetches existing `GET /v1/discover` beside `GET /v1/bench/runs`. Starter running / not-running labels are shown even when there are no verified runs. Copy says desktop inventory is diagnostic and **never a freeze blocker**. The live supervisor still loads public bench summaries only; it does **not** import `four_arm` or the hidden evaluator. Grok Bot is excluded from that inventory. Proven by `starterHarnessInventoryCopy` / `starterInventoryFromDiscover` in `apps/desktop/src/viewModel.test.ts`. Packaged Tauri visual QA of Bench is still missing. Manifest stays **`frozen: false`**. Do not cite leaked 1/5 vs 4/5.

## 29 Aug 2026 — Ask PEX inspects artifacts; STOP has web_search/scrape_url tools; still NO-GO

**Do not submit, deploy, publish, spend, stage, commit, or discard the dirty worktree.** Overall status remains **NO-GO**.

Current verified local suite: **`uv run pytest -q` → 853 passed, 19 skipped**; **`uv run ruff check .` green**. Desktop `npm test`: **33 passed**.

### CORE §4 / §4.1 / BUILD §6.4 (this slice)

STOP Strands tools now include CORE §4.1 `web_search` and `scrape_url` beside the workspace/git/file/artifact/process inspect tools. Hidden-evaluator queries and local/private scrape URLs are refused. The supervisor prompt no longer tells the model to skip inspect/search. Ask PEX still must not go through `decide()`. Spec questions stay canonical; “did the eval actually finish?” now inspects attached `results.jsonl` / `results.json` row counts when a session cwd is present, and will not call a 27-row file finished against a 30-row acceptance. Freeform Ask with a real Strands model uses a read-only `ReviewAnswer` agent on the same inspect tools, then falls back to `inspect_http` if that path is unavailable. Proven by `tests/unit/test_evidence_tools.py`, `test_ask.py` artifact inspect, `test_ask_review.py`, and `test_strands_runtime.py` prompt assertions. This is local tool-contract evidence, not a live loaded-model Ask on Codex, and not a live Firecrawl/Exa call.


## 29 Aug 2026 — STOP inspect tools query repo/git/artifacts/process; still NO-GO

**Do not submit, deploy, publish, spend, stage, commit, or discard the dirty worktree.** Overall status remains **NO-GO**.

Current verified local suite: **`uv run pytest -q` → 847 passed, 19 skipped**; **`uv run ruff check .` green**. Desktop `npm test`: **33 passed**; `npx tsc --noEmit` clean. Historical: 846/19 after companion compact/drift status; 845/19 after the first companion-honesty pass; 843/19 after remote channels + Open agent.

### CORE §4 / recovery §2 / BUILD §17 inspect tools (this slice)

The Strands supervisor no longer gets a dumped workspace blob in the user prompt. It has request-scoped tools: `inspect_workspace`, `inspect_git`, `inspect_file`, `inspect_artifact`, `inspect_process`, plus `run_verification`. Local cwd can read a visible relative file, a bounded git status/diff, and artifact tails; hidden evaluators and `..` paths are refused. AgentCore still receives compacted inventory only (`changed_paths`, no tails, no diffs). `get_context` is an index of those query tools, not a second dump. The inspector shows recorded `verification_status` and `evidence_tools` when an intervention has them. Proven by `tests/unit/test_evidence_tools.py`, `test_strands_runtime.py` prompt masking, `test_agentcore_boundary_recompacts_raw_workspace_evidence_before_cloud`, and desktop inspector source tests. This is local tool-contract evidence, not a live Codex STOP with a loaded supervisor model actually calling the tools, and Ask PEX `inspect_http` remains a bounded completion rather than this tool loop.

## 29 Aug 2026 — companion compact is counts, not a catalog; drift is present-tense; still NO-GO

**Do not submit, deploy, publish, spend, stage, commit, or discard the dirty worktree.** Overall status remains **NO-GO**.

Current verified local suite: **`uv run pytest -q` → 847 passed, 19 skipped**; **`uv run ruff check .` green**. Desktop `npm test`: **33 passed**; `npx tsc --noEmit` clean. Historical: 846/19 after companion compact/drift status; 845/19 after the first companion-honesty pass; 843/19 after remote channels + Open agent; 841/19 after remote channels; 832/19 after speculative probes; 717/19 before MCP/hooks.

### BUILD §6.1 / CORE §8 companion (this slice)

Compact is the pet, live counts, an attached goal title if one exists, and Inspect. The eight-mascot roster lives in Settings. Worker tiles and Ask PEX chips are not on compact; they belong on inspector expand and the command deck. Overlay copy uses observed `last_message` or count-backed fallbacks; it does not invent “consequential decision,” token savings, or “drifting → corrected.” A loop/refactor `SEND_NUDGE` no longer stamps a past-tense win. After a drift nudge actually sends, the session is `SessionStatus.DRIFTING` until a USER_PROMPT, a required-file edit, STOP, or ERROR. Compact then reads `Codex drifting` (or `N drifting`) in the present tense. Proven by `test_pet_snapshot_does_not_claim_drift_corrected_from_a_nudge`, `test_pet_snapshot_names_a_drifting_session_in_the_present_tense`, `test_unrelated_refactor_is_redirected` (status + `/v1/pet`), and desktop `viewModel.test.ts`. This is synthetic + local UI evidence, not a packaged Tauri visual QA or a live Cursor/Codex overlay demo.

Ask PEX chips on inspector/deck name live attached harnesses only, and “why did you message X?” appears only after a recorded `SEND_NUDGE`/`APPLY_OVERLAY`. Spec example strings remain in `ASK_PEX_QUESTIONS` as documentation; the live form does not hardcode Devin. Context view marks stale, superseded, and replaces-prior facts from `supersedes`; health copy names counted contradictions. Consumer login is still unimplemented and declared so.

The main-window compact surface still has the Compact/Inspector/Deck switch. The always-on-top overlay (`shell === "pet"`) is the closer §6.1 pet. Packaged visual QA remains missing.

## 29 Aug 2026 — remote inbox + Open agent Devin links; messengers stay disconnected; still NO-GO


**Do not submit, deploy, publish, spend, stage, commit, or discard the dirty worktree.** Overall status remains **NO-GO**.

Current verified local suite: **`uv run pytest -q` → 846 passed, 19 skipped**; **`uv run ruff check .` green**. Desktop `npm test`: **32 passed**. Historical: 845/19 after the first companion-honesty pass; 843/19 after remote channels + Open agent; 841/19 after remote channels; 832/19 after speculative probes; 717/19 before MCP/hooks; 818/19 after context health; 807/19 after rejected-approach handoff; 806/19 after fingerprint overlay use.

### Build spec §6.5 Open agent (this slice)

Open agent now focuses a local window when `focus_ui` is truthful, or opens an allowlisted existing Devin session URL (`https://app.devin.ai/sessions/{id}`) in the browser. It does not POST start, does not invent hosts, and rejects `javascript:`, http, query strings, credentials, and `/sessions/new`. Untrusted API `url` fields are ignored; the official existing-session path is used instead. Proven by `tests/unit/test_deep_links.py`, Devin discover assertions, and desktop `canOpenSession` / `safeExternalUrl`. This is allowlist + mock-API evidence, not a live Devin click or a packaged Tauri opener.

### Build spec §6.6 remote channels (this slice)

Human-decision interventions (`ASK_HUMAN` / `FORK_PROBE` / lifecycle `awaiting_human`) now fan out through `ChannelHub` with the same attention policy as the deck. The only implemented delivery path is a local JSONL inbox at `{PEX_HOME}/channels/inbox.jsonl` (`PEX_NOTIFY_FILE`, default on). Telegram, Discord, WhatsApp, and Slack stay `configured: false` / `connected: false` even if messenger env tokens exist; PEX will not fake a bot. Worker `SEND_NUDGE` text still must not start with `PEX:` and does not write the inbox. Remote copy for humans may start with `PEX:` and uses the harness label, not vendor session ids. Settings lists that honest status via `GET /v1/channels`. Proven by `tests/unit/test_channels.py`, `tests/e2e/test_remote_channels.py`, and desktop `channelStatusCopy`. This is file-inbox evidence, not a live Telegram/Discord delivery.

## 29 Aug 2026 — speculative probes are human-gated; OpenCode can fork; still NO-GO

### Build spec §23 speculative execution (this slice)

Two cheap unresolved questions on STOP no longer stay silent when the harness can `fork`. PEX proposes `FORK_PROBE` with `ASK_HUMAN` (never Autopilot, never this desktop). After an authenticated allow, the parent gets approach A with an 8-tool-call budget and an isolated child gets approach B. OpenCode now advertises `fork=True` when `opencode serve` is connected and implements `POST /session/:id/fork` (mock HTTP only; no live `opencode serve` was called). After both probes STOP, pytest/verification evidence picks a winner: the winner is continued, the loser is `STOP_AGENT` pending human dispose. A failed pytest inside an unfinished pair is probe evidence, not a nag to keep going. Acceptance-gap STOP still outranks proposing a new fork. Proven by `tests/unit/test_speculative.py`, `test_opencode_fork.py`, planner compare/wait tests, `test_fork_probe_sends_approach_a_to_parent_and_b_to_child`, and `tests/e2e/test_speculative_execution.py`. This is synthetic + MemoryHttpTransport evidence, not a live OpenCode/Cursor dual-worker probe.

### Operator 29 Aug afternoon — live Cursor attach authorized only if edits cannot freeze; Submit still blocked

This Cursor's `~/.cursor/hooks.json` is empty (`"hooks": {}`). PEX did **not** install hooks into it. Ordinary editor writes stay on `afterFileEdit` (observe-only). `preToolUse` matches only `Delete|Task`. `beforeReadFile` and `beforeMCPExecution` are no longer `failClosed`, so a slow or dead hook cannot deny a read or MCP call. Ordinary non-secret reads fail-open even without `workspace_roots`; credential-shaped paths and `Delete` stay held; destructive shell still asks. Proven by `tests/contract/test_cursor_hooks.py`. Live this-desktop chain is still unrun because installing global hooks onto this working agent would still add Python round-trips on every shell. Do not Submit. Do not freeze. Do not spawn a second Cursor.

### Build spec §15.5 / §21.2 context health and attention metrics (this slice)

`HarnessSession.context_health` is no longer a stub 1.0. Ingest scores observed compactions, repeated forgotten facts (durable files re-read twice after compaction with no edit), contradictions, stale decisions, repeated reads, and token utilization **only when the harness exposed a window**. Unmeasured fields (`summary_depth`, token utilization when absent, human active seconds) stay null. A first compaction still checkpoints the ledger; forgotten facts are named in that nudge. After two compactions with forgotten facts and health below 0.6, overlay-capable harnesses pin a reversible context-health overlay whose instructions are those facts (not a canned `PEX:` nag) and drop unrelated research tools. Cursor without `modify_config` still gets the checkpoint nudge. The Context view renders the measured score; Now shows counted attention metrics without inventing “saved tokens.” Proven by `tests/unit/test_context_health.py`, `test_repeated_forgotten_context_applies_health_overlay_on_compaction`, `test_ingest_persists_measured_context_health`, `test_repeated_forgotten_facts_after_compaction_apply_context_overlay`, and desktop `contextHealthCopy` / `attentionMetrics`. This is synthetic COMPACTION evidence, not a live Cursor `preCompact`.

### CORE §6 / build spec §15.3 context mesh (this slice)

Handoff `next_objective` is an unresolved question or remaining acceptance criterion, not canned “Continue the attached goal.” Rejected-approach Decision rows enter the mesh and land in `do_not_redo`. Artifact `metadata.files` become `deep_links`. Labeled ledger rows also persist as HUMAN context items so they can transfer. Proven by `test_rejected_approach_and_unresolved_question_shape_the_handoff_bundle` and `test_goal_create_persists_labeled_decision_ledger`. Live Cursor/Codex handoff remains unproven.

### Build spec §20.2 fingerprint overlay use (earlier this day)

Counted STOP fingerprints now influence overlay generation without overfitting one session and without replacing a first-sample STOP nudge. After two verifier-backed gap/contradiction STOPs on a harness that can `modify_config`, an acceptance-gap STOP applies a reversible `evidence-before-done` overlay whose instructions are the specific missing-evidence correction (not a canned `PEX:` nag). Cursor-style harnesses without `modify_config` still get the nudge. Repeated-failure debug overlays also pin evidence-before-done, and the drift overlay threshold eases only after those two samples. Proven by `test_repeated_premature_fingerprint_applies_evidence_overlay_on_stop` and `test_fingerprint_lowers_drift_overlay_threshold_without_one_session_overfit`. Recovery Tests 1–5 stay synthetic first-sample nudges.

### Build spec §9.2 / §14.2 Decision ledger (earlier this day)

Labeled `Decisions:`, `Rejected approaches:`, and `Unresolved questions:` on create/patch persist as `Decision` rows (`GET /v1/goals/{id}/decisions`). Prompt linting treats an active rejected approach like a ledger contradiction. The inspector shows those three lists and the goal editor can write them directly. Proven by `test_parse_public_task_lifts_decisions_rejected_and_unresolved`, `test_rejected_ledger_decision_is_a_prompt_contradiction`, `test_goal_create_persists_labeled_decision_ledger`, and desktop `partitionLedgerDecisions`. This is durable-store evidence, not a live Cursor submit of a rejected-approach prompt.

### Build spec §9.7 / command-deck Agents (earlier this day)

`GET /v1/deck` fingerprints no longer invent personality. Strengths, failure modes, `verified_success_rate`, and `evidence-before-done` come only from persisted STOP verification counts (`supported` vs `contradicted`/`acceptance_gap`) plus overlay rows. Unmeasured spec fields (`token_efficiency`, `repeated_tool_rate`, `context_degradation_profile`, `approval_behavior`, `model_settings_hash`) stay null. The Agents view renders those counts instead of placeholder lies. Proven by `tests/unit/test_store_fingerprints.py`, `test_command_deck_fingerprints_use_stop_verification_counts`, and desktop `fingerprint*` view-model tests. This is durable-store evidence, not a live multi-harness personality study. Overlay generation **is** driven by those fingerprints after two gap/contradiction STOPs (build spec §20.2).

### CORE §18.12 / build spec Process Monitor (earlier this day)

Abandoned-background detection no longer trusts a fake pid. On STOP, PEX looks up the observed pid in the OS process table. A still-running job is named in the nudge as running in the process table; a pid that has already exited is not treated as abandoned, even if the last event still said `running: true`. Planner will not reopen a job the pipeline already cleared. Proven by `tests/unit/test_background.py`, `test_process_table_cleared_job_is_not_reopened_from_events`, `test_abandoned_background_train_is_woken_on_stop` (live child process), and `test_exited_background_job_is_not_treated_as_abandoned`. That is this-machine process-table evidence, not a live Codex/Cursor worker.

### CORE §18.14 / build spec §33.4.8 cloud supervisor unavailable (earlier this day)

AgentCore-only mode still does not call the local semantic model. When the remote supervisor is down or returns NOOP, local deterministic truth is preserved: an acceptance-gap STOP still sends the evidenced correction (`used_llm: false`). Pipeline timeout/crash uses `plan_deterministic` instead of dropping that correction. Dangerous permissions stay locally gated. Proven by `test_agentcore_unavailable_keeps_local_acceptance_gap`, `test_agentcore_remote_noop_cannot_erase_local_acceptance_gap`, and `test_cloud_supervisor_unavailable_still_corrects_missing_rows`. Live AgentCore drop is still missing.

### CORE §18.15 malformed adapter event (earlier this day)

A malformed Cursor hook still returns 422 and leaves `/health` ok. A sibling synthetic session on the same bridge still inspects STOP against its attached ledger. Proven by `test_malformed_adapter_event_does_not_stop_sibling_supervision`.

### CORE §18.4 repeated identical error loop (earlier this day)

Scoring now lets a tight identical-error + repeated-command loop reach redirect drift (`>= 0.75`). Four identical failing `python train.py` commands apply a reversible debug overlay (or a specific nudge); overlay undo is truthful. Proven by `test_repeated_identical_command_errors_reach_redirect_drift` and `test_repeated_identical_error_loop_is_redirected`.

### Build spec §14.3 accidental-ambiguity rewrite (earlier this day)

`beforeSubmitPrompt` no longer only ASK/block. Accidental ambiguity (`just quickly` / `whatever` / `hack`) continues the prompt and prepends a ledger-grounded `user_message` via `ANNOTATE` (allowed on BEFORE). The Cursor hook now forwards `user_message` when `continue` is true. Contradictions still ASK; explicit overrides still record Decision rows. Proven by `test_ambiguous_user_prompt_is_rewritten_against_the_ledger` and `test_before_submit_prompt_rewrites_accidental_ambiguity`. Live Cursor submit proof is still missing.

### CORE §18.13 / build spec §49 duplicate work across agents (earlier this day)

When two attached sessions share a goal and project, a later FILE_EDIT/SHELL/TOOL_CALL that overlaps a sibling's observed path or identical non-test command is a specific `SEND_NUDGE`: it names the sibling harness and overlapping path/command and tells the worker to use that observed result instead of repeating. Pytest/npm/cargo/go test are not treated as duplicate commands. Vendor session ids stay out of worker-facing text. Detached/paused siblings are ignored; a stopped sibling still counts as work already done. Proven by `tests/unit/test_drift.py`, `test_duplicate_sibling_work_is_redirected_without_leaking_vendor_ids`, and `test_duplicate_work_across_agents_is_redirected`. Live two-harness proof is still missing.

### CORE §18.6–18.7 / build spec §49 refactor drift and compacted context (earlier this day)

Broad FILE_EDIT of four or more files that are not named by the attached ledger is redirected; editing a required artifact is not treated as drift. `preCompact` / COMPACTION checkpoints the persistent title, acceptance, constraints, and required files into a specific non-`PEX:` nudge so compacted worker context does not drop the ledger. Proven by `test_unrelated_refactor_is_redirected` and `test_compaction_checkpoints_durable_ledger`. Live Cursor `preCompact` proof is still missing.

### CORE §18.12 / build spec §49 abandoned background process (earlier this day)

If a worker launches an observed background job (`nohup`, trailing `&`, `process_state.background/running`) and then STOPs without an observed finish, PEX checks the OS process table when a pid is present. A live pid is woken with command, pid, and process-table evidence; an exited pid is not. Pytest is not treated as a background job. Proven by `test_abandoned_background_train_is_woken_on_stop` and `test_exited_background_job_is_not_treated_as_abandoned`. Live Codex/Cursor proof is still missing. Manifest still **`not_yet_satisfied`**.

### Spec §14.4 / §49 premature cleanup (earlier this day)

Deleting a ledger-required artifact (`rm dataset.parquet` when the goal requires it) is `ASK_HUMAN` before the command and a restore nudge if it already started. Agent output that matches an active constraint contradiction is redirected. Proven by `test_premature_cleanup_of_required_artifact_asks` and `test_agent_output_contradicting_ledger_is_redirected`. Live Codex/Cursor proof is still missing.

### Build spec §6.4 / CORE §8 Ask PEX from canonical state (earlier this day)

`POST /v1/ask` now loads stored context and recent interventions and answers the spec examples from canonical state without messaging workers: what Codex is doing, which agent is blocked, why PEX messaged Cursor, what Devin observed that Codex lacks, which approach looks better (fail closed), whether eval finished, and what needs the user. Secret/local-only items stay out of knowledge-gap answers. Cloud review still must not see vendor session ids, goal titles, or tokens (`test_ask_minimizes_and_redacts_cloud_review_context`). Spec-shaped answers are no longer overridden by a loaded supervisor model. Proven by `tests/unit/test_ask.py` and `tests/e2e/test_ask_canonical.py`. Manifest still **`not_yet_satisfied`**. Live Codex/Cursor proof is still missing.

### CORE §2 wrong dependency order (earlier this day)

The planner previously returned NOOP for `python eval_runner.py --full` even when the goal required `dataset.parquet exists`, because it refused to invent workspace evidence (and the old “dataset-before-eval” nudge was gone). During SHELL work PEX now snapshots the cwd when the goal names required files, and a downstream consumer command (`eval` / `train` / `deploy` / `bench`) with an observed missing artifact gets a specific `SEND_NUDGE`. A generator command (`generate_dataset.py`) stays silent. “`dataset.parquet exists`” is now a real required-file parse, so STOP also treats that phrasing as an acceptance gap. Proven by synthetic e2e `test_eval_before_missing_dataset_is_redirected`. Manifest still **`not_yet_satisfied`**. Live Codex/Cursor proof is still missing.

### CORE §2 user-mistake / build spec §14.3 (earlier this day)

Explicit override prompts persist as `Decision` rows; constraint contradictions still block `beforeSubmitPrompt` and name the constraint. Accidental ambiguity now continues with a ledger-grounded rewrite. Preferences extract from labeled lists. Live Cursor submit proof of that rewrite is still missing.

### Spec §14.2 ledger edit (earlier this day)

The inspector can **Edit this ledger** and `PATCH /v1/goals/{id}`. Explicit empty lists in a PATCH stay empty. Create still extracts labeled lists when those fields are empty. Packaged visual smoke of the edit path is still missing.

### Persistent intent extract on create (earlier this day)

Create/patch fill empty Goal lists from labeled objective sections; explicit lists are not overwritten. STOP inspect uses the stored Goal, not a second extract. The companion objective field is a textarea (`GoalEditor.tsx`). Proven by `POST /v1/goals` → stored `acceptance_criteria` and recovery STOP `SEND_NUDGE` naming `report.txt`. Isolated TASK.md parse still applies to the bench child.

### Spec §6.1 overlay click-through (earlier this day)

`PetSettings.click_through` already persisted on the bridge but Settings never exposed it and the overlay never called Tauri `setIgnoreCursorEvents`. Settings now has an explicit checkbox (saved with appearance). The pet window applies ignore-cursor only when `click_through === true`. Proven by `GET/PATCH /v1/pets/settings` in `tests/e2e/test_m0_roundtrip.py` and desktop `petClickThroughEnabled`. Packaged visual smoke of the ignore-cursor path is still missing.

### Spec §6.2 overlay expand (earlier this day)

The always-on-top pet always emitted `inspector`, so a second click never opened the command deck. Overlay activate now expands: compact/other → inspector, inspector/deck → deck (`nextPetExpansion` in `apps/desktop/src/releasePet.ts`; main window handles `pex-open-surface` payload `expand`). Proven by `apps/desktop` `node --test` (`18` pass, including the new expansion test). Packaged visual smoke is still missing.

### Exact-eight on disk vs git HEAD

`tests/unit/test_fleet_pets_codex.py::test_starter_spritesheets_are_not_gitignored_and_match_release_manifest` now proves: none of the eight spritesheets are gitignored, each `pet.json` is `spriteVersionNumber` 2, and bytes match `apps/desktop/src/pets/release-manifest.json`. That is dirty-worktree proof. **`git ls-files` still does not contain `apps/desktop/src/pets/von/spritesheet.webp`**, so a clean clone of current HEAD would miss Von’s atlas. Do not `git add`/`commit` until the operator authorizes a reviewed boundary. `build-sidecar.mjs` and `release-manifest.json` remain untracked.

### Earlier night (still true)

Cursor same-session continuation capture and isolated stop-hook wiring are local-only. Live this-desktop chain and four-arm freeze are not proven. MCP §25 eight tools are locally proven. Recovery Tests 1–5 are synthetic.

### Next causal work

1. Do **not** Submit. Do not freeze. Do not AgentCore-deploy. Do not install PEX hooks onto this working Cursor until the operator asks for a dedicated isolated chain. Do not call live `opencode serve` fork unless the operator asks.
2. Operator-authorized commit of Von’s spritesheet (and sidecar freeze inputs) so clean-clone packages the eight.
3. Honest four-arm freeze (manifest still unfrozen) only after a live isolated chain with `used_llm` audits.
4. Packaged GUI/visual proof.
5. AgentCore deploy only with explicit AWS login authorization.
6. Live duplicate-work across two real harnesses, live `preCompact`, live OpenCode fork, and live AgentCore drop are still unproven.

## 28 Aug 2026 night — Cursor same-session capture plus isolated stop path; still NO-GO

**Do not submit, deploy, publish, spend, stage, commit, or discard the dirty worktree.** Overall status remains **NO-GO**.

Historical baseline before the MCP/hook slice: **717 passed, 19 skipped**. After MCP + local recovery STOP E2E: **723 passed, 19 skipped**. After continuation capture: **726 passed, 19 skipped**. Current verified local suite after isolated Cursor-stop wiring: **`uv run pytest -q` → 730 passed, 19 skipped**; **`uv run ruff check .` green**.

### Cursor+PEX same-session continuation (local controller)

A this-desktop stop payload is not a treatment. The hook now writes `{stop_id}.json` for the inbound stop and a second `kind: "followup_delivery"` drop for the follow-up it actually returned. Delivery ids are `{initial}_followup_{ns}` and retry once on Windows `FileExistsError`. `benchmarks/four_arm.py` `wait_for_cursor_treatment_chain` requires inbound stop + non-empty non-`PEX:` delivery + a later inbound stop on the same conversation. `run_live_this_cursor` still refuses `cursor_pex` replay payloads and waits without `wait_cursor_stop`.

This is necessary and not sufficient for a presentation row. Manifest `cursor_same_session_treatment_status` stays **`not_yet_satisfied`**. Do not freeze. Do not cite leaked 1/5 vs 4/5.

### Isolated Cursor supervisor at hook time (local wiring)

`supervise_isolated_codex` cannot prove Cursor continuation: `CursorAdapter.wait_for_turn_completion` returns `delivery_accepted_completion_unobserved`. Isolated PEX for this desktop therefore runs inside the stop hook:

- `prepare_isolated_workspace` writes an out-of-band control pointer (`benchmarks/results/_scratch/_control/{workspace}.json`, overridable with `PEX_CURSOR_ISOLATED_CONTROL`).
- Baseline `cursor` stops in a prepared workspace return no follow-up and do **not** POST to the user bridge.
- `cursor_pex` stops subprocess `benchmarks/cursor_isolated_stop.py` → `pex_attach.decide_isolated_cursor_stop` → the same out-of-process `pex_supervisor_process.py` child Codex uses. Audits land in `_private_control`. Follow-up returns on hook stdout.
- `run_live_this_cursor` attaches `pex_meta` only from that isolated receipt. Mocked chain tests remain `live: false` / `not_a_presentation_arm: true`.

Not proven: a live this-Cursor two-stop chain against a prepared workspace, with `used_llm`, audits, and `followups >= 1` from that isolated child. The user's running bridge on `:7420` is not that evidence.

### Earlier this day (still true)

MCP §25 eight named tools are locally proven via `tests/e2e/test_mcp_server.py`. Recovery Tests 1–5 are local synthetic only. Live Codex/Cursor recovery §13/§30 remains **BLOCKED BY EXTERNAL AUTHORITY**. Cursor hook fail-open for routine work is restored; restart Cursor if an old hook copy is still what `~/.cursor/hooks.json` invokes.

### Next causal work

1. Live this-desktop Cursor+PEX chain when the operator authorizes working in a prepared isolated workspace — do not spawn a second Cursor.
2. Live Codex recovery when authorized.
3. Honest four-arm freeze (manifest still unfrozen).
4. Packaged GUI/visual proof, exact-eight pet integrity, clean-clone packaging.
5. AgentCore deploy only with explicit AWS login authorization.

Keep `STATUS.md` / `BENCHMARKS.md` / `KNOWN_FAILURES.md` aligned. Do not treat this wiring as a citeable impact result.

## 28 Aug 2026 evening — MCP §25 verified locally; recovery Tests 1–5 still not live

**Do not submit, deploy, publish, spend, stage, commit, or discard the dirty worktree.** Overall status remains **NO-GO**.

Historical baseline before this slice: **717 passed, 19 skipped** with `uv run ruff check .` green. That count does not describe the code below.

Current verified local suite after this slice: **`uv run pytest -q` → 723 passed, 19 skipped**; **`uv run ruff check .` green**. `create_app()` imports. Superseded as the latest count by the night section above.

### Cursor hook fail-open (this session)

Local `integrations/cursor-hook/pex_cursor_hook.py` had been fail-closed on every non-routine pre-hook, which froze this agent with `PEX is unavailable, so this non-routine action was held.` Spec and threat model require fail-open for routine work when the bridge is down; only destructive/sensitive actions stay held. Restored:

- `_is_routine_safe` for in-workspace reads and non-destructive single commands
- routine fail-open **allow**; deny-only non-routine **deny**; other non-routine **ask**
- `_safe_hook_stdout` converts bridge `ask` → `allow` on routine payloads (Cursor deny-only hooks cannot ask)
- permission hooks fast-path allow routine work, then best-effort notify

Proven by `tests/contract/test_cursor_hooks.py`. Live editor still needs a Cursor restart to pick up the script if the old copy is what `~/.cursor/hooks.json` invokes.

### Build spec §25 MCP — now locally proven, including mutations

Transport: FastMCP 1.29 Streamable HTTP at `/mcp/` behind `MCPTokenMiddleware` (bearer, constant-time, no query-string token). DNS-rebinding protection allows loopback Host with or without a port, plus trusted UI origins.

Official client E2E: `tests/e2e/test_mcp_server.py` uses `ClientSession` + `streamable_http_client` against ASGI `http://127.0.0.1/mcp/`, entering `app.state.pex_mcp.session_manager.run()` in the test task (pytest fixtures cannot own that anyio cancel scope).

Named tools now implemented and listed:

| Tool | Path | Local proof |
| --- | --- | --- |
| `pex.get_goal` | store session+goal | exact-session bind; missing/unattached fail |
| `pex.get_relevant_context` | `build_bundle` | target-relevant min bundle; SECRET/LOCAL_ONLY excluded |
| `pex.find_agent_with_context` | bundle + `source_session_id` | sibling attribution; secrets excluded |
| `pex.get_project_state` | store lists | SECRET/LOCAL_ONLY excluded from counts |
| `pex.report_progress` | `Pipeline.record_reported_progress` | RESULT persisted; `verified` never set from self-assertion; empty `evidence_refs` fails |
| `pex.request_decision` | `Pipeline.request_human_decision` | ASK_HUMAN + `awaiting_human`; session `needs_decision`; not auto-resolved |
| `pex.handoff` | `Pipeline.request_context_handoff` → `deliver_context_handoff` | sibling inject + receipt; self-target fails |
| `pex.verify_claim` | `extract_claims` + `verify_claims` | maps supported→verified, contradicted, else uncertain; uncertain is not completion |

Auth: 401 without bearer; query `?token=` rejected; initialize/list-tools succeeds with bearer.

Not proven: a live worker actually calling `/mcp/`; HTTP/WebSocket companion surfaces were already present and are not a substitute for live MCP clients.

### Recovery Tests 1–5

Local synthetic pipeline E2E (deterministic supervisor, `PEX_SUPERVISOR_DISABLE=1`):

- Test 1 genuine pytest completion → NOOP, empty inbox: `tests/e2e/test_recovery_stop_loop.py`
- Test 2 premature missing `report.txt` → specific nudge → FILE_EDIT observed → later STOP NOOP: same file
- Test 3 false test claim → cite failing node → later passing pytest NOOP: already `tests/e2e/test_handoff_and_permissions.py`
- Test 4 uncertain → evidence receipt then silence: same file
- Test 5 ten genuine completions → 0 false-positive nudges: `tests/e2e/test_recovery_stop_loop.py`

Live Codex/Cursor recovery §13/§30 remains **BLOCKED BY EXTERNAL AUTHORITY** (no extra Cursor instance, no live Codex spend unless the operator authorizes). Isolated Codex App Server and live Cursor stop tests still skip without `PEX_LIVE_CODEX` / `PEX_LIVE_SUPERVISOR`.

### Next causal work

1. Live Codex/Cursor recovery when authorized — do not spawn a second Cursor.
2. Honest four-arm benchmark freeze (manifest still unfrozen; do not cite leaked 1/5 vs 4/5).
3. Packaged GUI/visual proof, exact-eight pet integrity, clean-clone packaging.
4. AgentCore deploy only with explicit AWS login authorization.

Keep `STATUS.md` / `BENCHMARKS.md` / `KNOWN_FAILURES.md` aligned with the facts above. Do not treat this MCP/local-STOP slice as the product.

The next product gap after MCP is still the live recovery loop and citeable impact evidence.

## 28 Aug 2026 quota handoff — historical (MCP was then unverified)

The operator's Codex quota was exhausted mid-MCP. The last fully verified baseline **before** the MCP/hook work in this file was **717 passed, 19 skipped**. The MCP implementation at that snapshot was read-only only, untested through `/mcp/`, and must not be cited as the current tree.

---

# PEX agent handoff — 27 Aug 2026

**Read this entire file before writing code.** Then read the three binding specs. Then audit the tree against those specs. Do not trust previous agents, `STATUS.md`, commit messages, or a green pytest as proof the product exists.

The previous agent repeatedly ended turns by telling the operator to `aws login`, screen-record Cursor, and Submit. That was wrong. The product is not complete. The UI is not the spec UI. The three specs are not cleared. There is no honest citeable four-arm impact result. **Do not Submit. Do not treat Devpost artifacts as the remaining work.**

The operator is moving to a new agent because the last one did half-finished slices and called remaining work “blocked on you.” Operator quote, paraphrased: agent complete — no; app UI/UX perfect — no; submittable — no; cleared the three spec files — no; benchmarked — no.

## 28 Aug 2026 quota handoff — active MCP work is not yet verified

**Superseded by the 28 Aug evening section at the top of this file.** Keep the snapshot below as the mid-MCP transfer record. Do not treat the “untested MCP” claims here as current tree state.

The operator's current Codex quota is exhausted and they are moving this work to another agent. The persistent objective remains active. **Do not submit, deploy, publish, spend, stage, commit, or discard the dirty worktree.** The last fully verified baseline before the work below is still **717 passed, 19 skipped** with `uv run ruff check .` green.

The current audit target is build spec §25: the required inter-agent HTTP/WebSocket/MCP surface and these named operations:

- `pex.get_goal`
- `pex.get_relevant_context`
- `pex.report_progress`
- `pex.request_decision`
- `pex.find_agent_with_context`
- `pex.handoff`
- `pex.verify_claim`
- `pex.get_project_state`

Audit result: the bridge already had a substantial companion HTTP API and authenticated `/v1/events` WebSocket, but no MCP server and no agent-facing implementation of those named operations. An MCP implementation was started immediately before this quota handoff:

- New untracked file `services/bridge/src/pex_bridge/mcp_server.py` builds an app-scoped FastMCP 1.29.1 server with stateless Streamable HTTP at the child path `/`. It currently implements only four **read-only** tools: `pex.get_goal`, `pex.get_relevant_context`, `pex.find_agent_with_context`, and `pex.get_project_state`.
- `services/bridge/pyproject.toml` now directly declares `mcp>=1.29.1`; `uv.lock` contains the bridge MCP dependency. MCP was already present transitively through Strands, but direct ownership is intentional.
- `services/bridge/src/pex_bridge/app.py` now constructs a fresh MCP server per `create_app()`, mounts it at `/mcp` behind `MCPTokenMiddleware`, exposes `Mcp-Session-Id` through CORS, and enters the child session manager from the parent FastAPI lifespan. The public transport URL is expected to be **`/mcp/`** because the child path is `/`.
- The middleware uses the existing bridge bearer token, constant-time comparison, and never accepts a query-string token. When auth is disabled it passes through, matching the existing local test mode.
- The four tools are bound to an exact existing session with an attached persistent goal. Context comes from the canonical store and existing minimum-bundle builder. Project state excludes `SECRET` and `LOCAL_ONLY` context. Returned worker/context text must remain untrusted evidence, never executable instructions.

**Verification boundary:** only `uv run ruff check services/bridge/src/pex_bridge/mcp_server.py` passed before the `app.py` integration. The integrated app has not yet passed Ruff, import, protocol, auth, focused pytest, or the full suite. No MCP E2E test file exists yet. Treat this code as in-progress, not working functionality.

First actions for the next agent:

1. Read this whole handoff and all three binding specs before editing.
2. Run `uv run ruff check services/bridge/src/pex_bridge/app.py services/bridge/src/pex_bridge/mcp_server.py`, then `uv run python -c "from pex_bridge.app import create_app; create_app(); print('ok')"`. Repair any issue before adding functionality.
3. Add `tests/e2e/test_mcp_server.py` using the official Python SDK client: `ClientSession` plus `mcp.client.streamable_http.streamable_http_client`. `httpx.ASGITransport` does not run lifespan automatically, so either enter the app lifespan or enter the exact app-scoped `app.state.pex_mcp.session_manager.run()` context in the test. Use `http://127.0.0.1` rather than host `test` to satisfy the SDK's default DNS-rebinding protection.
4. Prove real initialize/list-tools/call-tool traffic through `/mcp/`; exact four current tool names; exact-session binding; missing-session failure; target-relevant minimum context; source-session attribution; `SECRET`/`LOCAL_ONLY` exclusion; 401 without bearer; success with bearer; and no token in query strings/loggable URLs.
5. Review the lifespan carefully. It deliberately stores one `mcp_context = ...run()` and calls `__aenter__`/`__aexit__` on that same object. Do not call `.run()` separately at exit; the session manager is single-use per server instance. Mounted child lifespan is not run by Starlette, so the parent must own it.
6. After focused proof, run `uv run pytest -q` and `uv run ruff check .`, then update this handoff with actual counts.
7. Only then design the four mutation tools. `pex.report_progress`, `pex.request_decision`, `pex.handoff`, and `pex.verify_claim` must reuse canonical store/pipeline pathways with provenance, target binding, authorization, bounded inputs, audit receipts, and fail-closed behavior. Do not create direct database shortcuts or expose side effects merely to complete the name list.

The next product gap after the MCP read-only surface is the safely audited mutation half of §25, followed by the still-unproven live Cursor/Codex recovery loops and clean four-arm benchmark. Overall status remains **NO-GO**.

## Operator continuation mandate — persistent execution and mandatory subagent split

This section is a direct operating instruction from the operator for the replacement agent. It supplements the product specs; it does not weaken any safety, evidence, authorization, or submission gate elsewhere in this handoff.

### Do not voluntarily stop while safe in-scope work remains

- Create or resume one persistent goal with the complete objective: audit every prior-agent change against this handoff and all three binding specs, repair or replace incorrect work, build the actual spec-compliant PEX product, and verify it end to end strongly enough to maximize the chance of winning the hackathon.
- Do **not** redefine completion around one passing test group, one feature, MCP, pets, UI, packaging, local simulation, or a demo. The objective is the full product and evidence package described by the specs.
- Do **not** voluntarily end an active goal turn merely because a convenient slice is green, the next task is difficult, a tool call takes time, or the operator is unavailable. Continue to the next safe, highest-impact requirement.
- Use automatic goal continuations when available. On every continuation, inspect authoritative current state, classify the preceding turn as real progress / verified wait / no progress, and immediately take the next safe action.
- A status update, plan, handoff paragraph, speculative diagnosis, or repeated test result is not progress by itself. Progress means changing authoritative code/artifacts toward the specs or gathering new evidence that changes the next action.
- Never claim the goal complete until a requirement-by-requirement audit proves every binding requirement, named operation, recovery test, UI/runtime gate, adapter claim, benchmark claim, artifact, and submission prerequisite. Missing or indirect evidence means incomplete.
- If a long-running process is genuinely active, wait on its actual handle and report bounded progress. Do not restart a live run merely because one observation timed out.
- If external authorization is required, keep doing all other safe local work. Do not use “the operator must log in / record / submit” as an excuse to stop the product audit.
- If the platform, quota, context, or host forcibly ends work, update this handoff first with exact files, diffs, commands, results, running handles, unverified assumptions, and the next executable action. Leave the persistent goal active. That forced transfer is the only acceptable early stopping boundary.

### Use subagents deliberately and immediately

The replacement agent must use subagents to split independent audit and implementation work. Use all useful available concurrency slots, but keep the parent agent responsible for architecture, integration, conflict resolution, full-suite verification, and truthfulness. Subagents are not a way to outsource judgment or accept unreviewed code.

After the parent reads this entire handoff and all three specs, start bounded subagent workstreams such as:

1. **Spec-compliance auditor (read-only first).** Build a numbered matrix covering every normative requirement in `PEX_CORE_SPEC.md`, `PEX_BUILD_SPEC.md`, and `PEX_IMPLEMENTATION_RECOVERY_SPEC.md`. For each requirement record the exact implementation path, test/evidence path, status (`PROVEN`, `PARTIAL`, `CONTRADICTED`, `MISSING`, or `BLOCKED BY EXTERNAL AUTHORITY`), and next proof. This agent must challenge status-doc claims rather than echo them.
2. **MCP/security implementer or reviewer.** Own the narrowly bounded §25 MCP transport and named-tool slice described above. Inspect the in-progress files, repair lifecycle/auth/schema defects, add real protocol E2E tests, and report exact diffs and commands. Do not implement mutation shortcuts outside canonical store/pipeline/audit paths.
3. **Recovery/live-loop auditor.** Trace Codex and Cursor from real harness event → normalized event → persistent goal/context → supervisor evidence → policy → adapter action → observed result. Compare each path to recovery §13 and §30, identify the first unproven invariant, and build local deterministic/contract proof without opening extra desktop instances or spending external resources.
4. **UX/package/benchmark auditor** when a slot becomes available. Check command-deck behavior, accessibility, pet/runtime state priority, packaged assets, benchmark isolation/freeze honesty, and submission claims. Keep visual evidence distinct from source/build evidence and keep synthetic benchmark results distinct from live measured impact.

Subagent coordination rules:

- Give every subagent a concrete scope, expected evidence, allowed files, forbidden actions, and completion condition. “Audit the repo” is too broad.
- Prefer parallel read-only audits first. Assign write ownership by non-overlapping file sets. Never let two agents blindly edit the same file.
- All agents share the same dirty worktree. Before editing, each subagent must inspect the latest file and preserve user/prior-agent work. No reset, checkout-discard, clean, mass deletion, or broad formatter.
- The parent must review every subagent diff line by line against the specs before treating it as integrated. A subagent saying “done” is not evidence.
- Require exact command output, test counts, relevant paths, and unresolved caveats in every subagent report. Reject summaries that provide only confidence or intent.
- Use an independent/blind reviewer for high-risk or visually subjective work whenever a slot can be recycled. The reviewer must inspect the actual final artifact/diff, not the implementer's prose.
- After integrating a subagent slice, run focused tests, then the widest relevant regression suite. Once multiple slices converge, run the full Python, desktop, Rust, package, and protocol gates appropriate to the touched scope.
- If a subagent stalls or discovers an overlap, stop or redirect that subagent rather than allowing conflicting speculative edits.
- Do not let subagents stage, commit, push, deploy, publish, submit, spend, open extra desktop harness instances, or contact external parties. Those authority gates remain with the operator.

### Parent-agent execution order from this exact snapshot

Do not start with more prose or a new UI feature. Use this order unless new authoritative evidence proves a more causal ordering:

1. Read this entire file to EOF, then read the three specs to EOF. Extract their exact numbered requirements before trusting existing code or docs.
2. Inspect `git status --short`, `git diff --stat`, and relevant diffs. The worktree is intentionally dirty and contains user/prior-agent work. Preserve it. Do not infer that tracked means reviewed or untracked means disposable.
3. Spawn the bounded subagent workstreams above. Keep one integration slot for the parent.
4. Stabilize the in-progress MCP slice before extending it:
   - Ruff `app.py` and `mcp_server.py`.
   - Import and instantiate `create_app()`.
   - Verify dependency/lock consistency.
   - Test the mounted `/mcp/` transport with an official MCP client.
   - Test authentication enabled and disabled, invalid/missing bearer behavior, DNS-rebinding behavior, bounded inputs, missing session/goal errors, relevance filtering, provenance, sensitivity filtering, and tool schema/name stability.
   - Revisit the manual lifespan context if cancellation/startup failure can leak the session manager or overlay task. Prefer a structurally safe context/exit stack if tests reveal a problem.
5. Implement the remaining §25 mutation operations only through canonical domain functions:
   - `pex.report_progress`: bind reporter identity/session/goal, accept bounded structured progress/evidence references, persist provenance, and never accept a bare self-assertion as verified completion.
   - `pex.request_decision`: create or reuse the canonical pending-decision flow, preserve urgency/options/context, audit creation/resolution, and never auto-resolve a human-only decision.
   - `pex.handoff`: validate source and target sessions/project/goal, build the smallest relevant provenance-bound bundle, deliver through the real adapter path, observe delivery, and persist a receipt.
   - `pex.verify_claim`: route through the existing claim extraction/verification/evidence machinery, return explicit verified/contradicted/uncertain states, and fail closed on unavailable evidence.
   - Do not invent a second database schema, bypass `Pipeline`, write unverifiable context directly, or expose arbitrary shell/network execution through MCP.
6. Re-run the full local suite and update test counts only after the command finishes. Preserve the previous 717/19 baseline as historical evidence; never rewrite it as proof of newer untested code.
7. Continue the spec matrix in causal order: real Codex/Cursor recovery loops, context handoff quality, policy/autonomy safety, UI runtime/visual proof, exact-eight pet integrity, packaging/clean-clone reproducibility, benchmark isolation and honest four-arm evidence, cloud readiness, demo/submission artifacts.
8. Update `STATUS.md`, `BENCHMARKS.md`, `KNOWN_FAILURES.md`, `INTEGRATIONS.md`, and this handoff only with verified current facts. Resolve contradictions rather than adding another optimistic layer.
9. Keep overall status **NO-GO** until all local gates and external authority gates are actually cleared. “Code exists,” “tests import,” “package built,” “AWS login available,” and “submission draft exists” are different facts and must remain separate.

### Evidence discipline for every requirement

For each spec item, record all four of these before marking it proven:

1. **Implementation evidence:** the exact live code path used in production, including how it is reached. Dead code, declarations, mock-only paths, and adapter names are insufficient.
2. **Behavioral evidence:** a focused test or runtime trace that exercises the requirement's failure and success cases through the real boundary.
3. **Safety evidence:** authorization, sensitivity/redaction, bounds/timeouts, provenance, audit receipt, idempotency/concurrency, and fail-closed behavior appropriate to the operation.
4. **End-to-end evidence:** the requirement works as part of the closed loop, not only as a helper/unit. For visual requirements this means inspecting the rendered/package runtime; for external harnesses it means an allowed real integration run; for impact it means one clean isolated experiment.

Use these truth labels consistently:

- `PROVEN`: current authoritative evidence covers the full requirement.
- `PARTIAL`: some real implementation/evidence exists but scope or E2E proof is incomplete.
- `CONTRADICTED`: current behavior or artifacts violate the requirement or an existing claim.
- `MISSING`: no live implementation/proof exists.
- `BLOCKED BY EXTERNAL AUTHORITY`: all safe local preparation is complete and the only remaining action requires explicit operator authority or unavailable external state. This label applies to that item only; it does not stop other work.

### Absolute authority and honesty boundaries

- Never stage, commit, push, open a PR, deploy to AWS/AgentCore, incur spend, publish, submit to Devpost, consume a one-shot action, contact organizers, or alter external accounts without explicit action-time authorization.
- Never erase or overwrite the dirty worktree to obtain a clean result. A clean-clone proof requires a reviewed, operator-authorized commit boundary first.
- Never open a second Cursor instance. Use the already-open apps only when a live test is authorized and safe. Ask before opening Hermes or Devin desktop applications.
- Do not expose tokens, secrets, private paths, or sensitive context in MCP, HTTP, WebSocket, logs, benchmark rows, screenshots, docs, handoffs, or submission material.
- Do not call a declared adapter Deep. Prove event fidelity, action fidelity, observed outcomes, and recovery behavior for each harness label.
- Do not treat model agreement as verification. Evidence must be independent, bounded, attributable, and checked against external/project state.
- Do not treat synthetic/local contract tests as live harness proof, source presence as rendered visual proof, a package artifact as launch proof, merged scratch rows as a clean benchmark, or a UI/config indicator as runtime behavior.
- NOOP and silence are first-class correct outcomes. Do not reintroduce generic STOP nagging, pressure workers after verified completion, or convert uncertainty into a warning.
- Keep the built-in pet fleet exactly eight: `pex`, `ledger`, `mesh`, `nudge`, `drift`, `quiet`, `ember`, `von`. Do not revive the stale count of ten or mix custom imports into the starter count.

### Required reporting while the operator is away

- Keep commentary concise but evidence-based: current task, authoritative finding, change made, verification result, and next causal action.
- Do not ask the operator routine implementation questions that can be answered from specs/code/tests. Make conservative, reversible assumptions and document them.
- Ask only when a choice materially changes product intent, requires new authority, risks irreversible loss, incurs external cost, or consumes a submission/one-shot quota.
- Every forced handoff must state: GO/NO-GO; exact last verified commands/counts; files changed; processes still running and their handles; unverified code; external blockers; authority not granted; and the first executable next command.
- The replacement agent must keep this document current after each material verified milestone so another quota transition does not lose causal context.

## 28 Aug 2026 verified update — pets/package green, overall goal still active

This section supersedes older pet/package and command-deck existence statements below. It does **not** supersede the recovery, live-loop, benchmark-honesty, cloud, remote-channel, visual-runtime, or submission gates.

- The binding built-in fleet is exactly **8**, in registry order: `pex`, `ledger`, `mesh`, `nudge`, `drift`, `quiet`, `ember`, `von`. Custom imports remain separate.
- All eight shipped Codex-v2 atlases now have hash-bound structural validation, three isolated blind reviews, independent exact-WebP final visual review, parent promotion evidence, and approved release receipts under `apps/desktop/src/pets/_audit/release/`.
- Mesh was the last blocker. The accepted v19 attempt is `apps/desktop/src/pets/_hatch/mesh/repairs/20260827-a/candidate-v19/final/spritesheet-extended-attempt-5.webp`, promoted byte-for-byte to `apps/desktop/src/pets/mesh/spritesheet.webp`, SHA-256 `3931f2604269b41b5e6053271131f85413dffcf615550f4afa5b8139130f18ee`.
- The build-enforced exact-eight manifest now exists at `apps/desktop/src/pets/release-manifest.json`. `apps/desktop/scripts/build-sidecar.mjs` verifies ordered IDs, pet manifests, shipped spritesheets, release receipts, and every evidence hash before freezing pets into the bridge.
- Frozen bridge inventory verification passes with `version=1`, `pet_count=8`, and the exact expected pet IDs/hashes.
- Desktop verification after Mesh promotion: `npm test` **16/16 pass**; `npm run build` pass; `uv run pytest -q` **707 passed, 19 skipped**; `uv run ruff check .` pass; Rust `cargo test` **4/4 pass**.
- Sidecars rebuild successfully. Tauri debug packaging now succeeds after explicitly binding the existing icon set in `tauri.conf.json`. Local artifacts:
  - `apps/desktop/src-tauri/target/debug/bundle/msi/PEX_0.1.0_x64_en-US.msi`
  - `apps/desktop/src-tauri/target/debug/bundle/nsis/PEX_0.1.0_x64-setup.exe`
- A hidden packaged-GUI smoke command was blocked by the host's process-control policy before launch. Do not claim that GUI-launch smoke. The non-interactive frozen bridge verifier and complete Tauri package build are green.
- **Overall release remains NO-GO.** The repository is still a large dirty worktree (176 tracked paths changed and 274 untracked paths at this snapshot); critical release inputs, receipts, and the manifest are untracked. Nothing was staged or committed. A clean-clone/package proof is impossible until the operator explicitly authorizes a reviewed commit boundary.
- AgentCore cloud deployment remains NO-GO without live AWS authentication/tooling/ARN and separate action-time authorization. Do not deploy, spend, publish, or submit from this update.
- The persistent goal remains active because the three product specs, live Codex/Cursor recovery demonstrations, clean four-arm evidence, full UX/demo bar, and submission are not yet all cleared.
- The desktop now contains the six required command-deck views (`Now`, `Decisions`, `Context`, `Interventions`, `Agents`, `Bench`) plus compact and inspector surfaces. TypeScript production build and desktop unit tests pass, but the packaged GUI still lacks an allowed launch/visual smoke on this host; do not treat source presence as visual-runtime proof.

### 28 Aug recovery hardening — uncertain evidence cannot authorize a warning

- Recovery Test 4 had a real fail-open edge: a semantic intervention could be accepted when the independent verifier called only `run_verification`, even if that immutable receipt was `uncertain`, `no_claims`, or unavailable. A second model saying “approved” was enough to turn uncertainty into a worker-facing message.
- `services/supervisor/src/pex_supervisor/loop.py` now rejects that verifier result with `independent_verifier_status=uncertain_evidence`. To approve a semantic-only intervention from an uncertain local receipt, the verifier must inspect another relevant bounded source such as recent events/context/scores/session state and return concrete evidence. Deterministic contradictions remain unchanged and still win over model output.
- Every STOP verification stored by `services/bridge/src/pex_bridge/pipeline.py` now carries an `evidence_gathering` receipt: whether gathering ran, which bounded sources were consulted, workspace snapshot state, and claim count. This makes Recovery Test 4's “gather evidence first” ordering auditable rather than implicit.
- Added regression coverage proving an uncertain STOP gathers evidence and stays silent, an uncertain verification receipt alone cannot authorize a semantic nudge, and ten verified completions inspected by a deliberately nagging model produce **0/10 worker-facing interventions (0.0 false-positive rate)**.
- Verification after this repair: focused recovery tests **35 passed**; full Python suite **710 passed, 19 skipped**; `uv run ruff check .` passes.
- This is local deterministic/adversarial-model proof, not a substitute for the still-required explicitly authorized live Codex/Cursor Test 4 and ten-task Test 5 runs. Overall release remains **NO-GO**; nothing was staged, committed, deployed, published, or submitted.

### 28 Aug UX state repair — supported pet moods are now reachable

- The atlas/frontend declared `observing`, `handoff`, and `approved` moods, but the live bridge never returned a `mood`; ordinary `working` therefore made those spec states unreachable. This was a real implementation gap behind the status copy.
- `pet_snapshot()` now derives bounded 12-second transitions only from recent audited outcomes: successful context delivery → `handoff`, confirmed allow delivery → `approved`, and an evidenced silent STOP inspection → `observing`. Accessible headline text accompanies each state.
- A second stale mood selector in `AppState.decorate_pet()` initially overwrote those bridge states back to `working`/`idle`. It now preserves audited handoff/approval/observing transitions while retaining the same safety priority; the M0 API roundtrip asserts the live `/v1/pet` response, not only the helper.
- Priority is fail-safe: bridge offline, human decision, blocked/error, and drift/working state cannot be hidden by a stale celebratory transition. Handoff/approval may briefly animate over ordinary work, but never over a decision or warning.
- Latest verification: full Python suite **713 passed, 19 skipped**; `uv run ruff check .` passes; desktop tests **17/17 passed**; TypeScript/Vite production build passes. Packaged GUI visual smoke remains unproven under the host policy.

### 28 Aug context-mesh repair — target work now controls the minimum bundle

- The mesh scorer already had provenance, goal/project, sensitivity, staleness, duplicate, supersession, token-budget, and verified-evidence gates. The stale “length + 120s heuristic” description below was no longer accurate.
- A remaining defect still violated the smallest-bundle rule: when a target declared a concrete task/role/active files, goal-relevant but target-irrelevant items could pass on broad goal overlap and kind/recency bonuses. The bundle ranked them lower but still sent them.
- `build_bundle()` now makes declared target work a hard admission gate. Ordinary facts/artifacts/results must overlap the target role, current task, phase, or active files. Goal-wide decisions, constraints, and unresolved dependencies remain eligible because dropping them would be unsafe.
- The runtime previously read `current_task`, `task_phase`, and `active_files` but never populated them. Event ingestion now derives bounded routing state from real user prompts, file activity, shell/test phase, and errors, and preserves those bridge-owned fields across later adapter discovery snapshots.
- End-to-end proof: a target prompt scoped work to the frontend pet atlas; a source backend-migration artifact was withheld; a later frontend artifact produced one handoff whose `bundle.items` contained only that frontend fact. The complete goal summary/acceptance contract remains mandatory in the wire bundle.
- Latest verification: focused context/pipeline/E2E tests **30 passed**; full Python suite **717 passed, 19 skipped**; `uv run ruff check .` passes. This is local synthetic end-to-end proof; the judged live Cursor→Codex/Codex→Cursor handoff remains unproven.

---

## 0. First action: audit the slop

Do this **before** new features, UI polish, extra harnesses, AgentCore, posts, or Submit.

Previous work mixed real progress with overclaims, stale docs, unused code paths, merged gitignored jsonl that made the manifest look frozen, and a habit of stopping at “the operator must login.” Assume anything that smells like a demo shortcut is guilty until you prove it from runtime evidence.

### 0.1 Honesty audit (must produce written findings)

Prove or disprove each claim with files, tests, live logs, or jsonl — not intent.

| Claim previous agents made | How to audit | Likely truth |
| --- | --- | --- |
| “PEX is a working supervisor loop” | Recovery spec §25 + §30 vs live Codex/Cursor | Partial machinery. Not recovery-complete. |
| “Closed loop starts from a user-created goal” | Companion form → `POST /v1/goals` → attach → STOP uses that goal | Implemented in UI + store. Not the same as “PEX reasons.” |
| “STOP inspects rather than nags” | `decide()` + `plan_deterministic` + live STOP traces | STOP with an attached goal **always** calls the model (`needs_semantic_inference`). Deterministic NOOP exists, but the live path is not “inspect only when needed.” |
| “Strands supervisor with tools” | `services/supervisor/src/pex_supervisor/loop.py` + `evidence_tools.py` | Audit repair now uses a fresh bounded supervisor with six request-scoped read-only evidence tools and validated structured output. Model-originated interventions not required by deterministic evidence must pass a fresh second verifier Agent and fail closed on rejection/failure/empty evidence. Tool calls and both model cycles are audited. This is not a Strands Graph, and no side-effect/web tool is claimed. |
| “Claims verified against pytest/artifacts” | `claims.py`, `verify.py`, Cursor/Codex `process_state` | Real code. Uncertain → silence is tested. Premature missing-file without a claim is **uncommitted** (see §8). Recovery Test 4 “gather evidence first” is weak/absent. |
| “Auto-handoff is real context mesh” | `pipeline.py` `_maybe_auto_handoff` + `context/mesh.py` | Provenance-bound relevance and compact bundles now run in the live path, with target prompt/phase/files persisted and target-irrelevant facts excluded. Live cross-harness demonstration and first-action handoff-quality proof remain open. |
| “Drift detection” | `planner.py` + `scoring.py` | `drift >= 0.75` and `repeated_command_count >= 3` → nudge. Repeated identical failures → overlay **only** if overlay-capable (synthetic / `modify_config`). Cursor cannot overlay. Not semantic trajectory reasoning. |
| “JIT harness compiler” | `APPLY_OVERLAY` + `CursorAdapter.apply_overlay` | Overlay object exists. Cursor `apply_overlay` returns False and must **not** smuggle overlay text into the prompt. Not a compiler that changes tools/MCP/model on Cursor. |
| “Four-arm is frozen / live rows exist” | `benchmarks/manifest.yaml` `frozen: true` vs `BENCHMARKS.md` vs gitignored jsonl | **Docs contradict each other.** Freeze test passes because local jsonl exist and `freeze_blockers()` is empty. That is **not** a citeable impact score. See §6. |
| “Live inspect proofs for many harnesses” | `tests/contract/test_live_*.py` + `benchmarks/results/_scratch/` | Live tests **require** `used_llm is True`. Last full live suite had **12 failures** (OpenRouter was sent Zen ids). Routing fix is on `main` (`b435ab5`) but live suite was **not re-run**. Do not believe `_scratch` without opening the files. |
| “Companion is the spec pet/command deck” | `apps/desktop/src/App.tsx` + `components/CommandDeck.tsx` vs build spec §6 | Compact, inspector, Settings, overlay, and all six named deck views now exist and build. Open agent focuses local windows or an allowlisted existing Devin URL. Local attention inbox exists; Telegram/Discord/WhatsApp/Slack stay disconnected. Measured fingerprint depth, packaged-window visual QA, and the judged live demo remain open. |
| “Starter pet count” | `apps/desktop/src/pets/` | Historical note was wrong. The operator later clarified the binding fleet is exactly **8**: `pex`, `ledger`, `mesh`, `nudge`, `drift`, `quiet`, `ember`, `von`. Custom imports/hatches are separate. |
| “Canned `PEX:` nag is gone” | grep worker text, planner, tests | Prefix is stripped/rejected. Generic nag was the original recovery target. Still audit every SEND_NUDGE for recovery §29 quality. |

### 0.2 Contradictory docs (fix after you know the truth)

These files currently cannot all be true:

- `STATUS.md` — “working loop”, frozen four-arm, Cursor/Codex process_state (includes **uncommitted** Codex work).
- `BENCHMARKS.md` — still says `frozen: false` and **“No valid presentation scores.”**
- `README.md` — “No scores until frozen live rows exist” while `benchmarks/manifest.yaml` is `frozen: true`.
- `docs/posts/02-attention-benchmark.md` — talks as if four-arm is frozen and honest.
- `KNOWN_FAILURES.md` — thin, stale (“seven pets”, “not submission-ready”) and missing the real product holes.

`STATUS.md` is supposed to contain **only verified** status (recovery §27). Previous agents padded it.

### 0.3 Unused / misleading code

| Path | Issue |
| --- | --- |
| `services/supervisor/src/pex_supervisor/graphs.py` | Removed during audit because it was not the live path and its rejection branch did not reliably replace the proposed action. |
| `services/supervisor/src/pex_supervisor/tools.py` | Removed. It was a non-live ContextVar/tool-action path. The replacement `evidence_tools.py` is request-scoped, read-only, bounded, and used by both fresh Agents. |
| `services/bridge/src/pex_bridge/adapters/fleet.py` | Pi / Prime / ZCode / DeepSeek are **DeclaredAdapter** shells (Basic/Experimental). Registry lists them so `REQUIRED_HARNESSES` stays green. That is not Deep control. |
| `benchmarks/manifest.yaml` `frozen: true` | Driven by **merged coverage** across multiple gitignored jsonl files, not one clean four-arm experiment. |

### 0.4 How previous agents failed (do not repeat)

1. Treated “operator must `aws login` / record demo / Submit” as the leftover work.
2. Shipped thin slices (goal form, claims regex, pytest parse) and wrote STATUS as if the closed loop was the product.
3. Froze or described the benchmark from local jsonl without a citeable, single-run, isolated four-arm.
4. Ended turns when a subset of unit tests passed.
5. Did not walk the three specs requirement-by-requirement against runtime.
6. Did not verify UI in a real companion window against build spec §6.
7. Did not re-run live LLM tests after inspect routing changes.
8. Left product work **uncommitted** (Codex `process_state`) while talking as if it shipped.

---

## 1. What we are actually trying to achieve

Hackathon: AWS + Devpost **Agents for Humans**, track **Professional Agents**. Deadline **14 Sep 2026 17:00 PDT**. Public repo: https://github.com/josepha-mayo/pex (MIT). Workspace: `C:\Users\JosephMayo\Projects\pex` (Windows, PowerShell).

Operator intent (from [PEX hackathon build](0c8698c5-d86c-4265-a369-c2a15f801d92), 25–27 Aug 2026):

- Win if possible, but **build the real product** even if it does not win.
- Follow the specs in detail. Do not build “generic agent orchestrator slop.”
- All listed harnesses, honestly labeled. Cursor and Codex are the **deep** targets. Do not fake Deep.
- Pets: exactly **8 starters** per the operator’s later correction, Codex-v2 atlases, customizable, hatch. Check how Codex pets work; **do not copy Codex built-in art.**
- Use the operator’s already-open apps (Cursor, Codex/ChatGPT.exe, Grok Bot). **Do not spawn a second Cursor.** Do not install leftover `cursor-agent`. Ask before opening Hermes/Devin desktops.
- Subagents should audit. Do not hallucinate harness protocols — read official docs and installed binaries.
- Do not stop until Submit is actually done **and** the work is good enough to have a real chance. Submit is the **last** step, not the current one.

**One-sentence product** (`docs/PEX_CORE_SPEC.md` §0):

> PEX is an independent, goal-aware supervisor that sits above existing coding-agent harnesses, watches what they actually do, and autonomously handles the repetitive human work of supervising them.

If someone can summarize the implementation as “Codex gets extra instructions when PEX is enabled,” it is wrong.

**Success** (`docs/PEX_BUILD_SPEC.md` Definition of success + core spec §22):

A person runs several coding agents they already use, gives PEX persistent goals, and stops doing most babysitting. PEX observes, preserves/transfers context, catches drift/stagnation/false-done, nudges or reconfigures, handles low-risk approvals under **local** policy, verifies claims against external state, and interrupts the human only for real decisions.

The **closed loop** (core spec §3) must be real:

```text
USER GOAL → persistent intent + acceptance
→ existing worker → real harness events + files + tests + process state
→ PEX observes → reasons → decides (including NOOP)
→ action through a real adapter → observe result → loop
```

Hackathon judging cares about Technical Implementation, Design (pet/UX), Impact (measured lift + less human management), Originality, Presentation (live closed loop). **None of those are satisfied by a login checklist.**

---

## 2. Binding specs (clear all three; do not cherry-pick)

| File | Role |
| --- | --- |
| `docs/PEX_CORE_SPEC.md` | Product law. Closed loop, not-a-prompt-suffix, demo bar §20, benchmark integrity, development order §19. |
| `docs/PEX_BUILD_SPEC.md` | Full product: UX §6, architecture, adapters §12, data model §9, scoring, pets, hackathon artifacts. |
| `docs/PEX_IMPLEMENTATION_RECOVERY_SPEC.md` | Written because the first implementation **was canned STOP nag**. Completion-hook PEX is forbidden. Recovery “done” is §30. |
| `docs/PEX_SUPERVISOR_PROVIDERS.md` | BYOK / login / local / custom. Also inlined as core §4.1 and build §26.0. |

Also keep current: `STATUS.md`, `DECISIONS.md`, `INTEGRATIONS.md`, `BENCHMARKS.md`, `KNOWN_FAILURES.md`. Recovery wants `PEX_INTERVENTION_LOG.jsonl` — check whether it actually exists and is written in production.

**Tension you must resolve with evidence, not vibes:** recovery §0 says stop extra UI/integrations until one real Codex loop works. The operator now wants the **full** specs cleared (agent + UI + benches + then submit). Correct order:

1. Audit slop.
2. Make the Codex **and** Cursor closed loops meet recovery §13 tests + §30 on **live** sessions (complete → NOOP; incomplete → specific evidenced continue; false test claim → cite failure; uncertain → gather not nag; no spam).
3. Then build the spec UI (command deck, pet states, exactly 8 built-ins) **on top of a real supervisor**, not instead of it.
4. Then a **clean** four-arm you can stand behind (or keep unfrozen and say so).
5. Then deepen other harnesses without lying about labels.
6. Then AgentCore, Builder posts, ≤5 min live demo, Devpost Submit.

Do not skip to 6.

---

## 3. Recovery spec “PEX works” bar (not cleared)

From `docs/PEX_IMPLEMENTATION_RECOVERY_SPEC.md` §25 / §30. Treat every box as **unproven** until you have a live log.

### Core

- [ ] Real Codex session attaches (isolated `codex app-server` stdio — **not** ChatGPT.exe).
- [ ] Events stream (`item/completed`, `turn/completed`, approvals).
- [ ] Persistent goal attaches (companion-created, not invented).
- [ ] Claims extract from worker narration, not from shell stdout.
- [ ] Evidence providers work (pytest `process_state`, workspace snapshot, not hidden evaluator).
- [ ] Real model inference (`used_llm=true` on STOP inspect when a goal is attached — re-prove after routing fix).
- [ ] Structured decision.
- [ ] NOOP works on genuine completion.
- [ ] Specific intervention works on genuine miss.
- [ ] Follow-up reaches the **same** `threadId`.
- [ ] Outcome is observed after the nudge.
- [ ] Audit log complete.

### Behavior (Codex demo tests §13)

- [ ] Test 1 — correct completion → inspect → **NOOP** (not a generic warning).
- [ ] Test 2 — premature stop → exact missing criterion + evidence → continue → verify final.
- [ ] Test 3 — “tests pass” after failing pytest → cite **exact** failure.
- [ ] Test 4 — uncertain → gather evidence first, then NOOP or specific intervene.
- [ ] Test 5 — ten correct completions must not yield ten warnings. **Measure false-positive rate.** This was never done.

### Safety / integrity

- [ ] Wrong session never receives the message.
- [ ] Destructive approvals not silent-allow.
- [ ] Cloud cannot bypass local policy.
- [ ] Supervision can be paused.
- [ ] Reversible actions undo.
- [ ] No hidden benchmark data in the supervisor process.
- [ ] No task-specific canned intervention / treatment-only prompt suffix.

**Recovery is not done** because files exist, Docker builds, Tauri launches, hooks fire, or one unit test passes (§30).

---

## 4. Core spec gaps (not cleared)

Walk `docs/PEX_CORE_SPEC.md` yourself. Known holes vs current tree:

| Spec | Gap |
| --- | --- |
| §2 premature stop / false completion | Machinery started (claims + verify + process_state). Live Codex Test 1+2 pair not proven this week. Codex pytest parse is **uncommitted**. |
| §2 context handoff | Local E2E now proves observed fact → provenance store → target-task relevance → one-item bundle → target delivery → audit, including irrelevant-fact exclusion. Demo bar §20 steps 5–6 remain unproven on live Cursor/Codex sessions. |
| §2 drift | Repeat-command heuristic. |
| §2 wrong dependency order | Observed missing required artifacts during downstream eval/train/deploy/bench commands; generator commands stay silent. Live harness proof still missing. |
| §2 permission | Policy engine + Cursor `beforeShellExecution` + Codex approvals. Fail-open hooks if bridge down. |
| §2 user mistake | `classify_prompt` + Cursor `beforeSubmitPrompt` ASK_HUMAN. Needs live proof. |
| §4 actual agent | STOP has request-scoped inspect tools plus `web_search` / `scrape_url`. Ask PEX inspects eval artifacts from session cwd and can run a read-only Strands review Agent. A live loaded-model STOP/Ask on Codex is still unproven. |
| §4.1 providers | Registry in `providers.py` is broad. Login/OAuth modes mostly **not** implemented (BYOK/custom/Zen work). Catalog in Settings. |
| §5 persistent intent | Goal model + companion create/attach. `non_goals` added. Fingerprints are count-based STOP/overlay aggregates (unmeasured rates stay null). Labeled decisions / rejected approaches / unresolved questions persist as Decision rows and are shown on the inspector; prompt lint uses rejected approaches. After two gap/contradiction STOPs, overlay-capable harnesses get a reversible evidence-before-done overlay; first-sample STOP remains a specific nudge. |
| §6 context mesh | `context/mesh.py` + store. Target-task relevance, rejected approaches in `do_not_redo`, and a real next objective are locally proven. Live Cursor/Codex transfer and full health-driven session migration remain open. |
| §7 JIT | Overlay for overlay-capable harnesses only. |
| §8 pet | Compact is pet + live counts (not a worker catalog). Drift nudges mark `drifting` in the present tense and do not stamp “corrected.” Inspector + six-view deck build; Open agent can focus a local window or open an allowlisted existing Devin URL. Local attention inbox exists; live messengers and packaged-window visual QA remain open. |
| §9 harnesses | See `INTEGRATIONS.md`. Prime/ZCode/DeepSeek/Pi thin. |
| §10–16 benchmark | Integrity tests exist (`tests/unit/test_leakage.py`, `test_audit_invariants.py`). Presentation freeze is **local jsonl merge**. Do not cite leaked 1/5 vs 4/5. |
| §17 audit | Interventions stored in SQLite via pipeline and appended to `PEX_INTERVENTION_LOG.jsonl` next to the store. Completeness of every CORE §17 field on every production path is not independently re-audited this slice. |
| §18 product tests | Unit/e2e green; live LLM suite stale/failing. |
| §19 order | Previous agents jumped around (pets, many adapters, freeze) before recovery loop was done. |
| §20 demo | 15-step live demo **does not exist**. `docs/demo/companion.webm` is companion stills, not live attach. |

---

## 5. Build spec UX gaps (UI/UX is not perfect)

`docs/PEX_BUILD_SPEC.md` §6 vs `apps/desktop/src/App.tsx` + `styles.css`:

**Exists**

- Tauri 2 + React companion, compact ~920×700, Settings as its own hash page, transparent pet overlay (`releasePet`).
- Home compact: pet, live working/need-you/drifting counts, optional attached goal title, Inspect. Pet roster is Settings. Session list is command-deck Now. Ask PEX is inspector + deck, read-only (`/v1/ask`) — **must not** be routed through `decide()`. Spec answers stay canonical. Eval questions inspect attached workspace artifacts when cwd is present. A loaded Strands model may run a read-only inspect review; `inspect_http` remains the fallback.
- Settings: appearance, supervisor provider + model id, hatch, import.

**Still missing / unproven vs spec**

- Packaged-window visual and interaction QA for the compact → inspector → deck expansion (the source/build path exists).
- Full live-data proof for every deck view; Agents intentionally leaves unmeasured fingerprint fields unknown and Bench remains unfrozen.
- Remote messengers (Telegram, Discord, WhatsApp, Slack) stay honestly disconnected. The local `{PEX_HOME}/channels/inbox.jsonl` inbox is the implemented §6.6 path.
- “Saved N tokens” (token savings are not invented). Attention metrics on Now count ASK_HUMAN, reversals, and confidence; human active seconds stay unavailable.
- Judged ≤5 min video of **live Cursor or Codex attach**, not companion stills.

Do not polish CSS to hide a missing supervisor. Recovery §20: the pet is the face, not the product. After the loop is real, the UI still has to match §6 — the operator was explicit that UX is not done.

---

## 6. Benchmark honesty (not “benchmarked”)

Raw jsonl are **gitignored** (`benchmarks/results/*.jsonl`). They exist on this machine. `freeze_blockers()` is **not** empty without a single coherent live run. `tests/unit/test_audit_invariants.py::test_pexbench_manifest_stays_unfrozen_without_one_coherent_live_run` requires `benchmarks/manifest.yaml` `frozen: false`, which is the current file.

Existing local jsonl files are diagnostic only. Later files overwrite earlier keys (`four_arm.arm_coverage`). They cannot justify a freeze.

Local files:

| File | What is in it (audit yourself) |
| --- | --- |
| `benchmarks/results/fourarm_sol.jsonl` | All 5 Codex pairs + Cursor baselines 001–005 (mostly fail) + `cursor_pex` 001 fail. Codex 002: baseline **success**, PEX **fail** (PEX can hurt). Codex 001 both fail. |
| `benchmarks/results/fourarm_solb.jsonl` | Cursor + Cursor+PEX 002–005 success, 001 both fail. |
| `benchmarks/results/fourarm_20260827.jsonl` | One Codex 001 live fail. |
| `benchmarks/results/synthetic_smoke.jsonl` | `synthetic_pex`, `not_a_presentation_arm`. Forbidden as a Cursor/Codex arm. |
| `benchmarks/results/INVALID_LEAKED_RUNS_DO_NOT_USE/` | **Never cite.** Previous 1/5 vs 4/5 stuffed treatment prompts + handoff oracle. |

**You may not:**

- Invent lift.
- Cite leaked 1/5 vs 4/5.
- Treat `frozen: true` as “impact criterion met.”
- Complete `pexbench_001` by writing `math_utils.py` yourself.
- Re-seed stubs over a worker workspace.
- Hand-edit jsonl.

**You must audit:** whether Cursor `transport_kind=cursor_hooks` rows actually ran isolated `TASK.md` workspaces, or stamped `live=True` against this desktop. `four_arm.py` refuses spawning another Cursor window. That makes honest Cursor arms hard — previous agents may have stretched “this-desktop hooks” into presentation rows. If those rows are not isolated task runs, **unfreeze** and say so. A valid incomplete freeze is better than a lying freeze.

`BENCHMARKS.md` is stale and closer to the honest “no valid presentation scores” line than `STATUS.md`. Reconcile after the audit.

Tasks (not sacred, do not add more until the loop works): `benchmarks/tasks/pexbench_00{1-5}_*` premature_stop, drift, permission_spam, false_claim, handoff.

---

## 7. What previous work actually built (file map)

### Conversation / git

- Transcript: `C:\Users\JosephMayo\.cursor\projects\c-Users-JosephMayo-Projects-pex\agent-transcripts\0c8698c5-d86c-4265-a369-c2a15f801d92\0c8698c5-d86c-4265-a369-c2a15f801d92.jsonl`
- Branch: `main` tracking `origin/main` at `b435ab5`.
- Recent commits:
  - `b435ab5` Feed live Cursor shell results into STOP verification; stop sending Zen ids to OpenRouter.
  - `b24d8b8` Check STOP claims against pytest/artifacts; nudge only when contradicted.
  - `49e76dc` User-created goal, auto-handoff, STOP claims (not silence = done).
  - `143376b` Honest live attach, compact companion, frozen four-arm rows.
  - `b084edb` Inspect loop + compact companion rebuild.
  - `d138f4a` Publish supervisor tree.

### Uncommitted (must finish or revert; do not lose)

Working tree at handoff (not on `origin`):

- `services/bridge/src/pex_bridge/adapters/codex.py` — `normalize_item` pytest `process_state`; shell stdout **not** `message_delta`; `turn/completed` ingests `commandExecution`/`fileChange`; STOP text from last `agentMessage`; `completed` status ≠ exit 0.
- `services/bridge/src/pex_bridge/shell_state.py` — `aggregated` in blob; drop `completed` from success outcomes.
- `services/supervisor/src/pex_supervisor/verify.py` — no asserted claims + observed workspace + missing required filename → contradicted.
- tests: `test_codex_pipeline_pump.py`, `test_verify.py`, `test_planner.py`, `test_shell_state.py`
- `STATUS.md` — already describes some of this as if shipped.

Offline tests after that work: **189 passed**, 1 skipped, 13 live deselected. That does **not** prove live Codex/Cursor.

### Runtime layout

```text
apps/desktop/          Tauri companion (App.tsx, styles.css, pets/)
services/bridge/       FastAPI :7420 — adapters, pipeline, store, policy, pets, hooks
services/supervisor/   inspect_http, planner, verify, providers, evidence_tools, two-Agent loop
packages/protocol/     Goal, events, InterventionType, overlays
integrations/          cursor hooks, claude hook, hermes plugin, generic pex_hook.py
benchmarks/            four_arm.py, evaluator.py, runner.py, boundary.py, tasks/
deploy/agentcore/      Docker/AgentCore — not deployed
docs/                  specs, posts drafts, SUBMISSION.md, architecture PNG
tests/                 unit, e2e, contract (live_*), chaos, integration
```

### Supervisor path (what actually runs on STOP)

1. Adapter normalizes event → `Pipeline.handle`.
2. On STOP: `extract_claims` → `snapshot(cwd)` → `verify_claims` → features on scores.
3. `decide(request, model)`:
   - `plan_deterministic` always.
   - If goal attached: `run_strands` → `complete_typed_action` (HTTP JSON) → `_action_from_proposal`.
   - LLM NOOP can be upgraded to nudge if required filename missing (`loop.py`).
4. Local policy → `executor` → adapter `send_message` / permission / overlay.
5. Cursor stop hook may return `followup_message` when action is SEND_NUDGE **and evidenced** (not only when `used_llm`).

Python: `C:\Users\JosephMayo\Projects\pex\.venv\Scripts\python.exe`. PowerShell: use `;` not `&&`. Never `git config`. Never commit `.env`. The final QA-approved built-in Von spritesheet must be tracked so clean-clone packages include it; `_hatch/` QA candidates remain unshipped.

### Adapters (honest labels in INTEGRATIONS.md)

| Harness | Code | Truth |
| --- | --- | --- |
| Synthetic | `adapters/synthetic.py` | Deep in-process. Tests/demo only. |
| Cursor | `cursor.py`, `cursor_hooks.py`, `pex_cursor_observe.py` | This desktop: **observe JSONL only** (timeout 3, no failClosed). Not Strong control. Never second window. ACP send is explicit attach; `cursor:desktop` cannot send or take a goal. |
| Codex isolated | `codex.py` | `codex app-server --listen stdio://`. Deep after initialize. |
| ChatGPT.exe | desktop observe | **Not** App Server. Observe/focus only. |
| OpenCode / Qwen | HTTP | Deep when daemon + pump attached. |
| Claude Code | hooks | Strong. |
| Hermes / Kimi / OMP | ACP stdio | Strong→Deep with pump. Hermes plugin `integrations/hermes-plugin/pex_plugin.py`. |
| Grok Build | `grok agent stdio` | Not Grok Bot. PATH `agent` is Grok Build — never Cursor. |
| Grok Bot | `grok_bot.py` | Observe-only. |
| Devin | org-api | Poll `exit` then POST messages. Do not launch Devin.exe. |
| Pi / Prime / ZCode / DeepSeek | `fleet.py` | Basic / Experimental declarations. |

### Policy / never canned

- Worker-facing text must not start with `PEX:`.
- Default STOP is NOOP unless evidence justifies.
- Fail-open hooks if bridge down; fail-closed destructive when up.
- `/v1/ask` is review, not `decide()`.

---

## 8. Never-do list (operator + specs + prior disasters)

- Do not Submit until the product, UI, specs, and an honest bench story are real.
- Do not mark the long-running hackathon goal complete until Devpost is actually submitted **after** that.
- Do not canned `PEX:` injects.
- Do not cite leaked benches.
- Do not spawn a second Cursor / leftover `cursor-agent`.
- Do not treat ChatGPT.exe as Deep App Server.
- Do not implement JIT as extra worker prompt text.
- Do not route Ask PEX through `decide()`.
- Do not weaken live tests to accept `used_llm=False` as Strands proof.
- Do not copy Codex built-in pet art.
- Do not print or commit `.env`.
- Do not invent four-arm lift.
- Do not complete pexbench tasks in the worker workspace yourself.
- Do not redefine PEX into a dashboard, prompt suffix, or notification tray.

---

## 9. Historical operator notes — superseded; do not execute these commands

- OS: Windows 10/11, PowerShell.
- Apps often open: this Cursor, Codex/ChatGPT, Grok Bot. Ask before opening others.
- **REVOKED/UNSAFE:** the former `pex-bridge --no-auth` command no longer exists and
  must not be reconstructed with `PEX_REQUIRE_AUTH=false`. Use the authenticated Tauri
  owned-sidecar flow described in the 30 Aug checkpoint below. Do not restart, kill,
  or duplicate the currently occupied `127.0.0.1:7420` process without explicit
  operator coordination.
- Companion: `apps/desktop` `npm run dev` — on this machine use `http://localhost:1420` (`127.0.0.1:1420` may not bind). See `docs/demo/README.md`.
- Tests: `.\.venv\Scripts\python.exe -m pytest tests/unit tests/e2e tests/contract -q -m "not live_llm and not live_codex"`
- Live LLM: needs keys in gitignored `.env`. Current inspect backend observed as **Zen** `laguna-s-2.1-free` with Zen fallbacks only. OpenRouter must **not** receive `hy3-free` / `laguna-s-2.1-free` / `big-pickle` (`inspect_http._candidate_models`).
- `aws sts` was NoCredentials. AgentCore is optional strengthening, not a substitute for the product. `deploy/agentcore/README.md`.
- builder.aws.com posts: drafts in `docs/posts/` with **Agents for Humans** in titles. **0/3 published.** Do not publish empty journey posts.
- Devpost: registered; Create/Submit recaptcha-gated. Copy: `docs/SUBMISSION.md`. `docs/HACKATHON_TRACK.md`.

User-gated items (login, recording, captcha, publishing) are **last**. They are not an excuse to stop building.

---

## 10. Historical suggested work order — superseded by the 30 Aug checkpoint

1. **Do not perform the historical restart instruction.** The current rule is to leave
   the occupied `127.0.0.1:7420` process untouched until the operator explicitly
   coordinates a replacement. Re-run local isolated tests without binding that port.
2. **Live Codex** only with `PEX_LIVE_CODEX=1`: isolated App Server, goal on the thread not `codex:desktop`, recovery Tests 1–2, `used_llm=true`, same `threadId`.
3. **Live Cursor→Codex handoff** on conversation + isolated thread, same project/goal; never `*:desktop`. Keep this editor on observe; no control hooks here.
4. Uncertain / gather-evidence (recovery Test 4) and **measure** Test 5 false positives on live sessions.
5. Packaged Tauri visual QA; track Von spritesheet on a clean clone.
6. Clean four-arm or stay unfrozen. Never fake lift. Never freeze while observe ≠ stop treatment.
7. Remaining harness depth without fake Deep. AgentCore after `aws login`. Builder posts after real lessons. Devpost Submit **last**, only after operator authorization.

---

## 11. Verdict (do not argue with this)

| Question | Answer |
| --- | --- |
| Is the agent complete? | **No.** |
| Is app UI/UX spec-perfect? | **No.** |
| Submittable as a winning Professional Agents entry? | **No.** |
| Three spec files cleared? | **No.** |
| Honestly benchmarked with citeable impact? | **No.** Manifest is **`frozen: false`**. Do not put a coverage merge or leaked 1/5 vs 4/5 on Devpost. |
| Should you tell the user to login and Submit? | **No.** |

Build PEX. Then submit PEX. Not the other way around.

---

## 30 Aug 2026 continuation — atomic MCP proof, exact-eight pet reseal, and newly confirmed P0s

This section is the newest operational checkpoint and supersedes any older line that
recommends `pex-bridge --no-auth`, treats an inserted event row as completed
processing, or treats the pre-repair pet release hashes as current.

### Goal, specs, rubric, and authority state

- The persistent Codex goal remains **active**: audit every prior-agent change against
  this file and all three binding specs, repair or replace incorrect work, build the
  real product, and verify it end to end strongly enough to maximize the chance of
  winning. Do **not** mark it complete.
- The parent reread `PEX_CORE_SPEC.md`, `PEX_BUILD_SPEC.md`, and
  `PEX_IMPLEMENTATION_RECOVERY_SPEC.md` and is continuing in their causal order.
- There is no public Devpost leaderboard. Use the official judging order as the bar:
  Technical Implementation first/tie-break, then Design, Impact, Creativity, and
  Presentation; builder.aws can add up to 0.6. This does not authorize submission.
- Overall status remains **NO-GO**. No stage, commit, push, deploy, publish, AWS spend,
  benchmark freeze, or Devpost submission was performed or authorized.
- The existing process on `127.0.0.1:7420` was inspected read-only and was not
  restarted, killed, duplicated, or mutated.

### Parallel workstreams used in this continuation

The parent used bounded subagents and independently reviewed/integrated their work:

1. `mcp_verify_atomic_fix_20260830`: implemented typed atomic claim verification; the
   parent found and fixed two additional flaws (legacy replay semantics and circular
   PEX-receipt-as-proof), then added durable workspace snapshot provenance.
2. `eight_pet_postrepair_visual_qa_20260830`: isolated reviewer; inspected only the
   eight post-repair runtime contact sheets, attested isolation, and returned PASS for
   all eight. It did not inspect source code or prior verdicts and made no edits.
3. `bridge_security_spec_audit_20260830`: read-only security/spec audit. It confirmed
   the live no-auth process, operator-bearer exposure to worker hooks, post-event-commit
   loss, pre-receipt external side effects, paid hatch replay, missing event reconnect,
   missing rate limits, and partial goal/ledger transactions. It is now implementing
   the P0 auth repair without touching the live process.
4. `event_ingest_replay_design_20260830`: read-only crash/replay design. It specified
   the required transactional inbox, persisted plan, per-effect pre-I/O reservations,
   honest `delivery_uncertain`, restart recovery, migration, and chaos matrix. It is
   now auditing package/clean-clone/benchmark readiness read-only.
5. `mcp_decision_atomic_fix_20260830`: currently converging typed, principal-bound,
   caller-idempotent `pex.request_decision` plus canonical durable resolution. Do not
   edit its Store/pipeline/decision regions concurrently until its handoff arrives.

### `pex.verify_claim` — parent-reviewed current contract

Current code paths:

- `packages/protocol/src/pex_protocol/context.py` defines frozen, extra-forbid
  `ClaimVerificationRequest` with a caller-supplied 8–128 character idempotency key and
  a 1–4000 character claim.
- `services/bridge/src/pex_bridge/mcp_server.py` accepts **only** the typed `request`.
  The temporary scalar compatibility shim was removed. Its deterministic implicit key
  would have replayed an earlier uncertain receipt forever after new evidence arrived;
  callers must own the retry key.
- `Pipeline.verify_reported_claim` revalidates the authenticated session principal
  against the live session, goal, project, harness, vendor session, scope, expiry, and
  supersession state; redacts the claim; reads only events with that exact binding;
  invokes existing claim extraction/verification; and delegates one atomic commit.
- `Store.commit_claim_verification` uses `BEGIN IMMEDIATE` and atomically persists the
  trigger event, raw claim contexts, bounded result contexts, ANNOTATE intervention,
  immutable audit revision, and MCP replay receipt. Same principal/tool/key/content
  replays the stored response; changed content conflicts; a final live binding change,
  evidence rebind, ID collision, or transaction failure rolls back.
- A PEX-authored verification receipt is now explicitly `verified: false`; it is an
  audit receipt, not independent evidence. Only supported TEST or WORKSPACE result
  items may be returned in `verified_items`. This closes the circular proof defect
  where the receipt itself could satisfy the supported invariant.
- Verified TEST context must have exactly the trigger plus one bound, passing,
  full-suite pytest event. Existing verification logic already downgrades after later
  file edits and rejects partial-suite invocations as proof of “all tests pass.”
- Verified WORKSPACE context must reference a durable trigger-bound workspace snapshot
  receipt containing a redacted snapshot SHA-256 and the exact evidence facts used.
  Missing, unused, malformed, or noncanonical snapshot provenance is rejected.
- Contradicted and uncertain results are durable and auditable but never mint verified
  reusable context. Old-goal pytest events cannot launder a new-goal claim.

Current focused proof after the parent fixes:

```text
uv run ruff check <verify/MCP files>                         -> green
uv run pytest -q tests/unit/test_verify.py \
  tests/unit/test_claim_verification_protocol.py \
  tests/unit/test_store_mcp_verify_claim.py \
  tests/e2e/test_mcp_verify_claim_atomic.py                  -> 53 passed
```

The full MCP regression must be rerun after the concurrently edited human-decision
schema finishes; an intermediate combined run failed only because old scalar decision
test calls raced the newly landed typed schema. Do not record that transient partial
tree as a product failure or a green suite.

### Exact-eight pet runtime contract — repaired and hash-resealed

Authoritative roster and order remain exactly:

```text
pex, ledger, mesh, nudge, drift, quiet, ember, von
```

The parent fully read the `hatch-pet` skill and its animation-row reference. That skill
contained an internal contradiction: prose and the installed Codex runtime require six
idle frames and transparent unused tails, while its assembler invented an extra neutral
idle frame at row 0 column 6. The installed Codex renderer and PEX desktop renderer both
address `[6,8,8,4,5,8,6,6,6,8,8]`; pointer dead-zone falls back to idle and never
addresses row 0 column 6. Product code now follows the actual runtime contract.

Repairs:

- `services/bridge/src/pex_bridge/pets/__init__.py` validates every required frame as
  nonempty and **every** unaddressed tail cell as fully transparent.
- `services/bridge/src/pex_bridge/pets/atlas.py` renders only the runtime-required cells
  and validates cached atlases with the same strict production validator.
- `tests/unit/test_fleet_pets_codex.py` explicitly rejects pixels in `idle[6]`.
- `scripts/pet_atlas_runtime_contract.py` provides deterministic audit/repair,
  lossless WebP output, decoded runtime-pixel before/after hashing, unused-cell checks,
  path-safe JSON, and correct runtime contact sheets.
- Before changing the eight atlases, recoverable copies were placed at
  `C:\Users\JosephMayo\AppData\Local\Temp\pex-pet-atlas-backup-20260830`.
  The script cleared only unaddressed cells; all 73 runtime-used cells per pet are
  decoded-RGBA byte-identical before/after.

Current exact asset hashes:

| Pet | shipped WebP SHA-256 | decoded runtime-pixel SHA-256 |
| --- | --- | --- |
| pex | `3c251995d1641ad70354861507311cf4c0530732f979389a981d0345064fd0e5` | `d62e37ae0aebb8d32c9efe15c1bd0b426f6bfe313a0473896df56b71000cedad` |
| ledger | `f2a2cd6ec27411169180f9705d314005529d7a717cce229e338ca4ddea0b86d2` | `6f5afe6aa7d63b6df3899612dc291dbcdb9a7c48ef7c64990f110041c6741cf5` |
| mesh | `93484a5430e21507de62d12ae3a1c088660b6aa3a16cb30742f4aa1d359120a6` | `75910d17fce58d331cbe0ab4f2904c4d549826d5362f84927da75f7d49084158` |
| nudge | `a61e99d6f5a1787c487bbf3a937711b6af2b7a6e67a8544ff463795e4fc03f92` | `b4308659978d07530cfbbe275a50e650742cad6c4167423dc4793100d4c27c68` |
| drift | `b6526b575d094a43537cb5500a4c3bcdee9b88b53792a992a4b583bf7914d701` | `68c44c5b4130111a24e1885218d377de2bad31ee2bb9150e2fb96c4f2352c032` |
| quiet | `c32646c1e374f8bc1e48722b30f13355263e08d52b3450e658153d871e8529ba` | `28d0b05d31998a9a54ae06be1f94ba5043658ab2a0163a99fe38b540b23b03ce` |
| ember | `de1cd3a83940ac5ad1bce2b8bdc3a5c28eebef0c590c69d4663afc07b6c589e7` | `7daed311968c19f19e47f6b741562482403e7a3f870f50e4e68ca460e4cfd726` |
| von | `92963736e5bb32a54e498dac9f887b04f0ebb8ef4fcc369272e08ed879b3aeee` | `f323e7d9b3170a6391b55c355feabc7a25fce411deb0d982b97b87668a8da2d2` |

Hash-bound evidence is under
`apps/desktop/src/pets/_audit/release/`:

- `evidence/runtime-contract-repair-20260830.json` proves the targeted repair and
  identical runtime pixels.
- `evidence/runtime-contract-validation-20260830.json` proves all eight current assets
  have 73 populated runtime cells, 15 transparent unused cells, and no remaining
  occupied tail.
- `runtime-contract-contact/{pet}-runtime-contract.png` labels every used/unused cell.
- `{pet}-structural-runtime-20260830.json`, `{pet}-final-postrepair-20260830.json`, and
  `{pet}-promotion-runtime-20260830.json` bind exact structural, isolated visual, and
  import evidence to the new asset hash.
- The isolated reviewer passed all eight with no warning/failure; it explicitly noted
  that cadence was inferred from ordered static frames, not a live animation capture.
- Previous three-reviewer blind direction verdicts remain applicable only through the
  mathematically sealed decoded-runtime-pixel continuity. The new exact-full-asset
  final review covers the changed transparent tail. Do not overclaim stronger old
  reviewer provenance than the files actually contain.
- All eight pass `import_codex_pet` as `import:{id}`, sprite version 2, and resolve from
  the bundled catalog.
- `release-manifest.json`, `_audit/release/{pet}.json`, and
  `_audit/release/manifest.json` were resealed to the new hashes.
- `apps/desktop/scripts/build-sidecar.mjs` now validates internal structural contract,
  common repair/validation reports, exact contact-sheet hashes, reviewer isolation,
  decoded-pixel continuity, promotion/import evidence, and the exact ordered fleet.
  `npm run validate:pets` performs this gate without rebuilding PyInstaller helpers.

Current pet/desktop proof:

```text
npm run validate:pets                                      -> ok, exact ordered 8
uv run pytest -q tests/unit/test_fleet_pets_codex.py \
  -k "all_eight_shipped_starter_atlases or import_codex_pet \
      or cached_atlas or atlas_renders"                    -> 10 passed
npm test                                                    -> 35 passed
npm run build                                               -> TypeScript + Vite green
```

Remaining pet/package truth boundary:

- The release manifest, receipts, evidence tree, build-sidecar script, Von atlas, and
  other release inputs are still untracked in this intentionally dirty worktree.
  Therefore a clean clone is **not yet proven** and packaging remains NO-GO until the
  operator later authorizes a normal commit workflow and a clean-clone build is run.
- Source/contact-sheet QA is not packaged Tauri always-on-top animation QA. A packaged
  runtime capture/inspection is still required.
- A full PyInstaller sidecar rebuild and frozen bundle smoke are still required after
  the concurrent security/decision source changes settle.

### Newly confirmed P0: release authentication and worker/operator separation

The live companion is actually unauthenticated: read-only probes returned `200` from
`/health/live` and `/health` without Authorization, while `/health/identity` returned
`503`. Source and docs exposed `--no-auth`. In authenticated mode, Cursor/generic/Hermes/
OpenCode hook helpers deliberately read the same global `bridge.token` that authorizes
the entire operator REST plane. A compromised same-user worker/plugin can therefore
invoke operator mutations or spoof sibling hook traffic. CORS does not prevent simple
cross-origin POST side effects.

Required repair now in progress:

1. Remove release/demo `--no-auth`; keep any auth-disabled path test-only.
2. In packaged Tauri, generate/retain the operator secret in the Rust broker, pass it
   only to the owned sidecar, and return it only through trusted Tauri IPC. Never spawn
   a second bridge when port 7420 is occupied by an identity that cannot be proven.
3. Stop worker integrations from reading the operator bearer. Give them distinct,
   expiring, stored-digest hook-ingest credentials with exact route/harness/session/
   vendor/project binding wherever the integration supplies those identities.
4. Prove a hook credential cannot call goals, messages, handoff, hatch, MCP credential
   issuance, or operator MCP; prove cross-session/project spoofing fails.
5. Add mutation Origin/CSRF and Host checks appropriate to the loopback threat model.
6. Do not claim cryptographic isolation from an unrestricted same-user OS process; the
   honest invariant is least-privilege worker credentials and no deliberate operator
   secret exposure in worker files/config/environment.

The existing live process was **not** restarted to apply this work. After the source is
green, a restart still needs explicit operator coordination because another bridge must
never be spawned on the occupied port.

### Newly confirmed P0: event insertion is not event completion

`Pipeline._ingest_event_locked` currently commits the event first, then separately
updates the session, prior intervention, contexts, bus, health, verification, supervisor,
external action, and main intervention. A crash/cancellation/listener exception after
the first commit causes a retry with the same event ID to return early forever. The
event row exists while the required state transition/action is silently lost.

The accepted repair design is a transactional inbox plus per-effect durable saga:

- atomically insert the event and `event_processing(accepted)` row;
- exact duplicates resume unfinished processing or return the stored terminal receipt;
- collision content still fails;
- process per-session acceptance order and prevent a replayed older event from seeing
  later accepted history;
- persist the exact redacted supervisor plan and local projections before dispatch;
- reserve every main action, remote-attention effect, and auto-handoff under a stable
  event-derived key before external I/O;
- revalidate current goal/project/session/pause/supersession immediately before I/O;
- finalize delivered/failed/uncertain atomically with intervention/audit state;
- never blindly resend stale `dispatching`; reconcile by downstream operation ID when
  supported, otherwise persist terminal `delivery_uncertain`;
- recover unfinished nonlegacy rows at startup before pumps; backfill old events as
  `legacy_complete` without pretending old partial processing can be reconstructed;
- move WebSocket publication to a durable/bounded outbox so a socket cannot control
  ingestion completion.

This repair is designed but not yet implemented. Do not apply the tempting incorrect
fixes of moving `add_event` to the end, holding SQLite open across remote I/O, adding
only a Boolean processed flag, or blindly retrying an accepted external action.

### Other confirmed high-priority gaps after the two P0s

1. Generic actions, REST message, REST/automatic handoff, and overlays can perform
   external I/O before a durable receipt; unify them under pre-I/O reservations and
   honest uncertain outcomes.
2. Paid pet hatch POST has no caller idempotency/charge authorization key. One hatch can
   make 13 provider calls. Persist request fingerprint/job before work and replay the
   same job; interrupted remaining charges need new explicit authorization.
3. No queryable/paginated event API or WebSocket resume cursor exists; adapter retention
   gaps can permanently omit events. Add stable event sequence, keyset query, WS `after`,
   explicit gaps, persisted cursors, and authoritative resync/degraded state.
4. No control-plane rate limit; sockets/concurrent buffering/backpressure are unbounded.
   Add route-cost token buckets, connection caps, read/idle timeouts, bounded per-socket
   queues, and decouple broadcast from ingestion.
5. Goal + extracted decision/context, successor + credential revocation, and ledger writes
   are not one transaction and lack API request replay keys.
6. Active overlays can disappear behind a global 1000-row pre-filter; decisions and
   overlays return silent truncation without pagination metadata.
7. Universal case-folding merges distinct paths on case-sensitive systems. Project
   identity must be platform-aware.
8. Windows token DACL ownership is not actually verified; Unix-only mode tests do not
   prove Windows ACL safety.

### Exact next execution order from this checkpoint

1. Let the atomic human-decision agent finish and parent-review every changed line; run
   its protocol/unit/fault/E2E suite plus the official MCP lifecycle/auth regressions.
2. Finish and parent-review the P0 auth implementation; run Python, integration-helper,
   Rust, packaged-sidecar, browser-origin, and privilege-escalation tests. Do not touch
   the live 7420 process.
3. Implement the transactional event inbox/effect reservations and chaos/restart matrix.
4. Extend the reservation/idempotency pattern to direct message, REST/automatic handoff,
   overlays, and paid hatch.
5. Add queryable/resumable events, backpressure/rate control, and atomic goal ledger.
6. Run the widest local Python suite, Ruff, desktop tests/build, Rust tests, sidecar
   build/frozen bundle smoke, then a clean-clone gate once tracking/commit is authorized.
7. Only after those local gates: operator-authorized live Codex/Cursor proof, packaged
   visual/runtime proof, honest four-arm freeze, optional AWS, demo recording, posts,
   and Devpost submission. Manifest remains `frozen: false` throughout this work.

If quota or host transfer forces another handoff before these converge, append exact
commands/results/current agents/unverified assumptions here first and leave the
persistent goal active.

---

## 30 Aug 2026 03:14 WAT — authoritative continuation checkpoint; still NO-GO

This section supersedes the earlier 30 Aug statements that authentication and generic
human decisions were still in progress. It does not erase the historical evidence or
the unresolved live/package gates above.

### Goal, leaderboard/rubric, authority, and live-state boundary

- The persistent Codex goal remains **active**: audit every prior-agent code change
  against `_HANDOFF.md` and all three specs, replace incorrect work, build the correct
  implementation, and verify it end to end to maximize the hackathon result. Do not
  mark the goal complete while live recovery, packaging, and release gates remain.
- Official Devpost state was rechecked on 30 Aug: there is a project gallery but no
  public scored leaderboard. Use the actual judging order as the bar:
  **Technical Implementation first and as the tie-break**, then Design, Potential
  Impact, Creativity/Originality, and Presentation. Builder.aws may add up to `+0.6`
  in Stage Two. Do not invent a competitor score.
- Exactly eight shipped pets, in this order:
  `pex, ledger, mesh, nudge, drift, quiet, ember, von`.
- Do **not** submit, deploy, publish, spend, stage, commit, discard the dirty tree, or
  invoke paid/cloud resources without fresh action-time operator authorization.
- The pre-existing process on `127.0.0.1:7420` was not restarted, killed, duplicated,
  or mutated. Never start a second bridge on that occupied port. Source repairs below
  are not proof that the already-running process loaded them.
- `benchmarks/manifest.yaml` remains `frozen: false`. No live four-arm, AgentCore,
  provider-image, Devpost, or submission action was taken.

### Current broad green baseline and exact truth boundary

Before transactional event edits began:

```text
uv run pytest -q                                             -> 1158 passed, 19 skipped
```

That is the strongest current full Python baseline. It was run after the auth/decision
work and before the event-processing schema landed. Re-run the full suite after event
and hatch work converge; do not present `1158/19` as post-event proof.

Other current focused proof:

```text
Auth/config/Host/Cursor post-change matrix                    -> 82 passed, 2 skipped
Auth + MCP + decision parent reproduction                    -> 136 passed, 2 skipped
Generic decision focused backend                             -> 89 passed
Desktop npm test                                             -> 38 passed
Desktop npx tsc --noEmit                                     -> green
verify_claim protocol/Store/MCP                              -> 53 passed
Benchmark public/integrity suite                             -> 112 passed
Handoff timeout safety                                       -> 32 passed
Pet runtime/import/cached-atlas focus                        -> 10 passed
npm run validate:pets                                       -> exact ordered 8, green
Strands supervisor/evidence/verifier/runtime focus           -> 43 passed
Ruff on that Strands slice                                   -> green
Hatch image-provider security + existing hatch tests         -> 74 passed
Ruff on hatch provider slice                                 -> green
Event-processing Store checkpoint                            -> 22 passed
Ruff on event-processing Store checkpoint                   -> green
```

Desktop `npm run build` was green before the latest backend-only edits. Rust auth had
eight passing tests earlier. A fresh Vite/Tauri/PyInstaller/frozen-bundle/installer
matrix is still required after source convergence.

### Release authentication and worker/operator separation — source P0 repaired

The source contract now fails closed:

- Release CLI rejects `--no-auth`; `PEX_REQUIRE_AUTH=false` and ordinary
  `Settings(require_auth=False)` reject. Only explicit process-local
  `Settings.for_test(require_auth=False, ...)` can disable auth in tests.
- Operator tokens are `repr=False`, copied into AppState, then cleared from Settings.
  Token environment is scrubbed case-insensitively before child spawn.
- Tauri creates a 384-bit operator token in Rust memory and passes it only to its owned
  sidecar. Nonce-HMAC identity proof and occupied-port refusal prevent accidentally
  trusting or spawning over another bridge.
- The lifespan preserves/revalidates the Tauri-supplied token; it no longer overwrites
  it with a stale fallback token. A real lifespan test proves the Tauri token reaches
  `/health/identity` and bearer auth while the stale fallback is rejected.
- Strict loopback Host validation covers HTTP and WebSocket. Missing, duplicate,
  malformed, or non-loopback Host is rejected; IPv4, `localhost`, and `[::1]` are the
  accepted forms. Mutation Origin protection remains active.
- Worker integrations no longer read the operator bearer. Digest-only, expiring,
  revocable hook credentials are bound to exact route/harness/project/session/vendor
  identity. OpenCode binding permits only its heartbeat mutation; overlay GET is
  read-only. Hook tokens cannot call the operator plane.
- Tauri CSP/navigation guards and Cursor private-token length/printability bounds are
  tested. README quick start is authenticated Tauri only.

Known auth boundary: a same-user unrestricted OS process is not cryptographically
isolated; the honest guarantee is least privilege and no deliberate operator-secret
exposure. Windows fallback token-file DACL ownership still needs native verification.
The live 7420 process was not restarted, so its previously observed unauthenticated
runtime remains a live-state NO-GO until explicit operator coordination.

### Generic human decision — source P0 repaired

- Frozen/extra-forbid `HumanDecisionRequest` has bounded text, caller idempotency,
  stable logical identity across credential rotation, bounded options, and
  NFKC/casefold collision rejection.
- Request commit is atomic with pending/lifetime session quotas. REST is operator-only;
  a hook credential is denied.
- Delivery performs a bounded capability probe, exactly one adapter send, and treats
  only `accepted is True` as delivered. False is rejected; timeout, exception,
  cancellation during send, or non-Boolean results are honestly uncertain.
- The raw freeform answer exists only for the ephemeral adapter call. Durable state and
  UI feedback contain `[freeform answer sha256:<digest>]` / `[answer submitted]`, never
  the raw answer. DB-wide tests cover this.
- Delivery is reserved and CAS-marked `dispatching` before I/O. Prior-process
  dispatching becomes `delivery_uncertain` with zero resend. Cancellation finalization
  preserves the original cancellation rather than replacing it with a cleanup error.
- Concurrent attention rows preserve every decision id and newer external state.
  Unsupported/rejected/failed/uncertain decisions remain `NEEDS_DECISION`.
- The old dirty-tree-only `Store.resolve_requested_human_decision` path that wrote raw
  choices was removed. `git show HEAD`, git history, and a strict read-only check of the
  operator DB showed the legacy table/path was never shipped there, so no speculative
  destructive migration was added.

Known follow-on: Store is authoritative if commit succeeds but bus publication is
cancelled; there is not yet a durable WebSocket outbox. The transactional event/outbox
work below must close that without weakening the decision contract.

### Hatch image-provider trust boundary — repaired and parent-reviewed

`services/bridge/src/pex_bridge/pets/imagegen.py` now enforces:

- `OPENAI_API_KEY` inheritance only for exact `https://api.openai.com/v1`.
- Every explicit `PEX_HATCH_BASE_URL`, even canonical OpenAI, requires an explicit
  `PEX_HATCH_API_KEY`.
- A supervisor base-URL override cannot retarget an inherited OpenAI key.
- Arbitrary remote endpoints require validated HTTPS; cleartext is limited to literal
  `127.0.0.1` or `::1`.
- Userinfo, query/fragment, percent/backslash paths, dot/double-slash paths, embedded
  image endpoints, ambiguous IP spellings, malformed/default ports, redirects, and
  result-URL downloads fail closed.
- Config/public/error representations omit or redact secrets; raw provider bodies and
  exception causes are not persisted or surfaced. Response/base64/prompt/size bounds
  are enforced before large work.
- Parent review caught and fixed a confused-deputy edge: explicitly supplied empty
  config no longer falls back to ambient credentials. The combined proof is now
  **74 passed**, not the agent's earlier 73.

No provider/network call was made. The paid hatch workflow itself remains blocked until
the durable receipt work below lands.

### Transactional event ingestion — Store checkpoint landed; end to end still active

Current Store-only state:

- `event_processing` has AUTOINCREMENT acceptance order, one row per event, exact
  session/harness/goal/project binding, pipeline/legacy/record-only mode, semantic
  hash, explicit processing/uncertain/terminal states, revision/attempt/lease,
  plan/receipt slots, and recovery indexes.
- `event_effects` has stable effect identity, unique event/effect key, ordinal/kind/
  target/request hash/payload, reserved → dispatching → terminal state, CAS version,
  dispatcher boot id, result, timestamps, and downstream operation id.
- An AFTER INSERT trigger gives every direct event writer a terminal
  `record_only_complete` row. Migration backfills preexisting rows as
  `legacy_complete`; neither is replayed as if the old pipeline had completed.
- `accept_pipeline_event` performs event insert + trigger-row upgrade atomically.
  Exact replay returns the first canonical event/acceptance sequence. Only the
  top-level synthesized timestamp is nonsemantic; message, tool, files, goal, project,
  metadata, and nested vendor timestamp changes collide.
- Per-session smallest nonterminal acceptance sequence blocks overtaking. Unrelated
  sessions claim independently. `recent_events_through` freezes the acceptance prefix
  rather than ordering by vendor time.
- External effects reserve before I/O; prior-boot dispatching becomes uncertain and is
  never automatically resent. A planner dispatch without a durable result becomes
  `plan_generation_uncertain`, which blocks later same-session work.

Parent review then closed every known Store-boundary issue before Pipeline integration:
canonical tuple effect IDs; uncertain-event claim behavior; lease/state validation;
downstream-operation replay; same-owner claims; terminal planner receipts; exact
projection replay; session/goal/project/action/capability binding; immutable proposal
updates; preservation of newer concurrent session state; safe failure before dispatch;
planner-only generic effect APIs; an exact versioned plan envelope; unexpired plan
leases; and main-effect ID/ordinal/hash revalidation. The independently reproduced
checkpoint is now **22 passed** with Ruff green. `app.py`/lifespan remains deliberately
paused while Pipeline integration proceeds.

End-to-end claims are still forbidden until Pipeline uses atomic acceptance, persists
plan/local projections before I/O, derives stable artifact ids, reserves the main
effect, revalidates pause/detach/terminal/goal/project/supersession immediately before
dispatch, stores one terminal receipt, recovers before pumps, and disables/defer
automatic handoff until multi-effect recovery exists. Manual MCP handoff must remain.

### Paid hatch durability — active isolated implementation

The previous path is release-blocking:

- concurrent calls could make 26 provider requests for one logical job;
- cancelling the asyncio wrapper did not stop its thread from completing all 13 calls;
- a second Registry could mark an active job interrupted and admit another paid job;
- POST had no caller idempotency key or exact provider/request/expiry authorization;
- no per-call reservation/receipt/reconciliation existed;
- text-only independent row prompts could not preserve canonical identity and violated
  the hatch-pet staged/reference/QA contract.

The isolated hatch agent owns only `pets/hatch.py`, a dedicated `hatch_store.py`, and
hatch tests. Its first checkpoint replaced the unsafe 13-row path with exactly **one**
explicitly authorized base-candidate generation, a separate SQLite reservation/effect
ledger, global dispatch serialization, deadline-based no-resend recovery, exact
duplicate-risk acknowledgement, and zero-call legacy import. The result stays
unverified and `awaiting_assembly_qa`; it is never called a playable pet. The first
focused checkpoint was **42 passed** with Ruff green and made no provider call.

Parent hatch-pet review has not accepted that checkpoint yet. Required fixes now active:

- local reconciliation/final delivery must require a strict candidate receipt bound to
  current job/effect/request/provider/generate fingerprint/path/hash/size; a PNG alone
  is not provenance and a crash before receipt must remain uncertain;
- every candidate/reference/receipt write and legacy read must reject symlink/junction
  parent escape from the hatch root;
- a fresh server timestamp on an otherwise identical principal/idempotency replay must
  return the first canonical job, not conflict;
- wrong dispatch tokens/CAS loss must not silently look successful;
- authorization issue/expiry skew and maximum lifetime need a bounded contract.

`app.py` and desktop integration remain blocked until those core fixes are independently
reproduced.

### Realtime event query/WebSocket audit — complete, implementation still P0

The read-only audit made no edits/server/network calls and reproduced two failures:
ordinary `EventBus.publish()` propagates a listener exception, and vendor-timestamp
`recent/latest` order diverges from durable acceptance order. Current `/v1/events` is
live-only; there is no GET timeline, cursor, resume, retention/gap receipt, connection
cap, bounded per-socket queue, or desktop event timeline. Direct record-only MCP events
also have durable acceptance rows but are not live-published.

The accepted smallest design uses decimal-string `event_processing.accept_seq` cursors,
an `AFTER INSERT ON event_processing` payloadless publication ledger (so pipeline,
record-only, and legacy rows are all covered), frozen `through` keyset pages, GET and WS
on `/v1/events`, explicit retention/gap receipts, DB-tailing sockets with a hard cap and
bounded queues, and no ingestion await on presentation. Canonical event readers must
join processing and order by `accept_seq`, never vendor time. Durable adapter observation
gaps are a later typed normalized receipt and must block false completion until resync.
Do not mistake `publish_committed` for a durable outbox.

### AgentCore timeout/hybrid ambiguity — isolated source repair active

`AgentCoreSupervisorClient.decide()` currently times out an `asyncio.to_thread` SDK
call that may continue, while `SupervisorRouter` hybrid can start a second local
semantic call. The isolated repair is adding a bounded secret-safe
`AgentCoreDeliveryUncertainError`, re-raising cancellation, treating every failure after
the SDK invocation boundary conservatively as uncertain, and allowlisting hybrid
semantic fallback only for proven pre-dispatch configuration failures. Pipeline must
persist this as planner uncertainty and use explicit deterministic reconciliation;
it may never automatically make a second model call.

The `hatch-pet` skill materially changed this design: source/reference continuity and
independent animation QA matter more than the superficial count of generated strips.

### Systemic project identity — P0 design complete; implementation waits for Store

Universal `strip → backslash-to-slash → rstrip → casefold` is copied through protocol,
Store/SQL/fingerprints, Pipeline, MCP, routes, executor, decisions, mesh, AgentCore,
supervisor runtime, and adapters. It incorrectly merges, among other pairs:

```text
POSIX /tmp/a\b  with /tmp/a/b
POSIX /tmp/Foo with /tmp/foo
POSIX /tmp/a␠  with /tmp/a
POSIX /tmp/ß   with /tmp/ss
Windows C:\    with drive-relative C:
```

It also misses real aliases involving dot segments, relative bases, symlinks/junctions,
UNC/device/8.3 paths, and multi-root workspaces. A one-helper replacement is **NO-GO**.
The approved direction is typed/versioned locators (`local_path`, `remote_path`,
provider workspace, repository URI, workspace set, opaque), origin namespace/host,
platform-aware lexical rules, optional physical identity proof, stable random identity
ids, raw display retention, additive tables/columns, dual write, conflict quarantine,
credential revocation/reissue for ambiguity, and versioned receipt compatibility. No
legacy receipt may be recomputed or rewritten. The smallest safe implementation slice
starts only after transactional event Store changes stabilize.

### Additional parent code-review disposition

The removed `services/supervisor/src/pex_supervisor/graphs.py`, old ContextVar action
`tools.py`, their obsolete test, and the superseded supervisor Dockerfile should not be
restored merely to claim Strands Graph. The shipped replacement is a real bounded
request-scoped evidence-tool supervisor plus a fresh verifier; side-effect/web tools
and Graph are not falsely claimed. Parent proof:

```text
uv run pytest -q tests/unit/test_supervisor_loop.py \
  tests/unit/test_strands_runtime.py tests/unit/test_evidence_tools.py \
  tests/unit/test_ask_review.py                                  -> 43 passed
uv run ruff check <same implementation/test slice>             -> green
```

`docker-compose.yml` now points at the hardened `deploy/agentcore/Dockerfile`; the
deleted older Dockerfile is not referenced. This is local code evidence, not a built
ARM64 image or deployed AgentCore Runtime.

### AgentCore post-dispatch uncertainty — parent-accepted core, Pipeline integration open

`services/bridge/src/pex_bridge/agentcore.py` now makes the semantic dispatch boundary
explicit. Local request serialization/validation and SDK-client construction are
pre-dispatch. Once `invoke_agent_runtime` begins, timeout, transport failure, response
protocol/binding failure, and unexpected failure raise the closed-field
`AgentCoreDeliveryUncertainError`; it retains only a validated stable
`pexinv_<32-hex>` invocation id and one of four bounded reason codes. Provider exception
text/body is not retained. Raw `asyncio.CancelledError` propagates unchanged because the
SDK thread may still finish after caller cancellation. SDK retry total remains one, and
a late thread result after timeout is ignored rather than launching a second semantic
backend. Hybrid local semantic fallback is allowlisted only for proven Runtime
configuration failure; definite request-side protocol failure remains deterministic
and fail-closed, while ambiguous transport/client failures never fall back.

Parent line review and independent proof on 30 Aug 2026:

```text
uv run pytest -q tests/unit/test_agentcore_client.py \
  tests/unit/test_agentcore_runtime.py                         -> 57 passed
uv run pytest -q tests/unit/test_agentcore_client.py \
  tests/unit/test_agentcore_runtime.py \
  tests/unit/test_agentcore_preflight.py \
  tests/unit/test_strands_runtime.py \
  tests/integration/test_strands_supervisor.py                 -> 85 passed
uv run ruff check services/bridge/src/pex_bridge/agentcore.py \
  tests/unit/test_agentcore_client.py \
  tests/unit/test_agentcore_runtime.py                         -> green
uv run python -m py_compile services/bridge/src/pex_bridge/agentcore.py -> green
```

This is not yet an end-to-end recovery claim. The transactional Pipeline must catch
the typed uncertainty, persist `plan_generation_uncertain` with only the reason code
and transport invocation id, never retry that semantic request, and turn cancellation
after its durable dispatch marker into an equally non-retryable reconciliation state.
No AWS call, image build, deploy, spend, or live-port action occurred.

### Active parallel work at this exact checkpoint

1. `event_ingest_replay_design_20260830` — Store is parent-accepted at 22 focused
   tests; atomic Pipeline integration is active; `app.py` remains paused.
2. `hatch_durable_effect_store_20260830` — isolated one-call hatch SQLite saga is at a
   42-test first checkpoint and is fixing parent-found provenance/filesystem/idempotency
   gaps; no app/imagegen/shared-Store edits and no provider calls.
3. `agentcore_uncertain_timeout_20260830` — AgentCore uncertainty core is parent-accepted
   and the same agent is now implementing only a pure typed project-identity-v2 module
   plus adversarial tests; no Store/Pipeline/app/adapter integration is authorized yet.

`realtime_event_api_audit_20260830` has finished read-only; its implementation waits for
the transactional Pipeline checkpoint to freeze.

### Exact next execution order

1. Parent-review every event Store correction and independently reproduce its tests.
2. Review atomic plan/projection/receipt APIs before allowing lifespan recovery.
3. Integrate Pipeline; run crash/cancellation/concurrency/supersession/pause chaos,
   then auth/MCP/decision overlap and the full Python suite.
4. Parent-review the one-call hatch ledger; then wire typed app/UI idempotency and exact
   charge authorization, keeping capability discovery network-free until user action.
5. Convert the realtime audit into stable acceptance cursors, keyset query, WS resume,
   explicit gaps, bounded slow-consumer behavior, and an outbox that cannot determine
   ingestion completion.
6. Implement typed project identity additively, starting with pure adversarial vectors,
   schema/dual write, and fail-closed mutation gates; no global helper swap.
7. Continue file-by-file audit: direct message/handoff/overlay reservations, atomic goal
   ledger, query pagination/truncation, rate/connection limits, Windows ACL proof, and
   adapter-specific contract review.
8. Only after source convergence: widest Python/Ruff, desktop tests/typecheck/build,
   Rust, pet validation, PyInstaller sidecar/frozen-bundle/installer smoke. Clean-clone
   proof requires an operator-authorized reviewed commit boundary.
9. Only after local gates and separate authorization: live Codex/Cursor recovery Tests
   1–5, packaged visual QA, honest four-arm freeze, optional AWS, demo/video/posts, and
   Devpost submission.

## 2026-08-30 continuation checkpoint — transactional Pipeline and hatch core accepted

This section supersedes the stale “active parallel work” and “end to end still active”
wording immediately above. There are currently **no live subagents**. The persistent
goal remains active and the release remains **NO-GO**; do not mark the goal complete.

### Transactional event processing is now integrated end to end

The bridge no longer performs semantic planning or worker-visible dispatch before an
event has a durable acceptance row. The current path is:

```text
canonical event + accepted session snapshot
  -> atomic event_processing acceptance sequence
  -> per-session ordered claim with unrelated sessions still parallel
  -> durable planner effect / exact planning snapshot
  -> atomic local projection + intervention + main-effect reservation
  -> live intent/capability revalidation
  -> dispatch marker before worker I/O
  -> one terminal effect result + one terminal event receipt
```

Material guarantees now implemented in `store.py`, `pipeline.py`, and `app.py`:

- A duplicate event returns its first canonical receipt and cannot trigger a second
  semantic plan or main worker dispatch.
- An accepted event cannot overtake an older unfinished event for the same session;
  different sessions can still progress independently.
- Planner evidence is stored as a strict `pex.event-planning-snapshot.v1` payload.
  Recovery reuses the original claims, verification, context, decisions, and
  intervention projections even if the workspace changes after the first planner
  result. It never pairs an old semantic result with newly probed evidence.
- The snapshot has exact-key validation, typed reconstruction, collection bounds, and
  a 2 MiB canonical-size ceiling at both creation and restoration.
- A crash/restart after a planner or worker dispatch marker terminalizes that effect as
  delivery uncertain. It is never converted back into a retry lease.
- Cancellation after the main dispatch marker seals a durable uncertain receipt under
  `asyncio.shield`, then re-raises the original cancellation.
- AgentCore `AgentCoreDeliveryUncertainError` is persisted as planner uncertainty and
  deterministically reconciled without a second local or remote semantic call.
- Direct AgentCore decisions still pass through deterministic truth preservation;
  remote NOOP cannot erase a locally observed acceptance gap.
- Main-effect claim revalidates the exact event/session/goal/project/action/capability
  envelope plus pause, detach, goal supersession, and verification-trigger identity.
- Startup initializes Store/auth/pets/adapters/supervisor, recovers unfinished events,
  and only then starts adapter pumps. Prior-boot dispatch markers become uncertain
  before new events are admitted.
- Startup lease release is explicit and limited to the single-writer lifespan recovery
  call. Routine recovery cannot steal another live runner's lease.
- Event/intervention/pet presentation publication is post-commit, bounded, and
  non-authoritative. A hanging/broken listener cannot delay or roll back ingestion.
- The accepted durable session snapshot is the merge baseline. A stale adapter object
  cannot erase newly negotiated capabilities, context-health state, or status.
- Evidence from an intervention created under an old goal is ignored after the vendor
  session is rebound to a replacement goal. This closes a real cross-goal satisfaction
  bug found by the full-suite audit.

Automatic cross-harness handoff is restored after the authoritative event receipt. It
now revalidates the live source and target goal/project/status/pause bindings, serializes
handoff mutation, stores a `delivering` intervention receipt before adapter I/O, and
treats delivered **or uncertain** item IDs as non-retryable. Exact Cursor-to-isolated-
Codex, isolated-Codex-to-Cursor, synthetic handoff, target-phase relevance filtering,
and verified-result promotion tests pass. Observe-only desktop inventory tiles remain
excluded.

The local human-attention inbox is also restored without blind duplicate append. Each
notice carries an exact event/intervention idempotency key; because the inbox is capped
at 1 MiB, replay scans are bounded. If the process dies after append but before the
intervention metadata update, replay finds the existing key, reports `notified:file`,
and repairs the ledger instead of writing a second notice. Worker nudges still never
fan out to the human channel.

One architectural follow-on remains: automatic handoff and remote-attention follow-up
are durable/idempotent in their own ledgers, but the event-processing row does not yet
contain a general ordered multi-effect list. A crash before entering the post-commit
follow-up can omit that follow-up until the exact event is replayed. Do not call this a
fully general transactional outbox. The realtime publication/outbox slice below should
add an explicit recoverable follow-up ledger rather than moving I/O before commit.

Current independently reproduced proof:

```text
uv run pytest -q tests/unit/test_event_processing_pipeline.py \
  tests/unit/test_event_processing_store.py \
  tests/unit/test_pipeline_serialization.py \
  tests/unit/test_pipeline_session_merge.py                       -> 44 passed

uv run pytest -q tests/unit/test_event_processing_pipeline.py \
  tests/unit/test_event_processing_store.py \
  tests/unit/test_pipeline_serialization.py \
  tests/unit/test_pipeline_session_merge.py \
  tests/unit/test_agentcore_pipeline.py \
  tests/unit/test_codex_pipeline_pump.py \
  tests/unit/test_opencode_pipeline_pump.py \
  tests/unit/test_policy_scoring.py tests/unit/test_pet_snapshot.py \
  tests/e2e/test_m0_roundtrip.py tests/e2e/test_recovery_stop_loop.py
                                                               -> 120 passed

uv run pytest --lf -q                                      -> 31 passed
uv run pytest -q                                           -> 1259 passed, 19 skipped
uv run ruff check .                                        -> All checks passed
```

The intervention audit expectation was intentionally updated: a worker-visible action
now records `delivery_reserved`, then `delivery_delivered` (or another exact terminal
state), followed by outcome observations. Reverting this to a single `created` record
would erase the crash boundary and is forbidden.

### Paid hatch core is parent-accepted; app/UI integration is still blocked

The one-call hatch saga in `pets/hatch.py` plus `pets/hatch_store.py` now passes the
parent review requirements that were still open above:

- exactly one explicitly authorized base-candidate provider call per logical job;
- first canonical job returned across a fresh authenticated timestamp replay;
- exact principal/idempotency/request/provider/generate fingerprint binding;
- bounded authorization issued-at/expiry skew and lifetime;
- strict candidate receipt bound to job/effect/request/provider/path/hash/size;
- PNG presence alone can never reconcile a missing provider receipt;
- symlink/junction containment checks on candidate, reference, receipt, and legacy
  paths;
- exact dispatch-token/CAS enforcement;
- process interruption after dispatch is uncertain and never silently retried;
- legacy import makes zero provider calls;
- output remains an **unverified canonical base candidate** in
  `awaiting_assembly_qa`, never a playable pet.

Proof, with no provider or network call:

```text
uv run pytest -q tests/unit/test_hatch_durability.py \
  tests/unit/test_pet_hatch.py tests/unit/test_hatch_imagegen_security.py
                                                               -> 95 passed
```

Do not wire the route as a paid/playable success yet. The next slice must expose typed
authorization/idempotency/uncertain receipts through the API and desktop, then perform
deterministic 8x11 v2 row assembly from the canonical source/reference and independent
visual/semantic QA under the `hatch-pet` skill. One provider candidate is not an atlas.

### AgentCore core and Pipeline integration are now accepted

The earlier AgentCore section's “Pipeline integration open” warning is obsolete. The
typed post-dispatch uncertainty is now handled by the transactional planner path, and
focused AgentCore/Pipeline/recovery coverage is included in the 120-path and full-suite
gates above. This remains local proof only: no SDK network invocation, AWS image build,
Runtime deployment, spend, or live cloud receipt occurred.

### Project identity v2 status

The earlier statement that identity v2 did not land is obsolete. The pure protocol,
additive Store schema, ambiguity quarantine, credential revocation, explicit resolution,
core mutation gates, planner/main-effect/follow-up gates, and adversarial tests are now
implemented locally. The detailed 31 Aug checkpoint at the end of this file is the
authoritative identity record. This remains an additive migration: do not replace every
legacy project helper globally, infer untyped legacy rows, or claim all downstream
mutation surfaces are already converted.

### Leaderboard and judging bar

The official Devpost pages were checked live on 30 Aug 2026. No public scored
leaderboard was available, so do not fabricate a rank. Use the official judging order
as the bar: **Technical Implementation** first and as tie-breaker, then Design, Impact,
Creativity, and Presentation; verified Builder.aws eligibility can add 0.6. Recheck the
live official contract immediately before any publication/submission because wording
can change. No post, deploy, spend, AWS action, Devpost submission, or attempt was made.

### Exact next execution order from this checkpoint

1. Finish the technical-first direct-control durability slice: caller-idempotent,
   request-hashed Store reservations for direct message and REST/MCP handoff, durable
   pre-I/O dispatch markers, exact replay/collision handling, quarantine revalidation,
   and terminal uncertainty with no resend. Apply the same pattern to overlay
   apply/revert immediately after message/handoff.
2. Finish typed-project integration at remaining mutation boundaries without a global
   helper swap: human-decision/permission/lifecycle start gates, generic context/
   decision/intervention/lifecycle writers, goal-ledger atomicity, and explicit
   operator API/UI for locator registration and conflict resolution. Preserve
   authority-reducing pause/revoke/finalization operations.
3. Wire typed paid-hatch API/desktop authorization and idempotency without making a
   provider call. Then implement deterministic atlas assembly and independent QA; keep
   exactly eight bundled pets in order: `pex, ledger, mesh, nudge, drift, quiet, ember,
   von`.
4. Continue the file-by-file security/contract audit, especially query pagination and
   bounds, Windows ACL evidence, direct handoff/overlay reservations, and every adapter
   protocol boundary.
5. Re-run full Python/Ruff after each foundational slice; then desktop unit/typecheck/
   build, Rust, pet validation, PyInstaller sidecar/frozen bundle, and installer smoke.
6. A clean-clone proof requires an operator-authorized reviewed commit boundary. Do not
   stage or commit this huge inherited dirty worktree merely to manufacture that proof.
7. Only with separate action-time authorization: live Codex/Cursor Tests 1–5, packaged
   visual QA, honest frozen four-arm benchmark, optional AWS/Builder.aws work,
   demo/video/posts, and irreversible Devpost submission.

Current release status remains **NO-GO** because durable direct-control reservations,
remaining typed-identity mutation surfaces, hatch API/assembly/QA, Rust/package gates, live harness proof,
honest frozen benchmark evidence, AWS proof, visual demo assets, and submission review
are still incomplete. The full Python gate is green, but it is not equivalent to those
external and packaged-system proofs.

### Realtime publication implementation started after the full-suite checkpoint

The first Store/HTTP slice is now landed locally:

- `event_publications` is a payloadless ledger keyed by
  `event_processing.accept_seq`, with an insert trigger and migration backfill. It
  therefore covers pipeline, record-only, and migrated legacy event rows without
  duplicating event payloads.
- `Store.event_publication_page()` uses decimal-string public cursors, exclusive
  `after`, inclusive frozen `through`, acceptance-ordered keyset reads, optional exact
  session scope, current watermark, retention bounds, explicit gap/degraded fields,
  and bounded limits.
- Retention/gap bounds are global, not scoped: a filtered session naturally has sparse
  global cursors and that sparsity must not be misreported as data loss.
- A first page freezes `through`; events accepted during later pages update the
  watermark but cannot leak into that snapshot.
- Authenticated `GET /v1/events` now exposes this canonical page. Leading-zero or
  oversized cursor syntax is rejected, as are impossible `after/through` ranges.
- Vendor timestamps intentionally reversed in tests do not affect publication order.

Current focused proof:

```text
uv run pytest -q tests/unit/test_event_publications.py \
  tests/unit/test_event_processing_store.py                    -> 25 passed
uv run pytest -q tests/unit/test_event_publications.py \
  tests/unit/test_websocket_auth.py                             -> 4 passed
uv run ruff check <Store/app/publication test slice>            -> green
```

This is not the completed realtime contract. The existing WebSocket is still
live-broadcast-only and must be replaced with DB catch-up/tailing, bounded connection
and queue behavior, heartbeat, explicit slow-consumer/shutdown closes, cursor resume,
and desktop cursor/gap persistence. Canonical `recent_events`,
`recent_events_for_binding`, and `latest_events` also still contain vendor-time query
paths and must be converted carefully to acceptance order with compatibility tests.

### Realtime event contract completed locally after that first slice

The warning immediately above is now obsolete. The existing live-only socket was
replaced with a DB-backed event stream:

- WebSocket `after` is a canonical decimal cursor; query bearer tokens remain forbidden.
- Initial catch-up and live tail both read `event_publications`, never the process-local
  event broadcast. `AppState.broadcast("event", ...)` is now explicitly only a wake
  hint and sends no event payload.
- Catch-up freezes a watermark page-by-page, is capped at 1000 events, and then moves to
  monotonic DB polling. Pages contain the same explicit cursor/watermark/retention/gap
  receipt as GET.
- Hard bounds are 16 sockets, 128 queued messages per socket, 100 events per catch-up
  page, 2 seconds per send, 250 ms DB poll, and 15 second heartbeat.
- A full queue, send timeout, excessive catch-up, or retention gap closes with 1013;
  shutdown closes sockets with 1001. A gap page is flushed under the send deadline
  before the resync close.
- Auxiliary pet/intervention messages share the bounded per-socket sender; unit fakes
  retain direct serialized sends. Slow consumers are closed and unregistered.
- Client disconnect cancellation is treated as terminal socket cleanup; no authoritative
  mutation is owned by the socket handler.
- `recent_events`, `recent_events_for_binding`, and `latest_events` now join
  `event_processing` and order by `accept_seq`, not vendor timestamps.
- The desktop persists `pex.event_cursor.v1`, sends it on reconnect, validates all
  cursor syntax, advances only from an `event_page` receipt, and computes
  `earliest_available - 1` with exact `BigInt` arithmetic on a retention gap. Disabled
  localStorage degrades to explicit cursor zero rather than inventing delivery.

Current proof after this completion:

```text
focused Store/HTTP/WS/recovery/canonical-query tests            -> 53 passed
uv run pytest -q                                               -> 1266 passed, 19 skipped
uv run ruff check .                                            -> All checks passed
cd apps/desktop && npm test                                    -> 39 passed
cd apps/desktop && npm run build                               -> tsc + Vite green
```

The remaining event-related P0 is narrower and explicit: automatic handoff and remote
human attention have their own idempotent ledgers but still need an event-bound ordered
follow-up/outbox row so a crash before post-commit follow-up entry cannot omit them.

### Event-bound follow-up outbox completed after realtime

That remaining P0 is now closed locally. `event_followups` is created in the same
transaction as the event plan and contains exact `(event_id, kind)` rows for
`auto_handoff` and `human_attention`. Important behavior:

- Event planning records `followup_kinds` in the immutable plan envelope and atomically
  inserts pending follow-up rows. No post-commit scheduling gap remains.
- Follow-ups use boot-bound owners, bounded leases, explicit pending/claimed/complete
  states, attempt counts, and immutable terminal JSON results.
- Two runners in the same boot cannot execute the same live lease. A claimed row from a
  dead process boot is recoverable immediately even when its wall-clock lease has not
  expired; it does not impose a false 60-second startup delay.
- Startup first recovers authoritative event processing, then enumerates recoverable
  follow-ups and re-enters the exact terminal event without semantic replanning.
- Automatic handoff remains protected by its own pre-I/O `delivering` intervention
  receipt. Re-entering a pending follow-up treats delivered **or uncertain** item IDs as
  non-retryable, so the outbox cannot blindly resend after an ambiguous adapter call.
- Human attention retains its bounded inbox idempotency key. A crash after append but
  before ledger update reuses the exact inbox entry and repairs metadata; a channel
  exception cannot invalidate the committed event receipt and leaves the claimed row
  for lease/next-boot recovery.
- A live goal/project/pause rebind causes a typed skipped follow-up result rather than a
  stale handoff or alert.
- Focused tests prove claim exclusion, wrong-owner rejection, terminal immutability,
  immediate prior-boot reclaim, startup replay without replanning, handoff routing, and
  a completed human-attention receipt.

Proof:

```text
focused event Store/Pipeline/handoff/channel gate                 -> 65 passed
uv run pytest -q                                                 -> 1268 passed, 19 skipped
uv run ruff check .                                              -> All checks passed
```

## 31 Aug 2026 — typed project identity, quarantine, and queue-liveness checkpoint

This section supersedes every older statement that project identity did not land. It is
the current operational checkpoint. Overall release
status remains **NO-GO**. The persistent Codex goal remains active. No file was staged or
committed; no bridge process was started/restarted/killed; no provider, AgentCore, AWS,
deployment, publication, benchmark-freeze, or Devpost action occurred.

### Why this slice was necessary

The inherited `_project_key()` / `_same_project()` compatibility rule performs universal
`strip()`, backslash-to-slash conversion, trailing-slash removal, and Unicode
`casefold()`. That is unsafe as a universal identity primitive. It can falsely merge:

- POSIX `/tmp/Foo` and `/tmp/foo`;
- POSIX `/tmp/a\\b` and `/tmp/a/b`;
- a path with a real trailing space and the path without it;
- Unicode sharp-s and `ss`;
- Windows drive-relative `C:repo` with an assumed absolute interpretation;
- the same spelling on two different machines/providers;
- provider tenant identifiers whose case semantics are not known.

It also cannot prove physical aliases such as a symlink/worktree path and its target.
Replacing the helper globally would have silently rewritten old evidence and created a
large, unverifiable migration. The accepted strategy is additive, typed, origin-aware,
and fail-closed once a key participates in v2.

### Pure protocol now implemented

New file: `packages/protocol/src/pex_protocol/project_identity.py`, exported from
`pex_protocol.__init__`.

Typed schemas:

- `pex.project-locator.v2` / `ProjectLocator`;
- `pex.project-identity.v2` / `ProjectIdentity`;
- locator kinds `local_path`, `remote_path`, `repository_uri`,
  `provider_workspace`, `workspace_set`, and `opaque`;
- explicit `PathPlatform.POSIX` / `PathPlatform.WINDOWS`;
- explicit `ProjectOrigin(namespace, host)`;
- optional `PhysicalIdentityProof(provider, volume_id, object_id)`.

Important semantics:

- Raw locator text is retained exactly; canonical text is validated and cannot be
  forged on deserialization.
- POSIX paths must be absolute, remain case-sensitive, treat backslash as a literal,
  and retain meaningful trailing spaces.
- Windows paths must be drive-absolute, UNC, or a supported device path. Drive-relative
  paths are rejected. ASCII case normalization is used instead of Unicode casefold.
  Ambiguous trailing dot/space components are rejected. Extended `\\?\\` paths do not
  collapse `.` or `..`, because extended-length semantics bypass Win32 normalization.
- Repository locators accept only `https` or `ssh`, reject credentials/query/fragment,
  normalize DNS host/default port, preserve repository path case, and bracket IPv6
  authorities correctly.
- Provider/opaque identifiers remain exact. Only repository DNS origins are
  case-normalized; arbitrary provider tenant origins are not.
- Workspace sets are order-independent and reject duplicate members.
- Fingerprints include the typed canonical locator, origin, members, and physical proof.
  The same lexical path with two contradictory physical proofs is therefore two
  candidates, never an automatic merge.
- A missing physical proof may later be enriched without manufacturing a new project.
  Two different lexical locators merge only when exact same-origin physical proof
  establishes the alias. Contradictory proofs never merge.
- Stable identities use random `prj_<uuidhex>` IDs and a sorted locator-fingerprint set;
  identity is not derived from a lossy normalized path string.

### Additive Store schema and APIs now implemented

New SQLite tables in `Store.SCHEMA`:

- `project_identities`;
- `project_locators`;
- `legacy_project_bindings` with `active|quarantined` status;
- append-only `project_identity_conflicts`;
- append-only/idempotent `project_identity_resolutions`.

`Store.register_project_locator()`:

- requires an explicit typed locator; it never guesses a locator type from a legacy
  string and never infers existing legacy goals/sessions into v2;
- preserves the legacy key exactly, including case and spaces;
- replays canonical aliases such as Windows slash/case/dot variants and reversed
  workspace-set member order without treating their different raw display as a hash
  collision;
- scans a bounded locator set for same-origin physical aliases;
- creates a stable random identity for a genuinely new locator;
- quarantines a legacy key when a second non-alias identity is registered for it;
- turns same-path/different-filesystem-object proof into quarantine rather than rolling
  back and leaving the old authority silently active;
- appends a conflict receipt and does not merge the candidate identities.

`Store.resolve_project_identity()` returns only active typed bindings. Quarantined and
unregistered keys return no identity; unregistered legacy rows remain readable.

`Store.resolve_project_identity_conflict()` is the explicit operator resolution path:

- requires a unique resolution ID, exact legacy key, selected current candidate,
  resolver identity, rationale, and optional timezone-aware time;
- writes an immutable `pex.project-identity-resolution.v1` receipt;
- atomically reactivates only the selected identity and resets current candidates/
  fingerprints to that identity;
- exact replay is idempotent even when `resolved_at` was server-generated;
- a replay returns the **current** binding, so a later re-quarantine is not presented as
  stale `active` state;
- records `credentials_restored: false`. Resolution never revives a revoked credential;
  reissue is a separate explicit action.

There is not yet an operator HTTP/desktop surface for locator registration/resolution.
The Store contract is implemented and tested, but UI/API exposure remains work.

### Credential and partial-migration containment

`ProjectIdentityBlockedError` is the typed fail-closed signal with stable codes
`project_identity_quarantined` and `project_identity_unresolved`.

Once any lexical lookalike has a typed binding, an unregistered lookalike cannot inherit
its authority through the old helper. It must be explicitly typed. This prevents a key
such as `c:/REPO/` from bypassing quarantine of an exact `C:\\Repo` session binding.

On quarantine, one transaction revokes:

- active MCP principals whose own project, bound session project, or bound goal project
  is the quarantined exact legacy key;
- active hook credentials whose own project or bound session `project_id|cwd` is that
  key.

Receipts receive `revoked_at` and
`revocation_reason=project_identity_quarantined`. MCP/hook lookup also performs a live
typed-aware comparison, so a migrated legacy alias cannot authenticate merely because
its credential row did not join the exact legacy string. Issuance, rotation, and hook
session binding use the typed-aware comparison. Safe physical aliases are accepted;
the old synchronous validator no longer re-rejects them after the async typed check.

The three atomic MCP mutation commits (report progress, request a human decision, and
verify a claim) now re-read and gate the live session project inside their write
transaction, compare principal/goal/event/context/evidence through the typed-aware
matcher, and do not rely only on credential revocation.

### Core mutation and event boundaries now gated

The following paths reject quarantine/unresolved typed aliases in the same write
transaction:

- `upsert_goal`;
- `supersede_goal`;
- `upsert_session`;
- `add_event`;
- `accept_pipeline_event`;
- MCP principal/hook issuance and hook binding;
- planner-effect reservation and final pre-model dispatch CAS;
- `commit_event_plan` after a model result but before projections/action reservation;
- final pre-worker-I/O `claim_main_event_effect`;
- event follow-up claim;
- canonical `recent_events_for_binding` verification evidence selection.

Session-derived event binding now uses `project_id or cwd` for stored sessions and
accepted snapshots. Derivation and quarantine checks occur before duplicate acceptance;
legacy unbound duplicate rows remain idempotent only after the live derived binding is
checked. A cwd-only quarantined session cannot escape by supplying a new `project_id`:
incoming and existing effective bindings are both gated/compared, and the original raw
binding is retained.

### Queue liveness and no-I/O behavior

Quarantine must not merely raise and leave `event_processing.state=planning`, because
that would block every later event in the session. Pipeline planning and uncertain
reconciliation now catch `ProjectIdentityBlockedError` and call
`fail_event_processing()` with the stable identity code. The failure transaction:

- writes an immutable failed event receipt;
- skips any reserved non-dispatched effect;
- releases the processing lease;
- preserves any already-terminal uncertainty effect;
- allows the session queue to advance.

The planner model is not called when quarantine lands before its dispatch CAS. If a
conflict lands after the model returns, `commit_event_plan` prevents all context,
decision, intervention, session, main-effect, and follow-up projections from committing.
The main worker-effect claim returns a typed skip reason before adapter I/O, and the
existing Pipeline sealing path records a terminal skipped result.

Pending `auto_handoff` / `human_attention` follow-ups no longer remain pending forever
under quarantine. Claim atomically terminalizes them as complete with:

```json
{"status":"skipped","reason":"project_identity_quarantined"}
```

No handoff or notification I/O occurs and recovery no longer retries that row.

### Authority-reducing exceptions

Fail-closed does not mean blocking containment or audit finalization. Under exact
quarantine:

- goal `paused: false -> true` remains allowed only when every other goal field is
  unchanged (apart from monotonic `updated_at`);
- session `supervision_paused: false -> true` remains allowed only with explicit
  `allow_supervision_change` and an otherwise identical session;
- unpause/resume, project/goal rebinding, capability/status changes, and normal discovery
  updates remain blocked;
- credential revocation, conflict resolution, and terminal effect/audit finalization
  remain available.

### Adversarial coverage added

Pure and Store/Pipeline tests now cover:

- POSIX case/backslash/space/Unicode non-merges;
- Windows absolute/UNC/device/drive-relative and dot-segment behavior;
- IPv6 repository canonicalization and path-case preservation;
- provider-origin case separation;
- physical alias merge and contradictory-proof non-merge;
- Windows raw canonical aliases and workspace-set order replay;
- same lexical path changing physical object -> quarantine;
- exact legacy key/case/space preservation and no speculative legacy inference;
- conflict receipt deduplication;
- resolution replay with server-generated time and current-binding re-quarantine truth;
- credential revocation, reissue refusal, and legacy alias credential containment;
- core goal/session/event mutation rejection while reads remain available;
- authority-reducing pause allowed, resume rejected;
- cwd-only session rebind and unbound-event bypass rejection;
- quarantine immediately before planner reservation -> zero model calls, failed receipt,
  released queue, and successful processing after explicit resolution;
- quarantined follow-up -> terminal skipped receipt and no recovery retry.

### Current proof — 31 Aug

```text
focused identity/MCP/event Store/Pipeline gate                 -> 110 passed
uv run pytest -q                                               -> 1300 passed, 19 skipped
                                                               -> 257.95 seconds
uv run ruff check .                                            -> All checks passed
cd apps/desktop && npm test                                    -> 39 passed
cd apps/desktop && npm run build                               -> tsc + Vite green
```

These are local software proofs. They do not prove a packaged sidecar, a live vendor
session, a deployed AgentCore runtime, AWS eligibility, a visual demo, or benchmark
lift.

### Remaining identity/control gaps — do not overclaim completion

The legacy helper intentionally remains for unregistered compatibility and still exists
in unconverted call sites. Highest-risk remaining Store/control surfaces are:

- direct `/v1/sessions/{id}/message` now has the durable caller-idempotent contract
  documented in the next checkpoint; remaining direct-message work is bounded hardening,
  not the old unreserved-I/O defect;
- REST handoff omits the existing `request_identity` reservation path; MCP/REST/auto
  handoff need one canonical source+target reservation;
- overlay apply/revert performs adapter I/O before durable state;
- human-decision, permission, and lifecycle dispatch reservation/start paths need typed
  project gates with explicit authority-reducing exceptions;
- generic context/decision/intervention/lifecycle writers and the goal decision-only
  patch path need project resolution inside the same transaction;
- goal write plus extracted decision/context ledger is not one atomic/replayable request;
- project registration/resolution needs an authenticated operator API and honest desktop
  conflict UI;
- query truncation/rate limits and Windows token-file DACL ownership proof remain open.

The technical-first next slice is convergence of REST/MCP/automatic handoff on the
now-working operator-effect ledger, followed by overlay apply/revert. This ranks above hatch UI
because Technical Implementation is the official first criterion and tie-breaker, and
the pet follows the real closed loop in the recovery spec. After that, finish the
remaining identity mutation boundaries, then repair the stale hatch route/UI (which
still claims 13 calls) to use the accepted one-call typed `HatchAuthorization`, then
deterministic 8x11 assembly and independent QA under `hatch-pet`.

Exactly eight bundled pets remain, in order:
`pex, ledger, mesh, nudge, drift, quiet, ember, von`. User-hatched pets remain separate.
The four-arm manifest remains `frozen: false`.

## 31 Aug 2026 — durable direct-message operator effect checkpoint

This checkpoint supersedes every older statement that the direct
`/v1/sessions/{id}/message` route performs unreserved adapter I/O. Overall release status
remains **NO-GO**. No live bridge process, provider, AgentCore deployment, AWS resource,
benchmark freeze, submission, staging, or commit action occurred.

### Why this was the deadline-critical next slice

The old route loaded a session and immediately called `adapter.send_message()`. It had no
caller idempotency key, no immutable request hash, no pre-I/O Store record, no final
project/goal/pause CAS, and no permanent suppression after timeout. A client retry after
a lost response could therefore send the same worker instruction twice. Technical
Implementation is the first official criterion and tie-breaker, so this was completed
before returning to pet polish.

### Additive `operator_effects` ledger

`Store.SCHEMA` now contains an additive `operator_effects` table keyed by:

```text
UNIQUE(principal_id, action_kind, idempotency_key)
effect_id = stable SHA-256 typed tuple of principal/action/key
```

The first action kind is `session_message`. The row stores the caller request hash,
source/target session, captured raw project and goal, exact vendor/harness snapshot,
state/version/boot owner, reservation/dispatch/final timestamps, bounded payload/result,
and an optional bounded downstream operation ID.

The only supported transitions are:

```text
reserved -> dispatching -> delivered
                        -> failed
                        -> delivery_uncertain
reserved -> skipped
```

Every terminal receipt is immutable. `delivery_uncertain` is never automatically made
retryable.

### Request identity is separate from the live binding snapshot

The caller request hash contains only the immutable caller intent:

```json
{
  "schema": "pex.operator-request.session-message.v1",
  "session_id": "...",
  "text": "..."
}
```

The captured project, goal, vendor session, and harness remain in the durable payload but
are not part of caller intent. Reservation looks up
`(principal_id, action_kind, idempotency_key)` before live authorization:

- same key + same session/text returns the exact historical receipt without I/O;
- same key + changed session/text raises the typed `OperatorEffectConflictError`;
- a genuinely new request then validates live state and inserts `reserved`.

This distinction matters: a delivered/failed/uncertain receipt remains retrievable after
later pause, adapter disappearance, goal rebind, supersession, or project quarantine.
That replay is a read, not renewed mutation authority. A still-reserved replay must cross
the full dispatch gate again.

### Final pre-I/O dispatch gate

`Store.start_operator_message_dispatch()` re-reads and validates in one `BEGIN IMMEDIATE`
transaction:

- the effect is still `reserved`;
- global supervision is not paused;
- the session exists, is not detached, and is not supervision-paused;
- the session is not an observe-only desktop inventory tile;
- the exact session/target, vendor-session, and harness snapshot still match;
- the exact goal remains attached, exists, is not paused, and has no successor;
- current session project and goal project match the stored project through the typed
  live-project comparator;
- quarantine/unresolved typed aliases reject before I/O;
- no other direct operator effect is currently `dispatching` for that session.

Only the CAS from `reserved` to `dispatching` grants one adapter call. A binding failure
between reservation and this CAS is terminalized as `skipped`; the quarantine race test
proves zero adapter calls.

Different keys are serialized against an active `dispatching` message. A second request
remains safely `reserved` and may be retried after the first terminalizes. There is not
yet a global acceptance sequence for ordering multiple different reserved keys; do not
claim FIFO semantics.

### HTTP and cancellation semantics

`MessageIn` now requires:

```json
{
  "idempotency_key": "caller-stable-0001",
  "text": "Continue with the verified parser."
}
```

The key uses the existing 8-128 character safe request-key alphabet. The server never
generates a key for an external caller. Public receipts omit message text and return:

- `200` for delivered or exact replay of delivered;
- `202` for already-reserved/dispatching work, without resend;
- `409` for collision, skipped binding, session busy, or authoritative adapter rejection;
- `502` for terminal delivery uncertainty;
- `422` for a missing/invalid key or invalid text;
- `404` only for a genuinely new request whose session does not exist.

Adapter lookup happens after reservation replay, so a historical receipt is still
readable when the adapter is no longer present. Adapter `False` is treated as an
authoritative failure under the current adapter contract. Timeout or any transport
exception after the dispatch marker becomes terminal `delivery_uncertain`.

Cancellation during adapter I/O seals uncertainty before re-raising. Every post-I/O
terminal Store finalization is run in a shielded task, so cancellation while persisting a
known success/failure cannot cancel the receipt CAS. If storage itself fails, the row
remains `dispatching`; replay returns in-progress and does not resend, and startup
recovery seals it uncertain.

### Restart ownership and Cursor compatibility

Prior-boot `dispatching` rows are sealed to `delivery_uncertain` by the explicit
single-writer app-lifespan startup step. Generic `Store.connect()` does **not** run that
destructive recovery: a test proves that opening a second Store does not rewrite a live
owner's dispatch. The recovery method is owner-only by contract; a durable multi-process
owner lease is still a hardening gap.

The Cursor bridge follow-up helper now supplies the new required idempotency key. When
the direct-message route calls an adapter it passes the durable operator effect ID as
private attachment metadata; Cursor hashes that upstream identity into its bridge
request key. Legacy internal Cursor calls that do not yet carry an upstream effect fall
back to a deterministic session/text hash. That preserves compatibility but can collapse
two legitimate identical legacy messages, so event/human-decision senders must propagate
their durable effect identity when those paths are unified.

### Tests and current proof

Nine new tests cover:

- exact reserve and terminal replay;
- changed-body idempotency collision;
- one dispatch grant and immutable terminal state;
- terminal replay after project quarantine;
- quarantine between reservation and dispatch -> skipped, zero adapter I/O;
- session dispatch serialization without losing the second reservation;
- prior-boot dispatch -> terminal uncertainty and no redispatch;
- second Store connect leaves a live dispatch unchanged;
- HTTP missing-key rejection, one-send exact replay, changed-body conflict, timeout
  uncertainty/no resend, quarantine race/no I/O, and global-pause/no I/O.

```text
direct-message + event state-machine focused regression -> 43 passed
uv run pytest -q                                      -> 1300 passed, 19 skipped
                                                       -> 257.95 seconds
focused Ruff check                                    -> All checks passed
```

These are local software proofs. They do not prove a real vendor session or packaged
sidecar.

### Subagent read-only audit synthesis and exact next work

Three read-only subagents audited direct messages, handoffs, and overlays against all
three specs. Their findings were used to constrain implementation; they made no edits.

Next P0: generalize the working operator-effect ledger for one canonical context-handoff
path used by REST, MCP, and automatic event follow-up. The reservation must atomically
bind source + target + goal + both typed projects + selected bundle + stable trigger
event + intervention/audit row. Only the final CAS may grant adapter injection. REST/MCP
must require caller keys; automatic handoff must derive its key from the event and exact
selected items. Timeout, cancellation, or prior-boot dispatch must remain terminal
uncertain with no resend. Do not create a separate competing handoff ledger.

Then repair overlay apply/revert. The current code still mutates the adapter before
durable overlay state and blindly attempts rollback after ambiguous apply. The undo route
can also revert an overlay proposed by a failed colliding intervention because it trusts
proposal metadata instead of a delivered apply receipt. Required direction:

- durable overlay operation before I/O;
- no blind rollback/resend after ambiguity;
- local proof of exact reversibility and authority effect, never model assertion alone;
- only proven authority-reducing containment may cross quarantine;
- direct indexed earliest-expiry query, because the current newest-1000 in-memory filter
  can hide an old active overlay;
- OpenCode should become a Store-projected transition rather than pretend its in-memory
  helper is an external mutation.

Deadline priority after those two control-plane slices: expose the remaining typed
project conflict operator API, repair the hatch route/UI from stale 13-call admission to
the accepted one-call authorization, build deterministic 8x11 assembly and independent
QA, then package/live/demo/benchmark work. If time pressure forces a cut, preserve the
proven closed loop, the honest release gate, and the eight required pets; cut speculative
polish first.

## 31 Aug 2026 — canonical durable context-handoff checkpoint; still NO-GO

This section supersedes the immediately preceding “Next P0” paragraph: the canonical
handoff ledger is now implemented and verified. Overall release state is still
**NO-GO** because live Codex/Cursor evidence, overlay repair, hatch/atlas completion,
packaging, demo, benchmark freeze gates, AgentCore deployment, and submission artifacts
remain incomplete. No live companion was restarted, no external vendor was called, no
AWS resource was used, and nothing was submitted, deployed, published, staged, committed,
or frozen in this slice.

### Why this slice was deadline-first

The Technical Implementation category is the first judging criterion and tie-breaker.
The prior handoff implementation had four competing truth paths: REST rebuilt and sent
directly, MCP used process-local locking/cooldown, automatic follow-up used a legacy
intervention-only reservation, and internal callers could still call the old delivery
method. Those paths could disagree after cancellation/restart or inject the same context
twice. This slice finished the one durable Store boundary before moving to visual polish.

### Canonical request protocol

`packages/protocol/src/pex_protocol/context.py` now exports a strict, frozen
`ContextHandoffRequest`:

```text
idempotency_key     required; 8..128; safe caller-key alphabet
target_session_id  required; trimmed/control-free; 1..512
token_budget       strict integer; 256..12000; default 2000
extra fields       forbidden
```

This is the shared request object for REST and MCP. A missing key is never silently
replaced with a server-generated value. The operator request fingerprint contains only
caller intent: source session, target session, and token budget. Live vendor, goal,
project, capability, and bundle state are captured separately so exact historical replay
survives later pause/detach/quarantine while changed caller intent still conflicts.

### One `operator_effects` ledger, not a second handoff database

`services/bridge/src/pex_bridge/store.py` generalizes the existing durable operator
effect state machine with `action_kind=context_handoff`:

```text
reserved -> dispatching -> delivered | failed | delivery_uncertain
reserved ---------------------------> skipped
```

Reservation is one `BEGIN IMMEDIATE` transaction that binds:

- stable effect identity from principal + action kind + caller/derived key;
- source and target PEX session IDs;
- source and target immutable vendor session IDs and harness types;
- goal ID and pause/successor state;
- source, target, and goal legacy project keys plus stable typed-identity snapshots;
- the canonical provenance-minimized `ContextBundle` and token budget;
- the trigger event;
- one stable intervention ID, reserved intervention row, and audit row.

The Store re-runs the security boundary rather than trusting Pipeline objects. It rejects
detached/paused/observe-only desktop sessions, a paused or superseded goal, missing
`inject_context`, cross-goal/project bundles, quarantined/unresolved typed identities,
source and target rows that alias the same physical `(harness, vendor_session_id)`,
DENY interventions, reversible `FRESH_HANDOFF`, wrong capability requirements, extra
action payload keys, mismatched trigger IDs/types, noncanonical reservation receipts,
duplicate item IDs/refs, blank/NUL refs, stale/future items, falsified token estimates,
oversized payloads, and unstored/fabricated context.

Bundle provenance is checked against the exact stored context projection. Store rebuilds
the mesh bundle from the stored Goal, target, stored ContextItems, recent accepted source
events, token budget, and already-reserved/delivered target item IDs. After excluding the
time/estimate fields that are recomputed at the boundary, the supplied projection must be
identical. This prevents a caller from placing fabricated top-level “decisions,” evidence,
or progress into a legitimate-looking handoff.

Reservation no longer mutates the caller-owned `Intervention`. It constructs and
Pydantic-validates a new instance before persistence, so a rolled-back transaction cannot
leave the Pipeline object falsely marked reserved. The schema now includes a target/state
index as well as the source/state index.

### Final dispatch CAS and typed-identity TOCTOU protection

`start_operator_handoff_dispatch()` is the only grant for adapter `inject_context`.
Inside a final `BEGIN IMMEDIATE`, it revalidates:

- global, source, target, and goal pause/detach state;
- goal successor state;
- immutable source/target vendor and harness snapshots;
- current source/target/goal typed identity snapshots against reservation snapshots;
- exact live project equivalence and quarantine state;
- target capability;
- stored event/intervention/bundle integrity;
- token/provenance/sensitivity/source bindings;
- overlapping source/target operator dispatches, including direct messages;
- same-target/same-goal ContextItem overlap against earlier reserved, dispatching,
  delivered, or uncertain handoffs.

The overlap query is ordered and bounded. Two different keys selecting the same item for
the same target cannot both reach adapter I/O; the earlier reservation wins. A project
key bound to physical identity A at reservation cannot cross a quarantine/resolution to
identity B before dispatch even if the legacy string is unchanged.

Dispatch grant atomically changes both the effect and intervention to dispatching and
adds the audit revision. Finalization atomically changes effect + intervention + audit to
one immutable terminal truth. Only delivered sets `action_taken=FRESH_HANDOFF`; failed,
skipped, and uncertain remain `NOOP`. Terminal replays cannot alter result or resend.

### Cancellation, timeout, restart, and recovery semantics

Adapter I/O is made once after the dispatch marker. Timeout, transport exception, or
request cancellation after that marker becomes terminal `delivery_uncertain`; PEX never
guesses whether the vendor applied the context and never resends. Known success/failure
finalization is shielded from request cancellation.

`Store.recover_interrupted_operator_effects()` now recovers prior-boot handoffs in one
transaction. It changes the effect, bound intervention, and audit chain together to
`delivery_uncertain / handoff_delivery_uncertain / NOOP`. Generic `Store.connect()` still
does not rewrite another live Store owner; only the app-lifespan owner explicitly invokes
recovery. A durable multi-process owner lease remains future hardening, not claimed.

### Exact historical replay integrity

`_validate_operator_handoff_effect()` is shared by Store replay/find/start/finalize. It
checks the stable effect ID, caller tuple, request hash, closed payload shape, source and
target columns, goal/project binding, token budget, stable intervention ID, trigger row,
event-processing state, intervention/action/bundle agreement, audit existence, and exact
wire token estimate. Deleting or corrupting a bound event/intervention/audit no longer
leaves a replayable success-looking effect.

### REST and MCP convergence

`POST /v1/sessions/{source}/handoff` now takes the typed request. It uses stable principal
`local_bridge_operator`, preserves the canonical receipt, and maps truthfully:

- 200 delivered;
- 202 reserved/dispatching with no claim of delivery;
- 409 key collision, failed, or skipped;
- 502 terminal delivery uncertainty;
- 422 malformed/missing key or budget.

The public receipt includes effect state/bindings and excludes secret message content.

MCP `pex.handoff` also takes `ContextHandoffRequest`. Its principal namespace is derived
from the bound source session, so credential rotation does not change idempotency. It
returns failed/uncertain terminal receipts structurally instead of converting them into
success or hiding them as a transport error. Existing MCP auth, source-session, goal,
scope, desktop, and typed-project checks remain authoritative.

### Automatic follow-up convergence without event pollution or deadlock

Automatic handoff now derives one key from the canonical JSON tuple:

```text
schema + original event_id + source_session_id + target_session_id + goal_id
+ token_budget + sorted unique selected ContextItem IDs
```

Principal is `system_auto_handoff`; the full SHA-256 is used in the safe key. The bundle
and reservation are selected under `_handoff_mutation_lock`, but adapter I/O happens only
after releasing that lock. This prevents a Cursor ACP `session/prompt` from deadlocking
against a hook/event that re-enters Pipeline and needs the same lock. An E2E adapter
assertion proves the lock is not held at injection time.

Automatic handoff does **not** mint a second fake `AGENT_RESPONSE` or `STOP`. Store has an
explicit `trigger_event_mode=existing`: it verifies the exact original event, requires
terminal event processing and a claimed/complete `auto_handoff` follow-up, binds the
intervention to that event, and skips event insertion. REST/MCP retain deterministic
record-only `USER_PROMPT` trigger events because those are genuinely new control calls.
The unused legacy unrecoverable ingestion path no longer invokes automatic handoff.

If auto dispatch remains reserved/dispatching because another operator effect owns the
session, `_maybe_auto_handoff` raises so the durable event follow-up remains recoverable;
it does not mark a pending injection complete. `reserved` is deliberately not treated as
delivered during bundle selection, allowing the same derived key to resume an unstarted
reservation. `dispatching`, delivered, and uncertain items remain excluded.

`deliver_context_handoff()` remains only as a compatibility wrapper, but it now enters the
same canonical ledger and releases the Python lock before I/O. It no longer persists an
intervention and calls the executor through a competing legacy truth path.

### Subagent split and how findings were used

- `handoff_protocol_v2` implemented the strict shared request protocol and focused tests.
- `handoff_reservation_redteam` performed a read-only Store adversarial audit. Its P0s
  directly caused coupled recovery/finalization, trigger/action invariants, typed physical
  identity snapshots, canonical provenance rebuilding, bounds, logical dedupe, caller
  object immutability, target/source dispatch serialization, and vendor-alias rejection.
- `handoff_rest_mcp` converged only app/MCP callers and caller tests, avoiding Store/Pipeline
  overlap.
- `auto_handoff_audit` performed a read-only automatic-path audit. Its findings directly
  caused lock/I/O separation, original-event trigger mode, centralized derived keys,
  recoverable nonterminal follow-ups, replay flag repair, and removal of the legacy
  unrecoverable auto call.

### Added/updated proof

The focused handoff matrix covers protocol bounds, missing caller key, exact replay,
changed-request collision, one dispatch grant, concurrent same-key calls, terminal
immutability, timeout/cancellation uncertainty, restart recovery, quarantine race,
physical identity re-resolution, same-vendor alias, cross-project/source/goal rejection,
duplicate-item suppression across different keys, REST status mapping, MCP schema/auth,
original automatic trigger ownership, no synthetic event duplication, audit chain,
follow-up completion, one auto injection, and lock release at adapter I/O.

```text
REST/MCP/auto/store/protocol focused gate -> 100 passed
uv run ruff check .                    -> All checks passed
uv run pytest -q                       -> 1335 passed, 19 skipped
                                         225.98 seconds
```

These remain local software proofs. They do not prove a live Cursor ACP session, real
Codex App Server, packaged Tauri sidecar, or Devpost demo.

### Exact next action after this checkpoint

Overlay apply/revert is now the next P0. The existing implementation still has
mutate-before-record, ambiguous-apply blind rollback, revert-before-reservation, newest-
1000 expiry truncation, and undo ownership hazards. Required completion criteria:

1. durable overlay operation reserved before adapter I/O;
2. apply/revert dispatch CAS with timeout/cancellation uncertainty and no blind resend;
3. exact ownership so undo can revert only a delivered PEX-owned apply;
4. locally proven authority reduction/reversibility, not model assertions;
5. typed project/session/goal/pause/capability revalidation at the final CAS;
6. indexed earliest-expiry recovery that cannot hide old active overlays;
7. OpenCode projected honestly instead of claiming an external mutation from an
   in-memory helper;
8. adversarial tests plus full-suite/Ruff checkpoint.

After overlay: remaining project-conflict operator API and mutation gates; one-call paid
hatch admission + deterministic 8x11 atlas + independent visual QA for exactly eight
built-ins; then package/live/demo/benchmark/AWS/release gates. Deadline is 14 Sep 2026
17:00 PDT, but do not trade away receipt correctness or honest evidence. Cut speculative
polish before the closed loop, release gate, or required eight-pet product surface.

---

# Prior 1 Sep 2026 fingerprint/release checkpoint (historical; superseded above)

This was the canonical continuation point before the BYOK/custom checkpoint at the top.
Keep it only as implementation history; the persistent goal remains **active**:

> Audit every prior-agent change in `C:\Users\JosephMayo\Projects\pex` against this
> handoff and the three specs, repair/replace incorrect work, build the correct product,
> verify it end to end, and maximize the chance of winning the hackathon.

Do not interpret this checkpoint as completion. The three specifications remain the
authority, in this order on conflict:

1. `docs/PEX_CORE_SPEC.md`
2. `docs/PEX_BUILD_SPEC.md`
3. `docs/PEX_IMPLEMENTATION_RECOVERY_SPEC.md`

The recovery spec's real Codex + real Strands + same-session continuation/outcome/audit
loop remains the binding milestone. The work in this checkpoint is safe offline
correctness/release hardening; it does not replace that live proof.

## Current top-level state

- Overall state: **NO-GO** for Devpost submission, deployment, publication, AWS/provider
  use, installer/sidecar build, packaging, freeze, staging, or commit.
- Official deadline: **14 Sep 2026, 5:00 PM PDT**.
- No scored public leaderboard was found. Do not invent rank or retain an unvalidated
  leaderboard comparison.
- Manifest remains `frozen:false`.
- Exactly eight built-in pets, ordered:
  `pex, ledger, mesh, nudge, drift, quiet, ember, von`.
- Do not touch/restart the bridge at `127.0.0.1:7420`.
- Real Codex requires a fresh `PEX_LIVE_CODEX=1` authorization; real supervisor requires
  fresh `PEX_LIVE_SUPERVISOR=1`. Package/deploy/publish/submit/spend also require their
  own action-time approvals.
- The dirty tree is user-owned. Do not reset, clean, delete, stage, commit, or overwrite
  unrelated changes.

## Historical receipts from that checkpoint

Final exact-code Python gate:

```text
uv run pytest -q
1568 passed, 20 skipped in 357.92s (0:05:57)
```

Additional current focused gates:

```text
fingerprint/planner/event-processing/E2E final gate  83 passed
release/processing selected gate                    77 passed, 58 deselected
uv run ruff check <all changed Python files>        All checks passed
desktop npm test                                    59 passed
  - prior UI/view-model tests                       51 passed
  - new hostile release-contract tests               8 passed
```

The previous 1568/20 run at 447.16s predates that checkpoint's committed-plan ownership
seal. One intermediate rerun was deliberately
interrupted at 68% because code changed during the red-team fix; that interruption was
not a test failure. The 357.92s run above was final for that historical slice; use the
1603/21 receipt at the top for the current tree.

No live/vendor/AWS/browser mutation, package build, Git mutation, deploy, publication,
freeze, or submission occurred.

## Slice A — pure hostile release-contract validation

New files:

- `apps/desktop/scripts/release-contract.mjs`
- `apps/desktop/scripts/release-contract.test.mjs`

Modified release consumers/tests:

- `apps/desktop/scripts/build-sidecar.mjs`
- `apps/desktop/package.json`
- `tests/unit/test_fleet_pets_codex.py`

`release-contract.mjs` is not test-only: production `build-sidecar.mjs` imports it. It
provides pure validators for canonical release paths, Git hidden-index/untracked
classification, exact Tauri wiring/capabilities, pinned toolchains, sidecar stamps,
frozen-bundle inventory, source/status TOCTOU snapshots, and schema-2 release-evidence
closure.

The eight Node tests attack:

- Git S/h hidden-index flags and malformed index records;
- active-vs-pinned Node/Python/Rust/PyInstaller mismatches;
- widened Tauri capabilities, window scope, external binaries, and resources;
- stale, forged, malformed, and extended sidecar stamps;
- invalid frozen JSON, reordered inventory, mismatched values, and extra keys;
- release/source/status changes between preflight phases;
- traversal, absolute paths, case aliases, suffix aliases, and canonical filename-prefix
  namespaces;
- corrupt schema-2 links and forged playback authority.

`npm test` now runs both suites:

```text
node --test src/viewModel.test.ts scripts/release-contract.test.mjs
```

### Exact evidence closure

The earlier recursive release walk swept 842 `_audit` files, including 170 files not
reachable from the current release authority: 137 historical artifacts outside the
release, 25 superseded evidence files, and 8 known-failing hatch-validator reports.

`build-sidecar.mjs` now:

- excludes both `_hatch` and `_audit` from broad source recursion;
- collects only evidence actually validated while walking current manifests/receipts;
- keys evidence by resolved physical identity and rejects case/path aliases;
- requires paths to remain under `apps/desktop/src/pets/_audit/release/`;
- sorts canonically with stable code-unit ordering;
- adds only the validated evidence back to release inputs;
- includes `audit_reachable_input_count` and `audit_closure_sha256` in preflight;
- includes the production release-contract module in the sidecar source fingerprint.

Current reachable closure is exactly **672** files:

- 597 current playback artifacts;
- 9 release roots;
- 58 receipt-evidence artifacts;
- 8 runtime contact sheets.

Stable release evidence identities:

```text
audit closure sha256  94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470
release manifest      866348ec48730d04bb366630514e64c36564666868f7c731d7787f229ee9c4ed
fleet audit           ec759c3791b2c487beb43f18a5c7b02cad86fbfb4e08d25a16dc3b6aff0c3637
direct playback       57d63ccc75290b7660b45f3aa8c227156b71d9f2d8f67be9879548603fd87a9f
```

Latest preflight after the final code and documentation checkpoint:

```text
source_ready:false
release_ready:false
release_input_count:885
tracked_release_input_count:166
untracked_release_input_count:719
hidden_index_input_count:0
audit_reachable_input_count:672
release_input_sha256:0a646ad3b321011e8a7272e233d15512730d66b012386d3ff33e2acd96aad9e2
sidecar source input sha256:92eb724a29f08c043a0a90ed0523881699053c3e74f8cdc95ab36a791f97e1b3
stale stamp input sha256:be840b7c65f57575d0f629dfe2ccccd9c0c026b8352a71985e7a8b8db0b931b0
bridge sha256:bbcf165d4e8d3b46b66837e1a8aafc64bfe55e99b1cbaa6606cc20c576e59de4
cursor hook sha256:d81355dd1bf1c768a49287767c2e0d347c12170151ac0f4fa22f1298d88b150f
dirty status records:1193
toolchains verified:true
Tauri wiring verified:true
sidecars current:false
```

The exact release-input/source fingerprints must be refreshed after any code or handoff
edit. Never reuse an older hash as a current claim. The substantive blockers remain only
untracked inputs, dirty worktree, and stale/missing sidecars. Do not clear them without
explicit Git/package authorization.

## Slice B — immutable, fail-closed AgentFingerprint cohorts

Modified:

- `services/bridge/src/pex_bridge/store.py`
- `services/bridge/src/pex_bridge/fingerprints.py`
- `services/bridge/src/pex_bridge/pipeline.py`
- `tests/unit/test_store_fingerprints.py`
- `tests/e2e/test_m0_roundtrip.py` (truthful display assertions retained)

### Original defect

Planner fingerprints were initially harness-wide. The first attempted repair scoped
history by current `sessions.json` model/reasoning/project fields and synthesized an
authority-looking settings hash when the adapter supplied none. Independent red-team
review proved that old interventions would migrate when a mutable session changed model,
reasoning, settings, or project class; `legacy:` project bindings could be treated as
typed; arbitrary verification strings inflated confidence; multiple SELECTs could observe
different database snapshots; and a plain dictionary with `cohort_scoped:true` could
unlock an overlay recommendation.

That first attempt was not retained.

### Final authority design

Pipeline now passes both the exact `session.id` and current `event.event_id` to
`agent_fingerprint_stats`. Store targets the immutable acceptance row for that event, not
the current mutable session. It requires:

- `mode='pipeline'`;
- exact event/session binding;
- non-null persistent goal;
- valid `accepted_session_json`;
- durable vendor-session identity match;
- accepted snapshot id/harness/goal equal the event-processing scalars;
- a current live typed `identity:...` project binding equal to the acceptance binding;
- nonempty model;
- canonical `metadata.model_settings` dictionary;
- `metadata.model_settings_hash` equal to SHA-256 of canonical JSON containing model,
  reasoning effort, and settings;
- exact model, reasoning effort, settings hash, project class, harness, and physical
  project binding across eligible historical accepted events.

Historical evidence is limited to 500 candidate planned events. Overflow returns neutral
instead of silently truncating an authority-bearing recommendation.

### Exact committed-plan ownership

Red-team pass two found that `metadata.trigger_event_id` plus scalar bindings was still
insufficient: generic `add_intervention` could create an orphan row that looked like
history. The retained design therefore requires all of the following:

- valid committed `pex.event-plan.v1`;
- plan event/session/goal/project scalars match the acceptance row;
- plan contains a nonempty exact `intervention_id`;
- strict `pex.intervention-bound.v1` envelope with exactly the canonical envelope keys;
- envelope/payload id, session, goal, project, project binding, vendor session, harness,
  action hash, version, and proposed action all match their Store columns and plan;
- intervention `metadata.trigger_event_id` equals the exact accepted event;
- status is one of `supported`, `contradicted`, `acceptance_gap` and applies to STOP;
- each session counts at most once per category.

Generic/orphan interventions, missing trigger IDs, wrong-schema/top-level legacy JSON,
malformed JSON, cross-session references, forged vendor snapshots, mismatched settings
payload/hash, non-finite settings corruption, unknown statuses, stale project identity,
and current-session mutations all fail closed. Malformed session/intervention JSON also
cannot crash the descriptive Deck aggregate.

### Non-copyable planner authority

The Store seals a validated scoped result with a process-local non-serializable object.
`fingerprint_score_features` requires identity equality to that seal plus all provenance
flags, exact single model/hash, and coherent nonnegative counts. Copying the visible flags
into a plain dictionary cannot unlock score features. Harness-wide Deck results remain
descriptive and never carry this seal.

There is intentionally no production writer yet for canonical `model_settings` /
`model_settings_hash`. Therefore real runtime fingerprint influence remains safely
neutral until an adapter supplies a complete canonical settings identity. Do not call
this feature live-active yet. This is a known functional gap, not a safety bypass.

### Regressions retained

- two distinct exact-cohort planned gap sessions reach the minimum recommendation;
- duplicate/orphan history does not count;
- another project/model/reasoning cohort does not contaminate;
- mutating the current live session after acceptance does not move old evidence;
- legacy/untyped/missing-settings targets return no scoped result;
- wrong-schema and malformed intervention rows remain neutral;
- forged accepted vendor and non-finite settings snapshots return neutral;
- copied authority booleans remain neutral;
- only the three known verifier statuses enter inspected/reliability counts.

Final independent spot-check reported **no remaining P0/P1**. Its last two lower-severity
findings (non-finite settings hashing and malformed Deck JSON) were fixed and included in
the 83-test focused gate and final 1568/20 full run.

## Subagent split and exact influence

Continue using focused subagents, because the user explicitly requested delegation and a
detailed continuation trail. Avoid overlapping edits; give each agent one bounded cluster
and keep the primary agent responsible for spec reconciliation and final integration.

- `fullgate_proof_cluster`
  - implemented the pure release validator/tests;
  - red-teamed fingerprint authority twice;
  - found mutable-history migration, legacy-key acceptance, synthesized settings identity,
    copyable authority flags, non-snapshot reads, unknown-status inflation, orphan
    intervention ownership, wrong-schema fallback, vendor/settings provenance gaps, and
    malformed/non-finite corruption edges;
  - final read-only spot-check: no remaining P0/P1 before the last two P2 fixes.
- `fullgate_store_fixture_cluster`
  - proved that `event_processing.accepted_session_json` and
    `accepted_project_binding` are the existing immutable acceptance authority;
  - prevented retaining an unsafe new schema column populated from mutable sessions;
  - specified the exact-event recovery/plan ownership regressions.
- `fullgate_pipeline_cluster`
  - re-read the three specs and ranked safe offline gaps;
  - identified fingerprint scope as the best bounded correctness slice completed here;
  - ranked remaining work: BYOK/custom supervisor configuration, durable attention
    metrics, typed handoff assimilation, and one real lifecycle-resource producer.

Subagents were read-only whenever their work could overlap the primary patch. Their
findings were independently verified rather than copied blindly.

## Next safe work, in priority order

1. Preserve the exact full/focused/release gates. Re-run the smallest affected tests after
   every edit and a fresh full suite before any release claim.
2. The binding product milestone is the real Codex + real Strands same-session loop, but
   do not run it without fresh action-time authorization and the required environment
   gates.
3. BYOK/custom supervisor backend authority is now locally complete; use the latest
   checkpoint above for its exact limits and do not repeat or weaken that design.
4. Move attention metrics from the client's last-40 slice to a durable backend
   aggregate with explicit window, denominator, truncation, and consent semantics.
5. Add typed handoff-assimilation evidence tied to the exact bundle/intervention and
   target first action; generic activity is not proof of assimilation.
6. Wire lifecycle cleanup to one real tightly scoped producer only after identifying its
   exact ownership/Undo contract. Do not invent broad temp cleanup.
7. Only after authorization: clean tracked release state, rebuild sidecars, package Tauri,
   visually QA packaged playback, run the live loop, and prepare Devpost evidence. Each is
   a separate gate.

Do not expand PexBench, remote channels, AWS, pet count, or speculative presentation
polish ahead of these bindings. Do not cite synthetic scores, fixture scores, the old
1/5-vs-4/5 leak, or direct playback as live packaged proof.

## Commands for the next agent

Safe read-only/focused continuation commands:

```powershell
Set-Location -LiteralPath C:\Users\JosephMayo\Projects\pex
uv run ruff check .
uv run pytest -q tests/unit/test_providers.py tests/unit/test_supervisor_config.py tests/contract/test_supervisor_settings.py tests/unit/test_search.py
Push-Location apps/desktop
npm test
npm run build
Pop-Location
node apps/desktop/scripts/build-sidecar.mjs --preflight-release
```

The preflight is expected to return nonzero while printing truthful JSON because release
is NO-GO. Do not "fix" that by building, staging, committing, deleting evidence, or
rewriting the sidecar stamp without authorization.

## 2026-09-06 live submission-sprint checkpoint

The operator set a hard three-day runway on September 6. Prioritize the judge-visible
same-session recovery loop, release stability, and a coherent native demo over broad new
features. The objective remains winning the hackathon, but do not turn that objective
into unsupported completion claims.

### Pushed checkpoints

- `286e1696a231adb006f34a2c8f845d29964435d5` — rebuilt the pet/compact UX and hardened
  the desktop-owned bridge lifecycle. The native pet is closable, Escape-aware, durably
  restorable from Settings, transparent, and shown before bridge recovery so a bridge
  failure cannot trap the overlay. All eight built-in pets were validated as Codex v2
  transparent RGBA atlases; the visual background defect was CSS/fallback presentation,
  not baked asset backgrounds.
- `111045ea9e085b31be5f527fb94eab69d7a0d01c` — split Settings into Companion,
  Supervisor, Connections, and Goals tabs; added keyboard/ARIA tab behavior and routed
  current settings failures to the Supervisor retry surface; retained `--clean` for
  release PyInstaller builds while allowing fingerprint-checked cache reuse in dev.
- `658d0d7fac131ffdadcb1df5b87d34ecd4d44eb5` — pinned the intentionally modest live
  Codex proof worker to `gpt-5.3-codex-spark` through the supported turn parameter.
- `5c49c10eaed4ad96346ceef8d2eb257e46fcd425` — seeded the Windows proof target so the
  parent verifier can read operator-owned evidence after a sandboxed worker updates it.

Each commit above was pushed and local `HEAD` was verified equal to its upstream after
the push. At this checkpoint both resolve to `5c49c10eaed4ad96346ceef8d2eb257e46fcd425`.

### Live native and BYOK evidence

- Native Tauri Settings loaded successfully through the attached WebView. The four
  section controls rendered as real tabs and ArrowLeft/ArrowRight activation was tested.
- The UI saved provider `zen`, model `muse-spark-1.3-contributor-free`, auth mode
  `api_key`, and `https://opencode.ai/zen/v1` as supervisor revision 1. The credential is
  represented only by an opaque OS-secret-store reference in `~/.pex/supervisor.json`;
  no secret was printed or committed.
- A separately authorized free live probe passed: `tests/contract/test_live_supervisor.py`
  reported `1 passed in 14.26s`. Its assertions require a real completed Strands call,
  `used_llm=true`, `runtime=strands-agents`, exact Zen/Muse provider identity, and at
  least one model call.
- No Ollama model was present (`0` model files). The unused Ollama server process was
  stopped. Do not reinstall or redownload a local model unless the operator changes the
  chosen architecture.

### Validated real Codex + Strands proof pair

The binding Recovery Spec proof pair is now green on current source. The two tests were
run in separate pytest processes because each deliberately cancels all remaining asyncio
tasks during cleanup.

1. `test_live_codex_stop_inspects_with_strands`
   - result: `1 passed in 83.62s`;
   - proof: `benchmarks/results/_scratch/codex_inspect_proof.json`;
   - schema status/kind: `validated` / `evidence_supported_noop`;
   - exact worker thread: `01a073ff-c2bb-76b1-8c4c-89fc48a039ac`;
   - one Codex turn, one intervention, action `NOOP`, artifact content `pong`;
   - real supervisor receipt: `used_llm=true`, `runtime=strands-agents`, provider `zen`,
     model `muse-spark-1.3-contributor-free`.
2. `test_live_codex_incomplete_stop_sends_specific_continue`
   - result: `1 passed in 137.53s`;
   - proof: `benchmarks/results/_scratch/codex_incomplete_proof.json`;
   - schema status/kind: `validated` / `same_thread_intervention_outcome`;
   - exact worker thread: `01a07401-5767-7c93-8664-eeaf0dc944a2`;
   - two Codex turns on that same thread, two interventions, actions
     `SEND_NUDGE,NOOP`, artifact content `shipped`;
   - both supervisor receipts contain `used_llm=true`, `runtime=strands-agents`, provider
     `zen`, and model `muse-spark-1.3-contributor-free`;
   - the test additionally proves exact delivery binding, final STOP correlation,
     acceptance transition from unsatisfied to supported, durable SQLite/JSONL parity,
     `helped=true`, unchanged App Server process identity, and unchanged source fingerprint.

The first attempt at the restraint case correctly failed because a sandbox-created
Windows file existed but was unreadable to the parent verifier, yielding
`acceptance_status=uncertain`. Production verification was left fail-closed. The fixture
now pre-creates an empty operator-owned `ping.txt`, matching the already-correct recovery
case's `report.txt` boundary. Never weaken unreadable evidence into supported evidence.

The validated receipts are deliberately under gitignored `_scratch`; inspect and copy
only sanitized evidence into submission materials. They bind to source revision
`5c49c10eaed4ad96346ceef8d2eb257e46fcd425` and to the exact dirty-worktree fingerprint.
The dirty bit is expected because the protected operator-owned file below is retained.

### Protected boundary and remaining risks

- Do not edit, stage, restore, reformat, or clean
  `services/supervisor/src/pex_supervisor/loop.py`. Its retained SHA-256 is
  `392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`.
- After the proof pair, `git status --short` contained only that protected file. No owned
  proof Codex child remained; the only App Server process was the pre-existing desktop
  process started at 2026-09-05 20:56:55.
- Desktop gate after the Settings rebuild: `172/172` tests passed and TypeScript + Vite
  production build passed (60 modules).
- The bridge's prior discovery storm was reduced, and `/health/live` answered 200 in
  roughly 0.2 seconds, but the live bridge still consumed about 1.58 CPU seconds during
  a five-second sample. Treat residual CPU usage as an open performance defect.
- `PATCH /v1/supervisor` still constructs the provider/model synchronously while holding
  an async configuration lock. A naive `wait_for(to_thread(...))` was reviewed and
  rejected because cancellation can leak a staged credential and allow overlapping
  hanging constructor threads. Fix this only with independently owned transaction/finalizer
  semantics or a safely bounded worker process.
- Release/package preflight remains NO-GO until a fresh clean release build, packaged
  native visual pass, evidence curation, and submission checklist are complete. The live
  proof pair closes the central same-session requirement; it does not by itself declare
  the full app submission-ready.

### Immediate next work

1. Preserve and sanitize the two validated proof receipts into judge-facing evidence
   without including secrets, machine-only credentials, or temp paths.
2. Profile the residual native bridge CPU and stop any remaining redundant polling or
   desktop discovery work without weakening freshness.
3. Repair the supervisor configuration transaction hang safely, with hostile tests for
   timeout, cancellation, credential retirement, and concurrent PATCH attempts.
4. Run the full Python/Rust/frontend gates, then the truthful release preflight; resolve
   only owned blockers and preserve the protected loop file.
5. Build/package Tauri, visually QA the packaged app and every critical demo surface,
   and rehearse the exact restraint + recovery narrative before preparing Devpost assets.
