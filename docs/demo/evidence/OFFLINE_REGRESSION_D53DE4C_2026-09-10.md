# Combined offline regression — 10 September 2026

Source: `d53de4c`, clean worktree throughout these commands. This is a selected
cross-component regression gate, **not** the full Python suite or live acceptance.

## Backend

From the repository root:

```text
.venv\Scripts\python.exe -m pytest -q tests/e2e/test_goal_lifecycle.py tests/e2e/test_goal_control_operation_routes.py tests/unit/test_public_task.py tests/unit/test_goal_intent_authority.py tests/unit/test_goal_control_operations.py tests/unit/test_goal_store_transaction.py tests/unit/test_goal_intent_semantics.py tests/unit/test_agentcore_client.py tests/unit/test_agentcore_runtime.py tests/unit/test_agentcore_preflight.py tests/unit/test_agentcore_pipeline.py tests/unit/test_strands_runtime.py tests/integration/test_strands_supervisor.py tests/unit/test_codex_pipeline_pump.py tests/unit/test_opencode_outcome_lineage.py tests/unit/test_opencode_pipeline_pump.py --tb=short
```

Exit 0: **423 passed in 111.34 seconds**.

Scope includes persistent intent updates, stale revision rejection, transaction
rollback, semantic intent hashing, AgentCore request/result contracts and routing,
fake-model Strands invocation/evidence handling, and Codex/OpenCode delivery and
recovery. Fixtures inject fake models/clients and temporary SQLite; the preflight
commands are mocked. No AWS deployment, paid inference, live worker attachment,
or native app launch occurred.

The recent focused capture-budget/writer and HTTP/SSE tests remain separately
recorded in CODE_AUDIT_COVERAGE; their entire containing test files were not part
of this combined backend command.

## Desktop

From `apps/desktop`:

```text
npm test -- --test-concurrency=2
```

Exit 0: **268 passed, zero skipped, in 6.842 seconds**. This tests view-model,
source wiring, request/recovery contracts, and package/pet validation contracts.
It does not render or exercise the native desktop.

## Remaining gates

- Current installer is still source `166a656`; later HTTP/Codex resource fixes
  await the next collected rebuild.
- Native safety hold remains active after the Codex-closure report.
- Real startup/recovery, transparency, animation, hide/dismiss controls and idle
  CPU/memory are not established by these tests.
- Visible BYOK, same-worker Strands supervision, live AgentCore proof, fair frozen
  benchmark, full source audit, filming and submission remain open.

691 passing tests across these two commands are regression evidence, not proof
that PEX is submission-ready.
