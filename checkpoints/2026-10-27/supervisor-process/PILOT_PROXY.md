# Pilot-only platform CONNECT qualification
2026-10-27 12:44 UTC. Source 7d0496f2; tests adc8f7ca.

Only the independently SHA-bound private pilot config may select optional
platform_proxy with proxy_sha256, ca_path, ca_sha256. The value of supplied
HTTPS_PROXY is never persisted in source. SSL_CERT_FILE path and bytes must match.
The clean controller launcher must preserve those two selected platform variables.
No environment-only production activation exists.

The exact approved US HTTPS chat endpoint retains its original hostname for
normal proxy CONNECT and verified TLS SNI. Explicit SSLContext uses the pinned
platform CA. trust_env=False, retries=0, redirect following=False. Exact
method/headers/body/model/output/credential checks remain. Default transport
still resolves and pins public origin IPs directly. Budget accounting is unchanged.

7 authored proxy tests and 416 combined local/authored tests passed (5.33s).
Credential-free GET to the exact US /v1/chat/completions endpoint returned HTTP405
using this explicit transport; no Authorization header, model POST, inference,
sandbox or payment was involved. This qualifies connectivity, not a benchmark.

Changed proxy/CA/path/digest or other endpoint refuses admission. The request
transport validates the selected identities before HTTP dispatch. Root must
regenerate source/config bindings and independently validate readiness, and the
recording GO remains separate. Existing historical tests are not a live claim.
