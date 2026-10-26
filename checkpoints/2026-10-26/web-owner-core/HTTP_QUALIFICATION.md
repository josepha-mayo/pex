# Owner-auth HTTP qualification: authored local tests only

2026-10-26 23:09 UTC. Source checkpoint 14f84b8b757d2a8d790f00564927a44b08146d37.

The standalone auth-only ASGI factory passes 16 authored in-process event tests. The session core passes 33 tests. Both ran with cleared environment and network audit hooks: zero DNS/connect/send attempts. All four source/test files pass Ruff check and format check. The parent independently reran the combined 49 tests successfully; this is not a browser or TLS test.

Coverage: login, cookie-only opaque session transport, stable-CSRF session reload without renewal, logout/replay refusal; pre-body exact Host/Origin/HTTPS and duplicate checks; exact route inventory and WebSocket refusal; strict JSON and content headers; declared versus streamed body length; byte/event/time bounds and disconnect; configuration revocation and expiry during body awaits; rejection of authenticated request bodies. No source behavior fixes were needed in this HTTP phase. Test formatting/import order was corrected in separate checkpoints.

Reproduce from the reviewed historical base with this delta applied: set PYTHONPATH=services/bridge/src, then run Python on tests/unit/test_web_owner_http.py and tests/unit/test_web_owner_auth.py. These direct entry points install the network audit hook. Python 3.12 is required for asyncio.timeout.

Limits: no real credentials, no HTTP listener, browser, proxy or TLS qualification, no app/UI wiring, no private-data routes, no WebSocket authority, no providers or model calls, no production deployment. This delta is not a self-contained app or recovered latest source. The in-memory session store revokes on restart. Production model-only admission remains deny-all. A real owner verifier must not be provisioned merely to run these tests.
