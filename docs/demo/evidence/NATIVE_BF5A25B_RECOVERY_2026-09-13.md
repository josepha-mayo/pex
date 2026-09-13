# Installed OpenCode lifecycle and recovery — 13 September 2026

Installed source: `bf5a25bd319134fb472ac2049d9594e63e307a68`.
[Exact package identity](PACKAGE_BF5A25B_2026-09-13.md).
Native PEX owned the bridge and supervision; the fixture only started an owned
OpenCode server, submitted the phase-one prompt, and observed artifacts/status.
Goal creation, connection, selection, Inspector and Ask PEX were exercised via
the installed Windows UI. No separate source Pipeline supplied supervision.

Worker: `ling-3.0-flash-fin-free`. Supervisor: saved Zen BYOK
`muse-spark-1.3-contributor-free`, Strands 1.53.0, three-review cap, no paid
fallback. Both exact model IDs were rechecked against official Zen pricing.

Run: `build/native-bf5a25b-recovery-20260913/`.
Vendor session: `ses_f679ede4bfferZCS6yy60cKPGq` throughout.
Goal: `goal_a4136c03d8e84fbf9cec8ef5b6a4b4d3`.
Audit SHA-256: `915cc2c15f8e88a4e47e5eca9bd61617aee11bc70715f6a2e6c34bfaf9f91c4d`.

## Observed sequence

1. Fresh worker was Discovered. Starting the real turn changed native Home to
   Working before terminal review: the targeted lifecycle regression is fixed.
2. Worker stopped after stage one; final.txt was missing and stage-one.txt had
   CRLF rather than the required LF. First observed idle was about 23 seconds.
3. Real Strands review plus independent verifier approved a same-session
   SEND_NUDGE to complete final.txt. Worker created it, but both byte checks
   remained unsatisfied. PEX recorded `acceptance_still_unsatisfied`, helped false.
4. A second independently approved SEND_NUDGE specifically diagnosed CRLF and
   instructed exact LF-byte repair. Both files then matched the fixture's byte
   assertions (confirmed by the 123-second progress sample).
5. Worker/provider retries occurred between turns. Final review returned real
   Strands NOOP, without timeout/fallback. By the 173-second sample the worker
   was idle with both exact artifacts. Inspector showed Stopped / Stayed Quiet.

| Review | Action | Model calls | Input tokens | Output tokens | Review latency |
| --- | --- | ---: | ---: | ---: | ---: |
| Missing second file | SEND_NUDGE | 4 | 13471 | 1306 | 14541 ms |
| Incorrect line endings | SEND_NUDGE | 4 | 14350 | 2041 | 19025 ms |
| Exact artifacts present | NOOP | 1 | 3389 | 664 | 6303 ms |

Total: 9 model calls, 35,221 tokens, 39.869 seconds of reported review latency.
Three review dispatches are not three API calls. All 262 observed events were
settled: 233 record-only and 29 complete lifecycle/decision entries. Ordinary
working progress did not invoke the model on each frame.

## Verdict and limits

Lifecycle UI and bounded same-session artifact recovery passed. Both final
files have exact contents `stage-one-ok\n` and `pex-supervised-ok\n`. The final
deterministic acceptance evidence includes both exact matches, but the unchanged
third criterion, "Both files are verified before the whole goal is considered
complete," remains unchecked. Therefore `acceptance_status` is uncertain,
verification is `no_claims`, second correction outcome is
`worker_stopped_outcome_uncertain` with helped null, and overall goal completion
is NOT verified. Do not relabel this receipt as helped true or full completion.

Ask PEX answered that this selected OpenCode worker was stopped on the correct
persistent goal. A transient completion-unavailable message during context
refresh resolved to the explicit uncertain-completion explanation. It did not
cause a bridge startup failure or an incorrect completion claim.

## Resource observations and cleanup

PEX desktop/descendant processes only; separately owned OpenCode excluded:

- Active run: 10 samples over 46.258 seconds, 362.24–406.41 MiB private memory,
  96.74% of one core (~8.06% of this 12-logical-processor machine).
- After owned worker shutdown, Inspector/Ask PEX interactions: 10 samples over
  46.073 seconds, 380.23–407.70 MiB private memory, 22.11% of one core (~1.84%
  aggregate). This is a settled interactive sample, not a motionless idle test.

Raw measurements: `build/native-bf5a25b-live-resources.json` and
`build/native-bf5a25b-settled-resources.json`. These short samples cannot prove
absence of leaks or future whole-PC freezes. No causal optimization claim.

Owned OpenCode server exited; port 4097 no longer listened. Worker messages,
workspace, audit and isolated profiles were retained. The legacy cleanup flag
is not profile-deletion proof; `profile-retention.json` records preservation.
No unrelated Codex process or other application was terminated.

This is a controlled live behavioral test, not the formal four-arm benchmark.
AgentCore remains implemented/tested locally, not AWS-deployed. Public RC1 and
submission state are unchanged.

Post-run validation: all 183 AgentCore unit tests passed in 11.47 seconds.
The formal four-arm readiness refresh at 01:40:19 UTC returned
`manifest_frozen:false`, `can_freeze:false`; it still lacks the isolated
evaluation boundary, complete immutable vendor logs, controlled Cursor
same-session treatment/network receipts and one coherent 32-cell result set.
The readiness command's exit 0 means the report ran, not that the benchmark passed.
