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
- Exact route fingerprint, endpoint, model, role, currency, pricing provenance digest
  and numeric pricing/budget identity persist across reopen. Mismatched routes
  cannot reuse another route's rates, even when numeric prices are identical. Schema constraints plus
  validation of every existing row/receipt before new reservation refuse corrupt
  NULL/negative/noninteger charges, invalid state/identity and altered settlement.
  Atomic expected-state UPDATE prevents stale concurrent settlement overwrite.
- Launcher reads at most 64KiB aggregate stdout/stderr, 30s deadline, kills owned
  process group on completion/failure. It runs trusted authored fixtures only,
  never model-generated code. Explicit trusted source roots are NOT hash-admitted
  production runtime images.

## Latest verification
Fresh independent verification at 2026-10-27 02:18 UTC: 28 authored checks
passed in the clean child (0.65s), including route/model/currency/provenance
mismatch and reopen refusals. Source blobs accounting.py and test_process.py
exactly matched remote checkpoint 1c431323b0b85f45c2185843ec991e087f28d150.
The earlier combined 316-test result was for the previous 17-test candidate;
it is historical, not a fresh combined pass for these changed bytes. No real
network/provider/model calls; all response bodies authored. No lift, cost savings,
worker quality or paired result claimed. SOURCE_SHA256.json now identifies this
candidate and four transport source files; full dependency admission is separate.

Follow-up combined run at 02:19 UTC: **327 passed in 4.17s** (299 existing
transport + 28 current process checks). The first combined command produced
326 passes and one nested telemetry-subprocess import failure because the
ad-hoc harness omitted protocol source paths from its child PYTHONPATH. The
rerun supplied the same explicit trusted source paths to that nested process;
no application or test logic was changed to obtain the passing result.

## Run
From this directory (absolute paths to the existing trusted source/runtime):

    python3 launch_authored.py --python /path/to/pex/.venv/bin/python \
      --transport /path/to/managed-transport-candidate --pex /path/to/pex

Uses existing local packages; no install, network or resource provisioning.
Ledger files and test output remain private temporary artifacts, never source pushes.

## Limits and next live gates
The legacy authored profile uses configured `max_usage_tokens * max(rate)` as a
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

## Split-envelope candidate — 2026-10-27 10:31 UTC (WIP, authored verification passed)

Ledger now optionally accepts input_token_bound=262144 and output_token_bound=4096.
This exact profile requires the catalog Nemotron Super model, US endpoint, USD,
300/900 nano-USD per input/output token, max_completion_tokens output field and
request output limit at most 4096. It reserves 82,329,600 nano-USD before each dispatch. Validated
actual usage settles lower, so six small calls can fit a 250,000,000 nano-USD cap;
three full/uncertain reservations prevent a fourth. This does not guarantee enough
budget to complete a review. Missing/uncertain receipts retain full reservations.
Cached input is priced fully; reasoning is included in output, not added twice.

Profile identity is persisted; pre-profile databases require a NEW private ledger,
not silent migration. Focused authored tests cover dynamic settlements, concurrent
reservations, full/uncertain caps, route/rate/profile identity, and token overflow.
Fresh clean-child run: 46 passed in 0.79s. Combined current transport/process run:
345 passed in 4.76s. These are authored responses/local SQLite checks only.
No live inference or provider-enforced
cash cap is claimed. Finite whole-pilot attempt count and combined planner/verifier
budget coordination remain controller responsibilities, not this single-route DB.

Contractual sources: official public catalog /api/public/models_info on
https://tokenfactory.nebius.com and canonical Chat Completions documentation
https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion .
Official cookbook pins the US endpoint/model:
https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-super-120B.md .
Public regional routing can change: no automatic fallback or retry is authorized.
The split profile grants no authority; invoke_live still refuses unconditionally.

## Shared pilot funding candidate — 10:37 UTC (WIP, authored verification passed)

Use ONE private Ledger database/instance for the pilot, primary route=planner,
approved_routes=(planner_route, verifier_route), max_attempts=12, budget=250000000,
input_token_bound=262144, output_token_bound=4096. The two routes must be identical
except role and their individually pinned output limits. Shared mode refuses any different ceiling, attempt limit or role set.
It persists both fingerprints and the global attempt limit; each receipt must match
its own reserved route AND role. The same SQLite transaction checks aggregate
settled/uncertain cost and all attempted reservations before admitting either role.
No separate per-role funding pools are permitted. Reopening cannot reset the cap.
Pre-shared-profile ledger databases require new private storage; never reuse a fresh
DB to bypass an already begun pilot. Controller must retain this exact DB across
both roles and process restarts. Live process admission remains closed.
New authored tests for cross-role receipts, interleaved/concurrent shared costs,
global attempt exhaustion and reopen/corruption passed: 58 focused clean-child
checks in 0.97s; 357 combined current transport/process checks in 5.31s.
All responses authored; no actual inference or payment.


## Private one-pilot entry — 2026-10-27 10:51 UTC

`pilot_process.pilot_model(private_config_path, request, invocation_id=...,
proposal=None, expected_config_sha256=...)` is a separately scoped, root-only
entry. The ordinary `invoke_live` and production model gates remain denied.
The independent expected configuration SHA is mandatory: do not derive it from
an untrusted worker's supplied file. The controller must create and pin the file
inside a mode-0700 directory, mode-0600 config and credential files. Exact schema
is code-owned in `_load_config`; complete source module hashes are mandatory.

Admission pins the recorded one-pilot approval, fixed pilot identity, exact
model/US endpoint/prices/budget/attempt count, private key digest, shared ledger
path, and goal/session/vendor-session. A fresh process must initialize NoOp
telemetry before framework imports. The internal execution expiry is no later
than 2026-10-27 14:00 UTC (not a user-stated deadline). All bindings are rechecked
before each call. Existing planner1200/verifier900 output limits are unchanged;
4096 remains only the conservative output reservation bound. Original bridge
source was restored unchanged; no global role-policy override remains.

Factory construction makes no provider request. Calling `await model.invoke_async()`
uses the owned full prompts/tools and exact authenticated HTTP transport with one
completion, no retries/redirects/fallback/custom tier. Each call reserves first in
ONE shared durable ledger. Root cleanup MUST call `close_pilot(path,
expected_config_sha256=...)` after success or failure, revoke temporary keys, and
retain the ledger as private evidence. Close persists a terminal state; reopening
cannot spend again. Never reset/delete the ledger to bypass exhaustion.

Fresh checks: 73 focused clean-child tests passed in 1.42s; 372 combined current
transport/process/pilot tests passed in 4.98s. Four authored HTTP responses drive
actual owned planner/verifier protocols through the same ledger; config/approval,
expiry, source identity, request binding, file permissions, key changes and
terminal reopen failures are exercised. External sockets are forbidden by tests.
These are authored fixtures, NOT live inference, provider billing verification,
a completed paired benchmark or demonstrated PEX improvement. Runtime config,
credentials, ledger and recordings remain private and are never source pushes.
