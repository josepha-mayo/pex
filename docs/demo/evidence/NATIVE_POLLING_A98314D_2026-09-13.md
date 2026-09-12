# Inspector polling diagnostic — 13 September 2026

Clean source `a98314d` removes full Deck, benchmark-result and desktop-discovery
reads from Inspector's 32-second reconciliation. Inspector retains context,
intervention and attention reads. Entering Deck enables its full reconciliation.

A diagnostic Tauri release executable built with `--no-bundle` and a temporary
before-build override running release preflight and the frontend build. The
unchanged bridge sidecars were validated, not rebuilt. No new installer was
generated or installed; installed `949cb47` remains unchanged.

Diagnostic desktop SHA256:
`8e1c0dbac9b21f0a596e5eb3b27701579b716e47b9eed753e0105e8b1a17b501`.

Native Home opened. Selected the retained Native RC2 two-stage recovery
OpenCode session and opened Inspector; its saved outcome and inference receipt
remained visible. Entering Deck refreshed from loading to **Canonical local
state**, with current worker rows and attention metrics. No worker turn or
provider call was requested. Closed the diagnostic normally afterward.

## Resource observation, not a controlled performance benchmark

The same all-descendant sampler measured ten PEX processes, including bridge
and WebViews, with the saved pet-hidden preference retained. Over 46.066 seconds,
CPU advanced 10.796 seconds: 23.44% of one logical core. Private memory fell from
389.22 MiB near entry to 330.35 MiB; minimum 328.18 MiB.

The earlier installed `949cb47` hidden-pet sample averaged 30.89% of one core and
ended at 350.89 MiB. The later observation is lower, but startup age, process
state and test order were not fully controlled. Do not claim a causal percentage
speedup, low-idle-CPU clearance, or resolved freeze. Idle CPU remains noticeable.

Raw sample: `build/native-inspector-resources-a98314d.json`; SHA256
`ff2a8c83777a5cefbb2d51f15b2031535aa4832f153ac872716ba8c26915fc68`.
Build log: `build/native-performance-build-a98314d.log`.

Source tests: 298 passed, one intentional Windows symlink skip. Frontend and
native diagnostic builds passed. Release packaging is still pending. Full goal,
live Codex, formal benchmark, AgentCore deployment, recording and submission
remain separate gates; none is inferred from this test.
