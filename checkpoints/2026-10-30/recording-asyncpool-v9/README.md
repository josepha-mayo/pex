# PEX recording support V9 — local qualification, not inference

This is an explicit upgrade of the active `benchmarks/live_recording` source
from its previous version through the immutable V7 stage-classification and
V8 readable-display checkpoints, plus the V9 authored-namespace guard.
The V8 checkpoint and historical recordings are unchanged.

## Repair

V8 allowed `EvidenceDisplay('authored-recorder-example').render()` and a follower
started with the same authored run ID but without `--authored-fixture` to emit
LIVE labels. The renderer, follower, event validator, metadata writer, and native
wrapper now reject known `authored-*` IDs without explicit fixture mode.
Fixture mode requires the reserved `authored-recorder-*` namespace and a literal
boolean flag. Tests that previously exercised authored prose through LIVE labels
now use explicit fixture mode and assert no LIVE label appears.

This guards accidental known-fixture mislabeling; it is not cryptographic proof
that arbitrary operator-authored input is a provider response. Root review and
hash-bound wire/ledger provenance remain mandatory. No automatic prose approval,
provider call, VM, credential read, or native capture is performed by this change.

## Asyncpool audit

The frozen asyncpool ID format is supported. The 16,384-output-token profile,
worker/planner/verifier parser, split source/display storage, root approval
triples, and terminal refusal remain supported. Recorder code has no Stockroom
name or check-count assumption. It intentionally does not display grades: eight
asyncpool checks are therefore neither shown nor mistaken for Stockroom's forty.
Counts/status and reviewed prose alone do not prove PEX benefit.

Local authored verification: 85 tests and 88 subtests passed. All fixtures are
SIMULATED / NOT REAL INFERENCE. The change does not establish actual inference,
a completed benchmark, a real benefit, or publication readiness.

Future live use requires explicit source review and fresh frozen recording
source identities; do not rewrite an already-frozen run configuration.
