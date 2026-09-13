# Final OpenCode + Zen + Strands rehearsal — 13 September 2026

Clean source `694d452ede277a1b6e84bf835ce0409ca1ffcf8c` ran one
isolated recovery and one isolated already-correct control. The worker was
OpenCode `ling-3.0-flash-fin-free`; PEX used the saved OS-vault Zen BYOK route,
Muse Spark 1.3 Contributor Free, and Strands Agents. Both owned servers exited,
the source stayed unchanged, and no paid fallback or existing user session was
used.

- Recovery: **PASS** in 207.20 s. PEX observed exact phase-one state with the
  required final file absent, completed real semantic review, sent exactly one
  same-session `SEND_NUDGE`, observed both exact artifacts, verified the causal
  outcome, settled all 201 events, and sent no second correction. Five model
  calls reported 14,159 input and 1,946 output tokens.
- Quiet control: **PASS** in 155.48 s. Exact output existed before PEX review;
  one completed semantic `NOOP` was recorded, with zero follow-ups, no
  unnecessary interruption, and all 104 events settled. Two model calls
  reported 5,894 input and 806 output tokens.

Retained local receipts:

- recovery summary: 1,878 bytes, SHA-256
  `7d5b4b3e55b20f35726d5ddce1371f8aa7a82f5942291a62328f0df91770b77b`
- recovery receipt: 1,362 bytes, SHA-256
  `c7d49fab7fdcd2fff8f1c11f4523eb6bd5a7afceab1ab6ab5fdbac97449cfa4c`
- quiet summary: 2,065 bytes, SHA-256
  `f1a2354eaccfaab82fc93143b779424537757e01a34aecf0757c005aeca2979f`
- quiet receipt: 1,420 bytes, SHA-256
  `576a22885d5bc9db6739e12fcdebb039f539e056188d56530caff15f335ed250`

Two preceding attempts remain retained and are not counted as passes. Ling
recovered the exact files but exhausted the old single six-minute settling
window after repeated upstream endpoint failures. Nemotron 3.5 Lightning wrote
the wrong bytes and never stopped. The runner now remains globally bounded to
nine minutes while reserving up to three minutes after the first actionable
STOP; no product policy, dispatch cap, oracle boundary, or pass assertion was
weakened.

This pair is current-source behavioral evidence, not the frozen comparative
four-arm benchmark, native-desktop-driven supervision, or live AgentCore cloud
deployment.
