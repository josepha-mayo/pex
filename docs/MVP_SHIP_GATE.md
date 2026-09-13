# PEX current MVP shipping gate

Updated 13 September 2026. Superseded checkpoints are preserved in
[MVP_SHIP_GATE_HISTORY.md](MVP_SHIP_GATE_HISTORY.md), not active instructions.

## Authority and scope

Read [core](PEX_CORE_SPEC.md), [build](PEX_BUILD_SPEC.md),
[recovery](PEX_IMPLEMENTATION_RECOVERY_SPEC.md) and [handoff](AGENT_HANDOFF.md).
The user's later shipping scope is UI/UX, exactly Pex and Von, Zen BYOK,
OpenCode/Codex, real Strands supervision, AgentCore implementation and honest
behavioral measurement. Cursor is optional for this MVP. Full-spec research
obligations remain open, not redefined away.

Work autonomously on authorized local changes, audit after each change, retain
failed evidence and push verified updates. Native control stays confined to
PEX/installer when authorized. No paid fallback, uncovered AWS spend, unrelated
app termination, fabricated benchmark score or false completion claim.

## Current candidate

Published product source: **`f2832a8651442eb3ee47a508a9c81cc16a82ec5d`**.
Local NSIS: `build/release-candidate-f2832a8/PEX_0.1.0_x64-setup.exe`.
Bytes: `101722399`; SHA-256:
`63d9f4ae90ac9b3f83f5334b3d3c9abf8ef3db7d8be82e87ff1876f3b007b18a`.
The package receipt and installed smoke are retained beside that candidate.
The exact package is public as
[PEX 0.1.0 RC4](https://github.com/josepha-mayo/pex/releases/tag/v0.1.0-rc4).

## Sequenced acceptance checklist

- [x] **1. Build and verify the actual installer.**
  Spec: Recovery §27 engineering discipline.
  Acceptance: rebuilt runtime/desktop, verified MSI/NSIS inventories, installed
  hash match, startup/normal close and no surviving PEX process.
  Current evidence: f2832a8 full rebuild, three frozen tests, zero-blocker
  package verification, exact installed executable hashes, authenticated bridge
  identity/settings and clean shutdown. The packaged-settings smoke passed with
  no provider calls. Exact installed-window acceptance remains on the recording card.
  Final-day source preflight also passes with zero blockers; its release-input,
  sidecar-input and all sidecar executable hashes exactly equal the RC4 receipt.

- [x] **2. Exercise focused native UI, chat and companion controls.**
  Spec: Core §8; Recovery §20–21.
  Acceptance: Home/Inspector/Settings, exactly two pets, transparent Von,
  independent message dismissal and stationary Hide; selected-worker Ask PEX.
  Current evidence: immediately preceding installed candidate Home/Settings, exactly two companions,
  transparent Von, independent message dismissal, separate overlay Hide,
  Escape-to-hide/reset, bridge liveness and ordinary cleanup. RC4 changes the
  OpenCode permission lifecycle and benchmark harness rather than the renderer,
  but still requires a short exact-build visual click-through before recording.
  These remain bounded checks, not every scale/monitor configuration.

- [x] **3. Use saved Zen BYOK in real Strands supervision.**
  Spec: Core §4.1; Recovery §6.
  Acceptance: vault credential, selected provider/model, genuine inference,
  usage displayed, no fallback or key disclosure.
  Current evidence: exact-current f2832a8 OpenCode and a529316 Codex pairs used
  saved Muse Contributor Free through Strands with cap three. A dispatch may
  make multiple API calls; cap three is not a token cap.

- [x] **4. Verify OpenCode lifecycle and same-session artifact recovery.**
  Spec: Core §3; Recovery §2, §10–11.
  Acceptance: Working during activity; independently approved correction;
  same worker repairs output; final quiet review is genuine.
  Evidence: exact f2832a8 recovery retained under
  `build/recovery-f2832a8-mimo-20260913-r1`: exact initial incomplete state,
  one same-session correction, exact repaired artifact, helped outcome, 185
  settled events, then `NOOP`. The active handoff records hashes and boundaries.
  A fresh clean-source rerun at `890d701` independently passed in 83.98 seconds:
  one `CONTINUE_SESSION`, exact repaired artifact, causal outcome verified, all
  112 events settled, then `NOOP`; see
  `demo/evidence/LIVE_OPENCODE_RECOVERY_890D701_2026-09-13.md`.

- [x] **5. Preserve distinct Codex recovery and quiet evidence.**
  Spec: Recovery §12–13.
  Acceptance: supported real App Server, same-thread continuation, persistent
  goal/evidence, real Strands, quiet control with zero follow-ups.
  Latest evidence: [exact-current pair](demo/evidence/LIVE_CODEX_PAIR_A529316_2026-09-13.md),
  two passed in 161.12s: one helpful same-thread correction followed by NOOP,
  and one supported NOOP with no follow-up.
  This proves that source and owned App Server surface, not arbitrary existing
  Codex desktop-thread control or a bf5a25b native Codex run.

- [x] **6. Preserve a separate already-correct OpenCode control.**
  Spec: Recovery §8, §13–14.
  Acceptance: correct output before review, completed Strands NOOP, no follow-up;
  preserve failed attempts separately.
  Evidence: exact-current `build/quiet-ten-762b4e2-20260913-r1` ran ten
  independently specified already-correct dummy projects: ten exact artifacts,
  only `NOOP`, zero follow-ups. This is a false-positive behavior sample, not a
  comparative productivity benchmark.

- [x] **7. Verify AgentCore implementation without inventing deployment.**
  Spec: build AgentCore path and user requirement.
  Acceptance: local client/runtime/pipeline/preflight contracts.
  Evidence: 277 focused tests passed with four environment skips. The local
  AgentCore Runtime-compatible contract is implemented; no AWS deployment occurred.

- [x] **8. Finish current-source broad regression.**
  Spec: Recovery §25, §27.
  Acceptance: full offline Python and desktop suites pass; repair/rerun actual
  failures and preserve exact source, failed attempts and exclusions.
  Current result: the last broad source suite passed 4,532 tests with 16 skips
  and 18 explicit live-marker deselections. After the final product delta,
  affected OpenCode lifecycle/planner/policy suites passed 121 tests, the
  focused Strands/AgentCore gate passed 277 with four skips, and desktop passed
  303 with one Windows symlink-capability skip. Package preflight remained green.

- [x] **9. Measure bounded installed resource behavior.**
  Spec: usable desktop MVP; user-reported whole-PC freeze.
  Acceptance: PEX-owned measurement during live work, responsive post-run
  navigation and normal cleanup.
  Current RC4 bridge-only soak ran 300.016 seconds with 274 authenticated
  identity checks, 28 authenticated settings checks, zero provider calls and
  clean shutdown. It used 2.578 CPU-seconds, peaked at 100.2 MiB working set /
  80.8 MiB private, and ended 372 KiB / 596 KiB lower than its first sample.
  See `demo/evidence/INSTALLED_BRIDGE_SOAK_F2832A8_2026-09-13.json`. This does
  not replace a full desktop soak or erase the historical whole-PC-freeze report.

- [ ] **10. Record and inspect exact-build recovery/quiet demo.**
  Spec: Recovery §26; official working-demo requirement.
  Acceptance: publicly playable video ≤5 minutes, genuine recovery and separate
  quiet case, readable evidence/usage, no private unrelated content.
  Follow [second-laptop card](demo/SECOND_LAPTOP_ACCEPTANCE.md) and
  [voiceover](demo/VOICEOVER_SCRIPT.md); describe actual uncertainty. Fresh-user
  installation and longer soak remain limitations, not fabricated passes.

- [ ] **11. Publish matching artifacts and complete Devpost handoff.**
  Acceptance: current public download/hash, public MIT source/setup,
  architecture/thumbnail, video URL, correct Builder ID/individual details,
  reviewed draft and final submission receipt after authorized submit.
  Existing public project: `https://devpost.com/software/pex-mbcpr4`, not submitted.
  A logged-out check on 13 September rendered the complete current story,
  repository/RC4 links and the clean processed thumbnail; it exposed no video
  or architecture attachment and no hackathon-submission receipt. See
  `demo/evidence/PUBLIC_DEVPOST_PAGE_2026-09-13.md`.
  Current read-only repository/material check:
  [public preflight](demo/evidence/PUBLIC_PREFLIGHT_9581DAC_2026-09-13.md).
  The clean project mark is now the uploaded Devpost thumbnail. Matching RC4
  installers, architecture and verification assets are public on GitHub. The
  required Devpost architecture attachment, video and final submission remain pending.

## Full-objective work still open

Formal four-arm benchmark is unfrozen. Readiness refresh on 13 September at
01:40:19 UTC says `can_freeze:false`: isolated hidden-evaluator boundary,
immutable complete vendor logs, controlled same-session Cursor treatment and
network receipts, and one coherent 32-cell result set remain absent. Exit 0
means a report was produced, not that the benchmark passed.

The recovery specification's complete live behavior matrix, broad provider/
adapter coverage and full goal-completion proof are not established by these
bounded examples. Winning is an aim, never an engineering guarantee. Keep the
persistent goal active while requirements remain unproven.

Current verified recording transfer bundle:
`D:\PEX-recording-kit-f2832a8-v4.zip`, 102,247,762 bytes, SHA-256
`8c28864512bce2883de167bc769bc56ac6e2ac8e48575d4ace10ef2395a930b4`.
Its 23-entry inventory and checksum list were reopened and verified after
creation; all bundled active guides are RC4-aligned.

## Official submission boundary

Live organizer refresh 13 September at 19:28 UTC: deadline 15 September 00:00 UTC /
01:00 Africa/Lagos. Live demo URL and AWS AgentCore deployment are optional;
working Strands project, public source/license/setup, architecture, ≤5-minute
video and Builder ID are required. Recheck
[official rules](https://agentsforhumans.devpost.com/rules) before submission.
Do not infer authorization to spend or submit from this document.
