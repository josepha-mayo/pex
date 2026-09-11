# Current-source OpenCode quiet-completion receipt — 11 September 2026

## Result

**PASS for one bounded quiet case.** Clean source
`6a1d98be19fe5b127b7dd39e74ba91f2de13b194` ran a real OpenCode 1.18.30
worker through the production HTTP/SSE adapter and the real local Strands
supervisor. The worker completed the public deduplication task correctly before
PEX's completion review. PEX then stayed quiet: one completed model-backed
`NOOP`, zero follow-ups, no unnecessary interruption, and every observed event
settled.

This is a current-source restraint diagnostic. It is not a comparative
benchmark, a native-desktop acceptance result, a ten-case false-positive rate,
or AgentCore deployment evidence.

## Bound result

- Run root: `build/opencode-quiet-6a1d98b-20260911-r1` (local and ignored).
- Public case: `deduplicate`; `unique.txt` was exactly `apple,pear` plus one LF.
- The input file remained byte-exact.
- PEX session: `opencode:ses_f6ed23eb9ffeeD1AQzDmEThMby`.
- Goal: `goal_6ee4dc915c424ec5b269a606cdf5aa29`.
- First observed stop was already correct and had zero prior PEX follow-ups.
- Latest user/assistant generation: `msg_0912dc46f001Rqsb3obbu4hcnu` /
  `msg_0912e61e50018IVw934j7DzFhY`.
- 258 events were retained and all processing rows settled.
- One semantic review completed; action list was exactly `[NOOP]`.
- Model accounting: 2 calls, 6,944 input tokens, 820 output tokens.
- Wall time: 169.11 seconds, including the resettable 12-second quiet fence.
- Worker: `ling-3.0-flash-fin-free`; supervisor:
  `muse-spark-1.3-contributor-free` through saved Zen BYOK.

The [current official Zen pricing table](https://opencode.ai/docs/zen#pricing)
listed both exact models as Free for input and output at execution time. No AWS
route or paid fallback was enabled.

## Integrity and cleanup

| Artifact | SHA-256 |
| --- | --- |
| `summary.json` | `7f41c20ead683911e294fc0eeb8e332f5aa95141637eda2c31285e200f97f702` |
| `case-01-deduplicate/receipt.json` | `dc2657de348bfd6f02b2cbd32f894414652893ec24a4b7ab8efa6ad44c53069d` |
| retained `runner.py` | `b253196429871b36dae107be9160ffa267263f8389b901d09f2dcf60c150329c` |
| retained `completion-fence.py` | `d613e24b7b6a4a4082ad88fa36fcd3e6387f074927cebd1994963f472baeff4d` |

The summary binds unchanged clean source and reports `owned_server_exited:
true`. A byte-exact scan of the 34 retained proof files outside the isolated
OpenCode cache/config/data/state directories found zero copies of the saved
vault secret. Those profile directories remain local for diagnosis and must not
be published without a separate privacy review.

## Remaining gate

Run one current-source controlled incomplete-stop recovery, requiring a specific
same-session correction, exact final artifacts, a final model-backed `NOOP`, and
`goal_evidence_supported` / `helped: true`. Then run visible current-package
startup, transparency, hide/restore, connection, BYOK and foreground-resource
acceptance when the shared screen is free.
