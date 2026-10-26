# Standalone managed transport — offline candidate checkpoint

Published 2026-10-26 as a separate source lane, not an integration or deployment.

- New standalone source; does not replace PEX root application source.
- 149 authored offline tests pass; Ruff lint/format pass. Tests use synthetic data and non-routable fixture hosts.
- Direct HTTPX, one buffered text-only request design; in-memory receipts only.
- Public live invocation is denied. No provider, model, account, paid job, credentials or real inference was used for this qualification.
- No Strands tools, durable budget integration, live accounting validation or app integration is claimed.
- Historical PEX reconstruction is not full missing V14 recovery. This checkpoint does not restore that missing source.
- Source and selected text evidence only; no secrets, environment files, dependency bytes, runtime databases, screenshots, browser state, private benchmark answers or raw HTTP headers.

The repository root and existing branches remain unchanged. This lane is retained for review and continuation, not release readiness.
