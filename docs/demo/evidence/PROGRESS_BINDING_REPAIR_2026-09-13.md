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
