# PEX continuation checkpoint — 6 September 2026

The user's internal shipping target is now **9 September 2026, Africa/Lagos**.
The full three-spec objective remains active. Submission remains **NO-GO**.
This checkpoint supersedes older `current` / `final` claims in the rolling handoff,
STATUS, shipping checklist and submission draft.

## Source and package boundaries

- `43690b8e728f8c69d3b4cdad7939f724ee7adb3f` was pushed and verified against remote
  main. It pins all five frozen public benchmark prompts to LF through `.gitattributes`.
  A new Windows checkout confirmed `i/lf w/lf attr/text eol=lf` for all five prompts.
  The exact-byte regression and original failing test passed; full PexBench passed
  **129 tests** under strict resource/unraisable-warning settings in the main checkout.
- `44fa68b` changes supervisor configuration wording. Constructing a Strands client
  does not prove connection or inference. Credentials may be in the OS vault or
  environment; the previous blanket `.env` claim was incorrect. Provider tests:
  **76 passed**; desktop view-model tests: **62 passed**.
- Current source also repairs Companion settings overflow and checkbox sizing after
  reproducing both in the native app at its normal 920-by-730 window size. The roster
  wraps within its grid area; narrow windows use one settings column. The production
  frontend build and **184 desktop tests** pass. The test run emitted an HMR-port
  warning (`24678` in use), despite all assertions passing. Rendered verification of
  the changed layout is still required.
- The latest retained package receipt is for **`4f8b567`**, not current source.
  Local receipt: `C:\Users\JosephMayo\Projects\pex-release-final-8b\build\pex-package-receipt.json`.
  It reports `release_ready: true`, `blockers: []` for package integrity only.
  MSI SHA-256: `5a725c81bc9a89cf4b1f3285477d80a765a3adeedfdee49d173cbc92c5b49994`.
  NSIS SHA-256: `f133ad58e495bd0ef27195da7b40155f7d11090d6ebbc3caa79aaea460b70c8c`.
  A new final package must incorporate subsequent source changes.

## Full-suite diagnosis

The earlier clean `4f8b567` run failed 16 PexBench tests because Git materialized the
public prompts as CRLF, while text-mode workspace reads normalized LF. This was a
checkout portability defect, not test-order contamination. Keep exact byte/hash checks;
do not normalize only one reader and create mutually inconsistent fingerprints.

The fresh `43690b8` checkout is
`C:\Users\JosephMayo\Projects\pex-release-final-9c`. Its full strict suite was
interrupted after **225 passed, 16 skipped**, while the 65-handoff capacity case appeared
stalled. Independent evidence subsequently showed continued durable handoff progress
and an isolated **PASS in 266.58 seconds**. Therefore a deadlock is not established.
The expensive path is being profiled before changing fixtures or production code.
A diagnostic run with `faulthandler_timeout=45` emitted a Windows access violation;
do not report that diagnostic as a passing run or silently attribute it to PEX code.
There is still **no completed green full-suite receipt for the latest source**.

## Native interaction evidence

Computer Use became available with the refreshed plugin on this continuation.
The exact extracted `4f8b567` desktop was launched from
`build\native-smoke-4f8-01\pex-desktop.exe`, using the retained isolated
`build\native-profile-4f8-01` via `PEX_HOME`. It reached **All quiet**.

Observed through the native accessibility tree and screenshots:

- The separate pet window showed Pex and its status bubble.
- Clicking **Dismiss PEX status message** removed the bubble and retained the pet and
  accessible status label.
- **Alt+F4** removed the pet window while the main PEX window remained open.
- Companion settings exposed all eight named built-ins, but the old package layout
  overflowed horizontally and rendered oversized visibility checkboxes.
- Supervisor settings eventually loaded. Their old `Semantic model is loaded` and
  `.env` wording triggered the truthfulness repair above.

The user pressed physical Escape during the next UI refresh. Computer Use stopped
immediately. **Settings restoration, restart persistence, final all-eight animation
replay and rendered validation of the new layout remain incomplete.** Resume app input
only when the user directs it. Do not bypass the stop through another UI tool.
The current app/process/window IDs are ephemeral; rediscover them before reuse.

## Remaining execution order

1. Finish profiling the 65-handoff cost; fix any demonstrated production bottleneck,
   independently review it, then complete the necessary full-suite gate.
2. Visually validate the settings repair and complete native close/restore/restart and
   all-eight-pet checks when app interaction resumes.
3. Recapture the real Codex + Strands restraint/recovery pair on the final runtime,
   including independent verifier evidence where required and ten quiet tasks.
   The retained live pair proves only source `5c49c10`; see the curated live receipt.
4. Complete required cross-harness behavior, honest isolated comparisons, AgentCore
   deployment under the user's no-card-charge condition, and the final audited package.
5. Record the real public demo video and finish the truthful submission artifacts.
   PexBench remains unfrozen; no leaderboard rank or measured productivity lift exists.

Use bounded subagents and independent review. New subagents use GPT-5.6 Sol low.
Push reviewed scoped updates, verify remote equality, and preserve the complete product
goal rather than redefining readiness around tests or packaging.

Protected operator-owned file: `services/supervisor/src/pex_supervisor/loop.py`.
Do not edit, stage, restore, format or clean it. Its rechecked SHA-256 remains
`392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`.
No cloud deployment, paid call, public post or submission occurred in this continuation.
