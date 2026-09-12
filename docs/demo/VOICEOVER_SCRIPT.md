# PEX demo voiceover — target 4:35

Read naturally; do not race. Bracketed text is a screen cue, not narration.
Keep credentials and account details off-camera. If the live take differs from
the words, describe what actually happened or discard the take.

## 0:00–0:25 — Problem

[Show the prepared OpenCode worker and the PEX Home window.]

“Coding agents save time, but running several of them creates another job:
remember the original goal, check every ‘done,’ catch drift, and keep typing
‘continue.’ PEX is a supervisor for the coding agents you already use. You keep
intent and irreversible decisions. PEX handles the mechanical babysitting.”

## 0:25–0:55 — Product and audience

[Show the selected OpenCode worker and its attached persistent goal.]

“PEX is for developers and other professionals who already work through tools
like OpenCode and Codex. It attaches through supported local interfaces rather
than replacing the worker. This goal is durable: both files need exact contents,
and PEX will judge progress against those acceptance criteria and observed
evidence.”

## 0:55–1:15 — Companion UX

[Dismiss the message while Pex remains visible. Open Companion Settings, switch
once to Von, then open Inspector.]

“The desktop companion is the attention surface, not another transcript. I can
dismiss its message without hiding the pet, or hide and restore it separately.
The focused build ships only two companions, Pex and Von. Inspector is where the
auditable details live.”

## 1:15–2:30 — Same-session recovery

[Show stage-one.txt, missing final.txt, the goal evidence, `SEND_NUDGE`, the
unchanged vendor session ID, and final.txt after correction.]

“This is a controlled recovery case. I deliberately asked the worker to finish
only stage one, so final.txt is missing. PEX observes that mismatch. Its Strands
supervisor cites the evidence and proposes one specific correction. Local policy
allows that bounded action, and PEX sends it to this same OpenCode session—not a
replacement agent with lost context. The worker creates final.txt, PEX observes
the exact result, and the outcome is recorded as helpful.”

## 2:30–3:15 — Strands and safety

[Show the sanitized `used_llm=true`, `runtime=strands-agents`, evidence IDs,
policy result, and outcome fields.]

“This is real Strands Agents reasoning over request-scoped, read-only evidence
tools. The model must return a validated structured action and cite observations
for any intervention. Strands proposes; deterministic verification and local
policy remain authoritative. Missing evidence, malformed output, a timeout, or
a rejected action safely becomes NOOP. The provider here is Zen BYOK using Muse
Spark Contributor Free, with a saved review cap of three and no silent model
fallback.”

## 3:15–3:50 — Quiet completion

[Switch to the separate completed case. Show both exact files, model-backed
`NOOP`, and zero PEX follow-ups.]

“Supervision is useful only if it knows when to stop. In this separate case the
worker completed both criteria before review. PEX verified the evidence,
Strands chose NOOP, and no follow-up was sent. The point is not more agent
activity; it is fewer unnecessary human interruptions.”

## 3:50–4:20 — Architecture and AgentCore

[Show `docs/architecture/pex-architecture.png`, then the local AgentCore protocol
receipt.]

“The desktop-owned bridge normalizes worker events, stores goals and evidence
locally, invokes bounded Strands reasoning, and policy-gates any same-session
delivery. PEX also implements a versioned AgentCore Runtime-compatible ping and
invocation contract. That path is locally tested, but I am not claiming a live
AWS deployment.”

## 4:20–4:35 — Honest close

[Return to Von or Pex beside the verified goal.]

“The formal comparative benchmark is not frozen, so I am not claiming an uplift
or leaderboard score. What this demo proves is narrower and useful: PEX can see
an incomplete goal, make one evidence-grounded same-session correction, verify
the outcome, and stay quiet when the work is already done. You keep the goal and
dangerous approvals. PEX keeps the mechanical supervision quiet.”

## Final export checks

- Duration is no more than 5:00.
- Video is publicly playable on YouTube or Vimeo.
- No credential, email, private task, or unrelated desktop content is visible.
- The recovery visibly uses one unchanged OpenCode session ID.
- The quiet case visibly has zero PEX follow-ups.
- AgentCore is labeled locally tested and not deployed.
- No benchmark score, uplift, or leaderboard rank appears.
