# Focused MVP package and native check — 10 September 2026

Product source `fcb624d064448947d09e2813bc493b4f2b03b1e3`;
clean package-verification checkout `d50e420448636e73ff44ffb753c3db43952e35eb`
adds documentation only. This is a bounded acceptance check, not a new live
worker benchmark or proof that the earlier whole-PC freeze is causally solved.

## Package

Tauri production build passed. The first verification attempt stopped with
`dirty_worktree` because README/STATUS edits were uncommitted. After committing
those documentation changes, verification passed without rebuilding or changing
product inputs. Both installers' embedded binaries and eight-pet inventory match.

- Receipt: `build/pex-package-receipt-d50e420.json`
- Receipt SHA-256: `00d32b52f17709f4b57a5f0c9b812447e42610bb6127d4f1f722aca6c12cf007`
- Canonical desktop: `43c884d56f46c1c40204b821b8e804cdfdfdc71f3466e79912b71aa772b95eb9`
- Bridge: `54b6c0f41c2f16e681c90d8e96984704e209bd35e80e553f7935314844b26162`
- MSI: `193d1896251755c51bb0333998efaff3ebf546591f886f902f175c47b52605c2`
- NSIS: `82f1b9d63ea7624b7905731999ac6a4cf730a34a2b0983b3c06a2aa6cace8d9c`

`release_ready: true` here means package integrity, not submission completion.

## Native observation

PEX was closed through its own window and the rebuilt canonical executable
opened successfully. No other agent was controlled or terminated.

- Home and Inspector show the real OpenCode response beginning “Both files
  verified”, rather than `message.part.updated` or a bare role label.
- The recorded worker remains Stopped. Newer unverified completion is uncertain,
  not an obsolete acceptance-gap verdict or invented success.
- Pause supervision changed to Resume supervision; resuming restored the button.
  A read-only SQLite check confirms `supervision_paused: false`, status stopped.
- Review allowance stayed 1 of 3 with 2 reserved; no new worker turn was started.
- A second normal close/reopen succeeded, preserving the saved Von selection,
  hidden-overlay preference and recorded OpenCode session. PEX remains open.
- Pet remained hidden during this check; earlier transparent/dismiss/hide native
  evidence remains source-bound and is not relabeled as a fresh pet-animation run.

Twelve read-only process samples covered about two minutes, overlapping the
Inspector/pause/resume checks. No hang was observed. The retained final six
samples cover 60.07 seconds: 343.7–362.4 MiB total private memory across eleven
PEX-owned processes and 10.66 CPU seconds (17.75% of one core, not the whole PC).
This is not an idle-only workload, long soak or comparative performance result.
Tail receipt: `build/pex-resource-fcb624d-tail-20260910.json`, SHA-256
`f8d772604c7210c5280539dca88120a272f5d0d551a4bb26bdc5f018b4cd1fbe`.

## Fresh packaged bridge profile

The exact bridge was launched with a new, separate profile, authenticated
loopback, observe mode and model calls disabled. Readiness took 11.8 seconds.
Unauthenticated protected access was rejected; 18 authenticated pet, goal and
supervisor reads returned valid JSON. Only the retained owned subprocess handle
was stopped. The fixture data/logs are retained; no user profile was replaced.

Receipt: `build/fresh-bridge-fcb624d-20260910/receipt.json`, SHA-256
`4af96a66189ba1026e5659c97fa9987c3fffcf959332a458a475651d1f1e9ea6`.
This is **not** a fresh Windows-user native installation or BYOK inference test.

## Regression evidence

- Full offline suite before this small follow-up, product/test source `1a5eb92`:
  4,313 passed, 16 skipped, 16 deselected; exit 0.
- Follow-up snapshot/OpenCode lineage/delta suite: 84 passed; exit 0.
- Wider OpenCode unit selection: 117 passed, 3,805 deselected; exit 0.
- Ruff and independent review pass. The adapter explicitly distinguishes
  synthetic fallback text from genuine text equal to an event kind. Legacy
  immutable journal entries without that marker retain a display heuristic.

No new AWS deployment, paid call, comparative benchmark score, or submission is
claimed. See the focused MVP gate for remaining recording/submission work.
