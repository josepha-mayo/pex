# Broad regression and stale Cursor replay repair — 13 September 2026

## Full offline run (retained failure)

Started on clean `d4f6507`. Product/test/benchmark code stayed unchanged during
the run; local README/checklist/submission text was edited while it ran.
Live provider, worker, desktop and AgentCore markers were excluded and opt-ins
disabled. Installed Cargo was added to this shell's PATH only.

Result: **4,474 passed, one failed, 16 skipped, 18 deselected**, exit 1,
1054.98 seconds. XML: `build/offline-d4f6507.xml`, SHA-256
`8882eb79d2bc9e053b351955a7b4ffc79cf0cb4a0809d55bbabe3407291029b1`.
XML reports 4,491 cases, one failure, zero errors and 16 skips. Do not relabel
the original full run as green.

Sole failure: `test_readme_documents_reproducible_source_setup_and_all_sidecars`
required explicit wording distinguishing source development from an installer.
README now states that the development workflow is not a packaged installer.
All eight source-setup contracts then passed in 1.77 seconds. Desktop suite:
300 passed, one Windows symlink-permission skip, zero failures.

## Native-discovered Cursor discrepancy

Installed bf5a25b Home showed one working Cursor entry while process inventory
did not show Cursor.exe. Inventory alone was not proof of a defect. Read-only
inspection then found its last recorded events were from 5 September, while
the session's last_activity was refreshed on 13 September. No private worker
text was required and no session was deleted or rewritten during diagnosis.

A failing regression reproduced the cause: `_prepare_cursor_hook` upserted a
fresh Working session before the pipeline recognized a replayed observer event.
Thus replaying an old inbox record could manufacture current activity.

The source repair checks the recorded event identity after normalization. For a
replay it preserves the authoritative session and old heartbeat, while still
passing the incoming event through normal pipeline duplicate validation. It
does not discard the event or substitute a cached response. A newly arriving
hook must not be rolled back: object ownership protects the session projection,
and an explicit adapter revision protects the heartbeat. Timestamp equality
alone failed the concurrent regression because Windows clock ticks can coincide.

Regression covers both old Working and Stopped sessions, durable/in-memory
activity preservation, normal new-hook advancement, and a genuine hook arriving
during the duplicate lookup. The initial replay test failed before the repair;
the initial timestamp-based concurrency guard also failed and was replaced.
Final focused regression and Ruff pass. Broader exact-final validation:
**276 passed in 59.79 seconds**, zero failures/errors/skips. XML:
`build/cursor-replay-final-20260913.xml`, SHA-256
`fe5ef5806096833da861c89c1637685d68183a5d03e3129b95210714f27023e2`.
Selection: all Cursor unit files; Cursor hook/capture/delivery-ack contracts;
hook-credential E2E; event-processing pipeline and source-setup contracts.

This is a source repair, not yet included in installed bf5a25b. Rebuild and
verify the runtime/installer, then confirm native counts without reviving the
old Cursor row. The old full-suite receipt predates this code repair. No new
provider calls, AWS resources, benchmark score or final entry resulted here.
