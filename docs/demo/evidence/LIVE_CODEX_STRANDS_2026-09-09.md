# Exact-source Codex + Strands check — 9 September 2026

This is a sanitized receipt for bounded live checks on exact clean product source
`9966a602be7ed700844979e5fac2e2669cdb8823`. It records one success and one unresolved
provider-latency failure; it is not a complete live pair and must not be presented as one.

## Configuration

- Worker: isolated Codex App Server, requested model `gpt-5.3-codex-spark`.
- Supervisor: Strands Agents 1.53.0 through Zen Responses,
  `muse-spark-1.3-contributor-free`.
- The saved credential was loaded without being printed or copied into tracked source.
- No local-model fallback, paid provider, native PEX window, AWS request, AgentCore deployment,
  or Docker start occurred.

## Quiet completion — validated

The worker created `ping.txt` containing `pong`. PEX observed the STOP, the real Strands
supervisor completed one model call, verified the existing completion, and emitted `NOOP`.
The proof binds a clean 646-file source fingerprint to revision `9966a60`, one exact Codex
thread/turn, the goal/session, STOP event, intervention, audit records, and artifact.

- Stable proof: `codex-inspect-proof-9966a60.json`.
- Proof SHA-256: `B7CEE65EFBF3259123C1D966F4618D91CF0F0912345DFAAC41033197CAC3B293`.

## Incomplete-work recovery — not validated

The main Strands agent correctly inspected the empty `report.txt`, called
`inspect_workspace`, `run_verification`, and `inspect_file`, and produced a specific semantic
correction. The independent verifier must make its own evidence-tool call before approving.
It did not complete its first provider response before the configured wall, so PEX correctly
replaced the unverified intervention with `NOOP`; no continuation was sent.

The first two-case run used the default 15-second verifier wall and ended **1 passed, 1 failed
in 158.27 seconds**. A single changed-condition retry ran only the failed recovery case with
the supported maximum 25-second wall. It failed the same way in **98.96 seconds**. The retained
audit row reports completed main inference with three model calls, exact acceptance-gap
observations, then verifier `status=timeout`, one attempted model call, zero verifier evidence
tools, and `latency_ms=25017`. This is consistent with current free-provider latency, not a
successful recovery proof. No further live retry was made.

- First-run JUnit SHA-256:
  `831D0DF8DD86E2200CE6798C5986A55221C05B5933076F8A51182AD4791A87C1`.
- Recovery-retry JUnit SHA-256:
  `5389C0EB3D760351C05314529D5B18E0CD57F687E5FB04A5F0FD30E8BE42A05A`.

Use the earlier exact `9357bb8` live pair for the currently validated recovery narrative, and
label it as ancestor evidence. Do not relabel this `9966a60` attempt, add its failed recovery to
quiet statistics, or claim current-source end-to-end recovery until a fresh bounded verifier
completes and the resulting same-thread outcome receipt validates.
