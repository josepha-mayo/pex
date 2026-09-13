# PEX judge testing guide

PEX is a Windows desktop companion that supervises coding workers through their
supported local interfaces. The focused submission supports OpenCode HTTP and an
isolated Codex App Server, and ships exactly two companions: Pex and Von.

## Fastest evaluation path

Download the current unsigned NSIS from
[PEX 0.1.0 RC2](https://github.com/josepha-mayo/pex/releases/tag/v0.1.0-rc2)
and verify SHA-256
`e405dbc55646fb08faf270b9ac0cb99b0c6a2f65a2e9310607fa2e08ff097eb1`.
Windows may show a publisher warning because this candidate is not code-signed.

Current published candidate: `0454122`. Its rebuilt installer, frozen bridge,
authenticated settings surface and package inventory passed. Fresh OpenCode and
Codex recovery plus quiet pairs remain source-applicable because the latest
delta is presentation-only. Repeat the exact-build installed visual card before
filming.
See [exact-copy/hash instructions](demo/SECOND_LAPTOP_ACCEPTANCE.md), or build
current source below.

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
profile, verifies authenticated identity plus Settings, disables worker/cloud
attachment, and owns the bridge in a kill-on-close Windows job.

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

## Configure Zen BYOK

Open **Settings → Supervisor**:

1. Choose provider **zen**.
2. Choose or paste `muse-spark-1.3-contributor-free`.
3. Keep authentication on **api key** and paste your own Zen key.
4. Keep the saved review limit at **3** for the bounded demo.
5. Choose **Save supervisor**.

The key field is write-only and the credential is stored in the operating-system
vault. Saving configuration does not test the key or prove inference. The model
label is not a billing guarantee; check the provider account and disable any
auto-reload before testing. PEX never silently changes to another model ID.

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
