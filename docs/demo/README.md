# Demo assets

The August stills and `companion.webm` are pre-redesign references. **Do not use them on
Devpost.** The recorder below drives headless Chromium against Vite, so its output is a
layout reference only—not native Tauri, packaged-app, live-worker, or submission proof.

The current judge-facing evidence summary is
[`evidence/LIVE_CODEX_STRANDS_2026-09-06.md`](evidence/LIVE_CODEX_STRANDS_2026-09-06.md).
Before submission, record a fresh native Tauri video showing both validated behaviors:
evidence-supported restraint and same-thread recovery. Upload the reviewed video to
YouTube or Vimeo (maximum five minutes). Voiceover: [`docs/SUBMISSION.md`](../SUBMISSION.md).

Regenerate:

```bash
uv run --no-project --with playwright python apps/desktop/scripts/record_submission_demo.py
```

The recorder must use `http://localhost:1420` on this machine (`127.0.0.1:1420` does not
bind). Its current output names are `01-compact.png`, `02-inspector.png`, six Deck frames,
and `09-settings.png` under `docs/demo/ui-reference/`.
