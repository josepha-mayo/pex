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

Installed product source: **`352d317fdda1ca6a8983e27ad896dd7afbcd6783`**.
Later documentation commits do not change these installer bytes.
Local NSIS: `build/release-candidate-352d317/PEX_0.1.0_x64-setup.exe`.
Bytes: `101669843`; SHA-256:
`9a6bdca0641564d6f066577d736277a22a86cfb461f85d5e3e352384b52c2149`.
[Package and live proof](demo/evidence/LIVE_ACCEPTANCE_352D317_2026-09-13.md).
Public RC1 contains older `49385f2`; do not film it as this build.

## Sequenced acceptance checklist

- [x] **1. Build and verify the actual installer.**
  Spec: Recovery §27 engineering discipline.
  Acceptance: rebuilt runtime/desktop, verified MSI/NSIS inventories, installed
  hash match, startup/normal close and no surviving PEX process.
  Evidence: bf5a25b package proof; three frozen lifetime tests passed.
  Follow-up complete on 352d317: Cursor replay-activity repair rebuilt,
  installed and natively checked; zero false working count on startup.

- [x] **2. Exercise focused native UI, chat and companion controls.**
  Spec: Core §8; Recovery §20–21.
  Acceptance: Home/Inspector/Settings, exactly two pets, transparent Von,
  independent message dismissal and stationary Hide; selected-worker Ask PEX.
  Evidence: bf5a25b package/native reports. Bounded checks do not cover every
  UI edge case or every scale on both pets.
  352d317 repeated the native controls, but exposed stale progress copy on the
  retained recovery session. That finding remains open; UI is not perfect.

- [x] **3. Use saved Zen BYOK in real Strands supervision.**
  Spec: Core §4.1; Recovery §6.
  Acceptance: vault credential, selected provider/model, genuine inference,
  usage displayed, no fallback or key disclosure.
  Evidence: installed bf5a25b Muse Contributor Free, cap three. A dispatch may
  make multiple API calls; cap three is not a token cap.

- [x] **4. Verify OpenCode lifecycle and same-session artifact recovery.**
  Spec: Core §3; Recovery §2, §10–11.
  Acceptance: Working during activity; independently approved correction;
  same worker repairs output; final quiet review is genuine.
  Evidence: [installed recovery](demo/evidence/NATIVE_BF5A25B_RECOVERY_2026-09-13.md):
  missing-file and CRLF corrections, exact bytes, Strands NOOP, 262 settled
  events. Overall completion remains uncertain for the unchecked third
  criterion; second correction helped is null, not true.

- [x] **5. Preserve distinct Codex recovery and quiet evidence.**
  Spec: Recovery §12–13.
  Acceptance: supported real App Server, same-thread continuation, persistent
  goal/evidence, real Strands, quiet control with zero follow-ups.
  Evidence: [clean-source 0ea2639 pair](demo/evidence/LIVE_CODEX_PAIR_0EA2639_2026-09-13.md).
  This proves that source and owned App Server surface, not arbitrary existing
  Codex desktop-thread control or a bf5a25b native Codex run.

- [x] **6. Preserve a separate already-correct OpenCode control.**
  Spec: Recovery §8, §13–14.
  Acceptance: correct output before review, completed Strands NOOP, no follow-up;
  preserve failed attempts separately.
  Evidence: [installed 0ea2639 quiet](demo/evidence/NATIVE_0EA2639_QUIET_2026-09-13.md).
  Additional 352d317 source-Pipeline batch: all ten consecutive already-correct
  public artifact tasks passed real semantic reviews, zero follow-ups, 33 model
  calls / 128320 supervisor tokens. Not a Codex batch, native desktop batch,
  representative coding score or comparative four-arm benchmark.

- [x] **7. Verify AgentCore implementation without inventing deployment.**
  Spec: build AgentCore path and user requirement.
  Acceptance: local client/runtime/pipeline/preflight contracts.
  Evidence: 183 tests passed on 13 September in 11.47s. AWS deployment remains
  unverified; no cost-incurring deployment is authorized by this checklist.

- [ ] **8. Finish current-source broad regression.**
  Spec: Recovery §25, §27.
  Acceptance: full offline Python and desktop suites pass; repair/rerun actual
  failures and preserve exact source, failed attempts and exclusions.
  Full result: 4,474 passed, one README contract failed, 16 skipped, 18 deselected;
  retained `build/offline-d4f6507.xml`. README fixed; eight setup contracts pass.
  Desktop: 300 passed, one skip. Subsequent Cursor source repair needs its own
  final regression/package acceptance. Do not relabel the failed full receipt.

- [x] **9. Measure bounded installed resource behavior.**
  Spec: usable desktop MVP; user-reported whole-PC freeze.
  Acceptance: PEX-owned measurement during live work, responsive post-run
  navigation and normal cleanup.
  Evidence: bf5a25b active 362–406 MiB private, settled interactive 380–408 MiB,
  approximately 1.84% total CPU on this 12-thread machine. Short samples do not
  prove leak freedom or clear the historical whole-PC-freeze report.

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
