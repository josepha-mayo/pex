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
worker tokens, cost, human active time, vendor raw logs, or repo commits remain
explicitly null with availability flags. PEX must not have benchmark-only
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
receipts.

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

See `benchmarks/manifest.yaml`. The recovery suite deliberately remains the five
self-contained deterministic tasks that existed when the recovery spec froze
feature expansion. It covers:

- premature stop
- forgotten acceptance criterion
- permission interruption
- cross-session handoff
- false completion

Each package has a concrete public prompt, starter repository, public cases,
private cases, and a private reference implementation used only to validate the
fixture. All five reference implementations pass both case sets. The repaired
handoff tasks use identical durable artifacts in every arm; they no longer
assume an oracle fact known only to one harness.

The recovery spec says not to add benchmark tasks before the live closed loop
passes. The discarded 006–036 microtask expansion was therefore not a valid
way to improve the impact claim.

This suite is the deterministic management-stress half only. It is
repository-shaped, but it is not a frozen set of public reproducible repository
issues or SWE-bench Verified tasks. Natural-task coverage in §34.6 remains a
NO-GO gap and the suite must not be described as satisfying that half of the
primary experiment.

## Predeclared execution and reporting protocol

`manifest.yaml` now fixes a deterministic 20-row schedule. It SHA-256 sorts 10
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

Current harness capture hashes the normalized event subset used by the
controller, but it does not yet retain and bind a complete vendor raw event
log. That §34.12 integrity requirement is an explicit preflight blocker, not a
null field that can silently pass a presentation freeze.

`frozen: false` until one result file contains all 20 live rows (5 tasks × 4
arms) with an intact record chain, exact suite/controller fingerprints, paired
models/settings, fresh-workspace receipts, and real treatment audits. Coverage
may not be merged across files. If more than one coherent run exists, the run
must be selected explicitly.

## Current runs

**No valid presentation scores.** A prior Codex 1/5 vs Codex+PEX 4/5 run stuffed
treatment-only instructions and a handoff oracle into the worker prompt. Those
jsonl files are quarantined and must not be cited. Other local development rows
predate the current five-task declarative fingerprint and hash-chain contract, so they cannot
freeze this manifest either; they remain preserved as raw development evidence.

Synthetic smoke remains `not_a_presentation_arm`.

## Next

- Implement synchronous, evidenced same-session Cursor continuation without
  opening a second Cursor window.
- After the live recovery loop passes, replace or supplement the recovery
  fixtures with a predeclared natural public-repository task set and validate its setup.
- Obtain exact worker-token/cost/raw-log telemetry and active-human-time capture
  where the harness surface supports it.
- Execute isolated paired arms with identical `TASK.md` and seed fingerprints.
- Freeze only the explicitly selected coherent result file; otherwise remain
  unfrozen and make no impact claim.
