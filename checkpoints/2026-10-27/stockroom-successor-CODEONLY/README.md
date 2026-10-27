# Stockroom paired successor — CODE ONLY, not activated

This new directory composes the existing actual Nebius worker, Stockroom task
adapters, managed review interface, cumulative worker accounting and cumulative
E2B pool. No existing runtime/expired loader is changed. There is no executable
CLI, live configuration, credential, provider call, VM creation or publication.

## Exact remaining blocker

The successor supervisor entry is now implemented and authored-qualified, but
**activation remains closed**: `successor_supervisor.APPROVED_RETRY_REF = None`.
Only after exact pending retry approval and parent coordination may root pin the
exact approval in source and regenerate all independent source/config digests.
No environment/config field can bypass the None gate. Existing `pilot_process.py`
remains pinned to its expired original window and is not edited or reused.
`run_successor(config_path, RootAdmission(...))` requires independently pinned
new supervisor source/config and this interface:

    SUCCESSOR_ENTRY_SCHEMA = 'pex.managed-supervisor-successor.v1'
    admit_successor(config_path, expected_config_sha256, approval_ref,
                    predecessor_sha256, prior_charged_nano_usd,
                    ledger_path, expires_at) -> managed_supervisor

The entry's admission must be local/no-network, validate explicit current owner
approval, exact model/endpoint/prices/output bounds and complete supervisor source
pins, bind SAME execution platform proxy/CA, initialize ONE durable ledger using
cumulative prior charges, retain uncertain charges, enforce the exact successor $0.30 cap and
request/session/proposal bindings, and expose `revalidate`, `model_factory`,
`summary`, `close`. `model_factory` must reuse the owned full managed planner/
verifier tool protocols, not a scripted correction or alternative model. `close`
must durably prevent reopening the concluded ledger. The parent-approved CODE/PREP split is $0.35/$0.35/$0.30 under the unchanged
$1 total Nebius ceiling; actual execution still awaits exact retry approval.
A shared successor budget is essential; new path/attempt counts do not reset prior spend.
No automatic import of the expired pilot entry or fallback is allowed.

Parent must coordinate exact retry approval and independently verify all config,
predecessor and source pins BEFORE any execution. Creating RootAdmission in code
is not evidence of user approval. Never derive its expected digests from worker
input or merely read them back from the config being admitted. Do not call any
live entry just because approval later appears without parent coordination.

## Config and predecessor contract

`successor_admission.REQUIRED` and `REQUIRED_SOURCES` define exact keys. Config
must be a private mode-0600 ordinary unlinked file under a mode-0700 directory.
RootAdmission independently pins config SHA, retry approval reference, original
funding approval reference, maximum expiry, predecessor SHA and successor-entry
SHA. All source/key/binary/package/network identities are validated before runtime
resource construction. Same-run revalidation occurs before each remote create,
review/model factory and controller admission. Existing output directory refuses
reuse; terminal states and ledgers are retained, never removed to reset ceilings.

Predecessor schema `pex.cumulative-predecessor.v1` contains `closed: true`, both
worker arm charges, supervisor charges, compute conservative upper bound and
`closed_evidence_sha256` binding the full root-reviewed evidence bundle. Root must
assemble this from original frozen run01 PLUS every later diagnostic/uncertain
reservation—not the original-only audit_closed helper applied to a successor.
The root-pinned predecessor receipt, all cumulative charges and config digest are
preserved in frozen/report outputs. This directory does not invent live totals.

Root must independently verify the complete predecessor evidence bundle. Private runtime evidence is excluded from this source checkpoint.

## Composition behavior

- Exact same frozen Stockroom public task/prompt, separate staged arms; nested
  directories are created before remote public uploads and readback checks.
- Same 12 calls, 49,152 output tokens, 180 active worker seconds per arm; all
  continuations consume the same worker budget. Stockroom worker task_profile and
  actual public unittest command are passed explicitly.
- WorkerFunding receives prior charge map + predecessor SHA. The exact successor $0.35/arm monetary ceiling stays cumulative while 12 successor
  attempts are a new limit. Both arms also receive the SAME fresh-phase limit of
  339,918,200 nano-USD, explicitly enforced by WorkerFunding. Prior charges remain
  in the cumulative totals; no arm can use the other arm’s spare remainder.
  If funding blocks either arm, classify inconclusive; never claim a PEX win.
- ComputeBudget receives conservative prior bound + predecessor SHA; same ledger
  is passed to PilotPool. Original $0.10 cumulative cap remains intact.
- OwnedReview gets frozen PUBLIC task spec and public evidence only. Exact public
  requests persist before managed model invocation. No hidden checks/reference in
  any worker/reviewer prompt or mount.
- Hidden grader requires both stopped and `mcp_revoked is True`; latter is set by
  worker only after successful MCP context closure. Grading uses remote isolated
  snapshot copies; candidate code never runs on controller. Same-VM anti-tamper
  limits remain, so no claim of adversarial isolation.
- Returned inconclusive/contract-changed grades promote controller state to
  grading_inconclusive. Resource exhaustion remains inconclusive even with partial
  grades. Recording off; pex_lift remains null; no presentation eligibility.
- Cleanup runs on every resource-bearing path. Success requires `terminal.json`
  with matching report digest after supervisor close. A report file alone is not
  a successful/fully-cleaned run. Cleanup uncertainty gets a separate receipt.

## Authored verification and limits

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/pex-stockroom-adapter-WIP-20261027-1432" \
      python -m unittest discover -s pex-stockroom-successor-CODEONLY-20261027-1442 -v

Tests use inert data/factories and fake keys only, never runtime_dependencies,
real NebiusCLIWorker, model factory dispatch, SDK or VM. Existing Stockroom task
and evaluator are not published. No live admission/config exists here. End-to-end authored controller/review/model
continuation is qualified, but live transport/inference/billing remain unverified.
The root-pinned source set covers composition/runtime sources, not every installed
third-party package; separately reviewed managed supervisor admission and runtime
qualification must address their dependency identities before launch.

## Successor supervisor authored qualification

`successor_supervisor.py` implements the exact new default-closed entry. It uses
the original complete ManagedPEXModel planner/verifier protocols, 1200/900 output
limits, original endpoint/model and 300/900 nano-USD token prices. One shared
Ledger reserves before every actual wire attempt, retains uncertain charges and
imports all prior liabilities without reset. Scope binds the frozen public task
and first observed PEX session durably; verifier requests must have been planned,
and request/proposal mutation refuses before dispatch. Durable closed admission
cannot reopen. Admission and model construction make zero transport calls.

Fresh-process `run_authored_supervisor.py` initializes NoOp telemetry before
framework imports. Nineteen authored tests use only HTTP MockTransport responses
and explicitly forbid sockets/DNS. They include complete owned planner/verifier
wire cycles, current controller + OwnedReview + same-session continuation then
NOOP, cumulative prior funding, default-closed gate, exact profile mismatch,
credential/proxy/source/session/request/proposal mutation, uncertain budget
terminal, and durable close/reopen refusal. These are not real inference or task
quality results. The paired controller uses an inert worker/grader in this test.

Authored tests synthesize approval only by monkeypatching the module in memory;
the checked-in source stays APPROVED_RETRY_REF=None. No legacy admission changes.
Task/evaluator/reference files remain private and excluded from publication.

Final combined fresh-process qualification (`run_authored_all.py`): **56 passed,
14 subtests passed**. This combines 12 pure runner/admission checks, 19 managed
supervisor checks and 25 Stockroom adapter checks. Peer audit's credential
read-between-validation race was fixed: the exact bytes used for ScopedCredential
are rehashed immediately before use; an authored changing-between-reads regression
confirms refusal with zero transport construction. All source approval gates stay
closed and no live/private configuration was created.
