# Packaged onboarding and bounded stability — 10 September 2026

Product `97e84d4`, clean package checkout
`06c6b734302c12231badee065e77156b4d7c424b`.

## First-run repair

Connecting a fresh OpenCode server does not create a worker session. The app and
README now explain starting `serve`, opening `attach` against the same address,
and creating/resuming the session in OpenCode before selecting it in PEX.
The [official CLI documentation](https://opencode.ai/docs/cli/#attach) was checked.
This is copy-only: no automatic worker, model call, credential or adapter change.

- Desktop suite: 276 passed, zero failed; exit 0.
- Production TypeScript/Vite build: exit 0.
- Independent read-only review: approved, no actionable findings.
- Tauri build and installer verification: exit 0, both inventories verified.
- Native startup and Home → Connect a worker: passed; the new three-step
  instructions render legibly in the packaged app. No connection was submitted.
- Both installers report `NotSigned`; no fresh Windows-user install was tested.

| Artifact | SHA-256 |
| --- | --- |
| `build/pex-package-receipt-06c6b73.json` | `6c3087c4c6704630875178343dcca22ec39cf153fa2d91b3143579e39d0c153d` |
| Canonical desktop | `26b10e96b175a3c3e5a175e3dcb1963c10177d77fcdc513d93d0a4f9be16cdd2` |
| Bundled bridge | `d8fafd42175d8c35e3ab50e503b10077563c4d4b9b97e73111b20b9abbcf3d47` |
| `PEX_0.1.0_x64_en-US.msi` | `35d23d0cc138a6d4cf741c4b0b181ee480fd1b429cd9abad616a6df97bb6eb09` |
| `PEX_0.1.0_x64-setup.exe` | `5c605996de9676c3ec65a82acc664517661640faa834ebc1eaf65d755ae7d9a4` |

## Pre-rebuild native observation

The previous `e56a077` package (same supervision logic, earlier setup copy)
completed 72 ten-second read-only samples, exit 0. No PEX input occurred during
sampling. Home showed the recorded OpenCode workflow, Von and its status bubble;
the overlay stayed hidden. Other PC activity was not controlled.

The initial seven samples were truncated in tool output. The retained 65 samples
cover 650.30 seconds: 336.8–340.4 MiB private memory, 105.999 CPU seconds across
PEX's owned process tree, equivalent to 16.30% of one core, not whole-PC CPU.
These figures must not be represented as metrics for all 72 samples. This is a
higher CPU observation than the earlier different-scene sample, not evidence of
a causal regression or improvement.

Afterward, Inspector navigation worked; its initial pending state resolved to
canonical data, including 1 of 3 review dispatches remaining. PEX then closed
normally through its own window before rebuilding. No unrelated process was
terminated. Twelve minutes is not a long-duration stability guarantee or causal
clearance of the previous whole-PC freeze.

Receipt `build/pex-soak-e56a077-20260910.json`, SHA-256
`5800b319d1fa494cddda8de90de3dc7aff109954aa155e5737f7f9b5627e34ec`.

## Remaining boundaries

Real recovery/quiet evidence remains source-bound to the existing receipts;
this copy-only update did not rerun model benchmarks. AgentCore is offline-tested
and undeployed. No formal comparative score, public installer release, fresh-user
installation, video or submitted entry is claimed. The full goal remains active.
