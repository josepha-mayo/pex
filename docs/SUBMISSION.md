# Devpost submission copy

Track: **Professional Agents**  
Deadline: 14 Sep 2026, 17:00 PDT  
License: MIT  
Public repo: https://github.com/josepha-mayo/pex (MIT).

Do not cite quarantined benchmark rows in `benchmarks/results/INVALID_LEAKED_RUNS_DO_NOT_USE/`.

## Title

PEX — a goal-aware supervisor for the coding agents you already run

## Tagline

Stop babysitting Cursor, Codex, and friends. Keep the goals and the irreversible decisions.

## The problem

Long-lived coding agents created a new job: remembering the real goal, noticing drift, catching false “done”, re-approving the same safe test, copying context between windows, and typing “continue”. That work is repetitive and judgment-heavy. It is not the work people hired those agents to do.

## Who it is for

Professionals who already run Cursor, Codex, Claude Code, OpenCode, or similar harnesses and are tired of managing the managers.

## Why it matters

If agents keep multiplying, humans become full-time dispatchers. PEX attacks that job directly: attach to the sessions you already have, do the mechanical supervision, and only interrupt for real decisions.

## What PEX does

- Attaches to existing harnesses. Work does not have to start inside PEX.
- Runs a Strands supervisor loop with tools (goal, session, events, scores, verification, web search/scrape, typed actions).
- Uses a high-stakes graph (supervisor → independent verifier) for false-done / drift.
- Keeps a local policy guard. Cloud can propose; it cannot bypass allow/deny/ask.
- Surfaces attention as a desktop pet, not another chat transcript.

## Demo video voiceover (≤5 minutes)

Timebox. Screen-record the pet + inspector + one live Cursor or Codex session. Do not use leaked benchmark numbers.

1. **0:00–0:25 — Problem.** Several coding agents running. You are the babysitter: continue, approve pytest, catch drift, copy context.
2. **0:25–0:45 — Who / why.** Built for people who already use those tools. Goal: get the human back to intent and irreversible calls.
3. **0:45–1:30 — Pet.** Compact PEX pet. Status bubble. Open inspector. Show “what PEX did” and Ask without interrupting the worker.
4. **1:30–2:30 — Live attach.** Cursor hooks or Codex App Server actually attached. A nudge, continue, or permission decision with an audit line.
5. **2:30–3:30 — Strands.** Supervisor tools + verifier graph. Policy still local. Optional AgentCore `/ping` if deployed.
6. **3:30–4:20 — Honesty.** Four-arm PexBench exists. No invented lift. Paired arms share one TASK.md. Isolated supervisor process.
7. **4:20–5:00 — Close.** You keep goals and dangerous approvals. PEX keeps the rest quiet.

## Builder Center posts (bonus, up to +0.6)

Drafts in `docs/posts/`. Publish on builder.aws.com **after** the live path is on camera. Titles must contain **Agents for Humans**.

1. Building a Cross-Harness Supervisor with Strands and AgentCore
2. Measuring Human Attention as an Agent Benchmark
3. Designing Safe Autonomous Approvals Across Coding Agents

## Checklist before clicking Submit

- [x] Public GitHub repo with MIT license visible
- [x] README + architecture diagram (`docs/architecture/hackathon.md` and `docs/architecture/pex-architecture.png`)
- [ ] YouTube or Vimeo demo ≤5 minutes (working product + pitch)
- [ ] AWS Builder ID email on the Devpost form
- [x] Functioning local demo: `uv run pex-bridge --no-auth` and `npm run dev` in `apps/desktop`
- [x] AgentCore deploy in eu-north-1 **or** honest “not deployed yet” (AgentCore is optional, strengthens Technical Implementation) — **not deployed**; `aws sts` returns NoCredentials until `aws login`
- [ ] No leaked 1/5 vs 4/5 numbers anywhere on Devpost (keep this true on the form)
