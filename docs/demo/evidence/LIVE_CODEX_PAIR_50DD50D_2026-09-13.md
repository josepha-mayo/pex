# Fresh Codex / Zen / Strands live pair — 13 September 2026

Both tests passed on clean source
`50dd50d6612fa4c6e95c6fa76cfabea63b807910`, source fingerprint
`9e24560789fa4ec6cf20282b0456c229bcb44d2539d2cde7bc5f223b5801e83f`.
These are live production-pipeline behavioral checks, not desktop-driven worker
turns or a comparative productivity benchmark.

Worker: explicitly requested `gpt-5.3-codex-spark` through a separately owned
Codex stdio app-server, using the approved ChatGPT quota. Preflight confirmed
the account type and model availability without starting a worker turn.
Supervisor: saved OS-vault Zen credential, exact
`muse-spark-1.3-contributor-free`, `https://opencode.ai/zen/v1`,
Strands Agents 1.53.0. Review cap three; no model substitution, paid fallback or
AWS deployment. Only public throwaway file tasks were sent to the provider.

## Observed results

| Case | Result | Worker turns | Supervisor calls | Test duration |
| --- | --- | ---: | ---: | ---: |
| Premature stop | Empty report.txt detected; one evidence-specific SEND_NUDGE; same session wrote exactly shipped; helped true; final NOOP | 2 | 5 (4 correction, 1 final) | 84.69 seconds |
| Correct completion | Worker wrote pong; acceptance supported; model-backed NOOP; no delivery receipt or follow-up | 1 | 1 | 38.97 seconds |

Recovery outcome is `goal_evidence_supported`. Its correction was independently
verified against the empty file, bound to the persistent goal and original
session, and delivered through the same app-server process. Both receipts have
`proof_status: validated`, correlated vendor STOP events, audit records, model
receipts and unchanged source provenance. Both JUnit reports show one test,
zero errors/failures/skips. The quiet test checks stripped text, not exact
newline bytes; do not promote it to an exact-byte assertion.

Commands: `.venv/Scripts/python.exe build/codex_live_20260913.py recovery` and
the same runner with `quiet`. The ignored runner loads the saved provider into
the test process without printing the key and invokes the corresponding tests
in `tests/contract/test_live_codex_pump.py` with unique retained pytest roots.
Prior scratch receipts were copied separately; current receipt timestamps and
source were checked, rather than assuming copied files were fresh success.

Retained receipts:

- `build/codex-20260913-recovery/codex_incomplete_proof.json`, SHA256
  `3868985db7d8466c91bef2c882f506511d74264cf2ee595dfb12f8ba051689ac`.
- `build/codex-20260913-quiet/codex_inspect_proof.json`, SHA256
  `8301ed5362484da9f367c9246355fdb5b68df41df58aaa33f6dd7c93ee3f259e`.
- Each directory retains `result.xml` and its isolated test workspace/database.

Owned Codex process IDs 9184 and 15400 were absent after cleanup. No other
Codex process or user session was closed.

## Separate installed-native check

The computer-use launcher resolved to installed PEX, not the requested source
diagnostic. Its executable hash was checked as
`b04647fefd9490670c18e937af4032bc9b2381837575cf1fc54cac87f82d269d`
(installed candidate `949cb47`). Home rendered the worker sidebar and flat cat
mark; Companion Settings rendered exactly Pex and Von, with pet visibility
off. Supervisor Settings showed saved Zen, exact free Muse model, cap three,
and a vault credential indicator without revealing a secret. No key was entered
or saved in this sweep. PEX closed through normal Alt+F4; no PEX desktop or
bridge process remained in the subsequent process check.

This small interaction sweep is not long-duration resource/freeze clearance.
The earlier idle CPU concern remains open. The newer Inspector polling fix
`a98314d` is still diagnostic-only, not part of this installed binary.

## Benchmark boundary

Fresh `benchmarks/four_arm.py readiness` still reports `can_freeze:false` and
an unfrozen manifest. Missing coherent four-arm evidence, isolated hidden
evaluation, vendor capture and Cursor treatment integrity remain blockers to
a comparative score. This pair proves two bounded Codex supervision behaviors;
it does not prove general productivity uplift, a leaderboard position, full
MVP completion or submission readiness by itself.
