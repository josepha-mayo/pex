# Current-source OpenCode supervision pair

Source: clean `150ea07b205776660219dbfb1802ff86b998e8df`, equal to
`origin/main` throughout both runs. The installed OpenCode version was 1.18.30.
The worker was `ling-3.0-flash-fin-free`; the PEX supervisor was the saved Zen
BYOK selection `muse-spark-1.3-contributor-free` through Strands Agents 1.53.0.
No AWS resource, paid fallback, browser, native PEX window, or comparative
benchmark ran.

## Quiet completion

Command:

```text
python scripts/opencode_quiet_ten.py
  --run-name opencode-quiet-current-150ea07
  --case-count 1
```

Result: pass, exit 0, 70.31 seconds.

- The worker created exact bytes `6170706c652c706561720a` and preserved the input.
- PEX observed the parent-bound terminal event after the correct artifact existed.
- One semantic review completed through Strands: `NOOP`.
- Follow-up count was zero and `unnecessary_interruption` was false.
- All 118 retained meaningful events settled; redundant token deltas were not
  placed on the durable decision queue.
- The owned OpenCode server exited and port 4098 had no listener afterward.

Receipts:

- `build/opencode-quiet-current-150ea07/summary.json`: 2,064 bytes,
  SHA-256 `acb3608184d86348515a6a0d7e86e2697286455eda14b121fedf7bfd31bc4f70`.
- `build/opencode-quiet-current-150ea07/case-01-deduplicate/receipt.json`:
  1,419 bytes, SHA-256
  `5bb2220a1b769e773baa27120312d87247bae1739ce71c32af5a42eceb439c1c`.

## Same-session recovery

Command:

```text
python scripts/opencode_recovery_once.py
  --run-name opencode-recovery-current-150ea07
```

Result: pass, exit 0, 114.44 seconds.

- The deliberately incomplete first stop had exact `stage-one.txt`, absent
  `final.txt`, and zero earlier PEX follow-ups.
- Deterministic verification reported `missing:final.txt`.
- The Strands supervisor proposed one specific `SEND_NUDGE`; an independent
  semantic verifier approved it.
- The correction was accepted by the same vendor session, the worker continued,
  and `final.txt` reached the exact required bytes.
- The intervention outcome was `goal_evidence_supported` with `helped:true`.
- A second model-backed review returned `NOOP` after supported completion.
- Exactly one follow-up was sent, all 124 events and all semantic reviews settled,
  the source stayed unchanged, and the owned server/port were clean afterward.

Receipts:

- `build/opencode-recovery-current-150ea07/summary.json`: 1,804 bytes,
  SHA-256 `510750d39081c880f0af6bc18177f9cdb56028435dc02263a137eeb0473327b2`.
- `build/opencode-recovery-current-150ea07/receipt.json`: 1,292 bytes,
  SHA-256 `15e49001fff888de834995bc511b341e7d76183a44def6caca6300ea470091e8`.

## Defects found and repaired before the accepted pair

Three retained failed attempts remain diagnostic evidence and are not passes:

1. `opencode-quiet-current-2dd6625` stopped at session creation with
   `DeliveryUncertainError`. A fresh isolated no-model diagnostic showed that
   OpenCode reports global health before cold project/database initialization is
   complete. HTTP connect/write/pool bounds remain eight seconds; the response
   read bound is now 30 seconds so a successful mutation can return its receipt.
2. `opencode-quiet-current-6d493ae` produced the exact artifact but exhausted
   the 240-second fence before terminal review because 106 token deltas were
   durably queued. The pump now discards only redundant delta fragments and
   retains complete part/message/tool/status/terminal evidence.
3. `opencode-recovery-current-8bcbf6e` correctly produced and independently
   verified the exact correction, but delivery was denied because the two-second
   capability probe timed out. OpenCode alone now receives an eight-second
   bounded probe; a true timeout still fails closed.

Verification after the repairs:

- OpenCode adapter/safety gate: 259 passed, one environment-gated skip.
- Expanded MVP seam after event triage: 552 passed, one environment-gated skip.
- Capability/OpenCode gate: 144 passed.
- Stop/recovery and dispatch-identity gate: 90 passed.
- Ruff and `git diff --check`: pass.

## Claim boundary

These are two controlled, public, non-comparative behavioral diagnostics. They
prove the current OpenCode/Zen/Strands closed loop and restraint behavior on this
machine. They do not prove a frozen four-arm benchmark, Cursor behavior, native
desktop acceptance, an AWS AgentCore deployment, a fresh-machine install, or a
zero-cost guarantee from the provider.
