# PEX 0.1.0 RC2 — Windows judge build

Draft release notes, not a published release. Product bytes were built from
[`1cd42c8`](https://github.com/josepha-mayo/pex/commit/1cd42c8790d72035252cf7d1f94654ec4931fbe3).
Later commits add evidence and submission assets only.

PEX is a local goal-aware supervisor for existing coding agents. This focused
Windows MVP ships exactly two companions, Pex and Von, and supports OpenCode
HTTP plus Codex App Server. Supervisor inference uses the Strands Agents SDK;
the verified live path uses a user-supplied Zen credential stored in the OS
vault and the `muse-spark-1.3-contributor-free` model. PEX does not silently
select a paid fallback.

Download `PEX_0.1.0_x64-setup.exe` for the recommended Windows installer, or use
the MSI alternative. Both installers are unsigned, so Windows may show an
unknown-publisher warning.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| PEX_0.1.0_x64-setup.exe | 101689109 | `81c85b528e0e7aeae57a6c4bc554b08c54302df87f776f034bbec7aa9f36d849` |
| PEX_0.1.0_x64_en-US.msi | 114499608 | `7254c5aaf88150bd156f33cb24dc01dc380d6273252cda5c85a1194e87191663` |

Both embedded inventories passed verification with zero blockers. The installed
bridge hash matches the NSIS payload. Bounded native acceptance covered startup,
Home and Settings, exactly two pets, transparent Von, independent message
dismissal, separate overlay Hide/Escape behavior, bridge liveness and ordinary
cleanup. A 20-second visible-Home sample measured 128.5 MiB private and 178.1
MiB working set for desktop plus bridge; this is not a long-run leak claim.

The current-product non-live Python gate completed with 4,532 passed, 16 skipped
and 18 explicit live deselections. Desktop completed with 302 passed and one
Windows symlink-capability skip. Three frozen bridge lifetime tests passed.

Fresh release-source OpenCode and Codex checks each demonstrated one
evidence-specific correction delivered to the same worker session, an observed
helpful outcome, and a final model-backed `NOOP`. Separate already-correct
controls produced `NOOP` with zero PEX follow-ups. These are bounded behavioral
proofs, not a comparative productivity benchmark.

AgentCore's versioned `/ping` and `/invocations` runtime contract is implemented
and locally tested, but no AWS AgentCore deployment is claimed. PexBench remains
unfrozen and no score or leaderboard rank is claimed. Cursor remains optional
and observe-only in this focused MVP.

Follow the [judge guide](https://github.com/josepha-mayo/pex/blob/main/docs/JUDGE_TESTING.md)
and [recording setup](https://github.com/josepha-mayo/pex/blob/main/docs/demo/SECOND_LAPTOP_ACCEPTANCE.md).
Supply your own supervisor key; no credential is bundled.

RC1 remains available with its original, older artifacts.
