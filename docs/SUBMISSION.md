# Devpost submission copy

> **Draft only — release and submission remain NO-GO.** The real Codex + Strands loop is now validated on source revision `5c49c10`; do not publish or submit until that evidence is recaptured on the final reviewed release candidate, the packaged app is visually reviewed, and the operator gives action-time authorization.

**Honesty that must match README / STATUS:** Bedrock AgentCore Runtime is a deploy target, not a deployed service. The four-arm PexBench manifest stays `frozen: false`; there is no citeable impact score or retained public leaderboard rank. The September 6 Codex receipts are real live closed-loop proof, but they are not packaged-release proof. Do not cite quarantined rows in `benchmarks/results/INVALID_LEAKED_RUNS_DO_NOT_USE/`.

Track: **Professional Agents**  
Deadline: 14 Sep 2026, 17:00 PDT  
License: MIT  
Public repo: https://github.com/josepha-mayo/pex (MIT).

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
- Implements a bounded Strands supervisor with six request-scoped, read-only evidence tools and requires a validated structured action. The live Codex proof demonstrates real Strands decisions and outcome verification; it does not claim every tool path was exercised on camera.
- Routes semantic-only interventions through an independent verifier Agent in locally tested contracts; failures and evidence-free approvals become NOOP, while deterministic verification truth remains authoritative. The curated live receipt does not independently prove this tier, so do not call it live-demonstrated unless a judge-readable trace is captured.
- Keeps a local policy guard. Cloud can propose; it cannot bypass allow/deny/ask.
- Surfaces attention as a desktop pet, not another chat transcript.

On September 6, PEX completed both prepared live contracts with an isolated Codex worker and a real Strands supervisor: it stayed quiet after evidence-supported completion, then in a separate case detected incomplete work, sent a specific nudge to the same Codex thread, observed the resulting artifact, marked the intervention helped, and ended with a verified NOOP. The supervisor was Zen's free `muse-spark-1.3-contributor-free`; the intentionally modest worker was pinned to `gpt-5.3-codex-spark`. Recapture these contracts on the final release revision before submission.

Current source contains exactly eight built-in pets. A one-call hatch result is only an unverified base candidate, not a playable pet.

## Demo video voiceover (≤5 minutes)

Timebox. Screen-record the pet + inspector + one live Cursor or Codex session. Do not use leaked benchmark numbers.

1. **0:00–0:25 — Problem.** Several coding agents running. You are the babysitter: continue, approve pytest, catch drift, copy context.
2. **0:25–0:45 — Who / why.** Built for people who already use those tools. Goal: get the human back to intent and irreversible calls.
3. **0:45–1:15 — Pet.** Compact PEX pet. Close it, restore it from Settings, then open the inspector. Show that the companion communicates state instead of becoming another transcript.
4. **1:15–2:45 — Live recovery.** In one Codex thread, show the intentional stop, PEX's specific `SEND_NUDGE`, the second turn on the same thread ID, `report.txt = shipped`, `helped=true`, and the final evidence-supported `NOOP`.
5. **2:45–3:35 — Strands and safety.** Show the real `used_llm=true`, `runtime=strands-agents` receipts and the local deterministic-truth/policy boundary. Show an independent-verifier receipt only if a separate judge-readable capture exists. Do not call this a Strands Graph or claim web/side-effect tools. Optional AgentCore `/ping` only if actually deployed.
6. **3:35–4:15 — Restraint.** Show the separate completed-task contract: one turn, artifact `pong`, and PEX correctly choosing `NOOP`. The point is fewer pointless interruptions, not maximum agent activity.
7. **4:15–4:40 — Honest limits.** PexBench is not frozen and there is no retained leaderboard rank. AgentCore is a deploy target unless a live deployment is proven before recording.
8. **4:40–5:00 — Close.** You keep goals and dangerous approvals. PEX keeps the mechanical supervision quiet.

## Builder Center posts (bonus, up to +0.6)

Status: **1 / 3 user-reported published**. Its signed-in rendered Published state was
observed, but logged-out accessibility and bonus credit remain unverified; do not publish
it again. The other two remain local drafts. If they are published, use builder.aws.com
after the live path is on camera and keep **Agents for Humans** in each title.

1. Building a Cross-Harness Supervisor with Strands and AgentCore
2. Measuring Human Attention as an Agent Benchmark
3. Designing Safe Autonomous Approvals Across Coding Agents

## Checklist before clicking Submit

- [ ] Verify at action time that the public MIT repository contains the exact reviewed release candidate; the current dirty/untracked tree is not publication proof
- [x] README and architecture source/PNG are current; the 6 September render was visually inspected with the verifier in the blue local-contract tier
- [ ] YouTube or Vimeo demo ≤5 minutes (working product + pitch)
- [ ] AWS Builder ID email on the Devpost form
- [x] Validate a real authenticated same-thread intervention/NOOP and observed outcome on reviewed source (`5c49c10`; final-release recapture still required)
- [ ] Recapture the validated pair on the final release revision and record it in the packaged-app demo
- [x] Honest disclosure: AgentCore is optional and not deployed; AgentCore evidence is contract-only, while controlled local Codex + provider-live Strands evidence now exists
- [ ] No leaked 1/5 vs 4/5 numbers anywhere on Devpost (keep this true on the form)
