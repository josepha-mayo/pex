# BENCHMARKS

Raw files in `benchmarks/results/` are append-only evidence. They must never be
edited, merged, or backfilled. Every new presentation row carries a chained row
hash; any legacy or edited file fails closed at freeze time.

## Design (frozen intent)

Four arms per task:

1. Cursor baseline
2. Cursor + PEX
3. Codex baseline
4. Codex + PEX

Primary metric: task success rate (independent hidden evaluator).
Headline secondary metric: human interventions per successful task.

The shared task wall budget includes worker and PEX time. PEX wall time,
interventions, and supervisor tokens are recorded when exposed; unavailable
worker tokens, cost, human active time, or unavailable vendor raw logs remain
explicitly null with availability flags. Every newly prepared workspace now has a
deterministic root commit for its exact public seed; the external preparation receipt
binds that commit, scoring re-verifies it in HEAD history, and each result row records it. PEX must not have benchmark-only
privileges.

**Same prompt rule:** baseline and treatment receive identical `TASK.md`. Treatment extra is an attached supervisor with tools, not a better prompt and not an oracle fact.

The hidden evaluator remains in the controller process. PEX decisions run in a
separate child process that receives only the public task, opaque session data,
worker messages, and an allowlisted public observation: relative file hashes,
the exact public-workspace fingerprint after observation, and normal visible
pytest output. Public tests run with explicit filenames, parent conftests and
plugin autoload disabled, hidden-marker paths excluded, and a post-test rescan.
Runtime gates reject
prompt drift, hidden-evaluator markers, treatment-only instructions, workspace
seed mismatches, worker-configuration mismatches, harness-version mismatches,
stale task packages, changed controller code, and missing fresh-workspace
receipts. Missing or unrelated replacement seed history fails before a row can be scored.

`live: true` is accepted only with transport evidence. Codex requires a running
`codex app-server` stdio process, an explicit worker model, and process-isolated
PEX audit records. In-memory transports are labeled `not_a_presentation_arm`
even when they exercise the full runner.

Cursor stop-drop files prove observation only. The this-desktop hook now also
records the follow-up it actually returned, and four-arm can wait for a later
stop on the same conversation. That still does not freeze Cursor+PEX:
isolated STOP now verifies claims against the public observation and treats a
still-failing pytest on STOP as unfinished work even without a tests-pass
claim, so a disable-pinned premature-stop CLI can return a real non-`PEX:`
nudge (`followups ≥ 1`, `used_llm: false`). Tests pin `PEX_SUPERVISOR_DISABLE=1`
so they cannot supply `used_llm` audits. Presentation rows still need a live
chain plus process-isolated supervisor audits (`used_llm`). Replayed payloads
and the user bridge on `:7420` cannot pass. Do not substitute a bridge queue
receipt.

## Task list (not frozen)

See `benchmarks/manifest.yaml`. The development smoke combines five
self-contained deterministic recovery tasks:

- premature stop
- forgotten acceptance criterion
- permission interruption
- cross-session handoff
- false completion

and three MIT-licensed, source-pinned QuixBugs reproductions: `wrap`,
`next_permutation`, and `kth`. Each natural package binds the upstream repository,
exact commit, source/test paths and SHA-256 values, exact packaged starter and
reference bytes, plus protected public source and license notices.

Every package has a concrete public prompt, starter repository, public cases,
private cases, and a private reference implementation used only to validate the
fixture. All eight reference implementations pass both case sets, and each of the
three natural starters fails before repair. The repaired handoff tasks use identical
durable artifacts in every arm; they do not assume an oracle fact known only to one
harness.

This meets the source-packaging part of the development-smoke task mix. It does not
yet meet the execution requirement: candidate code still lacks an enforced OS-level
filesystem/network boundary, so `natural_task_source_status` stays
`not_yet_satisfied`. Eight tasks are the §34.6 development-smoke floor, not the
30-plus final benchmark target.

## Predeclared execution and reporting protocol

`manifest.yaml` now fixes a deterministic 32-row schedule. It SHA-256 sorts 16
task-within-harness paired blocks and independently randomizes baseline versus
treatment order inside every block. Every row binds the schedule and protocol
hashes. The natural-completion cap is 600 seconds across worker plus PEX, with
evaluation timed separately. Selective task reruns are forbidden: a vendor
outage, disconnect, controller/provenance failure, budget exhaustion, or
operator intervention terminally aborts the run ID, preserves its partial
JSONL, and requires a complete restart under a new run ID.

`benchmarks/report.py` reads one result file without mutating it. Incomplete,
aborted, reordered, stale, or mixed-provenance data returns `NO-GO` with
`metrics: null`. A coherent run can produce a new derived directory containing
`summary.csv`, a statistical JSON report, failed-run appendix, deterministic
SVG plot, and analysis hashes. The analysis reports Wilson intervals, exact
McNemar tests, and deterministic paired-bootstrap intervals; it makes only
within-harness comparisons and reports telemetry missingness. Arm summaries
include both human interventions per task and the headline human interventions
per successful task. Human active time is availability-aware: a complete total
and per-success value remain null if any row lacks consented timing, while the
observed subtotal, median, missing-row count, and paired available-case delta
are labeled separately. Missing timing is never converted to zero.

Human interventions mean logged user actions that alter or unblock execution,
not PEX actions, automated approval decisions, or merely asking the user a
question. Codex isolated runs therefore start at zero; synchronous Cursor
evidence must include an exact action log. Routine-permission requests are
tracked separately as management requests.

Live Codex presentation runs now attach a controller-owned journal before the App Server
process starts. It writes every exact bounded stdin/stdout line as base64 plus byte length and
SHA-256, including malformed output before parsing, to one exclusive canonical JSONL file.
The footer binds run, arm, task, thread, initial turn, expected turn count, harness identity,
transport, direction counts, and completion time. Before a result row can append, the
controller independently reopens the stable bounded file and verifies the hash, contiguous
sequence, request/response closure, initialize/thread/start/turn/start receipts, and every
bound turn start/completion event. Capture, bound, identity, or validation failure aborts the
row; test doubles retain the older diagnostic-only normalized-event path. The journal module
itself is included in `controller_sha256`, so changing capture semantics invalidates the
controller/benchmark identity rather than inheriting an old provenance hash.

This closes the implementation gap only for Codex stdio. Cursor still exposes ordered local
hook receipts with explicitly partial coverage rather than a complete vendor transcript, so
the global §34.12 raw-harness-log preflight field remains `not_yet_satisfied` and presentation
freeze still fails closed.

`frozen: false` until one result file contains all 32 live rows (8 tasks × 4
arms) with an intact record chain, exact suite/controller fingerprints, paired
models/settings, fresh-workspace receipts, and real treatment audits. Coverage
may not be merged across files. If more than one coherent run exists, the run
must be selected explicitly.

## Current runs

**No valid presentation scores.** A prior Codex 1/5 vs Codex+PEX 4/5 run stuffed
treatment-only instructions and a handoff oracle into the worker prompt. Those
jsonl files are quarantined and must not be cited. Other local development rows
predate the current eight-task declarative fingerprint and hash-chain contract, so they cannot
freeze this manifest either; they remain preserved as raw development evidence.

Synthetic smoke remains `not_a_presentation_arm`.

## Next

- Implement synchronous, evidenced same-session Cursor continuation without
  opening a second Cursor window.
- Enforce an OS-level hidden-data/no-network worker boundary for the pinned natural tasks.
- Obtain exact worker-token/cost/raw-log telemetry and active-human-time capture
  where the harness surface supports it.
- Execute isolated paired arms with identical `TASK.md` and seed fingerprints.
- Freeze only the explicitly selected coherent result file; otherwise remain
  unfrozen and make no impact claim.
