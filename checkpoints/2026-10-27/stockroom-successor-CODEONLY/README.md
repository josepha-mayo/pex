# Stockroom paired successor — CLOSED, code-only WIP

The proposed **USD 2 total Nebius ceiling is awaiting user approval**. The actual
approved ceiling remains USD 1. This code does not authorize spending, create
credentials, launch a worker, start a sandbox, resume an interrupted run, deploy
anything, or submit a hackathon project.

Three source gates remain `None`:
- `successor_admission.APPROVED_PAIR_REF`
- `successor_supervisor.APPROVED_RETRY_REF`
- `worker_funding.APPROVED_SUCCESSOR_WORKER_REF`

Pair admission rejects before configuration or credential-file reads. The
supervisor independently rejects before its configuration, keys, ledger or
transport. The original USD 1 worker approval cannot open the larger profile.
Caller configuration or environment variables cannot open these gates.

## Frozen proposed funding profile

All amounts below are integer nanoUSD. These are cumulative ceilings, not extra
money on top of prior work. Historical uncertainty is not refunded.

| Component | Retained prior | Equal/new phase allowance | Effective cumulative ceiling |
| --- | ---: | ---: | ---: |
| Baseline worker | 10,081,800 | 400,000,000 | 410,081,800 |
| PEX worker | 9,382,800 | 400,000,000 | 409,382,800 |
| Shared supervisor | 659,514,900 | 521,020,500 | 1,180,535,400 |
| Total | 678,979,500 | 1,321,020,500 | 2,000,000,000 |

The worker ledger's common outer guard is 410,081,800. Each arm's separate
400,000,000 phase guard is also enforced, so PEX cannot borrow the 699,000
difference. There is no cross-arm pooling. Supervisor overhead remains separate.

The proposed phase permits twelve fresh requests, 49,152 output tokens and
180 active seconds per worker, including continuations, plus twelve shared
supervisor wire attempts. Historical attempt counts 10/10/9 remain evidence;
they are not represented as these new phase counts. Dollar charges never reset.
A request's large reservation or uncertainty can block further requests even
when actual usage was small. Exhaustion is inconclusive, not a task failure or
an automatic top-up/replacement.

E2B keeps the original USD 0.10 cumulative ceiling. The independently checked
prior bound is 19,965,000. With the existing synchronous, sequential verified
allocation/settlement path, the second-create peak is 78,787,500 and the final
full-lifetime bound is 39,930,000. No extension or replacement is authorized.

## Composition and integrity

- The exact frozen Stockroom public task, prompt and initial bytes are shared by
  both arms; separately staged workspaces and equal fresh worker limits are used.
- The actual OpenCode Nebius worker is retained. The supervisor uses the full
  owned planner/verifier protocols, not a scripted correction or substitute model.
- Admission pins task, source/import paths, dependencies, configuration,
  predecessor evidence, route/prices and the current platform proxy/CA identity.
  A changed input fails closed rather than selecting an alternate route.
- Public review requests are persisted before model invocation. Hidden checks or
  reference solutions are not placed in worker/reviewer inputs or mounts.
- Protected grading waits for worker stop and confirmed MCP revocation. Candidate
  code is not run on the controller. Same-VM grading remains anti-tamper-limited;
  this is not a claim of adversarial isolation.
- Unconfirmed cleanup or inconclusive grading prevents a successful comparison.
  Resources and ledgers are closed explicitly. Existing interrupted diagnostic
  output is never reopened as a fresh run or silently treated as completed.
- Recording remains off for initial qualification. No generalized PEX benefit,
  publication readiness or successful demonstration is implied by local tests.

## Qualification

The documented `run_authored_all.py` entrypoint now includes the pending-budget
regressions: **66 local tests and 14 subtests passed**. An independent reviewer
reproduced that result and a focused 41-test guard suite, checked all listed
source identities, and added synthetic boundary checks for the tighter PEX phase
guard and twelve-request limit. The broader current transport/process/adapter
suite passed **561 tests and 14 subtests**. These tests use authored responses,
inert factories and synthetic credentials, not real provider/VM execution.

The scoped post-edit review found no blocking code defect. It did not independently
re-audit historical ledgers or remote commit identity; those remain separately
verified root evidence. Fresh live configuration, complete predecessor pins and
resource viability must still be independently checked after exact user approval
and before any execution. All three activation gates remain closed.

See `PENDING_TWO_DOLLAR_PROFILE_WIP.md`, `PAIR_APPROVAL_GATE_WIP.md` and
`SOURCE_SHA256.json`. Earlier USD 0.35/0.35/0.30 plans and their test counts are
historical checkpoints in version control, not the current proposed profile.
