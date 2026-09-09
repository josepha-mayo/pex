# Live OpenCode quiet-completion receipt — 9 September 2026

## Result

**Product behavior PASS; original harness boolean rejected by a corrected checker predicate.**
A real OpenCode 1.18.29 worker using `opencode/mimo-v2.5-free` created both exact required files
in one turn. Production PEX observed the terminal SSE event, used the saved Zen BYOK credential
with `muse-spark-1.3-contributor-free`, concluded `NOOP`, and sent zero follow-ups. That is the
required quiet behavior: inspect a correctly completed goal without nagging the worker or user.

The raw run wrote `success:false` because the proof harness incorrectly required zero
intervention rows. PEX correctly persists a `NOOP` intervention row for auditability. The harness
predicate was repaired to accept one or more all-`NOOP` rows plus zero delivered prompts. An
independent read-only validator applied that corrected predicate to the retained immutable run and
exited 0 with `quiet_acceptance_predicate: PASS`. No worker/model rerun was used to rewrite history.

## Evidence

- Product code: package source `933239a1bd0e05e65274d9c895750374239407b3`; intervening
  tracked changes were documentation-only.
- Session: `opencode:ses_f787d9b1fffee12xUbzuE5RQFQ`.
- Exact outputs: `stage-one.txt` = `stage-one-ok\n`; `final.txt` = `pex-supervised-ok\n`.
- Retained SSE events: 282.
- Supervisor: 2 model calls, 6,994 input tokens, 811 output tokens, 14,437 ms recorded latency.
- Durable action: `NOOP`; PEX follow-up count: 0.
- Raw receipt SHA-256: `2b3159324634220f31b6d4b67525826ad56bf4079a46a1b055f77809725d1f9c`.
- SSE JSONL SHA-256: `311f918c7a47b7771a8d111ba395b035bae6feb9fc78064e8a673f03a6523a8c`.
- Intervention JSON SHA-256: `575d1db2d40e9cb4b26f20c01b06ee1cfd2aadd95af40d1181c8345bb06f5ed2`.
- SQLite SHA-256: `aab81a4e37725ba755913f69dd5e155cc24e37c70615a030fc33234e927d7579`.
- All three secret-pattern scans returned zero matches; temporary profile directories were
  removed; port 4097 and the owned serve process were absent after cleanup.

The first quiet attempt used the free Ling worker. It created both exact files but did not emit a
terminal event before the five-minute bound, so PEX correctly had no STOP authority and sent no
message. That failed attempt remains at `build/opencode-pex-quiet-ling-timeout.json`, SHA-256
`e9741880f0bc67baed7ea63c136c15726b86a5ca9793f80c3b70a9f50f43f040`.

This is one controlled quiet case, not the required ten-case false-positive-rate sample and not a
benchmark score. No independent verifier is expected on an evidence-supported `NOOP`; the main
Strands inference inspected and stayed silent.
