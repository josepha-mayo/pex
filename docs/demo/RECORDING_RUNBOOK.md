# PEX five-minute recording runbook

Use the verified OpenCode recovery story, one PEX companion, and a clear persistent
goal. Mention Codex App Server support separately; do not imply control of an
arbitrary existing Codex desktop conversation. AgentCore deployment is optional
under the official rules refreshed through Devpost on 11 September 2026. The
organizers' latest guidance favors deterministic agent behavior over extra
features, so the take must make PEX's evidence checks, guardrails and same-worker
steering visible.

## Before recording

- Use the [public rehearsal card](REHEARSAL_CARD.md) for exact persistent-goal,
  worker-prompt and byte-check steps. It is a recipe, not a new passing receipt.
- Use the source-specific installer and receipt identified in the active
  [handoff](../AGENT_HANDOFF.md). Do not use old submission folders by habit.
- Confirm the package receipt still says `release_ready: true` with no blockers.
  The current candidate is product source `79d4d18`; its exact receipt and
  installer hashes are in [the package evidence](evidence/PACKAGE_79D4D18_2026-09-11.md).
- Complete the separately authorized bounded native stability run. Stop if startup, Retry,
  closing, or reopening hangs; retain the failure instead of filming around it.
  **Never run the quarantined 933239a native-smoke launcher.** It uses unsafe
  process cleanup. Close PEX normally through its own window; fixture controllers
  may stop only subprocess handles they created. Never kill a recursive PID tree
  or unrelated Codex/Cursor/Devin process to prepare a recording.
- Verify current free-provider availability before using the Muse supervisor and an
  isolated OpenCode worker. Historical receipts do not guarantee current pricing or
  availability. On 11 September, the official Zen page listed
  `muse-spark-1.3-contributor-free` as free on `/v1/responses`, but also documented
  account auto-reload and contributor-model training use. Before any take, verify
  auto-reload is disabled and select the exact Contributor Free ID—plain
  `muse-spark-1.3` is paid. Use only a public throwaway prompt/workspace. Never
  reuse the private proof session or switch to a paid fallback. See the
  [official Zen page](https://opencode.ai/docs/zen).
- Prepare one tiny workspace whose public acceptance criterion is visible on screen. Do not
  expose API keys, raw private worker state, hidden evaluator data, or local account details.
- Follow the README's two-terminal OpenCode setup: `serve` keeps the backend
  running; `attach` opens the worker interface on that same address. Create or
  resume the session in OpenCode before selecting it in PEX. An empty server
  is not a broken PEX connection, and connecting PEX does not create a task.
- Use the [shipping gate](../MVP_SHIP_GATE.md) and its source-bound evidence for
  claim boundaries. Historical blocks in `SUBMISSION.md` remain history; use only
  its current claim boundary and two-pet MVP copy for recording.

## Shot list

1. **0:00–0:25 — The problem.** Show one active OpenCode task and explain the repetitive human
   work: checking progress, catching a false finish, and typing another safe instruction.
2. **0:25–0:55 — Attach without replacing.** Open PEX Home and Inspector. State that PEX keeps
   the persistent goal and attaches through supported harness surfaces; it does not require the
   work to originate inside PEX.
3. **0:55–1:20 — Quiet companion.** Show Pex. Dismiss its message while leaving the pet visible,
   then open Companion Settings and switch once to Von. These are the only two shipping pets.
4. **1:20–2:45 — Same-session recovery.** In one isolated OpenCode session, show stage one
   stopping without `final.txt`, PEX's evidence-bound `SEND_NUDGE`, the follow-up on the identical
   vendor session ID, and the exact required `final.txt` artifact.
   Label this a controlled two-stage demonstration with a deliberate initial
   stop, not a naturally occurring failure or a comparative benchmark.
5. **2:45–3:25 — Real Strands and safety.** Show the sanitized receipt fields
   `used_llm=true` and `runtime=strands-agents`. Explain that Strands proposes a bounded action;
   deterministic evidence and local policy remain authoritative. Describe PEX as a steering
   supervisor with read-only evidence tools and a same-session delivery path, not a second chat.
   Show independent-verifier fields only if the recorded run actually contains them.
6. **3:25–4:00 — Restraint.** Show the separate completed OpenCode case, PEX choosing a
   model-backed `NOOP`, and zero PEX follow-ups. The benefit is fewer unnecessary human
   interruptions, not more agent chatter.
7. **4:00–4:25 — Engineering evidence.** Briefly show the source-bound current two-pet audit,
   broad MVP seam and bounded packaged-bridge idle profile, not a stale hardcoded test count.
   If useful, show the retained local AgentCore protocol receipt, but say AgentCore is the
   tested deploy target unless a real AWS Runtime is deployed before filming.
8. **4:25–4:45 — Honest limits.** Do not show or quote a benchmark lift. PexBench is unfrozen,
   and there is no public scored leaderboard.
9. **4:45–5:00 — Close.** “You keep the goal and the irreversible decisions. PEX keeps the
   mechanical supervision quiet.”

## Immediate rejection checks

Discard and re-record any take that:

- exceeds five minutes;
- shows a key, token, email, private thread content, or hidden benchmark material;
- implies AgentCore was deployed when it was not;
- calls the green benchmark tests a productivity result;
- uses a different worker thread for the recovery follow-up;
- hides a startup/recovery failure through editing;
- shows the old opaque pet card, non-closable message bubble, or stale pre-redesign stills.
