# WIP asyncpool data adapter — no live admission

Separate task identity, exact manifest/public-content/prompt digests, public-only
staging, immutable public snapshot validation and distinct eight-check grade
schema. The monitor request carries only public task/source/check evidence.
The existing shared snapshot reader admits the asyncpool namespace only under
this exact task+manifest identity; Stockroom remains in its existing namespace.

The adapter deliberately does NOT create a VM, invoke a model, execute candidate
code, upload heldout checks or bypass an existing stopped admission. `dispatch`
always refuses. No existing Stockroom grant/run/context is reusable here.

Remaining live work: separately reviewed lifecycle/export/worker/grade integration,
new frozen comparison config and source pins, equal worker budgets, explicit
recipient permissions, isolated execution and recording. Do not describe this
code-only adapter or authored tests as measured PEX benefit.

Reference/heldout source is withheld from model context, not a secret security
boundary: source checkpoints may be public. Future workers must receive only the
exact public allowlist and may not fetch or access the evaluator/reference files.
