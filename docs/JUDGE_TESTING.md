# PEX judge testing guide

PEX is a Windows and Linux x64 desktop companion that supervises coding workers through their
supported local interfaces. The focused submission supports OpenCode HTTP and an
isolated Codex App Server, and ships exactly two companions: Pex and Von.

## Fastest evaluation path

**Current Nebius/NVIDIA candidate:** download
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
The current no-spend OpenCode diagnostic also passed 10/10 baseline and 10/10
PEX-attached public artifact tasks on exact source `63dc5cd`. Every PEX case
settled its event journal, produced an exact local deterministic `NOOP`, sent no
follow-up, and made zero supervisor model calls. See
[`docs/evidence/opencode-deterministic-paired-diagnostic-63dc5cd.json`](evidence/opencode-deterministic-paired-diagnostic-63dc5cd.json).
This is attachment, observation, restraint, and overhead evidence; semantic
supervision was disabled and it is not a productivity benchmark.
Privacy-safe earlier-build Home, Inspector, and Settings screenshots are retained
under [`docs/demo/assets`](demo/assets), with hashes and browser-mode boundaries
in [`docs/evidence/ui-browser-rc13.json`](evidence/ui-browser-rc13.json). A public
under-three-minute video remains required before submission.

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

From a small throwaway project, keep one local server and its attached terminal
open:

```powershell
opencode serve --port 4096
opencode attach http://127.0.0.1:4096
```

In PEX, open **Settings → Connections**, keep the loopback address
`http://127.0.0.1:4096`, and choose **Connect OpenCode**. Create or resume the
worker session in the OpenCode terminal first; connecting PEX does not create a
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

- Amazon Bedrock AgentCore support is implemented and offline-tested, but the
  submission does not claim a deployed AgentCore Runtime.
- PexBench is unfrozen; no comparative productivity score is claimed.
- Codex support means an isolated `codex app-server` connection, not control of
  an arbitrary private Codex desktop conversation.
- The installer is unsigned; source and SHA-256 hashes are published with the
  accepted candidate.
- Devpost requires a free judge-accessible working demo or test build, a public
  YouTube video under three minutes, product feedback, and an explanation of
  the significant post-August-26 updates. See `devpost-submission.md`.
