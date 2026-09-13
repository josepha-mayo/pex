# Current-release OpenCode/Strands supervision pair — 13 September 2026

Source: clean `1caa8223cdfa1eb729775ec1ca55b43c4b56208d`, equal to
`origin/main` before and after both runs. Product code is the exact verified
package source at `1cd42c8`; `1caa822` adds package/native evidence only.

Both runs used a new isolated OpenCode server and workspace. The worker was
`ling-3.0-flash-fin-free`; the PEX supervisor was the saved Zen BYOK route
`muse-spark-1.3-contributor-free` through Strands Agents. Each runner refused a
provider, model, endpoint, secret-store, or dirty-source mismatch. No paid
fallback, AWS resource, existing user session, native UI action, or comparative
benchmark was involved.

## Controlled same-session recovery

Command:

```text
.\.venv\Scripts\python.exe scripts\opencode_recovery_once.py \
  --run-name opencode-recovery-1caa822-20260913
```

Result: **PASS**, exit 0, 81.92 seconds.

- The first observed stop had exact `stage-one.txt`, absent `final.txt`, and
  zero prior PEX follow-ups.
- PEX completed model-backed semantic reviews through Strands.
- The action history was `NOOP`, then one justified `SEND_NUDGE` to the same
  OpenCode vendor session.
- The worker continued and produced both exact final artifacts.
- The causal recovery predicate passed, all 118 observed events settled, the
  follow-up count was exactly one, and the final observation stayed quiet.
- The owned OpenCode server exited and the source remained unchanged.

Retained local receipts:

- `build/opencode-recovery-1caa822-20260913/summary.json` — 1,878 bytes —
  SHA-256 `2562512371df92992741a3a0c3b8d490702de39240f94cd812769d767b1a27a3`
- `build/opencode-recovery-1caa822-20260913/receipt.json` — 1,362 bytes —
  SHA-256 `6fc925c087cc37a2de46dbd5484d4a05e71bcb8c2b04fb469c7b90a86214a91b`

## Correct completion stays quiet

Command:

```text
.\.venv\Scripts\python.exe scripts\opencode_quiet_ten.py \
  --run-name opencode-quiet-1caa822-20260913 --case-count 1
```

Result: **PASS**, exit 0, 76.31 seconds.

- Exact output bytes `6170706c652c706561720a` existed at the first stop,
  the input remained unchanged, and no earlier follow-up existed.
- The worker completion fence and completion-stop review passed.
- One model-backed semantic decision completed and was `NOOP`.
- Follow-up count was zero; `unnecessary_interruption` was false.
- All 102 observed events settled, the server exited, and source remained clean.

Retained local receipts:

- `build/opencode-quiet-1caa822-20260913/summary.json` — 2,064 bytes —
  SHA-256 `6fdcdfdfae7b398c2e55daf5be0b001bde023cafac90b4e4f693f55d680031bb`
- `build/opencode-quiet-1caa822-20260913/case-01-deduplicate/receipt.json` —
  1,419 bytes — SHA-256
  `fbfb435623ed0948e9bc81c256d94f572803e38466d2daffc02fe9da78009aaf`

## Claim boundary

This is fresh current-release behavioral evidence that PEX distinguishes one
controlled incomplete stop from one correct completion, corrects only the
former on the same session, verifies the outcome, and leaves the latter alone.
It is not a frozen comparative benchmark, a statistical interruption-rate
estimate, a current Codex pair, native-desktop-driven supervision, or a live AWS
AgentCore deployment.
