# Web-owner core — preflight API checkpoint

Standalone core has33 passing synthetic tests with zero network attempts and lint/format passing. This increment adds a locked request-boundary preflight method for a future bounded-body HTTP adapter; it grants no authentication and must be rechecked after awaits. Preflight-specific HTTP tests and routes are not yet implemented.

Configuration revocation and stable reload-CSRF behavior remain tested. No real verifier provisioning, environment loading, browser UI, actual TLS/proxy boundary, WebSocket lifecycle, provider call or deployment is qualified. Native bearer/MCP/hook lanes and model-only deny-all remain unchanged. Still unwired/non-deployable.
