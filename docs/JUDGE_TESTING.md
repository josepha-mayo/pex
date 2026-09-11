# PEX judge testing guide

PEX is a Windows desktop companion that supervises coding workers through their
supported local interfaces. The focused submission supports OpenCode HTTP and an
isolated Codex App Server, and ships exactly two companions: Pex and Von.

## Fastest evaluation path

The current installer candidate is unsigned. Its public download link will be
added only after the final native acceptance run. Until then, build from the
public source checkout using the pinned prerequisites in the README:

```powershell
.\scripts\install.ps1
npm --prefix apps/desktop run tauri dev
```

PEX starts without a cloud credential and remains honest about deterministic-
only observation. A semantic supervision demo requires a model configured by the
tester. No developer key is bundled.

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
- A deliberately incomplete task produces one evidence-specific correction on
  the same OpenCode session; PEX observes the resulting artifact before calling
  the intervention helpful.
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

