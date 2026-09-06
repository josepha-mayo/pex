# Controlled live Codex + Strands proof

Status: **fresh production shared-worker pair independently reviewed on clean
source `4543a58c84a7839d30168b292d2a6abe441214ea`**.

## Existing-worker production path — newest evidence

An operator created each dedicated demo worker before PEX inspected and connected
to it. Persistent goals and correction grants were set through the normal bridge
HTTP API. PEX neither started a replacement harness nor used a test-only delivery
override. Worker configuration requested `gpt-5.3-codex-spark`; this is not an
attestation of executed model identity. Supervisor inference used real Strands
and the explicitly configured free Muse model, with no paid fallback.

| Case | Observed behavior | Worker turns |
| --- | --- | --- |
| Controlled premature stop | Empty artifact → one evidence-grounded correction → exact `shipped\n` artifact → supported outcome, `helped=true` → NOOP | One warm-up, one deliberate stop, one PEX correction in the same thread |
| Correct completion | Worker produced exact `shipped\n`; PEX returned NOOP with corrections enabled | One warm-up, one completion; no PEX-generated turn |

Recovery used three main and three independently gathered verifier observations.
An independent review recomputed all six output hashes and verified goal/session/
trigger/request bindings and separate invocation IDs. The delivered correction,
worker response, shell observations and final STOP share the exact correction
turn. Immutable delivery scope also binds subscription, endpoint and connection
generation across effect, intervention and durable audit. Final artifact bytes
were checked independently, not inferred from the worker's completion claim.

The quiet case made one real Strands decision (`used_llm=true`, 3,175 ms recorded
inference latency) and produced no correction receipt. Both grants were revoked
and both observers detached; separate worker reads confirmed idle completed
threads without stopping their App Server. Warm-up notifications were not
reliably delivered to the operator's waiter: one timed out and the other was
closed after read-only inspection established completion. Neither warm-up was
resent. This is retained as an operator-driver limitation, not erased as success.

Private terminal capture SHA-256 values:

- Recovery: `D5FA8E24115D159FBDC87665298E7F30210BBA34599DE0FB2CC1433A13441F1F`.
- Quiet: `A7DEB3CE10DE35DD0C979FDFF802D8075EBBE694C05CB413AEFF040CDE464FB3`.

These are controlled dedicated-worker cases, not proof on an unrelated user's
ongoing work, ten varied tasks, productivity lift, deployed AgentCore, future
silence, or final installed-build behavior. Earlier evidence below remains
historical and is not silently relabeled as this production path.

## Fresh independently bound pair

Both cases ran from one clean source fingerprint with the requested worker model
`gpt-5.3-codex-spark`, pinned in the isolated App Server process configuration.
This records requested configuration, not authoritative executed-model identity.
The real supervisor used Strands Agents 1.53.0 and Zen's exact
`muse-spark-1.3-contributor-free` model with no paid fallback.

| Case | Observed outcome | Real supervisor calls | Test time |
| --- | --- | --- | --- |
| Correct completion | `ping.txt=pong`, one worker turn, evidence-supported `NOOP` | 1 | 98.44s |
| Premature stop | Empty `report.txt` -> `SEND_NUDGE` -> same-thread second turn -> `report.txt=shipped` -> supported `NOOP`, `helped=true` | 4 initial, including 2 independent-verifier calls; 1 final | 135.52s |

The independent verifier returned `approved` with three typed observations, distinct
from the main invocation and bound to the same goal, session, trigger and request
digest. The v4 validator checks evidence hashes/references and canonical SQLite/audit
agreement, not just an aggregate model-call counter. The initial call count already
includes the verifier; do not add it again. Durations include worker/setup/inspection,
not isolated supervisor inference latency.

Raw receipt SHA-256 values:

- Restraint: `13222498A44212F9A25FFD5BEBFCF76A6084DC0DF3999957F40CC09310A6179E`
- Recovery: `8D3C92581CC0895ECB7A5A4E89C5C0F1B680D4DB084ED39691E3B6B5C142E8A1`

Earlier `f53c13b` recovery failed closed after verifier budget exhaustion; the prompt
was repaired without weakening the evidence/permission gates. These are the first
post-repair v4 attempts. A setup-only restraint attempt failed before worker/model
calls because the scratch parent directory was absent; that directory was created.
Retained unique scratch directories preserve both live databases for inspection.

These remain controlled file tasks in isolated Codex threads, not attachment to the
user's pre-existing worker, ten quiet cases, cross-harness benchmarks, AgentCore
deployment or final-package evidence. The earlier v3 pair below is historical only.

## Narrow repeated restraint check — source `726a3d2`

Ten consecutive isolated repetitions of the same completed `ping.txt=pong` task
passed, with a fresh worker thread and real Strands inference each time. Requested
worker and supervisor models were unchanged from the v4 pair above. This checks
repeatability of restraint on one narrow artifact case; it does not satisfy a suite
of ten varied coding tasks or measure productivity. Test times in order were
111.18, 105.33, 107.52, 108.31, 91.00, 95.45, 93.27, 85.68, 88.02 and 92.73 seconds.
The raw receipts/databases remain separately retained locally. First and last
receipt SHA-256 values are respectively
`B11E6117B6C7FFE085A1BF173AB8D28F8D7A55523855EDD06BAC53A608259DC2` and
`95B7EC59F2D7A87751061805479A106215C38B97F6FB7CEB3EEBDEAB006C708D`.

## Historical v3 pair — source `5c49c10`

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
