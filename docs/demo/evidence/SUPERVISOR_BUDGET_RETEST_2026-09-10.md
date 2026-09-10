# Supervisor budget retest — 10 September 2026

Source: `320249b3ed2387a32c265a3ddf8720c710e5ff7c`, unchanged during the run.
This is a two-case source-level behavioral retest, not native supervision,
a clean ten-case batch, a comparative benchmark or a causal performance study.

## Change and preserved safeguards

The earlier failed identifiers case used three model turns only for evidence
tools, then hit `limit_turns` without a structured decision. The main supervisor
prompt now explicitly includes its final `SupervisorDecision` in that three-call
budget, requests batched necessary reads and discourages repeating the supplied
goal. It asks for NOOP if evidence remains insufficient, never invented evidence.

This is prompt guidance, **not a runtime-enforced reservation**. The runtime
still caps turns at three and fails closed if no validated decision is returned.
71 supervisor tests pass, including a real Strands loop with a scripted model
that deliberately exhausts its turns. Independent review approved the safety
boundary. The earlier failed receipt is unchanged and remains a failure.

## Live results

Both the worker and supervisor used their pinned free routes: OpenCode
`ling-3.0-flash-fin-free` and saved-vault Zen `muse-spark-1.3-contributor-free`.
The [official Zen pricing page](https://opencode.ai/docs/zen/) was checked before
the run and listed these routes as free. No paid fallback or AWS deployment.
Only fixture data was sent; free-provider data-retention exceptions apply.

| Case | Completed semantic reviews | Model calls | Input / output tokens | Followups | Wall time |
| --- | ---: | ---: | ---: | ---: | ---: |
| Identifiers (previously failed) | 1 | 2 | 6,925 / 750 | 0 | 133.94 s |
| Error-log control | 2 | 4 | 13,834 / 1,888 | 0 | 187.33 s |

Each output was exact **before** PEX review, input files were preserved, and all
observed journal entries settled. Every decision was a completed Strands NOOP,
not a timeout/error relabeled as quiet. The control still had two reviews;
duplicate-review efficiency remains a limitation. A single retest cannot prove
that prompt guidance eliminates budget exhaustion across arbitrary work.

The fixture server exited normally through its retained process handle. Profiles,
public tasks, initial observations, worker messages and failed historical runs
remain available for audit. Do not edit or rerun the sealed output directory.

- Root: `build/opencode-quiet-budget-20260910-r1`
- Summary SHA-256: `d2af36ee8bef6969d3a7c22a6649c3d0f8d7c820ad659f00e8fb1ad49449ec61`
- Archived runner SHA-256: `f97ed01b314103e46a9f4ae1df1638637a2f7d40d4be0fa4eea873e20c51b886`
- Run exit: 0; requested cases: 2; passed cases: 2; source unchanged: true.

## Separate native idle observation

Native product `fcb624d` stayed on Home with the overlay hidden and no PEX input
for 18 ten-second samples (180.09 seconds). Its eleven owned processes used
335.3–338.3 MiB private memory and 4.911 CPU seconds, about 2.73% of one core.
The source OpenCode retest ran separately on the PC and was excluded from PEX's
process tree. PEX remained targetable and Inspector navigation worked afterward.
An accessibility click reported unavailable geometry; a fresh screenshot and
coordinate click succeeded. This was not a PEX hang.

Receipt: `build/pex-idle-fcb624d-20260910.json`, SHA-256
`306ad3d41374a267cd35753415e3a08eebe7764e1518a828f52cfcad9ea70385`.
Three minutes is not a long soak or causal clearance of the earlier PC freeze.
