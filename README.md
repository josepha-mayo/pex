# PEX

**PEX turns you from a full-time manager of AI agents into the owner of goals and decisions.**

It is a goal-aware adaptive supervisor that lives *above* Cursor, Codex, Claude Code, OpenCode, and other coding agents you already use. It is not another coding harness, not a Kanban board, and not a chat UI that makes you babysit a babysitter.

**MVP in final validation — 11 September 2026.** The shipping focus is OpenCode,
Codex App Server, Zen BYOK and a small, controllable desktop companion. Native
OpenCode + Strands has demonstrated same-worker correction, exact artifact
recovery, a helped outcome and quiet completion. Codex App Server has separate
real recovery/quiet proofs; this is not control of arbitrary Codex desktop tasks.
Package source `16153b3` (base UI product `8394b4b`) ships only Pex and Von,
defaults fresh installs to three semantic review dispatches per session, and passes both installer
content/inventory gates. It also routes Zen Muse through Responses and forbids
silent model fallback. The most recent full Python regression passed 4,436 tests
with 32 skips and zero failures/errors at `dd06443`; it predates the narrow
exact-Zen change, whose affected provider/BYOK/settings/security slice passes
197 tests on package source `f585562`. An earlier package passed
native unpacked-runtime startup, pet transparency, dismissal/hiding and
selected-session Ask checks; the newest scale-aware overlay, Ask layout and
explicit-cancellation repairs still need bounded native checks.
The latest live OpenCode run hit its free-provider quota and is not a benchmark pass;
provider-limit blocking and idle suppression now pass a native negative-case
check with zero additional reviews or nudges. Final stability and recording remain.
Installed OpenCode 1.18.30 also passes a fresh model-free production HTTP/session/
SSE smoke, reaching Deep after the real event-stream handshake; this does not
replace the separate model-backed recovery evidence.
AgentCore is implemented and tested but **not deployed**;
deployment is optional under the current contest rules. No formal comparative
benchmark score is claimed. See [the focused shipping gate](docs/MVP_SHIP_GATE.md),
[current package evidence](docs/demo/evidence/PACKAGE_16153B3_2026-09-11.md),
[current status](STATUS.md), and the source-bound evidence linked there.

## The pain it removes

Running several long-lived coding agents created a new job: remembering the real goal, noticing drift, catching false “done”, approving the same safe test command, copying context between windows, and typing “continue”.

PEX attaches to those sessions and does that mechanical work. You keep intent, priorities, and irreversible decisions.

## Why this is not another orchestrator

PEX does not require work to start inside PEX. Existing tools stay usable. Context belongs to the project/goal, not a chat transcript. Interventions are typed, policy-gated, reversible when possible, and audited.

## Supported harnesses

| Harness | Current label | Surface |
| --- | --- | --- |
| Synthetic | Deep | In-process reference adapter (tests/demo) |
| Cursor | Strong / Basic / Unavailable | Official hooks are Strong; optional verified ACP without hook observation is Basic |
| Codex | Deep / Observe-only / Unavailable | Isolated `codex app-server` JSON-RPC when attached. ChatGPT.exe is observe/focus only. |
| OpenCode | Deep / Unavailable | `opencode serve` HTTP when attached |
| Qwen Code | Strong / Basic / Unavailable | Strong only after negotiated HTTP plus a session-bound SSE stream, or a live official hook |
| Claude Code, Kimi, Grok Build, OMP, Hermes | Strong / Basic / Unavailable | Provider hooks/plugins or capability-gated ACP; Hermes hook-only is Basic |
| Devin | Basic / Unavailable | Thinner official organization API |
| Pi | Unavailable | Registered target; no verified provider-specific adapter yet |
| Grok Bot | Observe-only | Not Grok Build |
| Prime, ZCode, DeepSeek | Unavailable | Registered targets pending exact provider-specific integrations |

See [`INTEGRATIONS.md`](INTEGRATIONS.md) for the live matrix.

Judges and evaluators can follow the focused [testing guide](docs/JUDGE_TESTING.md)
for the two-pet OpenCode/Zen path and its exact claim boundaries.

## Pets

The desktop is designed around a compact command surface and a separate transparent,
always-on-top pet overlay. Transparency and controls passed bounded native checks;
prolonged stability is not yet claimed. It supervises existing harnesses.

- Exactly two companions: **Pex**, the owl, and **Von**, the dark-navy cat, selected in Settings → Companion.
- Uses reviewed **Codex v2** atlases (`1536×2288`, `spriteVersionNumber: 2`), restrained playback and manual dragging. The overlay does not roam or hop on hover.
- Separate controls hide the pet or dismiss only its status message; the pet can be restored from Settings. Both actions were observed independently in native checks.
- Custom imports and image generation are disabled in this MVP, including their write APIs. Existing legacy import metadata is preserved; retired selections fall back to Pex.
- Both current installer inventories contain only Pex and Von. See the [shipping gate](docs/MVP_SHIP_GATE.md) for current source-bound checks and remaining limits.

## Benchmark headline

Four-arm experiment: Cursor / Cursor+PEX / Codex / Codex+PEX.

Paired arms share one `TASK.md` and equivalent workspaces. The PEX supervisor decides in a separate process on public observations only. The deterministic development smoke has five recovery tasks plus three source-pinned public QuixBugs repairs and is **unfrozen**: an OS-enforced hidden-data/no-network worker boundary is still missing, existing rows predate the current 32-row suite/integrity contract, and Cursor+PEX still lacks complete same-session/raw-log evidence. **There is no citeable impact score or validated public leaderboard rank yet.** Do not cite quarantined leakage runs.

## Quick start

### Windows source prerequisites

This public repository provides a **source-development bootstrap**, not a packaged installer.
A verified local Windows
installer candidate exists for package source `16153b3` (base UI product `8394b4b`) and
is not code-signed.
These instructions cover building from source; package integrity is not native
acceptance or publisher trust. Current source-bound package evidence is recorded
in the [active handoff](docs/AGENT_HANDOFF.md). To build from source,
install Git and `uv`, Node matching [`.node-version`](.node-version),
and Rust matching [`rust-toolchain.toml`](rust-toolchain.toml). A Windows Tauri
build also needs the Microsoft C++ build tools and WebView2 runtime. `uv` uses
the Python version in [`.python-version`](.python-version) and installs the
workspace, test tools, and PyInstaller into `.venv`; do not substitute an
unrelated global Python.

From the repository root, run:

```powershell
.\scripts\install.ps1
npm --prefix apps/desktop run tauri dev
```

The setup script checks the required command-line tools, runs `uv sync --dev`,
uses the locked npm dependency graph with `npm ci`, and prepares all three
required desktop sidecars: the bridge, Cursor control hook, and Cursor observer.
It stops on a failed native command. It does **not** install hooks or modify
Cursor's global configuration. To run those steps manually:

```powershell
uv sync --dev
npm --prefix apps/desktop ci
npm --prefix apps/desktop run prepare:sidecar
npm --prefix apps/desktop run tauri dev
```

Tauri starts its owned authenticated bridge, proves its identity with a fresh
nonce, and only then releases its in-memory bearer to the local UI. An unknown
process already occupying port 7420 makes startup fail closed. A successful
source build is not evidence that a packaged installer or release bundle passed
its clean-profile checks. Native desktop startup explicitly uses the standard
`~/.pex/pex.sqlite` profile; ambient `PEX_HOME` or `PEX_DB_PATH` values from a
benchmark shell do not redirect the owned bridge. Provider configuration remains
explicit and local as documented below.

### Connect a worker

Connect or start a real worker before attaching a persistent goal. The current
Agents view discovers candidates but has no generic worker **Attach** button;
the Inspector's **Attach goal** control only binds a stored goal to an already
live vendor session.

For OpenCode, start the official server in the exact worker project first:

```powershell
Set-Location C:\path\to\worker-project
opencode serve --port 4096
```

Keep that server running. In another terminal, attach the OpenCode interface to
the **same** server and create or resume a worker session there:

```powershell
opencode attach http://127.0.0.1:4096
```

A newly started server may have no sessions: connecting PEX alone does not
create one. Running plain `opencode` in another terminal can open a different
backend; use the explicit attach address. Configure the worker's provider/model
in OpenCode separately from PEX's supervisor provider. These commands follow the
[official OpenCode CLI interface](https://opencode.ai/docs/cli/#attach).

In PEX, choose **Connect a worker → Connect your local OpenCode server**, enter
`http://127.0.0.1:4096`, then choose **Connect OpenCode**. Return Home, select the
worker and set its persistent goal. Connecting does not start a worker turn.
The quick-connect form supports unauthenticated loopback servers only; do not
put the Zen key in the server address.

Alternatively, set the loopback origin before starting PEX from a second shell:

```powershell
$env:PEX_OPENCODE_URL="http://127.0.0.1:4096"
npm --prefix apps/desktop run tauri dev
```

If the OpenCode server uses Basic authentication, give both processes the same
official `OPENCODE_SERVER_USERNAME` and `OPENCODE_SERVER_PASSWORD` values. PEX
rejects credentials embedded in the URL and does not treat a desktop TUI process
as the HTTP control surface. The optional session-scoped overlay is documented
in [`integrations/opencode-plugin/README.md`](integrations/opencode-plugin/README.md).

If Codex CLI is installed, this starts a new isolated Codex App Server transport;
it does not take control of ChatGPT.exe or an arbitrary existing Codex task:

```powershell
$env:PEX_CODEX_ATTACH="1"
npm --prefix apps/desktop run tauri dev
```

Cursor hook installation is a separate, explicit opt-in. This source command
changes the current user's `~/.cursor/hooks.json`, writes observe-only hooks that
refer to this checkout, and backs up an existing file as
`hooks.json.pex-backup`:

```powershell
uv run python integrations/cursor-hook/install.py
```

Observe-only hooks do not prove that a continuation reached the same Cursor
worker. Do not run that command merely to install PEX dependencies, and do not
move or delete the checkout while those source-backed hooks are active. The
scoped hook credential for a chosen project is provisioned separately in
**Settings → Worker integrations** before starting the hooked worker.

For rollback, inspect both `hooks.json` and `hooks.json.pex-backup` first. The
backup is only the state seen immediately before the most recent PEX install;
later Cursor or user edits may exist in the current file. Do not restore the
backup blindly. If it is the confirmed desired pre-install state and no later
entries must be retained, close Cursor before restoring that reviewed file.
Otherwise remove only the PEX command entries and preserve every unrelated
hook. There is not yet an automated uninstall command.

### Configure PEX and attach intent

With no supervisor provider configured, PEX stays on deterministic triage and
reports `used_llm=false`; it does not invent model-backed supervision. To enable
semantic supervision, open **Settings → Supervisor inference**, select the
provider/model and credential source, and save it. Provider setup is independent
of worker attachment.

After a genuine vendor session appears, create or select a stored goal and use
the Inspector's **Attach goal** control. Only then should supervised work begin.
On a genuinely attached control surface, PEX can inspect evidence and issue a
specific policy-gated continuation. Observe-only surfaces never claim delivery.

Raw-browser no-auth operation is not available from an environment variable or
release CLI; it exists only inside explicit in-process Python test harnesses via
`Settings.for_test(...)`.

## Architecture

![PEX architecture](docs/architecture/pex-architecture.png)

Editable diagram: [Mermaid source](docs/architecture/pex-architecture.mmd).

User input is the pet and persistent goals. Each semantic inspection can create a
fresh bounded Strands supervisor with request-scoped, read-only evidence tools
for canonical goal/session state, events, context, decisions, workspace/git/file
inspection, configured verification, and bounded public-web evidence. Exact
sanitized tool returns are captured as request-, event-, stage-, and
invocation-bound observations; the model must cite valid observation IDs for a
non-NOOP proposal. A returned observation proves what the tool returned, not
that the model understood it or that an intervention helped. A model-originated
STOP intervention must also pass a fresh independent verifier Agent using its
own observations and invocation. Timeout, malformed output, missing evidence,
or rejection becomes NOOP. Deterministic verification truth and local policy
still own the final boundary. Bedrock AgentCore Runtime is a hardened deploy
target, not a deployed-service claim. Historical source `933239a` has a retained real
OpenCode recovery: main Strands inference inspected the workspace, a separate verifier approved
the exact missing-artifact finding, policy admitted one same-session correction, and the free
worker produced the exact final bytes. A separate correctly completed OpenCode task produced a
model-backed `NOOP` and zero PEX follow-ups. See the
[recovery](docs/demo/evidence/LIVE_OPENCODE_PEX_CLOSED_LOOP_2026-09-09.md) and
[quiet](docs/demo/evidence/LIVE_OPENCODE_QUIET_2026-09-09.md) receipts. Real Codex restraint and
same-thread recovery are also retained on packaged ancestor `9357bb8`. This does not prove the
outstanding bounded native stability run, ten-case quiet statistics, AgentCore deployment, or a
benchmark result.

The cloud supervisor can propose actions. It cannot bypass local policy.

Full diagram notes: [`docs/architecture/hackathon.md`](docs/architecture/hackathon.md).

## Hackathon

Built for the AWS + Devpost [Agents for Humans Hackathon](https://agentsforhumans.devpost.com/), Professional Agents track. PEX uses Strands Agents locally and implements an optional AgentCore Runtime path, which is not deployed. Source-bound native OpenCode and separate Codex App Server behavior proofs are retained. Final native/setup checks and the demo/submission remain pending under [the focused MVP gate](docs/MVP_SHIP_GATE.md). Optional cloud deployment and the uncompleted formal research benchmark are not contest-entry prerequisites; no comparative score or leaderboard rank is claimed. Canonical draft: [submission copy](docs/SUBMISSION.md).

- License: MIT
- Devpost copy and demo script: [`docs/SUBMISSION.md`](docs/SUBMISSION.md)
- Spec: [`docs/PEX_BUILD_SPEC.md`](docs/PEX_BUILD_SPEC.md)
- Hackathon/AWS track: [`docs/HACKATHON_TRACK.md`](docs/HACKATHON_TRACK.md)
- Why not an orchestrator: [`docs/DIFFERENTIATION.md`](docs/DIFFERENTIATION.md)
- Status: [`STATUS.md`](STATUS.md)
