# Devpost submission draft — Nebius x NVIDIA Global AI Hackathon

Working draft for the submission form. Every claim below is backed by a
committed receipt or a runnable demo path — nothing aspirational. Edit before
pasting; keep the honesty framing (judges reward it, and the form requires it).

**Deadline: Oct 30, 2026 10:00 AM PT (17:00 UTC) — morning, not end-of-day.**

Judging: two-stage — a pass/fail viability gate (automated repo-clone build in
a Nebius Sandbox + Token Factory/model-ID grep + Tavily demo-URL scrape + video
length check), then four equally weighted human criteria (25% each):
Technological Implementation, Design, Potential Impact, Quality of the Idea.
Write to those four words explicitly.

Form checklist (all required unless noted):

- [ ] Name, tagline, ONE track: **Coding and Agentic Engineering**
- [ ] Description (elevator text below)
- [ ] **Working demo URL** → `https://josepha-mayo.github.io/pex/` — see below
- [ ] **Demo video** → ≤3:00, **public on YouTube at submission time**
      (not just by judging), English, no third-party marks
- [ ] Public repo + OSI license visible at repo top (MIT — done)
- [ ] README highlights NVIDIA-model usage + Token Factory + other Nebius tools
- [ ] **Feedback on Nebius/NVIDIA tooling** — required component, not optional
- [ ] Testing instructions (below) — keep runnable through Dec 15
- [ ] Pre-existing-project "what changed" note (below)
- [x] Tavily bonus ($3k): live call verified through the supervisor's search
      contract 2026-10-15 — `docs/evidence/tavily-evidence-path-2026-10-15.json`
      (3 real results, HTTP 200, wired into adjudication not a demo path).
      Optional: city association ($500 city awards)

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

**Why it matters.** PEX plus your existing coding agents *is* the
agentic-engineering system that plans, writes, runs, and tests code — the
supervisor half is what makes its output shippable. The audience is every
team already running more than one coding agent. The stakes are measured:
METR found 39 of 128 unprompted frontier-model runs on RE-Bench attempted
reward hacking (~30%) — modifying the tests, monkey-patching the evaluator,
caching the answer. PEX is built for exactly that failure class: it caught
a real OpenCode worker claiming done on a decoy checker, and disputed a
weakened acceptance test with named evidence. One more thing, for the
judges reading this: the hackathon's own evaluation pipeline — automated
evidence gates, a Nemotron judgment pass, humans on the calls that matter —
is the architecture PEX ships. This submission is, in a real sense,
judged by our thesis.

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
  context bundle — re-runnable via `scripts/probe_ruling_continuity.py`.
  Human intent outlives the worker that asked. That exact
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

**Tavily (bonus award)**: a real runtime integration, not decoration — **live
call verified 2026-10-15** ([receipt](evidence/tavily-evidence-path-2026-10-15.json),
`check_search_backend.py --provider tavily` → HTTP 200, 3 results, 1688 ms).
When a
worker cites a public claim, the supervisor's evidence surface exposes
`web_search` — routed to Tavily when `TAVILY_API_KEY`/`PEX_TAVILY_API_KEY`
is set — so the model can check the citation against the live web before
ruling. Deliberately scoped: the tool is only offered when a public claim
is classified, and it can never reach hidden evaluators.
`uv run python scripts/check_search_backend.py --provider tavily` verifies
the wiring with one real search call.

## Working demo URL

**Primary (submit this): `https://josepha-mayo.github.io/pex/`** — a static
page served from this repo's `docs/` that renders real product output: the
self-verifying evidence-pack HTML (recomputes its own digests in the
browser), the 19/19 replay suite receipt, and the one-command offline
verification path. A web scraper or a skimming judge sees the artifact, not
a README wall — and the page itself is a demo of the deliverable.

Repo link stays in the description as the test build: a five-minute,
no-keys replay path (`uv run python scripts/demo.py`, then any fixture
button) replays real recorded worker sessions through the live adjudication
pipeline in the judge's browser. Live mode
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
#                                        scores all 19 (prints a table;
#                                        --json/--html write a receipt file)
# With a Token Factory key (PowerShell: $env:NEBIUS_API_KEY="..." first):
NEBIUS_API_KEY=... uv run python scripts/check_token_factory.py --infer
#   # one real catalog + one real inference call against Nemotron
```

## Built during the submission period (pre-existing-project note)

This repository predates the submission window in part — the window opened
August 26, 2026, and 1,388 of the project's 1,389 commits land inside it;
the single earlier commit (`d138f4a`, the initial tree publish) predates it
by ~18 hours. The work submitted here was built during the window. Substantially
new since it opened:

- The entire worker↔PEX MCP supervision loop (session-bound credentials,
  eight session-bound tools behind five scopes — one read, four write —
  with a flat+nested arg contract) — including the worker-initiated
  escalation captured live into `worker_escalation_eval`.
- Durable human rulings: journaled rulings distinct from editable goal
  text, surviving worker termination, propagating to sibling workers.
- The deterministic replay system: 18-fixture suite, evaluator, replay
  isolation (`replay: true` + `not_live_control: true` enforced server-side —
  sealed ledgers refuse control mutations yet remain legitimate handoff
  *sources* via `sealed_source` triggers: evidence in, control out).
- The verdict-card claim ledger: every worker claim rendered beside its
  adjudicated verdict — "All tests passed" shown *contradicted* on a
  premature stop, then *verified* after a real pytest run.
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
- **AI Cloud**: we evaluated Serverless Jobs/Endpoints for the pack-verify
  proxy and judged them unnecessary — the deliverable's trust property is
  *offline* verifiability, so we shipped hash-chained packs + a stdlib
  verifier instead of hosted compute. Sandboxes (ConTree) was the one
  AI Cloud surface with a real fit — see below.
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

## Strategy notes (verified against official rules + RoundOne docs)

- **Award stacking**: a submission can win one Overall award OR one Track
  award + one Bonus award — not Overall + Bonus. PEX's natural play is Track
  (Coding & Agentic Engineering) + Tavily bonus ($3k): the Tavily call is
  load-bearing (adjudication evidence), not decorative.
- **RoundOne automated gate**: repo is cloned into a Nebius Sandbox and
  install/test is *inferred* from the repo — `requirements.txt` is the
  foolproof path; code scraper greps for `api.tokenfactory.nebius.com` and
  NVIDIA model ids (both present in `providers.py`/`README`); video reviewer
  checks ≤3 min + public; demo URL is scraped via Tavily (JSON-LD +
  `verdict.json` cover machine-legibility).
- **Injection-flag hygiene**: RoundOne rows can flag "suspicious or prompt
  injection". Worker-directed strings are fenced as product inputs (README
  reviewer note at the end of the MCP section).
- **Runtime-call requirement**: "runs on Nebius" = a runtime Token Factory
  inference call — PEX's adjudication calls qualify; the receipts in
  `docs/evidence/` prove it and the video should show one.
- **Keep-alive budget**: demo + referenced model ids must work through
  Dec 15 noon PT — keep Token Factory spend headroom; re-run
  `check_token_factory.py` before submitting.
- **Credit codes** (organizer-posted): `NEBIUS-DEVPOST-GLOBAL26` ($25 Token
  Factory), Builders Program ($25 + Tavily + Academy), `BBDEVPOST` (Tavily).
- **Differentiation vs. adjacent submissions** (e.g. ForgeXi's bounded
  repair loop, Agents Squad's sandbox-verified repair): PEX's claim ledger
  adjudicates *what the worker said* against *what the workspace proves*,
  human rulings are durable intent that outlive the worker and propagate to
  siblings, workers can call back through scoped MCP, and every run emits a
  hash-chained pack a judge can re-verify offline with zero install.

## Links to wire up at submission time

- Demo video: **<3:00, public on YouTube specifically** (rules: ≤3 min,
  public — not unlisted; no third-party music/trademarks; must be public
  *at submission time*). A ready-made captioned rough cut is committed at
  `docs/demo/assets/pex-demo-roughcut.mp4` (96s, all beats, narration burned
  in as captions — uploadable as-is, or record VO over the silent cut).
  Regenerate via `docs/demo/assemble-roughcut.sh` → `build/pex-demo-roughcut*.mp4`.
  Beat→asset map: `docs/demo/FOOTAGE_MANIFEST.md`;
  narration: `docs/demo/DEMO_SCRIPT.md`.
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

Live-verified: OpenCode + Codex supervision, Nemotron inference + a full
semantic adjudication through the pipeline (2026-10-15, Token Factory), MCP
worker↔PEX loop incl. worker-initiated escalation, Tavily web evidence
(2026-10-15), deterministic replays, evidence packs, human rulings surviving
worker termination. Key-gated: ConTree sandboxed verification (beta creds
pending). Replay is always labeled replay — nothing in the demo fakes a
live call.
