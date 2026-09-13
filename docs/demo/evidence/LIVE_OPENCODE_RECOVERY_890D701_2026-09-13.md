# Fresh current-source OpenCode recovery — 13 September 2026

Source at execution was clean, pushed
`890d7012e38a0c352d98f6d57c0870168c990046`. The product code remains the
published RC4 source `f2832a8651442eb3ee47a508a9c81cc16a82ec5d`; later
changes add evidence and installed-bridge soak tooling.

The bounded `scripts/opencode_recovery_once.py` diagnostic ran against a new
dummy workspace and a new owned OpenCode server. The worker was Zen
`mimo-v2.5-free`. The PEX supervisor was Zen
`muse-spark-1.3-contributor-free` through Strands Agents, using the previously
saved credential. No paid-provider fallback or AWS request was allowed.

## Result

- PASS in 83.98 seconds; source remained unchanged and the owned server exited.
- PEX observed the first completed worker stop with the phase-one artifact exact,
  the required final artifact absent, and zero prior follow-ups.
- PEX completed a real semantic review and issued exactly one
  `CONTINUE_SESSION` to the same OpenCode session.
- The worker produced the exact final artifact. PEX then observed the new stop,
  verified causal recovery, settled all 112 observed events and semantic reviews,
  and ended with `NOOP`.
- Receipt: one follow-up, five PEX model calls, 13,554 input tokens and 1,484
  output tokens. The configured three-dispatch limit counts review dispatches,
  not internal model calls.

Retained evidence directory:
`build/recovery-current-20260913-r2`.

- `receipt.json` SHA-256
  `891f9f1ff4bb1aa0fcdf8af6a1563c78d143910eb6175fa9886eb5882872acac`
- `summary.json` SHA-256
  `14baf6ed5f161d533dd3622a67998aba8849a4ac09c0bde2bf6fd6ddaeb26f6a`
- `events.json` SHA-256
  `5d0f77eb1bb6fc28dc1f3761a912034284ba42160426c3868b3fa6f6cacd1000`
- `PEX_INTERVENTION_LOG.jsonl` SHA-256
  `54522c8d499e9c1ffc5d5e5c6d0477467986bb3f94ad635d86c3e6415982446f`

This proves the MVP recovery behavior: observe a real harness, inspect external
workspace evidence, decide through Strands, continue the same worker, and verify
that the intervention helped. It is a controlled behavioral diagnostic, not a
four-arm comparative benchmark, native-desktop-driven supervision, a permanent
free-tier guarantee, or an AWS AgentCore deployment.
