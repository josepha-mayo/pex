# Stockroom paired successor — CODE ONLY, not activated

This new directory composes the existing actual Nebius worker, Stockroom task
adapters, managed review interface, cumulative worker accounting and cumulative
E2B pool. No existing runtime/expired loader is changed. There is no executable
CLI, live configuration, credential, provider call, VM creation or publication.

## Exact remaining blocker

A separately reviewed **successor supervisor admission entry is not implemented
or supplied here**. Existing `pilot_process.py` remains pinned to the expired
original 14:00 window and MUST NOT be edited/bypassed to launch this successor.
`run_successor(config_path, RootAdmission(...))` requires independently pinned
new supervisor source/config and this interface:

    SUCCESSOR_ENTRY_SCHEMA = 'pex.managed-supervisor-successor.v1'
    admit_successor(config_path, expected_config_sha256, approval_ref,
                    predecessor_sha256, prior_charged_nano_usd,
                    ledger_path, expires_at) -> managed_supervisor

The entry's admission must be local/no-network, validate explicit current owner
approval, exact model/endpoint/prices/output bounds and complete supervisor source
pins, bind SAME execution platform proxy/CA, initialize ONE durable ledger using
cumulative prior charges, retain uncertain charges, enforce original $0.25 cap and
request/session/proposal bindings, and expose `revalidate`, `model_factory`,
`summary`, `close`. `model_factory` must reuse the owned full managed planner/
verifier tool protocols, not a scripted correction or alternative model. `close`
must durably prevent reopening the concluded ledger. A shared parent-approved
successor budget is essential; new path/attempt counts do not reset prior spend.
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

The root must independently verify the complete predecessor evidence bundle; no private runtime evidence is included in this source checkpoint.

## Composition behavior

- Exact same frozen Stockroom public task/prompt, separate staged arms; nested
  directories are created before remote public uploads and readback checks.
- Same 12 calls, 49,152 output tokens, 180 active worker seconds per arm; all
  continuations consume the same worker budget. Stockroom worker task_profile and
  actual public unittest command are passed explicitly.
- WorkerFunding receives prior charge map + predecessor SHA. Original $0.375/arm
  monetary ceiling stays cumulative while 12 successor attempts are a new limit.
  Prior arm charges can differ, hence available remaining MONEY can differ even
  though call/time/output allowances match. Do not claim equal dollar resources.
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
and evaluator are not published. No live admission/config exists here; full
end-to-end integration and supervisor successor admission remain unverified.
The root-pinned source set covers composition/runtime sources, not every installed
third-party package; separately reviewed managed supervisor admission and runtime
qualification must address their dependency identities before launch.
