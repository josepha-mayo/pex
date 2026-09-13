# Public submission preflight — f188125

Read-only refresh on 13 September 2026. No release, Devpost field, video, AWS
resource, provider call or submission was created or changed.

## Repository and source

- Local `HEAD`: `f18812538c8f4ca58b055c0ffad2cd54eda40ecf`.
- `origin/main`: `f18812538c8f4ca58b055c0ffad2cd54eda40ecf`.
- Worktree at the check: clean.
- GitHub repository: `josepha-mayo/pex`, public, default branch `main`.
- GitHub license: MIT.
- Exact locally packaged product source: `fc20329794a6a453868ca01ea903b4c41f471475`.

## Transfer kit

`D:\PEX-recording-kit-fc20329` contains the exact MSI/NSIS plus matching
architecture, mark, acceptance, rehearsal, runbook, voiceover and RC2 notes.
All six copied Markdown files are byte-identical to the repository versions.

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `PEX_0.1.0_x64-setup.exe` | 101712659 | `aee5a212997dc4a493cec5a812344af04aed539ef219ee5ddbc78ea33781629c` |
| `PEX_0.1.0_x64_en-US.msi` | 114561048 | `da223af2e251d3cd030fdb3af6a3918fabb5889d6636967739ed864320b94519` |
| `pex-architecture.png` | 104099 | `6839bdcf9667b3de104e87a675df896a75654ff62adc6111bb619d26b41eae73` |
| `pex-mark.png` | 99348 | `61ff11794df490525b95a3e7b83c6c635e641f01c50f1a0cb8187f1276709795` |

## Public release boundary

Public prerelease `v0.1.0-rc1` remains available and immutable, but contains
older product source `49385f2`. Its public assets still report:

| Asset | Bytes | GitHub digest |
| --- | ---: | --- |
| `PEX_0.1.0_x64-setup.exe` | 101680803 | `sha256:6fb27ff7d4ec986e5b64209b1f00b70cab6593b67daafa42e08add5bd90c6d92` |
| `PEX_0.1.0_x64_en-US.msi` | 114483224 | `sha256:5c60b8fb322e8f8a187cbb103b58ff852ca09bbc79c7104483836f8e550747d5` |

Do not attach that RC1 URL to the `fc20329` hashes. Publish the current
candidate as a separate RC2 only after its recording-laptop visual card passes.

## Tracked-secret scan

A narrow high-entropy credential-pattern scan found zero matching files in
product code and active documentation after excluding test fixtures and
archived evidence. A full tracked-file scan found ten matching files, all under
`tests/`. No matched value was printed. This is a bounded local preflight, not a
replacement for repository-host secret scanning.

## Remaining gates

1. Run the short exact-build visual/close card on the recording laptop.
2. Record and independently inspect the public demo, maximum five minutes.
3. Publish the exact `fc20329` installers as RC2 and verify a fresh public
   download against the retained hashes.
4. Replace the old thumbnail, attach the architecture PNG, fill the remaining
   private Devpost values, review and submit with action-time authorization.
