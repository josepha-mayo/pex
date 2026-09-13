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

Installed product source: **`fc20329794a6a453868ca01ea903b4c41f471475`**.
Local NSIS: `build/release-candidate-fc20329/PEX_0.1.0_x64-setup.exe`.
Bytes: `101712659`; SHA-256:
`aee5a212997dc4a493cec5a812344af04aed539ef219ee5ddbc78ea33781629c`.
[Package and startup proof](demo/evidence/PACKAGE_FC20329_2026-09-13.md).
The complete current-product non-live gate is green. Public RC1 contains older
`49385f2`; do not film it as this build.

## Sequenced acceptance checklist

- [x] **1. Build and verify the actual installer.**
  Spec: Recovery §27 engineering discipline.
  Acceptance: rebuilt runtime/desktop, verified MSI/NSIS inventories, installed
  hash match, startup/normal close and no surviving PEX process.
  Current evidence: fc20329 full rebuild, three frozen tests, zero-blocker
  package verification, installed hash match and authenticated native startup.
  Native-close control was unavailable after reboot; forced cleanup left zero
  PEX processes.

- [x] **2. Exercise focused native UI, chat and companion controls.**
  Spec: Core §8; Recovery §20–21.
  Acceptance: Home/Inspector/Settings, exactly two pets, transparent Von,
  independent message dismissal and stationary Hide; selected-worker Ask PEX.
  Current evidence: immediately preceding installed candidate Home/Settings, exactly two companions,
  transparent Von, independent message dismissal, separate overlay Hide,
  Escape-to-hide/reset, bridge liveness and ordinary cleanup. `fc20329` changes
  only reviewed brand/icon assets and their test, but still requires a short
  exact-build visual click-through before recording. These remain bounded checks,
  not every scale/monitor configuration.

- [x] **3. Use saved Zen BYOK in real Strands supervision.**
  Spec: Core §4.1; Recovery §6.
  Acceptance: vault credential, selected provider/model, genuine inference,
  usage displayed, no fallback or key disclosure.
  Current evidence: fresh 1caa822 OpenCode and 8e99e9f Codex pairs used saved
  Muse Contributor Free through Strands with cap three. A dispatch may make
  multiple API calls; cap three is not a token cap.

- [x] **4. Verify OpenCode lifecycle and same-session artifact recovery.**
  Spec: Core §3; Recovery §2, §10–11.
  Acceptance: Working during activity; independently approved correction;
  same worker repairs output; final quiet review is genuine.
  Evidence: [fresh release-source pair](demo/evidence/LIVE_OPENCODE_PAIR_1CAA822_2026-09-13.md):
  exact initial incomplete state, one same-session correction, exact final
  artifacts, helped outcome, 118 settled events, then quiet.

- [x] **5. Preserve distinct Codex recovery and quiet evidence.**
  Spec: Recovery §12–13.
  Acceptance: supported real App Server, same-thread continuation, persistent
  goal/evidence, real Strands, quiet control with zero follow-ups.
  Latest evidence: [fresh release-source pair](demo/evidence/LIVE_CODEX_PAIR_8E99E9F_2026-09-13.md),
  two passed in 145.36s: one helpful same-thread correction followed by NOOP,
  and one supported NOOP with no follow-up.
  This proves that source and owned App Server surface, not arbitrary existing
  Codex desktop-thread control or a bf5a25b native Codex run.

- [x] **6. Preserve a separate already-correct OpenCode control.**
  Spec: Recovery §8, §13–14.
  Acceptance: correct output before review, completed Strands NOOP, no follow-up;
  preserve failed attempts separately.
  Evidence: the current OpenCode quiet control had exact output before review,
  one real semantic NOOP, zero follow-ups and 102 settled events. It is one
  control, not a statistical false-positive estimate or comparative benchmark.

- [x] **7. Verify AgentCore implementation without inventing deployment.**
  Spec: build AgentCore path and user requirement.
  Acceptance: local client/runtime/pipeline/preflight contracts.
  Evidence: 243 focused tests passed in 25.61s. Current read-only preflight is
  undeployable/uninvokable; AWS is unauthenticated and no deployment occurred.

- [x] **8. Finish current-source broad regression.**
  Spec: Recovery §25, §27.
  Acceptance: full offline Python and desktop suites pass; repair/rerun actual
  failures and preserve exact source, failed attempts and exclusions.
  Current result: 4,532 passed, 16 skipped, 18 explicit live-marker
  deselections, zero failures/errors in 3,020.82 seconds. Desktop after the
  branding delta: 303 passed, one Windows symlink-capability skip. See the
  current offline and package receipts.

- [x] **9. Measure bounded installed resource behavior.**
  Spec: usable desktop MVP; user-reported whole-PC freeze.
  Acceptance: PEX-owned measurement during live work, responsive post-run
  navigation and normal cleanup.
  Current installed `fc20329` sample over 20 seconds: 1.219 aggregate
  CPU-seconds, 175.0 MiB working set and 128.3 MiB private for desktop + bridge;
  both processes remained responsive. The unavailable native close control
  required forced cleanup, which left zero survivors. Short samples do not prove
  leak freedom or erase the historical freeze report.

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
  Existing draft: `https://devpost.com/software/pex-mbcpr4`, not submitted.
  Current read-only repository/material check:
  [public preflight](demo/evidence/PUBLIC_PREFLIGHT_9581DAC_2026-09-13.md).
  A clean transparent project mark is ready at `demo/assets/pex-mark.png`.
  Do not replace RC1's immutable bytes or claim publication from local files.

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

## Official submission boundary

Live organizer refresh 13 September at 01:47 UTC: deadline 15 September 00:00 UTC /
01:00 Africa/Lagos. Live demo URL and AWS AgentCore deployment are optional;
working Strands project, public source/license/setup, architecture, ≤5-minute
video and Builder ID are required. Recheck
[official rules](https://agentsforhumans.devpost.com/rules) before submission.
Do not infer authorization to spend or submit from this document.
