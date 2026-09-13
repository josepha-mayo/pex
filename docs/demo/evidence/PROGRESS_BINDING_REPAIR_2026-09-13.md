# Progress projection repair — 13 September 2026

The installed 352d317 native check showed an old CRLF correction as latest
progress while the latest supervisor decision correctly described repaired
files. A read-only, session-scoped SQLite inspection identified the cause:
the actual final assistant response and byte-check tool results existed, but
their record-only event-processing rows had no accepted project binding.
The authoritative projection properly excluded those unbound rows.

Do not fix this by trusting arbitrary transcript history or weakening the
project/goal authority filter. The source repair adds opt-in observation
binding to Store.add_event, used only by the live OpenCode progress fast path.
Session, harness, goal and project checks occur in the existing write
transaction, before inserting the event. The trigger's record-only row then
receives that validated project binding in the same transaction. There is no
semantic-plan reservation, model call, session projection or worker action.

Default historical insertion stays unbound. Duplicate replay returns before
any binding update, so old unbound history is not retroactively promoted.
No user database rows or recorded worker messages were modified by this repair.
The old session can therefore retain its historical display limitation;
native acceptance must use fresh events on the rebuilt package.

Regression chronology:

- Added authoritative visibility assertions to the existing fast-path test:
  three failed, six passed before repair. Each failing case was stored but
  absent from recent_events_for_authority.
- Initial focused suites after repair: 77 passed, then 127 passed including
  fresh snapshot and non-promoting historical replay regressions.
- Final targeted suite: **319 passed in 82.95 seconds**. Includes all OpenCode
  unit files plus pet snapshot, event-processing Pipeline/Store, current
  projection and project-identity Store tests. Explicit wrong-goal and
  wrong-harness inserts reject without an event or processing row.
- Ruff and git diff checks passed.

Receipt: `build/progress-binding-final-20260913.xml`, SHA-256
`92a8b0e9121963b427ec06d4f50467a2d0863479f114d03e5db199691d972128`.

This report proves source regression behavior, not a rebuilt native pass.
The installed package and ten live quiet-control receipts remain tied to
352d317. Rebuild this repair and run fresh native progress/quiet acceptance
before promoting it into the public release. Full offline regression remains
open; the earlier failed broad-suite receipt has not been relabeled.

## Subsequent clean-source live and package results

Product source: `e989bdd1fe2925f57a8aa72992eb5676fb30f72e`.
Fresh single-case live quiet control passed on unchanged clean source in
145.77s: correct before review, two successful semantic NOOP reviews, zero
follow-ups, four supervisor calls, 14174 input + 1393 output tokens. All 290
events settled and the owned server exited. This is separate from the earlier
352d317 ten-case batch, not a new ten-case result.

Read-only inspection of this fresh journal confirmed all 270 record-only
events carry the accepted project binding (plus 20 pipeline events). The
newest visible bound text is the real assistant's final result: unique.txt
contains apple,pear plus LF and words.txt is unchanged. This confirms actual
live persistence; rendered native UI remains a separate pending check.

Live receipt: `build/quiet-e989bdd-20260913/summary.json`; SHA-256
`a221dce230b0ec98ed543f0794cb76998a8aa9a90512caf27790f446a026b938`.

Full runtime, frontend, native and installer build passed; three frozen
bridge lifetime tests passed in 12.33s. Package verification passed first
attempt with zero blockers. Silent installation exited 0 and installed hash
matched the extracted desktop executable:
`f49677e1950ded64ead0abe0378d7124143a2d65835b33e88ee585fc9ab9ba36`.

Retained in `build/release-candidate-e989bdd/`:

| Installer | Bytes | SHA-256 |
| --- | ---: | --- |
| PEX_0.1.0_x64-setup.exe | 101666799 | `6154c44068805d48534750271c4867b0169533369a5051190d982481cee3db35` |
| PEX_0.1.0_x64_en-US.msi | 114454552 | `7803a9c5c3aba0b3d73a55364bb9325a1d7a864b09aeda38307487ee9c4ab41d` |

Package receipt: `build/pex-package-receipt-e989bdd.json`; SHA-256
`00ff34d502e6f989597594f2df2eb1a6a6d68c539258808e24f5d6ae601fedbe`.

Full offline Python regression was launched after installation against this
source, writing `build/offline-e989bdd.xml`. Its result is pending, not passed.
No fresh native UI launch was performed after this installation yet. No public
release, video upload, AgentCore deployment or Devpost submission occurred.
