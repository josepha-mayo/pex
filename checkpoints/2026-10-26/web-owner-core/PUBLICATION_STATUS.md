# WIP: standalone owner authentication

The core has 33 passing synthetic unit tests. This checkpoint adds an unwired, auth-only ASGI factory with exact login/session/logout routes. HTTP behavior tests have not yet run. AST and lint checks were reported for the new file; no browser, TLS/proxy, server integration or deployment qualification exists. No provider calls or real credentials. This delta is not a self-contained app, not recovery of lost latest source, and grants no worker or private-data authority.

HTTP source SHA256: d622fceade9a24fafb95d1b6ce7204753e317811126e36b41e04588b81290883
