# PEX continuation checkpoint — 6 September 2026

The user's internal shipping target is now **9 September 2026, Africa/Lagos**.
The full three-spec objective remains active. Submission remains **NO-GO**.
This checkpoint supersedes older `current` / `final` claims in the rolling handoff,
STATUS, shipping checklist and submission draft.

## Source and package boundaries

### Latest review cycle: shared outcome persistence and responsive pet assets

The initial shared outcome patch was rejected by independent review: adding
`shared_delivery_scope` during settlement violated the Store metadata contract.
Root reproduced the failure in cancellation settlement (126 passed, 2 failed);
the reviewer reproduced it in correction/framed flows (21 passed, 5 failed).
The current repair captures immutable subscription scope at acknowledged dispatch,
validates its Store/effect/audit binding and rejects a later subscription generation
even if the same vendor turn ID reappears. Final independent gate is pending.

A separate native responsiveness repair offloads bounded atlas reads/full Pillow
validation to the framework thread pool. Four pet API tests passed, including a
blocked-reader case that completes the real HMAC identity endpoint while artwork
requests remain pending. This establishes event-loop responsiveness for that case,
not the root cause of the earlier native exit. Identity limits remain unchanged.

The floating-pet shell now refreshes canonical goals with a lightweight 30-second
poll and stale-response fencing, without loading the heavy Settings catalog.
Desktop tests: 192 passed; production build passed. Native roster reinspection
again showed all eight previews and the persisted hidden-pet checkbox. The older
native binary is still running; latest-source cold-start/restart remains pending.

A new operator-owned proof thread was created before PEX attachment:
`01a076df-926d-7701-adb4-ff8c78838e9d`, workspace
`C:\Users\JosephMayo\pex-live-demo\workspace\shared-recovery-20260906-03`.
Warm-up notification waiting timed out; an independent `thread/read` confirmed
one completed turn with no error and idle status. The private operator reader now
retains notifications arriving before an RPC response. Do not send another warm-up
or describe this timeout as a failed worker completion. No PEX goal/grant/trigger
has been sent for this new thread yet. Historical run-02 evidence stays unchanged.

### New live continuation: existing-worker setup and native recovery

The current execution checklist is `SUBMISSION_SPRINT_2026_09_09.md`.

The operator approved resuming native checks. On source `065cb22`, the native
Home rendered correctly, but opening Companion settings was followed by a real
`bridge_process_stopped` failure. This is not a passing stability result. Normal
Retry recovered the bridge and all eight roster thumbnails rendered. The root
cause of the first exit remains unproven; independent review found that a later
shutdown can overwrite the original failure code, which is being repaired.

Separately, a clean-source bridge on isolated port 7431 successfully inspected and
confirmed a pre-existing operator-owned Codex shared thread, without starting a
worker turn. Goal setup exposed a production bug: an explicitly connected idle
shared session with no activity timestamp was excluded from the canonical pet
snapshot. The projection now keeps that session selectable before its first live
event; ordinary historical idle rows remain excluded. Focused root verification:
**25 passed, 1 skipped** (pet snapshot and HTTP helper tests). Goal attachment and
real correction through this shared-worker production path were pending at that
snapshot. A fresh clean `1e645cd` bridge subsequently passed goal attachment and
grant, independently generated and verified a specific correction through real
Strands, sent it to the same existing worker, and observed a final NOOP. The
external artifact oracle verified exact bytes `736869707065640a` (eight bytes).
The worker has three total turns including its earlier one-turn warm-up.
Grant revocation and observer detach both succeeded; a post-detach worker read
confirmed it remained idle and readable. Private capture:
`pex-shared-live-065/build/shared-demo-client-receipts-02/capture-20260906T125941539159Z.json`.

**Audit gap, not complete proof:** the delivered intervention still has empty
worker-response/outcome fields and `helped=null`. Shared event IDs differ from
the isolated Codex normalizer IDs expected by the outcome matcher, and shared
STOP lacks its raw turn reference. Repair and fresh recapture are required;
never retrofit success into the historical receipt.

Native follow-up confirmed message-minus hides only the bubble and pet-X saves
`quiet=true`, reflected by unchecked Show desktop pet. A frontend repair also
routes floating-pet text through Home's canonical first-run state; no worker is
no longer falsely described as All quiet. Full frontend gate: **191 passed** and
production build passed. React review confirmed the change adds no new poller or
effect. Native first-failure-wins handling preserves an earlier identity failure
against a follow-on child shutdown; **15 Rust tests passed**, with root's focused
regression independently passing. Neither repair establishes the original native
exit's cause or final installed-build stability.

- `43690b8e728f8c69d3b4cdad7939f724ee7adb3f` was pushed and verified against remote
  main. It pins all five frozen public benchmark prompts to LF through `.gitattributes`.
  A new Windows checkout confirmed `i/lf w/lf attr/text eol=lf` for all five prompts.
  The exact-byte regression and original failing test passed; full PexBench passed
  **129 tests** under strict resource/unraisable-warning settings in the main checkout.
- `44fa68b` changes supervisor configuration wording. Constructing a Strands client
  does not prove connection or inference. Credentials may be in the OS vault or
  environment; the previous blanket `.env` claim was incorrect. Provider tests:
  **76 passed**; desktop view-model tests: **62 passed**.
- Current source also repairs Companion settings overflow and checkbox sizing after
  reproducing both in the native app at its normal 920-by-730 window size. The roster
  wraps within its grid area; narrow windows use one settings column. The production
  frontend build and **184 desktop tests** pass. The test run emitted an HMR-port
  warning (`24678` in use), despite all assertions passing. Native rendered checks
  now confirm the corrected normal-window layout; see the native evidence below.
- The latest retained package receipt is for **`4f8b567`**, not current source.
  Local receipt: `C:\Users\JosephMayo\Projects\pex-release-final-8b\build\pex-package-receipt.json`.
  It reports `release_ready: true`, `blockers: []` for package integrity only.
  MSI SHA-256: `5a725c81bc9a89cf4b1f3285477d80a765a3adeedfdee49d173cbc92c5b49994`.
  NSIS SHA-256: `f133ad58e495bd0ef27195da7b40155f7d11090d6ebbc3caa79aaea460b70c8c`.
  A new final package must incorporate subsequent source changes.

## Full-suite diagnosis

The earlier clean `4f8b567` run failed 16 PexBench tests because Git materialized the
public prompts as CRLF, while text-mode workspace reads normalized LF. This was a
checkout portability defect, not test-order contamination. Keep exact byte/hash checks;
do not normalize only one reader and create mutually inconsistent fingerprints.

The fresh `43690b8` checkout is
`C:\Users\JosephMayo\Projects\pex-release-final-9c`. Its full strict suite was
interrupted after **225 passed, 16 skipped**, while the 65-handoff capacity case appeared
stalled. Independent evidence subsequently showed continued durable handoff progress
and an isolated **PASS in 266.58 seconds**. Therefore a deadlock is not established.
The isolated capacity case passed again under `cProfile` in **281.67 seconds**.
Profiling found roughly **16,046 SQLite connections**: its helper created 65 attached
source siblings, so each new event exercised expanding sibling and automatic-handoff
scans before the intended indexed delivery. The capacity fixture is now narrowed to
one attached source and 65 real, distinct REST handoffs so it still proves the exact
beyond-64 contract without accidentally benchmarking an expanding sibling-scan topology.
The corrected case passed in **116.50 seconds**; two adjacent index/ownership cases
passed in **10.27 seconds**. Independent review approved the unchanged beyond-64
authority, oldest-delivery acknowledgement and artifact-evidence assertions. This is
a fixture-runtime improvement, not a measured production speedup.
This does **not** dismiss the separate production scalability concern: large attached
fleets still cause repeated authority-bound session, recent-event and intervention
reads, and that all-pairs path needs its own bounded performance work and evidence.
A diagnostic run with `faulthandler_timeout=45` emitted a Windows access violation;
do not report that diagnostic as a passing run or silently attribute it to PEX code.
The completed strict `ebca89c` full-suite receipt is recorded below; later proof-only
changes have their own focused gate. Do not conflate source revisions.

## Fresh live supervisor result and current repair

The clean checkout `C:\Users\JosephMayo\Projects\pex-live-final-f53`, source
`f53c13b187421448b3fc26e3b82c2ef0571f34ea`, ran real Codex and Strands with the exact
Zen model `muse-spark-1.3-contributor-free`. Its restraint case passed in **139.97s**:
one worker turn, one real supervisor call, artifact-supported acceptance and `NOOP`.
Raw restraint receipt SHA-256:
`283334E846A7F01273DF5AE3DAE00D0C823F4D4A4EC715F0855DB12A7A002D9E`.

The fresh recovery case **FAILED in 219.53s**. It produced one initial STOP decision,
not zero: the main model proposed a correction, but the independent verifier spent
all three model calls on evidence reads and returned no typed verdict. Its status
was `missing_structured_output`; PEX correctly failed closed to `NOOP`, and no second
worker turn occurred. The test's old `no initial STOP intervention` assertion was
misleading because it assigned the first decision only after seeing two. Do not
describe this source as a freshly validated live pair. The earlier `5c49c10` pair
remains historical evidence only. The failed case's temporary SQLite was inspected
before pytest's normal retention removed it; future live runs must use a unique
explicit `--basetemp` under ignored scratch so failures remain inspectable.

A bounded free-provider diagnostic confirmed Muse rejects `tool_choice=required`
with HTTP 400 and explicitly supports only `auto`. Do not change the adapter to
required or claim its compatibility mapping caused this failed run. The reviewed
repair instead gives the verifier generic budget guidance: gather sufficient
independent evidence efficiently, reserve a call for its typed verdict, and reject
when evidence is insufficient. Runtime limits and evidence/permission gates are
unchanged. The strict Strands-runtime unit gate passed **47 tests**, including
one/two evidence-call approval controls and three-call exhaustion failing closed.
This supports the safety boundary; only another real run can verify model behavior.

Independent review also found the reusable proof omitted the verifier receipt and
the requested worker model. The reviewed v4 proof now binds independent verifier
observations and main observations to the same session, goal, trigger and request
digest, while requiring separate invocation IDs and valid evidence hashes/references.
Mirrored negative tests reject missing receipts, forged bindings, duplicate evidence,
empty main references and malformed model fields. The isolated child pins Spark in
its process configuration and records raw per-turn model requests. Null continuation
model means documented inheritance, not proof of a model switch; requested settings
are not authoritative executed-model identity. Old v3 receipts are historical only.
The strict combined proof/runtime gate passed **60 tests in 8.08s**, Ruff passed.
This reviewed update is pushed as `6212b625f01232405d8708cc134d1e515853387e`;
remote main equality was verified. Clean `pex-release-final-9c` now points to that
revision. Its v4 restraint case passed **98.44s** and recovery passed **135.52s**.
Recovery used two worker turns in one thread: SEND_NUDGE -> artifact-supported NOOP,
helped=true. Initial aggregate calls 4 include two independent-verifier calls;
the final NOOP used one call. The verifier approved with three independently bound
observations. Curated receipt: `docs/demo/evidence/LIVE_CODEX_STRANDS_2026-09-06.md`.
Both raw receipts and SQLite databases remain under that checkout's ignored scratch.
A setup-only attempt first failed because the scratch parent did not
exist, before any worker/model call; the parent was created before the actual run.

The reviewed prompt/fixture/checkpoint update is pushed as
`ebca89ccc1880d25066d973e7bdf7e8ec9e77696`, with remote equality verified. The PC
subsequently shut down; the user confirmed it is back on. The interrupted full-suite
process was absent after reboot and left no completed XML report. It is **not a pass**.
A fresh strict run completed in the clean `pex-release-final-9c` checkout at
`ebca89c`: **3600 passed, 25 skipped in 1073.00s**, with unraisable/resource warnings
treated as errors. Report: `build/full-suite-ebca89c-post-reboot.xml`. This source
predates the new v4 proof tests, whose separate focused gate is recorded above.

The user's latest cost preference supersedes all older Sol assignments: use
**GPT-5.6 Terra, medium reasoning** for subagents. The proof owner completed its
bounded review and read-only large-fleet audit. It then audited first-run UX and
implemented the small pure first-run view-model helper/tests; root owns integration.

## Native interaction evidence

Computer Use became available with the refreshed plugin on this continuation.
The exact extracted `4f8b567` desktop was launched from
`build\native-smoke-4f8-01\pex-desktop.exe`, using the retained isolated
`build\native-profile-4f8-01` via `PEX_HOME`. It reached **All quiet**.

Observed through the native accessibility tree and screenshots:

- The separate pet window showed Pex and its status bubble.
- Clicking **Dismiss PEX status message** removed the bubble and retained the pet and
  accessible status label.
- **Alt+F4** removed the pet window while the main PEX window remained open.
- Companion settings exposed all eight named built-ins, but the old package layout
  overflowed horizontally and rendered oversized visibility checkboxes.
- Supervisor settings eventually loaded. Their old `Semantic model is loaded` and
  `.env` wording triggered the truthfulness repair above.

The user pressed physical Escape during the next UI refresh. Computer Use stopped
immediately. After the PC reboot, the user explicitly answered **Yes, resume PEX app
checks**. Native interaction is authorized again; that permission does not authorize
security/authentication UI or paid/public actions. The normal development launch is
being rebuilt with isolated `PEX_HOME=build/native-profile-ebca-dev-01` to inspect
current frontend changes. It is not the retained release-package receipt.
The rebuilt native dev app reached All quiet without a bridge error. At 920x730,
Companion settings show all eight loaded pet thumbnails in a contained 4x2 grid,
normal-sized checkboxes and no horizontal overflow. No release-package claim follows
from this dev observation. Enabling Show desktop pet produced the separate pet
window. Its minus button removed the message while retaining the pet; its X button
removed the pet window while the main PEX window remained. User input/minimization
interleaved with the check, so further mouse actions paused to avoid interference.
Settings reflected the hidden state, and enabling visibility again restored the
separate pet window. **Restart persistence and final all-eight animation replay
remain incomplete.** The current app/process/
window IDs are ephemeral; rediscover them before reuse.

## Current first-run UX repair

Native observation found that no connected worker/goal could still be presented as
All quiet with only a generic inspect action. The new Home setup guidance distinguishes
no observable worker, an unbound worker, a current attached goal and unavailable state.
Navigation to goal setup preserves the existing form/draft and guarded submit path;
it does not create or attach anything. A direct Connections destination now survives
supervisor-settings loading. Native Home -> Connections navigation was observed.
Supervisor configuration availability is visible on Home and Inspector, explicitly
not a connection/inference receipt. The view fetches settings read-only outside Settings
too, but does not introduce form polling. Paused and urgent states retain precedence
over setup copy. Independent review caught the quiet-tone paused edge case; it is
covered in the pure helper used by App. The Home card now stacks metrics beneath the
pet rather than squeezing them into a narrow right column; the OPEN label contrast
was increased. Final desktop gate: **190 passed, zero skipped**, production frontend
build passed. Terra-medium independently reviewed the integrated flow; the paused
precedence defect it identified was fixed and tested before acceptance. The previous
189-case run predates the added pure status regression; do not sum overlapping runs.

The existing Brave preview was reused through its connected extension (no browser
restart/new profile). It renders current source without a build-error overlay, but
shows Bridge offline because it lacks native desktop bridge authentication. This is
not a native startup failure or a completed authenticated browser test.

## Remaining execution order

1. **P0: finish native UI restart/retry verification of the reviewed repair below**, then finish real
   native setup and persistence. First-run UX is pushed as `726a3d2` with remote equality.
   The stronger proof contract, clean full-suite and controlled live recovery pair
   now pass on their exact revisions above; they do not close pre-existing-worker proof.
   Keep the measured large-fleet authority-read amplification tracked separately;
   correcting the 65-delivery fixture did not repair production fleet scalability.
2. Complete native close/restore/restart and all-eight-pet checks. Settings layout,
   pet hide, message dismissal and restore have native evidence; restart does not yet.
3. Recapture the real Codex + Strands restraint/recovery pair on the final runtime,
   including independent verifier evidence where required and ten quiet tasks.
   The latest retained v4 live pair proves source `6212b62`; see the curated live receipt.
4. Complete required cross-harness behavior, honest isolated comparisons, AgentCore
   deployment under the user's no-card-charge condition, and the final audited package.
5. Record the real public demo video and finish the truthful submission artifacts.
   PexBench remains unfrozen; no leaderboard rank or measured productivity lift exists.

Use bounded subagents and independent review. New subagents use GPT-5.6 Terra medium.
Push reviewed scoped updates, verify remote equality, and preserve the complete product
goal rather than redefining readiness around tests or packaging.

Protected operator-owned file: `services/supervisor/src/pex_supervisor/loop.py`.
Do not edit, stage, restore, format or clean it. Its rechecked SHA-256 remains
`392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`.
No cloud deployment, paid call, public post or submission occurred in this continuation.

## Native restart blocker and narrow restraint repetitions

A normal `tauri dev --no-watch` restart at `726a3d2` failed with `identity_timeout`.
Observed desktop creation was 12:47:28 WAT and Python payload creation 12:47:41:
about 13 seconds elapsed before the payload even started. The 20-second budget
covered extraction, imports and identity verification. Killing the owned PyInstaller
bootloader on timeout left its payload alive, holding port 7420 while the desktop
remained open. Closing only that isolated desktop normally subsequently removed both
the desktop and payload; a read-only check confirmed no listener remained on 7420.
This is a real release blocker, not an authentication-check false positive to bypass.

Reviewed patch: retain/watch both desktop and distinct frozen Windows bootloader
process handles before importing the heavy bridge app; preserve standalone
`--verify-bundle` auditing. The bounded cold-start allowance becomes 60 seconds and
the visible copy is tested against the native constant. Identity, nonce, token and
untrusted-port checks are unchanged. Strict watchdog/auth gate: **34 passed, 2 skipped**;
desktop: **190 passed**; Rust: **14 passed**; production frontend build passed.
Independent review caught both standalone-bundle regression and remaining pre-watchdog
dependency imports; both were fixed before acceptance. The ordinary sidecar rebuild
passed its input-fingerprint and frozen inventory gates. An earlier concurrent-source
build correctly refused installation and is not a successful build.

Actual frozen regression: **3 passed in 47.80s** against bridge SHA-256
`0CDC3F6D34BFD55BECDBCC7C700BE8717B8AFBEC7D80F2D51913347A23A24702`.
Two isolated launches proved nonce/HMAC identity, then terminated only their retained
bootloader handles. Both reached zero job-owned processes and released the listener
**before** closing the test safety job. Standalone inventory worked without a desktop
parent or operator token and returned the exact ordered eight pets. Raw local report:
`build/frozen-lifetime-726-fix-02.xml`, with retained isolated profiles/logs alongside.
The first fixture attempt failed before readiness because its sanitized Windows
environment lacked a home directory; it was interrupted and repaired with isolated
profile/app-data/temp roots, not the real user's profile.

Negative control: retained old `4f8b567` bridge SHA-256
`B4B1FD6DD9402CB16D906FF917B95DF2091426C338FFBBDF8FF0F438A228CAAA`
failed the same lifetime assertion in **23.48s**, with **4 active job processes**
after bootloader death. The test then closed only its own job for cleanup; a process
inventory confirmed the old executable was absent afterward. Report:
`build/frozen-lifetime-old-negative-01.xml`. This is an expected negative-control
failure, not a passing old runtime or a failure of the new runtime.
The standalone inventory fixture was then additionally job-contained for timeout
cleanup and passed again in **10.40s** (`build/frozen-bundle-contained-01.xml`).
Final default focused gate: **34 passed, 5 skipped in 21.51s**; three skips are the
explicit opt-in frozen cases already exercised above. Scoped Ruff/whitespace passed.

The user pressed physical Escape again during the rebuilt-app window lookup.
All Computer Use stopped; no further app input is authorized until the user resumes
it. The new desktop and its bridge stayed alive beyond startup, but **native visual
restart/retry and pet visibility persistence remain unverified**. Frozen process
tests do not replace those UI gates or prove a final installer. There remains a narrow
pre-Python lifetime/PID-reuse edge; this patch does not claim atomic desktop job
containment of a payload stalled before Python can register its parent handles.

Ten consecutive real quiet repetitions completed on clean source `726a3d2`, each
using a new isolated Codex thread and the same `ping.txt=pong` completed-artifact
task. All ten passed. Exact requested worker: `gpt-5.3-codex-spark`; real supervisor:
Strands + `muse-spark-1.3-contributor-free`, no paid fallback. These are ten repeats
of one narrow case, **not ten varied coding tasks, a productivity benchmark, or
production existing-worker attachment proof**. Unique receipts and SQLite databases
are retained in `pex-release-final-9c/benchmarks/results/_scratch/quiet-repeat-726-01`
through `quiet-repeat-726-10`; do not use the overwritten global scratch receipt as
the earlier pair's original receipt. The earlier pair has its own unique retained dirs.
