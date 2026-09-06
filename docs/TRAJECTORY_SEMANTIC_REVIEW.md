# Trajectory semantic review: verified gap and implementation contract

Status: **P0 OPEN**, inspected 6 September 2026 on source `7d0a19c`.
Binding authority: recovery spec section 15; core/build specs remain unchanged.

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

`loop.py` contains protected uncommitted work (SHA256
`392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`).
A narrow-edit permission question is pending. Preserve its existing work and do
not stage it wholesale. No implementation, new inference, runtime restart or
remote deployment occurred in this inspection. This contract is not a completion
claim and does not replace any broader submission requirement.
