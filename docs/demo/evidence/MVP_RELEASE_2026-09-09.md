# PEX MVP release acceptance — 9 September 2026

This receipt binds the submission-focused MVP checks to clean commit
`933239a1bd0e05e65274d9c895750374239407b3`.

## Stability repair

The adapter registry endpoints previously ran a synchronous Windows `tasklist` process scan
inside every concurrent adapter probe. UI polling could therefore block the event loop, cancel
an otherwise healthy OpenCode HTTP probe, and amplify system load. The registry now captures
one desktop-process snapshot with `asyncio.to_thread` and shares it across the bounded probes.
A regression test proves one snapshot is reused for the whole registry.

Focused verification passed:

- adapter/process/event-pump tests: **58 passed, 1 live test deselected**;
- supervisor, OpenCode, Codex, and Cursor integration contracts: **361 passed, 3 live tests
  deselected**;
- desktop UI contracts: **260/260**;
- Tauri Rust tests: **18/18**;
- Strands and AgentCore contracts: **200/200**;
- production TypeScript/Vite build: passed.

The final clean repository-wide Python gate was then run with the pinned Rust/Cargo 1.97.1
toolchain available to release-preflight tests: **4,178 passed, 32 skipped, zero failures** in
1,949.92 seconds (32:29), exit code 0. An earlier environment-only attempt produced one failure
because `rustc` was absent from `PATH`; the exact failed release-preflight node passed after the
pinned toolchain was restored, and the complete clean rerun above is the accepted gate.

## Exact frozen bridge + OpenCode

Installed OpenCode 1.18.29 was started only on loopback port 4097. The exact frozen bridge later
embedded in both installers was started with a fresh isolated profile, no Codex/Cursor attach,
cloud reasoning disabled, and no model call. Across 20 authenticated `/v1/adapters` polls:

- `/health/live`: healthy;
- OpenCode support: `deep` on all 20 requests;
- minimum / median / maximum latency: **492.1 / 506.7 / 707.7 ms**;
- the live capability receipt included event-level message, tool, file, session, send, inject,
  resume, fork, and async permission support.

Both owned processes were stopped. Ports 4097 and 17423 and the temporary profile were verified
absent afterward. This is a no-model packaged-bridge integration proof, not a benchmark arm.

## Zen BYOK + Strands

The saved Zen choice resolved its credential from the Windows OS secret store without printing
or writing the secret. One bounded production supervisor invocation completed with:

- provider `zen`;
- model `muse-spark-1.3-contributor-free`;
- generation API `responses`;
- runtime `strands-agents` 1.53.0;
- `used_llm=true`, `inference_status=completed`, four model calls;
- final action `NOOP`, preserving the independent-verification fail-closed boundary.

No paid fallback, AWS resource, or AgentCore deployment was used.

## Package

`npm run tauri build` produced and `npm run verify:package` verified:

- MSI: `PEX_0.1.0_x64_en-US.msi`, SHA-256
  `49f7f8ceb2df3831bbd8dca71fde25024c6a6b57622b7283170bfe7e65994903`;
- NSIS: `PEX_0.1.0_x64-setup.exe`, SHA-256
  `1bfeaa456028f75cfc58692ff673c1dcf9fe8843bb61c01f97d72febb0e79ce7`;
- package receipt: `release_ready=true`, `blockers=[]`;
- both extracted inventories contain the desktop, frozen bridge, Cursor hook, and Cursor observer;
- embedded bridge SHA-256:
  `04b8b7d79eeb0158ffecf229bf2be43bd54c82bf47638c02fb9a171415aeb32c`.

## UI and pet boundary

A browser-only production-source review confirmed the compact Pex view, the settings/BYOK form,
the transparent owl asset, a separately dismissible status message, and a separate pet-hide
control. Pex and Von remain the two judge-facing characters; the full spec-required eight-pet
fleet remains packaged. Native Tauri interaction was not run because the earlier idle whole-PC
freeze requires the separately authorized bounded native smoke.

## Benchmark boundary

PexBench correctly remains `frozen:false`. Current readiness refuses a score because no single
coherent four-arm file satisfies OS-isolated hidden evaluation and Cursor still lacks a
controller-enforced network-policy receipt. Old partial rows are not a submission result. The
green benchmark contract suite must not be described as a productivity score or leaderboard
rank.
