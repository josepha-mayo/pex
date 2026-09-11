# PEX current offline MVP gate — 11 September 2026

Tested tree: `a58ad4fb18cddf4418f28714d1d64cb133ee600a`.
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
