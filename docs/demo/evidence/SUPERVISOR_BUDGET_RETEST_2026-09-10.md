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

## Packaged follow-through

Clean checkout `e56a07772d202323d07f463be1f46cb3685bf6db` includes product
`320249b`. Production build and package verification both exited 0. MSI and
NSIS extraction verified embedded binaries and all eight catalog pets. Both
installers are unsigned. Integrity verification is not a fresh-user install test.

Native PEX started successfully; selecting the saved OpenCode workflow showed
the actual worker message, Von and a dismiss control. The overlay stayed hidden.
This readback made no new supervisor inference and is not a fresh recovery run.

| Artifact | SHA-256 |
| --- | --- |
| `build/pex-package-receipt-e56a077.json` | `c4029ba6838c106ea16f9220b46dd3ca03ad145526e7852f047948639c6f6076` |
| Canonical desktop executable | `4f5780ac701f21c6e10facb8c4a95584e55064c589e14c6c3d40ed1fe1ecc21c` |
| Bundled bridge | `6c0ba075556a75945aa437f17f7c6234148a0c6e467a7345c508170d93d63e14` |
| `PEX_0.1.0_x64_en-US.msi` | `a63cea52d2193f8c1bedd2fe9fdd2fd25c202a0818f4e15ec1800b4f53957171` |
| `PEX_0.1.0_x64-setup.exe` | `338da5607f6d629a1f0a6c4e40979875b4294eb4ad0879cd727a181e438c2200` |

The public repository is MIT-licensed. Authenticated Devpost lists registration,
not submission. No current test-CI proof, release publication, AWS deployment,
fresh Windows-user installation or long-soak result is claimed.
