# Footage manifest — storyboard beats to captured assets

The final cut follows `DEMO_SCRIPT.md` (cold-open on the claim ledger, the
catch, durable ruling, positive control, pack verify, platform close — under
three minutes). This manifest maps each beat to the asset that satisfies it so
assembly is mechanical. Every clip is captured from the live local UI
(vite + demo bridge, `scripts/demo.py`), not a mock frame — replay clips are
labeled `not_live_control` inside the product itself.

## Beat map

| # | Beat (script) | Asset | Source capture |
|---|----------------|-------|----------------|
| 1 | Cold open — claim ledger: "All tests passed" → contradicted, same words → supported | `assets/pex-claim-ledger-a6ada5f.mp4` (43 s, trim to ~15 s: ledger rows ~22–38 s) | `apps/desktop/scripts/capture-claim-ledger.mjs` — `premature_stop_eval` replay |
|   | still alternative | `assets/pex-verdict-card.png` | `capture-verdict-png.mjs` |
| 2 | The catch — config-injection / reward hack | `assets/pex-config-injection-27d95bd.mp4` | `capture-config-injection.mjs` |
|   | still: the diff PEX caught | `assets/pex-injection-diff.png` | `capture-config-injection.mjs` |
| 3 | Worker → PEX MCP escalation | `assets/pex-escalation-arc-6d16888.mp4` | `capture-escalation.mjs` |
|   | still alternative | `assets/pex-escalation-ruling-58d8c3a.png` | `capture-escalation.mjs` |
|   | MCP tool-call eval overlay | `assets/pex-mcp-eval.mp4` | `capture-mcp-eval.mjs` |
| 4 | Durable human ruling (centerpiece) | `assets/pex-ruling-arc-eabd646.mp4` | `capture-ruling-arc.mjs` |
|   | stills: ledger row + context | `assets/pex-ledger-ruling-audit.png`, `assets/pex-ledger-ruling-context.png` | `capture-ledger-ruling.mjs` |
| 5 | Positive control — verified complete | `assets/pex-replay-walkthrough-b28d999.mp4` (tail) | `capture-walkthrough.mjs` |
| 6 | Offline pack verification | `assets/pex-pack-verify-browser.png` (still) or a fresh terminal capture of `uv run python scripts/verify_pack.py` | `capture-pack-verify.mjs` |
| 7 | Judge arc overview / suite | `assets/pex-judge-arc-597ce13.mp4` | `capture-judge-arc.mjs` |
| 8 | Close — Nebius Token Factory × NVIDIA Nemotron card | title card over `pex-mark.svg`; URLs: `api.tokenfactory.nebius.com/v1`, model `nvidia/nemotron-3-super-120b-a12b` | static — script end-card |
| 9 | Live worker self-escalation (2026-10-15 run) | `assets/pex-live-escalation-2026-10-15.mp4` | `capture-live-escalation.mjs` — real OpenCode worker read the tamper task, escalated via `pex.request_decision` quoting the sealed forbidden outcome; ruling recorded durably (`session_terminal` delivery, honest) |

## Supporting stills (cutaways / thumbnails)

- `pex-claim-timeline-fa8d76e.png` — Inspector claim timeline on a live capture
- `pex-live-escalation-inspector-2026-10-15.png` — LIVE WORKER chip + "I should
  not proceed with the forbidden…" + 7 `pex.*` calls + honest "delivery failed"
- `pex-live-opencode-tamper-b21b51d.png` / `pex-live-tamper-demo.mp4` — live
  OpenCode tamper catch (use for the "real worker" proof beat)
- `pex-live-handoff-d02df03.png` — sealed-source handoff affordance
- `pex-goals-registry.png` / `pex-goal-lineage.png` — durable intent lineage
- `pex-decisions-ask-human-37a512b.png` — decision queue

## Re-capture checklist (before final cut)

- Re-run `capture-claim-ledger.mjs` if the eyebrow copy changed — committed
  code now renders the fixture title, not the raw id.
- Confirm the verdict card shows `worker_pex_calls` chips (metadata merge fix).
- Keep every clip ≤ 40 s raw; the cut needs ~160 s total of footage for a
  sub-three-minute finish with narration room.
