# Trajectory semantic review: verified gap and implementation contract

Status: **P0 OPEN**, inspected 6 September 2026 on source `7d0a19c`.
Binding authority: recovery spec section 15; core/build specs remain unchanged.

## 6 September implementation follow-up — bounded repeated failures

The user approved narrow integration into `loop.py` while preserving its existing
uncommitted addition. The STOP-only gate below is now historical. New shared
candidate logic recognizes three observed nonzero command exits with matching
command/failure text, within ten minutes, bound to the active goal. Goal/session
pause, ambiguous/duplicate receipts, pre-goal events, successful commands and
intervening edits prevent stale accumulation. Ordinary progress remains quiet.

The bridge enables this path only with an explicit finite per-session dispatch
cap. Candidate reservation and cap reservation share the planner dispatch
transaction. A durable key binds session, goal content, selected workspace,
failure and observed progress anchor; repeated keys become audited
`trajectory_review_coalesced` NOOP without provider dispatch, including after
restart. New failure text can be reviewed until the cap is exhausted. Failure,
timeout and cancellation do not refund a possibly consumed reservation.

Codex normalization retains typed exit codes even when no pytest receipt exists.
Local evidence tools and the redacted cloud request carry exact candidate event
IDs and exit codes, not raw process output. Cloud routing retains eligibility.
The prompt calls this a candidate, not a drift verdict; completed NOOP survives.
Both local arbitration and the bridge's remote-result contract require independent
verification for material trajectory corrections. Inactive request extensions
are omitted from serialization to preserve historical evidence digests.

Verification so far: 293 tests across twelve complete affected files passed;
the additional remote missing-verifier guard passed the 96-test trajectory/client
gate. Final workspace-incarnation/pipeline/client gate: 117 passed in 76.86s.
No live model calls, provider settings changes or remote deployments occurred.

This is one material signal, not section 15 completion. Semantic search repetition,
dependency/constraint/context candidates, measured restraint and same-worker live
outcomes, time-based pacing and aggregate model-call/token/cost accounting remain
open. The existing dispatch cap is not a spending guarantee. Native UX, other
spec requirements and final-source packaging remain separate unclosed gates.

## Current call path

1. `pipeline.py` reserves and claims a durable planner effect, checks current
   workspace authority, then calls `needs_semantic_inference(request)` before
   `_invoke_supervisor`. This flag influences ambiguous-dispatch reconciliation.
2. `agentcore.py` routes local requests to `decide_async`; remote/hybrid requests
   separately use `needs_semantic_inference` to choose local deterministic work
   or AgentCore dispatch.
3. `loop.py` again gates the actual local inference. Its ordinary gate accepts
   STOP with a goal; `force_llm` or PEX_FORCE_LLM bypasses that restriction.
4. `runtime.py` validates the remote request and passes a force flag to `decide`.

A bridge-only forced call would leave routing, accounting or remote behavior
inconsistent. Enabling global PEX_FORCE_LLM would risk calling a model on routine
events, contrary to the user's quota concern. Neither workaround was applied.

## Required implementation and verification

- Use one shared, explicit eligibility decision across local and remote paths.
  Preserve STOP behavior; require an attached active goal and a material observed
  candidate for mid-task review. Ordinary progress must remain cheap and quiet.
- Candidate evidence is not a verdict. Carry exact source/current event IDs,
  workspace/goal authority, and current progress into semantic evidence gathering.
  Do not restore deterministic duplicate-work or broad-refactor accusations.
- Bound review frequency and total model use per session; coalesce repeated
  signals without hiding new failures. Make budget exhaustion auditable and
  non-corrective. Reuse existing durable dispatch ownership and reconciliation;
  never retry an ambiguous model dispatch as if it certainly did not happen.
- Preserve local/AgentCore parity, exact action authority, independent verification
  where required, cancellation behavior and stale workspace/goal rejection.
- Mocked tests first: normal progress/no goal => no model call; material candidate
  => evidence-gathering review; justified NOOP survives; justified correction
  retains references; failed inference => silence; repeated candidate within
  budget window => no duplicate inference; changed goal/workspace => no stale
  action; remote/local routing agrees on eligibility.
- Then live evidence under the user's model/budget authorization: real mid-task
  signal, actual Strands call, justified decision, same-worker continuation and
  measured outcome. Mocked success is not this gate.

## Ownership and current limits

### Budget audit follow-up — source `5ee1ee7`

Subsequent implementation adds an opt-in durable per-session **dispatch** cap;
see `SUPERVISOR_DISPATCH_LIMIT.md`. It counts attempts conservatively and returns
NOOP on exhaustion. This is one guard, not completion of the aggregate monetary,
inner-model-call, UI and trajectory-budget requirements below. The following
paragraph records the pre-repair audit and must not be read as current absence
of the newly added dispatch cap.

Inspected bridge Settings and `_invoke_supervisor` / durable planner-dispatch
paths, plus local Agent construction and provider token settings. No dedicated
per-session semantic-dispatch count or cumulative-spend reservation was found in
these paths. Existing limits are different: 30-second bridge invocation wait,
bounded local inference waits, selected provider output-token caps, bounded
evidence payloads, and durable protection against repeating the same planner
effect. None guarantees a total dollar or account-quota limit across new events.
The local wait shields an inference task, so a timeout is not proof that its
underlying provider work stopped. Treat ambiguous/failed dispatches as potentially
consumed work when implementing a budget; do not refund them solely because no
successful result arrived. Also include verifier/tool-loop model use, not only
one nominal supervisor invocation. This was a source audit, not a live billing
experiment, and does not claim that spending has occurred in these local checks.

Before enabling ordinary mid-task inference, implement/test the shared budget
reservation and expose its exhausted/unknown state honestly. Do not describe
existing timeouts or a free-provider label as a no-charge guarantee.

`loop.py` contains protected uncommitted work (SHA256
`392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`).
The narrow edit is now authorized; preserve the existing addition and do not
stage it wholesale. The paragraph's hash records the pre-integration file, not
the modified source. No runtime restart or remote deployment occurred. This is not a completion
claim and does not replace any broader submission requirement.
