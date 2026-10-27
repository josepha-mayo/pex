# Supervisor failure timing checkpoint (WIP live qualification)

The controller previously recorded zero supervisor time when a review threw an
infrastructure or budget-exhaustion exception. A try/finally now retains elapsed
review time on those paths without charging it to the worker active-time budget.

Two authored fake-clock regressions reproduce 70 seconds of missing overhead
before this fix and preserve 70 supervisor seconds / 1 worker second afterward.
They use inert worker, reviewer and grader objects, not live inference or a real
benchmark. Failure classifications stay infrastructure_error and
supervisor_budget_terminal_inconclusive; no task failure or PEX gain is claimed.

Live qualification remains WIP. Default-closed supervisor gates stay unchanged.
Actual-CLI startup, provider inference, VM execution and browser UI are not
qualified by these tests. Prior live receipts must not be relabeled as results
for these changed bytes. Independently refresh any source pins that include the
controller before a later explicitly authorized run. Historical receipts and
closed predecessor evidence remain unchanged.

## Fresh verification after the timing fix

93 tests and 14 subtests passed against the changed controller, covering owned
mock planner/verifier composition, successor admission, Stockroom adapters, public
evidence boundaries, and stop persistence. The initial broader invocation lacked
the opencode_cli import root and stopped during collection; the corrected explicit
source-root invocation passed. No CLI binary, real provider, or VM was launched.

Five pre-existing stale manifest entries (cli_worker.py, nebius_worker.py,
probe_free.py, test_loop.py, test_public_infrastructure.py) were refreshed only
after local Git blob identities matched the existing remote files. This is source
identity correction, not new runtime qualification. The three actual-CLI test
modules remain unverified and excluded.
