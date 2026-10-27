# Stockroom isolated runtime adapter candidate

No live provider/VM calls, permissions changes, publication, or runtime-source edits.
Frozen task package remains unchanged, manifest SHA:
`c242f9128edd87b34c678e5e0db36527b556f0b2163533577e5c96320c3b5f19`.

## Runtime-owner integration (not performed by this package)

1. Import `stage, FILES` from `stockroom_task` instead of legacy task05 adapter.
   Stage returns `(frozen, prompt)` with existing `public_sha256` receipt fields.
   Copy ONLY staged `workers/{arm}` files to fresh corresponding worker mounts.
   Create all nested directories before uploads. Never mount this adapter's tests,
   entire source task package, protected evaluator, reference or qualification.
2. Replace worker's legacy public observation block with
   `stockroom_request.collect_public_observation(remote, receipt)`.
   The actual public command is `python -m unittest discover -s tests -v`.
   Merely replacing the request builder is insufficient: old worker executes
   test_smoke.py and would silently run zero Stockroom public tests.
3. Construct review with `make_public_request(package)` from stockroom_request.
   This provides frozen public TASK.md to the model, not hidden tests. Public
   smoke success leaves hidden acceptance explicitly uncertain. Public diffs
   include added helpers/tests, not just git-status names. Truncated evidence
   is UTF-8-byte bounded and explicitly marked; it is not a full repository view.
4. Construct `stockroom_grade.RemoteGrade(remotes, package, stopped,
   revoked=confirmed_mcp_revocation_callback)`. `await grader.grade(arm)` matches
   the controller shape. `revoked` MUST reflect successful relay/context closure,
   not just a stop-request flag: existing worker sets `stopped=True` BEFORE its
   context-manager exit, so that flag alone cannot confirm revocation. If closure
   is uncertain, callback returns false and grading does not upload hidden files.
5. Include all adapter execution-source hashes in independent runtime admission,
   including exporter/public-diff scripts. Do not alter the frozen task manifest.
   A grader result with status inconclusive/public_contract_changed is NOT a
   successful comparison. Controller currently stores grader reports without
   promoting their status; integration must propagate/interpret them explicitly.

## Grading behavior and boundaries

- Single grading per arm, both stop and revocation checked before export and again
  before hidden upload. Public regression tests run before hidden files arrive.
- Exports/hashes entire implementation/tests trees, including added modules,
  resources and tests, not only an original single implementation file. Refactors
  may remove internal implementation modules. TASK/existing tests must be unchanged.
- Export code is trusted read-only data collection executed only remotely; no
  candidate import on the controller. Bound: 128 files/128KiB aggregate excluding
  bytecode caches; symlinks/nonregular files refused. Bound refusal is inconclusive.
- Copies snapshot bytes into a new remote grading directory, uploads only trusted
  runner + hidden checks (NEVER reference), runs Python there as ordinary user.
- Checks exact schema, 17 parent checks, nonnegative integer counts, consistency,
  exit codes, and infrastructure-vs-quality distinction. Public failures remain
  visible and make `task_success` false even if hidden checks all pass.
- Same-VM anti-tamper limits remain explicit: no proof of absent escaped processes,
  sudo removal, candidate-proof hidden evaluator, or immutable execution. Hashes
  describe exported bytes, not proof the candidate cannot modify grading state.
  Never call this an adversarial sandbox or use it as evidence of general lift.

## Authored checks
Run from workspace root with installed PEX protocol types:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/pex-paired-loop-WIP-20261027-1012:$PWD/pex-supervisor-model-only-WORKING-20261026-2028/packages/protocol/src" \
      python -m unittest discover -s pex-stockroom-adapter-WIP-20261027-1432 -p 'test_stockroom*.py' -v

Tests use fake remotes and trusted local data collectors only. Candidate-like
marker files contain raising code to establish collectors do not import them.
No grader/model-generated code executes locally. No model inference, runtime
qualification, budget sufficiency, or PEX effectiveness is established.
