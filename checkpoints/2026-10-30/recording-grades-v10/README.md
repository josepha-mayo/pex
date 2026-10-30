# PEX final-grade recording V10 — WIP, authored-qualified only

Explicit upgrade from V9. Old V8/V9 checkpoints, Stockroom source, historical
recordings, and frozen benchmark configurations are unchanged. This code does
not run a benchmark, a provider, a VM, credentials, candidate code, or a capture.

## Opt-in observer and trust boundary

The sidecar's new `--final-grades` opt-in reads an already-finalized current-run
receipt. The independently root-reviewed exact configuration SHA remains its
external authority: root must review the **entire** source/SDK graph and the
real admitted producer, not just this observer. The observer additionally pins
core source versions whose grade semantics it understands. Those compatibility
pins are not a substitute for admission or source review.

Custody checks: configuration bytes and run identity; hash-bound launcher
terminal; exact closed-admitted report; per-arm durable grade artifact pin;
exact envelope run/config/full-source-set/task/arm/kind identities; exact payload
agreement (excluding the self-pin and separately attached phase0 result); raw
grade JSON, return code, summary, and protected grader hashes. Only finite safe
fields leave the private parser; raw test stdout/stderr is never displayed.

These hashes establish custody inside the root-controlled producer trust
boundary, not adversarial authenticity. A person controlling all inputs could
fabricate matching hashes. The retained same-VM limits remain visible; neither
this observer nor a hash proves real inference, a hardened grader, PEX benefit,
or publication eligibility.

## Exact task identities and unknowns

- `asyncpool_v1_cancel_safe_dual_limit`: protected expected 8, public expected 4;
  manifest `dcfdef0ac5790762e8b27639e8c3c8b47eb2a3cca24c4ed57603cadba5e72c76`.
- `stockroom_v3_atomic_reservations`: protected expected 40, public expected 6;
  manifest `90b1d9042ba5b223c75820dd70989c0d227216b884503d76926af21b1cbc5d60`.

Complete protected receipts show expected/executed/passed. Asyncpool candidate
or grader import failure shows executed 0 and passed **NOT MEASURED**, never
8 executed/failed. Missing, partial, stale, substituted, unbound, or unsupported
receipts emit no grade counters: unknown stays unknown, not zero. Public command
pass/fail is retained, but executed public-test counts are not independently
reported and are not inferred from expected counts. No baseline-to-PEX lift is
calculated. Final grades cannot be replaced by phase0 grades.

## Ordering and immutability

The sidecar observes the finalized receipt, emits any verified grade summaries,
and only then emits its single terminal event, which closes the feed. It never
reopens or rewrites a completed feed for a late artifact. If a grade is missing
at terminal observation it stays unknown in that recording. Malformed grade
artifacts do not suppress otherwise valid terminal status.

## Local qualification

137 tests plus 92 subtests passed; all evidence fixtures are SIMULATED / NOT REAL
INFERENCE. Coverage includes worker/planner/verifier excerpts, namespace guards,
8/40 task separation, public expectations, import failure, source/config/task/arm
and cross-run substitutions, forged return codes, partial/raw/summary mismatch,
malformed JSON/shapes, phase0 confusion, and late-arrival terminal ordering.
`preview_grade_display.py` is a no-file/no-network SIMULATED visual-fit preview;
its worst-case panel has 36 lines, maximum 96 columns. No native visual fit or
screen capture is asserted by these unit tests. Root independently inspected the
SIMULATED preview in a 1177x808 native terminal: all 36 lines fit, both grade rows
and NOT MEASURED were readable, and the eight-line excerpt was unclipped. That
was a visual check only, not a recording or model call. Fixture body headers
now say `PEX Evidence - SIMULATED`; the reserved native-window title is unchanged.

Future live use needs independent review and fresh frozen recording source
identities. Current E2B transfer/admission blockers remain unchanged.
