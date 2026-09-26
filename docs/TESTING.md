# PEX testing guide

PEX is a Windows and Linux x64 desktop companion that supervises coding workers through their
supported local interfaces. The primary paths use OpenCode HTTP and an
isolated Codex App Server, and ships exactly two companions: Pex and Von.

## Main-branch verification checkpoints

Exact source `1e21082` passed the
[Windows and Ubuntu source workflow](https://github.com/josepha-mayo/pex/actions/runs/36252854380):
4,776 backend tests passed on Windows (12 skipped, 16 deselected), and 4,769
passed on Ubuntu (19 skipped, 16 deselected). Both desktop test suites and
production builds passed. This run did not execute native package jobs.

The later adapter workspace changes at `6a048c4` are undergoing the full
[source and native workflow](https://github.com/josepha-mayo/pex/actions/runs/36253951573).
Its result is pending; the earlier source checkpoint does not prove those
changes or the subsequent Context UI changes passed installed-app acceptance.

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
- Codex support means an isolated `codex app-server` connection, not control of
  an arbitrary private Codex desktop conversation.
- The installer is unsigned; source and SHA-256 hashes are published with the
  accepted candidate.
