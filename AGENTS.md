# Project working rules

- PEX is a goal-aware supervisor for existing coding agents (OpenCode, Codex),
  not an agent itself. Worker narration is never proof; PEX independently
  verifies workspace state and acceptance evidence before trusting claims.
- Keep honesty labels precise: implemented, mock-tested, key-gated, live-tested,
  and not deployed are different claims. Do not claim a live provider call,
  a ConTree sandbox run, a formal benchmark, an AgentCore deployment, or a
  packaged-release readiness that did not actually happen. Deterministic
  supervision must never pretend a model ran when it did not.
- Recorded replay sessions are labeled `replay: true` + `not_live_control: true`
  everywhere they surface. They are deterministic recorded trajectories, never
  live worker control.
- Live contract tests require a literal first-statement gate
  `require_live_authorization("FLAG")` plus an entry in
  `tests/contract/test_authorization_inventory.py`; the AST inventory test
  checks both.
- `PEX_PUBLIC_PYTEST_BACKEND=contree` routes public pytest into a disposable,
  network-isolated Nebius ConTree VM. A configured-but-unavailable sandbox must
  report an honest `error_type` and never silently fall back to local
  execution. The image must ship pytest (networking is off); the default
  `tag:python:3.12-slim` deliberately reports `sandbox_image_missing_pytest`.
- Never commit runtime data, secrets, credentials, or generated databases.
  Inspect the staged file list before committing.
- Operator controls that imply a live worker must refuse `not_live_control`
  sessions honestly — server-side first (`pause/resume-supervision` 409s),
  then the UI affordance. Focus, pause, and handoff-targeting are already
  guarded; a replay's goal context is still a legitimate handoff *source*.
  When adding a new session-scoped mutation, check
  `session.metadata.not_live_control` before wiring it.

## Verification

Run from `D:\PEX-work` (Windows paths shown; adapt for Linux):

```powershell
.\.venv\Scripts\python -m pytest -q -m "not live_llm and not live_codex and not live_opencode and not live_agentcore and not live_contree"
.\.venv\Scripts\ruff check services packages tests scripts
.\.venv\Scripts\ruff format --check services packages tests scripts
```

Both ruff gates run in CI (`checks.yml`); the tree was normalized in
`ec69621`, so format diffs now mean your change, not inherited drift.

Desktop (`apps/desktop`):

```powershell
npm test
npx tsc --noEmit
npm run build
```

`npm test` runs an explicit file list in `package.json` — a new `*.test.ts`
is silently skipped until it is added there. JSX components cannot be run
under `node --test` (no JSX transform), so testable logic lives in plain
`.ts` modules (`viewModel.ts`, `capabilities.ts`, …) beside the `.tsx`
that renders it.

Release preflight must run with `apps/desktop` as cwd:

```powershell
node apps/desktop/scripts/build-sidecar.mjs --preflight-release
```

Full backend suite takes ~35 min on this machine; do not run two suites
concurrently (CPU contention has caused false `TimeoutExpired` on the
preflight test, which now has a 300 s budget).

## Notes

- Judge-facing commands always use `uv run python …` (self-syncing workspace
  env); a bare `python scripts/demo.py` now fails fast with an actionable
  message because the bridge spawns on the same interpreter.
- `python scripts/demo.py` is the one-command path: it starts the demo bridge
  (`scripts/demo_bridge.py`, `http://127.0.0.1:7420`, unauthenticated and
  loopback-only) plus the vite dev UI on `:1420` with a `/v1` proxy, waits for
  real readiness, and kills whole process trees on exit. `--live` adds a real
  `opencode serve` on :4096 (free Zen model, credential-free homes) plus a
  seeded git workspace under `build/demo/live-<utc>/` and attaches the goal
  via the bridge API (`scripts/demo_live.py`). Live workspaces MUST be their
  own git root — nested inside this repo, OpenCode adopts PEX's AGENTS.md and
  runs PEX's own test suite. `--live` also seeds an idle sibling session on
  the same goal so the Inspector's **Hand off →** control has a real target,
  and saves `pex-receipt.json` (the verification report) on exit. The demo
  bridge advertises `unauthenticated_operator` on `/health` (test-scoped
  `allow_unauthenticated_operator`), which unlocks the browser UI's operator
  controls — decisions, pause/resume, the task composer, and handoffs. On
  this machine OpenCode 1.18.32 lives at `D:\tools\opencode` (add
  `node_modules\.bin` to PATH). The packaged Tauri app uses the same bridge
  port with a bearer token owned by the Rust launcher.
- ConTree API details verified against the published OpenAPI
  (`docs.tokenfactory.nebius.com`): the instance `InstanceResult`
  (state/stdout/stderr) hangs off `metadata.result` on the operation, not the
  top-level `result` (that is the image-import shape); `image` accepts an image
  uuid or a `tag:`-prefixed reference; auth is `Authorization: Bearer` +
  `Project` header.
- Judge-facing entry points: `docs/HACKATHON.md` (track mapping + five-minute
  path), `docs/demo/RUNBOOK.md` (live and replay demos),
  `docs/demo/DEMO_SCRIPT.md` (video narration), and the app's Recorded-replay
  fixture buttons (no worker install needed).
- SQLite read conventions (hard-won): the long-lived `store.db` connection can
  hold a stale snapshot while another connection commits — reads that need the
  committed view must go through `store._committed_connection()` /
  `_committed_fetch*`, which borrow from a bounded pool of pre-configured read
  connections (fresh `BEGIN` per borrow, rollback on return). Never add a bare
  `self.db.execute(...)` read outside a transaction; the audit pattern is the
  dedicated-conn + `BEGIN` used throughout `store.py`. In-transaction reads on
  `self.db` inside `BEGIN IMMEDIATE` write blocks are correct and must stay on
  that connection.
- `scripts/eval_replays.py` adjudicates every fixture in `fixtures/demo/`
  through the real bridge and emits the suite receipt with `--json`/`--html`
  (flags are `--json <path>` and `--html <path>` — not `--json-out`). The
  fixture expectation contract lives in each fixture's `expected` block and
  supports `completion_in`, `interventions_any`, `interventions_never`,
  `max_verified_or_supported`, and evidence requirements.
- Session-row signals derived from event content (e.g. `worker_pex_calls`)
  must be projected at the `/v1/sessions` read path from the committed event
  ledger, not stamped during ingest — the OpenCode pump hands `ingest_event`
  a *deep-copied* session, so in-ingest metadata mutations never persist for
  live sessions. Read-time projection is exact for live, replay, and
  pre-feature sessions alike.
- Fixture ids share one strict contract on both sides —
  `[a-z0-9][a-z0-9_-]{0,62}` in `pex_bridge/demo.py` and `demoReplay.ts` —
  because the desktop drops ids it cannot parse and the bridge must never
  advertise an unclickable fixture. New fixtures get lowercase+underscore
  stems and a `FIXTURE_ORDER` slot (`demoReplay.ts`) if they belong in the
  curated narrative.
- `scripts/capture_replay.py` exports a recorded live session into a fixture.
  `pex_*` worker-MCP tool calls are supervision signal, not transport detail —
  they are preserved as first-class `tool_call` events (paired pending/result
  frames collapse by call id); other unmapped tools stay filtered.
- Attention durability: `needs_decision` is a durable human obligation, not a
  recency hint — it never ages out of `collapse_promptable_agents` (exempt
  from `_PROMPTABLE_STALE`) or the pet's `needs_you` (counted from projected
  sessions, not the freshness-filtered live set). If a new status carries a
  pending obligation, keep both projections in sync.
- Worker-requested human decisions (`pex.request_decision` → ASK_HUMAN):
  resolving one on a *terminal* session still records the ruling durably
  (Decision row + resolved context + resolution receipt) and finalizes the
  reserved delivery effect as `failed`/`session_terminal` — the answer is
  durable intent even when no live worker can receive it. Liveness gates
  (paused, live project binding, goal supersession) protect delivery only;
  identity checks (session/goal/pending-context binding) still apply. The
  pending question also outlives the session's live status on the attention
  surfaces: `attention_metrics` keeps an unresolved `mcp_human_request`
  intervention in `current_pending` after the session stops, and the pet's
  `needs_you` counts it — session-bound permission requests still die with
  their session.
- `note` (all operational-failure copy) must render on every surface —
  Inspector/Settings render it in-context; compact Home and the Command Deck
  get it via the topbar-level `surface-note` in `App.tsx` (`surface !==
  "inspector"`). A new surface must not leave action failures silent.
- Deep links: `#inspector/<encodeURIComponent(sessionId)>` restores the
  selected session on load/reload; `openInspector` writes it. Keep
  `surfaceFromHash`/`sessionFromHash` parsing tolerant of stale ids (the
  Inspector falls back to its no-worker state).
- Shared derivations live in `viewModel.ts` so JSX components stay thin and
  logic stays node-testable: e.g. `governedSessionsForGoal` (goal + ancestor
  lineage → governed sessions) is shared by the Inspector strip and the
  deck's Goals registry.
- Worker-facing MCP wiring (hard-won, verified live 2026-10-14): OpenCode
  `serve` connects remote MCP servers but never registers their tools into
  sessions (1.18.32 + 1.19.0); `type: "local"` stdio servers DO register.
  `demo.py --live` therefore mounts `/mcp/` via `scripts/pex_mcp_stdio.py`,
  and the mcp block must live in `<workspace>/opencode.json` — session MCP
  registration resolves from the session directory's config chain, not the
  server's cwd config. The stdio shim reads `--token-file` lazily per call:
  mint via `POST /v1/sessions/{id}/mcp-credential` after goal attach, drop
  the file at run root, and write-scoped tools unlock without respawning
  the MCP subprocess. On the demo bridge (`require_auth` off) a valid
  session bearer resolves to its scoped principal; absent/invalid →
  anonymous read-only. All four worker-facing write tools accept both the
  nested model (`request:`/`report:`) and flat top-level args — workers
  fumble nested schemas (a live worker failed `verify_claim` three times
  on the wrapper). Flat calls that omit `idempotency_key` derive
  `mcp-flat-<sha256(session + payload)[:32]>`, so retries replay exactly;
  keep every flat field bounded identically to the protocol model (the
  safety-contract test audits bounds). New write tools must follow the
  same dual-shape contract.
- `opencode run` (headless) hits Zen's free-tier gate without a signed-in
  OpenCode profile — `serve` mode does not. `scripts/probe_worker_mcp.py`
  exercises the run-mode path and needs real worker credentials.
