# Contributing

PEX is a goal-aware supervisor for existing coding agents (OpenCode, Codex).
It is not a coding agent itself and it does not trust worker narration —
it independently verifies workspace state and acceptance evidence before
believing a claim.

## Development setup

Python 3.12+ and Node 20+ are required.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e "services/bridge[dev]"
cd apps\desktop && npm install
```

## Verification

Run the non-live suite, lint, and format check from the repo root:

```powershell
.\.venv\Scripts\python -m pytest -q -m "not live_llm and not live_codex and not live_opencode and not live_agentcore and not live_contree"
.\.venv\Scripts\ruff check services packages tests scripts
.\.venv\Scripts\ruff format --check services packages tests scripts
```

Desktop checks (from `apps/desktop`):

```powershell
npm test
npx tsc --noEmit
npm run build
```

The replay fixture suite is scored end-to-end by `scripts/eval_replays.py`
against a running demo bridge (`python scripts/demo.py`):

```powershell
.\.venv\Scripts\python scripts/eval_replays.py --bridge http://127.0.0.1:7420
```

## Replay fixtures

`fixtures/demo/` holds recorded supervision trajectories that run through the
real event pipeline with no agent install. Every fixture declares the arc it
exists to demonstrate in an `expected` block (completion class, required and
forbidden interventions, claim floors, evidence markers); the bridge scores
each adjudicated run against that contract. See `fixtures/demo/README.md` for
the schema — adversarial fixtures are welcome.

Recorded replays are always labeled `replay: true` +
`not_live_control: true`. Never surface one as live worker control.

## Honesty rules

Honesty labels are load-bearing in this project: *implemented*,
*mock-tested*, *key-gated*, *live-tested*, and *not deployed* are different
claims, and docs/tests must keep them distinct. Specifically:

- Do not claim a live provider call (Nebius, NVIDIA, OpenCode) without the
  call actually happening; key-gated paths must stay visibly gated.
- Do not claim a ConTree sandbox run that did not execute — a configured
  but unavailable sandbox reports an honest `error_type` and never falls
  back to local execution silently.
- Do not claim AgentCore deployment without a Runtime ARN and a live
  invocation record.
- Do not describe the curated fixture suite as a benchmark.
- Deterministic supervision must never imply a model ran when it did not.

Live contract tests need a literal first-statement
`require_live_authorization("FLAG")` plus an inventory entry in
`tests/contract/test_authorization_inventory.py`.

## What not to commit

Never commit runtime data, generated databases (`*.sqlite`, WAL/lock files),
secrets, credentials, or `build/` outputs. Inspect `git status` before
staging.

## Pull requests

Keep diffs focused. If a change touches supervision semantics, add or update
a replay fixture (and its `expected` block) so the behavior is scored in CI.
