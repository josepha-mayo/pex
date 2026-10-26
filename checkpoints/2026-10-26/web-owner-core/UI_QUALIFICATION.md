# Owner web shell qualification

2026-10-26 23:29 UTC. Source checkpoint d20bac5dc7d8e3b10fa5e8fb7e033d9bc6d79d37. All13 selected source blobs were matched to the remote tree by Git identity and byte size.

## Verified

- Full frontend npm test:475 passing tests, zero failures. This comprises453 pre-existing tests plus22 owner tests (15 controller and7 built-page DOM tests). TypeScript check and isolated Vite owner build pass.
- Python owner boundary remains33 core +16 authored ASGI tests passing with zero network attempts; all4 Python files lint/format clean. Parent independently reran49. These are independent of frontend tests.
- Isolated dark responsive shell does not mount the historical desktop App, replay entry, provider settings or Origin-rewriting proxy. Login/session/logout are the only client routes, same-origin cookies, redirects refused, no-store, one attempt. No bearer, cookie or CSRF is persisted in browser storage.
- Authored controller and built-production-JS DOM tests verify credential field clearing, login/reload/logout, rejection of malformed/oversized replies, no duplicate clicks/retry, generation-scoped abort and stale-response suppression, uncertain logout's locked state, pagehide/bfcache/visibility revalidation, and expiry hiding. The workspace explicitly says it is not connected to agent data/control.
- Found and corrected a pre-JavaScript fallback risk: owner input starts disabled and the form explicitly uses POST, never default query-string submission.
- Parent review found response-arrival-based expiry could overstate display lifetime. Corrected to request-start plus TTL minus a one-second rounding margin; expired-on-arrival or backward-clock replies cannot reveal the workspace. This is a conservative UI lease, not a replacement for server authorization.
- Exact43-character validation rejects trailing-newline owner/CSRF values.

## Reproduce

From apps/desktop with the unchanged locked dependencies installed: npm run test:owner. The full npm test command explicitly includes it. npm run build:owner creates dist-owner only. The tests execute the built HTML and JS through linkedom with authored fetch responses, not a real browser.

From repository root with PYTHONPATH=services/bridge/src: run Python directly on tests/unit/test_web_owner_auth.py and tests/unit/test_web_owner_http.py to activate their network-audit hooks.

## Limits

Actual HTTP-only desktop and393px iframe visual checks are recorded separately in BROWSER_QUALIFICATION.md. No HTTPS/TLS/proxy qualification, actual owner credential, provider call, payment, worker-plus-supervisor benchmark or deployment. The UI and auth-only ASGI are not mounted into a production service. No private data or worker capability is available. The source remains a delta on a reconstructed historical baseline, not recovered latest code or a self-contained app. No claims from earlier lost source transfer to these bytes.

Built artifacts are identified in BUILD_SHA256.json but deliberately not pushed. Prior pre-expiry HTML/JS hashes are superseded. Local same-process static HTTP served earlier build artifacts with200 and exact bytes; cross-command listener reachability was not established. Final browser handoff must verify current build hashes and use its supported local serving route. HTTP preview should show HTTPS-required/unavailable with no auth requests. A mocked successful browser flow must be labeled authored simulation, never real authentication or TLS.

