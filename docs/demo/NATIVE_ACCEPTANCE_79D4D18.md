# PEX-only native acceptance plan for package 79d4d18

This is the final bounded acceptance procedure for the current Windows release
candidate. It is a plan, not passing evidence. Do not check an item until it is
observed on the exact package, and do not use an older installed PEX build.

## Candidate identity

Use `build/release-candidate-79d4d18/PEX_0.1.0_x64-setup.exe` or the MSI in the
same folder. Before installation, verify `SHA256SUMS.txt`. Expected installer
hashes:

- NSIS: `e76389632460030d5f7aae5089ec9ced04b9c378c3b2256c3bf31fd9bc2dcd74`
- MSI: `44f3c035fe9c863e9c5b5a7cdb5fa614b29052e45b563efac8772e744cdeeb93`

The package is unsigned. A Windows unknown-publisher warning is expected and
must not be described as code-signing success.

## Safety boundary

- Wait for Joseph to explicitly release the screen.
- Confine mouse/keyboard control to PEX and its installer.
- Do not close, restart or control Codex, Cursor, OpenCode, Brave or another app.
- Close PEX through its own window. Never use the quarantined recursive-process
  cleanup script.
- Use only the dedicated public OpenCode demo server/session. Do not attach to a
  private or unrelated worker.
- Never display, paste into logs, or capture the Zen key. Use its saved OS-vault
  binding. Do not switch to a paid model or deploy AWS resources.

## Acceptance sequence

1. Confirm no PEX candidate process and no listener on port 7420.
2. Install the exact candidate and record whether install, first launch and
   bridge readiness complete without Retry, freeze or whole-machine slowdown.
3. Close PEX normally, reopen it, and confirm Home loads current state again.
4. Inspect Home, Inspector, Deck and Settings at normal window size. Reject
   clipped controls, horizontal overflow, overlapping text, stale opaque cards,
   or navigation that loses the selected worker.
5. Inspect Pex and Von separately. Require transparent overlay backgrounds,
   restrained movement, stable identity, drag without accidental activation,
   and no continuous high-cost animation while idle.
6. Dismiss only the status message and confirm the pet remains. Then hide the
   pet and restore it from Settings. Confirm Escape hides the pet, and that the
   status-dismiss and hide controls remain fixed, legible and independently
   keyboard reachable.
7. Open Supervisor inference. Require Zen plus
   `muse-spark-1.3-contributor-free`, saved-credential indication without secret
   disclosure, and the visible default cap of three semantic reviews per worker
   session. Do not claim a key is valid merely because it is saved.
8. Connect the dedicated loopback OpenCode server. Require one attach attempt,
   an actionable empty-server state when no session exists, accurate provider-
   limit/cancellation states, and selection of the intended vendor session.
9. Attach the prepared persistent goal. Ask PEX “What needs me?” and confirm the
   answer is bound to the selected session and stays inside its column. Switching
   sessions must discard any superseded answer.
10. Run the prepared controlled two-stage recovery only if the free worker and
    free supervisor routes are still confirmed. Require one specific correction
    on the identical vendor session, exact final artifact, helped outcome and
    final NOOP. Abort on paid fallback, repeated follow-up or identity drift.
11. Run the already-correct case. Require exact artifact, model-backed NOOP and
    zero PEX follow-ups.
12. Observe the complete owned PEX process tree for a bounded foreground-idle
    interval and during the worker journey. Reject unbounded CPU growth, memory
    growth, unresponsive controls, duplicate bridge payloads or surviving owned
    processes/listeners after normal close.

## Evidence to retain

- Candidate hashes and package receipt.
- One screenshot each of Home, Inspector, Settings, Pex overlay and Von overlay.
- A short screen capture of message dismissal plus pet hide/restore.
- Sanitized recovery and quiet receipts with exact session identity and no key.
- Start/reopen/close timings and bounded resource samples.
- Every failure, Retry state or rejected take; never film around a defect.

Only after all required observations pass should the accepted unsigned installer
be published, the five-minute-or-shorter demo be recorded, and the Devpost form
be completed under separate submission authorization.
