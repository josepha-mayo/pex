# Demo assets

## 6 September native-package checkpoint

The final repository revision is
`f99fe4399720a223d96f1ad860b34ae175f5d917`. Its clean package receipt has SHA-256
`23E1FA33736E387C22292D471375E43AC970DD37E3D27319E8D88CA204683C12` and reports
`release_ready: true` with no package-integrity blockers. This is narrowly package
integrity, not overall release or submission readiness. The unsigned MSI is 122,585,088
bytes with SHA-256
`759A9B2091804603563333C9087AD88ED4BFA60FD60A9BBBE3F89C126B2660DE`; the unsigned
NSIS installer is 121,294,055 bytes with SHA-256
`ADD72B18AFF7792D32D5AEAA1BC07C48929E3ED0A45F0AD4CDD896833FF76A69`.

The extracted NSIS app was exercised with a fresh profile: its packaged bridge reached
**All quiet**, the UI exposed exactly eight pets, and the pet rendered transparently.
Escape dismissal and Settings restoration were proven on the same packaged runtime in
the preceding pass. Windows Security then displayed a Node-automation prompt and blocked
the final all-eight playback and Alt+F4 replay. Do not turn those uncompleted replays
into screenshots, captions, or voiceover claims.

No final submission video has been recorded. The live Codex + Strands receipts remain
bound to `5c49c10eaed4ad96346ceef8d2eb257e46fcd425`, AgentCore remains undeployed, and
PexBench remains unfrozen. The next judge-facing asset must show the packaged native app
and clearly separate current package proof from the earlier live pair.

The August stills and `companion.webm` are pre-redesign references. **Do not use them on
Devpost.** The recorder below drives headless Chromium against Vite, so its output is a
layout reference only—not native Tauri, packaged-app, live-worker, or submission proof.

The current judge-facing evidence summary is
[`evidence/LIVE_CODEX_STRANDS_2026-09-06.md`](evidence/LIVE_CODEX_STRANDS_2026-09-06.md).
Before submission, record a fresh native Tauri video showing both validated behaviors:
evidence-supported restraint and same-thread recovery. Upload the reviewed video to
YouTube or Vimeo (maximum five minutes). Voiceover: [`docs/SUBMISSION.md`](../SUBMISSION.md).

The curated live receipt is tied to `5c49c10`; it does not prove live behavior on final
revision `f99fe43`, AgentCore, a frozen benchmark, a leaderboard rank, or the independent-
verifier tier. Package integrity is separately proven by the checkpoint above. Current
source has exactly eight built-in pets; older August assets remain stale even where they
happen to depict those pets.

Regenerate:

```bash
uv run --no-project --with playwright python apps/desktop/scripts/record_submission_demo.py
```

The recorder must use `http://localhost:1420` on this machine (`127.0.0.1:1420` does not
bind). Its current output names are `01-compact.png`, `02-inspector.png`, six Deck frames,
and `09-settings.png` under `docs/demo/ui-reference/`.
