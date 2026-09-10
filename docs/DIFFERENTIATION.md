# Why PEX is not another agent orchestrator

Most coding-agent control planes begin by spawning work that they own: a new agent, a new
worktree, a new task card, and another dashboard. PEX begins with a different object:

> the human, the persistent goal, and the coding-agent sessions already doing the work

PEX is the missing supervisory layer between “start another agent” and “keep checking every
window yourself.” It observes supported harness events, compares progress with durable intent,
verifies claims against local evidence, performs only policy-allowed mechanical follow-up, and
stays quiet when the work is actually complete.

## Judge-facing distinction

| Common orchestration pattern | PEX behavior | Current evidence |
| --- | --- | --- |
| Work must start inside the orchestrator | Attach to supported existing sessions; preserve the worker and goal identity | Real same-thread Codex recovery on clean `e864389`; native OpenCode recovery retained on its source revision |
| More activity is treated as better | Evidence-supported completion produces `NOOP`; intervention is bounded and measured as human attention | Real Strands quiet receipt plus deterministic and contract coverage |
| One generic integration badge | Runtime capability labels distinguish Deep, Strong, Basic, Observe-only, Experimental, and Unavailable | Adapter, Cursor-hook, and UI contracts; unsupported live claims remain explicit |
| The model decides what is true | Strands proposes; request-bound evidence, an independent verifier, and local policy decide whether an action may proceed | Fresh Strands/AgentCore gate 200/200; live verifier failure on `9966a60` correctly failed closed |
| Cloud control owns local side effects | AgentCore can host reasoning, but the local bridge retains credentials, policy, and execution authority | Exact-package local AgentCore protocol smoke; AWS deployment honestly remains open |
| Another transcript or kanban | A quiet desktop companion communicates working, drifting, and needs-human state | Exactly two shipping companions, Pex and Von, with transparent/dismissible native behavior retained on the prior candidate |
| Productivity claim from a convenient fixture | PexBench requires equivalent prompts/environments, private-evaluator separation, raw evidence, failed-run retention, and a coherent freeze | Eight-task gate 201/201; manifest remains honestly `frozen: false` |

## What is real today

- Exactly two Codex-v2 companions, Pex and Von, are packaged in both verified installers.
- Clean source `567778b` produced verified MSI and NSIS inventories with zero package blockers.
- Current focused gates pass 290 frontend tests (one platform skip), 77 supervision/continuity
  tests, and 228 Ask PEX + offline AgentCore tests. The latest broad offline run is retained as
  4,426 passed and four failures; it is not mislabeled as a current full-suite pass.
- A real Codex Spark worker and free Muse/Strands supervisor demonstrated restraint and
  specific same-thread recovery on clean `e864389`.
- A retained package source passes the real local AgentCore-compatible `/ping` and strict
  `/invocations` protocol path. This is protocol proof, not AWS deployment.

## What PEX refuses to fake

- It does not call Observe-only attachment “Deep control.”
- It does not claim that AgentCore is deployed without a Runtime ARN and live invocation.
- It does not publish a PexBench lift while the four-arm manifest is unfrozen.
- It does not treat browser screenshots as native overlay or resource-stability proof.
- It does not turn a timed-out independent verifier into permission to intervene.
- It does not use hidden evaluator facts, task-specific nudges, or treatment-only prompts.

## The five-minute thesis

Show one existing Codex worker, one persistent goal, and two outcomes. First, completed work
receives silence. Second, incomplete work receives one specific, evidence-bound nudge on the
same thread, then silence after the artifact is verified. Pex makes the state legible; Strands
provides bounded semantic judgment; local evidence and policy keep it safe. That is a tighter
and more human story than “we spawned more agents.”
