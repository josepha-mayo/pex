# One-shot supervisor process candidate — authored qualification only

This wires the existing owned PEX planner/verifier Strands tool transport to durable
per-wire-call reservations in a fresh process. It does NOT activate production,
web supervision, a real provider, or a paired benchmark. `invoke_live` refuses
unconditionally. The fixture factory only accepts an invalid authored endpoint and
synthetic model/credential; no provider credentials are loaded.

## Executed behavior
- Fresh `python -I` child, explicit trusted source paths, clean environment, no
  inherited OTEL variables/exporters; installs NoOp trace/meter providers BEFORE
  importing Strands. Late/ambient initialization refuses. This is process-local
  telemetry control, NOT an OS sandbox or hostile-code isolation guarantee.
- Both actual planner and verifier retain existing complete prompts, authoritative
  output schemas, evidence closures and three-round cap. Authored tests perform
  `get_goal` then final structured output; no scripted correction in application
  source and no deterministic replacement planner/verifier.
- SQLite FULL-synchronous committed reservation precedes transport creation. Each
  round—including forced-final—uses the same wrapper. Successful typed HTTP200
  single-dispatch raw-wire receipts settle usage; SDK-derived worker metrics are
  NOT accepted as supervisor wire evidence. Missing/uncertain/429/refused outcomes
  retain the entire reservation; no retry/rebate or missing-as-zero cost.
- Exact pricing/budget identity persists across reopen. Schema constraints plus
  validation of every existing row/receipt before new reservation refuse corrupt
  NULL/negative/noninteger charges, invalid state/identity and altered settlement.
  Atomic expected-state UPDATE prevents stale concurrent settlement overwrite.
- Launcher reads at most 64KiB aggregate stdout/stderr, 30s deadline, kills owned
  process group on completion/failure. It runs trusted authored fixtures only,
  never model-generated code. Explicit trusted source roots are NOT hash-admitted
  production runtime images.

## Latest verification
17 authored checks passed in the clean child (0.58s). Combined existing transport
299 plus new17 tests: 316 passed. No real network/provider/model calls; all response
bodies authored. No lift, cost savings, worker quality or paired result claimed.
The original299 results were rerun on current dependency sources, not transferred
from an older report. SOURCE_SHA256.json records this candidate and four transport
source files; full PEX/dependency admission remains separate.

## Run
From this directory (absolute paths to the existing trusted source/runtime):

    python3 launch_authored.py --python /path/to/pex/.venv/bin/python \
      --transport /path/to/managed-transport-candidate --pex /path/to/pex

Uses existing local packages; no install, network or resource provisioning.
Ledger files and test output remain private temporary artifacts, never source pushes.

## Limits and next live gates
Reservation currently uses configured `max_usage_tokens * max(rate)` as a
CONSERVATIVE FIXTURE ENVELOPE ONLY. max_usage_tokens validates observed responses;
it does not enforce provider input tokens, pricing, cash cap or account overage.
Live transport therefore remains denied even if a caller supplies flags/credentials.
A live path still needs separately reviewed exact authorization/provider/model,
validated request/token/pricing bounds, funded budget, isolated telemetry/runtime
identity, and expiry/worker-oracle isolation. Do not remove this gate merely because
fixtures pass. No provider-enforced cashcap is claimed.

The two roles are independently exercised, not yet a fully admitted planner ->
verifier -> actuation pipeline. Policy/evidence authorization, durable whole-run
accounting, immutable request/proposal binding and baseline comparability remain
separate admission gates. A valid structured reply does not authorize intervention.
