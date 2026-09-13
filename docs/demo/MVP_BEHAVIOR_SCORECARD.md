# PEX MVP behavior scorecard

Current as of 13 September 2026. This scorecard separates observed product
behavior from the still-unfrozen comparative PexBench experiment.

## What the live evidence proves

| Acceptance behavior | OpenCode | Codex |
| --- | --- | --- |
| Existing worker observed | Fresh owned HTTP session | Fresh owned App Server session |
| Persistent goal checked against workspace evidence | Yes | Yes |
| Supervisor | Strands Agents with saved Zen BYOK | Strands Agents with saved Zen BYOK |
| Deliberately incomplete stop detected | Final artifact absent | `report.txt` empty |
| Correction delivered to the same worker session | One `CONTINUE_SESSION` | One `SEND_NUDGE` |
| Requested repair verified | Exact final artifact | Exact `shipped` |
| Helpful outcome recorded | Yes, causal recovery | Yes, `helped:true` |
| Settled final decision | `NOOP` | `NOOP` |
| Separate correct-completion control | Passed, zero follow-ups | Exact `pong`, zero follow-ups |

The OpenCode recovery took 83.98 seconds and settled all 112 observed events
and semantic reviews. It made five supervisor model calls using 13,554 input
and 1,484 output tokens. The paired Codex recovery and quiet control completed
in 161.12 seconds. These timings include worker and orchestration time; they are
not model-latency comparisons.

## Restraint measurement

Ten consecutive OpenCode correct-completion controls passed without selective
retry. PEX produced only `NOOP` decisions and sent zero follow-ups: **0/10
observed unnecessary interventions** on this small public-artifact control set.
The run used 33 supervisor model calls and 128,320 supervisor tokens across
903.65 case-wall seconds. Silence is therefore proven as delivery restraint,
not as zero inference cost.

## Runtime and implementation checks

- Exact RC4 bridge soak: 300.016 seconds, 274 authenticated identity checks,
  28 authenticated settings checks, zero provider calls, and clean shutdown.
  It used 2.578 CPU-seconds, peaked at 100.2 MiB working set / 80.8 MiB private,
  and ended below its initial memory sample.
- Current Strands, AgentCore, provider, supervisor, and submission-preflight
  gate: 349/349 tests passed in 21.23 seconds.
- AgentCore's versioned `/ping` and `/invocations` contract is implemented and
  locally tested. No live AWS Runtime deployment is claimed.
- Zen credentials are entered write-only, stored in the operating-system vault,
  and were used in the live dummy-project runs. No credential is stored in
  these receipts.

## Evidence

- [OpenCode recovery](evidence/LIVE_OPENCODE_RECOVERY_890D701_2026-09-13.md)
- [OpenCode ten-case quiet control](evidence/LIVE_ACCEPTANCE_352D317_2026-09-13.md)
- [Codex recovery and quiet pair](evidence/LIVE_CODEX_PAIR_A529316_2026-09-13.md)
- [Exact RC4 bridge soak](evidence/INSTALLED_BRIDGE_SOAK_F2832A8_2026-09-13.json)

## Honest benchmark boundary

`python benchmarks/four_arm.py readiness` still reports
`manifest_frozen:false`, `coherent_runs:[]`, and `can_freeze:false`. Historical
rows do not share the isolation, raw-log, configuration, and same-session
treatment guarantees required for a fair Cursor/Codex four-arm uplift score.
They are not averaged, repaired, or promoted here. The table above is a bounded
MVP behavioral acceptance scorecard, not a comparative productivity claim.
