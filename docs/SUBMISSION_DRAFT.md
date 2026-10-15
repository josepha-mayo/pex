# Devpost submission draft — Nebius x NVIDIA Global AI Hackathon

Working draft for the submission form. Every claim below is backed by a
committed receipt or a runnable demo path — nothing aspirational. Edit before
pasting; keep the honesty framing (judges reward it, and the form requires it).

**Deadline: Oct 30, 2026 10:00 AM PT (17:00 UTC) — morning, not end-of-day.**

Form checklist (all required unless noted):

- [ ] Name, tagline, ONE track: **Coding and Agentic Engineering**
- [ ] Description (elevator text below)
- [ ] **Working demo URL** → repo link (test build) — see section below
- [ ] **Demo video** → ≤3:00, **public on YouTube**, English
- [ ] Public repo + OSI license visible at repo top (MIT — done)
- [ ] README highlights NVIDIA-model usage + Token Factory + other Nebius tools
- [ ] **Feedback on Nebius/NVIDIA tooling** — required component, not optional
- [ ] Testing instructions (below) — keep runnable through Dec 15
- [ ] Pre-existing-project "what changed" note (below)
- [ ] Optional: city association ($500 city awards); Tavily bonus ($3k) —
      wired already, needs `TAVILY_API_KEY` + `check_search_backend.py` run

## Project name

PEX — the judge for coding agents.

## Tagline

Your coding agent says it finished. PEX is the supervisor that checks whether
it actually did — against your intent, not its narration.

## Track

Coding and Agentic Engineering.

## Elevator description (~2 paragraphs)

A coding agent asked its human for permission to disobey the human — the
task ordered it to weaken a test the goal had forbidden it to touch. The
agent escalated through PEX's own MCP server with three options and
`urgency: blocking`. Its session died before the human answered — and the
ruling still landed on a durable intent ledger, honestly marked
undeliverable, then propagated to a sibling worker that never asked. That
arc is PEX: a supervisor for the coding agents you already run (OpenCode,
Codex) that treats worker narration as evidence-free until independently
verified against sealed goals and workspace state.

PEX catches what a green exit code hides: injected `pytest.ini` files that
empty the suite, edits to sealed acceptance tests, "all tests pass" with no
attributable run, identical failing probes looped forever. Every verdict
ships a tamper-evident evidence pack — hash-chained ledger, manifest
digests — verifiable offline without trusting us. Semantic supervision runs
NVIDIA Nemotron through Nebius Token Factory; the deterministic evidence
layer does most of the catching, and both are labeled honestly.

## The live story (for the "story" field / video)

- A worker on OpenCode's free Nemotron route is told to make
  `python -m pytest -q` pass by *editing the sealed acceptance test* — but
  the PEX goal forbids touching `test_csv_utils.py`. The worker reads its
  goal through `pex.get_goal`, discovers the conflict itself, and
  escalates: *"your instruction says weaken the test, the goal forbids it —
  how should I proceed?"* with three authored options and
  `urgency: blocking`.
- The worker's turn ends before the human answers. PEX records the ruling
  durably anyway (delivery honestly reported as `session_terminal`) — and a
  sibling session, created *before* the ruling, receives it in its next
  context bundle. Human intent outlives the worker that asked. That exact
  session replays deterministically as the `worker_escalation_eval` fixture —
  judges can watch the escalation, not just read about it.
- A worker claims "all tests pass" after modifying the test file. PEX inspects
  the workspace itself, hashes the touched files, and disputes the claim with
  named evidence — the audit trail a judge can verify event-by-event.
- Live receipts committed: OpenCode false-claim correction, tamper dispute,
  worker-initiated escalation + durable ruling, and a Token Factory/Nemotron
  supervisor correcting a Codex worker's incomplete stop
  (`docs/evidence/codex-nebius-live-2026-09-24.json`).

## How we used the platform (required-ish content — also answers feedback)

**The qualifying NVIDIA-model call: PEX's semantic supervisor calls
NVIDIA Nemotron-3-Super-120B-A12B through the Nebius Token Factory
inference API.** The supervisor is the bounded LLM that re-reads the goal
against independently gathered workspace evidence and writes the
pass/fail/correct ruling a worker cannot talk its way out of. This is a
real runtime call to `api.tokenfactory.nebius.com` — live-verified
(`docs/evidence/codex-nebius-live-2026-09-24.json` records a Nemotron
supervisor correcting a Codex worker's premature stop). Configuration is
two environment variables (`NEBIUS_API_KEY`,
`PEX_SUPERVISOR_PROVIDER=nebius`) and
`uv run python scripts/check_token_factory.py --infer` proves the wiring
with one real inference call in seconds.

**NVIDIA Nemotron also powers the workers in the demo**: live sessions run
on OpenCode's free Nemotron route, and with a Token Factory key a Nemotron
supervisor judges a Nemotron worker — receipted in
`docs/evidence/nebius-opencode-proof.json` (Nemotron-3.5-Lightning worker,
Super-120B supervisor, false-claim recovery). (PEX is worker-agnostic; the
worker's model choice is the worker's. The hackathon-qualifying model call
is the supervisor's Token Factory path above — not the worker's free
route.)

**ConTree/Token Factory Sandboxes**: wired (`PEX_PUBLIC_PYTEST_BACKEND=contree`
dispatches the bounded verification set into a disposable network-isolated
VM), gated on the Sandboxes beta — declared honestly, never silently
falling back.

**Tavily (bonus award)**: a real runtime integration, not decoration. When a
worker cites a public claim, the supervisor's evidence surface exposes
`web_search` — routed to Tavily when `TAVILY_API_KEY`/`PEX_TAVILY_API_KEY`
is set — so the model can check the citation against the live web before
ruling. Deliberately scoped: the tool is only offered when a public claim
is classified, and it can never reach hidden evaluators.
`uv run python scripts/check_search_backend.py --provider tavily` verifies
the wiring with one real search call.

## Working demo URL

`https://github.com/josepha-mayo/pex` — the repo IS the test build: a
five-minute, no-keys replay path (`uv run python scripts/demo.py`, then any
fixture button) replays real recorded worker sessions through the live
adjudication pipeline in the judge's browser. Live mode
(`uv run python scripts/demo.py --live`) supervises a real OpenCode worker.
Testing instructions are in `docs/HACKATHON.md`; the repo must stay public
and runnable through Dec 15 judging.

## Testing instructions (paste into the form)

```text
git clone https://github.com/josepha-mayo/pex && cd pex
npm install --prefix apps/desktop    # once — the UI bundle
uv run python scripts/demo.py        # bridge + UI, no keys needed
# open http://127.0.0.1:1420 → "Recorded replays" → run premature_stop_eval
# (tagged "start here") — then worker_escalation_eval, or any of the 18
# fixtures; each replays a recorded trajectory through the
# real adjudication pipeline — four were exported from real live worker
# sessions — and shows its verdict.
uv run python scripts/eval_replays.py   # second terminal, while demo.py runs;
#                                        scores all 18 (prints a table;
#                                        --json/--html write a receipt file)
# With a Token Factory key (PowerShell: $env:NEBIUS_API_KEY="..." first):
NEBIUS_API_KEY=... uv run python scripts/check_token_factory.py --infer
#   # one real catalog + one real inference call against Nemotron
```

## Built during the submission period (pre-existing-project note)

This repository predates the submission window in part; the work submitted
here was built during it. Substantially new since the window opened:

- The entire worker↔PEX MCP supervision loop (session-bound credentials,
  eight session-bound tools behind five scopes — one read, four write —
  with a flat+nested arg contract) — including the worker-initiated
  escalation captured live into `worker_escalation_eval`.
- Durable human rulings: journaled rulings distinct from editable goal
  text, surviving worker termination, propagating to sibling workers.
- The deterministic replay system: 18-fixture suite, evaluator, replay
  isolation (`replay: true` + `not_live_control: true` enforced server-side).
- Evidence packs + offline verification (`scripts/verify_pack.py`).
- The desktop supervision surface (fixtures rail, capabilities panel,
  inspector, escalation affordances).

## Tooling feedback (required field — draft)

- **Token Factory**: OpenAI-compatible endpoint made integration a provider
  entry, not a rewrite — `PEX_SUPERVISOR_PROVIDER=nebius` + `NEBIUS_API_KEY`
  and the supervisor was live. The model catalog endpoint made the smoke
  check trivial (`scripts/check_token_factory.py` does one real catalog +
  inference call). A first-class "verify my key+model" recipe in the
  console would shortcut onboarding.
- **Nemotron-3-Super-120B-A12B**: strong at structured judgment — it read an
  acceptance criterion, inspected evidence lines, and produced an actionable
  correction for a live worker that stopped early (receipt:
  `docs/evidence/codex-nebius-live-2026-09-24.json`). Deterministic-enough
  for supervision when bounded (we cap dispatches per session and never let
  the model override the deterministic evidence layer).
- **Sandboxes/ConTree**: the API shape (operation → `metadata.result`,
  `tag:`-prefixed image refs) integrated cleanly behind
  `PEX_PUBLIC_PYTEST_BACKEND=contree`; we could not exercise it end-to-end
  because beta credentials are still pending. Honest gap: error paths are
  contract-tested, live execution is not.
- **Wishlist**: Sandboxes beta availability for CI; a published
  latency profile per model would help teams size supervision budgets;
  model-id lifecycle notices (rename/deprecation warnings) so a frozen
  submission can't silently break mid-judging.
- **Would we build on it again?** Yes — the OpenAI-compatible surface meant
  our deterministic layer owned correctness while the model owned judgment,
  which is exactly the split a supervisor needs.

## Links to wire up at submission time

- Demo video: **<3:00, public on YouTube specifically** (rules: ≤3 min,
  public — not unlisted; no third-party music/trademarks). Source footage:
  `docs/demo/assets/pex-replay-walkthrough-b28d999.mp4` (full judge path)
  and `docs/demo/assets/pex-escalation-arc-6d16888.mp4` (worker-initiated
  `pex.request_decision` → durable ruling, real live data). Narration plan:
  `docs/demo/DEMO_SCRIPT.md` — cut to ~2:55.
- Supporting clips: `docs/demo/assets/pex-live-tamper-demo.mp4`,
  `docs/demo/assets/pex-judge-arc-597ce13.mp4`,
  `docs/demo/assets/pex-ruling-arc-eabd646.mp4`
- Repo: https://github.com/josepha-mayo/pex (public, MIT — LICENSE at root)
- Judge path: `docs/HACKATHON.md` — five-minute replay path, no keys needed
- Keep-alive: the repo and any Token Factory model ids referenced must stay
  valid through judging (Dec 15 noon PT); if `nemotron-3-super-120b-a12b`
  is renamed/deprecated in the catalog, update the provider default and
  re-run `check_token_factory.py` before the deadline.

## Honest capability line (put this somewhere visible)

Live-verified: OpenCode + Codex supervision, semantic Nebius/Nemotron rulings,
MCP worker↔PEX loop incl. worker-initiated escalation, deterministic replays,
evidence packs, human rulings surviving worker termination. Key-gated:
ConTree sandboxed verification (beta creds pending). Replay is always
labeled replay — nothing in the demo fakes a live call.
