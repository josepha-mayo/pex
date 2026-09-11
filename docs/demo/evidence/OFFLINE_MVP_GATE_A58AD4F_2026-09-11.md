# PEX current offline MVP gate — 11 September 2026

Focused-gate tree: `a58ad4fb18cddf4418f28714d1d64cb133ee600a`.
Accepted full-regression tree: `dd0644390078ee5b3f4d19827e145a94ee63baf0`.
Package source: `56783bff3dec8c25e725c3dded603b8ad1d76079`.

All checks below were local/offline. They made no provider, worker or AWS call.

| Area | Result |
| --- | ---: |
| Zen BYOK/provider/configuration/security | 210 passed, 1 Windows symlink skip |
| OpenCode/Codex cancellation, lineage and correction | 137 passed |
| AgentCore local client/runtime/pipeline/preflight | 183 passed, 1 opt-in live-cloud skip |
| Frozen packaged bridge lifetime and standalone manifest | 3 passed |
| Benchmark, Cursor hook, audit, execution safety, public summary and scoring | 261 passed |
| Policy scoring and speculative execution | 22 passed |
| Source/setup contract after edits | 8 passed |
| Full Python regression on current tree | 4,436 passed, 32 skipped |

The first OpenCode/Codex run lacked the pinned Rust directory in `PATH`; its
nested release preflight returned before the fleet section, producing 59 passes
and one environment-caused failure. The corrected full rerun used the release
toolchain path and passed 137/137.

The frozen-runtime gate initially found a stale contract assertion for the
retired eight-pet inventory. Product output was already correct (`pex`, `von`).
The test was repaired to the two-pet MVP contract; its complete rerun passed 3/3
and Ruff passed.

The 283 benchmark/scoring checks prove deterministic accounting, contamination
and isolation guards, public-summary honesty, Cursor hook behavior and policy
scoring. They are **not** a live productivity score. `benchmarks/manifest.yaml`
remains `frozen: false` until one coherent, retained multi-arm run meets its
declared evidence requirements.

Native interaction/visual acceptance, live final-package supervision, demo
recording, AgentCore deployment and submission remain open. AgentCore deployment
is optional and no uncovered AWS spend was authorized.

## Broader regression continuation

The final fresh normal-priority run on `dd06443` completed successfully: 4,436
passed, 32 skipped, zero failures/errors in 2,743.56 seconds, exit 0. Its JUnit
artifact is `build/full-offline-dd06443-20260911.xml` (718,224 bytes), SHA-256
`a9aae1f63ad0206df6083b0069b710005683701139fac59ece2238390fa843c2`.
No matching PEX or repository pytest process remained afterward. This is the
accepted broad regression result; the stopped attempts below are retained only
as causal repair history.

A below-normal-priority full Python run stopped at its first failure after 3,232
passes and 30 skips. The failure was another stale pre-cap test expectation:
`test_pet_snapshot_includes_idle_harness_for_prompts` expected an unlimited
allowance although the shipped fresh-install default is three. Product output
was correct. The test now requires the default 3/3 allowance and separately
proves an explicit 1/1 override. Its complete file rerun passed 26/26 and Ruff
passed. The stopped run is not a pass and is superseded by the clean result
above.

The next fresh whole-suite attempt stopped at 1,261 passed and 21 skips on a
10-second async fixture settle timeout in
`test_stop_then_external_input_same_batch_freezes_distinct_prefixes`. The exact
case then passed in isolation and its complete file passed 5/5, so no production
latency change was justified. The test-only settle budget is now a still-bounded
30 seconds to tolerate Windows scheduler contention during the below-normal
broad run. Ruff passes. This second stopped run is also not a pass and is
superseded by the clean result above.

A later normal-priority broad run stopped at 781 passed and 19 skips because a
fresh subprocess importing the complete bridge/Strands ASGI graph exceeded its
test-only 15-second wall clock before reaching the auth assertions. The exact
security test passed in isolation; the full auth file then passed 16 with two
Windows skips. Its subprocess budget is now a bounded 45 seconds. Operator-token
scrubbing and child non-inheritance assertions are unchanged; no production
timeout changed. The stopped broad run is not a pass and is superseded by the
clean result above.
