# Wirepool v1 — isolated clean-room repair benchmark

**Identity:** `wirepool_v1_cancel_safe_resp_client`. This is a new task, not the
previous dual-limit asyncpool task. Do not transfer prior scores to this task.

## Execution contract

* Worker input: precisely the eight paths in PUBLIC_FILES.json, rooted at public/.
* Worker prompt: INITIAL_PROMPT.txt. No reference/, heldout/, qualify.py, evidence/,
  manifest-private commentary, or mutation descriptions enter worker/monitor input.
* Worker implementation package: wirepool/. Public command:
  `python -m unittest discover -s tests -v` (8 public test methods).
* Post-worker grader, in the authorized isolated evaluation copy only:
  `python heldout/run_grade.py /absolute/candidate` (8 protected groups).
* The grader emits one `pex.wirepool-grade.v1` JSON object with exact fields
  schema/checks/passed/failed/complete/all_pass. Subcase failures count once per
  test group. Import failures emit `pex.wirepool-import-grade.v1`, zero checks,
  expected_checks=8, loader_errors=1, complete=false, all_pass=false, and either
  candidate_import_failure (exit 1) or grader_import_infrastructure (exit 2).
* Normal exit 0 means all eight protected groups pass; exit 1 means failure.
  A process timeout is inconclusive infrastructure/candidate-hang evidence, not
  eight executed failures. Public pass and protected pass are distinct signals.
* Target runtime: CPython 3.11.6 stdlib on admitted VM. Local qualification used
  CPython 3.12.14; this difference is disclosed, not silently equated.
* Proposed unchanged equal worker budgets: 12 model calls (8+4), 540 active
  seconds, max 16,384 output tokens/call. Supervisor overhead is separate.
  Parent/runtime owner must freeze actual comparison policy before dispatch.

## Source basis and authorship

Primary real bug reports, inspected 2026-10-30:

1. https://github.com/redis/redis-py/issues/2665 — ordinary async commands could
   leave unread replies after cancellation; the prior pipeline-oriented repair
   did not address every command path.
2. https://github.com/redis/redis-py/issues/2624 — cancellation after send and
   before parsing could shift later request/reply ownership by one response.

All task code, transport doubles, test schedules, reference, and mutants here
were authored locally. No upstream implementation or correct patch was copied
into the worker inputs. The extra pool-factory, codec, FIFO, shutdown and error
requirements are explicit benchmark extensions, not claims about the complete
historical Redis behavior. No live Redis, TCP, installed library, downloaded
software, API inference, or external resource job was used in qualification.

## Oracle and mutation evidence

The public and protected suites construct literal wire frames and observe only
the published API, wire writes/closes, event barriers, and acquired lease identity.
They do not import reference implementation internals. Watchdogs bound hangs,
not race placement: every correctness interleaving uses explicit events or
ready-queue barriers. See REQUIREMENTS_MATRIX.md and evidence/qualification.json.
Reference and deliberate faulty variants are authored test qualification, never
worker baselines. Starter failures do not predict any model outcome.

## Honest limitations and feasibility

This task combines incremental framing, command/pipeline reply ownership,
cancellation, graceful shutdown, and bounded FIFO connection creation across
multiple files. It should demand substantially more reasoning than a bare
bounded pool; that is a design assessment, not measured model difficulty.
A competent single worker may solve all of it. No baseline failure or PEX gain
is promised, selected, fabricated, or forced. Preserve every real attempt and
report baseline/PEX ties or failures as such.

The 16 test methods cover many subcases but are not a proof for all Python
interleavings or arbitrary hostile transports. The factory's own cancellation
cleanup and the synchronous non-raising close contract are trusted boundaries.
No real-server compatibility, throughput, or security isolation claim is made.
Protected checks are withheld from model context, not a hardened secret from an
adversarial worker on the same VM. Candidate execution must remain in the
approved evaluation environment, not on the controller.

## Author-side reproduction (no worker code)

`python -B qualify.py` runs only the authored reference, starter, and mutations,
records every result/log, and asserts reference success plus mutation rejection.
Evidence logs are frozen qualification artifacts; rerunning produces a new
snapshot and therefore requires a new MANIFEST pin, not in-place silent changes.
No existing adapter/source/runtime/pin was edited to author this package.
