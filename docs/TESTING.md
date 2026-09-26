# PEX testing guide

PEX is a Windows and Linux x64 desktop companion that supervises coding workers through their
supported local interfaces. The primary paths use OpenCode HTTP and an
isolated Codex App Server, and ships exactly two companions: Pex and Von.

## Main-branch verification checkpoints

Exact source `ea049d2` also reported a green workflow in
[run 36258099806](https://github.com/josepha-mayo/pex/actions/runs/36258099806).
Its Ubuntu backend passed 4,802 tests and its 324 desktop tests passed. Windows
backend passed 4,809 tests, but the desktop log retained the same two
symlink-containment failures masked by the combined build step. Both native
packages passed 20 Rust tests, bridge identity and OS-vault/BYOK roundtrips with
zero provider calls. This does not establish full acceptance for that source.
The corrected workflow and canonical runtime-root handling at `a05958e` completed
in [run 36258789552](https://github.com/josepha-mayo/pex/actions/runs/36258789552).
Its Linux native job failed the installed fresh-state gate despite both software
renderer settings. The 60-second capture showed desktop recovery; the
post-failure input/capture showed Home. Packaging, 20 Rust tests, bridge identity
and Secret Service/BYOK checks passed with zero provider calls. Earlier visual
passes are exact-run evidence, not proof of reliable startup across builds.

Exact source `6edbb89` was reported green by all Windows and Ubuntu jobs in
[run 36257145205](https://github.com/josepha-mayo/pex/actions/runs/36257145205).
Ubuntu backend checks passed 4,791 tests (19 skipped, 16 deselected), and
all 324 desktop checks and the production build passed. Native packaging,
20 bootstrap tests, packaged
bridge identity, Secret Service storage, and the installed Home/Settings check
passed with the verified Xvfb software renderer. Windows native packaging,
bridge startup/identity, OS-vault and packaged BYOK checks also passed. Windows
backend checks passed 4,798 tests (12 skipped, 16 deselected), and its desktop
production build passed, but its desktop log contained 322 passes and two
symlink-containment failures. The combined PowerShell test/build step masked the
test failure with a successful build. Desktop tests and builds are now separate
steps so failure cannot be overwritten. Full acceptance for this source is not
claimed despite its workflow conclusion. Later context changes require their own
source and package acceptance; this is not a claim about latest HEAD.

The instrumented Linux package at `fd16129` still failed its fresh-state window
gate in [run 36255800464](https://github.com/josepha-mayo/pex/actions/runs/36255800464).
Its [startup diagnostic](evidence/linux-startup-ipc-fd16129.json) records prompt
native bootstrap returns and a 2 ms identity check. Ready-state polling continued
for over 80 seconds while the saved frame showed recovery; the post-failure
diagnostic capture showed Home. This points toward stale rendering, rather than
a blocked native status command, but does not prove a renderer cause or pass.
The overall workflow and Windows checks were still running when this diagnostic
was recorded.

That same package subsequently passed both
[combined-renderer replay 36256759610](https://github.com/josepha-mayo/pex/actions/runs/36256759610)
and [confirmation 36256944664](https://github.com/josepha-mayo/pex/actions/runs/36256944664)
with `WEBKIT_DISABLE_COMPOSITING_MODE=1` and `LIBGL_ALWAYS_SOFTWARE=1`.
Both retained the existing 90-second bridge/window and 60-second fresh-state
gates, Settings navigation, hidden overlay, and anonymous HTTP 401 checks.
The native CI Xvfb step now uses this verified combination. The production app
does not impose these overrides on users, and hardware-backed Linux rendering
is not established by a headless software-renderer replay.

Exact source `1e21082` passed the
[Windows and Ubuntu source workflow](https://github.com/josepha-mayo/pex/actions/runs/36252854380):
4,776 backend tests passed on Windows (12 skipped, 16 deselected), and 4,769
passed on Ubuntu (19 skipped, 16 deselected). Both production builds and Ubuntu
desktop tests passed. A subsequent log audit found the same two Windows desktop
symlink-containment failures masked by the successful build step; its reported
green result is not complete acceptance. This run did not execute native jobs.

The later adapter workspace changes at `6a048c4` completed the full
[source and native workflow](https://github.com/josepha-mayo/pex/actions/runs/36253951573).
Windows native packaging, authenticated bridge startup, OS-vault and packaged
BYOK checks passed. Ubuntu source checks passed, but its installed-window smoke
failed before fresh state was visible. The
[exact-package default-renderer replay](https://github.com/josepha-mayo/pex/actions/runs/36254900699)
also failed; a
[software-compositing replay](https://github.com/josepha-mayo/pex/actions/runs/36254914344)
passed Home, Settings, hidden pet and anonymous HTTP 401 checks, but its
[confirmation replay](https://github.com/josepha-mayo/pex/actions/runs/36255116707)
failed the fresh-state gate. Software compositing therefore remains a diagnostic
option and is not the CI default. The installed product's renderer is unchanged.
These results do not establish reliable physical-Linux startup or
accept the subsequent Context UI changes. Windows source finished with one
failure and 4,789 passing tests: the model-constructor quarantine test's 250 ms
health check expired during adapter probing. Its worker had started and remained
blocked. The test now checks cheap `/health/live` and the actual supervisor
settings read under the same deadline, retaining quarantine and rollback checks;
six focused activation/cancellation tests passed locally. This is a corrected
responsiveness contract, not proof of a repaired model-activation race.

Exact source `907395e` passed the full
[Windows and Ubuntu workflow](https://github.com/josepha-mayo/pex/actions/runs/36246994582):
source tests and desktop builds, native NSIS/DEB packages, authenticated packaged
bridge startup, native credential storage, and the installed Linux Home/Settings
visual smoke. Native bridge readiness is delivered to the webview as a typed
event, with bounded polling retained for recovery. This is Ubuntu/Xvfb evidence,
not a physical Linux workstation acceptance claim.

The later `28032d9` package had an intermittent Linux startup-smoke failure in
[its original run](https://github.com/josepha-mayo/pex/actions/runs/36248029746):
the bridge logged readiness, but the combined visible-window/anonymous-HTTP
condition did not pass within 90 seconds. The
[exact-package diagnostic replay](https://github.com/josepha-mayo/pex/actions/runs/36248956418)
passed Home, Settings, hidden pet, and anonymous HTTP 401 checks in a fresh
profile. Both outcomes remain relevant; the replay is not a startup repair or
proof of consistent native reliability. The smoke now captures window names,
HTTP status, and a screenshot if that early condition fails again.

The connection UI at `c0220d6` was exercised in browser mode against a
throwaway, test-scoped local bridge with cloud reasoning disabled. The Codex CLI
button completed a real isolated App Server handshake, returned Basic support,
and populated Home with available CLI threads; no model turn was requested.
This does not establish control of an arbitrary open Codex desktop task.

## Fastest evaluation path

**Current release candidate:** download
[PEX 0.1.0 RC24](https://github.com/josepha-mayo/pex/releases/tag/v0.1.0-rc24),
built from exact release source `263a30b`. Windows and Ubuntu CI on its product code
source suites and desktop builds passed. Local Windows NSIS/MSI package
verification and packaged-bridge smoke passed; the tagged Ubuntu workflow built
the Debian/AppImage packages and smoked its bundled bridge. A
bounded live Nemotron Super call retained from the audited BYOK path passed on
the global Token Factory endpoint; RC24 packaging made no paid provider call. See
[`docs/evidence/nebius-live-proof.json`](evidence/nebius-live-proof.json).
The retained live OpenCode pair also passed: one already-correct case produced
a model-backed `NOOP` with zero follow-ups, while one controlled false test claim
triggered a bound pytest request, same-session repair, independent passing rerun,
and final `NOOP`. See
[`docs/evidence/nebius-opencode-proof.json`](evidence/nebius-opencode-proof.json).
A later bounded run with the free `mimo-v2.6-flash-free` OpenCode worker did not
finish: PEX caught the false test claim and requested the failing suite and
parser repair, but the worker remained busy after repeated edits. Its final
file passed a post-run test, which is not a verified completed worker turn.
The failure is retained in
[`docs/evidence/nebius-opencode-free-worker-stall-2026-09-24.json`](evidence/nebius-opencode-free-worker-stall-2026-09-24.json).
A second bounded run reached a different failure: the full suite failed, but
the verifier omitted its dedicated citation field, so PEX sent no correction.
That receipt is retained in
[`docs/evidence/nebius-opencode-verifier-citation-2026-09-24.json`](evidence/nebius-opencode-verifier-citation-2026-09-24.json).
A third bounded run stayed silent on the first false claim because the main
decision cited an inspection receipt but omitted its separate evidence list.
See [`docs/evidence/nebius-opencode-main-evidence-2026-09-24.json`](evidence/nebius-opencode-main-evidence-2026-09-24.json).
After the receipt-handling changes, one bounded live retry with the free-labeled
OpenCode worker and Nebius BYOK supervisor passed: PEX observed a false test
claim, requested verification, sent a same-session correction, and an
independent pytest rerun passed. The final review was quiet. See
[`docs/evidence/nebius-opencode-free-worker-recovery-54366ca.json`](evidence/nebius-opencode-free-worker-recovery-54366ca.json).
This is one recovery case, not a comparative productivity result or native
desktop acceptance.
A controlled paired retry on exact source `9c505e0` used the same free OpenCode
worker, public task, test file, and deliberately inadequate project checker in
both arms. The unsupervised worker finished with independent pytest exit 1.
With PEX attached, the initial independent pytest also exited 1; PEX sent two
same-session follow-ups, and the final independent pytest exited 0. The PEX
arm used 10 Nemotron supervisor calls and took 175.14 seconds, versus 52.47
seconds for the baseline. The baseline raw SSE was retained locally; the PEX
arm retained processed events and its review journal, but this runner did not
capture its raw SSE. See
[`docs/evidence/opencode-controlled-recovery-pair-9c505e0.json`](evidence/opencode-controlled-recovery-pair-9c505e0.json).
This is a single controlled diagnostic with an extra persistent goal in the
PEX arm, not a representative reliability or productivity benchmark. The
current pair reporter now requires raw SSE from both arms, so this older
uncaptured pair remains historical evidence rather than an admitted pair.
The same false-claim scenario was repeated on source `6682328` with a free
OpenCode worker in both arms and a Nebius Nemotron supervisor only in the PEX
arm. The independent pytest failed before and after the baseline worker's
completed turn (exit 1). In the PEX arm it failed initially (exit 1), then
passed after two same-session follow-ups (exit 0). The matched-task and raw-SSE
pair validator passed with no blockers. PEX took 238.67 seconds and 10
supervisor model calls, versus 39.14 seconds for baseline; this demonstrates
one recovery at a substantial time and inference cost, not a general speed or
reliability gain. See
[`docs/evidence/opencode-controlled-recovery-pair-6682328.json`](evidence/opencode-controlled-recovery-pair-6682328.json).
The current no-spend OpenCode diagnostic also passed 10/10 baseline and 10/10
PEX-attached public artifact tasks on exact source `63dc5cd`. Every PEX case
settled its event journal, produced an exact local deterministic `NOOP`, sent no
follow-up, and made zero supervisor model calls. See
[`docs/evidence/opencode-deterministic-paired-diagnostic-63dc5cd.json`](evidence/opencode-deterministic-paired-diagnostic-63dc5cd.json).
This is attachment, observation, restraint, and overhead evidence; semantic
supervision was disabled and it is not a productivity benchmark.
On exact source `a957c2d`, a further no-spend controlled recovery pair used the
same free OpenCode worker and public false-test-claim task in both arms. The
unassisted worker completed with independent pytest still failing (exit 1).
With PEX's deterministic supervisor attached, the initial pytest also failed;
PEX requested verification, sent a same-session correction, and the final
independent pytest passed (exit 0). The final review was quiet, and PEX made
zero supervisor model calls. Both arms retained raw SSE and passed the matched
pair validator. PEX took 129.12 seconds versus 43.23 seconds without it. See
[`docs/evidence/opencode-deterministic-recovery-pair-a957c2d.json`](evidence/opencode-deterministic-recovery-pair-a957c2d.json).
This one controlled diagnostic does not establish a general reliability rate,
speedup, Nebius semantic-model performance, or native desktop acceptance.
On exact source `8c059c0`, a second no-spend pair tested context recovery across
two stages. Both free OpenCode workers created the exact first-stage artifact and
stopped with the final artifact absent. The baseline stayed incomplete (43.61
seconds). PEX carried the final-file acceptance criterion into one same-session
correction; the treatment worker wrote the exact final bytes, and PEX's next
review was `NOOP` (98.86 seconds, zero supervisor model calls). The matched
pair validator passed with raw SSE from both arms. See
[`docs/evidence/opencode-deterministic-two-stage-recovery-pair-8c059c0.json`](evidence/opencode-deterministic-two-stage-recovery-pair-8c059c0.json).
Earlier attempts on `e08e1c2` retained failed local OpenCode GET observations;
they were excluded from this pair. This single result demonstrates a specific
context handoff, not a general performance or native desktop claim.
Privacy-safe earlier-build Home, Inspector, and Settings screenshots are retained
under [`docs/demo/assets`](demo/assets), with hashes and browser-mode boundaries
in [`docs/evidence/ui-browser-rc13.json`](evidence/ui-browser-rc13.json).

<details>
<summary>Historical RC7 package instructions and evidence</summary>

Download the matching package from
[PEX 0.1.0 RC7](https://github.com/josepha-mayo/pex/releases/tag/v0.1.0-rc7)
and verify it against the attached `SHA256SUMS-rc7.txt`. Windows users should
choose the NSIS `PEX_0.1.0_x64-setup.exe`; Debian-family users should choose the
`.deb`; other graphical x64 Linux users should choose the AppImage. Windows may
show a publisher warning because this candidate is not code-signed.

Current package source: `600d1de`. Its rebuilt Windows installers, frozen
bridge, authenticated settings surface, package inventory, and packaged
executable hashes passed. Ubuntu 24.04 also passed all 309 desktop contracts,
built AppImage and Debian packages, and booted the packaged bridge through the
authenticated Settings check. Fresh OpenCode recovery and a quiet control pass
with Zen BYOK and Strands on the unchanged supervisor runtime. Codex App Server
integration passes the focused automated gate; neither behavior pair was rerun
for the packaging-only RC7 delta. Repeat the exact-build installed visual card
before filming, especially on Linux.
Build current source below, or use the package instructions in the README.

</details>

To build from the public source checkout instead, use the pinned prerequisites
in the README:

```powershell
.\scripts\install.ps1
npm --prefix apps/desktop run tauri dev
```

To check an installed Codex App Server without starting a model turn, run
`.\.venv\Scripts\python.exe scripts\smoke_codex_handshake.py` on Windows or
`.venv/bin/python scripts/smoke_codex_handshake.py` on Linux after installing
the project dependencies. It starts a separate local App Server, completes the
handshake and a bounded thread-list request, then closes it. This proves
connectivity only; it does not prove supervision of a worker turn or a
performance improvement.

PEX starts without a cloud credential and remains honest about deterministic-
only observation. A semantic supervision demo requires a model configured by the
tester. No developer key is bundled.

After a release build, the packaged local bridge defaults can be checked without
opening PEX or calling a model:

```powershell
.\.venv\Scripts\python.exe .\scripts\smoke_packaged_bridge.py `
  --exe .\apps\desktop\src-tauri\binaries\pex-bridge-runtime\pex-bridge.exe `
  --output .\build\packaged-settings-smoke.json
```

The command refuses a loose development executable, uses an isolated temporary
profile, verifies authenticated identity plus Settings, and disables
worker/cloud attachment. The CI gate runs the corresponding `pex-bridge` path
on Linux.

## Connect OpenCode

From a small throwaway project, start one local server:

```powershell
opencode serve --port 4096
```

In a second terminal, attach to it:

```powershell
opencode attach http://127.0.0.1:4096
```

Or use the OpenCode Desktop server picker to connect to
`http://127.0.0.1:4096` instead of starting the second terminal.

In PEX, open **Settings → Connections**, keep the loopback address
`http://127.0.0.1:4096`, and choose **Connect OpenCode**. Create or resume the
worker session in the attached terminal or Desktop app first; connecting PEX does not create a
task or restart OpenCode. Return Home, select the worker, and attach a persistent
goal with observable acceptance criteria.

## Configure Nebius Token Factory BYOK

Open **Settings → Supervisor**:

1. Choose provider **Nebius Token Factory**.
2. Choose `nvidia/nemotron-3-super-120b-a12b`, or another NVIDIA open-source
   model confirmed available to the tester's account.
3. Keep authentication on **api key** and paste your own Nebius Token Factory key.
4. Keep the saved review limit at **3** for the bounded demo.
5. Choose **Save supervisor**.

The key field is write-only and the credential is stored in the operating-system
vault. Saving configuration does not test the key or prove inference. Confirm a
successful receipt in Inspector and retain its exact provider and model identity.
PEX never silently changes to another model ID.

## What to verify

- Home names the selected worker and its attached persistent goal.
- The companion message can be dismissed without hiding the pet.
- The pet can be hidden and restored from Companion settings.
- Pex and Von are the only available companions.
- A genuinely complete task produces a model-backed **NOOP** and no worker
  follow-up.
- A deliberately incomplete task produces an evidence-specific correction on
  the same OpenCode session; PEX observes the resulting artifact before calling
  the intervention helpful.
- Additional defects may require further bounded review. PEX never promotes an
  intervention to helpful until its observed outcome is supported.
- Pausing supervision prevents new semantic dispatches.

The Inspector exposes the goal, evidence, structured decision, delivery state,
and outcome. The local policy guard remains authoritative even when a model or
optional AgentCore endpoint proposes an action.

## Honest boundaries

- Runtime-tree containment canonicalizes the root through native realpath before
  comparing resolved symlink targets. This avoids false escapes from ancestor
  aliases or Windows short/long path spellings while retaining rejection of a
  symlink root, escaping targets, dangling links and directory targets. All nine
  runtime-contract tests passed under WSL, including an ancestor-alias regression.
  Local Windows desktop checks passed 320 tests with five symlink-permission
  skips; privileged Windows execution still requires the corrected CI run.
- Compaction recovery excludes facts expired at the observation time, including
  facts that were valid during compaction but expired before the recovery check.
  Future-dated reads cannot establish a current forgotten-fact signal. Expired
  decision counts remain available as health diagnostics; they are not restored
  as working instructions. Health and planner regressions passed 63 tests.
- Context health identifies files by their complete lexical path rather than
  basename. POSIX case and literal backslashes remain distinct; relative paths
  are joined to a known absolute project root, with conservative Windows path
  normalization. This prevents another directory's reads from minting a
  forgotten-fact signal, or its edits from hiding one. Path matching here is a
  telemetry signal, not a filesystem identity or correctness proof. Context
  health, mesh and supervisor-context checks passed 75 tests.
- Handoffs include active project-wide human constraints in the mandatory contract,
  preserving full redacted text even after an earlier delivery. The immutable
  project check remains required at selection, reservation, and dispatch.
  Shared worker-authored records are not admitted as human constraints, and
  foreign-goal/project, private, expired and superseded records remain excluded.
  An insufficient token budget rejects the contract rather than shortening a
  prohibition. Goal-wide optional evidence retains its bounded selection.
  Context and reservation checks passed 62 tests, including the new reserved-to-
  delivered shared-constraint case. Handoff permissions, timeout safety and
  assimilation checks passed another 72 tests. These are controlled local
  adapter checks; live worker/model effectiveness still requires separate proof.
- Supervisor context retirement is applied before the Store page limit. The
  observation-time query checks all replacements in the same immutable project
  binding and current goal/shared scope, including expired replacements. This
  prevents a prioritized human constraint from returning merely because its
  replacement fell outside the 256-record page. Future replacements do not
  retire current context. Ordinary history/UI queries retain their existing
  behavior; the supervisor opts into this observation-time selection.
- Exact supervisor `get_context_items(context_id=...)` lookups return the full
  offered content, rather than clipping it again at 1,200 characters. The
  envelope still caps each record at 2,000 characters and now carries
  `content_truncated` when the sanitized source exceeded that cap. Page previews
  expose `source_content_truncated`; missing source text is not complete authority.
  The tail-constraint and source-truncation regressions, context selection, and
  Codex supervision pipeline passed (22 tests). Evidence tools and observation
  receipts passed 61 tests with four platform skips. These checks use no live
  model calls and do not prove live inference quality.
- Exact `get_decisions(decision_id=...)` reads likewise preserve the offered
  statement, rationale and scope. Each field reports whether source selection
  shortened it; list summaries expose the same source flags. Approval and privacy
  tail restrictions are covered by regressions. The combined context, evidence
  tools and receipt suite passed 81 tests with four platform skips. Rejected
  alternatives remain bounded previews, and large UTF-8 outputs still use the
  existing explicitly marked observation limit.
- A writable Linux worker-tool primitive passed the retained WSL smoke in
  [`linux-worker-boundary-wsl-2026-09-26.json`](evidence/linux-worker-boundary-wsl-2026-09-26.json):
  task reads/writes worked while the private oracle, controller source, and
  controller environment were unavailable; only loopback was visible. The
  receipt binds the boundary and smoke source hashes. Live coding-harness/model
  transport and isolated PEX integration remain unverified, so this does not
  satisfy the natural-task benchmark execution gate.
- The OpenCode paired diagnostic retains completed task failures. It reports
  worker correctness separately from the restraint diagnostic, and does not stop
  sampling merely because a completed case failed. Metrics require every
  requested case, complete worker observations, settled PEX reviews, and intact
  raw SSE evidence. Infrastructure aborts and partial samples are not compared.
- Amazon Bedrock AgentCore support is implemented and offline-tested; no
  deployed AgentCore Runtime is claimed.
- PexBench is unfrozen; no comparative productivity score is claimed.
- The Linux supervisor boundary primitive mounts a controller-curated public
  runtime and task read-only, exposes only a dedicated request/response control
  directory, clears inherited environment, disables model loading and excludes
  host networking. Seven WSL boundary checks passed, including a probe child
  denied access to a private host file, controller environment and listening
  socket, and denied writes to task/runtime/request while writing its response.
  Local Windows boundary/execution-safety checks passed 21 tests with five Linux
  skips. This initial run was a boundary probe, not the actual PEX decision child.
  Workspace payload rebinding, live model transport and
  complete action-time receipts remain required; the execution gate stays shut.
- Opt-in installed startup traces now include the last React-committed surface
  reported through the existing bootstrap status call. Rust accepts only five
  fixed names (unmounted, recovery, main, settings, pet), and the existing trace
  switch and bounded output apply. No DOM text, URLs or credentials are read.
  This diagnoses frontend-transition versus captured-frame differences; it
  does not bypass authentication or establish a startup fix. Production build
  and 320 local desktop checks passed, with five Windows permission skips.
  Native compilation and installed behavior require the next exact-source run.
- Compaction recovery excludes stored artifact/result/fact file-state records
  that predate a later observed edit of the associated file. Recovery can use
  the latest edit description, but an undescribed edit does not revive the old
  state. Durable decisions and constraints survive file edits. The combined
  context-health/planner suite passed 85 tests and both backend recovery cases
  passed. These records remain in the ledger; only their use as current
  file-state recovery evidence changes.
- Context health no longer uses repeated reads that precede a later edit of
  the same file to trigger forgotten-fact recovery. When no durable item supplies
  the fact, fallback edit evidence uses the latest observed description; an
  undescribed latest edit does not revive an older description. Context-health
  and planner checks passed 81 tests. Two backend compaction cases confirmed
  delivery of recovery without an edit and cooldown suppression of the ledger
  nudge after an edit, with no context-health overlay in the latter case.
- Routine read permission classification preserves POSIX case and uses Windows
  drive path semantics for Windows workers. Case-fold collisions, drive-relative
  paths, rooted paths without a drive, UNC paths and alternate data streams do
  not qualify for low-risk automatic approval. Ordinary workspace reads still
  qualify. Planner/policy checks passed 84 tests and three existing end-to-end
  permission scenarios passed. This is lexical classification, not a filesystem
  identity or symlink-containment witness.
- The Now view puts current workers and their controls before historical
  attention measurements. History expands on demand without changing metric
  values or coverage labels. Browser review at 1280px and 800px confirmed visible
  worker controls and expandable, scrollable history. The production build
  passed; local Windows desktop checks passed 320 tests with five symlink
  permission skips. This browser check used a disposable, unauthenticated bridge
  with cloud reasoning and automatic dispatch disabled, not live worker control.
- Deterministic debug and compaction recovery overlays preserve worker tools.
  Repeated errors or forgotten facts alone do not establish that browser/search
  access is irrelevant. Recovery still pins the reproduction and durable goal
  context. Planner and delivered compaction-overlay regressions passed 49 tests;
  these are offline checks, not evidence of live model performance.
- Codex support means an isolated `codex app-server` connection, not control of
  an arbitrary private Codex desktop conversation.
- The installer is unsigned; source and SHA-256 hashes are published with the
  accepted candidate.

- The actual offline PEX decision child ran inside the Linux supervisor boundary.
  Its public task required `report.json`; the worker reported completion while
  the public observation contained no files. PEX returned `SEND_NUDGE` naming
  the missing artifact, with `used_llm=false`, zero tokens and no worker dispatch.
  The [decision receipt](evidence/linux-isolated-supervisor-decision-2026-09-26.json)
  binds the retained request, response and runtime manifest hashes. The curated
  runtime contains only public PEX packages and dependency wheels matching
  `uv.lock`, excluding controller/evaluator sources and credentials. This proves
  an offline decision, not live worker improvement or comparative performance.
  The first attempt exposed an installed-package crash in checkout-only dotenv
  discovery. Dotenv now loads only from a verified source-checkout layout;
  packaged providers do not probe arbitrary ancestors. Runtime, provider and
  execution-safety checks passed 113 tests; the strengthened oversized-dotenv
  check and three other dotenv cases passed afterward. Full benchmark integration,
  live model transport and complete action-time receipts remain outstanding.
- Exact source `a05958e` Windows backend passed 4,818 tests (12 skipped,
  16 deselected), and all 325 desktop checks passed without skips, including
  privileged symlink containment. Its Linux installed visual gate still failed.
- Exact source `a2dff00` Linux native job in
  [run 36260871093](https://github.com/josepha-mayo/pex/actions/runs/36260871093)
  passed 21 Rust tests, bridge identity, Secret Service/BYOK storage and the
  installed fresh-profile Home/Settings visual gate with zero provider calls.
  The [installed receipt](evidence/linux-installed-smoke-a2dff00.json) and
  [startup trace](evidence/linux-startup-ipc-a2dff00.txt) retain that result.
  React reported main at 1,106 ms and settings at 2,966 ms. The Home screenshot
  was also inspected. This is an exact-run pass; the preceding visual failure
  remains relevant to startup reliability, and live worker quality is unproven.
- The comparison supervision loop now has an explicit `offline_runtime` option.
  It validates host session identity before mapping cwd/project to `/workspace`,
  uses the audited Linux boundary, forwards no host environment and records
  request/response SHA-256 hashes in each action audit. Host-executed pytest
  evidence and public-test execution are refused in this mode rather than
  relabelled as isolated evidence. Live inference reports are also refused.
  An actual WSL loop smoke used a controlled worker: missing `report.json` led
  to `SEND_NUDGE`, one same-session continuation created the report, and the
  next isolated PEX decision returned `NOOP`. The retained
  [loop receipt](evidence/linux-isolated-supervision-loop-2026-09-26.json) and
  [exact driver](evidence/linux-isolated-supervision-loop-driver.txt) identify
  this controlled scope. No Codex model turn, provider call, public pytest,
  natural-task benchmark eligibility or performance improvement is claimed.  The broad local run recorded 165 passes and six failures. Two new fixture
  failures were corrected; four exposed an import-order dependency in the
  evaluator test loader, now loaded with its package-qualified module name.
  All ten targeted checks passed after those repairs. Three fingerprint cases
  also passed: controller identity now includes the sandbox and runtime builder
  alongside the Codex protocol journal. The entire broad suite was not rerun.
- Exact-source run `36260871093` at `a2dff00` completed successfully in all
  four jobs. Retained job logs show Ubuntu backend 4,834 passed (19 skipped,
  16 deselected), Windows backend 4,841 passed (12 skipped, 16 deselected),
  and desktop 325 passed with zero failures/skips on both platforms. Both
  production builds passed. Native packages passed 21 Rust tests apiece,
  identity and OS-vault/BYOK roundtrips with zero provider calls. Linux also
  passed its installed fresh-profile Home/Settings visual check. This evidence
  belongs to that source; subsequent integration changes require their own CI.
- First-run guidance distinguishes connecting a running OpenCode session from
  creating an isolated Codex connection. A detected worker without control
  remains explicitly unavailable for goal attachment and supervision. Browser
  verification used a disposable bridge with cloud reasoning disabled and zero
  automatic dispatch allowance. Home-to-Connections navigation worked, both
  connection paths were visible, and Home/Connections had no horizontal overflow
  at 800px. The bridge/tab/dev server were closed afterward. Eight first-run
  checks and the production build passed. No worker was connected in this UI
  check, and no model turn or provider call was started.
- Stopping after a typed nonzero pytest exit is unfinished work even when no
  completion claim was extracted and the `ok` flag is absent or inconsistent.
  PEX now returns an acceptance gap with the observed event ID and exit code,
  rather than remaining silent. Later observed file edits retire that failure
  as current evidence; boolean/string exit values do not prove a failed run.
  Four regression cases reproduced silence before the fix. Verification,
  claim-protocol and planner checks passed 182 tests. Three backend scenarios
  passed, including two actual same-session synthetic deliveries of the exit-2
  correction and the existing false-claim scenario. Seven focused checks passed
  after adding explicit exit-code provenance. No live inference was used.
- Artifact verification preserves POSIX filename case and literal backslashes.
  `REPORT.json` no longer satisfies a Linux requirement for `report.json`, and
  the row count of a case-distinct artifact cannot substitute for the required
  file. Windows drive/UNC snapshot names retain ASCII case-insensitive matching;
  unclassified roots use exact spelling. Content/row/existence fallback reads
  are limited to native absolute workspace roots, preventing foreign snapshot
  paths from resolving against the controller host. Four regressions reproduced
  incorrect acceptance before the fix. Windows verification/exact-content/LF
  checks passed 157 tests with one Linux-only skip. All seven path checks passed
  in WSL, including an actual case-sensitive directory; system pytest emitted
  two unknown asyncio-config warnings. Three existing backend correction cases
  also passed. These are offline verification checks, not live model results.