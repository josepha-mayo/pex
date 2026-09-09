# Benchmark runtime preflight — 9 September 2026

Read-only checks at source `21246c4`:

- `Get-Command docker,wsl,WindowsSandbox -ErrorAction SilentlyContinue` found
  Docker CLI and WSL CLI, not WindowsSandbox on PATH. CLI presence does not prove
  a configured or running isolation environment.
- `docker version --format '{{json .Server}}'` exited 1: Docker Desktop Linux
  engine named pipe was unavailable. No engine was started.
- `benchmarks/boundary.py::execution_runtime_blockers` still reports no implemented
  OS-isolated worker/PEX and hidden-evaluator backend, plus no controller-enforced
  Cursor network-policy receipt.
- Manifest remains `frozen:false`, `task_execution_boundary: controlled_fixtures_only`.
  Natural task packaging is satisfied; natural-task execution, raw-log and Cursor
  same-session evidence gates remain unsatisfied.

Regression command:

```text
.venv\Scripts\python.exe -m pytest -q tests/unit/test_benchmark_execution_safety.py -k 'missing_runtime_isolation or manifest_assertions_cannot_create_runtime_isolation or post_run_evidence_does_not_make_execution_gate_circular' --tb=short
```

Result: 6 passed, 13 deselected, 3.58 seconds, exit 0. These checks call preflight
logic; they do not start a real worker, evaluator, model or desktop application.

The [earlier EFS probe](WINDOWS_EFS_BOUNDARY_PROBE_2026-09-09.md) is not a full
boundary: plaintext evaluator/task copies remain in repository/Git/other clones,
and Cursor is not covered by that Codex-specific denial evidence. Do not encrypt
or deny access to shared project paths used by other agents to work around this.

Next causal step: agree on a resource-bounded isolated execution environment,
implement and verify its worker/evaluator and network boundaries, then obtain
source-bound receipts before any scored live run. Starting Docker/VM services
requires fresh agreement under the native safety hold. Docker availability alone
would not complete the implementation or prove model/harness compatibility.
