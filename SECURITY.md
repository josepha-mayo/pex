# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately — open a GitHub security
advisory on this repository rather than a public issue. Include the affected
component (bridge, desktop shell, replay pipeline, packaging) and a minimal
reproduction.

## Trust model

- The demo bridge binds to `127.0.0.1` only and may advertise
  `unauthenticated_operator` **in test/demo mode**. Never deploy that mode
  on a routable interface — it intentionally unlocks operator controls
  (decisions, pause/resume, task composer, handoffs).
- The packaged desktop app authenticates the bridge with a bearer token
  owned by the Rust launcher; the token never enters the repository.
- Worker sessions (OpenCode/Codex) run under the user's own credentials and
  workspace; PEX supervises them but does not proxy or store provider keys.
- Nebius Token Factory / NVIDIA keys are read from the environment or the
  OS keyring, never written to the repo, logs, or evidence packs.
- ConTree public-test execution is network-isolated by design; a configured
  but unavailable sandbox fails closed with an explicit `error_type`.

## Data handling

Event payloads, ledger entries, and verification receipts may contain
workspace paths and code excerpts. Evidence packs are designed for offline
inspection (`scripts/verify_pack.py`) and contain no secrets by contract —
if you find one, report it as a vulnerability.

Recorded replay fixtures are deterministic, synthetic or captured-with-
provenance trajectories; they carry `replay: true` + `not_live_control:
true` markers and must never be presented as live worker sessions.
