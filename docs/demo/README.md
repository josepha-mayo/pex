# PEX demo assets

Use only the current evidence map below when preparing the Devpost video. Older files in this
directory are historical references and must not be presented as final-source proof.

## Current package

Clean product source `9966a602be7ed700844979e5fac2e2669cdb8823` produced the retained MSI and
NSIS installers. Both extracted inventories contain the desktop, frozen bridge, Cursor hook,
Cursor observer, and exactly eight packaged pet atlases. Package verification reports
`release_ready: true` with zero blockers. The source-bound receipt is
[`PACKAGE_RECEIPT_9966A60.json`](../PACKAGE_RECEIPT_9966A60.json).

The installers and working submission bundle are retained outside the repository at
`C:\Users\JosephMayo\Documents\Codex\PEX-submission-9966a60`. The installers are unsigned;
package integrity is not publisher identity and does not prove native runtime stability.

## Current visual evidence

Browser-only review of the exact package source covered Home, Inspector, Deck, Supervisor
Settings, Companion Settings, navigation, and the Pex companion. The target 920x700 Home and
Inspector renders had no error overlay, console error, blank content, or horizontal overflow.
The stable bundle contains the full screenshot set, including
`frontend-home-920x700-9966a60.png` and `frontend-inspector-920x700-9966a60.png`.

This is layout evidence, not native Tauri proof. PEX remains closed after the user-reported
idle whole-PC freeze. Native transparency, animation, close/reopen persistence, click-through,
and resource stability remain open until the user authorizes the exact bounded native smoke.
The exact package-source bridge independently passed an isolated empty-profile idle/resource
smoke with responsive liveness and no measured CPU, memory, thread, or handle growth; see
[`BRIDGE_IDLE_RESOURCE_2026-09-09.md`](evidence/BRIDGE_IDLE_RESOURCE_2026-09-09.md). That result
narrows the incident but does not clear the native window or real retained profile.

Keep the visual story to Pex and Von. All eight built-ins pass the structural v2 atlas
validator, but a two-character story is faster and clearer for judges. Pex is the default
supervisor; Von demonstrates that the companion can feel personal without turning the demo
into a pet gallery.

## Current Strands, AgentCore, and benchmark evidence

- Current pushed source `957c60c408a7463eccd12420cc660acc80b69cc3` passes the exact offline
  Strands/AgentCore gate **200/200 in 23.00 seconds** and the eight-task PexBench/Cursor-hook
  gate **201/201 in 343.82 seconds**. See
  [`OFFLINE_ACCEPTANCE_2026-09-09.md`](evidence/OFFLINE_ACCEPTANCE_2026-09-09.md).
- Exact clean packaged source `9357bb8` retains the complete real Codex Spark + free Muse
  Strands pair: evidence-supported quiet, then a specific same-thread recovery followed by a
  verified NOOP. See
  [`LIVE_CODEX_STRANDS_2026-09-08.md`](evidence/LIVE_CODEX_STRANDS_2026-09-08.md).
- Exact clean package source `9966a60` retains a fresh real Strands quiet success. Its recovery
  attempt failed closed because the independent verifier timed out twice under the free Muse
  provider; do not describe that retry as a current-source recovery pass. See
  [`LIVE_CODEX_STRANDS_2026-09-09.md`](evidence/LIVE_CODEX_STRANDS_2026-09-09.md).
- AgentCore is a fully contract-tested deployment target, not a deployed runtime. No active AWS
  credentials, verified ARM64 image, Runtime ARN, or no-card-charge proof exists. The exact
  package source does pass the real local AgentCore-compatible `/ping` + `/invocations`
  protocol smoke; see
  [`LOCAL_AGENTCORE_PROTOCOL_2026-09-09.md`](evidence/LOCAL_AGENTCORE_PROTOCOL_2026-09-09.md).
- PexBench remains `frozen: false`. The green contract gate is not a four-arm productivity
  score, leaderboard rank, or completed experiment.

## Filming

Follow [`RECORDING_RUNBOOK.md`](RECORDING_RUNBOOK.md) and the voiceover in
[`docs/SUBMISSION.md`](../SUBMISSION.md). The final video must be at most five minutes and must
show a real packaged native run, not the browser layout reference. Record only after bounded
native stability passes; otherwise present the current artifacts as a proof-of-concept package,
not a finished release.

The legacy headless recorder remains available for layout references only:

```powershell
uv run --no-project --with playwright python apps/desktop/scripts/record_submission_demo.py
```

It does not prove Tauri, the frozen bridge, a live worker, AgentCore deployment, or a benchmark
result.
