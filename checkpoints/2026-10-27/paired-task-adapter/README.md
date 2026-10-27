# Fixed-task schema adapter — staged, not executed

Selected `05_uncertain_commit` from the frozen six-task pilot at 2026-10-27
00:59 UTC, before any live model result. Selection rationale: ambiguous remote
side effects and retry invariants are relevant reliability work. This is NOT a
claim that DeepSeek will fail, nor proof that this small fixture is sufficiently
complex for the user's eventual autonomous benchmark. No replacement based on
outcomes, modified task contract, scripted correction, or reference solution.

`task_adapter.stage(package, destination)` pins the preserved manifest and copies
exactly five allowlisted public files into independent baseline/PEX directories.
It returns a controller-owned staging receipt and the unchanged initial prompt.
The original acceptance test and evaluator code are verified but NOT copied into
worker directories. Reference solutions are neither read nor copied. The separate
controller/evaluator-inputs.json contains hashes, not private contents or paths.
Keep that receipt and preserved package outside worker access. Neither permissions
nor this staging layout establishes isolation.

`make_arms(destination, receipt, prompt, worker, paired_smoke.Arm)` returns the
actual existing hardened-controller paired-smoke schema. Supply the SAME admitted
Worker profile to both arms; this adapter does not lower baseline steps, change
budgets, inject corrective prompts, or execute anything. Call validate_pair on
these arms. The legacy eight-task repository preparation is a different schema;
this adapter does not claim compatibility with that schema or combine its scores.

Verification on these source bytes:
- Eight trusted authored inert-fixture unit tests passed (0.011 s), including
  modified source/protected inputs, symlink, hardlink, reused destination and
  changed staged bytes rejection. No generated code imported/executed.
- Real frozen package data staged locally; five public files per arm; constructed
  actual preserved paired_smoke.Arm/Worker and validate_pair passed. Worker
  fingerprints were explicit placeholder zeros, NOT an admitted runtime profile.
- Public file-map SHA256: 7c9e92a2d8ff2ac3d0a437d0183b7f940f2184663e7fde61bc60493e492157ca.
- No candidate grading, model calls, real benchmark, success rate or lift.

Run authored tests: `env -i PATH=/usr/bin:/bin python3 -m unittest -v test_task_adapter`.

Live gates unchanged: genuinely verified external worker/evaluator isolation and
expiry; protected receipt/oracle mounts; confirmed worker stop before immutable
candidate grading; admitted equal worker budgets; natural stop proof; separate
supervisor overhead/accounting; authorized fresh provider access and spending
controls. `paired_smoke.run_pair` still refuses live mode. Never execute a model
candidate on the host or weaken that gate. Its 90 s diagnostic arm budget is not
an effectiveness benchmark design, and the 256-token transport qualification is
unrelated. Infrastructure errors must not be scored as task failures.

Public checkpoint includes ONLY this adapter, authored tests and this note.
Staged worker files, protected receipts, runtime state and oracle contents are
not published. Directory trees and receipts are controller-owned trusted inputs,
not worker-authored data or an adversarial filesystem sandbox.
