# PEX offline acceptance receipt — 9 September 2026

This receipt records fresh, local acceptance checks on pushed source revision
`957c60c408a7463eccd12420cc660acc80b69cc3`. The checkout matched `origin/main`
before the checks. The only local modification was the separately protected,
unstaged `services/supervisor/src/pex_supervisor/loop.py` tail; its SHA-256 remained
`DEA56DA49607069E889D56DA0D458D7CF5284555967FCD617867316A6D7ED77E` and it was
not edited, staged, formatted, or restored during this verification.

## Strands and AgentCore contract gate

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short tests\unit\test_agentcore_client.py tests\unit\test_agentcore_pipeline.py tests\unit\test_agentcore_runtime.py tests\unit\test_agentcore_preflight.py tests\unit\test_strands_runtime.py tests\integration\test_strands_supervisor.py
```

Result: **200 passed in 23.00 seconds**, exit code 0.

This covers the bounded Strands runtime and integration path plus AgentCore client,
pipeline, runtime-envelope, and preflight contracts. It is not evidence that an
AgentCore Runtime was deployed or invoked. Current read-only deployment preflight
still reports no authenticated AWS CLI session, current AgentCore CLI/CDK, running
Docker engine, verified ARM64 image, or configured Runtime ARN.

## PexBench and Cursor-hook contract gate

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short tests\unit\test_pexbench.py tests\contract\test_cursor_hooks.py
```

Result: **201 passed in 343.82 seconds**, exit code 0.

This covers the eight-task benchmark package, deterministic seed/source provenance,
private-evaluator boundaries, immutable result contracts, reporting logic, and Cursor
hook contracts. It is not a completed four-arm experiment. The authoritative manifest
remains `frozen: false`; OS-enforced untrusted execution, controller-verified Cursor
network policy, complete Cursor raw logs, and synchronous same-session Cursor + PEX
treatment evidence remain open. No benchmark worker, model call, Cursor session, AWS
resource, native PEX process, or paid provider was started by these checks.

## Submission-safe claim

PEX has a fresh green offline Strands/AgentCore gate and a fresh green eight-task
PexBench/Cursor contract gate on the current pushed source. AgentCore remains a tested
deployment target, and PexBench remains an unfrozen development benchmark until its
remaining real-execution evidence gates are satisfied.
