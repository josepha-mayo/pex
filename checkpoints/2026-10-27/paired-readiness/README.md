# PEX paired-run readiness: actual CLI compatibility, not a benchmark

2026-10-27. Source013a07c9322e22bb3c95a2bcf4f53c4ca4a607f8.

## Concrete repairs and new verified outcome

Actual installed OpenCode2.1.4 exposed two incompatibilities in the preserved repository CLI runner: JSON output no longer emits legacy step_start/step_finish, and positional multiword prompts are quoted (`--` additionally duplicated the prompt). This candidate retains the legacy validator unchanged and adds an explicit2.1.4 path: standalone server, exact stdin prompt, fresh-session/continuation sequence, and committed post-exit assistant finish=stop plus succeeded idle lineage, bound to the captured CLI message IDs and text. It refuses a changed/duplicated prompt, stale receipt, pending work, failed terminal result and cross-session output. Parent process groups are terminated on exit/failure; stdin delivery uses the same deadline.

Final actual CLI preflight completed first turn and one same-session continuation in2.171s, exactly two authored loopback SSE responses, invalid synthetic credential only,256 output-token cap per invocation, no tools. Ten negative/positive receipt unit tests and Ruff pass. Usage11/1 in the mock is authored, not measured inference. QUALIFICATION.json records exact captured-output hashes. Runtime DBs, profiles, raw logs and private tasks/oracles are deliberately not published.

## Exact safe command (authored responses only)

From this source directory, with the already installed pinned binary and plugin modules:

```sh
env -i PATH=/usr/bin:/bin python3 preflight.py --continuation \
  --binary /absolute/opencode-2.1.4/bin/opencode \
  --plugin-modules /absolute/installed/node_modules \
  --output /absolute/fresh/disposable-output
python3 -m unittest test_receipt -v
```

The binary must match SHA256 ca9b3ee262e33bb4e7aa0e1230dc61086a474c8c8016b980081d0719712fd2e7; plugin package version must be2.1.4. No package installation or downloads occur. Output directory must be new. No CLI credential profile or ambient environment is inherited. No live endpoint/key option exists in this preflight. Without --continuation it allows exactly one local request; with it exactly two, one per fresh CLI process. Shared45-second CLI deadline, steps1, no tools,256 output tokens per invocation. Output streams remain bounded64MiB each by the preserved executor. Local fixture responder validates exact path/model/stream/cap/no-tools/synthetic authorization and refuses extras.

Those small caps and scripted fixture replies are TRANSPORT QUALIFICATION ONLY. They must never become benchmark arm limits or manufactured baseline failure. No corrective solution/script is supplied to a benchmark task here.

## Negative route evidence supplied by the existing provider-readiness lane

The separate preserved OpenCode qualification already exercised an actual CLI429 response: one local POST for the free model at256 tokens, tools0, retry veto and nonzero exit. That evidence was not rerun or relabeled as task failure here. The positive startup and same-session checks complement it. This executor's strace attempt failed before the child ran (ptrace prohibited); no whole-process network syscall audit is claimed. Model requests were redirected/allowlisted to the authored loopback fixture with helper/WebSocket/retry vetoes, and received local requests are recorded.

## Exact remaining executable integration gaps

1. **Worker/evaluator boundary:** installed bubblewrap failed --unshare-all with `NETLINK_ROUTE socket: Operation not permitted`. Existing repository execute_attempt requires a verified Linux boundary and external expiry receipt. No host/private-task fallback was used. CLI DB lineage is trustworthy for these tools-disabled fixtures only; a tool-enabled worker must not be able to mutate controller DB/receipts or read private evaluator/oracles.
2. **Suite schema:** preserved six-task hardening pilot/controller and repository paired APIs are distinct schemas. Their tasks, scores and grading receipts cannot be mixed. Freeze one existing hard task/public contract and adapt its staging/grading deliberately, with no private oracle material in either agent context.
3. **Supervisor:** guarded model-only and tool-enabled managed transport public entry points still deny live invocation. A separate reviewed benchmark integration needs scoped actual planner+verifier transport, explicit telemetry isolation, durable pre-request reservations, no retries on uncertain outcomes, separate raw usage/cost and causal feedback receipts. No deterministic/scripted replacement or production deny-all removal occurred here.
4. **Resource/cost admission:** archived plans discuss a$1 inference ceiling and a separately authorized five-minute sandbox ceiling, but this source does not authorize creating a sandbox or spending now. Verify current per-action ceilings, provider prices and expiry before any live request; Nebius credit with overage enabled is not an unlimited/free admission.
5. **Fresh access:** root/provider lane owns fresh per-action OpenCode free-route and Nebius access. No old/revoked keys were read, no credentials created/transmitted, and no external inference occurred here. A tiny tools-disabled real free-route qualification can follow separately authorized access without pretending the coding sandbox is ready.

## Fair real paired run requirements

Same pinned OpenCode/DeepSeek worker, public task/initial prompt, permissions, autonomous behavior and comparable worker budgets in both arms. Treatment adds actual PEX-generated observation-grounded review, never a hardcoded correction/solution or a guaranteed-failure task. Record supervisor input/output/reasoning/cost/time separately and in treatment totals. Infrastructure429/timeouts/uncertain usage are not task failures or zero cost. Stop workers before private grading. Persist task completion/evaluator evidence independently of worker narration. No valid paired score or superiority claim exists from this readiness work.

This is a small delta on preserved public runner source, not recovered latest code, a full app, or production deployment. Owner web source and all original guards are unchanged.
