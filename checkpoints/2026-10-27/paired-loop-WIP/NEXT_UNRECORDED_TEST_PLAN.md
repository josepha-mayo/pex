# Unrecorded verification design

This document describes code and evaluation design only. It grants no execution,
resource or publication permission. Operational accounting remains private.

## Same-execution network binding

`same_exec_launcher.bind_root_policy` accepts an independently pinned private root
policy. The policy explicitly delegates only the currently supplied platform proxy
source; it does not accept an arbitrary proxy argument. Root source, endpoint,
model and CA identity stay pinned. Only a derived private template/config is written;
the helper never starts a run. The returned binding rechecks the same environment,
and the paid entry validates it before constructing resources.

A later authorized invocation must occur in the same execution after separate
cumulative admission. A stale binding is refused rather than silently falling back.
No TLS downgrade or change to default production transport is introduced.

## Preserve genuine observations

The review adapter now records the exact private public-evidence request before
model-factory invocation. A subsequent transport failure therefore does not destroy
the observation. This is future-only preservation, not recovery of historical data
that was never stored. Historical worker tool output must not be relabeled as an
exact later controller observation. Private requests never belong in source pushes.

## Evaluation sequence

- Keep recording off during initial verification.
- Prove both real provider stages function before attempting a comparison. A test
  using partial historical evidence must be labeled diagnostic, not a completed pair.
- Preregister multi-step tasks and protected checks before viewing outcomes. Use
  identical initial inputs, equal worker resources and independent workspaces.
- Allow only model-derived supervision from public evidence; do not leak hidden
  tests, script corrections, force baseline failure or tune one arm after grading.
- Preserve prior accounting and closed-run evidence; never reset resource ceilings
  merely by creating a new run directory.
- Record a demonstration only after completed unrecorded results support its claims.

Eight focused authored checks passed, covering binding identity, early refusal,
request persistence and prevention of dispatch after persistence failure. These
checks are orchestration evidence, not live inference or evidence of PEX benefit.
