# Home selection and D-drive migration evidence — 13 September 2026

This receipt covers a source repair and local workspace migration. It is not a
native package, live model-inference, AgentCore deployment, comparative benchmark
or submission receipt.

## Finding

Installed 268d39a connected to an owned OpenCode server on loopback. Before an
explicit worker selection, a bridge refresh reordered two `discovered` rows and
Home changed from the real OpenCode session to the observe-only Codex desktop
row. The previously visible Set Goal path consequently reached Connections.
Explicitly selecting OpenCode kept its workspace stable and Inspector accepted
and attached the persistent goal.

The selector reproduced independently from the production function: reversing
the two input rows changed the automatic selection, while explicit selection
remained stable.

## Repair

`selectPrimarySession` retains the existing urgency tiers. Within each tier it
now prefers a session that can own a persistent goal over an observe-only desktop
placeholder. An explicit selected ID remains authoritative. A regression covers
both discovery orders and the explicit-placeholder override.

## Verification

- Desktop suite: 303 tests, 302 passed, 1 platform capability skip, 0 failed.
- Production frontend: TypeScript and Vite build passed; 74 modules transformed.
- Cursor exact-completion contracts from the D: checkout: 60 passed in 43.40s.
- Python imports resolve to `D:\PEX-work` for protocol, bridge and supervisor.
- `git diff --check` passed before the evidence update.

## Migration boundary

`D:\PEX-work` is the authoritative checkout at base commit `0c9e9d4`. Its resumed
copy reported 193,407 files / 23.833 GiB and zero failures; Git fsck passed and
the pre-existing byte-exact Cursor fixture repair matched by SHA256. PEX runtime,
WebView data and live state payloads are on D: behind compatibility junctions.
C: recovered from zero bytes to roughly 66 GiB free. Recoverable archives are
under `D:\C-drive-recovery`.

The prior full offline suite is invalid because disk exhaustion generated errors
and prevented its JUnit report from completing. A fresh full run is still
required. This repair is not in installed 268d39a until a new package is built,
verified and installed.
