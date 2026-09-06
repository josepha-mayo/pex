# Controlled live Codex + Strands proof

Status: **validated on source revision `5c49c10eaed4ad96346ceef8d2eb257e46fcd425`**.

This is a sanitized, judge-readable summary of two strict local proof receipts. It is not
packaged-release proof, a benchmark score, or evidence of a deployed AgentCore service.
The raw receipts remain local and gitignored because they contain machine-specific paths
and identifiers.

## Case A — restraint after verified completion

- Controlled goal: create `ping.txt` containing `pong`.
- Worker: isolated Codex App Server thread in a `workspace-write`, no-network sandbox.
- Worker turns: 1.
- PEX decisions: 1.
- Acceptance: supported by the observed artifact.
- Action: `NOOP`.
- Supervisor: real provider call, `used_llm=true`, `inference_status=completed`,
  `runtime=strands-agents`, provider `zen`, model
  `muse-spark-1.3-contributor-free`, model calls 1.
- Safety evidence: source fingerprint and App Server process identity remained unchanged.
- Test receipt: `1 passed in 83.62s`.

## Case B — same-thread recovery from incomplete work

- Controlled goal: create `report.txt` containing `shipped`.
- Initial worker behavior: stopped deliberately without satisfying the goal.
- Worker: one isolated Codex App Server thread in a `workspace-write`, no-network sandbox.
- Worker turns: 2 on the same thread.
- PEX decisions: `SEND_NUDGE` followed by `NOOP`.
- Acceptance transition: `unsatisfied` to `supported`.
- Outcome: the second turn produced the observed `shipped` artifact; the intervention was
  correlated to the final STOP and recorded as `helped=true`.
- Delivery: the correction was bound to the exact worker thread and exact follow-up turn.
- Supervisor: both decisions used real provider calls with `used_llm=true`,
  `inference_status=completed`, `runtime=strands-agents`, provider `zen`, model
  `muse-spark-1.3-contributor-free`; the incomplete-state decision used 5 model calls and
  the final evidence-supported decision used 1.
- Durability: canonical SQLite rows matched their JSONL audit projections.
- Safety evidence: source fingerprint and App Server process identity remained unchanged.
- Test receipt: `1 passed in 137.53s`.

## Receipt integrity

- Local raw restraint receipt SHA-256:
  `512E78D56ED51B4711B91EC9F4189DF322748783A172B66A810C641FADA35065`
- Local raw recovery receipt SHA-256:
  `EC9B5145B4D0C2B08D168D88F0ACA3DBDEE874DBA8B2CC546952C5175C51F52C`

The cases ran in separate pytest processes by design. The first attempt at Case A failed
closed because a Windows sandbox-created file was unreadable to the parent verifier. The
fixture was corrected by pre-creating the operator-owned evidence target; production
verification still treats unreadable evidence as uncertain.

## Honest limits

- These are controlled file tasks, not a measured productivity lift.
- Codex is the live-demonstrated worker. Other adapters are implemented and
  capability-negotiated but are not claimed here as live-proven.
- AgentCore remains a deployment target until a live deployment receipt exists.
- The final release revision must recapture this pair before submission.
