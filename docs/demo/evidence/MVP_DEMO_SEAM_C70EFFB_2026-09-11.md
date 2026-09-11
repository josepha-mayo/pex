# Offline MVP demo-seam regression

Source: clean `c70effb`, equal to `origin/main` before this evidence-only commit.
No native PEX window, browser, worker, provider call, credential mutation, or AWS
resource was used.

## Command

The pinned Rust 1.97.1 toolchain was prepended to `PATH`, then the repository
virtual environment ran:

```text
python -m pytest -q
  tests/contract/test_supervisor_settings.py
  tests/integration/test_strands_supervisor.py
  tests/e2e/test_goal_lifecycle.py
  tests/e2e/test_goal_control_operation_routes.py
  tests/e2e/test_ask_canonical.py
  tests/unit/test_providers.py
  tests/unit/test_supervisor_config.py
  tests/unit/test_strands_runtime.py
  tests/unit/test_opencode_completion.py
  tests/unit/test_opencode_outcome_lineage.py
  tests/unit/test_opencode_pipeline_pump.py
  tests/unit/test_codex_correction_pipeline.py
  tests/unit/test_codex_correction_framed_pipeline.py
  tests/unit/test_ask.py
  tests/unit/test_ask_review.py
  tests/unit/test_agentcore_pipeline.py
  tests/unit/test_agentcore_runtime.py
  --tb=short
```

Result: **475 passed, 1 skipped, 0 failed in 99.50 seconds; exit 0.**

## Covered seam

- supervisor provider configuration, credential-destination binding, revisions,
  activation state, and dispatch caps
- real Strands integration contract and typed model decision parsing
- persistent goal lifecycle, goal-control operations, and canonical Ask PEX reads
- OpenCode event ingestion, completion review, outcome lineage, and pipeline pump
- Codex correction plus framed same-thread correction pipeline
- supervisor Ask/review behavior
- AgentCore-compatible local invocation protocol, durable pipeline metadata, and
  bridge-owned local authority checks

## Boundary

This is broad offline integration evidence, not a live provider, live worker,
native UI, AWS deployment, or comparative benchmark. Current live OpenCode quiet
and recovery receipts remain the behavioral proof. The exact `c3cc44c` package
still needs the bounded visible acceptance pass before filming.

