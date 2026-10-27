# Owner evidence view — WIP, not deployed

This delta extends the existing HTTPS owner workspace projection and cleaner web
owner page. It does not start a worker, provider, sandbox, runtime or recorder.
It is new source over the reconstructed owner-core candidate, not recovered latest
historical source. It does not modify the paired pilot or its frozen inputs.

Server composition may explicitly pass an absolute server-owned `event_path` to
`OwnerWorkspaceReader(database_path, event_path=...)`. The default is `None`.
There is no client path, environment auto-discovery or report.json reader. The
existing explicitly configured read-only workspace database remains required.
No production composition or real event file has been configured by this delta.
Parent directories must remain server-owned; final symlinks and nonregular files
are refused. This implementation targets the current Linux cloud runtime.

The bounded JSONL reader projects only known event/model IDs, canonical UTC time,
arm state and integer worker-call metadata. It does not return raw errors, paths,
prompts, reasoning, grades or hidden test details, even after both arms terminate.
A paired terminal flag requires both terminal arm records. Unknown/corrupt/partial
or oversized evidence yields unavailable metadata without blanking valid goals or
sessions. Reads are observational, not an atomic cross-file/database snapshot.

The UI uses the existing manual Refresh and owner auth/origin/session protection.
Logout, hidden page, expiry, failed refresh and stale-generation handling clear
metadata with the other private rows. No polling or new controls were added.

Controller-recorded metadata is not independently verified inference evidence.
Worker counts exclude supervisor overhead. Same-VM grading is anti-tamper-limited;
this view displays no grades, lift, success score or general superiority claim.

## Qualification

- Source checkpoint b86cc2c0: initial source and authored fixtures, WIP.
- Correctness checkpoint b9a1b296: canonical timestamp parser compatibility;
  69 backend unittest cases passed (authored JSONL and SQLite/ASGI records).
- Final frontend rerun: 487 tests passed (453 existing + 34 owner); TypeScript
  check and default/owner builds passed. The two new built-DOM regressions use
  authored fetch responses and pass; they are not real-browser/TLS checks.
- No new real-browser, authenticated TLS, real provider, paired score, deployed
  UI or payment qualification. Historical browser claims do not cover these bytes.
- Every checkpoint uses the existing review branch, expected-head nonforce,
  `[skip ci]`; no workflow dispatch. Source/test/document files only.
