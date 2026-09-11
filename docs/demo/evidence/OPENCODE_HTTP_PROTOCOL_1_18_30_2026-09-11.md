# Installed OpenCode 1.18.30 protocol smoke — 11 September 2026

The installed OpenCode CLI and PEX production HTTP/SSE adapter were exercised
against an isolated loopback server. This was a model-free protocol check.

## Result

- Installed OpenCode: `1.18.30`.
- Server: `opencode serve --hostname 127.0.0.1 --port 4097` in an empty probe
  directory.
- PEX transport: production `LiveHttpTransport`, not the memory test double.
- PEX adapter: production `OpenCodeAdapter` health/session/SSE path.
- The corrected live contract passed once, then passed five consecutive reruns:
  0.94s, 0.87s, 0.87s, 0.92s and 0.96s.
- After extending cleanup to cover every assertion path, the final exact live
  rerun passed in 1.91s and Ruff remained clean.
- The adapter progressed from Strong after HTTP session discovery to Deep after
  the `/global/event` SSE stream connected.
- Ruff passed for the changed contract.
- The owned server was stopped, no listener remained on port 4097, and the empty
  probe directory was removed.

## Failure and repair boundary

The prior live contract started the asynchronous SSE pump and asserted Deep on
the immediately following probe. OpenCode 1.18.30 exposed that scheduler race
twice: HTTP/session discovery returned Strong before the SSE task had connected.
The product adapter was not changed. The contract now waits at most five seconds
for the actual Deep condition and explicitly closes the production transport in
cleanup. If the stream cannot connect, the bounded wait still fails rather than
turning Strong into a false pass.

## Claim boundary

This proves installed-version health, session discovery and SSE capability
negotiation. It did not create or mutate a worker session, send a prompt, invoke
a model or supervisor, read a BYOK key, deploy AgentCore, access AWS, run a
benchmark arm, or launch the native PEX UI.
