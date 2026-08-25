# BENCHMARKS

Raw files in `benchmarks/results/` are immutable once written and must never be hand-edited.

## Design (frozen intent)

Four arms per task:

1. Cursor baseline
2. Cursor + PEX
3. Codex baseline
4. Codex + PEX

Primary metric: task success rate (independent hidden evaluator).
Headline secondary metric: human interventions per successful task.

PEX overhead (supervisor tokens/cost) is included. PEX must not have benchmark-only privileges.

**Same prompt rule:** baseline and treatment receive identical `TASK.md`. Treatment extra is an attached supervisor with tools, not a better prompt and not an oracle fact.

The hidden evaluator remains in the controller process. PEX decisions run in a
separate child process that receives only the public task, opaque session data,
worker messages, and a public workspace file inventory. Runtime gates reject
prompt drift, hidden-evaluator markers, treatment-only instructions, workspace
seed mismatches, worker-configuration mismatches, and harness-version
mismatches.

`live: true` is accepted only with transport evidence. Codex requires a running
`codex app-server` stdio process, an explicit worker model, and process-isolated
PEX audit records. In-memory transports are labeled `not_a_presentation_arm`
even when they exercise the full runner.

## Task list (not frozen)

See `benchmarks/manifest.yaml`. Five management-stress tasks exist:

- premature stop
- drift
- permission spam
- false claim
- cross-harness handoff

`frozen: false` until live Cursor **and** Codex presentation rows exist.

## Current runs

**No valid presentation scores.** A prior Codex 1/5 vs Codex+PEX 4/5 run stuffed treatment-only instructions and a handoff oracle into the worker prompt. Those jsonl files are quarantined and must not be cited.

Synthetic smoke remains `not_a_presentation_arm`.

## Next

- Isolated live Codex arms with the attached supervisor loop (same `TASK.md`)
- Isolated live Cursor arms without opening a second Cursor window
- Then freeze the manifest from jsonl only
- AgentCore deploy after Docker engine starts
