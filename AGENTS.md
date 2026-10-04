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

## Verification

Run from `D:\PEX-work` (Windows paths shown; adapt for Linux):

```powershell
.\.venv\Scripts\python -m pytest -q -m "not live_llm and not live_codex and not live_opencode and not live_agentcore and not live_contree"
.\.venv\Scripts\ruff check services packages tests scripts
.\.venv\Scripts\ruff format --check services packages tests scripts
```

Desktop (`apps/desktop`):

```powershell
npm test
npx tsc --noEmit
npm run build
```

Release preflight must run with `apps/desktop` as cwd:

```powershell
node apps/desktop/scripts/build-sidecar.mjs --preflight-release
```

Full backend suite takes ~35 min on this machine; do not run two suites
concurrently (CPU contention has caused false `TimeoutExpired` on the
preflight test, which now has a 300 s budget).

## Notes

- `python scripts/demo.py` is the one-command path: it starts the demo bridge
  (`scripts/demo_bridge.py`, `http://127.0.0.1:7420`, unauthenticated and
  loopback-only) plus the vite dev UI on `:1420` with a `/v1` proxy, waits for
  real readiness, and kills whole process trees on exit. The packaged Tauri
  app uses the same bridge port with a bearer token owned by the Rust
  launcher.
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
