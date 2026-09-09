# Installed OpenCode HTTP protocol smoke — 9 September 2026

The installed OpenCode CLI and PEX's production HTTP adapter were exercised in a bounded,
read-only protocol smoke.

## Result

- OpenCode version: `1.18.29`
- Server: `opencode serve --hostname 127.0.0.1 --port 4097`
- `GET /global/health`: `healthy: true`
- PEX transport: production `LiveHttpTransport`, not the in-memory test double
- PEX adapter: production `OpenCodeAdapter.discover_sessions()`
- Discovery: 100 returned sessions were accepted and every canonical PEX ID exactly matched
  `opencode:<vendor_session_id>`
- SSE: production `start_pipeline_pump()` connected `/global/event`; the pump remained running
  with no retained-event gap and no pump error
- Runtime capability: `support_label: deep`, `observe_messages: true`, `send_message: true`,
  and `permission_response_mode: async`
- Shutdown: the owned CLI process was stopped; no listener remained on port 4097
- Cleanup: the isolated empty probe directory and script were removed and verified absent

The server warned that no password was set. It was bound only to loopback for this temporary
read-only smoke and was terminated immediately after discovery. No session details, titles,
messages, prompts, or credentials were printed or retained.

## Claim boundary

This proves real OpenCode health, bounded session discovery, and a healthy SSE supervision pump
through PEX's production HTTP transport. It does not claim the optional PEX plugin was live, a
prompt/correction or permission response was delivered, a model ran, or OpenCode participated
in the four-arm benchmark. No native PEX window, Cursor process, AWS resource, or paid provider
was used.
