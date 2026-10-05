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
| Work must start inside the orchestrator | Attach to supported existing sessions; preserve the worker and goal identity | Real same-thread Codex recovery on clean `e864389`; current OpenCode 1.18.30 recovery on clean `93dfef3` |
| More activity is treated as better | Evidence-supported completion produces `NOOP`; intervention is bounded and measured as human attention | Current OpenCode quiet receipt on clean `6a1d98b` plus deterministic and contract coverage |
| One generic integration badge | Runtime capability labels distinguish Deep, Strong, Basic, Observe-only, Experimental, and Unavailable | Adapter, Cursor-hook, and UI contracts; unsupported live claims remain explicit |
| The model decides what is true | Strands proposes; request-bound evidence, an independent verifier, and local policy decide whether an action may proceed | Current recovery retains an approved independent-verifier decision and its bound read-only observations; failures still fail closed |
| Cloud control owns local side effects | AgentCore can host reasoning, but the local bridge retains credentials, policy, and execution authority | Exact-package local AgentCore protocol smoke; AWS deployment honestly remains open |
| Another transcript or kanban | A quiet desktop companion communicates working, drifting, and needs-human state | Exactly two shipping companions, Pex and Von, with transparent/dismissible native behavior retained on the prior candidate |
| Productivity claim from a convenient fixture | PexBench requires equivalent prompts/environments, private-evaluator separation, raw evidence, failed-run retention, and a coherent freeze | Integrity contracts pass; manifest remains honestly `frozen: false` and has no score claim |
| Verification trusts the worker's own host | `PEX_PUBLIC_PYTEST_BACKEND=contree` runs bounded public pytest inside a disposable, network-isolated Nebius ConTree VM, uploaded files bound to the fingerprinted manifest sha256s | Scripted-transport unit coverage; live sandbox execution requires Nebius Sandboxes beta access and reports its own honest `error_type` instead of masquerading as a test result |
| A green test run ends the audit | PEX seals the acceptance surface at goal attach and shows the byte-exact diff of what the worker weakened; a green run under an edited surface stays `uncertain` | Live-verified tamper scenario on OpenCode 1.18.32 — receipt + UI capture; `GET /v1/goals/{id}/acceptance-diff` serves sealed↔flagged bytes |
| Evidence can be reused forever | A green result that predates the last edit is downgraded `uncertain` with `later_edit:<path>` until a fresh run exists | `stale_evidence_eval` fixture; scored 5/5 by `scripts/eval_replays.py` on every push |
| "Working" means working | An observation gap beyond the configured threshold is reported as observed silence — never as progress | `observation.stalled` on session payloads; unit-covered gap semantics |
| Handoff means "we pasted some context" | `FRESH_HANDOFF` mints a content-addressed bundle, injects over the real transport, and stays `awaiting_target_evidence` until the target produces observable work | Live `handoff_injected` on OpenCode — `docs/demo/evidence/LIVE_OPENCODE_HANDOFF_*.json` |
| Replays can be steered | Recorded sessions are sealed evidence (`not_live_control`); they cannot be re-attached, resolved, or handed a bundle | `session_not_live_control` enforced at the store; demo badges them everywhere |

## What is real today

- Exactly two Codex-v2 companions, Pex and Von, are packaged in both verified installers.
- Clean source `c3cc44c` produced verified MSI and NSIS inventories with zero package blockers.
- Current focused gates pass 350 frontend tests (five platform-gated skips), 92
  supervision/recovery tests, and 243 expanded Strands/provider/AgentCore/evidence
  tests (four skips). The latest
  complete Python regression is 5,444 passed and 41 skipped on the `85af5ce` tree,
  with the ConTree slice re-verified focused at that revision; the earlier
  4,440-pass run at `570964b` is retained as a historical data point.
- A real Codex Spark worker and free Muse/Strands supervisor demonstrated restraint and
  specific same-thread recovery on clean `e864389`.
- A real OpenCode 1.18.30 worker and free Muse/Strands supervisor demonstrated one
  independently verified same-session recovery at `93dfef3` and one quiet completion at
  `6a1d98b`; each is a single diagnostic, not a benchmark score.
- A retained package source passes the real local AgentCore-compatible `/ping` and strict
  `/invocations` protocol path. This is protocol proof, not AWS deployment.
- A live OpenCode worker (free Nemotron 3 Ultra route, no key) was told to weaken the
  sealed acceptance test; every completion claim adjudicated `uncertain`, a corrective
  nudge named the file, and the worker restored it byte-identically before
  `verified_complete` — recorded in `docs/demo/evidence/` with a UI capture and video.
- A live goal handoff delivered a content-addressed context bundle into a sibling
  OpenCode session (`handoff_injected`) and honestly reported
  `awaiting_target_evidence` rather than claiming assimilation.
- `scripts/eval_replays.py` scores all five shipped replay fixtures against their
  declared supervision arcs in CI — 5/5, including stale-evidence and
  runner-config-injection vectors.

## What PEX refuses to fake

- It does not call Observe-only attachment “Deep control.”
- It does not claim that AgentCore is deployed without a Runtime ARN and live invocation.
- It does not publish a PexBench lift while the four-arm manifest is unfrozen.
- It does not treat browser screenshots as native overlay or resource-stability proof.
- It does not turn a timed-out independent verifier into permission to intervene.
- It does not report a sandbox infrastructure failure as a test outcome, or fall back to
  local execution of untrusted code when the operator selected the remote sandbox.
- It does not use hidden evaluator facts, task-specific nudges, or treatment-only prompts.
- It does not report a stalled worker as "working," reuse a pre-edit green run as
  current evidence, treat a handoff as absorbed without target evidence, or let a
  recorded replay accept live control.

## The five-minute thesis

Show one existing Codex worker, one persistent goal, and two outcomes. First, completed work
receives silence. Second, incomplete work receives one specific, evidence-bound nudge on the
same thread, then silence after the artifact is verified. Pex makes the state legible; Strands
provides bounded semantic judgment; local evidence and policy keep it safe. That is a tighter
and more human story than “we spawned more agents.”
