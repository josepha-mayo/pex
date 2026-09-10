# Current-source offline regression — 10 September 2026

**Passed:** 4,336 passed, 16 skipped, 18 deselected; exit 0; 1001.79 seconds.
Source: `aba8d384b66430af653b921ce831b9f6e332f6ce`. Git was clean at completion;
no production or test files changed during this run.

Local XML: `build/offline-aba8d38.xml`.
SHA-256: `ce9270da57c0dd6ea0d4215f08d4d982e79ca27c1d9095368fed3db020f3970b`.
The parsed XML independently reports 4,352 tests, zero failures, zero errors and
16 skipped; deselected tests are not XML test cases. XML suite duration is
1001.199 seconds; pytest's terminal total is 1001.79 seconds.

## Reproduction

Use the repository's `.venv` and make the installed Rust toolchain available on
this command's PATH. On this machine, prepending the existing `.cargo/bin`
directory was necessary; this was not a Rust install or global PATH change.
Set `PEX_SUPERVISOR_DISABLE=1`, `PEX_LIVE_SUPERVISOR=0`, `PEX_LIVE_CODEX=0`,
`PEX_LIVE_OPENCODE=0`, `PEX_AGENTCORE_LIVE=0`, and `PYTHONUTF8=1`.

```powershell
.venv/Scripts/python.exe -m pytest -q -m 'not live_llm and not live_codex and not live_opencode and not live_agentcore and not live_desktop' --tb=short --junitxml=build/offline-aba8d38.xml
```

Choose a new XML filename for a new run; do not overwrite this retained result.
The selected suite exercises unit/integration/contract behavior with live gates
disabled. It is not a new provider, real-worker, native-desktop or cloud proof.

## Failed attempts retained

- `5ea699d`: 4,335 passed, one failed, 16 skipped, 18 deselected. Release preflight
  correctly returned `rust_toolchain_unavailable` because Rust was absent from
  the command PATH. Making the installed compiler available passed the unchanged
  failing test. XML SHA-256:
  `9b4daab2f2bdb747894c5aae2d4577a9ad4e57ccc6022d98672733a9c98a5878`.
- `10d4f51`, corrected PATH: same totals, a different sole failure. The workspace
  mutation fixture assumed an immediate file create advances directory mtime.
  It also failed standalone. The repair explicitly changes that timestamp while
  retaining the actual file creation and both incomplete/reason assertions.
  XML SHA-256:
  `349757d33801056dc22eef50cd50bbd4d5804e458b1d5eb9aef170e4f85079ee`.
- The repaired workspace test file passed 23 tests with one skip; the specific
  fixture passed five consecutive standalone runs. Ruff and an independent
  read-only review passed. Production inventory behavior was not changed;
  unchanged/coalesced directory metadata can still conceal a concurrent namespace
  change. See `KNOWN_FAILURES.md` for the non-atomic inventory limitation.

## Scope and remaining gates

The desktop suite separately passed 276 tests on `5ea699d`; later changes are
workflow/docs and the Python fixture only. Current package remains `06c6b73`
(product `97e84d4`): this result does not require or prove a new installer build.
Prior source-bound live OpenCode/Codex and Strands receipts remain distinct.
Fresh Windows-user installation, longer stability observation, final recording,
authorized release/submission and formal comparative benchmark remain unproven.
AgentCore deployment and any winning/leaderboard claim remain unclaimed.
