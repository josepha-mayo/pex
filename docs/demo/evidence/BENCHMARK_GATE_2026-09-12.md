# PexBench integrity and readiness gate — 12 September 2026

This receipt records a fresh benchmark-system validation after publishing the
accepted PEX 0.1.0 RC1 Windows candidate. It is not a comparative agent result.

## Integrity suite

Command (from the repository root):

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short `
  tests\unit\test_pexbench.py `
  tests\unit\test_benchmark_public.py `
  tests\unit\test_benchmark_execution_safety.py `
  tests\unit\test_cursor_capture.py `
  tests\unit\test_cursor_delivery_store.py `
  tests\unit\test_cursor_followup_receipt.py `
  tests\unit\test_cursor_hook_preparation.py `
  tests\unit\test_cursor_inbox_budget.py `
  tests\unit\test_cursor_inbox_delivery.py `
  tests\unit\test_cursor_inbox_rejection_store.py `
  tests\unit\test_cursor_observe_idle.py `
  tests\unit\test_cursor_stop_response_authority.py `
  tests\unit\test_speculative.py `
  tests\contract\test_cursor_capture_hooks.py `
  tests\contract\test_cursor_delivery_ack_hook.py `
  tests\contract\test_cursor_hooks.py `
  tests\contract\test_cursor_prompt_policy.py `
  tests\e2e\test_speculative_execution.py
```

Result: **447 passed in 295.53 seconds**, exit code 0.

The selection covers PexBench prompt/provenance/integrity rules, immutable
result admission and chaining, hidden-evaluator boundaries, execution safety,
statistical/report refusal, Cursor capture/delivery/ack/policy behavior, and
speculative-supervision safety.

## Formal readiness

Command:

```powershell
.\.venv\Scripts\python.exe benchmarks\four_arm.py readiness
```

Result: exit code 0 with:

- `manifest_frozen: false`
- `coherent_runs: []`
- `can_freeze: false`
- Cursor hook mode `observe`

The decisive blockers remain:

- no single immutable result file contains a coherent four-arm experiment;
- no OS-isolated worker/PEX and hidden-evaluator execution backend;
- no complete immutable raw vendor-event capture;
- no controller-verified Cursor network-policy receipt;
- no synchronous Cursor+PEX same-session treatment;
- missing valid rows for the predeclared 32 arm/task cells.

Historical partial rows are diagnostic only. They do not share all required
pinned configuration and provenance fields and cannot be combined into a
score. The readiness command also identified an old synthetic-smoke fingerprint
as invalid; that file is non-presentation evidence and was not repaired or
rewritten.

## Claim boundary

The benchmark implementation is tested and fails closed. PEX has no citeable
four-arm uplift, confidence interval, leaderboard placement, or productivity
score. The submission should instead show the retained real OpenCode/Strands
same-session recovery and quiet-NOOP demonstrations, accurately labeled as
controlled behavioral evidence rather than a comparative benchmark.
