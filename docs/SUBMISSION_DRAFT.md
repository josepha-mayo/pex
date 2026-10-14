# Devpost submission draft — Nebius x NVIDIA Global AI Hackathon

Working draft for the submission form. Every claim below is backed by a
committed receipt or a runnable demo path — nothing aspirational. Edit before
pasting; keep the honesty framing (judges reward it, and the form requires it).

## Project name

PEX — the judge for coding agents.

## Tagline

Your coding agent says it finished. PEX is the supervisor that checks whether
it actually did — against your intent, not its narration.

## Track

Coding and Agentic Engineering.

## Elevator description (~2 paragraphs)

Coding agents narrate. They say "done" when tests are green — and "done" when
they weakened the test to get there. PEX is a supervisor that sits beside the
agent you already have (OpenCode today, Codex today, anything emitting
OpenTelemetry tomorrow): it reads the durable goal — objective, acceptance
criteria, forbidden outcomes — independently inspects the workspace, and
decides itself whether the acceptance state actually holds. When a worker's
claim doesn't match reality, PEX corrects it or stops the session. When intent
and instruction conflict, the worker can escalate *through PEX's own MCP
server* — and the human's ruling lands on a durable intent ledger that every
later worker inherits, even ones that never asked.

Everything the judge sees is replayable and verifiable: recorded live sessions
re-derive their verdicts deterministically, and signed evidence packs can be
re-checked offline. Supervision runs on Nebius Token Factory with NVIDIA
Nemotron — a real model making real pass/fail rulings about real agents'
workspaces, not a mock.

## The live story (for the "story" field / video)

- A worker on OpenCode's free Nemotron route is told to "run the tests" — but
  the PEX goal forbids editing `test_csv_utils.py`. The worker reads its goal
  through `pex.get_goal`, discovers the conflict itself, and escalates:
  *"your instruction says weaken the test, the goal forbids it — how should I
  proceed?"* with three authored options and `urgency: blocking`.
- The worker's turn ends before the human answers. PEX records the ruling
  durably anyway (delivery honestly reported as `session_terminal`) — and a
  sibling session, created *before* the ruling, receives it in its next
  context bundle. Human intent outlives the worker that asked.
- A worker claims "all tests pass" after modifying the test file. PEX inspects
  the workspace itself, hashes the touched files, and disputes the claim with
  named evidence — the audit trail a judge can verify event-by-event.
- Live receipts committed: OpenCode false-claim correction, tamper dispute,
  worker-initiated escalation + durable ruling, and a Token Factory/Nemotron
  supervisor correcting a Codex worker's incomplete stop
  (`docs/evidence/codex-nebius-live-2026-09-24.json`).

## How we used the platform (required-ish content — also answers feedback)

**Nebius Token Factory + NVIDIA Nemotron-3-Super-120B-A12B** power PEX's
semantic supervisor: the bounded LLM that re-reads the goal against
independently gathered workspace evidence and writes the pass/fail/correct
ruling a worker cannot talk its way out of. Configuration is three
environment variables (`NEBIUS_API_KEY`, `PEX_SUPERVISOR_PROVIDER=nebius`,
`PEX_CLOUD_REASONING=true`) and `scripts/check_token_factory.py` verifies the
wiring with one real catalog + inference call in seconds.

**NVIDIA Nemotron (open weights) also powers the workers**: live sessions run
on OpenCode's free Nemotron route, so the demo shows Nemotron both doing the
work and judging it — the supervisor model that catches its sibling's
reward hacking.

**ConTree/Token Factory Sandboxes**: wired (`PEX_PUBLIC_PYTEST_BACKEND=contree`
dispatches the bounded verification set into a disposable network-isolated
VM), gated on the Sandboxes beta — declared honestly, never silently
falling back.

## Tooling feedback (required field — draft)

- **Token Factory**: OpenAI-compatible endpoint made integration a provider
  entry, not a rewrite. Model catalog endpoint made the smoke check trivial.
  A first-class "verify my key+model" recipe in the console would shortcut
  onboarding.
- **Nemotron-3-Super-120B-A12B**: strong at structured judgment — it read an
  acceptance criterion, inspected evidence lines, and produced an actionable
  correction for a live worker that stopped early. Deterministic-enough
  for supervision when bounded (we cap dispatches per session).
- **Wishlist**: Sandboxes/ConTree beta availability for CI; a published
  latency profile per model would help teams size supervision budgets.

## Links to wire up at submission time

- Demo video: `assets/pcx-demo.mp4` (post to YouTube, link in form)
- Live escalation clip: `assets/pcx-mcp-worker-loop.mp4`
- Repo: https://github.com/josepha-mayo/pex (public, MIT)
- Judge path: `docs/HACKATHON.md` — five-minute replay path, no keys needed

## Honest capability line (put this somewhere visible)

Live-verified: OpenCode + Codex supervision, semantic Nebius/Nemotron rulings,
MCP worker↔PEX loop incl. worker-initiated escalation, deterministic replays,
evidence packs, human rulings surviving worker termination. Key-gated:
ConTree sandboxed verification (beta creds pending). Replay is always
labeled replay — nothing in the demo fakes a live call.
