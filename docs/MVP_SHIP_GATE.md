# PEX focused MVP shipping gate

This is the shipping scope from the user's later request: usable UI/UX, exactly
two pets (Pex and Von), Zen BYOK, OpenCode/Codex, Strands supervision, AgentCore
implementation and honest behavioral measurement. Cursor is optional. Preserve
the full specs and historical research checklist; do not pretend every expanded
feature or formal benchmark has been completed.

## Actual official requirements

Refreshed from Devpost MCP on 10 September 2026 at 07:27 UTC, event 30317.
[Official rules](https://agentsforhumans.devpost.com/rules) control.

> Deploying with Amazon Bedrock AgentCore is a smart architectural choice and will strengthen your Technical Implementation score, but it's not required.

Keep the tested AgentCore implementation and honestly disclose it as undeployed.
Do not treat optional cloud deployment as a prerequisite to submitting the local
Strands MVP, and do not incur uncovered AWS charges for it.

Submission closes 15 September 2026 at 00:00 UTC / 01:00 Africa/Lagos
(14 September, 17:00 PDT). The official requirements include a working Strands
project, public source/setup/assets with MIT or Apache license, README,
architecture diagram, maximum-five-minute working demo video and AWS Builder ID.
The live-demo URL is optional. This refresh does not record consent or submit
anything on the user's behalf.

## Evidence and remaining work

- [x] Repair observed OpenCode free-tier retry/idle follow-up loop in source;
  durable provider block survives refresh/restart and requires tool/file activity
  to clear. Processing/OpenCode: 123 passed; final persistence focus: 7 passed.
- [x] Explain provider limit and distinct connection failures in UI; frontend
  build passed, 288 tests passed with one platform skip.
- [x] Recheck offline AgentCore contracts: 183 passed, no AWS calls/deployment.
- [x] Rebuild and verify provider-limit repairs natively on `5a4c4ac`:
  first-attempt attach, Blocked state, zero new reviews/nudges after idle.
  [Native evidence](demo/evidence/NATIVE_QUOTA_FENCE_5A4C4AC_2026-09-10.md).
- [x] Clean-source Codex/Strands quiet + recovery pair at `e864389`: 1 passed in
  79.19s and 1 passed in 193.45s, validated receipts and same-thread recovery.
  [Evidence and limits](demo/evidence/CODEX_LIVE_E864389_2026-09-10.md).
- [x] Recheck packaged OpenCode quota behavior; the free Ling run remains
  quota-limited, not a passing artifact/recovery benchmark.
- [ ] Complete final stability, ordinary cancellation and recording checks.
- [x] Source repair for explicit OpenCode cancellation: persistent no-follow-up
  fence, quota precedence and truthful UI copy; 77 focused backend tests and
  290 frontend tests passed (one platform skip). Idle-only abort without an
  explicit cancellation event remains unproven; native verification pending.

### Latest candidate — supersedes older package descriptions below

Product `5a4c4ac` rebuilt successfully; MSI/NSIS verification passed on one
bounded retry after a retained cleanup EPERM. Native startup required no Retry,
both pet previews loaded, and the isolated OpenCode connection succeeded first
attempt. The quota fence survived cancellation/idle with no extra model review
or intervention. Exact receipts and limits are linked above. This is not a
fresh-user install or blanket stability claim.

### 10 September evening: current package and live recheck

Product `dbc141a` was rebuilt with the full Tauri build (exit 0). The verifier
cleanup-receipt fix is `d1da140`; its MSI/NSIS verification passed with zero
blockers and 2,375 matching runtime files. Receipt:
`build/package-d1da140-20260910.json`, SHA-256
`6394c80025cbdf7ebc05742c3e7e2b995b8f9e0aeb033c2c3009885f8d0ee97d`.
The prior verifier attempt failed on temporary-directory cleanup (EPERM), and
must not be reported as a pass. These are integrity checks, not a fresh-user
installation or complete MVP acceptance.

The rebuilt native Ask correctly answered for the selected synthetic OpenCode
session instead of an older worker. Both shipping pets remain Pex and Von.
The native OpenCode attach first failed confirmation; a bounded retry succeeded.
Independent local probe returned Strong in roughly one second. The first
failure's cause is not yet proven.

The isolated Ling free worker then returned `Free usage exceeded` without
creating the required `status.txt`. PEX received 40 events and recorded one
Strands/Zen model review. This is not a successful benchmark or recovery proof.
After aborting the owned session, another worker prompt appeared; the exact
owned server was stopped and its runner exited 0 to prevent further retries.
Audit provider-limit visibility and supervision after cancellation before
repeating this check. Do not substitute a paid model or reset the review budget.

Historical checkpoint below is retained; it does not supersede this update.

Latest installer pair remains `4de1db8`, with exactly Pex and Von. Its integrity
passed but native startup and Retry exceeded the unchanged 60-second deadline.
The replacement unpacked runtime in source `be67a91` now starts the release
desktop without Retry, with `ready` at 5.109 seconds after Python entry. Both
pets are transparent, dismissible and independently hideable. This is one
native check, not a fresh-Windows-user installation or prolonged stability proof.
Native BYOK save/catalog, OpenCode connection and synthetic goal attachment also
passed. Ask PEX exposed selected-session leakage from an older OpenCode worker;
the fix is under regression review and not yet in the running package.
Rebuild and verify the new MSI/NSIS runtime trees before calling them current.
[Current package evidence](demo/evidence/TWO_PET_PACKAGE_2026-09-10.md).

- [x] Resume PEX-only checks after permission; recorded startup failure retained.
- [x] Diagnose startup extraction delay; native unpacked-runtime launch and both pets checked.
- [ ] Verify new MSI/NSIS startup and rerun corrected Ask/session flows.

- [x] Native OpenCode connection and persistent goal attachment.
- [x] Real native Strands correction to the same OpenCode worker, exact recovery
  artifacts, helped outcome, then NOOP; see native d55e899 evidence.
- [x] Real Codex App Server recovery and quiet source proofs; describe that
  supported surface honestly, not arbitrary desktop-thread control.
- [x] Saved Zen vault credential used in real free-route inference; never publish
  keys or raw private receipts. BYOK configuration is not a billing guarantee.
- [x] Native transparent Von, bubble dismissal and pet hiding demonstrated.
  September 10 scope override: ship only Pex (owl) and Von (cat), per Joseph's
  latest request. Retain historical eight-pet evidence as history, not current proof.
- [x] Failed inference is distinguished from a successful quiet review.
- [x] Newer unverified STOP supersedes obsolete goal success/failure as uncertain.
- [x] Remove the remaining raw event-kind progress fallback and verify natively.
- [x] Complete offline regression on current source `aba8d38`: 4,336 passed,
  16 skipped, 18 deselected, exit 0. Live-provider/desktop tests are excluded.
  [Exact evidence and retained failed attempts](demo/evidence/OFFLINE_REGRESSION_2026-09-10.md).
- [x] Both installers pass on clean checkout `e56a077` (product `320249b`),
  including the progress-label and supervisor-budget guidance repairs. Native
  startup and recorded OpenCode selection pass. Installers remain unsigned.
- [x] Fresh packaged bridge profile, native reopen and pause/resume checks.
  [Exact evidence and limits](demo/evidence/MVP_NATIVE_FCB624D_2026-09-10.md).
- [x] Thirty-minute packaged resource observation: 180/180 samples retained,
  followed by responsive restore/navigation/Inspector refresh. PEX was minimized
  at inspection; [precise limits](demo/evidence/RESOURCE_OBSERVATION_2026-09-10.md).
- [ ] Fresh Windows-user installation and long-running foreground/active-worker
  stability remain unverified; bounded checks do not causally clear the old PC freeze.
- [x] Behavioral report retains failed/invalid attempts. Nine semantic
  quiet cases across runs are not a clean ten-case pass or comparative score.
- [x] The previously failed identifiers case and one control pass a separate
  two-case source retest, with completed Strands decisions and no followups.
  This does not retroactively make the original batch pass.
- [x] Public repository and MIT license verified; Devpost registration confirmed.
  No submission or public installer release performed.
- [x] Review architecture image and update the public OpenCode UI setup path.
- [ ] Finalize current submission copy and judge-facing demo assets.
- [ ] Record the working path and complete authorized submission.

Formal frozen Cursor/Codex four-arm scoring and its OS-level hidden-evaluator
boundary remain unfulfilled research/spec work, not an official contest-entry
requirement. Do not publish a formal PexBench score or claim full-spec completion.
Docker startup currently fails on its own inaccessible sailor-ingest.sock; no
Docker data deletion, security-setting change or VM workaround is authorized by
this document. Follow the user's current scope and action permissions.

**MVP readiness remains pending the unchecked items above**, not optional AWS
deployment or completion of every historical expansion. Winning remains an aim,
not a verifiable engineering guarantee.
