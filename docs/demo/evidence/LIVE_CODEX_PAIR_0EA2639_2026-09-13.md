# Fresh Codex recovery and quiet pair — 13 September 2026

Clean source `0ea2639fb9e8c20df413b18843d7056610af9b03`, fingerprint
`b87fe9cd0bf77a5a66c91040064b3cacdf366cc5b3e94060c265922d300954cb`.
Real worker: explicitly selected `gpt-5.3-codex-spark`, separately owned stdio
App Server, preflight-confirmed existing ChatGPT quota. Supervisor: saved Zen
BYOK `muse-spark-1.3-contributor-free`, local Strands 1.53.0, no paid fallback.

| Case | Outcome | Worker turns | Supervisor calls | Test duration |
| --- | --- | ---: | ---: | ---: |
| Incomplete stop | One independently verified same-thread SEND_NUDGE; empty report repaired to exactly shipped; helped true; final NOOP | 2 | 5 | 95.26 seconds |
| Correct completion | Model-backed NOOP, supported file acceptance, zero follow-up deliveries | 1 | 1 | 52.06 seconds |

Both receipts are `proof_status:validated`, with unchanged source, correlated
event/audit/delivery evidence. Recovery outcome is `goal_evidence_supported`.
The quiet fixture checks stripped `pong`, not exact newline bytes. Neither test
is a comparative productivity measurement or an installed-desktop test.

Retained receipts:

- `build/codex-0ea2639-20260913-recovery/codex_incomplete_proof.json`, SHA-256
  `1f78da6ca11d31617659462198ec613f014c65efecad703b0025fb0617305139`.
- `build/codex-0ea2639-20260913-quiet/codex_inspect_proof.json`, SHA-256
  `f4c0a6e33883d39557b2d394f2173823a70df3f431676be284de089d2348b1e9`.

Each directory retains JUnit and the workspace/database. Prior scratch receipts
were saved separately. Owned worker PIDs 17292 and 11628 were absent after
cleanup; no unrelated Codex task was closed.

The failed installed `32a0499` OpenCode quiet run remains failed in its own
report. These two passes do not overwrite or excuse that failure. Formal
four-arm readiness remains unfrozen, without a publishable comparative score.
