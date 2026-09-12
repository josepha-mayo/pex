# PEX active handoff

**Shipping scope: [MVP_SHIP_GATE.md](MVP_SHIP_GATE.md).** Current official rules
make AgentCore deployment optional. Retain its tested implementation without
claiming deployment. The user's later small-MVP request takes priority over
historical expansion gates; formal four-arm scores remain unclaimed. The unsafe
933239a launcher instructions have been removed from the recording runbook.

Maintained checkpoint: 11 September 2026; current two-pet package and three frozen restart smokes passed.
**Submission status: NO-GO. The full goal remains active.**
Verify Git/current files and running processes before relying on this checkpoint.
This is the active entry point, not another historical log.

Joseph's latest working target is now two days. Keep the critical path narrow:
do not add integrations, pets, cloud deployment, or speculative UI rewrites. The
remaining product gate is current-package native acceptance followed by one
bounded OpenCode recovery/quiet pair, fresh recording assets, and the explicitly
authorized public release/submission actions. Offline audits on 11 September
found no new hot polling loop or reproducible source defect in the desktop-owned
bridge lifecycle; do not churn the accepted package without failing evidence.

## Latest verified checkpoint — supersedes historical status below

**12 September installed candidate checkpoint:** the current locked release is
product source `79d4d18`, stored in `build/release-candidate-79d4d18`; repository
head `30c3ac8` matched `origin/main` and the worktree was clean before the run.
The exact NSIS candidate installed successfully. The first packaged bridge
reached ready in 15.297 seconds; a normal window-close message removed the
desktop, its owned bridge and port 7420 listener in 2.976 seconds; reopen reached
ready in 7.703 seconds with exactly one bridge/listener. A 25-second idle sample
was flat and responsive, and 100/100 live health requests passed with 20.54 ms
p95 and 0.12 MB bridge growth. The installed secret-backed configuration names
Zen Muse Contributor Free and cap 3 without exposing the key. Exact evidence and
the remaining visual boundary are in
[`NATIVE_RUNTIME_79D4D18_2026-09-12.md`](demo/evidence/NATIVE_RUNTIME_79D4D18_2026-09-12.md).
The host computer-control runtime returned `apps: []`, so this is installed
runtime acceptance, not visual pet/navigation acceptance and not submission
readiness. The same source subsequently passed 11/11 focused pet/UI contracts
and a clean 71-module production build. A hidden 1280-by-720 rendered preview
showed no horizontal overflow on Home, Inspector, Deck, or any of the four
Settings tabs; this is browser-rendered corroboration, not native-overlay proof.
The complete installed process tree was then measured, correcting the earlier
two-process-only view: 331.6 MB private memory and roughly 652 MB aggregate
working set across ten desktop/bridge/WebView/helper processes. Over 20 seconds,
private memory changed by +0.07 MB, working set by -0.41 MB, and the tree used
3.1% of one logical core with no unresponsive window. It is heavier than ideal
but did not leak or freeze in that bound.

Same-day `four_arm.py readiness` remains an honest refusal, not a benchmark
pass: `coherent_runs:[]`, `can_freeze:false`, with missing OS-isolated hidden
evaluation, controller-enforced Cursor network evidence, complete immutable raw
logs, and synchronous same-session Cursor treatment. Do not run around those
gates or cite historical partial rows. The current OpenCode quiet/recovery pair
is the usable behavioral evidence, not a comparative score.

**Current package source: `619ea71`; base UI product change: `8394b4b`.** The package
now contains the exact Zen/Ask correction: the selected Muse model is sent to
`/v1/responses`, `muse-spark-1.3-contributor-free` is the first Zen suggestion
and default, and Ask PEX can retry a transient failure once only with that same
model. It never silently changes to a different Zen model. Ruff passed; 197
provider/BYOK/settings/security tests passed on ancestor `f585562`; the final
desktop suite passed 289 with
one platform skip after 503 lines of unreachable schema-2/eight-pet release code
and self-only tests were removed; production build passed. The clean Tauri build and immutable
package verifier report `release_ready: true` with zero blockers. Receipt
`build/pex-package-receipt-619ea71.json`, SHA-256
`a32cfb0db8db062baf18bb40fcb23ccea58589bf0c637a7c2103d8f6d181eaf4`.
[Exact package evidence](demo/evidence/PACKAGE_619EA71_2026-09-11.md). The frozen
runtime contains 2,372 files and zero retired hatch/image implementation paths.
Three sequential isolated authenticated restart smokes report the default
dispatch cap 3 and the correct first Zen hint, with no provider, worker, or AWS
call and no surviving bridge process. The exact packaged bridge SHA-256 is
`2db6b3169fff7e52ddce109d01d6dd1d63a00c6376d84e01cf57b76653f1c7d8`;
`scripts/smoke_packaged_bridge.py` makes this gate repeatable. Visible native
acceptance remains pending while Joseph uses the PC.

Post-package offline closure on 11 September adds four green gates without
changing package source: AgentCore client/runtime/pipeline/preflight **183/183**;
bridge BYOK/auth/lifecycle/two-pet critical paths **143 passed, 3 skipped**;
Strands/provider/evidence/runtime/recovery **241 passed, 4 skipped**; and the
goal-to-OpenCode-outcome cluster **244/244**. These used fake/local transports
and disabled provider/AWS calls. They strengthen the package's offline contract
but do not clear native UI or live semantic supervision.

Current source `6a1d98b` now also passes one freshly bounded live OpenCode quiet
case: exact output existed before the reviewed stop, real free Muse/Strands
selected `NOOP`, no follow-up was delivered, all 258 events settled, and the
owned OpenCode 1.18.30 server exited. The runner's new `--case-count 1` limit
prevents an automatic ten-case quota burn. This is not native-package proof or a
comparative benchmark. See
[`LIVE_OPENCODE_QUIET_6A1D98B_2026-09-11.md`](demo/evidence/LIVE_OPENCODE_QUIET_6A1D98B_2026-09-11.md).

The current-head offline MVP spine also passes 259/259 with unhandled pytest
thread warnings promoted to failures: goal lifecycle, quiet completion and
recovery, two-pet APIs, authenticated supervisor settings, Strands policy,
Zen provider/Ask routing, and local AgentCore. No live provider or AWS call ran.
Post-package exact-head checks also pass: desktop 290 with one intentional
Windows symlink skip, production TypeScript/Vite build with 69 modules, native
Rust ownership/security/window-close contracts 19/19, and release pet validation
with exactly `pex` and `von`. The first pet-validator command omitted the pinned
Rust directory from `PATH` and failed before validation; the corrected documented
environment passed. This was a toolchain-shell failure, not a product failure.

The final frontend-only delta makes pet visibility storage-safe. Throwing
WebView `getItem` no longer blanks startup, and throwing `setItem` no longer
prevents the current-launch hide/show event from reaching the other PEX
WebView. Focused pet contracts pass 18/18; the full desktop suite passes 292
with one platform skip; the production and full Tauri builds pass. The new MSI
and NSIS pass the immutable verifier with zero blockers. No PEX window was
opened, so native hide/restore remains in the visible acceptance gate.

The judge-facing architecture source and PNG were regenerated on 11 September
as a more compact flow and an opaque dark RGB image that remains legible on
light Devpost pages. It shows the local evidence → Strands → verifier → policy
loop, Zen BYOK vault boundary, same-session worker action, durable audit, and
the optional AgentCore path explicitly marked **NOT DEPLOYED**.
The public [judge testing guide](JUDGE_TESTING.md) now gives the exact two-pet
OpenCode + Zen BYOK evaluation path without bundling a key or claiming a public
installer. There is no existing GitHub release/tag. Publish the accepted
installer and checksum only after the native gate passes and Joseph authorizes
that external release action.

Machine cleanup requested by Joseph is complete: Ollama and its common model
directories were already absent; the remaining unused WinGet `ggml.llamacpp`
runtime was found with no related process and successfully uninstalled on 11
September. `llama-server`, `llama-cli`, and the exact WinGet package now resolve
absent. No ambiguous shared model cache was deleted.

Fresh post-package contract gates on the same source are also green: an expanded
387-test Strands/supervisor/trajectory/evidence/outcome gate (6 skipped) and 183
local AgentCore tests (one opt-in live-cloud test skipped) both pass with
aiosqlite thread warnings promoted to errors. The earlier focused 253-test gate
also passed. In addition, 368 benchmark/Cursor/audit/execution-safety/scoring
integrity tests passed. The broad 368-test run emitted one aiosqlite
thread-shutdown warning. It did not
reproduce when the named test was rerun with thread warnings as errors, nor when
the entire owning Cursor contract passed 57/57 with that policy. Treat this as
a retained non-reproduced warning, not as a hidden pass or a proven product
defect. No provider, worker, AWS or native UI call occurred in these gates.

**Previous package source: `56783bf`; UI product change: `8394b4b`.** The floating
overlay's actor width, remaining status-bubble width and hide-button anchor now
derive from the same user scale, closing the fixed-126px geometry that could make
the × drift or squeeze the bubble. Full desktop: 291 passed, one platform skip;
production build exit 0. Fresh hatch-pet checks on the exact shipped Pex/Von
atlases report valid RGBA WebP v2 1536×2288 assets with zero errors/warnings, and
the runtime contract reports 57 standard frames each with no repair. See
[two-pet audit](demo/evidence/PET_UI_AUDIT_8394B4B_2026-09-11.md). The clean
preflight, full Tauri build and corrected package verifier pass with zero
blockers. Receipt `build/package-56783bf-20260911-verified.json`, SHA-256
`cacf98bccd87f14673961d1479f13ee0aa791bbbade0f47364695e76f8393e64`.
[Exact package evidence](demo/evidence/PACKAGE_56783BF_2026-09-11.md). The
packaged frozen bridge also passed isolated liveness, authenticated settings and
fresh-install cap-3 checks with no provider/worker/AWS call. Visible native
acceptance was still pending at that checkpoint; `f585562` supersedes it.

Submission-asset audit found that the five root-level `docs/demo` screenshots
and two duplicate short WebMs showed the retired sparse eight-pet browser UI and
Hatch/Import controls. The PNGs and byte-identical WebMs are now quarantined
under `docs/demo/archive/legacy-eight-pet/`. Do not use them in the gallery or
final video. Capture a fresh current-package Home/overlay/two-pet Settings/
BYOK/Inspector set only after native
acceptance. The public README, STATUS, hackathon track and submission checklist
now point to package `06a0e2b`, base UI product `8394b4b` and the current full-regression
evidence.

Installed OpenCode advanced to `1.18.30`. A fresh model-free production-adapter
smoke on loopback port 4097 now passes the corrected live contract once plus five
consecutive reruns (0.87–0.96 seconds), progressing Strong → Deep after the
`/global/event` SSE handshake. The old live test asserted Deep immediately after
starting an asynchronous pump and failed twice on scheduler timing; it now waits
at most five seconds for the real condition and closes `LiveHttpTransport` in
cleanup. Product code did not change. Port 4097 and the empty probe workspace
were removed afterward. See
[OpenCode 1.18.30 evidence](demo/evidence/OPENCODE_HTTP_PROTOCOL_1_18_30_2026-09-11.md).

Official Zen documentation refreshed 11 September still lists
`muse-spark-1.3-contributor-free` as free on the Responses endpoint, while plain
`muse-spark-1.3` is paid. It also documents account auto-reload and contributor-
model prompt/completion training use. Do not make the final live call until the
signed-in account visibly confirms auto-reload is disabled; use only the public
throwaway demo workspace and never fall back to the paid ID. The PEX three-
dispatch cap is a usage bound, not a dollar guarantee.

Current offline reruns after packaging are green: BYOK/provider/configuration
210 passed with one intentional Windows symlink skip; OpenCode/Codex
cancellation, lineage and correction 137 passed; AgentCore local contracts 183
passed with the opt-in cloud test skipped. The exact frozen bridge lifetime and
standalone manifest gate passes 3/3. That last gate exposed and removed one stale
hard-coded eight-pet assertion; it now requires only Pex and Von. No live model
or AWS call ran in these checks.

Current benchmark integrity also reran green: 261 benchmark/Cursor-hook/audit/
execution-safety/public-summary/scoring tests plus 22 disjoint policy-scoring and
speculative-execution tests, 283/283 total. This is contract evidence, not a live
score; `benchmarks/manifest.yaml` remains honestly `frozen: false`. See
[current offline MVP gate](demo/evidence/OFFLINE_MVP_GATE_A58AD4F_2026-09-11.md).

**Current full Python regression is green on source `dd06443`: 4,436 passed,
32 skipped, zero failures/errors in 2,743.56 seconds (exit 0).** The retained
JUnit artifact is `build/full-offline-dd06443-20260911.xml`, 718,224 bytes,
SHA-256 `a9aae1f63ad0206df6083b0069b710005683701139fac59ece2238390fa843c2`.
No matching PEX or repository pytest process remained afterward. This clean run
supersedes three stopped diagnostic attempts: those exposed a stale pre-cap pet
allowance assertion and two Windows-contention-sensitive test-only waits. The
assertion now requires the safe default 3/3 allowance; the bounded fixture and
fresh-subprocess waits were raised without changing production timeouts or
runtime behavior. Exact affected-file reruns and Ruff passed before the clean
whole-suite run. That regression predates the narrow exact-Zen source change;
the affected provider/BYOK/settings/security slice passes 197 on `f585562`.

**Prior package source: `204c766`; product change: `7bf591c`.** Product `7bf591c` changes
the fresh-install supervisor default from unbounded to three durable semantic
dispatches per worker session. This both bounds BYOK usage and enables the paced
trajectory-review path. The Settings override remains available. Ruff and 126
affected pipeline/settings tests pass; the broader provider/source/settings
slice passes 156 with one intentional provider skip. The desktop suite still
passes 290 with one platform skip. The full Tauri rebuild and corrected package
verifier now pass with
zero blockers and 2,375 matching runtime files. Receipt
`build/package-204c766-20260911-verified.json`, SHA-256
`16375f7afc60df94fdc5bec230f5b61bac6c7e1ebdc96124576786369cbcc2ce`.
[Exact installer hashes and limits](demo/evidence/PACKAGE_204C766_2026-09-11.md).
The packaged frozen bridge also passed an isolated headless settings smoke:
public liveness became ready and authenticated `/v1/supervisor` reported the
fresh-install cap of three. No provider, worker or AWS call ran. Visible native
verification remains pending; do not describe this package as accepted.

**Pre-cap packaged candidate: `567778b` (superseded by `204c766`).** Its clean full Tauri build completed;
MSI and NSIS verification passes with zero blockers and 2,375 matching runtime
files. Receipt `build/package-567778b-20260910-rebuilt.json`, SHA-256
`9bda2583d3307dd7470002fec4e419f7ba4700a7fd9e9dcb393132222de7185e`.
Documentation/evidence head `70a9c5c` publishes the exact installer hashes and
claim boundary in
`demo/evidence/PACKAGE_567778B_2026-09-11.md`; it does not change product code.
An earlier verification against stale pre-commit installer artifacts correctly
failed with runtime/helper mismatches; retain
`build/package-567778b-20260910.json` as failed evidence. `567778b` includes the
Ask overflow repair and explicit OpenCode cancellation fence. Source gates:
290 frontend passed/one platform skip, production build passed, 77 focused
supervision/continuity tests passed, and 228 Ask + offline AgentCore tests passed.
Current BYOK/provider contracts also pass **148 tests with one intentional skip**;
the supplied Zen key has zero tracked-source matches. Generic secret-pattern hits
are deliberate redaction fixtures in tests. No live provider call ran in this gate.
Current benchmark/scoring/execution-safety and Cursor-hook contracts pass
**280/280 in 284.29s**. This proves the gate and its fail-closed accounting, not
a productivity score: `benchmarks/manifest.yaml` remains `frozen: false` because
complete raw vendor logs and Cursor same-session treatment evidence are missing.
Current Tauri/Rust contracts pass **19/19**; release preflight exits 0 with clean
tracked inputs, exactly Pex/Von, current sidecars and verified toolchains/wiring.
An additional passive-resource audit found serialized 30–32 second desktop
reconciliation, hidden-webview suspension, coalesced event refresh and no pumps
for dormant transport adapters. Its focused backend tests pass **10/10** and the
desktop suite again passes **290/290 with one platform skip**. Source setup
contracts pass **8/8**. This supports the bounded design but does not causally
clear the historical whole-PC freeze or replace foreground native observation.
Preflight's `release_ready: false` is intentional; package readiness is proven
only by the separate green installer receipt above.
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
source-tested and packaged in `567778b`, but not yet natively verified. Idle-only
cancellation
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

## 11 September two-day MVP sprint checkpoint

The shipping scope is deliberately narrow: a polished two-pet desktop experience,
Zen BYOK, OpenCode as the primary live worker path, Codex as the second supported
path, Strands semantic supervision, the implemented/offline-tested AgentCore route,
and evidence-backed quiet/corrective behavior. Cursor and a live AgentCore deployment
remain optional behind the core journey. Do not widen the pet fleet or resurrect
retired UI/demo paths.

Latest cleanup removed 329 unreachable lines from the old schema-2/eight-pet release
validator in `apps/desktop/scripts/build-sidecar.mjs`. The active schema-4 compact
validator still bundles exactly `pex` and `von`; archived eight-pet review hashes are
retained only as immutable provenance. A release-contract source assertion prevents
the obsolete validator and error text from returning. Focused release-contract tests
passed 14/14 and the script parses. Complete desktop gates are rerun before push.

No native PEX window, browser, live provider, worker, or AWS resource was opened in
this batch because the user is currently using the computer. Continue safe offline
code/tests now. When the user explicitly yields the screen, the next critical gate is
bounded native acceptance on the exact packaged source, followed by the confirmed-free
Zen/OpenCode recovery and quiet-completion journeys. Keep benchmark scoring NO-GO and
`frozen:false` until raw, fair, citeable evidence exists.

The next offline cleanup removed 226 compiled/test lines belonging only to the retired
frontend hatch-generation flow: three unused DTOs plus disclosure, acknowledgement,
idempotency, request-building, and response-matching helpers. The live two-pet UI had
no callers for them. Backend import compatibility and catalog parsing were deliberately
left intact. The existing two-pet source contract now rejects restoration of these
helpers. Focused view-model tests passed 76/76; complete desktop tests passed 289 with
one intentional Windows symlink skip; TypeScript/Vite passed. This remains source-only
until a new exact-source package is built and verified.

Backend follow-up found that “disabled” hatch generation still loaded the old hatch,
image-provider, and SQLite registry stack on every bridge start. The active app no
longer imports or constructs that runtime, tracks hatch tasks, or touches hatch storage
for compatibility reads. POST remains authenticated, strictly validated, and returns
the explicit two-pet-MVP 409; capability is false; list is empty; job lookup is 404.
The standalone retired modules remain in source for now but are not imported by bridge
startup. Isolated import proof confirmed all three modules absent from `sys.modules`.
Focused tests passed 7/7, the broader app/pet/HTTP gate passed 111/111 with pinned
Rust on `PATH`, and Ruff passed. Native startup/RSS impact remains unmeasured.

## Previous verified fallback package: 9668bcc

Exact product source `9668bcc2afb5a080cfa0936d778c2f8c641544fa` now has a verified
MSI and NSIS candidate. The verifier reports `release_ready:true`, zero blockers;
the frozen bridge manifest has 2,372 files and zero retired hatch/image files.
Three sequential isolated bridge restarts passed identity/auth/supervisor checks
with Zen `muse-spark-1.3-contributor-free`, cap 3, and zero provider calls. Desktop
contracts passed 290 with one intentional Windows symlink skip. Rust passed 19/19
and release check/build are warning-free. The combined MVP backend spine passed
259/259 before packaging-only and test-only Rust changes.

Artifacts:

- MSI: 111,648,792 bytes, SHA-256 `6be4090ab5d4969dd923addbea31234bbb8d4579c32a50e7f7d4c6f5e20f51a2`.
- NSIS: 98,837,415 bytes, SHA-256 `6bf4154a058ddb6c54be71fd90084953447bb8c45850dca5fd3516cb6ef80db8`.
- Bridge SHA-256: `962b2ebee197865873d1e9b37c09e0e0886e8902df6be350d29f8029378c8ad1`.
- Receipt: `build/pex-package-receipt-9668bcc.json`, SHA-256 `27837dcb8263b4f4f32e1c6109f88ad1790d63ffe3fa83e5130c1fecc0df8b80`.
- Evidence: `docs/demo/evidence/PACKAGE_9668BCC_2026-09-11.md`.

Do not rebuild or modify product source casually: this is the exact verified fallback.
Remaining P0 work still needs the user's screen: bounded native UI/pet/startup/resource
acceptance, then confirmed-free live Zen/OpenCode corrective and quiet-completion
journeys. After those pass, capture the sub-five-minute demo and publish/submit only
with action-time authorization. AgentCore remains implemented and offline-tested,
not deployed; benchmark remains `frozen:false` and has no score claim.

## Full-regression repair: 570964b

The full Python suite first exposed one release-preflight failure when the
ordinary shell could not resolve `rustc`: preflight returned a truncated error
object instead of its full structured source audit. The release builder now
derives only the platform artifact tuple in that failure path, retains
`rust_toolchain_unavailable` as a blocker, emits the complete fleet/Git/sidecar/
toolchain report, and keeps `source_ready:false`. The exact failed node passes
without Rust on PATH; desktop tests pass 290 with one intentional platform skip;
the production frontend build passes. Commit `570964b1eb61ba220aa0edbff3e25a3952994ab6`
is pushed and clean.

With the pinned Rust 1.97.1 toolchain on PATH, the complete Python regression
passes **4,440 with 32 skipped in 2,342.58 seconds**, with unhandled pytest thread
exceptions promoted to failures. No provider, worker, browser, native PEX window
or AWS resource ran. [Exact evidence](demo/evidence/FULL_OFFLINE_570964B_2026-09-11.md).
Package `06a0e2b` below supersedes `9668bcc`; retain `9668bcc` only as a verified
fallback with its own immutable hashes.

## Latest verified package: 06a0e2b

Exact source `06a0e2b2d180b75dfe8ece27c9f55583a282b499` has a fresh verified
MSI and NSIS. The verifier reports `release_ready:true`, zero blockers; the
frozen runtime has 2,372 files, exactly Pex/Von, and zero retired hatch/image
implementation paths. Three sequential isolated bridge restarts passed
identity/auth/settings with exact Zen Contributor Free first, cap 3, zero
provider calls, no worker, cloud reasoning off, and zero surviving bridge
processes.

Artifacts:

- MSI: 111,644,696 bytes, SHA-256 `0d7083418eea9a662333a64e1c1c3c5ec284a566df1619b6b03f00b5ee66ba1c`.
- NSIS: 98,830,453 bytes, SHA-256 `4df2b82465d530f904196a20dc7655a6359881dc2fe0c585fe275c7445302e1f`.
- Bridge: 34,459,441 bytes, SHA-256 `fdf48337e4e24af26698a9420dea12a905adc571301b58f93fafaffdde6eabbf`.
- Receipt: `build/pex-package-receipt-06a0e2b.json`, SHA-256 `8e59ae84fbd6ca8ad34051d55a74cb2b720b628b37efdf199d88b4e18d3dc00b`.
- Evidence: `docs/demo/evidence/PACKAGE_06A0E2B_2026-09-11.md`.

One additional verifier attempt is preserved as
`build/pex-package-receipt-06a0e2b-failed-cleanup.json`: installer validation
completed, but Windows returned `EPERM` removing its temporary extraction tree,
so that attempt correctly stayed `release_ready:false`. The earlier successful
receipt above binds the same immutable installer hashes and is not overwritten.
The cleanup directory remains under the user Temp folder because the attempted
bounded removal was rejected by the execution policy; it is not part of either
installer or the repository.

Remaining P0 is now entirely live/native: UI and pet interaction plus bounded
foreground/active-worker stability, then the confirmed-free Zen/OpenCode
corrective and quiet journeys, fresh screenshots/video, authorized public
release, and submission. Do not claim AgentCore deployment or a benchmark score.

The installed OpenCode 1.18.30 production HTTP/session/SSE contract was rerun
after packaging in a fresh empty workspace: 1/1 passed in 1.32 seconds and the
adapter progressed Strong → Deep after the real event stream connected. The
owned server stopped, port 4097 had zero listeners, and the empty workspace was
removed. This used no worker, provider, saved key, browser, or native PEX window.

## 11 September current-source live proof and final package delta

Current-source OpenCode quiet behavior passed once on clean `6a1d98b`: exact
artifact before review, one real Muse/Strands `NOOP`, zero PEX follow-ups, all
258 events settled, and owned-server cleanup. A separate controlled incomplete
case on clean `93dfef3` passed the causal recovery contract: exact stage-one
state and missing final artifact at the first stop; zero prior follow-ups; one
independently verified, delivered correction in the same OpenCode session;
exact final artifacts; `goal_evidence_supported`; `helped:true`; then a final
model-backed `NOOP`. All 441 events settled. Both ran Ling 3.0 Flash Fin Free as
worker and Muse Spark 1.3 Contributor Free as the saved Zen BYOK supervisor; no
AWS or paid fallback was enabled. These are single public diagnostics, not a
comparative benchmark or native acceptance.

The recovery audit caught one presentation defect in the passing raw evidence:
the supervisor repeated the correct literal but invented a wrong parenthetical
byte count. Commit `a242a84` deterministically strips model-derived
parenthetical byte-count asides, instructs the supervisor not to invent derived
counts, and requires the independent verifier to reject unsupported numeric
claims. Focused loop/Strands/recovery tests pass 92/92; the expanded
Strands/provider/AgentCore/evidence gate passes 243 with 4 intentional skips;
Ruff and diff checks pass. This product fix is newer than package `06a0e2b` and
therefore requires one final exact-source rebuild and installer verification.

Evidence:

- [Quiet completion](demo/evidence/LIVE_OPENCODE_QUIET_6A1D98B_2026-09-11.md)
- [Causal recovery, raw limitation, and repair](demo/evidence/LIVE_OPENCODE_RECOVERY_93DFEF3_2026-09-11.md)

Immediate offline order: commit these receipts, build MSI/NSIS from the clean
resulting source with pinned Rust and two build jobs, run the package verifier
to a new exclusive receipt, run isolated packaged-bridge identity/settings
smokes with zero provider calls, then update this handoff with immutable hashes.
When the user releases the screen, perform only bounded PEX-window checks:
startup/retry/reopen, transparent two-pet overlay, calm motion, fixed hide and
message-dismiss controls, Home/Inspector/Deck/Settings, Zen BYOK, OpenCode
attach, and foreground/active-worker resources. Capture fresh screenshots and
a sub-five-minute demo only after those pass. Do not freeze or score the
comparative benchmark, claim AgentCore deployment, publish a release, or submit
without the corresponding evidence and action-time authority.

## Latest verified package: c3cc44c

The immediate rebuild above is complete. Exact source
`c3cc44c7fd23c8b5268acaa926e20face9f0bc25` produced fresh MSI and NSIS
installers. The package verifier exited 0 with `release_ready:true`, zero
blockers, both extracted inventories verified, a 2,372-file frozen runtime, and
the updated supervisor loop/prompt bytes. Three sequential isolated packaged
bridge restarts passed authenticated identity/settings with Zen Muse
Contributor Free first, dispatch cap 3, cloud reasoning and worker attachment
off, and zero provider calls. No PEX process or checked listener survived.

Artifacts:

- MSI: 111,652,888 bytes, SHA-256 `503fa9540c7d71f94613b2dc911aa0f50d70f3a47187a93eb9acede4e8e09a32`.
- NSIS: 98,831,110 bytes, SHA-256 `76ac6b5341a1954da974674533306fc0b89e588f108049fd8e80b154e3b2fe5e`.
- Bridge: 34,459,560 bytes, SHA-256 `2f7bc317498560bc0bfb135e62189ecef73fd023e8fbceef48fc46760e070eee`.
- Receipt: `build/pex-package-receipt-c3cc44c.json`, SHA-256
  `69a241f75467c1a7a9ce16e34c8a767312a216fb29c9d56dc06e2dded304c7e4`.
- Evidence: [package c3cc44c](demo/evidence/PACKAGE_C3CC44C_2026-09-11.md).

The first verifier command omitted pinned Rust from that separate shell and
failed before writing a receipt; the unchanged binaries passed after Rust
1.97.1 was explicitly restored to `PATH`. Do not describe that invocation error
as an installer failure. This package supersedes `06a0e2b` for final acceptance.

Remaining P0 is visible and bounded: when the user says the screen is free,
verify startup/retry/reopen, transparent Pex/Von overlay, calm motion, fixed
hide and dismiss controls, Home/Inspector/Deck/Settings, Zen BYOK, real
OpenCode attachment, and foreground/active-worker resources. Then capture fresh
screenshots and a sub-five-minute demo. Until then the installer is technically
verified but not visually accepted. Benchmark remains `frozen:false`; AgentCore
remains implemented/offline-tested rather than deployed.

## Current AgentCore-compatible local protocol recheck

On source `1ea1539` (product runtime identical to package `c3cc44c`), the real
`pex_supervisor.runtime` entrypoint passed its explicit deterministic-only
`local_http` contract on unused loopback port 18080. `/ping` and
`/invocations` both returned 200; schema and invocation identity matched; the
typed `NOOP` remained bound to session `smoke`; `used_llm:false`; and the owned
Uvicorn process shut down cleanly with no listener remaining. The exercised
`runtime.py` hash exactly matches the frozen package receipt. No model, AWS
credential, AgentCore cloud Runtime, worker, or native UI was used.

[Exact current receipt and limits](demo/evidence/LOCAL_AGENTCORE_PROTOCOL_1EA1539_2026-09-11.md).

## Final two-pet artifact audit before native acceptance

On clean `8cf2ae7`, the exact Pex and Von source atlases were revalidated using
the installed `hatch-pet` v2 workflow and bundled workspace Python. Both are
1536 x 2288 RGBA WebP atlases with 192 x 208 cells, `spriteVersionNumber: 2`,
zero validator errors/warnings, zero transparent-RGB residue, and zero opaque
chroma or fringe pixels. Their SHA-256 values exactly match the two-pet release
manifest and occur in the current `c3cc44c` package receipt. Fresh contact and
direction sheets received parent visual review; identities, state families,
opposite gaits, transparency, and cardinal/clockwise gaze semantics had no
static blocker. No risky regeneration was warranted.

The complete desktop contract command reran 290 tests: 289 passed, zero failed,
one intentional Windows symlink-permission skip. It covers the transparent
native canvas contract, scale-aware fixed pet hide button, separate persistent
status-message dismissal, calm/paused animation, hidden-view timer/poll/socket
cleanup, visibility races, and exactly two release pets. Exact evidence and
limitations: [final two-pet audit](demo/evidence/TWO_PET_FINAL_AUDIT_8CF2AE7_2026-09-11.md).

Do not call this native acceptance. The remaining P0 is unchanged and bounded:
when the user says the screen is free, run only the exact-package PEX checks for
startup/reopen, transparent overlay, live cadence, fixed hide/message controls,
Home/Inspector/Deck/Settings, Zen BYOK, OpenCode attachment, and bounded
foreground/active-worker resources. Then record the sub-five-minute demo.

## Broad offline MVP seam checkpoint

Clean `c70effb` passed a combined 17-file MVP seam regression: **475 passed, 1
skipped, 0 failed in 99.50 seconds**. The selection crosses supervisor settings
and provider binding, real Strands integration contracts, persistent goal
lifecycle/control, canonical Ask PEX, OpenCode completion/outcome/pump, Codex
same-thread correction, and AgentCore local protocol/authority. Exact command,
scope, and limits: [offline MVP demo seam](demo/evidence/MVP_DEMO_SEAM_C70EFFB_2026-09-11.md).

This makes native acceptance the critical path; do not widen the offline feature
scope or rewrite green core logic without a concrete failure. Continue preparing
the judge journey and failure-safe recording materials while the user owns the
screen, then run the bounded PEX-only pass as soon as they explicitly release it.

## Packaged bridge idle resource sample

On clean `899a824`, the exact frozen bridge used by package `c3cc44c` ran for a
bounded 30-second idle sample in an isolated profile and local/no-provider mode.
CPU advanced 0.109 seconds (about 0.36% of one core on average); private memory
was 78.4 -> 78.3 MiB; working set 97.2 -> 97.1 MiB; threads 11 -> 8; handles
259 -> 257. The owned process shut down normally and left zero exact bridge
instances/listeners. [Exact sample and limits](demo/evidence/PACKAGED_BRIDGE_IDLE_899A824_2026-09-11.md).

This rules out an obvious headless idle busy loop or short-window bridge leak.
It does not prove the complete desktop/WebView/GPU path or active-worker load;
retain those measurements in the bounded native pass.

## Current package after active-event burst repair: 761cbde

Package `761cbde` supersedes `c3cc44c`. A busy event stream previously woke up
to five derived UI refresh families for each committed event page. Cursor
persistence remains immediate, but those goal/detail/handoff/identity reads now
share one cancellable 250 ms burst gate. This changes desktop observation load,
not backend supervision or model dispatch timing.

The complete desktop gate now has 291 tests: 290 passed, zero failed, one
intentional Windows symlink-permission skip. Production TypeScript/Vite passed.
The full release build passed with pinned Rust 1.97.1 and two Cargo jobs,
producing fresh bridge/Cursor sidecars, desktop, MSI and NSIS. The exclusive
package verifier reports `release_ready:true`, zero blockers, both inventories
verified and 2,372 runtime files. An isolated packaged-bridge smoke verified
identity and authenticated settings, cap 3, Zen Contributor Free first, zero
provider calls, and zero surviving exact bridge processes.

Exact hashes and limitations: [package 761cbde](demo/evidence/PACKAGE_761CBDE_2026-09-11.md).
Native acceptance remains pending and must target this package, not `c3cc44c`.

## Current package after bundled-pet resource repair: 6d18167

Package `6d18167` supersedes `761cbde`. Pex and Von are already bound by the
schema-4 release manifest, so both WebViews now use their stable bundled asset
URLs instead of repeatedly transferring and Pillow-validating the same large
atlases through the bridge. This also prevents selected Von from briefly showing
Pex while an asset request resolves. Unknown future IDs retain the authenticated
bridge fallback. No supervision, event, model or credential behavior changed.

Fresh hatch-pet v2 validation passed both atlases at RGBA `1536x2288` with no
structural errors/warnings and zero transparent-RGB residue. Normal-size contact
and direction sheets were inspected; heuristic continuity warnings remain review
evidence rather than proven defects, and this is not independent/native playback
approval. The desktop suite passed 291 with one intentional Windows symlink
skip; production build passed 71 modules. Full Tauri build, exclusive package
verification and packaged-bridge smoke all passed: `release_ready:true`, zero
blockers, both inventories verified, 2,372 runtime files, cap 3, Zen Contributor
Free first, zero provider calls and zero surviving bridge processes.

Exact hashes and limitations: [package 6d18167](demo/evidence/PACKAGE_6D18167_2026-09-11.md).
Native acceptance must now target `6d18167`.

## 11 September final two-day submission lock

Joseph has set a stricter internal target of two remaining days. Do not spend
that window expanding the product. The locked submission story is: two polished
pets, Zen BYOK, one real OpenCode same-session recovery, the corresponding quiet
NOOP case, honest Codex App Server support, Strands-backed bounded supervision,
and the tested local AgentCore-compatible protocol. Cursor and AWS deployment
remain optional and must not displace native acceptance, recording or submission.

The official Devpost requirements and judging rubric were refreshed at 17:16
UTC on 11 September in [the focused shipping gate](MVP_SHIP_GATE.md). Five areas
are equally weighted: Technical Implementation, Design, Potential Impact,
Creativity & Originality and Presentation. The organizer's latest announcement
explicitly favors deterministic agent behavior over more features. The
[recording runbook](demo/RECORDING_RUNBOOK.md) now makes same-worker steering,
read-only evidence tools, guardrails, quiet completion and source-bound proof
the center of the five-minute take.

The two updated documents pass `git diff --check`, and every local Markdown link
they contain resolves. Remaining P0 is unchanged: wait for Joseph to explicitly
release the screen, then perform the bounded exact-package native pass and record
only after it passes. Do not use computer control while he is working. Do not
acknowledge Devpost rules on his behalf, deploy paid infrastructure, publish an
installer, freeze/score the benchmark or submit without the required explicit
authority and evidence.

## Current exact-source package: 79d4d18

Commit `79d4d185a816f5d8b2be732f7b6dfff205d4ce91` built cleanly with
Rust 1.97.1 and `CARGO_BUILD_JOBS=2`. MSI and NSIS artifacts exist. The
exclusive verifier passed `release_ready:true` with zero blockers and exact
source, sidecar and canonical desktop hashes. The packaged bridge smoke passed
authenticated settings read, verified identity, Zen free model first in the
catalog, the three-dispatch cap and zero provider calls. Full commands, hashes
and boundaries are in [the package evidence](demo/evidence/PACKAGE_79D4D18_2026-09-11.md).

The only P0 product gate left before filming is bounded native acceptance of
this exact package: startup/reopen, transparent Pex and Von surfaces, calm pet
motion, close-message and hide/restore controls, Home/Inspector/Deck/Settings,
Zen BYOK display/save/test without exposing the secret, OpenCode attachment,
Ask PEX layout/cancel, and foreground/idle resource sanity. Run it only after
Joseph explicitly says the screen is free. Preserve `frozen:false`; do not
claim AgentCore cloud deployment, publish a release, acknowledge rules or
submit without the corresponding authority and evidence.

Post-package current-tree verification also passed 332 AgentCore/client/
pipeline/runtime/preflight plus supervisor-settings/provider/configuration tests
with two intentional opt-in skips in 125.83 seconds. Thread warnings were
promoted to errors. No AWS resource or provider call ran; preserve the explicit
implemented-and-offline-tested, not deployed, claim.

Current-head benchmark follow-through: `test_pexbench.py`, Cursor hooks, policy
scoring and speculative execution passed 236/236 in 871.91 seconds with thread
warnings promoted to errors. This is integrity/implementation evidence only.
No live arm ran, no comparative score exists, and `benchmarks/manifest.yaml`
must stay `frozen:false`.

The exact final PEX-only screen procedure is now pinned in
[the 79d4d18 native acceptance plan](demo/NATIVE_ACCEPTANCE_79D4D18.md). It is a
plan, not evidence. Follow it only after Joseph releases the screen, and retain
failures rather than checking items from source/tests alone.

## Full-tree resource observer correction

The read-only installed-app observer now emits explicit full-tree totals for
process count, private bytes, aggregate working-set bytes and lifetime CPU, and
includes private bytes on every owned process row. Its synthetic PID-reuse and
read-only-command test passes eight identity cases plus static coverage of all
five required metrics. A live three-sample run against the already-running
installed `79d4d18` candidate reported ten owned processes, about 350.6-351.2 MB
private memory and 686.1-686.5 MB aggregate working set. Those figures include
the desktop process, bridge, WebView renderers/GPU/utility/crash handler and
console host; aggregate working set can double-count shared pages. This is an
auditability repair, not a product-runtime or installer change, and it does not
prove long-duration leak freedom beyond the separate bounded stability sample.

## Current responsive agent-harness package: 067916a

Clean pushed source `067916aa71aa37f5d90e8f85145d35f23da8bd11`
supersedes `4ebebb6` with a narrow viewport repair: Inspector/Deck heading text
wraps and its action remains reachable instead of widening or clipping the page.
Desktop contracts passed 293 with one intentional Windows symlink skip; the
71-module production build and full Tauri release build passed. The exclusive
package verifier returned `release_ready:true` with zero blockers. Packaged Zen
settings smoke passed with Contributor Free first, cap three and zero provider
calls; frozen bridge lifetime passed 3/3. Retained MSI/NSIS hashes, installed
identity and exact boundaries are in
[package 067916a](demo/evidence/PACKAGE_067916A_2026-09-12.md).

An ordinary silent same-version install misleadingly returned zero while leaving
the predecessor executable. Hash comparison caught it. Explicitly selecting the
standard `%LOCALAPPDATA%\\PEX` path installed the new binary and restored all
uninstall metadata. Installed SHA-256 is
`6a510e8c5dfaf6323133e4227e749bb474ade3173317463e612977cb872e02b5`;
it differs from canonical `e878bb3f...` only in the expected three-byte Tauri
`UNK` to `NSS` marker. `/health/live` is healthy. A 60-second startup/idle sample
settled at ten processes and 377.49 MiB private; the final 35.5 seconds moved
only +0.36 MiB private with about 3.9% of one logical core. This is moderate but
not runaway, and is not a long-duration leak proof.

Visible native interaction remains open because computer control still exposes
no native app surface. Use
[the 067916a acceptance card](demo/NATIVE_ACCEPTANCE_067916A.md).

## Superseded agent-harness package: 4ebebb6

Clean pushed source `4ebebb6577029e7370f0e67d58bf35512cf9dfec` replaces the
sparse Home rail with an explicit OpenCode/Codex harness presentation, canonical
live/checking state, a larger companion and clearer visual hierarchy. Desktop
contracts passed 292 with one intentional platform skip; the production build
passed 71 modules; a fresh production preview was inspected without visible
overflow. Full Tauri release build completed with pinned Rust 1.97.1 and two
Cargo jobs. The exclusive verifier returned `release_ready:true` with zero
blockers, the packaged-settings smoke passed identity/authentication with Zen
Muse Contributor Free first, cap three and zero provider calls, and frozen-bridge
lifetime/bundle checks passed 3/3 with exactly Pex and Von. MSI and NSIS copies
are retained under `build/release-candidate-4ebebb6`. Exact hashes and boundaries:
[package 4ebebb6](demo/evidence/PACKAGE_4EBEBB6_2026-09-12.md).

The NSIS candidate is now installed at
`C:\Users\JosephMayo\AppData\Local\PEX\pex-desktop.exe` and launches its
desktop-owned bridge to authenticated ready state. This was not a measured cold
start: the later health poll observed ready in 0.756 seconds after the launch
command had already returned. A 20-second full-tree observer retained ten
samples with ten owned processes: private memory stayed between 325.14 and
328.56 MB and ended 0.24 MB below its first sample; aggregate working set fell
13.02 MB from 656.48 MB; lifetime CPU advanced 0.766 seconds. Aggregate working
set can double-count shared WebView pages. The sample is heavier than ideal but
shows neither bounded growth nor a runaway loop.

A fresh 60-second idle observer run after relaunch kept the same ten processes.
Private memory moved from 324.55 to 325.04 MB (+0.49 MB), aggregate working set
from 641.67 to 643.70 MB (+2.03 MB), and lifetime CPU advanced 1.8125 seconds
(about 3.0% of one logical core). This strengthens bounded stability but is not
an hours-long leak proof.

Installer identity audit found the expected three-byte Tauri `UNK` to `NSS`
bundle-marker transform, but an isolated `/D=` verification install temporarily
repointed PEX's shortcuts and uninstall metadata into
`build/native-install-4ebebb6`. Both shortcuts plus InstallLocation,
UninstallString and DisplayIcon were explicitly restored and read back against
`C:\Users\JosephMayo\AppData\Local\PEX`. The ignored temporary copy is not
running or referenced; it remains 171.18 MiB/2,376 files because its NSIS
uninstaller returned zero without removing it and the host denied recursive
deletion. It is disk-only residue, not part of the measured RAM footprint.

Installed SHA-256 is
`8caa884e92476d3cb115dbd3d791b809806f7c49b52409e8df36dd9816d48f34`.
It differs from the receipt's pre-bundle canonical desktop in exactly the three
bytes that change Tauri's bundle marker from `UNK` to `NSS`; all other bytes are
identical. Treat this as the expected NSIS transform, not an identity mismatch.

Visible native acceptance is still open because the computer-control host
continues to expose `apps: []`; do not infer pet motion, hide/restore, Settings
or overlay acceptance from the production-browser inspection. The installed
candidate is the correct package for Joseph's manual/native recording pass.

## Current-source MVP backend seam: 4069b11

The final combined submission-critical local selection passes **476 tests with
one intentional skip and zero failures in 220.44 seconds**. It covers Zen
BYOK/provider binding, Strands supervision, goals, Ask PEX, OpenCode, Codex and
the local AgentCore protocol/runtime. An earlier invalid live-run CLI timeout
was repaired at `4069b11` by validating arguments before importing the full
runtime. A later single HTTP 503 in the key-rotation contract did not reproduce
in five consecutive isolated runs, the full 60-test settings file, or the final
combined run; its assertion now preserves the safe response body if it recurs.
[Exact selection, chronology and boundaries](demo/evidence/MVP_SEAM_4069B11_2026-09-12.md).

No live secret/provider call, worker mutation or AWS deployment occurred in
this seam. Fresh formal benchmark readiness still reports `frozen:false`, no
coherent runs and `can_freeze:false`; do not invent an uplift score. The paired
real OpenCode quiet/recovery proof remains the honest live behavior demo.

Current public preflight on `bfcde36` also passes: local/remote main match,
GitHub reports public/main/MIT, required README/license/judge/submission and
architecture assets exist, and common high-entropy prefix matches are confined
to deliberate test fixtures. The required architecture PNG was visually checked
and honestly labels AgentCore as not deployed. Public installer and video URLs
remain missing. [Exact preflight](demo/evidence/PUBLIC_PREFLIGHT_BFCDE36_2026-09-12.md).

## Current OpenCode MVP closure: 150ea07

Clean pushed source `150ea07b205776660219dbfb1802ff86b998e8df` now passes
the paired free OpenCode supervision behaviors on the same exact source. Quiet
completion finished in 70.31 seconds with exact output, one Strands/Zen `NOOP`,
zero follow-ups and all 118 meaningful events settled. Controlled recovery
finished in 114.44 seconds: PEX observed exact stage one plus missing final,
deterministically recorded `missing:final.txt`, obtained an independently
verified `SEND_NUDGE`, delivered exactly one follow-up to the same session,
observed exact completion, recorded `goal_evidence_supported` and `helped:true`,
then returned a final model-backed `NOOP`. Both owned servers exited and the
source remained equal to `origin/main`.

The accepted pair follows four causal repairs: OpenCode cold session responses
receive a 30-second read bound while connect/write/pool remain eight; redundant
`message.part.delta` fragments do not enter the durable pump; ordinary progress
events remain durable/UI-visible but record-only instead of each running a full
decision; and OpenCode capability negotiation receives an eight-second bounded
probe rather than a false-negative two-second limit. True probe failure still
removes control and denies delivery. Verification: 259 OpenCode safety tests
with one environment skip, 552 expanded MVP seam tests with one environment
skip, 144 capability/OpenCode tests, 90 recovery/dispatch tests, Ruff and diff
checks all pass. [Exact evidence](demo/evidence/LIVE_OPENCODE_PAIR_150EA07_2026-09-11.md).

Immediate next order is fixed: manually accept the exact installed `067916a`
Home/Settings/Pex/Von interaction using
[the current ten-minute card](demo/NATIVE_ACCEPTANCE_067916A.md), then complete
the explicit Devpost rules-review gate, create the local Devpost draft, record
the maximum-five-minute OpenCode recovery/quiet story, and only then publish the
accepted installer and submit with the required architecture PNG, AWS Builder
ID, video URL and bonus-post URL. Do not add features, rerun paid models, claim
AgentCore cloud deployment, freeze the comparative benchmark, publish a release,
acknowledge rules, or submit without the missing authority and evidence.
