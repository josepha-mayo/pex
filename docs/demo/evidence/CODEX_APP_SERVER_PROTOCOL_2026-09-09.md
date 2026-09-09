# Installed Codex App Server protocol smoke — 9 September 2026

PEX's production `CodexStdioTransport` was exercised against the installed Codex binary in a
bounded, read-only protocol smoke.

## Result

- Binary: `codex-cli 0.153.4`
- Binary SHA-256: `E5AA76D19C7C94E2E9EF9B707D590206A73AC0E97C8DDC8382181242494BEF75`
- Transport: fixed-argv `codex app-server --listen stdio://`
- `initialize`: returned a valid object with `platformOs: windows`; transport reached
  `initialized: true`
- `initialized` notification: sent by the production transport
- `thread/list`: returned the documented `data` list shape with the requested limit of one
- Shutdown: `CodexStdioTransport.close()` stopped the owned child; the postcondition was
  `_proc is None` and `initialized: false`
- Probe script: deleted after completion and verified absent

The command exited 0. No thread was created, resumed, edited, or started; no turn or model call
ran; no native PEX window, Cursor process, OpenCode process, AWS resource, or paid provider was
used. The receipt intentionally records only response shape and count, not private thread data.

## Claim boundary

This proves the installed Codex version interoperates with PEX's real App Server initialization,
bounded discovery, and owned-process shutdown path. It does not replace the retained live
same-thread recovery proof, demonstrate attachment to the user's current Codex desktop task,
clear the benchmark isolation gate, or prove native PEX stability.
