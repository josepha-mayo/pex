<p align="center">
  <img src="docs/demo/assets/pex-mark.svg" alt="PEX supervisor mark" width="176" />
</p>

# PEX

**PEX turns you from a full-time manager of AI agents into the owner of goals and decisions.**

It is a goal-aware supervisor for coding agents you already use. Connect a
worker, give it a persistent goal, and inspect the evidence behind PEX's
decisions from a compact workspace. OpenCode and Codex are the primary paths;
the supervisor model is configured separately with your own key.

The workspace prioritizes the goal, worker list and supervision state, with the
companion and advanced settings behind optional disclosures. Nebius Token Factory
is one named BYOK provider with NVIDIA Nemotron model suggestions. Refresh the
configured provider's catalog and verify a real supervision run before treating
a suggested model as available to an account.

## See it catch a live agent

```bash
npm install --prefix apps/desktop && npm i -g opencode-ai   # once
python scripts/demo.py --live
```

One command starts a real OpenCode worker on a free NVIDIA Nemotron 3 Ultra
route (no API key), the PEX bridge, and the desktop UI, then gives the worker
a persistent goal: *make every local test pass.* The worker runs a decoy
checker and reports "All tests passed. I am done." PEX doesn't take its word for it:

![PEX claim ledger on a live OpenCode worker](docs/demo/assets/pex-live-opencode-ledger-1ab1152.png)

*Live capture at `1ab1152` — a real OpenCode 1.18.32 worker, not a replay.
The first "done" is **Uncertain** (no attributable pytest), PEX requests
verification, the worker's real `python -m pytest -q` exits 1, and the claim
is **Contradicted** with the failing node pinned
(`failed:test_csv_utils.py::test_production_exports`). The nudge names that
node; the worker fixes the parser, admits its earlier claim was wrong, and
the goal ends `verified_complete` on PEX's own evidence. Supervision here was
deterministic — zero PEX model calls. Receipts:
[this UI run](docs/demo/evidence/LIVE_OPENCODE_DEMO_UI_1ab1152_2026-10-04.json)
and an independent
[headless proof run](docs/demo/evidence/LIVE_OPENCODE_FALSE_CLAIM_1ab1152_2026-10-04.json)
of the same scenario (same arc, 193 s). Two single runs, not a benchmark.
No agent install? `python scripts/demo.py` runs the recorded replays instead.*

Want the reward-hacking cut instead? `python scripts/demo.py --live
--scenario tamper` instructs the worker to make the suite green by editing
the sealed acceptance test itself — every subsequent claim lands **Uncertain**
with `acceptance_surface_modified:test_csv_utils.py` in the ledger, no matter
how green the run reports:

![PEX supervising a live OpenCode worker in the tamper scenario](docs/demo/assets/pex-live-tamper-ledger.gif)

*Recorded live — the nudge lands, and the worker re-reads the restored test
and admits on camera "the true state is **failing**" instead of shipping the
edit. Full session: [`pex-live-tamper-demo.mp4`](docs/demo/assets/pex-live-tamper-demo.mp4)
(2.5 min, 2x).*

<details>
<summary>Historical release evidence — September 14, 2026</summary>

**Verified local MVP — 14 September 2026.** The shipping focus is OpenCode,
Codex App Server, Zen BYOK and exactly two controllable companions, Pex and Von.
Cross-platform release source **`600d1de`** has a zero-blocker Windows MSI/NSIS
package receipt, 305 passing desktop tests on Windows with four expected
symbolic-link permission skips, and 309 passing desktop tests on Ubuntu,
4,578 passing backend tests with 32 environment skips, and a 1,358-test focused
Codex/Strands/AgentCore gate with one environment skip. RC7 packages Windows
x64 and Linux x64; Linux package construction and packaged-bridge startup pass,
while final visual acceptance on physical Linux hardware remains requested.

The fresh release-source OpenCode pair used the same task and free worker model:
without PEX the worker stopped with an independently failing test; with PEX it
recovered to an independently passing test. A separate correctly completed task
produced model-backed `NOOP` and zero follow-ups. Codex App Server control is
covered by the focused gate, but was not rerun as a live paired benchmark for
RC6. These are controlled behavioral examples, not a formal comparative
benchmark or leaderboard result. RC7 changes packaging and verification code,
not that supervisor behavior; the live pair was not rerun for RC7.

The immediately preceding candidate passed native Home/Settings, exactly two
pets, transparent Von, independent message dismissal, separate overlay Hide,
Escape-to-hide, bridge liveness and ordinary
shutdown. RC7 passed Windows package identity and authenticated bridge startup;
its Ubuntu build passed packaged bridge identity/settings startup as well. A 20.48-minute local
release run remained responsive across ten owned processes and ended near 640
MiB aggregate working set / 323 MiB private; a fresh RC7 recording-laptop visual
click-through remains required, especially on Linux. This is bounded evidence, not an indefinite leak
claim. AgentCore is
implemented and locally tested but
**not AWS-deployed**. The formal four-arm benchmark is unfrozen and has no valid
score. Final recording remains. See the
[testing guide](docs/TESTING.md) and the
[architecture overview](docs/architecture/overview.md).

</details>

![PEX Home showing replayed sessions and the no-install demo fixtures](docs/demo/assets/pex-home-replay-5d0bf81.png)

*Browser capture at `5d0bf81`: the worker rail lists recorded replays (each
visibly tagged, never live worker control), the selected replay's last
observed state ("Removed the stray pytest.ini; the real suite is green"),
and the no-install "See the loop without a worker" fixtures — the same buttons
a judge gets from `python scripts/demo.py`.*

<details>
<summary>Goal boundaries and optional details</summary>

![PEX goal editor showing separate constraints, non-goals, and forbidden outcomes](docs/demo/assets/pex-goal-boundaries-browser-907395e.png)

*Browser-verified at `907395e` against a throwaway bridge with cloud reasoning
disabled and automatic dispatch capped at zero. The forbidden-outcome field
accepted a draft value and retained a visible focus outline. No goal was submitted,
key saved, or worker attached. See the [testing guide](docs/TESTING.md) for native
package and live-provider evidence.*

</details>

## The pain it removes

Running several long-lived coding agents created a new job: remembering the real goal, noticing drift, catching false “done”, approving the same safe test command, copying context between windows, and typing “continue”.

PEX attaches to those sessions and does that mechanical work. You keep intent, priorities, and irreversible decisions.

## Why this is not another orchestrator

PEX does not require work to start inside PEX. Existing tools stay usable. Context belongs to the project/goal, not a chat transcript. Interventions are typed, policy-gated, reversible when possible, and audited.

## Independent claim verification

A worker's "all tests passed" is a claim, not a verdict. PEX independently
inspects the workspace and event history before letting a goal complete — and
it verifies the *acceptance surface*, not just the reported exit code:

- At goal attach, PEX seals a first-write-wins SHA-256 baseline of every
  acceptance-relevant file (tests, runner configs, fixtures, dependency
  manifests) per (session, goal), with TOCTOU-fenced reads.
- When a completion claim arrives, the workspace is diffed against that sealed
  baseline. A test weakened or deleted mid-task — or a `pytest.ini`/`conftest.py`
  injected to deselect checks — downgrades the claim to `uncertain`, names the
  changed files, and sends the worker a corrective nudge to restore or justify
  them. A green exit code cannot launder a changed test.
- The seal keeps **content, not just digests** — every file's sealed bytes are
  verified to match the baseline hash before storing, and each integrity flag
  captures the offending bytes at flag time. `GET
  /v1/goals/{id}/acceptance-diff?path=<file>` returns the sealed text, the
  flagged bytes, and what's on disk now — so a judge sees `- assert
  add(1,1)==2` → `+ pass`, not just a filename.
- `GET /v1/claims/metrics` reports the durable ledger: verdict counts, sealed
  baselines, integrity incidents, and corrective nudges issued.

Try it with no agent install: `python scripts/demo.py` starts the bridge and
the desktop together, then the Recorded-replay card in the app walks
`tampered_acceptance_eval` through seal → tamper → catch → nudge → restore →
`verified_complete` in the real pipeline (see the
[demo runbook](docs/demo/RUNBOOK.md), Scenario D).

![PEX Inspector on the replayed tamper catch](docs/demo/assets/pex-claim-verification-f3347dd.png)

*Browser capture of the deterministic `tampered_acceptance_eval` replay at
`f3347dd`: the claim ledger shows the `uncertain` verdict, the corrective nudge,
and the flagged `tests/test_core.py` with its adjudication evidence
(`acceptance_surface_modified:tests/test_core.py`), ending in `verified`. The
full report exports from the Inspector as a self-contained HTML adjudication
record (human-readable timeline plus the embedded raw JSON). The session is labeled
"Recorded replay · not live worker control" — a deterministic fixture, not a
live worker receipt.*

![Sealed-baseline diff of the weakened test](docs/demo/assets/pex-tamper-diff-c281f0f.png)

*Click a flagged file in the ledger and it expands the sealed-baseline diff —
the sealed test the worker claimed green against on top, the exact bytes PEX
flagged below: the worker replaced `assert add(1, 1) == 2` with `pass`. The
same record is served raw at `/v1/goals/{id}/acceptance-diff`, so the
evidence doesn't depend on the UI.*

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

Evaluators for the Nebius x NVIDIA hackathon can start from
[docs/HACKATHON.md](docs/HACKATHON.md) — it maps track requirements to the
code, gives a five-minute no-install judge path, and states what is real
versus credential-gated. Otherwise follow the focused [testing guide](docs/TESTING.md)
for the OpenCode/Nebius path and its exact claim boundaries. To walk the
supervised-worker loop end to end in a browser — connect a real OpenCode
worker, attach a persistent goal, watch PEX verify a false completion claim —
follow the [demo runbook](docs/demo/RUNBOOK.md).

## Pets

The desktop is designed around a compact command surface and a separate transparent,
always-on-top pet overlay. Transparency and controls passed bounded native checks;
prolonged stability is not yet claimed. It supervises existing harnesses.

- Exactly two companions: **Pex**, the owl, and **Von**, the dark-navy cat, selected in Settings → Companion.
- Uses reviewed **Codex v2** atlases (`1536×2288`, `spriteVersionNumber: 2`), restrained playback and manual dragging. The overlay does not roam or hop on hover.
- Separate controls hide the pet or dismiss only its status message; the pet can be restored from Settings. Both actions were observed independently in native checks.
- Custom imports and image generation are disabled in this MVP, including their write APIs. Existing legacy import metadata is preserved; retired selections fall back to Pex.
- Both current installer inventories contain only Pex and Von. See the [testing guide](docs/TESTING.md) for the focused evaluation path and remaining limits.

## Benchmark status

The current unfrozen integrity protocol still defines Cursor / Cursor+PEX /
Codex / Codex+PEX. It predates the focused OpenCode-and-Codex product scope and
is not a product-aligned impact benchmark. The next coherent protocol revision
must replace the Cursor pair with OpenCode / OpenCode+PEX before any headline
performance claim is eligible.

Paired arms share one `TASK.md` and equivalent workspaces. The PEX supervisor decides in a separate process on public observations only. The deterministic development smoke has five recovery tasks plus three source-pinned public QuixBugs repairs and is **unfrozen**: the harness mix is not aligned with the shipping scope, an OS-enforced hidden-data/no-network worker boundary is still missing, and existing rows predate the current 32-row suite/integrity contract. **There is no citeable impact score or validated public leaderboard rank yet.** Do not cite quarantined leakage runs.

A current five-task Codex-only paired diagnostic is retained in
[`docs/evidence/codex-paired-diagnostic-7cfc7f4.json`](docs/evidence/codex-paired-diagnostic-7cfc7f4.json).
Both arms passed all five controlled recovery tasks with no human intervention.
The PEX arms made five isolated local decisions and correctly sent no follow-up.
Across one run per arm and task, PEX averaged 3.20 seconds faster while the
median pair was 8.98 seconds slower; tool calls were 82 versus 90. Supervisor
inference was disabled to prevent paid Nebius usage. This is restraint and
overhead evidence, not a productivity score, and the rows remain outside the
presentation benchmark.

A current ten-task OpenCode diagnostic is retained in
[`docs/evidence/opencode-deterministic-paired-diagnostic-63dc5cd.json`](docs/evidence/opencode-deterministic-paired-diagnostic-63dc5cd.json).
Both exact-source arms passed 10/10 public artifact tasks. With PEX attached,
every event journal settled, all ten completion-event reviews produced a local
deterministic `NOOP`, no worker follow-up was sent, and no supervisor model call
was made. The observed mean and median wall-time deltas were -1.92 and -1.97
seconds. This validates attachment, observation, deterministic policy, restraint,
and bounded overhead; semantic supervision was disabled and no general
productivity claim is made.

## Quick start

### Install PEX

Download the package for your x64 computer from
[PEX 0.1.0 RC24](https://github.com/josepha-mayo/pex/releases/tag/v0.1.0-rc24).

**Windows 10/11:** use `PEX_0.1.0_x64-setup.exe` for the normal install, or
`PEX_0.1.0_x64_en-US.msi` for MSI deployment.
The binary is not code-signed, so Windows may show a publisher warning.

**Ubuntu, Debian, Linux Mint, Pop!_OS:** download the `.deb`, then run:

```bash
sudo apt install ./PEX_0.1.0_amd64.deb
```

Linux needs a graphical desktop and a normal Secret Service/keyring (for
example GNOME Keyring or KWallet) to save a BYOK key through Settings. The
exact-commit CI gate built the Debian package on Ubuntu 24.04 and booted its
packaged bridge; it did not visually exercise every Linux desktop environment.
Other graphical x64 Linux users can use `PEX_0.1.0_amd64.AppImage`.
macOS and ARM64 packages are not available in RC24.

All RC24 packages are built from exact release source
`263a30bb5ccf778969c4f5d6c7a3768462a23714`. The Windows NSIS installer SHA-256 is
`a8b5f4d26d9fed6973eafbfab740289bbdf4c156d9740a60ae40c9c3f5e1ef1d`;
the MSI SHA-256 is
`0f32ac1f0b6ee525977e28b65448eee0636c6fc5e6de7003af4d5fc328959f24`;
the Debian package SHA-256 is
`a5ed2878d95f990083908326090ae50cbd63805a91eae59fdee0d794a90cb99f`;
and the AppImage SHA-256 is
`6dc89641c9fe86ce900741e3c212bdcc16e09d656590a16356fe032575e7f889`.
The release also includes `SHA256SUMS`.
Package integrity is not indefinite stability or publisher trust; current
source-bound behavior and trust boundaries are summarized in the [architecture overview](docs/architecture/overview.md).

Use the [testing guide](docs/TESTING.md) before evaluating this release, or build current source below.

### Build from source

To build from source instead,
use the development workflow below; it is not a packaged installer.
Install Git and `uv`, Node matching [`.node-version`](.node-version),
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

For OpenCode Desktop, use its Home screen server picker to connect to the same
`http://127.0.0.1:4096` server, then create or resume the session there. PEX
attaches to that shared server address too. OpenCode documents the
[Desktop server picker](https://opencode.ai/docs/troubleshooting/#clear-the-desktop-default-server-url)
and [Desktop connection to a server](https://opencode.ai/docs/windows-wsl/#desktop-app--wsl-server).

A newly started server may have no sessions: connecting PEX alone does not
create one. Running plain `opencode` in another terminal can open a different
backend; use the explicit attach address. Configure the worker's provider/model
in OpenCode separately from PEX's supervisor provider. The terminal commands follow the
[official OpenCode CLI interface](https://opencode.ai/docs/cli/#attach).

In PEX, choose **Connect a worker → Connect your local OpenCode server**, enter
`http://127.0.0.1:4096`, then choose **Connect OpenCode**. Return Home, select the
worker and set its persistent goal. Connecting does not start a worker turn.
The quick-connect form supports optional OpenCode Basic credentials for a
loopback server; do not put provider keys or credentials in the server address.

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

Open **PEX Settings → Connections → Connect isolated Codex** to do this from
the app without editing an environment variable. After the handshake, enter an
existing absolute project folder and select **Create Codex worker**. PEX creates
an idle, isolated thread with workspace-write permissions; it does not send a
task or start a model turn. Select **Return Home** to choose that exact worker
and attach its goal. Sending work is a separate operator action. If creation is
not confirmed, inspect Home before retrying because an empty thread may exist.
The source-development equivalent is:

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
semantic supervision, open **Settings → Supervisor**, select the
provider/model and credential source, and save it. Provider setup is independent
of worker attachment.

After a genuine vendor session appears, create or select a stored goal and use
the Inspector's **Attach goal** control. Only then should supervised work begin.
On a genuinely attached control surface, PEX can inspect evidence and issue a
specific policy-gated continuation. Observe-only surfaces never claim delivery.

Raw-browser no-auth operation is not available from an environment variable or
release CLI; it exists only inside explicit in-process Python test harnesses via
`Settings.for_test(...)`.

### Nebius Token Factory + NVIDIA Nemotron

In **Settings → Supervisor**, choose **Nebius Token Factory**, select an
account-supported NVIDIA model, paste the key and save. Keys go into the OS
credential store; Linux needs an unlocked Secret Service or KWallet backend.
Unsaved drafts survive background refreshes. If another client changes the saved
configuration, reload explicitly before saving again.

To pause automatic model reviews while keeping the provider and key saved, open
**Settings → Supervisor → Automatic reviews**, set the saved review limit to
`0`, and choose **Save supervisor**. This stops new semantic dispatches; it does
not cancel a review already in flight. A positive limit counts review
dispatches, not dollars or individual model calls. Saving the key alone does
not make a model call.

Alternatively, configure the process environment before launching PEX:

```text
PEX_SUPERVISOR_PROVIDER=nebius
PEX_SUPERVISOR_MODEL=nvidia/nemotron-3-super-120b-a12b
NEBIUS_API_KEY=<your Token Factory key>
```

The default endpoint is `https://api.tokenfactory.nebius.com/v1`.
A custom compatible endpoint is an explicit credential destination: provide a key
for that endpoint in Settings or through `PEX_SUPERVISOR_API_KEY`. PEX does not
forward another provider's key to it. See the
[official Nebius Nemotron example](https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-super-120B.md).

### Nebius ConTree sandboxed verification

PEX never executes untrusted workspace code inside the bridge process; by
default bounded public pytest evidence runs as a scrubbed local subprocess with
no inherited secrets. Setting `PEX_PUBLIC_PYTEST_BACKEND=contree` dispatches
the same bounded test set to a disposable, network-isolated Nebius ConTree VM
instead. Only files already admitted by the public manifest are uploaded, each
re-verified against its fingerprinted sha256, so the sandbox sees exactly the
bytes the observation receipt describes — drift between fingerprint and
dispatch is refused rather than executed. The run keeps the isolated public
pytest argv (`python -I -B ... --rootdir /workspace --confcutdir /workspace -c
/dev/null`), the same output redaction and hidden-evaluator withholding, and
adds executor provenance (instance, operation, image, resource counters) to the
receipt.

```text
PEX_PUBLIC_PYTEST_BACKEND=contree
PEX_CONTREE_API_KEY or NEBIUS_API_KEY
PEX_CONTREE_PROJECT or NEBIUS_PROJECT_ID
```

Optional overrides: `PEX_CONTREE_BASE_URL`, `PEX_CONTREE_IMAGE`,
`PEX_CONTREE_PYTHON`, `PEX_CONTREE_TIMEOUT_SECONDS`,
`PEX_CONTREE_MAX_UPLOAD_BYTES`, `PEX_CONTREE_MAX_FILES`.

`PEX_CONTREE_IMAGE` accepts an image UUID or a `tag:` reference resolved by the
sandbox (default `tag:python:3.12-slim`). The image must ship pytest because
networking is disabled for the run — the stock `python` images do not, so a
default configuration reports `sandbox_image_missing_pytest` rather than
faking a result. Import an OCI image once (for example
`FROM python:3.12-slim` + `pip install pytest`) and point
`PEX_CONTREE_IMAGE` at its UUID or tag.

A missing key, auth
rejection, malformed response, expired dispatch budget, or an image without
pytest reports an honest `error_type` on the result — infrastructure trouble is
never presented as a test outcome, and a configured-but-unavailable sandbox
never silently downgrades to local execution. This path is implemented and
covered by scripted-transport unit tests; live ConTree execution additionally
requires Nebius Sandboxes beta access and is labeled accordingly, not claimed.
With credentials and beta access, `PEX_LIVE_CONTREE=1 pytest
tests/contract/test_live_contree.py` runs two real disposable-VM executions as
the live contract check.

Push and pull-request checks run the offline backend suite, desktop contracts,
lint and frontend production build on Windows and Ubuntu. Live provider calls,
native visual acceptance and installer testing remain separate checks.

## Architecture

![PEX architecture](docs/architecture/pex-architecture.png)

Editable references: [SVG](docs/architecture/pex-architecture.svg) and
[Mermaid](docs/architecture/pex-architecture.mmd). Regenerate the architecture
PNG with `python scripts/render_architecture.py`.

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
target, not a deployed-service claim. The current Nebius/OpenCode source retains
one controlled false-claim recovery and one already-correct quiet control.
Nemotron Super requested a bound pytest run, the same OpenCode session repaired
the failing parser, an independent rerun passed, and the final review stayed
quiet; the control produced `NOOP` with zero PEX follow-ups. See
[`docs/evidence/nebius-opencode-proof.json`](docs/evidence/nebius-opencode-proof.json).
This bounded pair does not prove broad quiet statistics, AgentCore deployment,
or a comparative benchmark result.

The cloud supervisor can propose actions. It cannot bypass local policy.

The [architecture overview](docs/architecture/overview.md) describes the local
policy and evidence boundaries. A [live Windows Codex recovery](docs/evidence/codex-nebius-live-2026-09-24.json)
showed Nemotron 3 Super correcting one incomplete stop on the same thread and
staying quiet after verification. This is a bounded case, not a benchmark score.
AgentCore remains optional and is not deployed. See the
[testing guide](docs/TESTING.md) for reproducible checks and limits.
