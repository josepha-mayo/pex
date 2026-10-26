# Web-owner core — locally tested, still unwired

Standalone stdlib core:33/33 synthetic tests pass with zero network attempts; lint/format pass. Configuration is read-only; actual reconfiguration revokes all sessions under the shared lock. Authenticated status can recover stable session-bound CSRF without exposing the opaque cookie token, rotating sibling-tab CSRF or extending expiry.

No HTTP routes, UI, actual TLS/proxy or active WebSocket lifecycle is implemented or qualified. Only authored verifier/tokens/fake clock were used. No real credentials, environment loading, provider calls or deployment. Existing native bearer/MCP/hook lanes and model-only deny-all are unchanged. This is not a public-ready web boundary or recovered full V14.
