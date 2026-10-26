# Web-owner core — test-first WIP

The standalone core remains unwired and not deployable. Synthetic stdlib tests:33 total,27 passed,1 failure and5 missing-contract errors. The six red cases specify immutable/revoking reconfiguration and stable reload-recoverable CSRF; their core implementation is the next increment. No HTTP routes, UI, real TLS/proxy or active WebSocket lifecycle is qualified.

Only authored fixture verifier/tokens and fake clock are used. No real credentials, environment loading, provider/network calls or deployment. Existing native bearer/MCP/hook lanes and model-only deny-all are unchanged. Do not use this as a public owner boundary.
