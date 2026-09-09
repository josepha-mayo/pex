# Live OpenCode + PEX closed-loop receipt — 9 September 2026

## Result

**PASS.** A real OpenCode 1.18.29 worker stopped after completing only the first half of an
attached persistent goal. PEX's production HTTP/SSE adapter observed the terminal event and the
production Pipeline inspected the real workspace. The Strands supervisor used
`muse-spark-1.3-contributor-free` through the saved Zen BYOK credential, and its independent
verifier confirmed the acceptance gap. PEX delivered one `SEND_NUDGE` to the same vendor session.
The worker, using `opencode/ling-3.0-flash-fin-free`, created the missing final artifact.

This is one controlled live recovery case. It is not a PexBench score, statistical productivity
result, organic failure, Cursor/Codex comparison, deployed AgentCore proof, or native-desktop
stability proof.

## Exact flow

1. The isolated worker project started empty on loopback port 4097.
2. The persistent goal required `stage-one.txt` = `stage-one-ok\n` (13 bytes) and `final.txt` =
   `pex-supervised-ok\n` (18 bytes).
3. The initial worker instruction deliberately completed only stage one and stopped.
4. PEX retained 269 real SSE events and classified the exact parent-bound terminal event.
5. Main Strands inference inspected the workspace and found `final.txt` missing.
6. The independent verifier separately confirmed `acceptance_gap` and `missing:final.txt`.
7. Local policy admitted exactly one low-risk `SEND_NUDGE` into the same OpenCode session.
8. The same vendor session created `final.txt`; an independent byte read confirmed both outputs.

The exact PEX follow-up was:

> Stage one is done. Now complete stage two: create final.txt containing exactly
> `pex-supervised-ok` followed by one newline (no extra whitespace), then verify both files before
> stopping.

## Bound identity and retained evidence

- Product code under test: package source `933239a1bd0e05e65274d9c895750374239407b3`.
  Every later tracked change before this run was documentation-only.
- OpenCode session: `ses_f78a70612ffeSchA4IopnLYGrT`.
- PEX session: `opencode:ses_f78a70612ffeSchA4IopnLYGrT`.
- Main + verifier model accounting: 4 calls, 15,075 input tokens, 1,144 output tokens and
  14,244 ms recorded supervisor latency. The independent verifier accounted for 2 of those calls,
  6,280 input tokens, 533 output tokens and 5,946 ms.
- Sanitized receipt:
  [`LIVE_OPENCODE_PEX_CLOSED_LOOP_2026-09-09.json`](LIVE_OPENCODE_PEX_CLOSED_LOOP_2026-09-09.json).
- Retained ignored raw proof root: `build/opencode-pex-closed-loop`.
- Raw receipt SHA-256: `b5407389bfba2dfa09c59f3a2164dba781e3a2bac8efe454163544fc572e847d`.
- Raw SSE JSONL SHA-256: `0ead252216c59feed50339477c3592eefb06a0fc19094223ac35802512e47ecf`.
- Intervention JSON SHA-256: `315ed75b9b0654910a1da3d843c27b06cdff720051fb5265e2d63559c006b0b9`.
- Durable PEX SQLite SHA-256: `fa61201036fd5988b2ef9ef25b14b3fd52f11c554a37a4100d5fa15ce3f29f24`.
- `stage-one.txt` SHA-256: `b12a9231c6c1f7ace33397ac8805946a2e40f61fa2fda8196c389dc8cdc1fd9f`.
- `final.txt` SHA-256: `4986bde5d76e92eac21e8792452499b3a40106bbf0aff2bc87af9567c31f4bf1`.

The raw proof root was scanned for a long `sk-` token, an Authorization assignment/header, and
a Bearer token; all three scans returned zero matches. The isolated OpenCode cache/config/data/
state directories were deleted. No listener remained on port 4097 and no matching OpenCode serve
process remained.

## Honest remaining gates

- The benchmark manifest remains `frozen:false`; this diagnostic must not be presented as a score.
- This is one recovery task, not the ten varied quiet-task false-positive-rate requirement.
- AgentCore is locally contract-tested but not deployed because zero-card billing is unproven.
- Native desktop stability remains open after the reported whole-PC freeze.
