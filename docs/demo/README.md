# Demo stills

Recorded against the live local bridge (`127.0.0.1:7420`) and Vite companion (`localhost:1420`).

Current UI: home roster, Ask PEX, Settings page. Stills `01-home.png` … `05-home-return.png`. Video: `companion.webm`.

Use these on Devpost. Screen-record a live Cursor or Codex session on top, then upload that combined video to YouTube/Vimeo (max 5 minutes). Voiceover: [`docs/SUBMISSION.md`](../SUBMISSION.md).

Regenerate:

```bash
uv run --no-project --with playwright python apps/desktop/scripts/record_submission_demo.py
```

The recorder must use `http://localhost:1420` on this machine (`127.0.0.1:1420` does not bind).
