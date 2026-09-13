# Public submission preflight — 9581dac

Read-only refresh on 13 September 2026. No release, form field, video, AWS
resource, provider call, or Devpost submission was created or changed.

## Repository

- Local `HEAD`: `9581dac2b1473a9c346fac65a4d768a317e1698f`.
- `origin/main`: `9581dac2b1473a9c346fac65a4d768a317e1698f`.
- Worktree: clean.
- GitHub repository: `josepha-mayo/pex`, public, default branch `main`.
- GitHub license endpoint: `MIT`, path `LICENSE`.

## Required local material

The following files exist:

- `LICENSE`
- `README.md`
- `docs/JUDGE_TESTING.md`
- `docs/SUBMISSION.md`
- `docs/architecture/pex-architecture.png`
- `docs/demo/assets/pex-mark.png`
- `docs/demo/RELEASE_NOTES_0.1.0_RC2.md`
- both retained `1cd42c8` Windows installers

The new project mark is a true-alpha 1024×1024 PNG with SHA-256
`61ff11794df490525b95a3e7b83c6c635e641f01c50f1a0cb8187f1276709795`.

## Public release boundary

Public prerelease `v0.1.0-rc1` remains available, but it is the older build:

| Asset | Bytes | GitHub digest |
| --- | ---: | --- |
| `PEX_0.1.0_x64-setup.exe` | 101680803 | `sha256:6fb27ff7d4ec986e5b64209b1f00b70cab6593b67daafa42e08add5bd90c6d92` |
| `PEX_0.1.0_x64_en-US.msi` | 114483224 | `sha256:5c60b8fb322e8f8a187cbb103b58ff852ca09bbc79c7104483836f8e550747d5` |

The verified current local candidate is still unpublished. Its NSIS SHA-256 is
`81c85b528e0e7aeae57a6c4bc554b08c54302df87f776f034bbec7aa9f36d849`;
do not attach the RC1 URL to that hash.

## Tracked-secret scan

A narrow high-entropy credential-pattern scan found zero matches in product
code and active documentation after excluding evidence archives and tests. A
full tracked-file scan found 20 matches, all confined to explicit security/test
fixtures in nine files under `tests/`. No matched value was printed. This scan
is a useful preflight, not a substitute for repository-host secret scanning.

## Remaining gates

1. Record and publicly upload the maximum-five-minute working demo.
2. Publish the exact `1cd42c8` MSI/NSIS as a new immutable release and verify a
   fresh public download against the retained hashes.
3. Replace the older Devpost thumbnail, attach the architecture PNG, complete
   the required private form values, review, and submit only with current
   action-time authorization.
